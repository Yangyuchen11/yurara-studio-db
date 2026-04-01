from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import date
from models import Product, InventoryLog, ProductColor, CompanyBalanceItem, CostItem, FinanceRecord, Warehouse
from constants import PRODUCT_COST_CATEGORIES, AssetPrefix, BalanceCategory, Currency, StockLogReason, FinanceCategory

class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.COST_CATEGORIES = PRODUCT_COST_CATEGORIES

    # ================= 1. 核心底座：大货资产与单价动态同步 =================
    def sync_product_metrics(self, product_id):
        """核心计算引擎：根据最新状态动态推导单价、大货资产以及在制资产(WIP)抵扣"""
        prod = self.db.query(Product).filter(Product.id == product_id).first()
        if not prod: return
        
        # 1. 计算在成本中消耗的数量 (仅限成套消耗)
        consumed_qty = 0
        logs = self.db.query(InventoryLog).filter(
            InventoryLog.product_name == prod.name,
            InventoryLog.reason == StockLogReason.OUT_STOCK,
            InventoryLog.part_name == None
        ).all()
        for l in logs:
            if l.note and "消耗" in l.note:
                consumed_qty += abs(l.change_amount)
                
        # 2. 动态计算预计可销售数量
        stats = self.get_stock_overview_by_parts(prod.id, prod.name)
        if prod.is_production_completed:
            base_qty = sum(s.get("produced", 0) for s in stats.values())
        else:
            base_qty = prod.total_quantity
            
        prod.marketable_quantity = max(0, base_qty - consumed_qty)
        
        # 3. 重新计算单价
        total_cost = self.db.query(func.sum(CostItem.actual_cost)).filter(CostItem.product_id == prod.id).scalar() or 0.0
        unit_cost = total_cost / prod.marketable_quantity if prod.marketable_quantity > 0 else 0.0
        
        # 4. 实时更新大货资产 (实库存 * 最新单价)
        actual_stock = sum(s.get("actual", 0) for s in stats.values())
        asset_name = f"{AssetPrefix.STOCK}{prod.name}"
        asset_val = actual_stock * unit_cost
        
        item = self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name == asset_name, 
            CompanyBalanceItem.category == BalanceCategory.ASSET
        ).first()
        
        if asset_val > 0.01:
            if item:
                item.amount = asset_val
            else:
                self.db.add(CompanyBalanceItem(
                    name=asset_name, amount=asset_val, category=BalanceCategory.ASSET, 
                    currency=Currency.CNY, asset_type="资产"
                ))
        else:
            if item and not item.finance_record_id:
                self.db.delete(item)
                
        # 5. ✨ 实时动态核算在制资产冲销 (WIP_OFFSET)
        if prod.is_production_completed:
            # 如果已经生产完成，100% 抵扣成本（清零在制资产）
            wip_offset_val = -total_cost
        else:
            # 尚未生产完成时，根据已验收完成入库的数量（按比例）抵扣在制资产
            produced_qty = sum(s.get("produced", 0) for s in stats.values())
            wip_offset_val = -(produced_qty * unit_cost)
            
        offset_name = f"{AssetPrefix.WIP_OFFSET}{prod.name}"
        offset_item = self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name == offset_name,
            CompanyBalanceItem.category == BalanceCategory.ASSET
        ).first()
        
        if abs(wip_offset_val) > 0.01:
            if offset_item:
                offset_item.amount = wip_offset_val
            else:
                self.db.add(CompanyBalanceItem(
                    name=offset_name, amount=wip_offset_val, category=BalanceCategory.ASSET, 
                    currency=Currency.CNY, asset_type="资产"
                ))
        else:
            if offset_item and not offset_item.finance_record_id:
                self.db.delete(offset_item)
                
        self.db.flush()

    # ================= 2. 基础获取 =================
    def get_all_products(self):
        return self.db.query(Product).all()

    def get_product_colors(self, product_id):
        return self.db.query(ProductColor).filter(ProductColor.product_id == product_id).order_by(ProductColor.id.asc()).all()

    def get_recent_logs(self, product_name=None, limit=100):
        query = self.db.query(InventoryLog)
        if product_name:
            query = query.filter(InventoryLog.product_name == product_name)
        return query.order_by(InventoryLog.id.desc()).limit(limit).all()

    # ================= 3. 仓库管理 =================
    def get_all_warehouses(self):
        return self.db.query(Warehouse).all()
        
    def add_warehouse(self, name, remarks):
        if self.db.query(Warehouse).filter(Warehouse.name == name).first():
            raise ValueError("仓库名称已存在")
        self.db.add(Warehouse(name=name, remarks=remarks))
        self.db.commit()
        
    def delete_warehouse(self, warehouse_id):
        details = self.get_warehouse_inventory_details()
        w_data = details.get(warehouse_id)
        if w_data:
            for p, v_dict in w_data["stock"].items():
                for v, pt_dict in v_dict.items():
                    for pt, qty in pt_dict.items():
                        if qty > 0:
                            raise ValueError(f"仓库中仍有存货 ({p}-{v}-{pt}: {qty})，无法删除")
        wh = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if wh:
            self.db.delete(wh)
            self.db.commit()

    def get_warehouse_inventory_details(self):
        warehouses = self.db.query(Warehouse).all()
        logs = self.db.query(InventoryLog).all()
        
        wh_dict = {w.id: {"name": w.name, "stock": {}} for w in warehouses}
        wh_dict[None] = {"name": "未分配仓库", "stock": {}} 

        products = self.db.query(Product).all()
        req_map = {} 
        for prod in products:
            req_map[prod.name] = {}
            for c in prod.colors:
                req_map[prod.name][c.color_name] = {p.part_name: p.quantity for p in c.parts} if c.parts else {"整套": 1}

        for l in logs:
            w_id = l.warehouse_id
            if w_id not in wh_dict: continue

            if l.reason not in [StockLogReason.INSPECT_COMPLETED, StockLogReason.OTHER_IN, StockLogReason.OUT_STOCK, StockLogReason.IN_STOCK, StockLogReason.RETURN_IN, StockLogReason.TRANSFER]:
                continue

            delta = l.change_amount
            p_name = l.product_name
            v_name = l.variant
            
            if p_name not in wh_dict[w_id]["stock"]: wh_dict[w_id]["stock"][p_name] = {}
            if v_name not in wh_dict[w_id]["stock"][p_name]: wh_dict[w_id]["stock"][p_name][v_name] = {}

            if l.part_name:
                parts_delta = [(l.part_name, delta)]
            else:
                parts_req = req_map.get(p_name, {}).get(v_name, {"整套": 1})
                parts_delta = [(pt, delta * req) for pt, req in parts_req.items()]

            for pt, d in parts_delta:
                wh_dict[w_id]["stock"][p_name][v_name][pt] = wh_dict[w_id]["stock"][p_name][v_name].get(pt, 0) + d

        return wh_dict

    # ================= 4. 部件维度的整体库存计算 =================
    def get_stock_overview_by_parts(self, product_id, product_name):
        product = self.db.query(Product).filter(Product.id == product_id).first()
        logs = self.db.query(InventoryLog).filter(InventoryLog.product_name == product_name).all()

        stats = {}
        for c in product.colors:
            v_name = c.color_name
            parts_req = {p.part_name: p.quantity for p in c.parts}
            if not parts_req:
                parts_req = {"整套": 1}

            part_actual = {p: 0 for p in parts_req}
            part_inspecting = {p: 0 for p in parts_req}
            part_produced = {p: 0 for p in parts_req}

            v_logs = [l for l in logs if l.variant == v_name]
            for l in v_logs:
                delta = l.change_amount
                l_parts = []
                if l.part_name and l.part_name in parts_req:
                    l_parts = [(l.part_name, delta)]
                elif not l.part_name: 
                    l_parts = [(p, delta * req) for p, req in parts_req.items()]

                for p, d in l_parts:
                    if l.reason == StockLogReason.IN_INSPECT:
                        part_inspecting[p] += d
                    elif l.reason == StockLogReason.INSPECT_COMPLETED:
                        part_inspecting[p] -= d
                        part_actual[p] += d
                        part_produced[p] += d 
                    elif l.reason == StockLogReason.OUT_STOCK:
                        part_actual[p] += d   
                    elif l.reason in [StockLogReason.OTHER_IN, StockLogReason.IN_STOCK, StockLogReason.RETURN_IN, StockLogReason.TRANSFER]:
                        part_actual[p] += d
                        if l.reason == StockLogReason.IN_STOCK:
                            part_produced[p] += d

            def calc_sets(pool):
                if not parts_req: return 0
                return min(max(0, pool[p]) // req for p, req in parts_req.items()) if pool else 0

            actual_sets = calc_sets(part_actual)
            inspecting_sets = calc_sets(part_inspecting)
            produced_sets = calc_sets(part_produced)

            excess = {}
            for p, req in parts_req.items():
                exc = part_actual[p] - (actual_sets * req)
                if exc > 0:
                    excess[p] = exc

            stats[v_name] = {
                "planned": c.quantity,
                "produced": produced_sets,
                "inspecting": inspecting_sets,
                "actual": actual_sets,
                "excess": excess
            }
        return stats

    # ================= 5. 库存变动提交 =================
    def add_inventory_movement(self, product_id, product_name, variant, quantity, 
                               move_type, date_obj, remark, warehouse_id=None, to_warehouse_id=None, 
                               is_set=True, part_name=None,
                               out_type=None, cons_cat=None, cons_content=None):
        
        target_prod_obj = self.db.query(Product).filter(Product.id == product_id).first()
        actual_change_amt = -quantity if move_type == StockLogReason.OUT_STOCK else quantity

        if move_type == StockLogReason.TRANSFER:
            if warehouse_id == to_warehouse_id:
                raise ValueError("移出仓库和移入仓库不能相同！")
            
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=-quantity,
                reason=StockLogReason.TRANSFER, note=f"移出至某仓 | {remark}", date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.TRANSFER, note=f"从某仓移入 | {remark}", date=date_obj,
                warehouse_id=to_warehouse_id, part_name=None if is_set else part_name
            ))
            msg = "库存移动成功（生成一进一出两笔记录）"

        elif move_type == StockLogReason.OUT_STOCK:
            if out_type == "消耗" and target_prod_obj and is_set:
                new_cost = CostItem(
                    product_id=product_id, item_name=cons_content, actual_cost=0, supplier="", category=cons_cat,      
                    unit_price=0, quantity=0, unit="", remarks=f"款式:{variant} 数量:{quantity} | {remark}"
                )
                self.db.add(new_cost)

            log_note = f"消耗: {cons_content} | {remark}" if out_type == "消耗" else f"出库: {remark}"
            
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=actual_change_amt,
                reason=StockLogReason.OUT_STOCK, note=log_note, is_other_out=True, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            msg = "出库成功"

        elif move_type == StockLogReason.IN_INSPECT:
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.IN_INSPECT, note=remark, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            msg = "入库验收已录入"

        elif move_type == StockLogReason.INSPECT_COMPLETED:
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.INSPECT_COMPLETED, note=remark, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            msg = "验收完成入库已录入"
            
        elif move_type == StockLogReason.OTHER_IN:
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.OTHER_IN, note=remark, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            msg = "其他入库已录入"
        else:
            msg = "未知操作类型"

        self.db.flush()
        # ✨ 底层拦截一切物理操作，进行统一重算
        self.sync_product_metrics(product_id)
        return msg

    def commit(self):
        self.db.commit()

    # ================= 6. 日志修改与删除 =================
    def update_logs_batch(self, changes):
        has_change = False
        for log_id, diff in changes.items():
            target_log = self.db.query(InventoryLog).filter(InventoryLog.id == log_id).first()
            if target_log:
                if "日期" in diff:
                    new_d = diff["日期"]
                    if hasattr(new_d, 'date'): new_d = new_d.date()
                    target_log.date = new_d
                    has_change = True
                if "详情" in diff:
                    target_log.note = diff["详情"]
                    has_change = True
        if has_change:
            self.db.commit()
        return has_change

    def delete_log_cascade(self, log_id):
        log_to_del = self.db.query(InventoryLog).filter(InventoryLog.id == log_id).first()
        if not log_to_del: raise ValueError("记录不存在")

        msg_list = []
        target_prod = self.db.query(Product).filter(Product.name == log_to_del.product_name).first()
        is_set = (log_to_del.part_name is None)

        is_consumable_out = (log_to_del.reason == StockLogReason.OUT_STOCK and "消耗" in (log_to_del.note or ""))
        if is_consumable_out and target_prod and is_set:
            try:
                content_part = log_to_del.note.split("|")[0].replace("消耗:", "").strip()
                target_cost = self.db.query(CostItem).filter(
                    CostItem.product_id == target_prod.id,
                    CostItem.actual_cost == 0,
                    CostItem.item_name.like(f"%{content_part}%")
                ).first()
                if target_cost: 
                    self.db.delete(target_cost)
                    msg_list.append("关联消耗成本记录已删除")
            except: pass

        if log_to_del.reason == StockLogReason.OUT_STOCK and log_to_del.is_sold:
            target_fin = self.db.query(FinanceRecord).filter(
                FinanceRecord.date == log_to_del.date,
                FinanceRecord.amount == log_to_del.sale_amount,
                FinanceRecord.category == FinanceCategory.SALES_INCOME,
                FinanceRecord.description.like(f"%{log_to_del.product_name}%")
            ).first()
            if target_fin:
                cash_name = f"{AssetPrefix.CASH}({log_to_del.currency})"
                cash_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == cash_name).first()
                if cash_item: cash_item.amount -= target_fin.amount
                self.db.delete(target_fin)
                msg_list.append("销售流水已回滚")
                    
        elif log_to_del.reason == StockLogReason.TRANSFER:
            msg_list.append("单条移动记录已删除（移入/移出为两条记录）")

        self.db.delete(log_to_del)
        self.db.flush()

        if target_prod:
            self.sync_product_metrics(target_prod.id)
            msg_list.append("大货资产及在制资产重算完成")

        self.db.commit()
        return " | ".join(msg_list) if msg_list else "日志已删除"

    # ================= 7. 在制资产检测 =================
    def get_wip_balance(self, product_id):
        from services.cost_service import CostService
        cost_service = CostService(self.db)
        current_offset = cost_service.get_wip_offset(product_id)
        all_items = self.db.query(CostItem).filter(CostItem.product_id == product_id).all()
        current_total_cost = sum([i.actual_cost for i in all_items])
        return current_total_cost + current_offset

    def clear_wip_for_product(self, product_id):
        from services.cost_service import CostService
        cost_service = CostService(self.db)
        cost_service.perform_wip_fix(product_id)
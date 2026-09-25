# services/inventory_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import date
from models import Product, InventoryLog, ProductColor, CompanyBalanceItem, CostItem, FinanceRecord, Warehouse, ConsignmentItem
from constants import PRODUCT_COST_CATEGORIES, AssetPrefix, BalanceCategory, Currency, StockLogReason, FinanceCategory

class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.COST_CATEGORIES = PRODUCT_COST_CATEGORIES

    # ================= 1. 核心底座：大货资产与单价动态同步 =================
    def sync_product_metrics(self, product_id):
        prod = self.db.query(Product).filter(Product.id == product_id).first()
        if not prod: return
        
        # 1. 完整库存快照（含所有物理变动，用于大货资产 & 在制核算）
        stats = self.get_stock_overview_by_parts(prod.id, prod.name)
        actual_assemblable = sum(s.get("actual", 0) for s in stats.values())
        produced_sets = sum(s.get("produced", 0) for s in stats.values())

        # 2. 消耗专用快照：OUT_STOCK 仅纳入标记"消耗"的记录，排除售出
        #    利用木桶原理让模拟自然计算出消耗后实际能组装的套数，
        #    彻底避免手工比例折算带来的误差（散件多件配一套等复杂情况均正确处理）
        stats_cons = self.get_stock_overview_by_parts(prod.id, prod.name, consumption_only=True)
        assemblable_after_consumption = sum(s.get("actual", 0) for s in stats_cons.values())

        # 3. 计算 marketable_quantity（成本摊销分母）
        #    = 生产出来的套数里，去掉消耗后剩余可销售的部分
        #    售出不影响此分母（已售套数仍承担其成本份额）
        if prod.is_production_completed:
            # 已结单：消耗后可组装套数即为可销售分母
            prod.marketable_quantity = max(0, assemblable_after_consumption)
        else:
            # WIP：当前消耗后在库可组装 + 尚未入库的计划产量
            not_yet_produced = max(0, prod.total_quantity - produced_sets)
            prod.marketable_quantity = max(0, assemblable_after_consumption + not_yet_produced)

        total_cost = self.db.query(func.sum(CostItem.actual_cost)).filter(CostItem.product_id == prod.id).scalar() or 0.0
        unit_cost = total_cost / prod.marketable_quantity if prod.marketable_quantity > 0 else 0.0
        
        # 4. 实时更新大货资产 (实库存 * 最新单价)
        actual_stock = actual_assemblable  # 复用步骤 1 已计算的实际可组装套数
        asset_name = f"{AssetPrefix.STOCK}{prod.name}"
        asset_val = actual_stock * unit_cost
        
        # 获取所有可能的记录，准备自动清理重复的老数据
        items = self.db.query(CompanyBalanceItem).filter(
            or_(
                (CompanyBalanceItem.product_id == prod.id) & CompanyBalanceItem.name.like(f"{AssetPrefix.STOCK}%"),
                CompanyBalanceItem.name == asset_name
            ),
            CompanyBalanceItem.category == BalanceCategory.ASSET
        ).all()
        
        if asset_val > 0.01:
            if items:
                main_item = items[0]
                main_item.amount = asset_val
                main_item.name = asset_name 
                main_item.product_id = prod.id 
                
                for orphan in items[1:]:
                    self.db.delete(orphan)
            else:
                self.db.add(CompanyBalanceItem(
                    name=asset_name, amount=asset_val, category=BalanceCategory.ASSET, 
                    currency=Currency.CNY, asset_type="资产", product_id=prod.id
                ))
        else:
            for item in items:
                if not item.finance_record_id:
                    self.db.delete(item)
                
        # 5. 实时动态核算在制资产冲销 (WIP_OFFSET)
        if prod.is_production_completed:
            wip_offset_val = -total_cost
        else:
            wip_offset_val = -(produced_sets * unit_cost)
            
        offset_name = f"{AssetPrefix.WIP_OFFSET}{prod.name}"
        
        offset_items = self.db.query(CompanyBalanceItem).filter(
            or_(
                (CompanyBalanceItem.product_id == prod.id) & CompanyBalanceItem.name.like(f"{AssetPrefix.WIP_OFFSET}%"),
                CompanyBalanceItem.name == offset_name
            ),
            CompanyBalanceItem.category == BalanceCategory.ASSET
        ).all()
        
        if abs(wip_offset_val) > 0.01:
            if offset_items:
                main_offset = offset_items[0]
                main_offset.amount = wip_offset_val
                main_offset.name = offset_name 
                main_offset.product_id = prod.id 
                
                for orphan in offset_items[1:]:
                    self.db.delete(orphan)
            else:
                self.db.add(CompanyBalanceItem(
                    name=offset_name, amount=wip_offset_val, category=BalanceCategory.ASSET, 
                    currency=Currency.CNY, asset_type="资产", product_id=prod.id
                ))
        else:
            for offset_item in offset_items:
                if not offset_item.finance_record_id:
                    self.db.delete(offset_item)
                
        self.db.flush()

    # ================= 2. 基础获取 =================
    def get_all_products(self):
        return self.db.query(Product).all()

    def get_product_colors(self, product_id):
        return self.db.query(ProductColor).filter(ProductColor.product_id == product_id).order_by(ProductColor.id.asc()).all()

    def get_recent_logs(self, product_name=None, limit=None):
        query = self.db.query(InventoryLog)
        if product_name:
            query = query.filter(InventoryLog.product_name == product_name)
        query = query.order_by(InventoryLog.id.desc())
        if limit is not None:
            query = query.limit(limit)
        return query.all()

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

            if l.reason not in [StockLogReason.INSPECT_COMPLETED, StockLogReason.INSPECT_REVERSAL, StockLogReason.OTHER_IN, StockLogReason.OUT_STOCK, StockLogReason.IN_STOCK, StockLogReason.RETURN_IN, StockLogReason.TRANSFER, StockLogReason.REPAIR_IN]:
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
    def get_stock_overview_by_parts(self, product_id, product_name, consumption_only: bool = False):
        """
        按款式计算各部件维度的库存快照。
        consumption_only=True 时，OUT_STOCK 仅计入 note 含"消耗"的记录，
        排除售出和其他出库，用于正确计算 marketable_quantity。
        """
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
            part_repaired = {p: 0 for p in parts_req}

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
                    elif l.reason in [StockLogReason.INSPECT_COMPLETED, StockLogReason.INSPECT_REVERSAL]:
                        part_inspecting[p] -= d
                        part_actual[p] += d
                        part_produced[p] += d 
                    elif l.reason == StockLogReason.REPAIR_OUT:
                        loss_qty = abs(d)
                        part_inspecting[p] -= loss_qty
                        part_repaired[p] += loss_qty
                    elif l.reason == StockLogReason.REPAIR_IN:
                        in_qty = abs(d)
                        part_repaired[p] -= in_qty
                        part_actual[p] += in_qty
                        part_produced[p] += in_qty
                    elif l.reason == StockLogReason.OUT_STOCK:
                        # consumption_only 模式下，跳过非消耗出库（售出、其他）
                        if consumption_only and not (l.note and "消耗" in l.note):
                            continue
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
            repaired_sets = calc_sets(part_repaired)

            excess = {}
            parts_detail = []
            for p, req in parts_req.items():
                exc = part_actual[p] - (actual_sets * req)
                if exc > 0:
                    excess[p] = exc
                
                p_produced = part_produced[p]
                p_inspecting = part_inspecting[p]
                p_repaired = part_repaired[p]
                p_actual = part_actual[p]
                p_sets = max(0, p_actual // req) if req > 0 else 0
                parts_detail.append({
                    "part_name": p,
                    "req_qty": req,
                    "produced": p_produced,
                    "inspecting": p_inspecting,
                    "repaired": p_repaired,
                    "actual_qty": p_actual,
                    "calculable_sets": p_sets
                })

            stats[v_name] = {
                "planned": c.quantity,
                "produced": produced_sets,
                "inspecting": inspecting_sets,
                "repaired": repaired_sets,
                "actual": actual_sets,
                "excess": excess,
                "parts": parts_detail
            }
        return stats

    # ================= 5. 库存变动提交 =================
    def add_inventory_movement(self, product_id, product_name, variant, quantity, 
                               move_type, date_obj, remark, warehouse_id=None, to_warehouse_id=None, 
                               is_set=True, part_name=None,
                               out_type=None, cons_cat=None, cons_content=None,
                               consignment_shop=None):
        
        if quantity <= 0:
            raise ValueError("变动数量必须大于 0！")

        target_prod_obj = self.db.query(Product).filter(Product.id == product_id).first()
        if not target_prod_obj:
            raise ValueError(f"商品不存在 (ID: {product_id})")

        # ✨ 1. 验收完成入库 & 返修出库：严格防负数校验（校验入库验收中余量）
        is_repair_out = (move_type == StockLogReason.REPAIR_OUT)
        if move_type == StockLogReason.INSPECT_COMPLETED or is_repair_out:
            stats = self.get_stock_overview_by_parts(product_id, product_name)
            v_stat = stats.get(variant)
            if not v_stat:
                raise ValueError(f"商品【{product_name}】不存在款式【{variant}】")

            parts_dict = {p["part_name"]: p for p in v_stat.get("parts", [])}
            action_name = "返修出库" if is_repair_out else "验收完成入库"

            if is_set:
                for pt_name, pt_info in parts_dict.items():
                    req_needed = quantity * pt_info.get("req_qty", 1)
                    avail_inspect = pt_info.get("inspecting", 0)
                    if avail_inspect < req_needed:
                        raise ValueError(
                            f"入库验收数量不足！【{product_name}-{variant}】部件【{pt_name}】在验收中仅剩 {avail_inspect} 件，"
                            f"无法执行{action_name} {req_needed} 件（{quantity}套）的操作。"
                        )
            else:
                pt_info = parts_dict.get(part_name)
                if not pt_info:
                    raise ValueError(f"款式【{variant}】不存在部件【{part_name}】")
                avail_inspect = pt_info.get("inspecting", 0)
                if avail_inspect < quantity:
                    raise ValueError(
                        f"入库验收数量不足！【{product_name}-{variant}】部件【{part_name}】在验收中仅剩 {avail_inspect} 件，"
                        f"无法执行{action_name} {quantity} 件的操作。"
                    )

        # ✨ 1.5 返修后入库：严格防负数校验（校验返修出库中的余量）
        if move_type == StockLogReason.REPAIR_IN:
            stats = self.get_stock_overview_by_parts(product_id, product_name)
            v_stat = stats.get(variant)
            if not v_stat:
                raise ValueError(f"商品【{product_name}】不存在款式【{variant}】")

            parts_dict = {p["part_name"]: p for p in v_stat.get("parts", [])}
            if is_set:
                for pt_name, pt_info in parts_dict.items():
                    req_needed = quantity * pt_info.get("req_qty", 1)
                    avail_repaired = pt_info.get("repaired", 0)
                    if avail_repaired < req_needed:
                        raise ValueError(
                            f"返修数量不足！【{product_name}-{variant}】部件【{pt_name}】在返修出库中仅剩 {avail_repaired} 件，"
                            f"无法执行返修后入库 {req_needed} 件（{quantity}套）的操作。"
                        )
            else:
                pt_info = parts_dict.get(part_name)
                if not pt_info:
                    raise ValueError(f"款式【{variant}】不存在部件【{part_name}】")
                avail_repaired = pt_info.get("repaired", 0)
                if avail_repaired < quantity:
                    raise ValueError(
                        f"返修数量不足！【{product_name}-{variant}】部件【{part_name}】在返修出库中仅剩 {avail_repaired} 件，"
                        f"无法执行返修后入库 {quantity} 件的操作。"
                    )

        # ✨ 2. 出库、移库及入库冲销前的严格物理仓库库存校验
        if (move_type == StockLogReason.OUT_STOCK and not is_repair_out) or move_type == StockLogReason.TRANSFER or move_type == StockLogReason.INSPECT_REVERSAL:
            wh_details = self.get_warehouse_inventory_details()
            
            # 解析本次操作具体扣减了哪些底层部件
            parts_to_check = {}
            if is_set:
                target_c = next((c for c in target_prod_obj.colors if c.color_name == variant), None) if target_prod_obj else None
                if target_c and target_c.parts:
                    for p in target_c.parts:
                        parts_to_check[p.part_name] = quantity * p.quantity
                else:
                    parts_to_check["整套"] = quantity
            else:
                parts_to_check[part_name] = quantity
                
            # 获取目标仓库的物理库存快照
            stock_in_wh = wh_details.get(warehouse_id, {}).get("stock", {}).get(product_name, {}).get(variant, {})
            wh_name = wh_details.get(warehouse_id, {}).get("name", "未分配仓库")
            
            # 逐个部件进行校验
            for pt, req_qty in parts_to_check.items():
                avail_qty = stock_in_wh.get(pt, 0)
                if avail_qty < req_qty:
                    raise ValueError(f"库存不足！【{product_name}-{variant}】的部件【{pt}】在【{wh_name}】中仅剩 {avail_qty} 件，无法执行扣减 {req_qty} 件的操作。")

        # ✨ 2.5 入库冲销前的累计生产数校验
        if move_type == StockLogReason.INSPECT_REVERSAL:
            stats = self.get_stock_overview_by_parts(product_id, product_name)
            v_stat = stats.get(variant, {})
            avail_produced = v_stat.get("produced", 0)
            if is_set:
                if avail_produced < quantity:
                    raise ValueError(f"冲销失败！款式【{product_name}-{variant}】累计生产入库仅有 {avail_produced} 套，无法冲销 {quantity} 套。")
            else:
                parts_dict = {p["part_name"]: p for p in v_stat.get("parts", [])}
                pt_info = parts_dict.get(part_name)
                pt_prod = pt_info.get("produced", 0) if pt_info else 0
                if pt_prod < quantity:
                    raise ValueError(f"冲销失败！款式【{product_name}-{variant}】部件【{part_name}】累计生产入库仅有 {pt_prod} 件，无法冲销 {quantity} 件。")

        if move_type == StockLogReason.TRANSFER:
            if warehouse_id == to_warehouse_id:
                raise ValueError("移出仓库和移入仓库不能相同！")
            
            # 优化流水备注：清晰写明移入移出仓库的名字
            wh_details = self.get_warehouse_inventory_details()
            wh_from_name = wh_details.get(warehouse_id, {}).get("name", "未分配仓库")
            wh_to_name = self.db.query(Warehouse).filter(Warehouse.id == to_warehouse_id).first().name if to_warehouse_id else "未分配仓库"
            
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=-quantity,
                reason=StockLogReason.TRANSFER, note=f"移出至【{wh_to_name}】 | {remark}", date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.TRANSFER, note=f"从【{wh_from_name}】移入 | {remark}", date=date_obj,
                warehouse_id=to_warehouse_id, part_name=None if is_set else part_name
            ))
            msg = "库存移动成功（生成一进一出两笔记录）"

        elif is_repair_out:
            # ✨ 验收不合格返修出库：扣减入库验收中数量
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=-quantity,
                reason=StockLogReason.REPAIR_OUT,
                note=f"验收不合格返修 | {remark}" if remark else "验收不合格返修",
                is_other_out=True, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            unit_label = "套" if is_set else "件"
            msg = f"【{product_name}-{variant}】验收不合格返修出库已录入，已从入库验收中扣减 {quantity} {unit_label}"

        elif move_type == StockLogReason.OUT_STOCK:
            actual_change_amt = -quantity
            target_cost_id = None
            if out_type == "消耗" and target_prod_obj and is_set:
                new_cost = CostItem(
                    product_id=product_id, item_name=cons_content, actual_cost=0, supplier="", category=cons_cat,      
                    unit_price=0, quantity=0, unit="", remarks=f"款式:{variant} 数量:{quantity} | {remark}"
                )
                self.db.add(new_cost)
                self.db.flush() 
                target_cost_id = new_cost.id

            if out_type == "消耗":
                log_note = f"消耗: {cons_content} | {remark}" if remark else f"消耗: {cons_content}"
            elif out_type == "寄售":
                shop_label = consignment_shop.strip() if consignment_shop else "默认寄售点"
                log_note = f"寄售: {shop_label} | {remark}" if remark else f"寄售: {shop_label}"
            else:
                log_note = f"出库: {remark}" if remark else "出库"
            
            new_log = InventoryLog(
                product_name=product_name, variant=variant, change_amount=actual_change_amt,
                reason=StockLogReason.OUT_STOCK, note=log_note, is_other_out=True, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name,
                cost_item_id=target_cost_id 
            )
            self.db.add(new_log)
            self.db.flush()

            if out_type == "寄售":
                shop_label = consignment_shop.strip() if consignment_shop else "默认寄售点"
                cons_item = ConsignmentItem(
                    shop_name=shop_label,
                    product_name=product_name,
                    variant=variant,
                    quantity=quantity,
                    remaining_qty=quantity,
                    remarks=remark or "",
                    date=date_obj,
                    inventory_log_id=new_log.id
                )
                self.db.add(cons_item)

            if out_type == "寄售":
                msg = f"【{product_name}-{variant}】寄售出库成功并已录入寄售管理"
            else:
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

        elif move_type == StockLogReason.INSPECT_REVERSAL:
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=-quantity,
                reason=StockLogReason.INSPECT_REVERSAL,
                note=f"入库冲销 | {remark}" if remark else "入库冲销",
                date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            unit_label = "套" if is_set else "件"
            msg = f"【{product_name}-{variant}】入库冲销已成功录入，已扣减实物与生产数各 {quantity} {unit_label}，并恢复验收中余量"

        elif move_type == StockLogReason.REPAIR_IN:
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.REPAIR_IN, note=remark or "返修后入库", date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            ))
            unit_label = "套" if is_set else "件"
            msg = f"【{product_name}-{variant}】返修后入库已录入，已增加仓储实物并减扣返修中数量 {quantity} {unit_label}"
            
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
        self.sync_product_metrics(product_id)
        return msg

    def add_batch_inventory_movements(self, product_id, product_name, entries: list[dict], 
                                      move_type, date_obj, batch_remark, warehouse_id=None, 
                                      to_warehouse_id=None, out_type=None, cons_cat=None, cons_content=None,
                                      auto_inspect_complete=False, consignment_shop=None):
        """在一个数据库事务内批量执行多款式/多散件库存变动。"""
        if not entries:
            raise ValueError("没有待录入的条目！")
            
        success_count = 0
        total_quantity = 0
        for item in entries:
            qty = item.get("quantity", 0)
            if qty <= 0:
                continue
            v_name = item.get("variant")
            p_name = item.get("part_name")
            is_set = (p_name is None or p_name == "" or p_name == "整套")
            actual_p_name = None if is_set else p_name
            
            if move_type == StockLogReason.IN_INSPECT and auto_inspect_complete:
                # 1. 录入入库验收
                self.add_inventory_movement(
                    product_id=product_id,
                    product_name=product_name,
                    variant=v_name,
                    quantity=qty,
                    move_type=StockLogReason.IN_INSPECT,
                    date_obj=date_obj,
                    remark=batch_remark,
                    warehouse_id=warehouse_id,
                    to_warehouse_id=to_warehouse_id,
                    is_set=is_set,
                    part_name=actual_p_name,
                    out_type=out_type,
                    cons_cat=cons_cat,
                    cons_content=cons_content,
                    consignment_shop=consignment_shop
                )
                # 2. 紧接着录入验收完成入库
                self.add_inventory_movement(
                    product_id=product_id,
                    product_name=product_name,
                    variant=v_name,
                    quantity=qty,
                    move_type=StockLogReason.INSPECT_COMPLETED,
                    date_obj=date_obj,
                    remark=batch_remark,
                    warehouse_id=warehouse_id,
                    to_warehouse_id=to_warehouse_id,
                    is_set=is_set,
                    part_name=actual_p_name,
                    out_type=out_type,
                    cons_cat=cons_cat,
                    cons_content=cons_content,
                    consignment_shop=consignment_shop
                )
                success_count += 2
                total_quantity += qty
            else:
                self.add_inventory_movement(
                    product_id=product_id,
                    product_name=product_name,
                    variant=v_name,
                    quantity=qty,
                    move_type=move_type,
                    date_obj=date_obj,
                    remark=batch_remark,
                    warehouse_id=warehouse_id,
                    to_warehouse_id=to_warehouse_id,
                    is_set=is_set,
                    part_name=actual_p_name,
                    out_type=out_type,
                    cons_cat=cons_cat,
                    cons_content=cons_content,
                    consignment_shop=consignment_shop
                )
                success_count += 1
                total_quantity += qty
            
        if success_count == 0:
            raise ValueError("未检测到大于 0 的有效变动数量，请输入数量后再提交！")
            
        if move_type == StockLogReason.IN_INSPECT and auto_inspect_complete:
            return f"一键验收+合格入库成功！共生成 {success_count} 笔明细流水（入库验收与合格入库各 {success_count // 2} 笔），合计入库 {total_quantity} 套/件"
        return f"批量录入成功！共生成 {success_count} 笔明细流水，合计变动 {total_quantity} 套/件"

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

        if getattr(log_to_del, 'order_id', None):
            raise ValueError("拒绝操作：此库存变动由【销售订单】自动生成。为了保证数据一致性，请前往【线上销售管理】模块撤销发货或删除该订单。")

        target_prod = self.db.query(Product).filter(Product.name == log_to_del.product_name).first()

        # ✨ 防负数预检：模拟删除该记录后，验证是否会导致验收中或仓储实物变为负数
        if target_prod and log_to_del.reason in [
            StockLogReason.IN_INSPECT, StockLogReason.INSPECT_COMPLETED, StockLogReason.INSPECT_REVERSAL,
            StockLogReason.REPAIR_OUT, StockLogReason.REPAIR_IN,
            StockLogReason.OTHER_IN, StockLogReason.IN_STOCK
        ]:
            all_logs = self.db.query(InventoryLog).filter(
                InventoryLog.product_name == target_prod.name,
                InventoryLog.id != log_to_del.id
            ).all()

            for c in target_prod.colors:
                parts_req = {p.part_name: p.quantity for p in c.parts} or {"整套": 1}
                sim_inspecting = {p: 0 for p in parts_req}
                sim_repaired = {p: 0 for p in parts_req}
                sim_actual = {p: 0 for p in parts_req}

                v_logs = [l for l in all_logs if l.variant == c.color_name]
                for l in v_logs:
                    delta = l.change_amount
                    l_parts = [(l.part_name, delta)] if (l.part_name and l.part_name in parts_req) else [(p, delta * req) for p, req in parts_req.items()]
                    for p, d in l_parts:
                        if l.reason == StockLogReason.IN_INSPECT:
                            sim_inspecting[p] += d
                        elif l.reason in [StockLogReason.INSPECT_COMPLETED, StockLogReason.INSPECT_REVERSAL]:
                            sim_inspecting[p] -= d
                            sim_actual[p] += d
                        elif l.reason == StockLogReason.REPAIR_OUT:
                            sim_inspecting[p] -= abs(d)
                            sim_repaired[p] += abs(d)
                        elif l.reason == StockLogReason.REPAIR_IN:
                            sim_repaired[p] -= abs(d)
                            sim_actual[p] += abs(d)
                        elif l.reason == StockLogReason.OUT_STOCK:
                            sim_actual[p] += d
                        elif l.reason in [StockLogReason.OTHER_IN, StockLogReason.IN_STOCK, StockLogReason.RETURN_IN, StockLogReason.TRANSFER]:
                            sim_actual[p] += d

                for p in parts_req:
                    if sim_inspecting[p] < 0:
                        raise ValueError(f"无法删除该记录：删除后将导致【{target_prod.name}-{c.color_name}】部件【{p}】的验收中数量变为负数 ({sim_inspecting[p]})！请先撤销后续的扣减记录。")
                    if sim_repaired[p] < 0:
                        raise ValueError(f"无法删除该记录：删除后将导致【{target_prod.name}-{c.color_name}】部件【{p}】的返修中数量变为负数 ({sim_repaired[p]})！请先撤销后续的返修后入库记录。")
                    if sim_actual[p] < 0 and log_to_del.reason in [StockLogReason.INSPECT_COMPLETED, StockLogReason.REPAIR_IN, StockLogReason.OTHER_IN, StockLogReason.IN_STOCK]:
                        raise ValueError(f"无法删除该记录：删除后将导致【{target_prod.name}-{c.color_name}】部件【{p}】的仓储实物数量变为负数 ({sim_actual[p]})！请先撤销后续的出库或移库记录。")

        msg_list = []
        target_prod = self.db.query(Product).filter(Product.name == log_to_del.product_name).first()
        is_set = (log_to_del.part_name is None)

        is_consumable_out = (log_to_del.reason == StockLogReason.OUT_STOCK and "消耗" in (log_to_del.note or ""))
        if is_consumable_out and target_prod and is_set:
            if getattr(log_to_del, 'cost_item_id', None):
                target_cost = self.db.query(CostItem).filter(CostItem.id == log_to_del.cost_item_id).first()
                if target_cost: 
                    self.db.delete(target_cost)
                    msg_list.append("关联消耗成本记录已精准删除")
            else:
                try:
                    content_part = log_to_del.note.split("|")[0].replace("消耗:", "").strip()
                    target_cost = self.db.query(CostItem).filter(
                        CostItem.product_id == target_prod.id,
                        CostItem.actual_cost == 0,
                        CostItem.item_name.like(f"%{content_part}%")
                    ).first()
                    if target_cost: 
                        self.db.delete(target_cost)
                        msg_list.append("关联消耗成本记录已删除(按向后兼容模式)")
                except: pass

        # 如果是寄售出库，清理关联的寄售记录
        is_consignment_out = (log_to_del.reason == StockLogReason.OUT_STOCK and "寄售" in (log_to_del.note or ""))
        if is_consignment_out:
            cons_item = self.db.query(ConsignmentItem).filter(ConsignmentItem.inventory_log_id == log_to_del.id).first()
            if cons_item:
                self.db.delete(cons_item)
                msg_list.append("关联寄售记录已同步删除")

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
                msg_list.append("关联的历史销售流水已回滚(向后兼容)")
                    
        elif log_to_del.reason == StockLogReason.TRANSFER:
            msg_list.append("单条移动记录已删除（注：移入/移出分别为独立的记录）")

        self.db.delete(log_to_del)
        self.db.flush()

        if target_prod:
            self.sync_product_metrics(target_prod.id)
            msg_list.append("资产重算完成")

        self.db.commit()
        return " | ".join(msg_list) if msg_list else "日志已删除"

    # ================= 7. 在制资产检测 =================
    def get_wip_balance(self, product_id):
        from services.cost_service import CostService
        cost_service = CostService(self.db)
        current_offset = cost_service.get_wip_offset(product_id)
        all_items = self.db.query(CostItem).filter(CostItem.product_id == product_id).all()
        current_total_cost = sum([(i.actual_cost or 0.0) for i in all_items])
        return current_total_cost + current_offset

    def clear_wip_for_product(self, product_id):
        from services.cost_service import CostService
        cost_service = CostService(self.db)
        cost_service.perform_wip_fix(product_id)

    # ================= 8. 寄售管理 =================
    def get_all_consignments(self):
        """获取所有寄售记录，按日期倒序"""
        return self.db.query(ConsignmentItem).order_by(ConsignmentItem.date.desc(), ConsignmentItem.id.desc()).all()

    def update_consignment_item(self, item_id: int, remaining_qty: int = None, remarks: str = None, shop_name: str = None):
        """更新寄售条目（剩余数量/备注/店铺）"""
        item = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == item_id).first()
        if not item:
            raise ValueError(f"未找到 ID 为 {item_id} 的寄售记录")
        if remaining_qty is not None:
            item.remaining_qty = max(0, int(remaining_qty))
        if remarks is not None:
            item.remarks = str(remarks).strip()
        if shop_name is not None and shop_name.strip():
            item.shop_name = str(shop_name).strip()
        self.db.flush()
        return item

    def delete_consignment_item(self, item_id: int):
        """删除单笔寄售记录"""
        item = self.db.query(ConsignmentItem).filter(ConsignmentItem.id == item_id).first()
        if not item:
            raise ValueError(f"未找到 ID 为 {item_id} 的寄售记录")
        self.db.delete(item)
        self.db.flush()

    def add_consignment_item(self, shop_name: str, product_name: str, variant: str, quantity: int, remaining_qty: int = None, remarks: str = "", date_obj = None):
        """手动新增寄售条目"""
        if not shop_name or not shop_name.strip():
            raise ValueError("寄售店铺名称不能为空")
        if not product_name or not product_name.strip():
            raise ValueError("商品名称不能为空")
        if quantity <= 0:
            raise ValueError("寄售数量必须大于 0")
        if remaining_qty is None:
            remaining_qty = quantity
        if date_obj is None:
            date_obj = date.today()
        new_item = ConsignmentItem(
            shop_name=shop_name.strip(),
            product_name=product_name.strip(),
            variant=variant.strip() if variant else "通用",
            quantity=int(quantity),
            remaining_qty=max(0, int(remaining_qty)),
            remarks=remarks.strip() if remarks else "",
            date=date_obj
        )
        self.db.add(new_item)
        self.db.flush()
        return new_item
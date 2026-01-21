from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import date
import math
from models import Product, InventoryLog, ProductColor, CompanyBalanceItem, CostItem, PreShippingItem, FinanceRecord
from constants import PRODUCT_COST_CATEGORIES, AssetPrefix, BalanceCategory, Currency, StockLogReason, FinanceCategory

class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        # 定义成本分类常量
        self.COST_CATEGORIES = PRODUCT_COST_CATEGORIES

    # ================= 辅助方法 (内部使用) =================
    def _get_unit_cost(self, product_id):
        """获取产品单位成本"""
        total_actual_cost = self.db.query(func.sum(CostItem.actual_cost))\
            .filter(CostItem.product_id == product_id).scalar() or 0.0
        product = self.db.query(Product).filter(Product.id == product_id).first()
        denom = product.marketable_quantity if (product and product.marketable_quantity is not None) else (product.total_quantity if product else 0)
        
        if denom > 0:
            return total_actual_cost / denom
        return 0.0

    def _update_asset_by_name(self, name, delta, category="asset", currency="CNY", finance_id=None):
        """按名称更新资产项"""
        item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == name).with_for_update().first()
        if item: 
            item.amount += delta
            # 容错：只有当金额极小且无关联流水时才物理删除，防止误删
            if abs(item.amount) <= 0.01 and not item.finance_record_id: 
                self.db.delete(item)
        else: 
            self.db.add(CompanyBalanceItem(
                name=name, amount=delta, category=category, 
                currency=currency, finance_record_id=finance_id
            ))

    # ================= 1. 数据获取 =================
    def get_all_products(self):
        return self.db.query(Product).all()

    def get_product_colors(self, product_id):
        return self.db.query(ProductColor).filter(ProductColor.product_id == product_id).order_by(ProductColor.id.asc()).all()

    def get_stock_overview(self, product_name):
        """
        获取库存概览数据：包括实际库存、预入库、预出库(待发)
        返回: real_stock_map, pre_in_map, pre_out_map, has_pending_logs_map
        """
        all_logs = self.db.query(InventoryLog).filter(InventoryLog.product_name == product_name).all()
        pre_out_items = self.db.query(PreShippingItem).filter(PreShippingItem.product_name == product_name).all()
        
        real_stock_map = {}
        pre_in_map = {}
        pre_out_map = {}
        has_pending_logs_map = {} # 记录哪些款式有挂起的预入库日志

        for log in all_logs:
            if log.reason in [StockLogReason.IN_STOCK, StockLogReason.OUT_STOCK, StockLogReason.EXTRA_PROD, StockLogReason.RETURN_IN, StockLogReason.UNDO_SHIP]:
                real_stock_map[log.variant] = real_stock_map.get(log.variant, 0) + log.change_amount

            elif log.reason in [StockLogReason.PRE_IN, StockLogReason.PRE_IN_REDUCE]:
                pre_in_map[log.variant] = pre_in_map.get(log.variant, 0) + log.change_amount
                # 标记该款式有未完成的预入库
                has_pending_logs_map[log.variant] = True
        
        for item in pre_out_items:
            pre_out_map[item.variant] = pre_out_map.get(item.variant, 0) + item.quantity
            
        return real_stock_map, pre_in_map, pre_out_map, has_pending_logs_map

    def get_pre_shipping_items(self, product_name):
        return self.db.query(PreShippingItem).filter(PreShippingItem.product_name == product_name).all()

    def get_recent_logs(self, product_name=None, limit=100):
        query = self.db.query(InventoryLog)
        if product_name:
            query = query.filter(InventoryLog.product_name == product_name)
        return query.order_by(InventoryLog.id.desc()).limit(limit).all()

    # ================= 2. 生产/入库操作 =================
    def action_production_complete(self, product_id, product_name, variant, quantity, date_obj):
        """生产完成：记录预入库，更新在制/预入库资产"""
        self.db.add(InventoryLog(
            product_name=product_name, variant=variant,
            change_amount=quantity, reason=StockLogReason.PRE_IN, note="生产完成", date=date_obj
        ))
        unit_cost = self._get_unit_cost(product_id)
        val = quantity * unit_cost
        self._update_asset_by_name(f"{AssetPrefix.PRE_STOCK}{product_name}", val)
        self._update_asset_by_name(f"{AssetPrefix.WIP_OFFSET}{product_name}", -val)
        self.db.commit()

    def action_finish_stock_in(self, product_id, product_name, variant_color_obj, pre_in_qty, date_obj):
        """入库完成/结单：预入库转实物，清理资产偏差"""
        unit_cost = self._get_unit_cost(product_id)
        variant_name = variant_color_obj.color_name
        
        # 1. 资产转移：预入库 -> 大货资产
        if pre_in_qty > 0:
            val = pre_in_qty * unit_cost
            self._update_asset_by_name(f"{AssetPrefix.PRE_STOCK}{product_name}", -val)
            self._update_asset_by_name(f"{AssetPrefix.STOCK}{product_name}", val)
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant_name,
                change_amount=pre_in_qty, reason=StockLogReason.IN_STOCK, note="预入库转实物", date=date_obj
            ))
            if variant_color_obj.produced_quantity is None: variant_color_obj.produced_quantity = 0
            variant_color_obj.produced_quantity += pre_in_qty
        
        # 2. 更新旧日志状态 (标记为完成)
        pending_logs = self.db.query(InventoryLog).filter(
            InventoryLog.product_name == product_name,
            InventoryLog.variant == variant_name,
            or_(InventoryLog.reason == StockLogReason.PRE_IN, InventoryLog.reason == StockLogReason.PRE_IN_REDUCE)
        ).all()
        for pl in pending_logs: pl.reason = StockLogReason.PRE_IN_COMPLETE
        
        # 3. 清零计划数量
        variant_color_obj.quantity = 0 
        
        # 4. 检查是否该产品所有款式都已结单，如果是，清理尾差
        other_pending_count = self.db.query(func.count(InventoryLog.id)).filter(
            InventoryLog.product_name == product_name,
            or_(InventoryLog.reason == StockLogReason.PRE_IN, InventoryLog.reason == StockLogReason.PRE_IN_REDUCE),
            InventoryLog.variant != variant_name
        ).scalar()
        
        residual_val = 0.0
        if other_pending_count == 0:
            wip_asset_name = f"{AssetPrefix.PRE_STOCK}{product_name}"
            offset_asset_name = f"{AssetPrefix.WIP_OFFSET}{product_name}"
            wip_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == wip_asset_name).first()

            if wip_item:
                residual_val = wip_item.amount
                if abs(residual_val) > 0.01:
                    # 记录一笔调账流水
                    self.db.add(FinanceRecord(
                        date=date_obj,
                        amount=0,
                        currency=Currency.CNY,
                        category=FinanceCategory.ASSET_ADJUST,
                        description=f"【调账】{product_name} 结单修正：{residual_val:,.2f}"
                    ))
                    self.db.delete(wip_item)
            
            offset_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == offset_asset_name).first()
            if offset_item:
                self.db.delete(offset_item)
        
        self.db.commit()
        return residual_val

    # ================= 3. 发货/出库管理 =================
    def update_pre_shipping_info(self, changes_dict):
        """处理 DataEditor 的修改 (金额/备注/币种)"""
        has_change = False
        for item_id, diff in changes_dict.items():
            p_obj = self.db.query(PreShippingItem).filter(PreShippingItem.id == item_id).first()
            if p_obj:
                if "预售/销售额" in diff or "币种" in diff:
                    if "预售/销售额" in diff: p_obj.pre_sale_amount = diff["预售/销售额"]
                    if "币种" in diff: p_obj.currency = diff["币种"]
                    
                    # 联动更新关联的挂账资产
                    if p_obj.related_debt_id:
                        asset_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == p_obj.related_debt_id).first()
                        if asset_item:
                            asset_item.amount = p_obj.pre_sale_amount
                            asset_item.currency = p_obj.currency
                    has_change = True
                    
                if "备注" in diff:
                    p_obj.note = diff["备注"]
                    has_change = True
        if has_change:
            self.db.commit()
        return has_change

    def confirm_shipping_receipt(self, pre_item_id):
        """确认收款：删除挂账资产，转入收入流水，增加现金"""
        target_pre = self.db.query(PreShippingItem).filter(PreShippingItem.id == pre_item_id).first()
        if not target_pre:
            raise ValueError("发货单不存在")

        # 1. 删除关联的“待结算”资产
        if target_pre.related_debt_id:
            pending_asset = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_pre.related_debt_id).first()
            if pending_asset: self.db.delete(pending_asset)
        
        # 2. 记录真实收入并增加现金资产
        fin_rec = FinanceRecord(
            date=date.today(), 
            amount=target_pre.pre_sale_amount, 
            currency=target_pre.currency, 
            category=FinanceCategory.SALES_INCOME, 
            description=f"发货单收款: {target_pre.product_name}-{target_pre.variant} (x{target_pre.quantity})"
        )
        self.db.add(fin_rec)
        self.db.flush()
        
        target_asset_name = f"{AssetPrefix.CASH}({target_pre.currency})"
        self._update_asset_by_name(
            target_asset_name, target_pre.pre_sale_amount, 
            category="asset", currency=target_pre.currency, finance_id=fin_rec.id
        )

        self.db.delete(target_pre)
        self.db.commit()
        return target_asset_name

    def undo_shipping(self, pre_item_id, selected_product_id):
        """撤销发货：回滚库存，删除待结算资产，删除发货单"""
        target_pre_obj = self.db.query(PreShippingItem).filter(PreShippingItem.id == pre_item_id).first()
        if not target_pre_obj:
            raise ValueError("发货单不存在")

        # 1. 回滚账面资产 (待结算款)
        if target_pre_obj.related_debt_id:
            pending_asset = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_pre_obj.related_debt_id).first()
            if pending_asset: self.db.delete(pending_asset)
        
        # 提取平台信息
        platform_str = "其他"
        if target_pre_obj.note and "平台:" in target_pre_obj.note:
            try:
                part1 = target_pre_obj.note.split("|")[0] 
                platform_str = part1.split(":")[-1].strip()
            except:
                pass
        
        # 2. 回滚库存数量 (InventoryLog) - 显式记录金额和平台，方便统计
        self.db.add(InventoryLog(
            product_name=target_pre_obj.product_name,
            variant=target_pre_obj.variant,
            change_amount=target_pre_obj.quantity, # 正数，加回库存
            reason=StockLogReason.UNDO_SHIP,
            note=f"撤销发货单: {target_pre_obj.note}",
            date=date.today(),
            platform=platform_str,
            is_sold=False, # 撤销不算已售，但在统计中会用到 sale_amount 抵扣
            sale_amount=-abs(target_pre_obj.pre_sale_amount),
            currency=target_pre_obj.currency
        ))

        # 3. 回滚库存资产价值 (大货资产)
        unit_cost = self._get_unit_cost(selected_product_id)
        asset_val = target_pre_obj.quantity * unit_cost
        self._update_asset_by_name(f"{AssetPrefix.STOCK}{target_pre_obj.product_name}", asset_val)

        # 4. 删除发货单
        self.db.delete(target_pre_obj)
        self.db.commit()
        return platform_str

    # ================= 4. 库存变动提交核心逻辑 =================
    def add_inventory_movement(self, product_id, product_name, variant, quantity, 
                               move_type, date_obj, remark, 
                               out_type=None, sale_curr=None, sale_platform=None, sale_price=0.0,
                               cons_cat=None, cons_content=None,
                               refund_curr=None, refund_amount=0.0, refund_platform=None):
        
        target_prod_obj = self.db.query(Product).filter(Product.id == product_id).first()
        
        # --- A. 计划入库减少 (特殊校验) ---
        if move_type == StockLogReason.PRE_IN_REDUCE:
            current_pre_in_qty = 0
            check_logs = self.db.query(InventoryLog).filter(
                InventoryLog.product_name == product_name,
                InventoryLog.variant == variant,
                or_(InventoryLog.reason == StockLogReason.PRE_IN, InventoryLog.reason == StockLogReason.PRE_IN_REDUCE)
            ).all()
            for l in check_logs: current_pre_in_qty += l.change_amount
            
            if current_pre_in_qty <= 0:
                raise ValueError(f"款式【{variant}】当前没有挂起的预入库数量。")
            elif quantity > current_pre_in_qty:
                raise ValueError(f"减少数量 ({quantity}) 不能超过当前预入库总数 ({current_pre_in_qty})。")

        # --- B. 出库逻辑 ---
        if move_type == StockLogReason.OUT_STOCK:
            unit_cost = self._get_unit_cost(product_id)
            cost_val = quantity * unit_cost
            
            # 分支 B1: 售出 (进入发货管理)
            if out_type == "售出":
                # 1. 创建"待结算"资产
                asset_name = f"{product_name}-{variant}-待结算({sale_platform})"
                pending_asset = CompanyBalanceItem(
                    name=asset_name, amount=sale_price, category="asset", currency=sale_curr
                )
                self.db.add(pending_asset)
                self.db.flush()

                # 2. 创建 PreShippingItem (发货单)
                pre_item = PreShippingItem(
                    product_name=product_name, variant=variant, quantity=quantity, 
                    pre_sale_amount=sale_price, currency=sale_curr, 
                    related_debt_id=pending_asset.id,
                    note=f"平台:{sale_platform} | {remark}", created_date=date_obj
                )
                self.db.add(pre_item)

                # 3. 记录出库日志 (立即扣库存)
                log = InventoryLog(
                    product_name=product_name, variant=variant, change_amount=-quantity,
                    reason=StockLogReason.OUT_STOCK, note=f"售出待结: {remark}", is_sold=True,
                    sale_amount=sale_price, currency=sale_curr, platform=sale_platform, date=date_obj
                )
                self.db.add(log)

                # 4. 扣减库存资产
                self._update_asset_by_name(f"{AssetPrefix.STOCK}{product_name}", -cost_val)
                return "已录入发货单，库存已扣减"

            # 分支 B2: 消耗 (扣减可售数量)
            elif out_type == "消耗":
                if target_prod_obj:
                    if target_prod_obj.marketable_quantity is None: target_prod_obj.marketable_quantity = target_prod_obj.total_quantity
                    target_prod_obj.marketable_quantity -= quantity
                    
                    combined_remark = f"款式:{variant} 数量:{quantity}"
                    if remark: combined_remark += f" | {remark}"

                    # 添加0金额成本记录
                    new_cost = CostItem(
                        product_id=product_id,
                        item_name=cons_content, actual_cost=0, supplier="", category=cons_cat,      
                        unit_price=0, quantity=0, unit="", remarks=combined_remark 
                    )
                    self.db.add(new_cost)

                log_note = f"消耗: {cons_content} | {remark}"
                self.db.add(InventoryLog(
                    product_name=product_name, variant=variant, change_amount=-quantity,
                    reason=StockLogReason.OUT_STOCK, note=log_note, is_other_out=True, date=date_obj
                ))
                self._update_asset_by_name(f"{AssetPrefix.STOCK}{product_name}", -cost_val)
                return f"可销售数量已减少 {quantity}，记录已添加至【{cons_cat}】"

            # 分支 B3: 其他出库
            else: 
                log_note = f"其他: {remark}"
                self.db.add(InventoryLog(
                    product_name=product_name, variant=variant, change_amount=-quantity, 
                    reason="出库", note=log_note, is_other_out=True, date=date_obj
                ))
                self._update_asset_by_name(f"{AssetPrefix.STOCK}{product_name}", -cost_val)
                return "其他出库成功"

        # --- C. 退货入库 ---
        elif move_type == StockLogReason.RETURN_IN:
            # 记录退货日志 (负销售额)
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.RETURN_IN, note=f"平台: {refund_platform} | {remark}",
                date=date_obj, is_sold=True, sale_amount=-refund_amount,
                currency=refund_curr, platform=refund_platform
            ))
            # 记录退款流水
            fin_rec = FinanceRecord(
                date=date_obj, amount=-refund_amount, currency=refund_curr,
                category=FinanceCategory.SALES_REFUND, description=f"{product_name}-{variant} 退货 (x{quantity}) | {remark}"
            )
            self.db.add(fin_rec)
            # 扣减现金
            self._update_asset_by_name(f"{AssetPrefix.CASH}({refund_curr})", -refund_amount, category=BalanceCategory.ASSET, currency=refund_curr)
            
            # 增加库存资产
            unit_cost = self._get_unit_cost(product_id)
            asset_val = quantity * unit_cost
            self._update_asset_by_name(f"{AssetPrefix.STOCK}{product_name}", asset_val)
            return "退货入库完成"

        # --- D. 计划入库减少 ---
        elif move_type == StockLogReason.PRE_IN_REDUCE:
            if target_prod_obj:
                if target_prod_obj.marketable_quantity is None: target_prod_obj.marketable_quantity = target_prod_obj.total_quantity
                target_prod_obj.marketable_quantity -= quantity

            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=-quantity,
                reason=StockLogReason.PRE_IN_REDUCE, note=f"修正预入库: {remark}", date=date_obj
            ))
            unit_cost = self._get_unit_cost(product_id)
            val = quantity * unit_cost
            self._update_asset_by_name(f"{AssetPrefix.PRE_STOCK}{product_name}", -val)
            # 加回冲销，保持平衡
            self._update_asset_by_name(f"{AssetPrefix.WIP_OFFSET}{product_name}", val)
            return f"预入库数量已减少: {quantity}"

        # --- E. 其他入库 (入库, 预入库, 额外生产入库) ---
        else: 
            self.db.add(InventoryLog(
                product_name=product_name, variant=variant, change_amount=quantity, 
                reason=move_type, note=remark, date=date_obj
            ))
            
            if move_type == StockLogReason.EXTRA_PROD and product_id:
                c_rec = self.db.query(ProductColor).filter(
                    ProductColor.product_id==product_id, ProductColor.color_name==variant
                ).first()
                if c_rec: 
                    if c_rec.produced_quantity is None: c_rec.produced_quantity = 0
                    c_rec.produced_quantity += quantity
                
                # 额外生产会增加可售数量
                if target_prod_obj:
                    if target_prod_obj.marketable_quantity is None: target_prod_obj.marketable_quantity = target_prod_obj.total_quantity
                    target_prod_obj.marketable_quantity += quantity

            unit_cost = self._get_unit_cost(product_id)
            val_change = quantity * unit_cost
            
            if move_type in [StockLogReason.IN_STOCK, StockLogReason.EXTRA_PROD]:
                self._update_asset_by_name(f"{AssetPrefix.STOCK}{product_name}", val_change)
            elif move_type == StockLogReason.PRE_IN: 
                self._update_asset_by_name(f"{AssetPrefix.PRE_STOCK}{product_name}", val_change)
            
            return f"{move_type} 成功"

    def commit(self):
        """提交事务"""
        self.db.commit()

    # ================= 5. 日志修改与删除 =================
    def update_logs_batch(self, changes):
        """批量更新日志 (日期/备注)"""
        has_change = False
        for log_id, diff in changes.items():
            target_log = self.db.query(InventoryLog).filter(InventoryLog.id == log_id).first()
            if target_log:
                if "日期" in diff:
                    new_d = diff["日期"]
                    # 兼容不同格式
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
        """删除日志并级联回滚所有关联数据"""
        log_to_del = self.db.query(InventoryLog).filter(InventoryLog.id == log_id).first()
        if not log_to_del:
            raise ValueError("记录不存在")

        msg_list = []
        target_prod = self.db.query(Product).filter(Product.name == log_to_del.product_name).first()
        
        # 1. 回滚可销售数量 (针对“计划入库减少”、“额外生产入库”和“消耗出库”)
        if target_prod:
            reasons_affecting_marketable = [StockLogReason.PRE_IN_REDUCE, StockLogReason.EXTRA_PROD]
            is_consumable_out = (log_to_del.reason == StockLogReason.OUT_STOCK and "消耗" in (log_to_del.note or ""))
            
            if log_to_del.reason in reasons_affecting_marketable or is_consumable_out:
                if target_prod.marketable_quantity is None: 
                    target_prod.marketable_quantity = target_prod.total_quantity
                
                old_mq = target_prod.marketable_quantity
                # 回滚操作：减去变动量 (注意变动量本身的符号)
                target_prod.marketable_quantity -= log_to_del.change_amount
                msg_list.append(f"可售数量 {old_mq} -> {target_prod.marketable_quantity}")

        # 计算资产变动成本
        unit_cost = self._get_unit_cost(target_prod.id) if target_prod else 0
        asset_delta = log_to_del.change_amount * unit_cost
        
        # 2. 根据类型回滚资产和关联单据
        if log_to_del.reason in [StockLogReason.IN_STOCK, StockLogReason.EXTRA_PROD, StockLogReason.RETURN_IN]:
            # 当初是增加资产，现在减回去
            self._update_asset_by_name(f"{AssetPrefix.STOCK}{log_to_del.product_name}", -asset_delta)
            msg_list.append("大货资产已回滚")
        
        elif log_to_del.reason == StockLogReason.OUT_STOCK:
            # A. 回滚大货库存资产 (把扣掉的加回来)
            self._update_asset_by_name(f"{AssetPrefix.STOCK}{log_to_del.product_name}", -asset_delta)
            msg_list.append("大货资产已回滚")
            
            # B. 处理销售关联
            if log_to_del.is_sold:
                # 尝试找已完成的流水
                target_fin = self.db.query(FinanceRecord).filter(
                    FinanceRecord.date == log_to_del.date,
                    FinanceRecord.amount == log_to_del.sale_amount,
                    FinanceRecord.category == FinanceCategory.SALES_INCOME,
                    FinanceRecord.description.like(f"%{log_to_del.product_name}%")
                ).first()
                
                if target_fin:
                    # 找到了流水，说明已确认收款 -> 回滚现金流 + 删除流水
                    cash_name = f"{AssetPrefix.CASH}({log_to_del.currency})"
                    cash_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == cash_name).first()
                    if cash_item:
                        cash_item.amount -= target_fin.amount
                        msg_list.append(f"流动资金已扣除 {target_fin.amount}")
                    self.db.delete(target_fin)
                    msg_list.append("关联销售流水已删除")
                else:
                    # 没找到流水，尝试找发货单 PreShippingItem
                    target_pre = self.db.query(PreShippingItem).filter(
                        PreShippingItem.product_name == log_to_del.product_name,
                        PreShippingItem.variant == log_to_del.variant,
                        PreShippingItem.quantity == abs(log_to_del.change_amount),
                        PreShippingItem.pre_sale_amount == log_to_del.sale_amount,
                        PreShippingItem.created_date == log_to_del.date 
                    ).first()

                    if target_pre:
                        # 删除待结算资产
                        if target_pre.related_debt_id:
                            pending_asset = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == target_pre.related_debt_id).first()
                            if pending_asset:
                                self.db.delete(pending_asset)
                                msg_list.append("关联待结算资产已清理")
                        self.db.delete(target_pre)
                        msg_list.append("关联待发货/结算单已删除")

            # C. 处理消耗关联
            if "消耗:" in (log_to_del.note or ""):
                try:
                    # 尝试从备注中提取消耗内容，模糊匹配删除
                    content_part = log_to_del.note.split("|")[0].replace("消耗:", "").replace("内部消耗:", "").strip()
                    target_cost = self.db.query(CostItem).filter(
                        CostItem.product_id == target_prod.id,
                        CostItem.actual_cost == 0,
                        CostItem.item_name.like(f"%{content_part}%")
                    ).first()
                    if target_cost:
                        self.db.delete(target_cost)
                        msg_list.append("关联成本记录已删除")
                except:
                    pass

        elif log_to_del.reason in [StockLogReason.PRE_IN, StockLogReason.PRE_IN_REDUCE]:
            # 回滚预入库资产和冲销项
            self._update_asset_by_name(f"{AssetPrefix.PRE_STOCK}{log_to_del.product_name}", -asset_delta)
            self._update_asset_by_name(f"{AssetPrefix.WIP_OFFSET}{log_to_del.product_name}", asset_delta)
            msg_list.append("预入库/冲销资产已回滚")

        self.db.delete(log_to_del)
        self.db.commit()
        return " | ".join(msg_list)

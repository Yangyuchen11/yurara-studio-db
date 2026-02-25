from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import date
from models import ConsumableItem, ConsumableLog, Product, CostItem, FinanceRecord, CompanyBalanceItem
from constants import AssetPrefix, BalanceCategory, Currency, FinanceCategory

class ConsumableService:
    def __init__(self, db: Session):
        self.db = db

    # ================= 辅助方法 =================
    def _get_cash_asset(self, currency):
        """获取流动资金账户 (复用财务逻辑)"""
        return self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name.like(f"{AssetPrefix.CASH}%"),
            CompanyBalanceItem.currency == currency,
            CompanyBalanceItem.category == BalanceCategory.ASSET
        ).order_by(CompanyBalanceItem.id.asc()).first()

    # ================= 1. 数据获取 =================
    def get_all_consumables(self):
        """获取所有资产项"""
        return self.db.query(ConsumableItem).all()

    def get_active_consumables(self):
        """获取有库存的资产项 (用于下拉框)"""
        return self.db.query(ConsumableItem).filter(ConsumableItem.remaining_qty > 0).all()

    def get_consumable_by_id(self, item_id):
        return self.db.query(ConsumableItem).filter(ConsumableItem.id == item_id).first()

    def get_logs(self):
        """获取操作日志"""
        return self.db.query(ConsumableLog).order_by(ConsumableLog.id.desc()).all()
    
    def get_all_products(self):
        """获取所有产品 (用于成本分摊选择)"""
        return self.db.query(Product).all()

    # ================= 2. 核心业务：库存变动 =================
    def process_inventory_change(self, item_name, date_obj, delta_qty, exchange_rate, 
                                 mode="normal",  # normal, sale, cost
                                 sale_info=None, # dict: content, source, amount, currency, remark
                                 cost_info=None, # dict: product_id, category, remark
                                 base_remark=""
                                 ):
        """
        处理库存变动，并根据模式处理联动 (销售/成本)
        """
        item = self.db.query(ConsumableItem).filter(ConsumableItem.name == item_name).with_for_update().first()
        if not item:
            raise ValueError("物品不存在")

        # 校验库存 (如果是出库)
        if delta_qty < 0 and item.remaining_qty < abs(delta_qty):
            raise ValueError("库存不足")

        # 1. 更新库存
        item.remaining_qty += delta_qty

        # 2. 计算价值变动 (用于日志)
        curr = getattr(item, "currency", "CNY")
        rate = exchange_rate if curr == "JPY" else 1.0
        val_change_cny = delta_qty * item.unit_price * rate

        link_msg = ""
        log_note = base_remark

        # === 分支 A: 销售模式 ===
        if mode == "sale" and sale_info:
            if sale_info['amount'] > 0:
                # 记录流水
                note_detail = f"来源: {sale_info['source']}" if sale_info['source'] else ""
                if sale_info['remark']: note_detail += f" | {sale_info['remark']}"
                
                fin_rec = FinanceRecord(
                    date=date_obj,
                    amount=sale_info['amount'],
                    currency=sale_info['currency'],
                    category=FinanceCategory.SALES_INCOME,
                    description=f"{sale_info['content']} [{note_detail}]"
                )
                self.db.add(fin_rec)
                self.db.flush()

                # 增加流动资金
                target_cash = self._get_cash_asset(sale_info['currency'])
                if not target_cash:
                    target_cash = CompanyBalanceItem(
                        category=BalanceCategory.ASSET,
                        name=f"{AssetPrefix.CASH}({sale_info['currency']})",
                        amount=0.0,
                        currency=sale_info['currency']
                    )
                    self.db.add(target_cash)
                target_cash.amount += sale_info['amount']

                link_msg = f" | 💰 已入账 {sale_info['amount']}{sale_info['currency']} 至流动资金"
                log_note = f"对外销售: {sale_info['content']} | 金额:{sale_info['amount']}{sale_info['currency']}"
            else:
                log_note = f"对外销售 (无金额): {sale_info['content']}"

        # === 分支 B: 内部消耗 ===
        elif mode == "cost" and cost_info:
            cost_amount = abs(val_change_cny)
            new_cost = CostItem(
                product_id=cost_info['product_id'],
                item_name=f"资产分摊: {item.name}",
                actual_cost=cost_amount,
                supplier="自有库存",
                category=cost_info['category'],
                unit_price=cost_amount / abs(delta_qty) if delta_qty else 0,
                quantity=abs(delta_qty),
                unit="个",
                remarks=f"从资产库出库: {cost_info['remark']}"
            )
            self.db.add(new_cost)
            
            p_obj = self.db.query(Product).filter(Product.id == cost_info['product_id']).first()
            p_name = p_obj.name if p_obj else "未知"
            link_msg = f" | 📉 已计入【{p_name}】成本 ¥{cost_amount:.2f}"
            log_note = f"内部消耗: {cost_info['remark']}"

        else:
            # 普通出入库
            prefix = "库存操作"
            if delta_qty > 0: prefix = "补货入库"
            log_note = f"{prefix}: {base_remark}"

        # 3. 记录日志
        new_log = ConsumableLog(
            item_name=item.name,
            change_qty=delta_qty,
            value_cny=val_change_cny,
            note=log_note,
            date=date_obj
        )
        self.db.add(new_log)
        self.db.commit()
        
        return item.name, delta_qty, link_msg

    # ================= 3. 批量更新 =================
    def update_items_batch(self, changes):
        """处理 DataEditor 的批量修改"""
        has_change = False
        for item_id, diff in changes.items():
            item = self.get_consumable_by_id(item_id)
            if item:
                if "币种" in diff: item.currency = diff["币种"]; has_change = True
                if "单价 (原币)" in diff: item.unit_price = float(diff["单价 (原币)"]); has_change = True
                if "店铺" in diff: item.shop_name = diff["店铺"]; has_change = True
                if "备注" in diff: item.remarks = diff["备注"]; has_change = True
                if "剩余数量" in diff: item.remaining_qty = float(diff["剩余数量"]); has_change = True
        
        if has_change:
            self.db.commit()
        return has_change

    def update_logs_batch(self, changes):
        """处理日志日期的修改"""
        has_change = False
        for log_id, diff in changes.items():
            log = self.db.query(ConsumableLog).filter(ConsumableLog.id == log_id).first()
            if log:
                if "日期" in diff:
                    new_d = diff["日期"]
                    if hasattr(new_d, 'date'): new_d = new_d.date()
                    log.date = new_d
                    has_change = True
        
        if has_change:
            self.db.commit()
        return has_change

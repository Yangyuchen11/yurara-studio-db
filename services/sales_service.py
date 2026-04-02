# services/sales_service.py
import pandas as pd
from sqlalchemy import or_
from models import InventoryLog, SalesOrder, SalesOrderItem
from constants import Currency, StockLogReason

class SalesService:
    """
    负责销售数据的获取、清洗与聚合逻辑
    """

    @staticmethod
    def get_raw_sales_logs(db):
        """
        获取所有与销售相关的库存日志
        包含：正常销售(is_sold=True) 和 撤销记录(reason="发货撤销")
        """
        return db.query(InventoryLog).filter(
            or_(
                InventoryLog.is_sold == True, 
                InventoryLog.reason == StockLogReason.UNDO_SHIP
            )
        ).order_by(InventoryLog.id.asc()).all()

    @staticmethod
    def process_sales_data(db, all_logs): # ✨ 新增 db 参数
        """
        核心逻辑：将数据库日志对象转换为标准化的销售明细 DataFrame
        """
        if not all_logs:
            return pd.DataFrame()

        raw_data_list = []

        for log in all_logs:
            # 提取基础信息
            item = {
                "id": log.id,
                "date": log.date,
                "product": log.product_name,
                "variant": log.variant,
                "platform": log.platform, 
                "currency": log.currency,
                "qty": 0,
                "amount": 0.0,
                "type": "unknown"
            }
            
            # ✨ 核心重构1：利用外键 order_id 精准溯源缺失的平台/币种信息
            if (not item["platform"] or not item["currency"]) and getattr(log, 'order_id', None):
                order = db.query(SalesOrder).filter(SalesOrder.id == log.order_id).first()
                if order:
                    item["platform"] = item["platform"] or order.platform
                    item["currency"] = item["currency"] or order.currency
                    
            # Fallback 兜底值
            item["platform"] = item["platform"] or "其他/未知"
            item["currency"] = item["currency"] or Currency.CNY

            # --- A. 销售 (Sale) ---
            if log.is_sold and log.change_amount < 0:
                item["qty"] = -log.change_amount 
                item["amount"] = log.sale_amount or 0
                item["type"] = "sale"

            # --- B. 退货 (Return) ---
            elif log.is_sold and log.change_amount > 0:
                item["qty"] = -log.change_amount 
                item["amount"] = log.sale_amount or 0 
                item["type"] = "return"

            # --- C. 撤销 (Undo) ---
            elif log.reason == "发货撤销":
                deduct_qty = log.change_amount
                item["qty"] = -deduct_qty 
                item["type"] = "undo"
                
                if log.sale_amount and log.sale_amount != 0:
                    item["amount"] = -abs(log.sale_amount)
                else:
                    # ✨ 核心重构2：彻底抛弃按字符串拼接的猜测逻辑，改用外键获取精准成交价
                    if getattr(log, 'order_id', None):
                        order_item = db.query(SalesOrderItem).filter(
                            SalesOrderItem.order_id == log.order_id,
                            SalesOrderItem.product_name == log.product_name,
                            SalesOrderItem.variant == log.variant
                        ).first()
                        if order_item:
                            item["amount"] = -(order_item.unit_price * deduct_qty)
                    else:
                        # 面对上古时期的历史老数据(连 order_id 都没有的)，统一算作 0，绝不乱猜
                        item["amount"] = 0

            raw_data_list.append(item)

        return pd.DataFrame(raw_data_list)

    @staticmethod
    def get_product_leaderboard(df, exchange_rate=0.048):
        """
        生成产品销售榜单数据
        """
        if df.empty:
            return pd.DataFrame()
            
        df_prod_summary = df.groupby('product').apply(
            lambda x: pd.Series({
                'CNY总额': x[x['currency'] == 'CNY']['amount'].sum(),
                'JPY总额': x[x['currency'] == 'JPY']['amount'].sum()
            }),
            include_groups=False  
        ).reset_index()
        
        df_prod_summary['折合CNY总额'] = df_prod_summary['CNY总额'] + (df_prod_summary['JPY总额'] * exchange_rate)
        df_prod_summary = df_prod_summary.sort_values(by='折合CNY总额', ascending=False)
        
        return df_prod_summary[['product', '折合CNY总额', 'CNY总额', 'JPY总额']]
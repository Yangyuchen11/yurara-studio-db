# services/sales_service.py
import pandas as pd
from sqlalchemy import or_
from models import InventoryLog, SalesOrder, OrderRefund, SalesOrderItem
from constants import Currency, StockLogReason

class SalesService:
    """
    负责销售数据的获取、清洗与聚合逻辑 (包含 V1 和 V2 两套引擎)
    """

    # ==================== V2.0 终极极简架构 (A方案/新版) ====================
    @staticmethod
    def process_sales_data_v2(db):
        if not db: return pd.DataFrame()
        data_list = []

        # 1. 销售额与销量 (订单表)
        orders = db.query(SalesOrder).filter(
            SalesOrder.status.in_(["已发货", "订单完成", "售后中"])
        ).all()

        for o in orders:
            for item in o.items:
                data_list.append({
                    "id": f"O_{item.id}", "date": o.created_date, "product": item.product_name,
                    "variant": item.variant, "platform": o.platform, "currency": o.currency,
                    "qty": item.quantity, "amount": item.subtotal, "type": "sale"
                })

        # 2. 售后退款金额 (只精准扣钱，不碰数量)
        refunds = db.query(OrderRefund).all()
        for r in refunds:
            o = r.order
            if not o: continue
            order_items_total = sum(i.subtotal for i in o.items)
            for item in o.items:
                allocated_refund = (item.subtotal / order_items_total * r.refund_amount) if order_items_total > 0 else 0
                if allocated_refund > 0:
                    data_list.append({
                        "id": f"R_{r.id}_{item.id}", "date": r.refund_date, "product": item.product_name,
                        "variant": item.variant, "platform": o.platform, "currency": o.currency,
                        "qty": 0, "amount": -allocated_refund, "type": "refund"
                    })

        # 3. 退货实物数量 (只精准扣数量，不碰钱)
        return_logs = db.query(InventoryLog).filter(
            InventoryLog.is_sold == True,
            InventoryLog.reason == "退货入库"
        ).all()

        for log in return_logs:
            o = db.query(SalesOrder).filter(SalesOrder.id == log.order_id).first() if log.order_id else None
            platform = o.platform if o else (log.platform or "未知")
            currency = o.currency if o else (log.currency or "CNY")

            data_list.append({
                "id": f"Ret_{log.id}", "date": log.date, "product": log.product_name,
                "variant": log.variant, "platform": platform, "currency": currency,
                "qty": -abs(log.change_amount), "amount": 0.0, "type": "return"
            })

        return pd.DataFrame(data_list)

    # ==================== V1.0 物理库存版 (更新前旧版) ====================
    @staticmethod
    def get_raw_sales_logs_v1(db):
        return db.query(InventoryLog).filter(
            or_(
                InventoryLog.is_sold == True, 
                InventoryLog.reason == StockLogReason.UNDO_SHIP
            )
        ).order_by(InventoryLog.id.asc()).all()

    @staticmethod
    def process_sales_data_v1(db, all_logs):
        if not all_logs: return pd.DataFrame()
        raw_data_list = []
        
        for log in all_logs:
            item = {
                "id": log.id, "date": log.date, "product": log.product_name,
                "variant": log.variant, "platform": log.platform, 
                "currency": log.currency, "qty": 0, "amount": 0.0, "type": "unknown"
            }
            
            if (not item["platform"] or not item["currency"]) and getattr(log, 'order_id', None):
                order = db.query(SalesOrder).filter(SalesOrder.id == log.order_id).first()
                if order:
                    item["platform"] = item["platform"] or order.platform
                    item["currency"] = item["currency"] or order.currency
                    
            item["platform"] = item["platform"] or "其他/未知"
            item["currency"] = item["currency"] or Currency.CNY

            if log.is_sold and log.change_amount < 0:
                item["qty"] = -log.change_amount 
                item["amount"] = log.sale_amount or 0
                item["type"] = "sale"
            elif log.is_sold and log.change_amount > 0:
                item["qty"] = -log.change_amount 
                item["amount"] = log.sale_amount or 0 
                item["type"] = "return"
            elif log.reason == "发货撤销":
                deduct_qty = log.change_amount
                item["qty"] = -deduct_qty 
                item["type"] = "undo"
                if log.sale_amount and log.sale_amount != 0:
                    item["amount"] = -abs(log.sale_amount)
                else:
                    if getattr(log, 'order_id', None):
                        order_item = db.query(SalesOrderItem).filter(
                            SalesOrderItem.order_id == log.order_id,
                            SalesOrderItem.product_name == log.product_name,
                            SalesOrderItem.variant == log.variant
                        ).first()
                        if order_item:
                            item["amount"] = -(order_item.unit_price * deduct_qty)
                    else:
                        item["amount"] = 0

            raw_data_list.append(item)
            
        return pd.DataFrame(raw_data_list)

    # ==================== 共享榜单方法 ====================
    @staticmethod
    def get_product_leaderboard(df, exchange_rate=0.048):
        if df.empty: return pd.DataFrame()
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
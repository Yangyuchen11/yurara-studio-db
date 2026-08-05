# app_sales/services/sales_service.py
import pandas as pd
from django.db.models import Q
from app_sales.models import SalesOrder, OrderRefund, SalesOrderItem
from app_inventory.models import InventoryLog
from app_core.constants import Currency, StockLogReason, to_cny

class SalesService:
    @staticmethod
    def process_sales_data_v2():
        data_list = []

        orders = SalesOrder.objects.prefetch_related('items').filter(
            status__in=["已发货", "订单完成", "售后中"]
        )

        for o in orders:
            for item in o.items.all():
                data_list.append({
                    "id": f"O_{item.id}", "date": o.created_date, "product": item.product_name,
                    "variant": item.variant, "platform": o.platform, "currency": o.currency,
                    "qty": item.quantity, "amount": item.subtotal, "type": "sale"
                })

        refunds = OrderRefund.objects.select_related('order').prefetch_related('order__items').all()
        for r in refunds:
            o = r.order
            if not o:
                continue
            order_items = list(o.items.all())
            order_items_total = sum(i.subtotal for i in order_items)
            for item in order_items:
                allocated_refund = (item.subtotal / order_items_total * r.refund_amount) if order_items_total > 0 else 0
                if allocated_refund > 0:
                    data_list.append({
                        "id": f"R_{r.id}_{item.id}", "date": r.refund_date, "product": item.product_name,
                        "variant": item.variant, "platform": o.platform, "currency": o.currency,
                        "qty": 0, "amount": -allocated_refund, "type": "refund"
                    })

        return_logs = InventoryLog.objects.filter(
            is_sold=True,
            reason="退货入库"
        )

        for log in return_logs:
            o = SalesOrder.objects.filter(id=log.order_id).first() if log.order_id else None
            platform = o.platform if o else (log.platform or "未知")
            currency = o.currency if o else (log.currency or "CNY")

            data_list.append({
                "id": f"Ret_{log.id}", "date": log.date, "product": log.product_name,
                "variant": log.variant, "platform": platform, "currency": currency,
                "qty": -abs(log.change_amount), "amount": 0.0, "type": "return"
            })

        return pd.DataFrame(data_list)

    @staticmethod
    def get_raw_sales_logs_v1():
        return InventoryLog.objects.filter(
            Q(is_sold=True) | Q(reason=StockLogReason.UNDO_SHIP)
        ).order_by('id')

    @staticmethod
    def process_sales_data_v1(all_logs):
        if not all_logs:
            return pd.DataFrame()
        raw_data_list = []

        for log in all_logs:
            item = {
                "id": log.id, "date": log.date, "product": log.product_name,
                "variant": log.variant, "platform": log.platform,
                "currency": log.currency, "qty": 0, "amount": 0.0, "type": "unknown"
            }

            if (not item["platform"] or not item["currency"]) and getattr(log, 'order_id', None):
                order = SalesOrder.objects.filter(id=log.order_id).first()
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
                        order_item = SalesOrderItem.objects.filter(
                            order_id=log.order_id,
                            product_name=log.product_name,
                            variant=log.variant
                        ).first()
                        if order_item:
                            item["amount"] = -(order_item.unit_price * deduct_qty)
                    else:
                        item["amount"] = 0

            raw_data_list.append(item)

        return pd.DataFrame(raw_data_list)

    @staticmethod
    def get_product_leaderboard(df, rates_map=None):
        if df.empty:
            return pd.DataFrame()
        if rates_map is None:
            rates_map = {"JPY": 0.048}

        df = df.copy()
        df['equiv_cny'] = df.apply(lambda r: to_cny(float(r['amount']), str(r['currency']), rates_map), axis=1)

        df_prod_summary = df.groupby('product').apply(
            lambda x: pd.Series({
                '折合CNY总额': x['equiv_cny'].sum(),
                'CNY总额': x[x['currency'] == 'CNY']['amount'].sum(),
                'JPY总额': x[x['currency'] == 'JPY']['amount'].sum()
            }),
            include_groups=False
        ).reset_index()
        df_prod_summary = df_prod_summary.sort_values(by='折合CNY总额', ascending=False)
        return df_prod_summary[['product', '折合CNY总额', 'CNY总额', 'JPY总额']]

# app_sales/services/sales_order_service.py
import math
import pandas as pd
from django.db import transaction
from django.db.models import Q, Sum, Count
from app_sales.models import SalesOrder, SalesOrderItem, OrderRefund
from app_inventory.models import InventoryLog
from app_inventory.services.inventory_service import InventoryService
from app_finance.models import CompanyBalanceItem, FinanceRecord
from app_core.models import Product, CostItem, Warehouse, SalesPlatform
from app_core.constants import OrderStatus, FinanceCategory, AssetPrefix

class SalesOrderService:
    @staticmethod
    def _update_asset_by_name(name: str, delta: float, category="asset", currency="CNY"):
        item = CompanyBalanceItem.objects.select_for_update().filter(name=name).first()
        if item:
            item.amount += delta
            if item.amount < 0 and name.startswith(AssetPrefix.PENDING_SETTLE):
                item.amount = 0

            if abs(item.amount) <= 0.01 and not item.finance_record_id:
                item.delete()
            else:
                item.save()
        else:
            if delta < 0 and name.startswith(AssetPrefix.PENDING_SETTLE):
                return

            a_type = "现金" if name.startswith(AssetPrefix.CASH) else "资产"
            CompanyBalanceItem.objects.create(
                name=name, amount=delta, category=category, currency=currency, asset_type=a_type
            )

    @classmethod
    def _distribute_pending_asset(cls, order: SalesOrder, amount_delta: float):
        legacy_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
        legacy_item = CompanyBalanceItem.objects.filter(name=legacy_asset_name).first()
        if legacy_item:
            cls._update_asset_by_name(legacy_asset_name, amount_delta, category="asset", currency=order.currency)
            return

        order_items = list(order.items.all())
        total_initial = sum(item.subtotal for item in order_items)

        if total_initial > 0:
            product_subtotals = {}
            for item in order_items:
                product_subtotals[item.product_name] = product_subtotals.get(item.product_name, 0.0) + item.subtotal

            for p_name, subtotal in product_subtotals.items():
                item_delta = amount_delta * (subtotal / total_initial)
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{p_name}-{order.currency}"
                cls._update_asset_by_name(pending_asset_name, item_delta, category="asset", currency=order.currency)
        else:
            if order_items:
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order_items[0].product_name}-{order.currency}"
                cls._update_asset_by_name(pending_asset_name, amount_delta, category="asset", currency=order.currency)

    @staticmethod
    def get_all_orders(status=None, product_name=None, order_type="线上", limit=100):
        query = SalesOrder.objects.prefetch_related('items', 'refunds').filter(order_type=order_type)
        if status:
            query = query.filter(status=status)
        if product_name:
            query = query.filter(items__product_name=product_name).distinct()

        return query.order_by('-id')[:limit]

    @staticmethod
    def get_order_by_id(order_id: int):
        return SalesOrder.objects.prefetch_related('items', 'refunds').filter(id=order_id).first()

    @staticmethod
    def get_order_by_no(order_no: str, order_type="预售"):
        return SalesOrder.objects.prefetch_related('items', 'refunds').filter(
            order_no=order_no,
            order_type=order_type
        ).first()

    @classmethod
    @transaction.atomic
    def create_order(cls, order_no: str, platform: str, currency: str, items_data: list,
                     order_type="线上", target_account_name=None, notes="", discount_note=""):

        if SalesOrder.objects.filter(order_no=order_no).exists():
            raise ValueError(f"注文番号 {order_no} は既に存在します。")

        # 各明細の在庫チェック
        wh_details = InventoryService.get_warehouse_inventory_details()
        for item in items_data:
            p_name = item['product_name']
            v_name = item['variant']
            qty = item['quantity']
            w_id = item.get('warehouse_id')

            stock_in_wh = wh_details.get(w_id, {}).get("stock", {}).get(p_name, {}).get(v_name, {})
            prod = Product.objects.prefetch_related('colors__parts').filter(name=p_name).first()
            if not prod:
                raise ValueError(f"商品【{p_name}】が存在しません。")

            colors = list(prod.colors.all())
            target_c = next((c for c in colors if c.color_name == v_name), None)
            parts = list(target_c.parts.all()) if target_c else []
            reqs = {p.part_name: p.quantity for p in parts} if parts else {"整套": 1}

            for pt, req_qty in reqs.items():
                avail_qty = stock_in_wh.get(pt, 0)
                needed = qty * req_qty
                if avail_qty < needed:
                    wh_obj = Warehouse.objects.filter(id=w_id).first() if w_id else None
                    wh_name = wh_obj.name if wh_obj else "未分配倉庫"
                    raise ValueError(f"在庫不足: 【{p_name}-{v_name}】パーツ【{pt}】 (【{wh_name}】) 残り {avail_qty} 件、必要 {needed} 件")

        total_amount = sum(item['subtotal'] for item in items_data)
        status = OrderStatus.PENDING

        new_order = SalesOrder.objects.create(
            order_no=order_no,
            order_type=order_type,
            platform=platform,
            currency=currency,
            total_amount=total_amount,
            status=status,
            target_account_name=target_account_name,
            notes=notes,
            discount_note=discount_note
        )

        for item in items_data:
            SalesOrderItem.objects.create(
                order=new_order,
                product_name=item['product_name'],
                variant=item['variant'],
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                subtotal=item['subtotal'],
                warehouse_id=item.get('warehouse_id')
            )

            # 在庫ログ作成 (出庫)
            prod = Product.objects.filter(name=item['product_name']).first()
            prod_id = prod.id if prod else None

            InventoryLog.objects.create(
                product_name=item['product_name'],
                variant=item['variant'],
                change_amount=-item['quantity'],
                reason=StockLogReason.OUT_STOCK,
                note=f"販売出庫 (注文号: {order_no})",
                is_sold=True,
                sale_amount=item['subtotal'],
                currency=currency,
                platform=platform,
                warehouse_id=item.get('warehouse_id'),
                order_id=new_order.id
            )

            if prod_id:
                InventoryService.sync_product_metrics(prod_id)

        # 未決済資産の加算
        cls._distribute_pending_asset(new_order, total_amount)

        return new_order

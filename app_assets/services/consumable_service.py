# app_assets/services/consumable_service.py
from datetime import date
from django.db import transaction
from app_assets.models import ConsumableItem, ConsumableLog
from app_core.models import Product, CostItem
from app_finance.models import FinanceRecord, CompanyBalanceItem
from app_core.constants import AssetPrefix, BalanceCategory, FinanceCategory, to_cny

class ConsumableService:
    @staticmethod
    def _get_cash_asset(currency: str):
        return CompanyBalanceItem.objects.filter(
            name__startswith=AssetPrefix.CASH,
            currency=currency,
            category=BalanceCategory.ASSET
        ).order_by('id').first()

    @staticmethod
    def get_all_consumables():
        return ConsumableItem.objects.all()

    @staticmethod
    def get_active_consumables():
        return ConsumableItem.objects.filter(remaining_qty__gt=0)

    @staticmethod
    def get_consumable_by_id(item_id: int):
        return ConsumableItem.objects.filter(id=item_id).first()

    @staticmethod
    def get_logs():
        return ConsumableLog.objects.order_by('-id')

    @staticmethod
    def get_all_products():
        return Product.objects.all()

    @classmethod
    @transaction.atomic
    def process_inventory_change(cls, item_name: str, date_obj, delta_qty: int, rates_map: dict,
                                 mode="normal", sale_info=None, cost_info=None, base_remark=""):
        delta_qty = int(delta_qty)
        item = ConsumableItem.objects.select_for_update().filter(name=item_name).first()
        if not item:
            raise ValueError("物品が存在しません。")

        if delta_qty < 0 and item.remaining_qty < abs(delta_qty):
            raise ValueError("在庫不足です。")

        item.remaining_qty += delta_qty
        item.save()

        curr = getattr(item, "currency", "CNY") or "CNY"
        val_change_cny = delta_qty * item.unit_price * (to_cny(1.0, curr, rates_map) if curr != "CNY" else 1.0)

        link_msg = ""
        log_note = base_remark

        if mode == "sale" and sale_info:
            if sale_info['amount'] > 0:
                note_detail = f"来源: {sale_info['source']}" if sale_info['source'] else ""
                if sale_info['remark']:
                    note_detail += f" | {sale_info['remark']}"

                target_cash = None
                if sale_info.get('account_id'):
                    target_cash = CompanyBalanceItem.objects.filter(id=sale_info['account_id']).first()

                if not target_cash:
                    target_cash = cls._get_cash_asset(sale_info['currency'])

                if target_cash:
                    target_cash.amount += sale_info['amount']
                    target_cash.save()

                    FinanceRecord.objects.create(
                        date=date_obj,
                        amount=sale_info['amount'],
                        currency=target_cash.currency,
                        category=FinanceCategory.SALES_INCOME,
                        description=f"{sale_info['content']} [{note_detail}]",
                        account_id=target_cash.id
                    )

        elif mode == "cost" and cost_info:
            cost_amount = abs(val_change_cny)
            CostItem.objects.create(
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

            p_obj = Product.objects.filter(id=cost_info['product_id']).first()
            p_name = p_obj.name if p_obj else "未知"
            link_msg = f" | 📉 已计入【{p_name}】成本 ¥{cost_amount:.2f}"
            log_note = f"内部消耗: {cost_info['remark']}"
        else:
            prefix = "补货入库" if delta_qty > 0 else "库存操作"
            log_note = f"{prefix}: {base_remark}"

        ConsumableLog.objects.create(
            item_name=item.name,
            change_qty=delta_qty,
            value_cny=val_change_cny,
            note=log_note,
            date=date_obj
        )

        return item.name, delta_qty, link_msg

    @classmethod
    @transaction.atomic
    def update_items_batch(cls, changes: dict) -> bool:
        has_change = False
        for item_id, diff in changes.items():
            item = cls.get_consumable_by_id(item_id)
            if item:
                if "name" in diff:
                    item.name = diff["name"]
                    has_change = True
                if "category" in diff:
                    item.category = diff["category"]
                    has_change = True
                if "currency" in diff or "币种" in diff:
                    item.currency = diff.get("currency", diff.get("币种"))
                    has_change = True
                if "unit_price" in diff or "单价 (原币)" in diff:
                    item.unit_price = float(diff.get("unit_price", diff.get("单价 (原币)")))
                    has_change = True
                if "shop_name" in diff or "店铺" in diff:
                    item.shop_name = diff.get("shop_name", diff.get("店铺"))
                    has_change = True
                if "remarks" in diff or "备注" in diff:
                    item.remarks = diff.get("remarks", diff.get("备注"))
                    has_change = True
                if "remaining_qty" in diff or "剩余数量" in diff:
                    item.remaining_qty = float(diff.get("remaining_qty", diff.get("剩余数量")))
                    has_change = True
                if "url" in diff or "相关链接" in diff:
                    item.url = diff.get("url", diff.get("相关链接"))
                    has_change = True
                if has_change:
                    item.save()
        return has_change

    @classmethod
    @transaction.atomic
    def update_logs_batch(cls, changes: dict) -> bool:
        has_change = False
        for log_id, diff in changes.items():
            log = ConsumableLog.objects.filter(id=log_id).first()
            if log:
                if "日期" in diff:
                    new_d = diff["日期"]
                    if hasattr(new_d, 'date'):
                        new_d = new_d.date()
                    log.date = new_d
                    log.save()
                    has_change = True
        return has_change

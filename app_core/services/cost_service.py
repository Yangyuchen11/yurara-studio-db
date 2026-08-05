# app_core/services/cost_service.py
from django.db import transaction
from django.db.models import Q
from app_core.models import Product, CostItem
from app_finance.models import FinanceRecord, CompanyBalanceItem
from app_core.constants import PRODUCT_COST_CATEGORIES, AssetPrefix, BalanceCategory

class CostService:
    DETAILED_CATS = PRODUCT_COST_CATEGORIES[:4]
    SIMPLE_CATS = PRODUCT_COST_CATEGORIES[4:]
    ALL_CATS = PRODUCT_COST_CATEGORIES

    @staticmethod
    def get_all_products():
        return Product.objects.all()

    @staticmethod
    def get_product_by_name(name: str):
        return Product.objects.prefetch_related('colors__prices').filter(name=name).first()

    @staticmethod
    def get_cost_items(product_id: int):
        return CostItem.objects.filter(product_id=product_id)

    @staticmethod
    def get_wip_offset(product_id: int) -> float:
        prod = Product.objects.filter(id=product_id).first()
        if not prod:
            return 0.0

        offset_item = CompanyBalanceItem.objects.filter(
            Q(product_id=product_id, name__startswith=AssetPrefix.WIP_OFFSET) |
            Q(name=f"{AssetPrefix.WIP_OFFSET}{prod.name}"),
            category=BalanceCategory.ASSET
        ).first()

        return offset_item.amount if offset_item else 0.0

    @classmethod
    @transaction.atomic
    def add_budget_item(cls, product_id: int, category: str, name: str, unit_price: float, quantity: float, unit: str, remarks: str, currency="CNY"):
        new_cost = CostItem.objects.create(
            product_id=product_id,
            item_name=name,
            actual_cost=0,
            supplier="预算设定",
            category=category,
            unit_price=unit_price,
            quantity=quantity,
            unit=unit,
            remarks=remarks,
            currency=currency,
            is_budget=True
        )

        from app_inventory.services.inventory_service import InventoryService
        InventoryService.sync_product_metrics(product_id)

        return new_cost

    @classmethod
    @transaction.atomic
    def update_cost_item(cls, item_id: int, updates: dict) -> bool:
        target_item = CostItem.objects.filter(id=item_id).first()
        if not target_item:
            return False

        has_change = False
        if "unit" in updates and updates["unit"] != (target_item.unit or ""):
            target_item.unit = updates["unit"]
            has_change = True
        if "supplier" in updates and updates["supplier"] != (target_item.supplier or ""):
            target_item.supplier = updates["supplier"]
            has_change = True
        if "remarks" in updates and updates["remarks"] != (target_item.remarks or ""):
            target_item.remarks = updates["remarks"]
            has_change = True
        if "url" in updates and updates["url"] != (target_item.url or ""):
            target_item.url = updates["url"]
            has_change = True

        if target_item.is_budget:
            if "quantity" in updates:
                new_q = float(updates["quantity"])
                if abs(new_q - target_item.quantity) > 0.001:
                    target_item.quantity = new_q
                    has_change = True

            if "unit_price" in updates:
                new_p = float(updates["unit_price"])
                if abs(new_p - target_item.unit_price) > 0.01:
                    target_item.unit_price = new_p
                    has_change = True

            if "total_budget" in updates:
                new_total = float(updates["total_budget"])
                current_total = target_item.unit_price * target_item.quantity
                if abs(new_total - current_total) > 0.01:
                    target_item.unit_price = new_total
                    target_item.quantity = 1.0
                    has_change = True

        if has_change:
            target_item.save()
            from app_inventory.services.inventory_service import InventoryService
            InventoryService.sync_product_metrics(target_item.product_id)

        return has_change

    @classmethod
    @transaction.atomic
    def delete_cost_item(cls, item_id: int):
        item_to_del = CostItem.objects.filter(id=item_id).first()
        if not item_to_del:
            raise ValueError("項目が存在しません。")

        if item_to_del.is_budget and (item_to_del.actual_cost or 0.0) > 0.01:
            raise ValueError("⚠️ 削除できません: この予算項目には実払いが含まれています。")

        product_id = item_to_del.product_id

        if item_to_del.finance_record_id:
            fin_rec = FinanceRecord.objects.filter(id=item_to_del.finance_record_id).first()
            if fin_rec:
                restore_amount = abs(fin_rec.amount)
                restore_currency = fin_rec.currency

                cash_asset = None
                if fin_rec.account_id:
                    cash_asset = CompanyBalanceItem.objects.filter(id=fin_rec.account_id).first()
                else:
                    cash_asset = CompanyBalanceItem.objects.filter(
                        name__startswith=AssetPrefix.CASH,
                        currency=restore_currency,
                        category=BalanceCategory.ASSET
                    ).first()

                if cash_asset:
                    cash_asset.amount += restore_amount
                    cash_asset.save()

                fin_rec.amount = 0
                fin_rec.category = "取消/冲销"
                fin_rec.description = f"【已取消成本】{fin_rec.description}"
                fin_rec.save()

        item_to_del.delete()

        from app_inventory.services.inventory_service import InventoryService
        InventoryService.sync_product_metrics(product_id)

    @classmethod
    @transaction.atomic
    def perform_wip_fix(cls, product_id: int):
        prod = Product.objects.filter(id=product_id).first()
        if not prod:
            raise ValueError("商品が存在しません。")

        prod.is_production_completed = True
        prod.save()

        from app_inventory.services.inventory_service import InventoryService
        InventoryService.sync_product_metrics(prod.id)
        return 0, 0

# app_sales/services/offline_sales_service.py
from django.db import transaction
from django.db.models import Q
from app_sales.models import OfflineTemplate, OfflineTemplateItem, SalesOrder, SalesOrderItem
from app_inventory.models import InventoryLog
from app_finance.models import FinanceRecord, CompanyBalanceItem
from app_core.models import Product, Warehouse
from app_core.constants import OrderStatus, FinanceCategory

class OfflineSalesService:
    @staticmethod
    def _get_available_sets(warehouse_id: int, product_name: str, variant_name: str) -> int:
        from app_inventory.services.inventory_service import InventoryService
        wh_details = InventoryService.get_warehouse_inventory_details()
        stock_in_wh = wh_details.get(warehouse_id, {}).get("stock", {})
        pt_dict = stock_in_wh.get(product_name, {}).get(variant_name, {})

        prod = Product.objects.prefetch_related('colors__parts').filter(name=product_name).first()
        if not prod:
            return 0

        colors = list(prod.colors.all())
        target_c = next((c for c in colors if c.color_name == variant_name), None)
        if not target_c:
            return 0

        parts = list(target_c.parts.all())
        reqs = {p.part_name: p.quantity for p in parts} if parts else {"整套": 1}

        possible_sets = 0
        if reqs:
            possible_sets = min((pt_dict.get(pt, 0) // req) for pt, req in reqs.items())
        return max(0, possible_sets)

    @classmethod
    def _validate_template_stock(cls, warehouse_id: int, items_data: list):
        for item in items_data:
            qty = item['quantity']
            if qty > 0:
                current_stock = cls._get_available_sets(warehouse_id, item['product_name'], item['variant'])
                if qty > current_stock:
                    wh_obj = Warehouse.objects.filter(id=warehouse_id).first() if warehouse_id else None
                    wh_name = wh_obj.name if wh_obj else "未分配仓库"
                    raise ValueError(f"在庫不足: 【{item['product_name']}-{item['variant']}】 (【{wh_name}】) 最大可組装 {current_stock} 套")

    @staticmethod
    def get_all_templates():
        return OfflineTemplate.objects.prefetch_related('items').all()

    @classmethod
    @transaction.atomic
    def create_template(cls, name: str, code: str, currency: str, warehouse_id: int, platform: str, items_data: list):
        if OfflineTemplate.objects.filter(Q(code=code) | Q(name=name)).exists():
            raise ValueError(f"テンプレート名 '{name}' またはコード '{code}' は既に存在します。")

        cls._validate_template_stock(warehouse_id, items_data)

        new_template = OfflineTemplate.objects.create(
            name=name, code=code, currency=currency,
            warehouse_id=warehouse_id, platform=platform
        )

        for item in items_data:
            OfflineTemplateItem.objects.create(
                template=new_template,
                product_name=item['product_name'],
                variant=item['variant'],
                preset_price=item['preset_price'],
                quantity=item['quantity'],
                remaining_quantity=item['quantity']
            )

    @classmethod
    @transaction.atomic
    def update_template(cls, template_id: int, name: str, code: str, currency: str, warehouse_id: int, platform: str, items_data: list):
        exist = OfflineTemplate.objects.filter(
            Q(code=code) | Q(name=name)
        ).exclude(id=template_id).first()

        if exist:
            raise ValueError("テンプレート名またはコードが重複しています。")

        tpl = OfflineTemplate.objects.filter(id=template_id).first()
        if not tpl:
            raise ValueError("テンプレートが存在しません。")

        cls._validate_template_stock(warehouse_id, items_data)

        tpl.name = name
        tpl.code = code
        tpl.currency = currency
        tpl.warehouse_id = warehouse_id
        tpl.platform = platform
        tpl.save()

        OfflineTemplateItem.objects.filter(template_id=template_id).delete()
        for item in items_data:
            OfflineTemplateItem.objects.create(
                template=tpl,
                product_name=item['product_name'],
                variant=item['variant'],
                preset_price=item['preset_price'],
                quantity=item['quantity'],
                remaining_quantity=item['quantity']
            )

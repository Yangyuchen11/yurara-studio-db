# app_finance/services/finance_service.py
import re
import pandas as pd
from django.db import transaction
from django.db.models import Q, Sum, Case, When, Value, FloatField, F, Window
from django.db.models.functions import Coalesce
from app_finance.models import FinanceRecord, CompanyBalanceItem
from app_core.models import Product, CostItem
from app_assets.models import ConsumableItem, FixedAsset
from app_core.constants import AssetPrefix, BalanceCategory, Currency, FinanceCategory, to_cny

class FinanceService:
    NON_CASH_CATEGORIES = {"现有资产增加", "新资产增加", "现有资产减少", "其他资产增加"}

    @staticmethod
    def extract_qty_from_desc(description: str) -> float:
        if not description:
            return 1.0
        match = re.search(r'\(x([\d\.]+)\)', description)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 1.0

    @staticmethod
    def get_transferable_assets():
        return CompanyBalanceItem.objects.filter(
            category=BalanceCategory.ASSET,
            asset_type="现金"
        ).order_by('currency', 'id')

    @staticmethod
    def get_cash_asset(currency: str):
        return CompanyBalanceItem.objects.filter(
            name__startswith=AssetPrefix.CASH,
            currency=currency,
            category=BalanceCategory.ASSET
        ).order_by('id').first()

    @staticmethod
    def get_balance_items(category: str):
        return CompanyBalanceItem.objects.filter(category=category)

    @staticmethod
    def get_all_products():
        return Product.objects.all()

    @staticmethod
    def get_budget_items(product_id: int, category: str):
        return CostItem.objects.filter(
            product_id=product_id,
            category=category,
            is_budget=True
        )

    @staticmethod
    def get_consumable_items():
        return ConsumableItem.objects.all()

    @classmethod
    def get_finance_records_page(cls, page=1, page_size=100, search_query="", filter_type="", filter_category=""):
        queryset = FinanceRecord.objects.all().order_by('-date', '-id')

        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query) |
                Q(category__icontains=search_query)
            )

        if filter_category:
            queryset = queryset.filter(category=filter_category)

        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        records = list(queryset[start:end])

        return records, total_count

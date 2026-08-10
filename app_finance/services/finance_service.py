# app_finance/services/finance_service.py
import re
import pandas as pd
from django.db import connection, transaction
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
        table = FinanceRecord._meta.db_table

        where_conditions = ["1=1"]
        params = []

        # 关键字搜索
        search_query = search_query.strip()
        if search_query:
            like_pat = f"%{search_query}%"
            search_conds = [
                "sub.category LIKE %s",
                "sub.description LIKE %s",
                "sub.currency LIKE %s",
                "CAST(sub.date AS TEXT) LIKE %s",
                "CAST(sub.amount AS TEXT) LIKE %s"
            ]
            params.extend([like_pat, like_pat, like_pat, like_pat, like_pat])
            if "收入" in search_query:
                search_conds.append("sub.amount > 0")
            if "支出" in search_query:
                search_conds.append("sub.amount < 0")
            where_conditions.append(f"({' OR '.join(search_conds)})")

        # 业务大类筛选
        if filter_type == "收入":
            where_conditions.append("sub.amount > 0 AND sub.category NOT IN ('货币兑换', '转账-流出', '转账-流入')")
        elif filter_type == "支出":
            where_conditions.append("sub.amount < 0 AND sub.category NOT IN ('货币兑换', '转账-流出', '转账-流入')")
        elif filter_type == "货币兑换":
            where_conditions.append("sub.category = '货币兑换'")
        elif filter_type == "负债":
            where_conditions.append("sub.category IN ('借入资金', '新增挂账资产', '债务偿还', '资产抚消', '其他待付款', '商品成本待付款')")
        elif filter_type == "资金移动":
            where_conditions.append("sub.category IN ('转账-流出', '转账-流入', '资金移动')")

        # 细分类型筛选
        if filter_category and filter_category.strip():
            where_conditions.append("sub.category = %s")
            params.append(filter_category.strip())

        where_sql = " AND ".join(where_conditions)

        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT id, date, currency, amount, category, description FROM {table}
            ) AS sub WHERE {where_sql}
        """

        data_sql = f"""
            SELECT sub.id, sub.date, sub.currency, sub.amount, sub.category, sub.description, sub.url, sub.account_id, sub.related_item_id, sub.cny_bal, sub.jpy_bal
            FROM (
                SELECT id, date, currency, amount, category, description, url, account_id, related_item_id,
                       SUM(CASE WHEN currency = 'CNY' THEN amount ELSE 0 END) OVER (ORDER BY date ASC, id ASC) AS cny_bal,
                       SUM(CASE WHEN currency = 'JPY' THEN amount ELSE 0 END) OVER (ORDER BY date ASC, id ASC) AS jpy_bal
                FROM {table}
            ) AS sub
            WHERE {where_sql}
            ORDER BY sub.date DESC, sub.id DESC
            LIMIT %s OFFSET %s
        """

        offset = (page - 1) * page_size

        with connection.cursor() as cursor:
            cursor.execute(count_sql, params)
            total_count = cursor.fetchone()[0]

            cursor.execute(data_sql, params + [page_size, offset])
            rows = cursor.fetchall()

        records = []
        for r in rows:
            date_val = r[1]
            records.append({
                "id": r[0],
                "date": date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val or ""),
                "currency": r[2] or "CNY",
                "amount": float(r[3] or 0),
                "category": r[4] or "",
                "description": r[5] or "",
                "url": r[6] or "",
                "account_id": r[7],
                "related_item_id": r[8],
                "cny_bal": float(r[9] or 0),
                "jpy_bal": float(r[10] or 0),
            })

        return records, total_count


# app_finance/admin.py
from django.contrib import admin
from app_finance.models import FinanceRecord, CompanyBalanceItem

@admin.register(FinanceRecord)
class FinanceRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'date', 'category', 'amount', 'currency', 'description', 'account_id']
    list_filter = ['currency', 'category', 'date']
    search_fields = ['description', 'category']

@admin.register(CompanyBalanceItem)
class CompanyBalanceItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'category', 'amount', 'currency', 'asset_type', 'product_id']
    list_filter = ['category', 'currency', 'asset_type']
    search_fields = ['name']

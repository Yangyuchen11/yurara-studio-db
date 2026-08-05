# app_sales/admin.py
from django.contrib import admin
from app_sales.models import (
    SalesOrder, SalesOrderItem, OrderRefund,
    OfflineTemplate, OfflineTemplateItem
)

class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 0

class OrderRefundInline(admin.TabularInline):
    model = OrderRefund
    extra = 0

@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'order_no', 'order_type', 'status', 'total_amount', 'currency', 'platform', 'created_date']
    list_filter = ['order_type', 'status', 'currency', 'platform', 'created_date']
    search_fields = ['order_no', 'notes']
    inlines = [SalesOrderItemInline, OrderRefundInline]

class OfflineTemplateItemInline(admin.TabularInline):
    model = OfflineTemplateItem
    extra = 0

@admin.register(OfflineTemplate)
class OfflineTemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'code', 'currency', 'platform', 'created_at']
    search_fields = ['name', 'code']
    inlines = [OfflineTemplateItemInline]

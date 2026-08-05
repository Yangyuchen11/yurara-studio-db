# app_inventory/admin.py
from django.contrib import admin
from app_inventory.models import InventoryLog

@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'date', 'product_name', 'variant', 'change_amount', 'reason', 'is_sold', 'sale_amount', 'currency', 'warehouse_id']
    list_filter = ['reason', 'is_sold', 'currency', 'date']
    search_fields = ['product_name', 'variant', 'note']

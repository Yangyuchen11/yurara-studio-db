# app_assets/admin.py
from django.contrib import admin
from app_assets.models import (
    FixedAsset, FixedAssetLog, ConsumableItem, ConsumableLog
)

@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'unit_price', 'quantity', 'remaining_qty', 'currency', 'purchase_date']
    list_filter = ['currency', 'purchase_date']
    search_fields = ['name', 'shop_name', 'remarks']

@admin.register(FixedAssetLog)
class FixedAssetLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'asset_name', 'decrease_qty', 'reason', 'date']
    search_fields = ['asset_name', 'reason']

@admin.register(ConsumableItem)
class ConsumableItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'category', 'unit_price', 'initial_quantity', 'remaining_qty', 'currency', 'purchase_date']
    list_filter = ['category', 'currency', 'purchase_date']
    search_fields = ['name', 'shop_name', 'remarks']

@admin.register(ConsumableLog)
class ConsumableLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'item_name', 'change_qty', 'value_cny', 'date']
    search_fields = ['item_name', 'note']

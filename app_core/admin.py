# app_core/admin.py
from django.contrib import admin
from app_core.models import (
    Warehouse, Product, ProductColor, ProductPrice, ProductPart,
    CostItem, SalesPlatform, MemoNote, SystemSetting
)

class ProductColorInline(admin.TabularInline):
    model = ProductColor
    extra = 0

class CostItemInline(admin.TabularInline):
    model = CostItem
    extra = 0

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'total_quantity', 'marketable_quantity', 'is_production_completed', 'target_platform']
    list_filter = ['is_production_completed', 'target_platform']
    search_fields = ['name']
    inlines = [ProductColorInline, CostItemInline]

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'remarks']
    search_fields = ['name']

@admin.register(SalesPlatform)
class SalesPlatformAdmin(admin.ModelAdmin):
    list_display = ['id', 'code', 'name', 'currency', 'fee_rate', 'fee_fixed']
    search_fields = ['code', 'name']

@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'value', 'description']
    search_fields = ['key', 'description']

@admin.register(MemoNote)
class MemoNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'date', 'content', 'created_at']
    search_fields = ['content', 'date']

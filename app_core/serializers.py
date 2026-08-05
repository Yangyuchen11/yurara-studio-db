# app_core/serializers.py
from rest_framework import serializers
from app_core.models import (
    Warehouse, Product, ProductColor, ProductPrice, ProductPart,
    CostItem, SalesPlatform, MemoNote, SystemSetting
)

class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = '__all__'


class ProductPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPrice
        fields = '__all__'


class ProductPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPart
        fields = '__all__'


class ProductColorSerializer(serializers.ModelSerializer):
    prices = ProductPriceSerializer(many=True, read_only=True)
    parts = ProductPartSerializer(many=True, read_only=True)

    class Meta:
        model = ProductColor
        fields = '__all__'


class CostItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostItem
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    colors = ProductColorSerializer(many=True, read_only=True)
    costs = CostItemSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = '__all__'


class SalesPlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesPlatform
        fields = '__all__'


class MemoNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemoNote
        fields = '__all__'


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = '__all__'

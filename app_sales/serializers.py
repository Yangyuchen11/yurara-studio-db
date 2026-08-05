# app_sales/serializers.py
from rest_framework import serializers
from app_sales.models import (
    SalesOrder, SalesOrderItem, OrderRefund,
    OfflineTemplate, OfflineTemplateItem, PresaleOrderBinding
)

class SalesOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrderItem
        fields = '__all__'


class OrderRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderRefund
        fields = '__all__'


class PresaleOrderBindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresaleOrderBinding
        fields = '__all__'


class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True, read_only=True)
    refunds = OrderRefundSerializer(many=True, read_only=True)
    bound_deposits = PresaleOrderBindingSerializer(many=True, read_only=True)
    bound_finals = PresaleOrderBindingSerializer(many=True, read_only=True)

    class Meta:
        model = SalesOrder
        fields = '__all__'


class OfflineTemplateItemSerializer(serializers.ModelSerializer):
    image_data = serializers.SerializerMethodField()
    product_color = serializers.SerializerMethodField()

    class Meta:
        model = OfflineTemplateItem
        fields = '__all__'

    def get_image_data(self, obj):
        from app_core.models import ProductColor
        color = ProductColor.objects.filter(
            product__name=obj.product_name,
            color_name=obj.variant
        ).first()
        if color:
            if color.image_data:
                return color.image_data
            elif color.image:
                return color.image.url
        return ""

    def get_product_color(self, obj):
        from app_core.models import ProductColor
        color = ProductColor.objects.filter(
            product__name=obj.product_name,
            color_name=obj.variant
        ).first()
        return color.id if color else obj.id


class OfflineTemplateSerializer(serializers.ModelSerializer):
    items = OfflineTemplateItemSerializer(many=True, read_only=True)
    warehouse_name = serializers.SerializerMethodField()

    class Meta:
        model = OfflineTemplate
        fields = '__all__'

    def get_warehouse_name(self, obj):
        if obj.warehouse_id:
            from app_core.models import Warehouse
            wh = Warehouse.objects.filter(id=obj.warehouse_id).first()
            return wh.name if wh else "未分配"
        return "未分配"


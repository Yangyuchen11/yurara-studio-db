# app_assets/serializers.py
from rest_framework import serializers
from app_assets.models import (
    FixedAsset, FixedAssetLog, ConsumableItem, ConsumableLog
)

class FixedAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = FixedAsset
        fields = '__all__'


class FixedAssetLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FixedAssetLog
        fields = '__all__'


class ConsumableItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumableItem
        fields = '__all__'


class ConsumableLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumableLog
        fields = '__all__'

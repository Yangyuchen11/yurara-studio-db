# app_inventory/serializers.py
from rest_framework import serializers
from app_inventory.models import InventoryLog

class InventoryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryLog
        fields = '__all__'

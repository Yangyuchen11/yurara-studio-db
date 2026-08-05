# app_finance/serializers.py
from rest_framework import serializers
from app_finance.models import FinanceRecord, CompanyBalanceItem

class FinanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinanceRecord
        fields = '__all__'


class CompanyBalanceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyBalanceItem
        fields = '__all__'

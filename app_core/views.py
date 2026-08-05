# app_core/views.py
import asyncio
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from app_core.models import (
    Warehouse, Product, ProductColor, CostItem,
    SalesPlatform, MemoNote, SystemSetting
)
from app_core.serializers import (
    WarehouseSerializer, ProductSerializer, ProductColorSerializer,
    CostItemSerializer, SalesPlatformSerializer, MemoNoteSerializer,
    SystemSettingSerializer
)
from app_core.services.product_service import ProductService
from app_core.services.cost_service import CostService
from app_core.services.memo_service import get_all_memos, create_memo, update_memo, delete_memo
from app_core.services.rate_service import get_all_rates, set_rate, remove_rate, fetch_live_rates, fetch_live_rates_sync

class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.prefetch_related('colors__prices', 'colors__parts', 'costs').order_by('-id')
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def create_with_details(self, request):
        name = request.data.get('name')
        platform = request.data.get('platform')
        colors_with_prices = request.data.get('colors_with_prices', [])
        if not name:
            return Response({'error': '商品名は必須です。'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            prod = ProductService.create_product(name, platform, colors_with_prices)
            return Response(ProductSerializer(prod).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ProductColorViewSet(viewsets.ModelViewSet):
    queryset = ProductColor.objects.prefetch_related('prices', 'parts').all()
    serializer_class = ProductColorSerializer
    permission_classes = [IsAuthenticated]


class CostItemViewSet(viewsets.ModelViewSet):
    queryset = CostItem.objects.all().order_by('-id')
    serializer_class = CostItemSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def add_budget(self, request):
        product_id = request.data.get('product_id')
        category = request.data.get('category')
        name = request.data.get('name')
        unit_price = float(request.data.get('unit_price', 0))
        quantity = float(request.data.get('quantity', 1))
        unit = request.data.get('unit', '')
        remarks = request.data.get('remarks', '')
        currency = request.data.get('currency', 'CNY')

        if not product_id or not name:
            return Response({'error': 'product_id と name は必須です。'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cost = CostService.add_budget_item(product_id, category, name, unit_price, quantity, unit, remarks, currency)
            return Response(CostItemSerializer(cost).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def wip_fix(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id は必須です。'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            CostService.perform_wip_fix(int(product_id))
            return Response({'message': '生産完了 (WIP沖銷) が正常に適用されました。'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SalesPlatformViewSet(viewsets.ModelViewSet):
    queryset = SalesPlatform.objects.all().order_by('id')
    serializer_class = SalesPlatformSerializer
    permission_classes = [IsAuthenticated]


class MemoNoteViewSet(viewsets.ModelViewSet):
    queryset = MemoNote.objects.all().order_by('-created_at')
    serializer_class = MemoNoteSerializer
    permission_classes = [IsAuthenticated]


class RatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rates = get_all_rates()
        return Response({"rates": rates})

    def post(self, request):
        currency = request.data.get("currency")
        rate = request.data.get("rate")
        if not currency or rate is None:
            return Response({"error": "currency and rate are required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rate_val = float(rate)
            new_rate = set_rate(currency, rate_val)
            return Response({"message": "Rate updated successfully", "currency": currency, "rate": new_rate})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        currency = request.data.get("currency") or request.query_params.get("currency")
        if not currency:
            return Response({"error": "currency is required"}, status=status.HTTP_400_BAD_REQUEST)
        remove_rate(currency)
        return Response({"message": f"Rate for {currency} removed"})


class FetchLiveRatesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            updated = fetch_live_rates_sync()
            return Response({"message": "Live rates updated", "updated": updated})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

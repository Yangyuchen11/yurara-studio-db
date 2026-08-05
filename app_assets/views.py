# app_assets/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from app_assets.models import FixedAsset, FixedAssetLog, ConsumableItem, ConsumableLog
from app_assets.serializers import (
    FixedAssetSerializer, FixedAssetLogSerializer,
    ConsumableItemSerializer, ConsumableLogSerializer
)
from app_assets.services.asset_service import AssetService
from app_assets.services.consumable_service import ConsumableService
from app_core.services.rate_service import get_all_rates
from app_core.constants import to_cny
from app_finance.models import CompanyBalanceItem
from app_core.constants import AssetPrefix, BalanceCategory


class FixedAssetViewSet(viewsets.ModelViewSet):
    queryset = FixedAsset.objects.all().order_by('-id')
    serializer_class = FixedAssetSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def write_off(self, request, pk=None):
        decrease_qty = float(request.data.get('decrease_qty', 1.0))
        reason = request.data.get('reason', '')
        if not reason.strip():
            return Response({'error': '请填写核销原因说明'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            name = AssetService.write_off_asset(int(pk), int(decrease_qty), reason.strip())
            return Response({'message': f'成功核销资产: {name}'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def totals(self, request):
        assets = FixedAsset.objects.all()
        rates_map = get_all_rates()
        total_val, total_remain, total_jpy = AssetService.calculate_asset_totals(assets, rates_map)
        return Response({
            'total_cny': total_val,
            'total_cny_str': f"¥ {total_val:,.2f}",
            'remain_cny': total_remain,
            'remain_cny_str': f"¥ {total_remain:,.2f}",
            'remain_jpy': total_jpy,
            'remain_jpy_str': f"{total_jpy:,.0f} JPY"
        })


class FixedAssetLogViewSet(viewsets.ModelViewSet):
    queryset = FixedAssetLog.objects.all().order_by('-id')
    serializer_class = FixedAssetLogSerializer
    permission_classes = [IsAuthenticated]


class ConsumableItemViewSet(viewsets.ModelViewSet):
    queryset = ConsumableItem.objects.all().order_by('-id')
    serializer_class = ConsumableItemSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def movement(self, request):
        item_name = request.data.get('item_name')
        date_obj = request.data.get('date')
        delta_qty = int(request.data.get('change_qty', 0))
        mode = request.data.get('mode', 'normal')
        sale_info = request.data.get('sale_info')
        cost_info = request.data.get('cost_info')
        remark = request.data.get('remark', '')

        if not item_name or delta_qty == 0:
            return Response({'error': '请选择耗材项目并输入变动数量'}, status=status.HTTP_400_BAD_REQUEST)

        rates_map = get_all_rates()
        try:
            name, qty, link_msg = ConsumableService.process_inventory_change(
                item_name=item_name,
                date_obj=date_obj,
                delta_qty=delta_qty,
                rates_map=rates_map,
                mode=mode,
                sale_info=sale_info,
                cost_info=cost_info,
                base_remark=remark
            )
            return Response({'message': f'成功变动耗材库存: {name} ({qty:+d}件){link_msg}'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        items = ConsumableItem.objects.all()
        rates_map = get_all_rates()

        # Multi-currency indicators calculation
        curr_totals = {}
        grand_cny = 0.0

        for i in items:
            curr = getattr(i, 'currency', 'CNY') or 'CNY'
            val_orig = i.unit_price * i.remaining_qty
            val_cny = to_cny(val_orig, curr, rates_map)

            curr_totals[curr] = curr_totals.get(curr, 0.0) + val_orig
            grand_cny += val_cny

        valuation_indicators = []
        color_palette = ['violet', 'blue', 'emerald', 'amber', 'rose']
        for idx, (curr, amt) in enumerate(curr_totals.items()):
            amt_str = f"¥ {amt:,.2f}" if curr == 'CNY' else f"{amt:,.2f} {curr}"
            valuation_indicators.append({
                'currency': curr,
                'amount': amt,
                'amount_str': amt_str,
                'color': color_palette[idx % len(color_palette)]
            })

        # Cash Accounts for Consumable Sale
        cash_accounts = CompanyBalanceItem.objects.filter(
            name__startswith=AssetPrefix.CASH,
            category=BalanceCategory.ASSET
        ).order_by('id')

        account_options = [{'id': acc.id, 'label': f"{acc.name} ({acc.currency})"} for acc in cash_accounts]

        return Response({
            'grand_total_cny': grand_cny,
            'grand_total_cny_str': f"¥ {grand_cny:,.2f}",
            'valuation_indicators': valuation_indicators,
            'cash_accounts': account_options,
            'categories': list(set(i.category for i in items if i.category)),
            'currencies': list(set(i.currency for i in items if i.currency))
        })


class ConsumableLogViewSet(viewsets.ModelViewSet):
    queryset = ConsumableLog.objects.all().order_by('-id')
    serializer_class = ConsumableLogSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['patch'])
    def update_date(self, request, pk=None):
        log = self.get_object()
        new_date = request.data.get('date')
        if new_date:
            log.date = new_date
            log.save()
            return Response({'message': '日志日期已更正', 'date': str(log.date)})
        return Response({'error': 'date is required'}, status=status.HTTP_400_BAD_REQUEST)

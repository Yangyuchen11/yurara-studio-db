# app_finance/serializers.py
import re
from rest_framework import serializers
from app_finance.models import FinanceRecord, CompanyBalanceItem
from app_core.models import CostItem
from app_assets.models import FixedAsset, ConsumableItem

class FinanceRecordSerializer(serializers.ModelSerializer):
    child_items = serializers.SerializerMethodField()

    class Meta:
        model = FinanceRecord
        fields = '__all__'

    def get_child_items(self, obj):
        items = []
        try:
            # 1. CostItem by finance_record_id
            costs = CostItem.objects.filter(finance_record_id=obj.id)
            for c in costs:
                items.append({
                    'id': c.id,
                    'name': c.item_name,
                    'amount': c.original_amount if (hasattr(c, 'original_amount') and c.original_amount is not None) else c.actual_cost,
                    'qty': c.quantity or c.actual_qty or 1,
                    'desc': c.remarks or '',
                    'url': c.url or '',
                    'category': c.category or '商品成本',
                })

            # 2. FixedAsset
            fas = FixedAsset.objects.filter(finance_record_id=obj.id)
            for fa in fas:
                items.append({
                    'id': fa.id,
                    'name': fa.name,
                    'amount': (fa.unit_price or 0) * (fa.quantity or 1),
                    'qty': fa.quantity or 1,
                    'desc': fa.remarks or '',
                    'url': fa.url or '',
                    'category': '固定资产',
                })

            # 3. ConsumableItem
            cons = ConsumableItem.objects.filter(finance_record_id=obj.id)
            for con in cons:
                items.append({
                    'id': con.id,
                    'name': con.name,
                    'amount': (con.unit_price or 0) * (con.initial_quantity or 1),
                    'qty': con.initial_quantity or 1,
                    'desc': con.remarks or '',
                    'url': con.url or '',
                    'category': con.category or '其他资产',
                })

            # 4. SalesOrder Items (if order_id is set)
            if not items and obj.order_id:
                try:
                    from app_sales.models import SalesOrder
                    order = SalesOrder.objects.filter(id=obj.order_id).first()
                    if order:
                        for item in order.items.all():
                            items.append({
                                'id': item.id,
                                'name': item.product_name,
                                'amount': (item.unit_price or 0) * (item.quantity or 1),
                                'qty': item.quantity or 1,
                                'desc': f"规格: {item.variant}" if item.variant else '',
                                'url': '',
                                'category': '销售订单明细',
                            })
                except Exception:
                    pass

            # 5. CostItem by related_cost_id
            if not items and obj.related_cost_id:
                c = CostItem.objects.filter(id=obj.related_cost_id).first()
                if c:
                    items.append({
                        'id': c.id,
                        'name': c.item_name,
                        'amount': abs(obj.amount),
                        'qty': c.quantity or c.actual_qty or 1,
                        'desc': c.remarks or '',
                        'url': c.url or '',
                        'category': c.category or '商品成本',
                    })

            # 6. Description fallback parsing for legacy records
            if not items and obj.description:
                desc = obj.description.strip()
                if ' (x' in desc or ' | ' in desc:
                    parts = [p.strip() for p in desc.split(' | ') if p.strip()]
                    item_parts = [p for p in parts if not p.startswith('店铺:') and not p.startswith('账户:')]
                    if item_parts:
                        for idx, p in enumerate(item_parts):
                            qty_match = re.search(r'\(x([\d\.]+)\)', p)
                            qty = float(qty_match.group(1)) if qty_match else 1.0
                            clean_name = re.sub(r'\s*\(x[\d\.]+\)', '', p).strip()
                            items.append({
                                'id': idx + 1,
                                'name': clean_name or p,
                                'amount': abs(obj.amount) / len(item_parts),
                                'qty': qty,
                                'desc': p,
                                'url': obj.url or '',
                                'category': obj.category,
                            })
        except Exception:
            pass
        return items


class CompanyBalanceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyBalanceItem
        fields = '__all__'

# app_inventory/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from app_core.models import Product, Warehouse
from app_inventory.models import InventoryLog
from app_inventory.serializers import InventoryLogSerializer
from app_inventory.services.inventory_service import InventoryService


class InventoryLogViewSet(viewsets.ModelViewSet):
    queryset = InventoryLog.objects.all().order_by('-id')
    serializer_class = InventoryLogSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def movement(self, request):
        product_id = request.data.get('product_id')
        product_name = request.data.get('product_name')
        variant = request.data.get('variant')
        quantity = int(request.data.get('quantity', 0))
        move_type = request.data.get('move_type')
        date_obj = request.data.get('date')
        remark = request.data.get('remark', '')
        warehouse_id = request.data.get('warehouse_id')
        to_warehouse_id = request.data.get('to_warehouse_id') or request.data.get('target_warehouse_id')
        is_set = request.data.get('is_set', True)
        part_name = request.data.get('part_name')
        out_type = request.data.get('out_type')
        cons_cat = request.data.get('cons_cat')
        cons_content = request.data.get('cons_content')

        if not product_id or not product_name or not move_type:
            return Response({'error': '缺少必要参数 (product_id, product_name, move_type)。'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            msg = InventoryService.add_inventory_movement(
                product_id=int(product_id),
                product_name=product_name,
                variant=variant,
                quantity=quantity,
                move_type=move_type,
                date_obj=date_obj,
                remark=remark,
                warehouse_id=warehouse_id,
                to_warehouse_id=to_warehouse_id,
                is_set=is_set,
                part_name=part_name,
                out_type=out_type,
                cons_cat=cons_cat,
                cons_content=cons_content
            )
            return Response({'message': msg}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def cascade_delete(self, request, pk=None):
        try:
            msg = InventoryService.delete_log_cascade(int(pk))
            return Response({'message': msg})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['patch'])
    def update_note(self, request, pk=None):
        log = self.get_object()
        new_note = request.data.get('note')
        new_date = request.data.get('date')
        if new_note is not None:
            log.note = new_note
        if new_date is not None:
            log.date = new_date
        log.save()
        return Response({'message': '日志备注修改成功', 'note': log.note, 'date': str(log.date)})


class ClearWipView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            InventoryService.clear_wip_for_product(int(product_id))
            return Response({'message': '在制资产已清零重算'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventorySummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        product_id_param = request.query_params.get('product_id')
        products = Product.objects.all().order_by('id')
        product_list = [{'id': p.id, 'name': p.name, 'is_production_completed': p.is_production_completed} for p in products]

        selected_prod = None
        if product_id_param:
            try:
                selected_prod = products.filter(id=int(product_id_param)).first()
            except ValueError:
                pass
        if not selected_prod and products.exists():
            selected_prod = products.first()

        stats = {}
        wip_balance = 0.0
        wip_balance_str = "¥ 0.00"
        excess_parts = []

        if selected_prod:
            stats = InventoryService.get_stock_overview_by_parts(selected_prod.id, selected_prod.name)
            wip_balance = InventoryService.get_wip_balance(selected_prod.id)
            wip_balance_str = f"¥ {wip_balance:,.2f}"

            for v_name, v_stat in stats.items():
                for part_name, qty in v_stat.get("excess", {}).items():
                    if qty > 0:
                        excess_parts.append({
                            "variant": v_name,
                            "part_name": part_name,
                            "qty": qty
                        })

        wh_details = InventoryService.get_warehouse_inventory_details()
        warehouses_db = Warehouse.objects.all()

        warehouses_list = []
        total_quantity = 0

        for w in warehouses_db:
            w_info = wh_details.get(w.id, {})
            stock_map = w_info.get("stock", {})
            
            # Count total physical items in this warehouse
            w_total = 0
            for p_name, v_map in stock_map.items():
                for v_name, pt_map in v_map.items():
                    for pt_name, qty in pt_map.items():
                        if qty > 0:
                            w_total += qty

            is_empty = (w_total == 0)
            warehouses_list.append({
                "id": w.id,
                "name": w.name,
                "remarks": w.remarks or "",
                "is_empty": is_empty,
                "total_qty": w_total,
                "stock": stock_map
            })
            total_quantity += w_total

        return Response({
            "products": product_list,
            "selected_product_id": selected_prod.id if selected_prod else None,
            "selected_product_name": selected_prod.name if selected_prod else "",
            "is_production_completed": selected_prod.is_production_completed if selected_prod else False,
            "wip_balance": wip_balance,
            "wip_balance_str": wip_balance_str,
            "stats": stats,
            "excess_parts": excess_parts,
            "warehouses": warehouses_list,
            "warehouse_details": wh_details,
            "total_quantity": total_quantity
        })

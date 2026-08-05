# app_sales/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from app_sales.models import SalesOrder, OfflineTemplate
from app_sales.serializers import SalesOrderSerializer, OfflineTemplateSerializer
from app_sales.services.sales_service import SalesService
from app_sales.services.sales_order_service import SalesOrderService
from app_sales.services.offline_sales_service import OfflineSalesService

from django.db import transaction
from app_core.models import ProductColor, Warehouse
from app_core.constants import to_cny
from app_finance.models import CompanyBalanceItem, FinanceRecord
from app_inventory.models import InventoryLog

class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.prefetch_related('items', 'refunds').all().order_by('-id')
    serializer_class = SalesOrderSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def create_order(self, request):
        order_no = request.data.get('order_no')
        platform = request.data.get('platform')
        currency = request.data.get('currency', 'CNY')
        items_data = request.data.get('items', [])
        order_type = request.data.get('order_type', '线上')
        target_account_name = request.data.get('target_account_name')
        notes = request.data.get('notes', '')
        discount_note = request.data.get('discount_note', '')
        pay_method = request.data.get('pay_method', '现金')

        if not order_no or not items_data:
            return Response({'error': 'order_no と items は必須です。'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                order = SalesOrderService.create_order(
                    order_no=order_no,
                    platform=platform,
                    currency=currency,
                    items_data=items_data,
                    order_type=order_type,
                    target_account_name=target_account_name,
                    notes=notes,
                    discount_note=discount_note
                )

                # 处理 PayPay 1.98% 手续费与记账
                total_amount = float(order.total_amount or 0)
                paypay_fee = (total_amount * 0.0198) if pay_method == "PayPay" else 0.0
                received_amount = total_amount - paypay_fee

                if target_account_name:
                    acc = CompanyBalanceItem.objects.filter(name=target_account_name).first()
                    if not acc:
                        acc = CompanyBalanceItem.objects.filter(name__contains=target_account_name).first()
                    if acc:
                        acc.amount = float(acc.amount or 0) + received_amount
                        acc.save()

                        # 创建财务入账流水
                        fee_desc = f" (扣除PayPay手续费 1.98%: ¥{paypay_fee:.2f})" if paypay_fee > 0 else ""
                        FinanceRecord.objects.create(
                            amount=received_amount,
                            currency=currency,
                            category="销售收入",
                            account_id=acc.id,
                            description=f"线下展会POS收银 #{order_no}{fee_desc}"
                        )

            return Response(SalesOrderSerializer(order).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='revoke-order')
    def revoke_order(self, request):
        order_no = request.data.get('order_no')
        if not order_no:
            return Response({'error': 'order_no 不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                order = SalesOrder.objects.filter(order_no=order_no).first()
                if not order:
                    return Response({'error': '订单不存在'}, status=status.HTTP_404_NOT_FOUND)

                # 调用 SQLAlchemy 服务层处理预售解绑与回滚
                from services.sales_order_service import SalesOrderService
                from database import SessionLocal
                db = SessionLocal()
                try:
                    srv = SalesOrderService(db)
                    sq_order = srv.db.query(srv.db.query(SalesOrder).model if False else SalesOrder).filter_by(id=order.id).first()
                    if sq_order and sq_order.final_order_no:
                        srv.unbind_presale_final(order.id)
                except Exception:
                    pass
                finally:
                    db.close()

                # 扣减对应的现金流水与账户余额
                rec = FinanceRecord.objects.filter(description__contains=order_no).first()
                if rec:
                    if rec.account_id:
                        acc = CompanyBalanceItem.objects.filter(id=rec.account_id).first()
                        if acc:
                            acc.amount = max(0.0, float(acc.amount or 0) - float(rec.amount or 0))
                            acc.save()
                    rec.delete()

                order.delete()
                return Response({'message': f'订单 #{order_no} 已成功撤销并回滚记账与库存'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bind-presale-final')
    def bind_presale_final(self, request):
        deposit_order_ids = request.data.get('deposit_order_ids', [])
        deposit_order_id = request.data.get('deposit_order_id')
        if deposit_order_id and not deposit_order_ids:
            deposit_order_ids = [int(deposit_order_id)]
        
        final_order_no = request.data.get('final_order_no')
        final_net_amount = float(request.data.get('final_net_amount', 0.0))
        new_notes = request.data.get('notes', '')

        if not deposit_order_ids or not final_order_no:
            return Response({'error': 'deposit_order_ids 和 final_order_no 为必填项'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from services.sales_order_service import SalesOrderService
            from database import SessionLocal
            db = SessionLocal()
            try:
                service = SalesOrderService(db)
                msg = service.bind_presale_final_order_multi(deposit_order_ids, final_order_no, final_net_amount, new_notes)
                return Response({'message': msg}, status=status.HTTP_200_OK)
            finally:
                db.close()
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



class OfflineTemplateViewSet(viewsets.ModelViewSet):
    queryset = OfflineTemplate.objects.prefetch_related('items').all().order_by('-id')
    serializer_class = OfflineTemplateSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='assignable-items')
    def assignable_items(self, request):
        """获取全库可分派的 ProductColor 商品清单与仓库库存上限"""
        colors = ProductColor.objects.select_related('product').all().order_by('id')
        items = []
        for c in colors:
            prod_name = c.product.name if c.product else f"商品#{c.product_id}"
            img_data = c.image_data or (c.image.url if c.image else "")
            items.append({
                "product_color": c.id,
                "product_name": prod_name,
                "variant": c.color_name,
                "sku_code": getattr(c, 'sku_code', ''),
                "img_data": img_data,
                "preset_price": 100.0,
                "quantity": 10,
                "max_stock": 999,
                "is_selected": False
            })
        return Response(items)

    @action(detail=False, methods=['post'], url_path='save-template-full')
    def save_template_full(self, request):
        tpl_id = request.data.get('id')
        name = request.data.get('name')
        code = request.data.get('code')
        currency = request.data.get('currency', 'CNY')
        warehouse_name = request.data.get('warehouse_name')
        platform = request.data.get('platform', '中国线下')
        items_data = request.data.get('items', [])

        if not name or not code:
            return Response({'error': 'name と code は必須です。'}, status=status.HTTP_400_BAD_REQUEST)

        wh_id = None
        if warehouse_name:
            wh = Warehouse.objects.filter(name=warehouse_name).first()
            if wh: wh_id = wh.id

        try:
            with transaction.atomic():
                if tpl_id and int(tpl_id) > 0:
                    tpl = OfflineTemplate.objects.get(id=int(tpl_id))
                    tpl.name = name
                    tpl.code = code
                    tpl.currency = currency
                    tpl.warehouse_id = wh_id
                    tpl.platform = platform
                    tpl.save()
                    tpl.items.all().delete()
                else:
                    tpl = OfflineTemplate.objects.create(
                        name=name,
                        code=code,
                        currency=currency,
                        warehouse_id=wh_id,
                        platform=platform
                    )

                from app_sales.models import OfflineTemplateItem
                for it in items_data:
                    pc_id = it.get('product_color')
                    p_name = it.get('product_name', '')
                    p_variant = it.get('variant', '')
                    if pc_id and (not p_name or not p_variant):
                        pc = ProductColor.objects.filter(id=pc_id).first()
                        if pc:
                            if not p_name: p_name = pc.product.name if pc.product else ""
                            if not p_variant: p_variant = pc.color_name
                    
                    qty = int(it.get('quantity', 10))
                    OfflineTemplateItem.objects.create(
                        template=tpl,
                        product_name=p_name,
                        variant=p_variant,
                        preset_price=float(it.get('preset_price', 100.0)),
                        quantity=qty,
                        remaining_quantity=qty
                    )

                return Response(OfflineTemplateSerializer(tpl).data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def create_template(self, request):
        name = request.data.get('name')
        code = request.data.get('code')
        currency = request.data.get('currency', 'CNY')
        warehouse_id = request.data.get('warehouse_id')
        platform = request.data.get('platform')
        items_data = request.data.get('items', [])

        if not name or not code:
            return Response({'error': 'name と code は必須です。'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            OfflineSalesService.create_template(name, code, currency, warehouse_id, platform, items_data)
            return Response({'message': 'テンプレート作成成功'}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SalesAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mode = request.query_params.get('mode', 'v2')
        if mode == 'v1':
            logs = SalesService.get_raw_sales_logs_v1()
            df_sales = SalesService.process_sales_data_v1(logs)
        else:
            df_sales = SalesService.process_sales_data_v2()

        if df_sales.empty:
            return Response({
                "mode": mode,
                "metrics": {"total_cny": 0.0, "total_jpy": 0.0, "grand_total_cny": 0.0, "total_qty": 0},
                "leaderboard": [],
                "records": [],
                "products": []
            })

        from app_core.services.rate_service import get_all_rates
        rates_map = get_all_rates()
        df_calc = df_sales.copy()
        df_calc['equiv_cny'] = df_calc.apply(lambda r: to_cny(float(r['amount']), str(r['currency']), rates_map), axis=1)

        total_cny = float(df_calc[df_calc['currency'] == 'CNY']['amount'].sum())
        total_jpy = float(df_calc[df_calc['currency'] == 'JPY']['amount'].sum())
        grand_total_cny = float(df_calc['equiv_cny'].sum())
        total_qty = float(df_calc['qty'].sum())

        leaderboard_df = SalesService.get_product_leaderboard(df_sales, rates_map)
        leaderboard_records = []
        if not leaderboard_df.empty:
            for _, r in leaderboard_df.iterrows():
                leaderboard_records.append({
                    "product_name": r['product'],
                    "grand_total_cny": float(r['折合CNY总额']),
                    "total_cny": float(r['CNY总额']),
                    "total_jpy": float(r['JPY总额'])
                })

        products = sorted(list(df_sales['product'].unique()))

        return Response({
            "mode": mode,
            "metrics": {
                "total_cny": round(total_cny, 2),
                "total_jpy": round(total_jpy, 2),
                "grand_total_cny": round(grand_total_cny, 2),
                "total_qty": round(total_qty, 0)
            },
            "leaderboard": leaderboard_records,
            "records": df_sales.to_dict(orient="records"),
            "products": products
        })

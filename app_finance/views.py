# app_finance/views.py
import math
import re
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from app_finance.models import FinanceRecord, CompanyBalanceItem
from app_finance.serializers import FinanceRecordSerializer, CompanyBalanceItemSerializer
from app_finance.services.finance_service import FinanceService
from app_finance.services.balance_service import BalanceService
from app_core.constants import BalanceCategory, Currency, to_cny, AssetPrefix, PRODUCT_COST_CATEGORIES
from app_core.services.rate_service import get_all_rates
from app_core.models import Product, CostItem
from app_assets.models import ConsumableItem, FixedAsset


class FinanceRecordViewSet(viewsets.ModelViewSet):
    queryset = FinanceRecord.objects.all().order_by('-date', '-id')
    serializer_class = FinanceRecordSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """支持分页 + 搜索 + 业务大类筛选 + 细分类型筛选的流水列表"""
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        search_query = request.query_params.get('search', '').strip()
        filter_type = request.query_params.get('filter_type', '').strip()
        filter_category = request.query_params.get('filter_category', '').strip()

        records, total_count = FinanceService.get_finance_records_page(
            page=page, page_size=page_size,
            search_query=search_query,
            filter_type=filter_type,
            filter_category=filter_category
        )

        total_pages = max(1, math.ceil(total_count / page_size))

        serialized = []
        for r in records:
            desc_clean = re.sub(r'\s*\[cost_item:\d+\]', '', r["description"] or "")
            amt = r["amount"]
            cat = r["category"]
            # 判断收支方向
            rec_type = "收入" if amt > 0 and cat not in ("货币兑换", "转账-流出", "转账-流入") else "支出"
            if cat in ("货币兑换", "转账-流出", "转账-流入"):
                rec_type = cat

            serialized.append({
                "id": r["id"],
                "date": r["date"],
                "currency": r["currency"] or "CNY",
                "type": rec_type,
                "amount": round(abs(float(amt)), 2),
                "category": cat,
                "description": desc_clean,
                "url": r["url"] or "",
                "cny_bal": round(r["cny_bal"], 2),
                "jpy_bal": round(r["jpy_bal"], 2),
                "account_id": r["account_id"],
                "related_item_id": r["related_item_id"],
            })

        return Response({
            "results": serialized,
            "total_count": total_count,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
        })

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer(self, request):
        from_acc_id = request.data.get('from_account_id')
        to_acc_id = request.data.get('to_account_id')
        amount = float(request.data.get('amount', 0))
        date_str = request.data.get('date')
        desc = request.data.get('description', '账户资金划转')

        if not from_acc_id or not to_acc_id or amount <= 0:
            return Response({'error': '请选择转出/转入账户并输入有效金额'}, status=status.HTTP_400_BAD_REQUEST)
        if str(from_acc_id) == str(to_acc_id):
            return Response({'error': '转出和转入不能是同一个账户'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                from_acc = CompanyBalanceItem.objects.get(id=from_acc_id)
                to_acc = CompanyBalanceItem.objects.get(id=to_acc_id)

                from_acc.amount -= amount
                from_acc.save()

                to_acc.amount += amount
                to_acc.save()

                rec_out = FinanceRecord.objects.create(
                    date=date_str,
                    amount=-amount,
                    currency=from_acc.currency,
                    category="转账-流出",
                    description=f"【划转至 {to_acc.name}】{desc}",
                    account_id=from_acc.id
                )
                rec_in = FinanceRecord.objects.create(
                    date=date_str,
                    amount=amount,
                    currency=to_acc.currency,
                    category="转账-流入",
                    description=f"【从 {from_acc.name} 划入】{desc}",
                    account_id=to_acc.id,
                    related_item_id=rec_out.id
                )
                rec_out.related_item_id = rec_in.id
                rec_out.save()

                return Response({
                    'message': f'资金划转成功: {amount} 元',
                    'out_record': FinanceRecordSerializer(rec_out).data,
                    'in_record': FinanceRecordSerializer(rec_in).data
                })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create(self, request):
        items = request.data.get('items', [])
        date_str = request.data.get('date')
        category = request.data.get('category', '支出')
        currency = request.data.get('currency', 'CNY')
        account_id = request.data.get('account_id')
        shop = request.data.get('shop', '')
        shipping_fee = float(request.data.get('shipping_fee', 0))
        product_id = request.data.get('product_id')
        cost_cat = request.data.get('cost_cat', '')
        asset_cat = request.data.get('asset_cat', '')

        if not items and shipping_fee <= 0:
            return Response({'error': '明细列表不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        created_records = []
        with transaction.atomic():
            account = CompanyBalanceItem.objects.filter(id=account_id).first() if account_id else None
            items_total = sum(float(i.get('amount', 0)) for i in items)
            total_amount = items_total + shipping_fee

            first_url = ''
            for i in items:
                if i.get('url'):
                    first_url = i['url']
                    break

            # 1. 创建单条合并的主体流水记录 (Parent FinanceRecord)
            main_desc = f"购入 {len(items)} 项"
            if shop:
                main_desc += f" [{shop}]"

            main_rec = FinanceRecord.objects.create(
                date=date_str,
                amount=-items_total if items_total > 0 else 0,
                currency=currency,
                category=category,
                description=main_desc,
                url=first_url,
                account_id=account.id if account else None
            )
            created_records.append(main_rec)

            # 2. 为各个明细项创建子资产/成本记录并挂载 finance_record_id
            for item in items:
                amt = float(item.get('amount', 0))
                qty = float(item.get('qty', 1)) or 1.0
                unit_price = amt / qty if qty > 0 else 0.0

                if category == "商品成本":
                    from app_core.models import CostItem, Product
                    prod = Product.objects.filter(id=product_id).first() if product_id else None
                    if prod:
                        CostItem.objects.create(
                            product=prod,
                            item_name=item.get('name', ''),
                            actual_cost=amt,
                            original_amount=amt,
                            quantity=qty,
                            actual_qty=qty,
                            unit_price=unit_price,
                            actual_unit_price=unit_price,
                            supplier=shop,
                            category=cost_cat,
                            remarks=item.get('desc', ''),
                            finance_record_id=main_rec.id,
                            url=item.get('url', ''),
                            currency=currency
                        )
                elif category == "固定资产购入":
                    from app_assets.models import FixedAsset
                    FixedAsset.objects.create(
                        name=item.get('name', ''),
                        unit_price=unit_price,
                        quantity=int(qty),
                        remaining_qty=int(qty),
                        shop_name=shop,
                        remarks=item.get('desc', ''),
                        currency=currency,
                        finance_record_id=main_rec.id,
                        url=item.get('url', '')
                    )
                elif category == "其他资产购入":
                    from app_assets.models import ConsumableItem, ConsumableLog
                    target_item = ConsumableItem.objects.filter(name=item.get('name', '')).first()
                    if target_item:
                        old_total = target_item.unit_price * target_item.remaining_qty
                        target_item.remaining_qty += int(qty)
                        if target_item.remaining_qty > 0:
                            target_item.unit_price = (old_total + amt) / target_item.remaining_qty
                        if shop:
                            target_item.shop_name = shop
                        if asset_cat:
                            target_item.category = asset_cat
                        target_item.save()
                    else:
                        ConsumableItem.objects.create(
                            name=item.get('name', ''),
                            category=asset_cat or '其他',
                            unit_price=unit_price,
                            initial_quantity=int(qty),
                            remaining_qty=int(qty),
                            shop_name=shop,
                            remarks=item.get('desc', ''),
                            currency=currency,
                            finance_record_id=main_rec.id,
                            url=item.get('url', '')
                        )
                    ConsumableLog.objects.create(
                        item_name=item.get('name', ''),
                        change_qty=int(qty),
                        value_cny=amt,
                        note=f"批量购入入库: {item.get('desc', '')}",
                        date=date_str
                    )

            # 3. 共同邮费作为单独一条流水记录
            if shipping_fee > 0:
                rec_ship = FinanceRecord.objects.create(
                    date=date_str,
                    amount=-shipping_fee,
                    currency=currency,
                    category=category,
                    description=f"共同邮费 | 店铺:{shop}" if shop else "共同邮费",
                    account_id=account.id if account else None
                )
                created_records.append(rec_ship)

            # 4. 扣减账户余额
            if account and total_amount > 0:
                account.amount -= total_amount
                account.save()

        return Response({
            'message': f'批量录入成功: 关联创建 1 条合并主体流水账，总计 {total_amount:.2f}',
            'records': FinanceRecordSerializer(created_records, many=True).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='exchange')
    def exchange(self, request):
        src_acc_id = request.data.get('source_account_id')
        tgt_acc_id = request.data.get('target_account_id')
        amt_out = float(request.data.get('amount_out', 0))
        amt_in = float(request.data.get('amount_in', 0))
        src_curr = request.data.get('source_currency', 'CNY')
        tgt_curr = request.data.get('target_currency', 'JPY')
        date_str = request.data.get('date')
        desc = request.data.get('description', '货币资金兑换')

        if not src_acc_id or not tgt_acc_id or amt_out <= 0 or amt_in <= 0:
            return Response({'error': '请选择划出与划入账户并输入有效金额'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                src_acc = CompanyBalanceItem.objects.get(id=src_acc_id)
                tgt_acc = CompanyBalanceItem.objects.get(id=tgt_acc_id)

                src_acc.amount -= amt_out
                src_acc.save()

                tgt_acc.amount += amt_in
                tgt_acc.save()

                rec_out = FinanceRecord.objects.create(
                    date=date_str,
                    amount=-amt_out,
                    currency=src_curr,
                    category="货币兑换",
                    description=f"【兑出至 {tgt_acc.name} ({amt_in} {tgt_curr})】{desc}",
                    account_id=src_acc.id
                )
                rec_in = FinanceRecord.objects.create(
                    date=date_str,
                    amount=amt_in,
                    currency=tgt_curr,
                    category="货币兑换",
                    description=f"【从 {src_acc.name} 兑入 ({amt_out} {src_curr})】{desc}",
                    account_id=tgt_acc.id,
                    related_item_id=rec_out.id
                )
                rec_out.related_item_id = rec_in.id
                rec_out.save()

                return Response({
                    'message': '💱 货币兑换成功',
                    'out_record': FinanceRecordSerializer(rec_out).data,
                    'in_record': FinanceRecordSerializer(rec_in).data
                })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='debt-create')
    def debt_create(self, request):
        debt_name = request.data.get('debt_name')
        destination = request.data.get('destination', 'cash')
        amount = float(request.data.get('amount', 0))
        currency = request.data.get('currency', 'CNY')
        target_acc_id = request.data.get('target_account_id')
        rel_asset_name = request.data.get('related_asset_name', '')
        creditor = request.data.get('creditor', '')
        remark = request.data.get('remark', '')
        date_str = request.data.get('date')

        if not debt_name or amount <= 0:
            return Response({'error': '债务名称和金额为必填项'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                liability = CompanyBalanceItem.objects.create(
                    category='liability',
                    name=f"债务:{debt_name}",
                    amount=amount,
                    currency=currency,
                    asset_type='负债'
                )

                if destination == 'cash' and target_acc_id:
                    acc = CompanyBalanceItem.objects.get(id=target_acc_id)
                    acc.amount += amount
                    acc.save()

                    FinanceRecord.objects.create(
                        date=date_str,
                        amount=amount,
                        currency=currency,
                        category="投资",
                        description=f"【债务资金注资: {debt_name}】{creditor} - {remark}".strip(' -'),
                        account_id=acc.id
                    )
                elif destination == 'asset' and rel_asset_name:
                    CompanyBalanceItem.objects.create(
                        category='asset',
                        name=rel_asset_name,
                        amount=amount,
                        currency=currency,
                        asset_type='挂账资产'
                    )

                return Response({
                    'message': '📝 新增债务成功',
                    'liability': CompanyBalanceItemSerializer(liability).data
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='debt-repay')
    def debt_repay(self, request):
        debt_id = request.data.get('debt_id')
        repay_type = request.data.get('repay_type', 'cash')
        amount = float(request.data.get('amount', 0))
        source_acc_id = request.data.get('source_account_id')
        offset_asset_id = request.data.get('offset_asset_id')
        remark = request.data.get('remark', '')
        date_str = request.data.get('date')

        if not debt_id or amount <= 0:
            return Response({'error': '请选择目标债务并输入有效偿还金额'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                debt = CompanyBalanceItem.objects.get(id=debt_id, category='liability')
                debt.amount = max(0.0, debt.amount - amount)
                debt.save()

                if repay_type == 'cash' and source_acc_id:
                    acc = CompanyBalanceItem.objects.get(id=source_acc_id)
                    acc.amount -= amount
                    acc.save()

                    FinanceRecord.objects.create(
                        date=date_str,
                        amount=-amount,
                        currency=acc.currency,
                        category="撤资",
                        description=f"【偿还债务: {debt.name}】{remark}".strip(),
                        account_id=acc.id
                    )
                elif repay_type == 'offset' and offset_asset_id:
                    asset = CompanyBalanceItem.objects.get(id=offset_asset_id)
                    asset.amount = max(0.0, asset.amount - amount)
                    asset.save()

                msg = '💸 债务资金偿还成功' if repay_type == 'cash' else '🔄 资产抵债核销成功'
                return Response({'message': msg, 'remaining_debt': debt.amount})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='unsettled-debts')
    def unsettled_debts(self, request):
        debts = CompanyBalanceItem.objects.filter(category='liability', amount__gt=0).order_by('id')
        results = []
        for d in debts:
            source_type = ""
            if d.name.startswith("商品成本待付款:"):
                source_type = "商品成本待付款"
            elif d.name.startswith("其他待付款:"):
                source_type = "其他待付款"
            results.append({
                **CompanyBalanceItemSerializer(d).data,
                "source_type": source_type,
                "label": f"{d.name} (待还余额: {d.amount:,.2f})"
            })
        return Response(results)

    @action(detail=False, methods=['get'], url_path='offset-assets')
    def offset_assets(self, request):
        """获取可用于抵债的资产项列表"""
        assets = CompanyBalanceItem.objects.filter(category=BalanceCategory.ASSET).exclude(
            name__startswith="在制"
        ).exclude(
            name__startswith="预入库"
        ).exclude(
            name__startswith="流动资金"
        ).order_by('id')
        results = [{
            **CompanyBalanceItemSerializer(a).data,
            "label": f"{a.name} (余额: {a.amount:,.2f})"
        } for a in assets]
        return Response(results)

    @action(detail=False, methods=['get'], url_path='cash-accounts')
    def cash_accounts(self, request):
        """获取可操作的现金账户列表"""
        all_items = CompanyBalanceItem.objects.all().order_by('currency', 'id')
        accs = [i for i in all_items if is_cash_item(i)]
        curr = request.query_params.get('currency')
        if curr:
            accs = [i for i in accs if i.currency == curr]
        excluded_names = {"流动资金(CNY)", "流动资金(JPY)", "流动资金（CNY）", "流动资金（JPY）", "资金(CNY)", "资金(JPY)"}
        results = [{
            **CompanyBalanceItemSerializer(a).data,
            "label": f"[{a.currency}] {a.name} (余额: {a.amount:,.2f})"
        } for a in accs if a.name not in excluded_names]
        return Response(results)

    @action(detail=False, methods=['get'], url_path='consumable-items')
    def consumable_items(self, request):
        """获取现有消耗品/其他资产列表(用于补充库存)"""
        items = ConsumableItem.objects.all().order_by('id')
        results = [{
            "id": c.id,
            "name": c.name,
            "category": c.category or "",
            "label": c.name,
        } for c in items]
        return Response(results)

    @action(detail=False, methods=['get'], url_path='budget-items')
    def budget_items(self, request):
        """联动获取指定商品+成本分类下的预算项"""
        product_id = request.query_params.get('product_id')
        category = request.query_params.get('category', '')
        if not product_id:
            return Response([])
        items = FinanceService.get_budget_items(int(product_id), category)
        results = [{
            "id": b.id,
            "label": b.item_name or f"预算#{b.id}",
            "item_name": b.item_name or "",
            "quantity": float(b.quantity or 0),
            "unit_price": float(b.unit_price or 0),
            "total": float(b.quantity or 0) * float(b.unit_price or 0),
            "actual_cost": float(b.actual_cost or 0),
        } for b in items]
        return Response(results)

    @action(detail=False, methods=['post'], url_path='create-general')
    def create_general(self, request):
        """通用单笔收支记账 (含非现金操作)"""
        date_str = request.data.get('date')
        rec_type = request.data.get('type', '支出')
        category = request.data.get('category', '')
        amount = float(request.data.get('amount', 0))
        currency = request.data.get('currency', 'CNY')
        shop = request.data.get('shop', '')
        desc = request.data.get('description', '')
        url = request.data.get('url', '')
        account_id = request.data.get('account_id')
        is_non_cash = request.data.get('is_non_cash', False)

        if amount <= 0:
            return Response({'error': '金额必须大于0'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                signed_amount = amount if rec_type == "收入" else -amount

                desc_parts = []
                if desc:
                    desc_parts.append(desc)
                if shop:
                    desc_parts.append(f"店铺:{shop}")
                full_desc = " | ".join(desc_parts) if desc_parts else f"{category}流水"

                rec = FinanceRecord.objects.create(
                    date=date_str,
                    amount=signed_amount,
                    currency=currency,
                    category=category,
                    description=full_desc,
                    url=url or None,
                    account_id=int(account_id) if account_id and not is_non_cash else None,
                )

                # 如果不是非现金操作，更新账户余额
                if not is_non_cash and account_id:
                    acc = CompanyBalanceItem.objects.get(id=int(account_id))
                    acc.amount += signed_amount
                    acc.save()

                return Response({
                    'message': f'💾 记账成功: {category} {amount} {currency}',
                    'record': FinanceRecordSerializer(rec).data
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='create-pending')
    def create_pending(self, request):
        """创建待付款记录 (商品成本待付款 / 其他待付款)"""
        date_str = request.data.get('date')
        category = request.data.get('category', '其他待付款')
        currency = request.data.get('currency', 'CNY')
        total_amount = float(request.data.get('total_amount', 0))
        shop = request.data.get('shop', '')
        desc = request.data.get('description', '')
        items = request.data.get('items', [])
        shipping_fee = float(request.data.get('shipping_fee', 0))

        if total_amount <= 0 and not items:
            return Response({'error': '请输入有效金额或添加明细'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 计算实际总金额
                if items:
                    items_total = sum(float(i.get('amount', 0)) for i in items)
                    total_amount = items_total + shipping_fee

                # 创建负债记录
                liability_name = f"{category}:{desc}" if desc else f"{category}:{shop}"
                liability = CompanyBalanceItem.objects.create(
                    category='liability',
                    name=liability_name,
                    amount=total_amount,
                    currency=currency,
                    asset_type='负债'
                )

                # 创建流水记录
                desc_parts = [desc] if desc else []
                if shop:
                    desc_parts.append(f"店铺:{shop}")
                full_desc = " | ".join(desc_parts) if desc_parts else f"{category}"

                rec = FinanceRecord.objects.create(
                    date=date_str,
                    amount=-total_amount,
                    currency=currency,
                    category=category,
                    description=full_desc,
                )

                return Response({
                    'message': f'📋 {category}记录创建成功: {total_amount:.2f} {currency}',
                    'record': FinanceRecordSerializer(rec).data,
                    'liability': CompanyBalanceItemSerializer(liability).data,
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='delete-with-cascade')
    def delete_with_cascade(self, request):
        """带级联保护的流水删除"""
        record_id = request.data.get('record_id')
        include_budget = request.data.get('include_budget', False)

        if not record_id:
            return Response({'error': '请指定要删除的记录ID'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                rec = FinanceRecord.objects.get(id=record_id)

                # 保护核心销售流水
                if rec.category == "销售收入" and rec.order_id:
                    return Response(
                        {'error': '此笔为销售收入流水，请去线上订单列表删除，严禁在此直接删除核心流水。'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                msg = f'🗑️ 流水记录已删除 (ID: {record_id})'

                # 检查是否为成对的兑换/转账流水 (通过 related_item_id 关联)
                paired_rec = None
                if rec.related_item_id and rec.category in ("货币兑换", "转账-流出", "转账-流入", "资金移动"):
                    paired_rec = FinanceRecord.objects.filter(id=rec.related_item_id).first()

                # 回滚配对记录并物理删除
                if paired_rec:
                    if paired_rec.account_id:
                        try:
                            p_acc = CompanyBalanceItem.objects.get(id=paired_rec.account_id)
                            p_acc.amount -= paired_rec.amount  # 回滚配对账户余额
                            p_acc.save()
                        except CompanyBalanceItem.DoesNotExist:
                            pass
                    paired_rec.delete()
                    msg = f'🗑️ 兑换/转账配对流水已双向同步安全回滚与删除 (ID: {record_id} & {paired_rec.id})'

                # 如果主记录有关联账户，回滚余额
                if rec.account_id:
                    try:
                        acc = CompanyBalanceItem.objects.get(id=rec.account_id)
                        acc.amount -= rec.amount  # 回滚: 减去原来添加的金额
                        acc.save()
                    except CompanyBalanceItem.DoesNotExist:
                        pass

                # 如果关联预算且选择级联删除
                if include_budget and rec.related_item_id and not paired_rec:
                    try:
                        CostItem.objects.filter(id=rec.related_item_id).delete()
                    except Exception:
                        pass

                rec.delete()
                return Response({'message': msg})
        except FinanceRecord.DoesNotExist:
            return Response({'error': '记录不存在'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


def is_cash_item(item):
    if item.category != BalanceCategory.ASSET:
        return False
    name = item.name or ""
    atype = getattr(item, 'asset_type', '') or ""
    return name.startswith("资金") or name.startswith("流动资金") or "现金" in atype or "账户" in name


class CompanyBalanceItemViewSet(viewsets.ModelViewSet):
    queryset = CompanyBalanceItem.objects.all().order_by('id')
    serializer_class = CompanyBalanceItemSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='add-account')
    def add_account(self, request):
        name = request.data.get('name', '').strip()
        curr = request.data.get('currency', 'CNY').strip()
        if not name:
            return Response({'error': '账户名称不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        full_name = f"资金-{name}"
        if CompanyBalanceItem.objects.filter(name=full_name).exists():
            return Response({'error': f'账户 {full_name} 已存在'}, status=status.HTTP_400_BAD_REQUEST)
        acc = CompanyBalanceItem.objects.create(
            category=BalanceCategory.ASSET,
            name=full_name,
            amount=0.0,
            currency=curr,
            asset_type="现金"
        )
        return Response(CompanyBalanceItemSerializer(acc).data, status=status.HTTP_201_CREATED)


class FinancialSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rates_map = get_all_rates()

        # 从数据库统计多货币数据
        all_balance_items = list(CompanyBalanceItem.objects.all())
        cash_items = [i for i in all_balance_items if is_cash_item(i)]

        # 收集系统所有出现的货币
        all_currencies = set()
        for i in cash_items:
            if i.currency: all_currencies.add(i.currency)
        for i in all_balance_items:
            if i.currency: all_currencies.add(i.currency)
        all_currencies.discard("CNY")
        summary_currencies = sorted(list(all_currencies))
        display_currencies = ["CNY"] + summary_currencies

        # 分类累加字典 { currency: float }
        def sum_by_curr(items):
            res = {c: 0.0 for c in display_currencies}
            for item in items:
                c = item.currency or "CNY"
                if c not in res: res[c] = 0.0
                res[c] += float(item.amount or 0)
            return res

        cash_amts = sum_by_curr(cash_items)

        fixed_assets = list(FixedAsset.objects.all())
        fixed_amts = {c: 0.0 for c in display_currencies}
        for fa in fixed_assets:
            c = getattr(fa, 'currency', 'CNY') or 'CNY'
            if c not in fixed_amts: fixed_amts[c] = 0.0
            fixed_amts[c] += float(fa.unit_price or 0) * float(fa.remaining_qty or 0)

        consumables = list(ConsumableItem.objects.all())
        cons_amts = {c: 0.0 for c in display_currencies}
        for ca in consumables:
            c = getattr(ca, 'currency', 'CNY') or 'CNY'
            if c not in cons_amts: cons_amts[c] = 0.0
            cons_amts[c] += float(ca.unit_price or 0) * float(ca.remaining_qty or 0)

        manual_assets = [
            i for i in all_balance_items
            if i.category == BalanceCategory.ASSET
            and not is_cash_item(i)
            and not (i.name and i.name.startswith("在制资产冲销-"))
            and not (i.name and i.name.startswith("预入库"))
        ]
        offset_items = [
            i for i in all_balance_items
            if i.category == BalanceCategory.ASSET
            and i.name and i.name.startswith("在制资产冲销-")
        ]
        liabilities = [i for i in all_balance_items if i.category == BalanceCategory.LIABILITY]
        equities = [i for i in all_balance_items if i.category == BalanceCategory.EQUITY]

        manual_amts = sum_by_curr(manual_assets)
        liab_amts = sum_by_curr(liabilities)
        eq_amts = sum_by_curr(equities)

        # WIP 在制资产 (总成本 + 冲销值)
        offset_map = {}
        for off in offset_items:
            p_name = off.name.replace("在制资产冲销-", "").strip()
            offset_map[p_name] = offset_map.get(p_name, 0.0) + float(off.amount or 0)

        wip_total_cny = 0.0
        wip_list = []
        products = list(Product.objects.all())
        for p in products:
            total_cost = sum(float(ci.actual_cost or 0) for ci in CostItem.objects.filter(product_id=p.id))
            offset_val = offset_map.get(p.name, 0.0)
            net_wip = total_cost + offset_val
            if net_wip > 1.0:
                wip_list.append((p.name, net_wip))
                wip_total_cny += net_wip

        pure_asset_amts = {c: fixed_amts.get(c, 0.0) + cons_amts.get(c, 0.0) + manual_amts.get(c, 0.0) for c in display_currencies}
        pure_asset_amts["CNY"] += wip_total_cny

        total_asset_amts = {c: cash_amts.get(c, 0.0) + pure_asset_amts.get(c, 0.0) for c in display_currencies}
        net_amts = {c: total_asset_amts.get(c, 0.0) - liab_amts.get(c, 0.0) for c in display_currencies}

        # 辅助生成 KPI Item 数组
        def make_kpi_items(dict_by_curr):
            res = []
            for c in display_currencies:
                amt = dict_by_curr.get(c, 0.0)
                equiv = to_cny(amt, c, rates_map)
                res.append({
                    "currency": c,
                    "amount": round(amt, 2),
                    "amount_str": f"¥ {amt:,.2f}" if c == "CNY" else f"{amt:,.2f} {c}",
                    "amount_cny_equiv": round(equiv, 2),
                    "amount_cny_str": f"¥ {equiv:,.2f}"
                })
            return res

        def total_cny_for(dict_by_curr):
            return sum(to_cny(v, c, rates_map) for c, v in dict_by_curr.items())

        cash_total_cny = total_cny_for(cash_amts)
        pure_asset_total_cny = total_cny_for(pure_asset_amts)
        total_asset_total_cny = total_cny_for(total_asset_amts)
        liab_total_cny = total_cny_for(liab_amts)
        eq_total_cny = total_cny_for(eq_amts)
        net_total_cny = total_cny_for(net_amts)

        # 构建明细行 (多货币动态列)
        def build_display_rows(items_list):
            grouped = {}
            for item in items_list:
                amt = float(item.amount or 0)
                if abs(amt) < 0.01: continue
                name = item.name
                curr = item.currency or "CNY"
                if name not in grouped: grouped[name] = {c: 0.0 for c in display_currencies}
                if curr not in grouped[name]: grouped[name][curr] = 0.0
                grouped[name][curr] += amt

            rows = []
            for name, amts in grouped.items():
                amts_str = {}
                tot_cny = 0.0
                for c in display_currencies:
                    v = amts.get(c, 0.0)
                    if abs(v) > 0.001:
                        amts_str[c] = f"{v:,.2f}"
                        tot_cny += to_cny(v, c, rates_map)
                    else:
                        amts_str[c] = "-"
                rows.append({
                    "item_name": name,
                    "amounts_by_currency": amts_str,
                    "total_cny_str": f"¥ {tot_cny:,.2f}"
                })
            return rows

        assets_rows = []
        for ca in cash_items:
            amt = float(ca.amount or 0)
            if abs(amt) < 0.01: continue
            curr = ca.currency or "CNY"
            amts_str = {c: "-" for c in display_currencies}
            amts_str[curr] = f"{amt:,.2f}"
            tot_cny = to_cny(amt, curr, rates_map)
            assets_rows.append({
                "item_name": f"💵 {ca.name}",
                "amounts_by_currency": amts_str,
                "total_cny_str": f"¥ {tot_cny:,.2f}"
            })

        if any(v > 0 for v in fixed_amts.values()):
            amts_str = {c: f"{v:,.2f}" if v > 0 else "-" for c, v in fixed_amts.items()}
            assets_rows.append({
                "item_name": "固定资产(设备)",
                "amounts_by_currency": amts_str,
                "total_cny_str": f"¥ {total_cny_for(fixed_amts):,.2f}"
            })

        if any(v > 0 for v in cons_amts.values()):
            amts_str = {c: f"{v:,.2f}" if v > 0 else "-" for c, v in cons_amts.items()}
            assets_rows.append({
                "item_name": "其他资产",
                "amounts_by_currency": amts_str,
                "total_cny_str": f"¥ {total_cny_for(cons_amts):,.2f}"
            })

        for p_name, net_val in wip_list:
            amts_str = {c: "-" for c in display_currencies}
            amts_str["CNY"] = f"{net_val:,.2f}"
            assets_rows.append({
                "item_name": f"📦 在制资产-{p_name}",
                "amounts_by_currency": amts_str,
                "total_cny_str": f"¥ {net_val:,.2f}"
            })

        assets_rows.extend(build_display_rows(manual_assets))
        liabilities_rows = build_display_rows(liabilities)
        equities_rows = build_display_rows(equities)

        # 动态多币种现金卡片
        indicators = []
        colors_palette = ["emerald", "blue", "purple", "pink", "teal", "indigo"]
        color_idx = 0

        cny_total = cash_amts.get("CNY", 0.0)
        indicators.append({
            "currency": "CNY",
            "amount_str": f"¥ {cny_total:,.2f}",
            "cny_equiv_str": "CNY",
            "color": "emerald"
        })
        for curr in summary_currencies:
            amt = cash_amts.get(curr, 0.0)
            equiv = to_cny(amt, curr, rates_map)
            indicators.append({
                "currency": curr,
                "amount_str": f"{amt:,.2f} {curr}",
                "cny_equiv_str": f"折合 ¥ {equiv:,.2f}",
                "color": colors_palette[color_idx % len(colors_palette)]
            })
            color_idx += 1

        def serialize_item(i):
            return CompanyBalanceItemSerializer(i).data if i else None

        return Response({
            "cash_items": [serialize_item(i) for i in cash_items],
            "manual_assets": [serialize_item(i) for i in manual_assets],
            "liabilities": [serialize_item(i) for i in liabilities],
            "equities": [serialize_item(i) for i in equities],
            "summary_currencies": summary_currencies,
            "display_currencies": display_currencies,
            "cash_by_currency": make_kpi_items(cash_amts),
            "pure_asset_by_currency": make_kpi_items(pure_asset_amts),
            "total_asset_by_currency": make_kpi_items(total_asset_amts),
            "liability_by_currency": make_kpi_items(liab_amts),
            "equity_by_currency": make_kpi_items(eq_amts),
            "net_by_currency": make_kpi_items(net_amts),
            "cash_total_cny": cash_total_cny,
            "pure_asset_total_cny": pure_asset_total_cny,
            "total_asset_total_cny": total_asset_total_cny,
            "liability_total_cny": liab_total_cny,
            "equity_total_cny": eq_total_cny,
            "net_total_cny": net_total_cny,
            "cash_total_str": f"¥ {cash_total_cny:,.2f}",
            "pure_asset_total_str": f"¥ {pure_asset_total_cny:,.2f}",
            "total_asset_total_str": f"¥ {total_asset_total_cny:,.2f}",
            "liability_total_str": f"¥ {liab_total_cny:,.2f}",
            "equity_total_str": f"¥ {eq_total_cny:,.2f}",
            "net_total_str": f"¥ {net_total_cny:,.2f}",
            "assets_rows": assets_rows,
            "liabilities_rows": liabilities_rows,
            "equities_rows": equities_rows,
            "dynamic_cash_indicators": indicators,
            "total_cash_cny_str": f"¥ {cash_total_cny:,.2f}",
            "all_currencies": ["CNY"] + summary_currencies,
            # 向后兼容
            "total_cash_cny": cash_total_cny,
            "total_assets_cny": pure_asset_total_cny,
            "total_liabilities_cny": liab_total_cny,
            "net_equity_cny": net_total_cny,
        })


class FinancialReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import datetime
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report_type = params.get('report_type', 'month')
        year = params.get('year', str(datetime.now().year))
        month = params.get('month', datetime.now().strftime('%Y-%m'))
        rates_map = get_all_rates()

        records = list(FinanceRecord.objects.all())
        if not records:
            return Response({"has_data": False})

        # 可选年份和月份列表
        record_dates = [r.date for r in records if r.date]
        years = sorted(list(set(d.strftime('%Y') for d in record_dates)), reverse=True) or [str(datetime.now().year)]
        months = sorted(list(set(d.strftime('%Y-%m') for d in record_dates)), reverse=True) or [datetime.now().strftime('%Y-%m')]

        period_key = month if report_type == "month" else year

        # 数据分类
        PL_INCOME = ["销售收入", "其他现金收入"]
        PL_EXPENSE = ["商品成本", "退款", "其他", "分红"]
        ASSET_ADD = ["固定资产购入", "其他资产购入", "现有资产增加", "新资产增加", "其他资产增加"]
        ASSET_SUB = ["现有资产减少"]
        LIAB_ADD = ["借入资金", "新增挂账资产"]
        LIAB_SUB = ["债务偿还", "资产抵消"]
        EQUITY_ADD = ["投资"]
        EQUITY_SUB = ["撤资"]

        filtered_recs = []
        for r in records:
            r_year = r.date.strftime('%Y') if r.date else ""
            r_month = r.date.strftime('%Y-%m') if r.date else ""
            in_period = (r_month == period_key) if report_type == "month" else (r_year == period_key)

            amt = float(r.amount or 0)
            cny_equiv = to_cny(amt, r.currency or "CNY", rates_map)
            is_cash_flow = r.category not in ["现有资产增加", "新资产增加", "现有资产减少", "其他资产增加", "资产抵消", "取消/冲销", "新增挂账资产"]

            filtered_recs.append({
                "id": r.id,
                "date": r.date,
                "year": r_year,
                "month": r_month,
                "amount": amt,
                "currency": r.currency or "CNY",
                "category": r.category or "",
                "account_id": r.account_id,
                "cny_equiv": cny_equiv,
                "is_cash_flow": is_cash_flow,
                "in_period": in_period,
            })

        curr_period_recs = [r for r in filtered_recs if r["in_period"]]

        # 1. 资金账户变动与期初期末逆推
        all_accs = list(CompanyBalanceItem.objects.filter(category=BalanceCategory.ASSET))
        cash_accounts = [a for a in all_accs if is_cash_item(a)]
        acc_summary = []

        total_opening_cash = 0.0
        total_net_cash = 0.0
        total_closing_cash = 0.0

        for acc in cash_accounts:
            current_db_bal = float(acc.amount or 0)
            curr = acc.currency or "CNY"

            # 属于此账户的流水
            acc_recs = [r for r in filtered_recs if r["is_cash_flow"] and (r.get("account_id") == acc.id or not r.get("account_id"))]

            if report_type == "month":
                future_recs = [r for r in acc_recs if r["month"] > period_key]
                curr_recs = [r for r in acc_recs if r["month"] == period_key]
            else:
                future_recs = [r for r in acc_recs if r["year"] > period_key]
                curr_recs = [r for r in acc_recs if r["year"] == period_key]

            future_net = sum(r["amount"] for r in future_recs)
            curr_net = sum(r["amount"] for r in curr_recs)
            closing_bal = current_db_bal - future_net
            opening_bal = closing_bal - curr_net

            curr_in = sum(r["amount"] for r in curr_recs if r["amount"] > 0)
            curr_out = abs(sum(r["amount"] for r in curr_recs if r["amount"] < 0))

            if abs(opening_bal) < 0.01 and abs(closing_bal) < 0.01 and curr_in < 0.01 and curr_out < 0.01:
                continue

            rate = to_cny(1.0, curr, rates_map)
            total_opening_cash += opening_bal * rate
            total_net_cash += curr_net * rate
            total_closing_cash += closing_bal * rate

            acc_summary.append({
                "account_name": acc.name,
                "currency": curr,
                "opening_balance": opening_bal,
                "inflow": curr_in,
                "outflow": curr_out,
                "net_change": curr_net,
                "closing_balance": closing_bal,
                "opening_str": f"{curr} {opening_bal:,.2f}" if curr == "CNY" else f"{curr} {opening_bal:,.0f}",
                "inflow_str": f"{curr} {curr_in:,.2f}" if curr == "CNY" else f"{curr} {curr_in:,.0f}",
                "outflow_str": f"{curr} {curr_out:,.2f}" if curr == "CNY" else f"{curr} {curr_out:,.0f}",
                "net_str": f"{curr} {curr_net:,.2f}" if curr == "CNY" else f"{curr} {curr_net:,.0f}",
                "closing_str": f"{curr} {closing_bal:,.2f}" if curr == "CNY" else f"{curr} {closing_bal:,.0f}",
            })

        # 2. 实体资产投入与经营盈亏
        month_asset_add = sum(abs(r["cny_equiv"]) for r in curr_period_recs if r["category"] in ASSET_ADD)
        month_asset_sub = sum(abs(r["cny_equiv"]) for r in curr_period_recs if r["category"] in ASSET_SUB)
        net_asset_change = month_asset_add - month_asset_sub

        profit_in = sum(r["cny_equiv"] for r in curr_period_recs if r["category"] in PL_INCOME and r["cny_equiv"] > 0)
        profit_out = abs(sum(r["cny_equiv"] for r in curr_period_recs if r["category"] in PL_EXPENSE and r["cny_equiv"] < 0))
        net_profit = profit_in - profit_out

        # 3. 实时存货家底与非现金资产
        summary_data = BalanceService.get_financial_summary()
        wip_cny = summary_data["wip"]["total_cny"]

        manual_assets = [
            i for i in CompanyBalanceItem.objects.filter(category=BalanceCategory.ASSET)
            if not is_cash_item(i) and not (i.name and i.name.startswith(AssetPrefix.WIP_OFFSET))
        ]

        stock_items = [ma for ma in manual_assets if getattr(ma, 'product_id', None) is not None]
        other_manual_items = [ma for ma in manual_assets if getattr(ma, 'product_id', None) is None]

        stock_cny = sum(to_cny(ma.amount, ma.currency, rates_map) for ma in stock_items)
        other_manual_cny = sum(to_cny(ma.amount, ma.currency, rates_map) for ma in other_manual_items)

        fixed_assets = list(FixedAsset.objects.all())
        fixed_cny = sum(to_cny(f.unit_price * f.remaining_qty, getattr(f, 'currency', 'CNY'), rates_map) for f in fixed_assets)

        consumable_items = list(ConsumableItem.objects.all())
        cons_cny = sum(to_cny(c.unit_price * c.remaining_qty, getattr(c, 'currency', 'CNY'), rates_map) for c in consumable_items)

        inventory_total_cny = stock_cny + wip_cny + fixed_cny + cons_cny + other_manual_cny

        liab_cny = sum(to_cny(i.amount, i.currency, rates_map) for i in CompanyBalanceItem.objects.filter(category=BalanceCategory.LIABILITY))
        equity_cny = sum(to_cny(i.amount, i.currency, rates_map) for i in CompanyBalanceItem.objects.filter(category=BalanceCategory.EQUITY))

        def fmt_cny(val: float) -> str:
            if val is None: val = 0.0
            val = float(val)
            return f"¥ {val:,.2f}"

        # 4. 非现金资产 Accordion 5大分类
        def build_non_cash_cat(cat_name, closing_val, item_rows):
            return {
                "item_name": cat_name,
                "opening_balance": closing_val,
                "change": 0.0,
                "closing_balance": closing_val,
                "opening_str": fmt_cny(closing_val),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(closing_val),
                "details": item_rows
            }

        stock_details = [
            {
                "item_name": i.name,
                "opening_balance": to_cny(i.amount, i.currency, rates_map),
                "change": 0.0,
                "closing_balance": to_cny(i.amount, i.currency, rates_map),
                "opening_str": fmt_cny(to_cny(i.amount, i.currency, rates_map)),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(to_cny(i.amount, i.currency, rates_map))
            } for i in stock_items
        ]

        wip_details = [
            {
                "item_name": name,
                "opening_balance": val,
                "change": 0.0,
                "closing_balance": val,
                "opening_str": fmt_cny(val),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(val)
            } for name, val in summary_data["wip"]["list"]
        ]

        fixed_details = [
            {
                "item_name": f.name,
                "opening_balance": to_cny(f.unit_price * f.remaining_qty, getattr(f, 'currency', 'CNY'), rates_map),
                "change": 0.0,
                "closing_balance": to_cny(f.unit_price * f.remaining_qty, getattr(f, 'currency', 'CNY'), rates_map),
                "opening_str": fmt_cny(to_cny(f.unit_price * f.remaining_qty, getattr(f, 'currency', 'CNY'), rates_map)),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(to_cny(f.unit_price * f.remaining_qty, getattr(f, 'currency', 'CNY'), rates_map))
            } for f in fixed_assets
        ]

        cons_details = [
            {
                "item_name": c.name,
                "opening_balance": to_cny(c.unit_price * c.remaining_qty, getattr(c, 'currency', 'CNY'), rates_map),
                "change": 0.0,
                "closing_balance": to_cny(c.unit_price * c.remaining_qty, getattr(c, 'currency', 'CNY'), rates_map),
                "opening_str": fmt_cny(to_cny(c.unit_price * c.remaining_qty, getattr(c, 'currency', 'CNY'), rates_map)),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(to_cny(c.unit_price * c.remaining_qty, getattr(c, 'currency', 'CNY'), rates_map))
            } for c in consumable_items
        ]

        other_manual_details = [
            {
                "item_name": i.name,
                "opening_balance": to_cny(i.amount, i.currency, rates_map),
                "change": 0.0,
                "closing_balance": to_cny(i.amount, i.currency, rates_map),
                "opening_str": fmt_cny(to_cny(i.amount, i.currency, rates_map)),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(to_cny(i.amount, i.currency, rates_map))
            } for i in other_manual_items
        ]

        non_cash_asset_summary = [
            build_non_cash_cat("大货商品资产 (Stock Assets)", stock_cny, stock_details),
            build_non_cash_cat("在制在研资产 (WIP Assets)", wip_cny, wip_details),
            build_non_cash_cat("固定设备资产 (Fixed Assets)", fixed_cny, fixed_details),
            build_non_cash_cat("消耗品与物料 (Consumable Assets)", cons_cny, cons_details),
            build_non_cash_cat("其他手动资产 (Other Manual Assets)", other_manual_cny, other_manual_details),
        ]

        # 5. 采购与负债/资本变动
        asset_purchase_rows = []
        liab_equity_rows = []

        cat_groups = {}
        for r in curr_period_recs:
            c = r["category"]
            if c not in cat_groups: cat_groups[c] = []
            cat_groups[c].append(r)

        for c_name, rec_list in cat_groups.items():
            tot_cny = sum(r["cny_equiv"] for r in rec_list)
            cny_val = sum(r["amount"] for r in rec_list if r["currency"] == "CNY")
            jpy_val = sum(r["amount"] for r in rec_list if r["currency"] == "JPY")
            jpy_str = f"{jpy_val:,.0f} JPY" if abs(jpy_val) > 0.1 else "-"

            row = {
                "category": c_name,
                "cny_amount": cny_val,
                "jpy_amount": jpy_val,
                "total_cny_equiv": tot_cny,
                "cny_str": fmt_cny(cny_val),
                "jpy_str": jpy_str,
                "equiv_str": fmt_cny(abs(tot_cny))
            }
            if c_name in ASSET_ADD + ASSET_SUB:
                asset_purchase_rows.append(row)
            elif c_name in LIAB_ADD + LIAB_SUB + EQUITY_ADD + EQUITY_SUB:
                liab_equity_rows.append(row)

        # 6. 收支流向构成排行
        flow_summary = []
        for c_name, rec_list in cat_groups.items():
            tot_cny = sum(r["cny_equiv"] for r in rec_list)
            if abs(tot_cny) < 0.01: continue
            cny_val = sum(r["amount"] for r in rec_list if r["currency"] == "CNY")
            jpy_val = sum(r["amount"] for r in rec_list if r["currency"] == "JPY")
            flow_summary.append({
                "category": c_name,
                "direction": "流入" if tot_cny > 0 else "流出",
                "cny_amount": cny_val,
                "jpy_amount": jpy_val,
                "total_cny_equiv": tot_cny,
                "cny_str": fmt_cny(cny_val),
                "jpy_str": f"{jpy_val:,.0f} JPY" if abs(jpy_val) > 0.1 else "-",
                "equiv_str": fmt_cny(abs(tot_cny))
            })
        flow_summary = sorted(flow_summary, key=lambda x: abs(x["total_cny_equiv"]), reverse=True)

        chart_bar_data = []
        max_flow = max([abs(f["total_cny_equiv"]) for f in flow_summary] or [1.0])
        for f in flow_summary[:8]:
            pct = min(100, max(5, int((abs(f["total_cny_equiv"]) / max_flow) * 100)))
            chart_bar_data.append({
                "name": f"{f['category']} ({f['direction']})",
                "amount": abs(f["total_cny_equiv"]),
                "amount_str": f["equiv_str"],
                "width_pct": f"{pct}%"
            })

        # 7. 12个月走势 (年报模式)
        trend_chart_data = []
        if report_type == "year":
            year_recs = [r for r in filtered_recs if r["year"] == period_key and r["category"] in PL_INCOME + PL_EXPENSE]
            monthly_profits = {}
            for m_num in range(1, 13):
                m_str = f"{period_key}-{m_num:02d}"
                monthly_profits[m_str] = 0.0

            for r in year_recs:
                if r["month"] in monthly_profits:
                    monthly_profits[r["month"]] += r["cny_equiv"]

            max_profit = max([abs(p) for p in monthly_profits.values()] or [1.0])
            for m_str, p_val in monthly_profits.items():
                m_label = f"{int(m_str.split('-')[1])}月"
                height_pct = min(100, max(10, int((abs(p_val) / max_profit) * 100)))
                trend_chart_data.append({
                    "month": m_label,
                    "net_profit": p_val,
                    "profit_str": fmt_cny(p_val),
                    "height_str": f"{height_pct}px",
                    "is_positive": p_val >= 0
                })

        # 8. 期初与期末家底表
        opening_inventory = inventory_total_cny - net_asset_change
        closing_inventory = inventory_total_cny

        opening_total_assets = total_opening_cash + opening_inventory
        closing_total_assets = total_closing_cash + closing_inventory
        change_total_assets = total_net_cash + net_asset_change

        opening_net_assets = opening_total_assets - liab_cny
        closing_net_assets = closing_total_assets - liab_cny
        change_net_assets = change_total_assets

        balance_change_summary = [
            {
                "item_name": "💵 现金流动资金",
                "opening_balance": total_opening_cash,
                "change": total_net_cash,
                "closing_balance": total_closing_cash,
                "opening_str": fmt_cny(total_opening_cash),
                "change_str": fmt_cny(total_net_cash),
                "closing_str": fmt_cny(total_closing_cash),
            },
            {
                "item_name": "📦 实体及存货资产",
                "opening_balance": opening_inventory,
                "change": net_asset_change,
                "closing_balance": closing_inventory,
                "opening_str": fmt_cny(opening_inventory),
                "change_str": fmt_cny(net_asset_change),
                "closing_str": fmt_cny(closing_inventory),
            },
            {
                "item_name": "🏛️ 总资产 (Total Assets)",
                "opening_balance": opening_total_assets,
                "change": change_total_assets,
                "closing_balance": closing_total_assets,
                "opening_str": fmt_cny(opening_total_assets),
                "change_str": fmt_cny(change_total_assets),
                "closing_str": fmt_cny(closing_total_assets),
            },
            {
                "item_name": "💳 公司总负债 (Liabilities)",
                "opening_balance": liab_cny,
                "change": 0.0,
                "closing_balance": liab_cny,
                "opening_str": fmt_cny(liab_cny),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(liab_cny),
            },
            {
                "item_name": "🥧 股东权益/资本 (Capital / Equity)",
                "opening_balance": equity_cny,
                "change": 0.0,
                "closing_balance": equity_cny,
                "opening_str": fmt_cny(equity_cny),
                "change_str": fmt_cny(0.0),
                "closing_str": fmt_cny(equity_cny),
            },
            {
                "item_name": "✨ 净资产 (Net Assets)",
                "opening_balance": opening_net_assets,
                "change": change_net_assets,
                "closing_balance": closing_net_assets,
                "opening_str": fmt_cny(opening_net_assets),
                "change_str": fmt_cny(change_net_assets),
                "closing_str": fmt_cny(closing_net_assets),
            }
        ]

        return Response({
            "has_data": True,
            "active_report_type": report_type,
            "selected_year": year,
            "selected_month": month,
            "available_years": years,
            "available_months": months,
            "balance_change_summary": balance_change_summary,
            "past_cash_total_str": fmt_cny(total_opening_cash),
            "net_cash_total_str": fmt_cny(total_net_cash),
            "closing_cash_total_str": fmt_cny(total_closing_cash),
            "month_asset_add_str": fmt_cny(month_asset_add),
            "month_asset_sub_str": fmt_cny(month_asset_sub),
            "net_asset_change_str": fmt_cny(net_asset_change),
            "profit_in_str": fmt_cny(profit_in),
            "profit_out_str": fmt_cny(profit_out),
            "net_profit_str": fmt_cny(net_profit),
            "stock_cny_str": fmt_cny(stock_cny),
            "wip_cny_str": fmt_cny(wip_cny),
            "inventory_total_cny_str": fmt_cny(inventory_total_cny),
            "acc_summary": acc_summary,
            "non_cash_asset_summary": non_cash_asset_summary,
            "asset_purchase_rows": asset_purchase_rows,
            "liab_equity_rows": liab_equity_rows,
            "flow_summary": flow_summary,
            "chart_bar_data": chart_bar_data,
            "trend_chart_data": trend_chart_data,
        })


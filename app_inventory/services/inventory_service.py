# app_inventory/services/inventory_service.py
from django.db import transaction
from django.db.models import Sum, Q, F
from app_core.models import Product, ProductColor, Warehouse, CostItem
from app_inventory.models import InventoryLog
from app_finance.models import CompanyBalanceItem, FinanceRecord
from app_core.constants import (
    PRODUCT_COST_CATEGORIES, AssetPrefix, BalanceCategory, Currency,
    StockLogReason, FinanceCategory
)

class InventoryService:
    COST_CATEGORIES = PRODUCT_COST_CATEGORIES

    @classmethod
    @transaction.atomic
    def sync_product_metrics(cls, product_id: int):
        prod = Product.objects.filter(id=product_id).first()
        if not prod:
            return

        stats = cls.get_stock_overview_by_parts(prod.id, prod.name)
        actual_assemblable = sum(s.get("actual", 0) for s in stats.values())
        produced_sets = sum(s.get("produced", 0) for s in stats.values())

        stats_cons = cls.get_stock_overview_by_parts(prod.id, prod.name, consumption_only=True)
        assemblable_after_consumption = sum(s.get("actual", 0) for s in stats_cons.values())

        if prod.is_production_completed:
            prod.marketable_quantity = max(0, assemblable_after_consumption)
        else:
            not_yet_produced = max(0, prod.total_quantity - produced_sets)
            prod.marketable_quantity = max(0, assemblable_after_consumption + not_yet_produced)

        total_cost_res = CostItem.objects.filter(product_id=prod.id).aggregate(total=Sum('actual_cost'))
        total_cost = total_cost_res['total'] or 0.0
        unit_cost = total_cost / prod.marketable_quantity if prod.marketable_quantity > 0 else 0.0

        prod.save()

        # 大貨資産更新
        actual_stock = actual_assemblable
        asset_name = f"{AssetPrefix.STOCK}{prod.name}"
        asset_val = actual_stock * unit_cost

        items = CompanyBalanceItem.objects.filter(
            Q(product_id=prod.id, name__startswith=AssetPrefix.STOCK) | Q(name=asset_name),
            category=BalanceCategory.ASSET
        )

        if asset_val > 0.01:
            if items.exists():
                items_list = list(items)
                main_item = items_list[0]
                main_item.amount = asset_val
                main_item.name = asset_name
                main_item.product_id = prod.id
                main_item.save()

                for orphan in items_list[1:]:
                    orphan.delete()
            else:
                CompanyBalanceItem.objects.create(
                    name=asset_name, amount=asset_val, category=BalanceCategory.ASSET,
                    currency=Currency.CNY, asset_type="資産", product_id=prod.id
                )
        else:
            for item in items:
                if not item.finance_record_id:
                    item.delete()

        # WIP_OFFSET 更新
        if prod.is_production_completed:
            wip_offset_val = -total_cost
        else:
            wip_offset_val = -(produced_sets * unit_cost)

        offset_name = f"{AssetPrefix.WIP_OFFSET}{prod.name}"

        offset_items = CompanyBalanceItem.objects.filter(
            Q(product_id=prod.id, name__startswith=AssetPrefix.WIP_OFFSET) | Q(name=offset_name),
            category=BalanceCategory.ASSET
        )

        if abs(wip_offset_val) > 0.01:
            if offset_items.exists():
                offset_list = list(offset_items)
                main_offset = offset_list[0]
                main_offset.amount = wip_offset_val
                main_offset.name = offset_name
                main_offset.product_id = prod.id
                main_offset.save()

                for orphan in offset_list[1:]:
                    orphan.delete()
            else:
                CompanyBalanceItem.objects.create(
                    name=offset_name, amount=wip_offset_val, category=BalanceCategory.ASSET,
                    currency=Currency.CNY, asset_type="資産", product_id=prod.id
                )
        else:
            for offset_item in offset_items:
                if not offset_item.finance_record_id:
                    offset_item.delete()

    @staticmethod
    def get_all_products():
        return Product.objects.all()

    @staticmethod
    def get_product_colors(product_id: int):
        return ProductColor.objects.filter(product_id=product_id).order_by('id')

    @staticmethod
    def get_recent_logs(product_name=None, limit=100):
        query = InventoryLog.objects.all()
        if product_name:
            query = query.filter(product_name=product_name)
        return query.order_by('-id')[:limit]

    @staticmethod
    def get_all_warehouses():
        return Warehouse.objects.all()

    @staticmethod
    def add_warehouse(name: str, remarks: str):
        if Warehouse.objects.filter(name=name).exists():
            raise ValueError("倉庫名が既に存在します。")
        return Warehouse.objects.create(name=name, remarks=remarks)

    @classmethod
    def delete_warehouse(cls, warehouse_id: int):
        details = cls.get_warehouse_inventory_details()
        w_data = details.get(warehouse_id)
        if w_data:
            for p, v_dict in w_data["stock"].items():
                for v, pt_dict in v_dict.items():
                    for pt, qty in pt_dict.items():
                        if qty > 0:
                            raise ValueError(f"倉庫に在庫が残っているため削除できません ({p}-{v}-{pt}: {qty})")
        Warehouse.objects.filter(id=warehouse_id).delete()

    @classmethod
    def get_warehouse_inventory_details(cls):
        warehouses = Warehouse.objects.all()
        logs = InventoryLog.objects.all()

        wh_dict = {w.id: {"name": w.name, "stock": {}} for w in warehouses}
        wh_dict[None] = {"name": "未分配倉庫", "stock": {}}

        products = Product.objects.prefetch_related('colors__parts').all()
        req_map = {}
        for prod in products:
            req_map[prod.name] = {}
            for c in prod.colors.all():
                parts = c.parts.all()
                req_map[prod.name][c.color_name] = {p.part_name: p.quantity for p in parts} if parts else {"整套": 1}

        for l in logs:
            w_id = l.warehouse_id
            if w_id not in wh_dict:
                continue

            if l.reason not in [
                StockLogReason.INSPECT_COMPLETED, StockLogReason.OTHER_IN,
                StockLogReason.OUT_STOCK, StockLogReason.IN_STOCK,
                StockLogReason.RETURN_IN, StockLogReason.TRANSFER
            ]:
                continue

            delta = l.change_amount
            p_name = l.product_name
            v_name = l.variant

            if p_name not in wh_dict[w_id]["stock"]:
                wh_dict[w_id]["stock"][p_name] = {}
            if v_name not in wh_dict[w_id]["stock"][p_name]:
                wh_dict[w_id]["stock"][p_name][v_name] = {}

            if l.part_name:
                parts_delta = [(l.part_name, delta)]
            else:
                parts_req = req_map.get(p_name, {}).get(v_name, {"整套": 1})
                parts_delta = [(pt, delta * req) for pt, req in parts_req.items()]

            for pt, d in parts_delta:
                wh_dict[w_id]["stock"][p_name][v_name][pt] = wh_dict[w_id]["stock"][p_name][v_name].get(pt, 0) + d

        return wh_dict

    @classmethod
    def get_stock_overview_by_parts(cls, product_id: int, product_name: str, consumption_only: bool = False):
        product = Product.objects.prefetch_related('colors__parts').filter(id=product_id).first()
        if not product:
            return {}

        logs = list(InventoryLog.objects.filter(product_name=product_name))

        stats = {}
        for c in product.colors.all():
            v_name = c.color_name
            parts = c.parts.all()
            parts_req = {p.part_name: p.quantity for p in parts}
            if not parts_req:
                parts_req = {"整套": 1}

            part_actual = {p: 0 for p in parts_req}
            part_inspecting = {p: 0 for p in parts_req}
            part_produced = {p: 0 for p in parts_req}

            v_logs = [l for l in logs if l.variant == v_name]
            for l in v_logs:
                delta = l.change_amount
                l_parts = []
                if l.part_name and l.part_name in parts_req:
                    l_parts = [(l.part_name, delta)]
                elif not l.part_name:
                    l_parts = [(p, delta * req) for p, req in parts_req.items()]

                for p, d in l_parts:
                    if l.reason == StockLogReason.IN_INSPECT:
                        part_inspecting[p] += d
                    elif l.reason == StockLogReason.INSPECT_COMPLETED:
                        part_inspecting[p] -= d
                        part_actual[p] += d
                        part_produced[p] += d
                    elif l.reason == StockLogReason.OUT_STOCK:
                        if consumption_only and not (l.note and "消耗" in l.note):
                            continue
                        part_actual[p] += d
                    elif l.reason in [StockLogReason.OTHER_IN, StockLogReason.IN_STOCK, StockLogReason.RETURN_IN, StockLogReason.TRANSFER]:
                        part_actual[p] += d
                        if l.reason == StockLogReason.IN_STOCK:
                            part_produced[p] += d

            def calc_sets(pool):
                if not parts_req: return 0
                return min(max(0, pool[p]) // req for p, req in parts_req.items()) if pool else 0

            actual_sets = calc_sets(part_actual)
            inspecting_sets = calc_sets(part_inspecting)
            produced_sets = calc_sets(part_produced)

            excess = {}
            parts_detail = []
            for p, req in parts_req.items():
                exc = part_actual[p] - (actual_sets * req)
                if exc > 0:
                    excess[p] = exc

                p_produced = part_produced[p]
                p_inspecting = part_inspecting[p]
                p_actual = part_actual[p]
                p_sets = max(0, p_actual // req) if req > 0 else 0
                parts_detail.append({
                    "part_name": p,
                    "req_qty": req,
                    "produced": p_produced,
                    "inspecting": p_inspecting,
                    "actual_qty": p_actual,
                    "calculable_sets": p_sets
                })

            stats[v_name] = {
                "planned": c.quantity,
                "produced": produced_sets,
                "inspecting": inspecting_sets,
                "actual": actual_sets,
                "excess": excess,
                "parts": parts_detail
            }
        return stats

    @classmethod
    @transaction.atomic
    def add_inventory_movement(cls, product_id: int, product_name: str, variant: str, quantity: int,
                               move_type: str, date_obj, remark: str, warehouse_id=None, to_warehouse_id=None,
                               is_set=True, part_name=None, out_type=None, cons_cat=None, cons_content=None):

        target_prod_obj = Product.objects.prefetch_related('colors__parts').filter(id=product_id).first()

        if move_type in [StockLogReason.OUT_STOCK, StockLogReason.TRANSFER]:
            wh_details = cls.get_warehouse_inventory_details()

            parts_to_check = {}
            if is_set:
                target_c = next((c for c in target_prod_obj.colors.all() if c.color_name == variant), None) if target_prod_obj else None
                parts = target_c.parts.all() if target_c else []
                if target_c and parts:
                    for p in parts:
                        parts_to_check[p.part_name] = quantity * p.quantity
                else:
                    parts_to_check["整套"] = quantity
            else:
                parts_to_check[part_name] = quantity

            stock_in_wh = wh_details.get(warehouse_id, {}).get("stock", {}).get(product_name, {}).get(variant, {})
            wh_name = wh_details.get(warehouse_id, {}).get("name", "未分配仓库")

            for pt, req_qty in parts_to_check.items():
                avail_qty = stock_in_wh.get(pt, 0)
                if avail_qty < req_qty:
                    raise ValueError(f"在庫不足: 【{product_name}-{variant}】のパーツ【{pt}】 (【{wh_name}】) 残り {avail_qty} 件")

        actual_change_amt = -quantity if move_type == StockLogReason.OUT_STOCK else quantity

        if move_type == StockLogReason.TRANSFER:
            if warehouse_id == to_warehouse_id:
                raise ValueError("移動元と移動先倉庫を同じにすることはできません。")

            wh_details = cls.get_warehouse_inventory_details()
            wh_from_name = wh_details.get(warehouse_id, {}).get("name", "未分配仓库")
            wh_to_obj = Warehouse.objects.filter(id=to_warehouse_id).first()
            wh_to_name = wh_to_obj.name if wh_to_obj else "未分配仓库"

            InventoryLog.objects.create(
                product_name=product_name, variant=variant, change_amount=-quantity,
                reason=StockLogReason.TRANSFER, note=f"移出至【{wh_to_name}】 | {remark}", date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            )
            InventoryLog.objects.create(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.TRANSFER, note=f"从【{wh_from_name}】移入 | {remark}", date=date_obj,
                warehouse_id=to_warehouse_id, part_name=None if is_set else part_name
            )
            msg = "在庫移動完了"

        elif move_type == StockLogReason.OUT_STOCK:
            target_cost_id = None
            if out_type == "消耗" and target_prod_obj and is_set:
                new_cost = CostItem.objects.create(
                    product_id=product_id, item_name=cons_content, actual_cost=0, supplier="", category=cons_cat,
                    unit_price=0, quantity=0, unit="", remarks=f"款式:{variant} 数量:{quantity} | {remark}"
                )
                target_cost_id = new_cost.id

            log_note = f"消耗: {cons_content} | {remark}" if out_type == "消耗" else f"出库: {remark}"

            InventoryLog.objects.create(
                product_name=product_name, variant=variant, change_amount=actual_change_amt,
                reason=StockLogReason.OUT_STOCK, note=log_note, is_other_out=True, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name,
                cost_item_id=target_cost_id
            )
            msg = "出庫完了"

        elif move_type == StockLogReason.IN_INSPECT:
            InventoryLog.objects.create(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.IN_INSPECT, note=remark, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            )
            msg = "検品入庫完了"

        elif move_type == StockLogReason.INSPECT_COMPLETED:
            InventoryLog.objects.create(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.INSPECT_COMPLETED, note=remark, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            )
            msg = "検品完了入庫"

        elif move_type == StockLogReason.OTHER_IN:
            InventoryLog.objects.create(
                product_name=product_name, variant=variant, change_amount=quantity,
                reason=StockLogReason.OTHER_IN, note=remark, date=date_obj,
                warehouse_id=warehouse_id, part_name=None if is_set else part_name
            )
            msg = "その他入庫完了"
        else:
            msg = "未知の操作タイプ"

        cls.sync_product_metrics(product_id)
        return msg

    @classmethod
    @transaction.atomic
    def delete_log_cascade(cls, log_id: int):
        log_to_del = InventoryLog.objects.filter(id=log_id).first()
        if not log_to_del:
            raise ValueError("ログが存在しません。")

        if getattr(log_to_del, 'order_id', None):
            raise ValueError("この在庫ログは販売注文によって自動作成されています。販売注文画面から操作してください。")

        msg_list = []
        target_prod = Product.objects.filter(name=log_to_del.product_name).first()
        is_set = (log_to_del.part_name is None)

        is_consumable_out = (log_to_del.reason == StockLogReason.OUT_STOCK and "消耗" in (log_to_del.note or ""))
        if is_consumable_out and target_prod and is_set:
            if getattr(log_to_del, 'cost_item_id', None):
                CostItem.objects.filter(id=log_to_del.cost_item_id).delete()
                msg_list.append("関連消耗コスト記録を削除")

        if log_to_del.reason == StockLogReason.OUT_STOCK and log_to_del.is_sold:
            target_fin = FinanceRecord.objects.filter(
                date=log_to_del.date,
                amount=log_to_del.sale_amount,
                category=FinanceCategory.SALES_INCOME,
                description__icontains=log_to_del.product_name
            ).first()
            if target_fin:
                cash_name = f"{AssetPrefix.CASH}({log_to_del.currency})"
                cash_item = CompanyBalanceItem.objects.filter(name=cash_name).first()
                if cash_item:
                    cash_item.amount -= target_fin.amount
                    cash_item.save()
                target_fin.delete()
                msg_list.append("関連の販売流水をロールバック")

        log_to_del.delete()

        if target_prod:
            cls.sync_product_metrics(target_prod.id)
            msg_list.append("资产再计算完了")

        return " | ".join(msg_list) if msg_list else "ログ削除完了"

    @classmethod
    def get_wip_balance(cls, product_id: int) -> float:
        from app_core.services.cost_service import CostService
        current_offset = CostService.get_wip_offset(product_id)
        total_cost_res = CostItem.objects.filter(product_id=product_id).aggregate(total=Sum('actual_cost'))
        current_total_cost = total_cost_res['total'] or 0.0
        return current_total_cost + current_offset

    @classmethod
    def clear_wip_for_product(cls, product_id: int):
        from app_core.services.cost_service import CostService
        CostService.perform_wip_fix(product_id)

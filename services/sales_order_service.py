# services/sales_order_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from datetime import date
from models import (
    SalesOrder, SalesOrderItem, OrderRefund,
    Product, InventoryLog, CompanyBalanceItem,
    CostItem, FinanceRecord, Warehouse
)
from constants import OrderStatus, FinanceCategory, AssetPrefix

class SalesOrderService:
    def __init__(self, db: Session):
        self.db = db

    def _update_asset_by_name(self, name, delta, category="asset", currency="CNY"):
        item = self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name == name
        ).with_for_update().first()

        if item:
            item.amount += delta
            if item.amount < 0 and name.startswith(AssetPrefix.PENDING_SETTLE):
                item.amount = 0
                
            if abs(item.amount) <= 0.01 and not item.finance_record_id:
                self.db.delete(item)
        else:
            if delta < 0 and name.startswith(AssetPrefix.PENDING_SETTLE):
                return
                
            a_type = "现金" if name.startswith(AssetPrefix.CASH) else "资产"
            self.db.add(CompanyBalanceItem(
                name=name, amount=delta, category=category, currency=currency, asset_type=a_type
            ))

    def _distribute_pending_asset(self, order, amount_delta):
        legacy_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
        legacy_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == legacy_asset_name).first()
        if legacy_item:
            self._update_asset_by_name(legacy_asset_name, amount_delta, category="asset", currency=order.currency)
            return

        total_initial = sum(item.subtotal for item in order.items)
        
        if total_initial > 0:
            product_subtotals = {}
            for item in order.items:
                product_subtotals[item.product_name] = product_subtotals.get(item.product_name, 0.0) + item.subtotal
            
            for p_name, subtotal in product_subtotals.items():
                item_delta = amount_delta * (subtotal / total_initial)
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{p_name}"
                self._update_asset_by_name(pending_asset_name, item_delta, category="asset", currency=order.currency)
        else:
            if order.items:
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.items[0].product_name}"
                self._update_asset_by_name(pending_asset_name, amount_delta, category="asset", currency=order.currency)

    # ================= 1. 查询方法 =================

    def get_all_orders(self, status=None, product_name=None, limit=100):
        query = self.db.query(SalesOrder).options(
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.warehouse),
            joinedload(SalesOrder.refunds)
        )
        if status: query = query.filter(SalesOrder.status == status)
        if product_name:
            query = query.join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name
            ).distinct()

        return query.order_by(SalesOrder.id.desc()).limit(limit).all()

    def get_order_by_id(self, order_id):
        return self.db.query(SalesOrder).options(
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.warehouse)
        ).filter(SalesOrder.id == order_id).first()

    def get_order_statistics(self, product_name=None):
        base_query = self.db.query(func.count(SalesOrder.id.distinct()))

        if product_name:
            base_query = base_query.join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name
            )

            pending_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name,
                SalesOrder.status == OrderStatus.PENDING
            )
            shipped_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name,
                SalesOrder.status == OrderStatus.SHIPPED
            )
            completed_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name,
                SalesOrder.status == OrderStatus.COMPLETED
            )
            after_sales_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name,
                SalesOrder.status == OrderStatus.AFTER_SALES
            )
        else:
            pending_query = self.db.query(func.count(SalesOrder.id)).filter(
                SalesOrder.status == OrderStatus.PENDING
            )
            shipped_query = self.db.query(func.count(SalesOrder.id)).filter(
                SalesOrder.status == OrderStatus.SHIPPED
            )
            completed_query = self.db.query(func.count(SalesOrder.id)).filter(
                SalesOrder.status == OrderStatus.COMPLETED
            )
            after_sales_query = self.db.query(func.count(SalesOrder.id)).filter(
                SalesOrder.status == OrderStatus.AFTER_SALES
            )

        return {
            "total": base_query.scalar() or 0,
            "pending": pending_query.scalar() or 0,
            "shipped": shipped_query.scalar() or 0,
            "completed": completed_query.scalar() or 0,
            "after_sales": after_sales_query.scalar() or 0
        }

    # ================= 2. 创建订单 =================

    def create_order(self, items_data, platform, currency, notes="", order_date=None, order_no=None, target_account_name=None):
        if not items_data: return None, "订单明细不能为空"
        if not order_no or not order_no.strip(): return None, "订单号不能为空"
        order_no = order_no.strip()
        order_date = order_date or date.today()

        existing = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
        if existing: return None, f"订单号 {order_no} 已存在，请使用其他订单号"

        total_amount = sum(item["quantity"] * item["unit_price"] for item in items_data)

        order = SalesOrder(
            order_no=order_no, status=OrderStatus.PENDING, total_amount=total_amount,
            currency=currency, platform=platform, created_date=order_date, notes=notes,
            target_account_name=target_account_name 
        )
        self.db.add(order)
        self.db.flush()  

        for item in items_data:
            order_item = SalesOrderItem(
                order_id=order.id, product_name=item["product_name"], variant=item["variant"],
                quantity=item["quantity"], unit_price=item["unit_price"], subtotal=item["quantity"] * item["unit_price"],
                warehouse_id=item.get("warehouse_id") # ✨ 绑定指定的出货仓库
            )
            self.db.add(order_item)

        self.db.commit()
        return order, None

    # ================= 3. 订单状态流转 =================

    def ship_order(self, order_id, ship_date=None):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")
        if order.status != OrderStatus.PENDING: raise ValueError(f"当前订单状态为 {order.status}，无法发货")

        ship_date = ship_date or date.today()
        product_ids_to_sync = set()
        
        valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]

        for item in order.items:
            # ✨ 根据该条目的指定仓库，进行精准库存校验
            stock_query = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                InventoryLog.product_name == item.product_name,
                InventoryLog.variant == item.variant,
                InventoryLog.reason.in_(valid_reasons)
            )
            
            if item.warehouse_id is not None:
                stock_query = stock_query.filter(InventoryLog.warehouse_id == item.warehouse_id)
            else:
                stock_query = stock_query.filter(InventoryLog.warehouse_id == None)

            current_stock = stock_query.scalar() or 0

            if current_stock < item.quantity:
                wh_name_display = item.warehouse.name if item.warehouse_id else '未分配仓库'
                raise ValueError(f"库存不足：{item.product_name}-{item.variant} 在【{wh_name_display}】(需要:{item.quantity}, 可用:{current_stock})")

            # ✨ 强绑定订单 ID 和 出货仓库 ID
            self.db.add(InventoryLog(
                product_name=item.product_name, variant=item.variant, change_amount=-item.quantity,
                reason="出库", date=ship_date, note=f"销售订单发货: {order.order_no}",
                is_sold=True, sale_amount=item.subtotal, currency=order.currency, platform=order.platform,
                order_id=order.id, warehouse_id=item.warehouse_id
            ))
            
            product = self.db.query(Product).filter(Product.name == item.product_name).first()
            if product: product_ids_to_sync.add(product.id)

        self._distribute_pending_asset(order, order.total_amount)
        order.status = OrderStatus.SHIPPED
        order.shipped_date = ship_date

        self.db.flush()
        
        from services.inventory_service import InventoryService
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return f"订单 {order.order_no} 已发货，已生成待结算款"

    def complete_order(self, order_id, complete_date=None):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")
        if order.status != OrderStatus.SHIPPED: raise ValueError(f"当前订单状态为 {order.status}，只有已发货订单可以完成")

        complete_date = complete_date or date.today()
        actual_income = order.total_amount

        self._distribute_pending_asset(order, -actual_income)
        
        asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
        self._update_asset_by_name(asset_name, actual_income, category="asset", currency=order.currency)
        
        target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()

        self.db.add(FinanceRecord(
            date=complete_date, amount=actual_income, currency=order.currency,
            category=FinanceCategory.SALES_INCOME, 
            description=f"订单收款: {order.order_no} (平台:{order.platform}) [账户: {asset_name}]",
            order_id=order.id, account_id=target_acc.id if target_acc else None
        ))

        order.status = OrderStatus.COMPLETED
        order.completed_date = complete_date

        self.db.commit()
        return f"订单 {order.order_no} 已完成，收入 {actual_income:.2f} {order.currency}"

    # ================= 4. 售后处理 =================

    def add_refund(self, order_id, refund_amount, refund_reason, is_returned=False,
                   returned_quantity=0, returned_items=None, refund_date=None):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")
        if order.status == OrderStatus.PENDING: raise ValueError("待发货订单不能申请售后，请先标记发货")

        refund_date = refund_date or date.today()
        is_completed = (order.status == OrderStatus.COMPLETED)

        refund = OrderRefund(
            order_id=order_id, refund_amount=refund_amount, refund_reason=refund_reason,
            refund_date=refund_date, is_returned=is_returned, returned_quantity=returned_quantity
        )
        self.db.add(refund)
        self.db.flush()

        product_ids_to_sync = set()

        if is_returned and returned_items and order.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
            for item in returned_items:
                # ✨ 退货入库时，将其原路返回到原来的出货仓库
                self.db.add(InventoryLog(
                    product_name=item["product_name"], variant=item["variant"], change_amount=item["quantity"],
                    reason="退货入库", date=refund_date, note=f"订单退货: {order.order_no} - {refund_reason}",
                    is_sold=True, sale_amount=0, currency=order.currency, platform=order.platform,
                    order_id=order.id, warehouse_id=item.get("warehouse_id")
                ))
                product = self.db.query(Product).filter(Product.name == item["product_name"]).first()
                if product: product_ids_to_sync.add(product.id)

        first_item = self.db.query(SalesOrderItem).filter(SalesOrderItem.order_id == order_id).first()
        if first_item:
            product = self.db.query(Product).filter(Product.name == first_item.product_name).first()
            if product:
                cost_item = CostItem(
                    product_id=product.id, item_name=f"[{order.order_no}+售后]", actual_cost=refund_amount,
                    supplier=order.platform, category="售后成本", unit_price=refund_amount, quantity=1,
                    remarks=refund_reason, order_no=order.order_no
                )
                self.db.add(cost_item)
                self.db.flush()
                refund.cost_item_id = cost_item.id
                product_ids_to_sync.add(product.id)

        if is_completed:
            asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -refund_amount, category="asset", currency=order.currency)
            target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()
            
            self.db.add(FinanceRecord(
                date=refund_date, amount=-refund_amount, currency=order.currency,
                category=FinanceCategory.SALES_INCOME, 
                description=f"订单退款: {order.order_no} - {refund_reason} [账户: {asset_name}]",
                order_id=order.id, account_id=target_acc.id if target_acc else None
            ))
        else:
            order.total_amount -= refund_amount
            if order.total_amount < 0: order.total_amount = 0
            self._distribute_pending_asset(order, -refund_amount)

        order.status = OrderStatus.AFTER_SALES

        self.db.flush()
        from services.inventory_service import InventoryService
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return "售后记录已添加"

    def update_refund(self, refund_id, refund_amount=None, refund_reason=None):
        refund = self.db.query(OrderRefund).filter(OrderRefund.id == refund_id).first()
        if not refund: raise ValueError("售后记录不存在")
        order = self.db.query(SalesOrder).filter(SalesOrder.id == refund.order_id).first()
        is_completed = (order.status == OrderStatus.COMPLETED)
        old_amount = refund.refund_amount
        product_id_to_sync = None

        if refund_amount is not None and refund_amount != old_amount:
            refund.refund_amount = refund_amount
            amount_delta = refund_amount - old_amount

            if refund.cost_item_id:
                cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
                if cost_item:
                    cost_item.actual_cost = refund_amount
                    cost_item.unit_price = refund_amount
                    product_id_to_sync = cost_item.product_id

            if is_completed:
                asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
                self._update_asset_by_name(asset_name, -amount_delta, category="asset", currency=order.currency)
                target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()
                
                if amount_delta != 0:
                    self.db.add(FinanceRecord(
                        date=date.today(), amount=-amount_delta, currency=order.currency, category=FinanceCategory.SALES_INCOME,
                        description=f"售后金额调整: {order.order_no} (调整 {amount_delta:.2f})",
                        order_id=order.id, account_id=target_acc.id if target_acc else None
                    ))
            else:
                order.total_amount -= amount_delta
                if order.total_amount < 0: order.total_amount = 0
                self._distribute_pending_asset(order, -amount_delta)

        if refund_reason is not None:
            refund.refund_reason = refund_reason
            if refund.cost_item_id:
                cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
                if cost_item: cost_item.remarks = refund_reason

        self.db.flush()
        if product_id_to_sync:
            from services.inventory_service import InventoryService
            InventoryService(self.db).sync_product_metrics(product_id_to_sync)

        self.db.commit()
        return f"售后记录已更新"

    def delete_refund(self, refund_id):
        refund = self.db.query(OrderRefund).filter(OrderRefund.id == refund_id).first()
        if not refund: raise ValueError("售后记录不存在")
        order = self.db.query(SalesOrder).filter(SalesOrder.id == refund.order_id).first()
        is_completed = (order.status == OrderStatus.COMPLETED)
        refund_amount = refund.refund_amount
        product_ids_to_sync = set()

        if refund.cost_item_id:
            cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
            if cost_item:
                product_ids_to_sync.add(cost_item.product_id)
                self.db.delete(cost_item)

        if refund.is_returned:
            logs = self.db.query(InventoryLog).filter(
                or_(InventoryLog.order_id == order.id, InventoryLog.note.like(f"%{order.order_no}%")),
                InventoryLog.reason == "退货入库"
            ).all()

            for log in logs:
                product = self.db.query(Product).filter(Product.name == log.product_name).first()
                if product: product_ids_to_sync.add(product.id)
                self.db.delete(log)

        if is_completed:
            asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, refund_amount, category="asset", currency=order.currency)
            
            finances = self.db.query(FinanceRecord).filter(
                or_(FinanceRecord.order_id == order.id, FinanceRecord.description.like(f"%{order.order_no}%")),
                FinanceRecord.amount == -refund_amount
            ).all()
            for finance in finances: self.db.delete(finance)
        else:
            order.total_amount += refund_amount
            self._distribute_pending_asset(order, refund_amount)

        self.db.delete(refund)
        remaining_refunds = self.db.query(OrderRefund).filter(OrderRefund.order_id == order.id).count()

        if remaining_refunds == 0:
            if order.completed_date: order.status = OrderStatus.COMPLETED
            elif order.shipped_date: order.status = OrderStatus.SHIPPED
            else: order.status = OrderStatus.PENDING

        self.db.flush()
        from services.inventory_service import InventoryService
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return f"售后记录已删除"

    # ================= 5. 删除订单 (回滚) =================

    def delete_order(self, order_id):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")

        product_ids_to_sync = set()

        if order.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
            logs = self.db.query(InventoryLog).filter(
                or_(InventoryLog.order_id == order_id, InventoryLog.note.like(f"%{order.order_no}%"))
            ).all()
            for log in logs:
                product = self.db.query(Product).filter(Product.name == log.product_name).first()
                if product: product_ids_to_sync.add(product.id)
                self.db.delete(log)

        refunds = self.db.query(OrderRefund).filter(OrderRefund.order_id == order_id).all()
        for refund in refunds:
            if refund.cost_item_id:
                cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
                if cost_item:
                    product_ids_to_sync.add(cost_item.product_id)
                    self.db.delete(cost_item)

        if order.status == OrderStatus.COMPLETED:
            asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -order.total_amount, category="asset", currency=order.currency)

            finances = self.db.query(FinanceRecord).filter(
                or_(FinanceRecord.order_id == order_id, FinanceRecord.description.like(f"%{order.order_no}%"))
            ).all()
            for finance in finances: self.db.delete(finance)
                
        elif order.status in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]:
            self._distribute_pending_asset(order, -order.total_amount)
                
        self.db.delete(order)
        self.db.flush()
        
        from services.inventory_service import InventoryService
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return f"订单 {order.order_no} 已删除，所有数据已回滚"

    # ================= 6. 批量导入功能 (适配分仓) =================
    def validate_and_parse_import_data(self, df):
        # ✨ 新增第 8 列校验：出货仓库
        required_cols = ['订单号', '商品名', '商品型号', '数量', '销售平台', '订单总额', '币种', '出货仓库']
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols: return None, f"缺少必要列: {', '.join(missing_cols)}"

        df['订单号'] = df['订单号'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        if df['订单号'].duplicated().any():
            duplicate_orders = df[df['订单号'].duplicated()]['订单号'].unique().tolist()
            return None, f"Excel 表格中存在重复的订单号，请合并！重复项: {', '.join(duplicate_orders)}"

        valid_products = {}
        for p in self.db.query(Product).all():
            valid_products[p.name] = [c.color_name for c in p.colors]
            
        warehouses = self.db.query(Warehouse).all()
        warehouse_map = {w.name: w.id for w in warehouses}

        errors = []
        parsed_orders = []
        consumed_stock_in_excel = {}

        valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]

        for index, row in df.iterrows():
            order_no = row['订单号']
            
            existing = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
            if existing:
                errors.append(f"第 {index+2} 行 - 订单号已存在: {order_no}")
                continue

            platform = str(row['销售平台']).strip()
            currency = str(row['币种']).strip()
            p_name = str(row['商品名']).strip()
            
            try: gross_price = float(row['订单总额'])
            except ValueError:
                errors.append(f"订单号 {order_no}: 总金额无效")
                continue

            var_str = str(row['商品型号']).replace('；', ';')
            qty_str = str(row['数量']).replace('；', ';')
            wh_name_str = str(row.get('出货仓库', '')).replace('；', ';')
            
            variants = [v.strip() for v in var_str.split(';') if v.strip()]
            qtys_str = [q.strip() for q in qty_str.split(';') if q.strip()]
            wh_names = [w.strip() for w in wh_name_str.split(';') if w.strip()]

            if len(variants) != len(qtys_str):
                errors.append(f"订单号 {order_no}: 商品型号数量 ({len(variants)}) 与 数量个数 ({len(qtys_str)}) 不一致！")
                continue
            
            if len(variants) == 0:
                errors.append(f"订单号 {order_no}: 未读取到商品型号")
                continue
                
            # ✨ 智能分发逻辑：如果用户只写了一个仓库，但有多个型号，自动把该仓库应用给所有型号
            if len(wh_names) == 1 and len(variants) > 1:
                wh_names = wh_names * len(variants)
            elif len(wh_names) != len(variants):
                errors.append(f"订单号 {order_no}: 填写的出货仓库数量 ({len(wh_names)}) 与 型号数量 ({len(variants)}) 不一致！如果所有商品都在同一个仓出库，只写一次仓库名即可。")
                continue

            items_data = []
            total_qty = 0
            has_item_error = False
            
            for v_name, q_str, wh_name in zip(variants, qtys_str, wh_names):
                try:
                    qty = int(q_str)
                    if qty <= 0:
                        errors.append(f"订单号 {order_no}: 数量必须大于0 ({q_str})")
                        has_item_error = True; break
                except ValueError:
                    errors.append(f"订单号 {order_no}: 数量格式无效 ({q_str})")
                    has_item_error = True; break
                    
                wh_id = warehouse_map.get(wh_name)
                if wh_name != "未分配" and wh_id is None:
                    errors.append(f"订单号 {order_no}: 找不到名为 '{wh_name}' 的仓库！(如果不想分配请填写'未分配')")
                    has_item_error = True; break
                    
                if p_name not in valid_products:
                    errors.append(f"订单号 {order_no}: 数据库中不存在商品 '{p_name}'")
                    has_item_error = True; break
                elif v_name not in valid_products[p_name]:
                    errors.append(f"订单号 {order_no}: 商品 '{p_name}' 不存在型号 '{v_name}'")
                    has_item_error = True; break
                else:
                    stock_key = f"{p_name}_{v_name}_{wh_id}"
                    current_consumed = consumed_stock_in_excel.get(stock_key, 0)
                    
                    # ✨ 针对特定仓库校验库存
                    stock_query = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                        InventoryLog.product_name == p_name,
                        InventoryLog.variant == v_name,
                        InventoryLog.reason.in_(valid_reasons)
                    )
                    if wh_id is not None:
                        stock_query = stock_query.filter(InventoryLog.warehouse_id == wh_id)
                    else:
                        stock_query = stock_query.filter(InventoryLog.warehouse_id == None)
                        
                    current_stock = stock_query.scalar() or 0
                    
                    if current_stock < current_consumed + qty:
                        errors.append(f"订单号 {order_no}: '{p_name}-{v_name}' 在【{wh_name}】库存不足 (当前可用:{current_stock}, 表格内已占用:{current_consumed + qty})")
                        has_item_error = True; break
                    
                    consumed_stock_in_excel[stock_key] = current_consumed + qty
                    items_data.append({"product_name": p_name, "variant": v_name, "quantity": qty, "warehouse_id": wh_id})
                    total_qty += qty
                    
            if has_item_error: continue

            platform_lower = platform.lower()
            fee = 0.0
            shipping_and_other = 0.0
            
            if "booth" in platform_lower:
                preset_item_total = 0.0
                for item in items_data:
                    target_p = self.db.query(Product).filter(Product.name == item["product_name"]).first()
                    if target_p:
                        target_c = next((c for c in target_p.colors if c.color_name == item["variant"]), None)
                        if target_c:
                            target_price = next((pr.price for pr in target_c.prices if pr.platform and pr.platform.lower() == "booth"), 0.0)
                            preset_item_total += target_price * item["quantity"]
                
                if preset_item_total > 0:
                    shipping_and_other = max(0.0, gross_price - preset_item_total)
                else:
                    shipping_and_other = 0.0
                
                base_fixed_fee = 45 if currency == "JPY" else 2.16
                fee = gross_price * 0.056 + base_fixed_fee
                
            elif "微店" in platform_lower:
                fee = gross_price * 0.006
                
            net_price = gross_price - fee - shipping_and_other
            
            if net_price <= 0:
                errors.append(f"订单号 {order_no}: 扣除手续费后的净金额({net_price:.2f}) 小于等于 0")
                continue
                
            final_unit_price = net_price / total_qty
            for item in items_data:
                item["unit_price"] = final_unit_price
                item["subtotal"] = item["quantity"] * final_unit_price
                
            if "微店" in platform_lower: target_acc = "流动资金-微店账户"
            elif "booth" in platform_lower: target_acc = "流动资金-booth账户"
            elif currency == "JPY": target_acc = "流动资金-日元临时账户"
            else: target_acc = "流动资金-支付宝账户"

            parsed_orders.append({
                "order_no": order_no, "platform": platform, "currency": currency,
                "gross_price": gross_price, "fee": fee, "net_price": net_price,
                "total_qty": total_qty, "items": items_data,
                "target_account": target_acc 
            })

        return parsed_orders, errors

    def batch_create_orders(self, parsed_orders):
        created_count = 0
        for order_data in parsed_orders:
            order, err = self.create_order(
                items_data=order_data["items"], platform=order_data["platform"],
                currency=order_data["currency"], notes="Excel批量导入", order_no=order_data["order_no"],
                target_account_name=order_data["target_account"] 
            )
            if not err: created_count += 1
        return created_count

    def commit(self):
        self.db.commit()
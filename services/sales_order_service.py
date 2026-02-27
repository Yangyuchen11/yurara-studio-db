from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import date
from models import (
    SalesOrder, SalesOrderItem, OrderRefund,
    Product, InventoryLog, CompanyBalanceItem,
    CostItem, FinanceRecord
)
from constants import OrderStatus, FinanceCategory, AssetPrefix

class SalesOrderService:
    def __init__(self, db: Session):
        self.db = db

    # ================= 辅助方法 =================

    def _update_asset_by_name(self, name, delta, category="asset", currency="CNY"):
        """按名称更新资产项"""
        item = self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name == name
        ).with_for_update().first()

        if item:
            item.amount += delta
            # 如果金额极小且无关联流水，删除该项 (保持数据库整洁)
            if abs(item.amount) <= 0.01 and not item.finance_record_id:
                self.db.delete(item)
        else:
            self.db.add(CompanyBalanceItem(
                name=name, amount=delta, category=category, currency=currency
            ))

    def _get_unit_cost(self, product_id):
        """获取产品单位成本"""
        total_cost = self.db.query(func.sum(CostItem.actual_cost))\
            .filter(CostItem.product_id == product_id).scalar() or 0.0
        product = self.db.query(Product).filter(Product.id == product_id).first()

        denom = product.marketable_quantity if (product and product.marketable_quantity) else 0
        if denom > 0:
            return total_cost / denom
        return 0.0

    def _distribute_pending_asset(self, order, amount_delta):
        """
        按订单内商品的金额比例，将待结算金额分配到各个商品的待结算账户中
        amount_delta: 正数代表增加待结算，负数代表减少待结算
        """
        # 1. 兼容旧订单：如果存在旧的按订单号生成的待结算资产，优先处理旧资产，防止死账
        legacy_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
        legacy_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == legacy_asset_name).first()
        if legacy_item:
            self._update_asset_by_name(legacy_asset_name, amount_delta, category="asset", currency=order.currency)
            return

        # 2. 如果没有旧资产，按商品比例将金额分配到对应的【待结算-商品名】中
        total_initial = sum(item.subtotal for item in order.items)
        
        if total_initial > 0:
            # 累加各个商品的子计，因为同一个订单内可能有多个同商品的明细行
            product_subtotals = {}
            for item in order.items:
                product_subtotals[item.product_name] = product_subtotals.get(item.product_name, 0.0) + item.subtotal
            
            # 按比例增减金额
            for p_name, subtotal in product_subtotals.items():
                item_delta = amount_delta * (subtotal / total_initial)
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{p_name}"
                self._update_asset_by_name(pending_asset_name, item_delta, category="asset", currency=order.currency)
        else:
            # 兜底逻辑
            if order.items:
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.items[0].product_name}"
                self._update_asset_by_name(pending_asset_name, amount_delta, category="asset", currency=order.currency)

    # ================= 1. 查询方法 =================

    def get_all_orders(self, status=None, product_name=None, limit=100):
        """获取订单列表，支持按状态和商品筛选（已加入 joinedload 优化性能）"""
        query = self.db.query(SalesOrder).options(
            joinedload(SalesOrder.items),
            joinedload(SalesOrder.refunds)
        )

        if status:
            query = query.filter(SalesOrder.status == status)

        if product_name:
            query = query.join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name
            ).distinct()

        return query.order_by(SalesOrder.id.desc()).limit(limit).all()

    def get_order_by_id(self, order_id):
        """根据ID获取订单详情（包括明细和售后记录）"""
        return self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()

    def get_order_statistics(self, product_name=None):
        """获取订单统计信息，支持按商品筛选"""
        # 基础查询
        base_query = self.db.query(func.count(SalesOrder.id.distinct()))

        # 如果指定了商品名，添加JOIN筛选
        if product_name:
            base_query = base_query.join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name
            )

            # 各状态查询也需要JOIN
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
            # 无商品筛选时使用简单查询
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

        total_orders = base_query.scalar()
        pending = pending_query.scalar()
        shipped = shipped_query.scalar()
        completed = completed_query.scalar()
        after_sales = after_sales_query.scalar()

        return {
            "total": total_orders or 0,
            "pending": pending or 0,
            "shipped": shipped or 0,
            "completed": completed or 0,
            "after_sales": after_sales or 0
        }

    # ================= 2. 创建订单 =================

    def create_order(self, items_data, platform, currency, notes="", order_date=None, order_no=None):
        """
        创建订单（不扣减库存，发货时才扣减）
        """
        if not items_data:
            return None, "订单明细不能为空"

        # 验证订单号
        if not order_no or not order_no.strip():
            return None, "订单号不能为空"

        order_no = order_no.strip()
        order_date = order_date or date.today()

        # 检查订单号是否已存在
        existing = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
        if existing:
            return None, f"订单号 {order_no} 已存在，请使用其他订单号"

        # 计算订单总金额
        total_amount = sum(item["quantity"] * item["unit_price"] for item in items_data)

        # 创建订单主记录
        order = SalesOrder(
            order_no=order_no,
            status=OrderStatus.PENDING,
            total_amount=total_amount,
            currency=currency,
            platform=platform,
            created_date=order_date,
            notes=notes
        )
        self.db.add(order)
        self.db.flush()  # 获取 order.id

        # 创建订单明细（不扣减库存）
        for item in items_data:
            product_name = item["product_name"]
            variant = item["variant"]
            quantity = item["quantity"]
            unit_price = item["unit_price"]
            subtotal = quantity * unit_price

            # 创建订单明细
            order_item = SalesOrderItem(
                order_id=order.id,
                product_name=product_name,
                variant=variant,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=subtotal
            )
            self.db.add(order_item)

        self.db.commit()
        return order, None

    # ================= 3. 订单状态流转 =================

    def ship_order(self, order_id, ship_date=None):
        """
        订单发货 - 扣减库存，并增加待结算资产
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        if order.status != OrderStatus.PENDING:
            raise ValueError(f"当前订单状态为 {order.status}，无法发货")

        ship_date = ship_date or date.today()

        # 1. 校验库存是否充足并扣减库存
        for item in order.items:
            product_name = item.product_name
            variant = item.variant
            quantity = item.quantity

            # 计算当前库存
            current_stock = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                InventoryLog.product_name == product_name,
                InventoryLog.variant == variant,
                InventoryLog.reason.in_(["入库", "出库", "退货入库", "发货撤销"])
            ).scalar() or 0

            if current_stock < quantity:
                raise ValueError(f"库存不足：{product_name}-{variant} (需要:{quantity}, 可用:{current_stock})")

            # 创建出库日志
            log = InventoryLog(
                product_name=product_name,
                variant=variant,
                change_amount=-quantity,
                reason="出库",
                date=ship_date,
                note=f"销售订单发货: {order.order_no}",
                is_sold=True,
                sale_amount=item.subtotal,
                currency=order.currency,
                platform=order.platform
            )
            self.db.add(log)

            # 扣减库存对应的资产价值
            product = self.db.query(Product).filter(Product.name == product_name).first()
            if product:
                unit_cost = self._get_unit_cost(product.id)
                asset_delta = -quantity * unit_cost
                asset_name = f"{AssetPrefix.STOCK}{product_name}"
                self._update_asset_by_name(asset_name, asset_delta, category="asset", currency="CNY")

        # 2. 【新增】增加待结算资产
        self._distribute_pending_asset(order, order.total_amount)

        # 3. 更新订单状态
        order.status = OrderStatus.SHIPPED
        order.shipped_date = ship_date

        self.db.commit()
        return f"订单 {order.order_no} 已发货，已生成待结算款"

    def complete_order(self, order_id, complete_date=None):
        """
        订单完成 - 结清待结算资产，并转为流动资金
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        if order.status != OrderStatus.SHIPPED:
            raise ValueError(f"当前订单状态为 {order.status}，只有已发货订单可以完成")

        complete_date = complete_date or date.today()

        # 1. 计算实际入账金额
        # 注意：由于在“售后中但未完成”的订单退款时，已经直接扣减了 order.total_amount，
        # 所以到结单这一步，order.total_amount 就是真正应收的净额了，不需要再减一次退款。
        actual_income = order.total_amount

        # 2. 【新增】扣除对应的待结算资产 (兼容旧订单：只有存在时才扣除)
        self._distribute_pending_asset(order, -actual_income)

        # 3. 增加流动资金
        asset_name = f"{AssetPrefix.CASH}({order.currency})"
        self._update_asset_by_name(asset_name, actual_income, category="asset", currency=order.currency)

        # 4. 创建财务流水
        finance = FinanceRecord(
            date=complete_date,
            amount=actual_income,
            currency=order.currency,
            category=FinanceCategory.SALES_INCOME,
            description=f"订单收款: {order.order_no} (平台:{order.platform})"
        )
        self.db.add(finance)

        # 5. 更新订单状态
        order.status = OrderStatus.COMPLETED
        order.completed_date = complete_date

        self.db.commit()
        return f"订单 {order.order_no} 已完成，收入 {actual_income:.2f} {order.currency}"

    # ================= 4. 售后处理 =================

    def add_refund(self, order_id, refund_amount, refund_reason, is_returned=False,
                   returned_quantity=0, returned_items=None, refund_date=None):
        """
        添加售后记录
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        if order.status == OrderStatus.PENDING:
            raise ValueError("待发货订单不能申请售后，请先标记发货")

        refund_date = refund_date or date.today()
        is_completed = (order.status == OrderStatus.COMPLETED)

        # 1. 创建售后记录
        refund = OrderRefund(
            order_id=order_id,
            refund_amount=refund_amount,
            refund_reason=refund_reason,
            refund_date=refund_date,
            is_returned=is_returned,
            returned_quantity=returned_quantity
        )
        self.db.add(refund)
        self.db.flush()

        # 2. 如果有退货，回滚库存
        if is_returned and returned_items and order.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
            for item in returned_items:
                product_name = item["product_name"]
                variant = item["variant"]
                quantity = item["quantity"]

                log = InventoryLog(
                    product_name=product_name,
                    variant=variant,
                    change_amount=quantity,
                    reason="退货入库",
                    date=refund_date,
                    note=f"订单退货: {order.order_no} - {refund_reason}",
                    is_sold=True,
                    sale_amount=-refund_amount,
                    currency=order.currency,
                    platform=order.platform
                )
                self.db.add(log)

                product = self.db.query(Product).filter(Product.name == product_name).first()
                if product:
                    unit_cost = self._get_unit_cost(product.id)
                    asset_delta = quantity * unit_cost
                    asset_name = f"{AssetPrefix.STOCK}{product_name}"
                    self._update_asset_by_name(asset_name, asset_delta, category="asset", currency="CNY")

        # 3. 创建售后成本项
        first_item = self.db.query(SalesOrderItem).filter(
            SalesOrderItem.order_id == order_id
        ).first()

        if first_item:
            product = self.db.query(Product).filter(
                Product.name == first_item.product_name
            ).first()

            if product:
                cost_item = CostItem(
                    product_id=product.id,
                    item_name=f"[{order.order_no}+售后]",
                    actual_cost=refund_amount,
                    supplier=order.platform,
                    category="售后成本",
                    unit_price=refund_amount,
                    quantity=1,
                    remarks=refund_reason,
                    order_no=order.order_no
                )
                self.db.add(cost_item)
                self.db.flush()
                refund.cost_item_id = cost_item.id

        # 4. 区分完成前/后退款处理
        if is_completed:
            # 订单已完成：从流动资金中扣除退款
            asset_name = f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -refund_amount, category="asset", currency=order.currency)

            finance = FinanceRecord(
                date=refund_date,
                amount=-refund_amount,
                currency=order.currency,
                category=FinanceCategory.SALES_INCOME,
                description=f"订单退款: {order.order_no} - {refund_reason}"
            )
            self.db.add(finance)
        else:
            # 订单未完成：减少订单金额
            order.total_amount -= refund_amount
            if order.total_amount < 0:
                order.total_amount = 0
            
            # 从对应的待结算资产中扣除退款
            self._distribute_pending_asset(order, -refund_amount)

        # 5. 更新订单状态为"售后中"
        order.status = OrderStatus.AFTER_SALES

        self.db.commit()

        msg = f"售后记录已添加: 售后金额 {refund_amount:.2f} {order.currency}"
        if is_returned:
            msg += f", 已退货 {returned_quantity} 件"
        if is_completed:
            msg += " (已从流动资金扣除)"
        else:
            msg += " (已从订单待结算额中扣除)"
        return msg

    def update_refund(self, refund_id, refund_amount=None, refund_reason=None):
        """
        更新售后记录
        """
        refund = self.db.query(OrderRefund).filter(OrderRefund.id == refund_id).first()
        if not refund:
            raise ValueError("售后记录不存在")

        order = self.db.query(SalesOrder).filter(SalesOrder.id == refund.order_id).first()
        if not order:
            raise ValueError("订单不存在")

        is_completed = (order.status == OrderStatus.COMPLETED)
        old_amount = refund.refund_amount

        # 1. 更新售后记录
        if refund_amount is not None and refund_amount != old_amount:
            refund.refund_amount = refund_amount
            amount_delta = refund_amount - old_amount

            # 2. 更新关联的成本项
            if refund.cost_item_id:
                cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
                if cost_item:
                    cost_item.actual_cost = refund_amount
                    cost_item.unit_price = refund_amount

            # 3. 根据订单状态调整资产
            if is_completed:
                # 订单已完成：调整流动资金
                asset_name = f"{AssetPrefix.CASH}({order.currency})"
                self._update_asset_by_name(asset_name, -amount_delta, category="asset", currency=order.currency)

                if amount_delta != 0:
                    finance = FinanceRecord(
                        date=date.today(),
                        amount=-amount_delta,
                        currency=order.currency,
                        category=FinanceCategory.SALES_INCOME,
                        description=f"售后金额调整: {order.order_no} (调整 {amount_delta:.2f})"
                    )
                    self.db.add(finance)
            else:
                # 订单未完成：调整订单总额
                order.total_amount -= amount_delta
                if order.total_amount < 0:
                    order.total_amount = 0
                
                # 调整对应的待结算资产
                self._distribute_pending_asset(order, -amount_delta)

        if refund_reason is not None:
            refund.refund_reason = refund_reason
            if refund.cost_item_id:
                cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
                if cost_item:
                    cost_item.remarks = refund_reason

        self.db.commit()
        return f"售后记录已更新"

    def delete_refund(self, refund_id):
        """
        删除售后记录并回滚相关操作
        """
        refund = self.db.query(OrderRefund).filter(OrderRefund.id == refund_id).first()
        if not refund:
            raise ValueError("售后记录不存在")

        order = self.db.query(SalesOrder).filter(SalesOrder.id == refund.order_id).first()
        if not order:
            raise ValueError("订单不存在")

        is_completed = (order.status == OrderStatus.COMPLETED)
        refund_amount = refund.refund_amount

        # 1. 删除关联的成本项
        if refund.cost_item_id:
            cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
            if cost_item:
                self.db.delete(cost_item)

        # 2. 如果有退货，回滚库存
        if refund.is_returned:
            logs = self.db.query(InventoryLog).filter(
                InventoryLog.note.like(f"%{order.order_no}%"),
                InventoryLog.reason == "退货入库"
            ).all()

            for log in logs:
                product = self.db.query(Product).filter(Product.name == log.product_name).first()
                if product:
                    unit_cost = self._get_unit_cost(product.id)
                    asset_delta = -log.change_amount * unit_cost 
                    asset_name = f"{AssetPrefix.STOCK}{product.name}"
                    self._update_asset_by_name(asset_name, asset_delta, category="asset", currency="CNY")

                self.db.delete(log)

        # 3. 根据订单状态回滚资产
        if is_completed:
            asset_name = f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, refund_amount, category="asset", currency=order.currency)

            finances = self.db.query(FinanceRecord).filter(
                FinanceRecord.description.like(f"%{order.order_no}%"),
                FinanceRecord.amount == -refund_amount
            ).all()
            for finance in finances:
                self.db.delete(finance)
        else:
            # 订单未完成：返还订单金额
            order.total_amount += refund_amount
            
            # 因为撤销了未完成时的退款，待结算资产也应加回来
            self._distribute_pending_asset(order, refund_amount)

        # 4. 删除售后记录
        self.db.delete(refund)

        # 5. 恢复订单状态
        remaining_refunds = self.db.query(OrderRefund).filter(
            OrderRefund.order_id == order.id
        ).count()

        if remaining_refunds == 0:
            if order.completed_date:
                order.status = OrderStatus.COMPLETED
            elif order.shipped_date:
                order.status = OrderStatus.SHIPPED
            else:
                order.status = OrderStatus.PENDING

        self.db.commit()
        return f"售后记录已删除"

    # ================= 5. 删除订单 (回滚) =================

    def delete_order(self, order_id):
        """
        删除订单并完整回滚所有操作
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        # 1. 回滚库存
        if order.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
            logs = self.db.query(InventoryLog).filter(
                InventoryLog.note.like(f"%{order.order_no}%")
            ).all()

            for log in logs:
                product = self.db.query(Product).filter(
                    Product.name == log.product_name
                ).first()

                if product:
                    unit_cost = self._get_unit_cost(product.id)
                    asset_delta = -log.change_amount * unit_cost
                    asset_name = f"{AssetPrefix.STOCK}{product.name}"
                    self._update_asset_by_name(asset_name, asset_delta, category="asset", currency="CNY")

                self.db.delete(log)

        # 2. 删除关联的成本项
        refunds = self.db.query(OrderRefund).filter(OrderRefund.order_id == order_id).all()
        for refund in refunds:
            if refund.cost_item_id:
                cost_item = self.db.query(CostItem).filter(
                    CostItem.id == refund.cost_item_id
                ).first()
                if cost_item:
                    self.db.delete(cost_item)

        # 3. 回滚资金/待结算资产与流水
        if order.status == OrderStatus.COMPLETED:
            asset_name = f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -order.total_amount, category="asset", currency=order.currency)

            finances = self.db.query(FinanceRecord).filter(
                FinanceRecord.description.like(f"%{order.order_no}%")
            ).all()
            for finance in finances:
                self.db.delete(finance)
                
        elif order.status in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]:
            # 已发货但未完成，回滚发货时挂在账上的待结算资产
            self._distribute_pending_asset(order, -order.total_amount)
                
        # 4. 级联删除订单
        self.db.delete(order)

        self.db.commit()
        return f"订单 {order.order_no} 已删除，所有数据已回滚"

    # ================= 6. 批量导入功能 =================
    def validate_and_parse_import_data(self, df):
        """
        校验并解析上传的 Excel 订单数据 (新版：包含库存校验和多订单需求累计)
        """
        required_cols = ['订单号', '商品名', '商品型号', '数量', '销售平台', '订单总额', '币种']
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            return None, f"缺少必要列: {', '.join(missing_cols)}"

        # 确保订单号解析为纯字符串，并去除两端空格
        df['订单号'] = df['订单号'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # 1. 检查 Excel 内部是否有重复订单号
        if df['订单号'].duplicated().any():
            duplicate_orders = df[df['订单号'].duplicated()]['订单号'].unique().tolist()
            return None, f"Excel 表格中存在重复的订单号，请将同一个订单合并为一行！重复项: {', '.join(duplicate_orders)}"

        # 2. 获取数据库中所有有效的商品和款式
        valid_products = {}
        for p in self.db.query(Product).all():
            valid_products[p.name] = [c.color_name for c in p.colors]

        errors = []
        parsed_orders = []
        
        # 👇 新增：用于记录当前表格中每个款式累计已经被前面订单“预定”了多少件，防止超卖
        consumed_stock_in_excel = {}

        # 3. 逐行解析订单
        for index, row in df.iterrows():
            order_no = row['订单号']
            
            # 校验订单号是否已存在于数据库
            existing = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
            if existing:
                errors.append(f"第 {index+2} 行 - 订单号已存在: {order_no}")
                continue

            platform = str(row['销售平台']).strip()
            currency = str(row['币种']).strip()
            p_name = str(row['商品名']).strip()
            
            try:
                gross_price = float(row['订单总额'])
            except ValueError:
                errors.append(f"订单号 {order_no}: 总金额无效")
                continue

            # 解析款式和数量
            var_str = str(row['商品型号']).replace('；', ';')
            qty_str = str(row['数量']).replace('；', ';')
            
            variants = [v.strip() for v in var_str.split(';') if v.strip()]
            qtys_str = [q.strip() for q in qty_str.split(';') if q.strip()]

            # 校验分号分隔的数量是否一致
            if len(variants) != len(qtys_str):
                errors.append(f"订单号 {order_no}: 商品型号数量 ({len(variants)}) 与 数量个数 ({len(qtys_str)}) 不一致！")
                continue
            
            if len(variants) == 0:
                errors.append(f"订单号 {order_no}: 未读取到商品型号")
                continue

            items_data = []
            total_qty = 0
            has_item_error = False
            
            # 遍历该行分隔出来的每一对 (型号, 数量)
            for v_name, q_str in zip(variants, qtys_str):
                try:
                    qty = int(q_str)
                    if qty <= 0:
                        errors.append(f"订单号 {order_no}: 数量必须大于0 ({q_str})")
                        has_item_error = True
                        break
                except ValueError:
                    errors.append(f"订单号 {order_no}: 数量格式无效 ({q_str})")
                    has_item_error = True
                    break
                    
                # 校验商品和款式是否存在于数据库
                if p_name not in valid_products:
                    errors.append(f"订单号 {order_no}: 数据库中不存在商品 '{p_name}'")
                    has_item_error = True
                    break
                elif v_name not in valid_products[p_name]:
                    errors.append(f"订单号 {order_no}: 商品 '{p_name}' 不存在型号 '{v_name}'")
                    has_item_error = True
                    break
                else:
                    # 👇 新增核心逻辑：校验实际库存是否满足需求
                    stock_key = f"{p_name}_{v_name}"
                    current_consumed = consumed_stock_in_excel.get(stock_key, 0)
                    
                    # 实时查询当前数据库中的现货总库存
                    current_stock = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                        InventoryLog.product_name == p_name,
                        InventoryLog.variant == v_name,
                        InventoryLog.reason.in_(["入库", "出库", "退货入库", "发货撤销"])
                    ).scalar() or 0
                    
                    # 校验：数据库现有库存 < (表格前面订单用掉的 + 本次需要的)
                    if current_stock < current_consumed + qty:
                        errors.append(f"订单号 {order_no}: '{p_name}-{v_name}' 库存不足 (当前可用库存:{current_stock}, 表格内累计需要:{current_consumed + qty})")
                        has_item_error = True
                        break
                    
                    # 库存足够，记录累加消耗，留给表格中后面的订单校验使用
                    consumed_stock_in_excel[stock_key] = current_consumed + qty
                    
                    items_data.append({
                        "product_name": p_name,
                        "variant": v_name,
                        "quantity": qty
                    })
                    total_qty += qty
                    
            if has_item_error:
                continue

            # 4. 自动计算手续费
            fee = 0.0
            if platform == "微店":
                fee = gross_price * 0.006
            elif platform == "Booth":
                base_fixed_fee = 22 if currency == "JPY" else 1.0
                fee = gross_price * 0.056 + base_fixed_fee
                
            net_price = gross_price - fee
            
            if net_price <= 0:
                errors.append(f"订单号 {order_no}: 扣除手续费后的净金额({net_price:.2f}) 小于等于 0")
                continue
                
            # 计算分摊到每件商品的净单价
            final_unit_price = net_price / total_qty
            for item in items_data:
                item["unit_price"] = final_unit_price
                item["subtotal"] = item["quantity"] * final_unit_price
                
            # 组装校验后的完整订单数据
            parsed_orders.append({
                "order_no": order_no,
                "platform": platform,
                "currency": currency,
                "gross_price": gross_price,
                "fee": fee,
                "net_price": net_price,
                "total_qty": total_qty,
                "items": items_data
            })

        return parsed_orders, errors

    def batch_create_orders(self, parsed_orders):
        """
        执行批量创建订单
        """
        created_count = 0
        for order_data in parsed_orders:
            # 复用已有的 create_order 逻辑，记账逻辑会自动在内部处理
            order, err = self.create_order(
                items_data=order_data["items"],
                platform=order_data["platform"],
                currency=order_data["currency"],
                notes="Excel批量导入",
                order_no=order_data["order_no"]
            )
            if not err:
                created_count += 1
        return created_count
    

    def commit(self):
        """提交事务"""
        self.db.commit()
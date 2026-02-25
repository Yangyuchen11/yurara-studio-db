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
        pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
        self._update_asset_by_name(pending_asset_name, order.total_amount, category="asset", currency=order.currency)

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
        pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
        pending_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == pending_asset_name).first()
        if pending_item:
            self._update_asset_by_name(pending_asset_name, -actual_income, category="asset", currency=order.currency)

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
            
            # 【新增】因为未完成，这笔退款应从该订单现存的“待结算资产”中扣除 (兼容旧订单)
            pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
            pending_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == pending_asset_name).first()
            if pending_item:
                self._update_asset_by_name(pending_asset_name, -refund_amount, category="asset", currency=order.currency)

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
                
                # 【新增】调整待结算资产
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
                self._update_asset_by_name(pending_asset_name, -amount_delta, category="asset", currency=order.currency)

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
            
            # 【新增】因为撤销了未完成时的退款，待结算资产也应加回来
            pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
            self._update_asset_by_name(pending_asset_name, refund_amount, category="asset", currency=order.currency)

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
            # 【新增】已发货但未完成，回滚发货时挂在账上的待结算资产 (兼容旧订单)
            pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.order_no}"
            pending_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == pending_asset_name).first()
            if pending_item:
                self._update_asset_by_name(pending_asset_name, -order.total_amount, category="asset", currency=order.currency)
                
        # 4. 级联删除订单
        self.db.delete(order)

        self.db.commit()
        return f"订单 {order.order_no} 已删除，所有数据已回滚"

    def commit(self):
        """提交事务"""
        self.db.commit()
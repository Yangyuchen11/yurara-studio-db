from sqlalchemy.orm import Session
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
            # 如果金额极小且无关联流水，删除该项
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

    def get_all_orders(self, status=None, limit=100):
        """获取订单列表"""
        query = self.db.query(SalesOrder)
        if status:
            query = query.filter(SalesOrder.status == status)
        return query.order_by(SalesOrder.id.desc()).limit(limit).all()

    def get_order_by_id(self, order_id):
        """根据ID获取订单详情（包括明细和售后记录）"""
        return self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()

    def get_order_statistics(self):
        """获取订单统计信息"""
        total_orders = self.db.query(func.count(SalesOrder.id)).scalar()
        pending = self.db.query(func.count(SalesOrder.id)).filter(
            SalesOrder.status == OrderStatus.PENDING
        ).scalar()
        shipped = self.db.query(func.count(SalesOrder.id)).filter(
            SalesOrder.status == OrderStatus.SHIPPED
        ).scalar()
        completed = self.db.query(func.count(SalesOrder.id)).filter(
            SalesOrder.status == OrderStatus.COMPLETED
        ).scalar()
        after_sales = self.db.query(func.count(SalesOrder.id)).filter(
            SalesOrder.status == OrderStatus.AFTER_SALES
        ).scalar()

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
        创建订单并扣减库存

        items_data: list of dict, 格式 [
            {"product_name": "商品A", "variant": "红色", "quantity": 2, "unit_price": 100.0},
            ...
        ]
        platform: 销售平台
        currency: 币种
        notes: 订单备注
        order_date: 订单日期（默认今天）
        order_no: 订单号（用户输入，必填）

        返回: (order, error_message)
        """
        if not items_data:
            return None, "订单明细不能为空"

        # 【新增】验证订单号
        if not order_no or not order_no.strip():
            return None, "订单号不能为空"

        order_no = order_no.strip()
        order_date = order_date or date.today()

        # 【新增】检查订单号是否已存在
        existing = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
        if existing:
            return None, f"订单号 {order_no} 已存在，请使用其他订单号"

        # 1. 校验库存是否充足
        for item in items_data:
            product_name = item["product_name"]
            variant = item["variant"]
            quantity = item["quantity"]

            # 计算当前库存
            current_stock = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                InventoryLog.product_name == product_name,
                InventoryLog.variant == variant,
                InventoryLog.reason.in_(["入库", "出库", "退货入库", "发货撤销"])
            ).scalar() or 0

            if current_stock < quantity:
                return None, f"库存不足：{product_name}-{variant} (需要:{quantity}, 可用:{current_stock})"

        # 2. 计算订单总金额
        total_amount = sum(item["quantity"] * item["unit_price"] for item in items_data)

        # 3. 创建订单主记录（使用用户输入的订单号）
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

        # 4. 创建订单明细并扣减库存
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

            # 扣减库存 - 创建出库日志
            log = InventoryLog(
                product_name=product_name,
                variant=variant,
                change_amount=-quantity,
                reason="出库",
                date=order_date,
                note=f"销售订单: {order_no}",
                is_sold=True,
                sale_amount=subtotal,
                currency=currency,
                platform=platform
            )
            self.db.add(log)

            # 扣减库存对应的资产价值
            product = self.db.query(Product).filter(Product.name == product_name).first()
            if product:
                unit_cost = self._get_unit_cost(product.id)
                asset_delta = -quantity * unit_cost
                asset_name = f"{AssetPrefix.STOCK}{product_name}"
                self._update_asset_by_name(asset_name, asset_delta, category="asset", currency="CNY")

        self.db.commit()
        return order, None

    # ================= 3. 订单状态流转 =================

    def ship_order(self, order_id, ship_date=None):
        """
        订单发货
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        if order.status != OrderStatus.PENDING:
            raise ValueError(f"当前订单状态为 {order.status}，无法发货")

        ship_date = ship_date or date.today()
        order.status = OrderStatus.SHIPPED
        order.shipped_date = ship_date

        self.db.commit()
        return f"订单 {order.order_no} 已标记为已发货"

    def complete_order(self, order_id, complete_date=None):
        """
        订单完成 - 确认收款并计入收入
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        if order.status not in [OrderStatus.SHIPPED, OrderStatus.PENDING]:
            raise ValueError(f"当前订单状态为 {order.status}，无法完成")

        complete_date = complete_date or date.today()

        # 1. 计算实际应收金额（订单总额 - 已退款金额）
        total_refunded = self.db.query(func.sum(OrderRefund.refund_amount)).filter(
            OrderRefund.order_id == order_id
        ).scalar() or 0.0

        actual_income = order.total_amount - total_refunded

        # 2. 增加流动资金
        asset_name = f"{AssetPrefix.CASH}({order.currency})"
        self._update_asset_by_name(asset_name, actual_income, category="asset", currency=order.currency)

        # 3. 创建财务流水
        finance = FinanceRecord(
            date=complete_date,
            amount=actual_income,
            currency=order.currency,
            category=FinanceCategory.SALES_INCOME,
            description=f"订单收款: {order.order_no} (平台:{order.platform})"
        )
        self.db.add(finance)

        # 4. 更新订单状态
        order.status = OrderStatus.COMPLETED
        order.completed_date = complete_date

        self.db.commit()
        return f"订单 {order.order_no} 已完成，收入 {actual_income:.2f} {order.currency}"

    # ================= 4. 售后处理 =================

    def add_refund(self, order_id, refund_amount, refund_reason, is_returned=False,
                   returned_quantity=0, returned_items=None, refund_date=None):
        """
        添加售后记录

        order_id: 订单ID
        refund_amount: 退款金额
        refund_reason: 退款原因
        is_returned: 是否退货
        returned_quantity: 退货总数量（用于显示）
        returned_items: 退货明细 list of dict [{"product_name": "xxx", "variant": "红色", "quantity": 1}, ...]
        refund_date: 退款日期

        返回: 提示消息
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        refund_date = refund_date or date.today()

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
        if is_returned and returned_items:
            for item in returned_items:
                product_name = item["product_name"]
                variant = item["variant"]
                quantity = item["quantity"]

                # 创建退货入库日志
                log = InventoryLog(
                    product_name=product_name,
                    variant=variant,
                    change_amount=quantity,
                    reason="退货入库",
                    date=refund_date,
                    note=f"订单退货: {order.order_no} - {refund_reason}",
                    is_sold=True,
                    sale_amount=-refund_amount,  # 负数表示退款
                    currency=order.currency,
                    platform=order.platform
                )
                self.db.add(log)

                # 回滚库存资产价值
                product = self.db.query(Product).filter(Product.name == product_name).first()
                if product:
                    unit_cost = self._get_unit_cost(product.id)
                    asset_delta = quantity * unit_cost
                    asset_name = f"{AssetPrefix.STOCK}{product_name}"
                    self._update_asset_by_name(asset_name, asset_delta, category="asset", currency="CNY")

        # 3. 创建售后成本项（关键：计入商品成本核算）
        # 找到订单中的第一个商品的 product_id
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
                    item_name=f"售后退款-{refund_reason}",
                    actual_cost=refund_amount,
                    supplier=order.platform,  # 【关键】供应商字段记录销售平台
                    category="售后成本",
                    unit_price=refund_amount,
                    quantity=1,
                    remarks=refund_reason,
                    order_no=order.order_no  # 【新增】记录订单号
                )
                self.db.add(cost_item)
                self.db.flush()

                # 关联到售后记录
                refund.cost_item_id = cost_item.id

        # 4. 如果订单已完成，需要从流动资金中扣除退款
        if order.status == OrderStatus.COMPLETED:
            asset_name = f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -refund_amount, category="asset", currency=order.currency)

        # 5. 更新订单状态为"售后中"
        order.status = OrderStatus.AFTER_SALES

        self.db.commit()

        msg = f"售后记录已添加: 退款 {refund_amount:.2f} {order.currency}"
        if is_returned:
            msg += f", 已退货 {returned_quantity} 件"
        return msg

    # ================= 5. 删除订单 (回滚) =================

    def delete_order(self, order_id):
        """
        删除订单并完整回滚所有操作
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        # 1. 回滚库存 - 删除出库日志
        logs = self.db.query(InventoryLog).filter(
            InventoryLog.note.like(f"%{order.order_no}%")
        ).all()

        for log in logs:
            # 回滚资产价值
            product = self.db.query(Product).filter(
                Product.name == log.product_name
            ).first()

            if product:
                unit_cost = self._get_unit_cost(product.id)
                # 注意：log.change_amount 是负数，所以取反即可
                asset_delta = -log.change_amount * unit_cost
                asset_name = f"{AssetPrefix.STOCK}{product.name}"
                self._update_asset_by_name(asset_name, asset_delta, category="asset", currency="CNY")

            self.db.delete(log)

        # 2. 删除关联的成本项（售后成本）
        refunds = self.db.query(OrderRefund).filter(OrderRefund.order_id == order_id).all()
        for refund in refunds:
            if refund.cost_item_id:
                cost_item = self.db.query(CostItem).filter(
                    CostItem.id == refund.cost_item_id
                ).first()
                if cost_item:
                    self.db.delete(cost_item)

        # 3. 如果订单已完成，回滚流动资金
        if order.status == OrderStatus.COMPLETED:
            # 计算已收款金额
            total_refunded = self.db.query(func.sum(OrderRefund.refund_amount)).filter(
                OrderRefund.order_id == order_id
            ).scalar() or 0.0
            actual_income = order.total_amount - total_refunded

            asset_name = f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -actual_income, category="asset", currency=order.currency)

            # 删除关联的财务流水
            finance = self.db.query(FinanceRecord).filter(
                FinanceRecord.description.like(f"%{order.order_no}%")
            ).first()
            if finance:
                self.db.delete(finance)

        # 4. 级联删除订单（会自动删除订单明细和售后记录）
        self.db.delete(order)

        self.db.commit()
        return f"订单 {order.order_no} 已删除，所有数据已回滚"

    def commit(self):
        """提交事务"""
        self.db.commit()

# services/sales_order_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from datetime import date
from models import (
    SalesOrder, SalesOrderItem, OrderRefund,
    Product, InventoryLog, CompanyBalanceItem,
    CostItem, FinanceRecord, Warehouse, SalesPlatform
)
import math
import pandas as pd
from constants import OrderStatus, FinanceCategory, AssetPrefix
from services.inventory_service import InventoryService

class SalesOrderService:
    def __init__(self, db: Session):
        self.db = db
        self.inventory_service = InventoryService(db)
        
    def _get_default_target_account(self, platform: str = "", currency: str = "CNY") -> str:
        plat_str = (platform or "").lower()
        curr_str = (currency or "CNY").upper()
        if "微店" in plat_str or "weidian" in plat_str:
            return "流动资金-微店账户"
        if "booth" in plat_str:
            return "流动资金-booth账户"
        if curr_str == "JPY":
            acc = self.db.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.category == "asset",
                CompanyBalanceItem.asset_type == "现金",
                CompanyBalanceItem.currency == "JPY",
                CompanyBalanceItem.name.like("流动资金-%")
            ).first()
            if acc:
                return acc.name
            return "流动资金-日元银行账户"
        
        # CNY 默认支付宝账户
        acc = self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.category == "asset",
            CompanyBalanceItem.asset_type == "现金",
            CompanyBalanceItem.currency == "CNY",
            CompanyBalanceItem.name == "流动资金-支付宝账户"
        ).first()
        if acc:
            return acc.name
        return "流动资金-支付宝账户"

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
            self.db.flush()

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
                # 在资产名称后缀加上订单的币种，实现账目币种隔离
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{p_name}-{order.currency}" 
                self._update_asset_by_name(pending_asset_name, item_delta, category="asset", currency=order.currency)
        else:
            if order.items:
                pending_asset_name = f"{AssetPrefix.PENDING_SETTLE}-{order.items[0].product_name}-{order.currency}"
                self._update_asset_by_name(pending_asset_name, amount_delta, category="asset", currency=order.currency)

    # ================= 1. 查询方法 =================

    def get_all_orders(self, status=None, product_name=None, order_type="线上", limit=100):
        query = self.db.query(SalesOrder).options(
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.warehouse),
            joinedload(SalesOrder.refunds)
        ).filter(SalesOrder.order_type == order_type) 
        
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

    def get_order_by_no(self, order_no, order_type="预售"):
        """根据订单号精确查找预售订单"""
        return self.db.query(SalesOrder).options(
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.warehouse)
        ).filter(
            SalesOrder.order_no == order_no,
            SalesOrder.order_type == order_type
        ).first()

    def get_order_statistics(self, product_name=None, order_type="线上"):
        base_query = self.db.query(func.count(SalesOrder.id.distinct())).filter(SalesOrder.order_type == order_type)

        if product_name:
            base_query = base_query.join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name
            )

            pending_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name, SalesOrder.status == OrderStatus.PENDING, SalesOrder.order_type == order_type
            )
            shipped_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name, SalesOrder.status == OrderStatus.SHIPPED, SalesOrder.order_type == order_type
            )
            completed_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name, SalesOrder.status == OrderStatus.COMPLETED, SalesOrder.order_type == order_type
            )
            after_sales_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name, SalesOrder.status == OrderStatus.AFTER_SALES, SalesOrder.order_type == order_type
            )
            deposit_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name, SalesOrder.status == OrderStatus.PRESALE_PENDING_DEPOSIT, SalesOrder.order_type == order_type
            )
            final_query = self.db.query(func.count(SalesOrder.id.distinct())).join(SalesOrder.items).filter(
                SalesOrderItem.product_name == product_name, SalesOrder.status == OrderStatus.PRESALE_PENDING_FINAL, SalesOrder.order_type == order_type
            )
        else:
            pending_query = self.db.query(func.count(SalesOrder.id)).filter(SalesOrder.status == OrderStatus.PENDING, SalesOrder.order_type == order_type)
            shipped_query = self.db.query(func.count(SalesOrder.id)).filter(SalesOrder.status == OrderStatus.SHIPPED, SalesOrder.order_type == order_type)
            completed_query = self.db.query(func.count(SalesOrder.id)).filter(SalesOrder.status == OrderStatus.COMPLETED, SalesOrder.order_type == order_type)
            after_sales_query = self.db.query(func.count(SalesOrder.id)).filter(SalesOrder.status == OrderStatus.AFTER_SALES, SalesOrder.order_type == order_type)
            deposit_query = self.db.query(func.count(SalesOrder.id)).filter(SalesOrder.status == OrderStatus.PRESALE_PENDING_DEPOSIT, SalesOrder.order_type == order_type)
            final_query = self.db.query(func.count(SalesOrder.id)).filter(SalesOrder.status == OrderStatus.PRESALE_PENDING_FINAL, SalesOrder.order_type == order_type)

        return {
            "total": base_query.scalar() or 0,
            "pending": pending_query.scalar() or 0,
            "shipped": shipped_query.scalar() or 0,
            "completed": completed_query.scalar() or 0,
            "after_sales": after_sales_query.scalar() or 0,
            "pending_deposit": deposit_query.scalar() or 0,
            "pending_final": final_query.scalar() or 0
        }

    # ================= 2. 创建普通线上订单 =================

    def create_order(self, items_data, platform, currency, notes="", order_date=None, order_no=None, target_account_name=None):
        if not items_data: return None, "订单明细不能为空"
        if not order_no or not order_no.strip(): return None, "订单号不能为空"
        order_no = order_no.strip()
        order_date = order_date or date.today()

        existing = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
        if existing: return None, f"订单号 {order_no} 已存在，请使用其他订单号"

        if not target_account_name:
            target_account_name = self._get_default_target_account(platform, currency)

        total_amount = sum(item["quantity"] * item["unit_price"] for item in items_data)

        order = SalesOrder(
            order_no=order_no, status=OrderStatus.PENDING, total_amount=total_amount,
            order_type="线上",
            currency=currency, platform=platform, created_date=order_date, notes=notes,
            target_account_name=target_account_name 
        )
        self.db.add(order)
        self.db.flush()  

        for item in items_data:
            order_item = SalesOrderItem(
                order_id=order.id, product_name=item["product_name"], variant=item["variant"],
                quantity=item["quantity"], unit_price=item["unit_price"], subtotal=item["quantity"] * item["unit_price"],
                warehouse_id=item.get("warehouse_id")
            )
            self.db.add(order_item)

        self.db.commit()
        return order, None

    # ================= 预售专项方法 =================
    
    def create_presale_deposit_order(self, items_data, platform, currency, notes="", order_date=None, order_no=None, target_account_name=None, discount_note=""):
        """1. 创建定金订单，增加优惠字段"""
        if not items_data: return None, "订单明细不能为空"
        if not order_no or not order_no.strip(): return None, "定金订单号不能为空"
        order_no = order_no.strip()
        order_date = order_date or date.today()

        existing = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
        if existing: return None, f"订单号 {order_no} 已存在"

        if not target_account_name:
            target_account_name = self._get_default_target_account(platform, currency)

        deposit_amount = sum(item["quantity"] * item["unit_price"] for item in items_data)

        order = SalesOrder(
            order_no=order_no, order_type="预售", status=OrderStatus.PRESALE_PENDING_DEPOSIT, 
            total_amount=deposit_amount, deposit_amount=deposit_amount, final_amount=0.0,
            currency=currency, platform=platform, created_date=order_date, notes=notes,
            target_account_name=target_account_name,
            discount_note=discount_note
        )
        self.db.add(order)
        self.db.flush()

        for item in items_data:
            order_item = SalesOrderItem(
                order_id=order.id, product_name=item["product_name"], variant=item["variant"],
                quantity=item["quantity"], unit_price=item["unit_price"], subtotal=item["quantity"] * item["unit_price"],
                warehouse_id=item.get("warehouse_id")
            )
            self.db.add(order_item)

        self.db.commit()
        return order, None

    def complete_deposit_order(self, order_id, complete_date=None):
        """2. 完成定金订单 (不扣减库存，直接入账)"""
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")
        if order.status != OrderStatus.PRESALE_PENDING_DEPOSIT: raise ValueError("必须是【待完成定金】状态")

        complete_date = complete_date or date.today()
        actual_income = order.deposit_amount

        asset_name = order.target_account_name or self._get_default_target_account(order.platform, order.currency)
        self._update_asset_by_name(asset_name, actual_income, category="asset", currency=order.currency)
        target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()

        self.db.add(FinanceRecord(
            date=complete_date, amount=actual_income, currency=order.currency,
            category=FinanceCategory.SALES_INCOME, 
            description=f"定金收款: {order.order_no} (预售) [账户: {asset_name}]",
            order_id=order.id, account_id=target_acc.id if target_acc else None
        ))

        order.status = OrderStatus.PRESALE_PENDING_FINAL # 状态转为待付尾款
        self.db.commit()
        return f"定金订单 {order.order_no} 已完成，状态更新为待付尾款"

    def bind_presale_final_order(self, deposit_order_ids, final_order_no, final_net_amount, new_notes=""):
        """3. 绑定尾款并激活发货状态（支持单个/多个定金订单合并绑定同一尾款）"""
        if isinstance(deposit_order_ids, (int, str)):
            deposit_order_ids = [int(deposit_order_ids)]
        else:
            deposit_order_ids = [int(x) for x in deposit_order_ids]

        if not deposit_order_ids:
            raise ValueError("未指定任何定金订单")

        final_order_no = final_order_no.strip()

        # 检查是否与已有订单的主单号冲突
        main_order_conflict = self.db.query(SalesOrder).filter(
            SalesOrder.order_no == final_order_no
        ).first()
        if main_order_conflict:
            raise ValueError(f"该尾款单号与现有订单主单号 {final_order_no} 冲突，无法使用")

        # 查找本次要绑定的定金订单
        new_orders = self.db.query(SalesOrder).filter(
            SalesOrder.id.in_(deposit_order_ids),
            SalesOrder.order_type == "预售"
        ).all()

        if len(new_orders) != len(deposit_order_ids):
            raise ValueError("部分定金订单不存在或不是预售订单")

        for o in new_orders:
            if o.status != OrderStatus.PRESALE_PENDING_FINAL:
                raise ValueError(f"定金单 {o.order_no} 目前状态为【{o.status}】，非【待付尾款】状态，无法绑定")

        # 查找是否已有其他定金订单已经绑定了该 final_order_no
        existing_bound_orders = self.db.query(SalesOrder).filter(
            SalesOrder.final_order_no == final_order_no,
            SalesOrder.order_type == "预售",
            SalesOrder.id.notin_(deposit_order_ids)
        ).all()

        # 确定总实收尾款金额
        if existing_bound_orders and final_net_amount <= 0:
            total_final_net = sum(o.final_amount for o in existing_bound_orders)
        else:
            total_final_net = float(final_net_amount)

        all_target_orders = existing_bound_orders + new_orders

        # 校验币种一致性
        currencies = set(o.currency for o in all_target_orders)
        if len(currencies) > 1:
            raise ValueError(f"合并绑定的定金单币种不一致: {', '.join(currencies)}")

        # 按定金金额比例平摊尾款
        total_dep_amount = sum(o.deposit_amount for o in all_target_orders)
        accumulated_final = 0.0

        for i, o in enumerate(all_target_orders):
            if i == len(all_target_orders) - 1:
                o.final_amount = round(total_final_net - accumulated_final, 2)
            else:
                if total_dep_amount > 0:
                    share = round(total_final_net * (o.deposit_amount / total_dep_amount), 2)
                else:
                    share = round(total_final_net / len(all_target_orders), 2)
                o.final_amount = share
                accumulated_final += share

            o.final_order_no = final_order_no
            o.total_amount = round(o.deposit_amount + o.final_amount, 2)
            o.status = OrderStatus.PENDING  # 激活为待发货

            if o in new_orders and new_notes:
                o.notes = f"{o.notes} | 尾款备注: {new_notes}" if o.notes else new_notes

            total_qty = sum(item.quantity for item in o.items)
            if total_qty > 0:
                new_unit_price = o.total_amount / total_qty
                for item in o.items:
                    item.unit_price = new_unit_price
                    item.subtotal = item.quantity * new_unit_price

        self.db.commit()
        dep_nos_str = ", ".join(o.order_no for o in all_target_orders)
        return f"尾款 {final_order_no} 已成功合并绑定至 {len(all_target_orders)} 个定金单 ({dep_nos_str})，订单已转入待发货状态！"

    def batch_update_warehouse(self, order_ids: list[int], warehouse_id: int):
        """批量修改指定订单的发货仓库"""
        if not order_ids:
            raise ValueError("未选择任何订单")
        wh = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise ValueError("选中的仓库不存在")

        orders = self.db.query(SalesOrder).filter(SalesOrder.id.in_(order_ids)).all()
        for order in orders:
            for item in order.items:
                item.warehouse_id = warehouse_id
        
        self.db.commit()
        return len(orders), wh.name

    def batch_complete_deposit_orders(self, order_ids: list[int], complete_date=None):
        """🚀 批量完成定金订单：单事务统一处理与提交"""
        if not order_ids:
            return 0, []
        complete_date = complete_date or date.today()
        orders = self.db.query(SalesOrder).filter(SalesOrder.id.in_(order_ids)).all()
        
        success_count = 0
        errors = []
        
        for order in orders:
            if order.status != OrderStatus.PRESALE_PENDING_DEPOSIT:
                errors.append(f"定金单 {order.order_no} 当前状态为【{order.status}】，非待完成定金状态")
                continue
            
            actual_income = order.deposit_amount
            asset_name = order.target_account_name or self._get_default_target_account(order.platform, order.currency)
            target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()
            
            self._update_asset_by_name(asset_name, actual_income, category="asset", currency=order.currency)
            
            self.db.add(FinanceRecord(
                date=complete_date, amount=actual_income, currency=order.currency,
                category=FinanceCategory.SALES_INCOME,
                description=f"定金收款: {order.order_no} (预售) [账户: {asset_name}]",
                order_id=order.id, account_id=target_acc.id if target_acc else None
            ))
            
            order.status = OrderStatus.PRESALE_PENDING_FINAL
            success_count += 1
            
        self.db.commit()
        return success_count, errors

    def batch_ship_orders(self, order_ids: list[int], ship_date=None):
        """🚀 高性能批量发货：批量检查库存、去重预售关联单、延迟单次重算大货资产并单事务提交"""
        if not order_ids:
            return 0, []
        ship_date = ship_date or date.today()
        
        orders = self.db.query(SalesOrder).filter(SalesOrder.id.in_(order_ids)).all()
        order_map = {o.id: o for o in orders}
        
        processed_order_ids = set()
        product_ids_to_sync = set()
        success_count = 0
        errors = []
        valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]
        
        for o_id in order_ids:
            if o_id in processed_order_ids:
                continue
            order = order_map.get(o_id)
            if not order:
                order = self.db.query(SalesOrder).filter(SalesOrder.id == o_id).first()
            if not order:
                errors.append(f"订单 ID {o_id} 不存在")
                continue
                
            if order.status != OrderStatus.PENDING:
                if order.status == OrderStatus.SHIPPED and o_id in processed_order_ids:
                    continue
                errors.append(f"订单 {order.order_no} 当前状态为【{order.status}】，无法发货")
                continue
                
            orders_to_ship = [order]
            if order.order_type == "预售" and order.final_order_no:
                orders_to_ship = self.db.query(SalesOrder).filter(
                    SalesOrder.final_order_no == order.final_order_no,
                    SalesOrder.order_type == "预售"
                ).all()
                
            # 1. 检查库存
            stock_err = None
            for o in orders_to_ship:
                if o.status != OrderStatus.PENDING:
                    continue
                for item in o.items:
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
                        stock_err = f"库存不足：单据 {o.order_no} 的 {item.product_name}-{item.variant} 在【{wh_name_display}】(需要:{item.quantity}, 可用:{current_stock})"
                        break
                if stock_err:
                    break
                    
            if stock_err:
                errors.append(stock_err)
                continue
                
            # 2. 执行出库
            for o in orders_to_ship:
                if o.status != OrderStatus.PENDING:
                    continue
                for item in o.items:
                    self.db.add(InventoryLog(
                        product_name=item.product_name, variant=item.variant, change_amount=-item.quantity,
                        reason="出库", date=ship_date, note=f"销售订单发货: {o.final_order_no if o.order_type=='预售' else o.order_no}",
                        is_sold=True, sale_amount=item.subtotal, currency=o.currency, platform=o.platform,
                        order_id=o.id, warehouse_id=item.warehouse_id
                    ))
                    product = self.db.query(Product).filter(Product.name == item.product_name).first()
                    if product:
                        product_ids_to_sync.add(product.id)
                        
                pending_amount = o.final_amount if o.order_type == "预售" else o.total_amount
                self._distribute_pending_asset(o, pending_amount)
                o.status = OrderStatus.SHIPPED
                o.shipped_date = ship_date
                processed_order_ids.add(o.id)
                success_count += 1
                
        self.db.flush()
        
        # 3. 仅对整批涉及的各商品唯一 ID 执行 1 次全量资产重算！
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)
            
        self.db.commit()
        return success_count, errors

    def batch_complete_orders(self, order_ids: list[int], complete_date=None):
        """🚀 高性能批量收款结清：自动识别预售关联单、单事务批量记账并提交"""
        if not order_ids:
            return 0, []
        complete_date = complete_date or date.today()
        
        orders = self.db.query(SalesOrder).filter(SalesOrder.id.in_(order_ids)).all()
        order_map = {o.id: o for o in orders}
        
        processed_order_ids = set()
        processed_final_order_nos = set()
        success_count = 0
        errors = []
        
        for o_id in order_ids:
            if o_id in processed_order_ids:
                continue
            order = order_map.get(o_id)
            if not order:
                order = self.db.query(SalesOrder).filter(SalesOrder.id == o_id).first()
            if not order:
                errors.append(f"订单 ID {o_id} 不存在")
                continue
                
            if order.status not in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]:
                errors.append(f"订单 {order.order_no} 当前状态为【{order.status}】，不能结清")
                continue
                
            asset_name = order.target_account_name or self._get_default_target_account(order.platform, order.currency)
            target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()
            
            if order.order_type == "预售":
                if order.final_order_no and order.final_order_no in processed_final_order_nos:
                    continue
                orders_to_complete = [order]
                if order.final_order_no:
                    orders_to_complete = self.db.query(SalesOrder).filter(
                        SalesOrder.final_order_no == order.final_order_no,
                        SalesOrder.order_type == "预售"
                    ).all()
                    processed_final_order_nos.add(order.final_order_no)
                    
                total_final_income = sum(o.final_amount for o in orders_to_complete)
                
                for o in orders_to_complete:
                    if o.status in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]:
                        self._distribute_pending_asset(o, -o.final_amount)
                        o.status = OrderStatus.COMPLETED
                        o.completed_date = complete_date
                        processed_order_ids.add(o.id)
                        success_count += 1
                        
                self._update_asset_by_name(asset_name, total_final_income, category="asset", currency=order.currency)
                dep_nos = ", ".join(o.order_no for o in orders_to_complete)
                self.db.add(FinanceRecord(
                    date=complete_date, amount=total_final_income, currency=order.currency,
                    category=FinanceCategory.SALES_INCOME,
                    description=f"尾款收款: {order.final_order_no} (关联定金:{dep_nos}) [账户: {asset_name}]",
                    order_id=order.id, account_id=target_acc.id if target_acc else None
                ))
            else:
                actual_income = order.total_amount
                self._distribute_pending_asset(order, -actual_income)
                self._update_asset_by_name(asset_name, actual_income, category="asset", currency=order.currency)
                self.db.add(FinanceRecord(
                    date=complete_date, amount=actual_income, currency=order.currency,
                    category=FinanceCategory.SALES_INCOME,
                    description=f"订单收款: {order.order_no} (平台:{order.platform}) [账户: {asset_name}]",
                    order_id=order.id, account_id=target_acc.id if target_acc else None
                ))
                order.status = OrderStatus.COMPLETED
                order.completed_date = complete_date
                processed_order_ids.add(order.id)
                success_count += 1
                
        self.db.commit()
        return success_count, errors

    # ================= 3. 订单状态通用流转 =================

    def ship_order(self, order_id, ship_date=None):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")
        if order.status != OrderStatus.PENDING: raise ValueError(f"当前订单状态为 {order.status}，无法发货")

        ship_date = ship_date or date.today()
        product_ids_to_sync = set()
        valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]

        # 如果是预售订单且绑定了尾款，查找所有绑定同一尾款单的关联定金单（合并发货联动）
        orders_to_ship = [order]
        if order.order_type == "预售" and order.final_order_no:
            orders_to_ship = self.db.query(SalesOrder).filter(
                SalesOrder.final_order_no == order.final_order_no,
                SalesOrder.order_type == "预售"
            ).all()

        # 1. 预先做库存检查（所有关联订单整体检查）
        for o in orders_to_ship:
            if o.status != OrderStatus.PENDING:
                continue
            for item in o.items:
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
                    raise ValueError(f"库存不足：定金单 {o.order_no} 的 {item.product_name}-{item.variant} 在【{wh_name_display}】(需要:{item.quantity}, 可用:{current_stock})")

        # 2. 执行出库与状态更新
        for o in orders_to_ship:
            if o.status != OrderStatus.PENDING:
                continue
            for item in o.items:
                self.db.add(InventoryLog(
                    product_name=item.product_name, variant=item.variant, change_amount=-item.quantity,
                    reason="出库", date=ship_date, note=f"销售订单发货: {o.final_order_no if o.order_type=='预售' else o.order_no}",
                    is_sold=True, sale_amount=item.subtotal, currency=o.currency, platform=o.platform,
                    order_id=o.id, warehouse_id=item.warehouse_id
                ))
                
                product = self.db.query(Product).filter(Product.name == item.product_name).first()
                if product: product_ids_to_sync.add(product.id)

            pending_amount = o.final_amount if o.order_type == "预售" else o.total_amount
            self._distribute_pending_asset(o, pending_amount)
            o.status = OrderStatus.SHIPPED
            o.shipped_date = ship_date

        self.db.flush()
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        if len(orders_to_ship) > 1:
            dep_nos = ", ".join(o.order_no for o in orders_to_ship)
            return f"尾款 {order.final_order_no} 关联的 {len(orders_to_ship)} 个定金单 ({dep_nos}) 已合并发货！"
        return f"订单已发货，已生成待结算款"

    def complete_order(self, order_id, complete_date=None):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")
        if order.status not in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]: raise ValueError(f"当前状态 {order.status} 不能完成")

        complete_date = complete_date or date.today()
        asset_name = order.target_account_name or self._get_default_target_account(order.platform, order.currency)
        target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()
        
        if order.order_type == "预售":
            orders_to_complete = [order]
            if order.final_order_no:
                orders_to_complete = self.db.query(SalesOrder).filter(
                    SalesOrder.final_order_no == order.final_order_no,
                    SalesOrder.order_type == "预售"
                ).all()

            total_final_income = sum(o.final_amount for o in orders_to_complete)

            for o in orders_to_complete:
                if o.status in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]:
                    self._distribute_pending_asset(o, -o.final_amount) 
                    o.status = OrderStatus.COMPLETED
                    o.completed_date = complete_date

            self._update_asset_by_name(asset_name, total_final_income, category="asset", currency=order.currency)
            dep_nos = ", ".join(o.order_no for o in orders_to_complete)
            self.db.add(FinanceRecord(
                date=complete_date, amount=total_final_income, currency=order.currency,
                category=FinanceCategory.SALES_INCOME, 
                description=f"尾款收款: {order.final_order_no} (关联定金:{dep_nos}) [账户: {asset_name}]",
                order_id=order.id, account_id=target_acc.id if target_acc else None
            ))
            msg = f"预售尾款 {order.final_order_no} ({len(orders_to_complete)}单) 收清，订单彻底完成"
        else:
            actual_income = order.total_amount
            self._distribute_pending_asset(order, -actual_income)
            self._update_asset_by_name(asset_name, actual_income, category="asset", currency=order.currency)
            self.db.add(FinanceRecord(
                date=complete_date, amount=actual_income, currency=order.currency,
                category=FinanceCategory.SALES_INCOME, 
                description=f"订单收款: {order.order_no} (平台:{order.platform}) [账户: {asset_name}]",
                order_id=order.id, account_id=target_acc.id if target_acc else None
            ))
            order.status = OrderStatus.COMPLETED
            order.completed_date = complete_date
            msg = f"订单 {order.order_no} 已完成，收入 {actual_income:.2f} {order.currency}"

        self.db.commit()
        return msg

    # ================= 4. 售后处理 (自动兼容) =================
    
    def add_refund(self, order_id, refund_amount, refund_reason, is_returned=False,
                   returned_quantity=0, returned_items=None, refund_date=None,
                   exchange_rate=1.0, is_resend=False, resend_quantity=0, resend_items=None):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order: raise ValueError("订单不存在")
        if order.status in [OrderStatus.PENDING, OrderStatus.PRESALE_PENDING_DEPOSIT]: 
            raise ValueError("当前状态不允许售后申请")

        refund_date = refund_date or date.today()
        is_completed = (order.status == OrderStatus.COMPLETED)

        refund = OrderRefund(
            order_id=order_id, refund_amount=refund_amount, refund_reason=refund_reason,
            refund_date=refund_date, is_returned=is_returned, returned_quantity=returned_quantity,
            is_resend=is_resend, resend_quantity=resend_quantity
        )
        self.db.add(refund)
        self.db.flush()

        product_ids_to_sync = set()

        if is_returned and returned_items and order.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
            for item in returned_items:
                self.db.add(InventoryLog(
                    product_name=item["product_name"], variant=item["variant"], change_amount=item["quantity"],
                    reason="退货入库", date=refund_date, note=f"订单退货: {order.order_no} - {refund_reason}",
                    is_sold=True, sale_amount=0, currency=order.currency, platform=order.platform,
                    order_id=order.id, warehouse_id=item.get("warehouse_id")
                ))
                product = self.db.query(Product).filter(Product.name == item["product_name"]).first()
                if product: product_ids_to_sync.add(product.id)
                
        if is_resend and resend_items and order.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
            for item in resend_items:
                self.db.add(InventoryLog(
                    product_name=item["product_name"], variant=item["variant"], 
                    change_amount=-item["quantity"], 
                    reason="出库", date=refund_date, 
                    note=f"售后补发: {order.order_no} - {refund_reason}",
                    is_sold=False, sale_amount=0, currency=order.currency, platform=order.platform,
                    order_id=order.id, warehouse_id=item.get("warehouse_id"),
                    part_name=item.get("part_name") 
                ))
                product = self.db.query(Product).filter(Product.name == item["product_name"]).first()
                if product: product_ids_to_sync.add(product.id)

        first_item = self.db.query(SalesOrderItem).filter(SalesOrderItem.order_id == order_id).first()
        if first_item:
            product = self.db.query(Product).filter(Product.name == first_item.product_name).first()
            if product:
                cost_in_cny = refund_amount
                if order.currency == 'JPY':
                    cost_in_cny = refund_amount * exchange_rate
                    
                cost_item = CostItem(
                    product_id=product.id, item_name=f"[{order.order_no}+售后]", actual_cost=cost_in_cny,
                    supplier=order.platform, category="售后成本", unit_price=cost_in_cny, quantity=1,
                    remarks=refund_reason, order_no=order.order_no,
                    currency=order.currency, original_amount=refund_amount
                )
                self.db.add(cost_item)
                self.db.flush()
                refund.cost_item_id = cost_item.id
                product_ids_to_sync.add(product.id)

        if is_completed or order.status == OrderStatus.PRESALE_PENDING_FINAL:
            asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -refund_amount, category="asset", currency=order.currency)
            target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == asset_name).first()
            
            if refund_amount > 0:
                self.db.add(FinanceRecord(
                    date=refund_date, amount=-refund_amount, currency=order.currency,
                    category=FinanceCategory.SALES_INCOME, 
                    description=f"退款: {order.order_no} - {refund_reason} [账户: {asset_name}]",
                    order_id=order.id, account_id=target_acc.id if target_acc else None
                ))
        else:
            order.total_amount -= refund_amount
            if order.total_amount < 0: order.total_amount = 0
            self._distribute_pending_asset(order, -refund_amount)

        order.status = OrderStatus.AFTER_SALES

        self.db.flush()
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return "售后记录已添加"

    def update_refund(self, refund_id, refund_amount, refund_reason, exchange_rate=1.0):
        refund = self.db.query(OrderRefund).filter(OrderRefund.id == refund_id).first()
        if not refund: raise ValueError("售后记录不存在")
        
        order = refund.order
        old_amount = refund.refund_amount
        old_reason = refund.refund_reason
        delta = refund_amount - old_amount 
        
        if refund.cost_item_id:
            cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
            if cost_item:
                cost_in_cny = refund_amount
                if order.currency == 'JPY':
                    cost_in_cny = refund_amount * exchange_rate
                    
                cost_item.actual_cost = cost_in_cny
                cost_item.unit_price = cost_in_cny
                cost_item.original_amount = refund_amount
                cost_item.currency = order.currency
                cost_item.remarks = refund_reason

        if order.status == OrderStatus.COMPLETED or order.status == OrderStatus.PRESALE_PENDING_FINAL:
            asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, -delta, currency=order.currency)
            
            finance_rec = self.db.query(FinanceRecord).filter(
                FinanceRecord.order_id == order.id,
                FinanceRecord.description.like(f"退款: {order.order_no}%")
            ).first()
            if finance_rec:
                finance_rec.amount = -refund_amount
                finance_rec.description = f"退款: {order.order_no} - {refund_reason} [账户: {asset_name}]"
        else:
            self._distribute_pending_asset(order, -delta)

        if refund.is_returned and old_reason != refund_reason:
            target_old_note = f"订单退货: {order.order_no} - {old_reason}"
            return_logs = self.db.query(InventoryLog).filter(
                InventoryLog.order_id == order.id,
                InventoryLog.reason == "退货入库",
                InventoryLog.note == target_old_note
            ).all()
            for log in return_logs:
                log.note = f"订单退货: {order.order_no} - {refund_reason}"

        if getattr(refund, 'is_resend', False) and old_reason != refund_reason:
            target_old_note = f"售后补发: {order.order_no} - {old_reason}"
            resend_logs = self.db.query(InventoryLog).filter(
                InventoryLog.order_id == order.id,
                InventoryLog.reason == "出库",
                InventoryLog.note == target_old_note
            ).all()
            for log in resend_logs:
                log.note = f"售后补发: {order.order_no} - {refund_reason}"

        refund.refund_amount = refund_amount
        refund.refund_reason = refund_reason
        if order.items:
            product = self.db.query(Product).filter(Product.name == order.items[0].product_name).first()
            if product:
                InventoryService(self.db).sync_product_metrics(product.id)
        
        self.db.commit()
        return "售后记录已成功修改"

    def delete_refund(self, refund_id):
        refund = self.db.query(OrderRefund).filter(OrderRefund.id == refund_id).first()
        if not refund: raise ValueError("售后记录不存在")
        
        order = refund.order
        amount_to_restore = refund.refund_amount
        product_ids_to_sync = set()
        
        if order.status == OrderStatus.COMPLETED:
            asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
            self._update_asset_by_name(asset_name, amount_to_restore, currency=order.currency)
            self.db.query(FinanceRecord).filter(
                FinanceRecord.order_id == order.id,
                FinanceRecord.description.like(f"退款: {order.order_no}%")
            ).delete()
        else:
            self._distribute_pending_asset(order, amount_to_restore)

        if refund.cost_item_id:
            cost_item = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
            if cost_item:
                product_ids_to_sync.add(cost_item.product_id)
                self.db.delete(cost_item)

        if refund.is_returned:
            target_note = f"订单退货: {order.order_no} - {refund.refund_reason}"
            return_logs = self.db.query(InventoryLog).filter(
                InventoryLog.order_id == order.id,
                InventoryLog.reason == "退货入库",
                InventoryLog.note == target_note
            ).all()
            
            for log in return_logs:
                p = self.db.query(Product).filter(Product.name == log.product_name).first()
                if p: product_ids_to_sync.add(p.id)
                self.db.delete(log)

        if getattr(refund, 'is_resend', False):
            target_resend_note = f"售后补发: {order.order_no} - {refund.refund_reason}"
            resend_logs = self.db.query(InventoryLog).filter(
                InventoryLog.order_id == order.id,
                InventoryLog.reason == "出库",
                InventoryLog.note == target_resend_note
            ).all()
            
            for log in resend_logs:
                p = self.db.query(Product).filter(Product.name == log.product_name).first()
                if p: product_ids_to_sync.add(p.id)
                self.db.delete(log)
        
        self.db.delete(refund)
        self.db.flush()

        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return "售后记录已删除，相关的资金、成本及实物库存均已回滚"

    # ================= 5. 删除订单 (智能回滚兼容) =================

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

        finances = self.db.query(FinanceRecord).filter(
            or_(FinanceRecord.order_id == order_id, FinanceRecord.description.like(f"%{order.order_no}%"))
        ).all()
        
        income_to_rollback = sum(f.amount for f in finances if f.amount > 0 and f.category == FinanceCategory.SALES_INCOME)
        if income_to_rollback > 0:
            asset_name = order.target_account_name or self._get_default_target_account(order.platform, order.currency)
            self._update_asset_by_name(asset_name, -income_to_rollback, category="asset", currency=order.currency)

        for finance in finances: self.db.delete(finance)
                
        if order.status in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]:
            pending_to_rollback = order.final_amount if order.order_type == "预售" else order.total_amount
            self._distribute_pending_asset(order, -pending_to_rollback)
                
        self.db.delete(order)
        self.db.flush()
        
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return f"订单 {order.order_no} 已删除，相关资金流水与资产已回滚！"

    def update_order_info(self, order_id, updates):
        order = self.get_order_by_id(order_id)
        if not order: raise ValueError("订单不存在")
        
        has_change = False
        if "discount_note" in updates:
            order.discount_note = updates["discount_note"]
            has_change = True
        if "notes" in updates:
            order.notes = updates["notes"]
            has_change = True
            
        if has_change:
            self.db.commit()
            return True
        return False

    # ================= 预售专用：解绑/撤销尾款 =================
    def unbind_presale_final(self, order_id):
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order or order.order_type != "预售": raise ValueError("该订单不是预售订单")
        if not order.final_order_no: raise ValueError("尚未绑定尾款，无需解绑")

        final_order_no = order.final_order_no
        all_bound = self.db.query(SalesOrder).filter(
            SalesOrder.final_order_no == final_order_no,
            SalesOrder.order_type == "预售"
        ).all()
        other_bound = [o for o in all_bound if o.id != order.id]
        total_final_amount = sum(o.final_amount for o in all_bound)

        product_ids_to_sync = set()

        if order.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
            logs = self.db.query(InventoryLog).filter(
                InventoryLog.order_id == order.id,
                InventoryLog.reason == "出库"
            ).all()
            for log in logs:
                product = self.db.query(Product).filter(Product.name == log.product_name).first()
                if product: product_ids_to_sync.add(product.id)
                self.db.delete(log)
                
            if order.status in [OrderStatus.SHIPPED, OrderStatus.AFTER_SALES]:
                self._distribute_pending_asset(order, -order.final_amount)

        if order.status == OrderStatus.COMPLETED:
            finance = self.db.query(FinanceRecord).filter(
                FinanceRecord.order_id == order.id,
                FinanceRecord.category == FinanceCategory.SALES_INCOME,
                FinanceRecord.description.like(f"尾款收款: {final_order_no}%") 
            ).first()
            if finance:
                asset_name = order.target_account_name if order.target_account_name else f"{AssetPrefix.CASH}({order.currency})"
                self._update_asset_by_name(asset_name, -finance.amount, category="asset", currency=order.currency)
                self.db.delete(finance)

        refunds = self.db.query(OrderRefund).filter(OrderRefund.order_id == order.id).all()
        for refund in refunds:
            if refund.cost_item_id:
                cost = self.db.query(CostItem).filter(CostItem.id == refund.cost_item_id).first()
                if cost:
                    product_ids_to_sync.add(cost.product_id)
                    self.db.delete(cost)
            self.db.delete(refund)

        order.final_order_no = None
        order.total_amount = order.deposit_amount 
        order.final_amount = 0.0
        order.status = OrderStatus.PRESALE_PENDING_FINAL
        order.shipped_date = None
        order.completed_date = None

        total_qty = sum(item.quantity for item in order.items)
        if total_qty > 0:
            new_unit_price = order.total_amount / total_qty
            for item in order.items:
                item.unit_price = new_unit_price
                item.subtotal = item.quantity * new_unit_price

        # 如果还有其他订单共享该尾款单，把尾款总额在剩余订单中重新平摊重平衡
        if other_bound:
            total_dep = sum(o.deposit_amount for o in other_bound)
            accumulated = 0.0
            for i, o in enumerate(other_bound):
                if i == len(other_bound) - 1:
                    o.final_amount = round(total_final_amount - accumulated, 2)
                else:
                    if total_dep > 0:
                        o.final_amount = round(total_final_amount * (o.deposit_amount / total_dep), 2)
                    else:
                        o.final_amount = round(total_final_amount / len(other_bound), 2)
                    accumulated += o.final_amount
                
                o.total_amount = round(o.deposit_amount + o.final_amount, 2)
                t_qty = sum(item.quantity for item in o.items)
                if t_qty > 0:
                    u_price = o.total_amount / t_qty
                    for item in o.items:
                        item.unit_price = u_price
                        item.subtotal = item.quantity * u_price

        self.db.flush()

        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync:
            inv_service.sync_product_metrics(pid)

        self.db.commit()
        return f"尾款已成功剥离解绑！订单 {order.order_no} 已恢复至【待付尾款】状态，库存与资金已安全回滚。"

    # ================= 预售专用：拆分定金订单 (支持部分补款) =================
    def split_presale_deposit_order(self, order_id: int, split_items: list[dict]):
        """
        拆分预售定金订单：
        split_items: [{"item_id": int, "split_quantity": int}, ...]
        """
        order = self.db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
        if not order or order.order_type != "预售":
            raise ValueError("该订单不是有效的预售订单")
        if order.status != OrderStatus.PRESALE_PENDING_FINAL:
            raise ValueError(f"仅【待付尾款】状态的定金订单支持拆分，当前状态为【{order.status}】")
        if order.final_order_no:
            raise ValueError(f"该定金订单已绑定尾款单【{order.final_order_no}】，请先解绑尾款后再进行拆分")

        item_map = {item.id: item for item in order.items}
        if not item_map:
            raise ValueError("原订单无商品明细，无法拆分")

        total_original_qty = sum(item.quantity for item in order.items)
        total_split_qty = 0
        items_to_split = []

        for req in split_items:
            item_id = req.get("item_id")
            s_qty = req.get("split_quantity", 0)
            if item_id not in item_map:
                continue
            if not isinstance(s_qty, int) or s_qty < 0:
                raise ValueError("拆出数量必须为大于等于 0 的整数")
            orig_item = item_map[item_id]
            if s_qty > orig_item.quantity:
                raise ValueError(f"商品【{orig_item.product_name}-{orig_item.variant}】拆出数量({s_qty})超出原数量({orig_item.quantity})")
            if s_qty > 0:
                total_split_qty += s_qty
                items_to_split.append((orig_item, s_qty))

        if total_split_qty <= 0:
            raise ValueError("请至少选择并输入 1 件商品的拆出数量")
        if total_split_qty >= total_original_qty:
            raise ValueError("拆出商品总数不能等于或超过订单全部商品数，原订单必须保留至少 1 件商品")

        # 1. 精确计算拆出的定金金额
        # 按各商品项原有的定金小计比例切分
        split_deposit_amount = 0.0
        for orig_item, s_qty in items_to_split:
            item_unit_dep = orig_item.subtotal / orig_item.quantity if orig_item.quantity > 0 else 0.0
            split_deposit_amount += item_unit_dep * s_qty
        split_deposit_amount = round(split_deposit_amount, 2)

        if split_deposit_amount <= 0:
            split_deposit_amount = round(order.deposit_amount * (total_split_qty / total_original_qty), 2)

        remain_deposit_amount = round(order.deposit_amount - split_deposit_amount, 2)
        if remain_deposit_amount < 0:
            remain_deposit_amount = 0.0

        # 2. 生成自动递增的全局唯一定金子单号: {order_no}-{N}
        existing_splits = self.db.query(SalesOrder.order_no).filter(
            SalesOrder.order_no.like(f"{order.order_no}-%")
        ).all()
        max_idx = 0
        import re
        pattern = re.compile(rf"^{re.escape(order.order_no)}-(\d+)$")
        for (ex_no,) in existing_splits:
            m = pattern.match(ex_no)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
        new_order_no = f"{order.order_no}-{max_idx + 1}"

        # 3. 创建新的子定金订单 (绝不创建新的财务流水, 资金零变动)
        new_order = SalesOrder(
            order_no=new_order_no,
            order_type="预售",
            platform=order.platform,
            currency=order.currency,
            status=OrderStatus.PRESALE_PENDING_FINAL,
            created_date=order.created_date,
            deposit_amount=split_deposit_amount,
            final_amount=0.0,
            total_amount=split_deposit_amount,
            target_account_name=order.target_account_name,
            discount_note=order.discount_note,
            notes=f"由订单 {order.order_no} 拆分生成" + (f" ({order.notes})" if order.notes else "")
        )
        self.db.add(new_order)
        self.db.flush()

        # 4. 为新子单填充 items
        new_unit_price = split_deposit_amount / total_split_qty if total_split_qty > 0 else 0.0
        for orig_item, s_qty in items_to_split:
            subtot = round(s_qty * new_unit_price, 2)
            new_item = SalesOrderItem(
                order_id=new_order.id,
                product_name=orig_item.product_name,
                variant=orig_item.variant,
                quantity=s_qty,
                unit_price=new_unit_price,
                subtotal=subtot,
                warehouse_id=orig_item.warehouse_id
            )
            self.db.add(new_item)

        # 5. 更新原定金订单
        order.deposit_amount = remain_deposit_amount
        order.total_amount = remain_deposit_amount
        remain_total_qty = total_original_qty - total_split_qty
        remain_unit_price = remain_deposit_amount / remain_total_qty if remain_total_qty > 0 else 0.0

        for orig_item, s_qty in items_to_split:
            orig_item.quantity -= s_qty
            if orig_item.quantity <= 0:
                self.db.delete(orig_item)
            else:
                orig_item.unit_price = remain_unit_price
                orig_item.subtotal = round(orig_item.quantity * remain_unit_price, 2)

        # 对未被拆分的剩余 items 也同步重算单价小计
        for item in order.items:
            if item not in [x[0] for x in items_to_split]:
                item.unit_price = remain_unit_price
                item.subtotal = round(item.quantity * remain_unit_price, 2)

        self.db.flush()
        self.db.commit()

        return new_order, f"✅ 预售定金订单拆分成功！已生成新子单【{new_order.order_no}】（定金: ¥{new_order.deposit_amount:.2f}，共 {total_split_qty} 件），原单【{order.order_no}】剩余定金: ¥{order.deposit_amount:.2f}（共 {remain_total_qty} 件）。"

    # ================= 6. 批量导入预售扩展 =================
    def validate_and_parse_import_data(self, df, exchange_rate, presale_mode=None):
        required_cols = ['订单号', '商品名', '商品型号', '数量', '销售平台', '订单总额', '币种', '出货仓库']
        
        if presale_mode == "尾款":
            if '关联定金单号' not in df.columns:
                return None, "尾款绑定模式下，Excel 必须包含【关联定金单号】列"
            required_cols.append('关联定金单号')
        elif presale_mode == "定金":
            if '优惠' not in df.columns:
                return None, "批量导入定金单时，Excel 必须包含【优惠】列"
            required_cols.append('优惠')

        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols: return None, [f"缺少必要列: {', '.join(missing_cols)}"]

        df['订单号'] = df['订单号'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        if presale_mode == "尾款":
            df['关联定金单号'] = df['关联定金单号'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

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

        def safe_str(val):
            return "" if pd.isna(val) else str(val).strip()

        for index, row in df.iterrows():
            order_no = row['订单号']
            if not order_no or order_no == 'nan': 
                continue 
            
            if presale_mode == "尾款":
                existing_main = self.db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first()
                if existing_main:
                    errors.append(f"第 {index+2} 行: 该尾款订单号与主订单号 {order_no} 冲突")
                    continue
            else:
                existing = self.db.query(SalesOrder).filter(
                    or_(SalesOrder.order_no == order_no, SalesOrder.final_order_no == order_no)
                ).first()
                if existing:
                    errors.append(f"第 {index+2} 行 - 主订单号已存在: {order_no}")
                    continue
            
            discount_val = safe_str(row.get('优惠', '')) if presale_mode == "定金" else ""
            
            if presale_mode == "尾款":
                ref_deposit_no_raw = safe_str(row['关联定金单号'])
                if not ref_deposit_no_raw:
                    errors.append(f"第 {index+2} 行: 关联定金单号不能为空")
                    continue
                
                import re
                dep_nos = [d.strip() for d in re.split(r'[;；]+', ref_deposit_no_raw) if d.strip()]
                if not dep_nos:
                    errors.append(f"第 {index+2} 行: 未解析出有效的关联定金单号")
                    continue

                matched_deposit_orders = []
                dep_has_err = False
                for d_no in dep_nos:
                    deposit_order = self.db.query(SalesOrder).filter(
                        SalesOrder.order_no == d_no,
                        SalesOrder.order_type == "预售"
                    ).first()
                    if not deposit_order:
                        errors.append(f"第 {index+2} 行: 未找到单号为 {d_no} 的预售定金订单")
                        dep_has_err = True
                        continue
                    if deposit_order.status != OrderStatus.PRESALE_PENDING_FINAL:
                        errors.append(f"第 {index+2} 行: 定金单 {d_no} 状态为【{deposit_order.status}】，不是【待付尾款】，无法绑定")
                        dep_has_err = True
                        continue
                    matched_deposit_orders.append(deposit_order)
                
                if dep_has_err:
                    continue
                
                try: 
                    gross_price = float(row['订单总额'])
                except (ValueError, TypeError):
                    errors.append(f"订单号 {order_no}: 总金额无效")
                    continue
                    
                platform = safe_str(row['销售平台'])
                currency = safe_str(row['币种'])
                fee = 0.0
                shipping_and_other = 0.0
                
                db_plat = self.db.query(SalesPlatform).filter(
                    (SalesPlatform.name == platform) | (SalesPlatform.code == platform.lower())
                ).first()
                
                all_dep_items = []
                for d_ord in matched_deposit_orders:
                    all_dep_items.extend(d_ord.items)

                if db_plat:
                    if db_plat.code == "booth":
                        preset_item_total = 0.0
                        for item in all_dep_items:
                            target_p = self.db.query(Product).filter(Product.name == item.product_name).first()
                            if target_p:
                                target_c = next((c for c in target_p.colors if c.color_name == item.variant), None)
                                if target_c:
                                    target_price = next((pr.price for pr in target_c.prices if pr.platform and pr.platform.lower() == "booth"), 0.0)
                                    preset_item_total += target_price * item.quantity
                        if preset_item_total > 0:
                            shipping_and_other = max(0.0, gross_price - preset_item_total)
                            
                    raw_fee = gross_price * db_plat.fee_rate + db_plat.fee_fixed
                    if db_plat.currency == "JPY" or currency == "JPY":
                        fee = float(math.ceil(raw_fee))
                    else:
                        fee = round(raw_fee, 2)
                else:
                    platform_lower = platform.lower()
                    if "booth" in platform_lower:
                        preset_item_total = 0.0
                        for item in all_dep_items:
                            target_p = self.db.query(Product).filter(Product.name == item.product_name).first()
                            if target_p:
                                target_c = next((c for c in target_p.colors if c.color_name == item.variant), None)
                                if target_c:
                                    target_price = next((pr.price for pr in target_c.prices if pr.platform and pr.platform.lower() == "booth"), 0.0)
                                    preset_item_total += target_price * item.quantity
                        if preset_item_total > 0:
                            shipping_and_other = max(0.0, gross_price - preset_item_total)
                        base_fixed_fee = 45 if currency == "JPY" else 2.16
                        raw_fee = gross_price * 0.056 + base_fixed_fee
                        if currency == "JPY":
                            fee = float(math.ceil(raw_fee))
                        else:
                            fee = round(raw_fee, 2)
                    elif "微店" in platform_lower:
                        fee = round(gross_price * 0.006, 2)

                net_price = gross_price - fee - shipping_and_other
                
                if net_price <= 0:
                    errors.append(f"订单号 {order_no}: 扣除手续费后的净金额({net_price:.2f}) 小于等于 0")
                    continue
                
                if db_plat:
                    if db_plat.code == "weidian": target_acc = "流动资金-微店账户"
                    elif db_plat.code == "booth": target_acc = "流动资金-booth账户"
                    else:
                        if db_plat.currency == "JPY": target_acc = "流动资金-日元临时账户"
                        else: target_acc = f"流动资金-{db_plat.currency}账户"
                else:
                    if "微店" in platform.lower(): target_acc = "流动资金-微店账户"
                    elif "booth" in platform.lower(): target_acc = "流动资金-booth账户"
                    elif currency == "JPY": target_acc = "流动资金-日元临时账户"
                    else: target_acc = "流动资金-支付宝账户"
                
                fake_items = [{"product_name": i.product_name, "variant": i.variant, "quantity": i.quantity, "warehouse_id": i.warehouse_id} for i in all_dep_items]

                parsed_orders.append({
                    "order_no": order_no, "platform": platform, "currency": currency,
                    "gross_price": gross_price, "fee": fee, "net_price": net_price,
                    "total_qty": sum(i.quantity for i in all_dep_items), "items": fake_items,
                    "target_account": target_acc,
                    "matched_deposit_id": matched_deposit_orders[0].id,
                    "matched_deposit_ids": [d.id for d in matched_deposit_orders],
                    "discount_note": discount_val 
                })
                continue 
            
            platform = safe_str(row['销售平台'])
            currency = safe_str(row['币种'])
            p_name = safe_str(row['商品名'])
            
            try: 
                gross_price = float(row['订单总额'])
            except (ValueError, TypeError):
                errors.append(f"订单号 {order_no}: 总金额无效")
                continue

            var_str = safe_str(row['商品型号']).replace('；', ';')
            qty_str = safe_str(row['数量']).replace('；', ';')
            wh_name_str = safe_str(row.get('出货仓库', '')).replace('；', ';')
            
            if not wh_name_str: 
                errors.append(f"订单号 {order_no}: 出货仓库不能为空，请填写有效的仓库名称！")
                continue

            variants = [v.strip() for v in var_str.split(';') if v.strip()]
            qtys_str = [q.strip() for q in qty_str.split(';') if q.strip()]
            wh_names = [w.strip() for w in wh_name_str.split(';') if w.strip()]

            if len(variants) != len(qtys_str):
                errors.append(f"订单号 {order_no}: 商品型号数量 ({len(variants)}) 与 数量个数 ({len(qtys_str)}) 不一致！")
                continue
            
            if len(variants) == 0:
                errors.append(f"订单号 {order_no}: 未读取到商品型号")
                continue
                
            if len(wh_names) == 1 and len(variants) > 1:
                wh_names = wh_names * len(variants)
            elif len(wh_names) != len(variants):
                errors.append(f"订单号 {order_no}: 填写的出货仓库数量 ({len(wh_names)}) 与 型号数量 ({len(variants)}) 不一致！")
                continue

            items_data = []
            order_stock_issues = []
            is_order_out_of_stock = False
            total_qty = 0
            
            for v_name, q_str, wh_name in zip(variants, qtys_str, wh_names):
                try: 
                    qty = int(float(q_str))
                    if qty <= 0: raise ValueError
                except ValueError:
                    errors.append(f"订单号 {order_no}: 数量必须为大于0的整数: {q_str}")
                    continue
                
                total_qty += qty
                wh_id = warehouse_map.get(wh_name)
                if not wh_id:
                    errors.append(f"订单号 {order_no}: 仓库不存在: {wh_name}")
                    continue

                if p_name not in valid_products:
                    errors.append(f"订单号 {order_no}: 商品不存在: {p_name}")
                    continue
                    
                if v_name not in valid_products[p_name]:
                    errors.append(f"订单号 {order_no}: 商品 {p_name} 不存在型号: {v_name}")
                    continue

                if presale_mode != "定金":
                    stock_key = (p_name, v_name, wh_id)
                    cur_avail = consumed_stock_in_excel.get(stock_key)
                    if cur_avail is None:
                        stock_q = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                            InventoryLog.product_name == p_name,
                            InventoryLog.variant == v_name,
                            InventoryLog.warehouse_id == wh_id,
                            InventoryLog.reason.in_(valid_reasons)
                        )
                        cur_avail = stock_q.scalar() or 0
                    
                    if cur_avail < qty:
                        is_order_out_of_stock = True
                        order_stock_issues.append(f"【{p_name}-{v_name}】在【{wh_name}】缺货 (需 {qty}, 仅剩 {cur_avail})")
                    
                    consumed_stock_in_excel[stock_key] = cur_avail - qty

                items_data.append({
                    "product_name": p_name,
                    "variant": v_name,
                    "quantity": qty,
                    "warehouse_id": wh_id,
                    "warehouse_name": wh_name
                })
                
            if len(items_data) != len(variants):
                continue
                
            order_stock_warning_msg = " | ".join(order_stock_issues) if order_stock_issues else ""

            db_plat = self.db.query(SalesPlatform).filter(
                (SalesPlatform.name == platform) | (SalesPlatform.code == platform.lower())
            ).first()

            fee = 0.0
            shipping_and_other = 0.0

            if db_plat:
                if db_plat.code == "booth":
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
                        


            db_plat = self.db.query(SalesPlatform).filter(
                (SalesPlatform.name == platform) | (SalesPlatform.code == platform.lower())
            ).first()

            fee = 0.0
            shipping_and_other = 0.0

            if db_plat:
                if db_plat.code == "booth":
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
                        
                raw_fee = gross_price * db_plat.fee_rate + db_plat.fee_fixed
                if db_plat.currency == "JPY" or currency == "JPY":
                    fee = float(math.ceil(raw_fee))
                else:
                    fee = round(raw_fee, 2)
            else:
                platform_lower = platform.lower()
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
                    base_fixed_fee = 45 if currency == "JPY" else 2.16
                    raw_fee = gross_price * 0.056 + base_fixed_fee
                    if currency == "JPY":
                        fee = float(math.ceil(raw_fee))
                    else:
                        fee = round(raw_fee, 2)
                elif "微店" in platform_lower:
                    fee = round(gross_price * 0.006, 2)

            net_price = gross_price - fee - shipping_and_other
            
            if net_price <= 0:
                errors.append(f"订单号 {order_no}: 扣除手续费后的净金额({net_price:.2f}) 小于等于 0")
                continue
                
            final_unit_price = net_price / total_qty
            for item in items_data:
                item["unit_price"] = final_unit_price
                item["subtotal"] = item["quantity"] * final_unit_price
                
            if db_plat:
                if db_plat.code == "weidian": target_acc = "流动资金-微店账户"
                elif db_plat.code == "booth": target_acc = "流动资金-booth账户"
                else:
                    if db_plat.currency == "JPY": target_acc = "流动资金-日元临时账户"
                    else: target_acc = f"流动资金-{db_plat.currency}账户"
            else:
                if "微店" in platform_lower: target_acc = "流动资金-微店账户"
                elif "booth" in platform_lower: target_acc = "流动资金-booth账户"
                elif currency == "JPY": target_acc = "流动资金-日元临时账户"
                else: target_acc = "流动资金-支付宝账户"

            parsed_orders.append({
                "order_no": order_no, "platform": platform, "currency": currency,
                "gross_price": gross_price, "fee": fee, "net_price": net_price,
                "total_qty": total_qty, "items": items_data,
                "target_account": target_acc,
                "matched_deposit_id": None,
                "discount_note": discount_val,
                "is_out_of_stock": is_order_out_of_stock,
                "stock_warning": order_stock_warning_msg if is_order_out_of_stock else "🟢 充足"
            })

        return parsed_orders, errors

    def batch_create_orders(self, parsed_orders, presale_mode=None):
        created_count = 0
        for data in parsed_orders:
            if presale_mode == "定金":
                order, err = self.create_presale_deposit_order(
                    items_data=data["items"], platform=data["platform"], currency=data["currency"], 
                    notes="批量导入定金单", order_no=data["order_no"], target_account_name=data["target_account"],
                    discount_note=data.get("discount_note", "")
                )
                if not err: created_count += 1
            elif presale_mode == "尾款":
                try:
                    target_dep_ids = data.get("matched_deposit_ids") or ([data["matched_deposit_id"]] if data.get("matched_deposit_id") else [])
                    if target_dep_ids:
                        self.bind_presale_final_order(target_dep_ids, data["order_no"], data["net_price"], new_notes="批量绑定尾款")
                        created_count += len(target_dep_ids)
                except Exception as e:
                    print(f"Error binding final in batch: {e}")
            else:
                order, err = self.create_order(
                    items_data=data["items"], platform=data["platform"], currency=data["currency"], 
                    notes="Excel批量导入", order_no=data["order_no"], target_account_name=data["target_account"]
                )
                if not err: created_count += 1
        return created_count

    def commit(self):
        self.db.commit()
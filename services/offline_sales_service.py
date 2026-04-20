# services/offline_sales_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from datetime import datetime
from models import (
    OfflineTemplate, OfflineTemplateItem, SalesOrder, SalesOrderItem, 
    InventoryLog, FinanceRecord, CompanyBalanceItem, Product, Warehouse
)
from constants import OrderStatus, FinanceCategory

class OfflineSalesService:
    def __init__(self, db: Session):
        self.db = db

    def _validate_template_stock(self, warehouse_id, items_data):
        """核心校验引擎：检查分配的数量是否超过指定仓库的物理库存"""
        valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]
        for item in items_data:
            qty = item['quantity']
            if qty > 0:
                stock_query = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                    InventoryLog.product_name == item['product_name'],
                    InventoryLog.variant == item['variant'],
                    InventoryLog.reason.in_(valid_reasons)
                )
                if warehouse_id is not None:
                    stock_query = stock_query.filter(InventoryLog.warehouse_id == warehouse_id)
                else:
                    stock_query = stock_query.filter(InventoryLog.warehouse_id == None)
                    
                current_stock = stock_query.scalar() or 0
                if qty > current_stock:
                    wh_name = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first().name if warehouse_id else "未分配仓库"
                    raise ValueError(f"库存不足：【{item['product_name']}-{item['variant']}】在【{wh_name}】仅有 {current_stock} 件，无法分配 {qty} 件！")

    def get_all_templates(self):
        return self.db.query(OfflineTemplate).options(
            joinedload(OfflineTemplate.items),
            joinedload(OfflineTemplate.warehouse)
        ).all()

    def create_template(self, name, code, currency, warehouse_id, platform, items_data):
        if self.db.query(OfflineTemplate).filter(or_(OfflineTemplate.code == code, OfflineTemplate.name == name)).first():
            raise ValueError(f"模板名称 '{name}' 或代号 '{code}' 已存在！")
            
        # 写入前拦截校验库存
        self._validate_template_stock(warehouse_id, items_data)
            
        new_template = OfflineTemplate(
            name=name, code=code, currency=currency, 
            warehouse_id=warehouse_id, platform=platform
        )
        self.db.add(new_template)
        self.db.flush()

        for item in items_data:
            self.db.add(OfflineTemplateItem(
                template_id=new_template.id,
                product_name=item['product_name'],
                variant=item['variant'],
                preset_price=item['preset_price'],
                quantity=item['quantity'],
                remaining_quantity=item['quantity'] # 初始剩余等于分配
            ))
        self.db.commit()

    def update_template(self, template_id, name, code, currency, warehouse_id, platform, items_data):
        exist = self.db.query(OfflineTemplate).filter(
            or_(OfflineTemplate.code == code, OfflineTemplate.name == name),
            OfflineTemplate.id != template_id
        ).first()
        if exist: raise ValueError("名称或代号重复！")

        tpl = self.db.query(OfflineTemplate).filter(OfflineTemplate.id == template_id).first()
        if not tpl: raise ValueError("模板不存在")
        
        # 写入前拦截校验库存
        self._validate_template_stock(warehouse_id, items_data)
        
        tpl.name = name
        tpl.code = code
        tpl.currency = currency
        tpl.warehouse_id = warehouse_id
        tpl.platform = platform
        
        # 重新同步项目
        self.db.query(OfflineTemplateItem).filter(OfflineTemplateItem.template_id == template_id).delete()
        for item in items_data:
            self.db.add(OfflineTemplateItem(
                template_id=tpl.id,
                product_name=item['product_name'],
                variant=item['variant'],
                preset_price=item['preset_price'],
                quantity=item['quantity'],
                remaining_quantity=item['quantity']
            ))
        self.db.commit()

    def delete_template(self, template_id):
        tpl = self.db.query(OfflineTemplate).filter(OfflineTemplate.id == template_id).first()
        if tpl:
            self.db.delete(tpl)
            self.db.commit()

    def get_orders_by_template(self, template_code):
        return self.db.query(SalesOrder).options(joinedload(SalesOrder.items)).filter(
            SalesOrder.order_no.like(f"{template_code}-%")
        ).order_by(SalesOrder.id.desc()).all()

    def checkout_offline_order(self, template_id, cart_items, payment_method, fee_rate, account_id):
        """
        线下结账：扣减模板分配额 -> 校验并扣减真实仓库库存 -> 生成已完成订单
        """
        if not cart_items: raise ValueError("购物车为空")

        tpl = self.db.query(OfflineTemplate).filter(OfflineTemplate.id == template_id).first()
        if not tpl: raise ValueError("模板失效")

        now = datetime.now()
        order_no = f"{tpl.code}-{now.strftime('%Y%m%d%H%M%S')}"
        total_amount = 0.0
        product_ids_to_sync = set()

        # 1. 预校验：模板额度与物理库存
        for item in cart_items:
            # 校验模板内分配的额度
            tpl_item = self.db.query(OfflineTemplateItem).filter(
                OfflineTemplateItem.template_id == template_id,
                OfflineTemplateItem.product_name == item["product_name"],
                OfflineTemplateItem.variant == item["variant"]
            ).with_for_update().first()
            
            if not tpl_item or tpl_item.remaining_quantity < item["qty"]:
                raise ValueError(f"模板额度不足：{item['product_name']} 剩余 {tpl_item.remaining_quantity if tpl_item else 0}")

            # 校验物理仓库库存
            valid_reasons = ["入库", "出库", "退货入库", "发货撤销", "验收完成入库", "其他入库", "库存移动"]
            stock_query = self.db.query(func.sum(InventoryLog.change_amount)).filter(
                InventoryLog.product_name == item["product_name"],
                InventoryLog.variant == item["variant"],
                InventoryLog.reason.in_(valid_reasons)
            )
            if tpl.warehouse_id:
                stock_query = stock_query.filter(InventoryLog.warehouse_id == tpl.warehouse_id)
            else:
                stock_query = stock_query.filter(InventoryLog.warehouse_id == None)
                
            if (stock_query.scalar() or 0) < item["qty"]:
                raise ValueError(f"仓库实物不足：{item['product_name']} 在选定仓库中已售罄")

            total_amount += item["qty"] * item["unit_price"]

        # 2. 财务计算
        fee = total_amount * fee_rate if payment_method == "PayPay" else 0.0
        net_amount = total_amount - fee
        target_acc = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == account_id).first()

        # 3. 创建订单
        order = SalesOrder(
            order_no=order_no, 
            status=OrderStatus.COMPLETED, 
            total_amount=total_amount,
            
            order_type="线下", 
            
            currency=tpl.currency, 
            platform=tpl.platform, 
            target_account_name=target_acc.name,
            created_date=now.date(), 
            shipped_date=now.date(), 
            completed_date=now.date(),
            notes=f"POS结账: {payment_method}" + (f" (扣除手续费 {fee:.2f})" if fee > 0 else "")
        )
        self.db.add(order)
        self.db.flush()

        # 4. 执行扣减
        for item in cart_items:
            # 扣减模板额度
            tpl_item = self.db.query(OfflineTemplateItem).filter(
                OfflineTemplateItem.template_id == template_id,
                OfflineTemplateItem.product_name == item["product_name"],
                OfflineTemplateItem.variant == item["variant"]
            ).first()
            tpl_item.remaining_quantity -= item["qty"]

            subtotal = item["qty"] * item["unit_price"]
            # 记录订单明细（绑定出货仓库）
            self.db.add(SalesOrderItem(
                order_id=order.id, product_name=item["product_name"], variant=item["variant"],
                quantity=item["qty"], unit_price=item["unit_price"], subtotal=subtotal,
                warehouse_id=tpl.warehouse_id
            ))
            # 记录物理出库
            self.db.add(InventoryLog(
                product_name=item["product_name"], variant=item["variant"], change_amount=-item["qty"],
                reason="出库", date=now.date(), note=f"线下订单: {order.order_no}",
                is_sold=True, sale_amount=subtotal, currency=tpl.currency, platform=tpl.platform,
                order_id=order.id, warehouse_id=tpl.warehouse_id
            ))
            p = self.db.query(Product).filter(Product.name == item["product_name"]).first()
            if p: product_ids_to_sync.add(p.id)

        # 5. 财务入账
        self.db.add(FinanceRecord(
            date=now.date(), amount=net_amount, currency=tpl.currency,
            category=FinanceCategory.SALES_INCOME, description=f"POS销售: {order.order_no} ({tpl.platform})",
            order_id=order.id, account_id=target_acc.id
        ))
        target_acc.amount += net_amount

        self.db.flush()
        from services.inventory_service import InventoryService
        inv_service = InventoryService(self.db)
        for pid in product_ids_to_sync: inv_service.sync_product_metrics(pid)

        self.db.commit()
        return order.order_no, net_amount
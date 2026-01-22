from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import date
from models import Product, CostItem, FinanceRecord, CompanyBalanceItem, InventoryLog
from constants import PRODUCT_COST_CATEGORIES, AssetPrefix, BalanceCategory, Currency

class CostService:
    def __init__(self, db: Session):
        self.db = db
        # 定义预算/支出的分类
        self.DETAILED_CATS = PRODUCT_COST_CATEGORIES[:4]  # ["大货材料费", "大货加工费", "物流邮费", "包装费"]
        self.SIMPLE_CATS = PRODUCT_COST_CATEGORIES[4:]  # ["设计开发费", "检品发货等人工费", "宣发费", "其他成本"]
        self.ALL_CATS = PRODUCT_COST_CATEGORIES

    # ================= 1. 获取数据 =================
    def get_all_products(self):
        """获取所有产品"""
        return self.db.query(Product).all()

    def get_product_by_name(self, name):
        """按名称获取产品"""
        return self.db.query(Product)\
            .options(joinedload(Product.prices))\
            .filter(Product.name == name).first()

    def get_cost_items(self, product_id):
        """获取某产品的所有成本项"""
        return self.db.query(CostItem).filter(CostItem.product_id == product_id).all()

    def get_wip_offset(self, product_id):
        """获取产品的在制资产冲销额"""
        prod = self.db.query(Product).filter(Product.id == product_id).first()
        if not prod: return 0.0
        offset_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == f"{AssetPrefix.WIP_OFFSET}{prod.name}").first()
        return offset_item.amount if offset_item else 0.0

    # ================= 2. 预算管理 =================
    def add_budget_item(self, product_id, category, name, unit_price, quantity, unit, remarks):
        """添加预算项"""
        new_cost = CostItem(
            product_id=product_id,
            item_name=name,
            actual_cost=0,      
            supplier="预算设定", 
            category=category,
            unit_price=unit_price, 
            quantity=quantity,          
            unit=unit,
            remarks=remarks
        )
        self.db.add(new_cost)
        self.db.commit()
        return new_cost

    def update_cost_item(self, item_id, updates):
        """
        更新成本项 (支持预算和实付的混合更新)
        updates: 字典，包含需要更新的字段
        """
        target_item = self.db.query(CostItem).filter(CostItem.id == item_id).first()
        if not target_item:
            return False
        
        has_change = False
        
        # 通用字段
        if "unit" in updates and updates["unit"] != (target_item.unit or ""):
            target_item.unit = updates["unit"]
            has_change = True
        if "supplier" in updates and updates["supplier"] != (target_item.supplier or ""):
            target_item.supplier = updates["supplier"]
            has_change = True
        if "remarks" in updates and updates["remarks"] != (target_item.remarks or ""):
            target_item.remarks = updates["remarks"]
            has_change = True
            
        # 预算/数值逻辑
        if updates.get("is_budget", False):
            # 详细模式更新
            if "quantity" in updates:
                new_q = float(updates["quantity"])
                if abs(new_q - target_item.quantity) > 0.001:
                    target_item.quantity = new_q
                    has_change = True
            
            if "unit_price" in updates:
                new_p = float(updates["unit_price"])
                if abs(new_p - target_item.unit_price) > 0.01:
                    target_item.unit_price = new_p
                    has_change = True
            
            # 简易模式更新 (反算单价)
            if "total_budget" in updates:
                new_total = float(updates["total_budget"])
                current_total = target_item.unit_price * target_item.quantity
                if abs(new_total - current_total) > 0.01:
                    target_item.unit_price = new_total
                    target_item.quantity = 1.0
                    has_change = True

        if has_change:
            self.db.commit()
        return has_change

    def delete_cost_item(self, item_id):
        """删除成本项，并执行资金回滚"""
        item_to_del = self.db.query(CostItem).filter(CostItem.id == item_id).first()
        if not item_to_del:
            raise ValueError("项目不存在")

        # 如果关联了财务流水，执行资金回滚
        if item_to_del.finance_record_id:
            fin_rec = self.db.query(FinanceRecord).filter(FinanceRecord.id == item_to_del.finance_record_id).first()
            if fin_rec:
                # 1. 恢复资金 (回滚流动资金)
                # 支出在 FinanceRecord 中是负数，取绝对值加回
                restore_amount = abs(fin_rec.amount) 
                restore_currency = fin_rec.currency
                
                cash_asset = self.db.query(CompanyBalanceItem).filter(
                    CompanyBalanceItem.name.like(f"{AssetPrefix.CASH}%"),
                    CompanyBalanceItem.currency == restore_currency,
                    CompanyBalanceItem.category == BalanceCategory.ASSET
                ).first()
                
                if cash_asset:
                    cash_asset.amount += restore_amount
                
                # 2. 标记流水为已冲销
                fin_rec.amount = 0
                fin_rec.category = "取消/冲销"
                fin_rec.description = f"【已取消成本】{fin_rec.description}"
        
        self.db.delete(item_to_del)
        self.db.commit()

    # ================= 3. 高级功能: 强制结单 (WIP Fix) =================
    def perform_wip_fix(self, product_id):
        """
        强制结单/账目修正：
        计算 (总实付成本 - 已冲销额)，将剩余差额转入大货资产，并清零预入库资产。
        """
        prod = self.db.query(Product).filter(Product.id == product_id).first()
        if not prod: raise ValueError("产品不存在")

        # 1. 计算总实付成本
        all_items = self.db.query(CostItem).filter(CostItem.product_id == prod.id).all()
        current_total_cost = sum([i.actual_cost for i in all_items])
        
        # 2. 获取当前的冲销额
        offset_name = f"{AssetPrefix.WIP_OFFSET}{prod.name}"
        offset_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == offset_name).first()
        current_offset = offset_item.amount if offset_item else 0.0
        
        # 3. 计算追加的成本差额 (Old Accounted Cost 是负数，取绝对值)
        old_accounted_cost = abs(current_offset)
        added_cost_value = current_total_cost - old_accounted_cost

        # 4. 自动更新“大货资产”并记录流水
        if abs(added_cost_value) > 0.01:
            inventory_asset_name = f"{AssetPrefix.STOCK}{prod.name}"
            inv_item = self.db.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.name == inventory_asset_name,
                CompanyBalanceItem.category == BalanceCategory.ASSET
            ).first()

            if inv_item:
                inv_item.amount += added_cost_value
            else:
                new_inv = CompanyBalanceItem(
                    name=inventory_asset_name,
                    amount=added_cost_value,
                    category=BalanceCategory.ASSET,
                    currency=Currency.CNY
                )
                self.db.add(new_inv)
            
            # 记录虚拟流水
            fix_rec = FinanceRecord(
                date=date.today(),
                amount=0,
                currency=Currency.CNY,
                category="成本结转",
                description=f"【{prod.name}】追加成本结转: 将 {added_cost_value:.2f} 从在制转入大货资产"
            )
            self.db.add(fix_rec)

        # 5. 更新冲销项 (让 WIP 归零)
        target_offset = -current_total_cost
        if not offset_item:
            self.db.add(CompanyBalanceItem(
                name=offset_name, amount=target_offset, category="asset", currency="CNY" 
            ))
        else:
            offset_item.amount = target_offset
        
        # 6. 清理残留预入库资产
        pre_stock_name = f"{AssetPrefix.PRE_STOCK}{prod.name}"
        self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == pre_stock_name).delete()
        
        self.db.commit()
        return added_cost_value, current_total_cost + current_offset

    # ================= 4. 高级功能: 库存重估 (Revaluation) =================
    def calculate_revaluation_data(self, product_id):
        """计算重估所需的：实际库存、账面价值、目标价值、单价"""
        prod = self.db.query(Product).filter(Product.id == product_id).first()
        if not prod: return None

        # A. 计算单价
        all_items = self.db.query(CostItem).filter(CostItem.product_id == prod.id).all()
        total_real_cost = sum([i.actual_cost for i in all_items])
        make_qty = prod.marketable_quantity if prod.marketable_quantity is not None else prod.total_quantity
        unit_cost = total_real_cost / make_qty if make_qty > 0 else 0

        # B. 计算实际库存
        current_stock_qty = 0
        stock_logs = self.db.query(InventoryLog).filter(InventoryLog.product_name == prod.name).all()
        real_stock_reasons = ["入库", "出库", "额外生产入库", "退货入库", "发货撤销"]
        for l in stock_logs:
            if l.reason in real_stock_reasons:
                current_stock_qty += l.change_amount
        
        # C. 获取账面价值
        inventory_asset_name = f"大货资产-{prod.name}"
        inv_item = self.db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.name == inventory_asset_name,
            CompanyBalanceItem.category == "asset"
        ).first()
        current_inv_val = inv_item.amount if inv_item else 0.0

        # D. 计算目标值
        target_inv_val = current_stock_qty * unit_cost
        diff = target_inv_val - current_inv_val

        return {
            "current_stock_qty": current_stock_qty,
            "current_inv_val": current_inv_val,
            "target_inv_val": target_inv_val,
            "unit_cost": unit_cost,
            "diff": diff,
            "product_name": prod.name
        }

    def perform_inventory_revaluation(self, product_id):
        """执行重估补差"""
        data = self.calculate_revaluation_data(product_id)
        if not data: raise ValueError("无法计算数据")
        
        diff = data["diff"]
        p_name = data["product_name"]
        
        if abs(diff) > 0.01:
            inventory_asset_name = f"大货资产-{p_name}"
            inv_item = self.db.query(CompanyBalanceItem).filter(
                CompanyBalanceItem.name == inventory_asset_name,
                CompanyBalanceItem.category == BalanceCategory.ASSET
            ).first()

            if inv_item:
                inv_item.amount += diff
            else:
                self.db.add(CompanyBalanceItem(
                    name=inventory_asset_name, amount=diff, category=BalanceCategory.ASSET, currency=Currency.CNY
                ))
            
            # 记录虚拟流水
            self.db.add(FinanceRecord(
                date=date.today(),
                amount=0,
                currency=Currency.CNY,
                category="库存重估",
                description=f"【{p_name}】资产重估补差: 从 {data['current_inv_val']:.2f} 调整为 {data['target_inv_val']:.2f} (差额 {diff:.2f})"
            ))
            self.db.commit()

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import date
from models import Product, CostItem, FinanceRecord, CompanyBalanceItem, InventoryLog, ProductColor
from constants import PRODUCT_COST_CATEGORIES, AssetPrefix, BalanceCategory, Currency

class CostService:
    def __init__(self, db: Session):
        self.db = db
        self.DETAILED_CATS = PRODUCT_COST_CATEGORIES[:4]  
        self.SIMPLE_CATS = PRODUCT_COST_CATEGORIES[4:]  
        self.ALL_CATS = PRODUCT_COST_CATEGORIES

    # ================= 1. 获取数据 =================
    def get_all_products(self):
        return self.db.query(Product).all()

    def get_product_by_name(self, name):
        return self.db.query(Product)\
            .options(joinedload(Product.colors).joinedload(ProductColor.prices))\
            .filter(Product.name == name).first()

    def get_cost_items(self, product_id):
        return self.db.query(CostItem).filter(CostItem.product_id == product_id).all()

    def get_wip_offset(self, product_id):
        prod = self.db.query(Product).filter(Product.id == product_id).first()
        if not prod: return 0.0
        offset_item = self.db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == f"{AssetPrefix.WIP_OFFSET}{prod.name}").first()
        return offset_item.amount if offset_item else 0.0

    # ================= 2. 预算管理 =================
    def add_budget_item(self, product_id, category, name, unit_price, quantity, unit, remarks):
        new_cost = CostItem(
            product_id=product_id, item_name=name, actual_cost=0, supplier="预算设定", 
            category=category, unit_price=unit_price, quantity=quantity, unit=unit, remarks=remarks
        )
        self.db.add(new_cost)
        self.db.commit()
        
        # 触发底层同步刷新
        from services.inventory_service import InventoryService
        InventoryService(self.db).sync_product_metrics(product_id)
        
        return new_cost

    def update_cost_item(self, item_id, updates):
        target_item = self.db.query(CostItem).filter(CostItem.id == item_id).first()
        if not target_item:
            return False
        
        has_change = False
        if "unit" in updates and updates["unit"] != (target_item.unit or ""):
            target_item.unit = updates["unit"]
            has_change = True
        if "supplier" in updates and updates["supplier"] != (target_item.supplier or ""):
            target_item.supplier = updates["supplier"]
            has_change = True
        if "remarks" in updates and updates["remarks"] != (target_item.remarks or ""):
            target_item.remarks = updates["remarks"]
            has_change = True
        if "url" in updates and updates["url"] != (target_item.url or ""):
            target_item.url = updates["url"]
            has_change = True
            
        if updates.get("is_budget", False):
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
            
            if "total_budget" in updates:
                new_total = float(updates["total_budget"])
                current_total = target_item.unit_price * target_item.quantity
                if abs(new_total - current_total) > 0.01:
                    target_item.unit_price = new_total
                    target_item.quantity = 1.0
                    has_change = True

        if has_change:
            self.db.commit()
            from services.inventory_service import InventoryService
            InventoryService(self.db).sync_product_metrics(target_item.product_id)
            
        return has_change

    def delete_cost_item(self, item_id):
        item_to_del = self.db.query(CostItem).filter(CostItem.id == item_id).first()
        if not item_to_del:
            raise ValueError("项目不存在")

        product_id = item_to_del.product_id

        if item_to_del.finance_record_id:
            fin_rec = self.db.query(FinanceRecord).filter(FinanceRecord.id == item_to_del.finance_record_id).first()
            if fin_rec:
                restore_amount = abs(fin_rec.amount) 
                restore_currency = fin_rec.currency
                
                cash_asset = self.db.query(CompanyBalanceItem).filter(
                    CompanyBalanceItem.name.like(f"{AssetPrefix.CASH}%"),
                    CompanyBalanceItem.currency == restore_currency,
                    CompanyBalanceItem.category == BalanceCategory.ASSET
                ).first()
                
                if cash_asset:
                    cash_asset.amount += restore_amount
                
                fin_rec.amount = 0
                fin_rec.category = "取消/冲销"
                fin_rec.description = f"【已取消成本】{fin_rec.description}"
        
        self.db.delete(item_to_del)
        self.db.commit()
        
        from services.inventory_service import InventoryService
        InventoryService(self.db).sync_product_metrics(product_id)

    # ================= 3. 生产完成 (WIP 处理) =================
    def perform_wip_fix(self, product_id):
        """
        标记生产完成：修改标志位，并交给引擎去完全清零在制资产。
        """
        prod = self.db.query(Product).filter(Product.id == product_id).first()
        if not prod: raise ValueError("产品不存在")

        prod.is_production_completed = True
        self.db.commit()
        
        # 触发底层同步刷新
        from services.inventory_service import InventoryService
        InventoryService(self.db).sync_product_metrics(prod.id)
        
        return 0, 0
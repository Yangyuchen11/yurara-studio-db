# services/balance_service.py
from sqlalchemy import func
from models import CompanyBalanceItem, FixedAsset, ConsumableItem, FinanceRecord, Product, CostItem
from constants import AssetPrefix, BalanceCategory, Currency

class BalanceService:
    """
    负责公司账面/资产负债表的后端计算逻辑
    """
    
    @staticmethod
    def add_cash_account(db, name, currency):
        """新增自定义现金账户"""
        full_name = f"{AssetPrefix.CASH}-{name}"
        existing = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.name == full_name).first()
        if existing:
            raise ValueError(f"账户 {full_name} 已存在")
            
        new_account = CompanyBalanceItem(
            category=BalanceCategory.ASSET,
            name=full_name,
            amount=0.0,
            currency=currency,
            asset_type="现金"
        )
        db.add(new_account)
        db.commit()
        return new_account

    @staticmethod
    def get_financial_summary(db):
        all_balance_items = db.query(CompanyBalanceItem).all()
        fixed_assets = db.query(FixedAsset).all()
        consumables = db.query(ConsumableItem).all()

        # 1. 现金 (Flowing Cash)
        cash_items = [i for i in all_balance_items if getattr(i, 'asset_type', '') == "现金" and i.category == BalanceCategory.ASSET]
        cash_cny = sum(i.amount for i in cash_items if i.currency == Currency.CNY)
        cash_jpy = sum(i.amount for i in cash_items if i.currency == Currency.JPY)

        # 2. 固定资产 
        fixed_cny = sum(fa.unit_price * fa.remaining_qty for fa in fixed_assets if getattr(fa, 'currency', Currency.CNY) != Currency.JPY)
        fixed_jpy = sum(fa.unit_price * fa.remaining_qty for fa in fixed_assets if getattr(fa, 'currency', Currency.CNY) == Currency.JPY)

        # 3. 耗材/其他资产
        cons_cny = sum(c.unit_price * c.remaining_qty for c in consumables if getattr(c, 'currency', Currency.CNY) != Currency.JPY)
        cons_jpy = sum(c.unit_price * c.remaining_qty for c in consumables if getattr(c, 'currency', Currency.CNY) == Currency.JPY)

        # 4. 手动资产、负债、资本分类
        manual_assets = []
        offset_items = []
        liabilities = []
        equities = []

        for i in all_balance_items:
            if i.category == BalanceCategory.LIABILITY:
                liabilities.append(i)
            elif i.category == BalanceCategory.EQUITY:
                equities.append(i)
            elif i.category == BalanceCategory.ASSET:
                # ✨ 这里还是通过前缀判断它是不是属于 WIP，但计算归属时将使用 ID
                if i.name and i.name.startswith(AssetPrefix.WIP_OFFSET):
                    offset_items.append(i)
                elif getattr(i, 'asset_type', '') == "现金" or (i.name and i.name.startswith(AssetPrefix.PRE_STOCK)):
                    continue
                else:
                    manual_assets.append(i)

        # 5. 在制资产 (WIP) 计算
        # ✨ 修改查询：把 Product.id 连同 name 一起查出来，方便后续做 ID 关联
        wip_query = db.query(Product.id, Product.name, func.sum(CostItem.actual_cost)).outerjoin(CostItem, Product.id == CostItem.product_id).group_by(Product.id, Product.name).all()
        
        offset_map = {}
        for off in offset_items:
            # ✨ 优先使用 product_id 进行精确映射，兼容老数据则使用名字截取
            if off.product_id:
                offset_map[off.product_id] = offset_map.get(off.product_id, 0) + off.amount
            else:
                p_name = off.name.replace(AssetPrefix.WIP_OFFSET, "")
                offset_map[p_name] = offset_map.get(p_name, 0) + off.amount

        wip_list = []
        wip_total_cny = 0.0
        
        for p_id, p_name, total_cost in wip_query:
            if not total_cost: total_cost = 0
            
            # ✨ 优先尝试获取根据 ID 分组的 offset，如果没取到再去取名字分组的 (兼容逻辑)
            offset_val = offset_map.get(p_id, offset_map.get(p_name, 0))
            
            net_wip = total_cost + offset_val 
            if net_wip > 1.0:
                wip_list.append((p_name, net_wip))
                wip_total_cny += net_wip

        # --- C. 汇总计算 ---
        manual_cny = sum(i.amount for i in manual_assets if i.currency == Currency.CNY)
        manual_jpy = sum(i.amount for i in manual_assets if i.currency == Currency.JPY)

        pure_asset_cny = fixed_cny + cons_cny + manual_cny + wip_total_cny
        pure_asset_jpy = fixed_jpy + cons_jpy + manual_jpy

        total_asset_cny = cash_cny + pure_asset_cny
        total_asset_jpy = cash_jpy + pure_asset_jpy

        total_liab_cny = sum(i.amount for i in liabilities if i.currency == Currency.CNY)
        total_liab_jpy = sum(i.amount for i in liabilities if i.currency == Currency.JPY)

        total_eq_cny = sum(i.amount for i in equities if i.currency == Currency.CNY)
        total_eq_jpy = sum(i.amount for i in equities if i.currency == Currency.JPY)

        net_cny = total_asset_cny - total_liab_cny
        net_jpy = total_asset_jpy - total_liab_jpy

        return {
            "cash_items": cash_items, 
            "cash": {"CNY": cash_cny, "JPY": cash_jpy},
            "fixed": {"CNY": fixed_cny, "JPY": fixed_jpy},
            "consumable": {"CNY": cons_cny, "JPY": cons_jpy},
            "wip": {"list": wip_list, "total_cny": wip_total_cny},
            "manual_assets": manual_assets,
            "liabilities": liabilities,
            "equities": equities,
            "totals": {
                "pure_asset": {"CNY": pure_asset_cny, "JPY": pure_asset_jpy}, 
                "asset": {"CNY": total_asset_cny, "JPY": total_asset_jpy},     
                "liability": {"CNY": total_liab_cny, "JPY": total_liab_jpy},
                "equity": {"CNY": total_eq_cny, "JPY": total_eq_jpy},
                "net": {"CNY": net_cny, "JPY": net_jpy}
            }
        }
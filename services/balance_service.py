# services/balance_service.py
from sqlalchemy import func
from models import CompanyBalanceItem, FixedAsset, ConsumableItem, FinanceRecord, Product, CostItem
from constants import AssetPrefix, BalanceCategory, Currency

class BalanceService:
    """
    负责公司账面/资产负债表的后端计算逻辑（支持多货币动态列）
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

        # --- 辅助：按货币累加 ---
        def add_to(d, currency, amount):
            curr = currency or Currency.CNY
            d[curr] = d.get(curr, 0.0) + amount

        # 1. 现金 (Flowing Cash)
        cash_items = [i for i in all_balance_items
                      if getattr(i, 'asset_type', '') == "现金" and i.category == BalanceCategory.ASSET]
        cash_by_curr = {}
        for i in cash_items:
            add_to(cash_by_curr, i.currency, i.amount)
        # 确保 CNY 和 JPY 键始终存在（向后兼容）
        cash_by_curr.setdefault(Currency.CNY, 0.0)
        cash_by_curr.setdefault(Currency.JPY, 0.0)

        # 2. 固定资产（按货币分组）
        fixed_by_curr = {}
        for fa in fixed_assets:
            curr = getattr(fa, 'currency', Currency.CNY) or Currency.CNY
            add_to(fixed_by_curr, curr, fa.unit_price * fa.remaining_qty)
        fixed_by_curr.setdefault(Currency.CNY, 0.0)
        fixed_by_curr.setdefault(Currency.JPY, 0.0)

        # 3. 耗材/其他资产
        cons_by_curr = {}
        for c in consumables:
            curr = getattr(c, 'currency', Currency.CNY) or Currency.CNY
            add_to(cons_by_curr, curr, c.unit_price * c.remaining_qty)
        cons_by_curr.setdefault(Currency.CNY, 0.0)
        cons_by_curr.setdefault(Currency.JPY, 0.0)

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
                if i.name and i.name.startswith(AssetPrefix.WIP_OFFSET):
                    offset_items.append(i)
                elif getattr(i, 'asset_type', '') == "现金" or (i.name and i.name.startswith(AssetPrefix.PRE_STOCK)):
                    continue
                else:
                    manual_assets.append(i)

        # 5. 在制资产 (WIP) 计算
        wip_query = db.query(Product.id, Product.name, func.sum(CostItem.actual_cost)).outerjoin(
            CostItem, Product.id == CostItem.product_id
        ).group_by(Product.id, Product.name).all()

        offset_map = {}
        for off in offset_items:
            if off.product_id:
                offset_map[off.product_id] = offset_map.get(off.product_id, 0) + off.amount
            else:
                p_name = off.name.replace(AssetPrefix.WIP_OFFSET, "")
                offset_map[p_name] = offset_map.get(p_name, 0) + off.amount

        wip_list = []
        wip_total_cny = 0.0
        for p_id, p_name, total_cost in wip_query:
            if not total_cost: total_cost = 0
            offset_val = offset_map.get(p_id, offset_map.get(p_name, 0))
            net_wip = total_cost + offset_val
            if net_wip > 1.0:
                wip_list.append((p_name, net_wip))
                wip_total_cny += net_wip

        # 6. 归并旧式 CNY/JPY 汇总（向后兼容 totals 接口）
        manual_cny = sum(i.amount for i in manual_assets if (i.currency or "CNY") == Currency.CNY)
        manual_jpy = sum(i.amount for i in manual_assets if (i.currency or "") == Currency.JPY)

        pure_asset_cny = fixed_by_curr.get(Currency.CNY, 0.0) + cons_by_curr.get(Currency.CNY, 0.0) + manual_cny + wip_total_cny
        pure_asset_jpy = fixed_by_curr.get(Currency.JPY, 0.0) + cons_by_curr.get(Currency.JPY, 0.0) + manual_jpy

        total_asset_cny = cash_by_curr.get(Currency.CNY, 0.0) + pure_asset_cny
        total_asset_jpy = cash_by_curr.get(Currency.JPY, 0.0) + pure_asset_jpy

        total_liab_cny = sum(i.amount for i in liabilities if (i.currency or "CNY") == Currency.CNY)
        total_liab_jpy = sum(i.amount for i in liabilities if (i.currency or "") == Currency.JPY)

        total_eq_cny = sum(i.amount for i in equities if (i.currency or "CNY") == Currency.CNY)
        total_eq_jpy = sum(i.amount for i in equities if (i.currency or "") == Currency.JPY)

        net_cny = total_asset_cny - total_liab_cny
        net_jpy = total_asset_jpy - total_liab_jpy

        return {
            "cash_items": cash_items,
            "cash": cash_by_curr,          # 动态多货币字典
            "fixed": fixed_by_curr,         # 动态多货币字典
            "consumable": cons_by_curr,     # 动态多货币字典
            "wip": {"list": wip_list, "total_cny": wip_total_cny},
            "manual_assets": manual_assets,
            "liabilities": liabilities,
            "equities": equities,
            # 向后兼容：totals 仍保留 CNY/JPY 两键
            "totals": {
                "pure_asset": {"CNY": pure_asset_cny, "JPY": pure_asset_jpy},
                "asset": {"CNY": total_asset_cny, "JPY": total_asset_jpy},
                "liability": {"CNY": total_liab_cny, "JPY": total_liab_jpy},
                "equity": {"CNY": total_eq_cny, "JPY": total_eq_jpy},
                "net": {"CNY": net_cny, "JPY": net_jpy}
            }
        }
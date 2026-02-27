# services/balance_service.py
from sqlalchemy import func
from models import CompanyBalanceItem, FixedAsset, ConsumableItem, FinanceRecord, Product, CostItem
from constants import AssetPrefix, BalanceCategory, Currency

class BalanceService:
    """
    负责公司账面/资产负债表的后端计算逻辑
    """
    @staticmethod
    def get_financial_summary(db):
        """
        核心函数：计算资产负债表所需的所有汇总数据
        返回包含各类资产、负债、资本总额及详细列表的字典
        """
        # --- A. 数据获取 ---
        all_balance_items = db.query(CompanyBalanceItem).all()
        finance_records = db.query(FinanceRecord).all()
        fixed_assets = db.query(FixedAsset).all()
        consumables = db.query(ConsumableItem).all()

        # --- B. 计算各类具体资产 ---
        
        # 1. 现金 (Flowing Cash) - 从流水记录累加
        cash_cny = sum(r.amount for r in finance_records if r.currency == Currency.CNY)
        cash_jpy = sum(r.amount for r in finance_records if r.currency == Currency.JPY)

        # 2. 固定资产 (按币种汇总剩余价值)
        fixed_cny = sum(fa.unit_price * fa.remaining_qty for fa in fixed_assets if getattr(fa, 'currency', Currency.CNY) != Currency.JPY)
        fixed_jpy = sum(fa.unit_price * fa.remaining_qty for fa in fixed_assets if getattr(fa, 'currency', Currency.CNY) == Currency.JPY)

        # 3. 耗材/其他资产
        cons_cny = sum(c.unit_price * c.remaining_qty for c in consumables if getattr(c, 'currency', Currency.CNY) != Currency.JPY)
        cons_jpy = sum(c.unit_price * c.remaining_qty for c in consumables if getattr(c, 'currency', Currency.CNY) == Currency.JPY)

        # 4. 手动资产、负债、资本分类
        manual_assets = []
        offset_items = [] # 在制资产冲销项
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
                # 排除预入库和自动生成的流动资金（因为流动资金是上面算出来的）
                elif i.name and (i.name.startswith(AssetPrefix.PRE_STOCK) or i.name.startswith(AssetPrefix.CASH)):
                    continue
                else:
                    manual_assets.append(i)

        # 5. 在制资产 (WIP) 计算
        # 逻辑：产品总投入成本 + 冲销额(通常为负) = 净 WIP
        wip_query = db.query(Product.name, func.sum(CostItem.actual_cost)).join(Product).group_by(Product.id).all()
        
        offset_map = {}
        for off in offset_items:
            p_name = off.name.replace("在制资产冲销-", "")
            offset_map[p_name] = offset_map.get(p_name, 0) + off.amount

        wip_list = []
        wip_total_cny = 0.0
        
        for p_name, total_cost in wip_query:
            if not total_cost: total_cost = 0
            offset_val = offset_map.get(p_name, 0)
            net_wip = total_cost + offset_val 
            # 过滤掉已结单（接近0）的项目
            if net_wip > 1.0:
                wip_list.append((p_name, net_wip))
                wip_total_cny += net_wip

        # --- C. 汇总计算 ---
        
        # 手动资产总额
        manual_cny = sum(i.amount for i in manual_assets if i.currency == Currency.CNY)
        manual_jpy = sum(i.amount for i in manual_assets if i.currency == Currency.JPY)

        # 资产总计
        total_asset_cny = cash_cny + fixed_cny + cons_cny + manual_cny + wip_total_cny
        total_asset_jpy = cash_jpy + fixed_jpy + cons_jpy + manual_jpy

        # 负债总计
        total_liab_cny = sum(i.amount for i in liabilities if i.currency == Currency.CNY)
        total_liab_jpy = sum(i.amount for i in liabilities if i.currency == Currency.JPY)

        # 资本总计
        total_eq_cny = sum(i.amount for i in equities if i.currency == Currency.CNY)
        total_eq_jpy = sum(i.amount for i in equities if i.currency == Currency.JPY)

        # 净资产
        net_cny = total_asset_cny - total_liab_cny
        net_jpy = total_asset_jpy - total_liab_jpy

        return {
            "cash": {"CNY": cash_cny, "JPY": cash_jpy},
            "fixed": {"CNY": fixed_cny, "JPY": fixed_jpy},
            "consumable": {"CNY": cons_cny, "JPY": cons_jpy},
            "wip": {"list": wip_list, "total_cny": wip_total_cny},
            "manual_assets": manual_assets, # 列表对象，供前端聚合展示
            "liabilities": liabilities,
            "equities": equities,
            "totals": {
                "asset": {"CNY": total_asset_cny, "JPY": total_asset_jpy},
                "liability": {"CNY": total_liab_cny, "JPY": total_liab_jpy},
                "equity": {"CNY": total_eq_cny, "JPY": total_eq_jpy},
                "net": {"CNY": net_cny, "JPY": net_jpy}
            }
        }

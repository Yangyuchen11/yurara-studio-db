# app_finance/services/balance_service.py
from django.db.models import Sum
from app_finance.models import CompanyBalanceItem
from app_assets.models import FixedAsset, ConsumableItem
from app_core.models import Product, CostItem
from app_core.constants import AssetPrefix, BalanceCategory, Currency

class BalanceService:
    @staticmethod
    def add_cash_account(name: str, currency: str):
        full_name = f"{AssetPrefix.CASH}-{name}"
        if CompanyBalanceItem.objects.filter(name=full_name).exists():
            raise ValueError(f"口座 {full_name} は既に存在します。")

        return CompanyBalanceItem.objects.create(
            category=BalanceCategory.ASSET,
            name=full_name,
            amount=0.0,
            currency=currency,
            asset_type="现金"
        )

    @staticmethod
    def get_financial_summary():
        all_balance_items = list(CompanyBalanceItem.objects.all())
        fixed_assets = list(FixedAsset.objects.all())
        consumables = list(ConsumableItem.objects.all())

        def add_to(d, currency, amount):
            curr = currency or Currency.CNY
            d[curr] = d.get(curr, 0.0) + amount

        cash_items = [i for i in all_balance_items if getattr(i, 'asset_type', '') == "现金" and i.category == BalanceCategory.ASSET]
        cash_by_curr = {}
        for i in cash_items:
            add_to(cash_by_curr, i.currency, i.amount)
        cash_by_curr.setdefault(Currency.CNY, 0.0)
        cash_by_curr.setdefault(Currency.JPY, 0.0)

        fixed_by_curr = {}
        for fa in fixed_assets:
            curr = getattr(fa, 'currency', Currency.CNY) or Currency.CNY
            add_to(fixed_by_curr, curr, fa.unit_price * fa.remaining_qty)
        fixed_by_curr.setdefault(Currency.CNY, 0.0)
        fixed_by_curr.setdefault(Currency.JPY, 0.0)

        cons_by_curr = {}
        for c in consumables:
            curr = getattr(c, 'currency', Currency.CNY) or Currency.CNY
            add_to(cons_by_curr, curr, c.unit_price * c.remaining_qty)
        cons_by_curr.setdefault(Currency.CNY, 0.0)
        cons_by_curr.setdefault(Currency.JPY, 0.0)

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

        wip_query = Product.objects.annotate(total_cost=Sum('costs__actual_cost')).values('id', 'name', 'total_cost')

        offset_map = {}
        for off in offset_items:
            if off.product_id:
                offset_map[off.product_id] = offset_map.get(off.product_id, 0) + off.amount
            else:
                p_name = off.name.replace(AssetPrefix.WIP_OFFSET, "")
                offset_map[p_name] = offset_map.get(p_name, 0) + off.amount

        wip_list = []
        wip_total_cny = 0.0
        for item in wip_query:
            p_id = item['id']
            p_name = item['name']
            total_cost = item['total_cost'] or 0.0
            offset_val = offset_map.get(p_id, offset_map.get(p_name, 0))
            net_wip = total_cost + offset_val
            if net_wip > 1.0:
                wip_list.append((p_name, net_wip))
                wip_total_cny += net_wip

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
            "cash": cash_by_curr,
            "fixed": fixed_by_curr,
            "consumable": cons_by_curr,
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

# yurara_app/state/report_state.py
"""
财务分析与资本报表 State 模块。
负责从物理交易流水中以最新现金余额锚点，逆推计算任意历史时间节点的期初、流入、流出及期末资产值。
"""
import reflex as rx
import pandas as pd
from datetime import datetime
from pydantic import BaseModel
from typing import Any
from ..state.app_state import AppState
from models import FinanceRecord, CompanyBalanceItem
from services.balance_service import BalanceService
from constants import to_cny


def compile_non_cny_str(group, is_abs=False):
    """
    将 pandas DataFrame 分组中所有非 CNY 币种的变动金额汇总并格式化为拼接字符串。
    例如: "10,000 JPY / 50.00 USD"
    """
    non_cny_group = group[group['currency'] != 'CNY']
    if non_cny_group.empty:
        return "0"
    
    currency_sums = non_cny_group.groupby('currency')['amount'].sum()
    parts = []
    for curr, val in sorted(currency_sums.items()):
        display_val = abs(val) if is_abs else val
        if abs(display_val) < 0.001:
            continue
        if curr == 'JPY':
            parts.append(f"{display_val:,.0f} JPY")
        else:
            parts.append(f"{display_val:,.2f} {curr}")
            
    if not parts:
        return "0"
    return " / ".join(parts)





class AccountPeriodRow(BaseModel):
    account_name: str = ""
    currency: str = "CNY"
    opening_balance: float = 0.0
    inflow: float = 0.0
    outflow: float = 0.0
    net_change: float = 0.0
    closing_balance: float = 0.0
    
    # 格式化字符串便于前端渲染
    opening_str: str = ""
    inflow_str: str = ""
    outflow_str: str = ""
    net_str: str = ""
    closing_str: str = ""


class FlowSummaryRow(BaseModel):
    category: str = ""
    direction: str = "流入"
    cny_amount: float = 0.0
    jpy_amount: float = 0.0
    total_cny_equiv: float = 0.0
    
    cny_str: str = ""
    jpy_str: str = ""
    equiv_str: str = ""


class AssetLiabPeriodRow(BaseModel):
    category: str = ""
    cny_amount: float = 0.0
    jpy_amount: float = 0.0
    total_cny_equiv: float = 0.0
    
    cny_str: str = ""
    jpy_str: str = ""
    equiv_str: str = ""


class MonthProfitTrendRow(BaseModel):
    month: str = ""
    net_profit: float = 0.0


class NonCashDetailRow(BaseModel):
    item_name: str = ""
    opening_balance: float = 0.0
    change: float = 0.0
    closing_balance: float = 0.0
    
    opening_str: str = ""
    change_str: str = ""
    closing_str: str = ""


class BalanceChangeRow(BaseModel):
    item_name: str = ""
    opening_balance: float = 0.0
    change: float = 0.0
    closing_balance: float = 0.0
    
    opening_str: str = ""
    change_str: str = ""
    closing_str: str = ""
    details: list[NonCashDetailRow] = []


def _sync_recalculate_report(
    is_test: bool,
    exchange_rate: float,
    rates_map: dict[str, float],
    active_report_type: str,
    selected_month: str,
    selected_year: str
):
    """在后台线程中执行重度 pandas 和 数据库期末演算计算"""
    from sqlalchemy.orm import sessionmaker
    from .app_state import get_cached_engine
    from models import FinanceRecord, CompanyBalanceItem
    from services.balance_service import BalanceService
    from constants import to_cny
    import pandas as pd
    
    engine = get_cached_engine(is_test)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        records = db.query(FinanceRecord).all()
        if not records:
            return {}
            
        cash_accounts = db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.category == 'asset',
            CompanyBalanceItem.asset_type == '现金'
        ).all()
        
        default_acc_id = {}
        all_currencies = list(set(a.currency for a in cash_accounts if a.currency))
        for curr in all_currencies:
            first_acc = next((a for a in sorted(cash_accounts, key=lambda x: x.id) if a.currency == curr), None)
            if first_acc:
                default_acc_id[curr] = first_acc.id
                
        # 准备数据流性质划分
        PL_INCOME = ["销售收入", "其他现金收入"]
        PL_EXPENSE = ["商品成本", "退款", "其他", "分红"]
        ASSET_ADD = ["固定资产购入", "其他资产购入", "现有资产增加", "新资产增加", "其他资产增加"]
        ASSET_SUB = ["现有资产减少"]
        LIAB_ADD = ["借入资金", "新增挂账资产"]
        LIAB_SUB = ["债务偿还", "资产抵消"]
        EQUITY_ADD = ["投资"]
        EQUITY_SUB = ["撤资"]
        INTERNAL = ["资金移动", "货币兑换"]
        
        data = []
        for r in records:
            final_acc_id = r.account_id
            if not final_acc_id and r.currency in default_acc_id:
                final_acc_id = default_acc_id[r.currency]
                
            if r.category in PL_INCOME + PL_EXPENSE:
                nature = "经营损益"
            elif r.category in ASSET_ADD + ASSET_SUB:
                nature = "资产变动"
            elif r.category in LIAB_ADD + LIAB_SUB:
                nature = "负债变动"
            elif r.category in EQUITY_ADD + EQUITY_SUB:
                nature = "资本变动"
            elif r.category in INTERNAL:
                nature = "内部流转"
            else:
                nature = "其他"
                
            is_cash_flow = r.category not in ["现有资产增加", "新资产增加", "现有资产减少", "其他资产增加", "资产抵消", "取消/冲销", "新增挂账资产"]
            
            dt = pd.to_datetime(r.date)
            
            # 特殊处理：资金移动若为0（在现金账户间划转），分裂为转出和转入两条记录，以支持个别账户期初期末对账逆推
            if r.category == "资金移动" and r.amount == 0:
                import re
                transfer_amount = 0.0
                m = re.search(r"金额:\s*([0-9.]+)", r.description or "")
                if m:
                    try:
                        transfer_amount = float(m.group(1))
                    except ValueError:
                        pass
                
                if transfer_amount > 0:
                    # 1. 账户 A (转出): 转出账户 r.account_id
                    data.append({
                        "id": r.id,
                        "date": dt,
                        "amount": -transfer_amount,
                        "cny_original": -transfer_amount if r.currency == 'CNY' else 0.0,
                        "jpy_original": -transfer_amount if r.currency == 'JPY' else 0.0,
                        "currency": r.currency,
                        "category": r.category,
                        "nature": "内部流转",
                        "account_id": final_acc_id,
                        "is_cash_flow": True,
                        "year": str(dt.year),
                        "month": dt.strftime("%Y-%m")
                    })
                    # 2. 账户 B (转入): 转入账户 r.related_item_id
                    if r.related_item_id:
                        data.append({
                            "id": r.id,
                            "date": dt,
                            "amount": transfer_amount,
                            "cny_original": transfer_amount if r.currency == 'CNY' else 0.0,
                            "jpy_original": transfer_amount if r.currency == 'JPY' else 0.0,
                            "currency": r.currency,
                            "category": r.category,
                            "nature": "内部流转",
                            "account_id": r.related_item_id,
                            "is_cash_flow": True,
                            "year": str(dt.year),
                            "month": dt.strftime("%Y-%m")
                        })
                    continue
            
            data.append({
                "id": r.id,
                "date": dt,
                "amount": r.amount,
                "cny_original": r.amount if r.currency == 'CNY' else 0.0,
                "jpy_original": r.amount if r.currency == 'JPY' else 0.0,
                "currency": r.currency,
                "category": r.category,
                "nature": nature,
                "account_id": final_acc_id,
                "is_cash_flow": is_cash_flow,
                "year": str(dt.year),
                "month": dt.strftime("%Y-%m")
            })
            
        df = pd.DataFrame(data)
        rates = dict(rates_map)
        
        # 确定筛选区间
        if active_report_type == "month":
            period_key = selected_month
            df_current = df[df['month'] == period_key]
        else:
            period_key = selected_year
            df_current = df[df['year'] == period_key]
            
        # 1. 账户期初期末流转逆向演算
        acc_list = []
        for acc in cash_accounts:
            current_db_balance = acc.amount
            curr = acc.currency
            
            acc_df = df[(df['account_id'] == acc.id) & (df['is_cash_flow'] == True)]
            
            if active_report_type == "month":
                future_df = acc_df[acc_df['month'] > period_key]
                curr_period_df = acc_df[acc_df['month'] == period_key]
            else:
                future_df = acc_df[acc_df['year'] > period_key]
                curr_period_df = acc_df[acc_df['year'] == period_key]
                
            future_net = future_df['amount'].sum() if not future_df.empty else 0.0
            current_net = curr_period_df['amount'].sum() if not curr_period_df.empty else 0.0
            
            closing_balance = current_db_balance - future_net
            opening_balance = closing_balance - current_net
            
            if opening_balance < 0:
                opening_balance = 0.0
            
            current_in = curr_period_df[curr_period_df['amount'] > 0]['amount'].sum() if not curr_period_df.empty else 0.0
            current_out = abs(curr_period_df[curr_period_df['amount'] < 0]['amount'].sum()) if not curr_period_df.empty else 0.0
            
            if abs(opening_balance) < 0.01 and abs(closing_balance) < 0.01 and current_in < 0.01 and current_out < 0.01:
                continue
                
            acc_list.append(AccountPeriodRow(
                account_name=acc.name,
                currency=curr,
                opening_balance=opening_balance,
                inflow=current_in,
                outflow=current_out,
                net_change=current_net,
                closing_balance=closing_balance,
                opening_str=f"{curr} {opening_balance:,.2f}" if curr == "CNY" else f"{curr} {opening_balance:,.0f}",
                inflow_str=f"{curr} {current_in:,.2f}" if curr == "CNY" else f"{curr} {current_in:,.0f}",
                outflow_str=f"{curr} {current_out:,.2f}" if curr == "CNY" else f"{curr} {current_out:,.0f}",
                net_str=f"{curr} {current_net:,.2f}" if curr == "CNY" else f"{curr} {current_net:,.0f}",
                closing_str=f"{curr} {closing_balance:,.2f}" if curr == "CNY" else f"{curr} {closing_balance:,.0f}",
            ))
            
        # 计算折合 CNY 顶层现金汇总
        past_cash_total = sum(r.opening_balance * to_cny(1.0, r.currency, rates) for r in acc_list)
        net_cash_total = sum(r.net_change * to_cny(1.0, r.currency, rates) for r in acc_list)
        closing_cash_total = sum(r.closing_balance * to_cny(1.0, r.currency, rates) for r in acc_list)
        
        # 2. 实体资产变动逆向结算
        df_asset_current = df_current[df_current['nature'] == '资产变动']
        
        def equiv_cny(row):
            return to_cny(row['amount'], row['currency'], rates)
            
        month_add = 0.0
        month_sub = 0.0
        
        if not df_asset_current.empty:
            df_asset_current = df_asset_current.copy()
            df_asset_current['cny_equiv'] = df_asset_current.apply(equiv_cny, axis=1)
            
            for _, row in df_asset_current.iterrows():
                val = abs(row['cny_equiv'])
                cat = row['category']
                if cat in ["现有资产增加", "新资产增加", "其他资产增加"]:
                    month_add += val
                elif cat in ["现有资产减少"]:
                    month_sub += val
                else:
                    if row['cny_equiv'] < 0:
                        month_add += val
                    else:
                        month_sub += val
                        
        net_asset_change = month_add - month_sub
        
        # 3. 经营损益净利润结算
        df_pl = df_current[df_current['nature'] == '经营损益']
        if not df_pl.empty:
            df_pl = df_pl.copy()
            df_pl['cny_equiv'] = df_pl.apply(equiv_cny, axis=1)
            profit_in = df_pl[df_pl['cny_equiv'] > 0]['cny_equiv'].sum()
            profit_out = df_pl[df_pl['cny_equiv'] < 0]['cny_equiv'].sum()
        else:
            profit_in = 0.0
            profit_out = 0.0
        net_profit = profit_in + profit_out
        
        # 4. 存货资产
        summary = BalanceService.get_financial_summary(db)
        wip_cny = summary["wip"]["total_cny"]
        
        stock_val = 0.0
        for ma in summary["manual_assets"]:
            if getattr(ma, 'product_id', None) is not None:
                val = to_cny(ma.amount, ma.currency, rates)
                stock_val += val
        stock_cny = stock_val
        
        # 5. 详细收支资产与负债变动列表
        ast_rows = []
        if not df_asset_current.empty:
            grp = df_asset_current.groupby('category')
            for name, group in grp:
                cny_val = group[group['currency'] == 'CNY']['amount'].sum()
                jpy_val = group[group['currency'] == 'JPY']['amount'].sum()
                tot_equiv = group.apply(equiv_cny, axis=1).abs().sum()
                
                ast_rows.append(AssetLiabPeriodRow(
                    category=name,
                    cny_amount=cny_val,
                    jpy_amount=jpy_val,
                    total_cny_equiv=tot_equiv,
                    cny_str=f"¥ {abs(cny_val):,.2f}",
                    jpy_str=compile_non_cny_str(group, is_abs=True),
                    equiv_str=f"¥ {tot_equiv:,.2f}"
                ))
        
        liab_rows = []
        df_liab = df_current[df_current['nature'].isin(['负债变动', '资本变动'])]
        if not df_liab.empty:
            grp = df_liab.groupby('category')
            for name, group in grp:
                cny_val = group[group['currency'] == 'CNY']['amount'].sum()
                jpy_val = group[group['currency'] == 'JPY']['amount'].sum()
                tot_equiv = group.apply(equiv_cny, axis=1).sum()
                
                liab_rows.append(AssetLiabPeriodRow(
                    category=name,
                    cny_amount=cny_val,
                    jpy_amount=jpy_val,
                    total_cny_equiv=tot_equiv,
                    cny_str=f"¥ {cny_val:,.2f}",
                    jpy_str=compile_non_cny_str(group, is_abs=False),
                    equiv_str=f"¥ {tot_equiv:,.2f}"
                ))
        
        # 6. 收支流向绝对额汇总
        flow_rows = []
        df_cash_m = df_current[df_current['is_cash_flow'] == True]
        if not df_cash_m.empty:
            df_cash_m = df_cash_m.copy()
            df_cash_m['cny_equiv'] = df_cash_m.apply(equiv_cny, axis=1)
            
            grp = df_cash_m.groupby('category')
            for name, group in grp:
                cny_val = group[group['currency'] == 'CNY']['amount'].sum()
                jpy_val = group[group['currency'] == 'JPY']['amount'].sum()
                tot_equiv = group['cny_equiv'].sum()
                
                flow_rows.append(FlowSummaryRow(
                    category=name,
                    direction="流入" if tot_equiv > 0 else "流出",
                    cny_amount=cny_val,
                    jpy_amount=jpy_val,
                    total_cny_equiv=tot_equiv,
                    cny_str=f"¥ {cny_val:,.2f}",
                    jpy_str=compile_non_cny_str(group, is_abs=False),
                    equiv_str=f"¥ {tot_equiv:,.2f}"
                ))
        flow_summary = sorted(flow_rows, key=lambda x: abs(x.total_cny_equiv), reverse=True)
        
        # 7. 年报特有
        trend_rows = []
        if active_report_type == "year":
            df_year_pl = df[df['year'] == period_key]
            df_year_pl = df_year_pl[df_year_pl['nature'] == '经营损益']
            
            if not df_year_pl.empty:
                df_year_pl = df_year_pl.copy()
                df_year_pl['cny_equiv'] = df_year_pl.apply(equiv_cny, axis=1)
                
                months_in_year = sorted(list(df_year_pl['month'].unique()))
                for m in months_in_year:
                    m_df = df_year_pl[df_year_pl['month'] == m]
                    m_profit = m_df['cny_equiv'].sum()
                    m_label = m.split("-")[1]
                    trend_rows.append(MonthProfitTrendRow(
                        month=m_label,
                        net_profit=m_profit
                    ))

        # 8. 期初与期末资产、负债及资本变动逆推
        # 1) 计算当前各资产大类 (CNY折合)
        current_cash_cny = sum(to_cny(amount, curr, rates) for curr, amount in summary["cash"].items())
        current_fixed_cny = sum(to_cny(amount, curr, rates) for curr, amount in summary["fixed"].items())
        current_cons_cny = sum(to_cny(amount, curr, rates) for curr, amount in summary["consumable"].items())
        current_wip_cny = summary["wip"]["total_cny"]
        
        current_stock_cny = stock_cny
        current_other_cny = sum(to_cny(ma.amount, ma.currency, rates) for ma in summary["manual_assets"] if getattr(ma, 'product_id', None) is None)
        
        current_total_assets = current_cash_cny + current_fixed_cny + current_cons_cny + current_wip_cny + current_stock_cny + current_other_cny
        current_liabilities = sum(to_cny(i.amount, i.currency, rates) for i in summary["liabilities"])
        current_capital = sum(to_cny(i.amount, i.currency, rates) for i in summary["equities"])
        
        # 2) 演算总资产/负债/资本变动
        def get_alc_changes(target_df):
            assets_chg = 0.0
            liab_chg = 0.0
            cap_chg = 0.0
            if target_df.empty:
                return assets_chg, liab_chg, cap_chg
            for _, row in target_df.iterrows():
                val = row['amount']
                curr = row['currency']
                cat = row['category']
                equiv = to_cny(val, curr, rates)
                
                # 资产变动：除去置换和内部流转
                if cat in ["固定资产购入", "其他资产购入", "资金移动", "货币兑换"]:
                    a_val = 0.0
                else:
                    a_val = equiv
                assets_chg += a_val
                
                # 负债变动
                if cat in ["借入资金", "新增挂账资产", "债务偿还", "资产抵消"]:
                    l_val = equiv
                else:
                    l_val = 0.0
                liab_chg += l_val
                
                # 资本变动
                if cat in ["投资", "撤资"]:
                    c_val = equiv
                else:
                    c_val = 0.0
                cap_chg += c_val
            return assets_chg, liab_chg, cap_chg

        if active_report_type == "month":
            df_future = df[df['month'] > period_key]
        else:
            df_future = df[df['year'] > period_key]
            
        future_assets_change, future_liabilities_change, future_capital_change = get_alc_changes(df_future)
        current_assets_change, current_liabilities_change, current_capital_change = get_alc_changes(df_current)
        
        # 3) 计算历史负债与资本余额
        closing_liabilities = current_liabilities - future_liabilities_change
        opening_liabilities = closing_liabilities - current_liabilities_change
        
        closing_capital = current_capital - future_capital_change
        opening_capital = closing_capital - current_capital_change
        
        # 4) 细分非现金资产项计算
        items_map = {
            "fixed": {},
            "consumable": {},
            "wip": {},
            "stock": {},
            "other": {}
        }
        
        # 从数据库加载实体项目
        from models import FixedAsset, ConsumableItem
        fixed_assets = db.query(FixedAsset).all()
        consumables = db.query(ConsumableItem).all()
        
        for fa in fixed_assets:
            val = to_cny(fa.unit_price * fa.remaining_qty, fa.currency, rates)
            items_map["fixed"][fa.name] = items_map["fixed"].get(fa.name, 0.0) + val
            
        for c in consumables:
            val = to_cny(c.unit_price * c.remaining_qty, c.currency, rates)
            items_map["consumable"][c.name] = items_map["consumable"].get(c.name, 0.0) + val
            
        for name, wip_val in summary["wip"]["list"]:
            items_map["wip"][name] = wip_val
            
        for ma in summary["manual_assets"]:
            val = to_cny(ma.amount, ma.currency, rates)
            if getattr(ma, 'product_id', None) is not None:
                items_map["stock"][ma.name] = items_map["stock"].get(ma.name, 0.0) + val
            else:
                items_map["other"][ma.name] = items_map["other"].get(ma.name, 0.0) + val

        # 逆推细分项变动
        item_future = {cat: {} for cat in items_map.keys()}
        item_current = {cat: {} for cat in items_map.keys()}
        
        for r in records:
            cat = r.category
            desc = (r.description or "").lower()
            equiv = to_cny(r.amount, r.currency, rates)
            
            nc_cat = None
            nc_change = 0.0
            
            if cat in ["固定资产购入", "其他资产购入", "商品成本"]:
                nc_change = -equiv
                if cat == "固定资产购入":
                    nc_cat = "fixed"
                elif cat == "其他资产购入":
                    nc_cat = "consumable"
                else:
                    nc_cat = "wip" # 采购成本先作为在制资产增加
            elif cat in ["现有资产增加", "新资产增加", "其他资产增加", "现有资产减少", "资产抵消"]:
                nc_change = equiv
                if "固定" in desc:
                    nc_cat = "fixed"
                elif "耗材" in desc or "物料" in desc:
                    nc_cat = "consumable"
                elif "在制" in desc or "在研" in desc or "wip" in desc:
                    nc_cat = "wip"
                elif "大货" in desc or "商品" in desc or "库存" in desc or "存货" in desc:
                    nc_cat = "stock"
                else:
                    nc_cat = "other"
            
            if nc_cat:
                dt = pd.to_datetime(r.date)
                r_period = dt.strftime("%Y-%m") if active_report_type == "month" else str(dt.year)
                
                # 匹配具体项名称
                matched_item = None
                for name in items_map[nc_cat].keys():
                    clean_name = name.replace("大货资产-", "").replace("流动资金-", "").strip().lower()
                    if clean_name and (clean_name in desc or clean_name in cat.lower()):
                        matched_item = name
                        break
                if not matched_item:
                    matched_item = "其他未分类资产"
                    
                if r_period > period_key:
                    item_future[nc_cat][matched_item] = item_future[nc_cat].get(matched_item, 0.0) + nc_change
                elif r_period == period_key:
                    item_current[nc_cat][matched_item] = item_current[nc_cat].get(matched_item, 0.0) + nc_change

        # 结合物理库存变动日志 InventoryLog 重新计算大货与在制明细逆推
        from models import Product, InventoryLog, CostItem
        from sqlalchemy import func
        products = db.query(Product).all()
        
        for prod in products:
            total_cost = db.query(func.sum(CostItem.actual_cost)).filter(CostItem.product_id == prod.id).scalar() or 0.0
            unit_cost = total_cost / prod.marketable_quantity if (prod.marketable_quantity and prod.marketable_quantity > 0) else 0.0
            
            stock_name = f"大货资产-{prod.name}"
            wip_name = prod.name
            
            logs = db.query(InventoryLog).filter(InventoryLog.product_name == prod.name).all()
            for log in logs:
                dt = pd.to_datetime(log.date)
                log_period = dt.strftime("%Y-%m") if active_report_type == "month" else str(dt.year)
                
                val_change = log.change_amount * unit_cost
                
                # 大货实物变动
                if log_period > period_key:
                    item_future["stock"][stock_name] = item_future["stock"].get(stock_name, 0.0) + val_change
                elif log_period == period_key:
                    item_current["stock"][stock_name] = item_current["stock"].get(stock_name, 0.0) + val_change
                    
                # 生产成品入库，扣减在制
                is_production_in = (log.change_amount > 0 and log.reason in ["成品入库", "生产入库", "打样入库"])
                if is_production_in:
                    wip_change = -val_change
                    if log_period > period_key:
                        item_future["wip"][wip_name] = item_future["wip"].get(wip_name, 0.0) + wip_change
                    elif log_period == period_key:
                        item_current["wip"][wip_name] = item_current["wip"].get(wip_name, 0.0) + wip_change

        # 组装明细列表
        detail_lists = {cat: [] for cat in items_map.keys()}
        for cat in items_map.keys():
            all_keys = set(items_map[cat].keys()) | set(item_future[cat].keys()) | set(item_current[cat].keys())
            for name in all_keys:
                curr_val = items_map[cat].get(name, 0.0)
                fut_chg = item_future[cat].get(name, 0.0)
                curr_chg = item_current[cat].get(name, 0.0)
                
                closing = curr_val - fut_chg
                opening = closing - curr_chg
                
                if abs(opening) < 0.01 and abs(closing) < 0.01 and abs(curr_chg) < 0.01:
                    continue
                    
                detail_lists[cat].append(NonCashDetailRow(
                    item_name=name,
                    opening_balance=opening,
                    change=curr_chg,
                    closing_balance=closing,
                    opening_str=f"¥ {opening:,.2f}",
                    change_str=f"¥ {curr_chg:,.2f}",
                    closing_str=f"¥ {closing:,.2f}"
                ))
            detail_lists[cat] = sorted(detail_lists[cat], key=lambda x: x.closing_balance, reverse=True)

        # 汇总各大类
        closing_fixed = sum(r.closing_balance for r in detail_lists["fixed"])
        opening_fixed = sum(r.opening_balance for r in detail_lists["fixed"])
        change_fixed = sum(r.change for r in detail_lists["fixed"])
        
        closing_cons = sum(r.closing_balance for r in detail_lists["consumable"])
        opening_cons = sum(r.opening_balance for r in detail_lists["consumable"])
        change_cons = sum(r.change for r in detail_lists["consumable"])
        
        closing_wip = sum(r.closing_balance for r in detail_lists["wip"])
        opening_wip = sum(r.opening_balance for r in detail_lists["wip"])
        change_wip = sum(r.change for r in detail_lists["wip"])
        
        closing_stock = sum(r.closing_balance for r in detail_lists["stock"])
        opening_stock = sum(r.opening_balance for r in detail_lists["stock"])
        change_stock = sum(r.change for r in detail_lists["stock"])
        
        closing_other = sum(r.closing_balance for r in detail_lists["other"])
        opening_other = sum(r.opening_balance for r in detail_lists["other"])
        change_other = sum(r.change for r in detail_lists["other"])

        non_cash_asset_rows = [
            BalanceChangeRow(
                item_name="大货商品资产 (Stock Assets)",
                opening_balance=opening_stock,
                change=change_stock,
                closing_balance=closing_stock,
                opening_str=f"¥ {opening_stock:,.2f}",
                change_str=f"¥ {change_stock:,.2f}",
                closing_str=f"¥ {closing_stock:,.2f}",
                details=detail_lists["stock"]
            ),
            BalanceChangeRow(
                item_name="在制在研资产 (WIP Assets)",
                opening_balance=opening_wip,
                change=change_wip,
                closing_balance=closing_wip,
                opening_str=f"¥ {opening_wip:,.2f}",
                change_str=f"¥ {change_wip:,.2f}",
                closing_str=f"¥ {closing_wip:,.2f}",
                details=detail_lists["wip"]
            ),
            BalanceChangeRow(
                item_name="固定设备资产 (Fixed Assets)",
                opening_balance=opening_fixed,
                change=change_fixed,
                closing_balance=closing_fixed,
                opening_str=f"¥ {opening_fixed:,.2f}",
                change_str=f"¥ {change_fixed:,.2f}",
                closing_str=f"¥ {closing_fixed:,.2f}",
                details=detail_lists["fixed"]
            ),
            BalanceChangeRow(
                item_name="消耗品与物料 (Consumable Assets)",
                opening_balance=opening_cons,
                change=change_cons,
                closing_balance=closing_cons,
                opening_str=f"¥ {opening_cons:,.2f}",
                change_str=f"¥ {change_cons:,.2f}",
                closing_str=f"¥ {closing_cons:,.2f}",
                details=detail_lists["consumable"]
            ),
            BalanceChangeRow(
                item_name="其他手动资产 (Other Manual Assets)",
                opening_balance=opening_other,
                change=change_other,
                closing_balance=closing_other,
                opening_str=f"¥ {opening_other:,.2f}",
                change_str=f"¥ {change_other:,.2f}",
                closing_str=f"¥ {closing_other:,.2f}",
                details=detail_lists["other"]
            )
        ]
        
        # 综合计算总资产（包含物理库存在内的所有资产汇总）
        opening_total_assets = past_cash_total + opening_fixed + opening_cons + opening_wip + opening_stock + opening_other
        closing_total_assets = closing_cash_total + closing_fixed + closing_cons + closing_wip + closing_stock + closing_other
        current_assets_change = closing_total_assets - opening_total_assets
        
        closing_net_assets = closing_total_assets - closing_liabilities
        opening_net_assets = opening_total_assets - opening_liabilities

        balance_change_rows = [
            BalanceChangeRow(
                item_name="总资产 (Total Assets)",
                opening_balance=opening_total_assets,
                change=current_assets_change,
                closing_balance=closing_total_assets,
                opening_str=f"¥ {opening_total_assets:,.2f}",
                change_str=f"¥ {current_assets_change:,.2f}",
                closing_str=f"¥ {closing_total_assets:,.2f}"
            ),
            BalanceChangeRow(
                item_name="负债 (Liabilities)",
                opening_balance=opening_liabilities,
                change=current_liabilities_change,
                closing_balance=closing_liabilities,
                opening_str=f"¥ {opening_liabilities:,.2f}",
                change_str=f"¥ {current_liabilities_change:,.2f}",
                closing_str=f"¥ {closing_liabilities:,.2f}"
            ),
            BalanceChangeRow(
                item_name="资本 (Capital / Equity)",
                opening_balance=opening_capital,
                change=current_capital_change,
                closing_balance=closing_capital,
                opening_str=f"¥ {opening_capital:,.2f}",
                change_str=f"¥ {current_capital_change:,.2f}",
                closing_str=f"¥ {closing_capital:,.2f}"
            ),
            BalanceChangeRow(
                item_name="净资产 (Net Assets)",
                opening_balance=opening_net_assets,
                change=closing_net_assets - opening_net_assets,
                closing_balance=closing_net_assets,
                opening_str=f"¥ {opening_net_assets:,.2f}",
                change_str=f"¥ {(closing_net_assets - opening_net_assets):,.2f}",
                closing_str=f"¥ {closing_net_assets:,.2f}"
            )
        ]
                    
        return {
            "available_months": sorted(list(set(df['month'])), reverse=True) if not df.empty else [],
            "available_years": sorted(list(set(df['year'])), reverse=True) if not df.empty else [],
            "acc_summary": acc_list,
            "past_cash_total": past_cash_total,
            "net_cash_total": net_cash_total,
            "closing_cash_total": closing_cash_total,
            "month_asset_add": month_add,
            "month_asset_sub": month_sub,
            "net_asset_change": net_asset_change,
            "profit_in": profit_in,
            "profit_out": profit_out,
            "net_profit": net_profit,
            "wip_cny": wip_cny,
            "stock_cny": stock_cny,
            "asset_purchase_rows": ast_rows,
            "liab_equity_rows": liab_rows,
            "flow_summary": flow_summary,
            "trend_rows": trend_rows,
            "balance_change_summary": balance_change_rows,
            "non_cash_asset_summary": non_cash_asset_rows,
        }
    finally:
        db.close()


class ReportState(AppState):
    active_report_type: str = "month"  # "month" 或 "year"
    is_loading: bool = True
    available_months: list[str] = []
    available_years: list[str] = []
    selected_month: str = ""
    selected_year: str = ""
    
    # 逆推计算结果指标
    past_cash_total: float = 0.0
    net_cash_total: float = 0.0
    closing_cash_total: float = 0.0
    
    # 实体设备与物料采购
    month_asset_add: float = 0.0
    month_asset_sub: float = 0.0
    net_asset_change: float = 0.0
    
    # 经营收支
    profit_in: float = 0.0
    profit_out: float = 0.0
    net_profit: float = 0.0
    
    # 实时存货盘点
    stock_cny: float = 0.0
    wip_cny: float = 0.0
    
    # 明细列表
    acc_summary: list[AccountPeriodRow] = []
    asset_purchase_rows: list[AssetLiabPeriodRow] = []
    liab_equity_rows: list[AssetLiabPeriodRow] = []
    flow_summary: list[FlowSummaryRow] = []
    
    # 年报特有：月份走势
    trend_rows: list[MonthProfitTrendRow] = []
    balance_change_summary: list[BalanceChangeRow] = []
    non_cash_asset_summary: list[BalanceChangeRow] = []

    # ===================== 计算属性 =====================

    @rx.var
    def chart_bar_data(self) -> list[dict[str, Any]]:
        """收支构成直方图数据 (适配 CSS 柱状图)。"""
        data = []
        if not self.flow_summary:
            return data
            
        max_val = max(abs(r.total_cny_equiv) for r in self.flow_summary)
        if max_val == 0:
            max_val = 1.0
            
        for r in self.flow_summary:
            abs_val = abs(r.total_cny_equiv)
            pct = (abs_val / max_val) * 100
            data.append({
                "name": r.category,
                "amount_str": f"¥ {abs_val:,.2f}",
                "width_pct": f"{pct}%"
            })
        return data

    @rx.var
    def trend_chart_data(self) -> list[dict[str, Any]]:
        """年报利润走势数据 (适配 CSS 柱状图)。"""
        data = []
        if not self.trend_rows:
            return data
            
        max_abs_profit = max(abs(r.net_profit) for r in self.trend_rows)
        if max_abs_profit == 0:
            max_abs_profit = 1.0
            
        for r in self.trend_rows:
            abs_val = abs(r.net_profit)
            # 柱子高度百分比，最高 100px
            height_px = int((abs_val / max_abs_profit) * 100)
            data.append({
                "month": f"{r.month}月",
                "net_profit": r.net_profit,
                "profit_str": f"¥ {r.net_profit:,.2f}" if r.net_profit >= 0 else f"-¥ {abs(r.net_profit):,.2f}",
                "height_str": f"{height_px}px",
                "is_positive": r.net_profit >= 0
            })
        return data

    @rx.var
    def has_data(self) -> bool:
        return len(self.available_months) > 0
    # --- 顶层格式化 ---
    @rx.var
    def past_cash_total_str(self) -> str: return f"¥ {self.past_cash_total:,.2f}"
    @rx.var
    def net_cash_total_str(self) -> str: return f"¥ {self.net_cash_total:,.2f}"
    @rx.var
    def closing_cash_total_str(self) -> str: return f"¥ {self.closing_cash_total:,.2f}"
    @rx.var
    def month_asset_add_str(self) -> str: return f"¥ {self.month_asset_add:,.2f}"
    @rx.var
    def month_asset_sub_str(self) -> str: return f"¥ {self.month_asset_sub:,.2f}"
    @rx.var
    def net_asset_change_str(self) -> str: return f"¥ {self.net_asset_change:,.2f}"
    @rx.var
    def profit_in_str(self) -> str: return f"¥ {self.profit_in:,.2f}"
    @rx.var
    def profit_out_str(self) -> str: return f"¥ {abs(self.profit_out):,.2f}"
    @rx.var
    def net_profit_str(self) -> str: return f"¥ {self.net_profit:,.2f}"
    @rx.var
    def stock_cny_str(self) -> str: return f"¥ {self.stock_cny:,.2f}"
    @rx.var
    def wip_cny_str(self) -> str: return f"¥ {self.wip_cny:,.2f}"
    @rx.var
    def inventory_total_cny_str(self) -> str: return f"¥ {(self.stock_cny + self.wip_cny):,.2f}"

    # ===================== 事件处理器 =====================

    @rx.event
    async def load_report_page(self):
        """加载报表页面并进行首次逆向计算。"""
        if not await self.is_authenticated_user():
            return
        self.is_loading = True
        yield
        
        # 首次计算以获取可用的时间区间
        import asyncio
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            _sync_recalculate_report,
            self.test_mode,
            self.exchange_rate,
            self.rates_map,
            self.active_report_type,
            self.selected_month,
            self.selected_year
        )
        if res:
            self.available_months = res["available_months"]
            self.available_years = res["available_years"]
            if self.available_months and not self.selected_month:
                self.selected_month = self.available_months[0]
            if self.available_years and not self.selected_year:
                self.selected_year = self.available_years[0]
                
        # 载入带时间区间的完整报表数据
        await self.recalculate_report_async()
        self.is_loading = False

    @rx.event
    async def select_report_type(self, rtype: str):
        """选择切换月报看板 vs 年报看板。"""
        if not await self.is_authenticated_user():
            return
        self.active_report_type = rtype
        self.is_loading = True
        yield
        await self.recalculate_report_async()
        self.is_loading = False

    @rx.event
    async def select_month(self, m: str):
        """切换月份。"""
        if not await self.is_authenticated_user():
            return
        self.selected_month = m
        self.is_loading = True
        yield
        await self.recalculate_report_async()
        self.is_loading = False

    @rx.event
    async def select_year(self, y: str):
        """切换年份。"""
        if not await self.is_authenticated_user():
            return
        self.selected_year = y
        self.is_loading = True
        yield
        await self.recalculate_report_async()
        self.is_loading = False

    async def recalculate_report_async(self):
        """在后台线程中执行重度计算并回写状态。"""
        import asyncio
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            _sync_recalculate_report,
            self.test_mode,
            self.exchange_rate,
            self.rates_map,
            self.active_report_type,
            self.selected_month,
            self.selected_year
        )
        if not res:
            return
            
        self.available_months = res["available_months"]
        self.available_years = res["available_years"]
        self.acc_summary = res["acc_summary"]
        self.past_cash_total = res["past_cash_total"]
        self.net_cash_total = res["net_cash_total"]
        self.closing_cash_total = res["closing_cash_total"]
        self.month_asset_add = res["month_asset_add"]
        self.month_asset_sub = res["month_asset_sub"]
        self.net_asset_change = res["net_asset_change"]
        self.profit_in = res["profit_in"]
        self.profit_out = res["profit_out"]
        self.net_profit = res["net_profit"]
        self.wip_cny = res["wip_cny"]
        self.stock_cny = res["stock_cny"]
        self.asset_purchase_rows = res["asset_purchase_rows"]
        self.liab_equity_rows = res["liab_equity_rows"]
        self.flow_summary = res["flow_summary"]
        self.trend_rows = res["trend_rows"]
        self.balance_change_summary = res.get("balance_change_summary", [])
        self.non_cash_asset_summary = res.get("non_cash_asset_summary", [])

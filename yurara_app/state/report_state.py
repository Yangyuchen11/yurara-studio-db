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
            
            current_in = curr_period_df[curr_period_df['amount'] > 0]['amount'].sum() if not curr_period_df.empty else 0.0
            current_out = abs(curr_period_df[curr_period_df['amount'] < 0]['amount'].sum()) if not curr_period_df.empty else 0.0
            
            if abs(opening_balance) < 0.01 and abs(current_net) < 0.01 and abs(closing_balance) < 0.01:
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

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
    def load_report_page(self):
        """加载报表页面并进行首次逆向计算。"""
        self.is_loading = True
        db = self.get_db()
        try:
            records = db.query(FinanceRecord).all()
            if not records:
                self.is_loading = False
                return
            
            # 建立 pandas df 计算年月
            dates = [pd.to_datetime(r.date) for r in records]
            yms = sorted(list(set(d.strftime("%Y-%m") for d in dates)), reverse=True)
            years = sorted(list(set(str(d.year) for d in dates)), reverse=True)
            
            self.available_months = yms
            self.available_years = years
            
            if yms and not self.selected_month:
                self.selected_month = yms[0]
            if years and not self.selected_year:
                self.selected_year = years[0]
                
            self.recalculate_report(db)
        finally:
            db.close()
            self.is_loading = False

    @rx.event
    def select_report_type(self, rtype: str):
        """选择切换月报看板 vs 年报看板。"""
        self.active_report_type = rtype
        db = self.get_db()
        try:
            self.recalculate_report(db)
        finally:
            db.close()

    @rx.event
    def select_month(self, m: str):
        """切换月份。"""
        self.selected_month = m
        db = self.get_db()
        try:
            self.recalculate_report(db)
        finally:
            db.close()

    @rx.event
    def select_year(self, y: str):
        """切换年份。"""
        self.selected_year = y
        db = self.get_db()
        try:
            self.recalculate_report(db)
        finally:
            db.close()

    def recalculate_report(self, db):
        """核心逆推计算逻辑。"""
        records = db.query(FinanceRecord).all()
        if not records:
            return
            
        cash_accounts = db.query(CompanyBalanceItem).filter(
            CompanyBalanceItem.category == 'asset',
            CompanyBalanceItem.asset_type == '现金'
        ).all()
        
        default_acc_id = {}
        for curr in ['CNY', 'JPY']:
            first_acc = next((a for a in sorted(cash_accounts, key=lambda x: x.id) if a.currency == curr), None)
            if first_acc:
                default_acc_id[curr] = first_acc.id
                
        # 准备数据流性质划分
        PL_INCOME = ["销售收入", "其他现金收入"]
        PL_EXPENSE = ["商品成本", "退款", "其他", "分红"]
        ASSET_ADD = ["固定资产购入", "其他资产购入", "现有资产增加", "新资产增加"]
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
                
            is_cash_flow = r.category not in ["资产抵消", "取消/冲销", "新增挂账资产"]
            
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
        rate = self.exchange_rate
        
        # 确定筛选区间
        if self.active_report_type == "month":
            period_key = self.selected_month
            df_current = df[df['month'] == period_key]
        else:
            period_key = self.selected_year
            df_current = df[df['year'] == period_key]
            
        # 1. 账户期初期末流转逆向演算
        acc_list = []
        for acc in cash_accounts:
            current_db_balance = acc.amount
            curr = acc.currency
            
            acc_df = df[(df['account_id'] == acc.id) & (df['is_cash_flow'] == True)]
            
            if self.active_report_type == "month":
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
            
        self.acc_summary = acc_list
        
        # 计算折合 CNY 顶层现金汇总
        self.past_cash_total = sum(r.opening_balance * (rate if r.currency == 'JPY' else 1.0) for r in acc_list)
        self.net_cash_total = sum(r.net_change * (rate if r.currency == 'JPY' else 1.0) for r in acc_list)
        self.closing_cash_total = sum(r.closing_balance * (rate if r.currency == 'JPY' else 1.0) for r in acc_list)
        
        # 2. 实体资产变动逆向结算
        df_asset_current = df_current[df_current['nature'] == '资产变动']
        
        def equiv_cny(row):
            return row['amount'] * (rate if row['currency'] == 'JPY' else 1.0)
            
        if not df_asset_current.empty:
            df_asset_current = df_asset_current.copy()
            df_asset_current['cny_equiv'] = df_asset_current.apply(equiv_cny, axis=1)
            self.month_asset_add = abs(df_asset_current[df_asset_current['cny_equiv'] < 0]['cny_equiv'].sum())
            self.month_asset_sub = abs(df_asset_current[df_asset_current['cny_equiv'] > 0]['cny_equiv'].sum())
        else:
            self.month_asset_add = 0.0
            self.month_asset_sub = 0.0
        self.net_asset_change = self.month_asset_add - self.month_asset_sub
        
        # 3. 经营损益净利润结算
        df_pl = df_current[df_current['nature'] == '经营损益']
        if not df_pl.empty:
            df_pl = df_pl.copy()
            df_pl['cny_equiv'] = df_pl.apply(equiv_cny, axis=1)
            self.profit_in = df_pl[df_pl['cny_equiv'] > 0]['cny_equiv'].sum()
            self.profit_out = df_pl[df_pl['cny_equiv'] < 0]['cny_equiv'].sum()
        else:
            self.profit_in = 0.0
            self.profit_out = 0.0
        self.net_profit = self.profit_in + self.profit_out
        
        # 4. 存货资产（家底盘点）
        summary = BalanceService.get_financial_summary(db)
        self.wip_cny = summary["wip"]["total_cny"]
        
        stock_val = 0.0
        for ma in summary["manual_assets"]:
            if getattr(ma, 'product_id', None) is not None:
                val = ma.amount * (rate if ma.currency == 'JPY' else 1.0)
                stock_val += val
        self.stock_cny = stock_val
        
        # 5. 详细收支资产与负债变动列表
        ast_rows = []
        if not df_asset_current.empty:
            grp = df_asset_current.groupby('category')
            for name, group in grp:
                cny_val = group[group['currency'] == 'CNY']['amount'].sum()
                jpy_val = group[group['currency'] == 'JPY']['amount'].sum()
                tot_equiv = abs(cny_val) + (abs(jpy_val) * rate)
                
                ast_rows.append(AssetLiabPeriodRow(
                    category=name,
                    cny_amount=cny_val,
                    jpy_amount=jpy_val,
                    total_cny_equiv=tot_equiv,
                    cny_str=f"¥ {abs(cny_val):,.2f}",
                    jpy_str=f"¥ {abs(jpy_val):,.0f}",
                    equiv_str=f"¥ {tot_equiv:,.2f}"
                ))
        self.asset_purchase_rows = ast_rows
        
        liab_rows = []
        df_liab = df_current[df_current['nature'].isin(['负债变动', '资本变动'])]
        if not df_liab.empty:
            grp = df_liab.groupby('category')
            for name, group in grp:
                cny_val = group[group['currency'] == 'CNY']['amount'].sum()
                jpy_val = group[group['currency'] == 'JPY']['amount'].sum()
                tot_equiv = cny_val + (jpy_val * rate)
                
                liab_rows.append(AssetLiabPeriodRow(
                    category=name,
                    cny_amount=cny_val,
                    jpy_amount=jpy_val,
                    total_cny_equiv=tot_equiv,
                    cny_str=f"¥ {cny_val:,.2f}",
                    jpy_str=f"¥ {jpy_val:,.0f}",
                    equiv_str=f"¥ {tot_equiv:,.2f}"
                ))
        self.liab_equity_rows = liab_rows
        
        # 6. 收支流向绝对额汇总 (图表和构成)
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
                    jpy_str=f"¥ {jpy_val:,.0f}",
                    equiv_str=f"¥ {tot_equiv:,.2f}"
                ))
        # 根据绝对额降序排
        self.flow_summary = sorted(flow_rows, key=lambda x: abs(x.total_cny_equiv), reverse=True)
        
        # 7. 年报特有：年度内按月份经营净利润走势
        if self.active_report_type == "year":
            df_year_pl = df[df['year'] == period_key]
            df_year_pl = df_year_pl[df_year_pl['nature'] == '经营损益']
            
            trend_list = []
            if not df_year_pl.empty:
                df_year_pl = df_year_pl.copy()
                df_year_pl['cny_equiv'] = df_year_pl.apply(equiv_cny, axis=1)
                
                # 按月份分摊
                months_in_year = sorted(list(df_year_pl['month'].unique()))
                for m in months_in_year:
                    m_df = df_year_pl[df_year_pl['month'] == m]
                    m_profit = m_df['cny_equiv'].sum()
                    
                    # 仅截取月份数作为 label
                    m_label = m.split("-")[1]
                    trend_list.append(MonthProfitTrendRow(
                        month=m_label,
                        net_profit=m_profit
                    ))
            self.trend_rows = trend_list

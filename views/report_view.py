# views/report_view.py
import streamlit as st
import pandas as pd
from datetime import datetime
from services.balance_service import BalanceService
from models import FinanceRecord, CompanyBalanceItem

def show_report_page(db, exchange_rate):
    st.header("📊 财务分析与资本报表")
    
    # 1. 获取所有真实的现金账户
    cash_accounts = db.query(CompanyBalanceItem).filter(
        CompanyBalanceItem.category == 'asset',
        CompanyBalanceItem.asset_type == '现金'
    ).all()
    
    default_acc_id = {}
    for curr in ['CNY', 'JPY']:
        first_acc = next((a for a in sorted(cash_accounts, key=lambda x: x.id) if a.currency == curr), None)
        if first_acc:
            default_acc_id[curr] = first_acc.id

    # 2. 读取所有财务流水
    records = db.query(FinanceRecord).all()
    if not records:
        st.info("暂无财务流水数据，无法生成报表。")
        return

    # --- 财务分类标准 ---
    PL_INCOME = ["销售收入", "其他现金收入"]
    PL_EXPENSE = ["商品成本", "退款", "其他"] 
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
        cny_amount = r.amount * exchange_rate if r.currency == 'JPY' else r.amount
        cny_original = r.amount if r.currency == 'CNY' else 0.0
        jpy_original = r.amount if r.currency == 'JPY' else 0.0

        dt = pd.to_datetime(r.date)
        data.append({
            "日期": dt,
            "金额": r.amount,
            "CNY变动": cny_original,
            "JPY变动": jpy_original,
            "折合CNY": cny_amount,
            "币种": r.currency,
            "分类": r.category,
            "财务性质": nature,
            "account_id": final_acc_id,
            "计入现金流": is_cash_flow,
            "年份": dt.year,
            "月份": dt.month,
            "年月": dt.strftime("%Y-%m")
        })
        
    df = pd.DataFrame(data)
    
    # ================= 报表渲染核心函数 =================
    def render_report_dashboard(df_current, period_label, period_key):
        
        # 逆推计算账户余额
        acc_summary = []
        for acc in cash_accounts:
            current_db_balance = acc.amount
            curr = acc.currency
            
            acc_df = df[(df['account_id'] == acc.id) & (df['计入现金流'] == True)]
            if period_label.endswith("月度"):
                future_df = acc_df[acc_df['年月'] > period_key]
                current_df = acc_df[acc_df['年月'] == period_key]
            else:
                future_df = acc_df[acc_df['年份'] > int(period_key)]
                current_df = acc_df[acc_df['年份'] == int(period_key)]
                
            future_net = future_df['金额'].sum() if not future_df.empty else 0.0
            current_net = current_df['金额'].sum() if not current_df.empty else 0.0
            
            closing_balance = current_db_balance - future_net
            opening_balance = closing_balance - current_net
            
            current_in = current_df[current_df['金额'] > 0]['金额'].sum() if not current_df.empty else 0.0
            current_out = abs(current_df[current_df['金额'] < 0]['金额'].sum()) if not current_df.empty else 0.0
            
            if abs(opening_balance) < 0.01 and abs(current_net) < 0.01 and abs(closing_balance) < 0.01:
                continue
                
            acc_summary.append({
                "资金账户": acc.name,
                "币种": curr,
                "期初额 (前)": opening_balance,
                "本期流入": current_in,
                "本期流出": current_out,
                "净变动": current_net,
                "期末额 (后)": closing_balance,
                "is_total": False
            })

        past_cash_total = sum(r['期初额 (前)'] * (exchange_rate if r['币种'] == 'JPY' else 1) for r in acc_summary)
        net_cash_total = sum(r['净变动'] * (exchange_rate if r['币种'] == 'JPY' else 1) for r in acc_summary)
        closing_cash_total = sum(r['期末额 (后)'] * (exchange_rate if r['币种'] == 'JPY' else 1) for r in acc_summary)

        st.divider()

        # ---------------- 一、 公司总体情况 ----------------
        st.markdown(f"### 📈 一、 {period_label} 公司总体财务概览")
        
        st.markdown("#### 💰 1. 现金流汇总 (折算CNY总计)")
        c1, c2, c3 = st.columns(3)
        c1.metric("期初总资金 (变动前)", f"¥ {past_cash_total:,.2f}")
        c2.metric("本期净现金流", f"¥ {net_cash_total:,.2f}", delta=f"{net_cash_total:,.2f}")
        c3.metric("期末总资金 (变动后)", f"¥ {closing_cash_total:,.2f}")

        df_asset_current = df_current[df_current['财务性质'] == '资产变动']
        month_asset_add = abs(df_asset_current[df_asset_current['折合CNY'] < 0]['折合CNY'].sum())
        month_asset_sub = abs(df_asset_current[df_asset_current['折合CNY'] > 0]['折合CNY'].sum())
        net_asset_change = month_asset_add - month_asset_sub

        st.markdown("#### 🏢 2. 实体资产变动 (设备/耗材等)")
        a1, a2, a3 = st.columns(3)
        a1.metric("本期新增投入", f"¥ {month_asset_add:,.2f}")
        a2.metric("本期资产变现", f"¥ {month_asset_sub:,.2f}")
        a3.metric("资产价值净增长", f"¥ {net_asset_change:,.2f}", delta=f"{net_asset_change:,.2f}")

        df_pl = df_current[df_current['财务性质'] == '经营损益']
        profit_in = df_pl[df_pl['折合CNY'] > 0]['折合CNY'].sum() if not df_pl.empty else 0.0
        profit_out = df_pl[df_pl['折合CNY'] < 0]['折合CNY'].sum() if not df_pl.empty else 0.0
        net_profit = profit_in + profit_out

        st.markdown("#### 💼 3. 经营盈亏 (净利润)")
        p1, p2, p3 = st.columns(3)
        p1.metric("本期营业总收入", f"¥ {profit_in:,.2f}")
        p2.metric("本期营业总成本", f"¥ {abs(profit_out):,.2f}")
        p3.metric("本期净利润", f"¥ {net_profit:,.2f}", delta=f"{net_profit:,.2f}")

        # ✨ 新增：动态读取商品存货资产 (大货与在制)
        st.markdown("#### 📦 4. 当前商品存货资产盘点 (实时家底)")
        st.caption("注：存货由于每天发货入库在实时变动，此处展示的是系统**当前的实时总资产**。上方“营业总成本”中支付给工厂的钱，最终化为了这里的实物家底。")
        
        summary = BalanceService.get_financial_summary(db)
        
        # 1. 提取在制资产 (WIP) - 直接使用引擎算好的准确数值
        wip_cny = summary["wip"]["total_cny"]
        
        # 2. 提取大货资产 (Stock) - 从资产列表中剥离出带有商品ID的大货资产
        stock_cny = 0.0
        for ma in summary["manual_assets"]:
            if getattr(ma, 'product_id', None) is not None:
                val = ma.amount * (exchange_rate if ma.currency == 'JPY' else 1.0)
                stock_cny += val
                
        i1, i2, i3 = st.columns(3)
        i1.metric("当前大货资产总值", f"¥ {stock_cny:,.2f}")
        i2.metric("当前在制资产总值", f"¥ {wip_cny:,.2f}")
        i3.metric("存货资产合计 (实时)", f"¥ {stock_cny + wip_cny:,.2f}")

        st.divider()

        # ---------------- 二、 资金账户明细 ----------------
        st.markdown(f"### 💵 二、 各资金账户变动明细")
        if acc_summary:
            total_row = {
                "资金账户": "✨ 公司资金总计 (折算CNY汇总)",
                "币种": "CNY",
                "期初额 (前)": past_cash_total,
                "本期流入": sum(r['本期流入'] * (exchange_rate if r['币种'] == 'JPY' else 1) for r in acc_summary),
                "本期流出": sum(r['本期流出'] * (exchange_rate if r['币种'] == 'JPY' else 1) for r in acc_summary),
                "净变动": net_cash_total,
                "期末额 (后)": closing_cash_total,
                "is_total": True
            }
            
            df_temp = pd.DataFrame(acc_summary)
            df_temp = df_temp.sort_values(by="期末额 (后)", ascending=False)
            df_acc_final = pd.concat([df_temp, pd.DataFrame([total_row])], ignore_index=True)
            
            st.dataframe(
                df_acc_final.drop(columns=['is_total']), 
                width="stretch", 
                hide_index=True,
                column_config={
                    "期初额 (前)": st.column_config.NumberColumn(format="%.2f"),
                    "本期流入": st.column_config.NumberColumn(format="%.2f"),
                    "本期流出": st.column_config.NumberColumn(format="%.2f"),
                    "净变动": st.column_config.NumberColumn(format="%.2f"),
                    "期末额 (后)": st.column_config.NumberColumn(format="%.2f", help="该账户在本期末的实际剩余资金")
                }
            )
        else:
            st.info("本期暂无有效账户数据。")

        st.divider()

        # ---------------- 三、 资产与负债变动明细 ----------------
        st.markdown(f"### 🏢 三、 资产与负债/资本变动明细")
        asset_liab_col_config = {
            "CNY变动": st.column_config.NumberColumn(format="¥ %.2f"),
            "JPY变动": st.column_config.NumberColumn(format="¥ %.0f"),
            "折合CNY总计": st.column_config.NumberColumn(format="¥ %.2f")
        }

        col_ast, col_liab = st.columns(2)
        with col_ast:
            st.markdown("#### 🛒 实体设备与物料采购")
            if not df_asset_current.empty:
                ast_sum = df_asset_current.groupby('分类')[['CNY变动', 'JPY变动', '折合CNY']].sum().reset_index()
                ast_sum.rename(columns={'折合CNY': '折合CNY总计'}, inplace=True)
                ast_sum['CNY变动'] = ast_sum['CNY变动'].abs()
                ast_sum['JPY变动'] = ast_sum['JPY变动'].abs()
                ast_sum['折合CNY总计'] = ast_sum['折合CNY总计'].abs()
                st.dataframe(ast_sum, width="stretch", hide_index=True, column_config=asset_liab_col_config)
            else:
                st.caption("本期无固定/其他资产的增减记录。")

        with col_liab:
            st.markdown("#### 📉 负债与外部资本变动")
            df_liab = df_current[df_current['财务性质'].isin(['负债变动', '资本变动'])]
            if not df_liab.empty:
                liab_sum = df_liab.groupby('分类')[['CNY变动', 'JPY变动', '折合CNY']].sum().reset_index()
                liab_sum.rename(columns={'折合CNY': '折合CNY总计'}, inplace=True)
                st.dataframe(liab_sum, width="stretch", hide_index=True, column_config=asset_liab_col_config)
            else:
                st.caption("本期无借贷还款或资本注资记录。")

        st.divider()

        # ---------------- 四、 收支流向构成分析 ----------------
        st.markdown(f"### 📊 四、 详细收支流向构成")
        df_cash_m = df_current[df_current['计入现金流'] == True]
        if not df_cash_m.empty:
            summary_m = df_cash_m.groupby('分类')[['CNY变动', 'JPY变动', '折合CNY']].sum().reset_index()
            summary_m['流向'] = summary_m['折合CNY'].apply(lambda x: '流入' if x > 0 else '流出')
            summary_m['绝对金额'] = summary_m['折合CNY'].abs()
            summary_m.rename(columns={'折合CNY': '折合CNY总计'}, inplace=True)
            summary_m = summary_m.sort_values(by=['流向', '绝对金额'], ascending=[False, False])

            col_chart, col_table = st.columns([2, 2.5])
            with col_chart:
                chart_data = summary_m.set_index('分类')['绝对金额']
                st.bar_chart(chart_data, color="#4CAF50")
            with col_table:
                st.dataframe(
                    summary_m[['分类', '流向', 'CNY变动', 'JPY变动', '折合CNY总计']], 
                    width="stretch", hide_index=True,
                    column_config={
                        "CNY变动": st.column_config.NumberColumn(format="¥ %.2f"),
                        "JPY变动": st.column_config.NumberColumn(format="¥ %.0f"),
                        "折合CNY总计": st.column_config.NumberColumn(format="¥ %.2f")
                    }
                )

    # ================= 选项卡分发 =================
    st.divider()
    tab_month, tab_year = st.tabs(["📅 公司资本月报", "📆 公司资本年报"])

    with tab_month:
        month_opts = sorted(df['年月'].unique(), reverse=True) if not df.empty else []
        if month_opts:
            sel_month = st.selectbox("🔍 选择查询月份", month_opts, key="sel_m")
            df_m = df[df['年月'] == sel_month]
            render_report_dashboard(df_m, f"{sel_month} 月度", sel_month)
        else:
            st.info("暂无数据")

    with tab_year:
        year_opts = sorted(df['年份'].unique(), reverse=True) if not df.empty else []
        if year_opts:
            sel_year = st.selectbox("🔍 选择查询年份", year_opts, key="sel_y")
            df_y = df[df['年份'] == sel_year]
            render_report_dashboard(df_y, f"{sel_year} 年度", sel_year)
            
            st.divider()
            st.markdown("#### 📈 年度利润月份走势")
            df_y_pl = df_y[df_y['财务性质'] == '经营损益']
            trend_pl = df_y_pl.groupby('月份')['折合CNY'].sum().reset_index()
            trend_pl.rename(columns={'折合CNY': '净利润 (CNY)'}, inplace=True)
            if not trend_pl.empty:
                st.line_chart(trend_pl.set_index('月份')['净利润 (CNY)'])
        else:
            st.info("暂无数据")
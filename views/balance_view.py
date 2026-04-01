# views/balance_view.py
import streamlit as st
import pandas as pd
from services.balance_service import BalanceService

def show_balance_page(db, exchange_rate):
    st.header("📊 公司账面概览 (资产负债表)")
    
    # === 新增功能：追加现金账户 ===
    with st.expander("➕ 追加现金账户", expanded=False):
        st.caption("在此处可以开设备用金、独立银行卡等专属现金账户。")
        c_acc1, c_acc2, c_acc3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        new_acc_name = c_acc1.text_input("账户名称", placeholder="如：支付宝、三井住友银行、日常备用金")
        new_acc_curr = c_acc2.selectbox("币种", ["CNY", "JPY"], key="new_acc_curr")
        if c_acc3.button("确认追加", type="primary", use_container_width=True):
            if not new_acc_name:
                st.error("请输入账户名称")
            else:
                try:
                    BalanceService.add_cash_account(db, new_acc_name, new_acc_curr)
                    st.toast(f"账户【{new_acc_name}】追加成功！", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
                    
    st.divider()

    summary = BalanceService.get_financial_summary(db)
    cash = summary["cash"]
    cash_items = summary["cash_items"]
    fixed = summary["fixed"]
    cons = summary["consumable"]
    wip = summary["wip"]
    totals = summary["totals"]
    
    def get_aggregated_display_data(items_list):
        grouped = {}
        for item in items_list:
            if abs(item.amount) < 0.01: continue
            name = item.name
            if name not in grouped: grouped[name] = {"CNY": 0.0, "JPY": 0.0}
            if item.currency == "CNY": grouped[name]["CNY"] += item.amount
            elif item.currency == "JPY": grouped[name]["JPY"] += item.amount
        result = []
        for name, amts in grouped.items():
            result.append({
                "项目": name,
                "CNY": f"{amts['CNY']:,.2f}" if abs(amts['CNY']) > 0 else "-",
                "JPY": f"{amts['JPY']:,.0f}" if abs(amts['JPY']) > 0 else "-"
            })
        return result

    def get_summary_html(title, cny_total, jpy_total, rate, color_theme):
        colors = {
            "blue":   {"bg": "#e6f3ff", "border": "#2196F3", "text": "#0d47a1"}, 
            "orange": {"bg": "#fff3e0", "border": "#ff9800", "text": "#e65100"}, 
            "green":  {"bg": "#e8f5e9", "border": "#4caf50", "text": "#1b5e20"}, 
            "purple": {"bg": "#f3e5f5", "border": "#9c27b0", "text": "#4a148c"}, 
        }
        c = colors[color_theme]
        jpy_to_cny = jpy_total * rate
        grand_total = cny_total + jpy_to_cny
        
        return f"""
        <div style="background-color: {c['bg']}; padding: 15px; border-radius: 8px; border-left: 5px solid {c['border']}; margin-top: 10px; margin-bottom: 10px;">
            <h4 style="margin:0 0 10px 0; color: {c['text']}; border-bottom: 1px solid {c['border']}20; padding-bottom:5px;">{title}</h4>
            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #555;">
                <span>CNY:</span><span style="font-weight:bold; color: #333;">¥ {cny_total:,.2f}</span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #555;">
                <span>JPY:</span><span style="font-weight:bold; color: #333;">¥ {jpy_total:,.0f}</span>
            </div>
            <div style="display: flex; justify-content: flex-end; font-size: 12px; color: #888; margin-bottom: 8px;">
                (折合 CNY: ¥ {jpy_to_cny:,.2f})
            </div>
            <div style="border-top: 1px dashed {c['text']}40; margin-top: 5px; padding-top: 5px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight:bold; color: {c['text']};">综合总计(CNY):</span>
                <span style="font-size: 18px; font-weight:bold; color: {c['text']};">¥ {grand_total:,.2f}</span>
            </div>
        </div>
        """

    col_left, col_right = st.columns([1.1, 1])

    with col_left:
        st.subheader("🏢 现金与实物资产 (Assets)")
        
        asset_data = []
        # 分离细化展现所有的现金账户
        for cash_acc in cash_items:
            if abs(cash_acc.amount) < 0.01: continue
            asset_data.append({
                "项目": f"💵 {cash_acc.name}", 
                "CNY": f"{cash_acc.amount:,.2f}" if cash_acc.currency == "CNY" else "-", 
                "JPY": f"{cash_acc.amount:,.0f}" if cash_acc.currency == "JPY" else "-"
            })
            
        if fixed["CNY"] > 0 or fixed["JPY"] > 0: 
            asset_data.append({"项目": "固定资产(设备)", "CNY": f"{fixed['CNY']:,.2f}", "JPY": f"{fixed['JPY']:,.0f}" if fixed['JPY'] > 0 else "-"})
        if cons["CNY"] > 0 or cons["JPY"] > 0: 
            asset_data.append({"项目": "其他资产", "CNY": f"{cons['CNY']:,.2f}", "JPY": f"{cons['JPY']:,.0f}" if cons['JPY'] > 0 else "-"})
        for p_name, net_val in wip["list"]:
            asset_data.append({"项目": f"📦 在制资产-{p_name}", "CNY": f"{net_val:,.2f}", "JPY": "-"})

        manual_display = get_aggregated_display_data(summary["manual_assets"])
        asset_data.extend(manual_display)

        if asset_data: st.dataframe(pd.DataFrame(asset_data), width="stretch", hide_index=True)
        else: st.info("暂无资产")

        # === 核心修改：报表四分列展示 ===
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown(get_summary_html("💵 现金总计", cash["CNY"], cash["JPY"], exchange_rate, "green"), unsafe_allow_html=True)
        with col_c2:
            st.markdown(get_summary_html("🏢 资产总计 (非现金)", totals["pure_asset"]["CNY"], totals["pure_asset"]["JPY"], exchange_rate, "blue"), unsafe_allow_html=True)
        
        st.markdown(get_summary_html("🏛️ CNY/JPY 总资产 (现金+资产)", totals["asset"]["CNY"], totals["asset"]["JPY"], exchange_rate, "purple"), unsafe_allow_html=True)
        st.markdown(get_summary_html("✨ 净资产 (总资产 - 负债)", totals["net"]["CNY"], totals["net"]["JPY"], exchange_rate, "orange"), unsafe_allow_html=True)

    with col_right:
        st.subheader("📉 负债与资本 (Liabilities & Equity)")
        liab_display = get_aggregated_display_data(summary["liabilities"])
        if liab_display: st.dataframe(pd.DataFrame(liab_display), width="stretch", hide_index=True)
        else: st.caption("暂无负债")
        st.markdown(get_summary_html("负债总计", totals["liability"]["CNY"], totals["liability"]["JPY"], exchange_rate, "orange"), unsafe_allow_html=True)

        st.divider()

        eq_display = get_aggregated_display_data(summary["equities"])
        if eq_display: st.dataframe(pd.DataFrame(eq_display), width="stretch", hide_index=True)
        else: st.caption("暂无资本记录")
        st.markdown(get_summary_html("资本总计", totals["equity"]["CNY"], totals["equity"]["JPY"], exchange_rate, "green"), unsafe_allow_html=True)
# views/balance_view.py
import streamlit as st
import pandas as pd
from services.balance_service import BalanceService

def show_balance_page(db, exchange_rate):
    # ================= 1. 顶部标题与统一管理区 =================
    st.header("📊 公司账面概览 (资产负债表)")
    st.caption("💡 提示：如需修改或删除特定的资产/负债项目，请前往【财务流水】界面找到对应的初始记录并进行删除，系统将自动回滚账目。")
    st.divider()

    # ================= 2. 获取核心数据 =================
    
    # --- 调用 Service 获取所有汇总数据 ---
    summary = BalanceService.get_financial_summary(db)
    
    # 解包数据以方便后续使用
    cash = summary["cash"]
    fixed = summary["fixed"]
    cons = summary["consumable"]
    wip = summary["wip"]
    totals = summary["totals"]
    
    # === 辅助函数：聚合相同名称的项目 (UI展示逻辑) ===
    def get_aggregated_display_data(items_list):
        grouped = {}
        for item in items_list:
            if abs(item.amount) < 0.01: continue
            
            name = item.name
            if name not in grouped:
                grouped[name] = {"CNY": 0.0, "JPY": 0.0}
            
            if item.currency == "CNY":
                grouped[name]["CNY"] += item.amount
            elif item.currency == "JPY":
                grouped[name]["JPY"] += item.amount
        
        result = []
        for name, amts in grouped.items():
            cny_val = amts["CNY"]
            jpy_val = amts["JPY"]
            result.append({
                "项目": name,
                "CNY": f"{cny_val:,.2f}" if abs(cny_val) > 0 else "-",
                "JPY": f"{jpy_val:,.0f}" if abs(jpy_val) > 0 else "-"
            })
        return result

    # === 辅助函数：生成统计卡片 HTML ===
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
                <span>CNY:</span>
                <span style="font-weight:bold; color: #333;">¥ {cny_total:,.2f}</span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #555;">
                <span>JPY:</span>
                <span style="font-weight:bold; color: #333;">¥ {jpy_total:,.0f}</span>
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

    # ================= 3. 界面渲染 =================
    col_left, col_right = st.columns([1.1, 1])

    # ---------------- 左侧：资产展示 ----------------
    with col_left:
        st.subheader("🏢 公司资产 (Assets)")
        
        asset_data = []
        # 1. 现金 (自动计算)
        if cash["CNY"] != 0: asset_data.append({"项目": "流动资金(CNY)", "CNY": f"{cash['CNY']:,.2f}", "JPY": "-"})
        if cash["JPY"] != 0: asset_data.append({"项目": "流动资金(JPY)", "CNY": "-", "JPY": f"{cash['JPY']:,.0f}"})
        
        # 2. 固定资产 & 耗材 (自动计算)
        if fixed["CNY"] > 0 or fixed["JPY"] > 0: 
            asset_data.append({
                "项目": "固定资产(设备)", 
                "CNY": f"{fixed['CNY']:,.2f}", 
                "JPY": f"{fixed['JPY']:,.0f}" if fixed['JPY'] > 0 else "-"
            })
            
        if cons["CNY"] > 0 or cons["JPY"] > 0: 
            asset_data.append({
                "项目": "其他资产", 
                "CNY": f"{cons['CNY']:,.2f}", 
                "JPY": f"{cons['JPY']:,.0f}" if cons['JPY'] > 0 else "-"
            })
        
        # 3. 净 WIP 资产 (自动计算)
        for p_name, net_val in wip["list"]:
            asset_data.append({
                "项目": f"📦 在制资产-{p_name}", 
                "CNY": f"{net_val:,.2f}", 
                "JPY": "-"
            })

        # 4. 手动录入的其他资产 (聚合显示)
        manual_display = get_aggregated_display_data(summary["manual_assets"])
        asset_data.extend(manual_display)

        if asset_data:
            st.dataframe(pd.DataFrame(asset_data), width="stretch", hide_index=True)
        else:
            st.info("暂无资产")

        # 显示资产总计
        st.markdown(
            get_summary_html("资产总计", totals["asset"]["CNY"], totals["asset"]["JPY"], exchange_rate, "blue"), 
            unsafe_allow_html=True
        )
        
        st.write("") 
        
        # 显示净资产
        st.markdown(
            get_summary_html("✨ 净资产 (Net Worth)", totals["net"]["CNY"], totals["net"]["JPY"], exchange_rate, "purple"), 
            unsafe_allow_html=True
        )


    # ---------------- 右侧：负债与资本展示 ----------------
    with col_right:
        st.subheader("📉 负债 (Liabilities)")
        liab_display = get_aggregated_display_data(summary["liabilities"])
        
        if liab_display:
            st.dataframe(pd.DataFrame(liab_display), width="stretch", hide_index=True)
        else:
            st.caption("暂无负债")

        st.markdown(
            get_summary_html("负债总计", totals["liability"]["CNY"], totals["liability"]["JPY"], exchange_rate, "orange"), 
            unsafe_allow_html=True
        )

        st.divider()

        st.subheader("🏛️ 资本 (Equity)")
        eq_display = get_aggregated_display_data(summary["equities"])

        if eq_display:
            st.dataframe(pd.DataFrame(eq_display), width="stretch", hide_index=True)
        else:
            st.caption("暂无资本记录")
        
        st.markdown(
            get_summary_html("资本总计", totals["equity"]["CNY"], totals["equity"]["JPY"], exchange_rate, "green"), 
            unsafe_allow_html=True
        )
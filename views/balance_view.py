import streamlit as st
import pandas as pd
from sqlalchemy import func
from models import CompanyBalanceItem, FixedAsset, ConsumableItem, FinanceRecord, Product, CostItem

def show_balance_page(db, exchange_rate):
    st.header("📊 公司账面概览 (资产负债表)")

    # 【修改点】已删除顶部的 "➕ 新增条目" 区域
    # 现在所有资产/负债/资本的增加，都必须通过【财务资金流水】录入，保证账务合规。

    st.divider()

    # ================= 1. 核心计算 =================
    
    all_items = db.query(CompanyBalanceItem).all()
    
    # 分离 "在制资产冲销" 项
    offset_items = [i for i in all_items if i.name and i.name.startswith("在制资产冲销-")]
    
    # 过滤掉冲销项后的其他手动资产
    assets_manual = [i for i in all_items if i.category == 'asset' and not i.name.startswith("在制资产冲销-")]
    
    liabilities = [i for i in all_items if i.category == 'liability']
    equities = [i for i in all_items if i.category == 'equity']

    finance_records = db.query(FinanceRecord).all()
    fixed_assets = db.query(FixedAsset).all()
    consumables = db.query(ConsumableItem).all()

    # --- A. 计算资产总额 ---
    cash_cny = sum([r.amount for r in finance_records if r.currency == 'CNY'])
    cash_jpy = sum([r.amount for r in finance_records if r.currency == 'JPY'])
    
    # 固定资产 & 耗材 (统一折算为 CNY)
    fixed_total = 0
    for fa in fixed_assets:
        curr = getattr(fa, 'currency', 'CNY')
        rate = exchange_rate if curr == "JPY" else 1.0
        fixed_total += (fa.unit_price * fa.remaining_qty) * rate

    consumable_total = 0
    for c in consumables:
        curr = getattr(c, 'currency', 'CNY')
        rate = exchange_rate if curr == "JPY" else 1.0
        consumable_total += (c.unit_price * c.remaining_qty) * rate
    
    manual_asset_cny = sum([i.amount for i in assets_manual if i.currency == 'CNY'])
    manual_asset_jpy = sum([i.amount for i in assets_manual if i.currency == 'JPY'])

    # 在制资产计算 (总成本 - 冲销额)
    wip_query = db.query(Product.name, func.sum(CostItem.actual_cost)).join(Product).group_by(Product.id).all()
    
    offset_map = {}
    for off in offset_items:
        p_name = off.name.replace("在制资产冲销-", "")
        offset_map[p_name] = offset_map.get(p_name, 0) + off.amount 

    wip_final_list = []
    wip_total_cny = 0
    
    for p_name, total_cost in wip_query:
        if not total_cost: total_cost = 0
        offset_val = offset_map.get(p_name, 0)
        net_wip = total_cost + offset_val 
        if net_wip > 1.0:
            wip_final_list.append((p_name, net_wip))
            wip_total_cny += net_wip

    total_asset_cny = cash_cny + fixed_total + consumable_total + manual_asset_cny + wip_total_cny
    total_asset_jpy = cash_jpy + manual_asset_jpy

    # --- B. 负债 & C. 资本 & D. 净资产 ---
    total_liab_cny = sum([i.amount for i in liabilities if i.currency == 'CNY'])
    total_liab_jpy = sum([i.amount for i in liabilities if i.currency == 'JPY'])
    
    total_eq_cny = sum([i.amount for i in equities if i.currency == 'CNY'])
    total_eq_jpy = sum([i.amount for i in equities if i.currency == 'JPY'])
    
    net_cny = total_asset_cny - total_liab_cny
    net_jpy = total_asset_jpy - total_liab_jpy

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
                <span style="font-weight:bold; color: {c['text']};">综合总计:</span>
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
        # 自动项
        if cash_cny != 0: asset_data.append({"项目": "流动资金(CNY)", "CNY": f"{cash_cny:,.2f}", "JPY": "-", "_id": "a1", "_type": "auto"})
        if cash_jpy != 0: asset_data.append({"项目": "流动资金(JPY)", "CNY": "-", "JPY": f"{cash_jpy:,.0f}", "_id": "a2", "_type": "auto"})
        if fixed_total > 0: asset_data.append({"项目": "固定资产(设备)", "CNY": f"{fixed_total:,.2f}", "JPY": "-", "_id": "a3", "_type": "auto"})
        if consumable_total > 0: asset_data.append({"项目": "耗材资产", "CNY": f"{consumable_total:,.2f}", "JPY": "-", "_id": "a4", "_type": "auto"})
        
        # 净 WIP 资产
        for p_name, net_val in wip_final_list:
            asset_data.append({
                "项目": f"📦 在制资产-{p_name}", 
                "CNY": f"{net_val:,.2f}", 
                "JPY": "-", 
                "_id": f"wip_{p_name}", 
                "_type": "auto"
            })

        # 手动项 (其他资产)
        for item in assets_manual:
            cny = item.amount if item.currency == 'CNY' else 0
            jpy = item.amount if item.currency == 'JPY' else 0
            asset_data.append({
                "项目": item.name, "CNY": f"{cny:,.2f}" if cny else "-", "JPY": f"{jpy:,.0f}" if jpy else "-", "_id": item.id, "_type": "manual"
            })

        if asset_data:
            st.dataframe(pd.DataFrame(asset_data)[["项目", "CNY", "JPY"]], use_container_width=True, hide_index=True)
            with st.popover("🗑️ 删除其他资产"):
                # 只允许删除那些【没有】关联流水的项目 (即 finance_record_id 为空)
                # 这样防止用户在资产表误删了有账目来源的资产
                manuals = [x for x in asset_data if x['_type'] == 'manual']
                

                # 我们可以让用户选，但在点击删除时判断
                
                to_del = st.selectbox("选择删除", manuals, format_func=lambda x: x['项目'])
                
                if st.button("确认删除资产"):
                    # 查询该对象
                    item_to_del = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == to_del['_id']).first()
                    
                    if item_to_del:
                        if item_to_del.finance_record_id:
                            # 如果有关联流水，禁止删除，提示去流水表删
                            st.error("⚠️ 该项目关联了财务流水，无法在此删除！请去【财务资金流水】界面删除对应的收支记录。")
                        else:
                            db.delete(item_to_del)
                            db.commit()
                            st.rerun()
        else:
            st.info("暂无资产")

        st.markdown(get_summary_html("资产总计", total_asset_cny, total_asset_jpy, exchange_rate, "blue"), unsafe_allow_html=True)
        st.write("") 
        st.markdown(get_summary_html("✨ 净资产 (Net Worth)", net_cny, net_jpy, exchange_rate, "purple"), unsafe_allow_html=True)


    # ---------------- 右侧：负债与资本展示 ----------------
    with col_right:
        st.subheader("📉 负债 (Liabilities)")
        liab_data = []
        for item in liabilities:
            cny = item.amount if item.currency == 'CNY' else 0
            jpy = item.amount if item.currency == 'JPY' else 0
            liab_data.append({"项目": item.name, "CNY": f"{cny:,.2f}" if cny else "-", "JPY": f"{jpy:,.0f}" if jpy else "-", "_id": item.id})

        if liab_data:
            st.dataframe(pd.DataFrame(liab_data)[["项目", "CNY", "JPY"]], use_container_width=True, hide_index=True)
            with st.popover("🗑️ 删除债务"):
                l_del = st.selectbox("选择删除债务", liab_data, format_func=lambda x: x['项目'])
                if st.button("确认删除债务"):
                    db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == l_del['_id']).delete()
                    db.commit()
                    st.rerun()
        
        st.markdown(get_summary_html("负债总计", total_liab_cny, total_liab_jpy, exchange_rate, "orange"), unsafe_allow_html=True)

        st.divider()

        st.subheader("🏛️ 资本 (Equity)")
        eq_data = []
        for item in equities:
            cny = item.amount if item.currency == 'CNY' else 0
            jpy = item.amount if item.currency == 'JPY' else 0
            eq_data.append({"项目": item.name, "CNY": f"{cny:,.2f}" if cny else "-", "JPY": f"{jpy:,.0f}" if jpy else "-", "_id": item.id})

        if eq_data:
            st.dataframe(pd.DataFrame(eq_data)[["项目", "CNY", "JPY"]], use_container_width=True, hide_index=True)
            with st.popover("🗑️ 删除资本"):
                e_del = st.selectbox("选择删除资本", eq_data, format_func=lambda x: x['项目'])
                if st.button("确认删除资本"):
                    db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == e_del['_id']).delete()
                    db.commit()
                    st.rerun()
        
        st.markdown(get_summary_html("资本总计", total_eq_cny, total_eq_jpy, exchange_rate, "green"), unsafe_allow_html=True)
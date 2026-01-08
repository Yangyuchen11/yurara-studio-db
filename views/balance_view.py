import streamlit as st
import pandas as pd
from sqlalchemy import func
from models import CompanyBalanceItem, FixedAsset, ConsumableItem, FinanceRecord, Product, CostItem

# 修改函数签名，增加 exchange_rate 参数
def show_balance_page(db, exchange_rate):
    st.header("📊 公司账面概览 (资产负债表)")

    # --- 顶部控制栏 (简化了，移除了汇率输入) ---
    with st.expander("➕ 新增条目 (非固定资产/非流水类)", expanded=False):
        st.caption("注：现金余额已根据财务流水自动计算，无需在此手动添加。")
        with st.form("add_balance_item"):
            r1, r2, r3, r4 = st.columns([1.5, 1.5, 1, 1])
            f_cate = r1.selectbox("类别", ["资产 (Asset)", "债务 (Liability)", "资本 (Equity)"])
            f_name = r2.text_input("项目名称")
            f_curr = r3.radio("币种", ["CNY", "JPY"], horizontal=True)
            f_amount = r4.number_input("金额", min_value=0.0, step=100.0)
            
            if st.form_submit_button("添加", type="primary"):
                cate_code = "asset" if "资产" in f_cate else "liability" if "债务" in f_cate else "equity"
                new_item = CompanyBalanceItem(category=cate_code, name=f_name, currency=f_curr, amount=f_amount)
                db.add(new_item)
                db.commit()
                st.rerun()
    st.divider()

    # ================= 1. 核心计算 =================
    
    all_items = db.query(CompanyBalanceItem).all()
    
    # 【修改点】分离 "在制资产冲销" 项
    # 冲销项不应出现在 assets_manual 手动列表里，而是用于计算逻辑
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
    fixed_total = sum([fa.unit_price * fa.remaining_qty for fa in fixed_assets])
    consumable_total = sum([c.unit_price * c.remaining_qty for c in consumables])
    manual_asset_cny = sum([i.amount for i in assets_manual if i.currency == 'CNY'])
    manual_asset_jpy = sum([i.amount for i in assets_manual if i.currency == 'JPY'])

    # 【修改点】在制资产计算 (总成本 - 冲销额)
    # 1. 计算总实付成本
    wip_query = db.query(Product.name, func.sum(CostItem.actual_cost)).join(Product).group_by(Product.id).all()
    
    # 2. 准备冲销字典 { "在制资产冲销-产品名": 金额(负数) }
    offset_map = {}
    for off in offset_items:
        # 从 "在制资产冲销-XXX" 提取 "XXX"
        p_name = off.name.replace("在制资产冲销-", "")
        offset_map[p_name] = offset_map.get(p_name, 0) + off.amount # amount 是负数

    # 3. 计算净 WIP
    wip_final_list = []
    wip_total_cny = 0
    
    for p_name, total_cost in wip_query:
        if not total_cost: total_cost = 0
        offset_val = offset_map.get(p_name, 0)
        
        net_wip = total_cost + offset_val # 加上负数
        
        # 只有当净值 > 1 (忽略浮点误差) 时才显示
        if net_wip > 1.0:
            wip_final_list.append((p_name, net_wip))
            wip_total_cny += net_wip

    total_asset_cny = cash_cny + fixed_total + consumable_total + manual_asset_cny + wip_total_cny
    total_asset_jpy = cash_jpy + manual_asset_jpy

    # --- B. 计算负债总额 ---
    total_liab_cny = sum([i.amount for i in liabilities if i.currency == 'CNY'])
    total_liab_jpy = sum([i.amount for i in liabilities if i.currency == 'JPY'])

    # --- C. 计算资本总额 ---
    total_eq_cny = sum([i.amount for i in equities if i.currency == 'CNY'])
    total_eq_jpy = sum([i.amount for i in equities if i.currency == 'JPY'])

    # --- D. 计算净资产 ---
    net_cny = total_asset_cny - total_liab_cny
    net_jpy = total_asset_jpy - total_liab_jpy

    # ================= 2. 辅助函数 =================
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
        
        for p_name, net_val in wip_final_list:
            asset_data.append({
                "项目": f"📦 在制资产-{p_name}", 
                "CNY": f"{net_val:,.2f}", 
                "JPY": "-", 
                "_id": f"wip_{p_name}", 
                "_type": "auto"
            })

        # 显示手动资产 (已过滤掉冲销项)
        for item in assets_manual:
            cny = item.amount if item.currency == 'CNY' else 0
            jpy = item.amount if item.currency == 'JPY' else 0
            asset_data.append({
                "项目": item.name, "CNY": f"{cny:,.2f}" if cny else "-", "JPY": f"{jpy:,.0f}" if jpy else "-", "_id": item.id, "_type": "manual"
            })

        if asset_data:
            st.dataframe(pd.DataFrame(asset_data)[["项目", "CNY", "JPY"]], use_container_width=True, hide_index=True)
            
            # 删除逻辑保持不变
            with st.popover("🗑️ 删除手动资产"):
                manuals = [x for x in asset_data if x['_type'] == 'manual']
                if manuals:
                    to_del = st.selectbox("选择删除", manuals, format_func=lambda x: x['项目'])
                    if st.button("确认删除资产"):
                        db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == to_del['_id']).delete()
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
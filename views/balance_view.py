import streamlit as st
import pandas as pd
from sqlalchemy import func
from models import CompanyBalanceItem, FixedAsset, ConsumableItem, FinanceRecord, Product, CostItem

def show_balance_page(db, exchange_rate):
    # ================= 1. 顶部标题与统一管理区 =================
    c_title, c_del = st.columns([5, 1])
    c_title.header("📊 公司账面概览 (资产负债表)")
    
    # 获取所有可删除的项目
    all_items = db.query(CompanyBalanceItem).all()
    
    deletable_items = []
    for i in all_items:
        # 排除自动生成的在制资产冲销项
        if i.name and (i.name.startswith("在制资产冲销-") or i.name.startswith("预入库大货资产-") or i.name.startswith("大货资产-")):
            continue
        
        type_label = {"asset": "资产", "liability": "负债", "equity": "资本"}.get(i.category, "未知")
        
        # 只存 ID 和显示文本
        deletable_items.append({
            "id": i.id,
            "display": f"[{type_label}] {i.name} (¥{i.amount:,.2f})"
        })
    
    with c_del:
        with st.popover("🗑️ 删除项目", use_container_width=True):
            if not deletable_items:
                st.caption("暂无项目可删除")
            else:
                target_dict = st.selectbox("选择要删除的项目", deletable_items, format_func=lambda x: x["display"])
                st.caption("⚠️ 注意：删除此项将同时删除关联的财务流水记录！")
                
                if st.button("🔴 确认删除", type="primary", use_container_width=True):
                    del_id = target_dict["id"]
                    item_to_del = db.query(CompanyBalanceItem).filter(CompanyBalanceItem.id == del_id).first()
                    
                    if item_to_del:
                        try:
                            # 1. 尝试删除关联的流水
                            if item_to_del.finance_record_id:
                                fin_rec = db.query(FinanceRecord).filter(FinanceRecord.id == item_to_del.finance_record_id).first()
                                if fin_rec:
                                    db.delete(fin_rec)
                            
                            # 2. 删除资产/负债/资本项本身
                            name_bak = item_to_del.name
                            db.delete(item_to_del)
                            db.commit()
                            st.toast(f"已删除：{name_bak}", icon="🗑️")
                            st.rerun()
                        except Exception as e:
                            db.rollback()
                            st.error(f"删除失败: {e}")
                    else:
                        st.warning("该项目可能已被删除或不存在。")
                        st.rerun()

    st.divider()

    # ================= 2. 核心数据计算 =================
    
    # 重新查询数据
    all_items = db.query(CompanyBalanceItem).all()
    
    # 分离 "在制资产冲销" 项
    offset_items = [i for i in all_items if i.name and i.name.startswith("在制资产冲销-")]
    
    # 过滤掉 冲销项、预入库项、以及流动资金项
    assets_manual = [
        i for i in all_items 
        if i.category == 'asset' 
        and not i.name.startswith("在制资产冲销-")
        and not i.name.startswith("预入库大货资产-")  # 避免预入库重复显示
        and not i.name.startswith("流动资金")          # 避免流动资金重复显示
    ]
    
    liabilities = [i for i in all_items if i.category == 'liability']
    equities = [i for i in all_items if i.category == 'equity']

    finance_records = db.query(FinanceRecord).all()
    fixed_assets = db.query(FixedAsset).all()
    consumables = db.query(ConsumableItem).all()

    # --- A. 计算资产总额 ---
    cash_cny = sum([r.amount for r in finance_records if r.currency == 'CNY'])
    cash_jpy = sum([r.amount for r in finance_records if r.currency == 'JPY'])
    
    # 固定资产 (分别统计 CNY 和 JPY)
    fixed_total_cny = 0.0
    fixed_total_jpy = 0.0
    for fa in fixed_assets:
        curr = getattr(fa, 'currency', 'CNY')
        val_origin = fa.unit_price * fa.remaining_qty
        if curr == "JPY":
            fixed_total_jpy += val_origin
        else:
            fixed_total_cny += val_origin

    # 耗材/其他资产 (分别统计 CNY 和 JPY)
    consumable_total_cny = 0.0
    consumable_total_jpy = 0.0
    for c in consumables:
        curr = getattr(c, 'currency', 'CNY')
        val_origin = c.unit_price * c.remaining_qty
        if curr == "JPY":
            consumable_total_jpy += val_origin
        else:
            consumable_total_cny += val_origin
    
    manual_asset_cny = sum([i.amount for i in assets_manual if i.currency == 'CNY'])
    manual_asset_jpy = sum([i.amount for i in assets_manual if i.currency == 'JPY'])

    # 在制资产计算 (总成本 - 冲销额) -> 默认为 CNY
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
        # 只显示有价值的在制资产
        if net_wip > 1.0:
            wip_final_list.append((p_name, net_wip))
            wip_total_cny += net_wip

    # 汇总逻辑调整
    total_asset_cny = cash_cny + fixed_total_cny + consumable_total_cny + manual_asset_cny + wip_total_cny
    total_asset_jpy = cash_jpy + fixed_total_jpy + consumable_total_jpy + manual_asset_jpy

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
                <span style="font-weight:bold; color: {c['text']};">综合总计(CNY):</span>
                <span style="font-size: 18px; font-weight:bold; color: {c['text']};">¥ {grand_total:,.2f}</span>
            </div>
        </div>
        """

    # === 辅助函数：聚合相同名称的项目 ===
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

    # ================= 3. 界面渲染 =================
    col_left, col_right = st.columns([1.1, 1])

    # ---------------- 左侧：资产展示 ----------------
    with col_left:
        st.subheader("🏢 公司资产 (Assets)")
        
        asset_data = []
        # 1. 自动项 (流动资金)
        if cash_cny != 0: asset_data.append({"项目": "流动资金(CNY)", "CNY": f"{cash_cny:,.2f}", "JPY": "-"})
        if cash_jpy != 0: asset_data.append({"项目": "流动资金(JPY)", "CNY": "-", "JPY": f"{cash_jpy:,.0f}"})
        
        # 2. 自动项 (固定资产 & 其他资产)
        if fixed_total_cny > 0 or fixed_total_jpy > 0: 
            asset_data.append({
                "项目": "固定资产(设备)", 
                "CNY": f"{fixed_total_cny:,.2f}", 
                "JPY": f"{fixed_total_jpy:,.0f}" if fixed_total_jpy > 0 else "-"
            })
            
        if consumable_total_cny > 0 or consumable_total_jpy > 0: 
            asset_data.append({
                "项目": "其他资产", 
                "CNY": f"{consumable_total_cny:,.2f}", 
                "JPY": f"{consumable_total_jpy:,.0f}" if consumable_total_jpy > 0 else "-"
            })
        
        # 3. 净 WIP 资产
        for p_name, net_val in wip_final_list:
            asset_data.append({
                "项目": f"📦 在制资产-{p_name}", 
                "CNY": f"{net_val:,.2f}", 
                "JPY": "-"
            })

        # 4. 手动项 (其他资产) - 【已修改】应用聚合逻辑
        manual_display = get_aggregated_display_data(assets_manual)
        asset_data.extend(manual_display)

        if asset_data:
            st.dataframe(pd.DataFrame(asset_data), use_container_width=True, hide_index=True)
        else:
            st.info("暂无资产")

        st.markdown(get_summary_html("资产总计", total_asset_cny, total_asset_jpy, exchange_rate, "blue"), unsafe_allow_html=True)
        st.write("") 
        st.markdown(get_summary_html("✨ 净资产 (Net Worth)", net_cny, net_jpy, exchange_rate, "purple"), unsafe_allow_html=True)


    # ---------------- 右侧：负债与资本展示 ----------------
    with col_right:
        st.subheader("📉 负债 (Liabilities)")
        # 【已修改】应用聚合逻辑
        liab_display = get_aggregated_display_data(liabilities)
        
        if liab_display:
            st.dataframe(pd.DataFrame(liab_display), use_container_width=True, hide_index=True)
        else:
            if not liab_display: st.caption("暂无负债")

        st.markdown(get_summary_html("负债总计", total_liab_cny, total_liab_jpy, exchange_rate, "orange"), unsafe_allow_html=True)

        st.divider()

        st.subheader("🏛️ 资本 (Equity)")
        # 【已修改】应用聚合逻辑
        eq_display = get_aggregated_display_data(equities)

        if eq_display:
            st.dataframe(pd.DataFrame(eq_display), use_container_width=True, hide_index=True)
        else:
            if not eq_display: st.caption("暂无资本记录")
        
        st.markdown(get_summary_html("资本总计", total_eq_cny, total_eq_jpy, exchange_rate, "green"), unsafe_allow_html=True)
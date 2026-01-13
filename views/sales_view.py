import streamlit as st
import pandas as pd
from sqlalchemy import func
from models import InventoryLog, Product

def show_sales_page(db):
    st.header("📈 销售额一览")

    # === 1. 获取所有销售数据 ===
    # 只查询已售出的日志
    sold_logs = db.query(InventoryLog).filter(InventoryLog.is_sold == True).all()

    if not sold_logs:
        st.info("暂无销售数据。")
        return

    # === 2. 全局汇总卡片 ===
    total_sales_cny = sum([l.sale_amount for l in sold_logs if l.currency == 'CNY'])
    total_sales_jpy = sum([l.sale_amount for l in sold_logs if l.currency == 'JPY'])
    total_qty = sum([-l.change_amount for l in sold_logs]) # 出库记录通常是负数，取反

    # 简单的汇率估算用于展示总额 (可选，这里暂不折算，分别显示)
    with st.container(border=True):
        st.markdown("#### 🏢 全局销售总览")
        c1, c2, c3 = st.columns(3)
        c1.metric("累计销售额 (CNY)", f"¥ {total_sales_cny:,.2f}")
        c2.metric("累计销售额 (JPY)", f"¥ {total_sales_jpy:,.0f}")
        c3.metric("累计售出商品数", f"{total_qty} 件")

    st.divider()

    # === 3. 按产品维度统计 ===
    st.subheader("📦 各产品销售详情")

    # 数据预处理：按产品名称分组
    product_stats = {}
    
    for log in sold_logs:
        p_name = log.product_name
        if p_name not in product_stats:
            product_stats[p_name] = {
                "cny": 0.0,
                "jpy": 0.0,
                "qty": 0,
                "platforms": set()
            }
        
        if log.currency == 'CNY':
            product_stats[p_name]["cny"] += log.sale_amount
        elif log.currency == 'JPY':
            product_stats[p_name]["jpy"] += log.sale_amount
        
        product_stats[p_name]["qty"] += -log.change_amount
        if log.platform:
            product_stats[p_name]["platforms"].add(log.platform)

    # 转换为 DataFrame 用于展示列表
    summary_data = []
    for p_name, stats in product_stats.items():
        summary_data.append({
            "产品名称": p_name,
            "销售额 (CNY)": stats["cny"],
            "销售额 (JPY)": stats["jpy"],
            "售出数量": stats["qty"],
            "涉及平台": ", ".join(stats["platforms"])
        })
    
    df_summary = pd.DataFrame(summary_data)
    
    # 3.1 左侧：产品排行榜/列表
    c_list, c_detail = st.columns([1.5, 1])
    
    with c_list:
        st.markdown("##### 📋 产品销售榜单")
        st.dataframe(
            df_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "销售额 (CNY)": st.column_config.NumberColumn(format="¥ %.2f"),
                "销售额 (JPY)": st.column_config.NumberColumn(format="¥ %.0f"),
                "售出数量": st.column_config.NumberColumn(format="%d"),
            }
        )

    # 3.2 右侧/下方：单品详细筛选查看
    with c_detail:
        st.markdown("##### 🔍 单品详细查询")
        selected_product = st.selectbox("选择要查看详情的产品", df_summary["产品名称"].tolist())
        
        if selected_product:
            # 过滤出该产品的日志
            p_logs = [l for l in sold_logs if l.product_name == selected_product]
            
            # 再次统计该产品的平台分布
            pf_breakdown = {}
            for l in p_logs:
                pf = l.platform or "未知"
                if pf not in pf_breakdown: pf_breakdown[pf] = 0
                pf_breakdown[pf] += -l.change_amount
            
            # 展示
            with st.container(border=True):
                st.write(f"**{selected_product}**")
                
                # 平台分布饼图/数据
                st.caption("各平台销量分布:")
                df_pf = pd.DataFrame(list(pf_breakdown.items()), columns=["平台", "销量"])
                st.dataframe(df_pf, use_container_width=True, hide_index=True)
                
                # 最近几笔销售记录
                st.caption("最近销售记录:")
                recent_logs = sorted(p_logs, key=lambda x: x.id, reverse=True)[:15]
                for l in recent_logs:
                    st.text(f"{l.date} | {l.variant} | {l.change_amount} | {l.sale_amount}{l.currency}")
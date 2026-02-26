import streamlit as st
import pandas as pd
from services.sales_service import SalesService
from database import SessionLocal

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_sales_df(test_mode_flag):
    db_cache = st.session_state.get_dynamic_session()
    try:
        raw_logs = SalesService.get_raw_sales_logs(db_cache)
        df = SalesService.process_sales_data(raw_logs)
        return df
    finally:
        db_cache.close()

def show_sales_page(db):
    st.header("📈 销售数据透视")

    # === 1. 获取并处理数据 (带缓存加速) ===
    test_mode = st.session_state.get("test_mode", False)
    with st.spinner("正在加载销售大数据..."):
        df = get_cached_sales_df(test_mode)
    
    if df.empty:
        st.info("暂无销售数据。")
        return

    # === 2. 全局概览 ===
    total_cny = df[df['currency'] == 'CNY']['amount'].sum()
    total_jpy = df[df['currency'] == 'JPY']['amount'].sum()
    total_qty = df['qty'].sum()
    
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("累计销售额 (CNY)", f"¥ {total_cny:,.2f}")
        c2.metric("累计销售额 (JPY)", f"¥ {total_jpy:,.0f}")
        c3.metric("累计净销量", f"{total_qty} 件")
    
    st.divider()

    # === 3. 左右分栏布局 (1:2) ===
    col_nav, col_detail = st.columns([1, 2])

    # --- 左侧：产品总榜 (导航) ---
    with col_nav:
        st.subheader("📋 产品榜单")
        
        df_prod_summary = SalesService.get_product_leaderboard(df)
        
        # 显示简略表格
        st.dataframe(
            df_prod_summary,
            width="stretch",
            hide_index=True,
            column_config={
                "CNY总额": st.column_config.NumberColumn(format="¥%.0f"),
                "净销量": st.column_config.NumberColumn(format="%d"),
            },
            height=500
        )

    # --- 右侧：详细透视面板 ---
    with col_detail:
        # 获取用户选择的产品
        product_list = df_prod_summary['product'].tolist() if not df_prod_summary.empty else []
        default_idx = 0 if product_list else None
        
        selected_product = st.selectbox("🔍 选择要深入分析的产品", product_list, index=default_idx)

        if selected_product:
            st.markdown(f"### 📦 {selected_product} 销售详情")
            
            # 筛选该产品的数据 (View层做简单的切片操作即可)
            df_p = df[df['product'] == selected_product].copy()
            
            # 1. 顶部小卡片：该产品的数据
            p_cny = df_p[df_p['currency']=='CNY']['amount'].sum()
            p_qty = df_p['qty'].sum()
            active_platforms = df_p[df_p['qty'] != 0]['platform'].nunique()
            
            k1, k2, k3 = st.columns(3)
            k1.info(f"净销量: **{p_qty}** 件")
            k2.success(f"CNY: **¥{p_cny:,.2f}**")
            k3.warning(f"活跃平台: **{active_platforms}** 个")

            st.divider()

            # === 核心功能：款式 x 平台 透视表 ===
            st.markdown("#### 🧩 款式-平台 交叉透视 (净销量)")
            
            if not df_p.empty:
                pivot_table = pd.pivot_table(
                    df_p, 
                    values='qty', 
                    index='variant', 
                    columns='platform', 
                    aggfunc='sum', 
                    fill_value=0,
                    margins=True, 
                    margins_name='总计'
                )
                
                st.dataframe(
                    pivot_table, 
                    width="stretch",
                    column_config={
                        col: st.column_config.NumberColumn(format="%d") 
                        for col in pivot_table.columns
                    }
                )
            else:
                st.write("暂无数据")

            # === 可视化：堆叠柱状图 ===
            st.markdown("#### 📊 销量构成可视化")
            
            # 准备绘图数据
            chart_data = df_p.groupby(['variant', 'platform'])['qty'].sum().reset_index()
            # 过滤掉净销量为0的记录
            chart_data = chart_data[chart_data['qty'] != 0]
            
            if not chart_data.empty:
                st.bar_chart(
                    chart_data,
                    x="variant",
                    y="qty",
                    color="platform",
                    stack=True,
                    height=300
                )
            else:
                st.caption("没有有效的净销量数据可供绘图。")

            # === 底部：最近变动记录 ===
            with st.expander("📝 查看最近 20 笔变动日志 (含撤销/退款)", expanded=False):
                # 简单处理一下显示的 DataFrame
                df_logs = df_p.sort_values(by='id', ascending=False).head(20).copy()
                
                def format_type(row):
                    if row['type'] == 'sale': return "📤 售出"
                    elif row['type'] == 'return': return "↩️ 退货"
                    else: return "🔙 撤销"
                
                df_logs['类型'] = df_logs.apply(format_type, axis=1)
                
                df_display = df_logs.rename(columns={
                    'date': '日期', 'variant': '款式', 'qty': '变动数量', 
                    'amount': '金额', 'currency': '币种', 'platform': '平台'
                })
                
                st.dataframe(
                    df_display[['日期', '类型', '款式', '变动数量', '平台', '金额', '币种']],
                    width="stretch",
                    hide_index=True
                )
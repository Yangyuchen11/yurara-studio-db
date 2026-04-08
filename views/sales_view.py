# views/sales_view.py
import streamlit as st
import pandas as pd
import math
from services.sales_service import SalesService

def fragment_if_available(func):
    if hasattr(st, "fragment"):
        return st.fragment()(func)
    elif hasattr(st, "experimental_fragment"):
        return st.experimental_fragment()(func)
    return func

# --- 分别缓存 V1 和 V2 数据 ---
@st.cache_data(ttl=300, show_spinner=False)
def get_cached_sales_df_v1(test_mode_flag, cache_version): # ✨ 加入版本参数
    db_cache = st.session_state.get_dynamic_session()
    try:
        raw_logs = SalesService.get_raw_sales_logs_v1(db_cache)
        df = SalesService.process_sales_data_v1(db_cache, raw_logs)
        return df
    finally:
        db_cache.close()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_sales_df_v2(test_mode_flag, cache_version): # ✨ 加入版本参数
    db_cache = st.session_state.get_dynamic_session()
    try:
        df = SalesService.process_sales_data_v2(db_cache)
        return df
    finally:
        db_cache.close()

# --- 封装好的变动日志局部组件 (支持多版本前缀) ---
@fragment_if_available
def render_sales_logs_fragment(df_p, selected_product, version_prefix):
    with st.expander("📝 查看变动日志 (含撤销/退款)", expanded=False):
        df_logs_all = df_p.sort_values(by='id', ascending=False) if 'id' in df_p.columns else df_p.copy()
        total_rows = len(df_logs_all)
        
        if total_rows == 0:
            st.info("暂无变动日志")
        else:
            PAGE_SIZE = 20
            total_pages = math.ceil(total_rows / PAGE_SIZE)
            
            page_key = f"sales_log_page_{version_prefix}_{selected_product}"
            if page_key not in st.session_state:
                st.session_state[page_key] = 1
            
            if st.session_state[page_key] > total_pages:
                st.session_state[page_key] = total_pages
                
            current_page = st.session_state[page_key]
            start_idx = (current_page - 1) * PAGE_SIZE
            end_idx = current_page * PAGE_SIZE
            
            df_logs = df_logs_all.iloc[start_idx:end_idx].copy()
            
            def format_type(row):
                if row['type'] == 'sale': return "📤 售出"
                elif row['type'] == 'return': return "↩️ 退货入库"
                elif row['type'] == 'refund': return "💸 仅退款"
                else: return "🔙 撤销"
            
            df_logs['类型'] = df_logs.apply(format_type, axis=1)
            df_display = df_logs.rename(columns={
                'date': '日期', 'variant': '款式', 'qty': '变动数量', 
                'amount': '金额', 'currency': '币种', 'platform': '平台'
            })
            
            st.dataframe(
                df_display[['日期', '类型', '款式', '变动数量', '平台', '金额', '币种']],
                width="stretch", hide_index=True,
                column_config={"金额": st.column_config.NumberColumn(format="%.2f")}
            )
            
            if total_pages > 1:
                col_btn1, col_btn2, col_page, col_btn3, col_btn4 = st.columns([1, 1, 2, 1, 1])
                with col_btn2:
                    if st.button("⬅️ 上一页", disabled=(current_page == 1), key=f"prev_log_{version_prefix}_{selected_product}", use_container_width=True):
                        st.session_state[page_key] -= 1
                        st.rerun() 
                with col_page:
                    st.markdown(f"<div style='text-align: center; padding-top: 5px; color: #555;'>第 <b>{current_page}</b> / {total_pages} 页</div>", unsafe_allow_html=True)
                with col_btn3:
                    if st.button("下一页 ➡️", disabled=(current_page == total_pages), key=f"next_log_{version_prefix}_{selected_product}", use_container_width=True):
                        st.session_state[page_key] += 1
                        st.rerun()

# --- 封装好的单页大屏渲染器 ---
def render_sales_dashboard(df, exchange_rate, version_prefix):
    if df.empty:
        st.info("暂无销售数据。")
        return

    total_cny = df[df['currency'] == 'CNY']['amount'].sum()
    total_jpy = df[df['currency'] == 'JPY']['amount'].sum()
    total_qty = df['qty'].sum()
    grand_total_cny = total_cny + (total_jpy * exchange_rate)

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("纯 CNY 销售额", f"¥ {total_cny:,.2f}")
        c2.metric("纯 JPY 销售额", f"¥ {total_jpy:,.0f}")
        c3.metric("折合总销售额 (CNY)", f"¥ {grand_total_cny:,.2f}", help=f"当前汇率: {exchange_rate*100}")
        c4.metric("累计净销量", f"{int(total_qty)} 件")
    
    st.divider()
    col_nav, col_detail = st.columns([1, 2])

    with col_nav:
        st.subheader("📋 产品榜单")
        df_prod_summary = SalesService.get_product_leaderboard(df, exchange_rate)
        if not df_prod_summary.empty:
            df_display = df_prod_summary.rename(columns={'product': '产品名'})
            st.dataframe(
                df_display, width="stretch", hide_index=True,
                column_config={
                    "产品名": st.column_config.TextColumn(),
                    "折合CNY总额": st.column_config.NumberColumn(format="¥ %.2f"),
                    "CNY总额": st.column_config.NumberColumn(format="¥ %.2f"),
                    "JPY总额": st.column_config.NumberColumn(format="¥ %.0f")
                },
                height=500
            )
        else:
            st.caption("暂无榜单数据")

    with col_detail:
        product_list = df_prod_summary['product'].tolist() if not df_prod_summary.empty else []
        default_idx = 0 if product_list else None
        selected_product = st.selectbox("🔍 选择要深入分析的产品", product_list, index=default_idx, key=f"sel_prod_{version_prefix}")

        if selected_product:
            st.markdown(f"### 📦 {selected_product} 销售详情")
            df_p = df[df['product'] == selected_product].copy()
            
            p_cny = df_p[df_p['currency']=='CNY']['amount'].sum()
            p_jpy = df_p[df_p['currency']=='JPY']['amount'].sum()
            p_cny_equiv = p_cny + (p_jpy * exchange_rate)
            p_qty = df_p['qty'].sum()
            active_platforms = df_p[df_p['qty'] != 0]['platform'].nunique()
            
            k1, k2, k3 = st.columns(3)
            k1.info(f"净销量: **{int(p_qty)}** 件")
            k2.success(f"折合CNY: **¥{p_cny_equiv:,.2f}**") 
            k3.warning(f"活跃平台: **{active_platforms}** 个")

            st.divider()
            st.markdown("#### 🧩 款式-平台 交叉透视 (净销量)")
            if not df_p.empty:
                pivot_table = pd.pivot_table(
                    df_p, values='qty', index='variant', columns='platform', 
                    aggfunc='sum', fill_value=0, margins=True, margins_name='总计'
                )
                st.dataframe(
                    pivot_table, width="stretch",
                    column_config={col: st.column_config.NumberColumn(format="%d") for col in pivot_table.columns}
                )
            else:
                st.write("暂无数据")

            st.markdown("#### 📊 销量构成可视化")
            chart_data = df_p.groupby(['variant', 'platform'])['qty'].sum().reset_index()
            chart_data = chart_data[chart_data['qty'] != 0]
            
            if not chart_data.empty:
                st.bar_chart(chart_data, x="variant", y="qty", color="platform", stack=True, height=300)
            else:
                st.caption("没有有效的净销量数据可供绘图。")

            render_sales_logs_fragment(df_p, selected_product, version_prefix)

# --- 主页面入口 ---
def show_sales_page(db, exchange_rate):
    st.header("📈 销售数据透视")

    test_mode = st.session_state.get("test_mode", False)
    cache_version = st.session_state.get("global_cache_version", 0) # ✨ 提取版本参数
    
    # 两个 Tab 分页
    tab_v2, tab_v1 = st.tabs(["🚀 V2.0 订单系统版 (精准)", "🕰️ V1.0 历史数据版 (兼容)"])
    
    with tab_v2:
        st.info("💡 **系统版本 V2.0**：数据源完全解耦，仅从「销售订单」和「售后管理」抓取。彻底消除冗余翻倍、负数异常、并能完美兼容“仅退款”操作。(**推荐使用**)")
        with st.spinner("正在加载 V2.0 销售大数据..."):
            df_v2 = get_cached_sales_df_v2(test_mode, cache_version) # ✨ 传入版本
        render_sales_dashboard(df_v2, exchange_rate, "v2")
        
    with tab_v1:
        st.warning("⚠️ **系统版本 V1.0**：数据通过抓取底层「物理库存日志」强行反推。包含早期无订单记录的历史老数据，但受限于旧逻辑存在少量数据翻倍、负数等异常。(仅供历史对账参考)")
        with st.spinner("正在加载 V1.0 销售大数据..."):
            df_v1 = get_cached_sales_df_v1(test_mode, cache_version) # ✨ 传入版本
        render_sales_dashboard(df_v1, exchange_rate, "v1")
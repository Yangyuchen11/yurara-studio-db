import streamlit as st
import pandas as pd
import math
from services.sales_service import SalesService
from database import SessionLocal

def fragment_if_available(func):
    """兼容性封装：将 UI 拆分为局部组件，使得分页点击只刷新当前组件"""
    if hasattr(st, "fragment"):
        return st.fragment()(func)
    elif hasattr(st, "experimental_fragment"):
        return st.experimental_fragment()(func)
    return func

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_sales_df(test_mode_flag):
    db_cache = st.session_state.get_dynamic_session()
    try:
        raw_logs = SalesService.get_raw_sales_logs(db_cache)
        df = SalesService.process_sales_data(raw_logs)
        return df
    finally:
        db_cache.close()

@fragment_if_available
def render_sales_logs_fragment(df_p, selected_product):
    with st.expander("📝 查看变动日志 (含撤销/退款)", expanded=False):
        # 获取该产品的所有日志
        df_logs_all = df_p.sort_values(by='id', ascending=False).copy()
        total_rows = len(df_logs_all)
        
        if total_rows == 0:
            st.info("暂无变动日志")
        else:
            PAGE_SIZE = 20
            total_pages = math.ceil(total_rows / PAGE_SIZE)
            
            # 使用动态 key，防止切换产品时页码越界报错
            page_key = f"sales_log_page_{selected_product}"
            if page_key not in st.session_state:
                st.session_state[page_key] = 1
            
            # 容错：如果当前页大于总页数，重置为最后一页
            if st.session_state[page_key] > total_pages:
                st.session_state[page_key] = total_pages
                
            current_page = st.session_state[page_key]
            start_idx = (current_page - 1) * PAGE_SIZE
            end_idx = current_page * PAGE_SIZE
            
            # 截取当前页的数据
            df_logs = df_logs_all.iloc[start_idx:end_idx].copy()
            
            def format_type(row):
                if row['type'] == 'sale': return "📤 售出"
                elif row['type'] == 'return': return "↩️ 退货"
                else: return "🔙 撤销"
            
            df_logs['类型'] = df_logs.apply(format_type, axis=1)
            
            df_display = df_logs.rename(columns={
                'date': '日期', 'variant': '款式', 'qty': '变动数量', 
                'amount': '金额', 'currency': '币种', 'platform': '平台'
            })
            
            # 渲染表格，并配置金额列保留两位小数
            st.dataframe(
                df_display[['日期', '类型', '款式', '变动数量', '平台', '金额', '币种']],
                width="stretch",
                hide_index=True,
                column_config={
                    "金额": st.column_config.NumberColumn(format="%.2f")
                }
            )
            
            # 渲染分页按钮
            if total_pages > 1:
                col_btn1, col_btn2, col_page, col_btn3, col_btn4 = st.columns([1, 1, 2, 1, 1])
                with col_btn2:
                    if st.button("⬅️ 上一页", disabled=(current_page == 1), key=f"prev_log_{selected_product}", use_container_width=True):
                        st.session_state[page_key] -= 1
                        st.rerun()  # 💡 这里的 rerun 在 fragment 内部触发，只会刷新本函数！
                with col_page:
                    st.markdown(f"<div style='text-align: center; padding-top: 5px; color: #555;'>第 <b>{current_page}</b> / {total_pages} 页</div>", unsafe_allow_html=True)
                with col_btn3:
                    if st.button("下一页 ➡️", disabled=(current_page == total_pages), key=f"next_log_{selected_product}", use_container_width=True):
                        st.session_state[page_key] += 1
                        st.rerun()  # 💡 同样只会局部刷新

def show_sales_page(db, exchange_rate):
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
    
    # 综合折合总额
    grand_total_cny = total_cny + (total_jpy * exchange_rate)

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("纯 CNY 销售额", f"¥ {total_cny:,.2f}")
        c2.metric("纯 JPY 销售额", f"¥ {total_jpy:,.0f}")
        c3.metric("折合总销售额 (CNY)", f"¥ {grand_total_cny:,.2f}", help=f"当前汇率: {exchange_rate*100}")
        c4.metric("累计净销量", f"{total_qty} 件")
    
    st.divider()

    # === 3. 左右分栏布局 (1:2) ===
    col_nav, col_detail = st.columns([1, 2])

    # --- 左侧：产品总榜 (导航) ---
    with col_nav:
        st.subheader("📋 产品榜单")
        
        # 传入实时汇率计算榜单
        df_prod_summary = SalesService.get_product_leaderboard(df, exchange_rate)
        
        if not df_prod_summary.empty:
            # 将 'product' 列重命名为 '产品名' 用于展示
            df_display = df_prod_summary.rename(columns={'product': '产品名'})
            
            # 显示简略表格
            st.dataframe(
                df_display,
                width="stretch",
                hide_index=True,
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
            p_jpy = df_p[df_p['currency']=='JPY']['amount'].sum()
            # 结合传入的 exchange_rate 计算该产品的折合总额
            p_cny_equiv = p_cny + (p_jpy * exchange_rate)
            
            p_qty = df_p['qty'].sum()
            active_platforms = df_p[df_p['qty'] != 0]['platform'].nunique()
            
            k1, k2, k3 = st.columns(3)
            k1.info(f"净销量: **{p_qty}** 件")
            k2.success(f"折合CNY: **¥{p_cny_equiv:,.2f}**") # 更新文案和变量
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

            # === 底部：变动记录 (带分页的局部组件) ===
            render_sales_logs_fragment(df_p, selected_product)
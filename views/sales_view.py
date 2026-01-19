import streamlit as st
import pandas as pd
from sqlalchemy import func, or_
from models import InventoryLog, Product

def show_sales_page(db):
    st.header("📈 销售数据透视")

    # === 1. 获取数据 (包含销售、退货、撤销) ===
    all_logs = db.query(InventoryLog).filter(
        or_(
            InventoryLog.is_sold == True, 
            InventoryLog.reason == "发货撤销"
        )
    ).order_by(InventoryLog.id.asc()).all()

    if not all_logs:
        st.info("暂无销售数据。")
        return

    # === 2. 数据清洗与标准化处理 ===
    # 将数据库对象转化为扁平的 List[Dict]，方便 Pandas 处理
    raw_data_list = []
    
    # 价格记忆器 (Key: Product_Variant, Value: InfoDict)
    last_sold_info = {}

    for log in all_logs:
        p_key = f"{log.product_name}_{log.variant}"
        
        # 提取基础信息
        item = {
            "id": log.id,
            "date": log.date,
            "product": log.product_name,
            "variant": log.variant,
            "platform": log.platform or "其他/未知", # 默认填充
            "currency": log.currency or "CNY",
            "qty": 0,
            "amount": 0.0,
            "type": "unknown"
        }

        # --- A. 销售 (Sale) ---
        if log.is_sold and log.change_amount < 0:
            item["qty"] = -log.change_amount # 负转正
            item["amount"] = log.sale_amount or 0
            item["type"] = "sale"
            
            # 记忆该款式的成交信息
            last_sold_info[p_key] = {
                "unit_price": (item["amount"] / item["qty"]) if item["qty"] else 0,
                "currency": item["currency"],
                "platform": item["platform"]
            }

        # --- B. 退货 (Return) ---
        elif log.is_sold and log.change_amount > 0:
            item["qty"] = -log.change_amount # 正转负
            item["amount"] = log.sale_amount or 0 # 也是负数
            item["type"] = "return"

        # --- C. 撤销 (Undo) ---
        elif log.reason == "发货撤销":
            # 尝试回溯平台信息 (如果日志里没记)
            if item["platform"] == "其他/未知":
                mem = last_sold_info.get(p_key)
                if mem: item["platform"] = mem["platform"]
            
            deduct_qty = log.change_amount
            item["qty"] = -deduct_qty # 变成负数，抵消销量
            item["type"] = "undo"
            
            # 计算回滚金额
            if log.sale_amount and log.sale_amount != 0:
                item["amount"] = -abs(log.sale_amount)
                item["currency"] = log.currency
            else:
                # 智能估算
                mem = last_sold_info.get(p_key)
                if mem:
                    item["amount"] = -(mem["unit_price"] * deduct_qty)
                    item["currency"] = mem["currency"]
                else:
                    item["amount"] = 0

        raw_data_list.append(item)

    # 创建主 DataFrame
    df = pd.DataFrame(raw_data_list)
    
    # === 3. 全局概览 ===
    if not df.empty:
        total_cny = df[df['currency'] == 'CNY']['amount'].sum()
        total_jpy = df[df['currency'] == 'JPY']['amount'].sum()
        total_qty = df['qty'].sum()
        
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("累计销售额 (CNY)", f"¥ {total_cny:,.2f}")
            c2.metric("累计销售额 (JPY)", f"¥ {total_jpy:,.0f}")
            c3.metric("累计净销量", f"{total_qty} 件")
    
    st.divider()

    # === 4. 左右分栏布局 (1:2) ===
    col_nav, col_detail = st.columns([1, 2])

    # --- 左侧：产品总榜 (导航) ---
    with col_nav:
        st.subheader("📋 产品榜单")
        
        # 按产品聚合
        df_prod_summary = df.groupby('product').agg({
            'amount': lambda x: x[df['currency'] == 'CNY'].sum(), # 简便起见，榜单仅按CNY排序
            'qty': 'sum'
        }).reset_index().rename(columns={'amount': 'CNY总额', 'qty': '净销量'})
        
        df_prod_summary = df_prod_summary.sort_values(by='CNY总额', ascending=False)
        
        # 显示简略表格
        st.dataframe(
            df_prod_summary,
            use_container_width=True,
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
        product_list = df_prod_summary['product'].tolist()
        default_idx = 0 if product_list else None
        
        # 放在 header 位置的选择框
        selected_product = st.selectbox("🔍 选择要深入分析的产品", product_list, index=default_idx)

        if selected_product:
            st.markdown(f"### 📦 {selected_product} 销售详情")
            
            # 筛选该产品的数据
            df_p = df[df['product'] == selected_product].copy()
            
            # 1. 顶部小卡片：该产品的数据
            p_cny = df_p[df_p['currency']=='CNY']['amount'].sum()
            p_qty = df_p['qty'].sum()
            
            k1, k2, k3 = st.columns(3)
            k1.info(f"净销量: **{p_qty}** 件")
            k2.success(f"CNY: **¥{p_cny:,.2f}**")
            
            # 计算该产品涉及的平台数
            active_platforms = df_p[df_p['qty'] != 0]['platform'].nunique()
            k3.warning(f"活跃平台: **{active_platforms}** 个")

            st.divider()

            # === 核心功能：款式 x 平台 透视表 ===
            st.markdown("#### 🧩 款式-平台 交叉透视 (净销量)")
            
            if not df_p.empty:
                # 创建透视表：行=款式，列=平台，值=净销量
                pivot_table = pd.pivot_table(
                    df_p, 
                    values='qty', 
                    index='variant', 
                    columns='platform', 
                    aggfunc='sum', 
                    fill_value=0,
                    margins=True, # 显示总计
                    margins_name='总计'
                )
                
                # 样式优化：高亮显示销量高的格子
                st.dataframe(
                    pivot_table, 
                    use_container_width=True,
                    column_config={
                        col: st.column_config.NumberColumn(format="%d") 
                        for col in pivot_table.columns
                    }
                )
            else:
                st.write("暂无数据")

            # === 可视化：堆叠柱状图 ===
            st.markdown("#### 📊 销量构成可视化")
            
            # 准备绘图数据：去掉 total 行，防止绘图重复
            chart_data = df_p.groupby(['variant', 'platform'])['qty'].sum().reset_index()
            # 过滤掉净销量为0的记录 (比如卖1退1)
            chart_data = chart_data[chart_data['qty'] != 0]
            
            if not chart_data.empty:
                # 使用 Streamlit 原生图表，按款式分组，颜色代表平台
                st.bar_chart(
                    chart_data,
                    x="variant",
                    y="qty",
                    color="platform",
                    stack=True, # 堆叠模式
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
                
                # 选取要显示的列
                display_cols = ['date', 'type', 'variant', 'qty', 'amount', 'currency', 'platform', '类型']
                df_display = df_logs[display_cols].rename(columns={
                    'date': '日期', 'variant': '款式', 'qty': '变动数量', 
                    'amount': '金额', 'currency': '币种', 'platform': '平台'
                })
                
                st.dataframe(
                    df_display[['日期', '类型', '款式', '变动数量', '平台', '金额', '币种']],
                    use_container_width=True,
                    hide_index=True
                )
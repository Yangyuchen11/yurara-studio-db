import streamlit as st
import pandas as pd
from services.product_service import ProductService
from constants import PLATFORM_CODES  # 确保从 constants 导入平台定义

def show_product_page(db):
    # 初始化 Service
    service = ProductService(db)

    # --- 辅助函数：从“颜色/规格”对象的价格列表中提取特定平台价格 ---
    def get_price(color_obj, platform_key):
        if not color_obj or not color_obj.prices:
            return 0.0
        # 遍历该颜色的价格列表
        for p in color_obj.prices:
            if p.platform == platform_key:
                return p.price
        return 0.0

    # --- 0. 全局消息提示逻辑 ---
    if "toast_msg" in st.session_state:
        msg, icon = st.session_state.toast_msg
        st.toast(msg, icon=icon)
        del st.session_state["toast_msg"]

    st.header("商品管理")
    
    tab1, tab2, tab3 = st.tabs(["➕ 新建产品", "✏️ 编辑产品", "📋 产品列表"])
    
    # ================= 模块 1：新建产品 =================
    with tab1:
        st.subheader("新建 - 基础信息")
        
        c1, c2 = st.columns(2)
        new_name = c1.text_input("产品名称 (如：水母睡裙)", key="create_name")
        platform_options = ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他"] 
        new_platform = c2.selectbox("首发平台", platform_options, key="create_platform")
        
        st.divider()
        
        # --- 规格与多平台定价矩阵 ---
        st.subheader("规格与各平台定价")
        st.caption("请在下方表格中添加颜色款式，并直接为每个款式设置各平台价格。")
        
        # 初始化新建用的矩阵数据
        if "create_matrix_df" not in st.session_state:
            # 基础列
            initial_data = {"颜色名称": [""], "预计制作数量": [0]}
            # 动态添加平台价格列
            for pf_key in PLATFORM_CODES.keys():
                initial_data[pf_key] = [0.0]
            st.session_state.create_matrix_df = pd.DataFrame(initial_data)

        # 配置列显示（将平台 Key 映射为中文名称）
        col_config = {
            # 【修复】删除了不支持的 placeholder 参数
            "颜色名称": st.column_config.TextColumn("颜色名称", required=True), 
            "预计制作数量": st.column_config.NumberColumn("预计产量", min_value=0, step=1, format="%d"),
        }
        for pf_key, pf_name in PLATFORM_CODES.items():
            col_config[pf_key] = st.column_config.NumberColumn(f"{pf_name} 价格", min_value=0.0, format="%.2f")

        # 使用数据编辑器
        new_matrix = st.data_editor(
            st.session_state.create_matrix_df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="create_product_editor",
            column_config=col_config
        )

        st.divider()
        
        if st.button("💾 保存新产品", type="primary", key="btn_save_create"):
            # 过滤掉空行
            valid_rows = new_matrix[new_matrix["颜色名称"].str.strip() != ""]
            
            if not new_name:
                st.error("产品名称不能为空")
            elif valid_rows.empty:
                st.error("请至少添加一个颜色规格")
            else:
                try:
                    # 构造符合新 Service 逻辑的数据结构：[{name, qty, prices: {pf: val}}]
                    colors_with_prices = []
                    for _, row in valid_rows.iterrows():
                        color_data = {
                            "name": row["颜色名称"].strip(),
                            "qty": int(row["预计制作数量"]),
                            "prices": {pf_key: float(row[pf_key]) for pf_key in PLATFORM_CODES.keys()}
                        }
                        colors_with_prices.append(color_data)
                    
                    # 调用 Service
                    service.create_product(
                        name=new_name,
                        platform=new_platform,
                        colors_with_prices=colors_with_prices
                    )
                    
                    # 清空缓存
                    if "create_matrix_df" in st.session_state:
                        del st.session_state["create_matrix_df"]
                    
                    st.session_state["toast_msg"] = (f"产品《{new_name}》创建成功！", "✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"创建失败: {e}")

    # ================= 模块 2：编辑产品 =================
    with tab2:
        st.subheader("修改现有产品信息")
        all_products = service.get_all_products()
        
        if not all_products:
            st.info("暂无产品可编辑，请先新建产品。")
        else:
            prod_options = {p.id: p.name for p in all_products}
            selected_prod_id = st.selectbox("选择要编辑的产品", options=list(prod_options.keys()), format_func=lambda x: prod_options[x])
            target_prod = service.get_product_by_id(selected_prod_id)
            
            if target_prod:
                # 准备编辑用的矩阵数据（回填现有数据）
                if st.session_state.get("last_edited_prod_id") != target_prod.id:
                    matrix_data = []
                    for c in target_prod.colors:
                        row = {
                            "颜色名称": c.color_name,
                            "库存/预计数量": c.quantity
                        }
                        # 填充各平台价格
                        for pf_key in PLATFORM_CODES.keys():
                            row[pf_key] = get_price(c, pf_key)
                        matrix_data.append(row)
                    
                    st.session_state.edit_matrix_df = pd.DataFrame(matrix_data)
                    st.session_state.last_edited_prod_id = target_prod.id
                
                edit_name = st.text_input("修改产品名称", value=target_prod.name)
                
                platform_idx = platform_options.index(target_prod.target_platform) if target_prod.target_platform in platform_options else 0
                edit_platform = st.selectbox("首发平台", platform_options, index=platform_idx)

                st.markdown("#### 📊 规格与多平台定价矩阵")
                st.caption("修改规格名称或价格后点击下方的确认修改。")

                # 编辑器的列配置
                edit_col_config = {
                    "颜色名称": st.column_config.TextColumn("颜色名称", required=True),
                    "库存/预计数量": st.column_config.NumberColumn("库存/预计数量", min_value=0, step=1, format="%d"),
                }
                for pf_key, pf_name in PLATFORM_CODES.items():
                    edit_col_config[pf_key] = st.column_config.NumberColumn(pf_name, format="%.2f")

                edited_matrix = st.data_editor(
                    st.session_state.edit_matrix_df,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key="edit_product_matrix",
                    column_config=edit_col_config
                )

                if st.button("💾 确认修改", type="primary", key="btn_save_edit"):
                    valid_edit_rows = edited_matrix[edited_matrix["颜色名称"].str.strip() != ""]
                    
                    if not edit_name:
                        st.error("产品名称不能为空")
                    elif valid_edit_rows.empty:
                        st.error("请至少保留一个规格")
                    else:
                        try:
                            # 调用更新方法，传入包含价格的矩阵 DataFrame
                            service.update_product(
                                product_id=target_prod.id,
                                name=edit_name,
                                platform=edit_platform,
                                color_matrix_data=valid_edit_rows
                            )

                            st.session_state["toast_msg"] = (f"产品《{edit_name}》修改成功！", "✅")
                            if "last_edited_prod_id" in st.session_state:
                                del st.session_state["last_edited_prod_id"]
                            st.rerun()
                        except Exception as e:
                            st.error(f"修改失败: {e}")

    # ================= 模块 3：产品列表 =================
    with tab3:
        st.subheader("现有产品列表")
        products = service.get_all_products()
        
        if products:
            for p in products:
                with st.expander(f"📦 {p.name}"):
                    st.markdown(f"**首发平台**: {p.target_platform} | **制作总数**: {p.total_quantity} 件")
                    
                    st.markdown("#### 🎨 规格与定价详情")
                    
                    # 构建展示表格：每一行是一个款式，每一列是一个平台价格
                    display_data = []
                    for c in p.colors:
                        row = {"规格": c.color_name, "库存/预计": c.quantity}
                        for pf_key, pf_name in PLATFORM_CODES.items():
                            price = get_price(c, pf_key)
                            row[pf_name] = f"¥ {price:,.2f}" if price > 0 else "-"
                        display_data.append(row)
                    
                    st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)

                    st.divider()
                    
                    _, col_delete = st.columns([5, 1])
                    with col_delete:
                        with st.popover("🗑️ 删除产品", use_container_width=True):
                            st.warning(f"确定要删除《{p.name}》吗？")
                            if st.button("确认删除", type="primary", key=f"btn_confirm_del_{p.id}"):
                                try:
                                    service.delete_product(p.id)
                                    st.session_state["toast_msg"] = (f"已删除产品：{p.name}", "🗑️")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"删除失败: {e}")
        else:
            st.info("暂无产品数据")
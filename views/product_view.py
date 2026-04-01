import streamlit as st
import pandas as pd
from services.product_service import ProductService
from constants import PLATFORM_CODES

def show_product_page(db):
    # 初始化 Service
    service = ProductService(db)

    # --- 辅助函数：从“颜色/规格”对象的价格列表中提取特定平台价格 ---
    def get_price(color_obj, platform_key):
        if not color_obj or not color_obj.prices:
            return 0.0
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
        
        # 引入动态版本号，保证保存后组件彻底重置
        if "create_form_ver" not in st.session_state:
            st.session_state.create_form_ver = 0
        c_ver = st.session_state.create_form_ver
        
        c1, c2 = st.columns(2)
        new_name = c1.text_input("产品名称 (如：水母睡裙)", key=f"create_name_{c_ver}")
        platform_options = ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他"] 
        new_platform = c2.selectbox("首发平台", platform_options, key=f"create_platform_{c_ver}")
        
        st.divider()
        
        # --- 1. 规格与多平台定价矩阵 ---
        st.subheader("1. 规格与各平台定价")
        st.caption("请先在此添加颜色款式并设置定价，款式名称将同步给下方的部件设置使用。")
        
        if "create_matrix_df" not in st.session_state:
            initial_data = {"颜色名称": [""], "预计制作数量": [0]}
            for pf_key in PLATFORM_CODES.keys():
                initial_data[pf_key] = [0.0]
            st.session_state.create_matrix_df = pd.DataFrame(initial_data)

        col_config = {
            "颜色名称": st.column_config.TextColumn("颜色名称", required=True), 
            "预计制作数量": st.column_config.NumberColumn("预计产量", min_value=0, step=1, format="%d"),
        }
        for pf_key, pf_name in PLATFORM_CODES.items():
            col_config[pf_key] = st.column_config.NumberColumn(f"{pf_name} 价格", min_value=0.0, format="%.2f")

        new_matrix = st.data_editor(
            st.session_state.create_matrix_df,
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key=f"create_product_editor_{c_ver}", # 动态Key
            column_config=col_config
        )

        st.divider()
        
        # --- 2. 部件设置矩阵 ---
        st.subheader("2. 款式部件设置 (可选)")
        st.caption("在下方表格定义部件及其数量，勾选下方款式即可在保存时自动应用。")
        
        if "create_template_parts_df" not in st.session_state:
            st.session_state.create_template_parts_df = pd.DataFrame([{"部件名称": "", "数量": 1}])
        
        template_parts = st.data_editor(
            st.session_state.create_template_parts_df,
            num_rows="dynamic",
            width="stretch",
            key=f"create_template_editor_{c_ver}", # 动态Key
            column_config={
                "部件名称": st.column_config.TextColumn("部件名称", required=True),
                "数量": st.column_config.NumberColumn("数量", min_value=1, step=1, default=1)
            }
        )
        
        valid_colors = new_matrix[new_matrix["颜色名称"].str.strip() != ""]["颜色名称"].dropna().unique().tolist()
        
        st.markdown("**应用到以下勾选的款式：**")
        selected_colors = []
        if valid_colors:
            rows = (len(valid_colors) + 3) // 4
            for r in range(rows):
                cols = st.columns(4)
                for c in range(4):
                    idx = r * 4 + c
                    if idx < len(valid_colors):
                        color_name = valid_colors[idx]
                        if cols[c].checkbox(color_name, key=f"create_cb_{c_ver}_{color_name}"): # 动态Key
                            selected_colors.append(color_name)
        else:
            st.info("请先在上方规格表格中填写款式名称。")

        st.write("")

        if st.button("💾 保存新产品", type="primary", key=f"btn_save_create_{c_ver}", use_container_width=True):
            valid_rows = new_matrix[new_matrix["颜色名称"].str.strip() != ""]
            if not new_name:
                st.error("产品名称不能为空")
            elif valid_rows.empty:
                st.error("请至少添加一个颜色规格")
            else:
                try:
                    colors_with_prices = []
                    for _, row in valid_rows.iterrows():
                        color_data = {
                            "name": row["颜色名称"].strip(),
                            "qty": int(row["预计制作数量"]),
                            "prices": {pf_key: float(row[pf_key]) for pf_key in PLATFORM_CODES.keys()}
                        }
                        colors_with_prices.append(color_data)
                    
                    parts_df_to_save = pd.DataFrame(columns=["颜色名称", "部件名称", "数量"])
                    valid_tpl = template_parts[template_parts["部件名称"].str.strip() != ""]
                    
                    if selected_colors and not valid_tpl.empty:
                        new_rows = []
                        for c in selected_colors:
                            for _, p_row in valid_tpl.iterrows():
                                new_rows.append({"颜色名称": c, "部件名称": p_row["部件名称"], "数量": p_row["数量"]})
                        parts_df_to_save = pd.DataFrame(new_rows)
                    
                    service.create_product(
                        name=new_name,
                        platform=new_platform,
                        colors_with_prices=colors_with_prices,
                        parts_df=parts_df_to_save
                    )
                    
                    # 清理数据状态并升级版本号，强制销毁旧UI组件
                    if "create_matrix_df" in st.session_state: del st.session_state["create_matrix_df"]
                    if "create_template_parts_df" in st.session_state: del st.session_state["create_template_parts_df"]
                    st.session_state.create_form_ver += 1
                    
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
                # 当产品切换时，重置底层数据 DataFrame
                if st.session_state.get("last_edited_prod_id") != target_prod.id:
                    matrix_data = []
                    for c in target_prod.colors:
                        row = {"颜色名称": c.color_name, "库存/预计数量": c.quantity}
                        for pf_key in PLATFORM_CODES.keys():
                            row[pf_key] = get_price(c, pf_key)
                        matrix_data.append(row)
                    st.session_state.edit_matrix_df = pd.DataFrame(matrix_data)

                    part_data = []
                    for c in target_prod.colors:
                        for p in c.parts:
                            part_data.append({"颜色名称": c.color_name, "部件名称": p.part_name, "数量": p.quantity})
                    st.session_state.edit_parts_df = pd.DataFrame(part_data) if part_data else pd.DataFrame(columns=["颜色名称", "部件名称", "数量"])
                    
                    st.session_state.edit_template_parts_df = pd.DataFrame([{"部件名称": "", "数量": 1}])
                    st.session_state.last_edited_prod_id = target_prod.id
                
                # 以下所有输入组件均绑定 target_prod.id 作为动态 Key
                p_id = target_prod.id
                
                edit_name = st.text_input("修改产品名称", value=target_prod.name, key=f"edit_name_{p_id}")
                platform_idx = platform_options.index(target_prod.target_platform) if target_prod.target_platform in platform_options else 0
                edit_platform = st.selectbox("首发平台", platform_options, index=platform_idx, key=f"edit_platform_{p_id}")

                st.markdown("#### 1. 规格与多平台定价矩阵")
                edit_col_config = {
                    "颜色名称": st.column_config.TextColumn("颜色名称", required=True),
                    "库存/预计数量": st.column_config.NumberColumn("库存/预计数量", min_value=0, step=1, format="%d"),
                }
                for pf_key, pf_name in PLATFORM_CODES.items():
                    edit_col_config[pf_key] = st.column_config.NumberColumn(pf_name, format="%.2f")

                edited_matrix = st.data_editor(
                    st.session_state.edit_matrix_df, num_rows="dynamic", width="stretch", 
                    hide_index=True, key=f"edit_product_matrix_{p_id}", # 动态Key
                    column_config=edit_col_config
                )

                st.markdown("#### 2. 款式部件设置")
                st.caption("在下方表格定义部件及其数量，勾选下方款式即可在保存时覆盖应用原有部件。")
                
                if "edit_template_parts_df" not in st.session_state:
                    st.session_state.edit_template_parts_df = pd.DataFrame([{"部件名称": "", "数量": 1}])
                
                edit_template = st.data_editor(
                    st.session_state.edit_template_parts_df,
                    num_rows="dynamic",
                    width="stretch",
                    key=f"edit_template_editor_{p_id}", # 动态Key
                    column_config={
                        "部件名称": st.column_config.TextColumn("部件名称", required=True),
                        "数量": st.column_config.NumberColumn("数量", min_value=1, step=1, default=1)
                    }
                )
                
                valid_edit_colors = edited_matrix[edited_matrix["颜色名称"].str.strip() != ""]["颜色名称"].dropna().unique().tolist()
                
                st.markdown("**应用到以下勾选的款式：**")
                selected_edit_colors = []
                if valid_edit_colors:
                    rows = (len(valid_edit_colors) + 3) // 4
                    for r in range(rows):
                        cols = st.columns(4)
                        for c in range(4):
                            idx = r * 4 + c
                            if idx < len(valid_edit_colors):
                                color_name = valid_edit_colors[idx]
                                if cols[c].checkbox(color_name, key=f"edit_cb_{p_id}_{color_name}"): # 动态Key
                                    selected_edit_colors.append(color_name)
                else:
                    st.info("请先在上方规格表格中填写款式名称。")

                st.write("")
                
                if st.button("💾 确认修改", type="primary", key=f"btn_save_edit_{p_id}", use_container_width=True):
                    valid_edit_rows = edited_matrix[edited_matrix["颜色名称"].str.strip() != ""]
                    if not edit_name: st.error("产品名称不能为空")
                    elif valid_edit_rows.empty: st.error("请至少保留一个规格")
                    else:
                        try:
                            current_parts = st.session_state.get("edit_parts_df", pd.DataFrame(columns=["颜色名称", "部件名称", "数量"])).copy()
                            valid_tpl = edit_template[edit_template["部件名称"].str.strip() != ""]
                            
                            if selected_edit_colors:
                                current_parts = current_parts[~current_parts["颜色名称"].isin(selected_edit_colors)]
                                if not valid_tpl.empty:
                                    new_rows = []
                                    for c in selected_edit_colors:
                                        for _, p_row in valid_tpl.iterrows():
                                            new_rows.append({"颜色名称": c, "部件名称": p_row["部件名称"], "数量": p_row["数量"]})
                                    current_parts = pd.concat([current_parts, pd.DataFrame(new_rows)], ignore_index=True)
                            
                            service.update_product(
                                product_id=target_prod.id, name=edit_name, platform=edit_platform, 
                                color_matrix_data=valid_edit_rows, parts_df=current_parts
                            )
                            
                            st.session_state["toast_msg"] = (f"产品《{edit_name}》修改成功！", "✅")
                            if "last_edited_prod_id" in st.session_state: del st.session_state["last_edited_prod_id"]
                            st.rerun()
                        except Exception as e:
                            st.error(f"修改失败: {e}")

                st.divider()
                st.markdown("#### 🧩 现有款式与部件明细")
                
                all_p_names_edit = set()
                for c in target_prod.colors:
                    if c.parts:
                        for part in c.parts:
                            all_p_names_edit.add(part.part_name)
                
                if not all_p_names_edit:
                    st.caption("该商品当前暂未设置任何部件")
                else:
                    parts_matrix_edit = []
                    for part_name in sorted(list(all_p_names_edit)):
                        row = {"部件名称": part_name}
                        for c in target_prod.colors:
                            qty = "-" 
                            if c.parts:
                                for part in c.parts:
                                    if part.part_name == part_name:
                                        qty = part.quantity
                                        break
                            row[c.color_name] = qty
                        parts_matrix_edit.append(row)
                        
                    st.dataframe(pd.DataFrame(parts_matrix_edit), width="stretch", hide_index=True)

    # ================= 模块 3：产品列表 =================
    with tab3:
        st.subheader("现有产品列表")
        products = service.get_all_products()
        
        if products:
            for p in products:
                with st.expander(f"📦 {p.name}"):
                    st.markdown(f"**首发平台**: {p.target_platform} | **制作总数**: {p.total_quantity} 件")
                    
                    st.markdown("#### 🎨 规格与定价详情")
                    price_display_data = []
                    for c in p.colors:
                        row = {"规格": c.color_name, "库存/预计": c.quantity}
                        for pf_key, pf_name in PLATFORM_CODES.items():
                            price = get_price(c, pf_key)
                            row[pf_name] = f"¥ {price:,.2f}" if price > 0 else "-"
                        price_display_data.append(row)
                    st.dataframe(pd.DataFrame(price_display_data), width="stretch", hide_index=True)

                    st.markdown("#### 🧩 款式与部件明细")
                    all_part_names = set()
                    for c in p.colors:
                        if c.parts:
                            for part in c.parts:
                                all_part_names.add(part.part_name)
                    
                    if not all_part_names:
                        st.caption("该商品暂未设置任何部件")
                    else:
                        parts_matrix_data = []
                        for part_name in sorted(list(all_part_names)):
                            row = {"部件名称": part_name}
                            for c in p.colors:
                                qty = "-" 
                                if c.parts:
                                    for part in c.parts:
                                        if part.part_name == part_name:
                                            qty = part.quantity
                                            break
                                row[c.color_name] = qty
                            parts_matrix_data.append(row)
                        st.dataframe(pd.DataFrame(parts_matrix_data), width="stretch", hide_index=True)

                    st.divider()
                    _, col_delete = st.columns([5, 1])
                    with col_delete:
                        with st.popover("🗑️ 删除产品", width="stretch"):
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
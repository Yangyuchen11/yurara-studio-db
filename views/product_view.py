# views/product_view.py
import streamlit as st
import pandas as pd
import base64
from io import BytesIO
from PIL import Image
from services.product_service import ProductService
from constants import PLATFORM_CODES

# ================= 🚀 性能优化：局部刷新兼容 =================
if hasattr(st, "fragment"):
    fragment_decorator = st.fragment
else:
    fragment_decorator = st.experimental_fragment

# --- 辅助函数：从“颜色/规格”对象的价格列表中提取特定平台价格 ---
def get_price(color_obj, platform_key):
    if not color_obj or not color_obj.prices:
        return 0.0
    for p in color_obj.prices:
        if p.platform == platform_key:
            return p.price
    return 0.0

# ================= 模块 1：新建产品 (局部刷新) =================
@fragment_decorator
def render_create_tab(db):
    service = ProductService(db)
    
    st.subheader("新建 - 基础信息")
    
    if "create_form_ver" not in st.session_state:
        st.session_state.create_form_ver = 0
    c_ver = st.session_state.create_form_ver
    
    # 快速复制功能
    st.subheader("📋 复制现有商品")
    all_products_for_clone = service.get_all_products()
    if all_products_for_clone:
        c_clone1, c_clone2 = st.columns([3, 1], vertical_alignment="bottom")
        source_prod_id = c_clone1.selectbox(
            "选择要复制的源商品", 
            options=[p.id for p in all_products_for_clone],
            format_func=lambda x: next(p.name for p in all_products_for_clone if p.id == x),
            key=f"clone_source_select_{c_ver}"
        )
        if c_clone2.button("复制内容", use_container_width=True):
            source_prod = service.get_product_by_id(product_id=source_prod_id)
            if source_prod:
                st.session_state[f"create_name_{c_ver}"] = f"{source_prod.name} (复制)"
                st.session_state[f"create_platform_{c_ver}"] = source_prod.target_platform
                
                matrix_data = []
                for c in source_prod.colors:
                    row = {"颜色名称": c.color_name, "预计制作数量": c.quantity}
                    for pf_key in PLATFORM_CODES.keys():
                        row[pf_key] = get_price(c, pf_key)
                    matrix_data.append(row)
                st.session_state.create_matrix_df = pd.DataFrame(matrix_data)
                
                parts_data = []
                if source_prod.colors and source_prod.colors[0].parts:
                    for p in source_prod.colors[0].parts:
                        parts_data.append({"部件名称": p.part_name, "数量": p.quantity})
                if not parts_data:
                    parts_data = [{"部件名称": "", "数量": 1}]
                st.session_state.create_template_parts_df = pd.DataFrame(parts_data)
                
                if "create_image_map_storage" not in st.session_state:
                    st.session_state.create_image_map_storage = {}
                
                cloned_imgs = {}
                for c in source_prod.colors:
                    if getattr(c, 'image_data', None):
                        cloned_imgs[c.color_name] = c.image_data
                st.session_state.create_image_map_storage = cloned_imgs

                st.success(f"已成功复制《{source_prod.name}》的配置！请修改商品名后保存。")
                st.rerun()
    else:
        st.info("暂无现有商品可供复制")

    st.divider()
    
    c1, c2 = st.columns(2)
    new_name = c1.text_input("产品名称 (如：水母睡裙)", key=f"create_name_{c_ver}")
    platform_options = ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他"] 
    new_platform = c2.selectbox("首发平台", platform_options, key=f"create_platform_{c_ver}")
    
    st.divider()
    
    st.subheader("1. 规格与各平台定价")
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
        key=f"create_product_editor_{c_ver}",
        column_config=col_config
    )

    st.markdown("#### 🖼️ 上传款式缩略图 (可选)")
    create_image_map = st.session_state.get("create_image_map_storage", {})
    valid_create_rows = new_matrix[new_matrix["颜色名称"].str.strip() != ""]
    
    if not valid_create_rows.empty:
        v_colors = valid_create_rows["颜色名称"].unique().tolist()
        for r in range(0, len(v_colors), 3):
            cols = st.columns(3)
            for c in range(3):
                if r + c < len(v_colors):
                    c_name = v_colors[r + c]
                    with cols[c]:
                        with st.container(border=True):
                            st.caption(f"🎨 {c_name}")
                            if c_name in create_image_map:
                                st.image(create_image_map[c_name], width=80)
                                if st.button("🗑️ 移除", key=f"rem_cloned_img_{c_name}_{c_ver}"):
                                    del create_image_map[c_name]
                                    st.rerun()
                            
                            up_file = st.file_uploader("上传图片", key=f"create_img_{c_ver}_{c_name}", type=['png', 'jpg', 'jpeg'], label_visibility="collapsed")
                            if up_file:
                                img = Image.open(up_file)
                                if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                                img.thumbnail((100, 100))
                                buffered = BytesIO()
                                img.save(buffered, format="PNG")
                                create_image_map[c_name] = f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"
    
    st.session_state.create_image_map_storage = create_image_map

    st.divider()
    st.subheader("2. 款式部件设置 (可选)")
    if "create_template_parts_df" not in st.session_state:
        st.session_state.create_template_parts_df = pd.DataFrame([{"部件名称": "", "数量": 1}])
    
    template_parts = st.data_editor(
        st.session_state.create_template_parts_df,
        num_rows="dynamic",
        width="stretch",
        key=f"create_template_editor_{c_ver}",
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
                    if cols[c].checkbox(color_name, key=f"create_cb_{c_ver}_{color_name}"):
                        selected_colors.append(color_name)

    if st.button("💾 保存新产品", type="primary", key=f"btn_save_create_{c_ver}", use_container_width=True):
        if not new_name:
            st.error("产品名称不能为空")
        elif valid_create_rows.empty:
            st.error("请至少添加一个颜色规格")
        else:
            try:
                colors_with_prices = []
                for _, row in valid_create_rows.iterrows():
                    color_data = {
                        "name": row["颜色名称"].strip(),
                        "qty": int(row["预计制作数量"]),
                        "prices": {pf_key: float(row[pf_key]) for pf_key in PLATFORM_CODES.keys()},
                        "image_data": create_image_map.get(row["颜色名称"].strip())
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
                
                service.create_product(name=new_name, platform=new_platform, colors_with_prices=colors_with_prices, parts_df=parts_df_to_save)
                
                if "create_matrix_df" in st.session_state: del st.session_state["create_matrix_df"]
                if "create_template_parts_df" in st.session_state: del st.session_state["create_template_parts_df"]
                if "create_image_map_storage" in st.session_state: del st.session_state["create_image_map_storage"]
                st.session_state.create_form_ver += 1
                st.session_state["toast_msg"] = (f"产品《{new_name}》创建成功！", "✅")
                st.rerun()
            except Exception as e:
                st.error(f"创建失败: {e}")

# ================= 模块 2：编辑产品 (局部刷新) =================
@fragment_decorator
def render_edit_tab(db):
    service = ProductService(db)
    
    st.subheader("修改现有产品信息")
    all_products = service.get_all_products()
    
    if not all_products:
        st.info("暂无产品可编辑，请先新建产品。")
        return
        
    prod_options = {p.id: p.name for p in all_products}
    selected_prod_id = st.selectbox("选择要编辑的产品", options=list(prod_options.keys()), format_func=lambda x: prod_options[x])
    target_prod = service.get_product_by_id(selected_prod_id)
    
    if target_prod:
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
        
        p_id = target_prod.id
        edit_name = st.text_input("修改产品名称", value=target_prod.name, key=f"edit_name_{p_id}")
        platform_options = ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他"] 
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
            hide_index=True, key=f"edit_product_matrix_{p_id}",
            column_config=edit_col_config
        )

        st.markdown("#### 2. 款式部件设置")
        if "edit_template_parts_df" not in st.session_state:
            st.session_state.edit_template_parts_df = pd.DataFrame([{"部件名称": "", "数量": 1}])
        
        edit_template = st.data_editor(
            st.session_state.edit_template_parts_df,
            num_rows="dynamic", width="stretch", key=f"edit_template_editor_{p_id}",
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
                        if cols[c].checkbox(color_name, key=f"edit_cb_{p_id}_{color_name}"):
                            selected_edit_colors.append(color_name)

        st.markdown("#### 🖼️ 款式缩略图管理")
        image_map = {}
        current_images = {c.color_name: getattr(c, 'image_data', None) for c in target_prod.colors if getattr(c, 'image_data', None)}
        
        if valid_edit_colors:
            for r in range(0, len(valid_edit_colors), 3):
                cols = st.columns(3)
                for c_idx in range(3):
                    if r + c_idx < len(valid_edit_colors):
                        c_name = valid_edit_colors[r + c_idx]
                        with cols[c_idx]:
                            with st.container(border=True):
                                st.markdown(f"**🎨 {c_name}**")
                                existing_img = current_images.get(c_name)
                                
                                del_check = False
                                if existing_img:
                                    st.image(existing_img, use_container_width=True)
                                    del_check = st.checkbox("🗑️ 删除此图片", key=f"del_img_chk_{p_id}_{c_name}")
                                else:
                                    st.markdown("<div style='height: 80px; display: flex; align-items: center; justify-content: center; color: gray; background-color: #f0f2f6; border-radius: 5px; margin-bottom: 10px;'>暂无图片</div>", unsafe_allow_html=True)
                                
                                uploaded_file = st.file_uploader(f"更新图片", key=f"img_up_{p_id}_{c_name}", type=['png', 'jpg', 'jpeg'], label_visibility="collapsed")
                                
                                if uploaded_file:
                                    try:
                                        img = Image.open(uploaded_file)
                                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                                        img.thumbnail((100, 100))
                                        buffered = BytesIO()
                                        img.save(buffered, format="PNG")
                                        image_map[c_name] = f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"
                                    except Exception as e:
                                        st.error(f"失败: {e}")
                                        image_map[c_name] = existing_img
                                elif del_check:
                                    image_map[c_name] = None
                                else:
                                    image_map[c_name] = existing_img

        st.write("")
        if st.button("💾 确认修改", type="primary", key=f"btn_save_edit_{p_id}", use_container_width=True):
            valid_edit_rows_final = edited_matrix[edited_matrix["颜色名称"].str.strip() != ""]
            if not edit_name: st.error("产品名称不能为空")
            elif valid_edit_rows_final.empty: st.error("请至少保留一个规格")
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
                    
                    service.update_product(product_id=target_prod.id, name=edit_name, platform=edit_platform, color_matrix_data=valid_edit_rows_final, parts_df=current_parts, image_map=image_map)
                    
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
                for part in c.parts: all_p_names_edit.add(part.part_name)
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
                            if part.part_name == part_name: qty = part.quantity; break
                    row[c.color_name] = qty
                parts_matrix_edit.append(row)
            st.dataframe(pd.DataFrame(parts_matrix_edit), width="stretch", hide_index=True)

# ================= 模块 3：产品列表 (局部刷新) =================
@fragment_decorator
def render_list_tab(db):
    service = ProductService(db)
    
    st.subheader("现有产品列表")
    products = service.get_all_products()
    if products:
        for p in products:
            with st.expander(f"📦 {p.name}"):
                st.markdown(f"**首发平台**: {p.target_platform} | **制作总数**: {p.total_quantity} 件")
                
                colors_with_img = [c for c in p.colors if getattr(c, 'image_data', None)]
                if colors_with_img:
                    st.markdown("#### 🖼️ 款式缩略图预览")
                    for r in range(0, len(colors_with_img), 4):
                        cols = st.columns(4)
                        for c_idx in range(4):
                            if r + c_idx < len(colors_with_img):
                                color_obj = colors_with_img[r + c_idx]
                                with cols[c_idx]:
                                    with st.container(border=True):
                                        st.image(color_obj.image_data, use_container_width=True)
                                        st.markdown(f"<div style='text-align: center; color: gray; font-size: 13px;'>{color_obj.color_name}</div>", unsafe_allow_html=True)

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
                        for part in c.parts: all_part_names.add(part.part_name)
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
                                    if part.part_name == part_name: qty = part.quantity; break
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

# ================= 主函数入口 =================
def show_product_page(db):
    # --- 0. 全局消息提示逻辑 ---
    if "toast_msg" in st.session_state:
        msg, icon = st.session_state.toast_msg
        st.toast(msg, icon=icon)
        del st.session_state["toast_msg"]

    st.header("商品管理")
    
    tab1, tab2, tab3 = st.tabs(["➕ 新建产品", "✏️ 编辑产品", "📋 产品列表"])
    
    with tab1:
        render_create_tab(db)
        
    with tab2:
        render_edit_tab(db)
        
    with tab3:
        render_list_tab(db)
import streamlit as st
import pandas as pd
from models import Product, ProductColor

def show_product_page(db):
    # --- 0. 全局消息提示逻辑 ---
    if "toast_msg" in st.session_state:
        msg, icon = st.session_state.toast_msg
        st.toast(msg, icon=icon)
        del st.session_state["toast_msg"]

    st.header("商品管理")
    
    # 修改点：增加“编辑产品”标签页
    tab1, tab2, tab3 = st.tabs(["➕ 新建产品", "✏️ 编辑产品", "📋 产品列表"])
    
    # ================= 模块 1：新建产品 (保持原样，略微优化变量名) =================
    with tab1:
        st.subheader("新建 - 基础信息")
        
        c1, c2 = st.columns(2)
        new_name = c1.text_input("产品名称 (如：水母睡裙)", key="create_name")
        
        platform_options = ["微店", "Booth", "日本线下", "中国线下", "其他"]
        new_platform = c2.selectbox("首发平台", platform_options, key="create_platform")
        
        st.divider()
        
        # --- 颜色配置 (新建模式) ---
        st.subheader("颜色规格")
        st.caption("输入颜色名称并点击“添加”按钮。")
        
        if "create_temp_colors" not in st.session_state:
            st.session_state.create_temp_colors = []

        col_input, col_btn = st.columns([3, 1])
        color_input_val = col_input.text_input("输入颜色名称", key="create_color_input")
        
        if col_btn.button("➕ 添加", key="btn_add_color_create"):
            if color_input_val.strip():
                if color_input_val.strip() not in st.session_state.create_temp_colors:
                    st.session_state.create_temp_colors.append(color_input_val.strip())
                else:
                    st.toast("颜色已存在", icon="⚠️")
            else:
                st.toast("请输入颜色名称", icon="⚠️")

        if st.session_state.create_temp_colors:
            st.write("已添加颜色：")
            st.code("  ".join(st.session_state.create_temp_colors), language="text")
            if st.button("清空列表", key="btn_clear_color_create"):
                st.session_state.create_temp_colors = []
                st.rerun()
        else:
            st.info("暂未添加颜色")

        st.divider()

        # --- 定价策略 (新建模式) ---
        st.subheader("多平台定价")
        p1, p2, p3, p4, p5 = st.columns(5)
        price_w = p1.number_input("微店 (CNY)", min_value=0.0, key="create_p_w")
        price_b = p2.number_input("Booth (JPY)", min_value=0.0, key="create_p_b")
        price_jp = p3.number_input("日本线下 (JPY)", min_value=0.0, key="create_p_jp")
        price_cn = p4.number_input("中国线下 (CNY)", min_value=0.0, key="create_p_cn")
        price_other = p5.number_input("其他 (CNY)", min_value=0.0, key="create_p_other")
        
        st.divider()
        
        if st.button("💾 保存新产品", type="primary", key="btn_save_create"):
            if not new_name:
                st.error("产品名称不能为空")
            elif not st.session_state.create_temp_colors:
                st.error("请至少添加一个颜色")
            else:
                # 1. 创建主表
                new_prod = Product(
                    name=new_name,
                    target_platform=new_platform,
                    price_weidian=price_w,
                    price_booth=price_b,
                    price_offline_jp=price_jp,
                    price_offline_cn=price_cn,
                    price_other=price_other,
                    total_quantity=0
                )
                db.add(new_prod)
                db.flush()
                
                # 2. 插入颜色
                for c_name in st.session_state.create_temp_colors:
                    db.add(ProductColor(product_id=new_prod.id, color_name=c_name, quantity=0))
                
                db.commit()
                
                st.session_state.create_temp_colors = []
                st.session_state["toast_msg"] = (f"产品《{new_name}》创建成功！", "✅")
                st.rerun()

    # ================= 模块 2：编辑产品 (新增功能) =================
    with tab2:
        st.subheader("修改现有产品信息")
        
        # 1. 获取所有产品用于选择
        all_products = db.query(Product).order_by(Product.id.desc()).all()
        
        if not all_products:
            st.info("暂无产品可编辑，请先新建产品。")
        else:
            # 生成选择映射字典 {id: name}
            prod_options = {p.id: f"{p.name} (ID: {p.id})" for p in all_products}
            selected_prod_id = st.selectbox("选择要编辑的产品", options=list(prod_options.keys()), format_func=lambda x: prod_options[x])
            
            # 获取当前选中的产品对象
            target_prod = db.query(Product).filter(Product.id == selected_prod_id).first()
            
            if target_prod:
                st.divider()
                
                # --- A. 颜色数据初始化逻辑 (关键) ---
                # 当切换了选中的产品时，我们需要把数据库里的颜色加载到 session_state 中
                # 使用 'edit_last_id' 来判断是否切换了产品
                if "edit_colors" not in st.session_state:
                    st.session_state.edit_colors = []
                
                if "edit_last_id" not in st.session_state or st.session_state.edit_last_id != selected_prod_id:
                    # 发生了切换，从数据库重新加载颜色
                    db_colors = db.query(ProductColor).filter(ProductColor.product_id == selected_prod_id).all()
                    st.session_state.edit_colors = [c.color_name for c in db_colors]
                    st.session_state.edit_last_id = selected_prod_id

                # --- B. 基础信息回显与修改 ---
                ec1, ec2 = st.columns(2)
                # 使用 value 参数进行回显
                edit_name = ec1.text_input("产品名称", value=target_prod.name, key="edit_name")
                
                # 处理下拉框回显，需要找到 index
                platform_idx = 0
                if target_prod.target_platform in platform_options:
                    platform_idx = platform_options.index(target_prod.target_platform)
                edit_platform = ec2.selectbox("首发平台", platform_options, index=platform_idx, key="edit_platform")

                # --- C. 颜色修改逻辑 ---
                st.markdown("#### 颜色规格修改")
                ec_input, ec_btn = st.columns([3, 1])
                edit_color_in = ec_input.text_input("新增颜色", key="edit_color_input")
                
                if ec_btn.button("➕ 添加", key="btn_add_color_edit"):
                    if edit_color_in.strip():
                        if edit_color_in.strip() not in st.session_state.edit_colors:
                            st.session_state.edit_colors.append(edit_color_in.strip())
                        else:
                            st.toast("颜色已存在", icon="⚠️")
                
                # 显示当前颜色列表
                if st.session_state.edit_colors:
                    st.write("当前颜色列表 (保存后生效):")
                    st.code("  ".join(st.session_state.edit_colors), language="text")
                    
                    # 颜色重置按钮 (恢复到数据库状态 或 清空)
                    col_rst1, col_rst2 = st.columns([1, 4])
                    if col_rst1.button("重置/清空", key="btn_clear_color_edit"):
                        st.session_state.edit_colors = []
                        st.rerun()
                else:
                    st.warning("⚠️ 当前列表为空，保存将删除所有颜色规格！")

                # --- D. 价格修改 ---
                st.markdown("#### 定价策略修改")
                ep1, ep2, ep3, ep4, ep5 = st.columns(5)
                e_price_w = ep1.number_input("微店", min_value=0.0, value=target_prod.price_weidian, key="edit_p_w")
                e_price_b = ep2.number_input("Booth", min_value=0.0, value=target_prod.price_booth, key="edit_p_b")
                e_price_jp = ep3.number_input("日本线下", min_value=0.0, value=target_prod.price_offline_jp, key="edit_p_jp")
                e_price_cn = ep4.number_input("中国线下", min_value=0.0, value=target_prod.price_offline_cn, key="edit_p_cn")
                e_price_other = ep5.number_input("其他", min_value=0.0, value=target_prod.price_other, key="edit_p_other")

                st.divider()

                # --- E. 保存逻辑 ---
                if st.button("💾 确认修改", type="primary", key="btn_save_edit"):
                    if not edit_name:
                        st.error("产品名称不能为空")
                    elif not st.session_state.edit_colors:
                        st.error("请至少保留一个颜色")
                    else:
                        # 1. 更新主表字段
                        target_prod.name = edit_name
                        target_prod.target_platform = edit_platform
                        target_prod.price_weidian = e_price_w
                        target_prod.price_booth = e_price_b
                        target_prod.price_offline_jp = e_price_jp
                        target_prod.price_offline_cn = e_price_cn
                        target_prod.price_other = e_price_other
                        
                        # 2. 更新颜色表 (策略：删除旧的 -> 插入新的)
                        # 这样处理比较简单，但注意：这会重置颜色的 quantity (库存)。
                        # 如果需要保留库存数量，逻辑会更复杂（需要对比新旧列表）。
                        # *此处假设修改规格会重置库存，或者库存管理在另一处*
                        # 为了保留库存，我们优化一下逻辑：
                        
                        # A. 获取现有数据库中的颜色对象 {name: object}
                        existing_db_colors = db.query(ProductColor).filter(ProductColor.product_id == target_prod.id).all()
                        existing_map = {c.color_name: c for c in existing_db_colors}
                        
                        current_edit_list = st.session_state.edit_colors
                        
                        # B. 删除：在数据库中有，但在编辑列表中没有的
                        for c_obj in existing_db_colors:
                            if c_obj.color_name not in current_edit_list:
                                db.delete(c_obj)
                        
                        # C. 新增：在编辑列表中有，但在数据库中没有的
                        for c_name in current_edit_list:
                            if c_name not in existing_map:
                                db.add(ProductColor(product_id=target_prod.id, color_name=c_name, quantity=0))
                            # 如果已经在数据库中，则保持不动 (保留了原有的 quantity)
                        
                        db.commit()
                        st.session_state["toast_msg"] = (f"产品《{edit_name}》修改成功！", "✅")
                        
                        # 清除缓存ID，强制下次刷新数据
                        if "edit_last_id" in st.session_state:
                            del st.session_state["edit_last_id"]
                        st.rerun()

    # ================= 模块 3：产品列表与删除 (保持原有逻辑) =================
    with tab3:
        st.subheader("现有产品列表")
        products = db.query(Product).order_by(Product.id.desc()).all()
        
        if products:
            for p in products:
                with st.expander(f"📦 {p.name}"):
                    col_a, col_b = st.columns([1, 1])
                    
                    with col_a:
                        st.markdown("#### 🏷️ 基础信息")
                        st.write(f"**首发平台**: {p.target_platform}")
                        st.caption("定价明细")
                        price_data = {
                            "渠道": ["微店", "Booth", "日本线下", "中国线下", "其他"],
                            "价格": [
                                f"¥ {p.price_weidian}", 
                                f"¥ {p.price_booth} (JPY)",
                                f"¥ {p.price_offline_jp} (JPY)",
                                f"¥ {p.price_offline_cn}",
                                f"¥ {p.price_other}"
                            ]
                        }
                        st.dataframe(pd.DataFrame(price_data), use_container_width=True, hide_index=True)
                    
                    with col_b:
                        st.markdown("#### 🎨 颜色规格")
                        p_colors = db.query(ProductColor).filter(ProductColor.product_id == p.id).all()
                        if p_colors:
                            color_names = [c.color_name for c in p_colors]
                            tags_html = "".join([
                                f'<span style="background-color:#3E3E3E; border:1px solid #666666; padding:4px 12px; border-radius:15px; margin:4px; display:inline-block; color:#FFFFFF; font-weight:bold; font-size:14px;">{name}</span>' 
                                for name in color_names
                            ])
                            st.markdown(tags_html, unsafe_allow_html=True)
                        else:
                            st.caption("暂无颜色规格")

                    st.divider()
                    
                    _, col_delete = st.columns([5, 1])
                    with col_delete:
                        with st.popover("🗑️ 删除产品", use_container_width=True):
                            st.warning(f"⚠️ 确定要删除《{p.name}》吗？")
                            if st.button("确认删除", type="primary", key=f"btn_confirm_del_{p.id}"):
                                try:
                                    db.delete(p)
                                    db.commit()
                                    st.session_state["toast_msg"] = (f"已删除产品：{p.name}", "🗑️")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"删除失败: {e}")

        else:
            st.info("暂无产品数据")
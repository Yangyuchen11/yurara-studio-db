import streamlit as st
import pandas as pd
from services.product_service import ProductService

def show_product_page(db):
    # 初始化 Service
    service = ProductService(db)

    # --- 辅助函数：从产品对象的价格列表中提取特定平台价格 ---
    def get_price(product_obj, platform_key):
        if not product_obj or not product_obj.prices:
            return 0.0
        # 遍历查找
        for p in product_obj.prices:
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
    
    # ================= 模块 1：新建产品 (保持不变，只是Service调用内部变了) =================
    with tab1:
        st.subheader("新建 - 基础信息")
        
        c1, c2 = st.columns(2)
        new_name = c1.text_input("产品名称 (如：水母睡裙)", key="create_name")
        platform_options = ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他"] 
        new_platform = c2.selectbox("首发平台", platform_options, key="create_platform")
        
        st.divider()
        
        # --- 颜色与预计产量配置 ---
        st.subheader("规格与预计制作数量")
        if "create_temp_colors" not in st.session_state:
            st.session_state.create_temp_colors = [] 

        col_n, col_q, col_b = st.columns([2, 2, 1])

        with col_n:
            c_name = st.text_input("颜色名称", key="c_color_name", placeholder="如：水母蓝")

        with col_q:
            c_qty = st.number_input("预计制作数量", min_value=0, step=1, key="c_color_qty")

        with col_b:
            st.markdown('<div style="margin-top:28px;"></div>', unsafe_allow_html=True) 
            if st.button("➕ 添加规格", key="btn_add_color_create", use_container_width=True):
                if c_name.strip():
                    if any(d['name'] == c_name.strip() for d in st.session_state.create_temp_colors):
                        st.toast("该颜色已在列表中", icon="⚠️")
                    else:
                        st.session_state.create_temp_colors.append({"name": c_name.strip(), "qty": c_qty})
                        st.rerun() 
                else:
                    st.toast("请输入颜色名称", icon="⚠️")

        if st.session_state.create_temp_colors:
            df_temp = pd.DataFrame(st.session_state.create_temp_colors)
            df_temp.columns = ["颜色名称", "预计产量"]
            st.table(df_temp)
            if st.button("清空规格列表", key="btn_clear_color_create"):
                st.session_state.create_temp_colors = []
                st.rerun()

        st.divider()

        # --- 定价策略 ---
        st.subheader("多平台定价")
        
        st.caption("🇨🇳 人民币 (CNY) 定价")
        p_cn1, p_cn2, p_cn3 = st.columns(3)
        price_w = p_cn1.number_input("微店 (CNY)", min_value=0.0, key="create_p_w")
        price_cn = p_cn2.number_input("中国线下 (CNY)", min_value=0.0, key="create_p_cn")
        price_other = p_cn3.number_input("其他 (CNY)", min_value=0.0, key="create_p_other")

        st.caption("🇯🇵 日元 (JPY) 定价")
        p_jp1, p_jp2, p_jp3, p_jp4 = st.columns(4)
        price_b = p_jp1.number_input("Booth (JPY)", min_value=0.0, key="create_p_b")
        price_insta = p_jp2.number_input("Instagram (JPY)", min_value=0.0, key="create_p_insta")
        price_jp = p_jp3.number_input("日本线下 (JPY)", min_value=0.0, key="create_p_jp")
        price_other_jpy = p_jp4.number_input("其他 (JPY)", min_value=0.0, key="create_p_other_jpy")
        
        st.divider()
        
        if st.button("💾 保存新产品", type="primary", key="btn_save_create"):
            if not new_name:
                st.error("产品名称不能为空")
            elif not st.session_state.create_temp_colors:
                st.error("请至少添加一个颜色")
            else:
                try:
                    # 封装价格字典 (Key 对应 ProductService 中的 map)
                    prices = {
                        "weidian": price_w,
                        "offline_cn": price_cn,
                        "other": price_other,
                        "booth": price_b,
                        "instagram": price_insta,
                        "offline_jp": price_jp,
                        "other_jpy": price_other_jpy
                    }
                    
                    # 调用 Service
                    new_prod = service.create_product(
                        name=new_name,
                        platform=new_platform,
                        prices=prices,
                        colors=st.session_state.create_temp_colors
                    )
                    
                    st.session_state.create_temp_colors = []
                    st.session_state["toast_msg"] = (f"产品《{new_name}》创建成功！", "✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"创建失败: {e}")

    # ================= 模块 2：编辑产品 =================
    with tab2:
        st.subheader("修改现有产品信息")
        
        # 使用 Service 获取列表
        all_products = service.get_all_products()
        
        if not all_products:
            st.info("暂无产品可编辑，请先新建产品。")
        else:
            prod_options = {p.id: p.name for p in all_products}
            selected_prod_id = st.selectbox("选择要编辑的产品", options=list(prod_options.keys()), format_func=lambda x: prod_options[x])
            
            # 使用 Service 获取详情
            target_prod = service.get_product_by_id(selected_prod_id)
            
            if target_prod:
                # 【关键修改】数据回填逻辑：从 prices 列表读取
                if st.session_state.get("last_edited_prod_id") != target_prod.id:
                    st.session_state["edit_name"] = target_prod.name
                    st.session_state["edit_platform"] = target_prod.target_platform
                    
                    # 使用辅助函数读取价格
                    st.session_state["edit_p_w"] = get_price(target_prod, "weidian")
                    st.session_state["edit_p_cn"] = get_price(target_prod, "offline_cn")
                    st.session_state["edit_p_other"] = get_price(target_prod, "other")
                    
                    st.session_state["edit_p_b"] = get_price(target_prod, "booth")
                    st.session_state["edit_p_insta"] = get_price(target_prod, "instagram")
                    st.session_state["edit_p_jp"] = get_price(target_prod, "offline_jp")
                    st.session_state["edit_p_other_jpy"] = get_price(target_prod, "other_jpy")
                    
                    st.session_state["last_edited_prod_id"] = target_prod.id
                
                st.divider()
                
                # --- A. 基础信息 ---
                ec1, ec2 = st.columns(2)
                edit_name = ec1.text_input("修改产品名称", value=target_prod.name)
                
                platform_idx = 0
                if target_prod.target_platform in platform_options:
                    platform_idx = platform_options.index(target_prod.target_platform)
                edit_platform = ec2.selectbox("首发平台", platform_options, index=platform_idx, key="edit_platform")

                # --- B. 规格与数量修改 ---
                st.markdown("#### 🎨 规格与数量管理")
                st.caption("请直接在下方表格中修改名称、数量，或添加/删除行。")

                if "edit_specs_df" not in st.session_state or st.session_state.get("edit_last_id") != selected_prod_id:
                    db_colors = service.get_product_colors(selected_prod_id)
                    data = [{"颜色名称": c.color_name, "库存/预计数量": c.quantity} for c in db_colors]
                    st.session_state.edit_specs_df = pd.DataFrame(data)
                    st.session_state.edit_last_id = selected_prod_id

                edited_df = st.data_editor(
                    st.session_state.edit_specs_df,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key="editor_specs",
                    column_config={
                        "颜色名称": st.column_config.TextColumn(required=True),
                        "库存/预计数量": st.column_config.NumberColumn(min_value=0, step=1, required=True, format="%d")
                    }
                )

                # --- C. 价格修改 ---
                st.markdown("#### 定价策略修改")
                
                # 从 Session State 读取初始值 (已由上方逻辑填充)
                st.caption("🇨🇳 CNY")
                ep_cn1, ep_cn2, ep_cn3 = st.columns(3)
                e_price_w = ep_cn1.number_input("微店", min_value=0.0, key="edit_p_w")
                e_price_cn = ep_cn2.number_input("中国线下", min_value=0.0, key="edit_p_cn")
                e_price_other = ep_cn3.number_input("其他 (CNY)", min_value=0.0, key="edit_p_other")

                st.caption("🇯🇵 JPY")
                ep_jp1, ep_jp2, ep_jp3, ep_jp4 = st.columns(4)
                e_price_b = ep_jp1.number_input("Booth", min_value=0.0, key="edit_p_b")
                e_price_insta = ep_jp2.number_input("Instagram", min_value=0.0, key="edit_p_insta")
                e_price_jp = ep_jp3.number_input("日本线下", min_value=0.0, key="edit_p_jp")
                e_price_other_jpy = ep_jp4.number_input("其他 (JPY)", min_value=0.0, key="edit_p_other_jpy")

                st.divider()

                # --- D. 保存逻辑 ---
                if st.button("💾 确认修改", type="primary", key="btn_save_edit"):
                    if not edit_name:
                        st.error("产品名称不能为空")
                    elif edited_df.empty:
                        st.error("请至少保留一个颜色规格")
                    else:
                        try:
                            # 封装价格
                            prices = {
                                "weidian": e_price_w,
                                "offline_cn": e_price_cn,
                                "other": e_price_other,
                                "booth": e_price_b,
                                "instagram": e_price_insta,
                                "offline_jp": e_price_jp,
                                "other_jpy": e_price_other_jpy
                            }
                            
                            # 调用 Service 更新
                            service.update_product(
                                product_id=target_prod.id,
                                name=edit_name,
                                platform=edit_platform,
                                prices=prices,
                                colors_df=edited_df
                            )

                            st.session_state["toast_msg"] = (f"产品《{edit_name}》修改成功！", "✅")
                            
                            if "edit_last_id" in st.session_state:
                                del st.session_state["edit_last_id"]
                            
                            st.rerun()
                        except Exception as e:
                            st.error(f"修改失败: {e}")

    # ================= 模块 3：产品列表 =================
    with tab3:
        st.subheader("现有产品列表")
        # 这里的 products 已经 eager load 了 prices
        products = service.get_all_products()
        
        if products:
            for p in products:
                with st.expander(f"📦 {p.name}"):
                    col_a, col_b = st.columns([1, 1])
                    
                    with col_a:
                        st.markdown("#### 🏷️ 基础信息")
                        st.write(f"**首发平台**: {p.target_platform}")
                        st.write(f"**制作总数**: {p.total_quantity} 件")
                        
                        st.caption("定价明细")
                        # 【关键修改】从 prices 关系中读取显示
                        price_data = {
                            "渠道": ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他(CNY)", "其他(JPY)"],
                            "价格": [
                                f"¥ {get_price(p, 'weidian')}", 
                                f"¥ {get_price(p, 'booth')} (JPY)",
                                f"¥ {get_price(p, 'instagram')} (JPY)",
                                f"¥ {get_price(p, 'offline_jp')} (JPY)",
                                f"¥ {get_price(p, 'offline_cn')}",
                                f"¥ {get_price(p, 'other')}",
                                f"¥ {get_price(p, 'other_jpy')} (JPY)"
                            ]
                        }
                        st.dataframe(pd.DataFrame(price_data), use_container_width=True, hide_index=True)
                    
                    with col_b:
                        st.markdown("#### 🎨 规格明细")
                        # p.colors 已经预加载了
                        if p.colors:
                            tags_html = "".join([
                                f'<span style="background-color:#3E3E3E; border:1px solid #666666; padding:4px 12px; border-radius:15px; margin:4px; display:inline-block; color:#FFFFFF; font-size:14px;">'
                                f'<b>{c.color_name}</b> <span style="color:#aaa; font-size:12px; margin-left:5px;">x{c.quantity}</span>'
                                f'</span>' 
                                for c in p.colors
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
                                    service.delete_product(p.id)
                                    st.session_state["toast_msg"] = (f"已删除产品：{p.name}", "🗑️")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"删除失败: {e}")
        else:
            st.info("暂无产品数据")
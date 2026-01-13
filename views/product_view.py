import streamlit as st
import pandas as pd
from models import Product, ProductColor, InventoryLog
from datetime import datetime

def show_product_page(db):
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
                # 1. 计算总数量
                total_q = sum([item['qty'] for item in st.session_state.create_temp_colors])

                # 2. 创建主表
                new_prod = Product(
                    name=new_name,
                    target_platform=new_platform,
                    price_weidian=price_w,
                    price_booth=price_b,
                    price_offline_jp=price_jp,
                    price_offline_cn=price_cn,
                    price_other=price_other,
                    price_instagram=price_insta,
                    price_other_jpy=price_other_jpy,
                    total_quantity=total_q,
                    # 初始化可销售数量等于总预计数量
                    marketable_quantity=total_q
                )
                db.add(new_prod)
                db.flush()
                
                # 3. 插入颜色
                for item in st.session_state.create_temp_colors:
                    db.add(ProductColor(
                        product_id=new_prod.id, 
                        color_name=item['name'],
                        quantity=item['qty'] # 这里只记录设定数量，不产生库存日志
                    ))
                    
                    # 【修改点】：删除了原先这里的 InventoryLog 预入库代码
                    # 现在的逻辑是：只设定目标，不产生流水，不影响资产
                
                db.commit()
                
                st.session_state.create_temp_colors = []
                st.session_state["toast_msg"] = (f"产品《{new_name}》创建成功！", "✅")
                st.rerun()

    # ================= 模块 2：编辑产品 =================
    with tab2:
        st.subheader("修改现有产品信息")
        
        all_products = db.query(Product).order_by(Product.id.desc()).all()
        
        if not all_products:
            st.info("暂无产品可编辑，请先新建产品。")
        else:
            prod_options = {p.id: p.name for p in all_products}
            selected_prod_id = st.selectbox("选择要编辑的产品", options=list(prod_options.keys()), format_func=lambda x: prod_options[x])
            
            target_prod = db.query(Product).filter(Product.id == selected_prod_id).first()
            
            if target_prod:
                st.divider()
                
                # --- A. 基础信息 ---
                ec1, ec2 = st.columns(2)
                edit_name = ec1.text_input("产品名称", value=target_prod.name, key="edit_name")
                
                platform_idx = 0
                if target_prod.target_platform in platform_options:
                    platform_idx = platform_options.index(target_prod.target_platform)
                edit_platform = ec2.selectbox("首发平台", platform_options, index=platform_idx, key="edit_platform")

                # --- B. 规格与数量修改 (使用 DataEditor) ---
                st.markdown("#### 🎨 规格与数量管理")
                st.caption("请直接在下方表格中修改名称、数量，或添加/删除行。")

                # 初始化数据：如果切换了产品，重新从数据库加载
                if "edit_specs_df" not in st.session_state or st.session_state.get("edit_last_id") != selected_prod_id:
                    db_colors = db.query(ProductColor).filter(ProductColor.product_id == selected_prod_id).all()
                    # 构造 DataFrame
                    data = [{"颜色名称": c.color_name, "库存/预计数量": c.quantity} for c in db_colors]
                    st.session_state.edit_specs_df = pd.DataFrame(data)
                    st.session_state.edit_last_id = selected_prod_id

                # 显示可编辑表格
                edited_df = st.data_editor(
                    st.session_state.edit_specs_df,
                    num_rows="dynamic", # 允许添加/删除行
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
                
                st.caption("🇨🇳 CNY")
                ep_cn1, ep_cn2, ep_cn3 = st.columns(3)
                e_price_w = ep_cn1.number_input("微店", min_value=0.0, value=target_prod.price_weidian, key="edit_p_w")
                e_price_cn = ep_cn2.number_input("中国线下", min_value=0.0, value=target_prod.price_offline_cn, key="edit_p_cn")
                e_price_other = ep_cn3.number_input("其他 (CNY)", min_value=0.0, value=target_prod.price_other, key="edit_p_other")

                st.caption("🇯🇵 JPY")
                ep_jp1, ep_jp2, ep_jp3, ep_jp4 = st.columns(4)
                e_price_b = ep_jp1.number_input("Booth", min_value=0.0, value=target_prod.price_booth, key="edit_p_b")
                e_price_insta = ep_jp2.number_input("Instagram", min_value=0.0, value=getattr(target_prod, 'price_instagram', 0.0), key="edit_p_insta")
                e_price_jp = ep_jp3.number_input("日本线下", min_value=0.0, value=target_prod.price_offline_jp, key="edit_p_jp")
                e_price_other_jpy = ep_jp4.number_input("其他 (JPY)", min_value=0.0, value=getattr(target_prod, 'price_other_jpy', 0.0), key="edit_p_other_jpy")

                st.divider()

                # --- D. 保存逻辑 ---
                if st.button("💾 确认修改", type="primary", key="btn_save_edit"):
                    if not edit_name:
                        st.error("产品名称不能为空")
                    elif edited_df.empty:
                        st.error("请至少保留一个颜色规格")
                    else:
                        # 1. 更新主表基础信息
                        target_prod.name = edit_name
                        target_prod.target_platform = edit_platform
                        target_prod.price_weidian = e_price_w
                        target_prod.price_booth = e_price_b
                        target_prod.price_offline_jp = e_price_jp
                        target_prod.price_offline_cn = e_price_cn
                        target_prod.price_other = e_price_other
                        target_prod.price_instagram = e_price_insta
                        target_prod.price_other_jpy = e_price_other_jpy
                        
                        # 2. 更新颜色规格 (策略：清空旧的 -> 写入新的)
                        # 先删除该产品所有旧规格
                        db.query(ProductColor).filter(ProductColor.product_id == target_prod.id).delete()
                        
                        new_total_qty = 0
                        # 写入 DataEditor 中的新数据
                        for index, row in edited_df.iterrows():
                            c_name = row["颜色名称"]
                            c_qty = int(row["库存/预计数量"])
                            if c_name: # 确保名称不为空
                                db.add(ProductColor(
                                    product_id=target_prod.id, 
                                    color_name=str(c_name), 
                                    quantity=c_qty
                                ))
                                new_total_qty += c_qty
                        
                        # 3. 更新主表的总数量
                        target_prod.total_quantity = new_total_qty

                        db.commit()
                        st.session_state["toast_msg"] = (f"产品《{edit_name}》修改成功！", "✅")
                        
                        # 强制清除缓存，触发重新加载
                        if "edit_last_id" in st.session_state:
                            del st.session_state["edit_last_id"]
                        
                        st.rerun()

    # ================= 模块 3：产品列表 =================
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
                        st.write(f"**制作总数**: {p.total_quantity} 件")
                        
                        st.caption("定价明细")
                        price_data = {
                            "渠道": ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他(CNY)", "其他(JPY)"],
                            "价格": [
                                f"¥ {p.price_weidian}", 
                                f"¥ {p.price_booth} (JPY)",
                                f"¥ {getattr(p, 'price_instagram', 0)} (JPY)",
                                f"¥ {p.price_offline_jp} (JPY)",
                                f"¥ {p.price_offline_cn}",
                                f"¥ {p.price_other}",
                                f"¥ {getattr(p, 'price_other_jpy', 0)} (JPY)"
                            ]
                        }
                        st.dataframe(pd.DataFrame(price_data), use_container_width=True, hide_index=True)
                    
                    with col_b:
                        st.markdown("#### 🎨 规格明细")
                        p_colors = db.query(ProductColor).filter(ProductColor.product_id == p.id).all()
                        if p_colors:
                            # 构造标签显示：名称 (数量)
                            tags_html = "".join([
                                f'<span style="background-color:#3E3E3E; border:1px solid #666666; padding:4px 12px; border-radius:15px; margin:4px; display:inline-block; color:#FFFFFF; font-size:14px;">'
                                f'<b>{c.color_name}</b> <span style="color:#aaa; font-size:12px; margin-left:5px;">x{c.quantity}</span>'
                                f'</span>' 
                                for c in p_colors
                            ])
                            st.markdown(tags_html, unsafe_allow_html=True)
                        else:
                            st.caption("暂无颜色规格")

                    st.divider()
                    
                    # 删除逻辑
                    _, col_delete = st.columns([5, 1])
                    with col_delete:
                        with st.popover("🗑️ 删除产品", use_container_width=True):
                            st.warning(f"⚠️ 确定要删除《{p.name}》吗？")
                            if st.button("确认删除", type="primary", key=f"btn_confirm_del_{p.id}"):
                                try:
                                    # 注意：因为 ProductColor 设置了 cascade="all, delete-orphan"，
                                    # 所以删除 Product 会自动删除关联的 colors
                                    db.delete(p)
                                    db.commit()
                                    st.session_state["toast_msg"] = (f"已删除产品：{p.name}", "🗑️")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"删除失败: {e}")
        else:
            st.info("暂无产品数据")
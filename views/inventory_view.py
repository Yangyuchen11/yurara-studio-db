import streamlit as st
import pandas as pd
from datetime import date
from services.inventory_service import InventoryService

def show_inventory_page(db):
    st.header("📦 库存管理")
    
    # 初始化 Service
    service = InventoryService(db)

    # ================= 1. 库存一览 =================
    products = service.get_all_products()
    product_names = [p.name for p in products]
    
    c_sel, c_view = st.columns([1, 3])
    p_name = c_sel.selectbox("选择产品", product_names or ["暂无产品"])
    
    selected_product_id = None
    colors = []

    if products and p_name != "暂无产品":
        selected_product = next((p for p in products if p.name == p_name), None)
        selected_product_id = selected_product.id
        
        with c_view:
            if selected_product_id:
                # 使用 Service 获取库存概览数据
                colors = service.get_product_colors(selected_product_id)
                real_stock_map, pre_in_map, pre_out_map, has_pending_logs_map = service.get_stock_overview(p_name)

                if colors:
                    cols_cfg = [1.5, 1, 1, 1, 1, 1, 1, 2.5]
                    h1, h2, h3, h4, h5, h6, h7, h8 = st.columns(cols_cfg)
                    h1.markdown("**款式**")
                    h2.markdown("**计划**")
                    h3.markdown("**已产**")
                    h4.markdown("**库存**") 
                    h5.markdown("**预入**")
                    h6.markdown("**待发**") 
                    h7.markdown("**状态**")
                    h8.markdown("**操作**")
                    
                    st.markdown("<hr style='margin: 5px 0; opacity:0.5;'>", unsafe_allow_html=True)

                    for c in colors:
                        real_qty = real_stock_map.get(c.color_name, 0)
                        pre_in_qty = pre_in_map.get(c.color_name, 0)
                        pre_out_qty = pre_out_map.get(c.color_name, 0)
                        produced_qty = c.produced_quantity if c.produced_quantity is not None else 0
                        status = "🔴 缺货" if real_qty <= 0 else "🟢 有货"

                        r1, r2, r3, r4, r5, r6, r7, r8 = st.columns(cols_cfg)
                        r1.write(f"🎨 {c.color_name}")
                        r2.write(f"**{c.quantity}**")
                        r3.write(f"{produced_qty}")
                        r4.write(f"{int(real_qty)}")
                        r5.write(f"{int(pre_in_qty)}")
                        r6.write(f"{int(pre_out_qty)}")
                        r7.write(status)

                        with r8:
                            c_btn1, c_btn2 = st.columns([1, 1])
                            
                            # 按钮 1: 生产完成
                            if pre_in_qty == 0 and c.quantity > 0:
                                if c_btn1.button("🏭 生产完成", key=f"btn_prod_done_v2_{c.id}"):
                                    try:
                                        service.action_production_complete(selected_product_id, p_name, c.color_name, c.quantity, date.today())
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"操作失败: {e}")

                            # 按钮 2: 入库完成
                            if has_pending_logs_map.get(c.color_name, False):
                                btn_label = "📥 入库完成" if pre_in_qty > 0 else "✅ 结单/清理"
                                if c_btn2.button(btn_label, key=f"btn_finish_stock_{c.id}"):
                                    try:
                                        residual = service.action_finish_stock_in(selected_product_id, p_name, c, pre_in_qty, date.today())
                                        if residual:
                                            st.toast(f"已清理账面偏差: {residual:,.2f}", icon="⚖️")
                                        st.toast("操作成功", icon="✅")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"操作发生错误: {e}")

                        st.markdown("<hr style='margin: 5px 0; opacity:0.1;'>", unsafe_allow_html=True)
                else:
                    st.info("该产品暂无颜色/款式信息")

    st.divider()

    # ================= 2. 出库/发货管理 =================
    st.subheader("🚚 出库/发货管理 (待结算)")
    st.caption("此处显示已从库存扣除、但资金尚未结算到账的订单。")
    
    pre_items = service.get_pre_shipping_items(p_name)
    
    if pre_items:
        pre_data_list = []
        for p in pre_items:
            pre_data_list.append({
                "ID": p.id,
                "日期": p.created_date,
                "产品": p.product_name,
                "款式": p.variant,
                "数量": p.quantity,
                "预售/销售额": p.pre_sale_amount, 
                "币种": p.currency,
                "备注": p.note
            })
        
        df_pre = pd.DataFrame(pre_data_list)
        
        # 显示编辑器
        st.data_editor(
            df_pre, 
            key="pre_shipping_editor",
            use_container_width=True, 
            hide_index=True,
            disabled=["ID", "日期", "产品", "款式"],
            column_config={
                "ID": None,
                "数量": st.column_config.NumberColumn(min_value=1, step=1, disabled=True),
                "预售/销售额": st.column_config.NumberColumn(format="%.2f"),
                "币种": st.column_config.SelectboxColumn(options=["CNY", "JPY"])
            }
        )
        
        # 处理修改
        if st.session_state.get("pre_shipping_editor") and st.session_state["pre_shipping_editor"].get("edited_rows"):
            changes = {}
            for idx_str, diff in st.session_state["pre_shipping_editor"]["edited_rows"].items():
                item_id = int(df_pre.iloc[int(idx_str)]["ID"])
                changes[item_id] = diff
            
            if service.update_pre_shipping_info(changes):
                st.toast("发货单信息已更新", icon="💾")
                st.rerun()
        
        c_p1, c_p2 = st.columns([3.5, 1], vertical_alignment="bottom")
        
        with c_p1:
            pre_item_labels = {
                p.id: f"{p.created_date} | {p.product_name}-{p.variant} (Qty:{p.quantity}) | 📝{p.note or ''}"
                for p in pre_items
            }
            selected_pre_id = st.selectbox(
                "选择要确认收款的订单", 
                options=list(pre_item_labels.keys()), 
                format_func=lambda x: pre_item_labels.get(x, "未知订单"),
                key="sel_pre_ship_order"
            )
            
        with c_p2:
            if st.button("✅ 确认收款 (转收入)", type="primary", use_container_width=True):
                try:
                    asset_name = service.confirm_shipping_receipt(selected_pre_id)
                    st.toast(f"收款完成！资金已存入 {asset_name}", icon="💰")
                    st.rerun()
                except Exception as e:
                    st.error(f"操作失败: {e}")
    else:
        st.info("当前没有待结算的发货单。")

    # --- 撤销/删除预出库逻辑 ---
    st.write("") 
    with st.popover("🗑️ 撤销发货 (库存回滚)", use_container_width=True):
        st.error("⚠️ 注意：此操作将删除发货单，并**自动把库存加回去**。")
        
        del_pre_options = {
            f"{p.created_date} | {p.product_name}-{p.variant} (Qty:{p.quantity}) | 📝{p.note or ''}": p.id 
            for p in pre_items
        }
        
        selected_del_pre_label = st.selectbox(
            "选择要撤销的发货记录", 
            options=list(del_pre_options.keys()), 
            key="del_pre_select_box"
        )
        
        if st.button("🔴 确认撤销并回滚", type="primary", use_container_width=True):
            try:
                target_pre_id = del_pre_options[selected_del_pre_label]
                platform_str = service.undo_shipping(target_pre_id, selected_product_id)
                st.success(f"发货单已撤销，库存已回滚 (平台: {platform_str})。")
                st.rerun()
            except Exception as e:
                st.error(f"撤销失败: {e}")

    st.divider()

    # ================= 3. 变动录入表单 =================
    st.subheader("📝 库存变动录入")
    
    f_date, f_type, f_var, f_qty, f_remark, f_btn = st.columns([1, 1.1, 1.1, 0.7, 1.2, 0.7])
    
    input_date = f_date.date_input("日期", value=date.today())
    move_type = f_type.selectbox("变动类型", ["出库", "入库", "退货入库", "预入库", "额外生产入库", "计划入库减少"])
    
    color_options = [c.color_name for c in colors] if selected_product_id and colors else ["通用"]
    p_var = f_var.selectbox("款式", color_options)
    input_qty = f_qty.number_input("数量", min_value=1, step=1)
    p_remark = f_remark.text_input("备注")
    
    extra_info_col = st.container()
    
    # 额外字段初始化
    out_type = "其他"
    sale_price = 0.0
    sale_curr = "CNY"
    sale_platform = "其他"
    refund_amount = 0.0
    refund_curr = "CNY"
    refund_platform = "其他"
    cons_cat = "其他成本"
    cons_content = ""

    if move_type == "出库":
        with extra_info_col:
            out_type = st.radio("出库类型", ["售出", "消耗", "其他"], horizontal=True)
            if out_type == "售出":
                st.info("ℹ️ **流程说明**：点击提交后，库存将**立即扣减**，订单将进入【发货/出库管理】列表待确认收款。")
                c1, c2, c3 = st.columns(3)
                sale_curr = c1.selectbox("销售币种", ["CNY", "JPY"], key="out_curr")
                pf_options = ["微店", "中国线下", "其他"] if sale_curr == "CNY" else ["Booth", "Instagram", "日本线下", "其他"]
                sale_platform = c2.selectbox("销售平台", pf_options)
                sale_price = c3.number_input("销售总价 (应收)", min_value=0.0, step=100.0, format="%.2f")
                if input_qty > 0 and sale_price > 0:
                    unit_val = sale_price / input_qty
                    st.caption(f"📊 折合单价: {unit_val:,.2f} {sale_curr}")

            elif out_type == "消耗":
                st.warning(f"⚠️ 注意：选择【消耗】将自动扣减该商品的【可销售数量】。（记入成本但不产生金额）")
                c_cons1, c_cons2 = st.columns([1, 2])
                cons_cat = c_cons1.selectbox("计入成本分类", service.COST_CATEGORIES, index=service.COST_CATEGORIES.index("宣发费") if "宣发费" in service.COST_CATEGORIES else 0)
                cons_content = c_cons2.text_input("消耗内容 (必填)", placeholder="如：宣发样衣、赠送KOL")

    elif move_type == "退货入库":
        with extra_info_col:
            st.info("💡 退货入库：增加库存，同时从流动资金中扣除退款。")
            rc1, rc2, rc3 = st.columns(3)
            refund_curr = rc1.selectbox("退款币种", ["CNY", "JPY"], key="ref_curr")
            refund_amount = rc2.number_input("退款总额", min_value=0.0, step=100.0)
            refund_platform = rc3.text_input("退款平台", placeholder="如：微店")

    with f_btn:
        st.write("")
        if st.button("提交", type="primary"):
            if p_name == "暂无产品":
                st.error("无效产品")
            elif move_type == "出库" and out_type == "消耗" and not cons_content.strip():
                st.error("❌ 失败：请填写【消耗内容】。")
            else:
                try:
                    msg = service.add_inventory_movement(
                        product_id=selected_product_id,
                        product_name=p_name,
                        variant=p_var,
                        quantity=input_qty,
                        move_type=move_type,
                        date_obj=input_date,
                        remark=p_remark,
                        out_type=out_type,
                        sale_curr=sale_curr,
                        sale_platform=sale_platform,
                        sale_price=sale_price,
                        cons_cat=cons_cat,
                        cons_content=cons_content,
                        refund_curr=refund_curr,
                        refund_amount=refund_amount,
                        refund_platform=refund_platform
                    )
                    # 提交事务
                    service.commit()
                    
                    icon_map = {"出库": "📤", "入库": "📥", "退货入库": "↩️", "预入库": "📥", "计划入库减少": "📉", "额外生产入库": "📥"}
                    st.toast(msg, icon=icon_map.get(move_type, "✅"))
                    st.rerun()
                except ValueError as ve:
                    st.error(f"❌ {ve}")
                except Exception as e:
                    service.db.rollback()
                    st.error(f"操作失败: {e}")

    # ================= 4. 库存变动记录 =================
    st.subheader("📜 库存变动历史记录")
    
    logs = service.get_recent_logs(p_name)
    
    if logs:
        log_data = []
        for l in logs:
            desc = l.note or ""
            if l.is_sold: 
                prefix = ""
                if l.change_amount < 0: prefix = f"售出: ¥{l.sale_amount}{l.currency} ({l.platform}) | "
                else: prefix = f"退货: -¥{abs(l.sale_amount)}{l.currency} ({l.platform}) | "
                if not desc.startswith("售出:") and not desc.startswith("退货:"):
                    desc = prefix + desc
            elif l.is_other_out and not desc.startswith("其他出库:"):
                desc = f"其他出库: {desc}"
            
            log_data.append({
                "_id": l.id, "日期": l.date, "产品": l.product_name, 
                "款式": l.variant, "数量": l.change_amount, "类型": l.reason, "详情": desc
            })
        
        df_logs = pd.DataFrame(log_data)
        
        st.data_editor(
            df_logs,
            key="log_editor",
            use_container_width=True,
            hide_index=True,
            column_config={
                "_id": None,
                "日期": st.column_config.DateColumn(required=True),
                "产品": st.column_config.TextColumn(disabled=True),
                "款式": st.column_config.TextColumn(disabled=True),
                "数量": st.column_config.NumberColumn(disabled=True),
                "类型": st.column_config.TextColumn(disabled=True),
                "详情": st.column_config.TextColumn(label="详情 (可编辑备注)", required=False)
            }
        )
        
        # 处理日志修改
        if st.session_state.get("log_editor") and st.session_state["log_editor"].get("edited_rows"):
            changes = {}
            for idx_str, diff in st.session_state["log_editor"]["edited_rows"].items():
                log_id = int(df_logs.iloc[int(idx_str)]["_id"])
                changes[log_id] = diff
            
            if service.update_logs_batch(changes):
                st.toast("日志已更新", icon="💾")
                st.rerun()

        # 处理日志删除
        with st.popover("🗑️ 删除记录 (级联回滚)", use_container_width=True):
            st.warning("⚠️ 删除操作将自动回滚：库存、资产价值、可销售数量。请谨慎操作！")
            del_options = {f"{l.date} | {l.product_name} {l.variant} ({l.reason} {l.change_amount}) | {l.note or ''}": l.id for l in logs}
            selected_del_label = st.selectbox("选择要删除的记录", list(del_options.keys()))
            
            if st.button("🔴 确认删除并回滚"):
                try:
                    log_id = del_options[selected_del_label]
                    full_msg = service.delete_log_cascade(log_id)
                    st.success(f"删除成功！\n{full_msg}")
                    st.rerun()
                except Exception as e:
                    service.db.rollback()
                    st.error(f"删除失败: {e}")
    else:
        st.info("暂无记录")
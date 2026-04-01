import streamlit as st
import pandas as pd
from datetime import date
from services.inventory_service import InventoryService
from cache_manager import sync_all_caches
from constants import PRODUCT_COST_CATEGORIES, StockLogReason

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
                colors = service.get_product_colors(selected_product_id)
                # 【修改】接收新增的 wait_prod_map
                real_stock_map, pre_in_map, wait_prod_map = service.get_stock_overview(p_name)

                if colors:
                    # 调整列宽
                    cols_cfg = [1.5, 1, 1, 1, 1, 1, 1, 2.5]
                    h1, h2, h3, h4, h5, h6, h7, h8 = st.columns(cols_cfg)
                    h1.markdown("**款式**")
                    h2.markdown("**计划**")
                    h3.markdown("**已产**")
                    h4.markdown("**待产**")  
                    h5.markdown("**库存**") 
                    h6.markdown("**预入**")
                    h7.markdown("**状态**")
                    h8.markdown("**操作**")
                    
                    st.markdown("<hr style='margin: 5px 0; opacity:0.5;'>", unsafe_allow_html=True)

                    for c in colors:
                        real_qty = real_stock_map.get(c.color_name, 0)
                        pre_in_qty = pre_in_map.get(c.color_name, 0)
                        wait_qty = wait_prod_map.get(c.color_name, 0) # 获取待产数量
                        produced_qty = c.produced_quantity if c.produced_quantity is not None else 0
                        status = "🔴 缺货" if real_qty <= 0 else "🟢 有货"

                        r1, r2, r3, r4, r5, r6, r7, r8 = st.columns(cols_cfg)
                        r1.write(f"🎨 {c.color_name}")
                        r2.write(f"**{c.quantity}**")
                        r3.write(f"{produced_qty}")
                        r4.write(f"{int(wait_qty)}")   # ✨ 显示待产数量
                        r5.write(f"{int(real_qty)}")
                        r6.write(f"{int(pre_in_qty)}") # 这里只显示已生产完成等待入库的数量
                        r7.write(status)
                        
                        # r8 是预留给你后面写操作按钮的 (例如：盘点/修改按钮)
                        # with r8:
                        #     ... 你的按钮逻辑 ...

                        with r8:
                            c_btn1, c_btn2 = st.columns([1, 1])
                            
                            # 按钮 1: 生产完成 (现在根据 wait_qty 判断)
                            # 如果有录入的排单(WAIT_PROD/EXTRA_PROD_WAIT)，显示生产完成
                            if wait_qty > 0:
                                if c_btn1.button(f"🏭 生产完成", key=f"btn_prod_done_{c.id}"):
                                    try:
                                        # 不需要传数量，内部自动处理所有 pending logs
                                        service.action_production_complete(selected_product_id, p_name, c.color_name, date.today())
                                        st.toast("生产确认成功，已计入预入库资产", icon="✅")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"操作失败: {e}")

                            # 按钮 2: 入库完成 (根据 pre_in_qty 判断)
                            # 如果有预入库数量(已生产但未入大货仓)，显示入库完成
                            if pre_in_qty > 0:
                                if c_btn2.button("📥 入库完成", key=f"btn_finish_stock_{c.id}"):
                                    try:
                                        residual = service.action_finish_stock_in(selected_product_id, p_name, c, pre_in_qty, date.today())
                                        if residual:
                                            st.toast(f"已清理账面偏差: {residual:,.2f}", icon="⚖️")
                                        st.toast("入库成功，库存已更新", icon="✅")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"操作发生错误: {e}")
                            
                            # (可选) 显示清理按钮：如果所有都为0但有残留日志，保留清理逻辑
                            elif c.quantity > 0 and produced_qty >= c.quantity and wait_qty == 0 and pre_in_qty == 0:
                                pass # 暂不显示，保持简洁

                        st.markdown("<hr style='margin: 5px 0; opacity:0.1;'>", unsafe_allow_html=True)
                else:
                    st.info("该产品暂无颜色/款式信息")

    st.divider()

    # ================= 3. 变动录入表单 =================
    st.subheader("📝 库存变动录入")

    f_date, f_type, f_var, f_qty, f_remark, f_btn = st.columns([1, 1.1, 1.1, 0.7, 1.2, 0.7], vertical_alignment="bottom")

    input_date = f_date.date_input("日期", value=date.today())
    # 【修改】移除 RETURN_IN (退货入库)
    move_type = f_type.selectbox("变动类型", [StockLogReason.OUT_STOCK, StockLogReason.IN_STOCK, StockLogReason.PRE_IN, StockLogReason.EXTRA_PROD, StockLogReason.PRE_IN_REDUCE])
    
    color_options = [c.color_name for c in colors] if selected_product_id and colors else ["通用"]
    p_var = f_var.selectbox("款式", color_options)
    input_qty = f_qty.number_input("数量", min_value=1, step=1)
    p_remark = f_remark.text_input("备注")
    
    extra_info_col = st.container()

    # 额外字段初始化
    out_type = "其他"
    cons_cat = "其他成本"
    cons_content = ""

    # 【修改】出库类型移除"售出"，只保留"消耗"和"其他"
    if move_type == StockLogReason.OUT_STOCK:
        with extra_info_col:
            out_type = st.radio("出库类型", ["消耗", "其他"], horizontal=True)

            if out_type == "消耗":
                st.warning(f"⚠️ 注意：选择【消耗】将自动扣减该商品的【可销售数量】。（记入成本但不产生金额）")
                c_cons1, c_cons2 = st.columns([1, 2])
                cons_cat = c_cons1.selectbox("计入成本分类", service.COST_CATEGORIES, index=service.COST_CATEGORIES.index("宣发费") if "宣发费" in service.COST_CATEGORIES else 0)
                cons_content = c_cons2.text_input("消耗内容 (必填)", placeholder="如：宣发样衣、赠送KOL")

    with f_btn:
        st.write("")
        if st.button("提交", type="primary"):
            if p_name == "暂无产品":
                st.error("无效产品")
            elif move_type == StockLogReason.OUT_STOCK and out_type == "消耗" and not cons_content.strip():
                st.error("❌ 失败：请填写【消耗内容】。")
            else:
                try:
                    # 【修改】移除售出和退货相关参数
                    msg = service.add_inventory_movement(
                        product_id=selected_product_id,
                        product_name=p_name,
                        variant=p_var,
                        quantity=input_qty,
                        move_type=move_type,
                        date_obj=input_date,
                        remark=p_remark,
                        out_type=out_type,
                        sale_curr="CNY",  # 默认值
                        sale_platform="其他",  # 默认值
                        sale_price=0.0,  # 默认值
                        cons_cat=cons_cat,
                        cons_content=cons_content,
                        refund_curr="CNY",  # 默认值
                        refund_amount=0.0,  # 默认值
                        refund_platform="其他"  # 默认值
                    )
                    # 提交事务
                    service.commit()

                    icon_map = {StockLogReason.OUT_STOCK: "📤", StockLogReason.IN_STOCK: "📥", StockLogReason.PRE_IN: "📥", StockLogReason.PRE_IN_REDUCE: "📉", StockLogReason.EXTRA_PROD: "📥"}
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
            width="stretch",
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
        with st.popover("🗑️ 删除记录 (级联回滚)", width="stretch"):
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

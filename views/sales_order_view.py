import streamlit as st
import pandas as pd
from datetime import date
from services.sales_order_service import SalesOrderService
from models import Product
from constants import OrderStatus, PLATFORM_CODES
from database import SessionLocal

# ------------------ 🚀 性能优化：独立数据层缓存 ------------------

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_order_stats(product_filter):
    """缓存订单统计数据，避免每次刷新重算"""
    db_cache = SessionLocal()
    try:
        service = SalesOrderService(db_cache)
        return service.get_order_statistics(product_name=product_filter)
    finally:
        db_cache.close()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_orders_df(status_filter, product_filter):
    """直接将数据转换为 DataFrame 并缓存，彻底阻断全选时的数据库查询"""
    db_cache = SessionLocal()
    try:
        service = SalesOrderService(db_cache)
        orders = service.get_all_orders(status=status_filter, product_name=product_filter, limit=100)
        
        data_list = []
        for o in orders:
            item_count = len(o.items)
            items_summary = ", ".join([f"{i.product_name}-{i.variant}×{i.quantity}" for i in o.items[:2]])
            if item_count > 2:
                items_summary += f" 等{item_count}项"

            total_refunded = sum([r.refund_amount for r in o.refunds])
            
            status_display = o.status
            if o.status == OrderStatus.PENDING: status_display = "📦 待发货"
            elif o.status == OrderStatus.SHIPPED: status_display = "🚚 已发货"
            elif o.status == OrderStatus.COMPLETED: status_display = "✅ 完成"
            elif o.status == OrderStatus.AFTER_SALES: status_display = "🔧 售后"

            data_list.append({
                "勾选": False,
                "ID": o.id,
                "订单号": o.order_no,
                "状态": status_display,
                "商品": items_summary,
                "金额": float(o.total_amount),
                "已退款": float(total_refunded),
                "币种": o.currency,
                "平台": o.platform,
                "日期": str(o.created_date)
            })
        return pd.DataFrame(data_list)
    finally:
        db_cache.close()

def clear_order_caches():
    """当发生增删改操作时，清空相关缓存"""
    get_cached_order_stats.clear()
    get_cached_orders_df.clear()

# ------------------ 主页面逻辑 ------------------

def show_sales_order_page(db):
    st.header("🛒 销售订单管理")
    service = SalesOrderService(db)

    # ================= 0. 商品选择 =================
    all_products = db.query(Product).all()
    product_options = ["全部商品"] + [p.name for p in all_products]

    selected_product = st.selectbox(
        "📦 选择商品",
        product_options,
        key="sales_order_product_filter",
        help="选择商品后，下方所有统计和订单都将筛选该商品"
    )
    product_filter = None if selected_product == "全部商品" else selected_product
    st.divider()

    # ================= 1. 订单统计概览 (秒开) =================
    stats = get_cached_order_stats(product_filter)
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("总订单数", stats["total"])
        c2.metric("待发货", stats["pending"], delta_color="off")
        c3.metric("已发货", stats["shipped"], delta_color="off")
        c4.metric("已完成", stats["completed"], delta_color="off")
        c5.metric("售后中", stats["after_sales"], delta_color="inverse")
    st.divider()

    # ================= 2. 创建订单 =================
    with st.expander("➕ 创建新订单", expanded=False):
        if not product_filter:
            st.warning("⚠️ 请先在顶部选择具体商品后再创建订单")
        else:
            st.subheader("订单信息")
            products = db.query(Product).all()
            product_dict = {p.name: p for p in products}

            if product_filter not in product_dict:
                st.error("选择的商品不存在")
            else:
                selected_product_obj = product_dict[product_filter]
                color_options = [c.color_name for c in selected_product_obj.colors]

                col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                order_no = col_p1.text_input("订单号", placeholder="输入订单号（必填）", key="order_no_input")
                platform = col_p2.selectbox("销售平台", list(PLATFORM_CODES.values()))
                currency = col_p3.selectbox("币种", ["CNY", "JPY"])
                order_date = col_p4.date_input("订单日期", value=date.today())

                col_price, col_notes = st.columns([1, 3])
                total_price = col_price.number_input("订单总价", min_value=0.0, step=10.0, value=0.0, format="%.2f", key="order_total_price")
                notes = col_notes.text_input("订单备注", placeholder="如：客户名称、特殊要求等", key="order_notes_input")
                st.divider()

                st.markdown("**商品款式明细（请输入每个款式的数量）:**")
                if not color_options:
                    st.warning("该商品没有可用的款式")
                else:
                    variant_quantities = {}
                    for idx, color in enumerate(color_options):
                        col_variant, col_qty, col_spacer = st.columns([1, 1, 3])
                        col_variant.write(f"**{color}**")
                        qty = col_qty.number_input("数量", min_value=0, step=1, value=0, key=f"variant_qty_{idx}_{color}", label_visibility="collapsed")
                        variant_quantities[color] = qty

                    st.divider()
                    total_quantity = sum(variant_quantities.values())
                    col_qty_display, col_price_display, col_spacer = st.columns([1, 1.5, 2])
                    col_qty_display.markdown(f"**总数量: {total_quantity} 件**")

                    if total_quantity > 0 and total_price > 0:
                        unit_price = total_price / total_quantity
                        col_price_display.markdown(f"**平均单价: {unit_price:.2f} {currency}/件**")
                    else:
                        col_price_display.markdown(f"**平均单价: - {currency}/件**")

                    if st.button("✅ 提交订单", type="primary", width="stretch"):
                        if not order_no or not order_no.strip(): st.error("❌ 请输入订单号")
                        elif total_quantity == 0: st.error("❌ 请至少输入一个款式的数量")
                        elif total_price <= 0: st.error("❌ 请输入订单总价")
                        else:
                            items_data = []
                            unit_price = total_price / total_quantity
                            for color, qty in variant_quantities.items():
                                if qty > 0:
                                    items_data.append({"product_name": product_filter, "variant": color, "quantity": qty, "unit_price": unit_price, "subtotal": qty * unit_price})
                            
                            order, error = service.create_order(items_data=items_data, platform=platform, currency=currency, notes=notes, order_date=order_date, order_no=order_no.strip())
                            if error:
                                st.error(f"创建失败: {error}")
                            else:
                                st.success(f"✅ 订单 {order.order_no} 创建成功！")
                                clear_order_caches() # <--- 数据库发生变化，清空缓存
                                st.rerun()

    st.divider()

    # ================= 3. 订单列表 =================
    st.subheader("📋 订单列表")

    tab_all, tab_pending, tab_shipped, tab_completed, tab_after = st.tabs([
        "全部", "待发货", "已发货", "已完成", "售后中"
    ])

    def render_order_list(status_filter=None):
        status_key_suffix = str(status_filter) if status_filter else "all"
        editor_key = f"editor_{status_key_suffix}"
        select_all_key = f"select_all_flag_{status_key_suffix}"

        # 初始化全局全选状态
        if select_all_key not in st.session_state:
            st.session_state[select_all_key] = False

        # ⚡ 极速加载：从缓存获取 DataFrame
        with st.spinner("加载数据中..."):
            # 【修复点1】必须使用 .copy()，以避免直接修改缓存的底层数据
            df = get_cached_orders_df(status_filter, product_filter).copy()

        if df.empty:
            st.info("暂无订单")
            return

        # ================= 3.1 状态安全的全选/取消逻辑 =================
        c_sel1, c_sel2, _ = st.columns([1, 1, 6])
        
        if c_sel1.button("☑️ 全选", key=f"btn_sel_all_{status_key_suffix}", width="stretch"):
            st.session_state[select_all_key] = True
            # 【修复点2】Streamlit 不允许直接赋值 data_editor 的状态，但允许通过 del 清空状态
            # 这样表格就会重新读取下方 df["勾选"] 的默认值
            if editor_key in st.session_state: 
                del st.session_state[editor_key]
            st.rerun()
            
        if c_sel2.button("☐ 取消全选", key=f"btn_desel_all_{status_key_suffix}", width="stretch"):
            st.session_state[select_all_key] = False
            if editor_key in st.session_state: 
                del st.session_state[editor_key]
            st.rerun()

        # 根据全局状态覆盖 DataFrame 的默认勾选状态
        is_all_selected = st.session_state[select_all_key]
        df["勾选"] = is_all_selected

        st.markdown("**👇 勾选下方订单，点击操作栏按钮执行相应操作**")

        # ================= 3.2 渲染数据表格 =================
        edited_df = st.data_editor(
            df,
            width="stretch",
            hide_index=True,
            disabled=["订单号", "状态", "商品", "金额", "已退款", "币种", "平台", "日期"], 
            column_config={
                "勾选": st.column_config.CheckboxColumn("选择", default=False),
                "ID": None,
                "金额": st.column_config.NumberColumn(format="%.2f"),
                "已退款": st.column_config.NumberColumn(format="%.2f")
            },
            key=editor_key
        )

        # ================= 3.3 按钮状态推导 =================
        selected_rows = edited_df[edited_df["勾选"] == True]
        selected_ids = selected_rows["ID"].tolist()
        selected_count = len(selected_ids)

        all_pending = selected_count > 0 and all(s == "📦 待发货" for s in selected_rows["状态"])
        all_shipped = selected_count > 0 and all(s == "🚚 已发货" for s in selected_rows["状态"])
        
        is_single_select = (selected_count == 1)
        target_order_id = selected_ids[0] if is_single_select else None
        
        can_refund = False
        if is_single_select:
            target_status = selected_rows.iloc[0]["状态"]
            can_refund = target_status in ["🚚 已发货", "✅ 完成", "🔧 售后"]

        # ================= 3.4 全局操作栏 =================
        st.divider()
        action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)
        
        if action_col1.button(f"📦 发货 ({selected_count})", key=f"btn_ship_{status_key_suffix}", type="primary", width="stretch", disabled=not all_pending, help="仅当选中的所有订单均为【待发货】时可用"):
            success_count = 0
            for o_id in selected_ids:
                try:
                    service.ship_order(o_id)
                    success_count += 1
                except Exception as e:
                    st.error(f"订单 {o_id} 发货失败: {e}")
            if success_count > 0:
                st.toast(f"✅ 成功发货 {success_count} 个订单", icon="📦")
                if editor_key in st.session_state: del st.session_state[editor_key]
                st.session_state[select_all_key] = False
                clear_order_caches() 
                st.rerun()

        if action_col2.button(f"✅ 完成 ({selected_count})", key=f"btn_comp_{status_key_suffix}", type="primary", width="stretch", disabled=not all_shipped, help="仅当选中的所有订单均为【已发货】时可用"):
            success_count = 0
            for o_id in selected_ids:
                try:
                    service.complete_order(o_id)
                    success_count += 1
                except Exception as e:
                    st.error(f"订单 {o_id} 完成失败: {e}")
            if success_count > 0:
                st.toast(f"✅ 成功完成 {success_count} 个订单", icon="💰")
                if editor_key in st.session_state: del st.session_state[editor_key]
                st.session_state[select_all_key] = False
                clear_order_caches()
                st.rerun()

        if action_col3.button("🔧 售后处理", key=f"btn_after_{status_key_suffix}", width="stretch", disabled=not can_refund, help="仅限对单个【已发货/完成/售后】订单操作"):
            st.session_state[f"show_refund_form_{target_order_id}"] = True
            st.session_state.pop(f"show_detail_{target_order_id}", None)

        if action_col4.button("📄 查看详情", key=f"btn_det_{status_key_suffix}", width="stretch", disabled=not is_single_select, help="仅限单选时查看详情"):
            st.session_state[f"show_detail_{target_order_id}"] = True
            st.session_state.pop(f"show_refund_form_{target_order_id}", None)

        if action_col5.button("🗑️ 删除订单", key=f"btn_del_{status_key_suffix}", width="stretch", disabled=not is_single_select, help="仅限单选时删除订单"):
            st.session_state[f"show_delete_confirm_{target_order_id}"] = True

        # ================== 3.5 单选展开面板 ==================
        if target_order_id:
            # 单笔查询速度极快，不影响全局性能
            o = service.get_order_by_id(target_order_id)
            
            # --- 展开：删除确认 ---
            if st.session_state.get(f"show_delete_confirm_{target_order_id}"):
                with st.container(border=True):
                    st.warning(f"⚠️ 确认删除订单 **{o.order_no}** 吗？")
                    st.markdown("**此操作将：**\n- 完整回滚订单数据\n- 回滚库存、资产、财务流水\n- 删除所有售后记录\n- **此操作不可恢复！**")
                    cd1, cd2 = st.columns([1, 4])
                    if cd1.button("🔴 确认删除", key=f"btn_conf_del_{target_order_id}", type="primary"):
                        try:
                            msg = service.delete_order(target_order_id)
                            st.toast(msg, icon="✅")
                            st.session_state.pop(f"show_delete_confirm_{target_order_id}", None)
                            if editor_key in st.session_state: del st.session_state[editor_key]
                            st.session_state[select_all_key] = False
                            clear_order_caches()
                            st.rerun()
                        except Exception as e:
                            st.error(f"删除失败: {e}")
                    if cd2.button("取消", key=f"btn_cancel_del_{target_order_id}"):
                        st.session_state.pop(f"show_delete_confirm_{target_order_id}", None)
                        st.rerun()

            # --- 展开：订单详情 ---
            if st.session_state.get(f"show_detail_{target_order_id}"):
                with st.container(border=True):
                    st.markdown(f"**订单明细 - {o.order_no}**")
                    col_d1, col_d2, col_d3 = st.columns(3)
                    col_d1.write(f"**状态:** {o.status}")
                    col_d2.write(f"**平台:** {o.platform}")
                    col_d3.write(f"**币种:** {o.currency}")

                    col_d4, col_d5, col_d6 = st.columns(3)
                    col_d4.write(f"**创建日期:** {o.created_date}")
                    col_d5.write(f"**发货日期:** {o.shipped_date or '未发货'}")
                    col_d6.write(f"**完成日期:** {o.completed_date or '未完成'}")

                    st.write(f"**备注:** {o.notes or '无'}")

                    st.divider()
                    st.markdown("**商品明细:**")
                    items_detail = [{"商品": i.product_name, "款式": i.variant, "数量": i.quantity, "单价": i.unit_price, "小计": i.subtotal} for i in o.items]
                    st.dataframe(pd.DataFrame(items_detail), width="stretch", hide_index=True, column_config={"单价": st.column_config.NumberColumn(format="%.2f"), "小计": st.column_config.NumberColumn(format="%.2f")})
                    
                    st.write(f"**订单总额: {o.total_amount:.2f} {o.currency}**")

            # --- 展开：售后管理 ---
            if st.session_state.get(f"show_refund_form_{target_order_id}"):
                with st.container(border=True):
                    st.markdown(f"**售后管理 - {o.order_no}**")

                    if o.refunds:
                        st.markdown("**已有售后记录:**")
                        for r in o.refunds:
                            with st.container(border=True):
                                col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns([1.5, 2, 1, 1, 1.5])
                                col_r1.write(f"**日期:** {r.refund_date}")
                                col_r2.write(f"**原因:** {r.refund_reason}")
                                col_r3.write(f"**金额:** {r.refund_amount:.2f}")
                                col_r4.write(f"**退货:** {'是' if r.is_returned else '否'}")

                                with col_r5:
                                    btn_c1, btn_c2 = st.columns(2)
                                    # 恢复修改按钮
                                    if btn_c1.button("✏️", key=f"edit_refund_{r.id}", help="修改", width="stretch"):
                                        st.session_state[f"is_editing_refund_{r.id}"] = True
                                        st.rerun()
                                    # 恢复删除按钮
                                    if btn_c2.button("🗑️", key=f"del_refund_{r.id}", help="删除", width="stretch"):
                                        try:
                                            msg = service.delete_refund(r.id)
                                            st.toast(msg, icon="✅")
                                            clear_order_caches()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))

                                # 恢复修改表单
                                if st.session_state.get(f"is_editing_refund_{r.id}"):
                                    with st.form(f"edit_refund_form_{r.id}"):
                                        st.markdown("**修改售后记录:**")
                                        new_amount = st.number_input("售后金额", value=float(r.refund_amount), min_value=0.0, step=10.0, format="%.2f")
                                        new_reason = st.text_input("售后原因", value=r.refund_reason)

                                        col_e1, col_e2 = st.columns(2)
                                        submit_edit = col_e1.form_submit_button("保存", type="primary", width="stretch")
                                        cancel_edit = col_e2.form_submit_button("取消", width="stretch")

                                        if submit_edit:
                                            try:
                                                msg = service.update_refund(refund_id=r.id, refund_amount=new_amount, refund_reason=new_reason)
                                                st.success(msg)
                                                del st.session_state[f"is_editing_refund_{r.id}"]
                                                clear_order_caches()
                                                st.rerun()
                                            except Exception as e:
                                                st.error(str(e))
                                        if cancel_edit:
                                            del st.session_state[f"is_editing_refund_{r.id}"]
                                            st.rerun()
                        st.divider()

                    # 恢复申请新售后表单 (带精确退货商品选择)
                    with st.form(f"new_refund_form_{o.id}"):
                        st.markdown("**添加新售后:**")
                        refund_amount = st.number_input("售后金额", min_value=0.0, step=10.0, format="%.2f")
                        refund_reason = st.text_input("售后原因", placeholder="如：尺寸不合适、质量问题等")
                        is_returned = st.checkbox("是否退货")

                        # 恢复具体的退货商品选择逻辑
                        returned_items = []
                        if is_returned:
                            st.markdown("**选择退货商品:**")
                            for item in o.items:
                                return_qty = st.number_input(
                                    f"{item.product_name}-{item.variant}",
                                    min_value=0,
                                    max_value=item.quantity,
                                    step=1,
                                    key=f"return_qty_{item.id}_{o.id}"
                                )
                                if return_qty > 0:
                                    returned_items.append({
                                        "product_name": item.product_name,
                                        "variant": item.variant,
                                        "quantity": return_qty
                                    })

                        col_rf1, col_rf2 = st.columns(2)
                        submit_refund = col_rf1.form_submit_button("添加售后", type="primary", width="stretch")
                        cancel_refund = col_rf2.form_submit_button("关闭", width="stretch")

                        if submit_refund:
                            try:
                                returned_quantity = sum(item["quantity"] for item in returned_items) if is_returned else 0
                                msg = service.add_refund(
                                    order_id=o.id,
                                    refund_amount=refund_amount,
                                    refund_reason=refund_reason,
                                    is_returned=is_returned,
                                    returned_quantity=returned_quantity,
                                    returned_items=returned_items if is_returned else None
                                )
                                st.success(msg)
                                st.session_state.pop(f"show_refund_form_{target_order_id}", None)
                                clear_order_caches()
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

                        if cancel_refund:
                            del st.session_state[f"show_refund_form_{target_order_id}"]
                            st.rerun()

    with tab_all: render_order_list()
    with tab_pending: render_order_list(OrderStatus.PENDING)
    with tab_shipped: render_order_list(OrderStatus.SHIPPED)
    with tab_completed: render_order_list(OrderStatus.COMPLETED)
    with tab_after: render_order_list(OrderStatus.AFTER_SALES)
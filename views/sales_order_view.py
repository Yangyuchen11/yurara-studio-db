import streamlit as st
import pandas as pd
from datetime import date
from services.sales_order_service import SalesOrderService
from models import Product
from constants import OrderStatus, PLATFORM_CODES

def show_sales_order_page(db):
    st.header("🛒 销售订单管理")

    # 初始化服务
    service = SalesOrderService(db)

    # ================= 0. 商品选择（最顶级） =================
    all_products = db.query(Product).all()
    product_options = ["全部商品"] + [p.name for p in all_products]

    selected_product = st.selectbox(
        "📦 选择商品",
        product_options,
        key="sales_order_product_filter",
        help="选择商品后，下方所有统计和订单都将筛选该商品"
    )

    # 确定商品筛选参数
    product_filter = None if selected_product == "全部商品" else selected_product

    st.divider()

    # ================= 1. 订单统计概览 =================
    stats = service.get_order_statistics(product_name=product_filter)

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
        # 检查是否选择了具体商品
        if not product_filter:
            st.warning("⚠️ 请先在顶部选择具体商品后再创建订单")
        else:
            st.subheader("订单信息")

            # 获取商品和颜色选项
            products = db.query(Product).all()
            product_dict = {p.name: p for p in products}

            if product_filter not in product_dict:
                st.error("选择的商品不存在")
            else:
                selected_product = product_dict[product_filter]
                color_options = [c.color_name for c in selected_product.colors]

                # 第一行：订单号、平台、币种、日期
                col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                order_no = col_p1.text_input("订单号", placeholder="输入订单号（必填）", key="order_no_input")
                platform = col_p2.selectbox("销售平台", list(PLATFORM_CODES.values()))
                currency = col_p3.selectbox("币种", ["CNY", "JPY"])
                order_date = col_p4.date_input("订单日期", value=date.today())

                # 第二行：订单总价、订单备注
                col_price, col_notes = st.columns([1, 3])
                total_price = col_price.number_input("订单总价", min_value=0.0, step=10.0, value=0.0, format="%.2f", key="order_total_price")
                notes = col_notes.text_input("订单备注", placeholder="如：客户名称、特殊要求等", key="order_notes_input")

                st.divider()

                # 款式数量列表
                st.markdown("**商品款式明细（请输入每个款式的数量）:**")

                if not color_options:
                    st.warning("该商品没有可用的款式")
                else:
                    # 存储每个款式的数量
                    variant_quantities = {}

                    for idx, color in enumerate(color_options):
                        col_variant, col_qty, col_spacer = st.columns([1, 1, 3])
                        col_variant.write(f"**{color}**")
                        qty = col_qty.number_input(
                            "数量",
                            min_value=0,
                            step=1,
                            value=0,
                            key=f"variant_qty_{idx}_{color}",
                            label_visibility="collapsed"
                        )
                        variant_quantities[color] = qty

                    st.divider()

                    # 计算总数量（常态显示）
                    total_quantity = sum(variant_quantities.values())

                    col_qty_display, col_price_display, col_spacer = st.columns([1, 1.5, 2])
                    col_qty_display.markdown(f"**总数量: {total_quantity} 件**")

                    if total_quantity > 0 and total_price > 0:
                        unit_price = total_price / total_quantity
                        col_price_display.markdown(f"**平均单价: {unit_price:.2f} {currency}/件**")
                    else:
                        col_price_display.markdown(f"**平均单价: - {currency}/件**")

                    # 提交订单按钮
                    if st.button("✅ 提交订单", type="primary", use_container_width=True):
                        # 验证
                        if not order_no or not order_no.strip():
                            st.error("❌ 请输入订单号")
                        elif total_quantity == 0:
                            st.error("❌ 请至少输入一个款式的数量")
                        elif total_price <= 0:
                            st.error("❌ 请输入订单总价")
                        else:
                            # 构建订单明细
                            items_data = []
                            unit_price = total_price / total_quantity

                            for color, qty in variant_quantities.items():
                                if qty > 0:
                                    items_data.append({
                                        "product_name": product_filter,
                                        "variant": color,
                                        "quantity": qty,
                                        "unit_price": unit_price,
                                        "subtotal": qty * unit_price
                                    })

                            # 创建订单
                            order, error = service.create_order(
                                items_data=items_data,
                                platform=platform,
                                currency=currency,
                                notes=notes,
                                order_date=order_date,
                                order_no=order_no.strip()
                            )

                            if error:
                                st.error(f"创建失败: {error}")
                            else:
                                st.success(f"✅ 订单 {order.order_no} 创建成功！")
                                st.rerun()

    st.divider()

    # ================= 3. 订单列表 =================
    st.subheader("📋 订单列表")

    # 状态筛选
    tab_all, tab_pending, tab_shipped, tab_completed, tab_after = st.tabs([
        "全部", "待发货", "已发货", "已完成", "售后中"
    ])

    def render_order_list(status_filter=None):
        orders = service.get_all_orders(status=status_filter, product_name=product_filter, limit=100)

        if not orders:
            st.info("暂无订单")
            return

        order_data = []
        for o in orders:
            # 计算商品数量
            item_count = len(o.items)
            items_summary = ", ".join([f"{i.product_name}-{i.variant}×{i.quantity}" for i in o.items[:2]])
            if item_count > 2:
                items_summary += f" 等{item_count}项"

            # 计算已退款金额
            total_refunded = sum([r.refund_amount for r in o.refunds])

            # 【新增】为状态添加图标
            status_display = o.status
            if o.status == OrderStatus.PENDING:
                status_display = "📦 待发货"
            elif o.status == OrderStatus.SHIPPED:
                status_display = "🚚 已发货"
            elif o.status == OrderStatus.COMPLETED:
                status_display = "✅ 订单完成"
            elif o.status == OrderStatus.AFTER_SALES:
                status_display = "🔧 售后中"

            order_data.append({
                "ID": o.id,
                "订单号": o.order_no,
                "状态": status_display,
                "商品": items_summary,
                "金额": o.total_amount,
                "已退款": total_refunded,
                "币种": o.currency,
                "平台": o.platform,
                "日期": o.created_date,
                "备注": o.notes
            })

        # 初始化批量操作的session state
        if "batch_selected_orders" not in st.session_state:
            st.session_state.batch_selected_orders = set()

        # 根据状态筛选显示批量操作按钮
        # 全部选项卡：不显示
        # 待发货：显示批量发货
        # 已发货：显示批量完成
        # 已完成/售后中：不显示
        show_batch_actions = False
        batch_action_type = None

        if status_filter == OrderStatus.PENDING:
            show_batch_actions = True
            batch_action_type = "ship"
        elif status_filter == OrderStatus.SHIPPED:
            show_batch_actions = True
            batch_action_type = "complete"

        # 批量操作按钮区域
        if orders and show_batch_actions:
            selected_count = len(st.session_state.batch_selected_orders)

            batch_col1, batch_col2, batch_col3, batch_col4 = st.columns([1, 1, 1.5, 4.5])

            # 全选按钮
            if batch_col1.button("全选", key=f"select_all_{status_filter}", use_container_width=True):
                st.session_state.batch_selected_orders = set([o.id for o in orders])
                st.rerun()

            # 取消全选按钮
            if batch_col2.button("取消全选", key=f"deselect_all_{status_filter}", use_container_width=True):
                st.session_state.batch_selected_orders = set()
                st.rerun()

            # 批量操作按钮（只在有选中订单时启用）
            if batch_action_type == "ship":
                button_label = f"📦 批量发货 ({selected_count})" if selected_count > 0 else "📦 批量发货"
                if batch_col3.button(button_label,
                                    key=f"batch_ship_{status_filter}",
                                    type="primary",
                                    use_container_width=True,
                                    disabled=(selected_count == 0)):
                    success_count = 0
                    error_messages = []
                    for order_id in list(st.session_state.batch_selected_orders):
                        try:
                            msg = service.ship_order(order_id)
                            success_count += 1
                        except Exception as e:
                            error_messages.append(f"订单ID {order_id}: {str(e)}")

                    if success_count > 0:
                        st.toast(f"✅ 成功发货 {success_count} 个订单", icon="✅")
                    if error_messages:
                        for err_msg in error_messages[:5]:  # 只显示前5条错误
                            st.error(err_msg)

                    st.session_state.batch_selected_orders = set()
                    st.rerun()

            elif batch_action_type == "complete":
                button_label = f"✅ 批量完成 ({selected_count})" if selected_count > 0 else "✅ 批量完成"
                if batch_col3.button(button_label,
                                    key=f"batch_complete_{status_filter}",
                                    type="primary",
                                    use_container_width=True,
                                    disabled=(selected_count == 0)):
                    success_count = 0
                    error_messages = []
                    for order_id in list(st.session_state.batch_selected_orders):
                        try:
                            msg = service.complete_order(order_id)
                            success_count += 1
                        except Exception as e:
                            error_messages.append(f"订单ID {order_id}: {str(e)}")

                    if success_count > 0:
                        st.toast(f"✅ 成功完成 {success_count} 个订单", icon="💰")
                    if error_messages:
                        for err_msg in error_messages[:5]:  # 只显示前5条错误
                            st.error(err_msg)

                    st.session_state.batch_selected_orders = set()
                    st.rerun()

            st.divider()

        # 【修改】使用表头 + 循环渲染每行，在最后添加操作按钮
        # 表头
        with st.container(border=True):
            header_cols = st.columns([0.5, 1.2, 1, 2.3, 1, 1, 0.8, 1, 1, 2.5])
            header_cols[0].markdown("**选择**")
            header_cols[1].markdown("**订单号**")
            header_cols[2].markdown("**状态**")
            header_cols[3].markdown("**商品**")
            header_cols[4].markdown("**金额**")
            header_cols[5].markdown("**已退款**")
            header_cols[6].markdown("**币种**")
            header_cols[7].markdown("**平台**")
            header_cols[8].markdown("**日期**")
            header_cols[9].markdown("**操作**")

        # 复选框状态切换函数
        def toggle_selection(order_id):
            """切换订单选择状态"""
            if order_id in st.session_state.batch_selected_orders:
                st.session_state.batch_selected_orders.discard(order_id)
            else:
                st.session_state.batch_selected_orders.add(order_id)

        # 【修改】渲染每一行订单
        for o in orders:
            # 计算商品摘要
            item_count = len(o.items)
            items_summary = ", ".join([f"{i.product_name}-{i.variant}×{i.quantity}" for i in o.items[:2]])
            if item_count > 2:
                items_summary += f" 等{item_count}项"

            # 计算已退款金额
            total_refunded = sum([r.refund_amount for r in o.refunds])

            # 状态显示
            status_display = o.status
            if o.status == OrderStatus.PENDING:
                status_display = "📦 待发货"
            elif o.status == OrderStatus.SHIPPED:
                status_display = "🚚 已发货"
            elif o.status == OrderStatus.COMPLETED:
                status_display = "✅ 完成"
            elif o.status == OrderStatus.AFTER_SALES:
                status_display = "🔧 售后"

            with st.container(border=True):
                row_cols = st.columns([0.5, 1.2, 1, 2.3, 1, 1, 0.8, 1, 1, 2.5])

                # 复选框
                is_selected = o.id in st.session_state.batch_selected_orders
                row_cols[0].checkbox("", value=is_selected, key=f"select_{o.id}_{status_filter}",
                                    label_visibility="collapsed",
                                    on_change=toggle_selection,
                                    args=(o.id,))

                row_cols[1].write(o.order_no)
                row_cols[2].write(status_display)
                row_cols[3].write(items_summary)
                row_cols[4].write(f"{o.total_amount:.2f}")
                row_cols[5].write(f"{total_refunded:.2f}")
                row_cols[6].write(o.currency)
                row_cols[7].write(o.platform)
                row_cols[8].write(str(o.created_date))

                # 【新增】操作按钮列 - 所有按钮始终显示，根据状态启用/禁用
                with row_cols[9]:
                    btn_cols = st.columns(5)

                    # 按钮1: 发货（仅待发货状态可用）
                    with btn_cols[0]:
                        can_ship = (o.status == OrderStatus.PENDING)
                        help_text = "标记发货" if can_ship else "仅待发货订单可发货"
                        if st.button("📦", key=f"ship_{o.id}_{status_filter}", help=help_text,
                                    use_container_width=True, disabled=not can_ship):
                            try:
                                msg = service.ship_order(o.id)
                                st.toast(msg, icon="✅")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

                    # 按钮2: 完成（仅已发货状态可用，必须先发货）
                    with btn_cols[1]:
                        can_complete = (o.status == OrderStatus.SHIPPED)
                        if o.status == OrderStatus.PENDING:
                            help_text = "请先标记发货"
                        elif o.status in [OrderStatus.COMPLETED, OrderStatus.AFTER_SALES]:
                            help_text = "订单已完成或售后中"
                        else:
                            help_text = "确认完成"
                        if st.button("✅", key=f"complete_{o.id}_{status_filter}", help=help_text,
                                    use_container_width=True, disabled=not can_complete):
                            try:
                                msg = service.complete_order(o.id)
                                st.toast(msg, icon="💰")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

                    # 按钮3: 售后（仅已发货、已完成、售后中状态可用）
                    with btn_cols[2]:
                        can_refund = (o.status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED, OrderStatus.AFTER_SALES])
                        help_text = "申请售后" if can_refund else "待发货订单不能申请售后"
                        if st.button("🔧", key=f"refund_{o.id}_{status_filter}", help=help_text,
                                    use_container_width=True, disabled=not can_refund):
                            # 关闭所有其他订单的售后和详情
                            for order in orders:
                                if order.id != o.id:
                                    st.session_state.pop(f"show_refund_form_{order.id}", None)
                                    st.session_state.pop(f"show_detail_{order.id}", None)
                            # 切换当前订单的售后显示状态
                            st.session_state[f"show_refund_form_{o.id}"] = not st.session_state.get(f"show_refund_form_{o.id}", False)
                            # 关闭详情
                            st.session_state.pop(f"show_detail_{o.id}", None)
                            st.rerun()

                    # 按钮4: 详情（所有状态都可用）
                    with btn_cols[3]:
                        if st.button("📄", key=f"detail_{o.id}_{status_filter}", help="查看详情",
                                    use_container_width=True):
                            # 关闭所有其他订单的售后和详情
                            for order in orders:
                                if order.id != o.id:
                                    st.session_state.pop(f"show_refund_form_{order.id}", None)
                                    st.session_state.pop(f"show_detail_{order.id}", None)
                            # 切换当前订单的详情显示状态
                            st.session_state[f"show_detail_{o.id}"] = not st.session_state.get(f"show_detail_{o.id}", False)
                            # 关闭售后
                            st.session_state.pop(f"show_refund_form_{o.id}", None)
                            st.rerun()

                    # 按钮5: 删除（所有状态都可用）
                    with btn_cols[4]:
                        if st.button("🗑️", key=f"delete_{o.id}_{status_filter}", help="删除订单",
                                    use_container_width=True):
                            # 显示确认对话框
                            st.session_state[f"show_delete_confirm_{o.id}"] = True
                            st.rerun()

                # 【新增】删除确认对话框
                if st.session_state.get(f"show_delete_confirm_{o.id}"):
                    st.divider()
                    with st.container(border=True):
                        st.warning(f"⚠️ 确认删除订单 **{o.order_no}** 吗？")
                        st.markdown("**此操作将：**")
                        st.markdown("- 完整回滚订单数据")
                        st.markdown("- 回滚库存、资产、财务流水")
                        st.markdown("- 删除所有售后记录")
                        st.markdown("- **此操作不可恢复！**")

                        col_del1, col_del2 = st.columns(2)

                        if col_del1.button("🔴 确认删除", key=f"confirm_delete_{o.id}_{status_filter}",
                                          type="primary", use_container_width=True):
                            try:
                                msg = service.delete_order(o.id)
                                st.toast(msg, icon="✅")
                                st.session_state.pop(f"show_delete_confirm_{o.id}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"删除失败: {e}")

                        if col_del2.button("取消", key=f"cancel_delete_{o.id}_{status_filter}",
                                          use_container_width=True):
                            st.session_state.pop(f"show_delete_confirm_{o.id}", None)
                            st.rerun()

                # 【新增】在订单行下方显示售后管理界面
                if st.session_state.get(f"show_refund_form_{o.id}"):
                    st.divider()
                    st.markdown(f"**售后管理**")

                    # 显示已有的售后记录
                    if o.refunds:
                        st.markdown("**已有售后记录:**")
                        for idx, r in enumerate(o.refunds):
                            with st.container(border=True):
                                col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns([1.5, 2, 1, 1, 1.5])
                                col_r1.write(f"**日期:** {r.refund_date}")
                                col_r2.write(f"**原因:** {r.refund_reason}")
                                col_r3.write(f"**金额:** {r.refund_amount:.2f}")
                                col_r4.write(f"**退货:** {'是' if r.is_returned else '否'}")

                                with col_r5:
                                    btn_c1, btn_c2 = st.columns(2)
                                    # 修改按钮
                                    if btn_c1.button("✏️", key=f"edit_refund_{r.id}_{status_filter}", help="修改", use_container_width=True):
                                        st.session_state[f"edit_refund_{r.id}"] = True
                                        st.rerun()
                                    # 删除按钮
                                    if btn_c2.button("🗑️", key=f"del_refund_{r.id}_{status_filter}", help="删除", use_container_width=True):
                                        try:
                                            msg = service.delete_refund(r.id)
                                            st.toast(msg, icon="✅")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))

                                # 修改表单
                                if st.session_state.get(f"edit_refund_{r.id}"):
                                    with st.form(f"edit_refund_form_{r.id}_{status_filter}"):
                                        st.markdown("**修改售后记录:**")
                                        new_amount = st.number_input("售后金额", value=float(r.refund_amount), min_value=0.0, step=10.0, format="%.2f")
                                        new_reason = st.text_input("售后原因", value=r.refund_reason)

                                        col_e1, col_e2 = st.columns(2)
                                        submit_edit = col_e1.form_submit_button("保存", type="primary", use_container_width=True)
                                        cancel_edit = col_e2.form_submit_button("取消", use_container_width=True)

                                        if submit_edit:
                                            try:
                                                msg = service.update_refund(
                                                    refund_id=r.id,
                                                    refund_amount=new_amount,
                                                    refund_reason=new_reason
                                                )
                                                st.success(msg)
                                                del st.session_state[f"edit_refund_{r.id}"]
                                                st.rerun()
                                            except Exception as e:
                                                st.error(str(e))

                                        if cancel_edit:
                                            del st.session_state[f"edit_refund_{r.id}"]
                                            st.rerun()

                        st.divider()

                    # 添加新售后记录
                    with st.form(f"new_refund_form_{o.id}_{status_filter}"):
                        st.markdown("**添加新售后:**")
                        refund_amount = st.number_input("售后金额", min_value=0.0, step=10.0, format="%.2f")
                        refund_reason = st.text_input("售后原因", placeholder="如：尺寸不合适、质量问题等")
                        is_returned = st.checkbox("是否退货")

                        returned_items = []
                        if is_returned:
                            st.markdown("**选择退货商品:**")
                            for item in o.items:
                                return_qty = st.number_input(
                                    f"{item.product_name}-{item.variant}",
                                    min_value=0,
                                    max_value=item.quantity,
                                    step=1,
                                    key=f"return_qty_{item.id}_{o.id}_{status_filter}"
                                )
                                if return_qty > 0:
                                    returned_items.append({
                                        "product_name": item.product_name,
                                        "variant": item.variant,
                                        "quantity": return_qty
                                    })

                        col_rf1, col_rf2 = st.columns(2)
                        submit_refund = col_rf1.form_submit_button("添加售后", type="primary", use_container_width=True)
                        cancel_refund = col_rf2.form_submit_button("关闭", use_container_width=True)

                        if submit_refund:
                            try:
                                returned_quantity = sum(item["quantity"] for item in returned_items)
                                msg = service.add_refund(
                                    order_id=o.id,
                                    refund_amount=refund_amount,
                                    refund_reason=refund_reason,
                                    is_returned=is_returned,
                                    returned_quantity=returned_quantity,
                                    returned_items=returned_items if is_returned else None
                                )
                                st.success(msg)
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

                        if cancel_refund:
                            del st.session_state[f"show_refund_form_{o.id}"]
                            st.rerun()

                # 【新增】在订单行下方显示订单详情
                if st.session_state.get(f"show_detail_{o.id}"):
                    st.divider()
                    st.markdown(f"**订单详情**")

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

                    items_detail = []
                    for item in o.items:
                        items_detail.append({
                            "商品": item.product_name,
                            "款式": item.variant,
                            "数量": item.quantity,
                            "单价": item.unit_price,
                            "小计": item.subtotal
                        })

                    st.dataframe(
                        pd.DataFrame(items_detail),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "单价": st.column_config.NumberColumn(format="%.2f"),
                            "小计": st.column_config.NumberColumn(format="%.2f")
                        }
                    )

                    st.write(f"**订单总额: {o.total_amount:.2f} {o.currency}**")

                    # 售后记录
                    if o.refunds:
                        st.divider()
                        st.markdown("**售后记录:**")

                        refund_detail = []
                        for r in o.refunds:
                            refund_detail.append({
                                "日期": r.refund_date,
                                "售后金额": r.refund_amount,
                                "售后原因": r.refund_reason,
                                "是否退货": "是" if r.is_returned else "否",
                                "退货数量": r.returned_quantity
                            })

                        st.dataframe(
                            pd.DataFrame(refund_detail),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "售后金额": st.column_config.NumberColumn(format="%.2f")
                            }
                        )

    with tab_all:
        render_order_list()

    with tab_pending:
        render_order_list(OrderStatus.PENDING)

    with tab_shipped:
        render_order_list(OrderStatus.SHIPPED)

    with tab_completed:
        render_order_list(OrderStatus.COMPLETED)

    with tab_after:
        render_order_list(OrderStatus.AFTER_SALES)

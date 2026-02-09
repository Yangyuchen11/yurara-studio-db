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

    # ================= 1. 订单统计概览 =================
    stats = service.get_order_statistics()

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
        st.subheader("订单信息")

        # 平台和币种
        col_p1, col_p2, col_p3 = st.columns(3)
        platform = col_p1.selectbox("销售平台", list(PLATFORM_CODES.values()))
        currency = col_p2.selectbox("币种", ["CNY", "JPY"])
        order_date = col_p3.date_input("订单日期", value=date.today())

        notes = st.text_area("订单备注", placeholder="如：客户名称、特殊要求等")

        st.divider()
        st.subheader("商品明细")

        # 使用 session_state 存储订单项
        if "order_items" not in st.session_state:
            st.session_state.order_items = []

        # 获取所有产品和颜色
        products = db.query(Product).all()
        product_dict = {p.name: p for p in products}

        # 添加商品表单
        with st.form("add_item_form", clear_on_submit=True):
            col_i1, col_i2, col_i3, col_i4, col_i5 = st.columns([2, 2, 1, 1.5, 1])

            selected_product_name = col_i1.selectbox("商品", list(product_dict.keys()) if products else ["暂无商品"])

            # 获取颜色选项
            color_options = []
            if selected_product_name and selected_product_name != "暂无商品":
                selected_product = product_dict[selected_product_name]
                color_options = [c.color_name for c in selected_product.colors]

            variant = col_i2.selectbox("款式/颜色", color_options if color_options else ["通用"])
            quantity = col_i3.number_input("数量", min_value=1, step=1, value=1)
            unit_price = col_i4.number_input("单价", min_value=0.0, step=10.0, value=0.0, format="%.2f")

            add_btn = col_i5.form_submit_button("添加", use_container_width=True, type="primary")

            if add_btn:
                if selected_product_name == "暂无商品":
                    st.error("请先创建商品")
                elif not variant or variant == "通用":
                    st.error("请选择款式")
                elif unit_price <= 0:
                    st.error("请输入有效单价")
                else:
                    st.session_state.order_items.append({
                        "product_name": selected_product_name,
                        "variant": variant,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "subtotal": quantity * unit_price
                    })
                    st.rerun()

        # 显示已添加的商品
        if st.session_state.order_items:
            st.markdown("**已添加的商品:**")

            items_data = []
            for idx, item in enumerate(st.session_state.order_items):
                items_data.append({
                    "序号": idx,
                    "商品": item["product_name"],
                    "款式": item["variant"],
                    "数量": item["quantity"],
                    "单价": item["unit_price"],
                    "小计": item["subtotal"]
                })

            df_items = pd.DataFrame(items_data)
            st.dataframe(
                df_items[["商品", "款式", "数量", "单价", "小计"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "单价": st.column_config.NumberColumn(format="%.2f"),
                    "小计": st.column_config.NumberColumn(format="%.2f")
                }
            )

            total = sum(item["subtotal"] for item in st.session_state.order_items)
            st.markdown(f"**订单总金额: {total:.2f} {currency}**")

            col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 3])

            if col_btn1.button("🗑️ 清空", use_container_width=True):
                st.session_state.order_items = []
                st.rerun()

            if col_btn2.button("✅ 提交订单", type="primary", use_container_width=True):
                order, error = service.create_order(
                    items_data=st.session_state.order_items,
                    platform=platform,
                    currency=currency,
                    notes=notes,
                    order_date=order_date
                )

                if error:
                    st.error(f"创建失败: {error}")
                else:
                    st.success(f"✅ 订单 {order.order_no} 创建成功！库存已扣减。")
                    st.session_state.order_items = []
                    st.rerun()
        else:
            st.info("请添加至少一件商品")

    st.divider()

    # ================= 3. 订单列表 =================
    st.subheader("📋 订单列表")

    # 状态筛选
    tab_all, tab_pending, tab_shipped, tab_completed, tab_after = st.tabs([
        "全部", "待发货", "已发货", "已完成", "售后中"
    ])

    def render_order_list(status_filter=None):
        orders = service.get_all_orders(status=status_filter, limit=100)

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

            order_data.append({
                "ID": o.id,
                "订单号": o.order_no,
                "状态": o.status,
                "商品": items_summary,
                "金额": o.total_amount,
                "已退款": total_refunded,
                "币种": o.currency,
                "平台": o.platform,
                "日期": o.created_date,
                "备注": o.notes
            })

        df_orders = pd.DataFrame(order_data)

        # 使用颜色标记状态
        def highlight_status(row):
            if row["状态"] == OrderStatus.PENDING:
                return ["background-color: #fff3cd"] * len(row)
            elif row["状态"] == OrderStatus.SHIPPED:
                return ["background-color: #d1ecf1"] * len(row)
            elif row["状态"] == OrderStatus.COMPLETED:
                return ["background-color: #d4edda"] * len(row)
            elif row["状态"] == OrderStatus.AFTER_SALES:
                return ["background-color: #f8d7da"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_orders.style.apply(highlight_status, axis=1),
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": None,
                "金额": st.column_config.NumberColumn(format="%.2f"),
                "已退款": st.column_config.NumberColumn(format="%.2f")
            }
        )

        # 订单操作
        st.divider()
        st.markdown("**订单操作**")

        order_options = {f"{o.order_no} - {o.platform} - {o.total_amount:.2f}{o.currency}": o.id for o in orders}
        selected_order_label = st.selectbox("选择订单", list(order_options.keys()), key=f"select_order_{status_filter}")
        selected_order_id = order_options[selected_order_label]

        # 获取订单详情
        order = service.get_order_by_id(selected_order_id)

        if order:
            col_o1, col_o2, col_o3, col_o4 = st.columns(4)

            # 订单发货
            if order.status == OrderStatus.PENDING:
                if col_o1.button("📦 标记发货", key=f"ship_{status_filter}", use_container_width=True):
                    try:
                        msg = service.ship_order(selected_order_id)
                        st.toast(msg, icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            # 订单完成
            if order.status in [OrderStatus.PENDING, OrderStatus.SHIPPED]:
                if col_o2.button("✅ 确认完成", key=f"complete_{status_filter}", type="primary", use_container_width=True):
                    try:
                        msg = service.complete_order(selected_order_id)
                        st.toast(msg, icon="💰")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            # 申请售后
            if order.status != OrderStatus.PENDING:
                if col_o3.button("🔧 申请售后", key=f"refund_{status_filter}", use_container_width=True):
                    st.session_state[f"show_refund_form_{selected_order_id}"] = True

            # 查看详情
            if col_o4.button("📄 查看详情", key=f"detail_{status_filter}", use_container_width=True):
                st.session_state[f"show_detail_{selected_order_id}"] = True

            # 售后表单
            if st.session_state.get(f"show_refund_form_{selected_order_id}"):
                with st.form(f"refund_form_{selected_order_id}"):
                    st.subheader(f"申请售后 - {order.order_no}")

                    refund_amount = st.number_input("退款金额", min_value=0.0, step=10.0, format="%.2f")
                    refund_reason = st.text_input("退款原因", placeholder="如：尺寸不合适、质量问题等")
                    is_returned = st.checkbox("是否退货")

                    returned_items = []
                    if is_returned:
                        st.markdown("**选择退货商品:**")
                        for item in order.items:
                            return_qty = st.number_input(
                                f"{item.product_name}-{item.variant}",
                                min_value=0,
                                max_value=item.quantity,
                                step=1,
                                key=f"return_qty_{item.id}"
                            )
                            if return_qty > 0:
                                returned_items.append({
                                    "product_name": item.product_name,
                                    "variant": item.variant,
                                    "quantity": return_qty
                                })

                    col_rf1, col_rf2 = st.columns(2)
                    submit_refund = col_rf1.form_submit_button("提交售后", type="primary", use_container_width=True)
                    cancel_refund = col_rf2.form_submit_button("取消", use_container_width=True)

                    if submit_refund:
                        try:
                            returned_quantity = sum(item["quantity"] for item in returned_items)
                            msg = service.add_refund(
                                order_id=selected_order_id,
                                refund_amount=refund_amount,
                                refund_reason=refund_reason,
                                is_returned=is_returned,
                                returned_quantity=returned_quantity,
                                returned_items=returned_items if is_returned else None
                            )
                            st.success(msg)
                            del st.session_state[f"show_refund_form_{selected_order_id}"]
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

                    if cancel_refund:
                        del st.session_state[f"show_refund_form_{selected_order_id}"]
                        st.rerun()

            # 订单详情
            if st.session_state.get(f"show_detail_{selected_order_id}"):
                with st.container(border=True):
                    st.subheader(f"订单详情 - {order.order_no}")

                    col_d1, col_d2, col_d3 = st.columns(3)
                    col_d1.write(f"**状态:** {order.status}")
                    col_d2.write(f"**平台:** {order.platform}")
                    col_d3.write(f"**币种:** {order.currency}")

                    col_d4, col_d5, col_d6 = st.columns(3)
                    col_d4.write(f"**创建日期:** {order.created_date}")
                    col_d5.write(f"**发货日期:** {order.shipped_date or '未发货'}")
                    col_d6.write(f"**完成日期:** {order.completed_date or '未完成'}")

                    st.write(f"**备注:** {order.notes or '无'}")

                    st.divider()
                    st.markdown("**商品明细:**")

                    items_detail = []
                    for item in order.items:
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

                    st.write(f"**订单总额: {order.total_amount:.2f} {order.currency}**")

                    # 售后记录
                    if order.refunds:
                        st.divider()
                        st.markdown("**售后记录:**")

                        refund_detail = []
                        for r in order.refunds:
                            refund_detail.append({
                                "日期": r.refund_date,
                                "退款金额": r.refund_amount,
                                "原因": r.refund_reason,
                                "是否退货": "是" if r.is_returned else "否",
                                "退货数量": r.returned_quantity
                            })

                        st.dataframe(
                            pd.DataFrame(refund_detail),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "退款金额": st.column_config.NumberColumn(format="%.2f")
                            }
                        )

                    if st.button("关闭详情", key=f"close_detail_{selected_order_id}"):
                        del st.session_state[f"show_detail_{selected_order_id}"]
                        st.rerun()

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

    # ================= 4. 删除订单 =================
    st.divider()

    with st.popover("🗑️ 删除订单 (数据回滚)", use_container_width=True):
        st.error("⚠️ 此操作将完整删除订单并回滚库存、资产、财务数据。")

        all_orders = service.get_all_orders(limit=200)
        del_order_options = {f"{o.order_no} - {o.platform} - {o.status}": o.id for o in all_orders}

        selected_del_label = st.selectbox("选择要删除的订单", list(del_order_options.keys()))

        if st.button("🔴 确认删除", type="primary", use_container_width=True):
            try:
                order_id = del_order_options[selected_del_label]
                msg = service.delete_order(order_id)
                st.success(msg)
                st.rerun()
            except Exception as e:
                st.error(f"删除失败: {e}")

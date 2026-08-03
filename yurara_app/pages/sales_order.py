# yurara_app/pages/sales_order.py
"""
线上销售订单管理页面。
支持手动购物车建单、Excel 批量导入、订单状态流转（发货/收款对账）、售后 Dialog 物理联动等核心功能。
"""
import reflex as rx
from ..state.auth_state import AuthState
from ..state.sales_order_state import SalesOrderState, SalesOrderRow
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state, confirm_dialog


def cart_item_row(item: dict) -> rx.Component:
    """渲染购物车中的单项"""
    return rx.table.row(
        rx.table.cell(rx.text(item["product_name"], size="1", weight="medium")),
        rx.table.cell(rx.text(item["variant"], size="1")),
        rx.table.cell(rx.text(item["warehouse_name"], size="1")),
        rx.table.cell(rx.text(item["quantity"].to_string(), size="1", weight="bold")),
        rx.table.cell(
            rx.icon_button(
                rx.icon("trash_2", size=12),
                on_click=lambda: SalesOrderState.remove_from_cart(item["key"]),
                size="1",
                variant="ghost",
                color_scheme="red",
            )
        ),
    )


def order_row_renderer(o: SalesOrderRow) -> rx.Component:
    """渲染订单列表的每一行"""
    return rx.table.row(
        rx.table.cell(
            rx.checkbox(
                checked=o.勾选,
                on_change=lambda _: SalesOrderState.toggle_order_select(o.id),
                size="1",
            )
        ),
        rx.table.cell(rx.text(o.order_no, size="1", weight="bold")),
        rx.table.cell(rx.badge(o.status, size="1", variant="soft", color_scheme="violet")),
        rx.table.cell(rx.text(o.items_summary, size="1", line_clamp=1)),
        rx.table.cell(rx.text(rx.fragment(o.currency, " ", o.total_amount.to_string()), size="1", weight="medium")),
        rx.table.cell(rx.text(rx.fragment(o.currency, " ", o.refunded_amount.to_string()), size="1", color=rx.cond(o.refunded_amount > 0, "red", "slate"))),
        rx.table.cell(rx.text(o.platform, size="1")),
        rx.table.cell(rx.text(o.created_date, size="1")),
        rx.table.cell(rx.text(o.notes, size="1", line_clamp=1, color=rx.color("slate", 9))),
        style={
            "transition": "all 0.15s ease",
            "cursor": "pointer",
            "backgroundColor": rx.cond(o.勾选, rx.color("violet", 2), "transparent"),
        },
    )


def render_preview_order_row(p: dict) -> rx.Component:
    """渲染Excel导入的预览行"""
    return rx.table.row(
        rx.table.cell(rx.text(p["stock_warning"], size="1")),
        rx.table.cell(rx.text(p["order_no"], size="1", weight="bold")),
        rx.table.cell(rx.text(p["platform"], size="1")),
        rx.table.cell(rx.text(p["target_account"], size="1")),
        rx.table.cell(rx.text(p["currency"], size="1")),
        rx.table.cell(rx.text(p["total_qty"].to_string(), size="1")),
        rx.table.cell(rx.text(p["gross_price"].to_string(), size="1")),
        rx.table.cell(rx.text(p["fee"].to_string(), size="1")),
        rx.table.cell(rx.text(p["net_price"].to_string(), size="1", weight="bold", color="green")),
        rx.table.cell(rx.text(p["items_str"], size="1", line_clamp=1)),
    )


def build_manual_order_form() -> rx.Component:
    """构建手动建单表单"""
    return rx.vstack(
        rx.heading("1. 订单基础信息", size="2", weight="bold"),
        rx.grid(
            custom_form_field(
                "订单号",
                rx.input(
                    placeholder="输入订单号（必填）",
                    value=SalesOrderState.order_no_input,
                    on_change=SalesOrderState.set_order_no_input,
                    size="2",
                    width="100%",
                ),
                required=True,
            ),
            custom_form_field(
                "订单日期",
                rx.input(
                    type="date",
                    value=SalesOrderState.order_date_input,
                    on_change=SalesOrderState.set_order_date_input,
                    size="2",
                    width="100%",
                ),
            ),
            custom_form_field(
                "销售平台",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            SalesOrderState.platform_options,
                            lambda p: rx.select.item(p, value=p)
                        )
                    , position="popper", side="bottom"),
                    value=SalesOrderState.platform_input,
                    on_change=SalesOrderState.set_platform_input,
                    size="2",
                    width="100%",
                ),
            ),
            custom_form_field(
                "币种",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            SalesOrderState.all_currencies,
                            lambda curr: rx.select.item(curr, value=curr)
                        )
                    , position="popper", side="bottom"),
                    value=SalesOrderState.currency_input,
                    on_change=SalesOrderState.set_currency_input,
                    size="2",
                    width="100%",
                ),
            ),
            custom_form_field(
                "收款现金账户",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            SalesOrderState.cash_account_options,
                            lambda acc: rx.select.item(acc, value=acc)
                        )
                    , position="popper", side="bottom"),
                    value=SalesOrderState.target_account_input,
                    on_change=SalesOrderState.set_target_account_input,
                    size="2",
                    width="100%",
                ),
            ),
            columns="2",
            spacing="4",
            width="100%",
        ),
        rx.divider(),
        rx.heading("2. 订单商品列表 (添加商品)", size="2", weight="bold"),
        rx.hstack(
            custom_form_field(
                "选择商品",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            SalesOrderState.product_options,
                            lambda p: rx.cond(p != "全部商品", rx.select.item(p, value=p), rx.fragment())
                        )
                    , position="popper", side="bottom"),
                    value=SalesOrderState.sel_p_name,
                    on_change=SalesOrderState.select_p_name,
                    size="2",
                    width="100%",
                ),
            ),
            custom_form_field(
                "选择款式",
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            SalesOrderState.active_variants,
                            lambda v: rx.select.item(v, value=v)
                        )
                    , position="popper", side="bottom"),
                    value=SalesOrderState.sel_v_name,
                    on_change=SalesOrderState.set_sel_v_name,
                    size="2",
                    width="100%",
                ),
            ),
            custom_form_field(
                "数量",
                rx.input(
                    type="number",
                    value=SalesOrderState.sel_qty.to_string(),
                    on_change=SalesOrderState.set_sel_qty,
                    size="2",
                    width="100%",
                ),
            ),
            custom_form_field(
                "出货仓库",
                rx.select.root(
                    rx.select.trigger(placeholder="选择出货仓库"),
                    rx.select.content(
                        rx.foreach(
                            SalesOrderState.warehouse_options,
                            lambda w: rx.select.item(w, value=w)
                        )
                    , position="popper", side="bottom"),
                    value=SalesOrderState.sel_wh_name,
                    on_change=SalesOrderState.set_sel_wh_name,
                    size="2",
                    width="100%",
                ),
            ),
            rx.button(
                rx.icon("plus", size=14),
                "加入订单",
                on_click=SalesOrderState.add_to_cart,
                size="2",
                color_scheme="violet",
                margin_top="auto",
            ),
            spacing="3",
            align_items="end",
            width="100%",
        ),
        
        # 购物车暂存内容展示
        rx.cond(
            SalesOrderState.order_cart,
            rx.vstack(
                rx.text("当前已加入的商品：", size="2", weight="medium"),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("商品名称", size="1"),
                            rx.table.column_header_cell("款式", size="1"),
                            rx.table.column_header_cell("出货仓库", size="1"),
                            rx.table.column_header_cell("数量", size="1"),
                            rx.table.column_header_cell("操作", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(SalesOrderState.order_cart, cart_item_row)
                    ),
                    size="1",
                    width="100%",
                ),
                rx.button(
                    "清空购物车",
                    on_click=SalesOrderState.clear_cart,
                    size="1",
                    variant="soft",
                    color_scheme="red",
                ),
                spacing="2",
                width="100%",
            ),
            rx.callout("🛒 购物车为空，请在上方选择商品并点击“加入订单”", icon="info", color_scheme="gray", size="1", width="100%")
        ),
        rx.divider(),
        rx.heading("3. 结算信息", size="2", weight="bold"),
        rx.grid(
            custom_form_field(
                "订单总价 (含邮费)",
                rx.input(
                    type="number",
                    placeholder="0.00",
                    value=SalesOrderState.total_price_input.to_string(),
                    on_change=SalesOrderState.set_total_price_input,
                    size="2",
                    width="100%",
                ),
            ),
            rx.hstack(
                rx.checkbox(
                    checked=SalesOrderState.deduct_fee_input,
                    on_change=SalesOrderState.toggle_deduct_fee,
                    size="2",
                ),
                rx.text("扣除平台手续费", size="2"),
                spacing="2",
                align="center",
                margin_top="1.5rem",
            ),
            custom_form_field(
                "订单备注",
                rx.input(
                    placeholder="客户名称、渠道明细等说明...",
                    value=SalesOrderState.notes_input,
                    on_change=SalesOrderState.set_notes_input,
                    size="2",
                    width="100%",
                ),
            ),
            columns="2",
            spacing="4",
            width="100%",
        ),
        
        # 结算指标预览
        rx.cond(
            SalesOrderState.cart_item_count > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.text(rx.fragment("总数量: ", SalesOrderState.cart_item_count.to_string(), " 件"), size="2", weight="bold"),
                        rx.spacer(),
                        rx.text(
                            rx.fragment(
                                "商品净入账: ", 
                                SalesOrderState.cart_net_price.to_string(), 
                                " ", 
                                SalesOrderState.currency_input, 
                                " | 净单价: ", 
                                SalesOrderState.cart_net_unit_price.to_string(), 
                                " ", 
                                SalesOrderState.currency_input, 
                                "/件"
                            ), 
                            size="2", 
                            weight="bold", 
                            color="green"
                        ),
                        width="100%"
                    ),
                    rx.text(
                        rx.fragment(
                            "(预估手续费: ", 
                            SalesOrderState.cart_estimated_fee.to_string(), 
                            " JPY/CNY)", 
                            rx.cond(SalesOrderState.cart_booth_shipping_peel > 0, rx.fragment(" | 已自动剥离 Booth 预估邮费: ", SalesOrderState.cart_booth_shipping_peel.to_string(), " JPY"), rx.fragment())
                        ), 
                        size="1", 
                        color="slate"
                    ),
                    spacing="1",
                    width="100%"
                ),
                padding="0.5rem 1rem",
                background=rx.color("green", 2),
                width="100%"
            )
        ),
        
        rx.button(
            "✅ 提交新建订单",
            on_click=SalesOrderState.submit_create_order,
            size="3",
            color_scheme="violet",
            width="100%",
            disabled=SalesOrderState.cart_item_count == 0,
        ),
        spacing="4",
        width="100%",
    )


def build_excel_import_form() -> rx.Component:
    """构建Excel导入面板"""
    return rx.vstack(
        rx.callout(
            "📊 导入 Excel 列名规范：订单号 | 商品名 | 商品型号 | 数量 | 销售平台 | 订单总额 | 币种 | 出货仓库。多款式请用英文分号 (;) 隔开。",
            icon="info",
            color_scheme="violet",
            size="1",
            width="100%",
        ),
        rx.upload(
            rx.vstack(
                rx.button("选择 Excel 模板文件", color_scheme="violet", variant="soft", size="2"),
                rx.text("或者拖拽文件到此处（仅限 .xlsx, .xls）", size="1", color=rx.color("slate", 9)),
                align="center",
                spacing="1",
                padding="1rem",
            ),
            id="excel_upload",
            border="1px dashed var(--slate-6)",
            border_radius="6px",
            background=rx.color("slate", 2),
            on_drop=SalesOrderState.handle_excel_import(rx.upload_files(upload_id="excel_upload")),
            width="100%",
        ),
        rx.cond(
            rx.selected_files("excel_upload"),
            rx.hstack(
                rx.foreach(
                    rx.selected_files("excel_upload"),
                    lambda file: rx.badge(f"📁 {file}", color_scheme="violet", variant="soft")
                ),
                spacing="2",
                flex_wrap="wrap",
                width="100%",
            )
        ),
        rx.button(
            "🔍 上传并开始解析校验 Excel",
            on_click=SalesOrderState.handle_excel_import(
                rx.upload_files(upload_id="excel_upload")
            ),
            color_scheme="violet",
            width="100%",
            size="2",
        ),
        
        # 错误反馈
        rx.cond(
            SalesOrderState.excel_import_errors,
            rx.vstack(
                rx.text("❌ Excel 校验发现以下数据问题：", size="2", color="red", weight="bold"),
                rx.foreach(
                    SalesOrderState.excel_import_errors,
                    lambda err: rx.text(rx.fragment("• ", err), size="1", color="red")
                ),
                spacing="1",
                width="100%",
                padding="0.5rem",
                background=rx.color("red", 2),
                border_radius="6px",
            )
        ),
        
        # 校验成功预览
        rx.cond(
            SalesOrderState.parsed_preview_orders,
            rx.vstack(
                rx.hstack(
                    rx.text("✅ Excel 校验成功！待入库订单预览：", size="2", weight="medium", color="green"),
                    rx.spacer(),
                    rx.button(
                        "🚀 确认无误，开始批量导入并记账",
                        on_click=SalesOrderState.submit_batch_import,
                        size="2",
                        color_scheme="green",
                    ),
                    width="100%",
                    align="center",
                ),
                rx.cond(
                    SalesOrderState.any_out_of_stock,
                    rx.callout("⚠️ 包含缺货超卖订单，系统将自动允许在“待发货”阶段进行库存调整。", icon="triangle_alert", color_scheme="orange", size="1", width="100%"),
                    rx.fragment()
                ),
                rx.scroll_area(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("状态盘点", size="1"),
                                rx.table.column_header_cell("订单号", size="1"),
                                rx.table.column_header_cell("平台", size="1"),
                                rx.table.column_header_cell("收款账户", size="1"),
                                rx.table.column_header_cell("币种", size="1"),
                                rx.table.column_header_cell("数量", size="1"),
                                rx.table.column_header_cell("原总价", size="1"),
                                rx.table.column_header_cell("预估手续费", size="1"),
                                rx.table.column_header_cell("净入账", size="1"),
                                rx.table.column_header_cell("商品明细", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(SalesOrderState.parsed_preview_orders, render_preview_order_row)
                        ),
                        size="1",
                        width="100%",
                    ),
                    width="100%",
                ),
                spacing="3",
                width="100%",
            )
        ),
        spacing="4",
        width="100%",
    )


def stat_metric_card(label: str, value: rx.Var, color_scheme: str = "violet", icon: str = "circle") -> rx.Component:
    """漂亮的统计卡片"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=16, color=rx.color(color_scheme, 9)),
                rx.text(label, size="1", color=rx.color("slate", 10)),
                spacing="2",
                align="center",
            ),
            rx.text(value.to_string(), size="6", weight="bold"),
            spacing="1",
            align_items="start",
        ),
        padding="0.75rem",
        width="100%",
    )


def order_detail_modal() -> rx.Component:
    """订单详细查看与备注修改 Dialog"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.heading(rx.fragment("📝 订单详情 - ", SalesOrderState.detail_order_no), size="3"),
                rx.spacer(),
                rx.dialog.close(
                    rx.icon_button(rx.icon("x", size=16), variant="ghost", color_scheme="gray")
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            
            rx.grid(
                custom_form_field("状态", rx.badge(SalesOrderState.detail_status, size="1", color_scheme="violet")),
                custom_form_field("销售平台", rx.text(SalesOrderState.detail_platform, size="2", weight="medium")),
                custom_form_field("交易币种", rx.text(SalesOrderState.detail_currency, size="2", weight="medium")),
                custom_form_field("下单时间", rx.text(SalesOrderState.detail_created_date, size="2")),
                custom_form_field("发货时间", rx.text(SalesOrderState.detail_shipped_date, size="2")),
                custom_form_field("收款完成时间", rx.text(SalesOrderState.detail_completed_date, size="2")),
                columns="3",
                spacing="3",
                width="100%",
                margin_bottom="0.5rem"
            ),
            
            custom_form_field("物理收款账户", rx.text(SalesOrderState.detail_target_account, size="2", weight="bold")),
            
            rx.divider(),
            rx.text("📦 商品清单", size="2", weight="bold"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("商品名称", size="1"),
                        rx.table.column_header_cell("款式颜色", size="1"),
                        rx.table.column_header_cell("发货仓", size="1"),
                        rx.table.column_header_cell("数量", size="1"),
                        rx.table.column_header_cell("单价", size="1"),
                        rx.table.column_header_cell("小计", size="1"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        SalesOrderState.detail_items,
                        lambda item: rx.table.row(
                            rx.table.cell(rx.text(item["product_name"], size="1")),
                            rx.table.cell(rx.text(item["variant"], size="1")),
                            rx.table.cell(rx.text(item["warehouse_name"], size="1")),
                            rx.table.cell(rx.text(item["quantity"].to_string(), size="1")),
                            rx.table.cell(rx.text(item["unit_price"].to_string(), size="1")),
                            rx.table.cell(rx.text(item["subtotal"].to_string(), size="1", weight="medium")),
                        )
                    )
                ),
                size="1",
                width="100%",
            ),
            
            rx.hstack(
                rx.spacer(),
                rx.text(
                    rx.fragment("订单记账总额: ", SalesOrderState.detail_total_amount.to_string(), " ", SalesOrderState.detail_currency), 
                    size="2", 
                    weight="bold"
                ),
            ),
            
            rx.divider(),
            
            # 可修改的表单内容
            rx.vstack(
                rx.text("✏️ 修改基础备注与优惠", size="2", weight="bold"),
                custom_form_field(
                    "优惠说明",
                    rx.input(
                        value=SalesOrderState.edit_discount_note,
                        on_change=SalesOrderState.set_edit_discount_note,
                        size="2",
                        width="100%",
                    )
                ),
                custom_form_field(
                    "系统备注",
                    rx.text_area(
                        value=SalesOrderState.edit_notes,
                        on_change=SalesOrderState.set_edit_notes,
                        size="2",
                        width="100%",
                    )
                ),
                rx.hstack(
                    rx.button("💾 保存修改", on_click=SalesOrderState.submit_update_notes, size="2", color_scheme="violet"),
                    rx.spacer(),
                    rx.cond(
                        SalesOrderState.show_delete_confirm,
                        rx.hstack(
                            rx.text("⚠️ 确认全额回滚删除吗？不可撤销！", size="1", color="red"),
                            rx.button("💥 确定删除", on_click=SalesOrderState.submit_delete_order, size="2", color_scheme="red"),
                            rx.button("取消", on_click=SalesOrderState.cancel_delete_confirm, size="2", variant="soft", color_scheme="gray"),
                            spacing="2",
                            align="center"
                        ),
                        rx.button("🗑️ 删除整个订单", on_click=SalesOrderState.open_delete_confirm, size="2", color_scheme="red")
                    ),
                    width="100%",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="650px",
        ),
        open=SalesOrderState.show_detail_flag,
        on_open_change=SalesOrderState.set_show_detail_flag,
    )


def refund_dialog_modal() -> rx.Component:
    """售后 Dialog 联动控制"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.heading("🔧 线下/线上售后联动管理", size="3"),
                rx.spacer(),
                rx.dialog.close(
                    rx.icon_button(rx.icon("x", size=16), variant="ghost", color_scheme="gray")
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            
            # 1. 已有售后展示
            rx.cond(
                SalesOrderState.existing_refunds,
                rx.vstack(
                    rx.text("📋 已有售后记录审计流水：", size="2", weight="bold"),
                    rx.foreach(
                        SalesOrderState.existing_refunds,
                        lambda ref: rx.vstack(
                            rx.hstack(
                                rx.text(rx.fragment("🕒 ", ref["refund_date"]), size="1", weight="medium"),
                                rx.badge(ref["refund_reason"], color_scheme="gray", size="1"),
                                rx.spacer(),
                                rx.text(rx.fragment("¥ ", ref["refund_amount"].to_string()), size="2", weight="bold", color="red"),
                                rx.text(rx.fragment(" 退实物:", rx.cond(ref["is_returned"], "是", "否"), " | 补发:", rx.cond(ref["is_resend"], "是", "否")), size="1", color="slate"),
                                spacing="2",
                                align="center",
                                width="100%"
                            ),
                            rx.cond(
                                ref["is_editing"],
                                rx.hstack(
                                    rx.input(value=SalesOrderState.editing_refund_amount.to_string(), on_change=SalesOrderState.set_editing_refund_amount, size="1", style={"width": "100px"}),
                                    rx.input(value=SalesOrderState.editing_refund_reason, on_change=SalesOrderState.set_editing_refund_reason, size="1"),
                                    rx.button("保存", on_click=SalesOrderState.submit_edit_refund, size="1", color_scheme="green"),
                                    rx.button("取消", on_click=SalesOrderState.cancel_edit_refund, size="1", variant="soft", color_scheme="gray"),
                                    spacing="2",
                                    width="100%",
                                ),
                                rx.hstack(
                                    rx.button("✏️ 编辑", on_click=lambda: SalesOrderState.start_edit_refund(ref["id"]), size="1", variant="soft", color_scheme="violet"),
                                    rx.button("🗑️ 回滚回退", on_click=lambda: SalesOrderState.submit_delete_refund(ref["id"]), size="1", variant="soft", color_scheme="red"),
                                    spacing="2",
                                )
                            ),
                            border="1px solid var(--slate-4)",
                            padding="0.5rem",
                            border_radius="6px",
                            width="100%",
                        )
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.fragment()
            ),
            
            rx.divider(),
            
            # 2. 新增售后表单
            rx.vstack(
                rx.text("➕ 登记新售后记录：", size="2", weight="bold"),
                custom_form_field(
                    "退款/售后金额 (CNY/JPY)",
                    rx.input(
                        type="number",
                        placeholder="0.00",
                        value=SalesOrderState.ref_amount_input.to_string(),
                        on_change=SalesOrderState.set_ref_amount_input,
                        size="2",
                        width="100%"
                    ),
                    helper="若仅补发货物且无退款，请填 0。"
                ),
                custom_form_field(
                    "售后原因 (必填)",
                    rx.input(
                        placeholder="请输入售后原因，审计必填...",
                        value=SalesOrderState.ref_reason_input,
                        on_change=SalesOrderState.set_ref_reason_input,
                        size="2",
                        width="100%"
                    )
                ),
                
                rx.grid(
                    rx.hstack(
                        rx.checkbox(checked=SalesOrderState.ref_is_returned, on_change=SalesOrderState.toggle_ref_is_returned, size="2"),
                        rx.text("🔄 客户退回物理实物 (退货入库)", size="2"),
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.checkbox(checked=SalesOrderState.ref_is_resend, on_change=SalesOrderState.toggle_ref_is_resend, size="2"),
                        rx.text("📦 补发商品或配件 (补发出库)", size="2"),
                        spacing="2",
                        align="center",
                    ),
                    columns="2",
                    width="100%",
                    margin_top="0.5rem"
                ),
                
                # 2.1 退货清单
                rx.cond(
                    SalesOrderState.ref_is_returned,
                    rx.vstack(
                        rx.text("选择退货入库的商品数量：", size="1", weight="bold", color="slate"),
                        rx.foreach(
                            SalesOrderState.ref_returned_items,
                            lambda item: rx.hstack(
                                rx.text(rx.fragment(item["product_name"], " (", item["variant"], ")"), size="1", weight="medium"),
                                rx.spacer(),
                                rx.text(rx.fragment("出货仓: ", item["warehouse_name"], " | 原数:", item["max_quantity"].to_string()), size="1", color="slate"),
                                rx.input(
                                    placeholder="退回数量",
                                    type="number",
                                    on_blur=lambda val: SalesOrderState.update_returned_qty(item["order_item_id"], val),
                                    size="1",
                                    style={"width": "80px"}
                                ),
                                spacing="3",
                                width="100%"
                            )
                        ),
                        spacing="2",
                        width="100%",
                        padding="0.5rem",
                        background=rx.color("slate", 3),
                        border_radius="6px"
                    )
                ),
                
                # 2.2 补发清单
                rx.cond(
                    SalesOrderState.ref_is_resend,
                    rx.vstack(
                        rx.text("选择需要补发出库的配件或整套：", size="1", weight="bold", color="slate"),
                        rx.foreach(
                            SalesOrderState.ref_resend_items,
                            lambda item: rx.vstack(
                                rx.hstack(
                                    rx.text(rx.fragment(item.product_name, " (", item.variant, ")"), size="1", weight="bold"),
                                    rx.spacer(),
                                    rx.text(rx.fragment("出货仓: ", item.warehouse_name), size="1", color="slate"),
                                    spacing="2",
                                    width="100%"
                                ),
                                rx.hstack(
                                    rx.select.root(
                                        rx.select.trigger(),
                                        rx.select.content(
                                            rx.foreach(
                                                item.part_options,
                                                lambda part: rx.select.item(part, value=part)
                                            )
                                        , position="popper", side="bottom"),
                                        value=item.part_name,
                                        on_change=lambda val: SalesOrderState.update_resend_part(item.order_item_id, val),
                                        size="1",
                                        placeholder="补发整套或指定部位"
                                    ),
                                    rx.select.root(
                                        rx.select.trigger(),
                                        rx.select.content(
                                            rx.foreach(
                                                SalesOrderState.warehouse_options,
                                                lambda w: rx.cond(w != "未分配", rx.select.item(w, value=w), rx.fragment())
                                            )
                                        , position="popper", side="bottom"),
                                        value=item.warehouse_name,
                                        on_change=lambda val: SalesOrderState.update_resend_warehouse(item.order_item_id, val),
                                        size="1",
                                    ),
                                    rx.input(
                                        placeholder="数量",
                                        type="number",
                                        on_blur=lambda val: SalesOrderState.update_resend_qty(item.order_item_id, val),
                                        size="1",
                                        style={"width": "70px"}
                                    ),
                                    spacing="2",
                                    width="100%"
                                ),
                                padding="0.5rem",
                                border="1px dashed var(--slate-5)",
                                width="100%"
                            )
                        ),
                        spacing="2",
                        width="100%",
                        padding="0.5rem",
                        background=rx.color("slate", 3),
                        border_radius="6px"
                    )
                ),
                
                rx.button(
                    "确认登记提交该售后单",
                    on_click=SalesOrderState.submit_add_refund,
                    size="3",
                    color_scheme="red",
                    width="100%",
                    margin_top="0.5rem"
                ),
                spacing="3",
                width="100%",
            ),
            max_width="600px",
        ),
        open=SalesOrderState.show_refund_form,
        on_open_change=SalesOrderState.set_show_refund_form,
    )


def sales_order_page() -> rx.Component:
    """线上销售管理主页面组件"""
    return page_layout(
        rx.vstack(
            # 顶部 Tab 面板
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("➕ 创建新订单 (购物车模式)", value="manual"),
                    rx.tabs.trigger("📥 批量导入订单 (Excel)", value="bulk"),
                ),
                rx.card(
                    rx.tabs.content(build_manual_order_form(), value="manual"),
                    rx.tabs.content(build_excel_import_form(), value="bulk"),
                    width="100%",
                    padding="1rem",
                    margin_top="0.5rem",
                ),
                default_value="manual",
                width="100%",
            ),
            
            rx.divider(),
            
            # 商品选择与 KPI 概览数据
            rx.hstack(
                rx.text("🔍 商品筛选：", size="2", weight="medium", margin_top="0.5rem"),
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            SalesOrderState.product_options,
                            lambda p: rx.select.item(p, value=p)
                        )
                    , position="popper", side="bottom"),
                    value=SalesOrderState.selected_product_filter,
                    on_change=SalesOrderState.select_product_filter,
                    size="2",
                    style={"maxWidth": "250px"},
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            
            # 统计指标
            rx.grid(
                stat_metric_card("总订单数", SalesOrderState.stat_total, "violet", "layers"),
                stat_metric_card("待发货 (仓储发货)", SalesOrderState.stat_pending, "orange", "package"),
                stat_metric_card("已发货 (已扣物存)", SalesOrderState.stat_shipped, "blue", "truck"),
                stat_metric_card("已完成 (收款对账)", SalesOrderState.stat_completed, "green", "circle_check"),
                stat_metric_card("售后中 (财务退款/补发)", SalesOrderState.stat_after_sales, "red", "wrench"),
                columns="5",
                spacing="3",
                width="100%",
            ),
            
            rx.divider(),
            
            # 订单主列表
            data_card(
                "📋 线上销售订单列表",
                rx.vstack(
                    # 分类 Tab 过滤
                    rx.tabs.root(
                        rx.tabs.list(
                            rx.tabs.trigger("全部", value="all"),
                            rx.tabs.trigger("待发货", value="pending"),
                            rx.tabs.trigger("已发货", value="shipped"),
                            rx.tabs.trigger("已完成", value="completed"),
                            rx.tabs.trigger("售后中", value="after_sales"),
                        ),
                        value=SalesOrderState.active_tab,
                        on_change=SalesOrderState.select_tab,
                        width="100%",
                    ),
                    
                    # 查询输入框
                    rx.input(
                        placeholder="🔍 输入订单号、平台、备注、状态或商品明细筛选...",
                        value=SalesOrderState.search_query,
                        on_change=SalesOrderState.set_search_query,
                        width="100%",
                        size="2",
                    ),
                    
                    # 批量操作辅助栏
                    rx.hstack(
                        rx.button("☑️ 全选", on_click=SalesOrderState.toggle_select_all, size="1", variant="soft", color_scheme="gray"),
                        rx.spacer(),
                        rx.text(rx.fragment("已勾选 ", SalesOrderState.selected_count.to_string(), " 项订单"), size="1", color=rx.color("slate", 10)),
                        rx.text(rx.fragment("折合合计金额: ¥ ", SalesOrderState.selected_amount_sum.to_string()), size="2", weight="bold", color="red"),
                        spacing="3",
                        align="center",
                        width="100%",
                    ),
                    
                    # 订单表格
                    rx.cond(
                        SalesOrderState.has_orders,
                        rx.vstack(
                            rx.scroll_area(
                                rx.table.root(
                                    rx.table.header(
                                        rx.table.row(
                                            rx.table.column_header_cell("选择", size="1"),
                                            rx.table.column_header_cell("订单号", size="1"),
                                            rx.table.column_header_cell("状态", size="1"),
                                            rx.table.column_header_cell("商品明细", size="1"),
                                            rx.table.column_header_cell("金额", size="1"),
                                            rx.table.column_header_cell("已退款", size="1"),
                                            rx.table.column_header_cell("平台", size="1"),
                                            rx.table.column_header_cell("日期", size="1"),
                                            rx.table.column_header_cell("备注说明", size="1"),
                                        )
                                    ),
                                    rx.table.body(
                                        rx.foreach(SalesOrderState.paginated_orders, order_row_renderer)
                                    ),
                                    size="1",
                                    width="100%",
                                ),
                                width="100%",
                            ),
                            # 分页控制栏
                            rx.hstack(
                                rx.button(
                                    "上一页",
                                    on_click=SalesOrderState.prev_page,
                                    disabled=~SalesOrderState.has_prev_page,
                                    size="1",
                                    variant="soft",
                                ),
                                rx.text(SalesOrderState.page_info, size="1", color=rx.color("slate", 10)),
                                rx.button(
                                    "下一页",
                                    on_click=SalesOrderState.next_page,
                                    disabled=~SalesOrderState.has_next_page,
                                    size="1",
                                    variant="soft",
                                ),
                                spacing="3",
                                align="center",
                                justify="center",
                                width="100%",
                                padding_y="0.25rem",
                            ),
                            width="100%",
                            spacing="3",
                        ),
                        empty_state("该筛选分类下无对应的线上销售订单数据")
                    ),
                    
                    # 操作动作区
                    rx.hstack(
                        rx.button(
                            rx.icon("package", size=14),
                            rx.fragment("📦 发货 (", SalesOrderState.selected_count.to_string(), ")"),
                            on_click=SalesOrderState.ship_selected_orders,
                            disabled=~SalesOrderState.can_ship,
                            size="2",
                            color_scheme="orange",
                        ),
                        rx.button(
                            rx.icon("badge_check", size=14),
                            rx.fragment("✅ 收款完成对账 (", SalesOrderState.selected_count.to_string(), ")"),
                            on_click=SalesOrderState.complete_selected_orders,
                            disabled=~SalesOrderState.can_complete,
                            size="2",
                            color_scheme="green",
                        ),
                        rx.button(
                            rx.icon("wrench", size=14),
                            "🔧 售后处理",
                            on_click=lambda: SalesOrderState.open_refund_dialog(SalesOrderState.single_selected_id),
                            disabled=~SalesOrderState.can_refund,
                            size="2",
                            color_scheme="red",
                        ),
                        rx.button(
                            rx.icon("eye", size=14),
                            "📄 查看/修改详情",
                            on_click=lambda: SalesOrderState.open_order_detail(SalesOrderState.single_selected_id),
                            disabled=~SalesOrderState.is_single_selected,
                            size="2",
                            variant="soft",
                            color_scheme="gray",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                )
            ),
            
            # 引入模态框 Dialog
            order_detail_modal(),
            refund_dialog_modal(),
            
            spacing="4",
            width="100%",
        ),
        title="🛒 线上销售订单管理"
    )

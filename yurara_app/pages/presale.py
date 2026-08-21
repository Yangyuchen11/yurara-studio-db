# yurara_app/pages/presale.py
"""
预售销售管理页面。
支持定金购物车建单、尾款单号精确绑定、尾款一键物理解绑、批量导入定金或尾款 Excel、退货补发售后物理联动等核心预售业务流转。
"""
import reflex as rx
from ..state.auth_state import AuthState
from ..state.presale_state import PresaleState, PresaleOrderRow
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state


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
                on_click=lambda: PresaleState.remove_from_pre_cart(item["key"]),
                size="1",
                variant="ghost",
                color_scheme="red",
            )
        ),
    )


def order_row_renderer(o: PresaleOrderRow) -> rx.Component:
    """渲染预售订单列表的每一行"""
    return rx.table.row(
        rx.table.cell(
            rx.checkbox(
                checked=o.勾选,
                on_change=lambda _: PresaleState.toggle_order_select(o.id),
                size="1",
            )
        ),
        rx.table.cell(rx.text(o.order_no, size="1", weight="bold")),
        rx.table.cell(rx.text(o.final_order_no, size="1", weight="medium", color=rx.cond(o.final_order_no != "-", "violet", "slate"))),
        rx.table.cell(rx.badge(o.status, size="1", variant="soft", color_scheme="violet")),
        rx.table.cell(rx.text(o.items_summary, size="1", line_clamp=1)),
        rx.table.cell(rx.text(rx.fragment(o.currency, " ", o.deposit_amount.to_string()), size="1", weight="medium")),
        rx.table.cell(rx.text(rx.fragment(o.currency, " ", o.final_amount.to_string()), size="1", weight="medium")),
        rx.table.cell(rx.text(rx.fragment(o.currency, " ", o.refunded_amount.to_string()), size="1", color=rx.cond(o.refunded_amount > 0, "red", "slate"))),
        rx.table.cell(rx.text(o.discount_note, size="1")),
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
    """渲染Excel导入的预售预览行"""
    return rx.table.row(
        rx.table.cell(rx.text(p["stock_warning"], size="1", color="green")),
        rx.table.cell(rx.text(p["order_no"], size="1", weight="bold")),
        rx.table.cell(rx.text(p["platform"], size="1")),
        rx.table.cell(rx.text(p["target_account"], size="1")),
        rx.table.cell(rx.text(p["currency"], size="1")),
        rx.table.cell(rx.text(p["total_qty"].to_string(), size="1")),
        rx.table.cell(rx.text(p["gross_price"].to_string(), size="1")),
        rx.table.cell(rx.text(p["fee"].to_string(), size="1")),
        rx.table.cell(rx.text(p["net_price"].to_string(), size="1", weight="bold", color="green")),
        rx.table.cell(rx.text(p["discount_note"], size="1")),
        rx.table.cell(rx.text(p["items_str"], size="1", line_clamp=1)),
    )


def build_presale_create_form() -> rx.Component:
    """构建预售手动建单/绑定尾款表单"""
    return rx.vstack(
        rx.segmented_control.root(
            rx.segmented_control.item("1️⃣ 创建主定金订单", value="1️⃣ 创建主定金订单"),
            rx.segmented_control.item("2️⃣ 绑定尾款单", value="2️⃣ 绑定尾款单"),
            value=PresaleState.create_mode,
            on_change=lambda val: PresaleState.set_create_mode(val),
            size="2",
            width="100%",
        ),
        rx.divider(),
        
        # 模式一：创建主定金
        rx.cond(
            PresaleState.create_mode == "1️⃣ 创建主定金订单",
            rx.vstack(
                rx.heading("1. 定金基础信息", size="2", weight="bold"),
                rx.grid(
                    custom_form_field(
                        "定金单号",
                        rx.input(
                            placeholder="输入定金单号（必填）",
                            value=PresaleState.pre_order_no,
                            on_change=PresaleState.set_pre_order_no,
                            size="2",
                            width="100%",
                        ),
                        required=True,
                    ),
                    custom_form_field(
                        "下单日期",
                        rx.input(
                            type="date",
                            value=PresaleState.pre_date_input,
                            on_change=PresaleState.set_pre_date_input,
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
                                    PresaleState.platform_options,
                                    lambda p: rx.select.item(p, value=p)
                                )
                            , position="popper", side="bottom"),
                            value=PresaleState.pre_plat,
                            on_change=PresaleState.set_pre_plat,
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
                                     PresaleState.all_currencies,
                                     lambda curr: rx.select.item(curr, value=curr)
                                 )
                             , position="popper", side="bottom"),
                            value=PresaleState.pre_curr,
                            on_change=PresaleState.set_pre_curr,
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
                                    PresaleState.cash_account_options,
                                    lambda acc: rx.select.item(acc, value=acc)
                                )
                            , position="popper", side="bottom"),
                            value=PresaleState.pre_target_account,
                            on_change=PresaleState.set_pre_target_account,
                            size="2",
                            width="100%",
                ),
                    ),
                    columns="2",
                    spacing="4",
                    width="100%",
                ),
                rx.divider(),
                rx.heading("2. 定金商品清单", size="2", weight="bold"),
                rx.hstack(
                    custom_form_field(
                        "选择商品",
                        rx.select.root(
                            rx.select.trigger(),
                            rx.select.content(
                                rx.foreach(
                                    PresaleState.product_options,
                                    lambda p: rx.cond(p != "全部商品", rx.select.item(p, value=p), rx.fragment())
                                )
                            , position="popper", side="bottom"),
                            value=PresaleState.sel_p_name,
                            on_change=PresaleState.select_p_name,
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
                                    PresaleState.active_variants,
                                    lambda v: rx.select.item(v, value=v)
                                )
                            , position="popper", side="bottom"),
                            value=PresaleState.sel_v_name,
                            on_change=PresaleState.set_sel_v_name,
                            size="2",
                            width="100%",
                        ),
                    ),
                    custom_form_field(
                        "数量",
                        rx.input(
                            type="number",
                            value=PresaleState.sel_qty.to_string(),
                            on_change=PresaleState.set_sel_qty,
                            size="2",
                            width="100%",
                        ),
                    ),
                    custom_form_field(
                        "预售仓",
                        rx.select.root(
                            rx.select.trigger(placeholder="选择出货仓库"),
                            rx.select.content(
                                rx.foreach(
                                    PresaleState.warehouse_options,
                                    lambda w: rx.select.item(w, value=w)
                                )
                            , position="popper", side="bottom"),
                            value=PresaleState.sel_wh_name,
                            on_change=PresaleState.set_sel_wh_name,
                            size="2",
                            width="100%",
                        ),
                    ),
                    rx.button(
                        rx.icon("plus", size=14),
                        "加进清单",
                        on_click=PresaleState.add_to_pre_cart,
                        size="2",
                        color_scheme="violet",
                        margin_top="auto",
                    ),
                    spacing="3",
                    align_items="end",
                    width="100%",
                ),
                rx.cond(
                    PresaleState.pre_cart,
                    rx.vstack(
                        rx.text("已录入的商品清单：", size="2", weight="medium"),
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
                                rx.foreach(PresaleState.pre_cart, cart_item_row)
                            ),
                            size="1",
                            width="100%",
                        ),
                        rx.button("清空商品", on_click=PresaleState.clear_pre_cart, size="1", variant="soft", color_scheme="red"),
                        spacing="2",
                        width="100%",
                    ),
                    rx.callout("🛒 定金商品表为空，请在上方添加商品以关联定金订单", icon="info", color_scheme="gray", size="1", width="100%")
                ),
                rx.divider(),
                rx.heading("3. 结算提交", size="2", weight="bold"),
                rx.grid(
                    custom_form_field(
                        "预售定金总价",
                        rx.input(
                            type="number",
                            placeholder="0.00",
                            value=PresaleState.pre_tp.to_string(),
                            on_change=PresaleState.set_pre_tp,
                            size="2",
                            width="100%",
                        ),
                    ),
                    rx.hstack(
                        rx.checkbox(
                            checked=PresaleState.pre_fee,
                            on_change=PresaleState.toggle_pre_fee,
                            size="2",
                        ),
                        rx.text("扣除平台手续费(推荐)", size="2"),
                        spacing="2",
                        align="center",
                        margin_top="1.5rem",
                    ),
                    custom_form_field(
                        "优惠说明 (选填)",
                        rx.input(
                            placeholder="如：减5元/包邮",
                            value=PresaleState.pre_discount,
                            on_change=PresaleState.set_pre_discount,
                            size="2",
                            width="100%",
                        ),
                    ),
                    custom_form_field(
                        "备注",
                        rx.input(
                            placeholder="输入定金单备注信息...",
                            value=PresaleState.pre_notes,
                            on_change=PresaleState.set_pre_notes,
                            size="2",
                            width="100%",
                        ),
                    ),
                    columns="2",
                    spacing="4",
                    width="100%",
                ),
                rx.cond(
                    PresaleState.cart_item_count > 0,
                    rx.card(
                        rx.hstack(
                            rx.text(rx.fragment("已分配: ", PresaleState.cart_item_count.to_string(), " 件"), size="2", weight="bold"),
                            rx.spacer(),
                            rx.text(rx.fragment("预估实际收回定金: ", PresaleState.cart_net_price.to_string(), " ", PresaleState.pre_curr), size="2", weight="bold", color="green"),
                        ),
                        padding="0.5rem 1rem",
                        background=rx.color("green", 2),
                        width="100%",
                    )
                ),
                rx.button(
                    "🚀 创建定金主订单",
                    on_click=PresaleState.submit_presale_deposit,
                    size="3",
                    color_scheme="violet",
                    width="100%",
                    disabled=PresaleState.cart_item_count == 0,
                ),
                spacing="4",
                width="100%",
            ),
            
            # 模式二：绑定尾款
            rx.vstack(
                rx.heading("🔗 精确查找原始定金单", size="2", weight="bold"),
                rx.hstack(
                    rx.input(
                        placeholder="请输入原始预售定金单号...",
                        value=PresaleState.search_dep_no,
                        on_change=PresaleState.set_search_dep_no,
                        size="2",
                        width="100%"
                    ),
                    rx.button("🔍 锁定单据", on_click=PresaleState.search_deposit_order, size="2", color_scheme="violet"),
                    spacing="2",
                    width="100%"
                ),
                
                rx.cond(
                    PresaleState.show_search_lock,
                    rx.vstack(
                        rx.card(
                            rx.vstack(
                                rx.text("✅ 定金单锁定成功！", size="2", weight="bold", color="green"),
                                rx.grid(
                                    rx.text(rx.fragment("下单日期: ", PresaleState.found_deposit_order_date), size="1", color="slate"),
                                    rx.text(rx.fragment("销售平台: ", PresaleState.found_deposit_order_platform), size="1", color="slate"),
                                    rx.text(rx.fragment("原单币种: ", PresaleState.found_deposit_order_currency), size="1", color="slate"),
                                    columns="3",
                                    width="100%"
                                ),
                                rx.text("原商品清单：", size="1", weight="bold"),
                                rx.table.root(
                                    rx.table.header(
                                        rx.table.row(
                                            rx.table.column_header_cell("商品", size="1"),
                                            rx.table.column_header_cell("款式", size="1"),
                                            rx.table.column_header_cell("数量", size="1"),
                                        )
                                    ),
                                    rx.table.body(
                                        rx.foreach(
                                            PresaleState.found_deposit_order_items,
                                            lambda item: rx.table.row(
                                                rx.table.cell(rx.text(item["product_name"], size="1")),
                                                rx.table.cell(rx.text(item["variant"], size="1")),
                                                rx.table.cell(rx.text(item["quantity"].to_string(), size="1")),
                                            )
                                        )
                                    ),
                                    size="1",
                                    width="100%"
                                ),
                                spacing="2",
                                width="100%"
                            ),
                            padding="0.75rem",
                            background=rx.color("green", 2),
                            width="100%"
                        ),
                        rx.divider(),
                        rx.heading("录入尾款绑定信息", size="2", weight="bold"),
                        rx.cond(
                            PresaleState.is_existing_final_no,
                            rx.callout(
                                PresaleState.existing_final_hint,
                                icon="info",
                                color_scheme="blue",
                                size="1",
                                width="100%"
                            )
                        ),
                        rx.grid(
                            custom_form_field(
                                "尾款订单号 (必填)",
                                rx.input(
                                    placeholder="输入绑定的尾款单号",
                                    value=PresaleState.final_no_input,
                                    on_change=PresaleState.set_final_no_input,
                                    size="2",
                                    width="100%",
                                ),
                            ),
                            rx.cond(
                                ~PresaleState.is_existing_final_no,
                                custom_form_field(
                                    rx.fragment("实收尾款金额 (", PresaleState.found_deposit_order_currency, ")"),
                                    rx.input(
                                        type="number",
                                        placeholder="0.00",
                                        value=PresaleState.final_amount_input.to_string(),
                                        on_change=PresaleState.set_final_amount_input,
                                        size="2",
                                        width="100%",
                                    ),
                                ),
                                custom_form_field(
                                    "尾款金额状态",
                                    rx.badge("🔗 共享合并尾款金额", color_scheme="blue", size="2")
                                )
                            ),
                            columns="2",
                            spacing="4",
                            width="100%"
                        ),
                        rx.cond(
                            ~PresaleState.is_existing_final_no,
                            rx.hstack(
                                rx.checkbox(
                                    checked=PresaleState.pre_fee_final,
                                    on_change=PresaleState.toggle_pre_fee_final,
                                    size="2"
                                ),
                                rx.text("扣除尾款平台手续费(推荐)", size="2"),
                                custom_form_field(
                                    "尾款备注说明",
                                    rx.input(
                                        placeholder="优惠抵扣或发货备注...",
                                        value=PresaleState.f_notes,
                                        on_change=PresaleState.set_f_notes,
                                        size="2",
                                        width="100%"
                                    )
                                ),
                                spacing="3",
                                align="center",
                                width="100%"
                            ),
                            custom_form_field(
                                "尾款备注说明",
                                rx.input(
                                    placeholder="优惠抵扣或发货备注...",
                                    value=PresaleState.f_notes,
                                    on_change=PresaleState.set_f_notes,
                                    size="2",
                                    width="100%"
                                )
                            )
                        ),
                        rx.cond(
                            ~PresaleState.is_existing_final_no,
                            rx.card(
                                rx.hstack(
                                    rx.text("尾款收支演算估算：", size="2", weight="medium"),
                                    rx.spacer(),
                                    rx.text(
                                        rx.fragment(
                                            "预估实际尾款净收益: ", 
                                            PresaleState.final_net_price.to_string(), 
                                            " ", 
                                            PresaleState.found_deposit_order_currency
                                        ), 
                                        size="2", 
                                        weight="bold", 
                                        color="green"
                                    )
                                ),
                                padding="0.5rem 1rem",
                                background=rx.color("green", 2),
                                width="100%"
                            )
                        ),
                        rx.button(
                            "🚀 立即绑定并激活待发货状态",
                            on_click=PresaleState.submit_bind_final,
                            size="3",
                            color_scheme="green",
                            width="100%",
                            disabled=PresaleState.final_no_input == ""
                        ),
                        spacing="3",
                        width="100%"
                    ),
                    rx.callout("🔍 查找定金订单并成功锁定后，将会显示出详细的尾款绑定控制面板", icon="info", color_scheme="gray", size="1", width="100%")
                ),
                spacing="4",
                width="100%"
            )
        ),
        spacing="4",
        width="100%"
    )


def build_excel_presale_import() -> rx.Component:
    """构建预售 Excel 批量处理表单"""
    return rx.vstack(
        rx.segmented_control.root(
            rx.segmented_control.item("🚀 批量导入定金", value="🚀 批量导入定金"),
            rx.segmented_control.item("🔗 批量匹配并绑定尾款", value="🔗 批量匹配并绑定尾款"),
            value=PresaleState.bulk_presale_mode,
            on_change=lambda val: PresaleState.set_bulk_presale_mode(val),
            size="2",
            width="100%",
        ),
        rx.divider(),
        
        rx.cond(
            PresaleState.bulk_presale_mode == "🚀 批量导入定金",
            rx.callout("📋 定金导入列：订单号 | 商品名 | 商品型号 | 数量 | 销售平台 | 订单总额 | 币种 | 出货仓库 | 优惠", icon="info", color_scheme="violet", size="1", width="100%"),
            rx.callout("📋 尾款绑定列：订单号 | 关联定金单号 | 商品名 | 商品型号 | 数量 | 销售平台 | 订单总额 | 币种 | 出货仓库", icon="info", color_scheme="violet", size="1", width="100%")
        ),
        
        rx.upload(
            rx.vstack(
                rx.button("上传预售 Excel 数据表", color_scheme="violet", variant="soft", size="2"),
                rx.text("拖拽文件到这里进行解析校验", size="1", color=rx.color("slate", 9)),
                align="center",
                spacing="1",
                padding="1rem",
            ),
            id="presale_upload",
            border="1px dashed var(--slate-6)",
            border_radius="6px",
            background=rx.color("slate", 2),
            on_drop=PresaleState.handle_excel_import(rx.upload_files(upload_id="presale_upload")),
            width="100%",
        ),
        rx.cond(
            rx.selected_files("presale_upload"),
            rx.hstack(
                rx.foreach(
                    rx.selected_files("presale_upload"),
                    lambda file: rx.badge(f"📁 {file}", color_scheme="violet", variant="soft")
                ),
                spacing="2",
                flex_wrap="wrap",
                width="100%",
            )
        ),
        rx.button(
            "🔍 上传并开始解析校验 Excel",
            on_click=PresaleState.handle_excel_import(
                rx.upload_files(upload_id="presale_upload")
            ),
            color_scheme="violet",
            width="100%",
            size="2",
        ),
        
        rx.cond(
            PresaleState.excel_import_errors,
            rx.vstack(
                rx.text("❌ Excel 校验发现以下异常错误：", size="2", color="red", weight="bold"),
                rx.foreach(
                    PresaleState.excel_import_errors,
                    lambda err: rx.text(rx.fragment("• ", err), size="1", color="red")
                ),
                spacing="1",
                width="100%",
                padding="0.5rem",
                background=rx.color("red", 2),
                border_radius="6px"
            )
        ),
        
        rx.cond(
            PresaleState.parsed_preview_orders,
            rx.vstack(
                rx.hstack(
                    rx.text("✅ 数据校验成功！Excel 数据预览：", size="2", weight="medium", color="green"),
                    rx.spacer(),
                    rx.button(
                        rx.fragment("🚀 立即开始批量处理 (", PresaleState.bulk_presale_mode, ")"),
                        on_click=PresaleState.submit_batch_import,
                        size="2",
                        color_scheme="green"
                    ),
                    width="100%",
                    align="center",
                ),
                rx.scroll_area(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("物理状态", size="1"),
                                rx.table.column_header_cell("单号", size="1"),
                                rx.table.column_header_cell("平台", size="1"),
                                rx.table.column_header_cell("收款账户", size="1"),
                                rx.table.column_header_cell("币种", size="1"),
                                rx.table.column_header_cell("数量", size="1"),
                                rx.table.column_header_cell("原总价", size="1"),
                                rx.table.column_header_cell("手续费", size="1"),
                                rx.table.column_header_cell("实入账", size="1"),
                                rx.table.column_header_cell("优惠", size="1"),
                                rx.table.column_header_cell("商品明细", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(PresaleState.parsed_preview_orders, render_preview_order_row)
                        ),
                        size="1",
                        width="100%",
                    ),
                    width="100%",
                ),
                spacing="3",
                width="100%"
            )
        ),
        spacing="4",
        width="100%"
    )


def stat_metric_card(label: str, value: rx.Var, color_scheme: str = "violet", icon: str = "circle") -> rx.Component:
    """KPI 卡片"""
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
    """预售详细 Dialog"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.heading(rx.fragment("📝 预售详情 | 定金: ", PresaleState.detail_order_no, " | 尾款: ", PresaleState.detail_final_order_no), size="3"),
                rx.spacer(),
                rx.dialog.close(
                    rx.icon_button(rx.icon("x", size=16), variant="ghost", color_scheme="gray")
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            
            rx.grid(
                custom_form_field("当前状态", rx.badge(PresaleState.detail_status, size="1", color_scheme="violet")),
                custom_form_field("定金实收", rx.text(rx.fragment("¥ ", PresaleState.detail_deposit_amount.to_string()), size="2", weight="bold")),
                custom_form_field("尾款实收", rx.text(rx.fragment("¥ ", PresaleState.detail_final_amount.to_string()), size="2", weight="bold")),
                custom_form_field("销售平台", rx.text(PresaleState.detail_platform, size="2", weight="medium")),
                custom_form_field("币种", rx.text(PresaleState.detail_currency, size="2")),
                custom_form_field("创建时间", rx.text(PresaleState.detail_created_date, size="2")),
                custom_form_field("发货时间", rx.text(PresaleState.detail_shipped_date, size="2")),
                custom_form_field("完成对账时间", rx.text(PresaleState.detail_completed_date, size="2")),
                columns="4",
                spacing="3",
                width="100%",
                margin_bottom="0.5rem"
            ),
            
            custom_form_field("收款记账钱包", rx.text(PresaleState.detail_target_account, size="2", weight="bold")),
            
            rx.divider(),
            rx.text("📦 购买商品明细：", size="2", weight="bold"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("商品名称", size="1"),
                        rx.table.column_header_cell("款式", size="1"),
                        rx.table.column_header_cell("分配仓", size="1"),
                        rx.table.column_header_cell("数量", size="1"),
                        rx.table.column_header_cell("定金+尾款分配金额", size="1"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        PresaleState.detail_items,
                        lambda item: rx.table.row(
                            rx.table.cell(rx.text(item["product_name"], size="1")),
                            rx.table.cell(rx.text(item["variant"], size="1")),
                            rx.table.cell(rx.text(item["warehouse_name"], size="1")),
                            rx.table.cell(rx.text(item["quantity"].to_string(), size="1")),
                            rx.table.cell(rx.text(item["subtotal"].to_string(), size="1", weight="medium")),
                        )
                    )
                ),
                size="1",
                width="100%",
            ),
            
            rx.hstack(
                rx.spacer(),
                rx.text(rx.fragment("累计记账实收总额: ¥ ", PresaleState.detail_total_amount.to_string()), size="2", weight="bold"),
            ),
            
            rx.divider(),
            
            # 编辑面板
            rx.vstack(
                rx.text("✏️ 属性修改与物理流向撤回：", size="2", weight="bold"),
                custom_form_field(
                    "优惠政策",
                    rx.input(
                        value=PresaleState.edit_discount_note,
                        on_change=PresaleState.set_edit_discount_note,
                        size="2",
                        width="100%"
                    )
                ),
                custom_form_field(
                    "流转备注",
                    rx.text_area(
                        value=PresaleState.edit_notes,
                        on_change=PresaleState.set_edit_notes,
                        size="2",
                        width="100%"
                    )
                ),
                rx.hstack(
                    rx.cond(
                        PresaleState.show_delete_confirm,
                        rx.hstack(
                            rx.text("⚠️ 全额物理回退？", size="1", color="red"),
                            rx.button("确定删除", on_click=PresaleState.submit_delete_order, size="2", color_scheme="red"),
                            rx.button("取消", on_click=PresaleState.cancel_delete_confirm, size="2", variant="soft", color_scheme="gray"),
                            spacing="2"
                        ),
                        rx.button("🗑️ 彻底删除整个预售订单", on_click=PresaleState.open_delete_confirm, size="2", color_scheme="red")
                    ),
                    rx.spacer(),
                    # 仅在有尾款时显示物理撤回尾款
                    rx.cond(
                        PresaleState.detail_final_order_no != "-",
                        rx.button("🟠 物理撤销/解绑尾款", on_click=PresaleState.unbind_presale_final, size="2", color_scheme="orange"),
                        rx.fragment()
                    ),
                    # 仅在待付尾款且未绑尾款时显示拆分定金订单
                    rx.cond(
                        PresaleState.can_split_order,
                        rx.button("✂️ 拆分定金订单 (部分补款)", on_click=PresaleState.open_split_modal, size="2", color_scheme="blue"),
                        rx.fragment()
                    ),
                    rx.button("💾 保存修改", on_click=PresaleState.submit_update_notes, size="2", color_scheme="violet"),
                    width="100%",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="650px"
        ),
        open=PresaleState.show_detail_flag,
        on_open_change=PresaleState.set_show_detail_flag,
    )


def split_presale_order_modal() -> rx.Component:
    """拆分定金订单 Dialog"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.heading(rx.fragment("✂️ 拆分预售定金订单 | 原单: ", PresaleState.split_base_order_no), size="3"),
                rx.spacer(),
                rx.dialog.close(
                    rx.icon_button(rx.icon("x", size=16), variant="ghost", color_scheme="gray", on_click=PresaleState.close_split_modal)
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            rx.callout(
                rx.fragment(
                    "💡 可选择拆出特定款式与数量。拆分后将自动生成独立子单【",
                    rx.text(PresaleState.split_next_order_no, weight="bold"),
                    "】，两笔定金订单可独立绑定各自的尾款单并分批发货对账。定金金额将按商品比例智能切分。"
                ),
                icon="info",
                color_scheme="blue",
                size="1",
                width="100%"
            ),
            rx.text("📦 请勾选或调整各款式拆出数量：", size="2", weight="bold"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("商品名称", size="1"),
                        rx.table.column_header_cell("款式", size="1"),
                        rx.table.column_header_cell("发货仓", size="1"),
                        rx.table.column_header_cell("原数量", size="1"),
                        rx.table.column_header_cell("单件定金", size="1"),
                        rx.table.column_header_cell("拆出件数", size="1"),
                        rx.table.column_header_cell("快捷全选", size="1"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        PresaleState.split_items_data,
                        lambda item: rx.table.row(
                            rx.table.cell(rx.text(item.product_name, size="1")),
                            rx.table.cell(rx.badge(item.variant, size="1", color_scheme="gray")),
                            rx.table.cell(rx.text(item.warehouse_name, size="1")),
                            rx.table.cell(rx.text(item.max_qty.to_string(), size="1", weight="bold")),
                            rx.table.cell(rx.text(rx.fragment("¥", item.unit_deposit.to_string()), size="1")),
                            rx.table.cell(
                                rx.input(
                                    type="number",
                                    value=item.split_qty.to_string(),
                                    on_change=lambda val: PresaleState.set_split_item_qty(item.item_id, val),
                                    size="1",
                                    width="70px",
                                    min=0,
                                    max=item.max_qty
                                )
                            ),
                            rx.table.cell(
                                rx.button(
                                    rx.cond(item.split_qty > 0, "取消", "全部拆出"),
                                    on_click=lambda: PresaleState.toggle_split_all_of_item(item.item_id),
                                    size="1",
                                    variant="soft",
                                    color_scheme=rx.cond(item.split_qty > 0, "red", "blue")
                                )
                            ),
                        )
                    )
                ),
                size="1",
                width="100%"
            ),
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.text(rx.fragment("🆕 即将生成新子单【", PresaleState.split_next_order_no, "】："), size="2", weight="bold", color=rx.color("blue", 11)),
                        rx.spacer(),
                        rx.text(rx.fragment("拆出数量: ", PresaleState.split_selected_total_qty.to_string(), " 件 | 分摊定金: ¥ ", PresaleState.split_preview_new_deposit.to_string()), size="2", weight="bold", color=rx.color("blue", 11)),
                        width="100%"
                    ),
                    rx.hstack(
                        rx.text(rx.fragment("📝 原定金订单【", PresaleState.split_base_order_no, "】："), size="2", weight="bold", color=rx.color("slate", 11)),
                        rx.spacer(),
                        rx.text(rx.fragment("剩余数量: ", PresaleState.split_preview_remain_qty.to_string(), " 件 | 剩余定金: ¥ ", PresaleState.split_preview_remain_deposit.to_string()), size="2", weight="bold", color=rx.color("slate", 11)),
                        width="100%"
                    ),
                    spacing="1",
                    width="100%"
                ),
                padding="0.75rem",
                background=rx.color("blue", 2),
                width="100%"
            ),
            rx.hstack(
                rx.button("取消", on_click=PresaleState.close_split_modal, size="2", variant="soft", color_scheme="gray"),
                rx.spacer(),
                rx.button(
                    "✂️ 确认拆分并生成子订单",
                    on_click=PresaleState.submit_split_presale_order,
                    size="2",
                    color_scheme="blue",
                    disabled=~PresaleState.can_submit_split
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
            max_width="650px"
        ),
        open=PresaleState.show_split_modal,
        on_open_change=PresaleState.close_split_modal,
    )


def refund_dialog_modal() -> rx.Component:
    """售后物理退货补发 Dialog"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.heading("🔧 预售订单物理售后处理", size="3"),
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
                PresaleState.existing_refunds,
                rx.vstack(
                    rx.text("📋 已有售后记录审计流水：", size="2", weight="bold"),
                    rx.foreach(
                        PresaleState.existing_refunds,
                        lambda ref: rx.vstack(
                            rx.hstack(
                                rx.text(rx.fragment("🕒 ", ref["refund_date"]), size="1", weight="medium"),
                                rx.badge(ref["refund_reason"], color_scheme="gray", size="1"),
                                rx.spacer(),
                                rx.text(rx.fragment("¥ ", ref["refund_amount"].to_string()), size="2", weight="bold", color="red"),
                                rx.text(rx.fragment(" 退货:", rx.cond(ref["is_returned"], "是", "否"), " | 补发:", rx.cond(ref["is_resend"], "是", "否")), size="1", color="slate"),
                                spacing="2",
                                align="center",
                                width="100%"
                            ),
                            rx.cond(
                                ref["is_editing"],
                                rx.hstack(
                                    rx.input(value=PresaleState.editing_refund_amount.to_string(), on_change=PresaleState.set_editing_refund_amount, size="1", style={"width": "100px"}),
                                    rx.input(value=PresaleState.editing_refund_reason, on_change=PresaleState.set_editing_refund_reason, size="1"),
                                    rx.button("保存", on_click=PresaleState.submit_edit_refund, size="1", color_scheme="green"),
                                    rx.button("取消", on_click=PresaleState.cancel_edit_refund, size="1", variant="soft", color_scheme="gray"),
                                    spacing="2",
                                    width="100%",
                                ),
                                rx.hstack(
                                    rx.button("✏️ 编辑", on_click=lambda: PresaleState.start_edit_refund(ref["id"]), size="1", variant="soft", color_scheme="violet"),
                                    rx.button("🗑️ 物理回滚", on_click=lambda: PresaleState.submit_delete_refund(ref["id"]), size="1", variant="soft", color_scheme="red"),
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
                rx.text("➕ 登记预售新售后：", size="2", weight="bold"),
                custom_form_field(
                    "退款/售后金额 (CNY/JPY)",
                    rx.input(
                        type="number",
                        placeholder="0.00",
                        value=PresaleState.ref_amount_input.to_string(),
                        on_change=PresaleState.set_ref_amount_input,
                        size="2",
                        width="100%"
                    ),
                    helper="仅补发不退钱，请填 0。"
                ),
                custom_form_field(
                    "售后原因 (审计必填)",
                    rx.input(
                        placeholder="请输入售后说明，便于审计...",
                        value=PresaleState.ref_reason_input,
                        on_change=PresaleState.set_ref_reason_input,
                        size="2",
                        width="100%"
                    )
                ),
                
                rx.grid(
                    rx.hstack(
                        rx.checkbox(checked=PresaleState.ref_is_returned, on_change=PresaleState.toggle_ref_is_returned, size="2"),
                        rx.text("🔄 物理退货 (回入大货仓库)", size="2"),
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.checkbox(checked=PresaleState.ref_is_resend, on_change=PresaleState.toggle_ref_is_resend, size="2"),
                        rx.text("📦 物理补发 (补寄配件/整套)", size="2"),
                        spacing="2",
                        align="center",
                    ),
                    columns="2",
                    width="100%",
                    margin_top="0.5rem"
                ),
                
                # 2.1 退回商品
                rx.cond(
                    PresaleState.ref_is_returned,
                    rx.vstack(
                        rx.text("选择退货入库商品及数量：", size="1", weight="bold", color="slate"),
                        rx.foreach(
                            PresaleState.ref_returned_items,
                            lambda item: rx.hstack(
                                rx.text(rx.fragment(item["product_name"], " (", item["variant"], ")"), size="1", weight="medium"),
                                rx.spacer(),
                                rx.text(rx.fragment("原出货仓: ", item["warehouse_name"], " | 原数:", item["max_quantity"].to_string()), size="1", color="slate"),
                                rx.input(
                                    placeholder="退回数",
                                    type="number",
                                    on_blur=lambda val: PresaleState.update_returned_qty(item["order_item_id"], val),
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
                
                # 2.2 补发配置
                rx.cond(
                    PresaleState.ref_is_resend,
                    rx.vstack(
                        rx.text("选择并配置补发出的商品散件/整套：", size="1", weight="bold", color="slate"),
                        rx.foreach(
                            PresaleState.ref_resend_items,
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
                                        on_change=lambda val: PresaleState.update_resend_part(item.order_item_id, val),
                                        size="1",
                                    ),
                                    rx.select.root(
                                        rx.select.trigger(),
                                        rx.select.content(
                                            rx.foreach(
                                                PresaleState.warehouse_options,
                                                lambda w: rx.cond(w != "未分配", rx.select.item(w, value=w), rx.fragment())
                                            )
                                        , position="popper", side="bottom"),
                                        value=item.warehouse_name,
                                        on_change=lambda val: PresaleState.update_resend_warehouse(item.order_item_id, val),
                                        size="1",
                                    ),
                                    rx.input(
                                        placeholder="数量",
                                        type="number",
                                        on_blur=lambda val: PresaleState.update_resend_qty(item.order_item_id, val),
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
                    "确认登记提交预售售后单",
                    on_click=PresaleState.submit_add_refund,
                    size="3",
                    color_scheme="red",
                    width="100%",
                    margin_top="0.5rem"
                ),
                spacing="3",
                width="100%"
            ),
            max_width="600px"
        ),
        open=PresaleState.show_refund_form,
        on_open_change=PresaleState.set_show_refund_form,
    )


def batch_wh_modal() -> rx.Component:
    """批量修改发货仓库 Dialog"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.heading("🏭 批量修改发货仓库", size="3"),
                rx.spacer(),
                rx.dialog.close(
                    rx.icon_button(rx.icon("x", size=16), variant="ghost", color_scheme="gray")
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            rx.vstack(
                rx.text(
                    rx.fragment(
                        "当前共选中了 ", 
                        rx.text(PresaleState.selected_count.to_string(), weight="bold", color="violet"), 
                        " 项预售订单。请选择统一修改的目标出货仓库："
                    ),
                    size="2"
                ),
                custom_form_field(
                    "目标发货仓库",
                    rx.select.root(
                        rx.select.trigger(placeholder="选择目标发货仓库"),
                        rx.select.content(
                            rx.foreach(
                                PresaleState.warehouse_options,
                                lambda w: rx.select.item(w, value=w)
                            ),
                            position="popper", side="bottom"
                        ),
                        value=PresaleState.batch_target_wh_name,
                        on_change=PresaleState.set_batch_target_wh_name,
                        size="2",
                        width="100%",
                    ),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button("取消", on_click=PresaleState.close_batch_wh_modal, variant="soft", color_scheme="gray", size="2"),
                    rx.button("💾 确认批量修改", on_click=PresaleState.submit_batch_update_warehouse, color_scheme="violet", size="2"),
                    width="100%",
                    spacing="2",
                    margin_top="1rem"
                ),
                spacing="3",
                width="100%",
            ),
            max_width="450px"
        ),
        open=PresaleState.show_batch_wh_modal,
        on_open_change=PresaleState.set_show_batch_wh_modal,
    )


def presale_page() -> rx.Component:
    """预售管理主页面"""
    return page_layout(
        rx.vstack(
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("➕ 创建预售单据 / 绑定尾款", value="create"),
                    rx.tabs.trigger("📥 批量导入预售 (Excel)", value="bulk"),
                ),
                rx.card(
                    rx.tabs.content(build_presale_create_form(), value="create"),
                    rx.tabs.content(build_excel_presale_import(), value="bulk"),
                    width="100%",
                    padding="1rem",
                    margin_top="0.5rem",
                ),
                default_value="create",
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
                            PresaleState.product_options,
                            lambda p: rx.select.item(p, value=p)
                        )
                    , position="popper", side="bottom"),
                    value=PresaleState.selected_product_filter,
                    on_change=PresaleState.select_product_filter,
                    size="2",
                    style={"maxWidth": "250px"},
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            
            # KPI 指标
            rx.grid(
                stat_metric_card("总预售单数", PresaleState.stat_total, "violet", "layers"),
                stat_metric_card("待完成定金", PresaleState.stat_pending_deposit, "orange", "clock"),
                stat_metric_card("待付尾款", PresaleState.stat_pending_final, "blue", "hourglass"),
                stat_metric_card("待发货(已绑尾)", PresaleState.stat_pending, "amber", "package"),
                stat_metric_card("已发货 (物理扣存)", PresaleState.stat_shipped, "indigo", "truck"),
                stat_metric_card("已完成对账结算", PresaleState.stat_completed, "green", "circle_check"),
                columns="6",
                spacing="3",
                width="100%",
            ),
            
            rx.divider(),
            
            # 预售订单列表
            data_card(
                "📋 预售订单管理列表",
                rx.vstack(
                    rx.tabs.root(
                        rx.tabs.list(
                            rx.tabs.trigger("全部", value="all"),
                            rx.tabs.trigger("待确认定金", value="deposit"),
                            rx.tabs.trigger("待付尾款", value="final"),
                            rx.tabs.trigger("待发货(已绑尾)", value="pending"),
                            rx.tabs.trigger("已发货", value="shipped"),
                            rx.tabs.trigger("已完成", value="completed"),
                            rx.tabs.trigger("售后中", value="after_sales"),
                        ),
                        value=PresaleState.active_tab,
                        on_change=PresaleState.select_tab,
                        width="100%",
                    ),
                    
                    # 查询输入框
                    rx.input(
                        placeholder="🔍 输入订单号、平台、备注、状态、款式或商品明细筛选...",
                        value=PresaleState.search_query,
                        on_change=PresaleState.set_search_query,
                        width="100%",
                        size="2",
                    ),
                    
                    rx.hstack(
                        rx.button("☑️ 全选", on_click=PresaleState.toggle_select_all, size="1", variant="soft", color_scheme="gray"),
                        rx.spacer(),
                        rx.text(rx.fragment("已选中 ", PresaleState.selected_count.to_string(), " 项订单"), size="2", color=rx.color("slate", 10)),
                        rx.badge(
                            rx.fragment("已选尾款合计: ¥ ", PresaleState.selected_final_amount_sum.to_string()),
                            size="2",
                            color_scheme="green",
                            variant="surface",
                            weight="bold"
                        ),
                        rx.badge(
                            rx.fragment("已选定金+尾款合计: ¥ ", PresaleState.selected_amount_sum.to_string()),
                            size="2",
                            color_scheme="ruby",
                            variant="surface",
                            weight="bold"
                        ),
                        spacing="3",
                        align="center",
                        width="100%"
                    ),
                    
                    # 预售表格
                    rx.cond(
                        PresaleState.has_orders,
                        rx.vstack(
                            rx.scroll_area(
                                rx.table.root(
                                    rx.table.header(
                                        rx.table.row(
                                            rx.table.column_header_cell("选择", size="1"),
                                            rx.table.column_header_cell("定金订单号", size="1"),
                                            rx.table.column_header_cell("尾款订单号", size="1"),
                                            rx.table.column_header_cell("状态", size="1"),
                                            rx.table.column_header_cell("商品明细", size="1"),
                                            rx.table.column_header_cell("定金金额", size="1"),
                                            rx.table.column_header_cell("尾款金额", size="1"),
                                            rx.table.column_header_cell("已退款", size="1"),
                                            rx.table.column_header_cell("优惠", size="1"),
                                            rx.table.column_header_cell("平台", size="1"),
                                            rx.table.column_header_cell("日期", size="1"),
                                            rx.table.column_header_cell("备注", size="1"),
                                        )
                                    ),
                                    rx.table.body(
                                        rx.foreach(PresaleState.paginated_orders, order_row_renderer)
                                    ),
                                    size="1",
                                    width="100%"
                                ),
                                width="100%"
                            ),
                            # 分页控制栏
                            rx.hstack(
                                rx.button(
                                    "上一页",
                                    on_click=PresaleState.prev_page,
                                    disabled=~PresaleState.has_prev_page,
                                    size="1",
                                    variant="soft",
                                ),
                                rx.text(PresaleState.page_info, size="1", color=rx.color("slate", 10)),
                                rx.button(
                                    "下一页",
                                    on_click=PresaleState.next_page,
                                    disabled=~PresaleState.has_next_page,
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
                        empty_state("该筛选分类下无对应的预售销售订单记录数据")
                    ),
                    
                    # 控制动作按钮
                    rx.hstack(
                        rx.button(
                            rx.icon("check", size=14),
                            rx.fragment("📥 完成定金收款 (", PresaleState.selected_count.to_string(), ")"),
                            on_click=PresaleState.complete_selected_deposits,
                            disabled=~PresaleState.can_complete_deposit,
                            size="2",
                            color_scheme="violet"
                        ),
                        rx.button(
                            rx.icon("package", size=14),
                            rx.fragment("📦 发货 (", PresaleState.selected_count.to_string(), ")"),
                            on_click=PresaleState.ship_selected_orders,
                            disabled=~PresaleState.can_ship,
                            size="2",
                            color_scheme="orange"
                        ),
                        rx.button(
                            rx.icon("store", size=14),
                            rx.fragment("🏭 批量修改发货仓库 (", PresaleState.selected_count.to_string(), ")"),
                            on_click=PresaleState.open_batch_wh_modal,
                            disabled=~PresaleState.can_batch_edit_wh,
                            size="2",
                            color_scheme="violet"
                        ),
                        rx.button(
                            rx.icon("badge_check", size=14),
                            rx.fragment("✅ 收尾款完成对账 (", PresaleState.selected_count.to_string(), ")"),
                            on_click=PresaleState.complete_selected_orders,
                            disabled=~PresaleState.can_complete,
                            size="2",
                            color_scheme="green"
                        ),
                        rx.button(
                            rx.icon("wrench", size=14),
                            "🔧 售后处理",
                            on_click=lambda: PresaleState.open_refund_dialog(PresaleState.single_selected_id),
                            disabled=~PresaleState.can_refund,
                            size="2",
                            color_scheme="red"
                        ),
                        rx.button(
                            rx.icon("eye", size=14),
                            "✏️ 编辑/详细/删除",
                            on_click=lambda: PresaleState.open_order_detail(PresaleState.single_selected_id),
                            disabled=~PresaleState.is_single_selected,
                            size="2",
                            variant="soft",
                            color_scheme="gray"
                        ),
                        spacing="3",
                        width="100%"
                    ),
                    spacing="3",
                    width="100%"
                )
            ),
            
            # 引入 Dialog 模态框
            order_detail_modal(),
            split_presale_order_modal(),
            refund_dialog_modal(),
            batch_wh_modal(),
            
            spacing="4",
            width="100%"
        ),
        title="⏳ 预售销售管理"
    )

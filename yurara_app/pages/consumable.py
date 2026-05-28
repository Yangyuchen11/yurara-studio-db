# yurara_app/pages/consumable.py
"""
其他资产(耗材)管理页面。
提供快速补货入库与出库消耗操作，出库可分摊至商品大货成本或直接记账销售，包含编辑详情对话框和自适应审计流水。
"""
import reflex as rx
from ..state.consumable_state import ConsumableState, ConsumableItem, ConsumableLogItem, DropdownOption
from ..components.layout import page_layout
from ..components.editable_table import data_card, form_field, empty_state
from constants import PRODUCT_COST_CATEGORIES


def operation_panel() -> rx.Component:
    """库存补货与消耗的交互表单面板"""
    return rx.card(
        rx.vstack(
            rx.heading("⚡ 快速库存操作", size="3", weight="bold"),
            rx.text("在下方执行货物的物理入库补货，或者物理出库消耗（计入商品成本或记账销售）。", size="1", color=rx.color("slate", 9)),
            
            rx.grid(
                form_field("📅 变动日期", rx.input(type="date", value=ConsumableState.op_date, on_change=ConsumableState.set_op_date, size="2")),
                form_field(
                    "📦 选择项目",
                    rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.foreach(
                                ConsumableState.active_item_names,
                                lambda name: rx.select.item(name, value=name)
                            )
                        ),
                        value=ConsumableState.op_item_name,
                        on_change=ConsumableState.on_change_item_name,
                        size="2"
                    )
                ),
                form_field(
                    "⚙️ 操作类型",
                    rx.radio_group.root(
                        rx.hstack(
                            rx.radio_group.item("出库", value="出库"),
                            rx.radio_group.item("入库", value="入库"),
                            spacing="3"
                        ),
                        value=ConsumableState.op_type,
                        on_change=ConsumableState.set_op_type
                    )
                ),
                form_field("🔢 变动数量", rx.input(type="number", value=ConsumableState.op_qty.to_string(), on_change=lambda v: ConsumableState.set_op_qty(rx.cond(v != "", v.to(float), 1.0)), size="2")),
                columns="4",
                spacing="4",
                width="100%"
            ),
            
            rx.divider(),
            
            # ================= CONDITIONAL BRANCHES FOR OUTBOUND =================
            rx.cond(
                ConsumableState.is_outbound,
                rx.vstack(
                    form_field(
                        "📤 出库目的",
                        rx.radio_group.root(
                            rx.hstack(
                                rx.radio_group.item("内部消耗 (计入成本)", value="内部消耗"),
                                rx.radio_group.item("对外销售 (计入收入)", value="对外销售"),
                                spacing="5"
                            ),
                            value=ConsumableState.out_mode,
                            on_change=ConsumableState.set_out_mode
                        )
                    ),
                    
                    # --- Subbranch A: External Sale ---
                    rx.cond(
                        ConsumableState.is_sale,
                        rx.vstack(
                            rx.callout("📝 请填写财务记账信息 (将自动在选定的现金账户中生成【销售收入】流水)", icon="circle_dollar_sign", color_scheme="green", size="1", width="100%"),
                            rx.grid(
                                form_field("收入内容说明", rx.input(value=ConsumableState.sale_content, on_change=ConsumableState.set_sale_content, size="2")),
                                form_field("收入来源 (如: 线下、闲鱼)", rx.input(placeholder="线下/闲鱼/Booth", value=ConsumableState.sale_source, on_change=ConsumableState.set_sale_source, size="2")),
                                form_field("销售总额 (原币)", rx.input(type="number", value=ConsumableState.sale_amount.to_string(), on_change=lambda v: ConsumableState.set_sale_amount(rx.cond(v != "", v.to(float), 0.0)), size="2")),
                                columns="3",
                                spacing="4",
                                width="100%"
                            ),
                            rx.grid(
                                form_field(
                                    "交易币种",
                                    rx.select.root(
                                        rx.select.trigger(),
                                        rx.select.content(
                                            rx.select.item("CNY", value="CNY"),
                                            rx.select.item("JPY", value="JPY")
                                        ),
                                        value=ConsumableState.sale_currency,
                                        on_change=ConsumableState.set_sale_currency,
                                        size="2"
                                    )
                                ),
                                form_field(
                                    "收款入账账户",
                                    rx.select.root(
                                        rx.select.trigger(),
                                        rx.select.content(
                                            rx.foreach(
                                                ConsumableState.cash_accounts,
                                                lambda acc: rx.select.item(acc.label, value=acc.value)
                                            )
                                        ),
                                        placeholder="选择现金账户...",
                                        value=ConsumableState.sale_account_id,
                                        on_change=ConsumableState.set_sale_account_id,
                                        size="2"
                                    )
                                ),
                                columns="2",
                                spacing="4",
                                width="100%"
                            ),
                            form_field("流水备注 (选填)", rx.input(placeholder="将显示在财务流水的备注一栏中", value=ConsumableState.sale_remark, on_change=ConsumableState.set_sale_remark, size="2")),
                            spacing="3",
                            width="100%"
                        ),
                        
                        # --- Subbranch B: Internal Cost ---
                        rx.vstack(
                            rx.grid(
                                form_field("分摊消耗选项", rx.checkbox("🔗 计入商品大货成本", checked=ConsumableState.is_link_product, on_change=ConsumableState.set_is_link_product)),
                                rx.cond(
                                    ConsumableState.is_link_product,
                                    form_field(
                                        "归属商品",
                                        rx.select.root(
                                            rx.select.trigger(),
                                            rx.select.content(
                                                rx.foreach(
                                                    ConsumableState.products_list,
                                                    lambda p: rx.select.item(p.label, value=p.value)
                                                )
                                            ),
                                            value=ConsumableState.target_product_id,
                                            on_change=ConsumableState.set_target_product_id,
                                            size="2"
                                        )
                                    ),
                                    rx.fragment()
                                ),
                                rx.cond(
                                    ConsumableState.is_link_product,
                                    form_field(
                                        "分摊成本分类",
                                        rx.select.root(
                                            rx.select.trigger(),
                                            rx.select.content(
                                                rx.foreach(
                                                    PRODUCT_COST_CATEGORIES,
                                                    lambda cat: rx.select.item(cat, value=cat)
                                                )
                                            ),
                                            value=ConsumableState.target_cost_category,
                                            on_change=ConsumableState.set_target_cost_category,
                                            size="2"
                                        )
                                    ),
                                    rx.fragment()
                                ),
                                columns="3",
                                spacing="4",
                                width="100%"
                            ),
                            form_field("出库备注说明 (选填)", rx.input(placeholder="如：打包用去", value=ConsumableState.op_remark, on_change=ConsumableState.set_op_remark, size="2")),
                            spacing="3",
                            width="100%"
                        )
                    ),
                    spacing="3",
                    width="100%"
                ),
                # If Inbound: Inbound Remark
                form_field("入库/补货备注说明 (选填)", rx.input(placeholder="如：淘宝店自主补货购入", value=ConsumableState.op_remark, on_change=ConsumableState.set_op_remark, size="2"))
            ),
            
            rx.button(
                rx.icon("play", size=13),
                "确认并提交库存变动更新",
                on_click=ConsumableState.submit_inventory_change,
                color_scheme="violet",
                size="2",
                width="100%"
            ),
            
            spacing="3",
            width="100%"
        ),
        padding="0.75rem",
        width="100%"
    )


def valuation_metric_card() -> rx.Component:
    """右侧库存总估值指标卡"""
    return rx.card(
        rx.vstack(
            rx.heading("📊 耗材库存总值", size="3", weight="bold"),
            rx.text("计算当前所有在库耗材的资产账面折算总价。", size="1", color=rx.color("slate", 9)),
            rx.hstack(
                rx.text("CNY 实物总值:", size="1", color=rx.color("slate", 10)),
                rx.spacer(),
                rx.text(ConsumableState.total_cny_str, size="2", weight="bold", color=rx.color("green", 11)),
                width="100%"
            ),
            rx.hstack(
                rx.text("JPY 实物总值:", size="1", color=rx.color("slate", 10)),
                rx.spacer(),
                rx.text(ConsumableState.total_jpy_str, size="2", weight="bold", color=rx.color("red", 11)),
                width="100%"
            ),
            rx.divider(),
            rx.hstack(
                rx.text("折算 CNY 总价值:", size="2", weight="bold", color=rx.color("violet", 11)),
                rx.spacer(),
                rx.text(ConsumableState.grand_total_cny_str, size="4", weight="bold", color=rx.color("violet", 11)),
                width="100%",
                align="center"
            ),
            spacing="2",
            width="100%"
        ),
        padding="0.75rem",
        width="100%"
    )


def edit_consumable_dialog() -> rx.Component:
    """弹出式编辑耗材对话框"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(rx.fragment("⚙️ 修改资产信息: ", ConsumableState.edit_name), size="3"),
            rx.dialog.description("在这里安全修改其他耗材的单价、当前库存数量、备注和采购店铺链接。", size="1", color=rx.color("slate", 9), margin_bottom="1rem"),
            
            rx.vstack(
                form_field("耗材名称 (必填)", rx.input(value=ConsumableState.edit_name, on_change=ConsumableState.set_edit_name, size="2")),
                form_field("分类说明", rx.input(placeholder="如：包装材/备用素材/周边", value=ConsumableState.edit_category, on_change=ConsumableState.set_edit_category, size="2")),
                rx.grid(
                    form_field("单价 (原币)", rx.input(type="number", value=ConsumableState.edit_unit_price.to_string(), on_change=lambda v: ConsumableState.set_edit_unit_price(rx.cond(v != "", v.to(float), 0.0)), size="2")),
                    form_field(
                        "交易币种",
                        rx.select.root(
                            rx.select.trigger(),
                            rx.select.content(
                                rx.select.item("CNY", value="CNY"),
                                rx.select.item("JPY", value="JPY")
                            ),
                            value=ConsumableState.edit_currency,
                            on_change=ConsumableState.set_edit_currency,
                            size="2"
                        )
                    ),
                    columns="2",
                    spacing="3"
                ),
                form_field("当前库存数量", rx.input(type="number", value=ConsumableState.edit_remaining_qty.to_string(), on_change=lambda v: ConsumableState.set_edit_remaining_qty(rx.cond(v != "", v.to(float), 0.0)), size="2")),
                form_field("店铺来源", rx.input(value=ConsumableState.edit_shop_name, on_change=ConsumableState.set_edit_shop_name, size="2")),
                form_field("购买链接 / 网址", rx.input(value=ConsumableState.edit_url, on_change=ConsumableState.set_edit_url, size="2")),
                form_field("备注说明", rx.input(value=ConsumableState.edit_remarks, on_change=ConsumableState.set_edit_remarks, size="2")),
                
                rx.hstack(
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=ConsumableState.close_edit_dialog)
                    ),
                    rx.button("确认保存", on_click=ConsumableState.submit_edit_item, color_scheme="violet"),
                    spacing="3",
                    margin_top="1rem",
                    justify="end",
                    width="100%"
                ),
                spacing="3",
                width="100%"
            ),
            style={"max_width": "450px"}
        ),
        open=ConsumableState.is_edit_open,
        on_open_change=lambda _: ConsumableState.close_edit_dialog()
    )


def render_consumable_row(i: ConsumableItem) -> rx.Component:
    """渲染表格单行"""
    return rx.table.row(
        rx.table.cell(rx.text(i.name, size="1", weight="bold")),
        rx.table.cell(rx.badge(i.category, variant="outline", size="1")),
        rx.table.cell(rx.text(i.currency, size="1")),
        rx.table.cell(rx.text(i.unit_price.to_string(), size="1")),
        rx.table.cell(rx.badge(i.remaining_qty.to_string(), color_scheme=rx.cond(i.remaining_qty > 0.01, "green", "gray"), size="1")),
        rx.table.cell(rx.text(rx.cond(i.remaining_cny > 0.001, i.remaining_cny.to_string(), "-"), size="1")),
        rx.table.cell(rx.text(rx.cond(i.remaining_jpy > 0.001, i.remaining_jpy.to_string(), "-"), size="1")),
        rx.table.cell(rx.text(i.shop_name, size="1")),
        rx.table.cell(
            rx.cond(
                i.url != "",
                rx.link(
                    rx.badge(rx.icon("link", size=10), "访问", color_scheme="violet", variant="soft", size="1"),
                    href=i.url,
                    is_external=True
                ),
                rx.text("-", size="1", color=rx.color("slate", 7))
            )
        ),
        rx.table.cell(rx.text(i.remarks, size="1", line_clamp=1)),
        rx.table.cell(
            rx.icon_button(
                rx.icon("pencil", size=11),
                on_click=lambda: ConsumableState.open_edit_dialog(i),
                size="1",
                variant="ghost"
            )
        )
    )


def consumable_list_table() -> rx.Component:
    """消耗性实物资产清单大表格"""
    return rx.cond(
        ~ConsumableState.has_items,
        empty_state("当前无有效在库库存资产。"),
        rx.vstack(
            rx.scroll_area(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("项目", size="1"),
                            rx.table.column_header_cell("分类", size="1"),
                            rx.table.column_header_cell("币种", size="1"),
                            rx.table.column_header_cell("单价(原币)", size="1"),
                            rx.table.column_header_cell("剩余数量", size="1"),
                            rx.table.column_header_cell("剩余价值(CNY)", size="1"),
                            rx.table.column_header_cell("剩余价值(JPY)", size="1"),
                            rx.table.column_header_cell("店铺", size="1"),
                            rx.table.column_header_cell("相关链接", size="1"),
                            rx.table.column_header_cell("备注", size="1"),
                            rx.table.column_header_cell("操作", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(ConsumableState.items, render_consumable_row)
                    ),
                    size="1",
                    width="100%"
                ),
                overflow_x="auto",
                width="100%"
            ),
            width="100%"
        )
    )


def render_log_row(l: ConsumableLogItem) -> rx.Component:
    """渲染审计日志列表的单行"""
    return rx.table.row(
        rx.table.cell(
            rx.input(
                type="date",
                value=l.date,
                on_blur=lambda val: ConsumableState.update_log_date(l.id, val),
                size="1",
                variant="soft",
                style={"padding": "0", "width": "110px"}
            )
        ),
        rx.table.cell(rx.text(l.item_name, size="1", weight="bold")),
        rx.table.cell(
            rx.cond(
                l.change_qty < 0,
                rx.badge(l.change_qty.to_string(), color_scheme="red", size="1"),
                rx.badge(rx.fragment("+", l.change_qty.to_string()), color_scheme="green", size="1")
            )
        ),
        rx.table.cell(rx.text(l.note, size="1")),
    )


def consumable_logs_table() -> rx.Component:
    """耗材变更流转日志记录表"""
    return rx.cond(
        ConsumableState.logs.length() == 0,
        empty_state("暂无相关耗材操作的变动日志流水记录"),
        rx.vstack(
            rx.callout("💡 提示：你可以直接在表格的【日期】单元格中重新选择，以修正该笔操作的账期。", icon="info", color_scheme="blue", size="1", width="100%"),
            rx.scroll_area(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("日期(支持修改)", size="1"),
                            rx.table.column_header_cell("名称", size="1"),
                            rx.table.column_header_cell("变动数量", size="1"),
                            rx.table.column_header_cell("详情说明", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(ConsumableState.logs, render_log_row)
                    ),
                    size="1",
                    width="100%"
                ),
                height="300px",
                width="100%"
            ),
            width="100%"
        )
    )


def consumable_page() -> rx.Component:
    """其他资产管理页面入口"""
    return page_layout(
        rx.vstack(
            # 顶部操作与库存卡片
            rx.grid(
                operation_panel(),
                valuation_metric_card(),
                columns="2",
                spacing="4",
                width="100%",
                align_items="start"
            ),
            
            # 主清单大卡片
            data_card(
                "📦 其他耗材清单明细",
                consumable_list_table()
            ),
            
            # 日期可修改的操作日志卡片
            data_card(
                "📜 耗材出入库历史记录",
                consumable_logs_table()
            ),
            
            # 编辑详情弹框
            edit_consumable_dialog(),
            
            spacing="4",
            width="100%"
        ),
        title="📦 其他资产管理"
    )

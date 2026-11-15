# yurara_app/pages/consignment.py
"""
寄售管理独立页面（归属销售管理）。
包含：
1. 在店寄售台账（仓库出库到寄售店、单笔/批量退回仓库、单笔/批量结算、手工补录、行编辑）
2. 寄售结算记录（销售明细、手续费、实收金额、入账账户、撤销回滚）
3. 寄售退回记录（退回仓库流水、撤销回滚）
4. 寄售店铺档案（默认币种、费率、固定手续费、默认入账账户、联系备注）
"""
import reflex as rx
from ..components.layout import page_layout
from ..components.editable_table import data_card, stat_card, custom_form_field, empty_state, confirm_dialog
from ..state.consignment_state import (
    ConsignmentState,
    ConsignmentLedgerRow,
    SettlementOrderRow,
    SettlementItemRow,
    ConsignmentReturnRow,
    ConsignmentShopRow,
    DispatchEntryRow,
    ReturnLineRow,
    SettleLineRow,
)


def _select_box(options, value, on_change, placeholder: str = "请选择...", width: str = "100%", extra_items=None) -> rx.Component:
    return rx.box(
        rx.select.root(
            rx.select.trigger(placeholder=placeholder, width="100%"),
            rx.select.content(
                rx.foreach(options, lambda item: rx.select.item(item, value=item)),
                *(extra_items or []),
                position="popper",
                side="bottom",
            ),
            value=value,
            on_change=on_change,
            size="2",
        ),
        width=width,
        min_width="0",
        flex_shrink="0",
    )


def render_ledger_row(row: ConsignmentLedgerRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.cond(
                row.has_remaining,
                rx.checkbox(
                    checked=row.is_selected,
                    on_change=lambda _: ConsignmentState.toggle_select_item(row.id),
                    size="2",
                ),
                rx.text("-", size="1", color=rx.color("slate", 8)),
            )
        ),
        rx.table.cell(rx.text(row.date, size="1", color=rx.color("slate", 10))),
        rx.table.cell(
            rx.badge(
                rx.hstack(rx.icon("store", size=11), rx.text(row.shop_name, size="1"), spacing="1", align="center"),
                color_scheme="violet",
                variant="surface",
                size="1",
            )
        ),
        rx.table.cell(rx.text(row.warehouse_name, size="1", color=rx.color("slate", 10))),
        rx.table.cell(
            rx.vstack(
                rx.text(row.product_name, size="1", weight="bold"),
                rx.hstack(
                    rx.badge(row.variant, color_scheme="violet", variant="soft", size="1"),
                    rx.cond(
                        row.part_name != "整套",
                        rx.badge(row.part_name, color_scheme="cyan", variant="soft", size="1"),
                        rx.fragment(),
                    ),
                    spacing="1",
                ),
                spacing="1",
                align="start",
            )
        ),
        rx.table.cell(rx.text(row.quantity.to_string(), size="1", weight="medium")),
        rx.table.cell(rx.text(row.sold_qty.to_string(), size="1", color=rx.color("blue", 10))),
        rx.table.cell(rx.text(row.returned_qty.to_string(), size="1", color=rx.color("slate", 10))),
        rx.table.cell(
            rx.badge(
                rx.fragment(row.remaining_qty.to_string(), " 件"),
                color_scheme=rx.cond(row.has_remaining, "green", "gray"),
                variant="soft",
                size="1",
            )
        ),
        rx.table.cell(
            rx.text(rx.fragment(row.unit_price_str, " ", row.currency), size="1", color=rx.color("slate", 11))
        ),
        rx.table.cell(rx.badge(row.status, color_scheme=row.status_color, variant="surface", size="1")),
        rx.table.cell(
            rx.hstack(
                rx.cond(
                    row.has_remaining,
                    rx.hstack(
                        rx.button(
                            "结算",
                            size="1",
                            color_scheme="green",
                            variant="soft",
                            on_click=lambda: ConsignmentState.open_settle_single(row.id),
                        ),
                        rx.button(
                            "退回",
                            size="1",
                            color_scheme="amber",
                            variant="soft",
                            on_click=lambda: ConsignmentState.open_return_single(row.id),
                        ),
                        spacing="1",
                    ),
                    rx.fragment(),
                ),
                rx.icon_button(
                    rx.icon("pencil", size=13),
                    size="1",
                    variant="ghost",
                    color_scheme="violet",
                    on_click=lambda: ConsignmentState.open_edit_modal(row.id),
                    title="编辑单价/余量/备注",
                ),
                confirm_dialog(
                    trigger=rx.icon_button(
                        rx.icon("trash-2", size=13),
                        size="1",
                        variant="ghost",
                        color_scheme="red",
                        title="删除寄售记录",
                    ),
                    title="删除寄售记录",
                    description="确认删除此寄售记录吗？若已产生售出结算或退回流水，将禁止直接删除，请先撤销关联单据。",
                    confirm_label="确认删除",
                    on_confirm=lambda: ConsignmentState.delete_consignment_item(row.id),
                ),
                spacing="1",
                align="center",
            )
        ),
    )


def ledger_tab_view() -> rx.Component:
    return rx.vstack(
        # 工具栏与筛选
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.button(
                        rx.hstack(rx.icon("truck", size=14), rx.text("仓库出库到寄售店"), spacing="1"),
                        color_scheme="violet",
                        size="2",
                        on_click=ConsignmentState.open_dispatch_modal,
                    ),
                    rx.button(
                        rx.hstack(rx.icon("plus", size=14), rx.text("手工补录寄售"), spacing="1"),
                        variant="outline",
                        color_scheme="violet",
                        size="2",
                        on_click=ConsignmentState.open_manual_add_modal,
                    ),
                    rx.spacer(),
                    rx.cond(
                        ConsignmentState.selected_count > 0,
                        rx.hstack(
                            rx.badge(rx.fragment("已勾选 ", ConsignmentState.selected_count.to_string(), " 项"), color_scheme="violet", size="2"),
                            rx.button(
                                rx.hstack(rx.icon("circle-dollar-sign", size=14), rx.text("批量结算售出"), spacing="1"),
                                color_scheme="green",
                                size="2",
                                on_click=ConsignmentState.open_settle_batch,
                            ),
                            rx.button(
                                rx.hstack(rx.icon("undo-2", size=14), rx.text("批量退回仓库"), spacing="1"),
                                color_scheme="amber",
                                size="2",
                                on_click=ConsignmentState.open_return_batch,
                            ),
                            rx.button(
                                "清空勾选",
                                size="2",
                                variant="ghost",
                                color_scheme="gray",
                                on_click=ConsignmentState.clear_selection,
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.button(
                            "全选在店商品",
                            size="2",
                            variant="soft",
                            color_scheme="gray",
                            on_click=ConsignmentState.select_all_filtered_remaining,
                        ),
                    ),
                    width="100%",
                    flex_wrap="wrap",
                    spacing="2",
                    align="center",
                ),
                rx.divider(),
                rx.hstack(
                    _select_box(
                        ConsignmentState.filter_shop_options,
                        ConsignmentState.filter_shop,
                        ConsignmentState.set_filter_shop,
                        width="160px",
                    ),
                    _select_box(
                        ["全部状态", "寄售中", "部分结算", "已结清"],
                        ConsignmentState.filter_status,
                        ConsignmentState.set_filter_status,
                        width="130px",
                    ),
                    _select_box(
                        ConsignmentState.filter_product_options,
                        ConsignmentState.filter_product,
                        ConsignmentState.set_filter_product,
                        width="170px",
                    ),
                    rx.input(
                        placeholder="搜索店铺、商品、款式、备注...",
                        value=ConsignmentState.filter_search,
                        on_change=ConsignmentState.set_filter_search,
                        size="2",
                        flex="1",
                        min_width="180px",
                    ),
                    rx.button(
                        "重置筛选",
                        size="2",
                        variant="ghost",
                        color_scheme="gray",
                        flex_shrink="0",
                        on_click=ConsignmentState.reset_filters,
                    ),
                    width="100%",
                    flex_wrap="wrap",
                    spacing="2",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            padding="1rem",
        ),
        data_card(
            "在店寄售台账明细",
            rx.cond(
                ConsignmentState.filtered_items.length() > 0,
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("选"),
                            rx.table.column_header_cell("日期"),
                            rx.table.column_header_cell("寄售店铺"),
                            rx.table.column_header_cell("来源仓库"),
                            rx.table.column_header_cell("商品 / 款式 / 部件"),
                            rx.table.column_header_cell("发出"),
                            rx.table.column_header_cell("已售"),
                            rx.table.column_header_cell("已退"),
                            rx.table.column_header_cell("在店余量"),
                            rx.table.column_header_cell("参考单价"),
                            rx.table.column_header_cell("状态"),
                            rx.table.column_header_cell("操作"),
                        )
                    ),
                    rx.table.body(rx.foreach(ConsignmentState.filtered_items, render_ledger_row)),
                    width="100%",
                    size="1",
                    variant="surface",
                ),
                empty_state("暂无寄售台账记录，可点击上方「仓库出库到寄售店」创建"),
            ),
        ),
        spacing="4",
        width="100%",
    )


def render_settlement_item_row(item: SettlementItemRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(item.product_name, size="1", weight="medium")),
        rx.table.cell(rx.text(rx.fragment(item.variant, " / ", item.part_name), size="1")),
        rx.table.cell(rx.text(item.sold_qty.to_string(), size="1")),
        rx.table.cell(rx.text(item.unit_price.to_string(), size="1")),
        rx.table.cell(rx.text(item.gross_subtotal.to_string(), size="1")),
        rx.table.cell(rx.text(item.net_subtotal.to_string(), size="1", weight="bold", color=rx.color("green", 10))),
    )


def render_settlement_card(st: SettlementOrderRow) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(st.settlement_no, color_scheme="violet", variant="solid", size="1"),
                rx.badge(st.shop_name, color_scheme="blue", variant="surface", size="1"),
                rx.text(st.settlement_date, size="1", color=rx.color("slate", 10)),
                rx.spacer(),
                rx.badge(rx.fragment("售出 ", st.total_sold_qty.to_string(), " 件"), color_scheme="cyan", variant="soft", size="1"),
                rx.text(
                    rx.fragment("总额 ", st.gross_amount.to_string(), " · 手续费 -", st.fee_amount.to_string(), " (", st.fee_rate.to_string(), "%)"),
                    size="1",
                    color=rx.color("slate", 10),
                ),
                rx.badge(
                    rx.fragment("实收入账 ", st.net_amount.to_string(), " ", st.currency),
                    color_scheme="green",
                    variant="surface",
                    size="2",
                ),
                spacing="2",
                align="center",
                flex_wrap="wrap",
                width="100%",
            ),
            rx.hstack(
                rx.text(rx.fragment("入账账户：", st.account_name), size="1", weight="medium"),
                rx.text(rx.fragment("售出商品：", st.items_summary), size="1", color=rx.color("slate", 10)),
                rx.cond(
                    st.notes != "",
                    rx.text(rx.fragment("备注：", st.notes), size="1", color=rx.color("slate", 9)),
                    rx.fragment(),
                ),
                rx.spacer(),
                rx.button(
                    rx.cond(ConsignmentState.expanded_settlement_id == st.id, "收起明细", "查看明细"),
                    size="1",
                    variant="ghost",
                    on_click=lambda: ConsignmentState.toggle_settlement_expand(st.id),
                ),
                confirm_dialog(
                    trigger=rx.button(
                        rx.hstack(rx.icon("rotate-ccw", size=12), rx.text("撤销结算"), spacing="1"),
                        size="1",
                        variant="soft",
                        color_scheme="red",
                    ),
                    title="撤销寄售结算单",
                    description="撤销后将自动扣回入账账户现金、删除关联销售订单与财务收入流水，并恢复对应商品的在店余量。确认撤销？",
                    confirm_label="确认撤销回滚",
                    on_confirm=lambda: ConsignmentState.delete_settlement_record(st.id),
                ),
                spacing="2",
                align="center",
                flex_wrap="wrap",
                width="100%",
            ),
            rx.cond(
                ConsignmentState.expanded_settlement_id == st.id,
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("商品"),
                            rx.table.column_header_cell("款式 / 部件"),
                            rx.table.column_header_cell("售出数"),
                            rx.table.column_header_cell("单价"),
                            rx.table.column_header_cell("毛额小计"),
                            rx.table.column_header_cell("净额分摊"),
                        )
                    ),
                    rx.table.body(rx.foreach(st.line_items, render_settlement_item_row)),
                    size="1",
                    width="100%",
                ),
                rx.fragment(),
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
        padding="1rem",
    )


def settlements_tab_view() -> rx.Component:
    return data_card(
        "寄售结算历史与入账流水",
        rx.cond(
            ConsignmentState.settlements.length() > 0,
            rx.vstack(
                rx.foreach(ConsignmentState.settlements, render_settlement_card),
                spacing="3",
                width="100%",
            ),
            empty_state("暂无寄售结算记录，请在台账页勾选或点击单条「结算」完成收款入账"),
        ),
    )


def render_return_row(r: ConsignmentReturnRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(r.return_date, size="1", color=rx.color("slate", 10))),
        rx.table.cell(rx.badge(r.shop_name, color_scheme="violet", variant="surface", size="1")),
        rx.table.cell(
            rx.hstack(
                rx.text(r.product_name, size="1", weight="bold"),
                rx.badge(r.variant, color_scheme="violet", variant="soft", size="1"),
                rx.cond(r.part_name != "整套", rx.badge(r.part_name, color_scheme="cyan", variant="soft", size="1"), rx.fragment()),
                spacing="1",
            )
        ),
        rx.table.cell(rx.badge(rx.fragment("+", r.return_qty.to_string(), " 件"), color_scheme="green", variant="soft", size="1")),
        rx.table.cell(rx.text(r.warehouse_name, size="1")),
        rx.table.cell(rx.text(r.notes, size="1", color=rx.color("slate", 10))),
        rx.table.cell(
            confirm_dialog(
                trigger=rx.button(
                    rx.hstack(rx.icon("rotate-ccw", size=12), rx.text("撤销退回"), spacing="1"),
                    size="1",
                    variant="soft",
                    color_scheme="red",
                ),
                title="撤销退回仓库单",
                description="确认撤销此退回记录吗？系统会扣减目标仓库已恢复的库存并还原商品为寄售在店状态。",
                confirm_label="确认撤销",
                on_confirm=lambda: ConsignmentState.revoke_return_record(r.id),
            )
        ),
    )


def returns_tab_view() -> rx.Component:
    return data_card(
        "寄售退回仓库历史记录",
        rx.cond(
            ConsignmentState.returns.length() > 0,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("退回日期"),
                        rx.table.column_header_cell("寄售店铺"),
                        rx.table.column_header_cell("商品 / 款式 / 部件"),
                        rx.table.column_header_cell("退回数量"),
                        rx.table.column_header_cell("入库仓库"),
                        rx.table.column_header_cell("备注"),
                        rx.table.column_header_cell("操作"),
                    )
                ),
                rx.table.body(rx.foreach(ConsignmentState.returns, render_return_row)),
                size="1",
                width="100%",
                variant="surface",
            ),
            empty_state("暂无退回仓库记录"),
        ),
    )


def render_shop_card(shop: ConsignmentShopRow) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.icon("store", size=16, color=rx.color("violet", 9)),
                    rx.text(shop.name, size="3", weight="bold"),
                    rx.badge(shop.currency, color_scheme="blue", variant="soft", size="1"),
                    spacing="2",
                    align="center",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.icon_button(
                        rx.icon("pencil", size=13),
                        size="1",
                        variant="ghost",
                        color_scheme="violet",
                        on_click=lambda: ConsignmentState.open_shop_edit(shop.id),
                    ),
                    confirm_dialog(
                        trigger=rx.icon_button(
                            rx.icon("trash-2", size=13),
                            size="1",
                            variant="ghost",
                            color_scheme="red",
                        ),
                        title="删除寄售店铺",
                        description="仅当该店铺名下没有任何寄售台账与结算记录时才可删除。确认删除？",
                        confirm_label="确认删除",
                        on_confirm=lambda: ConsignmentState.delete_shop_record(shop.id),
                    ),
                    spacing="1",
                ),
                width="100%",
                align="center",
            ),
            rx.grid(
                rx.vstack(rx.text("在店余量", size="1", color=rx.color("slate", 10)), rx.text(shop.remaining_qty.to_string(), size="3", weight="bold", color=rx.color("green", 10)), spacing="1"),
                rx.vstack(rx.text("已售出", size="1", color=rx.color("slate", 10)), rx.text(shop.sold_qty.to_string(), size="3", weight="bold", color=rx.color("blue", 10)), spacing="1"),
                rx.vstack(rx.text("已退回", size="1", color=rx.color("slate", 10)), rx.text(shop.returned_qty.to_string(), size="3", weight="bold"), spacing="1"),
                rx.vstack(rx.text("累计已结算", size="1", color=rx.color("slate", 10)), rx.text(shop.settled_str, size="3", weight="bold", color=rx.color("violet", 10)), spacing="1"),
                columns="4",
                spacing="2",
                width="100%",
            ),
            rx.divider(),
            rx.hstack(
                rx.badge(rx.fragment("默认手续费：", shop.fee_desc), variant="surface", color_scheme="amber", size="1"),
                rx.cond(
                    shop.default_account_name != "",
                    rx.badge(rx.fragment("默认账户：", shop.default_account_name), variant="surface", color_scheme="green", size="1"),
                    rx.fragment(),
                ),
                spacing="2",
                flex_wrap="wrap",
            ),
            rx.cond(
                shop.contact_info != "",
                rx.text(rx.fragment("联系/条款：", shop.contact_info), size="1", color=rx.color("slate", 10)),
                rx.fragment(),
            ),
            rx.cond(
                shop.remarks != "",
                rx.text(rx.fragment("备注：", shop.remarks), size="1", color=rx.color("slate", 9)),
                rx.fragment(),
            ),
            spacing="2",
            width="100%",
        ),
        padding="1rem",
        width="100%",
    )


def shops_tab_view() -> rx.Component:
    return data_card(
        "寄售合作店铺档案",
        rx.cond(
            ConsignmentState.shops.length() > 0,
            rx.grid(
                rx.foreach(ConsignmentState.shops, render_shop_card),
                columns=rx.breakpoints(initial="1", md="2"),
                spacing="3",
                width="100%",
            ),
            empty_state("暂无寄售店铺档案，点击右上角「新增寄售店」或出库时自动创建"),
        ),
        action_button=rx.button(
            rx.hstack(rx.icon("plus", size=14), rx.text("新增寄售店"), spacing="1"),
            color_scheme="violet",
            size="2",
            on_click=ConsignmentState.open_shop_create,
        ),
    )


# ==================== Modals ====================

def dispatch_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("仓库出库到寄售店"),
            rx.vstack(
                rx.grid(
                    custom_form_field(
                        "目标寄售店铺",
                        _select_box(
                            ConsignmentState.shop_names,
                            ConsignmentState.dispatch_shop_select,
                            ConsignmentState.set_dispatch_shop_select,
                            placeholder="选择店铺或新建...",
                            extra_items=[rx.select.item("+ 新建寄售店铺", value="__custom__")],
                        ),
                    ),
                    custom_form_field(
                        "出库物理仓库",
                        _select_box(
                            ConsignmentState.warehouse_names,
                            ConsignmentState.dispatch_warehouse_name,
                            ConsignmentState.set_dispatch_warehouse_name,
                            placeholder="选择仓库...",
                        ),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                rx.cond(
                    ConsignmentState.dispatch_shop_select == "__custom__",
                    custom_form_field(
                        "新建寄售店铺名称 (必填)",
                        rx.input(
                            placeholder="如：秋叶原委托店 / 线下代售点A",
                            value=ConsignmentState.dispatch_custom_shop,
                            on_change=ConsignmentState.set_dispatch_custom_shop,
                            size="2",
                            width="100%",
                        ),
                    ),
                    rx.fragment(),
                ),
                rx.grid(
                    custom_form_field(
                        "选择商品",
                        _select_box(
                            ConsignmentState.product_names,
                            ConsignmentState.dispatch_product_name,
                            ConsignmentState.set_dispatch_product_name,
                            placeholder="选择商品...",
                        ),
                    ),
                    custom_form_field(
                        "出库日期",
                        rx.input(type="date", value=ConsignmentState.dispatch_date, on_change=ConsignmentState.set_dispatch_date, size="2", width="100%"),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                rx.text("填写各款式/部件出库数量（扣减所选物理仓库现货）：", size="2", weight="medium"),
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("款式"),
                                rx.table.column_header_cell("部件"),
                                rx.table.column_header_cell("仓库现存"),
                                rx.table.column_header_cell("出库数量"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                ConsignmentState.dispatch_rows,
                                lambda r: rx.table.row(
                                    rx.table.cell(rx.badge(r.variant, color_scheme="violet", variant="soft", size="1")),
                                    rx.table.cell(rx.text(r.part_name, size="1")),
                                    rx.table.cell(rx.badge(r.warehouse_stock.to_string(), color_scheme=rx.cond(r.warehouse_stock > 0, "green", "gray"), size="1")),
                                    rx.table.cell(
                                        rx.input(
                                            type="number",
                                            min="0",
                                            placeholder="0",
                                            value=r.qty_input,
                                            on_change=lambda val: ConsignmentState.set_dispatch_row_qty(r.key, val),
                                            size="1",
                                            width="80px",
                                        )
                                    ),
                                ),
                            )
                        ),
                        size="1",
                        width="100%",
                    ),
                    max_height="260px",
                    overflow_y="auto",
                    width="100%",
                ),
                custom_form_field(
                    "出库备注",
                    rx.input(placeholder="可选备注...", value=ConsignmentState.dispatch_remarks, on_change=ConsignmentState.set_dispatch_remarks, size="2", width="100%"),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button("取消", variant="soft", color_scheme="gray", on_click=ConsignmentState.close_dispatch_modal),
                    rx.button("确认出库到寄售店", color_scheme="violet", on_click=ConsignmentState.submit_dispatch),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="620px",
        ),
        open=ConsignmentState.is_dispatch_open,
    )


def manual_add_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("手工补录寄售台账（不扣仓库库存）"),
            rx.vstack(
                rx.grid(
                    custom_form_field(
                        "寄售店铺",
                        _select_box(
                            ConsignmentState.shop_names,
                            ConsignmentState.manual_shop_select,
                            ConsignmentState.set_manual_shop_select,
                            extra_items=[rx.select.item("+ 新建寄售店铺", value="__custom__")],
                        ),
                    ),
                    custom_form_field(
                        "寄售日期",
                        rx.input(type="date", value=ConsignmentState.manual_date, on_change=ConsignmentState.set_manual_date, size="2", width="100%"),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                rx.cond(
                    ConsignmentState.manual_shop_select == "__custom__",
                    custom_form_field(
                        "新店铺名称",
                        rx.input(value=ConsignmentState.manual_custom_shop, on_change=ConsignmentState.set_manual_custom_shop, size="2", width="100%"),
                    ),
                    rx.fragment(),
                ),
                rx.grid(
                    custom_form_field("商品", _select_box(ConsignmentState.product_names, ConsignmentState.manual_product_name, ConsignmentState.set_manual_product_name)),
                    custom_form_field("款式", _select_box(ConsignmentState.manual_variant_options, ConsignmentState.manual_variant, ConsignmentState.set_manual_variant)),
                    custom_form_field("部件", _select_box(ConsignmentState.manual_part_options, ConsignmentState.manual_part_name, ConsignmentState.set_manual_part_name)),
                    columns="3",
                    spacing="2",
                    width="100%",
                ),
                rx.grid(
                    custom_form_field("寄售总数", rx.input(type="number", value=ConsignmentState.manual_qty, on_change=ConsignmentState.set_manual_qty, size="2", width="100%")),
                    custom_form_field("在店余量", rx.input(type="number", value=ConsignmentState.manual_remaining_qty, on_change=ConsignmentState.set_manual_remaining_qty, size="2", width="100%")),
                    custom_form_field("参考单价", rx.input(type="number", value=ConsignmentState.manual_unit_price, on_change=ConsignmentState.set_manual_unit_price, size="2", width="100%")),
                    custom_form_field("币种", _select_box(ConsignmentState.currency_options, ConsignmentState.manual_currency, ConsignmentState.set_manual_currency)),
                    columns="4",
                    spacing="2",
                    width="100%",
                ),
                custom_form_field("备注", rx.input(value=ConsignmentState.manual_remarks, on_change=ConsignmentState.set_manual_remarks, size="2", width="100%")),
                rx.hstack(
                    rx.spacer(),
                    rx.button("取消", variant="soft", color_scheme="gray", on_click=ConsignmentState.close_manual_add_modal),
                    rx.button("确认补录", color_scheme="violet", on_click=ConsignmentState.submit_manual_add),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="560px",
        ),
        open=ConsignmentState.is_manual_add_open,
    )


def edit_item_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("编辑寄售记录"),
            rx.vstack(
                rx.text(ConsignmentState.edit_product_info, size="2", weight="bold", color=rx.color("violet", 11)),
                custom_form_field("寄售店铺", rx.input(value=ConsignmentState.edit_shop_name, on_change=ConsignmentState.set_edit_shop_name, size="2", width="100%")),
                rx.grid(
                    custom_form_field("在店余量", rx.input(type="number", min="0", value=ConsignmentState.edit_remaining_qty, on_change=ConsignmentState.set_edit_remaining_qty, size="2", width="100%")),
                    custom_form_field("参考单价", rx.input(type="number", min="0", value=ConsignmentState.edit_unit_price, on_change=ConsignmentState.set_edit_unit_price, size="2", width="100%")),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                custom_form_field("备注", rx.input(value=ConsignmentState.edit_remarks, on_change=ConsignmentState.set_edit_remarks, size="2", width="100%")),
                rx.hstack(
                    rx.spacer(),
                    rx.button("取消", variant="soft", color_scheme="gray", on_click=ConsignmentState.close_edit_modal),
                    rx.button("保存修改", color_scheme="violet", on_click=ConsignmentState.submit_edit),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="460px",
        ),
        open=ConsignmentState.is_edit_open,
    )


def return_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("寄售商品退回仓库"),
            rx.vstack(
                rx.grid(
                    custom_form_field(
                        "退回入库仓库",
                        _select_box(
                            ConsignmentState.warehouse_names,
                            ConsignmentState.return_warehouse_name,
                            ConsignmentState.set_return_warehouse_name,
                        ),
                    ),
                    custom_form_field(
                        "退回日期",
                        rx.input(type="date", value=ConsignmentState.return_date, on_change=ConsignmentState.set_return_date, size="2", width="100%"),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("店铺"),
                                rx.table.column_header_cell("商品 / 款式"),
                                rx.table.column_header_cell("可退余量"),
                                rx.table.column_header_cell("本次退回数量"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                ConsignmentState.return_lines,
                                lambda r: rx.table.row(
                                    rx.table.cell(rx.badge(r.shop_name, color_scheme="violet", variant="soft", size="1")),
                                    rx.table.cell(rx.text(rx.fragment(r.product_name, " · ", r.variant, " / ", r.part_name), size="1")),
                                    rx.table.cell(rx.badge(r.max_qty.to_string(), color_scheme="green", size="1")),
                                    rx.table.cell(
                                        rx.input(
                                            type="number",
                                            min="0",
                                            value=r.return_qty_input,
                                            on_change=lambda val: ConsignmentState.set_return_line_qty(r.consignment_item_id, val),
                                            size="1",
                                            width="80px",
                                        )
                                    ),
                                ),
                            )
                        ),
                        size="1",
                        width="100%",
                    ),
                    max_height="240px",
                    overflow_y="auto",
                    width="100%",
                ),
                custom_form_field("退回备注", rx.input(placeholder="可选说明...", value=ConsignmentState.return_notes, on_change=ConsignmentState.set_return_notes, size="2", width="100%")),
                rx.hstack(
                    rx.spacer(),
                    rx.button("取消", variant="soft", color_scheme="gray", on_click=ConsignmentState.close_return_modal),
                    rx.button("确认退回并恢复库存", color_scheme="amber", on_click=ConsignmentState.submit_return),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="600px",
        ),
        open=ConsignmentState.is_return_open,
    )


def settle_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(rx.fragment("寄售售出结算 — ", ConsignmentState.settle_shop_name)),
            rx.vstack(
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("商品 / 款式 / 部件"),
                                rx.table.column_header_cell("可结"),
                                rx.table.column_header_cell("售出数量"),
                                rx.table.column_header_cell("结算单价"),
                                rx.table.column_header_cell("小计"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                ConsignmentState.settle_lines,
                                lambda l: rx.table.row(
                                    rx.table.cell(rx.text(rx.fragment(l.product_name, " · ", l.variant, " / ", l.part_name), size="1", weight="medium")),
                                    rx.table.cell(rx.badge(l.max_qty.to_string(), size="1", color_scheme="green")),
                                    rx.table.cell(
                                        rx.input(
                                            type="number",
                                            min="0",
                                            value=l.sold_qty_input,
                                            on_change=lambda val: ConsignmentState.set_settle_line_qty(l.consignment_item_id, val),
                                            size="1",
                                            width="75px",
                                        )
                                    ),
                                    rx.table.cell(
                                        rx.input(
                                            type="number",
                                            min="0",
                                            value=l.unit_price_input,
                                            on_change=lambda val: ConsignmentState.set_settle_line_price(l.consignment_item_id, val),
                                            size="1",
                                            width="85px",
                                        )
                                    ),
                                    rx.table.cell(rx.text(l.subtotal_str, size="1", weight="bold")),
                                ),
                            )
                        ),
                        size="1",
                        width="100%",
                    ),
                    max_height="220px",
                    overflow_y="auto",
                    width="100%",
                ),
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.hstack(
                                rx.text("销售毛额合计：", size="2", weight="medium", white_space="nowrap"),
                                rx.badge(
                                    rx.fragment(ConsignmentState.settle_gross_str, " ", ConsignmentState.settle_currency),
                                    color_scheme="violet",
                                    size="2",
                                    white_space="nowrap",
                                ),
                                spacing="2",
                                align="center",
                                flex_shrink="0",
                            ),
                            rx.spacer(),
                            rx.hstack(
                                rx.text("结算币种", size="1", color=rx.color("slate", 10), white_space="nowrap"),
                                _select_box(
                                    ConsignmentState.currency_options,
                                    ConsignmentState.settle_currency,
                                    ConsignmentState.set_settle_currency,
                                    width="100px",
                                ),
                                spacing="2",
                                align="center",
                                flex_shrink="0",
                            ),
                            align="center",
                            justify="between",
                            flex_wrap="wrap",
                            gap="2",
                            width="100%",
                        ),
                        rx.grid(
                            custom_form_field("店铺抽成费率 (%)", rx.input(type="number", value=ConsignmentState.settle_fee_rate, on_change=ConsignmentState.set_settle_fee_rate, size="2", width="100%")),
                            custom_form_field("店铺手续费金额", rx.input(type="number", value=ConsignmentState.settle_fee_amount, on_change=ConsignmentState.set_settle_fee_amount, size="2", width="100%")),
                            custom_form_field("实际入账金额", rx.input(type="number", value=ConsignmentState.settle_net_amount, on_change=ConsignmentState.set_settle_net_amount, size="2", width="100%")),
                            columns="3",
                            spacing="2",
                            width="100%",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    width="100%",
                    padding="0.75rem",
                ),
                rx.grid(
                    custom_form_field(
                        "入账现金账户 (必选)",
                        _select_box(
                            ConsignmentState.account_labels,
                            ConsignmentState.settle_account_label,
                            ConsignmentState.set_settle_account_label,
                            placeholder="选择入账账户...",
                        ),
                    ),
                    custom_form_field(
                        "结算日期",
                        rx.input(type="date", value=ConsignmentState.settle_date, on_change=ConsignmentState.set_settle_date, size="2", width="100%"),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                custom_form_field("结算备注", rx.input(placeholder="对账单号/备注说明...", value=ConsignmentState.settle_notes, on_change=ConsignmentState.set_settle_notes, size="2", width="100%")),
                rx.hstack(
                    rx.spacer(),
                    rx.button("取消", variant="soft", color_scheme="gray", on_click=ConsignmentState.close_settle_modal),
                    rx.button("确认结算并入账", color_scheme="green", on_click=ConsignmentState.submit_settlement),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="680px",
        ),
        open=ConsignmentState.is_settle_open,
    )


def shop_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(rx.cond(ConsignmentState.shop_edit_id > 0, "编辑寄售店铺档案", "新增寄售店铺档案")),
            rx.vstack(
                rx.grid(
                    custom_form_field("店铺名称 (必填)", rx.input(value=ConsignmentState.shop_form_name, on_change=ConsignmentState.set_shop_form_name, size="2", width="100%")),
                    custom_form_field("默认币种", _select_box(ConsignmentState.currency_options, ConsignmentState.shop_form_currency, ConsignmentState.set_shop_form_currency)),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                rx.grid(
                    custom_form_field("默认手续费率 (%)", rx.input(type="number", value=ConsignmentState.shop_form_fee_rate, on_change=ConsignmentState.set_shop_form_fee_rate, size="2", width="100%")),
                    custom_form_field("固定手续费", rx.input(type="number", value=ConsignmentState.shop_form_fee_fixed, on_change=ConsignmentState.set_shop_form_fee_fixed, size="2", width="100%")),
                    custom_form_field("默认入账账户", _select_box(ConsignmentState.shop_account_options, ConsignmentState.shop_form_account_name, ConsignmentState.set_shop_form_account_name)),
                    columns="3",
                    spacing="2",
                    width="100%",
                ),
                custom_form_field("联系方式 / 结算周期", rx.input(value=ConsignmentState.shop_form_contact, on_change=ConsignmentState.set_shop_form_contact, size="2", width="100%")),
                custom_form_field("备注", rx.input(value=ConsignmentState.shop_form_remarks, on_change=ConsignmentState.set_shop_form_remarks, size="2", width="100%")),
                rx.hstack(
                    rx.spacer(),
                    rx.button("取消", variant="soft", color_scheme="gray", on_click=ConsignmentState.close_shop_modal),
                    rx.button("保存店铺档案", color_scheme="violet", on_click=ConsignmentState.submit_shop_form),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="540px",
        ),
        open=ConsignmentState.is_shop_modal_open,
    )


def consignment_page() -> rx.Component:
    return page_layout(
        rx.vstack(
            rx.grid(
                stat_card("合作寄售店", ConsignmentState.kpi_shop_count, "家", "violet", "store"),
                stat_card("当前在店寄售", ConsignmentState.kpi_remaining_qty, "件", "green", "package"),
                stat_card("累计寄售售出", ConsignmentState.kpi_sold_qty, "件", "blue", "shopping-bag"),
                stat_card("累计退回仓库", ConsignmentState.kpi_returned_qty, "件", "amber", "undo-2"),
                stat_card("累计实收总额", ConsignmentState.kpi_settled_cny, "CNY", "cyan", "circle-dollar-sign"),
                columns=rx.breakpoints(initial="2", sm="3", md="5"),
                spacing="3",
                width="100%",
            ),
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger(rx.hstack(rx.icon("layers", size=14), rx.text("在店寄售台账"), spacing="1"), value="ledger"),
                    rx.tabs.trigger(rx.hstack(rx.icon("receipt", size=14), rx.text("结算记录"), spacing="1"), value="settlements"),
                    rx.tabs.trigger(rx.hstack(rx.icon("undo-2", size=14), rx.text("退回仓库记录"), spacing="1"), value="returns"),
                    rx.tabs.trigger(rx.hstack(rx.icon("store", size=14), rx.text("寄售店铺档案"), spacing="1"), value="shops"),
                    width="100%",
                ),
                rx.tabs.content(ledger_tab_view(), value="ledger"),
                rx.tabs.content(settlements_tab_view(), value="settlements"),
                rx.tabs.content(returns_tab_view(), value="returns"),
                rx.tabs.content(shops_tab_view(), value="shops"),
                value=ConsignmentState.active_tab,
                on_change=ConsignmentState.set_active_tab,
                width="100%",
            ),
            dispatch_modal(),
            manual_add_modal(),
            edit_item_modal(),
            return_modal(),
            settle_modal(),
            shop_modal(),
            spacing="4",
            width="100%",
        ),
        title="寄售管理",
    )

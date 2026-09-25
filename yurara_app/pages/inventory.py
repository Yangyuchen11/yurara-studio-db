# yurara_app/pages/inventory.py
"""
仓库库存管理视图层。
适配 Reflex 页面布局，搭载 HSL 渐变与现代高透玻璃拟态风格，承载仓储及移库消耗等操作。
"""
import reflex as rx
from ..state.inventory_state import InventoryState
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state, stat_card
from constants import StockLogReason


def render_part_row(part) -> rx.Component:
    """渲染拆分部件的详情子行。"""
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.icon("corner-down-right", size=12, color=rx.color("violet", 9)),
                rx.text(part.part_name, size="1", weight="medium"),
                spacing="1",
                align="center",
            )
        ),
        rx.table.cell(
            rx.badge(
                rx.fragment("1套配 ", part.req_qty.to_string(), " 件"),
                color_scheme="gray",
                variant="soft",
                size="1"
            )
        ),
        rx.table.cell(rx.text(part.produced.to_string(), size="1", color=rx.color("slate", 11))),
        rx.table.cell(rx.text(part.inspecting.to_string(), size="1", color=rx.color("slate", 11))),
        rx.table.cell(
            rx.text(
                part.repaired.to_string(),
                size="1",
                color=rx.cond(part.repaired > 0, rx.color("ruby", 10), rx.color("slate", 11)),
                weight=rx.cond(part.repaired > 0, "bold", "normal")
            )
        ),
        rx.table.cell(rx.text(part.actual_qty.to_string(), size="1", weight="bold")),
    )


def render_progress_row(row) -> rx.Component:
    """渲染商品款式进度条目（支持点击展开/收回部件明细）。"""
    is_expanded = InventoryState.expanded_variant == row.variant
    return rx.fragment(
        rx.table.row(
            rx.table.cell(
                rx.hstack(
                    rx.icon(
                        rx.cond(is_expanded, "chevron-down", "chevron-right"),
                        size=14,
                        color=rx.color("violet", 9)
                    ),
                    rx.text(rx.fragment("🎨 ", row.variant), size="1", weight="medium"),
                    spacing="1",
                    align="center"
                )
            ),
            rx.table.cell(rx.text(row.planned.to_string(), size="1", weight="bold")),
            rx.table.cell(rx.text(row.produced.to_string(), size="1")),
            rx.table.cell(rx.text(row.inspecting.to_string(), size="1")),
            rx.table.cell(rx.text(row.actual_qty.to_string(), size="1", weight="bold")),
            rx.table.cell(
                rx.badge(
                    row.status,
                    color_scheme=rx.cond(row.actual_qty > 0, "green", "red"),
                    variant="soft"
                )
            ),
            on_click=InventoryState.toggle_expanded_variant(row.variant),
            cursor="pointer",
            style={
                "&:hover": {"background_color": "var(--slate-3)"},
                "background_color": rx.cond(is_expanded, "var(--violet-2)", "transparent"),
                "transition": "background-color 0.2s ease",
            }
        ),
        rx.cond(
            is_expanded,
            rx.table.row(
                rx.table.cell(
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.icon("layers", size=14, color=rx.color("violet", 10)),
                                rx.text(
                                    rx.fragment("【", row.variant, "】各部件独立入库与库存拆分明细"),
                                    size="1",
                                    weight="bold",
                                    color=rx.color("violet", 11)
                                ),
                                spacing="1",
                                align="center"
                            ),
                            rx.table.root(
                                rx.table.header(
                                    rx.table.row(
                                        rx.table.column_header_cell("部件名称", size="1"),
                                        rx.table.column_header_cell("单套配比", size="1"),
                                        rx.table.column_header_cell("部件入库完成(件)", size="1"),
                                        rx.table.column_header_cell("部件验收中(件)", size="1"),
                                        rx.table.column_header_cell("部件返修出库(件)", size="1"),
                                        rx.table.column_header_cell("部件仓储实物(件)", size="1"),
                                    )
                                ),
                                rx.table.body(
                                    rx.foreach(
                                        row.parts,
                                        render_part_row
                                    )
                                ),
                                size="1",
                                width="100%",
                                variant="surface"
                            ),
                            spacing="2",
                            width="100%"
                        ),
                        variant="surface",
                        width="100%",
                        padding="0.75rem",
                        margin_y="0.25rem"
                    ),
                    col_span=6
                )
            )
        )
    )


def render_excess_row(row) -> rx.Component:
    """渲染散件条目。"""
    return rx.table.row(
        rx.table.cell(rx.text(row.variant, size="1")),
        rx.table.cell(rx.text(row.part_name, size="1")),
        rx.table.cell(rx.badge(row.qty.to_string(), color_scheme="orange", variant="solid"))
    )


def render_batch_set_row(row) -> rx.Component:
    """渲染批量成套录入矩阵行"""
    return rx.table.row(
        rx.table.cell(rx.badge(row.variant, color_scheme="violet", variant="soft")),
        rx.table.cell(rx.text(row.planned.to_string(), " 套", size="1", color=rx.color("slate", 11))),
        rx.table.cell(rx.badge(row.stock_display, color_scheme="blue", variant="surface", size="1")),
        rx.table.cell(
            rx.hstack(
                rx.input(
                    placeholder="0",
                    value=row.input_val,
                    on_change=lambda val: InventoryState.set_batch_input(row.key, val),
                    size="1",
                    width="100px",
                ),
                rx.text("套", size="1", color=rx.color("slate", 10)),
                spacing="1",
                align="center",
            )
        ),
        align="center",
    )


def render_batch_part_row(row) -> rx.Component:
    """渲染批量散件细分录入矩阵行"""
    return rx.table.row(
        rx.table.cell(rx.badge(row.variant, color_scheme="violet", variant="soft")),
        rx.table.cell(rx.text(row.part_name, size="1", weight="medium")),
        rx.table.cell(rx.text(row.req_qty.to_string(), " 件/套", size="1", color=rx.color("slate", 11))),
        rx.table.cell(rx.badge(row.stock_display, color_scheme="teal", variant="surface", size="1")),
        rx.table.cell(
            rx.hstack(
                rx.input(
                    placeholder="0",
                    value=row.input_val,
                    on_change=lambda val: InventoryState.set_batch_input(row.key, val),
                    size="1",
                    width="100px",
                ),
                rx.text("件", size="1", color=rx.color("slate", 10)),
                spacing="1",
                align="center",
            )
        ),
        align="center",
    )


def render_log_row(row) -> rx.Component:
    """渲染库存操作日志。"""
    return rx.table.row(
        rx.table.cell(rx.text(row.date, size="1")),
        rx.table.cell(rx.text(row.product_name, size="1")),
        rx.table.cell(rx.badge(row.variant, color_scheme="violet", variant="soft")),
        rx.table.cell(rx.text(row.part_display, size="1")),
        rx.table.cell(rx.text(row.warehouse_name, size="1")),
        rx.table.cell(
            rx.text(
                rx.cond(row.change_qty > 0, rx.fragment("+", row.change_qty.to_string()), row.change_qty.to_string()),
                size="1",
                weight="bold",
                color=rx.cond(row.change_qty > 0, "green", "red")
            )
        ),
        rx.table.cell(
            rx.badge(
                row.reason,
                color_scheme=rx.cond(
                    row.reason == StockLogReason.REPAIR_OUT,
                    "ruby",
                    rx.cond(
                        row.reason == StockLogReason.INSPECT_REVERSAL,
                        "amber",
                        rx.cond(
                            row.reason == StockLogReason.REPAIR_IN,
                            "teal",
                            rx.cond(
                                row.reason == StockLogReason.IN_INSPECT,
                                "violet",
                                rx.cond(
                                    row.reason == StockLogReason.INSPECT_COMPLETED,
                                    "green",
                                    "blue"
                                )
                            )
                        )
                    )
                ),
                variant="soft"
            )
        ),
        rx.table.cell(rx.text(row.note, size="1", color=rx.color("slate", 10))),
        rx.table.cell(
            rx.hstack(
                rx.icon_button(
                    rx.icon("pencil", size=13),
                    variant="ghost",
                    size="1",
                    on_click=InventoryState.open_log_edit(row)
                ),
                rx.icon_button(
                    rx.icon("trash_2", size=13),
                    variant="ghost",
                    size="1",
                    color_scheme="red",
                    on_click=InventoryState.delete_log_cascade(row.id)
                ),
                spacing="1"
            )
        )
    )


def log_filter_toolbar() -> rx.Component:
    """物理仓储移动变动明细表的多维列名组合筛选工具栏（整齐单行布局）"""
    return rx.flex(
        custom_form_field(
            "商品",
            rx.select.root(
                rx.select.trigger(width="100%"),
                rx.select.content(
                    rx.foreach(InventoryState.log_product_options, lambda item: rx.select.item(item, value=item)),
                    position="popper",
                    side="bottom",
                ),
                value=InventoryState.log_filter_product,
                on_change=InventoryState.set_log_filter_product,
                size="1",
            ),
            width="140px",
            flex_shrink="0",
        ),
        custom_form_field(
            "款式",
            rx.select.root(
                rx.select.trigger(width="100%"),
                rx.select.content(
                    rx.foreach(InventoryState.log_variant_options, lambda item: rx.select.item(item, value=item)),
                    position="popper",
                    side="bottom",
                ),
                value=InventoryState.log_filter_variant,
                on_change=InventoryState.set_log_filter_variant,
                size="1",
            ),
            width="105px",
            flex_shrink="0",
        ),
        custom_form_field(
            "规格/模式",
            rx.select.root(
                rx.select.trigger(width="100%"),
                rx.select.content(
                    rx.foreach(InventoryState.log_spec_options, lambda item: rx.select.item(item, value=item)),
                    position="popper",
                    side="bottom",
                ),
                value=InventoryState.log_filter_spec,
                on_change=InventoryState.set_log_filter_spec,
                size="1",
            ),
            width="100px",
            flex_shrink="0",
        ),
        custom_form_field(
            "所属仓库",
            rx.select.root(
                rx.select.trigger(width="100%"),
                rx.select.content(
                    rx.foreach(InventoryState.log_warehouse_options, lambda item: rx.select.item(item, value=item)),
                    position="popper",
                    side="bottom",
                ),
                value=InventoryState.log_filter_warehouse,
                on_change=InventoryState.set_log_filter_warehouse,
                size="1",
            ),
            width="115px",
            flex_shrink="0",
        ),
        custom_form_field(
            "变动类型",
            rx.select.root(
                rx.select.trigger(width="100%"),
                rx.select.content(
                    rx.foreach(InventoryState.log_reason_options, lambda item: rx.select.item(item, value=item)),
                    position="popper",
                    side="bottom",
                ),
                value=InventoryState.log_filter_reason,
                on_change=InventoryState.set_log_filter_reason,
                size="1",
            ),
            width="125px",
            flex_shrink="0",
        ),
        custom_form_field(
            "关键字匹配搜索",
            rx.input(
                placeholder="输入日期/说明/商品/款式/单号...",
                value=InventoryState.log_filter_search,
                on_change=InventoryState.set_log_filter_search,
                size="1",
                width="100%",
            ),
            flex="1",
            min_width="160px",
        ),
        rx.hstack(
            rx.button(
                rx.hstack(rx.icon("rotate_ccw", size=12), rx.text("重置", size="1"), spacing="1", align="center"),
                variant="soft",
                color_scheme="gray",
                size="1",
                on_click=InventoryState.reset_log_filters,
            ),
            rx.button(
                rx.hstack(rx.icon("box", size=12), rx.text("仅当前商品", size="1"), spacing="1", align="center"),
                variant="soft",
                color_scheme="violet",
                size="1",
                on_click=InventoryState.filter_current_product_logs,
            ),
            rx.button(
                rx.hstack(rx.icon("layers", size=12), rx.text("全部商品", size="1"), spacing="1", align="center"),
                variant="soft",
                color_scheme="blue",
                size="1",
                on_click=InventoryState.filter_all_products_logs,
            ),
            spacing="1",
            align="center",
            padding_bottom="1px",
            flex_shrink="0",
        ),
        wrap="nowrap",
        spacing="2",
        align="end",
        width="100%",
        padding_y="0.25rem",
        overflow_x="auto",
    )


def log_pagination_bar() -> rx.Component:
    """物理仓储日志分页控制栏"""
    return rx.hstack(
        # 左侧：每页条数
        rx.hstack(
            rx.text("每页显示", size="1", color=rx.color("slate", 10)),
            rx.select.root(
                rx.select.trigger(width="70px"),
                rx.select.content(
                    rx.foreach(InventoryState.log_page_size_options, lambda s: rx.select.item(s, value=s)),
                    position="popper",
                    side="top",
                ),
                value=InventoryState.log_page_size_str,
                on_change=InventoryState.set_log_page_size,
                size="1",
            ),
            rx.text("条", size="1", color=rx.color("slate", 10)),
            spacing="1",
            align="center",
        ),
        rx.spacer(),
        # 中间：分页指示与翻页按钮
        rx.hstack(
            rx.button(
                "首页",
                on_click=InventoryState.log_first_page,
                disabled=~InventoryState.log_has_prev_page,
                size="1",
                variant="soft",
                color_scheme="gray",
            ),
            rx.button(
                "上一页",
                on_click=InventoryState.log_prev_page,
                disabled=~InventoryState.log_has_prev_page,
                size="1",
                variant="soft",
            ),
            rx.badge(InventoryState.log_page_info, size="1", variant="surface", color_scheme="violet"),
            rx.button(
                "下一页",
                on_click=InventoryState.log_next_page,
                disabled=~InventoryState.log_has_next_page,
                size="1",
                variant="soft",
            ),
            rx.button(
                "末页",
                on_click=InventoryState.log_last_page,
                disabled=~InventoryState.log_has_next_page,
                size="1",
                variant="soft",
                color_scheme="gray",
            ),
            spacing="2",
            align="center",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding_y="0.5rem",
    )


def render_warehouse_stock_row(r) -> rx.Component:
    """渲染某个物理仓库下的底层商品散件库存行。"""
    return rx.table.row(
        rx.table.cell(rx.text(r.product_name, size="1", weight="medium")),
        rx.table.cell(rx.badge(r.variant, color_scheme="violet", variant="soft")),
        rx.table.cell(rx.text(r.part_name, size="1")),
        rx.table.cell(rx.text(r.physical_qty.to_string(), size="1", weight="bold")),
        rx.table.cell(
            rx.text(
                rx.cond(r.part_name == "整套", "-", r.assemblable_sets.to_string()),
                size="1",
                weight="bold"
            )
        ),
    )


def render_warehouse_card(w) -> rx.Component:
    """按仓库卡片展现。"""
    # 使用过滤后的库存数组（已根据商品筛选过）
    stock_rows = InventoryState.filtered_warehouse_stocks.get(w.id.to_string(), rx.Var.create([]))
    
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.icon("store", size=16, color=rx.color("violet", 9)),
                    rx.text(w.name, weight="bold", size="3"),
                    spacing="2",
                    align="center"
                ),
                rx.spacer(),
                rx.cond(
                    w.is_empty,
                    rx.button(
                        rx.icon("trash_2", size=12),
                        "注销仓库",
                        color_scheme="red",
                        variant="soft",
                        size="1",
                        on_click=InventoryState.delete_warehouse(w.id)
                    ),
                    rx.fragment()
                ),
                width="100%",
                align="center"
            ),
            rx.text(w.remarks, size="1", color=rx.color("slate", 9)),
            rx.divider(),
            
            # 库存表格（基于过滤后的 stock_rows 判断空置）
            rx.cond(
                stock_rows.length() == 0,
                rx.text(
                    rx.cond(
                        w.is_empty,
                        "该仓库当前空置，没有存储任何物料散件或商品大货。",
                        "该商品在此仓库暂无库存。"
                    ),
                    size="1", color=rx.color("slate", 9)
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("商品名称", size="1"),
                            rx.table.column_header_cell("款式", size="1"),
                            rx.table.column_header_cell("部件", size="1"),
                            rx.table.column_header_cell("物理余量", size="1"),
                            rx.table.column_header_cell("组装整套上限 (木桶原理)", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            stock_rows,
                            render_warehouse_stock_row
                        )
                    ),
                    size="1",
                    width="100%"
                )
            ),
            spacing="3",
            width="100%"
        ),
        width="100%",
        padding="1rem"
    )


def movement_entry_form() -> rx.Component:
    """库存变动录入卡片"""
    return rx.card(
        rx.vstack(
            rx.heading("📝 新增库存变动录入", size="3", color=rx.color("violet", 10)),
            # 顶部操作核心要素：日期、变动类型、目标操作仓库（三者宽度完全一致，视觉对齐）
            rx.cond(
                InventoryState.is_transfer_mode,
                rx.vstack(
                    rx.grid(
                        custom_form_field(
                            "变动日期",
                            rx.input(
                                type="date",
                                value=InventoryState.op_date,
                                on_change=InventoryState.set_op_date,
                                size="2",
                                width="100%",
                            ),
                            width="100%",
                        ),
                        custom_form_field(
                            "变动操作类型",
                            rx.select.root(
                                rx.select.trigger(width="100%"),
                                rx.select.content(
                                    rx.foreach(InventoryState.all_movement_types, lambda item: rx.select.item(item, value=item)),
                                    position="popper",
                                    side="bottom",
                                ),
                                value=InventoryState.op_type,
                                on_change=InventoryState.set_op_type,
                                size="2",
                                width="100%",
                            ),
                            width="100%",
                        ),
                        columns="2",
                        spacing="3",
                        width="100%",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.icon("arrow_left_right", size=16, color=rx.color("blue", 9)),
                                rx.text("跨仓调拨一步式向导 (原子划转)", weight="bold", size="2", color=rx.color("blue", 11)),
                                rx.spacer(),
                                rx.badge(
                                    rx.fragment("源仓可用: ", InventoryState.transfer_source_available.to_string(), " 套/件"),
                                    color_scheme=rx.cond(InventoryState.is_transfer_qty_excess, "ruby", "teal"),
                                    variant="soft",
                                    size="1"
                                ),
                                width="100%",
                                align="center"
                            ),
                            rx.grid(
                                custom_form_field(
                                    "移出仓库 (源仓扣减)",
                                    rx.select.root(
                                        rx.select.trigger(width="100%"),
                                        rx.select.content(
                                            rx.foreach(InventoryState.transfer_warehouse_options, lambda item: rx.select.item(item, value=item)),
                                            position="popper",
                                            side="bottom",
                                        ),
                                        value=InventoryState.op_wh_name,
                                        on_change=InventoryState.set_op_wh_name,
                                        size="2",
                                        width="100%",
                                    ),
                                    width="100%",
                                ),
                                custom_form_field(
                                    "移入仓库 (目的仓增加)",
                                    rx.select.root(
                                        rx.select.trigger(width="100%"),
                                        rx.select.content(
                                            rx.foreach(InventoryState.warehouse_options, lambda item: rx.select.item(item, value=item)),
                                            position="popper",
                                            side="bottom",
                                        ),
                                        value=InventoryState.op_to_wh_name,
                                        on_change=InventoryState.set_op_to_wh_name,
                                        size="2",
                                        width="100%",
                                    ),
                                    width="100%",
                                ),
                                columns="2",
                                spacing="3",
                                width="100%"
                            ),
                            rx.callout(
                                "💡【防错指引】：调拨为一体化原子事务，系统将自动从源仓扣减实物并向目的仓增加实物，生产完成数保持不变。切勿在目的仓单独录入【验收完成入库】！",
                                icon="info",
                                color_scheme="blue",
                                variant="soft",
                                size="1",
                                width="100%"
                            ),
                            rx.cond(
                                InventoryState.is_transfer_qty_excess,
                                rx.callout(
                                    rx.fragment("⚠️ 调拨录入数量已超出源仓当前实际可用库存（当前源仓仅有 ", InventoryState.transfer_source_available.to_string(), " 套/件）！"),
                                    icon="triangle_alert",
                                    color_scheme="ruby",
                                    variant="soft",
                                    size="1",
                                    width="100%"
                                ),
                                rx.fragment()
                            ),
                            spacing="2",
                            width="100%"
                        ),
                        bg=rx.color("blue", 2),
                        border=f"1px solid {rx.color('blue', 5)}",
                        padding="0.75rem",
                        width="100%"
                    ),
                    spacing="3",
                    width="100%",
                ),
                # 常规变动：变动日期、变动操作类型、目标操作仓库 三者等宽并排
                rx.grid(
                    custom_form_field(
                        "变动日期",
                        rx.input(
                            type="date",
                            value=InventoryState.op_date,
                            on_change=InventoryState.set_op_date,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    custom_form_field(
                        "变动操作类型",
                        rx.select.root(
                            rx.select.trigger(width="100%"),
                            rx.select.content(
                                rx.foreach(InventoryState.all_movement_types, lambda item: rx.select.item(item, value=item)),
                                position="popper",
                                side="bottom",
                            ),
                            value=InventoryState.op_type,
                            on_change=InventoryState.set_op_type,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    custom_form_field(
                        "目标操作仓库",
                        rx.select.root(
                            rx.select.trigger(width="100%"),
                            rx.select.content(
                                rx.foreach(InventoryState.warehouse_options, lambda item: rx.select.item(item, value=item)),
                                position="popper",
                                side="bottom",
                            ),
                            value=InventoryState.op_wh_name,
                            on_change=InventoryState.set_op_wh_name,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
            ),
            # ✨ 入库验收模式专属：一键完成入库验收合格快速通道勾选
            rx.cond(
                InventoryState.is_in_inspect_mode,
                rx.callout(
                    rx.hstack(
                        rx.checkbox(
                            checked=InventoryState.op_auto_inspect_complete,
                            on_change=InventoryState.set_op_auto_inspect_complete,
                            size="2",
                            color_scheme="green",
                        ),
                        rx.vstack(
                            rx.hstack(
                                rx.text("直接完成入库验收合格（一键完成入库验收 + 验收合格入库）", weight="bold", size="2", color=rx.color("green", 11)),
                                rx.badge("免二次操作", color_scheme="green", variant="soft", size="1"),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(
                                "勾选此项后，提交时系统将直接按序产生【入库验收】与【验收完成入库】两条连贯流水，一步到位完成入库验收合格并累加生产完成数与大货库存，无需再次前往待验收区进行二次点收。",
                                size="1",
                                color=rx.color("slate", 10),
                            ),
                            spacing="1",
                            align_items="start",
                        ),
                        spacing="3",
                        align="center",
                        width="100%",
                    ),
                    icon="check_check",
                    color_scheme="green",
                    variant="surface",
                    size="1",
                    width="100%",
                ),
                rx.fragment(),
            ),
            # 区分：【入库冲销】单项核准模式 vs 【常规多款式/多散件批量填报矩阵】模式
            rx.cond(
                InventoryState.is_reversal_mode,
                # ================= 模式 1：入库冲销（单项精准纠错核准模式） =================
                rx.vstack(
                    rx.callout(
                        "💡【入库冲销 / 红字更正】：专用于纠正【验收完成入库】误录敲错数量的场景。系统将同步扣减目标仓库的物理实物与商品累计生产总数，并将对应数量恢复至【入库验收中】。为防范批量误冲风险，入库冲销仅支持单款式/单散件精准核准录入。",
                        icon="rotate_ccw",
                        color_scheme="amber",
                        variant="soft",
                        size="1",
                        width="100%"
                    ),
                    rx.grid(
                        custom_form_field(
                            "选择冲销款式",
                            rx.select.root(
                                rx.select.trigger(),
                                rx.select.content(
                                    rx.foreach(InventoryState.active_variants, lambda item: rx.select.item(item, value=item)),
                                    position="popper",
                                    side="bottom",
                                ),
                                value=InventoryState.op_variant,
                                on_change=InventoryState.set_op_variant,
                                size="2"
                            )
                        ),
                        custom_form_field(
                            "冲销套数/物理件数",
                            rx.input(
                                value=InventoryState.op_qty.to_string(),
                                on_change=InventoryState.set_op_qty,
                                type="number",
                                min="1",
                                size="2"
                            )
                        ),
                        columns="2",
                        spacing="3",
                        width="100%"
                    ),
                    rx.cond(
                        InventoryState.has_parts_for_color,
                        rx.grid(
                            rx.hstack(
                                rx.switch(
                                    checked=InventoryState.op_is_set,
                                    on_change=InventoryState.set_op_is_set,
                                    size="1",
                                    color_scheme="amber"
                                ),
                                rx.text("整套动作 (款式所有部件同比例冲销)", size="1", color=rx.color("slate", 10)),
                                spacing="2",
                                align="center",
                                padding_top="1.5rem"
                            ),
                            rx.cond(
                                InventoryState.op_is_set,
                                rx.fragment(),
                                custom_form_field(
                                    "选择冲销归属散件",
                                    rx.select.root(
                                        rx.select.trigger(),
                                        rx.select.content(
                                            rx.foreach(InventoryState.active_parts, lambda item: rx.select.item(item, value=item)),
                                            position="popper",
                                            side="bottom",
                                        ),
                                        value=InventoryState.op_part,
                                        on_change=InventoryState.set_op_part,
                                        size="2"
                                    )
                                )
                            ),
                            columns="2",
                            spacing="3",
                            width="100%"
                        ),
                        rx.fragment()
                    ),
                    custom_form_field(
                        "冲销审计原因 (必填)",
                        rx.input(
                            placeholder="请说明冲销原因，如：质检复核多录2套，据实冲销扣减...",
                            value=InventoryState.op_remark,
                            on_change=InventoryState.set_op_remark,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.button(
                        "⚠️ 提交入库冲销 (单项核准纠错)",
                        on_click=InventoryState.submit_inventory_movement,
                        color_scheme="amber",
                        width="100%",
                        size="3"
                    ),
                    spacing="3",
                    width="100%"
                ),
                # ================= 模式 2：常规变动（多款式/多部件批量录入矩阵） =================
                rx.vstack(
                    # 返修后入库提示
                    rx.cond(
                        InventoryState.is_repair_in,
                        rx.callout(
                            "💡【返修后入库】：专用于之前进行过【验收不合格返修】的货物在修好后重新回仓入库。系统将增加物理仓储实物并自动从“返修出库中”减扣对应数量，同时计入累计生产完成数。",
                            icon="info",
                            color_scheme="teal",
                            variant="soft",
                            size="1",
                            width="100%"
                        ),
                        rx.fragment()
                    ),

                    # 验收不合格返修专属提示
                    rx.cond(
                        InventoryState.is_repair_out,
                        rx.callout(
                            "💡【验收不合格返修】：直接减扣【入库验收中】的数量，并计入【部件返修中】。不影响仓库物理实物。返修完毕后可通过【返修后入库】重新入库。",
                            icon="wrench",
                            color_scheme="ruby",
                            variant="soft",
                            size="1"
                        ),
                        rx.fragment()
                    ),

                    # 出库特有消耗记账表单
                    rx.cond(
                        InventoryState.is_out_mode,
                        rx.vstack(
                            custom_form_field(
                                "出库分类模式",
                                rx.radio(
                                    ["消耗", "寄售", "其他"],
                                    value=InventoryState.op_out_mode,
                                    on_change=InventoryState.set_op_out_mode,
                                    direction="row",
                                    spacing="3"
                                )
                            ),
                            rx.cond(
                                InventoryState.is_consumable_out,
                                rx.grid(
                                    custom_form_field(
                                        "计入商品成本科目",
                                        rx.select.root(
                                            rx.select.trigger(),
                                            rx.select.content(
                                                rx.foreach(InventoryState.cost_categories, lambda item: rx.select.item(item, value=item)),
                                                position="popper",
                                                side="bottom",
                                            ),
                                            value=InventoryState.op_cons_cat,
                                            on_change=InventoryState.set_op_cons_cat,
                                            size="2"
                                        )
                                    ),
                                    custom_form_field(
                                        "消耗内容 (必填描述)",
                                        rx.input(
                                            placeholder="如：宣发拍摄样衣",
                                            value=InventoryState.op_cons_content,
                                            on_change=InventoryState.set_op_cons_content,
                                            size="2"
                                        )
                                    ),
                                    columns="2",
                                    spacing="3",
                                    width="100%"
                                ),
                                rx.fragment()
                            ),
                            rx.cond(
                                InventoryState.is_consignment_out,
                                custom_form_field(
                                    "寄售店铺 (必填)",
                                    rx.input(
                                        placeholder="如：秋叶原店、某某代理店等...",
                                        value=InventoryState.op_consignment_shop,
                                        on_change=InventoryState.set_op_consignment_shop,
                                        size="2",
                                        width="100%",
                                    ),
                                    width="100%",
                                ),
                                rx.fragment()
                            ),
                            spacing="3",
                            width="100%"
                        ),
                        rx.fragment()
                    ),
                    
                    custom_form_field(
                        "批次通用备注 (选填)",
                        rx.input(
                            placeholder="本批次操作补充备注，如：工厂大货到货、调拨运单号等...",
                            value=InventoryState.op_remark,
                            on_change=InventoryState.set_op_remark,
                            size="2",
                            width="100%",
                        ),
                        width="100%",
                    ),

                    
                    # 批量填报矩阵卡片
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.hstack(
                                    rx.icon("boxes", size=16, color=rx.color("violet", 9)),
                                    rx.text("本批次款式 / 散件变动数量填报", weight="bold", size="2"),
                                    spacing="1",
                                    align="center"
                                ),
                                rx.spacer(),
                                rx.radio(
                                    ["成套录入 (默认)", "散件细分录入"],
                                    value=rx.cond(InventoryState.is_batch_set_mode, "成套录入 (默认)", "散件细分录入"),
                                    on_change=InventoryState.set_batch_mode,
                                    direction="row",
                                    spacing="3",
                                    size="1"
                                ),
                                align="center",
                                width="100%",
                                padding_y="0.25rem"
                            ),
                            rx.cond(
                                InventoryState.is_batch_set_mode,
                                # 成套录入矩阵
                                rx.scroll_area(
                                    rx.table.root(
                                        rx.table.header(
                                            rx.table.row(
                                                rx.table.column_header_cell("款式颜色", size="1"),
                                                rx.table.column_header_cell("计划生产", size="1"),
                                                rx.table.column_header_cell("当前仓库库存", size="1"),
                                                rx.table.column_header_cell("本次变动数量", size="1")
                                            )
                                        ),
                                        rx.table.body(
                                            rx.foreach(
                                                InventoryState.batch_set_rows,
                                                render_batch_set_row
                                            )
                                        ),
                                        size="1",
                                        width="100%",
                                        variant="surface"
                                    ),
                                    type="auto",
                                    scrollbars="vertical",
                                    max_height="320px",
                                    width="100%"
                                ),
                                # 散件细分录入矩阵
                                rx.scroll_area(
                                    rx.table.root(
                                        rx.table.header(
                                            rx.table.row(
                                                rx.table.column_header_cell("款式颜色", size="1"),
                                                rx.table.column_header_cell("部件名称", size="1"),
                                                rx.table.column_header_cell("配比要求", size="1"),
                                                rx.table.column_header_cell("当前仓库库存", size="1"),
                                                rx.table.column_header_cell("本次变动数量", size="1")
                                            )
                                        ),
                                        rx.table.body(
                                            rx.foreach(
                                                InventoryState.batch_part_rows,
                                                render_batch_part_row
                                            )
                                        ),
                                        size="1",
                                        width="100%",
                                        variant="surface"
                                    ),
                                    type="auto",
                                    scrollbars="vertical",
                                    max_height="320px",
                                    width="100%"
                                )
                            ),
                            rx.hstack(
                                rx.hstack(
                                    rx.icon("info", size=13, color=rx.color("violet", 9)),
                                    rx.text(InventoryState.batch_summary_text, size="1", weight="medium", color=rx.color("slate", 11)),
                                    spacing="1",
                                    align="center"
                                ),
                                rx.spacer(),
                                rx.button(
                                    rx.hstack(rx.icon("rotate_ccw", size=12), rx.text("清空已填", size="1"), spacing="1", align="center"),
                                    variant="soft",
                                    color_scheme="gray",
                                    size="1",
                                    on_click=InventoryState.clear_batch_inputs
                                ),
                                align="center",
                                width="100%",
                                padding_top="0.25rem"
                            ),
                            spacing="2",
                            width="100%"
                        ),
                        bg=rx.color("slate", 2),
                        border=f"1px solid {rx.color('slate', 5)}",
                        padding="0.75rem",
                        width="100%"
                    ),
                    rx.button(
                        rx.cond(
                            InventoryState.op_auto_inspect_complete,
                            "⚡ 一键完成入库验收 + 验收合格入库 (双流水写入)",
                            "🚀 一键批量录入并写入流水明细"
                        ),
                        on_click=InventoryState.submit_batch_inventory_movement,
                        color_scheme=rx.cond(InventoryState.op_auto_inspect_complete, "green", "violet"),
                        width="100%",
                        size="3"
                    ),
                    spacing="3",
                    width="100%"
                )
            ),
            spacing="3",
            width="100%"
        ),
        width="100%",
        padding="1rem"
    )


def log_memo_dialog() -> rx.Component:
    """修改日志备注 dialog"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("📝 修改操作日志备注"),
            rx.dialog.description("更改已发生库存变动记录的审计详情备注说明。", size="1"),
            rx.vstack(
                custom_form_field(
                    "审计备注",
                    rx.input(
                        value=InventoryState.edit_log_note,
                        on_change=InventoryState.set_edit_log_note,
                        size="2"
                    )
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=InventoryState.close_log_edit)
                    ),
                    rx.button("确认保存", on_click=InventoryState.submit_log_edit, color_scheme="violet"),
                    spacing="3",
                    justify="end",
                    width="100%"
                ),
                spacing="3",
                width="100%",
                margin_top="1rem"
            ),
            max_width="400px"
        ),
        open=InventoryState.is_log_edit_open,
    )


def overproduction_warning_dialog() -> rx.Component:
    """超计划入库拦截与强提醒对话框"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.icon("triangle_alert", size=24, color=rx.color("ruby", 9)),
                    rx.heading("⚠️ 超计划生产入库风险预警", size="4", weight="bold", color=rx.color("ruby", 11)),
                    spacing="2",
                    align="center",
                ),
                rx.callout(
                    rx.vstack(
                        rx.text(
                            rx.fragment(
                                "款式【", InventoryState.overprod_variant, "】计划生产 ",
                                InventoryState.overprod_planned.to_string(), " 套，当前已累计入库 ",
                                InventoryState.overprod_current.to_string(), " 套。"
                            ),
                            weight="medium",
                            size="2",
                        ),
                        rx.text(
                            rx.fragment(
                                "本次尝试录入 ", InventoryState.overprod_incoming.to_string(),
                                " 套后，累计入库将达到 ",
                                (InventoryState.overprod_current + InventoryState.overprod_incoming).to_string(),
                                " 套（超出计划生产数 ", InventoryState.overprod_diff.to_string(), " 套）！"
                            ),
                            weight="bold",
                            size="2",
                            color=rx.color("ruby", 11),
                        ),
                        spacing="1",
                    ),
                    icon="info",
                    color_scheme="ruby",
                    variant="soft",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("📌 请仔细核对本次录入的货物来源：", size="2", weight="bold"),
                    rx.text(
                        "1. 如果这批货是从其他网点（如中山仓）调拨运抵，请立即【取消】并在变动操作类型中选择【库存移动】，切勿录入【验收完成入库】（否则会导致累计生产数重复计算）！",
                        size="1",
                        color=rx.color("slate", 11),
                    ),
                    rx.text(
                        "2. 如果这批货确实是工厂额外完工交付的合格超产大货，请点击下方【确认属于超产，强制录入】。",
                        size="1",
                        color=rx.color("slate", 11),
                    ),
                    spacing="2",
                    padding="0.75rem",
                    border_radius="6px",
                    bg=rx.color("slate", 2),
                    width="100%",
                ),
                rx.hstack(
                    rx.button(
                        "❌ 取消并核对",
                        variant="soft",
                        color_scheme="gray",
                        on_click=InventoryState.close_overprod_dialog,
                    ),
                    rx.button(
                        "⚠️ 确认属于超产，强制录入",
                        color_scheme="ruby",
                        on_click=InventoryState.confirm_overprod_movement,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            max_width="520px",
        ),
        open=InventoryState.is_overprod_dialog_open,
    )


# ================= 寄售管理组件 =================
def render_consignment_row(row) -> rx.Component:
    """渲染单笔寄售条目（支持直接编辑剩余数量与备注，点击保存）"""
    return rx.table.row(
        rx.table.cell(rx.text(row.date, size="1", color=rx.color("slate", 10))),
        rx.table.cell(
            rx.badge(
                rx.hstack(rx.icon("store", size=11), rx.text(row.shop_name, size="1"), spacing="1", align="center"),
                color_scheme="violet",
                variant="surface",
                size="1"
            )
        ),
        rx.table.cell(rx.text(row.product_name, size="1", weight="bold")),
        rx.table.cell(rx.badge(row.variant, color_scheme="violet", variant="soft", size="1")),
        rx.table.cell(
            rx.badge(
                rx.fragment(row.quantity.to_string(), " 件"),
                color_scheme="blue",
                variant="soft",
                size="1"
            )
        ),
        # 可编辑剩余数量栏
        rx.table.cell(
            rx.hstack(
                rx.input(
                    type="number",
                    min="0",
                    value=row.remaining_input,
                    on_change=lambda val: InventoryState.set_consignment_row_input(row.id, "remaining_qty", val),
                    size="1",
                    width="70px",
                ),
                rx.text("件", size="1", color=rx.color("slate", 10)),
                rx.badge(row.status_label, color_scheme=row.status_color, variant="surface", size="1"),
                spacing="1",
                align="center",
            )
        ),
        # 可编辑备注栏
        rx.table.cell(
            rx.input(
                placeholder="填写寄售相关备注...",
                value=row.remarks_input,
                on_change=lambda val: InventoryState.set_consignment_row_input(row.id, "remarks", val),
                size="1",
                width="100%",
                min_width="160px",
            )
        ),
        # 操作栏
        rx.table.cell(
            rx.hstack(
                rx.button(
                    rx.hstack(rx.icon("save", size=11), rx.text("保存", size="1"), spacing="1", align="center"),
                    size="1",
                    color_scheme="violet",
                    variant="solid",
                    on_click=InventoryState.save_consignment_row(row.id),
                ),
                rx.icon_button(
                    rx.icon("pencil", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="gray",
                    on_click=InventoryState.open_consignment_edit(row.id),
                ),
                rx.icon_button(
                    rx.icon("trash_2", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="ruby",
                    on_click=InventoryState.delete_consignment_item(row.id),
                ),
                spacing="1",
                align="center",
            )
        ),
        align="center",
    )


def consignment_management_view() -> rx.Component:
    """寄售管理视图面板"""
    return rx.vstack(
        # 1. 顶部统计指标卡片
        rx.grid(
            stat_card("寄售店铺数", InventoryState.consignment_unique_shops_count, unit="家", color_scheme="violet", icon="store"),
            stat_card("寄售记录数", InventoryState.consignment_total_count, unit="笔", color_scheme="blue", icon="file-text"),
            stat_card("累计寄售总数", InventoryState.consignment_total_initial_qty, unit="件", color_scheme="cyan", icon="package"),
            stat_card("当前在店剩余", InventoryState.consignment_total_remaining_qty, unit="件", color_scheme="green", icon="boxes"),
            stat_card("估算售出/核销", InventoryState.consignment_total_sold_qty, unit="件", color_scheme="amber", icon="shopping-cart"),
            columns="5",
            spacing="3",
            width="100%",
            margin_top="1rem",
        ),
        
        # 2. 寄售操作与说明 Callout
        rx.callout(
            rx.vstack(
                rx.hstack(
                    rx.icon("info", size=14, color=rx.color("blue", 11)),
                    rx.text("💡 寄售管理功能说明：", weight="bold", size="2", color=rx.color("blue", 11)),
                    spacing="1",
                    align="center",
                ),
                rx.text(
                    "1. 在【出库】变动中选择【寄售】模式并填写店铺名称，出库扣减实物后将自动记录在此处；",
                    size="1",
                    color=rx.color("slate", 11),
                ),
                rx.text(
                    "2. 表格中的【剩余数量】和【备注】均支持在单元格内直接修改，修改后点击该行的【保存】按钮即可更新；",
                    size="1",
                    color=rx.color("slate", 11),
                ),
                rx.text(
                    "3. 【剩余数量】专用于手动盘点核对线下在店库存余量，修改该栏仅记录剩余件数，不会向仓库扣减或冲销实物。",
                    size="1",
                    color=rx.color("slate", 11),
                ),
                spacing="1",
            ),
            color_scheme="blue",
            variant="soft",
            size="1",
            width="100%",
        ),

        # 3. 筛选与操作工具栏
        rx.card(
            rx.hstack(
                # 店铺筛选
                custom_form_field(
                    "寄售店铺",
                    rx.select.root(
                        rx.select.trigger(width="100%"),
                        rx.select.content(
                            rx.foreach(InventoryState.consignment_shop_options, lambda s: rx.select.item(s, value=s)),
                            position="popper",
                            side="bottom",
                        ),
                        value=InventoryState.consignment_filter_shop,
                        on_change=InventoryState.set_consignment_filter_shop,
                        size="1",
                    ),
                    width="140px",
                ),
                # 商品筛选
                custom_form_field(
                    "所属商品",
                    rx.select.root(
                        rx.select.trigger(width="100%"),
                        rx.select.content(
                            rx.foreach(InventoryState.consignment_product_options, lambda p: rx.select.item(p, value=p)),
                            position="popper",
                            side="bottom",
                        ),
                        value=InventoryState.consignment_filter_product,
                        on_change=InventoryState.set_consignment_filter_product,
                        size="1",
                    ),
                    width="160px",
                ),
                # 关键词搜索
                custom_form_field(
                    "关键字快速搜索",
                    rx.input(
                        placeholder="搜索店铺/商品/款式/备注/日期...",
                        value=InventoryState.consignment_filter_search,
                        on_change=InventoryState.set_consignment_filter_search,
                        size="1",
                        width="100%",
                    ),
                    flex="1",
                    min_width="180px",
                ),
                # 按钮组
                rx.hstack(
                    rx.button(
                        rx.hstack(rx.icon("rotate_ccw", size=12), rx.text("重置筛选", size="1"), spacing="1", align="center"),
                        variant="soft",
                        color_scheme="gray",
                        size="1",
                        on_click=InventoryState.reset_consignment_filters,
                    ),
                    rx.button(
                        rx.hstack(rx.icon("refresh_cw", size=12), rx.text("刷新列表", size="1"), spacing="1", align="center"),
                        variant="soft",
                        color_scheme="violet",
                        size="1",
                        on_click=InventoryState.load_consignments,
                    ),
                    rx.button(
                        rx.hstack(rx.icon("plus", size=12), rx.text("手动新增寄售", size="1"), spacing="1", align="center"),
                        color_scheme="green",
                        size="1",
                        on_click=InventoryState.open_consignment_add,
                    ),
                    spacing="2",
                    align="end",
                    padding_bottom="1px",
                ),
                spacing="3",
                align="end",
                width="100%",
            ),
            width="100%",
            padding="0.75rem",
        ),

        # 4. 寄售记录表格
        data_card(
            "🏪 实体店铺寄售资产明细台账",
            rx.cond(
                InventoryState.filtered_consignments.length() == 0,
                empty_state("暂无寄售记录。可在上方变动操作中选择【出库 -> 寄售】模式出库自动沉淀，或点击【手动新增寄售】直接补录。"),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("寄售日期", size="1"),
                            rx.table.column_header_cell("寄售店铺", size="1"),
                            rx.table.column_header_cell("商品名称", size="1"),
                            rx.table.column_header_cell("款式规格", size="1"),
                            rx.table.column_header_cell("初始寄售数", size="1"),
                            rx.table.column_header_cell("【剩余数量】(手动编辑)", size="1"),
                            rx.table.column_header_cell("【备注说明】(手动编辑)", size="1"),
                            rx.table.column_header_cell("操作", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            InventoryState.filtered_consignments,
                            render_consignment_row
                        )
                    ),
                    size="1",
                    width="100%",
                    variant="surface",
                ),
            ),
        ),
        spacing="4",
        width="100%",
    )


def consignment_edit_dialog() -> rx.Component:
    """弹窗编辑寄售记录详情"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("📝 编辑寄售记录详情"),
            rx.dialog.description("核对并调整寄售店铺、手动维护剩余件数及补充备注。", size="1"),
            rx.vstack(
                custom_form_field(
                    "寄售店铺名称",
                    rx.input(
                        value=InventoryState.modal_cons_shop,
                        on_change=InventoryState.set_modal_cons_shop,
                        size="2",
                        width="100%",
                    )
                ),
                rx.grid(
                    custom_form_field(
                        "商品与款式 (只读)",
                        rx.text(rx.fragment(InventoryState.modal_cons_product, " - ", InventoryState.modal_cons_variant), size="2", weight="bold"),
                    ),
                    custom_form_field(
                        "初始寄售数量 (只读)",
                        rx.badge(rx.fragment(InventoryState.modal_cons_qty.to_string(), " 件"), color_scheme="blue", size="2"),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                custom_form_field(
                    "剩余数量 (件，用于手动记录当前还剩几件)",
                    rx.input(
                        type="number",
                        min="0",
                        value=InventoryState.modal_cons_remaining_qty.to_string(),
                        on_change=InventoryState.set_modal_cons_remaining_qty,
                        size="2",
                        width="100%",
                    ),
                    helper="此栏目仅用于手动记录剩余数量，不会扣减或冲销主仓库实物。"
                ),
                custom_form_field(
                    "备注说明",
                    rx.input(
                        placeholder="寄售说明、展出情况或结款备忘...",
                        value=InventoryState.modal_cons_remarks,
                        on_change=InventoryState.set_modal_cons_remarks,
                        size="2",
                        width="100%",
                    )
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=InventoryState.close_consignment_edit)
                    ),
                    rx.button("确认保存", on_click=InventoryState.submit_consignment_edit, color_scheme="violet"),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top="1rem",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="480px",
        ),
        open=InventoryState.is_consignment_modal_open,
    )


def consignment_add_dialog() -> rx.Component:
    """手动新增寄售记录弹窗"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("➕ 手动新增寄售记录"),
            rx.dialog.description("手动补录一条已有外部寄售，用于独立跟踪店铺剩余数量与备注。", size="1"),
            rx.vstack(
                custom_form_field(
                    "寄售店铺名称 (必填)",
                    rx.input(
                        placeholder="如：秋叶原店、某某代理店等...",
                        value=InventoryState.add_cons_shop,
                        on_change=InventoryState.set_add_cons_shop,
                        size="2",
                        width="100%",
                    )
                ),
                rx.grid(
                    custom_form_field(
                        "寄售商品 (必选)",
                        rx.select.root(
                            rx.select.trigger(width="100%"),
                            rx.select.content(
                                rx.foreach(InventoryState.product_names, lambda p: rx.select.item(p, value=p)),
                                position="popper",
                                side="bottom",
                            ),
                            value=InventoryState.add_cons_product,
                            on_change=InventoryState.set_add_cons_product,
                            size="2",
                        )
                    ),
                    custom_form_field(
                        "款式颜色",
                        rx.select.root(
                            rx.select.trigger(width="100%"),
                            rx.select.content(
                                rx.foreach(InventoryState.active_variants, lambda v: rx.select.item(v, value=v)),
                                position="popper",
                                side="bottom",
                            ),
                            value=InventoryState.add_cons_variant,
                            on_change=InventoryState.set_add_cons_variant,
                            size="2",
                        )
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                rx.grid(
                    custom_form_field(
                        "寄售数量 (件)",
                        rx.input(
                            type="number",
                            min="1",
                            value=InventoryState.add_cons_qty.to_string(),
                            on_change=InventoryState.set_add_cons_qty,
                            size="2",
                            width="100%",
                        )
                    ),
                    custom_form_field(
                        "初始剩余数量 (件)",
                        rx.input(
                            type="number",
                            min="0",
                            value=InventoryState.add_cons_remaining_qty.to_string(),
                            on_change=InventoryState.set_add_cons_remaining_qty,
                            size="2",
                            width="100%",
                        )
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                custom_form_field(
                    "寄售日期",
                    rx.input(
                        type="date",
                        value=InventoryState.add_cons_date,
                        on_change=InventoryState.set_add_cons_date,
                        size="2",
                        width="100%",
                    )
                ),
                custom_form_field(
                    "备注说明 (选填)",
                    rx.input(
                        placeholder="如：首批样衣试销、展示样品等...",
                        value=InventoryState.add_cons_remarks,
                        on_change=InventoryState.set_add_cons_remarks,
                        size="2",
                        width="100%",
                    )
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=InventoryState.close_consignment_add)
                    ),
                    rx.button("确认添加", on_click=InventoryState.submit_consignment_add, color_scheme="green"),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top="1rem",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="480px",
        ),
        open=InventoryState.is_consignment_add_open,
    )


def inventory_page() -> rx.Component:
    """库存主页面布局。"""
    return page_layout(
        rx.vstack(
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger(
                        rx.hstack(rx.icon("box", size=14), rx.text("库存管理与盘点"), spacing="1"),
                        value="stock",
                    ),
                    rx.tabs.trigger(
                        rx.hstack(rx.icon("store", size=14), rx.text("物理仓库与明细"), spacing="1"),
                        value="warehouse",
                    ),
                    rx.tabs.trigger(
                        rx.hstack(rx.icon("shopping-bag", size=14), rx.text("寄售管理"), spacing="1"),
                        value="consignment",
                    ),
                    width="100%"
                ),
                
                # ==== 选项卡 1：库存管理 ====
                rx.tabs.content(
                    rx.vstack(
                        # 顶部产品选择与新增面板
                        rx.card(
                            rx.hstack(
                                rx.text("当前核算商品:", size="2", weight="medium"),
                                rx.select.root(
    rx.select.trigger(),
    rx.select.content(
        rx.foreach(InventoryState.product_names, lambda item: rx.select.item(item, value=item)),
        position="popper",
        side="bottom",
    ),
    value=InventoryState.selected_product_name,
                                    on_change=InventoryState.select_product,
                                    size="2",
                                    width="200px"
),
                                rx.spacer(),
                                rx.button(
                                    rx.icon("refresh-cw", size=14),
                                    "刷新库存",
                                    on_click=InventoryState.load_inventory_page,
                                    variant="soft",
                                    color_scheme="gray",
                                    size="2",
                                ),
                                rx.cond(
                                    InventoryState.is_production_completed,
                                    rx.badge("🔒 生产结单", color_scheme="green", variant="soft"),
                                    rx.badge("⚡ WIP 流转中", color_scheme="orange", variant="soft")
                                ),
                                spacing="3",
                                align="center",
                                width="100%"
                            ),
                            width="100%",
                            padding="1rem",
                            margin_top="1rem"
                        ),
                        
                        rx.cond(
                            InventoryState.has_products,
                            rx.vstack(
                                # 左右双栏大格
                                rx.grid(
                                    # --- 左栏：款式进度表 ---
                                    rx.vstack(
                                        rx.heading("🎨 款式生产及实存进度表", size="4", weight="bold"),
                                        data_card(
                                            "各款式细化统计 (成套)",
                                            rx.table.root(
                                                rx.table.header(
                                                    rx.table.row(
                                                        rx.table.column_header_cell("款式颜色", size="1"),
                                                        rx.table.column_header_cell("计划生产数", size="1"),
                                                        rx.table.column_header_cell("验收完成入库", size="1"),
                                                        rx.table.column_header_cell("入库验收中", size="1"),
                                                        rx.table.column_header_cell("仓储实物(成套)", size="1"),
                                                        rx.table.column_header_cell("供货状态", size="1"),
                                                    )
                                                ),
                                                rx.table.body(
                                                    rx.foreach(
                                                        InventoryState.stats,
                                                        render_progress_row
                                                    )
                                                ),
                                                size="1",
                                                width="100%",
                                                variant="ghost"
                                            )
                                        ),
                                        
                                        # 多余部件折叠列表
                                        rx.cond(
                                            InventoryState.has_excess_parts,
                                            rx.accordion.root(
                                                rx.accordion.item(
                                                    header=rx.hstack(
                                                        rx.icon("search", size=13, color=rx.color("violet", 9)),
                                                        rx.text("查看无法成套的散落部件物理余量", size="1", weight="medium"),
                                                        spacing="1",
                                                        align="center"
                                                    ),
                                                    content=rx.table.root(
                                                        rx.table.header(
                                                            rx.table.row(
                                                                rx.table.column_header_cell("款式", size="1"),
                                                                rx.table.column_header_cell("散落部件", size="1"),
                                                                rx.table.column_header_cell("物理数量", size="1")
                                                            )
                                                        ),
                                                        rx.table.body(
                                                            rx.foreach(
                                                                InventoryState.excess_parts,
                                                                render_excess_row
                                                            )
                                                        ),
                                                        size="1",
                                                        width="100%"
                                                    ),
                                                    value="excess"
                                                ),
                                                collapsible=True,
                                                variant="outline",
                                                width="100%",
                                                style={
                                                    "border": "1px solid var(--violet-6)",
                                                    "borderRadius": "6px",
                                                    "padding": "0.25rem 0.75rem",
                                                }
                                            ),
                                            rx.fragment()
                                        ),
                                        grid_column="span 7",
                                        width="100%",
                                        spacing="3"
                                    ),
                                    
                                    # --- 右栏：操作提交与在制结清 ---
                                    rx.vstack(
                                        rx.heading("⚙️ 仓储操作与在制资产", size="4", weight="bold"),
                                        stat_card("在制资产估值 (WIP)", InventoryState.wip_balance_str, icon="wrench", color_scheme="orange"),
                                        
                                        rx.cond(
                                            InventoryState.is_production_completed,
                                            rx.card(
                                                rx.vstack(
                                                    rx.text("💡 该商品已生产结单（在制资产已清零）。若后期追加了新的真实物理成本项，请点击下方按钮重新触发木桶还原估值与大货资产的同步核算：", size="1", color=rx.color("slate", 10)),
                                                    rx.button("🔄 重新核算大货成本与资产", color_scheme="violet", variant="soft", on_click=InventoryState.clear_product_wip, size="2", width="100%"),
                                                    spacing="2",
                                                    width="100%"
                                                ),
                                                width="100%",
                                                padding="0.75rem"
                                            ),
                                            rx.card(
                                                rx.vstack(
                                                    rx.text("💡 当前未完结生产，可在生产大货全部进入仓库后，清零在制折旧冲账大货：", size="1", color=rx.color("slate", 10)),
                                                    rx.button("🚀 生产结单 (在制资产清零)", color_scheme="red", on_click=InventoryState.clear_product_wip, size="2", width="100%"),
                                                    spacing="2",
                                                    width="100%"
                                                ),
                                                width="100%",
                                                padding="0.75rem"
                                            )
                                        ),
                                        
                                        movement_entry_form(),
                                        grid_column="span 5",
                                        width="100%",
                                        spacing="3"
                                    ),
                                    columns="12",
                                    spacing="5",
                                    width="100%",
                                    align_items="start"
                                ),
                                
                                # --- 审计变动记录 ---
                                rx.vstack(
                                    rx.heading("📜 仓储物理日志与操作审计变动历史", size="4", weight="bold", margin_top="1rem"),
                                    data_card(
                                        "物理仓储移动变动明细",
                                        # 组合筛选工具栏
                                        log_filter_toolbar(),
                                        rx.divider(),
                                        # 表格与分页
                                        rx.cond(
                                            InventoryState.filtered_logs.length() == 0,
                                            empty_state("当前筛选条件下未查询到任何物理仓储变动明细。"),
                                            rx.vstack(
                                                rx.scroll_area(
                                                    rx.table.root(
                                                        rx.table.header(
                                                            rx.table.row(
                                                                rx.table.column_header_cell("日期", size="1"),
                                                                rx.table.column_header_cell("商品", size="1"),
                                                                rx.table.column_header_cell("款式", size="1"),
                                                                rx.table.column_header_cell("规格/模式", size="1"),
                                                                rx.table.column_header_cell("所属仓库", size="1"),
                                                                rx.table.column_header_cell("变动量", size="1"),
                                                                rx.table.column_header_cell("物理类型", size="1"),
                                                                rx.table.column_header_cell("审计说明(可改)", size="1"),
                                                                rx.table.column_header_cell("操作", size="1")
                                                            )
                                                        ),
                                                        rx.table.body(
                                                            rx.foreach(
                                                                InventoryState.paginated_logs,
                                                                render_log_row
                                                            )
                                                        ),
                                                        size="1",
                                                        width="100%",
                                                        variant="ghost"
                                                    ),
                                                    type="auto",
                                                    scrollbars="both",
                                                ),
                                                log_pagination_bar(),
                                                width="100%",
                                                spacing="3"
                                            )
                                        )
                                    ),
                                    width="100%",
                                    spacing="3"
                                ),
                                width="100%",
                                spacing="5"
                            ),
                            rx.callout(
                                "系统里没有任何商品，请先前往商品管理开户！",
                                icon="triangle_alert",
                                color_scheme="orange",
                                width="100%"
                            )
                        ),
                        spacing="4",
                        width="100%"
                    ),
                    value="stock",
                    on_mount=InventoryState.load_inventory_page
                ),
                
                # ==== 选项卡 2：仓库明细端 ====
                rx.tabs.content(
                    rx.vstack(
                        rx.heading("🏢 物理仓储实体网点配置", size="4", weight="bold", margin_top="1rem"),
                        
                        # 新建仓库折叠
                        rx.accordion.root(
                            rx.accordion.item(
                                header=rx.hstack(
                                    rx.icon("plus", size=13),
                                    rx.text("开立配置新仓库", size="2"),
                                    spacing="1",
                                    align="center"
                                ),
                                content=rx.vstack(
                                    rx.grid(
                                        custom_form_field(
                                            "仓库名称",
                                            rx.input(
                                                placeholder="如：北京1号分拣仓",
                                                value=InventoryState.new_wh_name,
                                                on_change=InventoryState.set_new_wh_name,
                                                size="2"
                                            )
                                        ),
                                        custom_form_field(
                                            "仓库备注",
                                            rx.input(
                                                placeholder="如：联系人电话/地址",
                                                value=InventoryState.new_wh_remarks,
                                                on_change=InventoryState.set_new_wh_remarks,
                                                size="2"
                                            )
                                        ),
                                        columns="2",
                                        spacing="3",
                                        width="100%"
                                    ),
                                    rx.button(
                                        "新建并持久化该仓库",
                                        on_click=InventoryState.add_warehouse,
                                        color_scheme="violet",
                                        size="2"
                                    ),
                                    spacing="3",
                                    width="100%"
                                ),
                                value="create-wh"
                            ),
                            collapsible=True,
                            width="100%"
                        ),
                        
                        rx.divider(),
                        rx.hstack(
                            rx.heading("🏬 各实体网点散落实存清单明细 (成套木桶还原折算)", size="4", weight="bold"),
                            rx.spacer(),
                            # 商品筛选器
                            rx.hstack(
                                rx.icon("filter", size=14, color=rx.color("violet", 9)),
                                rx.text("商品筛选:", size="2", weight="medium", color=rx.color("slate", 11)),
                                rx.select.root(
    rx.select.trigger(),
    rx.select.content(
        rx.foreach(InventoryState.wh_product_options, lambda item: rx.select.item(item, value=item)),
        position="popper",
        side="bottom",
    ),
    value=InventoryState.wh_filter_display,
                                    on_change=InventoryState.set_wh_filter_product,
                                    size="2",
                                    width="160px",
                                    color_scheme="violet"
),
                                rx.cond(
                                    InventoryState.wh_filter_product != "",
                                    rx.button(
                                        rx.icon("x", size=12),
                                        "清除筛选条件",
                                        size="1",
                                        variant="soft",
                                        color_scheme="gray",
                                        on_click=InventoryState.set_wh_filter_product("全部商品")
                                    ),
                                    rx.fragment()
                                ),
                                spacing="2",
                                align="center"
                            ),
                            align="center",
                            width="100%"
                        ),
                        
                        # 各物理仓库的卡片清单
                        rx.cond(
                            InventoryState.warehouses.length() == 0,
                            empty_state("尚未创建任何实体物理仓库，请先在上方进行仓库开立。"),
                            rx.vstack(
                                rx.foreach(
                                    InventoryState.warehouses,
                                    render_warehouse_card
                                ),
                                spacing="4",
                                width="100%"
                            )
                        ),
                        spacing="4",
                        width="100%"
                    ),
                    value="warehouse",
                ),
                # ==== 选项卡 3：寄售管理 ====
                rx.tabs.content(
                    consignment_management_view(),
                    value="consignment",
                ),
                width="100%",
                value=InventoryState.active_tab,
                on_change=InventoryState.select_tab
            ),
            
            # 日志备注弹出 Dialog、超计划预警拦截 Dialog 及 寄售弹窗
            log_memo_dialog(),
            overproduction_warning_dialog(),
            consignment_edit_dialog(),
            consignment_add_dialog(),
            spacing="4",
            width="100%"
        ),
        title="仓库库存管理"
    )

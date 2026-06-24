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


def render_progress_row(row) -> rx.Component:
    """渲染商品款式进度条目。"""
    return rx.table.row(
        rx.table.cell(rx.text(rx.fragment("🎨 ", row.variant), size="1", weight="medium")),
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
        )
    )


def render_excess_row(row) -> rx.Component:
    """渲染散件条目。"""
    return rx.table.row(
        rx.table.cell(rx.text(row.variant, size="1")),
        rx.table.cell(rx.text(row.part_name, size="1")),
        rx.table.cell(rx.badge(row.qty.to_string(), color_scheme="orange", variant="solid"))
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
        rx.table.cell(rx.badge(row.reason, color_scheme="blue", variant="soft")),
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
            rx.grid(
                custom_form_field(
                    "变动日期",
                    rx.input(
                        type="date",
                        value=InventoryState.op_date,
                        on_change=InventoryState.set_op_date,
                        size="2"
                    )
                ),
                custom_form_field(
                    "变动操作类型",
                    rx.select.root(
    rx.select.trigger(),
    rx.select.content(
        rx.foreach(InventoryState.all_movement_types, lambda item: rx.select.item(item, value=item)),
        position="popper",
        side="bottom",
    ),
    value=InventoryState.op_type,
                        on_change=InventoryState.set_op_type,
                        size="2"
)
                ),
                columns="2",
                spacing="3",
                width="100%"
            ),
            rx.grid(
                rx.cond(
                    InventoryState.is_transfer_mode,
                    custom_form_field(
                        "移出仓库 (源库)",
                        rx.select.root(
    rx.select.trigger(),
    rx.select.content(
        rx.foreach(InventoryState.transfer_warehouse_options, lambda item: rx.select.item(item, value=item)),
        position="popper",
        side="bottom",
    ),
    value=InventoryState.op_wh_name,
                            on_change=InventoryState.set_op_wh_name,
                            size="2"
)
                    ),
                    custom_form_field(
                        "目标操作仓库",
                        rx.select.root(
    rx.select.trigger(),
    rx.select.content(
        rx.foreach(InventoryState.warehouse_options, lambda item: rx.select.item(item, value=item)),
        position="popper",
        side="bottom",
    ),
    value=InventoryState.op_wh_name,
                            on_change=InventoryState.set_op_wh_name,
                            size="2"
)
                    )
                ),
                rx.cond(
                    InventoryState.is_transfer_mode,
                    custom_form_field(
                        "移入仓库 (目的库)",
                        rx.select.root(
    rx.select.trigger(),
    rx.select.content(
        rx.foreach(InventoryState.warehouse_options, lambda item: rx.select.item(item, value=item)),
        position="popper",
        side="bottom",
    ),
    value=InventoryState.op_to_wh_name,
                            on_change=InventoryState.set_op_to_wh_name,
                            size="2"
)
                    ),
                    rx.fragment()
                ),
                columns="2",
                spacing="3",
                width="100%"
            ),
            rx.grid(
                custom_form_field(
                    "选择款式",
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
                    "变动套数/物理件数",
                    rx.input(
                        value=InventoryState.op_qty.to_string(),
                        on_change=InventoryState.set_op_qty,
                        type="number",
                        size="2"
                    )
                ),
                columns="2",
                spacing="3",
                width="100%"
            ),
            
            # 部件散件联动
            rx.cond(
                InventoryState.has_parts_for_color,
                rx.grid(
                    rx.hstack(
                        rx.switch(
                            checked=InventoryState.op_is_set,
                            on_change=InventoryState.set_op_is_set,
                            size="1",
                            color_scheme="violet"
                        ),
                        rx.text("整套动作 (款式所有部件同比例变动)", size="1", color=rx.color("slate", 10)),
                        spacing="2",
                        align="center",
                        padding_top="1.5rem"
                    ),
                    rx.cond(
                        InventoryState.op_is_set,
                        rx.fragment(),
                        custom_form_field(
                            "选择归属物理散件",
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
            
            # 出库特有消耗记账表单
            rx.cond(
                InventoryState.is_out_mode,
                rx.vstack(
                    custom_form_field(
                        "出库分类模式",
                        rx.radio(
                            ["消耗", "其他"],
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
                    spacing="3",
                    width="100%"
                ),
                rx.fragment()
            ),
            custom_form_field(
                "备注 (选填)",
                rx.input(
                    placeholder="操作补充备注",
                    value=InventoryState.op_remark,
                    on_change=InventoryState.set_op_remark,
                    size="2"
                )
            ),
            rx.button(
                "🚀 提交库存移动/盘点",
                on_click=InventoryState.submit_inventory_movement,
                color_scheme="violet",
                width="100%",
                size="3"
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
                                        rx.cond(
                                            InventoryState.logs.length() == 0,
                                            empty_state("该商品近期没有进行过入库或出库等物理变动操作。"),
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
                                                        InventoryState.logs,
                                                        render_log_row
                                                    )
                                                ),
                                                size="1",
                                                width="100%",
                                                variant="ghost"
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
                width="100%",
                value=InventoryState.active_tab,
                on_change=InventoryState.select_tab
            ),
            
            # 日志备注弹出 Dialog
            log_memo_dialog(),
            spacing="4",
            width="100%"
        ),
        title="仓库库存管理"
    )

# yurara_app/pages/cost.py
"""
商品成本核算视图层。
适配 Reflex 页面布局，搭载 HSL 渐变与现代高透玻璃拟态风格。
"""
import reflex as rx
from ..state.cost_state import CostState
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state, stat_card
from constants import PRODUCT_COST_CATEGORIES


def render_cost_row(row: dict) -> rx.Component:
    """渲染成本/预算单行，包含动作按钮。"""
    return rx.table.row(
        rx.table.cell(rx.text(row["item_name"], size="1", weight="medium")),
        rx.table.cell(rx.text(row["unit"], size="1")),
        rx.table.cell(rx.text(row["currency"], size="1")),
        
        # 预算
        rx.table.cell(rx.text(row["budget_qty_str"], size="1")),
        rx.table.cell(rx.text(row["budget_price_str"], size="1")),
        rx.table.cell(rx.text(row["budget_total_str"], size="1")),
        
        # 实际
        rx.table.cell(rx.text(row["actual_qty_str"], size="1")),
        rx.table.cell(rx.text(row["actual_price_str"], size="1")),
        rx.table.cell(rx.text(row["actual_total_str"], size="1")),
        
        rx.table.cell(rx.text(row["supplier"], size="1")),
        rx.table.cell(
            rx.cond(
                row["url"] != "",
                rx.link("🔗 访问", href=row["url"], is_external=True, size="1"),
                rx.text("-", size="1")
            )
        ),
        rx.table.cell(rx.text(row["remarks"], size="1")),
        rx.table.cell(
            rx.hstack(
                rx.icon_button(
                    rx.icon("pencil", size=13),
                    variant="ghost",
                    size="1",
                    on_click=CostState.open_edit_dialog(row)
                ),
                rx.icon_button(
                    rx.icon("trash_2", size=13),
                    variant="ghost",
                    size="1",
                    color_scheme="red",
                    on_click=CostState.delete_cost_item(row["id"])
                ),
                spacing="1"
            )
        )
    )


def render_category_section(cat: str) -> rx.Component:
    """分组别渲染支出明细表。"""
    headers = [
        "项目名称", "单位", "币种", 
        "预算数量", "预算单价", "预算总额", 
        "实际数量", "实付单价", "实付总额", 
        "供应商", "链接", "备注", "操作"
    ]
    
    # 小计值引用自 state
    sub_real = CostState.category_subtotals[cat]["real_str"]
    sub_real_unit = CostState.category_subtotals[cat]["real_unit_str"]
    sub_budget = CostState.category_subtotals[cat]["budget_str"]
    sub_budget_unit = CostState.category_subtotals[cat]["budget_unit_str"]

    return rx.cond(
        CostState.grouped_cost_items[cat].length() > 0,
        rx.vstack(
            rx.heading(f"🔹 {cat}", size="3", margin_top="1rem", color=rx.color("violet", 10)),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        *[rx.table.column_header_cell(h, size="1") for h in headers]
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        CostState.grouped_cost_items[cat],
                        render_cost_row
                    )
                ),
                size="1",
                width="100%",
                variant="ghost"
            ),
            # 小计条
            rx.grid(
                rx.hstack(rx.text("小计实付:", size="1", color=rx.color("slate", 10)), rx.text(sub_real, size="1", weight="bold")),
                rx.hstack(rx.text("实付单价:", size="1", color=rx.color("slate", 10)), rx.text(sub_real_unit, size="1", weight="bold")),
                rx.hstack(rx.text("小计预算:", size="1", color=rx.color("slate", 10)), rx.text(sub_budget, size="1", weight="bold")),
                rx.hstack(rx.text("预算单价:", size="1", color=rx.color("slate", 10)), rx.text(sub_budget_unit, size="1", weight="bold")),
                columns="4",
                spacing="2",
                width="100%",
                padding="0.5rem 0.75rem",
                background=rx.color("slate", 2),
                border_radius="6px"
            ),
            rx.divider(),
            spacing="2",
            width="100%"
        ),
        rx.fragment()
    )


def budget_form() -> rx.Component:
    """预算录入折叠表单"""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.hstack(
                rx.icon("plus", size=14),
                rx.text("添加预算项目 (Budget)", size="2"),
                spacing="1",
                align="center",
            ),
            content=rx.vstack(
                rx.text("在此处录入的条目仅作为预算参考，实付金额默认为0。", size="1", color=rx.color("white", 9)),
                rx.grid(
                    custom_form_field(
                        "预算分类",
                        rx.select(
                            CostState.all_categories,
                            value=CostState.b_cat,
                            on_change=CostState.set_b_cat,
                            size="2"
                        )
                    ),
                    custom_form_field(
                        "项目名称",
                        rx.input(
                            placeholder="如：面料预算",
                            value=CostState.b_name,
                            on_change=CostState.set_b_name,
                            size="2"
                        )
                    ),
                    columns="2",
                    spacing="3",
                    width="100%"
                ),
                rx.cond(
                    CostState.is_detailed_b_cat,
                    rx.grid(
                        custom_form_field(
                            "预算单价",
                            rx.input(
                                placeholder="0.00",
                                value=CostState.b_unit_price.to_string(),
                                on_change=CostState.set_b_unit_price,
                                type="number",
                                size="2"
                            )
                        ),
                        custom_form_field(
                            "预算数量",
                            rx.input(
                                value=CostState.b_qty.to_string(),
                                on_change=CostState.set_b_qty,
                                type="number",
                                size="2"
                            )
                        ),
                        custom_form_field(
                            "单位",
                            rx.input(
                                placeholder="米/个/套",
                                value=CostState.b_unit_text,
                                on_change=CostState.set_b_unit_text,
                                size="2"
                            )
                        ),
                        columns="3",
                        spacing="3",
                        width="100%"
                    ),
                    custom_form_field(
                        "预算总额 (简易项目)",
                        rx.input(
                            placeholder="0.00",
                            value=CostState.b_unit_price.to_string(),
                            on_change=CostState.set_b_unit_price,
                            type="number",
                            size="2"
                        )
                    )
                ),
                rx.cond(
                    CostState.is_detailed_b_cat,
                    rx.hstack(
                        rx.text("💰 预算总价:", size="1", color=rx.color("slate", 10)),
                        rx.text(CostState.budget_total_val_str, size="2", weight="bold", color=rx.color("violet", 11)),
                        spacing="1",
                        align="center"
                    ),
                    rx.fragment()
                ),
                custom_form_field(
                    "备注 (选填)",
                    rx.input(
                        placeholder="预算备注信息",
                        value=CostState.b_remarks,
                        on_change=CostState.set_b_remarks,
                        size="2"
                    )
                ),
                rx.button(
                    "保存预算",
                    on_click=CostState.add_budget_item,
                    color_scheme="violet",
                    size="2"
                ),
                spacing="3",
                padding_top="0.5rem"
            ),
            value="add-budget"
        ),
        collapsible=True,
        width="100%"
    )


def edit_dialog() -> rx.Component:
    """弹出式明细修改对话框。"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("⚙️ 编辑项目支出信息"),
            rx.dialog.description("修改选定项目的预算规格、备注或供应商资质。", size="1"),
            rx.vstack(
                custom_form_field(
                    "项目名称 (不可改)",
                    rx.input(
                        value=CostState.edit_name,
                        disabled=True,
                        size="2"
                    )
                ),
                rx.cond(
                    CostState.edit_is_budget,
                    rx.grid(
                        custom_form_field(
                            "预算单价",
                            rx.input(
                                value=CostState.edit_unit_price.to_string(),
                                on_change=CostState.set_edit_unit_price,
                                type="number",
                                size="2"
                            )
                        ),
                        custom_form_field(
                            "预算数量",
                            rx.input(
                                value=CostState.edit_qty.to_string(),
                                on_change=CostState.set_edit_qty,
                                type="number",
                                size="2"
                            )
                        ),
                        columns="2",
                        spacing="3",
                        width="100%"
                    ),
                    rx.fragment()
                ),
                rx.grid(
                    custom_form_field(
                        "物理单位",
                        rx.input(
                            placeholder="如：套/米",
                            value=CostState.edit_unit,
                            on_change=CostState.set_edit_unit,
                            size="2"
                        )
                    ),
                    custom_form_field(
                        "供应商",
                        rx.input(
                            placeholder="如：淘宝网",
                            value=CostState.edit_supplier,
                            on_change=CostState.set_edit_supplier,
                            size="2"
                        )
                    ),
                    columns="2",
                    spacing="3",
                    width="100%"
                ),
                custom_form_field(
                    "相关链接",
                    rx.input(
                        placeholder="如淘宝宝贝网址",
                        value=CostState.edit_url,
                        on_change=CostState.set_edit_url,
                        size="2"
                    )
                ),
                custom_form_field(
                    "说明备注",
                    rx.input(
                        value=CostState.edit_remarks,
                        on_change=CostState.set_edit_remarks,
                        size="2"
                    )
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=CostState.close_edit_dialog)
                    ),
                    rx.button("保存修改", on_click=CostState.submit_edit_cost_item, color_scheme="violet"),
                    spacing="3",
                    justify="end",
                    width="100%"
                ),
                spacing="3",
                width="100%",
                margin_top="1rem"
            ),
            max_width="450px"
        ),
        open=CostState.is_edit_open,
    )


def profit_matrix_table() -> rx.Component:
    """款式毛利对照大表"""
    return rx.cond(
        CostState.profit_references.length() == 0,
        empty_state("该商品暂未设置任何价格或预计销售数"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("款式", size="1"),
                    rx.table.column_header_cell("销售平台", size="1"),
                    rx.table.column_header_cell("平台定价", size="1"),
                    rx.table.column_header_cell("扣除手续费(CNY)", size="1"),
                    rx.table.column_header_cell("单件毛利", size="1"),
                    rx.table.column_header_cell("毛利率", size="1"),
                    rx.table.column_header_cell("预期款式总毛利", size="1"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    CostState.profit_references,
                    lambda r: rx.table.row(
                        rx.table.cell(rx.badge(r.color_name, color_scheme="violet")),
                        rx.table.cell(rx.text(r.platform_label, size="1")),
                        rx.table.cell(
                            rx.text(r.preset_price_str, size="1")
                        ),
                        rx.table.cell(rx.text(r.estimated_fee_cny_str, size="1")),
                        rx.table.cell(
                            rx.text(
                                r.margin_cny_str, 
                                size="1", 
                                color=rx.cond(r.margin_cny > 0, "green", "red"),
                                weight="bold"
                            )
                        ),
                        rx.table.cell(
                            rx.badge(
                                r.margin_rate_str,
                                color_scheme=rx.cond(r.margin_cny > 0, "green", "red"),
                                variant="soft"
                            )
                        ),
                        rx.table.cell(
                            rx.text(
                                r.expected_total_profit_str, 
                                size="1", 
                                weight="bold",
                                color=rx.cond(r.expected_total_profit > 0, "violet", "red")
                            )
                        ),
                    )
                )
            ),
            size="1",
            width="100%"
        )
    )


def cost_page() -> rx.Component:
    """成本核算总页面布局"""
    return page_layout(
        rx.vstack(
            # 顶部产品选择与新增面板
            rx.card(
                rx.hstack(
                    rx.text("请选择要核算的商品:", size="2", weight="medium"),
                    rx.select(
                        CostState.product_names,
                        value=CostState.selected_product_name,
                        on_change=CostState.select_product,
                        size="2",
                        width="200px"
                    ),
                    rx.spacer(),
                    rx.cond(
                        CostState.is_production_completed,
                        rx.badge("🔒 生产已结单", color_scheme="green", variant="soft"),
                        rx.badge("⚡ 在制流转中", color_scheme="orange", variant="soft")
                    ),
                    spacing="3",
                    align="center",
                    width="100%"
                ),
                width="100%",
                padding="1rem"
            ),
            
            # 预算展开表单
            budget_form(),
            rx.divider(),
            
            rx.cond(
                CostState.has_products,
                rx.vstack(
                    # 左右分栏核心表格
                    rx.grid(
                        # === 左栏：明细账表 ===
                        rx.vstack(
                            rx.heading("📋 项目支出明细表", size="4", weight="bold"),
                            data_card(
                                "费用流向细明",
                                rx.vstack(
                                    # 利用 compile-time list comprehension 生成静态页面元素，防 Reflex nested foreach 报错
                                    *[render_category_section(cat) for cat in PRODUCT_COST_CATEGORIES],
                                    spacing="4",
                                    width="100%"
                                )
                            ),
                            grid_column="span 8",
                            width="100%",
                            spacing="3"
                        ),
                        
                        # === 右栏：核算大盘与 WIP 结清 ===
                        rx.vstack(
                            rx.heading("📊 财务核算面板", size="4", weight="bold"),
                            
                            stat_card("项目总支出 (实付)", CostState.total_real_cost_str, icon="circle_dollar_sign", color_scheme="green"),
                            stat_card("项目预算总成本", CostState.total_budget_cost_str, icon="calculator", color_scheme="blue"),
                            stat_card("预计可销售总数", CostState.make_qty_str, icon="package", color_scheme="purple"),
                            stat_card("单套综合成本 (实付)", CostState.unit_real_cost_str, icon="piggy_bank", color_scheme="green"),
                            stat_card("预算单套成本", CostState.unit_budget_cost_str, icon="trending_up", color_scheme="blue"),
                            
                            # 在制资产 WIP 清算
                            rx.card(
                                rx.vstack(
                                    rx.heading("🛠️ 生产完成 / 清零在制资产", size="3"),
                                    rx.text(
                                        "⚠️ 功能说明：如果该商品已经生产完成，请点击下方按钮。此操作会将在制资产冲归大货资产，并根据已生产数量重算毛利。",
                                        size="1",
                                        color=rx.color("slate", 10)
                                    ),
                                    rx.divider(),
                                    rx.hstack(
                                        rx.text("当前在制资产 (WIP):", size="1", color=rx.color("slate", 10)),
                                        rx.text(CostState.remaining_wip_str, size="2", weight="bold", color=rx.color("orange", 11)),
                                        align="center",
                                        width="100%"
                                    ),
                                    rx.cond(
                                        CostState.is_production_completed,
                                        rx.vstack(
                                            rx.box(
                                                rx.text("✅ 已完成生产结单", weight="bold", color=rx.color("green", 11), size="2"),
                                                padding="0.5rem",
                                                background=rx.color("green", 3),
                                                border=f"1px solid {rx.color('green', 6)}",
                                                border_radius="6px",
                                                width="100%",
                                                text_align="center"
                                            ),
                                            rx.button(
                                                "🔄 重新计算大货单价与资产",
                                                color_scheme="violet",
                                                variant="soft",
                                                on_click=CostState.wip_completed_fix,
                                                width="100%"
                                            ),
                                            spacing="2",
                                            width="100%"
                                        ),
                                        rx.button(
                                            "🚀 生产完成 (清零在制)",
                                            color_scheme="red",
                                            on_click=CostState.wip_completed_fix,
                                            width="100%"
                                        )
                                    ),
                                    spacing="3",
                                    width="100%"
                                ),
                                width="100%",
                                padding="1rem"
                            ),
                            grid_column="span 4",
                            width="100%",
                            spacing="3"
                        ),
                        columns="12",
                        spacing="5",
                        width="100%",
                        align_items="start"
                    ),
                    
                    # === 底栏：款式毛利多平台对照大盘 ===
                    rx.vstack(
                        rx.heading("📈 款式定价与毛利参考 (基于实付)", size="4", weight="bold", margin_top="1rem"),
                        data_card(
                            "多平台毛利矩阵分析",
                            profit_matrix_table()
                        ),
                        width="100%",
                        spacing="3"
                    ),
                    width="100%",
                    spacing="5"
                ),
                rx.callout(
                    "请先在“商品管理”中添加商品，方可进行核算！",
                    icon="triangle_alert",
                    color_scheme="orange",
                    width="100%"
                )
            ),
            
            # 挂载编辑项目 Dialog
            edit_dialog(),
            spacing="4",
            width="100%"
        ),
        title="商品成本核算"
    )

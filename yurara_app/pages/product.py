# yurara_app/pages/product.py
"""
商品管理页面。三个 Tab：产品列表 / 新建产品 / 编辑产品。
"""
import reflex as rx
from ..state.auth_state import AuthState
from ..state.product_state import ProductState, PLATFORM_CODES, ColorRow, PartRow, ProductItem
from ..components.layout import page_layout
from ..components.editable_table import data_card, confirm_dialog, empty_state, form_field


# ===================== 可编辑行组件 =====================

def create_color_row(row: ColorRow) -> rx.Component:
    """新建模式：单行颜色规格输入。"""
    return rx.table.row(
        rx.table.cell(
            rx.input(
                default_value=row.name,
                placeholder="如：粉色",
                size="1",
                on_blur=lambda v: ProductState.update_create_color_field(row.key, "name", v),
                width="85px",
            ),
        ),
        rx.table.cell(
            rx.input(
                default_value=row.quantity.to_string(),
                type="number", size="1", min="0",
                on_blur=lambda v: ProductState.update_create_color_field(row.key, "quantity", v),
                width="65px",
            ),
        ),
        rx.table.cell(rx.input(default_value=row.price_weidian.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_create_color_field(row.key, "price_weidian", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_booth.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_create_color_field(row.key, "price_booth", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_offline_cn.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_create_color_field(row.key, "price_offline_cn", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_offline_jp.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_create_color_field(row.key, "price_offline_jp", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_instagram.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_create_color_field(row.key, "price_instagram", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_other.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_create_color_field(row.key, "price_other", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_other_jpy.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_create_color_field(row.key, "price_other_jpy", v), width="70px")),
        rx.table.cell(
            rx.icon_button(
                rx.icon("x", size=11),
                on_click=lambda: ProductState.remove_create_color_row(row.key),
                size="1", variant="ghost", color_scheme="red",
            ),
        ),
    )


def edit_color_row(row: ColorRow) -> rx.Component:
    """编辑模式：单行颜色规格输入。"""
    return rx.table.row(
        rx.table.cell(
            rx.input(
                default_value=row.name,
                placeholder="颜色名称", size="1",
                on_blur=lambda v: ProductState.update_edit_color_field(row.key, "name", v),
                width="85px",
            ),
        ),
        rx.table.cell(
            rx.input(
                default_value=row.quantity.to_string(),
                type="number", size="1", min="0",
                on_blur=lambda v: ProductState.update_edit_color_field(row.key, "quantity", v),
                width="65px",
            ),
        ),
        rx.table.cell(rx.input(default_value=row.price_weidian.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_edit_color_field(row.key, "price_weidian", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_booth.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_edit_color_field(row.key, "price_booth", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_offline_cn.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_edit_color_field(row.key, "price_offline_cn", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_offline_jp.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_edit_color_field(row.key, "price_offline_jp", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_instagram.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_edit_color_field(row.key, "price_instagram", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_other.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_edit_color_field(row.key, "price_other", v), width="70px")),
        rx.table.cell(rx.input(default_value=row.price_other_jpy.to_string(), type="number", size="1", min="0", on_blur=lambda v: ProductState.update_edit_color_field(row.key, "price_other_jpy", v), width="70px")),
        rx.table.cell(
            rx.icon_button(
                rx.icon("x", size=11),
                on_click=lambda: ProductState.remove_edit_color_row(row.key),
                size="1", variant="ghost", color_scheme="red",
            ),
        ),
    )


def create_part_row(row: PartRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.input(
                default_value=row.part_name,
                placeholder="如：外套",
                size="1",
                on_blur=lambda v: ProductState.update_create_part_field(row.key, "part_name", v),
                width="160px",
            ),
        ),
        rx.table.cell(
            rx.input(
                default_value=row.quantity.to_string(),
                type="number", size="1", min="1",
                on_blur=lambda v: ProductState.update_create_part_field(row.key, "quantity", v),
                width="60px",
            ),
        ),
        rx.table.cell(
            rx.icon_button(
                rx.icon("x", size=11),
                on_click=lambda: ProductState.remove_create_part_row(row.key),
                size="1", variant="ghost", color_scheme="red",
            ),
        ),
    )


def color_matrix_table_create() -> rx.Component:
    return rx.scroll_area(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("颜色", size="1"),
                    rx.table.column_header_cell("预计数量", size="1"),
                    rx.table.column_header_cell("微店", size="1"),
                    rx.table.column_header_cell("Booth", size="1"),
                    rx.table.column_header_cell("国内线下", size="1"),
                    rx.table.column_header_cell("日本线下", size="1"),
                    rx.table.column_header_cell("Instagram", size="1"),
                    rx.table.column_header_cell("其他CNY", size="1"),
                    rx.table.column_header_cell("其他JPY", size="1"),
                    rx.table.column_header_cell("", size="1"),
                )
            ),
            rx.table.body(rx.foreach(ProductState.create_color_rows, create_color_row)),
            size="1",
        ),
        overflow_x="auto", width="100%",
    )


def color_matrix_table_edit() -> rx.Component:
    return rx.scroll_area(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("颜色", size="1"),
                    rx.table.column_header_cell("库存/预计", size="1"),
                    rx.table.column_header_cell("微店", size="1"),
                    rx.table.column_header_cell("Booth", size="1"),
                    rx.table.column_header_cell("国内线下", size="1"),
                    rx.table.column_header_cell("日本线下", size="1"),
                    rx.table.column_header_cell("Instagram", size="1"),
                    rx.table.column_header_cell("其他CNY", size="1"),
                    rx.table.column_header_cell("其他JPY", size="1"),
                    rx.table.column_header_cell("", size="1"),
                )
            ),
            rx.table.body(rx.foreach(ProductState.edit_color_rows, edit_color_row)),
            size="1",
        ),
        overflow_x="auto", width="100%",
    )


# ===================== Tab: 新建产品 =====================

def create_tab() -> rx.Component:
    return rx.vstack(
        data_card(
            "基础信息",
            rx.grid(
                form_field(
                    "产品名称",
                    rx.input(
                        placeholder="如：水母睡裙",
                        value=ProductState.create_name,
                        on_change=ProductState.set_create_name,
                        size="2", width="100%",
                    ),
                    required=True,
                ),
                form_field(
                    "首发平台",
                    rx.select(
                        ProductState.platform_launch_options,
                        value=ProductState.create_platform,
                        on_change=ProductState.set_create_platform,
                        size="2", width="100%",
                    ),
                ),
                columns="2", spacing="4", width="100%",
            ),
        ),
        data_card(
            "规格与各平台定价",
            color_matrix_table_create(),
            rx.button(
                rx.icon("plus", size=12), "添加规格行",
                on_click=ProductState.add_create_color_row,
                size="1", variant="soft", margin_top="0.5rem",
            ),
        ),
        data_card(
            "款式部件设置（可选）",
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("部件名称", size="1"),
                        rx.table.column_header_cell("数量", size="1"),
                        rx.table.column_header_cell("", size="1"),
                    )
                ),
                rx.table.body(rx.foreach(ProductState.create_part_rows, create_part_row)),
                size="1", width="100%",
            ),
            rx.button(
                rx.icon("plus", size=12), "添加部件",
                on_click=ProductState.add_create_part_row,
                size="1", variant="soft", margin_top="0.5rem",
            ),
        ),
        rx.cond(
            ProductState.create_error != "",
            rx.callout(ProductState.create_error, icon="circle_x", color_scheme="red", size="1"),
            rx.fragment(),
        ),
        rx.button(
            rx.icon("save", size=14), "保存新产品",
            on_click=ProductState.save_create_product,
            size="3",
            style={"background": "linear-gradient(135deg, #6366f1, #8b5cf6)", "color": "white"},
            width="100%",
        ),
        spacing="4", width="100%",
    )


# ===================== Tab: 编辑产品 =====================

def edit_tab() -> rx.Component:
    return rx.cond(
        ProductState.edit_product_id == 0,
        rx.callout(
            "请先在【产品列表】中点击某个商品的【编辑】按钮。",
            icon="info", color_scheme="blue", size="2",
        ),
        rx.vstack(
            data_card(
                "基础信息",
                rx.grid(
                    form_field(
                        "产品名称",
                        rx.input(
                            value=ProductState.edit_name,
                            on_change=ProductState.set_edit_name,
                            size="2", width="100%",
                        ),
                        required=True,
                    ),
                    form_field(
                        "首发平台",
                        rx.select(
                            ProductState.platform_launch_options,
                            value=ProductState.edit_platform,
                            on_change=ProductState.set_edit_platform,
                            size="2", width="100%",
                        ),
                    ),
                    columns="2", spacing="4", width="100%",
                ),
            ),
            data_card(
                "规格与各平台定价",
                color_matrix_table_edit(),
                rx.button(
                    rx.icon("plus", size=12), "添加规格行",
                    on_click=ProductState.add_edit_color_row,
                    size="1", variant="soft", margin_top="0.5rem",
                ),
            ),
            rx.cond(
                ProductState.edit_error != "",
                rx.callout(ProductState.edit_error, icon="circle_x", color_scheme="red", size="1"),
                rx.fragment(),
            ),
            rx.button(
                rx.icon("save", size=14), "确认修改",
                on_click=ProductState.save_edit_product,
                size="3",
                style={"background": "linear-gradient(135deg, #6366f1, #8b5cf6)", "color": "white"},
                width="100%",
            ),
            spacing="4", width="100%",
        ),
    )


# ===================== Tab: 产品列表 =====================

def product_card(product: ProductItem) -> rx.Component:
    """
    产品卡片。
    """
    return rx.card(
        rx.vstack(
            # 标题行
            rx.hstack(
                rx.vstack(
                    rx.heading(product.name, size="4"),
                    rx.hstack(
                        rx.badge(product.platform, color_scheme="violet", variant="soft", size="1"),
                        rx.badge(
                            rx.fragment(product.total_quantity.to_string(), " 件"),
                            color_scheme="blue", variant="soft", size="1",
                        ),
                        spacing="2",
                    ),
                    spacing="1", align_items="start",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.button(
                        rx.icon("pencil", size=13), "编辑",
                        on_click=lambda: ProductState.load_edit_product(product.id),
                        size="1", variant="soft",
                    ),
                    confirm_dialog(
                        trigger=rx.button(
                            rx.icon("trash_2", size=13), "删除",
                            size="1", variant="soft", color_scheme="red",
                        ),
                        title="确认删除商品",
                        description="此操作将永久删除该商品及所有关联数据，无法撤销。",
                        confirm_label="确认删除",
                        on_confirm=lambda: ProductState.delete_product(product.id),
                        confirm_color="red",
                    ),
                    spacing="2",
                ),
                align="start", width="100%",
            ),

            # 颜色/规格摘要
            rx.text(
                product.color_summary,
                size="1",
                color=rx.color("slate", 10),
            ),

            # 定价简表（主要平台）
            rx.scroll_area(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("规格", size="1"),
                            rx.table.column_header_cell("数量", size="1"),
                            rx.table.column_header_cell("微店", size="1"),
                            rx.table.column_header_cell("Booth", size="1"),
                            rx.table.column_header_cell("国内线下", size="1"),
                            rx.table.column_header_cell("日本线下", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(product.color_rows, _product_color_table_row),
                    ),
                    size="1", width="100%",
                ),
                overflow_x="auto",
            ),

            spacing="3", width="100%",
        ),
        width="100%", padding="1.25rem",
    )


def _product_color_table_row(color: ColorRow) -> rx.Component:
    """产品列表里的颜色定价行。"""
    return rx.table.row(
        rx.table.cell(rx.text(color.name, size="1", weight="medium")),
        rx.table.cell(rx.text(color.quantity.to_string(), size="1")),
        rx.table.cell(rx.cond(color.price_weidian > 0, rx.text(color.price_weidian.to_string(), size="1"), rx.text("-", size="1", color=rx.color("slate", 8)))),
        rx.table.cell(rx.cond(color.price_booth > 0, rx.text(color.price_booth.to_string(), size="1"), rx.text("-", size="1", color=rx.color("slate", 8)))),
        rx.table.cell(rx.cond(color.price_offline_cn > 0, rx.text(color.price_offline_cn.to_string(), size="1"), rx.text("-", size="1", color=rx.color("slate", 8)))),
        rx.table.cell(rx.cond(color.price_offline_jp > 0, rx.text(color.price_offline_jp.to_string(), size="1"), rx.text("-", size="1", color=rx.color("slate", 8)))),
    )


def list_tab() -> rx.Component:
    return rx.vstack(
        rx.cond(
            ProductState.is_loading,
            rx.center(rx.spinner(size="3"), padding="3rem"),
            rx.cond(
                ProductState.has_products,
                rx.vstack(
                    rx.foreach(ProductState.products, product_card),
                    spacing="3", width="100%",
                ),
                empty_state("暂无产品，请点击「新建产品」添加", "package"),
            ),
        ),
        width="100%",
    )


# ===================== 主页面 =====================

def product_page() -> rx.Component:
    return page_layout(
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger(
                    rx.hstack(rx.icon("list", size=13), rx.text("产品列表"), spacing="1"),
                    value="list",
                ),
                rx.tabs.trigger(
                    rx.hstack(rx.icon("circle_plus", size=13), rx.text("新建产品"), spacing="1"),
                    value="create",
                    on_click=ProductState.init_create_form,
                ),
                rx.tabs.trigger(
                    rx.hstack(rx.icon("pencil", size=13), rx.text("编辑产品"), spacing="1"),
                    value="edit",
                ),
                size="2",
            ),
            rx.tabs.content(list_tab(), value="list", padding_top="1.5rem"),
            rx.tabs.content(create_tab(), value="create", padding_top="1.5rem"),
            rx.tabs.content(edit_tab(), value="edit", padding_top="1.5rem"),
            default_value="list",
            value=ProductState.active_tab,
        ),
        title="商品管理",
    )

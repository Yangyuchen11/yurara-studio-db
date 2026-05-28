# yurara_app/pages/product.py
"""
商品管理页面。
三个 Tab：产品列表 / 新建产品 / 编辑产品。
"""
import reflex as rx
from ..state.auth_state import AuthState
from ..state.product_state import ProductState, ColorRow, PartRow
from ..components.layout import page_layout
from ..components.editable_table import (
    data_card, confirm_dialog, empty_state, form_field
)
from constants import PLATFORM_CODES


# ===================== 子组件 =====================

def price_input_row(row: ColorRow) -> rx.Component:
    """颜色行：名称 + 数量 + 各平台价格 + 删除按钮。"""
    return rx.table.row(
        # 颜色名称
        rx.table.cell(
            rx.input(
                default_value=row.name,
                placeholder="如：粉色",
                size="1",
                on_blur=lambda v: ProductState.update_create_color_field(row.key, "name", v),
                width="90px",
            ),
        ),
        # 预计数量
        rx.table.cell(
            rx.input(
                default_value=row.quantity.to_string(),
                type="number",
                size="1",
                on_blur=lambda v: ProductState.update_create_color_field(row.key, "quantity", v),
                width="70px",
            ),
        ),
        # 各平台价格
        *[
            rx.table.cell(
                rx.input(
                    default_value=row.prices[pf_key].to_string(),
                    type="number",
                    size="1",
                    on_blur=lambda v, k=pf_key: ProductState.update_create_color_field(
                        row.key, f"price_{k}", v
                    ),
                    width="80px",
                ),
            )
            for pf_key in PLATFORM_CODES.keys()
        ],
        # 图片上传
        rx.table.cell(
            rx.cond(
                row.image_data != "",
                rx.image(src=row.image_data, width="32px", height="32px", border_radius="4px"),
                rx.upload(
                    rx.icon_button(rx.icon("image-plus", size=12), size="1", variant="ghost"),
                    id=f"img_upload_{row.key}",
                    accept={"image/*": [".png", ".jpg", ".jpeg"]},
                    on_upload=lambda files: ProductState.upload_create_color_image(row.key, files),
                    max_files=1,
                ),
            ),
        ),
        # 删除行
        rx.table.cell(
            rx.icon_button(
                rx.icon("trash-2", size=12),
                on_click=lambda: ProductState.remove_create_color_row(row.key),
                size="1",
                variant="ghost",
                color_scheme="red",
            ),
        ),
    )


def edit_price_input_row(row: ColorRow) -> rx.Component:
    """编辑模式颜色行。"""
    return rx.table.row(
        rx.table.cell(
            rx.input(
                default_value=row.name,
                placeholder="颜色名称",
                size="1",
                on_blur=lambda v: ProductState.update_edit_color_field(row.key, "name", v),
                width="90px",
            ),
        ),
        rx.table.cell(
            rx.input(
                default_value=row.quantity.to_string(),
                type="number",
                size="1",
                on_blur=lambda v: ProductState.update_edit_color_field(row.key, "quantity", v),
                width="70px",
            ),
        ),
        *[
            rx.table.cell(
                rx.input(
                    default_value=row.prices[pf_key].to_string(),
                    type="number",
                    size="1",
                    on_blur=lambda v, k=pf_key: ProductState.update_edit_color_field(
                        row.key, f"price_{k}", v
                    ),
                    width="80px",
                ),
            )
            for pf_key in PLATFORM_CODES.keys()
        ],
        rx.table.cell(
            rx.cond(
                row.image_data != "",
                rx.image(src=row.image_data, width="32px", height="32px", border_radius="4px"),
                rx.text("-", size="1", color=rx.color("slate", 9)),
            ),
        ),
        rx.table.cell(
            rx.icon_button(
                rx.icon("trash-2", size=12),
                on_click=lambda: ProductState.remove_edit_color_row(row.key),
                size="1",
                variant="ghost",
                color_scheme="red",
            ),
        ),
    )


def part_input_row_create(row: PartRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.input(
                default_value=row.part_name,
                placeholder="如：外套、裙子",
                size="1",
                on_blur=lambda v: ProductState.update_create_part_field(row.key, "part_name", v),
                width="150px",
            ),
        ),
        rx.table.cell(
            rx.input(
                default_value=row.quantity.to_string(),
                type="number",
                size="1",
                on_blur=lambda v: ProductState.update_create_part_field(row.key, "quantity", v),
                width="60px",
            ),
        ),
        rx.table.cell(
            rx.icon_button(
                rx.icon("trash-2", size=12),
                on_click=lambda: ProductState.remove_create_part_row(row.key),
                size="1",
                variant="ghost",
                color_scheme="red",
            ),
        ),
    )


def color_rows_table(rows, is_edit: bool = False) -> rx.Component:
    """颜色/规格矩阵表格（带平台价格列）。"""
    platform_headers = [v for v in PLATFORM_CODES.values()]
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("颜色名称", size="1"),
                rx.table.column_header_cell("预计数量", size="1"),
                *[rx.table.column_header_cell(h, size="1") for h in platform_headers],
                rx.table.column_header_cell("缩略图", size="1"),
                rx.table.column_header_cell("", size="1"),
            )
        ),
        rx.table.body(
            rx.foreach(
                rows,
                edit_price_input_row if is_edit else price_input_row,
            )
        ),
        width="100%",
        size="1",
    )


def parts_table(rows, is_edit: bool = False) -> rx.Component:
    """部件表格。"""
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("部件名称", size="1"),
                rx.table.column_header_cell("数量", size="1"),
                rx.table.column_header_cell("", size="1"),
            )
        ),
        rx.table.body(
            rx.foreach(rows, part_input_row_create),
        ),
        width="100%",
        size="1",
    )


# ===================== Tab 内容 =====================

def create_tab() -> rx.Component:
    """新建产品 Tab。"""
    return rx.vstack(
        # 基础信息
        data_card(
            "基础信息",
            rx.grid(
                form_field(
                    "产品名称",
                    rx.input(
                        placeholder="如：水母睡裙",
                        value=ProductState.create_name,
                        on_change=ProductState.set_create_name,
                        size="2",
                        width="100%",
                    ),
                    required=True,
                ),
                form_field(
                    "首发平台",
                    rx.select(
                        ProductState.platform_launch_options,
                        value=ProductState.create_platform,
                        on_change=ProductState.set_create_platform,
                        size="2",
                        width="100%",
                    ),
                ),
                columns="2",
                spacing="4",
                width="100%",
            ),
        ),

        # 颜色规格矩阵
        data_card(
            "规格与各平台定价",
            color_rows_table(ProductState.create_color_rows),
            rx.button(
                rx.icon("plus", size=12),
                "添加规格行",
                on_click=ProductState.add_create_color_row,
                size="1",
                variant="soft",
                margin_top="0.5rem",
            ),
        ),

        # 部件设置
        data_card(
            "款式部件设置（可选）",
            parts_table(ProductState.create_part_rows),
            rx.button(
                rx.icon("plus", size=12),
                "添加部件",
                on_click=ProductState.add_create_part_row,
                size="1",
                variant="soft",
                margin_top="0.5rem",
            ),
        ),

        # 错误提示
        rx.cond(
            ProductState.create_error != "",
            rx.callout(ProductState.create_error, icon="circle-x", color_scheme="red", size="1"),
            rx.fragment(),
        ),

        # 提交按钮
        rx.button(
            rx.icon("save", size=14),
            "保存新产品",
            on_click=ProductState.save_create_product,
            size="3",
            background="linear-gradient(135deg, #6366f1, #8b5cf6)",
            color="white",
            width="100%",
        ),

        spacing="4",
        width="100%",
    )


def edit_tab() -> rx.Component:
    """编辑产品 Tab。"""
    return rx.cond(
        ProductState.edit_product_id == 0,
        rx.callout(
            "请先在【产品列表】中点击某个商品的【编辑】按钮。",
            icon="info",
            color_scheme="blue",
            size="2",
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
                            size="2",
                            width="100%",
                        ),
                        required=True,
                    ),
                    form_field(
                        "首发平台",
                        rx.select(
                            ProductState.platform_launch_options,
                            value=ProductState.edit_platform,
                            on_change=ProductState.set_edit_platform,
                            size="2",
                            width="100%",
                        ),
                    ),
                    columns="2",
                    spacing="4",
                    width="100%",
                ),
            ),
            data_card(
                "规格与各平台定价",
                color_rows_table(ProductState.edit_color_rows, is_edit=True),
                rx.button(
                    rx.icon("plus", size=12),
                    "添加规格行",
                    on_click=ProductState.add_edit_color_row,
                    size="1",
                    variant="soft",
                    margin_top="0.5rem",
                ),
            ),
            rx.cond(
                ProductState.edit_error != "",
                rx.callout(ProductState.edit_error, icon="circle-x", color_scheme="red", size="1"),
                rx.fragment(),
            ),
            rx.button(
                rx.icon("save", size=14),
                "确认修改",
                on_click=ProductState.save_edit_product,
                size="3",
                background="linear-gradient(135deg, #6366f1, #8b5cf6)",
                color="white",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
    )


def product_card(product) -> rx.Component:
    """单个产品展示卡片。"""
    return rx.card(
        rx.vstack(
            # 标题行
            rx.hstack(
                rx.vstack(
                    rx.heading(product.name, size="4"),
                    rx.hstack(
                        rx.badge(product.platform, color_scheme="violet", variant="soft", size="1"),
                        rx.badge(
                            f"制作 {product.total_quantity} 件",
                            color_scheme="blue",
                            variant="soft",
                            size="1",
                        ),
                        spacing="2",
                    ),
                    spacing="1",
                    align_items="start",
                ),
                rx.spacer(),
                # 操作按钮
                rx.hstack(
                    rx.button(
                        rx.icon("pencil", size=13),
                        "编辑",
                        on_click=lambda: ProductState.load_edit_product(product.id),
                        size="1",
                        variant="soft",
                    ),
                    confirm_dialog(
                        trigger=rx.button(
                            rx.icon("trash-2", size=13),
                            "删除",
                            size="1",
                            variant="soft",
                            color_scheme="red",
                        ),
                        title=f"确认删除商品",
                        description=f"此操作将永久删除该商品及其所有关联数据（颜色、价格、部件），无法撤销。",
                        confirm_label="确认删除",
                        on_confirm=lambda: ProductState.delete_product(product.id),
                        confirm_color="red",
                    ),
                    spacing="2",
                ),
                align="start",
                width="100%",
            ),

            # 颜色缩略图行
            rx.hstack(
                rx.foreach(
                    product.colors,
                    lambda c: rx.cond(
                        c.image_data != "",
                        rx.vstack(
                            rx.image(
                                src=c.image_data,
                                width="48px",
                                height="48px",
                                border_radius="6px",
                                object_fit="cover",
                            ),
                            rx.text(c.name, size="1", color=rx.color("slate", 10)),
                            spacing="1",
                            align="center",
                        ),
                        rx.fragment(),
                    ),
                ),
                spacing="2",
                wrap="wrap",
            ),

            # 定价简表
            rx.scroll_area(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("规格", size="1"),
                            rx.table.column_header_cell("库存/预计", size="1"),
                            *[
                                rx.table.column_header_cell(v, size="1")
                                for v in PLATFORM_CODES.values()
                            ],
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            product.colors,
                            lambda c: rx.table.row(
                                rx.table.cell(rx.text(c.name, size="1")),
                                rx.table.cell(rx.text(c.quantity.to_string(), size="1")),
                                *[
                                    rx.table.cell(
                                        rx.foreach(
                                            c.prices,
                                            lambda pr, k=pf_key: rx.cond(
                                                pr.platform == k,
                                                rx.text(
                                                    rx.cond(pr.price > 0, f"¥{pr.price}", "-"),
                                                    size="1",
                                                ),
                                                rx.fragment(),
                                            ),
                                        )
                                    )
                                    for pf_key in PLATFORM_CODES.keys()
                                ],
                            ),
                        )
                    ),
                    size="1",
                    width="100%",
                ),
                overflow_x="auto",
            ),

            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="1.25rem",
    )


def list_tab() -> rx.Component:
    """产品列表 Tab。"""
    return rx.vstack(
        rx.cond(
            ProductState.is_loading,
            rx.center(rx.spinner(size="3"), padding="3rem"),
            rx.cond(
                ProductState.has_products,
                rx.vstack(
                    rx.foreach(ProductState.products, product_card),
                    spacing="3",
                    width="100%",
                ),
                empty_state("暂无产品，请点击「新建产品」添加", "package"),
            ),
        ),
        width="100%",
    )


# ===================== 主页面函数 =====================

def product_page() -> rx.Component:
    return page_layout(
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger(
                    rx.hstack(rx.icon("list", size=13), rx.text("产品列表"), spacing="1"),
                    value="list",
                ),
                rx.tabs.trigger(
                    rx.hstack(rx.icon("plus-circle", size=13), rx.text("新建产品"), spacing="1"),
                    value="create",
                    on_click=ProductState.init_create_form,
                ),
                rx.tabs.trigger(
                    rx.hstack(rx.icon("pencil", size=13), rx.text("编辑产品"), spacing="1"),
                    value="edit",
                ),
                size="2",
            ),
            rx.tabs.content(
                list_tab(),
                value="list",
                padding_top="1.5rem",
            ),
            rx.tabs.content(
                create_tab(),
                value="create",
                padding_top="1.5rem",
            ),
            rx.tabs.content(
                edit_tab(),
                value="edit",
                padding_top="1.5rem",
            ),
            default_value="list",
            value=ProductState.active_tab,
            on_change=ProductState.switch_tab,
            width="100%",
        ),
        title="商品管理",
        subtitle="管理所有产品信息、规格定价和款式图片",
        on_load=[AuthState.check_auth, ProductState.load_products],
    )

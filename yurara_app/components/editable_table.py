# yurara_app/components/editable_table.py
"""
表单驱动的可编辑列表组件（替代 st.data_editor）。

使用模式：
1. 在对应的 State 中维护一个 list[dict] 状态作为数据源
2. 使用 editable_list() 渲染表格 + 新增行表单
3. 通过 State 的 event handler 处理行的增删改
"""
import reflex as rx
from typing import Any


def data_card(
    title: str,
    *content,
    action_button: rx.Component | None = None,
) -> rx.Component:
    """
    带标题和可选操作按钮的卡片容器。
    用于包裹可编辑列表或任何数据内容块。
    """
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text(title, weight="bold", size="3"),
                rx.spacer(),
                action_button or rx.fragment(),
                width="100%",
                align="center",
            ),
            rx.divider(),
            *content,
            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="1.25rem",
    )


def stat_card(
    label: str,
    value: Any,
    unit: str = "",
    color_scheme: str = "violet",
    icon: str = "circle",
) -> rx.Component:
    """统计数字卡片，用于仪表盘类展示。"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=16, color=rx.color(color_scheme, 9)),
                rx.text(label, size="1", color=rx.color("slate", 10)),
                spacing="1",
                align="center",
            ),
            rx.hstack(
                rx.text(value, size="6", weight="bold"),
                rx.text(unit, size="2", color=rx.color("slate", 10), margin_top="auto"),
                spacing="1",
                align="end",
            ),
            spacing="2",
            align_items="start",
        ),
        padding="1rem",
        width="100%",
    )


def empty_state(message: str = "暂无数据", icon: str = "inbox") -> rx.Component:
    """空状态占位组件。"""
    return rx.vstack(
        rx.icon(icon, size=40, color=rx.color("slate", 6)),
        rx.text(message, size="2", color=rx.color("slate", 10)),
        spacing="2",
        align="center",
        padding="3rem",
        width="100%",
    )


def confirm_dialog(
    trigger: rx.Component,
    title: str,
    description: str,
    confirm_label: str,
    on_confirm,
    confirm_color: str = "red",
) -> rx.Component:
    """
    确认对话框组件，用于危险操作（删除等）的二次确认。
    """
    return rx.alert_dialog.root(
        rx.alert_dialog.trigger(trigger),
        rx.alert_dialog.content(
            rx.alert_dialog.title(title),
            rx.alert_dialog.description(description, size="2"),
            rx.flex(
                rx.alert_dialog.cancel(
                    rx.button("取消", variant="soft", color_scheme="gray"),
                ),
                rx.alert_dialog.action(
                    rx.button(
                        confirm_label,
                        color_scheme=confirm_color,
                        on_click=on_confirm,
                    ),
                ),
                spacing="3",
                margin_top="1rem",
                justify="end",
            ),
        ),
    )


def form_field(
    label: str,
    *inputs,
    required: bool = False,
    helper: str = "",
) -> rx.Component:
    """
    表单字段包装器，提供统一的 label + input + helper text 布局。
    """
    return rx.form.field(
        rx.vstack(
            rx.hstack(
                rx.form.label(
                    label,
                    rx.cond(required, rx.text(" *", color="red", as_="span"), rx.fragment()),
                    size="2",
                    weight="medium",
                ),
                spacing="0",
            ),
            *inputs,
            rx.cond(
                helper != "",
                rx.text(helper, size="1", color=rx.color("slate", 10)),
                rx.fragment(),
            ),
            spacing="1",
            align_items="start",
            width="100%",
        ),
        width="100%",
    )


def inline_list_table(
    headers: list[str],
    rows: list,
    render_row,
    empty_message: str = "暂无数据",
) -> rx.Component:
    """
    通用只读列表表格，用于展示已录入的行数据。

    参数：
        headers: 表头列表
        rows: 数据行列表（响应式状态变量）
        render_row: 渲染每行的函数，接受一个 row 参数
        empty_message: 空状态提示文字
    """
    return rx.cond(
        rx.Var.create(len(rows) == 0),  # 空状态判断
        empty_state(empty_message),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    *[
                        rx.table.column_header_cell(h, weight="medium", size="1")
                        for h in headers
                    ]
                )
            ),
            rx.table.body(
                rx.foreach(rows, render_row),
            ),
            width="100%",
            size="1",
        ),
    )


def editable_list(
    title: str,
    add_form: rx.Component,
    table: rx.Component,
    is_expanded: bool = True,
) -> rx.Component:
    """
    组合组件：标题 + 已有记录表格 + 添加新记录的表单。
    这是 st.data_editor 的 Reflex 等价替代。

    参数：
        title: 区域标题
        add_form: 新增行的表单组件
        table: 显示当前所有行的表格组件
        is_expanded: 是否默认展开新增表单
    """
    return rx.vstack(
        # 已有记录区域
        data_card(title, table),

        # 新增记录展开区
        rx.accordion.root(
            rx.accordion.item(
                header=rx.hstack(
                    rx.icon("plus", size=14),
                    rx.text("添加新记录", size="2"),
                    spacing="1",
                    align="center",
                ),
                content=rx.box(
                    add_form,
                    padding="0.5rem 0",
                ),
                value="add-form",
            ),
            default_value="add-form" if is_expanded else "",
            collapsible=True,
            width="100%",
        ),

        spacing="3",
        width="100%",
    )

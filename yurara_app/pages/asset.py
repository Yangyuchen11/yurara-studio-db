# yurara_app/pages/asset.py
"""
固定资产管理页面。
包含采购总值、剩余价值及日元原币高亮卡片，支持弹出对话框编辑，以及便捷资产核销与记录表格。
"""
import reflex as rx
from ..state.asset_state import AssetState, AssetItem, AssetLogItem
from ..components.layout import page_layout
from ..components.editable_table import data_card, form_field, empty_state


def asset_metric_card(label: str, value: rx.Var, description: str, icon: str, color_scheme: str = "violet") -> rx.Component:
    """高亮指标卡片，包含左侧亮色条和悬浮提示信息"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=16, color=rx.color(color_scheme, 9)),
                rx.text(label, size="1", color=rx.color("slate", 10), weight="medium"),
                rx.tooltip(
                    rx.icon("circle_help", size=12, color=rx.color("slate", 7)),
                    content=description
                ),
                spacing="2",
                align="center",
            ),
            rx.text(value, size="5", weight="bold", color=rx.color(color_scheme, 11)),
            spacing="1",
            align_items="start",
            width="100%"
        ),
        width="100%",
        padding="0.75rem",
        style={"border_left": f"4px solid {rx.color(color_scheme, 9)}"}
    )


def edit_asset_dialog() -> rx.Component:
    """弹出式资产编辑表单"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(rx.fragment("⚙️ 编辑资产: ", AssetState.edit_name), size="3"),
            rx.dialog.description(
                "在此修改该项固定资产的采购店铺来源、网址链接或补充备注。",
                size="1",
                color=rx.color("slate", 9),
                margin_bottom="1rem"
            ),
            rx.vstack(
                form_field("店名 / 来源 (必填)", rx.input(value=AssetState.edit_shop_name, on_change=AssetState.set_edit_shop_name, size="2")),
                form_field("相关链接 / 网址", rx.input(value=AssetState.edit_url, on_change=AssetState.set_edit_url, size="2")),
                form_field("备注说明", rx.input(value=AssetState.edit_remarks, on_change=AssetState.set_edit_remarks, size="2")),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("取消", variant="soft", color_scheme="gray", on_click=AssetState.close_edit_dialog)
                    ),
                    rx.button("保存修改", on_click=AssetState.submit_edit_asset, color_scheme="violet"),
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
        open=AssetState.is_edit_open,
        on_open_change=lambda _: AssetState.close_edit_dialog()
    )


def asset_write_off_card() -> rx.Component:
    """资产核销操作板块"""
    return rx.card(
        rx.vstack(
            rx.heading("📉 资产核销/报废", size="3", weight="bold"),
            rx.text("对已损坏、丢失或产生物理折旧折旧的固定资产进行核销处理。", size="1", color=rx.color("slate", 9)),
            rx.cond(
                AssetState.active_assets_options.length() == 0,
                rx.callout("ℹ️ 当前没有可核销的资产 (剩余数量均为 0)", icon="info", color_scheme="blue", size="1", width="100%"),
                rx.vstack(
                    rx.grid(
                        form_field(
                            "选择要核销的资产",
                            rx.select.root(
                                rx.select.trigger(),
                                rx.select.content(
                                    rx.foreach(
                                        AssetState.active_assets_options,
                                        lambda opt: rx.select.item(opt["label"], value=opt["value"])
                                    )
                                ),
                                placeholder="选择资产...",
                                value=AssetState.write_off_asset_id,
                                on_change=AssetState.on_select_write_off_asset,
                                size="2"
                            )
                        ),
                        form_field(
                            "核销数量",
                            rx.input(
                                type="number",
                                value=AssetState.write_off_qty.to_string(),
                                on_change=lambda v: AssetState.set_write_off_qty(rx.cond(v != "", v.to(float), 1.0)),
                                size="2"
                            )
                        ),
                        form_field(
                            "核销原因 (必填)",
                            rx.input(
                                placeholder="如：损坏、折旧、丢失",
                                value=AssetState.write_off_reason,
                                on_change=AssetState.set_write_off_reason,
                                size="2"
                            )
                        ),
                        columns="3",
                        spacing="4",
                        width="100%"
                    ),
                    rx.button(
                        rx.icon("check_check", size=13),
                        "确认执行核销",
                        on_click=AssetState.submit_write_off,
                        color_scheme="red",
                        size="2",
                        width="100%"
                    ),
                    spacing="3",
                    width="100%"
                )
            ),
            spacing="3",
            width="100%"
        ),
        padding="0.75rem",
        width="100%"
    )


def asset_logs_table() -> rx.Component:
    """固定资产核销日志表格"""
    return rx.cond(
        AssetState.logs.length() == 0,
        empty_state("暂无相关固定资产核销或折旧流水记录"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("日期", size="1"),
                    rx.table.column_header_cell("资产名称", size="1"),
                    rx.table.column_header_cell("核销数量", size="1"),
                    rx.table.column_header_cell("原因说明", size="1"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    AssetState.logs,
                    lambda l: rx.table.row(
                        rx.table.cell(rx.text(l.date, size="1")),
                        rx.table.cell(rx.text(l.asset_name, size="1", weight="medium")),
                        rx.table.cell(rx.badge(rx.fragment("-", l.decrease_qty.to_string()), color_scheme="red", size="1")),
                        rx.table.cell(rx.text(l.reason, size="1")),
                    )
                )
            ),
            size="1",
            width="100%"
        )
    )


def render_asset_row(a: AssetItem) -> rx.Component:
    """渲染表格的单行"""
    return rx.table.row(
        rx.table.cell(rx.text(a.name, size="1", weight="bold")),
        rx.table.cell(rx.text(a.currency, size="1")),
        rx.table.cell(rx.text(a.unit_price.to_string(), size="1")),
        rx.table.cell(rx.text(a.quantity.to_string(), size="1")),
        rx.table.cell(rx.badge(a.remaining_qty.to_string(), color_scheme=rx.cond(a.remaining_qty > 0, "green", "gray"), size="1")),
        rx.table.cell(rx.text(a.total_price.to_string(), size="1")),
        rx.table.cell(rx.text(rx.cond(a.remaining_cny > 0.001, a.remaining_cny.to_string(), "-"), size="1")),
        rx.table.cell(rx.text(rx.cond(a.remaining_jpy > 0.001, a.remaining_jpy.to_string(), "-"), size="1")),
        rx.table.cell(rx.text(a.shop_name, size="1")),
        rx.table.cell(
            rx.cond(
                a.url != "",
                rx.link(
                    rx.badge(rx.icon("link", size=10), "访问", color_scheme="violet", variant="soft", size="1"),
                    href=a.url,
                    is_external=True
                ),
                rx.text("-", size="1", color=rx.color("slate", 7))
            )
        ),
        rx.table.cell(rx.text(a.remarks, size="1", line_clamp=1)),
        rx.table.cell(
            rx.icon_button(
                rx.icon("pencil", size=11),
                on_click=lambda: AssetState.open_edit_dialog(a),
                size="1",
                variant="ghost"
            )
        )
    )


def asset_list_table() -> rx.Component:
    """固定资产管理主表格"""
    return rx.cond(
        ~AssetState.has_assets,
        empty_state("暂无固定资产数据。请在【财务流水账】中录入‘固定资产购入’。"),
        rx.vstack(
            rx.scroll_area(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("项目", size="1"),
                            rx.table.column_header_cell("币种", size="1"),
                            rx.table.column_header_cell("单价(原币)", size="1"),
                            rx.table.column_header_cell("初始数量", size="1"),
                            rx.table.column_header_cell("剩余数量", size="1"),
                            rx.table.column_header_cell("总价(原币)", size="1"),
                            rx.table.column_header_cell("剩余价值(CNY)", size="1"),
                            rx.table.column_header_cell("剩余价值(JPY)", size="1"),
                            rx.table.column_header_cell("店铺", size="1"),
                            rx.table.column_header_cell("链接", size="1"),
                            rx.table.column_header_cell("备注", size="1"),
                            rx.table.column_header_cell("操作", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(AssetState.assets, render_asset_row)
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


def asset_page() -> rx.Component:
    """固定资产管理主页面入口"""
    return page_layout(
        rx.vstack(
            # 顶部统计指标卡片
            rx.grid(
                asset_metric_card("资产采购历史总值 (折合)", AssetState.val_total_str, "所有采购固定资产的历史金额以当前汇率折合为 CNY 的总和", "banknote", "violet"),
                asset_metric_card("当前剩余价值 (折合)", AssetState.val_remain_str, "所有在库/未报废资产按当前汇率折算为 CNY 的总和", "trending_up", "green"),
                asset_metric_card("其中日元资产原值", AssetState.val_jpy_raw_str, "仅统计以 JPY 计价的资产日元原值部分", "japanese_yen", "blue"),
                columns="3",
                spacing="3",
                width="100%"
            ),
            
            # 主清单表格
            data_card(
                "📋 固定资产清单",
                asset_list_table()
            ),
            
            # 核销报废与核销日志
            rx.grid(
                asset_write_off_card(),
                data_card(
                    "📜 固定资产核销记录",
                    asset_logs_table()
                ),
                columns="2",
                spacing="4",
                width="100%",
                align_items="start"
            ),
            
            # 编辑详情弹窗
            edit_asset_dialog(),
            
            spacing="4",
            width="100%"
        ),
        title="🏢 固定资产管理"
    )

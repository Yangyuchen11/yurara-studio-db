# yurara_app/pages/platforms.py
"""
销售平台管理视图。
支持添加平台代号、平台显示名称、结算币种及手续费费率设定，并提供列表清单和删除功能。
"""
import reflex as rx
from ..state.platforms_state import PlatformsState, PlatformDisplayItem
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state, confirm_dialog

def render_platform_row(p: PlatformDisplayItem) -> rx.Component:
    """渲染单个销售平台的行"""
    return rx.table.row(
        rx.table.cell(rx.text(p.code, size="1", weight="bold", color=rx.color("violet", 10))),
        rx.table.cell(rx.text(p.name, size="1", weight="medium")),
        rx.table.cell(rx.badge(p.currency, color_scheme="blue", variant="soft", size="1")),
        rx.table.cell(rx.text(p.fee_rate_pct_str, size="1")),
        rx.table.cell(rx.text(p.fee_fixed.to_string(), size="1")),
        rx.table.cell(
            confirm_dialog(
                trigger=rx.icon_button(
                    rx.icon("trash_2", size=13),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    cursor="pointer"
                ),
                title="确认删除销售平台",
                description=f"你确认要删除销售平台【{p.name}】吗？删除后，已保存的历史数据不受影响，但新建订单及商品时将无法再关联此平台。",
                confirm_label="确认删除",
                on_confirm=lambda: PlatformsState.delete_platform(p.id),
                confirm_color="red"
            )
        )
    )

def platform_form() -> rx.Component:
    """新增销售平台表单卡片"""
    return rx.card(
        rx.vstack(
            rx.heading("➕ 追加销售平台", size="3", weight="bold"),
            rx.text("在此为系统追加新的线上/线下销售渠道并配置其扣率和币种参数。", size="1", color=rx.color("slate", 9)),
            rx.divider(),
            
            custom_form_field(
                "平台英文代号 (唯一标识，如: ebay)",
                rx.input(
                    placeholder="请输入拼音或英文小写代号",
                    value=PlatformsState.new_code,
                    on_change=PlatformsState.set_new_code,
                    size="2",
                    width="100%"
                ),
                required=True
            ),
            custom_form_field(
                "平台显示名称 (如: eBay 商店)",
                rx.input(
                    placeholder="显示在列表与下拉菜单中的名称",
                    value=PlatformsState.new_name,
                    on_change=PlatformsState.set_new_name,
                    size="2",
                    width="100%"
                ),
                required=True
            ),
            
            rx.grid(
                custom_form_field(
                    "结算币种",
                    rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.foreach(
                                PlatformsState.currency_options,
                                lambda c: rx.select.item(c, value=c)
                            )
                        ),
                        value=PlatformsState.new_currency,
                        on_change=PlatformsState.set_new_currency,
                        size="2",
                        width="100%"
                    )
                ),
                custom_form_field(
                    "手续费率 (%)",
                    rx.input(
                        type="number",
                        placeholder="例如: 0.6 或 5.6",
                        on_change=PlatformsState.set_new_fee_rate,
                        size="2",
                        width="100%"
                    )
                ),
                custom_form_field(
                    "单笔固定费用 (原币)",
                    rx.input(
                        type="number",
                        placeholder="例如: 22",
                        on_change=PlatformsState.set_new_fee_fixed,
                        size="2",
                        width="100%"
                    )
                ),
                columns="3",
                spacing="3",
                width="100%"
            ),
            
            rx.button(
                rx.icon("plus", size=14),
                "添加销售平台",
                on_click=PlatformsState.add_platform,
                color_scheme="violet",
                size="2",
                width="100%"
            ),
            spacing="3",
            width="100%"
        ),
        padding="1rem"
    )

def platforms_list_table() -> rx.Component:
    """销售平台列表表格"""
    return rx.cond(
        PlatformsState.platforms.length() == 0,
        empty_state("暂无销售平台。"),
        rx.scroll_area(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("平台代号", size="1"),
                        rx.table.column_header_cell("平台名称", size="1"),
                        rx.table.column_header_cell("结算币种", size="1"),
                        rx.table.column_header_cell("手续费扣率", size="1"),
                        rx.table.column_header_cell("单笔固定费 (原币)", size="1"),
                        rx.table.column_header_cell("操作", size="1"),
                    )
                ),
                rx.table.body(
                    rx.foreach(PlatformsState.platforms, render_platform_row)
                ),
                size="1",
                width="100%"
            ),
            overflow_x="auto",
            width="100%"
        )
    )

def platforms_page() -> rx.Component:
    """销售平台管理主页面入口"""
    return page_layout(
        rx.vstack(
            rx.grid(
                # 左栏：平台列表
                data_card(
                    "📋 现有销售平台清单",
                    platforms_list_table()
                ),
                # 右栏：添加平台表单
                platform_form(),
                columns="12",
                spacing="4",
                width="100%",
                style={
                    "gridTemplateColumns": "7fr 5fr"
                },
                align_items="start"
            ),
            spacing="4",
            width="100%"
        ),
        title="🌐 销售平台管理"
    )

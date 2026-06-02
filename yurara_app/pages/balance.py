# yurara_app/pages/balance.py
"""
公司账面概览 (资产负债表与资本) 页面。
左右双栏经典财务布局，配合 HSL 渐变亮边高亮汇总指标卡片。
"""
import reflex as rx
from ..state.balance_state import BalanceState, BalanceDisplayRow
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state


def summary_card(title: str, cny_val: rx.Var, jpy_val: rx.Var, jpy_cny_val: rx.Var, total_val: rx.Var, color_scheme: str = "violet") -> rx.Component:
    """现代渐变高亮财务指标卡片"""
    return rx.card(
        rx.vstack(
            rx.heading(title, size="2", color_scheme=color_scheme),
            rx.hstack(
                rx.text("CNY:", size="1", color=rx.color("slate", 10)),
                rx.spacer(),
                rx.text(cny_val, size="1", weight="bold"),
                width="100%"
            ),
            rx.hstack(
                rx.text("JPY:", size="1", color=rx.color("slate", 10)),
                rx.spacer(),
                rx.text(jpy_val, size="1", weight="bold"),
                width="100%"
            ),
            rx.hstack(
                rx.spacer(),
                rx.text(rx.fragment("(折合 CNY: ", jpy_cny_val, ")"), size="1", color=rx.color("slate", 9)),
                width="100%"
            ),
            rx.divider(margin="0"),
            rx.hstack(
                rx.text("综合总计(CNY):", size="1", weight="bold", color=rx.color(color_scheme, 11)),
                rx.spacer(),
                rx.text(total_val, size="3", weight="bold", color=rx.color(color_scheme, 11)),
                width="100%",
                align="center"
            ),
            spacing="1",
            width="100%"
        ),
        width="100%",
        padding="0.75rem",
        style={"border_left": f"4px solid {rx.color(color_scheme, 9)}"}
    )


def create_account_accordion() -> rx.Component:
    """追加现金账户的折叠抽屉表单"""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.hstack(
                rx.icon("plus", size=14),
                rx.text("追加现金账户", size="2"),
                spacing="1",
                align="center",
            ),
            content=rx.vstack(
                rx.text("在此处可以开设备用金、独立银行卡等专属现金账户。", size="1", color=rx.color("slate", 10)),
                rx.hstack(
                    custom_form_field(
                        "账户名称",
                        rx.input(
                            placeholder="如：日常备用金、三井住友银行",
                            value=BalanceState.new_acc_name,
                            on_change=BalanceState.set_new_acc_name,
                            size="2",
                            width="250px"
                        ),
                        width="auto"
                    ),
                    custom_form_field(
                        "币种",
                        rx.select.root(
                            rx.select.trigger(width="120px"),
                            rx.select.content(
                                rx.select.item("CNY", value="CNY"),
                                rx.select.item("JPY", value="JPY")
                            ),
                            value=BalanceState.new_acc_curr,
                            on_change=BalanceState.set_new_acc_curr,
                            size="2"
                        ),
                        width="auto"
                    ),
                    spacing="3",
                    align="end"
                ),
                rx.button(
                    rx.icon("check", size=13),
                    "确认追加",
                    on_click=BalanceState.create_cash_account,
                    size="2",
                    color_scheme="violet"
                ),
                spacing="3",
                padding="1.5rem 0",
                width="100%",
                align_items="start"
            ),
            value="create-acc"
        ),
        collapsible=True,
        width="100%"
    )


def balance_table(rows: list, empty_msg: str = "暂无记录") -> rx.Component:
    """资产负债数据表格"""
    return rx.cond(
        rx.Var.create(rows).length() == 0,
        empty_state(empty_msg),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("项目", size="1"),
                    rx.table.column_header_cell("CNY", size="1"),
                    rx.table.column_header_cell("JPY", size="1"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    rows,
                    lambda r: rx.table.row(
                        rx.table.cell(rx.text(r.item_name, size="1", weight="medium")),
                        rx.table.cell(rx.text(r.cny_val, size="1")),
                        rx.table.cell(rx.text(r.jpy_val, size="1")),
                    )
                )
            ),
            size="1",
            width="100%"
        )
    )


def balance_page() -> rx.Component:
    """账面概览主页面"""
    return page_layout(
        rx.vstack(
            # 顶部操作栏
            create_account_accordion(),
            rx.divider(),
            
            # 双栏资产负债表布局
            rx.grid(
                # ==== 左栏：资产端 ====
                rx.vstack(
                    rx.heading("🏢 现金与实物资产 (Assets)", size="4", weight="bold"),
                    data_card(
                        "资产细明",
                        balance_table(BalanceState.assets_rows, "暂无资产数据")
                    ),
                    
                    # 报表四分汇总卡片
                    rx.grid(
                        summary_card("💵 现金总计", BalanceState.cash_cny_str, BalanceState.cash_jpy_str, BalanceState.cash_jpy_cny_str, BalanceState.cash_total_str, "green"),
                        summary_card("🏢 资产总计 (非现金)", BalanceState.pure_asset_cny_str, BalanceState.pure_asset_jpy_str, BalanceState.pure_asset_jpy_cny_str, BalanceState.pure_asset_total_str, "blue"),
                        columns="2",
                        spacing="3",
                        width="100%"
                    ),
                    summary_card("🏛️ CNY/JPY 总资产 (现金+资产)", BalanceState.total_asset_cny_str, BalanceState.total_asset_jpy_str, BalanceState.total_asset_jpy_cny_str, BalanceState.total_asset_total_str, "purple"),
                    summary_card("✨ 净资产 (总资产 - 负债)", BalanceState.net_cny_str, BalanceState.net_jpy_str, BalanceState.net_jpy_cny_str, BalanceState.net_total_str, "orange"),
                    spacing="3",
                    width="100%"
                ),
                
                # ==== 右栏：负债与资本端 ====
                rx.vstack(
                    # 负债部分
                    rx.heading("📉 负债与资本 (Liabilities & Equity)", size="4", weight="bold"),
                    data_card(
                        "负债细明",
                        balance_table(BalanceState.liabilities_rows, "当前无记录在案负债")
                    ),
                    summary_card("负债总计", BalanceState.liability_cny_str, BalanceState.liability_jpy_str, BalanceState.liability_jpy_cny_str, BalanceState.liability_total_str, "orange"),
                    
                    rx.divider(margin="1rem 0"),
                    
                    # 资本部分
                    data_card(
                        "资本记录",
                        balance_table(BalanceState.equities_rows, "当前无注入资本记录")
                    ),
                    summary_card("资本总计", BalanceState.equity_cny_str, BalanceState.equity_jpy_str, BalanceState.equity_jpy_cny_str, BalanceState.equity_total_str, "green"),
                    spacing="3",
                    width="100%"
                ),
                columns="2",
                spacing="5",
                width="100%",
                align_items="start"
            ),
            spacing="4",
            width="100%"
        ),
        title="公司账面概览 (资产负债表)"
    )

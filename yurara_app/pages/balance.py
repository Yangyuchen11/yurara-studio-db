# yurara_app/pages/balance.py
"""
公司账面概览 (资产负债表与资本) 页面。
已升级为多货币动态列架构：
  - 资产/负债/资本表格动态渲染所有货币列
  - 汇总卡片按实际货币动态展示
"""
import reflex as rx
from ..state.balance_state import BalanceState, BalanceDisplayRow, BalanceSummaryItem
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state


def summary_card_multi(title: str, items: list, total_cny: rx.Var, color_scheme: str = "violet") -> rx.Component:
    """多货币财务指标汇总卡片，动态渲染各货币原值行 + 折合CNY总计行。"""

    def item_row(item: BalanceSummaryItem) -> rx.Component:
        return rx.hstack(
            rx.text(item.currency + ":", size="1", color=rx.color("slate", 10)),
            rx.spacer(),
            rx.text(item.amount_str, size="1", weight="medium"),
            rx.cond(
                item.currency != "CNY",
                rx.text(f"≈ {item.amount_cny_str}", size="1", color=rx.color("slate", 9)),
                rx.fragment(),
            ),
            width="100%",
        )

    return rx.card(
        rx.vstack(
            rx.heading(title, size="2", color_scheme=color_scheme),
            rx.foreach(items, item_row),
            rx.divider(margin="0"),
            rx.hstack(
                rx.text("综合总计(CNY):", size="1", weight="bold", color=rx.color(color_scheme, 11)),
                rx.spacer(),
                rx.text(
                    rx.Var.create(f"¥ {{total_cny:,.2f}}") if not hasattr(total_cny, '__str__') else total_cny,
                    size="3",
                    weight="bold",
                    color=rx.color(color_scheme, 11),
                ),
                width="100%",
                align="center",
            ),
            spacing="1",
            width="100%",
        ),
        width="100%",
        padding="0.75rem",
        style={"border_left": f"4px solid {rx.color(color_scheme, 9)}"},
    )


def summary_card_simple(title: str, total_cny_str: rx.Var, color_scheme: str = "violet") -> rx.Component:
    """简化版汇总卡片，仅显示折合CNY合计。"""
    return rx.card(
        rx.vstack(
            rx.heading(title, size="2", color_scheme=color_scheme),
            rx.hstack(
                rx.text("综合总计(CNY):", size="1", weight="bold", color=rx.color(color_scheme, 11)),
                rx.spacer(),
                rx.text(total_cny_str, size="3", weight="bold", color=rx.color(color_scheme, 11)),
                width="100%",
                align="center",
            ),
            spacing="1",
            width="100%",
        ),
        width="100%",
        padding="0.75rem",
        style={"border_left": f"4px solid {rx.color(color_scheme, 9)}"},
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
                rx.text("在此处可以开设备用金、独立银行卡等专属现金账户。", size="1", color=rx.color("white", 9)),
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
                        rx.hstack(
                            rx.input(
                                placeholder="CNY / JPY / USD ...",
                                value=BalanceState.new_acc_curr,
                                on_change=BalanceState.set_new_acc_curr,
                                size="2",
                                width="120px",
                            ),
                            rx.text("（直接输入货币代码）", size="1", color=rx.color("white", 9)),
                            align="center",
                            spacing="2",
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
                    style={"background": "#10b981", "color": "white", "font-weight": "bold", "cursor": "pointer"}
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


def balance_table_multi(rows: rx.Var, currencies: rx.Var, empty_msg: str = "暂无记录") -> rx.Component:
    """
    多货币动态列账面明细表格。
    列：[项目名 | CNY | JPY | USD | ... | 折合CNY合计]
    """

    def header_cell(currency: str) -> rx.Component:
        return rx.table.column_header_cell(currency, size="1")

    def amount_cell_for(row: BalanceDisplayRow, currency: str) -> rx.Component:
        return rx.table.cell(
            rx.text(
                row.amounts_by_currency.get(currency, "-"),
                size="1",
                color=rx.cond(
                    row.amounts_by_currency.get(currency, "-") == "-",
                    rx.color("slate", 8),
                    rx.color("slate", 12),
                ),
            )
        )

    return rx.cond(
        rx.Var.create(rows).length() == 0,
        empty_state(empty_msg),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("项目", size="1"),
                    rx.foreach(currencies, header_cell),
                    rx.table.column_header_cell("折合CNY合计", size="1"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    rows,
                    lambda r: rx.table.row(
                        rx.table.cell(rx.text(r.item_name, size="1", weight="medium")),
                        rx.foreach(currencies, lambda c: amount_cell_for(r, c)),
                        rx.table.cell(
                            rx.text(r.total_cny_str, size="1", weight="medium",
                                    color=rx.color("violet", 11))
                        ),
                    )
                )
            ),
            size="1",
            width="100%",
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
                        balance_table_multi(BalanceState.assets_rows, BalanceState.display_currencies, "暂无资产数据")
                    ),

                    # 报表四分汇总卡片（简化版，仅显示CNY总计）
                    rx.grid(
                        summary_card_simple("💵 现金总计", BalanceState.cash_total_str, "green"),
                        summary_card_simple("🏢 资产总计 (非现金)", BalanceState.pure_asset_total_str, "blue"),
                        columns="2",
                        spacing="3",
                        width="100%"
                    ),

                    # 折明细的多货币卡片
                    rx.card(
                        rx.vstack(
                            rx.heading("🏛️ 总资产 (现金+资产)", size="2", color_scheme="purple"),
                            rx.foreach(
                                BalanceState.total_asset_by_currency,
                                lambda item: rx.hstack(
                                    rx.text(item.currency + ":", size="1", color=rx.color("slate", 10)),
                                    rx.spacer(),
                                    rx.text(item.amount_str, size="1", weight="medium"),
                                    rx.cond(
                                        item.currency != "CNY",
                                        rx.text("≈ " + item.amount_cny_str, size="1", color=rx.color("slate", 9)),
                                        rx.fragment(),
                                    ),
                                    width="100%",
                                )
                            ),
                            rx.divider(margin="0"),
                            rx.hstack(
                                rx.text("综合总计(CNY):", size="1", weight="bold", color=rx.color("purple", 11)),
                                rx.spacer(),
                                rx.text(BalanceState.total_asset_total_str, size="3", weight="bold", color=rx.color("purple", 11)),
                                width="100%", align="center",
                            ),
                            spacing="1", width="100%",
                        ),
                        width="100%", padding="0.75rem",
                        style={"border_left": f"4px solid {rx.color('purple', 9)}"},
                    ),

                    rx.card(
                        rx.vstack(
                            rx.heading("✨ 净资产 (总资产 - 负债)", size="2", color_scheme="orange"),
                            rx.foreach(
                                BalanceState.net_by_currency,
                                lambda item: rx.hstack(
                                    rx.text(item.currency + ":", size="1", color=rx.color("slate", 10)),
                                    rx.spacer(),
                                    rx.text(item.amount_str, size="1", weight="medium"),
                                    rx.cond(
                                        item.currency != "CNY",
                                        rx.text("≈ " + item.amount_cny_str, size="1", color=rx.color("slate", 9)),
                                        rx.fragment(),
                                    ),
                                    width="100%",
                                )
                            ),
                            rx.divider(margin="0"),
                            rx.hstack(
                                rx.text("综合总计(CNY):", size="1", weight="bold", color=rx.color("orange", 11)),
                                rx.spacer(),
                                rx.text(BalanceState.net_total_str, size="3", weight="bold", color=rx.color("orange", 11)),
                                width="100%", align="center",
                            ),
                            spacing="1", width="100%",
                        ),
                        width="100%", padding="0.75rem",
                        style={"border_left": f"4px solid {rx.color('orange', 9)}"},
                    ),

                    spacing="3",
                    width="100%"
                ),

                # ==== 右栏：负债与资本端 ====
                rx.vstack(
                    rx.heading("📉 负债与资本 (Liabilities & Equity)", size="4", weight="bold"),
                    data_card(
                        "负债细明",
                        balance_table_multi(BalanceState.liabilities_rows, BalanceState.display_currencies, "当前无记录在案负债")
                    ),
                    rx.card(
                        rx.vstack(
                            rx.heading("负债总计", size="2", color_scheme="red"),
                            rx.foreach(
                                BalanceState.liability_by_currency,
                                lambda item: rx.hstack(
                                    rx.text(item.currency + ":", size="1", color=rx.color("slate", 10)),
                                    rx.spacer(),
                                    rx.text(item.amount_str, size="1", weight="medium"),
                                    rx.cond(
                                        item.currency != "CNY",
                                        rx.text("≈ " + item.amount_cny_str, size="1", color=rx.color("slate", 9)),
                                        rx.fragment(),
                                    ),
                                    width="100%",
                                )
                            ),
                            rx.divider(margin="0"),
                            rx.hstack(
                                rx.text("综合总计(CNY):", size="1", weight="bold", color=rx.color("red", 11)),
                                rx.spacer(),
                                rx.text(BalanceState.liability_total_str, size="3", weight="bold", color=rx.color("red", 11)),
                                width="100%", align="center",
                            ),
                            spacing="1", width="100%",
                        ),
                        width="100%", padding="0.75rem",
                        style={"border_left": f"4px solid {rx.color('red', 9)}"},
                    ),

                    rx.divider(margin="1rem 0"),

                    data_card(
                        "资本记录",
                        balance_table_multi(BalanceState.equities_rows, BalanceState.display_currencies, "当前无注入资本记录")
                    ),
                    rx.card(
                        rx.vstack(
                            rx.heading("资本总计", size="2", color_scheme="green"),
                            rx.foreach(
                                BalanceState.equity_by_currency,
                                lambda item: rx.hstack(
                                    rx.text(item.currency + ":", size="1", color=rx.color("slate", 10)),
                                    rx.spacer(),
                                    rx.text(item.amount_str, size="1", weight="medium"),
                                    rx.cond(
                                        item.currency != "CNY",
                                        rx.text("≈ " + item.amount_cny_str, size="1", color=rx.color("slate", 9)),
                                        rx.fragment(),
                                    ),
                                    width="100%",
                                )
                            ),
                            rx.divider(margin="0"),
                            rx.hstack(
                                rx.text("综合总计(CNY):", size="1", weight="bold", color=rx.color("green", 11)),
                                rx.spacer(),
                                rx.text(BalanceState.equity_total_str, size="3", weight="bold", color=rx.color("green", 11)),
                                width="100%", align="center",
                            ),
                            spacing="1", width="100%",
                        ),
                        width="100%", padding="0.75rem",
                        style={"border_left": f"4px solid {rx.color('green', 9)}"},
                    ),

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
        title="公司账面概览 (资产负债表)",
    )

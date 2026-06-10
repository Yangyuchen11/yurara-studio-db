# yurara_app/pages/report.py
"""
财务分析与资本报表视图层。
适配 Reflex 页面布局，搭载 HSL 渐变与现代高透玻璃拟态风格，承载财务月报与年报结算展示。
"""
import reflex as rx
from ..state.report_state import ReportState
from ..components.layout import page_layout
from ..components.editable_table import data_card, stat_card, empty_state


def render_account_row(r) -> rx.Component:
    """渲染资金账户变动行。"""
    return rx.table.row(
        rx.table.cell(rx.text(r.account_name, size="1", weight="medium")),
        rx.table.cell(rx.badge(r.currency, color_scheme="violet", variant="soft")),
        rx.table.cell(rx.text(r.opening_str, size="1")),
        rx.table.cell(rx.text(r.inflow_str, size="1", color="green", weight="bold")),
        rx.table.cell(rx.text(r.outflow_str, size="1", color="red")),
        rx.table.cell(
            rx.text(
                r.net_str, 
                size="1", 
                weight="bold", 
                color=rx.cond(r.net_change >= 0, "green", "red")
            )
        ),
        rx.table.cell(rx.text(r.closing_str, size="1", weight="bold")),
    )


def render_asset_liab_row(r) -> rx.Component:
    """渲染资产负债明细行。"""
    return rx.table.row(
        rx.table.cell(rx.text(r.category, size="1", weight="medium")),
        rx.table.cell(rx.text(r.cny_str, size="1")),
        rx.table.cell(rx.text(r.jpy_str, size="1")),
        rx.table.cell(rx.text(r.equiv_str, size="1", weight="bold", color=rx.color("violet", 11))),
    )


def render_flow_row(r) -> rx.Component:
    """渲染收支明细行。"""
    return rx.table.row(
        rx.table.cell(rx.text(r.category, size="1", weight="medium")),
        rx.table.cell(
            rx.badge(
                r.direction, 
                color_scheme=rx.cond(r.direction == "流入", "green", "red"),
                variant="soft"
            )
        ),
        rx.table.cell(rx.text(r.cny_str, size="1")),
        rx.table.cell(rx.text(r.jpy_str, size="1")),
        rx.table.cell(rx.text(r.equiv_str, size="1", weight="bold")),
    )


def report_dashboard() -> rx.Component:
    """报表汇总大面板"""
    return rx.vstack(
        # 一、资金流汇总 (现金流汇总卡)
        rx.heading("💵 一、 期初与期末现金流汇总 (折算 CNY 总计)", size="3", margin_top="1rem", color=rx.color("violet", 10)),
        rx.grid(
            stat_card("期初总资金 (变动前)", ReportState.past_cash_total_str, icon="landmark", color_scheme="slate"),
            stat_card("本期净现金流 (变动额)", ReportState.net_cash_total_str, icon="arrow_left_right", color_scheme="violet"),
            stat_card("期末总资金 (变动后)", ReportState.closing_cash_total_str, icon="wallet", color_scheme="green"),
            columns="3",
            spacing="4",
            width="100%"
        ),
        
        # 二、资产、经营与存货
        rx.heading("🏢 二、 实体资产与经营盈亏结算 (经营利润与存货大盘)", size="3", color=rx.color("violet", 10)),
        rx.grid(
            # 实体资产变动
            rx.card(
                rx.vstack(
                    rx.hstack(rx.icon("shopping_bag", size=15), rx.text("实体设备与物料资产投入", size="1", color=rx.color("slate", 10)), spacing="1"),
                    rx.hstack(rx.text("本期新增投入:", size="1"), rx.spacer(), rx.text(ReportState.month_asset_add_str, size="1", weight="medium"), width="100%"),
                    rx.hstack(rx.text("本期资产变现:", size="1"), rx.spacer(), rx.text(ReportState.month_asset_sub_str, size="1"), width="100%"),
                    rx.divider(),
                    rx.hstack(rx.text("资产净变动:", size="1", weight="bold"), rx.spacer(), rx.text(ReportState.net_asset_change_str, size="2", weight="bold", color=rx.color("blue", 11)), width="100%"),
                    spacing="2",
                    width="100%"
                ),
                padding="1rem"
            ),
            
            # 经营利润变动
            rx.card(
                rx.vstack(
                    rx.hstack(rx.icon("trending_up", size=15), rx.text("主营盈亏净利润大盘", size="1", color=rx.color("slate", 10)), spacing="1"),
                    rx.hstack(rx.text("营业总收入:", size="1"), rx.spacer(), rx.text(ReportState.profit_in_str, size="1", weight="medium", color="green"), width="100%"),
                    rx.hstack(rx.text("营业总成本:", size="1"), rx.spacer(), rx.text(ReportState.profit_out_str, size="1", color="red"), width="100%"),
                    rx.divider(),
                    rx.hstack(rx.text("本期净利润:", size="1", weight="bold"), rx.spacer(), rx.text(ReportState.net_profit_str, size="2", weight="bold", color=rx.color("violet", 11)), width="100%"),
                    spacing="2",
                    width="100%"
                ),
                padding="1rem"
            ),
            
            # 实时存货家底
            rx.card(
                rx.vstack(
                    rx.hstack(rx.icon("box", size=15), rx.text("实时存货资产估值 (家底)", size="1", color=rx.color("slate", 10)), spacing="1"),
                    rx.hstack(rx.text("大货商品资产:", size="1"), rx.spacer(), rx.text(ReportState.stock_cny_str, size="1"), width="100%"),
                    rx.hstack(rx.text("在制在研资产:", size="1"), rx.spacer(), rx.text(ReportState.wip_cny_str, size="1"), width="100%"),
                    rx.divider(),
                    rx.hstack(rx.text("存货合计(实时):", size="1", weight="bold"), rx.spacer(), rx.text(ReportState.inventory_total_cny_str, size="2", weight="bold", color=rx.color("green", 11)), width="100%"),
                    spacing="2",
                    width="100%"
                ),
                padding="1rem"
            ),
            columns="3",
            spacing="4",
            width="100%"
        ),
        
        rx.divider(),
        
        # 三、资金账户明细表
        rx.heading("💵 三、 各流动资金账户变动明细", size="3", color=rx.color("violet", 10)),
        data_card(
            "资金账户对账单 (已过滤空账户)",
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("资金账户", size="1"),
                        rx.table.column_header_cell("币种", size="1"),
                        rx.table.column_header_cell("期初余额(前)", size="1"),
                        rx.table.column_header_cell("本期流入", size="1"),
                        rx.table.column_header_cell("本期流出", size="1"),
                        rx.table.column_header_cell("净变动额", size="1"),
                        rx.table.column_header_cell("期末余额(后)", size="1"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        ReportState.acc_summary,
                        render_account_row
                    )
                ),
                size="1",
                width="100%",
                variant="ghost"
            )
        ),
        
        rx.divider(),
        
        # 四、物料采购 vs 负债资本
        rx.heading("🏢 四、 固定及其他资产采购 / 负债与外部资本变动", size="3", color=rx.color("violet", 10)),
        rx.grid(
            # 物料卡片
            data_card(
                "🛒 实体设备与物料采购汇总",
                rx.cond(
                    ReportState.asset_purchase_rows.length() == 0,
                    rx.text("本期无固定设备或耗材采购记录。", size="1", color=rx.color("slate", 9)),
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("资产分类", size="1"),
                                rx.table.column_header_cell("CNY 变动", size="1"),
                                rx.table.column_header_cell("JPY 变动", size="1"),
                                rx.table.column_header_cell("折合 CNY 总计", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                ReportState.asset_purchase_rows,
                                render_asset_liab_row
                            )
                        ),
                        size="1",
                        width="100%"
                    )
                )
            ),
            # 负债卡片
            data_card(
                "📉 负债与外部投资资本变动汇总",
                rx.cond(
                    ReportState.liab_equity_rows.length() == 0,
                    rx.text("本期无外部借贷、还款或投资注资变动。", size="1", color=rx.color("slate", 9)),
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("资本分类", size="1"),
                                rx.table.column_header_cell("CNY 变动", size="1"),
                                rx.table.column_header_cell("JPY 变动", size="1"),
                                rx.table.column_header_cell("折合 CNY 总计", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                ReportState.liab_equity_rows,
                                render_asset_liab_row
                            )
                        ),
                        size="1",
                        width="100%"
                    )
                )
            ),
            columns="2",
            spacing="5",
            width="100%"
        ),
        
        rx.divider(),
        
        # 五、详细收支构成直方图
        rx.heading("📊 五、 经营性现金流收支流向构成分析", size="3", color=rx.color("violet", 10)),
        rx.grid(
            # 直方图
            rx.card(
                rx.vstack(
                    rx.text("收支流向绝对金额排行 (元)", size="2", weight="bold"),
                    rx.vstack(
                        rx.foreach(
                            ReportState.chart_bar_data,
                            lambda item: rx.vstack(
                                rx.hstack(
                                    rx.text(item["name"], size="1", weight="medium"),
                                    rx.spacer(),
                                    rx.text(item["amount_str"], size="1", weight="bold", color=rx.color("violet", 11)),
                                    width="100%",
                                ),
                                rx.box(
                                    rx.box(
                                        width=item["width_pct"],
                                        height="6px",
                                        background="linear-gradient(90deg, var(--violet-9), var(--fuchsia-9))",
                                        border_radius="3px",
                                    ),
                                    width="100%",
                                    height="6px",
                                    background="var(--slate-4)",
                                    border_radius="3px",
                                    overflow="hidden",
                                ),
                                width="100%",
                                spacing="1",
                            )
                        ),
                        width="100%",
                        spacing="3",
                        padding="0.5rem 0",
                    ),
                    width="100%",
                    spacing="3"
                ),
                padding="1rem",
                grid_column="span 5"
            ),
            # 明细表格
            rx.box(
                data_card(
                    "收支流水大类折合账表",
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("大类分类", size="1"),
                                rx.table.column_header_cell("资金流向", size="1"),
                                rx.table.column_header_cell("CNY 变动", size="1"),
                                rx.table.column_header_cell("JPY 变动", size="1"),
                                rx.table.column_header_cell("折合 CNY 总计", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                ReportState.flow_summary,
                                render_flow_row
                            )
                        ),
                        size="1",
                        width="100%"
                    )
                ),
                grid_column="span 7",
                width="100%"
            ),
            columns="12",
            spacing="5",
            width="100%",
            align_items="start"
        ),
        
        # 六、年度走势 (仅在年报模式下渲染)
        rx.cond(
            ReportState.active_report_type == "year",
            rx.vstack(
                rx.divider(),
                rx.heading("📈 六、 年度内按月份经营盈亏走势分析", size="3", color=rx.color("violet", 10)),
                rx.card(
                    rx.vstack(
                        rx.text("按月份净利润走势图 (CNY)", size="2", weight="bold"),
                        rx.hstack(
                            rx.foreach(
                                ReportState.trend_chart_data,
                                lambda item: rx.vstack(
                                    rx.center(
                                        rx.tooltip(
                                            rx.box(
                                                height=item["height_str"],
                                                width="14px",
                                                background=rx.cond(
                                                    item["is_positive"],
                                                    "linear-gradient(180deg, var(--green-9), var(--emerald-10))",
                                                    "linear-gradient(180deg, var(--red-9), var(--crimson-10))",
                                                ),
                                                border_radius="4px 4px 0 0",
                                                transition="all 0.2s ease",
                                                _hover={
                                                    "opacity": 0.8,
                                                    "transform": "scaleY(1.05)",
                                                },
                                            ),
                                            content=item["profit_str"],
                                        ),
                                        height="100px",
                                        align_items="end",
                                        width="100%",
                                    ),
                                    rx.text(item["month"], size="1", color=rx.color("slate", 10), weight="medium"),
                                    spacing="1",
                                    align="center",
                                    width="32px",
                                )
                            ),
                            width="100%",
                            justify="between",
                            align_items="end",
                            padding="1.5rem 0.5rem 0.5rem 0.5rem",
                        ),
                        width="100%",
                        spacing="3"
                    ),
                    width="100%",
                    padding="1rem"
                ),
                width="100%",
                spacing="3"
            ),
            rx.fragment()
        ),
        spacing="4",
        width="100%"
    )


def report_page() -> rx.Component:
    """报表总页面布局。"""
    return page_layout(
        rx.vstack(
            # Tab 切换控制（仅 triggers，不使用 tabs.content 避免重复渲染 Recharts）
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger(
                        rx.hstack(rx.icon("calendar", size=14), rx.text("📅 公司资本月报看板"), spacing="1"),
                        value="month",
                    ),
                    rx.tabs.trigger(
                        rx.hstack(rx.icon("calendar_range", size=14), rx.text("📆 公司资本年报看板"), spacing="1"),
                        value="year",
                    ),
                    width="100%"
                ),
                value=ReportState.active_report_type,
                on_change=ReportState.select_report_type,
            ),

            # 加载状态保护：避免 Recharts 在数据尚未就绪时渲染导致 React 崩溃
            rx.cond(
                ReportState.is_loading,
                rx.center(
                    rx.vstack(
                        rx.spinner(size="3"),
                        rx.text("正在加载报表数据...", size="2", color=rx.color("slate", 10)),
                        spacing="3",
                        align="center",
                    ),
                    padding="4rem",
                    width="100%",
                ),
                rx.vstack(
                    # 选择器区域（月/年 根据当前 tab 切换）
                    rx.card(
                        rx.hstack(
                            rx.cond(
                                ReportState.active_report_type == "month",
                                rx.text("🔍 请选择要查询的结算月份:", size="2", weight="medium"),
                                rx.text("🔍 请选择要查询的结算年份:", size="2", weight="medium"),
                            ),
                            rx.cond(
                                ReportState.active_report_type == "month",
                                rx.select(
                                    ReportState.available_months,
                                    value=ReportState.selected_month,
                                    on_change=ReportState.select_month,
                                    size="2",
                                    width="150px"
                                ),
                                rx.select(
                                    ReportState.available_years,
                                    value=ReportState.selected_year,
                                    on_change=ReportState.select_year,
                                    size="2",
                                    width="150px"
                                ),
                            ),
                            spacing="3",
                            align="center",
                            width="100%"
                        ),
                        width="100%",
                        padding="1rem",
                        margin_top="1rem"
                    ),

                    # 报表主体（只渲染一次 report_dashboard，避免 Recharts 重复实例化导致 React 崩溃）
                    rx.cond(
                        ReportState.has_data,
                        report_dashboard(),
                        empty_state("暂无流水数据")
                    ),
                    spacing="4",
                    width="100%"
                ),
            ),

            spacing="4",
            width="100%"
        ),
        title="财务报表与分析"
    )


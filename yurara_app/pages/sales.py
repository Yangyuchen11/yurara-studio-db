# yurara_app/pages/sales.py
"""
销售数据分析透视大屏。
支持 V2.0 和 V1.0 数据 Tab 自适应，提供热度榜单、款式-平台交叉表、Recharts 堆叠直方图及真分页销量变更日志流水。
"""
import reflex as rx
from ..state.sales_state import SalesState, SalesLeaderboardRow, SalesLogItem, VariantPivotRow
from ..components.layout import page_layout
from ..components.editable_table import data_card, custom_form_field, empty_state


def sales_metric_card(label: str, value: rx.Var, unit: str = "", color_scheme: str = "violet", icon: str = "trending_up", description: str = "") -> rx.Component:
    """高辨识度销售大屏指标卡片"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=16, color=rx.color(color_scheme, 9)),
                rx.text(label, size="1", color=rx.color("slate", 10)),
                rx.cond(
                    description != "",
                    rx.tooltip(
                        rx.icon("circle_help", size=12, color=rx.color("slate", 7)),
                        content=description
                    ),
                    rx.fragment()
                ),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                rx.text(value, size="5", weight="bold"),
                rx.cond(
                    unit != "",
                    rx.text(unit, size="1", color=rx.color("slate", 10), margin_top="auto"),
                    rx.fragment()
                ),
                spacing="1",
                align="end",
            ),
            spacing="1",
            align_items="start",
            width="100%"
        ),
        padding="0.75rem",
        width="100%",
    )


def render_leaderboard_row(r: SalesLeaderboardRow, idx: int) -> rx.Component:
    """产品榜单单行，支持点击选择切换"""
    is_selected = (SalesState.selected_product == r.product_name)
    bg_color = rx.cond(is_selected, rx.color("violet", 3), "transparent")
    border_color = rx.cond(is_selected, rx.color("violet", 7), "transparent")
    
    return rx.table.row(
        rx.table.cell(rx.text(idx + 1, size="1", weight="bold", color=rx.color("slate", 8))),
        rx.table.cell(rx.text(r.product_name, size="1", weight="bold", line_clamp=1)),
        rx.table.cell(rx.text(f"¥ {r.grand_total_cny:,.2f}", size="1", weight="medium")),
        on_click=lambda: SalesState.select_product(r.product_name),
        style={
            "backgroundColor": bg_color,
            "borderLeft": f"3px solid {border_color}",
            "cursor": "pointer",
            "transition": "all 0.15s ease"
        }
    )


def leaderboard_panel() -> rx.Component:
    """左侧：🏆 产品热卖榜单"""
    return rx.card(
        rx.vstack(
            rx.heading("🏆 热销产品榜单", size="3", weight="bold"),
            rx.text("点击产品行可以直接在右侧进行销售深度剖析。", size="1", color=rx.color("slate", 9)),
            rx.cond(
                SalesState.leaderboard_is_empty,
                empty_state("暂无销售榜单数据"),
                rx.scroll_area(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("排名", size="1"),
                                rx.table.column_header_cell("产品", size="1"),
                                rx.table.column_header_cell("折合总额", size="1"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                SalesState.leaderboard,
                                lambda row, idx: render_leaderboard_row(row, idx)
                            )
                        ),
                        size="1",
                        width="100%"
                    ),
                    height="500px",
                    width="100%"
                )
            ),
            spacing="3",
            width="100%"
        ),
        padding="0.75rem",
        width="100%",
        height="100%"
    )


def pivot_analysis_table() -> rx.Component:
    """款式-平台交叉销量透视表"""
    return rx.vstack(
        rx.scroll_area(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.foreach(
                            SalesState.pivot_headers,
                            lambda h: rx.table.column_header_cell(h, size="1")
                        )
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        SalesState.pivot_rows,
                        lambda row: rx.table.row(
                            rx.table.cell(rx.text(row.variant, size="1", weight="bold")),
                            rx.foreach(
                                SalesState.pivot_platforms,
                                lambda h: rx.table.cell(rx.text(row.qtys_by_platform[h].to_string(), size="1"))
                            ),
                            rx.table.cell(rx.text(row.total_qty.to_string(), size="1", weight="bold")),
                            style={"backgroundColor": rx.cond(row.variant == "总计", rx.color("slate", 3), "transparent")}
                        )
                    )
                ),
                size="1",
                width="100%"
            ),
            width="100%"
        ),
        width="100%"
    )


def visualization_chart() -> rx.Component:
    """销量构成直方图组件 (Stacked Bar Chart)"""
    return rx.vstack(
        rx.vstack(
            rx.foreach(
                SalesState.chart_data,
                lambda item: rx.vstack(
                    rx.hstack(
                        rx.text(item.variant, size="1", weight="bold"),
                        rx.spacer(),
                        rx.badge(
                            rx.fragment(item.total_qty.to_string(), " 件"),
                            color_scheme="violet",
                            variant="soft",
                            size="1",
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.hstack(
                        rx.foreach(
                            item.platforms,
                            lambda plat: rx.tooltip(
                                rx.box(
                                    width=plat.pct_str,
                                    height="12px",
                                    background=plat.color,
                                    transition="all 0.15s ease",
                                    _hover={"opacity": 0.85, "transform": "scaleY(1.15)"},
                                ),
                                content=plat.name + ": " + plat.qty.to_string() + " 件",
                            )
                        ),
                        width="100%",
                        height="12px",
                        background="var(--slate-3)",
                        border_radius="6px",
                        overflow="hidden",
                        spacing="0",
                    ),
                    width="100%",
                    spacing="2",
                )
            ),
            width="100%",
            spacing="4",
            padding="0.5rem 0",
        ),
        padding="0.5rem",
        width="100%"
    )


def render_log_item(l: SalesLogItem) -> rx.Component:
    """渲染流水明细的单行"""
    # 动态确定变动数量的配色
    is_neg = (l.qty < 0)
    qty_color = rx.cond(is_neg, "red", "green")
    qty_prefix = rx.cond(is_neg, "", "+")
    
    return rx.table.row(
        rx.table.cell(rx.text(l.date, size="1")),
        rx.table.cell(rx.badge(l.type_label, color_scheme=rx.cond(l.type_label.contains("售出"), "green", "orange"), size="1")),
        rx.table.cell(rx.text(l.variant, size="1", weight="medium")),
        rx.table.cell(rx.badge(rx.fragment(qty_prefix, l.qty.to_string()), color_scheme=qty_color, size="1")),
        rx.table.cell(rx.text(l.platform, size="1")),
        rx.table.cell(rx.text(rx.fragment(l.amount.to_string(), " ", l.currency), size="1", weight="bold")),
    )


def paginated_logs_panel() -> rx.Component:
    """真分页销量流水明细记录面板"""
    return rx.vstack(
        rx.cond(
            SalesState.logs_is_empty,
            empty_state("该产品暂无历史销量变动流水"),
            rx.vstack(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("日期", size="1"),
                            rx.table.column_header_cell("类型", size="1"),
                            rx.table.column_header_cell("款式", size="1"),
                            rx.table.column_header_cell("数量", size="1"),
                            rx.table.column_header_cell("平台", size="1"),
                            rx.table.column_header_cell("金额明细", size="1"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(SalesState.logs, render_log_item)
                    ),
                    size="1",
                    width="100%"
                ),
                
                # 翻页按钮组件
                rx.cond(
                    SalesState.total_pages > 1,
                    rx.hstack(
                        rx.spacer(),
                        rx.hstack(
                            rx.button(
                                "⬅️ 上一页",
                                on_click=lambda: SalesState.change_log_page(-1),
                                disabled=(SalesState.page == 1),
                                size="1", variant="soft"
                            ),
                            rx.text(
                                rx.fragment("第 ", SalesState.page.to_string(), " / ", SalesState.total_pages.to_string(), " 页"),
                                size="1", color=rx.color("slate", 10), align="center", padding="0.25rem 0.5rem"
                            ),
                            rx.button(
                                "下一页 ➡️",
                                on_click=lambda: SalesState.change_log_page(1),
                                disabled=(SalesState.page == SalesState.total_pages),
                                size="1", variant="soft"
                            ),
                            spacing="2", align="center"
                        ),
                        rx.spacer(),
                        width="100%", padding_top="0.5rem"
                    ),
                    rx.fragment()
                ),
                width="100%"
            )
        ),
        width="100%"
    )


def sales_detail_panel() -> rx.Component:
    """右侧：🔍 产品销售多角度深入透视面板"""
    return rx.cond(
        ~SalesState.has_selected_product,
        rx.card(
            empty_state("请选择左侧热卖产品或在上方下拉选择产品开始深入分析", "search"),
            width="100%",
            height="100%"
        ),
        rx.card(
            rx.vstack(
                # 标题和产品切换
                rx.hstack(
                    rx.heading(rx.fragment("📦 ", SalesState.selected_product, " 销售深度详情"), size="4", weight="bold"),
                    rx.spacer(),
                    # 提供方便的产品切换
                    rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            rx.foreach(
                                SalesState.product_names_list,
                                lambda name: rx.select.item(name, value=name)
                            )
                        ),
                        placeholder="切换分析产品...",
                        value=SalesState.selected_product,
                        on_change=SalesState.select_product,
                        size="2",
                        style={"maxWidth": "220px"}
                    ),
                    width="100%",
                    align="center"
                ),
                
                # 选中商品的 3 个轻量高彩指标卡
                rx.grid(
                    sales_metric_card("净销量", SalesState.p_net_qty_str, color_scheme="green", icon="shopping_bag"),
                    sales_metric_card("折合销售额", SalesState.p_cny_equiv_str, color_scheme="violet", icon="banknote"),
                    sales_metric_card("活跃平台数", SalesState.p_active_platforms_str, color_scheme="blue", icon="globe"),
                    columns="3",
                    spacing="3",
                    width="100%"
                ),
                
                # 款式-平台交叉表
                rx.divider(),
                rx.heading("🧩 款式-平台 交叉销量透视", size="2", weight="bold"),
                pivot_analysis_table(),
                
                # 款式销量柱状图
                rx.divider(),
                rx.heading("📊 各款式平台销量分布直方图", size="2", weight="bold"),
                visualization_chart(),
                
                # 销量变动流水分页日志
                rx.divider(),
                rx.heading("📝 销售流转日志流水 (含退款及撤销记录)", size="2", weight="bold"),
                paginated_logs_panel(),
                
                spacing="4",
                width="100%"
            ),
            padding="0.75rem",
            width="100%"
        )
    )


def sales_page() -> rx.Component:
    """销售数据透视主页面入口"""
    return page_layout(
        rx.vstack(
            # Tab 控件
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("🚀 V2.0 订单系统精准版", value="v2"),
                    rx.tabs.trigger("🕰️ V1.0 历史兼容版", value="v1"),
                ),
                value=SalesState.active_tab,
                on_change=SalesState.set_tab,
                width="100%"
            ),
            
            # Tab 介绍信息
            rx.cond(
                SalesState.active_tab == "v2",
                rx.callout("💡 【精准订单模式】：数据仅来源于「销售订单」和「售后管理」。数据完全隔离，剔除了早期反推中的冗余重复，兼容了\u201c仅退款\u201d场景。(推荐使用)", icon="info", color_scheme="green", size="1", width="100%"),
                rx.callout("⚠️ 【历史兼容模式】：数据强行从底层的「物理库存变动日志」反向推演。包含无订单系统的早期历史脏数据，可能因物理入出库存在部分重复记录，仅供对账参考。", icon="triangle_alert", color_scheme="orange", size="1", width="100%")
            ),
            
            # 加载状态保护：避免 Recharts 在数据尚未就绪时渲染导致 React 崩溃
            rx.cond(
                SalesState.is_loading,
                rx.center(
                    rx.vstack(
                        rx.spinner(size="3"),
                        rx.text("正在加载销售数据...", size="2", color=rx.color("slate", 10)),
                        spacing="3",
                        align="center",
                    ),
                    padding="4rem",
                    width="100%",
                ),
                rx.vstack(
                    rx.grid(
                        sales_metric_card("纯 CNY 累计收款额", SalesState.total_cny_str, color_scheme="green", icon="dollar_sign", description="纯 CNY 货币的实际成交及收款总计"),
                        sales_metric_card("折合总销售额 (CNY总计)", SalesState.grand_total_cny_str, color_scheme="violet", icon="banknote", description="包含汇率折合后的全币种总销售额大项结算"),
                        sales_metric_card("累计销量总数", SalesState.total_qty_str, color_scheme="orange", icon="layers", description="全品类产品的实际累计净销售出库数总计"),
                        columns="3",
                        spacing="3",
                        width="100%"
                    ),
                    
                    rx.divider(),
                    
                    # 分栏大屏布局
                    rx.grid(
                        # 左侧：🏆 热销产品榜单
                        leaderboard_panel(),
                        # 右侧：🔍 产品销售多角度剖析
                        sales_detail_panel(),
                        columns="12",
                        spacing="4",
                        width="100%",
                        style={
                            "gridTemplateColumns": "4fr 8fr"
                        }
                    ),
                    
                    spacing="4",
                    width="100%"
                ),
            ),
            
            spacing="4",
            width="100%"
        ),
        title="📈 销售数据数据分析透视"
    )

# yurara_app/components/sidebar.py
"""
现代化侧边栏导航组件。
特性：玻璃拟态风格、活跃路由高亮、分组导航、底部工具区。
"""
import reflex as rx
from ..state.auth_state import AuthState
from ..state.app_state import AppState
from ..state.memo_state import MemoState

# --- 导航菜单定义 ---
NAV_ITEMS = [
    {
        "group": "财务管理",
        "items": [
            {"label": "财务流水录入", "icon": "circle_dollar_sign", "href": "/finance"},
            {"label": "公司账面概览", "icon": "clipboard_list", "href": "/balance"},
            {"label": "财务报表与分析", "icon": "chart_pie", "href": "/report"},
        ]
    },
    {
        "group": "商品管理",
        "items": [
            {"label": "商品管理", "icon": "package", "href": "/product"},
            {"label": "商品成本核算", "icon": "calculator", "href": "/cost"},
        ]
    },
    {
        "group": "销售管理",
        "items": [
            {"label": "线上销售管理", "icon": "shopping_cart", "href": "/sales-order"},
            {"label": "预售销售管理", "icon": "shopping_basket", "href": "/presale"},
            {"label": "线下销售管理", "icon": "store", "href": "/offline-sales"},
            {"label": "销售额一览", "icon": "trending_up", "href": "/sales"},
            {"label": "销售平台管理", "icon": "globe", "href": "/platforms"},
        ]
    },
    {
        "group": "仓储资产",
        "items": [
            {"label": "仓库库存管理", "icon": "arrow_left_right", "href": "/inventory"},
            {"label": "固定资产管理", "icon": "camera", "href": "/asset"},
            {"label": "其他资产管理", "icon": "box", "href": "/consumable"},
        ]
    },
]


def nav_item(label: str, icon: str, href: str) -> rx.Component:
    """单个导航项，带活跃状态高亮。"""
    expanded_item = rx.link(
        rx.hstack(
            rx.icon(icon, size=16, class_name="nav-icon"),
            rx.text(label, size="2"),
            spacing="2",
            align="center",
            width="100%",
        ),
        href=href,
        width="100%",
        class_name="nav-item",
        _hover={},  # 通过 CSS 处理 hover
    )
    
    collapsed_item = rx.tooltip(
        rx.link(
            rx.center(
                rx.icon(icon, size=16, class_name="nav-icon"),
                width="100%",
                height="32px",
            ),
            href=href,
            width="100%",
            class_name="nav-item",
            padding="6px 0",
            _hover={},
        ),
        content=label,
        side="right",
    )
    
    return rx.cond(
        AppState.sidebar_collapsed,
        collapsed_item,
        expanded_item,
    )


def nav_group(group: str, items: list) -> rx.Component:
    """导航分组。"""
    return rx.cond(
        AppState.sidebar_collapsed,
        rx.vstack(
            *[nav_item(**item) for item in items],
            spacing="1",
            width="100%",
            align_items="center",
            padding_bottom="0.75rem",
        ),
        rx.vstack(
            rx.text(
                group,
                size="1",
                weight="bold",
                class_name="nav-group-label",
            ),
            *[nav_item(**item) for item in items],
            spacing="1",
            width="100%",
            align_items="start",
            padding_bottom="0.75rem",
        )
    )


def memo_dialog() -> rx.Component:
    """备忘录详情弹窗组件。"""

    def memo_item_row(memo: dict) -> rx.Component:
        """单条备忘录的编辑行。"""
        return rx.vstack(
            rx.hstack(
                rx.icon("calendar", size=12, color=rx.color("violet", 9)),
                rx.input(
                    default_value=memo["date"],
                    placeholder="日期 (YYYY-MM-DD)",
                    size="1",
                    width="130px",
                    on_blur=lambda val: MemoState.update_memo_date(memo["id"], val),
                ),
                rx.spacer(),
                rx.icon_button(
                    rx.icon("trash_2", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    cursor="pointer",
                    on_click=MemoState.delete_memo(memo["id"]),
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.text_area(
                default_value=memo["content"],
                placeholder="在此输入备忘内容…",
                size="1",
                width="100%",
                min_height="60px",
                resize="vertical",
                on_blur=lambda val: MemoState.update_memo_content(memo["id"], val),
            ),
            rx.divider(),
            spacing="2",
            width="100%",
            padding_bottom="0.5rem",
        )

    return rx.dialog.root(
        rx.dialog.trigger(
            rx.fragment(),  # 触发器由 memo_preview_widget 控制
        ),
        rx.dialog.content(
            rx.vstack(
                # 顶部标题行
                rx.hstack(
                    rx.icon("notebook_pen", size=18, color=rx.color("violet", 9)),
                    rx.heading("📝 备忘录", size="3"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(
                            rx.icon("x", size=16),
                            variant="ghost",
                            color_scheme="gray",
                            cursor="pointer",
                            on_click=MemoState.close_memo_dialog,
                        )
                    ),
                    width="100%",
                    align="center",
                    margin_bottom="0.75rem",
                ),
                # 搜索框
                rx.hstack(
                    rx.icon("search", size=14, color=rx.color("slate", 9)),
                    rx.input(
                        placeholder="搜索备忘录内容或日期…",
                        value=MemoState.memo_search_query,
                        on_change=MemoState.set_memo_search_query,
                        size="1",
                        flex="1",
                    ),
                    rx.cond(
                        MemoState.memo_search_query != "",
                        rx.icon_button(
                            rx.icon("x", size=12),
                            size="1",
                            variant="ghost",
                            color_scheme="gray",
                            cursor="pointer",
                            on_click=MemoState.set_memo_search_query(""),
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                    padding="0.5rem 0.75rem",
                    background=rx.color("slate", 2),
                    border_radius="8px",
                    margin_bottom="0.75rem",
                ),
                # 备忘录列表
                rx.scroll_area(
                    rx.cond(
                        MemoState.has_memos,
                        rx.vstack(
                            rx.foreach(MemoState.filtered_memos, memo_item_row),
                            spacing="1",
                            width="100%",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("notebook", size=32, color=rx.color("slate", 6)),
                                rx.text("暂无备忘录", size="2", color=rx.color("slate", 9)),
                                rx.text("点击下方按钮新增第一条备忘录", size="1", color=rx.color("slate", 8)),
                                spacing="2",
                                align="center",
                            ),
                            padding="2rem",
                            width="100%",
                        ),
                    ),
                    scrollbars="vertical",
                    max_height="55vh",
                    width="100%",
                ),
                # 底部新增按钮
                rx.divider(margin_y="0.5rem"),
                rx.button(
                    rx.hstack(
                        rx.icon("plus", size=14),
                        rx.text("新增备忘录", size="1"),
                        spacing="2",
                        align="center",
                    ),
                    variant="soft",
                    color_scheme="violet",
                    width="100%",
                    cursor="pointer",
                    on_click=MemoState.add_memo,
                ),
                spacing="0",
                width="100%",
            ),
            style={"maxWidth": "520px", "width": "90vw"},
        ),
        open=MemoState.memo_dialog_open,
        on_open_change=MemoState.close_memo_dialog,
    )


def memo_preview_widget() -> rx.Component:
    """侧边栏中的备忘录预览组件。展开时显示最新备忘录预览；收起时显示图标按钮。"""
    # 收起状态：只显示图标按钮
    collapsed_btn = rx.center(
        rx.tooltip(
            rx.icon_button(
                rx.icon("notebook_pen", size=16),
                variant="ghost",
                color_scheme="violet",
                cursor="pointer",
                on_click=MemoState.open_memo_dialog,
            ),
            content="备忘录",
            side="right",
        ),
        width="100%",
    )

    # 展开状态：标题行 + 预览内容卡片
    expanded_widget = rx.vstack(
        # 标题行
        rx.hstack(
            rx.icon("notebook_pen", size=13, color=rx.color("violet", 9)),
            rx.text("备忘录", size="1", weight="bold", color=rx.color("slate", 10)),
            rx.spacer(),
            rx.icon_button(
                rx.icon("pencil", size=12),
                size="1",
                variant="ghost",
                color_scheme="violet",
                cursor="pointer",
                on_click=MemoState.open_memo_dialog,
            ),
            spacing="1",
            align="center",
            width="100%",
        ),
        # 预览内容区（固定高度 2 行）
        rx.box(
            rx.text(
                MemoState.latest_memo_preview,
                size="1",
                color=rx.color("slate", 10),
                style={
                    "display": "-webkit-box",
                    "WebkitLineClamp": "2",
                    "WebkitBoxOrient": "vertical",
                    "overflow": "hidden",
                    "lineHeight": "1.4",
                    "wordBreak": "break-all",
                },
            ),
            width="100%",
            cursor="pointer",
            on_click=MemoState.open_memo_dialog,
            _hover={"opacity": "0.8"},
        ),
        spacing="1",
        width="100%",
        padding="0.75rem",
        background=rx.color("slate", 2),
        border_radius="8px",
        border=f"1px solid {rx.color('violet', 4)}",
    )

    return rx.cond(
        AppState.sidebar_collapsed,
        collapsed_btn,
        expanded_widget,
    )


def exchange_rate_widget() -> rx.Component:
    """多货币汇率展示面板 - 展开版（侧边栏收起时不显示，收起时直接使用 view_rates_button）。"""
    
    def rate_row_readonly(rate_info: dict) -> rx.Component:
        currency = rate_info["currency"]
        rate_str = rate_info["rate_str"]
        return rx.hstack(
            rx.text(
                f"100 {currency} =",
                size="1",
                color=rx.color("slate", 10),
                min_width="70px",
            ),
            rx.text(
                f"{rate_str} CNY",
                size="1",
                weight="medium",
                color=rx.color("slate", 11),
            ),
            spacing="1",
            align="center",
            width="100%",
        )

    return rx.cond(
        AppState.sidebar_collapsed,
        rx.fragment(),
        rx.vstack(
            rx.hstack(
                rx.icon("refresh_cw", size=13),
                rx.text("全局汇率", size="1", weight="bold"),
                spacing="1",
                align="center",
                color=rx.color("slate", 10),
                width="100%",
            ),
            rx.foreach(AppState.sorted_rates, rate_row_readonly),
            spacing="1",
            width="100%",
            padding="0.75rem",
            background=rx.color("slate", 2),
            border_radius="8px",
        )
    )



def test_mode_toggle(collapsed: bool = False) -> rx.Component:
    """测试模式切换。"""
    expanded_toggle = rx.hstack(
        rx.cond(
            AppState.test_mode,
            rx.badge("🧪 测试模式", color_scheme="orange", variant="soft"),
            rx.badge("🟢 正式环境", color_scheme="green", variant="soft"),
        ),
        rx.switch(
            checked=AppState.test_mode,
            on_change=AppState.toggle_test_mode,
            size="1",
            color_scheme="orange",
        ),
        spacing="2",
        align="center",
        width="100%",
        justify="between",
    )

    collapsed_toggle = rx.center(
        rx.tooltip(
            rx.switch(
                checked=AppState.test_mode,
                on_change=AppState.toggle_test_mode,
                size="1",
                color_scheme="orange",
            ),
            content=rx.cond(
                AppState.test_mode,
                "当前：测试模式 (点击切换)",
                "当前：正式环境 (点击切换)",
            ),
            side="right",
        ),
        width="100%",
    )

    return collapsed_toggle if collapsed else expanded_toggle


def _data_management_popover_content() -> rx.Component:
    """数据管理弹出面板的内容（复用于展开/收起两种触发器）。"""
    return rx.popover.content(
        rx.vstack(
            # === 备份区域 ===
            rx.heading("💾 数据备份与恢复", size="2"),
            rx.text("下载或导入本系统所有的业务数据。", size="1", color=rx.color("slate", 9)),

            rx.button(
                rx.icon("download", size=13),
                "下载全量备份 (ZIP)",
                on_click=AppState.download_backup_zip,
                color_scheme="green",
                width="100%",
                size="1",
            ),

            rx.divider(margin_y="0.25rem"),

            # === 恢复区域 ===
            rx.text("恢复/导入备份 ZIP:", size="1", weight="bold"),
            rx.upload(
                rx.center(
                    rx.vstack(
                        rx.icon("cloud_upload", size=16, color=rx.color("slate", 9)),
                        rx.text("拖拽 ZIP 文件至此或点击选择", size="1", color=rx.color("slate", 9)),
                        spacing="1",
                    )
                ),
                id="backup_upload",
                border=f"1px dashed {rx.color('slate', 5)}",
                padding="0.75rem",
                border_radius="6px",
                width="100%",
            ),

            rx.button(
                "🔴 确认导入并覆盖",
                on_click=AppState.handle_backup_restore(
                    rx.upload_files(upload_id="backup_upload")
                ),
                color_scheme="red",
                width="100%",
                size="1",
            ),

            rx.divider(margin_y="0.25rem"),

            # === 危险操作：清空 ===
            rx.heading("💣 危险：环境清空", size="2", color_scheme="red"),
            rx.text(
                rx.fragment("⚠️ 此操作将彻底删除【", AppState.env_label, "】的所有业务数据且无法撤销！"),
                size="1",
                color=rx.color("red", 10),
            ),

            rx.input(
                placeholder="请输入 DELETE 以确认",
                value=AppState.delete_confirm_code,
                on_change=AppState.set_delete_confirm_code,
                size="1",
                width="100%",
            ),

            rx.button(
                "确认清空所有数据",
                on_click=AppState.clear_environment_data,
                disabled=AppState.delete_confirm_code != "DELETE",
                color_scheme="red",
                width="100%",
                size="1",
            ),

            spacing="3",
            width="200px",
        ),
        style={"maxWidth": "220px"},
    )


def data_management_popover() -> rx.Component:
    """全局数据备份与恢复、清空的弹出控制面板。"""
    # 收起状态：图标按钮触发
    collapsed_popover = rx.popover.root(
        rx.popover.trigger(
            rx.tooltip(
                rx.icon_button(
                    rx.icon("database", size=16),
                    variant="soft",
                    color_scheme="violet",
                    cursor="pointer",
                ),
                content="数据管理与备份",
                side="right",
            ),
        ),
        _data_management_popover_content(),
    )

    # 展开状态：文字按钮触发
    expanded_popover = rx.popover.root(
        rx.popover.trigger(
            rx.button(
                rx.hstack(
                    rx.icon("database", size=14),
                    rx.text("数据管理与备份", size="1"),
                    spacing="2",
                    align="center",
                ),
                variant="soft",
                color_scheme="violet",
                width="100%",
                cursor="pointer",
            ),
        ),
        _data_management_popover_content(),
    )

    return rx.cond(
        AppState.sidebar_collapsed,
        collapsed_popover,
        expanded_popover,
    )


def view_rates_button(collapsed: bool) -> rx.Component:
    """查看全局汇率的按钮，点开显示对话框。"""
    dialog_content = rx.dialog.content(
        rx.hstack(
            rx.heading("🌐 全局登记汇率看板", size="3"),
            rx.spacer(),
            rx.dialog.close(
                rx.icon_button(rx.icon("x", size=16), variant="ghost", color_scheme="gray", cursor="pointer")
            ),
            width="100%",
            align="center",
            margin_bottom="1rem",
        ),
        rx.text(
            "您可以在这里管理所有已登记的币种汇率。修改输入框后光标离开 (Blur) 即可自动保存，也可以点击下方按钮从 Google Finance 同步最新汇率。",
            size="1",
            color=rx.color("slate", 9),
            margin_bottom="1.5rem",
        ),
        
        # 汇率管理表格
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("货币代号", size="1"),
                    rx.table.column_header_cell("汇率 (100单位 = X CNY)", size="1"),
                    rx.table.column_header_cell("逆向折算 (1 CNY)", size="1"),
                    rx.table.column_header_cell("操作", size="1"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    AppState.sorted_rates,
                    lambda rate: rx.table.row(
                        rx.table.cell(rx.badge(rate["currency"], color_scheme="violet", variant="soft", size="2")),
                        rx.table.cell(
                            rx.hstack(
                                rx.input(
                                    key=f"input_{rate['currency']}_{rate['rate_str']}",
                                    default_value=rate["rate_str"],
                                    type="number",
                                    size="1",
                                    width="85px",
                                    on_blur=lambda val: AppState.set_currency_rate(rate["currency"], val),
                                ),

                                rx.text("CNY", size="1", color=rx.color("slate", 10)),
                                spacing="1",
                                align="center",
                            )
                        ),
                        rx.table.cell(rx.text(rate["reverse_rate_str"], " ", rate["currency"], size="2")),
                        rx.table.cell(
                            rx.cond(
                                rate["currency"] != "JPY",
                                rx.icon_button(
                                    rx.icon("trash_2", size=12),
                                    size="1",
                                    variant="ghost",
                                    color_scheme="red",
                                    cursor="pointer",
                                    on_click=AppState.remove_currency_rate(rate["currency"]),
                                ),
                                rx.fragment()
                            )
                        ),
                    )
                )
            ),
            size="2",
            width="100%",
            margin_bottom="1.5rem",
        ),
        
        rx.divider(margin_y="1rem"),
        
        # 底部操作区：新增货币与一键获取
        rx.vstack(
            rx.text("➕ 登记新增货币：", size="1", weight="bold", color=rx.color("slate", 10)),
            rx.hstack(
                rx.input(
                    placeholder="例如: USD",
                    size="2",
                    width="110px",
                    value=AppState.new_currency_code,
                    on_change=AppState.set_new_currency_code,
                ),
                rx.input(
                    placeholder="100单位外币兑 CNY 汇率",
                    type="number",
                    size="2",
                    flex="1",
                    value=AppState.new_currency_rate,
                    on_change=AppState.set_new_currency_rate,
                ),
                rx.icon_button(
                    rx.icon("plus", size=16),
                    size="2",
                    variant="solid",
                    color_scheme="green",
                    cursor="pointer",
                    on_click=AppState.add_new_currency_from_dialog,
                ),

                spacing="2",
                width="100%",
                align="center",
            ),
            rx.divider(margin_y="0.5rem"),
            rx.button(
                rx.cond(
                    AppState.rates_fetching,
                    rx.spinner(size="1"),
                    rx.hstack(
                        rx.icon("globe", size=14),
                        rx.text("从 Google Finance 同步更新所有登记汇率", size="1"),
                        spacing="2",
                        align="center",
                    ),
                ),
                size="2",
                variant="soft",
                color_scheme="blue",
                width="100%",
                cursor="pointer",
                on_click=AppState.fetch_live_rates,
                disabled=AppState.rates_fetching,
            ),
            spacing="3",
            width="100%",
        ),

        rx.divider(margin_y="1rem"),

        # ── 汇率计算器 ──
        rx.vstack(
            rx.hstack(
                rx.icon("calculator", size=14, color=rx.color("violet", 9)),
                rx.text("汇率计算器", size="1", weight="bold", color=rx.color("slate", 10)),
                spacing="1",
                align="center",
            ),
            rx.hstack(
                # 输入金额
                rx.input(
                    value=AppState.calc_amount,
                    on_change=AppState.set_calc_amount,
                    type="number",
                    size="2",
                    width="110px",
                    placeholder="金额",
                ),
                # 源币种
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            AppState.calc_currencies,
                            lambda c: rx.select.item(c, value=c),
                        )
                    ),
                    value=AppState.calc_from,
                    on_change=AppState.set_calc_from,
                    size="2",
                    width="90px",
                ),
                # 换向按钮
                rx.tooltip(
                    rx.icon_button(
                        rx.icon("arrow_left_right", size=14),
                        on_click=AppState.swap_calc_currencies,
                        variant="soft",
                        color_scheme="violet",
                        size="2",
                        cursor="pointer",
                    ),
                    content="交换币种方向",
                    side="top",
                ),
                # 目标币种
                rx.select.root(
                    rx.select.trigger(),
                    rx.select.content(
                        rx.foreach(
                            AppState.calc_currencies,
                            lambda c: rx.select.item(c, value=c),
                        )
                    ),
                    value=AppState.calc_to,
                    on_change=AppState.set_calc_to,
                    size="2",
                    width="90px",
                ),
                spacing="2",
                align="center",
                width="100%",
                flex_wrap="wrap",
            ),
            # 计算结果展示
            rx.hstack(
                rx.text("=", size="2", color=rx.color("slate", 9), weight="bold"),
                rx.text(
                    AppState.calc_result,
                    size="4",
                    weight="bold",
                    color=rx.color("violet", 11),
                ),
                spacing="2",
                align="center",
                padding="0.5rem 0.75rem",
                background=rx.color("violet", 2),
                border_radius="8px",
                width="100%",
            ),
            spacing="2",
            width="100%",
            padding="0.75rem",
            background=rx.color("slate", 2),
            border_radius="8px",
        ),

        style={"maxWidth": "540px"},

    )

    btn = rx.cond(
        collapsed,
        rx.dialog.root(
            rx.dialog.trigger(
                rx.tooltip(
                    rx.icon_button(
                        rx.icon("eye", size=16),
                        variant="outline",
                        color_scheme="gray",
                        cursor="pointer",
                    ),
                    content="查看与管理汇率",
                    side="right",
                )
            ),
            dialog_content,
        ),
        rx.dialog.root(
            rx.dialog.trigger(
                rx.button(
                    rx.hstack(
                        rx.icon("eye", size=14),
                        rx.text("查看全部与管理汇率", size="1"),
                        spacing="2",
                        align="center",
                    ),
                    variant="outline",
                    color_scheme="gray",
                    width="100%",
                    cursor="pointer",
                )
            ),
            dialog_content,
        )
    )
    return btn



def sidebar_bottom_toolbar() -> rx.Component:
    """侧边栏底部工具栏：左侧主题切换按钮 + 右侧折叠按钮。"""

    # ── 展开状态布局：左侧主题 | spacer | 右侧折叠 ──
    expanded_bar = rx.hstack(
        rx.tooltip(
            rx.icon_button(
                rx.color_mode_cond(
                    rx.icon("moon", size=15),
                    rx.icon("sun", size=15),
                ),
                on_click=rx.toggle_color_mode,
                variant="ghost",
                color_scheme="gray",
                cursor="pointer",
            ),
            content="切换主题",
            side="top",
        ),
        rx.spacer(),
        rx.tooltip(
            rx.icon_button(
                rx.icon("chevron_left", size=16),
                on_click=AppState.toggle_sidebar,
                variant="ghost",
                color_scheme="gray",
                cursor="pointer",
            ),
            content="收起侧边栏",
            side="top",
        ),
        width="100%",
        padding="0.5rem 0.75rem",
        align="center",
    )

    # ── 收起状态布局：主题按钮居中 + 折叠按钮居中 ──
    collapsed_bar = rx.vstack(
        rx.center(
            rx.tooltip(
                rx.icon_button(
                    rx.color_mode_cond(
                        rx.icon("moon", size=15),
                        rx.icon("sun", size=15),
                    ),
                    on_click=rx.toggle_color_mode,
                    variant="ghost",
                    color_scheme="gray",
                    cursor="pointer",
                ),
                content="切换主题",
                side="right",
            ),
            width="100%",
        ),
        rx.center(
            rx.tooltip(
                rx.icon_button(
                    rx.icon("chevron_right", size=16),
                    on_click=AppState.toggle_sidebar,
                    variant="ghost",
                    color_scheme="gray",
                    cursor="pointer",
                ),
                content="展开侧边栏",
                side="right",
            ),
            width="100%",
        ),
        spacing="1",
        padding="0.5rem 0",
        width="100%",
    )

    return rx.cond(
        AppState.sidebar_collapsed,
        collapsed_bar,
        expanded_bar,
    )



def sidebar() -> rx.Component:
    """主侧边栏组件。"""
    return rx.box(
        # === 顶部 Logo 区域 ===
        rx.cond(
            AppState.sidebar_collapsed,
            rx.vstack(
                rx.center(
                    rx.box(
                        rx.text("Y", weight="bold", size="5", color="white"),
                        width="32px",
                        height="32px",
                        background="linear-gradient(135deg, #6366f1, #8b5cf6)",
                        border_radius="8px",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                    ),
                    width="100%",
                    padding="1rem 0",
                ),
                rx.divider(margin="0"),
                spacing="0",
                width="100%",
            ),
            rx.vstack(
                rx.hstack(
                    rx.box(
                        rx.text("Y", weight="bold", size="5", color="white"),
                        width="32px",
                        height="32px",
                        background="linear-gradient(135deg, #6366f1, #8b5cf6)",
                        border_radius="8px",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                    ),
                    rx.vstack(
                        rx.text("Yurara Studio", weight="bold", size="3"),
                        rx.text("综合管理系统", size="1", color=rx.color("slate", 10)),
                        spacing="0",
                        align_items="start",
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                    padding="1rem 1.25rem",
                ),
                rx.divider(margin="0"),
                spacing="0",
                width="100%",
            )
        ),

        # === 用户信息栏 ===
        rx.cond(
            AppState.sidebar_collapsed,
            rx.vstack(
                rx.tooltip(
                    rx.avatar(
                        fallback=AuthState.current_user_initial,
                        size="1",
                        radius="full",
                        color_scheme="violet",
                    ),
                    content=AuthState.current_user,
                    side="right",
                ),
                rx.tooltip(
                    rx.icon_button(
                        rx.icon("log_out", size=14),
                        on_click=AuthState.logout,
                        variant="ghost",
                        size="1",
                        color_scheme="red",
                    ),
                    content="退出登录",
                    side="right",
                ),
                spacing="2",
                align="center",
                width="100%",
                padding="0.75rem 0",
            ),
            rx.hstack(
                rx.avatar(
                    fallback=AuthState.current_user_initial,
                    size="1",
                    radius="full",
                    color_scheme="violet",
                ),
                rx.vstack(
                    rx.text(AuthState.current_user, size="2", weight="medium"),
                    rx.text("管理员", size="1", color=rx.color("slate", 10)),
                    spacing="0",
                    align_items="start",
                ),
                rx.spacer(),
                rx.tooltip(
                    rx.icon_button(
                        rx.icon("log_out", size=14),
                        on_click=AuthState.logout,
                        variant="ghost",
                        size="1",
                        color_scheme="red",
                    ),
                    content="退出登录",
                ),
                spacing="2",
                align="center",
                width="100%",
                padding="0.75rem 1rem",
            )
        ),

        rx.divider(margin="0"),

        # === 测试模式警告 ===
        rx.cond(
            AppState.test_mode,
            rx.cond(
                AppState.sidebar_collapsed,
                rx.center(
                    rx.tooltip(
                        rx.icon(
                            "triangle_alert",
                            color=rx.color("orange", 10),
                            size=18,
                        ),
                        content="测试模式已开启，操作不影响线上数据",
                        side="right",
                    ),
                    width="100%",
                    padding="0.5rem 0",
                ),
                rx.callout(
                    "测试模式已开启，操作不影响线上数据",
                    icon="triangle_alert",
                    color_scheme="orange",
                    size="1",
                    margin="0.5rem",
                ),
            ),
            rx.fragment(),
        ),

        # === 主导航区域 ===
        rx.scroll_area(
            rx.cond(
                AppState.sidebar_collapsed,
                rx.vstack(
                    *[nav_group(**grp) for grp in NAV_ITEMS],
                    spacing="0",
                    width="100%",
                    padding="0.75rem 0",
                    align_items="center",
                ),
                rx.vstack(
                    *[nav_group(**grp) for grp in NAV_ITEMS],
                    spacing="0",
                    width="100%",
                    padding="0.75rem",
                    align_items="start",
                ),
            ),
            flex="1",
            overflow_y="auto",
        ),

        rx.divider(margin="0"),

        # === 底部工具区 ===
        rx.cond(
            AppState.sidebar_collapsed,
            rx.vstack(
                memo_dialog(),
                memo_preview_widget(),
                rx.divider(margin="0", width="60%"),
                exchange_rate_widget(),
                view_rates_button(collapsed=True),
                test_mode_toggle(collapsed=True),
                data_management_popover(),
                rx.divider(margin="0"),
                sidebar_bottom_toolbar(),
                spacing="3",
                padding="0.75rem 0",
                width="100%",
                align_items="center",
            ),
            rx.vstack(
                memo_dialog(),
                memo_preview_widget(),
                rx.divider(margin="0"),
                exchange_rate_widget(),
                view_rates_button(collapsed=False),
                test_mode_toggle(collapsed=False),
                data_management_popover(),
                rx.divider(margin="0"),
                sidebar_bottom_toolbar(),
                spacing="2",
                padding="0.75rem",
                width="100%",
            ),
        ),

        # === 侧边栏容器样式 ===
        display="flex",
        flex_direction="column",
        height="100vh",
        width=rx.cond(AppState.sidebar_collapsed, "68px", "240px"),
        min_width=rx.cond(AppState.sidebar_collapsed, "68px", "240px"),
        background=rx.color("slate", 1),
        border_right=f"1px solid {rx.color('slate', 4)}",
        position="sticky",
        top="0",
        overflow="hidden",
        style={"transition": "width 0.2s ease, min-width 0.2s ease"},
    )

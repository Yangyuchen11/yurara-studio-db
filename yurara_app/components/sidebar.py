# yurara_app/components/sidebar.py
"""
现代化侧边栏导航组件。
特性：玻璃拟态风格、活跃路由高亮、分组导航、底部工具区。
"""
import reflex as rx
from ..state.auth_state import AuthState
from ..state.app_state import AppState

# --- 导航菜单定义 ---
NAV_ITEMS = [
    {
        "group": "财务管理",
        "items": [
            {"label": "财务流水录入", "icon": "circle-dollar-sign", "href": "/finance"},
            {"label": "公司账面概览", "icon": "clipboard-list", "href": "/balance"},
            {"label": "财务报表与分析", "icon": "chart-pie", "href": "/report"},
        ]
    },
    {
        "group": "商品管理",
        "items": [
            {"label": "商品管理", "icon": "package-heart", "href": "/product"},
            {"label": "商品成本核算", "icon": "calculator", "href": "/cost"},
        ]
    },
    {
        "group": "销售管理",
        "items": [
            {"label": "线上销售管理", "icon": "shopping-cart", "href": "/sales-order"},
            {"label": "预售销售管理", "icon": "shopping-basket", "href": "/presale"},
            {"label": "线下销售管理", "icon": "store", "href": "/offline-sales"},
            {"label": "销售额一览", "icon": "trending-up", "href": "/sales"},
        ]
    },
    {
        "group": "仓储资产",
        "items": [
            {"label": "仓库库存管理", "icon": "arrow-left-right", "href": "/inventory"},
            {"label": "固定资产管理", "icon": "camera", "href": "/asset"},
            {"label": "其他资产管理", "icon": "box", "href": "/consumable"},
        ]
    },
]


def nav_item(label: str, icon: str, href: str) -> rx.Component:
    """单个导航项，带活跃状态高亮。"""
    return rx.link(
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


def nav_group(group: str, items: list) -> rx.Component:
    """导航分组。"""
    return rx.vstack(
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


def exchange_rate_widget() -> rx.Component:
    """汇率设置小组件。"""
    return rx.vstack(
        rx.hstack(
            rx.icon("refresh-cw", size=13),
            rx.text("全局汇率", size="1", weight="bold"),
            spacing="1",
            color=rx.color("slate", 10),
        ),
        rx.hstack(
            rx.text("100 JPY =", size="1", color=rx.color("slate", 10)),
            rx.input(
                default_value=AppState.exchange_rate_100.to_string(),
                type="number",
                size="1",
                width="70px",
                on_blur=lambda v: AppState.set_exchange_rate(float(v)),
            ),
            rx.text("CNY", size="1", color=rx.color("slate", 10)),
            spacing="1",
            align="center",
        ),
        spacing="1",
        width="100%",
        padding="0.75rem",
        background=rx.color("slate", 2),
        border_radius="8px",
    )


def test_mode_toggle() -> rx.Component:
    """测试模式切换。"""
    return rx.hstack(
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


def sidebar() -> rx.Component:
    """主侧边栏组件。"""
    return rx.box(
        # === 顶部 Logo 区域 ===
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
        ),

        # === 用户信息栏 ===
        rx.hstack(
            rx.avatar(
                fallback=AuthState.current_user[:1].upper(),
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
                    rx.icon("log-out", size=14),
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
        ),

        rx.divider(margin="0"),

        # === 测试模式警告 ===
        rx.cond(
            AppState.test_mode,
            rx.callout(
                "测试模式已开启，操作不影响线上数据",
                icon="triangle-alert",
                color_scheme="orange",
                size="1",
                margin="0.5rem",
            ),
            rx.fragment(),
        ),

        # === 主导航区域 ===
        rx.scroll_area(
            rx.vstack(
                *[nav_group(**grp) for grp in NAV_ITEMS],
                spacing="0",
                width="100%",
                padding="0.75rem",
                align_items="start",
            ),
            flex="1",
            overflow_y="auto",
        ),

        rx.divider(margin="0"),

        # === 底部工具区 ===
        rx.vstack(
            exchange_rate_widget(),
            rx.box(height="0.5rem"),
            test_mode_toggle(),
            spacing="2",
            padding="0.75rem",
            width="100%",
        ),

        # === 侧边栏容器样式 ===
        display="flex",
        flex_direction="column",
        height="100vh",
        width="240px",
        min_width="240px",
        background=rx.color("slate", 1),
        border_right=f"1px solid {rx.color('slate', 4)}",
        position="sticky",
        top="0",
        overflow="hidden",
    )

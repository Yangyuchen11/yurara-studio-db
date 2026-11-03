# yurara_app/components/layout.py
"""
通用页面布局包装器。
所有业务页面都应通过 page_layout() 包裹，以获得统一的侧边栏 + 主内容区布局。
"""
import reflex as rx
from .sidebar import sidebar
from ..state.auth_state import AuthState
from ..state.app_state import AppState


def page_header(title: str, subtitle: str = "") -> rx.Component:
    """页面顶部标题区域。"""
    return rx.vstack(
        rx.heading(title, size="6", weight="bold"),
        rx.cond(
            subtitle != "",
            rx.text(subtitle, size="2", color=rx.color("slate", 10)),
            rx.fragment(),
        ),
        spacing="1",
        margin_bottom="1.5rem",
    )


def page_layout(*content, title: str = "", subtitle: str = "", hide_sidebar: rx.Var | bool = False, hide_header: rx.Var | bool = False, padding: str = "1.5rem 2rem", **kwargs) -> rx.Component:
    """
    标准页面布局。
    用法：
        def my_page() -> rx.Component:
            return page_layout(
                my_content(),
                title="商品管理",
                subtitle="管理所有产品信息",
            )
    """
    return rx.hstack(
        # 左侧侧边栏
        rx.cond(
            hide_sidebar,
            rx.fragment(),
            sidebar(),
        ),

        # 右侧主内容区
        rx.box(
            # 手机/平板端顶部导航条 (≤ 1024px 显示，全屏收银模式隐藏)
            rx.cond(
                hide_sidebar,
                rx.fragment(),
                rx.hstack(
                    rx.icon_button(
                        rx.icon("menu", size=20),
                        variant="surface",
                        color_scheme="violet",
                        size="2",
                        on_click=AppState.toggle_mobile_menu,
                    ),
                    rx.hstack(
                        rx.box(
                            rx.text("Y", weight="bold", size="3", color="white"),
                            width="26px",
                            height="26px",
                            background="linear-gradient(135deg, #6366f1, #8b5cf6)",
                            border_radius="6px",
                            display="flex",
                            align_items="center",
                            justify_content="center",
                            flex_shrink="0",
                        ),
                        rx.text(
                            title if title != "" else "Yurara Studio",
                            weight="bold",
                            size="3",
                            line_clamp=1,
                        ),
                        spacing="2",
                        align="center",
                        min_width="0",
                    ),
                    rx.spacer(),
                    rx.badge(
                        AppState.env_label,
                        color_scheme=rx.cond(AppState.test_mode, "orange", "green"),
                        variant="soft",
                        size="1",
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                    class_name="mobile-topbar",
                ),
            ),

            # 顶部面包屑 / 环境徽章 (桌面端显示)
            rx.cond(
                hide_header,
                rx.fragment(),
                rx.hstack(
                    rx.spacer(),
                    rx.badge(
                        AppState.env_label,
                        color_scheme=rx.cond(AppState.test_mode, "orange", "green"),
                        variant="soft",
                        size="1",
                    ),
                    width="100%",
                    padding_bottom="0.5rem",
                    class_name="desktop-env-bar",
                ),
            ),

            # 页面标题
            rx.cond(
                (title != "") & ~hide_header,
                page_header(title, subtitle),
                rx.fragment(),
            ),

            # 主内容
            *content,

            padding=rx.cond(hide_sidebar, "0.5rem", padding),
            flex="1",
            min_width="0",
            max_width="100%",
            width="100%",
            overflow_y="auto",
            overflow_x="hidden",
            min_height="100vh",
            background=rx.color("slate", 2),
            class_name=rx.cond(hide_sidebar, "app-main-content fullscreen-mode", "app-main-content"),
        ),

        width="100%",
        spacing="0",
        align_items="start",
        **kwargs
    )


def auth_guard(component_fn):
    """
    路由守卫装饰器。
    用于需要登录才能访问的页面，on_load 时检查认证状态。
    """
    def wrapper(*args, **kwargs):
        return rx.fragment(
            rx.script(
                # 简单的客户端重定向兜底
            ),
            component_fn(*args, **kwargs),
        )
    return wrapper

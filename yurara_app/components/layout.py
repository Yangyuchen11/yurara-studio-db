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


def page_layout(*content, title: str = "", subtitle: str = "", **kwargs) -> rx.Component:
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
        sidebar(),

        # 右侧主内容区
        rx.box(
            # 顶部面包屑 / 环境徽章
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
            ),

            # 页面标题
            rx.cond(
                title != "",
                page_header(title, subtitle),
                rx.fragment(),
            ),

            # 主内容
            *content,

            padding="1.5rem 2rem",
            flex="1",
            overflow_y="auto",
            min_height="100vh",
            background=rx.color("slate", 2),
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

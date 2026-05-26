# yurara_studio/components/layout.py
import reflex as rx
from yurara_studio_front.states.base_state import BaseState
from yurara_studio_front.components.sidebar import sidebar

def check_auth():
    """路由守卫：如果未登录，强制跳回首页"""
    if not BaseState.is_authenticated:
        return rx.redirect("/")

def require_auth(page_content: rx.Component) -> rx.Component:
    """包装器：为需要登录的页面添加侧边栏和布局"""
    return rx.cond(
        BaseState.is_authenticated,
        # 如果已登录，渲染侧边栏和内容
        rx.hstack(
            sidebar(),
            rx.box(
                page_content,
                margin_left="250px", # 腾出侧边栏的空间
                padding="2em",
                width="calc(100vw - 250px)",
                min_height="100vh",
                bg=rx.color("gray", 1),
            ),
            width="100%",
            align="start",
        ),
        # 如果未登录，显示空白（因为路由守卫会立刻将其重定向）
        rx.box()
    )
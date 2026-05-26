# yurara_studio/components/sidebar.py
import reflex as rx
from yurara_studio_front.states.base_state import BaseState

def sidebar_item(text: str, icon: str, url: str) -> rx.Component:
    """生成单个侧边栏菜单项"""
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=20),
            rx.text(text, size="3"),
            width="100%",
            padding_x="1em",
            padding_y="0.8em",
            align="center",
            style={
                "_hover": {
                    "bg": rx.color("accent", 3), 
                    "color": rx.color("accent", 11),
                    "border_radius": "8px",
                }
            },
        ),
        href=url,
        underline="none",
        color=rx.color("gray", 11),
        width="100%",
    )

def sidebar() -> rx.Component:
    """侧边栏主组件"""
    return rx.vstack(
        # 顶部 Logo 区域
        rx.hstack(
            rx.icon("layers", size=28, color=rx.color("accent", 9)),
            rx.heading("Yurara Studio", size="5"),
            align="center",
            padding_bottom="1.5em",
            padding_top="1em",
            width="100%"
        ),
        # 菜单列表
        rx.vstack(
            sidebar_item("控制台首页", "layout-dashboard", "/dashboard"),
            sidebar_item("财务流水录入", "banknote", "/finance"),
            sidebar_item("公司账面概览", "wallet", "/balance"),
            sidebar_item("商品管理", "package", "/products"),
            sidebar_item("商品成本核算", "calculator", "/costs"),
            width="100%",
            spacing="1",
        ),
        rx.spacer(), # 将底部用户信息推到最下边
        
        # 底部用户信息和操作区
        rx.vstack(
            rx.text(f"当前账号: {BaseState.current_user}", size="2", color=rx.color("gray", 8)),
            rx.button("退出登录", on_click=BaseState.logout, variant="outline", width="100%", color_scheme="red"),
            width="100%",
            border_top=f"1px solid {rx.color('gray', 4)}",
            padding_top="1em",
        ),
        # 侧边栏整体样式：固定在左侧
        width="250px",
        height="100vh",
        bg=rx.color("gray", 2),
        padding="1em",
        border_right=f"1px solid {rx.color('gray', 4)}",
        position="fixed",
        left="0px",
        top="0px",
        z_index="5",
    )
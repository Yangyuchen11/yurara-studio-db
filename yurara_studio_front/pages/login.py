# yurara_studio/pages/login.py
import reflex as rx
from yurara_studio_front.states.base_state import BaseState

def login_page() -> rx.Component:
    return rx.center(
        rx.card(
            rx.vstack(
                rx.center(
                    rx.icon("lock", size=40, color=rx.color("accent", 9)),
                    rx.heading("Yurara Studio", size="6"),
                    rx.text("ERP 综合管理系统", size="3", color=rx.color("gray", 11)),
                    direction="column",
                    spacing="2",
                    padding_bottom="1em",
                ),
                # 表单组件
                rx.form.root(
                    rx.vstack(
                        rx.input(name="username", placeholder="用户名", required=True, size="3"),
                        rx.input(name="password", type="password", placeholder="密码", required=True, size="3"),
                        rx.button("登录", type="submit", size="3", width="100%"),
                        
                        # 错误提示框，条件渲染
                        rx.cond(
                            BaseState.login_error != "",
                            rx.callout(
                                BaseState.login_error,
                                icon="alert-triangle",
                                color_scheme="red",
                                width="100%"
                            )
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    on_submit=BaseState.login,
                    reset_on_submit=False,
                    width="100%",
                ),
                width="100%",
                padding="2em",
            ),
            max_width="400px",
            width="100%",
            box_shadow="lg",
        ),
        width="100vw",
        height="100vh",
        bg=rx.color("gray", 2), # 浅色背景
    )
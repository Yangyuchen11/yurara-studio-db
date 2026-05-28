# yurara_app/pages/login.py
"""
登录页面。
UI 风格：深色背景 + 玻璃拟态卡片 + 渐变 Logo。
"""
import reflex as rx
from ..state.auth_state import AuthState


def login_page() -> rx.Component:
    return rx.box(
        # 背景：深色渐变 + 网格纹
        rx.box(
            # 渐变光晕装饰
            rx.box(
                position="absolute",
                top="-20%",
                left="-10%",
                width="600px",
                height="600px",
                background="radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%)",
                pointer_events="none",
            ),
            rx.box(
                position="absolute",
                bottom="-10%",
                right="-5%",
                width="500px",
                height="500px",
                background="radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%)",
                pointer_events="none",
            ),
            position="fixed",
            top="0",
            left="0",
            width="100%",
            height="100%",
            overflow="hidden",
            pointer_events="none",
        ),

        # 中心登录卡片
        rx.center(
            rx.card(
                rx.vstack(
                    # Logo 区域
                    rx.vstack(
                        rx.box(
                            rx.text("Y", weight="bold", size="7", color="white"),
                            width="56px",
                            height="56px",
                            background="linear-gradient(135deg, #6366f1, #8b5cf6)",
                            border_radius="14px",
                            display="flex",
                            align_items="center",
                            justify_content="center",
                            box_shadow="0 8px 24px rgba(99,102,241,0.4)",
                        ),
                        rx.heading("Yurara Studio", size="6", weight="bold"),
                        rx.text(
                            "综合管理系统",
                            size="2",
                            color=rx.color("slate", 10),
                        ),
                        spacing="2",
                        align="center",
                    ),

                    rx.divider(margin_y="0.5rem"),

                    # 错误提示
                    rx.cond(
                        AuthState.login_error != "",
                        rx.callout(
                            AuthState.login_error,
                            icon="circle-x",
                            color_scheme="red",
                            size="1",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),

                    # 登录表单
                    rx.form.root(
                        rx.vstack(
                            rx.form.field(
                                rx.vstack(
                                    rx.form.label("用户名", size="2", weight="medium"),
                                    rx.input(
                                        placeholder="请输入用户名",
                                        name="username",
                                        size="3",
                                        width="100%",
                                        required=True,
                                        auto_focus=True,
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                name="username",
                                width="100%",
                            ),
                            rx.form.field(
                                rx.vstack(
                                    rx.form.label("密码", size="2", weight="medium"),
                                    rx.input(
                                        placeholder="请输入密码",
                                        name="password",
                                        type="password",
                                        size="3",
                                        width="100%",
                                        required=True,
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                name="password",
                                width="100%",
                            ),
                            rx.button(
                                rx.cond(
                                    AuthState.is_loading,
                                    rx.hstack(
                                        rx.spinner(size="1"),
                                        rx.text("登录中..."),
                                        spacing="2",
                                    ),
                                    rx.hstack(
                                        rx.icon("log-in", size=14),
                                        rx.text("登 录"),
                                        spacing="2",
                                    ),
                                ),
                                type="submit",
                                size="3",
                                width="100%",
                                background="linear-gradient(135deg, #6366f1, #8b5cf6)",
                                color="white",
                                _hover={
                                    "background": "linear-gradient(135deg, #4f46e5, #7c3aed)",
                                    "box_shadow": "0 4px 16px rgba(99,102,241,0.4)",
                                },
                                cursor="pointer",
                                disabled=AuthState.is_loading,
                            ),
                            spacing="4",
                            width="100%",
                        ),
                        on_submit=AuthState.login,
                        width="100%",
                    ),

                    spacing="4",
                    width="100%",
                    align="center",
                ),
                width="380px",
                padding="2rem",
                background=rx.color("slate", 1),
                box_shadow="0 24px 64px rgba(0,0,0,0.4)",
                border=f"1px solid {rx.color('slate', 4)}",
            ),
            min_height="100vh",
            background="linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #0d1117 100%)",
        ),

        position="relative",
        width="100%",
        min_height="100vh",
    )

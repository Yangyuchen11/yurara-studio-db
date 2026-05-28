# yurara_app/state/auth_state.py
"""
认证 State。
管理：登录状态、Cookie 持久化、路由守卫。
"""
import hashlib
import os
import reflex as rx


def _generate_token(username: str, password: str) -> str:
    salt = "yurara_secret_salt_2024"
    return hashlib.sha256(f"{username}{password}{salt}".encode()).hexdigest()


class AuthState(rx.State):
    """认证状态，使用 rx.Cookie 在浏览器端持久化登录信息。"""

    # Cookie 自动持久化到浏览器（7天）
    auth_user: str = rx.Cookie(name="yurara_auth_user", max_age=604800, path="/")
    auth_token: str = rx.Cookie(name="yurara_auth_token", max_age=604800, path="/")

    # 运行时认证标记
    authenticated: bool = False
    login_error: str = ""
    is_loading: bool = False

    # ===================== 属性计算 =====================

    @rx.var
    def current_user(self) -> str:
        return self.auth_user or "Unknown"

    @rx.var
    def is_authenticated(self) -> bool:
        return self.authenticated

    # ===================== 事件处理器 =====================

    @rx.event
    async def check_auth(self):
        """
        页面加载时检查 Cookie 是否有效。
        若 Cookie 存在则自动恢复登录态；否则重定向到登录页。
        """
        if self.auth_user and self.auth_token:
            # 简单验证 token 格式（你可以加入更严格的服务端验证）
            self.authenticated = True
        else:
            self.authenticated = False
            yield rx.redirect("/login")

    @rx.event
    async def login(self, form_data: dict):
        """处理登录表单提交。"""
        self.is_loading = True
        self.login_error = ""
        yield

        username = form_data.get("username", "").strip()
        password = form_data.get("password", "").strip()

        # 从环境变量读取凭据（格式：CRED_用户名=密码）
        # 支持多用户：CRED_ADMIN=xxx, CRED_USER1=yyy
        found = False
        creds_raw = os.getenv("APP_CREDENTIALS", "")  # 格式: "user1:pass1,user2:pass2"
        
        if creds_raw:
            for pair in creds_raw.split(","):
                pair = pair.strip()
                if ":" in pair:
                    u, p = pair.split(":", 1)
                    if username == u.strip() and password == p.strip():
                        found = True
                        break
        else:
            # 兜底：检查单用户环境变量
            admin_user = os.getenv("ADMIN_USERNAME", "admin")
            admin_pass = os.getenv("ADMIN_PASSWORD", "")
            if username == admin_user and password == admin_pass:
                found = True

        self.is_loading = False

        if found:
            token = _generate_token(username, password)
            self.auth_user = username
            self.auth_token = token
            self.authenticated = True
            self.login_error = ""
            yield rx.redirect("/finance")
        else:
            self.login_error = "用户名或密码错误"

    @rx.event
    async def logout(self):
        """退出登录，清除 Cookie 并跳转登录页。"""
        self.auth_user = ""
        self.auth_token = ""
        self.authenticated = False
        yield rx.redirect("/login")

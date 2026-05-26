# yurara_studio/states/base_state.py
import reflex as rx
import os
from dotenv import load_dotenv

load_dotenv()

class BaseState(rx.State):
    exchange_rate: float = 4.8  # 预设的日元对人民币汇率，后续可以改为动态获取
    """全局共享状态"""
    # 存放在浏览器的 Cookie 中，过期时间设为 7 天
    auth_token: str = rx.Cookie(name="yurara_auth_token", max_age=604800, secure=True, same_site="Lax")
    current_user: str = rx.Cookie(name="yurara_auth_user", max_age=604800, secure=True, same_site="Lax")
    
    # 登录错误提示信息
    login_error: str = ""

    @rx.var
    def is_authenticated(self) -> bool:
        return bool(self.auth_token and self.current_user)

    def login(self, form_data: dict):
        """处理登录表单提交"""
        username = form_data.get("username")
        password = form_data.get("password")

        # 这里先使用 .env 里的管理员账号作为演示。
        # 后续你可以改写为查询数据库的用户表，或者像以前一样读取一个 JSON/配置
        admin_user = os.getenv("ADMIN_USER", "admin")
        admin_pw = os.getenv("ADMIN_PW", "admin_pw")

        if username == admin_user and password == admin_pw:
            self.current_user = username
            self.auth_token = "valid_token_123" # 生产环境可用 hashlib 生成安全 token
            self.login_error = ""
            return rx.redirect("/dashboard")
        else:
            self.login_error = "用户名或密码错误"

    def logout(self):
        """退出登录"""
        self.auth_token = ""
        self.current_user = ""
        return rx.redirect("/")
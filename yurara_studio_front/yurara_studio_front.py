# yurara_studio_front/yurara_studio_front.py
import reflex as rx

# 导入组件和页面
from yurara_studio_front.components.layout import check_auth
from yurara_studio_front.pages.login import login_page
from yurara_studio_front.pages.balance import balance_page
from yurara_studio_front.states.balance_state import BalanceState

# 实例化 Reflex App
app = rx.App(
    theme=rx.theme(
        appearance="light", 
        has_background=True, 
        radius="medium", 
        accent_color="indigo"
    )
)

# 注册路由
app.add_page(login_page, route="/", title="登录 - Yurara Studio")

# 注册公司账面概览页面
# on_load 表示页面加载时执行的事件：先检查登录状态，再加载账面数据
app.add_page(
    balance_page, 
    route="/balance", 
    title="公司账面概览 - Yurara", 
    on_load=[check_auth, BalanceState.load_data]
)

# 后续我们还会在这里依次添加 /finance, /products 等路由...
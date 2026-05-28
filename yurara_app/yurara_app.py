# yurara_app/yurara_app.py
"""
Reflex 应用主入口。
注册所有页面路由、全局主题和样式。
"""
import reflex as rx
from .pages.login import login_page
from .pages.product import product_page
from .state.auth_state import AuthState
from .state.app_state import AppState


# ---- 占位页面（后续逐步替换） ----

def placeholder_page(title: str, icon: str = "construction") -> rx.Component:
    """迁移进行中的临时占位页面。"""
    from .components.layout import page_layout
    return page_layout(
        rx.center(
            rx.vstack(
                rx.icon(icon, size=48, color=rx.color("violet", 8)),
                rx.heading(title, size="5"),
                rx.badge("迁移进行中...", color_scheme="orange", variant="soft"),
                rx.text(
                    "此页面正在从 Streamlit 迁移到 Reflex，暂时使用占位页面。",
                    size="2",
                    color=rx.color("slate", 10),
                    text_align="center",
                ),
                spacing="3",
                align="center",
            ),
            padding="4rem",
        ),
        title=title,
    )


def finance_page(): return placeholder_page("财务流水录入", "circle-dollar-sign")
def balance_page(): return placeholder_page("公司账面概览", "clipboard-list")
def report_page(): return placeholder_page("财务报表与分析", "chart-pie")
def cost_page(): return placeholder_page("商品成本核算", "calculator")
def sales_order_page(): return placeholder_page("线上销售管理", "shopping-cart")
def presale_page(): return placeholder_page("预售销售管理", "shopping-basket")
def offline_sales_page(): return placeholder_page("线下销售管理", "store")
def sales_page(): return placeholder_page("销售额一览", "trending-up")
def inventory_page(): return placeholder_page("仓库库存管理", "arrow-left-right")
def asset_page(): return placeholder_page("固定资产管理", "camera")
def consumable_page(): return placeholder_page("其他资产管理", "box")


# ---- 全局样式 ----

GLOBAL_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    box-sizing: border-box;
}

body {
    background-color: #0d1117;
}

/* 侧边栏导航项 */
.nav-item {
    display: flex;
    align-items: center;
    padding: 6px 10px;
    border-radius: 6px;
    text-decoration: none !important;
    color: var(--gray-11);
    transition: all 0.15s ease;
    font-size: 13px;
}
.nav-item:hover {
    background-color: var(--violet-3);
    color: var(--violet-11);
}
.nav-item[data-active="true"],
.nav-item.active {
    background-color: var(--violet-4);
    color: var(--violet-11);
    font-weight: 500;
}
.nav-icon {
    flex-shrink: 0;
    color: var(--gray-9);
}
.nav-item:hover .nav-icon {
    color: var(--violet-9);
}
.nav-group-label {
    color: var(--gray-9);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 10px;
    padding: 0 10px;
    margin-top: 0.5rem;
}

/* 卡片悬停效果 */
.radix-themes .rt-Card {
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.radix-themes .rt-Card:hover {
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
}

/* 平滑滚动 */
html {
    scroll-behavior: smooth;
}

/* 自定义滚动条 */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background: var(--gray-5);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--gray-7);
}
"""


# ---- App 定义 ----

app = rx.App(
    style={
        "font_family": "Inter, -apple-system, sans-serif",
    },
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
    ],
)

# ---- 路由注册 ----

app.add_page(login_page, route="/login", title="登录 | Yurara Studio")
app.add_page(
    product_page,
    route="/product",
    title="商品管理 | Yurara Studio",
    on_load=[AuthState.check_auth, AppState.load_exchange_rate],
)

# 占位页面（迁移进行中）
app.add_page(finance_page, route="/finance", title="财务流水 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate])
app.add_page(balance_page, route="/balance", title="账面概览 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(report_page, route="/report", title="财务报表 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(cost_page, route="/cost", title="成本核算 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(sales_order_page, route="/sales-order", title="线上销售 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(presale_page, route="/presale", title="预售管理 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(offline_sales_page, route="/offline-sales", title="线下销售 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(sales_page, route="/sales", title="销售额 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(inventory_page, route="/inventory", title="库存管理 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(asset_page, route="/asset", title="固定资产 | Yurara Studio", on_load=[AuthState.check_auth])
app.add_page(consumable_page, route="/consumable", title="其他资产 | Yurara Studio", on_load=[AuthState.check_auth])

# 默认根路由：跳转到财务（需登录）
def index_page() -> rx.Component:
    return rx.center(
        rx.spinner(size="3"),
        padding="8rem",
        width="100%",
        height="100vh",
    )

app.add_page(index_page, route="/", on_load=rx.redirect("/finance"))

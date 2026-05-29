# yurara_app/yurara_app.py
"""
Reflex 应用主入口。
注册所有页面路由、全局主题和样式。
"""
import reflex as rx
from .pages.login import login_page
from .pages.product import product_page
from .pages.finance import finance_page
from .pages.balance import balance_page
from .pages.asset import asset_page
from .pages.consumable import consumable_page
from .pages.sales import sales_page
from .pages.cost import cost_page
from .pages.inventory import inventory_page
from .pages.report import report_page
from .pages.offline_sales import offline_sales_page
from .pages.sales_order import sales_order_page
from .pages.presale import presale_page
from .state.auth_state import AuthState
from .state.app_state import AppState
from .state.finance_state import FinanceState
from .state.balance_state import BalanceState
from .state.asset_state import AssetState
from .state.consumable_state import ConsumableState
from .state.sales_state import SalesState
from .state.cost_state import CostState
from .state.inventory_state import InventoryState
from .state.report_state import ReportState
from .state.offline_sales_state import OfflineSalesState
from .state.sales_order_state import SalesOrderState
from .state.presale_state import PresaleState
from .state.product_state import ProductState

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

/* 解决所有紫色底色 Callout 中字体呈黑色难以看清的问题 */
.rt-CalloutRoot[data-color="violet"] {
    background-color: var(--violet-3) !important;
}
.rt-CalloutRoot[data-color="violet"] .rt-CalloutText {
    color: var(--violet-11) !important;
    font-weight: 500 !important;
}
.rt-CalloutRoot[data-color="violet"] .rt-CalloutIcon {
    color: var(--violet-11) !important;
}

/* 解决所有紫色 Badge 字体难以看清的问题 */
.rt-Badge[data-color="violet"] {
    background-color: var(--violet-3) !important;
    color: var(--violet-11) !important;
    font-weight: 500 !important;
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
        "fontFamily": "Inter, -apple-system, sans-serif",
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
    on_load=[AuthState.check_auth, AppState.load_exchange_rate, ProductState.load_products],
)

# 占位页面（迁移进行中）
app.add_page(finance_page, route="/finance", title="财务流水 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, FinanceState.load_finance_page])
app.add_page(balance_page, route="/balance", title="账面概览 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, BalanceState.load_balance_data])
app.add_page(report_page, route="/report", title="财务报表 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, ReportState.load_report_page])
app.add_page(cost_page, route="/cost", title="成本核算 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, CostState.load_cost_page])
app.add_page(sales_order_page, route="/sales-order", title="线上销售 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, SalesOrderState.load_orders_page])
app.add_page(presale_page, route="/presale", title="预售管理 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, PresaleState.load_presale_page])
app.add_page(offline_sales_page, route="/offline-sales", title="线下销售 | Yurara Studio", on_load=[AuthState.check_auth, OfflineSalesState.load_offline_page])
app.add_page(sales_page, route="/sales", title="销售额 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, SalesState.load_sales_data])
app.add_page(inventory_page, route="/inventory", title="库存管理 | Yurara Studio", on_load=[AuthState.check_auth, InventoryState.load_inventory_page])
app.add_page(asset_page, route="/asset", title="固定资产 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, AssetState.load_asset_page])
app.add_page(consumable_page, route="/consumable", title="其他资产 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, ConsumableState.load_consumable_page])

# 默认根路由：跳转到财务（需登录）
def index_page() -> rx.Component:
    return rx.center(
        rx.spinner(size="3"),
        padding="8rem",
        width="100%",
        height="100vh",
    )

app.add_page(index_page, route="/", on_load=rx.redirect("/finance"))

# === 自定义 API：全量数据备份 ZIP 下载接口 ===
def download_backup(request):
    from yurara_app.state.app_state import get_cached_engine, TABLES_MAP
    from sqlalchemy.orm import sessionmaker
    from starlette.responses import StreamingResponse
    import io
    import zipfile
    import pandas as pd
    from datetime import datetime

    test_mode = request.query_params.get("test_mode", "false")
    is_test = test_mode.lower() == "true"
    engine = get_cached_engine(is_test)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for file_name, table_name, model_cls in TABLES_MAP:
                try:
                    df_export = pd.read_sql(db.query(model_cls).statement, db.bind)
                    csv_bytes = df_export.to_csv(index=False).encode('utf-8-sig')
                    zf.writestr(file_name, csv_bytes)
                except Exception:
                    pass
        zip_buffer.seek(0)
        current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        env_suffix = "test" if is_test else "prod"
        filename = f"yurara-db-backup_{env_suffix}_{current_time}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    finally:
        db.close()

app._api.add_route("/backup", download_backup, methods=["GET"])


# ==========================================
# 自动数据库结构建立与迁移 (正式环境 / SQLite)
# ==========================================
try:
    from database import Base, engine
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[Reflex App] Database auto-migration / init failed: {e}")

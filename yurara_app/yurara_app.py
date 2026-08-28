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
from .pages.platforms import platforms_page
from .pages.schedule import schedule_page
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
from .state.platforms_state import PlatformsState
from .state.memo_state import MemoState
from .state.schedule_state import ScheduleState

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

/* 时间轴全景甘特图水平滑动条加粗与突出显示 (14px 宽大易点) */
.timeline-scrollbar-container::-webkit-scrollbar {
    height: 14px !important;
}
.timeline-scrollbar-container::-webkit-scrollbar-track {
    background: rgba(148, 163, 184, 0.15) !important;
    border-radius: 8px !important;
}
.timeline-scrollbar-container::-webkit-scrollbar-thumb {
    background: rgba(139, 92, 246, 0.6) !important;
    border-radius: 8px !important;
    border: 2px solid transparent !important;
    background-clip: content-box !important;
}
.timeline-scrollbar-container::-webkit-scrollbar-thumb:hover {
    background: rgba(139, 92, 246, 0.9) !important;
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

/* 输入框与下拉选择框的UI样式一致性：白色背景，黑色文本，灰色提示字，紫色高亮 */
.rt-TextFieldRoot, .rt-SelectTrigger {
    background-color: #ffffff !important;
    color: #000000 !important;
    border: 1px solid var(--gray-5) !important;
}

.rt-TextFieldRoot:focus-within, .rt-SelectTrigger:focus {
    border-color: var(--violet-8) !important;
    box-shadow: 0 0 0 2px var(--violet-4) !important;
}

/* 提示用字（Placeholder）保持为灰色 */
.rt-TextFieldInput::placeholder, 
.rt-SelectTrigger[data-placeholder] > span {
    color: var(--gray-8) !important;
}

/* 下拉菜单弹出框与选项样式 */
.rt-SelectContent {
    background-color: #ffffff !important;
    border: 1px solid var(--gray-4) !important;
}

.rt-SelectItem {
    color: #000000 !important;
}

.rt-SelectItem:hover, .rt-SelectItem[data-highlighted] {
    background-color: var(--violet-9) !important;
    color: #ffffff !important;
}

/* 解决折叠面板内部所有 Callout 提示框字体在深色背景下不清晰的问题（显示为白字与半透明白框） */
.rt-AccordionContent .rt-CalloutRoot {
    background-color: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
}
.rt-AccordionContent .rt-CalloutRoot * {
    color: #ffffff !important;
    font-weight: 500 !important;
}

/* 解决折叠面板内部表格标头和内容呈现黑色无法看清规整的问题，并左对齐表头与单元格以完美对齐下方输入框 */
.rt-AccordionContent .rt-TableRoot,
.rt-AccordionContent .rt-TableColumnHeaderCell,
.rt-AccordionContent .rt-TableCell,
.rt-AccordionContent .rt-TableColumnHeaderCell *,
.rt-AccordionContent .rt-TableCell * {
    color: #ffffff !important;
}
.rt-AccordionContent .rt-TableColumnHeaderCell,
.rt-AccordionContent .rt-TableCell {
    text-align: left !important;
}
"""


# ---- App 定义 ----

app = rx.App(
    style={
        "fontFamily": "Inter, -apple-system, sans-serif",
    },
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
        "/global.css"
    ],
    head_components=[
        rx.script(src="/timeline_zoom.js"),
    ],
    theme=rx.theme(
        appearance="dark",
        accent_color="violet",
        gray_color="slate",
        radius="medium",
        scaling="95%",
    )
)


# ---- 路由注册 ----

app.add_page(login_page, route="/login", title="登录 | Yurara Studio")
app.add_page(
    product_page,
    route="/product",
    title="商品管理 | Yurara Studio",
    on_load=[AuthState.check_auth, AppState.load_exchange_rate, ProductState.load_products, MemoState.load_memos],
)

# 占位页面（迁移进行中）
app.add_page(finance_page, route="/finance", title="财务流水 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, FinanceState.load_finance_page, MemoState.load_memos])
app.add_page(balance_page, route="/balance", title="账面概览 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, BalanceState.load_balance_data, MemoState.load_memos])
app.add_page(report_page, route="/report", title="财务报表 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, ReportState.load_report_page, MemoState.load_memos])
app.add_page(cost_page, route="/cost", title="成本核算 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, CostState.load_cost_page, MemoState.load_memos])
app.add_page(sales_order_page, route="/sales-order", title="线上销售 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, SalesOrderState.load_orders_page, MemoState.load_memos])
app.add_page(presale_page, route="/presale", title="预售管理 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, PresaleState.load_presale_page, MemoState.load_memos])
app.add_page(offline_sales_page, route="/offline-sales", title="线下销售 | Yurara Studio", on_load=[AuthState.check_auth, OfflineSalesState.load_offline_page, MemoState.load_memos])
app.add_page(sales_page, route="/sales", title="销售额 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, SalesState.load_sales_data, MemoState.load_memos])
app.add_page(platforms_page, route="/platforms", title="销售平台管理 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, PlatformsState.load_platforms, MemoState.load_memos])
app.add_page(inventory_page, route="/inventory", title="库存管理 | Yurara Studio", on_load=[AuthState.check_auth, InventoryState.load_inventory_page, MemoState.load_memos])
app.add_page(asset_page, route="/asset", title="固定资产 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, AssetState.load_asset_page, MemoState.load_memos])
app.add_page(consumable_page, route="/consumable", title="其他资产 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, ConsumableState.load_consumable_page, MemoState.load_memos])
app.add_page(schedule_page, route="/schedule", title="工期日程管理 | Yurara Studio", on_load=[AuthState.check_auth, AppState.load_exchange_rate, ScheduleState.on_page_load, MemoState.load_memos])

# 默认根路由：跳转到财务（需登录）
def index_page() -> rx.Component:
    return rx.center(
        rx.spinner(size="3"),
        padding="8rem",
        width="100%",
        height="100vh",
    )

app.add_page(index_page, route="/", on_load=AuthState.index_redirect)

# === 自定义 API：全量数据备份 ZIP 下载接口 ===
def download_backup(request):
    import traceback
    try:
        from yurara_app.state.app_state import get_cached_engine, TABLES_MAP
        from starlette.responses import Response
        import io
        import zipfile
        import pandas as pd
        from datetime import datetime

        test_mode = request.query_params.get("test_mode", "false")
        is_test = test_mode.lower() == "true"
        engine = get_cached_engine(is_test)

        zip_buffer = io.BytesIO()
        # 使用 engine.connect() 直接建立连接，避免已废弃的 Session.bind
        with engine.connect() as conn:
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file_name, table_name, model_cls in TABLES_MAP:
                    try:
                        df_export = pd.read_sql_table(table_name, conn)
                        csv_bytes = df_export.to_csv(index=False).encode('utf-8-sig')
                        zf.writestr(file_name, csv_bytes)
                        print(f"[Backup API] Exported {table_name}: {len(df_export)} rows")
                    except Exception as e_table:
                        print(f"[Backup API] Failed to export table {table_name}: {e_table}")

        current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        env_suffix = "test" if is_test else "prod"
        filename = f"yurara-db-backup_{env_suffix}_{current_time}.zip"
        return Response(
            zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[Backup API] Critical Error: {e}\n{tb}")
        from starlette.responses import PlainTextResponse
        return PlainTextResponse(f"Backup Error: {e}\n{tb}", status_code=500)

app._api.add_route("/backup", download_backup, methods=["GET"])


# === 自定义 API：根据 Color ID 动态渲染二进制图片接口 ===
def serve_color_image(request):
    import base64
    from starlette.responses import Response
    from database import SessionLocal
    from models import ProductColor
    
    color_id_str = request.path_params.get("color_id")
    if not color_id_str:
        return Response(status_code=400)
    try:
        color_id = int(color_id_str)
    except ValueError:
        return Response(status_code=400)
        
    db = SessionLocal()
    try:
        color = db.query(ProductColor).filter(ProductColor.id == color_id).first()
        if not color or not color.image_data:
            return Response(status_code=404)
        
        data_str = color.image_data
        if data_str.startswith("data:image/"):
            header, encoded = data_str.split(",", 1)
            mime_type = header.split(";")[0].split(":")[1]
            image_bytes = base64.b64decode(encoded)
            return Response(
                content=image_bytes,
                media_type=mime_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*"
                }
            )
        else:
            return Response(status_code=404)
    except Exception as e:
        print(f"[Image API] Error serving image for color_id {color_id}: {e}")
        return Response(status_code=500)
    finally:
        db.close()

app._api.add_route("/color-image/{color_id}", serve_color_image, methods=["GET"])


# ==========================================
# 自动数据库结构建立与迁移 (正式环境 / SQLite)
# ==========================================
import sys
# 编译与构建阶段（如 reflex init 或 reflex export）无需连接真实数据库，防止云端 Build 环境网络隔离导致连接超时失败
if not any(arg in sys.argv for arg in ["init", "export"]):
    try:
        from database import Base, engine, migrate_db
        try:
            migrate_db(engine)
        except Exception as migrate_err:
            print(f"[Reflex App] Database migration check failed: {migrate_err}")
        Base.metadata.create_all(bind=engine)
        # 自动初始化默认销售平台数据
        try:
            from database import SessionLocal
            from models import SalesPlatform
            db_session = SessionLocal()
            try:
                if db_session.query(SalesPlatform).count() == 0:
                    defaults = [
                        ("weidian", "微店", "CNY", 0.006, 0.0),
                        ("booth", "Booth", "JPY", 0.056, 22.0),
                        ("offline_cn", "国内线下", "CNY", 0.0, 0.0),
                        ("offline_jp", "日本线下", "JPY", 0.0, 0.0),
                        ("instagram", "Instagram", "JPY", 0.0, 0.0),
                        ("other", "其他(CNY)", "CNY", 0.0, 0.0),
                        ("other_jpy", "其他(JPY)", "JPY", 0.0, 0.0),
                    ]
                    for code, name, currency, fee_rate, fee_fixed in defaults:
                        db_session.add(SalesPlatform(
                            code=code,
                            name=name,
                            currency=currency,
                            fee_rate=fee_rate,
                            fee_fixed=fee_fixed
                        ))
                    db_session.commit()
                    print("[Reflex App] Seeded default sales platforms.")
            finally:
                db_session.close()
        except Exception as seed_err:
            print(f"[Reflex App] Failed to seed default sales platforms: {seed_err}")
    except Exception as e:
        print(f"[Reflex App] Database auto-migration / init failed: {e}")

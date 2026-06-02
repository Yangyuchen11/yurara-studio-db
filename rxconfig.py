import os
import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

# ==========================================
# 生产部署说明（Zeabur）：
#   API_URL      = https://your-app.zeabur.app
#   DATABASE_URL = postgresql://...
#   ADMIN_USERNAME / ADMIN_PASSWORD
# ==========================================

is_prod = (
    os.getenv("ENV", "dev").lower() == "prod"
    or os.getenv("REFLEX_ENV", "dev").lower() == "prod"
)

if is_prod:
    # 生产环境：后端统一监听 PORT（8080），前端通过后端 serve，不设 frontend_port
    backend_port = int(os.getenv("PORT", "8080"))
    api_url = os.getenv("API_URL", f"http://localhost:{backend_port}")
    extra = {}
else:
    # 开发环境：后端 8000，前端 3000（Reflex 默认双端口开发模式）
    backend_port = int(os.getenv("BACKEND_PORT", "8000"))
    api_url = os.getenv("API_URL", "http://localhost:8000")
    extra = {"frontend_port": 3000}

config = rx.Config(
    app_name="yurara_app",
    api_url=api_url,
    backend_port=backend_port,
    telemetry_enabled=False,
    disable_plugins=[SitemapPlugin],
    plugins=[
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(
                appearance="dark",
                accent_color="violet",
                gray_color="slate",
                radius="medium",
                scaling="95%",
            )
        ),
    ],
    **extra,
)

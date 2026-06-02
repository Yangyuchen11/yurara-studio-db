import os
import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

# ==========================================
# 生产部署说明（Zeabur）：
#   API_URL      = https://your-app.zeabur.app
#   DATABASE_URL = postgresql://...
#   ADMIN_USERNAME / ADMIN_PASSWORD
# ==========================================

# 检测运行环境
is_prod = (
    os.getenv("ENV", "dev").lower() == "prod"
    or os.getenv("REFLEX_ENV", "dev").lower() == "prod"
)

# 生产环境：前后端统一使用 PORT（8080），由 Zeabur 对外暴露
# 开发环境：后端 8000，前端 3000（Reflex 默认）
if is_prod:
    _port = int(os.getenv("PORT", "8080"))
    backend_port = _port
    frontend_port = _port
    api_url = os.getenv("API_URL", f"http://localhost:{_port}")
else:
    backend_port = int(os.getenv("BACKEND_PORT", "8000"))
    frontend_port = 3000
    api_url = os.getenv("API_URL", "http://localhost:8000")

config = rx.Config(
    app_name="yurara_app",
    api_url=api_url,
    backend_port=backend_port,
    frontend_port=frontend_port,
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
)

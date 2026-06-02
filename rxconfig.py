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
    # 生产模式：前后端必须用同一端口（Reflex 要求）
    # Zeabur 对外暴露 PORT（默认 8080）
    port = int(os.getenv("PORT", "8080"))
    backend_port = port
    frontend_port = port          # 必须和 backend_port 相同
    api_url = os.getenv("API_URL", f"http://localhost:{port}")
else:
    # 开发模式：后端 8000，前端 3000（Reflex 默认双端口）
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

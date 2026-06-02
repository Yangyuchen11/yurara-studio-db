import os
import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

# ==========================================
# 生产部署说明：
# 在 Zeabur 上需要配置以下环境变量：
#   API_URL = https://your-app.zeabur.app   （你的 Zeabur 公网 URL）
#   DATABASE_URL = postgresql://...
# ==========================================

# API_URL: 前端与后端通信的地址
# 生产环境必须设置为 Zeabur 的公网 URL（https://xxx.zeabur.app）
# 开发环境默认使用 localhost:8000
api_url = os.getenv("API_URL", "http://localhost:8000")

# 后端端口（生产环境为 8000，由 Caddy 在内部代理）
backend_port = int(os.getenv("BACKEND_PORT", "8000"))

# 前端端口（生产环境 Caddy 监听 8080，开发环境为 3000）
is_prod = os.getenv("ENV", "dev").lower() == "prod" or os.getenv("REFLEX_ENV", "dev").lower() == "prod"
frontend_port = int(os.getenv("PORT", "8080")) if is_prod else 3000

config = rx.Config(
    app_name="yurara_app",
    api_url=api_url,
    frontend_port=frontend_port,
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
)

import os
import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

# 从环境变量中读取 API_URL（Zeabur 等云端部署时必须配置为公网 API 地址）
api_url = os.getenv("API_URL", "http://localhost:8000")

# 允许通过环境变量指定后端端口
backend_port = int(os.getenv("PORT", os.getenv("BACKEND_PORT", "8000")))

# 如果是生产环境，前端和后端必须使用相同端口（单端口部署）
# 否则在本地开发模式（dev）下，前端运行在 3000，后端运行在 8000
is_prod = os.getenv("ENV", "dev").lower() == "prod" or os.getenv("REFLEX_ENV", "dev").lower() == "prod"
frontend_port = backend_port if is_prod else 3000

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

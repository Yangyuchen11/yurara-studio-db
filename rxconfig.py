import os
import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

# 从环境变量中读取 API_URL（Zeabur 等云端部署时必须配置为公网 API 地址）
api_url = os.getenv("API_URL", "http://localhost:8000")

# 允许通过环境变量指定后端端口
backend_port = int(os.getenv("PORT", os.getenv("BACKEND_PORT", "8000")))

config = rx.Config(
    app_name="yurara_app",
    api_url=api_url,
    frontend_port=3000,
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

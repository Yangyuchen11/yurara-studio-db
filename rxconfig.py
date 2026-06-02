import os
import sys
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

# --backend-only 模式下不能指定 frontend_port（Reflex 会报错）
# 检测是否以 backend-only 模式启动
is_backend_only = "--backend-only" in sys.argv

# 仅在非 backend-only 模式下设置前端端口
is_prod = os.getenv("ENV", "dev").lower() == "prod" or os.getenv("REFLEX_ENV", "dev").lower() == "prod"
frontend_port = int(os.getenv("PORT", "3000")) if not is_prod else 3000

config_kwargs = dict(
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
)

# backend-only 模式下不传 frontend_port，避免 Reflex 报错
if not is_backend_only:
    config_kwargs["frontend_port"] = frontend_port

config = rx.Config(**config_kwargs)

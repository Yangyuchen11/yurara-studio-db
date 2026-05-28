import reflex as rx

config = rx.Config(
    app_name="yurara_app",
    # 生产环境通过环境变量 API_URL 覆盖
    api_url="http://localhost:8000",
    # 前端开发端口
    frontend_port=3000,
    # 后端 API 端口
    backend_port=8000,
    # 禁用遥测
    telemetry_enabled=False,
)

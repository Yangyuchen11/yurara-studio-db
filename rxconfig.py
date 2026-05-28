import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

config = rx.Config(
    app_name="yurara_app",
    api_url="http://localhost:8000",
    frontend_port=3000,
    backend_port=8000,
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

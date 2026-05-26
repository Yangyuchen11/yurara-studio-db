import reflex as rx

config = rx.Config(
    app_name="yurara_studio_front",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)
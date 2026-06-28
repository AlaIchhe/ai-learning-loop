import reflex as rx
from reflex_base.plugins.sitemap import SitemapPlugin
from reflex_components_radix.plugin import RadixThemesPlugin

config = rx.Config(
    app_name="rxweb",
    frontend_port=3003,
    backend_port=8003,
    db_url="sqlite:///reflex.db",
    # Windows granian 不支持 WebSocket transport，使用 polling 模式
    transport="polling",
    plugins=[RadixThemesPlugin()],
    disable_plugins=[SitemapPlugin],
)

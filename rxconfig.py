import sys
from pathlib import Path

import reflex as rx
from reflex_base.plugins.sitemap import SitemapPlugin
from reflex_components_radix.plugin import RadixThemesPlugin

# ── 环境初始化（必须在 settings 单例构造之前） ───────────────────────────────
# Reflex 在启动时加载本模块；此时 setup_environment() 尚未执行，
# load_dotenv() 也未运行。为确保 settings 单例读取到 .env 中的值，
# 先在 sys.path 中注册项目根目录，再调用 setup_environment()。
_project_root = Path(__file__).parent.resolve()
_root_str = str(_project_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

from socratic_loop.infra.env import setup_environment  # noqa: E402

setup_environment(_project_root, verbose=False)

# ── 配置读取（setup_environment 之后，确保 os.environ 已填充） ───────────────
from socratic_loop.core.settings import settings  # noqa: E402

config = rx.Config(
    app_name="web",
    frontend_port=settings.frontend_port,
    backend_port=settings.backend_port,
    db_url=settings.db_url,
    # Windows granian 不支持 WebSocket transport，其余平台使用 websocket
    transport=settings.effective_transport(),
    plugins=[RadixThemesPlugin()],
    disable_plugins=[SitemapPlugin],
)

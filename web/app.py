"""Reflex entry point for Socratic Learning Loop.

创建 rx.App 实例并注册路由:
    /        → 聊天页（chat_page）
    /settings → 模型设置页（settings_page）

Reflex 通过 rxconfig.py 中的 app_name='web' 定位本模块。
"""

import reflex as rx

from .chat import chat_page
from .settings import settings_page
from .styles import global_style

app = rx.App(
    style=global_style,
    stylesheets=["/fonts.css"],
)

app.add_page(
    chat_page,
    route="/",
    title="苏格拉底学习引导 - 对话",
)
app.add_page(
    settings_page,
    route="/settings",
    title="模型设置",
)

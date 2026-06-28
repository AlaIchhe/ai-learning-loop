"""Reflex entry point for Socratic Learning Loop.
Reflex looks for rxweb/rxweb.py as the app module (app_name='rxweb' in rxconfig.py).
"""
from .state import AppState
from .chat import chat_page
from .model_settings import model_settings_page
from .styles import global_style

import reflex as rx

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
    model_settings_page,
    route="/settings",
    title="模型设置",
)

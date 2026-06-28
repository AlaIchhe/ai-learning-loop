"""Model settings page — provider CRUD + connection test."""
import reflex as rx
from .state import AppState
from .styles import colors


def provider_card(provider: dict) -> rx.Component:
    """单个 provider 卡片。"""
    entry_id = provider["entry_id"]
    label = provider["label"]
    status = provider["status"]
    base_url = provider["base_url"]
    status_msg = provider["status_msg"]

    status_color = rx.cond(status == "ok", "green", rx.cond(status == "error", "red", "gray"))
    status_text = rx.cond(status == "ok", "已连接", rx.cond(status == "error", "连接失败", "未测试"))

    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading(label, size="4"),
                rx.spacer(),
                rx.badge(status_text, color_scheme=status_color),
                rx.button(
                    rx.icon("trash-2", size=14),
                    on_click=AppState.remove_provider(entry_id),
                    variant="ghost", size="1", color_scheme="red",
                ),
                width="100%", align="center",
            ),
            rx.text(base_url, font_size="0.8rem", color=colors["text_secondary"]),
            rx.cond(
                status_msg != "",
                rx.text(status_msg, font_size="0.8rem", color=colors["text_secondary"]),
            ),
            rx.hstack(
                rx.button("测试连接", on_click=AppState.test_provider_connection(entry_id),
                          variant="soft", size="2"),
                width="100%", justify="end",
            ),
            width="100%", spacing="2",
        ),
        width="100%",
    )


def add_provider_form() -> rx.Component:
    """添加新 provider 的表单。"""
    presets = ["openai", "deepseek", "siliconflow", "tongyi", "zhipu", "moonshot", "ollama", "custom"]

    return rx.card(
        rx.vstack(
            rx.heading("添加新提供商", size="4"),
            rx.select(
                presets,
                value=AppState.setting_new_preset,
                on_change=AppState.set_setting_preset,
                label="选择预设",
                width="100%",
            ),
            rx.input(
                placeholder="显示名称（可选）",
                value=AppState.setting_new_name,
                on_change=AppState.set_setting_name,
                width="100%",
            ),
            rx.input(
                placeholder="API Key",
                value=AppState.setting_new_key,
                on_change=AppState.set_setting_key,
                type="password",
                width="100%",
            ),
            rx.input(
                placeholder="Base URL（可选，留空使用默认）",
                value=AppState.setting_new_url,
                on_change=AppState.set_setting_url,
                width="100%",
            ),
            rx.hstack(
                rx.button("取消", on_click=AppState.show_add_provider, variant="soft"),
                rx.button("添加", on_click=AppState.add_provider, color_scheme="blue"),
                width="100%", justify="end", spacing="3",
            ),
            width="100%", spacing="3",
        ),
        width="100%",
    )


def model_settings_page() -> rx.Component:
    """模型设置主页面。"""
    from .chat import sidebar
    return rx.hstack(
        sidebar(),
        rx.box(
            rx.vstack(
                rx.heading("模型设置", size="7", margin_bottom="2rem"),
                rx.text(
                    "配置 AI 模型提供商，支持多个提供商同时配置。",
                    color=colors["text_secondary"], margin_bottom="2rem",
                ),

                # 提供商列表
                rx.heading("已配置提供商", size="5", margin_bottom="1rem"),
                rx.cond(
                    AppState.providers_list.length() > 0,
                    rx.vstack(
                        rx.foreach(AppState.providers_list, provider_card),
                        width="100%", spacing="3",
                    ),
                    rx.box(
                        rx.text("暂无配置的提供商。点击下方按钮添加。", color=colors["text_secondary"]),
                        padding="2rem", text_align="center", width="100%",
                    ),
                ),

                # 添加新提供商
                rx.cond(
                    AppState.setting_show_add,
                    add_provider_form(),
                    rx.button(
                        "+ 添加新提供商",
                        on_click=AppState.show_add_provider,
                        variant="soft", size="3", width="100%", margin_top="1rem",
                    ),
                ),
                width="100%", align_items="flex-start",
            ),
            class_name="main-content", margin_left="280px", padding_top="2rem",
        ),
        width="100%", height="100vh",
        on_mount=[AppState.initialize, AppState.refresh_providers],
    )

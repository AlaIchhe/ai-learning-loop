"""Chat page component — multi-tab edition."""

import reflex as rx

from .state import AppState
from .styles import colors


def message_bubble(message: dict) -> rx.Component:
    role = message["role"]
    content = message["content"]
    is_streaming = message["is_streaming"]
    is_user = role == "user"

    avatar = rx.match(
        role,
        ("user", "👤"),
        ("questioner", "⚔️"),
        ("refiner", "✨"),
        ("guide", "🧠"),
        "📋",
    )
    name = rx.match(
        role,
        ("user", "你"),
        ("questioner", "提问者"),
        ("refiner", "提炼者"),
        ("guide", "引导者"),
        "系统",
    )

    return rx.box(
        rx.hstack(
            rx.box(
                rx.text(avatar),
                class_name=rx.cond(is_user, "message-avatar user-avatar", "message-avatar ai-avatar"),
            ),
            rx.box(
                rx.cond(is_user, rx.fragment(), rx.text(name, class_name="message-name")),
                rx.box(
                    rx.markdown(content),
                    rx.cond(is_streaming, rx.box(class_name="typing-cursor"), rx.fragment()),
                    class_name=rx.cond(is_user, "message-bubble user-bubble", "message-bubble ai-bubble"),
                ),
                # 时间戳（完成后显示）
                rx.cond(
                    is_streaming,
                    rx.fragment(),
                    rx.text("🕐", font_size="0.7rem", color=colors["text_secondary"], padding_x="0.25rem"),
                ),
                class_name="message-content",
                align_items=rx.cond(is_user, "flex-end", "flex-start"),
            ),
            class_name=rx.cond(is_user, "chat-message user-message", "chat-message ai-message"),
            spacing="3",
        ),
        width="100%",
    )


def interrupt_prompt(value: str) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(rx.text("💬"), class_name="message-avatar ai-avatar"),
            rx.box(
                rx.text("请回应", class_name="message-name"),
                rx.box(
                    rx.markdown(value),
                    class_name="message-bubble ai-bubble",
                    border=f"2px solid {colors['primary']}",
                ),
                class_name="message-content",
            ),
            class_name="chat-message ai-message",
            spacing="3",
        ),
        width="100%",
    )


def generating_indicator(node_name: str) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.spinner(size="1"),
            rx.text(node_name + " 正在思考...", font_size="0.875rem", color=colors["text_secondary"]),
            spacing="2",
            padding="1rem",
        ),
        width="100%",
        display=rx.cond(node_name != "", "flex", "none"),
    )


# ── Tab 列表（侧边栏内） ──


def tab_item(tab: dict) -> rx.Component:
    """单个 Tab 条目。不依赖 foreach 内事件闭包。"""
    label = tab["label"]
    tab_id = tab["id"]
    is_active = tab_id == AppState.active_tab_id

    return rx.hstack(
        rx.button(
            rx.text(label, font_size="0.875rem", max_width="140px", overflow="hidden", text_overflow="ellipsis"),
            on_click=AppState.switch_tab(tab_id),
            variant="ghost",
            size="2",
            flex_grow=1,
            justify="start",
            background_color=rx.cond(is_active, colors["primary"], "transparent"),
            color=rx.cond(is_active, "white", colors["text_primary"]),
            border_radius="0.5rem",
            padding="0.4rem 0.6rem",
        ),
        rx.button(
            rx.icon("x", size=12),
            on_click=AppState.remove_tab(tab_id),
            variant="ghost",
            size="1",
            color_scheme="gray",
            padding="0",
        ),
        width="100%",
        spacing="1",
        align="center",
    )


# ── 首页（话题输入） ──


def start_view() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.heading("苏格拉底学习引导", size="8", margin_bottom="1rem"),
            rx.text(
                "通过提问、精确化、引导的迭代过程，深化你对任意话题的理解",
                size="4",
                color=colors["text_secondary"],
                align="center",
                style={"max_width": "32rem"},
            ),
            rx.box(
                rx.input(
                    placeholder="输入你想探讨的话题...",
                    value=AppState.user_input,
                    on_change=AppState.set_user_input,
                    size="3",
                    width="100%",
                    radius="large",
                ),
                rx.button(
                    "开始探讨",
                    on_click=AppState.start_debate,
                    size="3",
                    width="100%",
                    margin_top="1rem",
                    color_scheme="blue",
                    disabled=AppState.user_input.strip() == "",
                ),
                width="100%",
                style={"max_width": "28rem"},
                margin_top="2rem",
            ),
            rx.box(
                rx.vstack(
                    rx.text("对话温度", size="2", color=colors["text_secondary"]),
                    rx.slider(
                        value=[AppState.agent_temperature],
                        on_value_commit=AppState.set_temperature_from_slider,
                        min=0.0,
                        max=1.5,
                        step=0.1,
                        width="100%",
                    ),
                    rx.text(AppState.agent_temperature.to_string(), size="1", color=colors["text_secondary"]),
                    spacing="1",
                ),
                width="100%",
                style={"max_width": "28rem"},
                margin_top="1.5rem",
            ),
            spacing="2",
            align="center",
        ),
        width="100%",
        height="60vh",
    )


# ── 聊天视图 ──


def active_chat_view() -> rx.Component:
    """Chat view for the active tab, using mirrored state fields."""
    return rx.vstack(
        rx.hstack(
            rx.heading(AppState.active_topic, size="5"),
            rx.spacer(),
            rx.button("新话题", on_click=AppState.clear_active_session, variant="soft", size="2"),
            width="100%",
            padding_y="1rem",
            border_bottom=f"1px solid {colors['border']}",
        ),
        rx.box(
            rx.vstack(
                rx.foreach(AppState.active_messages, message_bubble),
                rx.box(
                    interrupt_prompt(AppState.active_interrupt_value),
                    display=rx.cond(AppState.active_awaiting_user_response, "block", "none"),
                ),
                generating_indicator(AppState.active_current_node),
                # 锚点用于自动滚动
                rx.box(id="chat-scroll-anchor"),
                spacing="4",
                width="100%",
                # 每次消息变化时滚动到底部
                on_mount=rx.scroll_to("chat-scroll-anchor"),
            ),
            class_name="chat-container",
            width="100%",
            flex_grow=1,
            padding_y="1rem",
        ),
        rx.box(
            rx.box(
                rx.hstack(
                    rx.text_area(
                        placeholder="输入你的回应...",
                        value=AppState.user_input,
                        on_change=AppState.set_user_input,
                        size="3",
                        radius="large",
                        min_height="80px",
                        width="100%",
                    ),
                    rx.button(
                        "发送",
                        on_click=AppState.submit_user_response,
                        size="3",
                        color_scheme="blue",
                        disabled=AppState.user_input.strip() == "",
                    ),
                    align_items="flex-end",
                    width="100%",
                    class_name="input-container",
                ),
                display=rx.cond(AppState.active_awaiting_user_response, "block", "none"),
            ),
            rx.box(
                rx.text("正在生成中，请稍候...", color=colors["text_secondary"], text_align="center"),
                display=rx.cond(AppState.active_is_generating, "block", "none"),
                class_name="input-container",
                padding_y="1rem",
            ),
            class_name="input-area",
        ),
        width="100%",
        height="100%",
        spacing="0",
    )


# ── 侧边栏 ──


def sidebar() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("苏格拉底学习", size="6", margin_bottom="1rem"),
            # Tab 列表
            rx.text("会话", size="2", color=colors["text_secondary"], margin_top="0.5rem", width="100%"),
            rx.vstack(
                rx.foreach(AppState.tabs, tab_item),
                width="100%",
                spacing="1",
            ),
            # Tab 操作按钮
            rx.hstack(
                rx.button(
                    "+",
                    on_click=AppState.add_tab,
                    variant="ghost",
                    size="2",
                    title="新建会话",
                ),
                rx.button(
                    "✕",
                    on_click=AppState.remove_active_tab,
                    variant="ghost",
                    size="2",
                    title="关闭当前会话",
                    disabled=AppState.tabs.length() <= 1,
                ),
                width="100%",
                justify="center",
                spacing="1",
            ),
            rx.spacer(),
            # 模型设置链接
            rx.el.a(
                rx.hstack(
                    rx.icon("settings"),
                    rx.text("模型设置"),
                    width="100%",
                    padding="0.75rem",
                    border_radius="0.5rem",
                    _hover={"background_color": colors["border"]},
                ),
                href="/settings",
                width="100%",
                text_decoration="none",
                color="inherit",
            ),
            # 主题切换
            rx.hstack(
                rx.cond(AppState.dark_mode, rx.icon("moon"), rx.icon("sun")),
                rx.switch(checked=AppState.dark_mode, on_change=AppState.toggle_dark_mode),
                justify="between",
                width="100%",
                padding="0.75rem",
            ),
            align_items="flex-start",
            height="100%",
            width="100%",
        ),
        class_name="sidebar",
    )


# ── 主页面 ──


def chat_page() -> rx.Component:
    """Main chat page. 用 has_active_conversation 切换 start / chat 视图。"""
    has_conv = AppState.has_active_conversation
    return rx.hstack(
        sidebar(),
        rx.box(
            rx.box(start_view(), display=rx.cond(has_conv, "none", "flex")),
            rx.box(active_chat_view(), display=rx.cond(has_conv, "flex", "none"), width="100%"),
            class_name="main-content",
            margin_left="280px",
            width="100%",
            height="100vh",
        ),
        width="100%",
        height="100vh",
        on_mount=AppState.initialize,
    )

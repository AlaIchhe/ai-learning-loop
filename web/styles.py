"""Global styles for Reflex UI, matching original Streamlit design."""
import reflex as rx

# 颜色系统 - 与原Streamlit版本保持一致
colors = {
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_light": "#3b82f6",
    "ai_bubble": "#f1f5f9",
    "user_bubble": "#2563eb",
    "text_primary": "#0f172a",
    "text_secondary": "#64748b",
    "bg": "#ffffff",
    "bg_sidebar": "#f8fafc",
    "border": "#e2e8f0",
    # 暗色模式
    "dark": {
        "bg": "#0f172a",
        "bg_sidebar": "#1e293b",
        "ai_bubble": "#1e293b",
        "user_bubble": "#2563eb",
        "text_primary": "#f1f5f9",
        "text_secondary": "#94a3b8",
        "border": "#334155",
    }
}

# 全局样式
global_style = {
    "font_family": "'Inter', 'PingFang SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, sans-serif",
    "background_color": colors["bg"],
    "color": colors["text_primary"],
    "min_height": "100vh",
    # 主容器最大宽度，保持和原Streamlit一致的阅读宽度
    ".main-content": {
        "max_width": "48rem",
        "margin": "0 auto",
        "padding": "2rem 1rem 8rem 1rem",
    },
    # 消息容器
    ".chat-container": {
        "display": "flex",
        "flex_direction": "column",
        "gap": "1.5rem",
    },
    # 消息基础样式
    ".chat-message": {
        "display": "flex",
        "gap": "0.75rem",
        "animation": "messageSlideIn 0.3s ease-out",
    },
    ".ai-message": {
        "flex_direction": "row",
    },
    ".user-message": {
        "flex_direction": "row-reverse",
    },
    # 头像
    ".message-avatar": {
        "width": "2rem",
        "height": "2rem",
        "border_radius": "0.5rem",
        "display": "flex",
        "align_items": "center",
        "justify_content": "center",
        "flex_shrink": "0",
        "font_size": "1rem",
    },
    ".ai-avatar": {
        "background_color": colors["bg_sidebar"],
    },
    ".user-avatar": {
        "background_color": colors["primary"],
        "color": "white",
    },
    # 消息气泡
    ".message-content": {
        "max_width": "80%",
        "display": "flex",
        "flex_direction": "column",
        "gap": "0.25rem",
    },
    ".message-name": {
        "font_size": "0.75rem",
        "font_weight": "500",
        "color": colors["text_secondary"],
        "padding_x": "0.25rem",
    },
    ".message-bubble": {
        "padding": "0.875rem 1rem",
        "border_radius": "1rem",
        "line_height": "1.6",
        "font_size": "0.9375rem",
        "box_shadow": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
    },
    ".ai-bubble": {
        "background_color": colors["ai_bubble"],
        "color": colors["text_primary"],
        "border_bottom_left_radius": "0.25rem",
    },
    ".user-bubble": {
        "background_color": colors["user_bubble"],
        "color": "white",
        "border_bottom_right_radius": "0.25rem",
    },
    # 输入框区域 - 固定在底部
    ".input-area": {
        "position": "fixed",
        "bottom": "0",
        "left": "0",
        "right": "0",
        "background_color": "rgba(255, 255, 255, 0.95)",
        "backdrop_filter": "blur(8px)",
        "padding": "1rem",
        "border_top": f"1px solid {colors['border']}",
        "z_index": "10",
    },
    ".input-container": {
        "max_width": "48rem",
        "margin": "0 auto",
    },
    # 侧边栏
    ".sidebar": {
        "width": "280px",
        "background_color": colors["bg_sidebar"],
        "border_right": f"1px solid {colors['border']}",
        "height": "100vh",
        "padding": "1rem",
        "position": "fixed",
        "left": "0",
        "top": "0",
        "overflow_y": "auto",
    },
    # 打字光标动画
    ".typing-cursor": {
        "display": "inline-block",
        "width": "0.5rem",
        "height": "1.2em",
        "background_color": "currentColor",
        "margin_left": "0.125rem",
        "animation": "blink-cursor 0.8s step-end infinite",
        "vertical_align": "text-bottom",
    },
    # 动画定义
    "@keyframes blink-cursor": {
        "0%, 100%": {"opacity": "1"},
        "50%": {"opacity": "0"},
    },
    "@keyframes messageSlideIn": {
        "from": {
            "opacity": "0",
            "transform": "translateY(10px)",
        },
        "to": {
            "opacity": "1",
            "transform": "translateY(0)",
        },
    },
    # 按钮样式
    "button": {
        "border_radius": "0.5rem",
        "transition": "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
        "cursor": "pointer",
        "_hover": {
            "transform": "translateY(-1px)",
        },
    },
    ".primary-button": {
        "background_color": colors["primary"],
        "color": "white",
        "_hover": {
            "background_color": colors["primary_hover"],
        },
    },
    # 隐藏 Reflex 连接错误通知（Windows polling 模式下的误报）
    '[role="region"][aria-label="Notifications"]': {
        "display": "none",
    },
    'div[data-testid="connection-banner"]': {
        "display": "none",
    },
    # 滚动条美化
    "::-webkit-scrollbar": {
        "width": "6px",
    },
    "::-webkit-scrollbar-track": {
        "background": "transparent",
    },
    "::-webkit-scrollbar-thumb": {
        "background": "#cbd5e1",
        "border_radius": "3px",
        "_hover": {
            "background": "#94a3b8",
        },
    },
}

# 消息角色配置
role_config = {
    "user": {"is_user": True, "avatar": "👤", "name": "你"},
    "questioner": {"is_user": False, "avatar": "⚔️", "name": "提问者"},
    "refiner": {"is_user": False, "avatar": "✨", "name": "提炼者"},
    "guide": {"is_user": False, "avatar": "🧠", "name": "引导者"},
    "system": {"is_user": False, "avatar": "📋", "name": "系统"},
}

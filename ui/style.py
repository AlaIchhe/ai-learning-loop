"""
UI 样式注入 —— 全局 CSS + 自动滚动 JS。

原则：
1. 纯渲染层辅助，不包含任何业务逻辑。
2. CSS 从外部文件加载（ui/style.css），便于独立编辑和审查。
3. JavaScript 注入实现自动滚动和光标动画支持。
"""

from pathlib import Path

import streamlit as st

# CSS 文件路径（相对于本模块）
_CSS_PATH = Path(__file__).resolve().parent / "style.css"


def inject_global_css() -> None:
    """注入全局 CSS 样式表 + 自动滚动 JavaScript。

    应在 st.set_page_config() 之后、任何页面内容渲染之前调用。
    通过 st.session_state 缓存注入状态，同一 session 内仅执行一次。

    CSS 涵盖:
        - 字体（Inter + PingFang SC）
        - 消息气泡（圆角、阴影、hover）
        - 按钮 hover 过渡动画
        - 输入框 focus 高亮环
        - Expander 圆角 + hover
        - 侧边栏美化
        - 滚动条美化
        - 打字闪烁光标动画 (@keyframes blink-cursor)
        - 暗色模式适配

    JS 涵盖:
        - 新内容自动平滑滚动到底部
        - 流式输出时持续滚动，非流式时仅在用户已在底部时滚动
    """
    if st.session_state.get("_css_injected"):
        return

    # ---- CSS 注入 ----
    if _CSS_PATH.exists():
        css_content = _CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

    # ---- 自动滚动 JS 注入 ----
    st.markdown("""
<script>
(function() {
    // 自动滚动：监听 Streamlit 内容变化，平滑滚动到底部
    // 仅在用户已在底部（或流式输出时）才自动滚动，避免干扰手动阅读历史消息
    let autoScroll = true;
    let scrollTimeout = null;

    function isNearBottom(threshold = 150) {
        const scrollBottom = window.innerHeight + window.scrollY;
        return scrollBottom >= document.body.scrollHeight - threshold;
    }

    function scrollToBottom(smooth = true) {
        window.scrollTo({
            top: document.body.scrollHeight,
            behavior: smooth ? 'smooth' : 'instant'
        });
    }

    // 监听用户手动滚动：如果用户向上滚动，暂停自动滚动
    window.addEventListener('scroll', function() {
        if (scrollTimeout) clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(function() {
            if (!isNearBottom(100)) {
                autoScroll = false;
            } else {
                autoScroll = true;
            }
        }, 150);
    }, { passive: true });

    // MutationObserver 监听 DOM 变化（新消息/新内容）
    const observer = new MutationObserver(function() {
        if (autoScroll) {
            scrollToBottom(true);
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });

    // 初始滚动
    if (autoScroll) {
        setTimeout(function() { scrollToBottom(false); }, 200);
    }
})();
</script>
""", unsafe_allow_html=True)

    st.session_state["_css_injected"] = True


def typing_cursor_html() -> str:
    """返回打字闪烁光标的 HTML 片段。

    在流式文本末尾附加此 HTML 以显示闪烁光标。
    流式结束后应移除。

    Example:
        content = accumulated_text + typing_cursor_html()
        placeholder.markdown(content, unsafe_allow_html=True)
    """
    return '<span class="typing-cursor">▍</span>'

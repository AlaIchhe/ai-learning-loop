"""
Streamlit 展现层 —— 纯渲染与输入收集。

原则：
1. UI 层不包含任何业务逻辑。所有状态变更由 LangGraph 图驱动。
2. st.session_state 仅管理 UI 会话元数据（thread_id、api_key），
   辩论状态完全存储在 LangGraph checkpointer 中。
3. 使用动态 interrupt() + Command(resume=...) 实现人工介入。
4. 每个渲染函数只读取数据并绘制，不修改 graph state。
"""

# .env 必须在所有 LangChain/LangGraph import 之前加载，
# 否则 LANGCHAIN_TRACING_V2 等环境变量不会生效。
# ruff: noqa: E402
from pathlib import Path

from dotenv import load_dotenv

# 从脚本所在位置向上查找项目根目录的 .env，
# 确保无论从哪个目录启动 streamlit run 都能正确加载环境变量。
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()  # fallback: 尝试 cwd 或父目录自动搜索

import os
from typing import cast
from uuid import uuid4

import streamlit as st
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.opponent import opponent_compute_node, opponent_interact_node
from agents.presenter import presenter_compute_node, presenter_interact_node
from agents.referee import referee_deliberate_node
from core.schemas import RefereeJudgment
from core.state import AgentState
from workflow.graph import build_graph

# =============================================================================
# 页面配置
# =============================================================================

st.set_page_config(
    page_title="多智能体论题演化系统",
    page_icon="🎓",
    layout="wide",
)


# =============================================================================
# 侧边栏 —— 系统配置
# =============================================================================


def _render_sidebar() -> None:
    """渲染侧边栏：API Key 配置与初始论题。"""
    # ---- 读取 .env 中的配置状态 ----
    env_model = os.getenv("LLM_MODEL", "")
    env_base = os.getenv("LLM_BASE_URL", "")
    env_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    _placeholder_key = "sk-not-configured"
    env_configured = bool(env_key and env_key != _placeholder_key)

    if not env_configured or not env_model:
        provider_label = ""
    elif not env_base:
        provider_label = "OpenAI"
    elif "deepseek" in env_base.lower():
        provider_label = "DeepSeek"
    elif "siliconflow" in env_base.lower():
        provider_label = "硅基流动"
    elif "ollama" in env_base.lower() or "localhost" in env_base.lower():
        provider_label = "Ollama (本地)"
    else:
        provider_label = "自定义"

    with st.sidebar:
        st.title("⚙️ 配置")

        # ---- API Key 区域 ----
        if env_configured:
            masked_key = env_key[:12] + "..." + env_key[-4:] if len(env_key) > 16 else "****"
            st.success("✅ 已从 .env 加载配置")
            st.caption(f"供应商: {provider_label}")
            st.caption(f"模型: {env_model}")
            st.caption(f"Key: {masked_key}")

            with st.expander("🔧 手动覆盖 API Key（可选）"):
                st.caption("输入后将覆盖 .env 中的 Key，仅本次会话有效。")
                api_key = st.text_input(
                    "API Key（覆盖 .env）",
                    type="password",
                    key="api_key_override",
                    help="支持 DeepSeek / OpenAI / 硅基流动 等。",
                )
                if api_key:
                    st.session_state["api_key"] = api_key
                    os.environ["LLM_API_KEY"] = api_key
                    os.environ["OPENAI_API_KEY"] = api_key
                    st.info("已覆盖，本次会话生效。")
        else:
            st.warning("⚠️ 未检测到 .env 配置")
            st.caption("推荐在项目根目录创建 `.env` 文件配置 API Key。")
            api_key = st.text_input(
                "LLM API Key",
                type="password",
                value=st.session_state.get("api_key", ""),
                help="支持 DeepSeek / OpenAI / 硅基流动 等。仅本次会话有效。",
            )
            if api_key:
                st.session_state["api_key"] = api_key
                os.environ["LLM_API_KEY"] = api_key
                os.environ["OPENAI_API_KEY"] = api_key

            with st.expander("🛠️ 高级模型设置（可选）"):
                st.caption("自定义模型与端点，覆盖默认值。")
                custom_model = st.text_input(
                    "模型名", value="deepseek-chat", key="custom_model",
                )
                custom_base = st.text_input(
                    "Base URL", value="https://api.deepseek.com/v1", key="custom_base",
                )
                if st.button("应用模型设置"):
                    os.environ["LLM_MODEL"] = custom_model
                    os.environ["LLM_BASE_URL"] = custom_base
                    st.success(f"已切换至 {custom_model}")
                    st.rerun()

        st.divider()

        # ---- 初始论题输入 ----
        disabled = st.session_state.get("debate_started", False)
        initial_thesis = st.text_area(
            "初始论题 (Initial Thesis)",
            value=st.session_state.get(
                "initial_thesis_input",
                "人工智能的发展应该受到严格监管，以确保其安全性和可控性。",
            ),
            disabled=disabled,
            height=100,
            help="输入你希望被审视和演化的核心论题。",
        )
        st.session_state["initial_thesis_input"] = initial_thesis

        st.divider()

        # ---- 控制按钮 ----
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 开始辩论", disabled=disabled, use_container_width=True):
                _on_start_debate(initial_thesis or "人工智能的发展应该受到严格监管。")
        with col2:
            if st.button("🔄 重置", use_container_width=True):
                _on_reset()

        has_any_key = bool(
            st.session_state.get("api_key")
            or (env_key and env_key != _placeholder_key)
        )
        if not has_any_key:
            st.warning("请先配置 LLM API Key（.env 或侧边栏均可）")


# =============================================================================
# UI 事件处理
# =============================================================================


def _on_start_debate(initial_thesis: str) -> None:
    """开始辩论：初始化 graph state 并执行到第一个中断点。"""
    _placeholder_key = "sk-not-configured"
    api_key = st.session_state.get("api_key", "")
    env_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    has_key = bool(api_key) or bool(env_key and env_key != _placeholder_key)
    if not has_key:
        st.error("请先配置 LLM API Key（在项目 .env 文件中或侧边栏输入均可）")
        return

    checkpointer = MemorySaver()
    graph = build_graph(
        opponent_compute_node=opponent_compute_node,
        opponent_interact_node=opponent_interact_node,
        presenter_compute_node=presenter_compute_node,
        presenter_interact_node=presenter_interact_node,
        referee_deliberate_node=referee_deliberate_node,
        checkpointer=checkpointer,
    )
    thread_id = str(uuid4())

    st.session_state["debate_started"] = True
    st.session_state["thread_id"] = thread_id
    st.session_state["checkpointer"] = checkpointer
    st.session_state["graph"] = graph

    initial_state: AgentState = {
        "current_thesis": initial_thesis,
        "round": 1,
        "status": "idle",
        "messages": [],
        "history": [],
        "final_result": "",
        "_critique": "",
        "_user_response": "",
        "_draft_thesis": "",
        "_confirmed_thesis": "",
        "_improvement_hint": "",
    }

    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    graph.invoke(initial_state, config)
    st.rerun()


def _on_reset() -> None:
    """重置所有会话状态。"""
    for key in [
        "debate_started", "thread_id", "checkpointer", "graph",
        "initial_thesis_input",
    ]:
        st.session_state.pop(key, None)
    st.rerun()


def _resume_with_input(user_value: str) -> None:
    """从当前中断点恢复执行，传入用户输入。"""
    graph = st.session_state.get("graph")
    thread_id = st.session_state.get("thread_id")
    if graph is None or thread_id is None:
        return
    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    graph.invoke(Command(resume=user_value), config)
    st.rerun()


# =============================================================================
# 状态读取
# =============================================================================


def _get_current_state() -> AgentState | None:
    """从 LangGraph checkpointer 读取当前状态快照。"""
    graph = st.session_state.get("graph")
    thread_id = st.session_state.get("thread_id")
    if graph is None or thread_id is None:
        return None
    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    snapshot = graph.get_state(config)
    if snapshot is None or snapshot.values is None:
        return None
    return snapshot.values


def _get_interrupt_value() -> str | None:
    """获取当前活跃中断的值（若有）。"""
    graph = st.session_state.get("graph")
    thread_id = st.session_state.get("thread_id")
    if graph is None or thread_id is None:
        return None
    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    snapshot = graph.get_state(config)
    interrupts = getattr(snapshot, "interrupts", None) or ()
    if interrupts:
        return str(interrupts[0].value)
    return None


# =============================================================================
# 中断 UI 渲染
# =============================================================================


def _render_interrupt_ui(status: str, interrupt_value: str) -> None:
    """根据当前 status 渲染对应的中断输入界面。"""
    if status == "awaiting_critique_response":
        st.subheader("⚔️ 批判者的质疑")
        with st.chat_message("opponent", avatar="⚔️"):
            st.markdown(interrupt_value)
        st.divider()
        st.subheader("💬 你的回应")
        user_response = st.text_area(
            "针对批判者的质疑，请给出你的回应",
            placeholder="回应批判者的观点，澄清立场或修正论题...",
            height=150,
            key="critique_response_input",
        )
        if st.button("📤 提交回应", type="primary", use_container_width=True):
            if user_response.strip():
                _resume_with_input(user_response)
            else:
                st.warning("请输入回应内容")

    elif status == "awaiting_thesis_confirmation":
        st.subheader("📝 陈述者的精确化草稿")
        with st.chat_message("presenter", avatar="🗣️"):
            st.markdown(interrupt_value)
        st.divider()
        st.subheader("✅ 确认论题")
        st.caption("你可以直接确认，也可以编辑后再确认。")
        confirmed = st.text_area(
            "论题（可编辑）",
            value=interrupt_value,
            height=120,
            key="thesis_confirmation_input",
        )
        if st.button("✅ 确认论题", type="primary", use_container_width=True):
            if confirmed.strip():
                _resume_with_input(confirmed)
            else:
                st.warning("论题不能为空")


# =============================================================================
# 状态展示
# =============================================================================


def _render_status_badge(status: str) -> None:
    """渲染状态标签。"""
    label_map = {
        "idle": "⏳ 等待中",
        "opponent_computing": "⚔️ 批判者分析中…",
        "awaiting_critique_response": "💬 等待你的回应",
        "presenter_computing": "🗣️ 陈述者精确化中…",
        "awaiting_thesis_confirmation": "✅ 等待你确认论题",
        "referee_deliberating": "⚖️ 裁判审议中…",
        "done": "🏁 论题演化完成",
    }
    label = label_map.get(status, status)
    st.markdown(f"### {label}")


def _render_progress(current_round: int) -> None:
    """渲染轮次指示器。"""
    st.caption(f"当前轮次: 第 {current_round} 轮")


def _render_conversation(messages: list[dict]) -> None:
    """渲染对话历史。"""
    if not messages:
        st.info("辩论尚未开始，请在侧边栏输入初始论题并点击「开始辩论」。")
        return

    role_meta = {
        "system": ("📋", "系统"),
        "opponent": ("⚔️", "批判者"),
        "presenter": ("🗣️", "陈述者"),
        "referee": ("⚖️", "裁判"),
        "user": ("👤", "你"),
    }

    for msg in messages:
        role = msg.get("role", "unknown")
        emoji, label = role_meta.get(role, ("❓", role))
        round_num = msg.get("round", "?")

        with st.chat_message(label, avatar=emoji):
            st.caption(f"第 {round_num} 轮 · {label}")
            st.markdown(str(msg.get("content", "")))


def _render_judgment(judgment: RefereeJudgment | dict | None) -> None:
    """渲染裁判的审议结果。"""
    if judgment is None:
        return
    j = judgment if isinstance(judgment, dict) else judgment.model_dump()

    st.divider()
    st.subheader("📊 本轮审议")

    decision = "🔄 继续下一轮" if j.get("continue_debate") else "🏁 论题已完善"
    st.info(f"**判定**: {decision}")

    st.markdown("**拼合后的新论题**")
    st.success(j.get("new_thesis", ""))

    with st.expander("📝 审议详情"):
        st.markdown(f"**理由**: {j.get('reasoning', '')}")
        st.markdown(f"**建议**: {j.get('improvement_hint', '')}")


def _render_final_result(history: list, final_result: str) -> None:
    """渲染论题演化终局总结。"""
    if not history:
        return

    st.divider()
    st.subheader("🏁 论题演化总结")

    # 展示论题演化链
    st.markdown("### 论题演化历程")
    for i, r in enumerate(history):
        record = r if isinstance(r, dict) else r.model_dump()
        round_num = record.get("round_number", i + 1)
        before = record.get("thesis_before", "")
        after = record.get("thesis_after", "")

        with st.expander(f"第 {round_num} 轮: {before[:60]}... → {after[:60]}..."):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**本轮开始**")
                st.text(before)
                st.markdown("**批判**")
                st.text(record.get("critique", ""))
                st.markdown("**你的回应**")
                st.text(record.get("user_response", ""))
            with col2:
                st.markdown("**陈述者草稿**")
                st.text(record.get("draft_thesis", ""))
                st.markdown("**你确认的版本**")
                st.text(record.get("confirmed_thesis", ""))
                st.markdown("**裁判拼合**")
                st.info(after)

    # 统计
    total = len(history)
    continued = sum(
        1 for r in history
        for d in [r if isinstance(r, dict) else r.model_dump()]
        if d.get("continue_debate")
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("总轮次", total)
    col2.metric("继续轮次", continued)
    col3.metric("终局轮次", total - continued)

    if final_result:
        st.divider()
        st.subheader("📋 终局报告")
        st.markdown(final_result)


# =============================================================================
# 主页面
# =============================================================================


def main() -> None:
    """主入口：组合侧边栏、中断 UI 与状态展示。"""
    _render_sidebar()

    st.title("🎓 多智能体论题演化系统")
    st.caption("批判者审视 · 陈述者精确化 · 你确认 · 裁判拼合演化")

    state = _get_current_state()

    if state is None:
        st.info("在侧边栏输入初始论题并点击「开始辩论」")
        return

    status = state.get("status", "idle")

    # 检查是否有活跃中断
    interrupt_value = _get_interrupt_value()

    if interrupt_value and status in (
        "awaiting_critique_response",
        "awaiting_thesis_confirmation",
    ):
        # 在中断点：渲染输入界面
        _render_status_badge(status)
        _render_conversation(state.get("messages", []))
        st.divider()
        _render_interrupt_ui(status, interrupt_value)
        return

    # 非中断状态：展示完整状态
    _render_status_badge(status)
    _render_progress(state.get("round", 1))

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("💬 对话过程")
        _render_conversation(state.get("messages", []))

    with col_right:
        st.subheader("📊 裁判审议")
        # 从 history 的最后一项获取最近的 judgment
        history = state.get("history", [])
        if history and status == "done":
            last_record = history[-1]
            rec = last_record if isinstance(last_record, dict) else last_record.model_dump()
            _render_judgment({
                "continue_debate": rec.get("continue_debate", False),
                "new_thesis": rec.get("thesis_after", ""),
                "reasoning": rec.get("referee_reasoning", ""),
                "improvement_hint": "",
            })
        else:
            st.info("等待裁判审议…")

        if status == "done":
            _render_final_result(history, state.get("final_result", ""))


if __name__ == "__main__":
    main()

"""
Streamlit 展现层 —— 纯渲染与输入收集。

原则：
1. UI 层不包含任何业务逻辑。所有状态变更由 LangGraph 图驱动。
2. st.session_state 仅管理 UI 会话元数据（thread_id、api_key），
   辩论状态完全存储在 LangGraph checkpointer 中。
3. 每个渲染函数只读取数据并绘制，不修改 graph state。
"""

# .env 必须在所有 LangChain/LangGraph import 之前加载，
# 否则 LANGCHAIN_TRACING_V2 等环境变量不会生效。
# ruff: noqa: E402
from dotenv import load_dotenv

load_dotenv()

import os
from uuid import uuid4

import streamlit as st
from langgraph.checkpoint.memory import MemorySaver

from core.state import AgentState
from core.schemas import RefereeJudgment
from agents.presenter import presenter_node
from agents.opponent import opponent_node
from agents.referee import referee_node
from workflow.graph import build_graph


# =============================================================================
# 页面配置
# =============================================================================

st.set_page_config(
    page_title="多智能体辩论学习系统",
    page_icon="🎓",
    layout="wide",
)

# =============================================================================
# 侧边栏 —— 系统配置（非业务逻辑）
# =============================================================================


def _render_sidebar() -> None:
    """渲染侧边栏：API Key 配置与辩论参数。"""
    with st.sidebar:
        st.title("⚙️ 配置")

        # API Key
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.get("api_key", ""),
            help="输入你的 OpenAI API Key，仅本次会话有效。",
        )
        if api_key:
            st.session_state["api_key"] = api_key
            os.environ["OPENAI_API_KEY"] = api_key

        st.divider()

        # 辩论参数（仅在尚未开始时可修改）
        disabled = st.session_state.get("debate_started", False)
        topic = st.text_input(
            "辩论主题",
            value=st.session_state.get("topic_input", "AI 是否应该被严格监管？"),
            disabled=disabled,
        )
        max_rounds = st.slider(
            "最大轮次",
            min_value=1,
            max_value=5,
            value=st.session_state.get("max_rounds_input", 2),
            disabled=disabled,
        )
        st.session_state["topic_input"] = topic
        st.session_state["max_rounds_input"] = max_rounds

        st.divider()

        # 控制按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 开始辩论", disabled=disabled, use_container_width=True):
                _on_start_debate(topic, max_rounds)
        with col2:
            if st.button("🔄 重置", use_container_width=True):
                _on_reset()

        if not api_key:
            st.warning("请先输入 OpenAI API Key")


# =============================================================================
# UI 事件处理（不包含业务逻辑，只做会话初始化和调用图）
# =============================================================================


def _on_start_debate(topic: str, max_rounds: int) -> None:
    """开始辩论：初始化 graph state 并执行第一步。"""
    api_key = st.session_state.get("api_key", "")
    if not api_key:
        st.error("请输入 API Key")
        return

    # 初始化 LangGraph（checkpointer 必须参与编译，interrupt 才能恢复）
    checkpointer = MemorySaver()
    graph = build_graph(
        presenter_node=presenter_node,
        opponent_node=opponent_node,
        referee_node=referee_node,
        checkpointer=checkpointer,
    )
    thread_id = str(uuid4())

    st.session_state["debate_started"] = True
    st.session_state["thread_id"] = thread_id
    st.session_state["checkpointer"] = checkpointer
    st.session_state["graph"] = graph

    # 构造初始状态
    initial_state: AgentState = {
        "topic": topic,
        "round": 1,
        "max_rounds": max_rounds,
        "status": "idle",
        "messages": [],
        "presenter_argument": "",
        "opponent_rebuttal": "",
        "referee_judgment": None,
        "history": [],
        "final_result": "",
    }

    config = {"configurable": {"thread_id": thread_id}}
    # 首次调用：从 idle 走到第一个 interrupt_before（presenter）
    graph.invoke(initial_state, config)
    st.rerun()


def _on_reset() -> None:
    """重置所有会话状态。"""
    for key in [
        "debate_started",
        "thread_id",
        "checkpointer",
        "graph",
        "topic_input",
        "max_rounds_input",
    ]:
        st.session_state.pop(key, None)
    st.rerun()


def _on_continue() -> None:
    """继续执行：从当前断点恢复 graph 执行到下一个断点。"""
    graph = st.session_state.get("graph")
    thread_id = st.session_state.get("thread_id")
    if graph is None or thread_id is None:
        return
    config = {"configurable": {"thread_id": thread_id}}
    # 传入 None 表示从当前 checkpoint 恢复
    graph.invoke(None, config)
    st.rerun()


# =============================================================================
# 状态读取（只读，从 checkpointer 获取）
# =============================================================================


def _get_current_state() -> AgentState | None:
    """从 LangGraph checkpointer 读取当前状态快照。

    这是一个只读操作，不修改任何状态。
    """
    graph = st.session_state.get("graph")
    thread_id = st.session_state.get("thread_id")
    if graph is None or thread_id is None:
        return None
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if snapshot is None or snapshot.values is None:
        return None
    return snapshot.values


# =============================================================================
# 渲染函数（只读取 state，纯展示）
# =============================================================================


def _render_status_badge(status: str) -> None:
    """渲染状态标签。"""
    label_map = {
        "idle": "⏳ 等待中",
        "presenting": "🗣️ 陈述者论证中…",
        "opposing": "⚔️ 反驳者反驳中…",
        "judging": "⚖️ 裁判评分中…",
        "done": "✅ 辩论结束",
    }
    label = label_map.get(status, status)
    st.markdown(f"### {label}")


def _render_progress(current_round: int, max_rounds: int) -> None:
    """渲染轮次进度条。"""
    ratio = current_round / max_rounds
    st.progress(ratio, text=f"第 {current_round} / {max_rounds} 轮")


def _render_conversation(messages: list[dict]) -> None:
    """渲染对话历史。

    每条消息根据角色使用不同的样式和头像。
    """
    if not messages:
        st.info("辩论尚未开始，请点击「开始辩论」按钮。")
        return

    role_meta = {
        "system": ("📋", "系统"),
        "presenter": ("🗣️", "陈述者"),
        "opponent": ("⚔️", "反驳者"),
        "referee": ("⚖️", "裁判"),
    }

    for msg in messages:
        role = msg.get("role", "unknown")
        emoji, label = role_meta.get(role, ("❓", role))
        round_num = msg.get("round", "?")

        with st.chat_message(label, avatar=emoji):
            st.caption(f"第 {round_num} 轮 · {label}")
            st.markdown(msg.get("content", ""))


def _render_judgment(judgment: RefereeJudgment | dict | None) -> None:
    """渲染裁判的结构化评分。

    仅负责展示，不修改 judgment 数据。
    """
    if judgment is None:
        return
    # 兼容 dict 和 RefereeJudgment 实例
    if isinstance(judgment, dict):
        j = judgment
    else:
        j = judgment.model_dump()

    st.divider()
    st.subheader("📊 本轮评分")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**陈述者**")
        ps = j.get("presenter_score", {})
        st.metric("清晰度", f"{ps.get('clarity', 0):.1f}")
        st.metric("逻辑性", f"{ps.get('logic', 0):.1f}")
        st.metric("论据", f"{ps.get('evidence', 0):.1f}")
        st.metric("说服力", f"{ps.get('persuasiveness', 0):.1f}")
        st.markdown(f"### 🏆 {j.get('presenter_total', 0):.1f} / 10")

    with col2:
        st.markdown("**反驳者**")
        os_ = j.get("opponent_score", {})
        st.metric("清晰度", f"{os_.get('clarity', 0):.1f}")
        st.metric("逻辑性", f"{os_.get('logic', 0):.1f}")
        st.metric("论据", f"{os_.get('evidence', 0):.1f}")
        st.metric("说服力", f"{os_.get('persuasiveness', 0):.1f}")
        st.markdown(f"### 🏆 {j.get('opponent_total', 0):.1f} / 10")

    winner = j.get("winner", "draw")
    winner_label = {"presenter": "陈述者胜 🗣️", "opponent": "反驳者胜 ⚔️", "draw": "平局 🤝"}
    st.info(f"**本轮胜者**: {winner_label.get(winner, winner)}")

    with st.expander("📝 裁判详情"):
        st.markdown(f"**评分理由**: {j.get('reasoning', '')}")
        st.markdown(f"**陈述者亮点**: {j.get('presenter_strength', '')}")
        st.markdown(f"**陈述者不足**: {j.get('presenter_weakness', '')}")
        st.markdown(f"**反驳者亮点**: {j.get('opponent_strength', '')}")
        st.markdown(f"**反驳者不足**: {j.get('opponent_weakness', '')}")
        st.markdown(f"**改进建议**: {j.get('improvement_hint', '')}")


def _render_final_result(history: list, final_result: str) -> None:
    """渲染辩论终局总结。"""
    if not history:
        return

    st.divider()
    st.subheader("🏁 最终结果")

    # 统计各轮胜者
    presenter_wins = sum(
        1 for r in history
        for j in [r.get("judgment", {}) if isinstance(r, dict) else r.judgment.model_dump()]
        if j.get("winner") == "presenter"
    )
    opponent_wins = sum(
        1 for r in history
        for j in [r.get("judgment", {}) if isinstance(r, dict) else r.judgment.model_dump()]
        if j.get("winner") == "opponent"
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("陈述者胜", presenter_wins)
    col2.metric("反驳者胜", opponent_wins)
    col3.metric("平局", len(history) - presenter_wins - opponent_wins)

    if final_result:
        st.markdown(final_result)


def _render_controls(status: str) -> None:
    """渲染控制按钮。

    根据当前 status 决定显示哪些操作。
    此函数只渲染 UI，不包含分支逻辑。
    """
    if status == "idle":
        return  # 尚未开始，由侧边栏的「开始」按钮负责
    if status == "done":
        st.success("辩论已完成！点击侧边栏「重置」可开始新一轮。")
        return

    # 在断点处显示「继续」按钮
    interrupt_statuses = {"presenting", "opposing", "judging"}
    if status in interrupt_statuses:
        st.button("▶️ 继续执行", on_click=_on_continue, type="primary", use_container_width=True)


# =============================================================================
# 主页面
# =============================================================================


def main() -> None:
    """主入口：组合侧边栏与主内容区。"""

    _render_sidebar()

    st.title("🎓 多智能体辩论学习系统")
    st.caption("陈述者 vs 反驳者 · 裁判评分 · 多轮对抗")

    # 读取当前状态（只读）
    state = _get_current_state()

    if state is None:
        st.info("在侧边栏输入主题并点击「开始辩论」")
        return

    # 渲染状态标签
    status = state.get("status", "idle")
    _render_status_badge(status)

    # 渲染进度
    _render_progress(state.get("round", 1), state.get("max_rounds", 3))

    # 两栏布局：对话 + 评分
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("💬 辩论过程")
        _render_conversation(state.get("messages", []))

    with col_right:
        st.subheader("📊 当前裁判结果")
        _render_judgment(state.get("referee_judgment"))

        # 终局汇总
        if status == "done":
            _render_final_result(
                state.get("history", []),
                state.get("final_result", ""),
            )

    st.divider()
    _render_controls(status)


if __name__ == "__main__":
    main()

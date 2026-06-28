"""
Streamlit 展现层 —— 纯渲染与输入收集。

原则：
1. UI 层不包含任何业务逻辑。所有状态变更由 LangGraph 图驱动。
2. st.session_state 仅管理 UI 会话元数据（thread_id、api_key），
   辩论状态完全存储在 LangGraph checkpointer 中。
3. 使用动态 interrupt() + Command(resume=...) 实现人工介入。
4. 每个渲染函数只读取数据并绘制，不修改 graph state。
5. 多标签页：一个共享 graph + MemorySaver 服务多个独立辩论会话。
6. Per-tab 模型配置：每个标签页在启动时捕获侧边栏的模型配置，
   后续该标签页的所有 LLM 调用使用启动时的配置，不受侧边栏修改影响。
"""

# .env 必须在所有 LangChain/LangGraph import 之前加载，
# 否则 LANGCHAIN_TRACING_V2 等环境变量不会生效。
# ruff: noqa: E402
from pathlib import Path

from core.env import setup_environment

# 从脚本所在位置定位项目根目录，复用统一环境初始化入口。
_project_root = Path(__file__).resolve().parent.parent
setup_environment(_project_root, verbose=False)

import os
import traceback
from typing import cast
from uuid import uuid4

import streamlit as st
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from agents.opponent import opponent_compute_node, opponent_interact_node
from agents.presenter import presenter_compute_node, presenter_interact_node
from agents.referee import referee_deliberate_node
from core.logging import TraceLogger, trace_id_context
from core.model import has_configured_api_key
from core.schemas import RefereeJudgment
from core.state import AgentState, make_initial_state
from ui.style import inject_global_css, typing_cursor_html
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
# 侧边栏 —— 系统配置（全局共享）
# =============================================================================


def _apply_api_key_override(api_key: str) -> None:
    """应用侧边栏临时 API Key 覆盖（仅当前进程/会话有效）。

    API Key 保持全局共享（同一用户的密钥），但模型名和端点可按标签页隔离。
    """
    st.session_state["api_key"] = api_key
    os.environ["LLM_API_KEY"] = api_key
    os.environ["OPENAI_API_KEY"] = api_key


def _apply_model_override(model: str, base_url: str) -> None:
    """应用侧边栏临时模型端点覆盖（仅影响新启动的辩论）。

    已在运行的标签页使用其启动时捕获的配置，不受此次修改影响。
    """
    os.environ["LLM_MODEL"] = model
    os.environ["LLM_BASE_URL"] = base_url


def _capture_model_config() -> dict[str, str]:
    """捕获当前有效的模型配置，供新标签页在启动时冻结。

    返回的 dict 存入 per-tab session，后续该标签页的所有 LLM 调用使用此配置。
    """
    config: dict[str, str] = {
        "model_name": os.getenv("LLM_MODEL", ""),
        "base_url": os.getenv("LLM_BASE_URL", ""),
    }
    # 侧边栏临时覆盖的 API key 也一并捕获（用于回退）
    api_key = st.session_state.get("api_key", "")
    if api_key:
        config["api_key"] = api_key
    return config


def _render_sidebar() -> None:
    """渲染侧边栏：API Key 配置、温度调节等全局设置。"""
    # ---- 读取 .env 中的配置状态 ----
    env_model = os.getenv("LLM_MODEL", "")
    env_base = os.getenv("LLM_BASE_URL", "")
    env_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    env_configured = has_configured_api_key()

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
                    _apply_api_key_override(api_key)
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
                _apply_api_key_override(api_key)

            with st.expander("🛠️ 高级模型设置（可选）"):
                st.caption("自定义模型与端点，覆盖默认值。")
                custom_model = st.text_input(
                    "模型名", value="deepseek-chat", key="custom_model",
                )
                custom_base = st.text_input(
                    "Base URL", value="https://api.deepseek.com/v1", key="custom_base",
                )
                if st.button("应用模型设置"):
                    _apply_model_override(custom_model, custom_base)
                    st.success(f"已切换至 {custom_model}")
                    st.rerun()

        st.divider()

        # ---- 温度调节（全局，新辩论生效） ----
        st.caption("🎚️ Agent 创造性")
        st.slider(
            "温度",
            min_value=0.0,
            max_value=1.5,
            value=0.7,
            step=0.1,
            help="0.0 = 保守确定，0.7 = 创造性（默认），1.5 = 高度发散。裁判固定为 0.0。新建辩论时生效。",
            key="agent_temperature",
        )

        # ---- 最大轮次（安全阀） ----
        st.caption("🛡️ 安全限制")
        st.slider(
            "最大轮次",
            min_value=1,
            max_value=20,
            value=10,
            step=1,
            help="达到最大轮次后强制终止辩论，防止无限循环消耗 API 费用。新建辩论时生效。",
            key="max_rounds",
        )

        st.divider()

        # ---- 全局操作提示 ----
        has_any_key = bool(st.session_state.get("api_key") or env_configured)
        if not has_any_key:
            st.warning("请先配置 LLM API Key（.env 或侧边栏均可）")

        # Per-tab 模型隔离说明
        if has_any_key and st.session_state.get("sessions"):
            started_count = sum(
                1 for s in st.session_state["sessions"].values()
                if s.get("started")
            )
            if started_count > 0:
                st.caption(
                    f"ℹ️ 模型配置仅对新辩论生效。"
                    f"当前 {started_count} 个运行中的标签页使用启动时的配置。"
                )


# =============================================================================
# 标签页管理
# =============================================================================


def _ensure_default_tab() -> None:
    """确保至少存在一个标签页。"""
    if "sessions" not in st.session_state:
        st.session_state["sessions"] = {}
    if not st.session_state["sessions"]:
        tab_id = "tab_1"
        st.session_state["sessions"][tab_id] = {
            "thread_id": "",
            "initial_thesis": "人工智能的发展应该受到严格监管，以确保其安全性和可控性。",
            "label": "辩论 1",
            "custom_label": "",
            "started": False,
            "model_config": {},
        }
        st.session_state["next_tab_id"] = 2


def _add_new_tab() -> str:
    """添加新的辩论标签页，返回标签页 ID。"""
    next_id = st.session_state.get("next_tab_id", 2)
    tab_id = f"tab_{next_id}"
    st.session_state["sessions"][tab_id] = {
        "thread_id": "",
        "initial_thesis": "",
        "label": f"辩论 {next_id}",
        "custom_label": "",
        "started": False,
        "model_config": _capture_model_config(),
    }
    st.session_state["next_tab_id"] = next_id + 1
    return tab_id


def _close_tab(tab_id: str) -> None:
    """关闭指定标签页，同时清理其 checkpointer 中的残留状态。"""
    sessions = st.session_state.get("sessions", {})
    session = sessions.get(tab_id, {})

    # 清理 checkpointer 中该标签页的状态（释放内存）
    thread_id = session.get("thread_id", "")
    if thread_id:
        checkpointer = st.session_state.get("checkpointer")
        if checkpointer and hasattr(checkpointer, "storage"):
            # MemorySaver 内部使用 storage 字典存储 thread_id → checkpoint 映射
            storage = checkpointer.storage  # type: ignore[union-attr]
            # 尝试删除对应的 checkpoint 数据
            try:
                # MemorySaver 的存储结构：storage[thread_id] = checkpoint_data
                if thread_id in storage:
                    del storage[thread_id]
            except (TypeError, KeyError, AttributeError):
                pass

    sessions.pop(tab_id, None)
    if not sessions:
        _ensure_default_tab()


def _close_all_tabs() -> None:
    """关闭所有标签页并清理所有 checkpoint 数据。"""
    sessions = st.session_state.get("sessions", {})
    # 清理所有 checkpoint
    checkpointer = st.session_state.get("checkpointer")
    if checkpointer and hasattr(checkpointer, "storage"):
        storage = checkpointer.storage  # type: ignore[union-attr]
        for s in sessions.values():
            tid = s.get("thread_id", "")
            if tid:
                try:
                    if tid in storage:
                        del storage[tid]
                except (TypeError, KeyError, AttributeError):
                    pass
    sessions.clear()
    st.session_state["next_tab_id"] = 1
    _ensure_default_tab()


def _rename_tab(tab_id: str, new_label: str) -> None:
    """重命名指定标签页。"""
    sessions = st.session_state.get("sessions", {})
    if tab_id in sessions and new_label.strip():
        sessions[tab_id]["custom_label"] = new_label.strip()
        # 更新显示用 label
        sessions[tab_id]["label"] = new_label.strip()


def _get_tab_ids() -> list[str]:
    """获取所有标签页 ID 列表（按创建顺序）。"""
    return list(st.session_state.get("sessions", {}).keys())


# =============================================================================
# 状态读取（标签页感知）
# =============================================================================


def _get_current_state(tab_id: str) -> AgentState | None:
    """从 LangGraph checkpointer 读取指定标签页的当前状态。"""
    graph = st.session_state.get("graph")
    thread_id = (
        st.session_state.get("sessions", {})
        .get(tab_id, {})
        .get("thread_id", "")
    )
    if graph is None or not thread_id:
        return None
    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    snapshot = graph.get_state(config)
    if snapshot is None or snapshot.values is None:
        return None
    return snapshot.values


def _get_interrupt_value(tab_id: str) -> str | None:
    """获取指定标签页的当前活跃中断值（若有）。"""
    graph = st.session_state.get("graph")
    thread_id = (
        st.session_state.get("sessions", {})
        .get(tab_id, {})
        .get("thread_id", "")
    )
    if graph is None or not thread_id:
        return None
    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    snapshot = graph.get_state(config)
    interrupts = getattr(snapshot, "interrupts", None) or ()
    if interrupts:
        return str(interrupts[0].value)
    return None


# =============================================================================
# UI 事件处理（标签页感知）
# =============================================================================


def _ensure_shared_graph() -> None:
    """确保共享的 graph 和 checkpointer 已创建（全局唯一）。"""
    if "checkpointer" not in st.session_state:
        st.session_state["checkpointer"] = MemorySaver()
    if "graph" not in st.session_state:
        st.session_state["graph"] = build_graph(
            opponent_compute_node=opponent_compute_node,
            opponent_interact_node=opponent_interact_node,
            presenter_compute_node=presenter_compute_node,
            presenter_interact_node=presenter_interact_node,
            referee_deliberate_node=referee_deliberate_node,
            checkpointer=st.session_state["checkpointer"],
        )


def _node_label(node_name: str) -> str:
    """将 LangGraph 节点名映射为人类可读的中文标签。"""
    labels: dict[str, str] = {
        "start": "初始化",
        "opponent_compute": "批判者分析",
        "opponent_interact": "批判者交互",
        "presenter_compute": "陈述者精确化",
        "presenter_interact": "陈述者交互",
        "referee_deliberate": "裁判审议",
        "next_round": "进入下一轮",
    }
    return labels.get(node_name, node_name)


# =============================================================================
# 流式执行（在渲染线程中运行，支持渐进式 UI 更新）
# =============================================================================


def _execute_stream_start(tab_id: str) -> None:
    """从初始状态开始流式执行图，展示 LLM token 渐进输出。"""
    sessions = st.session_state["sessions"]
    session = sessions[tab_id]
    initial_thesis = session["initial_thesis"]
    model_config = session.get("model_config", {})

    st.toast("⚔️ 辩论已开始", icon="🚀")

    _ensure_shared_graph()
    graph = st.session_state["graph"]
    thread_id = str(uuid4())

    sessions[tab_id]["thread_id"] = thread_id
    sessions[tab_id].pop("pending_start", None)

    initial_state: AgentState = make_initial_state(
        initial_thesis,
        agent_temperature=session.get("agent_temperature", 0.7),
        model_name=model_config.get("model_name", ""),
        model_base_url=model_config.get("base_url", ""),
        max_rounds=session.get("max_rounds", 10),
    )
    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})

    _run_stream(graph, initial_state, config)
    st.rerun()


def _execute_stream_resume(tab_id: str, user_value: str) -> None:
    """从中断点流式恢复执行。"""
    sessions = st.session_state["sessions"]
    sessions[tab_id].pop("pending_resume", None)

    st.toast("✅ 已从错误中恢复")

    _ensure_shared_graph()
    graph = st.session_state["graph"]
    thread_id = sessions[tab_id].get("thread_id", "")
    if graph is None or not thread_id:
        return

    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    _run_stream(graph, Command(resume=user_value), config)
    st.rerun()


def _run_stream(graph, input_data, config: RunnableConfig) -> None:
    """执行 graph.stream() 并通过 st.empty() 渐进渲染 LLM token。

    在主渲染线程中调用（非按钮回调），因此 st.empty() 占位符
    可在循环中逐步更新，实现 token 级流式输出。

    包含错误边界：非 GraphInterrupt 的异常会被捕获并展示可操作的中文错误信息，
    用户可通过"重试"按钮从中断点恢复。
    """
    token_placeholder = st.empty()
    error_placeholder = st.empty()
    accumulated = ""
    current_node: str | None = None

    with trace_id_context() as tid:
        tlog = TraceLogger(tid)

        try:
            for event in graph.stream(
                input_data, config, stream_mode=["messages", "updates"],
            ):
                mode, data = event
                if mode == "messages":
                    msg, metadata = data
                    node: str = str(metadata.get("langgraph_node", ""))
                    if node != current_node:
                        current_node = node
                        accumulated = ""
                    if hasattr(msg, "content") and msg.content:
                        content = str(msg.content)
                        if content:
                            accumulated += content
                            header = f"💭 **{_node_label(current_node or '')}** 正在生成…\n\n"
                            token_placeholder.markdown(
                                header + accumulated + typing_cursor_html(),
                                unsafe_allow_html=True,
                            )
                elif mode == "updates":
                    accumulated = ""
                    token_placeholder.empty()
        except GraphInterrupt:
            # 到达 interrupt() 点，状态已由 LangGraph 检查点保存
            pass
        except Exception as exc:
            # --- 错误边界：捕获非预期的流式异常 ---
            token_placeholder.empty()
            error_msg = str(exc)
            error_type = type(exc).__name__

            # 记录到 trace logger
            tlog.record_error(f"{error_type}: {error_msg}")

            # 分类展示用户友好的错误信息
            if "api_key" in error_msg.lower() or "auth" in error_msg.lower() or "401" in error_msg:
                user_msg = "🔑 API Key 鉴权失败。请检查侧边栏或 .env 中的 API Key 是否正确。"
            elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                user_msg = "⏱️ LLM 请求超时。网络可能不稳定，请点击下方「重试」按钮。"
            elif "rate" in error_msg.lower() or "429" in error_msg:
                user_msg = "🚦 API 速率限制。请稍等片刻后点击下方「重试」按钮。"
            elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                user_msg = "🌐 网络连接失败。请检查网络后点击下方「重试」按钮。"
            elif "json" in error_msg.lower() or "parse" in error_msg.lower():
                user_msg = "📝 LLM 返回格式异常，系统无法解析。请点击下方「重试」按钮重新尝试。"
            else:
                user_msg = f"⚠️ 执行过程中发生错误：{error_msg[:200]}"

            error_placeholder.error(user_msg)

            # 可展开的技术详情
            with st.expander("🔍 技术详情"):
                st.code(traceback.format_exc(), language="python")
                summary = tlog.summary()
                st.json(summary)

            # 重试按钮 —— 利用 checkpoint 从中断点恢复
            col_retry, col_reset = st.columns([1, 1])
            with col_retry:
                if st.button("🔄 重试", key=f"retry_stream_{tid}", use_container_width=True):
                    st.rerun()
            with col_reset:
                if st.button("🏠 返回首页", key=f"home_stream_{tid}", use_container_width=True):
                    st.rerun()


def _on_start_debate(tab_id: str, initial_thesis: str) -> None:
    """为指定标签页启动辩论（设置 pending flag，实际执行在渲染循环中）。

    在启动时冻结当前侧边栏的模型配置和温度参数到 per-tab session，
    后续该标签页的所有 LLM 调用使用冻结的配置，不受侧边栏修改影响。
    """
    api_key = st.session_state.get("api_key", "")
    has_key = bool(api_key) or has_configured_api_key()
    if not has_key:
        st.error("请先配置 LLM API Key（在项目 .env 文件中或侧边栏输入均可）")
        return

    _ensure_shared_graph()

    thesis_display = initial_thesis[:30] + "…" if len(initial_thesis) > 30 else initial_thesis
    custom_label = st.session_state["sessions"].get(tab_id, {}).get("custom_label", "")

    sessions = st.session_state["sessions"]
    sessions[tab_id] = {
        "thread_id": "",
        "initial_thesis": initial_thesis,
        "label": custom_label or thesis_display,
        "custom_label": custom_label,
        "started": True,
        "pending_start": True,
        "model_config": _capture_model_config(),
        "agent_temperature": st.session_state.get("agent_temperature", 0.7),
        "max_rounds": st.session_state.get("max_rounds", 10),
    }
    st.rerun()


def _on_reset(tab_id: str) -> None:
    """重置指定标签页的辩论状态（保留模型配置以保持一致）。"""
    sessions = st.session_state.get("sessions", {})
    if tab_id in sessions:
        old_label = sessions[tab_id].get("custom_label", "") or sessions[tab_id].get(
            "label", f"辩论 {tab_id.split('_')[-1]}"
        )
        sessions[tab_id] = {
            "thread_id": "",
            "initial_thesis": sessions[tab_id].get("initial_thesis", ""),
            "label": old_label,
            "custom_label": sessions[tab_id].get("custom_label", ""),
            "started": False,
            "model_config": sessions[tab_id].get("model_config", {}),
        }
    st.rerun()


def _resume_with_input(tab_id: str, user_value: str) -> None:
    """从当前中断点恢复指定标签页的执行（设置 pending flag）。"""
    graph = st.session_state.get("graph")
    thread_id = (
        st.session_state.get("sessions", {})
        .get(tab_id, {})
        .get("thread_id", "")
    )
    if graph is None or not thread_id:
        return
    # 设置 pending flag，实际流式执行在渲染循环中
    st.session_state["sessions"][tab_id]["pending_resume"] = user_value
    st.rerun()


# =============================================================================
# 中断 UI 渲染（标签页感知，widget key 带命名空间）
# =============================================================================


def _render_interrupt_ui(tab_id: str, status: str, interrupt_value: str) -> None:
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
            key=f"critique_response_{tab_id}",
        )
        if st.button(
            "📤 提交回应", type="primary", use_container_width=True,
            key=f"submit_critique_{tab_id}",
        ):
            if user_response.strip():
                _resume_with_input(tab_id, user_response)
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
            key=f"thesis_confirmation_{tab_id}",
        )
        if st.button(
            "✅ 确认论题", type="primary", use_container_width=True,
            key=f"confirm_thesis_{tab_id}",
        ):
            if confirmed.strip():
                _resume_with_input(tab_id, confirmed)
            else:
                st.warning("论题不能为空")


# =============================================================================
# 状态展示（纯渲染，无标签页依赖）
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
        st.info("辩论尚未开始，请在标签页中输入论题并点击「开始辩论」。")
        return

    from datetime import datetime

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

        # 时间戳（兼容旧消息无 timestamp 字段）
        timestamp = msg.get("timestamp")
        time_str = ""
        if isinstance(timestamp, (int, float)):
            time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")

        with st.chat_message(label, avatar=emoji):
            st.caption(f"第 {round_num} 轮 · {label}")
            st.markdown(str(msg.get("content", "")))
            if time_str:
                st.markdown(
                    f'<span class="chat-timestamp">{time_str}</span>',
                    unsafe_allow_html=True,
                )


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
# 单个标签页内容渲染
# =============================================================================


def _render_tab_content(tab_id: str) -> None:
    """渲染单个标签页的完整辩论 UI。

    包含：标签页重命名、模型配置展示、流式执行（含错误边界）、
    中断 UI、对话历史、裁判审议和终局报告。
    """
    sessions = st.session_state["sessions"]
    session = sessions.get(tab_id, {})
    started = session.get("started", False)

    # ---- 流式执行：pending_start ----
    if session.get("pending_start"):
        _execute_stream_start(tab_id)
        return

    # ---- 流式执行：pending_resume ----
    pending_resume = session.get("pending_resume")
    if pending_resume is not None:
        _execute_stream_resume(tab_id, pending_resume)
        return

    # ---- 标签页工具栏：重命名 + 关闭 ----
    col_title, col_rename, col_close = st.columns([17, 4, 1])
    with col_close:
        if st.button("✕", key=f"close_{tab_id}", help="关闭此辩论标签页"):
            _close_tab(tab_id)
            st.rerun()

    if not started:
        # ---- 未启动：重命名 + 论题输入 + 开始按钮 ----
        with col_rename:
            custom = st.text_input(
                "标签名",
                value=session.get("custom_label", ""),
                placeholder=session.get("label", "辩论"),
                key=f"rename_{tab_id}",
                label_visibility="collapsed",
            )
            if custom and custom != session.get("custom_label", ""):
                _rename_tab(tab_id, custom)

        with col_title:
            st.subheader(session.get("custom_label") or "新辩论")

        thesis = st.text_area(
            "输入你的初始论题",
            value=session.get("initial_thesis", ""),
            height=100,
            key=f"thesis_input_{tab_id}",
            help="输入你希望被审视和演化的核心论题。",
        )
        sessions[tab_id]["initial_thesis"] = thesis

        # 模型配置信息
        mc = session.get("model_config", {})
        if mc.get("model_name"):
            st.caption(
                f"🔧 模型: {mc['model_name']}"
                f" | 温度: {session.get('agent_temperature', 0.7)}"
                f" | 最大轮次: {session.get('max_rounds', 10)}"
            )

        if st.button("🚀 开始辩论", key=f"start_{tab_id}", use_container_width=True):
            if thesis and thesis.strip():
                _on_start_debate(tab_id, thesis)
            else:
                st.warning("请输入论题")
        return

    # ---- 已启动：重命名 + 模型信息 + 状态渲染 ----
    with col_rename:
        custom = st.text_input(
            "标签名",
            value=session.get("custom_label", session.get("label", "")),
            placeholder=session.get("label", "辩论"),
            key=f"rename_{tab_id}",
            label_visibility="collapsed",
        )
        if custom and custom != session.get("custom_label", ""):
            _rename_tab(tab_id, custom)

    # 模型配置小标签
    mc = session.get("model_config", {})
    if mc.get("model_name"):
        with col_title:
            st.caption(
                f"🔧 {mc['model_name']}"
                f" | 温度 {session.get('agent_temperature', 0.7)}"
                f" | 最多 {session.get('max_rounds', 10)} 轮"
            )

    # ---- 读取 LangGraph 状态 ----
    state = _get_current_state(tab_id)

    if state is None:
        st.info("正在初始化…")
        return

    status = state.get("status", "idle")

    # 检查是否有活跃中断
    interrupt_value = _get_interrupt_value(tab_id)

    if interrupt_value and status in (
        "awaiting_critique_response",
        "awaiting_thesis_confirmation",
    ):
        _render_status_badge(status)
        _render_conversation(state.get("messages", []))
        st.divider()
        _render_interrupt_ui(tab_id, status, interrupt_value)
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
            # 学习完成庆祝（每标签页仅触发一次）
            done_key = f"_done_celebrated_{tab_id}"
            if not st.session_state.get(done_key):
                st.toast("🎉 学习会话完成！")
                st.balloons()
                st.session_state[done_key] = True
            _render_final_result(history, state.get("final_result", ""))
        else:
            # 非 done 状态时清除庆祝标记，以便下次完成时再次触发
            done_key = f"_done_celebrated_{tab_id}"
            if st.session_state.get(done_key):
                st.session_state.pop(done_key, None)

    # 重置按钮
    if st.button("🔄 重置此辩论", key=f"reset_{tab_id}"):
        _on_reset(tab_id)


# =============================================================================
# 主页面
# =============================================================================


def main() -> None:
    """主入口：组合侧边栏、标签页导航与辩论 UI。"""
    _render_sidebar()

    st.title("🎓 多智能体论题演化系统")
    st.caption("批判者审视 · 陈述者精确化 · 你确认 · 裁判拼合演化")

    # 注入全局 CSS + 自动滚动 JS（同一 session 仅执行一次）
    inject_global_css()

    _ensure_default_tab()

    tab_ids = _get_tab_ids()
    sessions = st.session_state["sessions"]

    # 标签栏 + 新建按钮 + 清空按钮
    col_info, col_add, col_clear = st.columns([7, 1, 1])
    with col_info:
        total_sessions = len(sessions)
        active_sessions = sum(1 for s in sessions.values() if s.get("started"))
        if active_sessions > 0:
            st.caption(f"📋 {total_sessions} 个标签页（{active_sessions} 个活跃）")
    with col_clear:
        if st.button(
            "🗑️ 清空", use_container_width=True,
            help="关闭所有标签页并清理缓存",
            key="clear_all_tabs",
        ):
            _close_all_tabs()
            st.rerun()
    with col_add:
        if st.button(
            "➕ 新辩论", use_container_width=True,
            help="新建一个独立的辩论标签页",
            key="add_tab_button",
        ):
            _add_new_tab()
            st.rerun()

    if not tab_ids:
        st.info("点击「新辩论」按钮创建辩论标签页")
        return

    # 使用 st.tabs() 渲染标签页
    tab_labels = [sessions[tid].get("label", tid) for tid in tab_ids]
    tabs = st.tabs(tab_labels)

    for i, tab in enumerate(tabs):
        tab_id = tab_ids[i]
        with tab:
            _render_tab_content(tab_id)


if __name__ == "__main__":
    main()

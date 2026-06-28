"""
Streamlit 展现层 —— 纯渲染与输入收集。

原则：
1. UI 层不包含任何业务逻辑。所有状态变更由 LangGraph 图驱动。
2. st.session_state 仅管理 UI 会话元数据（thread_id、model_store），
   辩论状态完全存储在 LangGraph checkpointer 中。
3. 使用动态 interrupt() + Command(resume=...) 实现人工介入。
4. 每个渲染函数只读取数据并绘制，不修改 graph state。
5. 多标签页：一个共享 graph + MemorySaver 服务多个独立辩论会话。
6. Per-tab 模型配置：每个标签页在启动时从 ModelStore 捕获当前活跃模型配置，
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

import traceback
import uuid
from typing import cast

import streamlit as st
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from agents.opponent import opponent_compute_node, opponent_interact_node
from agents.presenter import presenter_compute_node, presenter_interact_node
from agents.referee import referee_deliberate_node
from core.logging import TraceLogger, trace_id_context
from core.model import load_model_config
from core.model_store import ModelProfile, ModelStore, ProviderEntry
from core.schemas import RefereeJudgment
from core.state import AgentState, make_initial_state
from ui.model_settings import MODEL_CONFIG_FILENAME, render_model_settings_page
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
# ModelStore 管理
# =============================================================================


def _config_path() -> Path:
    return _project_root / MODEL_CONFIG_FILENAME


def _get_store() -> ModelStore:
    """获取或初始化持久化的 ModelStore。

    首次调用时：若 .model-config.json 存在则加载；否则从 .env 迁移并保存。
    """
    if "model_store" not in st.session_state:
        path = _config_path()
        if path.exists():
            st.session_state["model_store"] = ModelStore.load(path)
        else:
            store = ModelStore.migrate_from_env(load_model_config())
            store.save(path)
            st.session_state["model_store"] = store
    return st.session_state["model_store"]


def _save_store() -> None:
    store = st.session_state.get("model_store")
    if isinstance(store, ModelStore):
        store.save(_config_path())


def _capture_model_config() -> dict:
    """捕获当前活跃模型配置，供新标签页在启动时冻结。

    返回 dict 包含 model_name / base_url / api_key / json_mode 四个字段，
    后续直接传入 make_initial_state()。
    """
    store = _get_store()
    profile: ModelProfile | None = store.get_active_profile()
    if profile is None:
        return {
            "model_name": "",
            "base_url": "",
            "api_key": "",
            "json_mode": False,
        }
    entry = store.providers[profile.provider_entry_id]
    return {
        "model_name": profile.model_name,
        "base_url": entry.effective_base_url() or "",
        "api_key": profile.api_key or "",
        "json_mode": not profile.supports_structured_output,
    }


def _has_active_model() -> bool:
    """是否已有配置好的可用模型。"""
    return _get_store().get_active_profile() is not None


# =============================================================================
# 共享侧边栏 —— 两个页面共用
# =============================================================================


def _render_sidebar() -> None:
    """渲染侧边栏：导航、模型选择器、温度调节。

    注意：此函数在两个页面的公共区域调用（pg.run() 之前），
    因此两个页面共享同一份侧边栏内容。
    """
    with st.sidebar:
        # 导航菜单由 st.navigation 自动注入（此处仅添加导航下方的内容）
        st.divider()

        # ---- 当前模型选择 ----
        st.caption("🔌 当前模型")
        store = _get_store()
        profile = store.get_active_profile()

        configured = {k: v for k, v in store.providers.items() if v.status == "ok"}

        if not configured:
            st.warning("尚未配置可用模型。")
            if st.button("🔧 前往模型设置", use_container_width=True):
                st.switch_page(st.Page(render_model_settings_page, title="模型设置", icon="🔧"))
        else:
            # Provider 下拉选择
            entry_ids = list(configured.keys())
            entry_labels = {
                eid: _format_entry_label(eid, configured[eid]) for eid in entry_ids
            }

            # 确定当前选中的 provider
            active_eid = None
            active_model = None
            if profile is not None:
                active_eid = profile.provider_entry_id
                active_model = profile.model_name
            if active_eid not in configured:
                active_eid = entry_ids[0]

            selected_provider_idx = st.selectbox(
                "提供商",
                range(len(entry_ids)),
                index=entry_ids.index(active_eid) if active_eid in entry_ids else 0,
                format_func=lambda i: entry_labels[entry_ids[i]],
                key="_sidebar_provider_idx",
            )
            selected_eid = entry_ids[selected_provider_idx]
            selected_entry = configured[selected_eid]

            # 模型下拉
            models = selected_entry.all_models()
            if not models:
                st.info("此提供商暂无模型，请在模型设置中添加。")
            else:
                model_idx = models.index(active_model) if active_eid == selected_eid and active_model in models else 0
                selected_model = st.selectbox(
                    "模型",
                    models,
                    index=model_idx,
                    key="_sidebar_model",
                )
                # 若选择变化 → 持久化
                expected_profile_id = f"{selected_eid}:{selected_model}"
                if store.active_profile_id != expected_profile_id:
                    store.set_active_profile(selected_eid, selected_model)
                    _save_store()

                # 显示当前选择信息
                preset = selected_entry.preset()
                mode_hint = "JSON 模式" if not preset.supports_structured_output else "原生结构化输出"
                st.caption(f"✓ 将用于所有新辩论（{mode_hint}）")

            # 管理按钮
            if st.button("⚙️ 管理所有模型", use_container_width=True, key="_sidebar_manage"):
                st.switch_page(st.Page(render_model_settings_page, title="模型设置", icon="🔧"))

        st.divider()

        # ---- 温度调节 ----
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

        # ---- 最大轮次 ----
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

        # Per-tab 隔离说明
        sessions = st.session_state.get("sessions", {})
        started_count = sum(1 for s in sessions.values() if s.get("started"))
        if started_count > 0:
            st.caption(
                f"ℹ️ 模型配置仅对新辩论生效。"
                f"当前 {started_count} 个运行中的标签页使用启动时的配置。"
            )


def _format_entry_label(entry_id: str, entry: ProviderEntry) -> str:
    preset = entry.preset()
    return f"{preset.icon} {entry.display_name}"


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
            "model_config": _capture_model_config(),
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

    thread_id = session.get("thread_id", "")
    if thread_id:
        checkpointer = st.session_state.get("checkpointer")
        if checkpointer and hasattr(checkpointer, "storage"):
            storage = checkpointer.storage  # type: ignore[union-attr]
            try:
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
        sessions[tab_id]["label"] = new_label.strip()


def _get_tab_ids() -> list[str]:
    return list(st.session_state.get("sessions", {}).keys())


# =============================================================================
# 状态读取
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
# UI 事件处理
# =============================================================================


def _ensure_shared_graph() -> None:
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
# 流式执行
# =============================================================================


def _execute_stream_start(tab_id: str) -> None:
    sessions = st.session_state["sessions"]
    session = sessions[tab_id]
    initial_thesis = session["initial_thesis"]
    model_config = session.get("model_config", {})

    st.toast("⚔️ 辩论已开始", icon="🚀")

    _ensure_shared_graph()
    graph = st.session_state["graph"]
    thread_id = str(uuid.uuid4())

    sessions[tab_id]["thread_id"] = thread_id
    sessions[tab_id].pop("pending_start", None)

    initial_state: AgentState = make_initial_state(
        initial_thesis,
        agent_temperature=session.get("agent_temperature", 0.7),
        model_name=model_config.get("model_name", ""),
        model_base_url=model_config.get("base_url", ""),
        model_api_key=model_config.get("api_key", ""),
        model_json_mode=bool(model_config.get("json_mode", False)),
        max_rounds=session.get("max_rounds", 10),
    )
    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})

    _run_stream(graph, initial_state, config)
    st.rerun()


def _execute_stream_resume(tab_id: str, user_value: str) -> None:
    sessions = st.session_state["sessions"]
    sessions[tab_id].pop("pending_resume", None)

    st.toast("✅ 已继续")

    _ensure_shared_graph()
    graph = st.session_state["graph"]
    thread_id = sessions[tab_id].get("thread_id", "")
    if graph is None or not thread_id:
        return

    config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    _run_stream(graph, Command(resume=user_value), config)
    st.rerun()


def _run_stream(graph, input_data, config: RunnableConfig) -> None:
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
            pass
        except Exception as exc:
            token_placeholder.empty()
            error_msg = str(exc)
            error_type = type(exc).__name__
            tlog.record_error(f"{error_type}: {error_msg}")

            if "api_key" in error_msg.lower() or "auth" in error_msg.lower() or "401" in error_msg:
                user_msg = "🔑 API Key 鉴权失败。请在「模型设置」中检查 API Key 是否正确。"
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

            with st.expander("🔍 技术详情"):
                st.code(traceback.format_exc(), language="python")
                summary = tlog.summary()
                st.json(summary)

            col_retry, col_reset = st.columns([1, 1])
            with col_retry:
                if st.button("🔄 重试", key=f"retry_stream_{tid}", use_container_width=True):
                    st.rerun()
            with col_reset:
                if st.button("🏠 返回首页", key=f"home_stream_{tid}", use_container_width=True):
                    st.rerun()


def _on_start_debate(tab_id: str, initial_thesis: str) -> None:
    if not _has_active_model():
        st.error("请先在侧边栏或「模型设置」中配置并选择一个可用模型。")
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
    graph = st.session_state.get("graph")
    thread_id = (
        st.session_state.get("sessions", {})
        .get(tab_id, {})
        .get("thread_id", "")
    )
    if graph is None or not thread_id:
        return
    st.session_state["sessions"][tab_id]["pending_resume"] = user_value
    st.rerun()


# =============================================================================
# 中断 UI
# =============================================================================


def _render_interrupt_ui(tab_id: str, status: str, interrupt_value: str) -> None:
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
# 状态展示
# =============================================================================


def _render_status_badge(status: str) -> None:
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
    st.caption(f"当前轮次: 第 {current_round} 轮")


def _render_conversation(messages: list[dict]) -> None:
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
    if not history:
        return

    st.divider()
    st.subheader("🏁 论题演化总结")

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
    sessions = st.session_state["sessions"]
    session = sessions.get(tab_id, {})
    started = session.get("started", False)

    if session.get("pending_start"):
        _execute_stream_start(tab_id)
        return

    pending_resume = session.get("pending_resume")
    if pending_resume is not None:
        _execute_stream_resume(tab_id, pending_resume)
        return

    col_title, col_rename, col_close = st.columns([17, 4, 1])
    with col_close:
        if st.button("✕", key=f"close_{tab_id}", help="关闭此辩论标签页"):
            _close_tab(tab_id)
            st.rerun()

    if not started:
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

        mc = session.get("model_config", {})
        if mc.get("model_name"):
            # 显示冻结模型配置
            preset_label = ""
            store = _get_store()
            try:
                profile = store.get_active_profile()
                if profile is not None:
                    e = store.providers.get(profile.provider_entry_id)
                    if e is not None:
                        p = e.preset()
                        preset_label = f"{p.icon} {e.display_name} / "
            except Exception:
                pass
            st.caption(
                f"🔧 模型: {preset_label}{mc['model_name']}"
                f" | 温度: {session.get('agent_temperature', 0.7)}"
                f" | 最大轮次: {session.get('max_rounds', 10)}"
            )
        elif not _has_active_model():
            st.warning("⚠️ 请先在侧边栏选择或在「模型设置」中添加一个模型，再开始辩论。")

        can_start = bool(thesis and thesis.strip() and _has_active_model())
        if st.button(
            "🚀 开始辩论", key=f"start_{tab_id}", use_container_width=True,
            disabled=not can_start,
        ):
            if thesis and thesis.strip():
                _on_start_debate(tab_id, thesis)
            else:
                st.warning("请输入论题")
        return

    # ---- 已启动 ----
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

    mc = session.get("model_config", {})
    if mc.get("model_name"):
        with col_title:
            st.caption(
                f"🔧 {mc['model_name']}"
                f" | 温度 {session.get('agent_temperature', 0.7)}"
                f" | 最多 {session.get('max_rounds', 10)} 轮"
            )

    state = _get_current_state(tab_id)
    if state is None:
        st.info("正在初始化…")
        return

    status = state.get("status", "idle")
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
            done_key = f"_done_celebrated_{tab_id}"
            if not st.session_state.get(done_key):
                st.toast("🎉 学习会话完成！")
                st.balloons()
                st.session_state[done_key] = True
            _render_final_result(history, state.get("final_result", ""))
        else:
            done_key = f"_done_celebrated_{tab_id}"
            if st.session_state.get(done_key):
                st.session_state.pop(done_key, None)

    if st.button("🔄 重置此辩论", key=f"reset_{tab_id}"):
        _on_reset(tab_id)


# =============================================================================
# 辩论页面主渲染
# =============================================================================


def render_chat_page() -> None:
    """辩论主页面。"""
    st.title("🎓 多智能体论题演化系统")
    st.caption("批判者审视 · 陈述者精确化 · 你确认 · 裁判拼合演化")

    inject_global_css()

    _ensure_default_tab()

    tab_ids = _get_tab_ids()
    sessions = st.session_state["sessions"]

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

    tab_labels = [sessions[tid].get("label", tid) for tid in tab_ids]
    tabs = st.tabs(tab_labels)

    for i, tab in enumerate(tabs):
        tab_id = tab_ids[i]
        with tab:
            _render_tab_content(tab_id)


# =============================================================================
# 导航入口
# =============================================================================


def main() -> None:
    """主入口：配置共享侧边栏 + 多页面导航。

    注意：_render_sidebar() 必须在 pg.run() 之前调用，这样侧边栏在两个页面中共享。
    """
    # 确保 store 初始化（侧边栏需要用到）
    _get_store()
    _ensure_shared_graph()
    _ensure_default_tab()

    # 共享侧边栏
    _render_sidebar()

    # 多页面导航
    pg = st.navigation([
        st.Page(render_chat_page, title="辩论", icon="💬", default=True),
        st.Page(render_model_settings_page, title="模型设置", icon="🔧"),
    ])
    pg.run()


if __name__ == "__main__":
    main()

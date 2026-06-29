"""Application state management for Reflex UI — multi-tab edition."""
import reflex as rx
from reflex_base.event import event as rx_event
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt as GraphInterrupt
from typing import Optional
import uuid
import time
from pathlib import Path

from socratic_loop.core.state import make_initial_state
from socratic_loop.core.model_store import ModelStore
from socratic_loop.core.model import load_model_config
from socratic_loop.core.env import setup_environment
from socratic_loop.workflow.graph import build_graph
from socratic_loop.agents.opponent import opponent_compute_node, opponent_interact_node
from socratic_loop.agents.presenter import presenter_compute_node, presenter_interact_node
from socratic_loop.agents.referee import referee_deliberate_node

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
setup_environment(PROJECT_ROOT)
MODEL_CONFIG_PATH = PROJECT_ROOT / ".model-config.json"

_graph = None
_checkpointer = None
_model_store = None


def _mkmsg(role: str, content: str, is_streaming: bool = False) -> dict:
    return {"role": role, "content": content, "is_streaming": is_streaming, "timestamp": time.time()}


def _new_tab(label: str = "新对话") -> dict:
    """创建新 Tab 的数据结构。"""
    return {
        "id": str(uuid.uuid4()),
        "label": label,
        "thread_id": "",
        "topic": "",
        "messages": [],
        "is_generating": False,
        "interrupt_value": None,
        "awaiting_user_response": False,
        "current_node": "",
    }


class AppState(rx.State):
    """Reflex 全局应用状态 — 多 Tab 架构。"""
    dark_mode: bool = False

    # 多 Tab 数据
    tabs: list[dict] = [_new_tab("新对话")]
    active_tab_id: str = ""

    # 全局共享
    user_input: str = ""
    selected_model_id: str = ""
    agent_temperature: float = 0.7
    max_rounds: int = 10
    model_store_loaded: bool = False

    # 镜像：活跃 Tab 数据
    active_messages: list[dict] = []
    active_topic: str = ""
    active_is_generating: bool = False
    active_awaiting_user_response: bool = False
    active_interrupt_value: Optional[str] = None
    active_current_node: str = ""

    # 镜像：模型设置页数据
    providers_list: list[dict] = []
    setting_show_add: bool = False
    setting_new_preset: str = "deepseek"
    setting_new_name: str = ""
    setting_new_key: str = ""
    setting_new_url: str = ""
    setting_editing_id: str = ""

    # ── 便利访问器 ──

    def _active_tab(self) -> dict:
        for t in self.tabs:
            if t["id"] == self.active_tab_id:
                return t
        if self.tabs:
            self.active_tab_id = self.tabs[0]["id"]
            return self.tabs[0]
        t = _new_tab("新对话")
        self.tabs = [t]
        self.active_tab_id = t["id"]
        return t

    def _update_tab(self, tab_id: str, **kw):
        for i, t in enumerate(self.tabs):
            if t["id"] == tab_id:
                self.tabs[i] = {**t, **kw}
                if tab_id == self.active_tab_id:
                    self._sync_active()
                return

    def _sync_active(self):
        """将活跃 tab 的数据镜像到顶层字段，供 UI 组件直接访问。"""
        tab = self._active_tab()
        self.active_messages = tab["messages"]
        self.active_topic = tab["topic"]
        self.active_is_generating = tab["is_generating"]
        self.active_awaiting_user_response = tab["awaiting_user_response"]
        self.active_interrupt_value = tab["interrupt_value"]
        self.active_current_node = tab["current_node"]

    # ── 初始化 ──

    def initialize(self):
        global _graph, _checkpointer, _model_store
        if not self.active_tab_id and self.tabs:
            self.active_tab_id = self.tabs[0]["id"]
        if _model_store is None:
            if MODEL_CONFIG_PATH.exists():
                _model_store = ModelStore.load(MODEL_CONFIG_PATH)
            else:
                _model_store = ModelStore.migrate_from_env(load_model_config())
                _model_store.save(MODEL_CONFIG_PATH)
            profile = _model_store.get_active_profile()
            if profile and not self.selected_model_id:
                self.selected_model_id = profile.model_name
        if _graph is None:
            _checkpointer = MemorySaver()
            _graph = build_graph(
                opponent_compute_node, opponent_interact_node,
                presenter_compute_node, presenter_interact_node,
                referee_deliberate_node, checkpointer=_checkpointer,
            )
        self.model_store_loaded = True
        self.refresh_providers()

    # ── Tab 管理 ──

    @rx.var
    def has_active_conversation(self) -> bool:
        """是否当前 tab 有活跃对话（用于 UI 切换 start/chat 视图）。"""
        for t in self.tabs:
            if t["id"] == self.active_tab_id:
                return len(t["messages"]) > 0 or t["is_generating"] or t["awaiting_user_response"]
        return False

    def add_tab(self):
        t = _new_tab(f"对话 {len(self.tabs) + 1}")
        self.tabs = [*self.tabs, t]
        self.active_tab_id = t["id"]
        self.user_input = ""
        self._sync_active()

    def switch_tab(self, tab_id: str):
        self.active_tab_id = tab_id
        self.user_input = ""
        self._sync_active()

    def remove_active_tab(self):
        """关闭当前活跃的 tab。"""
        if len(self.tabs) <= 1:
            return
        self.remove_tab(self.active_tab_id)

    def remove_tab(self, tab_id: str):
        if len(self.tabs) <= 1:
            return
        for t in self.tabs:
            if t["id"] == tab_id and t["thread_id"]:
                global _checkpointer
                tid = t["thread_id"]
                if _checkpointer and hasattr(_checkpointer, "storage") and tid in _checkpointer.storage:
                    try:
                        del _checkpointer.storage[tid]
                    except (TypeError, KeyError):
                        pass
                break
        self.tabs = [t for t in self.tabs if t["id"] != tab_id]
        if self.active_tab_id == tab_id:
            self.active_tab_id = self.tabs[0]["id"]
        self._sync_active()

    def rename_tab(self, tab_id: str, new_label: str):
        if new_label.strip():
            for i, t in enumerate(self.tabs):
                if t["id"] == tab_id:
                    self.tabs[i] = {**t, "label": new_label.strip()}
                    return

    # ── 模型设置 ──

    def refresh_providers(self):
        """将 _model_store 数据镜像到 UI 状态。"""
        global _model_store
        if _model_store is None:
            return
        result = []
        for eid, entry in _model_store.configured_providers().items():
            preset_models = list(entry.preset().preset_models)
            result.append({
                "entry_id": eid,
                "preset_id": entry.preset_id,
                "label": entry.display_name,
                "base_url": entry.base_url or entry.preset().base_url or "",
                "status": entry.status,
                "status_msg": entry.status_message,
                "models": preset_models + list(entry.custom_models),
            })
        self.providers_list = result

    def show_add_provider(self):
        self.setting_show_add = not self.setting_show_add
        self.setting_new_preset = "deepseek"
        self.setting_new_name = ""
        self.setting_new_key = ""
        self.setting_new_url = ""

    def add_provider(self):
        global _model_store
        if _model_store is None:
            return
        import sys
        try:
            from socratic_loop.core.providers import get_preset
            preset = get_preset(self.setting_new_preset)
            entry_id = _model_store.add_provider(
                preset_id=self.setting_new_preset,
                display_name=self.setting_new_name.strip() or preset.label,
                base_url=self.setting_new_url.strip(),
                api_key=self.setting_new_key.strip(),
            )
            _model_store.save(MODEL_CONFIG_PATH)
            if not self.selected_model_id and preset.preset_models:
                profile = _model_store.get_active_profile()
                if profile:
                    self.selected_model_id = profile.model_name
            self.setting_show_add = False
            self.refresh_providers()
        except Exception as exc:
            print(f"[add_provider] error: {exc}", file=sys.stderr)

    def remove_provider(self, entry_id: str):
        global _model_store
        if _model_store is None:
            return
        try:
            _model_store.remove_provider(entry_id)
            _model_store.save(MODEL_CONFIG_PATH)
            self.refresh_providers()
        except Exception:
            import sys, traceback
            traceback.print_exc(file=sys.stderr)

    def test_provider_connection(self, entry_id: str):
        global _model_store
        if _model_store is None:
            return
        try:
            from socratic_loop.core.connection_test import check_connection
            provider = _model_store.configured_providers().get(entry_id)
            if provider is None:
                return
            result = check_connection(
                base_url=provider.effective_base_url(),
                api_key=provider.api_key,
                provider_id=provider.preset_id,
            )
            provider.status = "ok" if result.ok else "error"
            provider.status_message = result.message
            _model_store.save(MODEL_CONFIG_PATH)
            self.refresh_providers()
        except Exception:
            import sys, traceback
            traceback.print_exc(file=sys.stderr)

    def set_selected_model(self, model_name: str):
        self.selected_model_id = model_name

    def set_setting_preset(self, value: str):
        self.setting_new_preset = value

    def set_setting_name(self, value: str):
        self.setting_new_name = value

    def set_setting_key(self, value: str):
        self.setting_new_key = value

    def set_setting_url(self, value: str):
        self.setting_new_url = value

    # ── 模型配置 ──

    def _model_cfg(self) -> dict:
        global _model_store
        if _model_store is None:
            return {"model_name": "", "base_url": "", "api_key": "", "json_mode": False}
        p = _model_store.get_active_profile()
        if p is None:
            return {"model_name": "", "base_url": "", "api_key": "", "json_mode": False}
        return {
            "model_name": p.model_name, "base_url": p.base_url or "",
            "api_key": p.api_key or "", "json_mode": not p.supports_structured_output,
        }

    # ── 简单事件 ──

    def toggle_dark_mode(self, _val: bool):
        self.dark_mode = not self.dark_mode

    def clear_active_session(self):
        tab = self._active_tab()
        self._update_tab(tab["id"],
            messages=[], topic="", interrupt_value=None,
            awaiting_user_response=False, is_generating=False,
            thread_id="", current_node="",
        )
        self.user_input = ""

    def set_user_input(self, value: str):
        self.user_input = value

    def set_temperature_from_slider(self, values: list):
        if values:
            self.agent_temperature = float(values[0])

    def set_agent_temperature(self, value: float):
        self.agent_temperature = value

    def set_max_rounds(self, value: int):
        self.max_rounds = value

    # ── 后台任务：启动对话 ──

    @rx_event(background=True)
    async def start_debate(self):
        global _graph
        async with self:
            topic = self.user_input.strip()
            if not topic or _graph is None:
                return
            tab = self._active_tab()
            tid = str(uuid.uuid4())
            self._update_tab(tab["id"],
                thread_id=tid, topic=topic,
                messages=[_mkmsg("system", f"开始讨论话题：**{topic}**")],
                interrupt_value=None, awaiting_user_response=False,
                is_generating=True, current_node="",
            )
            self.user_input = ""
            mc = self._model_cfg()
            initial_state = make_initial_state(
                topic, agent_temperature=self.agent_temperature,
                model_name=mc["model_name"], model_base_url=mc["base_url"],
                model_api_key=mc["api_key"], model_json_mode=mc["json_mode"],
                max_rounds=self.max_rounds,
            )
            cfg = {"configurable": {"thread_id": tid}}

        await self._stream(_graph, initial_state, cfg, tab["id"])

    # ── 后台任务：提交回复 ──

    @rx_event(background=True)
    async def submit_user_response(self):
        global _graph
        async with self:
            tab = self._active_tab()
            if not self.user_input.strip() or not tab.get("awaiting_user_response") or _graph is None:
                return
            resp = self.user_input
            msgs = [*tab["messages"], _mkmsg("user", resp)]
            self._update_tab(tab["id"],
                messages=msgs, awaiting_user_response=False,
                interrupt_value=None, is_generating=True, user_input="",
            )
            self.user_input = ""
            cfg = {"configurable": {"thread_id": tab["thread_id"]}}

        await self._stream(_graph, Command(resume=resp), cfg, tab["id"])

    def set_topic_for_active_tab(self, value: str):
        tab = self._active_tab()
        self._update_tab(tab["id"], topic=value)

    # ── 流式管道 ──

    async def _stream(self, graph, input_data, config: dict, tab_id: str):
        NL = {"opponent_compute": "提问者", "presenter_compute": "提炼者", "referee_deliberate": "引导者"}
        RM = {"opponent_compute": "questioner", "presenter_compute": "refiner", "referee_deliberate": "guide"}
        acc = ""
        try:
            async for event in graph.astream(input_data, config=config, stream_mode=["messages", "updates"]):
                async with self:
                    mode, data = event
                    if mode == "messages":
                        msg, meta = data
                        token = str(msg.content) if msg.content else ""
                        if not token:
                            continue
                        node = meta.get("langgraph_node", "")
                        role = RM.get(node, "system")
                        self._update_tab(tab_id, current_node=NL.get(node, ""))
                        acc += token
                        # 从当前 tabs 读最新消息列表
                        tab = next((t for t in self.tabs if t["id"] == tab_id), None)
                        if tab is None:
                            return
                        msgs = tab["messages"]
                        if not msgs or msgs[-1].get("role") != role or not msgs[-1].get("is_streaming"):
                            self._update_tab(tab_id, messages=[*msgs, _mkmsg(role, acc, is_streaming=True)])
                        else:
                            self._update_tab(tab_id, messages=[*msgs[:-1], {**msgs[-1], "content": acc}])
                    elif mode == "updates":
                        tab = next((t for t in self.tabs if t["id"] == tab_id), None)
                        if tab is None:
                            return
                        msgs = tab["messages"]
                        if msgs and msgs[-1].get("is_streaming"):
                            self._update_tab(tab_id, messages=[*msgs[:-1], {**msgs[-1], "is_streaming": False}])
                        acc = ""
        except GraphInterrupt:
            pass
        except Exception:
            import sys, traceback
            traceback.print_exc(file=sys.stderr)

        # 流结束 → 检测中断状态
        async with self:
            tab = next((t for t in self.tabs if t["id"] == tab_id), None)
            if tab is None:
                return
            try:
                gs = graph.get_state(config)
                if gs and gs.values:
                    status = gs.values.get("status", "")
                    if status == "awaiting_critique_response":
                        critique = gs.values.get("_critique", "")
                        if critique:
                            msgs = [*tab["messages"], _mkmsg("questioner", critique)]
                            self._update_tab(tab_id, messages=msgs,
                                interrupt_value=critique, awaiting_user_response=True,
                                is_generating=False, current_node="")
                            return
                    elif status == "awaiting_thesis_confirmation":
                        draft = gs.values.get("_draft_thesis", "")
                        if draft:
                            msgs = [*tab["messages"], _mkmsg("refiner", draft)]
                            self._update_tab(tab_id, messages=msgs,
                                interrupt_value=draft, awaiting_user_response=True,
                                is_generating=False, current_node="")
                            return
            except Exception:
                pass

            msgs = [*tab["messages"], _mkmsg("system", "讨论已结束。你对这个话题的理解已经得到了深化！🎉")]
            self._update_tab(tab_id, messages=msgs, is_generating=False, current_node="")

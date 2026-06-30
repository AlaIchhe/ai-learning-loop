"""AppState —— Reflex 全局应用状态定义。

本模块定义 AppState 类，组合 StreamingMixin（流式管道）和 ProviderMixin（提供商管理），
并添加 UI 状态字段、Tab 管理方法和简单事件处理器。

模块级初始化在 _globals.py 中完成（sys.path、.env 加载、全局单例）。
"""

import contextlib

import reflex as rx

from . import _globals
from .providers import ProviderMixin
from .streaming import StreamingMixin


class AppState(StreamingMixin, ProviderMixin, rx.State):
    """Reflex 全局应用状态 —— 多 Tab 架构。"""

    # ── UI 显示状态 ──
    dark_mode: bool = False

    # ── 多 Tab 数据 ──
    tabs: list[dict] = [_globals._new_tab("新对话")]
    active_tab_id: str = ""

    # ── 全局共享 ──
    user_input: str = ""
    selected_model_id: str = ""
    agent_temperature: float = 0.7
    max_rounds: int = 10
    model_store_loaded: bool = False

    # ── 镜像：活跃 Tab 数据（供 UI 组件直接访问） ──
    active_messages: list[dict] = []
    active_topic: str = ""
    active_is_generating: bool = False
    active_awaiting_user_response: bool = False
    active_interrupt_value: str | None = None
    active_current_node: str = ""

    # ── 镜像：模型设置页数据 ──
    providers_list: list[dict] = []
    #: 可用预设 id 列表（从 infra/providers.py:iter_presets() 动态加载，避免硬编码重复）
    available_presets: list[str] = []
    setting_show_add: bool = False
    setting_new_preset: str = "deepseek"
    setting_new_name: str = ""
    setting_new_key: str = ""
    setting_new_url: str = ""
    setting_editing_id: str = ""

    # ════════════════════════════════════════════════════════════════════
    # 便利访问器
    # ════════════════════════════════════════════════════════════════════

    def _active_tab(self) -> dict:
        """获取当前活跃 tab 的数据字典（容错回退到第一个 tab）。"""
        for t in self.tabs:
            if t["id"] == self.active_tab_id:
                return t
        if self.tabs:
            self.active_tab_id = self.tabs[0]["id"]
            return self.tabs[0]
        t = _globals._new_tab("新对话")
        self.tabs = [t]
        self.active_tab_id = t["id"]
        return t

    def _update_tab(self, tab_id: str, **kw):
        """更新指定 tab 的数据并同步镜像字段。"""
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

    # ════════════════════════════════════════════════════════════════════
    # 初始化
    # ════════════════════════════════════════════════════════════════════

    def initialize(self):
        """幂等初始化——加载 ModelStore、构建图、刷新提供商列表。"""
        # 确保至少有一个活跃 tab
        if not self.active_tab_id and self.tabs:
            self.active_tab_id = self.tabs[0]["id"]

        # 加载可用预设列表（动态从 providers 注册表获取，避免硬编码与后端重复）
        if not self.available_presets:
            from socratic_loop.infra.providers import iter_presets

            self.available_presets = [p.id for p in iter_presets()]

        # 初始化 ModelStore（首次访问时从文件加载或从 .env 迁移）
        _globals._initialize_model_store()
        store = _globals._model_store
        if store is not None:
            profile = store.get_active_profile()
            if profile and not self.selected_model_id:
                self.selected_model_id = profile.model_name

        # 初始化 LangGraph 图
        _globals._initialize_graph()

        self.model_store_loaded = True
        self.refresh_providers()

    # ════════════════════════════════════════════════════════════════════
    # Tab 管理
    # ════════════════════════════════════════════════════════════════════

    @rx.var
    def has_active_conversation(self) -> bool:
        """是否当前 tab 有活跃对话（用于 UI 切换 start/chat 视图）。"""
        for t in self.tabs:
            if t["id"] == self.active_tab_id:
                return len(t["messages"]) > 0 or t["is_generating"] or t["awaiting_user_response"]
        return False

    def add_tab(self):
        """新建一个对话 tab 并切换到它。"""
        t = _globals._new_tab(f"对话 {len(self.tabs) + 1}")
        self.tabs = [*self.tabs, t]
        self.active_tab_id = t["id"]
        self.user_input = ""
        self._sync_active()

    def switch_tab(self, tab_id: str):
        """切换到指定 tab。"""
        self.active_tab_id = tab_id
        self.user_input = ""
        self._sync_active()

    def remove_active_tab(self):
        """关闭当前活跃的 tab。"""
        if len(self.tabs) <= 1:
            return
        self.remove_tab(self.active_tab_id)

    def remove_tab(self, tab_id: str):
        """关闭指定 tab 并清理其 checkpoint。"""
        if len(self.tabs) <= 1:
            return
        # 清理 checkpointer 中该 tab 的 thread_id
        for t in self.tabs:
            if t["id"] == tab_id and t["thread_id"]:
                tid = t["thread_id"]
                cp = _globals._checkpointer
                if cp is not None and hasattr(cp, "storage") and tid in cp.storage:
                    with contextlib.suppress(TypeError, KeyError):
                        del cp.storage[tid]
                break
        self.tabs = [t for t in self.tabs if t["id"] != tab_id]
        if self.active_tab_id == tab_id:
            self.active_tab_id = self.tabs[0]["id"]
        self._sync_active()

    def rename_tab(self, tab_id: str, new_label: str):
        """重命名指定 tab。"""
        if new_label.strip():
            for i, t in enumerate(self.tabs):
                if t["id"] == tab_id:
                    self.tabs[i] = {**t, "label": new_label.strip()}
                    return

    # ════════════════════════════════════════════════════════════════════
    # 模型配置
    # ════════════════════════════════════════════════════════════════════

    def _model_cfg(self) -> dict:
        """获取当前活跃模型的完整配置（供流式管道使用）。"""
        store = _globals._model_store
        if store is None:
            return {"model_name": "", "base_url": "", "api_key": "", "json_mode": False}
        p = store.get_active_profile()
        if p is None:
            return {"model_name": "", "base_url": "", "api_key": "", "json_mode": False}
        return {
            "model_name": p.model_name,
            "base_url": p.base_url or "",
            "api_key": p.api_key or "",
            "json_mode": not p.supports_structured_output,
        }

    # ════════════════════════════════════════════════════════════════════
    # 简单事件
    # ════════════════════════════════════════════════════════════════════

    def toggle_dark_mode(self, _val: bool):
        self.dark_mode = not self.dark_mode

    def clear_active_session(self):
        """清空当前 tab 的对话数据。"""
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

    def set_topic_for_active_tab(self, value: str):
        tab = self._active_tab()
        self._update_tab(tab["id"], topic=value)

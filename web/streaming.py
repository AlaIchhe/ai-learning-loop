"""LangGraph 流式管道 —— 将后台流式逻辑从 AppState 中分离。

本模块提供 StreamingMixin，包含:
    - start_debate / submit_user_response: 后台事件处理器
    - _stream: 核心流式管道（token 级推送 + 中断检测）

使用方式:
    class AppState(StreamingMixin, ProviderMixin, rx.State):
        ...
"""

import sys

from langgraph.types import Command
from langgraph.types import Interrupt as GraphInterrupt
from reflex_base.event import event as rx_event

from socratic_loop.core.state import make_initial_state

from . import _globals

# ── 节点名称映射（模块级常量避免每次调用重建） ——

_NODE_LABELS = {
    "opponent_compute": "提问者",
    "presenter_compute": "提炼者",
    "referee_deliberate": "引导者",
}
_NODE_ROLES = {
    "opponent_compute": "questioner",
    "presenter_compute": "refiner",
    "referee_deliberate": "guide",
}


class StreamingMixin:
    """流式管道 Mixin —— 为 AppState 提供 LangGraph 流式交互能力。

    前置条件: 宿主类需定义 agent_temperature / max_rounds / selected_model_id 字段，
    以及 _model_cfg() 方法和 _update_tab() / _active_tab() 方法。
    """

    # ── 后台任务：启动对话 ──

    @rx_event(background=True)
    async def start_debate(self):
        """启动新一轮辩论——从当前 tab 读取话题并发起流式执行。"""
        graph = _globals._graph
        async with self:
            topic = self.user_input.strip()
            if not topic or graph is None:
                return
            tab = self._active_tab()
            import uuid
            tid = str(uuid.uuid4())
            self._update_tab(tab["id"],
                thread_id=tid, topic=topic,
                messages=[_globals._mkmsg("system", f"开始讨论话题：**{topic}**")],
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

        await self._stream(graph, initial_state, cfg, tab["id"])

    # ── 后台任务：提交回复 ──

    @rx_event(background=True)
    async def submit_user_response(self):
        """提交用户对 interrupt 的回应——恢复图的执行。"""
        graph = _globals._graph
        async with self:
            tab = self._active_tab()
            if not self.user_input.strip() or not tab.get("awaiting_user_response") or graph is None:
                return
            resp = self.user_input
            msgs = [*tab["messages"], _globals._mkmsg("user", resp)]
            self._update_tab(tab["id"],
                messages=msgs, awaiting_user_response=False,
                interrupt_value=None, is_generating=True, user_input="",
            )
            self.user_input = ""
            cfg = {"configurable": {"thread_id": tab["thread_id"]}}

        await self._stream(graph, Command(resume=resp), cfg, tab["id"])

    # ── 核心流式管道 ——

    async def _stream(self, graph, input_data, config: dict, tab_id: str):
        """流式执行 LangGraph，逐 token 推送消息到 UI，结束后检测中断状态。

        处理两种流模式:
            - "messages": token 级增量，实时更新消息气泡
            - "updates": 节点完成标记，终止当前流式消息

        流结束后通过 graph.get_state() 检测是否处于 interrupt 状态，
        若是则在 UI 展示 interrupt 提示。
        """
        acc = ""
        try:
            async for event in graph.astream(input_data, config=config, stream_mode=["messages", "updates"]):
                async with self:
                    mode, data = event
                    if mode == "messages":
                        acc = await self._handle_token(data, tab_id, acc)
                    elif mode == "updates":
                        await self._handle_node_complete(tab_id)
                        acc = ""
        except GraphInterrupt:
            pass
        except Exception:
            import traceback
            traceback.print_exc(file=sys.stderr)

        # 流结束 → 检测中断状态
        await self._handle_stream_end(graph, config, tab_id)

    async def _handle_token(self, data, tab_id: str, acc: str) -> str:
        """处理单个 token 事件——更新或创建流式消息气泡。返回累加后的缓冲区。"""
        msg, meta = data
        token = str(msg.content) if msg.content else ""
        if not token:
            return acc
        node = meta.get("langgraph_node", "")
        role = _NODE_ROLES.get(node, "system")
        self._update_tab(tab_id, current_node=_NODE_LABELS.get(node, ""))
        new_acc = acc + token
        tab = next((t for t in self.tabs if t["id"] == tab_id), None)
        if tab is None:
            return new_acc
        msgs = tab["messages"]
        if not msgs or msgs[-1].get("role") != role or not msgs[-1].get("is_streaming"):
            self._update_tab(tab_id, messages=[*msgs, _globals._mkmsg(role, new_acc, is_streaming=True)])
        else:
            self._update_tab(tab_id, messages=[*msgs[:-1], {**msgs[-1], "content": new_acc}])
        return new_acc

    async def _handle_node_complete(self, tab_id: str):
        """处理节点完成事件——终止当前流式消息。"""
        tab = next((t for t in self.tabs if t["id"] == tab_id), None)
        if tab is None:
            return
        msgs = tab["messages"]
        if msgs and msgs[-1].get("is_streaming"):
            self._update_tab(tab_id, messages=[*msgs[:-1], {**msgs[-1], "is_streaming": False}])

    async def _handle_stream_end(self, graph, config: dict, tab_id: str):
        """流结束后检测 interrupt 状态，展示提示或结束消息。"""
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
                            msgs = [*tab["messages"], _globals._mkmsg("questioner", critique)]
                            self._update_tab(tab_id, messages=msgs,
                                interrupt_value=critique, awaiting_user_response=True,
                                is_generating=False, current_node="")
                            return
                    elif status == "awaiting_thesis_confirmation":
                        draft = gs.values.get("_draft_thesis", "")
                        if draft:
                            msgs = [*tab["messages"], _globals._mkmsg("refiner", draft)]
                            self._update_tab(tab_id, messages=msgs,
                                interrupt_value=draft, awaiting_user_response=True,
                                is_generating=False, current_node="")
                            return
            except Exception:
                pass

            msgs = [*tab["messages"], _globals._mkmsg("system", "讨论已结束。你对这个话题的理解已经得到了深化！🎉")]
            self._update_tab(tab_id, messages=msgs, is_generating=False, current_node="")

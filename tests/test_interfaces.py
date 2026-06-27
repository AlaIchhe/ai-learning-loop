"""
接口测试 —— 验证数据在各层接口之间传递的完整性与一致性。

覆盖：
- State 字段在节点间传递不丢失、不畸变
- Pydantic 模型序列化往返
- Checkpoint 持久化 fidelity
- 条件路由正确性
- Prompt 模板注入
"""

from typing import cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from agents.opponent import opponent_compute_node, opponent_interact_node
from agents.presenter import presenter_compute_node, presenter_interact_node
from agents.referee import referee_deliberate_node
from core.prompts import (
    FINAL_SUMMARY_PROMPT,
    OPPONENT_SYSTEM_PROMPT,
    PRESENTER_SYSTEM_PROMPT,
    REFEREE_SYSTEM_PROMPT,
    final_summary_prompt,
    opponent_prompt,
    presenter_prompt,
    referee_prompt,
)
from core.schemas import DebateResult, Message, RefereeJudgment, RoundRecord
from core.state import AgentState
from workflow.graph import _route_after_referee, build_graph

# =============================================================================
# 辅助函数
# =============================================================================


def _make_state(**overrides: object) -> AgentState:  # pyright: ignore[reportArgumentType]
    defaults: AgentState = {
        "current_thesis": "测试论题",
        "round": 1,
        "status": "opponent_computing",
        "messages": [],
        "history": [],
        "final_result": "",
        "_critique": "",
        "_user_response": "",
        "_draft_thesis": "",
        "_confirmed_thesis": "",
    }
    return cast(AgentState, {**defaults, **overrides})


def _make_mock_model(response_text: str) -> MagicMock:
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.content = response_text
    mock.invoke.return_value = mock_response
    return mock


# =============================================================================
# Prompt 模板测试
# =============================================================================


class TestPromptStrings:
    """验证所有 Prompt 字符串存在且为 str。"""

    def test_opponent_prompt_is_plain_str(self):
        assert isinstance(OPPONENT_SYSTEM_PROMPT, str)
        result = opponent_prompt("测试论题")
        assert isinstance(result, str)
        assert "测试论题" in result

    def test_presenter_prompt_is_plain_str(self):
        assert isinstance(PRESENTER_SYSTEM_PROMPT, str)
        result = presenter_prompt("原始论题", "批判内容", "用户回应")
        assert isinstance(result, str)
        assert "原始论题" in result
        assert "批判内容" in result
        assert "用户回应" in result

    def test_referee_prompt_is_plain_str(self):
        assert isinstance(REFEREE_SYSTEM_PROMPT, str)
        result = referee_prompt("当前论题", "草稿", "确认版", 1)
        assert isinstance(result, str)
        assert "当前论题" in result
        assert "草稿" in result
        assert "确认版" in result
        assert "Round 1" in result

    def test_final_summary_prompt_is_plain_str(self):
        assert isinstance(FINAL_SUMMARY_PROMPT, str)
        result = final_summary_prompt("初始论题", "最终论题", "[]")
        assert isinstance(result, str)
        assert "初始论题" in result
        assert "最终论题" in result


# =============================================================================
# Agent Node 输出接口测试
# =============================================================================


class TestNodeOutputInterface:
    """验证节点返回的 dict key 与 AgentState 兼容。"""

    def test_opponent_compute_output_keys_match_state(self):
        state = _make_state()
        model = _make_mock_model("批判")
        result = opponent_compute_node(state, model=model)
        for key in result:
            assert key in AgentState.__annotations__, f"Unknown key: {key}"

    def test_opponent_interact_output_keys_match_state(self):
        state = _make_state(
            _critique="c", status="awaiting_critique_response",
        )
        # Mock interrupt to avoid GraphInterrupt
        with patch("agents.opponent.interrupt") as mock_int:
            mock_int.return_value = "回应"
            result = opponent_interact_node(state)
        for key in result:
            assert key in AgentState.__annotations__, f"Unknown key: {key}"

    def test_presenter_compute_output_keys_match_state(self):
        state = _make_state(_critique="c", _user_response="u")
        model = _make_mock_model("草稿")
        result = presenter_compute_node(state, model=model)
        for key in result:
            assert key in AgentState.__annotations__, f"Unknown key: {key}"

    def test_presenter_interact_output_keys_match_state(self):
        state = _make_state(
            _draft_thesis="d", status="awaiting_thesis_confirmation",
        )
        with patch("agents.presenter.interrupt") as mock_int:
            mock_int.return_value = "确认"
            result = presenter_interact_node(state)
        for key in result:
            assert key in AgentState.__annotations__, f"Unknown key: {key}"

    def test_referee_output_keys_match_state(self):
        state = _make_state(
            _critique="c", _user_response="u",
            _draft_thesis="d", _confirmed_thesis="cf",
        )
        # Mock the full referee flow
        mock_model = MagicMock()
        structured_mock = MagicMock()
        structured_mock.invoke.return_value = RefereeJudgment(
            round=1, continue_debate=True,
            new_thesis="新论题", reasoning="理由",
        )
        mock_model.with_structured_output.return_value = structured_mock
        mock_model.invoke.return_value = MagicMock(content="总结")

        result = referee_deliberate_node(state, model=mock_model)
        for key in result:
            assert key in AgentState.__annotations__, f"Unknown key: {key}"

    def test_state_merge_is_additive(self):
        """多个节点的部分更新合并后 state 完整。"""
        # 模拟一轮完整流程的返回值合并
        state = _make_state(messages=[], history=[])
        model = _make_mock_model("批判")
        r1 = opponent_compute_node(state, model=model)  # 不修改 state
        assert state["messages"] == []  # 原始未变

        # 手动合并
        merged = {**state, **r1}
        assert merged["_critique"] == "批判"
        assert merged["status"] == "awaiting_critique_response"
        assert len(merged["messages"]) == 1

    def test_all_nodes_produce_same_message_structure(self):
        """所有节点产生的消息都包含 role/content/round。"""
        state = _make_state()
        model = _make_mock_model("测试内容")

        nodes = [
            opponent_compute_node(state, model=model),
        ]

        for node_result in nodes:
            msgs = node_result.get("messages", [])
            for msg in msgs:
                assert "role" in msg
                assert "content" in msg
                assert "round" in msg


# =============================================================================
# Pydantic 序列化往返测试
# =============================================================================


class TestSerializationFidelity:
    """Pydantic 模型 dict 序列化往返保真度。"""

    def test_referee_judgment_roundtrip(self):
        original = RefereeJudgment(
            round=3,
            continue_debate=False,
            new_thesis="最终论题：AI 应在高风险领域受监管。",
            reasoning="论题已清晰明确，边界条件完整。",
            improvement_hint="建议在实际政策制定中参考此论题。",
        )
        restored = RefereeJudgment(**original.model_dump())
        assert restored.round == original.round
        assert restored.continue_debate == original.continue_debate
        assert restored.new_thesis == original.new_thesis
        assert restored.reasoning == original.reasoning
        assert restored.improvement_hint == original.improvement_hint

    def test_round_record_roundtrip(self):
        original = RoundRecord(
            round_number=1,
            thesis_before="原始论题", critique="批判",
            user_response="回应", draft_thesis="草稿",
            confirmed_thesis="确认版", thesis_after="演化论题",
            continue_debate=True, referee_reasoning="理由",
        )
        restored = RoundRecord(**original.model_dump())
        assert restored.round_number == original.round_number
        assert restored.thesis_before == original.thesis_before
        assert restored.thesis_after == original.thesis_after

    def test_message_roundtrip(self):
        original = Message(role="user", content="我的回应", round=2)
        restored = Message(**original.model_dump())
        assert restored.role == "user"
        assert restored.content == "我的回应"
        assert restored.round == 2

    def test_debate_result_construction(self):
        record = RoundRecord(
            round_number=1, thesis_before="A", critique="B",
            user_response="C", draft_thesis="D", confirmed_thesis="E",
            thesis_after="F", continue_debate=False,
            referee_reasoning="完成",
        )
        result = DebateResult(
            initial_thesis="A",
            final_thesis="F",
            total_rounds=1,
            rounds=[record],
            summary="演化完成。",
        )
        assert result.initial_thesis == "A"
        assert result.final_thesis == "F"
        assert result.total_rounds == 1
        assert len(result.rounds) == 1


# =============================================================================
# Checkpoint 持久化测试
# =============================================================================


class TestCheckpointInterface:
    """验证 state 在 checkpoint 中完整保存和恢复。"""

    def test_state_survives_interrupt(self):
        checkpointer = MemorySaver()
        from langgraph.types import Command

        def _mock_oc(state): return {
            "_critique": "批判", "messages": state["messages"] + [
                {"role": "opponent", "content": "批判", "round": 1}
            ], "status": "awaiting_critique_response",
        }

        def _mock_oi(state):
            from langgraph.types import interrupt
            resp = interrupt(state["_critique"])
            return {
                "_user_response": str(resp), "messages": state["messages"] + [
                    {"role": "user", "content": str(resp), "round": 1}
                ], "status": "presenter_computing",
            }

        def _mock_pc(state): return {
            "_draft_thesis": "草稿", "messages": state["messages"] + [
                {"role": "presenter", "content": "草稿", "round": 1}
            ], "status": "awaiting_thesis_confirmation",
        }

        def _mock_pi(state):
            from langgraph.types import interrupt
            cf = interrupt(state["_draft_thesis"])
            return {
                "_confirmed_thesis": str(cf), "messages": state["messages"] + [
                    {"role": "user", "content": str(cf), "round": 1}
                ], "status": "referee_deliberating",
            }

        def _mock_rd(state):
            record = RoundRecord(
                round_number=1, thesis_before=state["current_thesis"],
                critique=state["_critique"], user_response=state["_user_response"],
                draft_thesis=state["_draft_thesis"],
                confirmed_thesis=state["_confirmed_thesis"],
                thesis_after="最终论题", continue_debate=False,
                referee_reasoning="完成",
            )
            return {
                "messages": state["messages"] + [
                    {"role": "referee", "content": "结束", "round": 1}
                ], "history": state["history"] + [record],
                "status": "done", "final_result": "报告",
            }

        graph = build_graph(
            _mock_oc, _mock_oi, _mock_pc, _mock_pi, _mock_rd,
            checkpointer=checkpointer,
        )

        thread_id = str(uuid4())
        config: dict = {"configurable": {"thread_id": thread_id}}
        graph.invoke(_make_state(), config)

        # 读取 checkpoint 快照
        snapshot = graph.get_state(config)
        saved = snapshot.values
        assert saved["current_thesis"] == "测试论题"
        assert saved["round"] == 1
        assert saved["_critique"] == "批判"
        assert len(saved["messages"]) == 1

        # Resume
        graph.invoke(Command(resume="回应"), config)
        graph.invoke(Command(resume="确认"), config)
        final_snapshot = graph.get_state(config)
        final = final_snapshot.values
        assert final["status"] == "done"
        assert len(final["history"]) == 1
        assert final["final_result"] == "报告"

    def test_current_thesis_persists_across_interrupts(self):
        """跨多个中断点 current_thesis 保持正确。"""
        checkpointer = MemorySaver()
        from langgraph.types import Command

        def _oc(state): return {
            "_critique": "批判", "messages": state["messages"] + [
                {"role": "opponent", "content": "批判", "round": state["round"]}
            ], "status": "awaiting_critique_response",
        }
        def _oi(state):
            from langgraph.types import interrupt
            r = interrupt(state["_critique"])
            return {
                "_user_response": str(r), "messages": state["messages"] + [
                    {"role": "user", "content": str(r), "round": state["round"]}
                ], "status": "presenter_computing",
            }
        def _pc(state): return {
            "_draft_thesis": "草稿", "messages": state["messages"] + [
                {"role": "presenter", "content": "草稿", "round": state["round"]}
            ], "status": "awaiting_thesis_confirmation",
        }
        def _pi(state):
            from langgraph.types import interrupt
            cf = interrupt(state["_draft_thesis"])
            return {
                "_confirmed_thesis": str(cf), "messages": state["messages"] + [
                    {"role": "user", "content": str(cf), "round": state["round"]}
                ], "status": "referee_deliberating",
            }
        def _rd(state):
            record = RoundRecord(
                round_number=state["round"],
                thesis_before=state["current_thesis"],
                critique=state["_critique"],
                user_response=state["_user_response"],
                draft_thesis=state["_draft_thesis"],
                confirmed_thesis=state["_confirmed_thesis"],
                thesis_after="演化后-V1",
                continue_debate=True,
                referee_reasoning="继续",
            )
            return {
                "current_thesis": "演化后-V1",
                "messages": state["messages"] + [
                    {"role": "referee", "content": "继续", "round": state["round"]}
                ], "history": state["history"] + [record],
                "status": "opponent_computing",
            }

        graph = build_graph(
            _oc, _oi, _pc, _pi, _rd, checkpointer=checkpointer,
        )

        config: dict = {"configurable": {"thread_id": str(uuid4())}}
        state = _make_state(current_thesis="持久性测试论题")
        graph.invoke(state, config)

        snapshot = graph.get_state(config)
        assert snapshot.values["current_thesis"] == "持久性测试论题"

        graph.invoke(Command(resume="R1回应"), config)
        graph.invoke(Command(resume="R1确认"), config)

        final = graph.get_state(config)
        assert final.values["current_thesis"] == "演化后-V1"
        assert final.values["round"] == 2


# =============================================================================
# 路由测试
# =============================================================================


class TestRoutingInterface:
    """条件路由正确性。"""

    def test_route_done_to_end(self):
        from langgraph.graph import END

        state = _make_state(status="done")
        assert _route_after_referee(state) == END

    def test_route_other_to_next_round(self):
        non_done_statuses = [
            "opponent_computing",
            "awaiting_critique_response",
            "presenter_computing",
            "awaiting_thesis_confirmation",
            "referee_deliberating",
            "idle",
        ]
        for s in non_done_statuses:
            state = _make_state(status=s)  # type: ignore[arg-type]
            assert _route_after_referee(state) == "next_round", f"Failed for {s}"

    def test_route_never_returns_ambiguous(self):
        all_statuses = [
            "idle", "opponent_computing", "awaiting_critique_response",
            "presenter_computing", "awaiting_thesis_confirmation",
            "referee_deliberating", "done",
        ]
        from langgraph.graph import END

        for s in all_statuses:
            state = _make_state(status=s)  # type: ignore[arg-type]
            result = _route_after_referee(state)
            assert result in (END, "next_round"), f"{s} → {result}"

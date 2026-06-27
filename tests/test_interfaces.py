"""
接口测试 —— 验证数据在各层接口之间传递的完整性与一致性。

覆盖：
- State 字段在节点间传递不丢失、不畸变
- Prompt 模板由 State 字段正确拼接
- 节点输出的 dict 可安全合并回 State
- RefereeJudgment 在 Pydantic ↔ dict 间往返序列化无损
- 消息格式在三类 Agent 间保持一致结构
- LangGraph checkpoint 存储/恢复的 fidelity
"""

from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END

from core.state import AgentState
from core.schemas import (
    Message,
    RefereeJudgment,
    CategoryScores,
    RoundRecord,
    DebateResult,
)
from core.prompts import (
    presenter_prompt,
    opponent_prompt,
    referee_prompt,
)
from workflow.graph import build_graph, _start_node, _next_round_node, _route_after_referee


# =============================================================================
# 1. Prompt 接口：State 字段 → 模板 → 正确字符串
# =============================================================================


class TestPromptInterface:
    """验证 State 字段正确注入 Prompt 模板。"""

    def test_presenter_prompt_injects_topic(self):
        result = presenter_prompt("AI 监管的必要性")
        assert "AI 监管的必要性" in result
        assert "请围绕此主题" in result  # 首轮提示

    def test_presenter_prompt_injects_opponent_feedback(self):
        result = presenter_prompt("AI 监管", "你的证据不充分")
        assert "AI 监管" in result
        assert "你的证据不充分" in result
        assert "上一轮反驳者的质疑" in result

    def test_presenter_prompt_handles_empty_opponent(self):
        """空字符串时走首轮分支。"""
        result = presenter_prompt("主题", "")
        assert "上一轮反驳" not in result
        assert "请围绕此主题" in result

    def test_opponent_prompt_injects_both_fields(self):
        result = opponent_prompt("AI 伦理", "AI 必须接受监管因为...")
        assert "AI 伦理" in result
        assert "AI 必须接受监管因为" in result

    def test_referee_prompt_injects_all_fields(self):
        result = referee_prompt("气候变化政策", 3, "论点正文...", "反驳正文...")
        assert "气候变化政策" in result
        assert "第 3 轮" in result
        assert "论点正文..." in result
        assert "反驳正文..." in result
        assert "JSON" in result

    def test_prompt_strings_are_plain_str(self):
        """所有模板返回纯 str，不含 None 或 bytes。"""
        p = presenter_prompt("X", "Y")
        o = opponent_prompt("X", "Y")
        r = referee_prompt("X", 1, "A", "B")
        for name, val in [("presenter", p), ("opponent", o), ("referee", r)]:
            assert isinstance(val, str), f"{name}: expected str, got {type(val)}"
            assert "None" not in val, f"{name} contains 'None'"


# =============================================================================
# 2. 节点输出接口：dict → State 合并兼容性
# =============================================================================


# Mock agent nodes (stateless, same shape as real agents)
def _test_presenter(state: AgentState) -> dict:
    return {
        "presenter_argument": f"论点-{state['topic']}",
        "messages": state["messages"] + [{"role": "presenter", "content": f"论点-{state['topic']}", "round": state["round"]}],
        "status": "opposing",
    }


def _test_opponent(state: AgentState) -> dict:
    return {
        "opponent_rebuttal": f"反驳-{state['presenter_argument'][:10]}",
        "messages": state["messages"] + [{"role": "opponent", "content": f"反驳-{state['presenter_argument'][:10]}", "round": state["round"]}],
        "status": "judging",
    }


def _test_referee(state: AgentState) -> dict:
    j = RefereeJudgment(
        round=state["round"],
        presenter_score=CategoryScores(clarity=7, logic=6, evidence=7, persuasiveness=6),
        opponent_score=CategoryScores(clarity=6, logic=7, evidence=5, persuasiveness=6),
        presenter_total=6.5,
        opponent_total=6.0,
        winner="presenter",
        reasoning="理由",
        presenter_strength="亮点",
        presenter_weakness="不足",
        opponent_strength="亮点",
        opponent_weakness="不足",
        improvement_hint="建议",
    )
    next_status = "done" if state["round"] >= state["max_rounds"] else "presenting"
    return {
        "referee_judgment": j,
        "messages": state["messages"] + [{"role": "referee", "content": f"裁决-R{state['round']}", "round": state["round"]}],
        "history": state["history"] + [RoundRecord(round_number=state["round"], presenter_argument=state["presenter_argument"], opponent_rebuttal=state["opponent_rebuttal"], judgment=j)],
        "status": next_status,
    }


class TestNodeOutputInterface:
    """验证节点输出 dict 可安全合并回 State。"""

    def _initial_state(self, **overrides) -> AgentState:
        s: AgentState = {
            "topic": "测试", "round": 1, "max_rounds": 2, "status": "presenting",
            "messages": [], "presenter_argument": "", "opponent_rebuttal": "",
            "referee_judgment": None, "history": [], "final_result": "",
        }
        s.update(overrides)
        return s

    def test_presenter_output_keys_match_state(self):
        result = _test_presenter(self._initial_state())
        # 所有返回键必须存在于 AgentState 中
        for key in result:
            assert key in AgentState.__annotations__, f"Key '{key}' not in AgentState"
        assert result["status"] == "opposing"
        assert len(result["presenter_argument"]) > 0
        assert len(result["messages"]) == 1

    def test_opponent_output_keys_match_state(self):
        s = self._initial_state(presenter_argument="论点内容", messages=[{"role": "presenter", "content": "论点内容", "round": 1}])
        result = _test_opponent(s)
        for key in result:
            assert key in AgentState.__annotations__, f"Key '{key}' not in AgentState"
        assert result["status"] == "judging"

    def test_referee_output_keys_match_state(self):
        s = self._initial_state(status="judging", presenter_argument="论点", opponent_rebuttal="反驳",
                                messages=[{"role": "opponent", "content": "反驳", "round": 1}])
        result = _test_referee(s)
        for key in result:
            assert key in AgentState.__annotations__, f"Key '{key}' not in AgentState"
        assert isinstance(result["referee_judgment"], RefereeJudgment)
        assert isinstance(result["history"][0], RoundRecord)

    def test_state_merge_is_additive(self):
        """节点返回的 dict 只覆盖对应 key，不删除其他 key。"""
        base = self._initial_state()
        result = _test_presenter(base)
        # 模拟 LangGraph 合并
        merged = {**base, **result}
        # 合并后所有原始 key 仍然存在
        for key in AgentState.__annotations__:
            assert key in merged, f"Key '{key}' lost after merge"

    def test_all_nodes_produce_same_message_structure(self):
        """三类 Agent 产生的消息具有相同结构。"""
        expected_keys = {"role", "content", "round"}
        s = self._initial_state()

        r1 = _test_presenter(s)
        msg = r1["messages"][-1]
        assert expected_keys.issubset(msg.keys()), f"presenter msg missing keys: {expected_keys - set(msg.keys())}"

        s2 = {**s, **r1}
        r2 = _test_opponent(s2)
        msg = r2["messages"][-1]
        assert expected_keys.issubset(msg.keys()), "opponent msg missing keys"

        s3 = {**s2, **r2}
        r3 = _test_referee(s3)
        msg = r3["messages"][-1]
        assert expected_keys.issubset(msg.keys()), "referee msg missing keys"

    def test_scheduler_nodes_dont_leak_keys(self):
        """调度节点只返回声明的 key，不污染 State。"""
        r1 = _start_node({"status": "idle"})
        assert set(r1.keys()) == {"status"}

        r2 = _next_round_node({"round": 1, "presenter_argument": "x", "opponent_rebuttal": "y", "referee_judgment": None})
        assert set(r2.keys()) == {"round", "presenter_argument", "opponent_rebuttal", "referee_judgment"}


# =============================================================================
# 3. 序列化接口：Pydantic ↔ dict 往返无损
# =============================================================================


class TestSerializationFidelity:
    """数据跨越 Pydantic ↔ dict 边界后不丢失、不畸变。"""

    def test_referee_judgment_roundtrip(self):
        original = RefereeJudgment(
            round=3,
            presenter_score=CategoryScores(clarity=7.5, logic=6.2, evidence=8.1, persuasiveness=7.0),
            opponent_score=CategoryScores(clarity=6.3, logic=7.8, evidence=5.4, persuasiveness=6.9),
            presenter_total=7.2,
            opponent_total=6.6,
            winner="presenter",
            reasoning="陈述者论据更充分，逻辑上有改进空间。",
            presenter_strength="数据翔实",
            presenter_weakness="推理跳跃",
            opponent_strength="逻辑严密",
            opponent_weakness="论据陈旧",
            improvement_hint="引用最新研究。",
        )
        d = original.model_dump()
        restored = RefereeJudgment(**d)
        assert restored.round == original.round == 3
        assert restored.presenter_score.clarity == 7.5
        assert restored.presenter_total == 7.2
        assert restored.winner == "presenter"
        assert restored.reasoning == "陈述者论据更充分，逻辑上有改进空间。"
        assert restored.improvement_hint == "引用最新研究。"

    def test_round_record_roundtrip(self):
        j = RefereeJudgment(
            round=2,
            presenter_score=CategoryScores(clarity=5, logic=5, evidence=5, persuasiveness=5),
            opponent_score=CategoryScores(clarity=5, logic=5, evidence=5, persuasiveness=5),
            presenter_total=5, opponent_total=5, winner="draw",
            reasoning="平局。", presenter_strength="", presenter_weakness="",
            opponent_strength="", opponent_weakness="", improvement_hint="",
        )
        r = RoundRecord(round_number=2, presenter_argument="P", opponent_rebuttal="O", judgment=j)
        d = r.model_dump()
        restored = RoundRecord(**d)
        assert restored.round_number == 2
        assert restored.presenter_argument == "P"
        assert restored.opponent_rebuttal == "O"
        assert restored.judgment.winner == "draw"

    def test_message_roundtrip(self):
        m = Message(role="presenter", content="论点...", round=2)
        d = m.model_dump()
        restored = Message(**d)
        assert restored.role == "presenter"
        assert restored.content == "论点..."
        assert restored.round == 2

    def test_debate_result_construction(self):
        j = RefereeJudgment(
            round=1, presenter_score=CategoryScores(clarity=8, logic=8, evidence=8, persuasiveness=8),
            opponent_score=CategoryScores(clarity=7, logic=7, evidence=7, persuasiveness=7),
            presenter_total=8, opponent_total=7, winner="presenter",
            reasoning="好", presenter_strength="", presenter_weakness="",
            opponent_strength="", opponent_weakness="", improvement_hint="",
        )
        r = RoundRecord(round_number=1, presenter_argument="A", opponent_rebuttal="B", judgment=j)
        result = DebateResult(topic="X", total_rounds=1, winner="presenter", presenter_wins=1, opponent_wins=0, draws=0, rounds=[r], summary="总结")
        assert result.presenter_wins + result.opponent_wins + result.draws == result.total_rounds


# =============================================================================
# 4. Checkpoint 接口：LangGraph 存储/恢复 fidelity
# =============================================================================


class TestCheckpointInterface:
    """验证状态经过 checkpointer 存取后数据不丢失。"""

    def test_full_state_survives_checkpoint_roundtrip(self):
        """完整 10 字段状态写入 checkpoint 再读出，每个字段一致。"""
        checkpointer = MemorySaver()
        graph = build_graph(
            _test_presenter, _test_opponent, _test_referee,
            checkpointer=checkpointer,
        )
        tid = str(uuid4())
        config = {"configurable": {"thread_id": tid}}

        initial: AgentState = {
            "topic": "端到端接口测试",
            "round": 1,
            "max_rounds": 1,
            "status": "idle",
            "messages": [],
            "presenter_argument": "",
            "opponent_rebuttal": "",
            "referee_judgment": None,
            "history": [],
            "final_result": "",
        }

        # 逐步推进至 done
        graph.invoke(initial, config)   # → interrupt before presenter
        graph.invoke(None, config)      # → presenter done
        graph.invoke(None, config)      # → opponent done
        graph.invoke(None, config)      # → referee → done

        # 从 checkpoint 读回
        snapshot = graph.get_state(config)
        saved = snapshot.values

        # 每个字段类型和值校验
        assert saved["topic"] == "端到端接口测试"
        assert saved["round"] == 1
        assert saved["max_rounds"] == 1
        assert saved["status"] == "done"
        assert isinstance(saved["messages"], list)
        assert len(saved["messages"]) == 3
        assert saved["presenter_argument"].startswith("论点-")
        assert saved["opponent_rebuttal"].startswith("反驳-")
        assert isinstance(saved["referee_judgment"], RefereeJudgment)
        assert isinstance(saved["history"], list)
        assert len(saved["history"]) == 1
        assert isinstance(saved["history"][0], RoundRecord)
        assert saved["final_result"] == ""

    def test_state_persistence_across_interrupts(self):
        """跨多个 interrupt 点，topic 和 max_rounds 始终不变。"""
        checkpointer = MemorySaver()
        graph = build_graph(
            _test_presenter, _test_opponent, _test_referee,
            checkpointer=checkpointer,
        )
        tid = str(uuid4())
        config = {"configurable": {"thread_id": tid}}

        s: AgentState = {
            "topic": "持久性测试", "round": 1, "max_rounds": 2, "status": "idle",
            "messages": [], "presenter_argument": "", "opponent_rebuttal": "",
            "referee_judgment": None, "history": [], "final_result": "",
        }

        # 在每个 interrupt 点读取 state
        states = []
        states.append(graph.invoke(s, config))          # before presenter
        states.append(graph.invoke(None, config))       # before opponent
        states.append(graph.invoke(None, config))       # before referee (R1)
        states.append(graph.invoke(None, config))       # before presenter (R2)
        states.append(graph.invoke(None, config))       # before opponent (R2)
        states.append(graph.invoke(None, config))       # before referee (R2)
        states.append(graph.invoke(None, config))       # done

        for i, st in enumerate(states):
            assert st["topic"] == "持久性测试", f"Step {i}: topic changed"
            # max_rounds never changes
            assert st["max_rounds"] == 2, f"Step {i}: max_rounds changed from 2"


# =============================================================================
# 5. 条件路由接口：status → 正确目标
# =============================================================================


class TestRoutingInterface:
    """验证 status 字段驱动路由的完整性。"""

    def test_all_status_values_map_correctly(self):
        """status 的 5 种值只有 'done' 映射到 END。"""
        assert _route_after_referee({"status": "presenting"}) == "next_round"
        assert _route_after_referee({"status": "opposing"}) == "next_round"
        assert _route_after_referee({"status": "judging"}) == "next_round"
        assert _route_after_referee({"status": "idle"}) == "next_round"
        assert _route_after_referee({"status": "done"}) == END

    def test_route_never_returns_none_or_empty(self):
        for status in ["idle", "presenting", "opposing", "judging", "done"]:
            result = _route_after_referee({"status": status})
            assert result is not None, f"status={status}: returned None"
            assert result in ("next_round", END), f"status={status}: bad target '{result}'"

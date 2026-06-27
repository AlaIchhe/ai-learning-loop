"""
端到端集成测试 —— 多轮辩论全生命周期。

使用 Mock Agent 节点 + 真实 LangGraph 图，
验证 interrupt_before 暂停/恢复、多轮循环、状态累积。
"""

from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from core.state import AgentState
from core.schemas import RefereeJudgment, CategoryScores, RoundRecord
from workflow.graph import build_graph


# =============================================================================
# Mock Agent 节点（模拟完整 LLM 行为，包含状态转移）
# =============================================================================


def _mock_presenter(state: AgentState) -> dict:
    argument = f"[陈述者] 第{state['round']}轮论点：支持「{state['topic']}」"
    msg = {"role": "presenter", "content": argument, "round": state["round"]}
    return {
        "presenter_argument": argument,
        "messages": state["messages"] + [msg],
        "status": "opposing",
    }


def _mock_opponent(state: AgentState) -> dict:
    rebuttal = f"[反驳者] 第{state['round']}轮反驳：质疑论点中的漏洞"
    msg = {"role": "opponent", "content": rebuttal, "round": state["round"]}
    return {
        "opponent_rebuttal": rebuttal,
        "messages": state["messages"] + [msg],
        "status": "judging",
    }


def _mock_referee(state: AgentState) -> dict:
    judgment = RefereeJudgment(
        round=state["round"],
        presenter_score=CategoryScores(clarity=7.5, logic=6.5, evidence=7.0, persuasiveness=7.0),
        opponent_score=CategoryScores(clarity=6.0, logic=7.0, evidence=5.5, persuasiveness=6.5),
        presenter_total=7.0,
        opponent_total=6.3,
        winner="presenter",
        reasoning=f"第{state['round']}轮：陈述者论据更充分。",
        presenter_strength="结构清晰",
        presenter_weakness="深度不足",
        opponent_strength="逻辑严密",
        opponent_weakness="例证缺乏",
        improvement_hint="双方应引用更多数据。",
    )
    next_status = "done" if state["round"] >= state["max_rounds"] else "presenting"
    msg = {
        "role": "referee",
        "content": f"[裁判] 第{state['round']}轮：陈述者 {judgment.presenter_total} vs 反驳者 {judgment.opponent_total}，胜者: {judgment.winner}",
        "round": state["round"],
    }
    record = RoundRecord(
        round_number=state["round"],
        presenter_argument=state["presenter_argument"],
        opponent_rebuttal=state["opponent_rebuttal"],
        judgment=judgment,
    )
    return {
        "referee_judgment": judgment,
        "messages": state["messages"] + [msg],
        "history": state["history"] + [record],
        "status": next_status,
    }


# =============================================================================
# 测试
# =============================================================================


class TestEndToEnd:
    """多轮辩论端到端集成测试。"""

    def test_full_two_round_debate(self):
        """两轮辩论全生命周期：idle → R1(presenter→opponent→referee) → R2 → done。"""
        checkpointer = MemorySaver()
        graph = build_graph(
            _mock_presenter, _mock_opponent, _mock_referee,
            checkpointer=checkpointer,
        )
        thread_id = str(uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: AgentState = {
            "topic": "AI 是否应该被严格监管？",
            "round": 1,
            "max_rounds": 2,
            "status": "idle",
            "messages": [],
            "presenter_argument": "",
            "opponent_rebuttal": "",
            "referee_judgment": None,
            "history": [],
            "final_result": "",
        }

        # Step 1: idle → start_node → interrupt_before presenter
        state = graph.invoke(initial_state, config)
        assert state["status"] == "presenting"
        assert state["round"] == 1
        assert len(state["messages"]) == 0  # presenter 尚未执行
        print("  Step 1 OK: idle → interrupted before presenter")

        # Step 2: resume → presenter → interrupt_before opponent
        state = graph.invoke(None, config)
        assert state["status"] == "opposing"
        assert "第1轮论点" in state["presenter_argument"]
        assert len(state["messages"]) == 1
        assert state["messages"][-1]["role"] == "presenter"
        print("  Step 2 OK: presenter executed → interrupted before opponent")

        # Step 3: resume → opponent → interrupt_before referee
        state = graph.invoke(None, config)
        assert state["status"] == "judging"
        assert "第1轮反驳" in state["opponent_rebuttal"]
        assert len(state["messages"]) == 2
        assert state["messages"][-1]["role"] == "opponent"
        print("  Step 3 OK: opponent executed → interrupted before referee")

        # Step 4: resume → referee (round 1) → interrupt_before presenter (round 2)
        state = graph.invoke(None, config)
        assert state["status"] == "presenting"  # 准备第 2 轮
        assert state["round"] == 2  # next_round 已执行
        assert state["referee_judgment"] is None  # 缓存已清空
        assert len(state["history"]) == 1
        assert isinstance(state["history"][0], RoundRecord)
        assert state["history"][0].round_number == 1
        assert len(state["messages"]) == 3
        assert state["messages"][-1]["role"] == "referee"
        print("  Step 4 OK: referee R1 executed → next_round → interrupted before presenter R2")

        # Step 5: resume → presenter (round 2) → interrupt_before opponent
        state = graph.invoke(None, config)
        assert state["status"] == "opposing"
        assert "第2轮论点" in state["presenter_argument"]
        assert len(state["messages"]) == 4
        print("  Step 5 OK: presenter R2 executed → interrupted before opponent")

        # Step 6: resume → opponent (round 2) → interrupt_before referee
        state = graph.invoke(None, config)
        assert state["status"] == "judging"
        assert "第2轮反驳" in state["opponent_rebuttal"]
        assert len(state["messages"]) == 5
        print("  Step 6 OK: opponent R2 executed → interrupted before referee")

        # Step 7: resume → referee (round 2) → status=done → END
        state = graph.invoke(None, config)
        assert state["status"] == "done"
        assert state["round"] == 2  # round 未再递增（done 后不进 next_round）
        assert len(state["history"]) == 2
        assert state["history"][0].round_number == 1
        assert state["history"][1].round_number == 2
        assert len(state["messages"]) == 6
        print("  Step 7 OK: referee R2 executed → status=done → END")

        # 最终状态校验
        roles = [m["role"] for m in state["messages"]]
        assert roles == [
            "presenter", "opponent", "referee",
            "presenter", "opponent", "referee",
        ]
        print(f"  Roles sequence: {roles}")

        assert state["topic"] == "AI 是否应该被严格监管？"
        print(f"  Topic preserved: {state['topic']}")

        print()
        print(f"  E2E PASSED: {state['max_rounds']} rounds, {len(state['messages'])} messages, {len(state['history'])} history records")

    def test_single_round_debate(self):
        """单轮辩论：max_rounds=1，裁判后直接结束。"""
        checkpointer = MemorySaver()
        graph = build_graph(
            _mock_presenter, _mock_opponent, _mock_referee,
            checkpointer=checkpointer,
        )
        thread_id = str(uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        state: AgentState = {
            "topic": "简答题",
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

        # Step 1: idle → interrupted before presenter
        state = graph.invoke(state, config)
        assert state["status"] == "presenting"

        # Step 2: presenter → interrupted before opponent
        state = graph.invoke(None, config)
        assert state["status"] == "opposing"

        # Step 3: opponent → interrupted before referee
        state = graph.invoke(None, config)
        assert state["status"] == "judging"

        # Step 4: referee → done (max_rounds=1, no next_round)
        state = graph.invoke(None, config)
        assert state["status"] == "done"
        assert state["round"] == 1  # 未递增
        assert len(state["history"]) == 1
        assert len(state["messages"]) == 3
        print("  Single round E2E PASSED")

    def test_graph_get_state_consistency(self):
        """验证 graph.get_state() 在任何时刻都能读到一致的状态快照。"""
        checkpointer = MemorySaver()
        graph = build_graph(
            _mock_presenter, _mock_opponent, _mock_referee,
            checkpointer=checkpointer,
        )
        thread_id = str(uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: AgentState = {
            "topic": "测试主题",
            "round": 1, "max_rounds": 1,
            "status": "idle",
            "messages": [], "presenter_argument": "", "opponent_rebuttal": "",
            "referee_judgment": None, "history": [], "final_result": "",
        }

        graph.invoke(initial_state, config)
        snapshot = graph.get_state(config)
        assert snapshot.values["status"] == "presenting"
        assert snapshot.values["topic"] == "测试主题"

        graph.invoke(None, config)
        snapshot = graph.get_state(config)
        assert snapshot.values["status"] == "opposing"
        assert "presenter" in snapshot.values["messages"][-1]["role"]

        graph.invoke(None, config)
        graph.invoke(None, config)  # → done
        snapshot = graph.get_state(config)
        assert snapshot.values["status"] == "done"
        assert len(snapshot.values["history"]) == 1

        print("  State consistency PASSED")

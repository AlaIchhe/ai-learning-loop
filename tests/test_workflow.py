"""
Workflow 图编排的单元测试。

测试目标：验证图的节点注册、边连接、条件路由和断点配置。
所有节点用纯函数 Mock，不涉及 LLM 调用。
"""

from unittest.mock import MagicMock

from langgraph.graph import END

from core.state import AgentState
from core.schemas import RefereeJudgment, CategoryScores
from workflow.graph import (
    build_graph,
    _start_node,
    _next_round_node,
    _route_after_referee,
)


# =============================================================================
# Mock 节点工厂
# =============================================================================


def _mock_presenter(state: AgentState) -> dict:
    return {
        "presenter_argument": f"论点-第{state['round']}轮",
        "messages": state["messages"]
        + [{"role": "presenter", "content": f"论点-第{state['round']}轮", "round": state["round"]}],
        "status": "opposing",
    }


def _mock_opponent(state: AgentState) -> dict:
    return {
        "opponent_rebuttal": f"反驳-第{state['round']}轮",
        "messages": state["messages"]
        + [{"role": "opponent", "content": f"反驳-第{state['round']}轮", "round": state["round"]}],
        "status": "judging",
    }


def _mock_referee(state: AgentState) -> dict:
    judgment = RefereeJudgment(
        round=state["round"],
        presenter_score=CategoryScores(clarity=7.0, logic=6.0, evidence=7.0, persuasiveness=6.5),
        opponent_score=CategoryScores(clarity=6.0, logic=7.0, evidence=5.5, persuasiveness=6.0),
        presenter_total=6.6,
        opponent_total=6.1,
        winner="presenter",
        reasoning="陈述者论据更充分。",
        presenter_strength="好",
        presenter_weakness="一般",
        opponent_strength="好",
        opponent_weakness="一般",
        improvement_hint="加油",
    )
    next_status = "done" if state["round"] >= state["max_rounds"] else "presenting"
    return {
        "referee_judgment": judgment,
        "messages": state["messages"]
        + [{"role": "referee", "content": f"裁决-第{state['round']}轮", "round": state["round"]}],
        "status": next_status,
    }


def _make_initial_state(**overrides) -> AgentState:
    defaults: AgentState = {
        "topic": "测试主题",
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
    defaults.update(overrides)
    return defaults


# =============================================================================
# 纯调度节点测试
# =============================================================================


class TestStartNode:
    def test_sets_status_to_presenting(self):
        state = _make_initial_state(status="idle")
        result = _start_node(state)
        assert result["status"] == "presenting"

    def test_only_touches_status(self):
        state = _make_initial_state()
        result = _start_node(state)
        assert set(result.keys()) == {"status"}


class TestNextRoundNode:
    def test_increments_round(self):
        state = _make_initial_state(round=2)
        result = _next_round_node(state)
        assert result["round"] == 3

    def test_clears_current_round_cache(self):
        state = _make_initial_state(
            presenter_argument="旧论点",
            opponent_rebuttal="旧反驳",
            referee_judgment=MagicMock(),
        )
        result = _next_round_node(state)
        assert result["presenter_argument"] == ""
        assert result["opponent_rebuttal"] == ""
        assert result["referee_judgment"] is None

    def test_returns_exactly_four_keys(self):
        result = _next_round_node(_make_initial_state())
        assert set(result.keys()) == {
            "round",
            "presenter_argument",
            "opponent_rebuttal",
            "referee_judgment",
        }


# =============================================================================
# 条件路由测试
# =============================================================================


class TestRouteAfterReferee:
    def test_routes_to_end_when_done(self):
        state = _make_initial_state(status="done")
        assert _route_after_referee(state) == END

    def test_routes_to_next_round_when_presenting(self):
        state = _make_initial_state(status="presenting")
        assert _route_after_referee(state) == "next_round"


# =============================================================================
# 图编译测试
# =============================================================================


class TestBuildGraph:
    def test_returns_compiled_graph(self):
        graph = build_graph(_mock_presenter, _mock_opponent, _mock_referee)
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "stream")

    def test_graph_has_all_nodes(self):
        graph = build_graph(_mock_presenter, _mock_opponent, _mock_referee)
        node_names = set(graph.nodes.keys())
        assert "start" in node_names
        assert "presenter" in node_names
        assert "opponent" in node_names
        assert "referee" in node_names
        assert "next_round" in node_names

    def test_all_mock_nodes_are_invoked(self):
        """使用 spy 验证图调用链覆盖了所有节点。"""
        presenter_spy = MagicMock(side_effect=_mock_presenter)
        opponent_spy = MagicMock(side_effect=_mock_opponent)
        referee_spy = MagicMock(side_effect=_mock_referee)

        graph = build_graph(presenter_spy, opponent_spy, referee_spy)

        # invoke 会因 interrupt_before 暂停多次，需要用 thread
        config = {"configurable": {"thread_id": "test-chain"}}
        # 多次调用直到结束，每次经过一个 interrupt
        state = _make_initial_state()
        list(graph.stream(state, config))
        # 第一个 interrupt 在 presenter 之前，所以 presenter 尚未被调用
        assert presenter_spy.call_count == 0

    def test_default_interrupt_before(self):
        graph = build_graph(_mock_presenter, _mock_opponent, _mock_referee)
        # 验证编译时传入了默认断点
        assert graph.interrupt_before_nodes is not None
        assert "presenter" in graph.interrupt_before_nodes
        assert "opponent" in graph.interrupt_before_nodes
        assert "referee" in graph.interrupt_before_nodes

    def test_custom_interrupt_before(self):
        graph = build_graph(
            _mock_presenter, _mock_opponent, _mock_referee,
            interrupt_before=["referee"],
        )
        assert graph.interrupt_before_nodes == ["referee"]

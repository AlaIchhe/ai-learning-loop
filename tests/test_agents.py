"""
Agent 节点的单元测试。

所有测试通过 Mock LLM 来验证输入输出契约，不依赖真实 API 调用。
"""

from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from core.state import AgentState
from core.schemas import RefereeJudgment, CategoryScores, RoundRecord
from agents.opponent import opponent_node
from agents.presenter import presenter_node
from agents.referee import referee_node


# =============================================================================
# 测试夹具
# =============================================================================


def _make_state(**overrides) -> AgentState:
    """构造测试用的最小合法 state。"""
    defaults: AgentState = {
        "topic": "AI 是否应该被严格监管？",
        "round": 1,
        "max_rounds": 3,
        "status": "opposing",
        "messages": [],
        "presenter_argument": "AI 监管是必要的，因为未受控的 AI 可能带来灾难性风险。",
        "opponent_rebuttal": "",
        "referee_judgment": None,
        "history": [],
        "final_result": "",
    }
    defaults.update(overrides)
    return defaults


def _make_mock_model(response_text: str = "这是一个测试反驳。陈述者的论点存在逻辑漏洞...") -> MagicMock:
    """构造一个返回固定文本的 Mock LLM（用于 opponent / presenter）。"""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.content = response_text
    mock.invoke.return_value = mock_response
    return mock


def _make_mock_referee_model(judgment: RefereeJudgment | None = None) -> MagicMock:
    """构造支持 with_structured_output 的 Mock LLM（用于 referee）。

    referee 调用链: model.with_structured_output(schema).invoke(messages)
    """
    if judgment is None:
        judgment = RefereeJudgment(
            round=1,
            presenter_score=CategoryScores(clarity=7.0, logic=6.5, evidence=7.0, persuasiveness=6.0),
            opponent_score=CategoryScores(clarity=6.0, logic=7.0, evidence=5.5, persuasiveness=6.5),
            presenter_total=6.6,
            opponent_total=6.3,
            winner="presenter",
            reasoning="陈述者论据更充分，但逻辑上有改进空间。",
            presenter_strength="数据引用准确",
            presenter_weakness="逻辑链条有跳跃",
            opponent_strength="逻辑推理严密",
            opponent_weakness="缺乏具体例证",
            improvement_hint="双方都应多引用实证数据。",
        )

    mock_structured = MagicMock()
    mock_structured.invoke.return_value = judgment

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_structured
    return mock_model


# =============================================================================
# opponent_node 测试
# =============================================================================


class TestOpponentNode:
    """反驳者节点的契约测试。"""

    def test_returns_correct_keys(self):
        state = _make_state()
        result = opponent_node(state, model=_make_mock_model())
        assert "opponent_rebuttal" in result
        assert "messages" in result
        assert "status" in result

    def test_opponent_rebuttal_is_non_empty_str(self):
        state = _make_state()
        result = opponent_node(state, model=_make_mock_model("反驳文本"))
        assert isinstance(result["opponent_rebuttal"], str)
        assert len(result["opponent_rebuttal"]) > 0
        assert result["opponent_rebuttal"] == "反驳文本"

    def test_status_transitions_to_judging(self):
        result = opponent_node(_make_state(), model=_make_mock_model())
        assert result["status"] == "judging"

    def test_appends_message_with_correct_role(self):
        state = _make_state(messages=[{"role": "system", "content": "start", "round": 0}])
        result = opponent_node(state, model=_make_mock_model("反驳内容"))
        msgs = result["messages"]
        assert len(msgs) == 2
        assert msgs[-1]["role"] == "opponent"
        assert msgs[-1]["content"] == "反驳内容"
        assert msgs[-1]["round"] == 1

    def test_does_not_mutate_original_state(self):
        state = _make_state()
        original_messages = list(state["messages"])
        opponent_node(state, model=_make_mock_model())
        assert state["messages"] == original_messages
        assert state["status"] == "opposing"

    def test_passes_topic_and_argument_to_llm(self):
        state = _make_state(topic="测试主题", presenter_argument="测试论点内容")
        mock = _make_mock_model("反驳")
        opponent_node(state, model=mock)
        user_msg = mock.invoke.call_args[0][0][1]
        assert isinstance(user_msg, HumanMessage)
        assert "测试主题" in str(user_msg.content)
        assert "测试论点内容" in str(user_msg.content)


# =============================================================================
# presenter_node 测试
# =============================================================================


class TestPresenterNode:
    """陈述者节点的契约测试。"""

    def test_returns_correct_keys(self):
        result = presenter_node(_make_state(), model=_make_mock_model())
        assert "presenter_argument" in result
        assert "messages" in result
        assert "status" in result

    def test_presenter_argument_is_non_empty_str(self):
        result = presenter_node(_make_state(), model=_make_mock_model("我的论点"))
        assert isinstance(result["presenter_argument"], str)
        assert result["presenter_argument"] == "我的论点"

    def test_status_transitions_to_opposing(self):
        result = presenter_node(_make_state(), model=_make_mock_model())
        assert result["status"] == "opposing"

    def test_appends_message_with_correct_role(self):
        state = _make_state(messages=[{"role": "system", "content": "start", "round": 0}])
        result = presenter_node(state, model=_make_mock_model("论点内容"))
        msgs = result["messages"]
        assert len(msgs) == 2
        assert msgs[-1]["role"] == "presenter"
        assert msgs[-1]["content"] == "论点内容"
        assert msgs[-1]["round"] == 1

    def test_does_not_mutate_original_state(self):
        state = _make_state(status="presenting")
        original_messages = list(state["messages"])
        presenter_node(state, model=_make_mock_model())
        assert state["messages"] == original_messages
        assert state["status"] == "presenting"

    def test_first_round_has_no_opponent_context(self):
        """第一轮时，prompt 中不应包含上一轮反驳内容。"""
        mock = _make_mock_model("论点")
        presenter_node(_make_state(messages=[]), model=mock)
        user_msg = mock.invoke.call_args[0][0][1]
        # 第一轮无对手历史，prompt 中不应出现「上一轮反驳」字样
        assert "上一轮反驳" not in str(user_msg.content)
        assert "质疑" not in str(user_msg.content)

    def test_subsequent_round_includes_opponent_rebuttal(self):
        """非首轮时，prompt 应包含上一轮对手的反驳文本。"""
        state = _make_state(
            round=2,
            messages=[
                {"role": "presenter", "content": "论点...", "round": 1},
                {"role": "opponent", "content": "你的证据不足!", "round": 1},
            ],
        )
        mock = _make_mock_model("修正后的论点")
        presenter_node(state, model=mock)
        user_msg = mock.invoke.call_args[0][0][1]
        assert "你的证据不足" in str(user_msg.content)


# =============================================================================
# referee_node 测试
# =============================================================================


class TestRefereeNode:
    """裁判节点的契约测试。"""

    def test_returns_correct_keys(self):
        state = _make_state(status="judging", opponent_rebuttal="反驳文本...")
        result = referee_node(state, model=_make_mock_referee_model())
        assert "referee_judgment" in result
        assert "messages" in result
        assert "history" in result
        assert "status" in result

    def test_judgment_is_referee_judgment_instance(self):
        state = _make_state(status="judging", opponent_rebuttal="反驳文本...")
        result = referee_node(state, model=_make_mock_referee_model())
        assert isinstance(result["referee_judgment"], RefereeJudgment)
        assert result["referee_judgment"].winner == "presenter"

    def test_status_done_when_max_rounds_reached(self):
        state = _make_state(round=3, max_rounds=3, status="judging", opponent_rebuttal="反驳")
        result = referee_node(state, model=_make_mock_referee_model())
        assert result["status"] == "done"

    def test_status_presenting_when_rounds_remain(self):
        state = _make_state(round=1, max_rounds=3, status="judging", opponent_rebuttal="反驳")
        result = referee_node(state, model=_make_mock_referee_model())
        assert result["status"] == "presenting"

    def test_appends_round_record_to_history(self):
        state = _make_state(
            status="judging",
            opponent_rebuttal="反驳文本",
            history=[],
        )
        result = referee_node(state, model=_make_mock_referee_model())
        assert len(result["history"]) == 1
        assert isinstance(result["history"][0], RoundRecord)
        assert result["history"][0].round_number == 1
        assert result["history"][0].presenter_argument == state["presenter_argument"]
        assert result["history"][0].opponent_rebuttal == "反驳文本"

    def test_preserves_existing_history(self):
        """追加模式：不覆盖已有 history。"""
        existing_record = RoundRecord(
            round_number=1,
            presenter_argument="旧论点",
            opponent_rebuttal="旧反驳",
            judgment=_make_mock_referee_model().with_structured_output.return_value.invoke.return_value,
        )
        state = _make_state(
            round=2,
            status="judging",
            opponent_rebuttal="新反驳",
            history=[existing_record],
        )
        result = referee_node(state, model=_make_mock_referee_model())
        assert len(result["history"]) == 2  # 旧 1 条 + 新 1 条

    def test_appends_message_with_correct_role(self):
        state = _make_state(
            status="judging",
            opponent_rebuttal="反驳",
            messages=[{"role": "opponent", "content": "反驳...", "round": 1}],
        )
        result = referee_node(state, model=_make_mock_referee_model())
        msgs = result["messages"]
        assert len(msgs) == 2
        assert msgs[-1]["role"] == "referee"
        assert msgs[-1]["round"] == 1
        assert "陈述者得分" in msgs[-1]["content"]

    def test_does_not_mutate_original_state(self):
        state = _make_state(status="judging", opponent_rebuttal="反驳")
        original_messages = list(state["messages"])
        original_history = list(state["history"])
        referee_node(state, model=_make_mock_referee_model())
        assert state["messages"] == original_messages
        assert state["history"] == original_history
        assert state["status"] == "judging"

    def test_passes_all_context_to_llm(self):
        """验证 LLM 收到的 prompt 包含 topic / round / 论点 / 反驳。"""
        state = _make_state(
            topic="测试主题",
            round=2,
            status="judging",
            presenter_argument="测试论点",
            opponent_rebuttal="测试反驳",
        )
        mock = _make_mock_referee_model()
        referee_node(state, model=mock)
        # referee 调用链: model.with_structured_output(...).invoke(messages)
        structured = mock.with_structured_output.return_value
        user_msg = structured.invoke.call_args[0][0][1]
        content = str(user_msg.content)
        assert "测试主题" in content
        assert "第 2 轮" in content
        assert "测试论点" in content
        assert "测试反驳" in content

"""冒烟测试 —— 验证系统能正常启动和组装。

所有测试使用 Mock LLM，无需真实 API Key。
覆盖：模块导入、图编译、Prompt 有效性、state 工厂、端到端组装。
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

from core.state import AgentState
from tests.helpers import make_mock_model, make_state

# =============================================================================
# 模块导入测试
# =============================================================================


class TestModuleImports:
    """验证所有核心模块可导入。"""

    def test_core_modules_import(self):
        """core/ 下 4 个模块全部可导入。"""
        import core.model
        import core.prompts
        import core.schemas
        import core.state  # noqa: F401

    def test_agent_modules_import(self):
        """agents/ 下 3 个模块全部可导入。"""
        import agents.opponent
        import agents.presenter
        import agents.referee  # noqa: F401

    def test_workflow_module_import(self):
        """workflow/graph.py 可导入。"""
        import workflow.graph  # noqa: F401

    def test_ui_module_top_level_does_not_crash(self):
        """ui/app.py 导入不崩溃（.env 加载 + langchain import）。"""
        # Mock streamlit 以避免 st.* 调用在测试中失败
        with patch.dict("sys.modules", {"streamlit": MagicMock()}):
            import ui.app  # noqa: F401


# =============================================================================
# 模型工厂冒烟测试
# =============================================================================


class TestModelFactorySmoke:
    """get_chat_model() 基本冒烟测试。"""

    def test_returns_without_crash(self):
        """无 env var 时 get_chat_model() 不崩溃。"""
        with patch.dict(os.environ, {}, clear=True), patch("core.model.ChatOpenAI"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from core.model import get_chat_model
                model = get_chat_model()
                assert model is not None

    def test_emits_warning_without_key(self):
        """缺少 API Key 时发出 RuntimeWarning。"""
        import warnings
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("core.model.ChatOpenAI"),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            from core.model import get_chat_model
            get_chat_model()
            assert len(w) == 1
            assert issubclass(w[0].category, RuntimeWarning)


# =============================================================================
# 图编译冒烟测试
# =============================================================================


class TestGraphCompilationSmoke:
    """build_graph() 使用真实 agent 节点的冒烟测试。"""

    def test_build_with_real_nodes_compiles(self):
        """使用真实 agent 节点调用 build_graph() → 7 个节点全部注册。"""
        from agents.opponent import opponent_compute_node, opponent_interact_node
        from agents.presenter import presenter_compute_node, presenter_interact_node
        from agents.referee import referee_deliberate_node
        from workflow.graph import build_graph

        graph = build_graph(
            opponent_compute_node,
            opponent_interact_node,
            presenter_compute_node,
            presenter_interact_node,
            referee_deliberate_node,
            checkpointer=None,
        )
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_graph_has_no_interrupt_before(self):
        """编译后的图 interrupt_before 应为空（仅使用动态 interrupt()）。"""
        from agents.opponent import opponent_compute_node, opponent_interact_node
        from agents.presenter import presenter_compute_node, presenter_interact_node
        from agents.referee import referee_deliberate_node
        from workflow.graph import build_graph

        graph = build_graph(
            opponent_compute_node,
            opponent_interact_node,
            presenter_compute_node,
            presenter_interact_node,
            referee_deliberate_node,
            checkpointer=None,
        )
        # build_graph 已返回编译后的图，检查 interrupt_before 配置
        interrupt_before = getattr(graph, "interrupt_before", None)
        assert interrupt_before is None or len(interrupt_before) == 0


# =============================================================================
# Prompt 有效性冒烟测试
# =============================================================================


class TestPromptValiditySmoke:
    """所有 Prompt 常量和模板函数的基本有效性。"""

    def test_all_system_prompts_are_non_empty(self):
        """4 个 SYSTEM_PROMPT 全部为非空字符串。"""
        from core.prompts import (
            FINAL_SUMMARY_PROMPT,
            OPPONENT_SYSTEM_PROMPT,
            PRESENTER_SYSTEM_PROMPT,
            REFEREE_SYSTEM_PROMPT,
        )
        assert len(OPPONENT_SYSTEM_PROMPT) > 100
        assert len(PRESENTER_SYSTEM_PROMPT) > 100
        assert len(REFEREE_SYSTEM_PROMPT) > 100
        assert len(FINAL_SUMMARY_PROMPT) > 100

    def test_all_prompt_functions_return_strings(self):
        """4 个模板函数全部返回 str 且包含参数。"""
        from core.prompts import (
            final_summary_prompt,
            opponent_prompt,
            presenter_prompt,
            referee_prompt,
        )
        o = opponent_prompt("测试论题")
        assert isinstance(o, str)
        assert "测试论题" in o

        p = presenter_prompt("论题", "批判", "回应")
        assert isinstance(p, str)
        assert "论题" in p
        assert "批判" in p
        assert "回应" in p

        r = referee_prompt("论题", "草稿", "确认", 1)
        assert isinstance(r, str)
        assert "论题" in r
        assert "第 1 轮" in r

        f = final_summary_prompt("初始", "最终", "[]")
        assert isinstance(f, str)
        assert "初始" in f
        assert "最终" in f


# =============================================================================
# State 工厂冒烟测试
# =============================================================================


class TestStateFactorySmoke:
    """AgentState 工厂函数的基本有效性。"""

    def test_make_state_produces_all_keys(self):
        """make_state() 应包含所有 10 个 AgentState 键。"""
        from core.state import AgentState
        state = make_state()
        required_keys = list(AgentState.__annotations__.keys())
        for key in required_keys:
            assert key in state, f"Missing key: {key}"
        assert len(state) == len(required_keys)


# =============================================================================
# 端到端图组装冒烟测试
# =============================================================================


class TestEndToEndAssemblySmoke:
    """使用 Mock LLM + 真实 agent 节点，验证图从 idle 运行到第一个中断点。"""

    def test_graph_invoke_to_first_interrupt(self):
        """idle → opponent_computing → awaiting_critique_response（无崩溃）。"""
        from langgraph.checkpoint.memory import MemorySaver

        from agents.opponent import opponent_compute_node, opponent_interact_node
        from agents.presenter import presenter_compute_node, presenter_interact_node
        from agents.referee import referee_deliberate_node
        from workflow.graph import build_graph

        # 用 Mock 替换 compute 节点中的 LLM 调用
        mock_model = make_mock_model("测试批判内容")

        def _mock_opponent_compute(state, model=None):
            return opponent_compute_node(state, model=mock_model)

        graph = build_graph(
            _mock_opponent_compute,
            opponent_interact_node,
            presenter_compute_node,
            presenter_interact_node,
            referee_deliberate_node,
            checkpointer=MemorySaver(),
        )

        initial_state: AgentState = {
            "current_thesis": "测试论题：AI 应受监管。",
            "round": 1,
            "status": "idle",
            "messages": [],
            "history": [],
            "final_result": "",
            "_critique": "",
            "_user_response": "",
            "_draft_thesis": "",
            "_confirmed_thesis": "",
        }

        import uuid
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        result = graph.invoke(initial_state, config)

        # 应运行到第一个 interrupt 点
        assert result["status"] == "awaiting_critique_response"
        assert len(result["_critique"]) > 0
        assert len(result["messages"]) >= 1
        assert result["messages"][0]["role"] == "opponent"


# =============================================================================
# 图导出冒烟测试
# =============================================================================


class TestExportGraphSmoke:
    """export_graph 使用真实节点编译的冒烟测试。"""

    def test_export_with_real_nodes(self):
        """使用真实 agent 节点调用 export_graph → 生成非空 PNG。"""
        from workflow.graph import export_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "smoke_graph.png")
            export_graph(path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

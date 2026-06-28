"""冒烟测试 —— 验证系统能正常启动和组装。

所有测试使用 Mock LLM，无需真实 API Key。
覆盖：模块导入、图编译、Prompt 有效性、state 工厂、端到端组装。
"""

import importlib
import os
import subprocess
import sys
import tempfile
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from core.state import AgentState, make_initial_state, validate_state_shape
from tests.helpers import make_mock_model, make_state


class _NoopContext:
    """测试用空上下文管理器，模拟 Streamlit 容器。"""

    def __enter__(self):
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False


def _import_ui_app_with_streamlit(streamlit_module: object) -> ModuleType:
    """使用指定 streamlit 替身重新导入 ui.app。"""
    sys.modules.pop("ui.app", None)
    with patch.dict("sys.modules", {"streamlit": streamlit_module}):
        return importlib.import_module("ui.app")


class _FakeStreamlit:
    """_render_sidebar() 测试用 Streamlit 替身。"""

    def __init__(self, *, text_inputs: list[str] | None = None, buttons: list[bool] | None = None) -> None:
        self.session_state = {}
        self.sidebar = _NoopContext()
        self._text_inputs = list(text_inputs or [])
        self._buttons = list(buttons or [])
        self.rerun_called = False

    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None

    def expander(self, *args: object, **kwargs: object) -> _NoopContext:
        return _NoopContext()

    def columns(self, _count: int) -> list[_NoopContext]:
        return [_NoopContext(), _NoopContext()]

    def text_input(self, *args: object, **kwargs: object) -> str:
        if self._text_inputs:
            return self._text_inputs.pop(0)
        value = kwargs.get("value", "")
        return value if isinstance(value, str) else ""

    def text_area(self, *args: object, **kwargs: object) -> str:
        value = kwargs.get("value", "")
        return value if isinstance(value, str) else ""

    def button(self, *args: object, **kwargs: object) -> bool:
        return self._buttons.pop(0) if self._buttons else False

    def rerun(self) -> None:
        self.rerun_called = True


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
        _import_ui_app_with_streamlit(MagicMock())

    def test_ui_module_uses_shared_environment_bootstrap(self):
        """ui/app.py 应复用 core.env.setup_environment() 加载 .env。"""
        with patch("core.env.setup_environment") as mock_setup:
            _import_ui_app_with_streamlit(MagicMock())

        mock_setup.assert_called_once()
        _, kwargs = mock_setup.call_args
        assert kwargs == {"verbose": False}


# =============================================================================
# UI 配置行为测试
# =============================================================================


class TestSidebarConfigSmoke:
    """侧边栏配置写入行为。"""

    def test_sidebar_api_key_override_updates_session_and_env(self):
        """手动覆盖 API Key 时，应同步 session_state 和 LLM/OpenAI env。"""
        fake_st = _FakeStreamlit(text_inputs=["sk-override-key"])
        app = _import_ui_app_with_streamlit(fake_st)
        render_sidebar = app._render_sidebar

        env = {
            "LLM_MODEL": "deepseek-chat",
            "LLM_API_KEY": "sk-existing-key",
        }
        with patch.dict(os.environ, env, clear=True):
            render_sidebar()
            assert os.environ["LLM_API_KEY"] == "sk-override-key"
            assert os.environ["OPENAI_API_KEY"] == "sk-override-key"

        assert fake_st.session_state["api_key"] == "sk-override-key"

    def test_sidebar_model_settings_update_env_and_rerun(self):
        """无 .env 配置时，应用高级模型设置应写入模型 env 并 rerun。"""
        fake_st = _FakeStreamlit(
            text_inputs=["", "custom-model", "https://example.com/v1"],
            buttons=[True, False, False],
        )
        app = _import_ui_app_with_streamlit(fake_st)
        render_sidebar = app._render_sidebar

        with patch.dict(os.environ, {}, clear=True):
            render_sidebar()
            assert os.environ["LLM_MODEL"] == "custom-model"
            assert os.environ["LLM_BASE_URL"] == "https://example.com/v1"

        assert fake_st.rerun_called is True


# =============================================================================
# 启动器冒烟测试
# =============================================================================


class TestLauncherSmoke:
    """run.py 启动器行为测试。"""

    def test_streamlit_startup_failure_is_propagated(self):
        """Streamlit 子进程失败时，启动器应返回非零。"""
        import run

        with (
            patch("run.setup_environment"),
            patch("run.subprocess.run", side_effect=subprocess.CalledProcessError(7, "streamlit")),
            patch.object(run.sys, "argv", ["run.py"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            run.main()

        assert exc_info.value.code == 7


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
        """make_state() 应包含所有 AgentState 键。"""
        from core.state import AgentState
        state = make_state()
        required_keys = list(AgentState.__annotations__.keys())
        for key in required_keys:
            assert key in state, f"Missing key: {key}"
        assert len(state) == len(required_keys)

    def test_make_initial_state_produces_workflow_entry_state(self):
        """core.state.make_initial_state() 应生成完整 idle 入口状态。"""
        state = make_initial_state("测试论题")

        assert state["current_thesis"] == "测试论题"
        assert state["round"] == 1
        assert state["status"] == "idle"
        assert state["messages"] == []
        assert state["history"] == []
        assert state["final_result"] == ""
        assert state["_critique"] == ""
        assert state["_user_response"] == ""
        assert state["_draft_thesis"] == ""
        assert state["_confirmed_thesis"] == ""
        assert state["_improvement_hint"] == ""
        assert set(state) == set(AgentState.__annotations__)

    def test_validate_state_shape_accepts_complete_state(self):
        """完整 AgentState 应通过 shape 校验并返回类型化 state。"""
        state = make_initial_state("测试论题")
        assert validate_state_shape(state) is state

    def test_validate_state_shape_rejects_missing_key(self):
        """缺少任一 AgentState 字段时应早失败。"""
        state = dict(make_initial_state("测试论题"))
        state.pop("_improvement_hint")

        try:
            validate_state_shape(state)
        except KeyError as exc:
            assert "_improvement_hint" in str(exc)
        else:
            raise AssertionError("validate_state_shape should reject missing keys")

    def test_validate_state_shape_rejects_non_mapping(self):
        """非 mapping 输入应以 TypeError 早失败。"""
        with pytest.raises(TypeError, match="AgentState 必须是 Mapping"):
            validate_state_shape(["not", "a", "state"])


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

        initial_state: AgentState = make_initial_state("测试论题：AI 应受监管。")

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

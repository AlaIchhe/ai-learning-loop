"""脚本契约测试 —— 验证诊断脚本与核心 schema 保持一致。"""

from unittest.mock import MagicMock, patch

from core.schemas import RefereeJudgment


class TestGhostProbeContracts:
    """ghost_probe.py 与核心数据契约的一致性。"""

    def test_structured_output_probe_accepts_current_referee_schema(self):
        """RefereeJudgment 不包含 round 字段时，结构化输出探针仍应通过。"""
        from scripts import ghost_probe

        mock_model = MagicMock()
        structured_model = MagicMock()
        structured_model.invoke.return_value = RefereeJudgment(
            continue_debate=True,
            new_thesis="AI 应在高风险领域接受监管。",
            reasoning="论题仍可继续细化监管边界。",
            improvement_hint="继续明确高风险领域的定义。",
        )
        mock_model.with_structured_output.return_value = structured_model

        with (
            patch.object(ghost_probe, "_has_api_key", return_value=True),
            patch("core.model.get_chat_model", return_value=mock_model),
        ):
            assert ghost_probe.probe_structured_output() is True

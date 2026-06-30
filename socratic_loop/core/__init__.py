"""契约层 —— 纯数据与纯函数，无副作用。

包含系统的核心数据契约（Pydantic 模型）、全局状态定义（TypedDict）
以及所有 Agent 的 LLM prompt 模板。

本包不依赖任何其他内部子包（infra/、agents/、workflow/），
是所有其他模块的根基。

公共 API:
    from socratic_loop.core import (
        AgentState, make_initial_state, validate_state_shape,
        RefereeJudgment, RoundRecord,
    )
"""

from socratic_loop.core.schemas import RefereeJudgment, RoundRecord
from socratic_loop.core.state import AgentState, make_initial_state, validate_state_shape

__all__ = [
    # —— 状态契约 ——
    "AgentState",
    "make_initial_state",
    "validate_state_shape",
    # —— 数据契约 ——
    "RefereeJudgment",
    "RoundRecord",
]

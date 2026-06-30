"""Socratic Learning Loop —— 基于 LangGraph 的三智能体苏格拉底式学习引导系统。

通过提问者（Opponent）、精确化者（Presenter）、裁判（Referee）三个 LLM 智能体
的迭代论题演化，帮助用户深化对任意话题的认知理解。

公共 API:
    from socratic_loop import AgentState, make_initial_state, RefereeJudgment, RoundRecord
"""

from socratic_loop.core.schemas import RefereeJudgment, RoundRecord
from socratic_loop.core.state import AgentState, make_initial_state, validate_state_shape

__all__ = [
    "AgentState",
    "make_initial_state",
    "validate_state_shape",
    "RefereeJudgment",
    "RoundRecord",
]

__version__ = "1.0.0"

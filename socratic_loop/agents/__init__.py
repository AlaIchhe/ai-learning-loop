"""LLM 节点函数 —— compute/interact 拆分的三智能体节点。

每个含 interrupt() 的智能体被拆分为 compute（LLM 调用）+ interact（人工 I/O）
两个节点，避免 resume 时重复执行 LLM。

公共 API:
    from socratic_loop.agents import (
        opponent_compute_node, opponent_interact_node,
        presenter_compute_node, presenter_interact_node,
        referee_deliberate_node,
    )
"""

from socratic_loop.agents.opponent import opponent_compute_node, opponent_interact_node
from socratic_loop.agents.presenter import presenter_compute_node, presenter_interact_node
from socratic_loop.agents.referee import referee_deliberate_node

__all__ = [
    # —— 提问者（批判者）——
    "opponent_compute_node",
    "opponent_interact_node",
    # —— 精确化者 ——
    "presenter_compute_node",
    "presenter_interact_node",
    # —— 裁判 ——
    "referee_deliberate_node",
]

"""
LangGraph 编排层 —— 纯粹的流转调度。

原则：
1. 图中不包含任何 LLM 调用逻辑，只做状态路由和调度。
2. 所有 LLM 逻辑封装在 agents/ 的节点函数中。
3. 断点（interrupt_before）使每一步都可在 UI 层暂停，实现人机协作。
4. 条件边（Conditional Edge）根据 state["status"] 决定下一步流向。

图结构：
    START
      │
  ┌─ presenter ──→ opponent ──→ referee ──┐
  │                                        │
  └──── next_round ←─── [route] ←──────────┘
                          │
                          └── "done" → END
"""

from langgraph.graph import StateGraph, END

from core.state import AgentState


# =============================================================================
# 纯调度节点（无 LLM 逻辑）
# =============================================================================


def _start_node(state: AgentState) -> dict:
    """初始化节点：将 idle 状态转为 presenting，触发首轮陈述。

    该节点仅在入口调用一次，用于状态机启动。
    """
    return {"status": "presenting"}


def _next_round_node(state: AgentState) -> dict:
    """轮次推进节点：round+1，清空本轮缓存，准备下一轮辩论。

    这是纯调度逻辑，不涉及任何 LLM。
    """
    return {
        "round": state["round"] + 1,
        "presenter_argument": "",
        "opponent_rebuttal": "",
        "referee_judgment": None,
    }


# =============================================================================
# 条件路由
# =============================================================================


def _route_after_referee(state: AgentState) -> str:
    """裁判评分后的条件路由。

    依据 state["status"] 判定：
    - "done"    → 辩论结束，流向 END
    - 其他状态  → 继续下一轮，流向 _next_round_node
    """
    if state["status"] == "done":
        return END
    return "next_round"


# =============================================================================
# 图构建
# =============================================================================


def build_graph(
    presenter_node,
    opponent_node,
    referee_node,
    interrupt_before: list[str] | None = None,
) -> StateGraph:
    """组装 LangGraph 状态图。

    所有 LLM 节点以依赖注入方式传入，图本身只负责编排。
    这使得图与具体的 LLM 实现完全解耦，便于测试和替换。

    Args:
        presenter_node: 陈述者节点函数 (AgentState) → dict
        opponent_node:  反驳者节点函数 (AgentState) → dict
        referee_node:   裁判节点函数 (AgentState) → dict
        interrupt_before: 需要暂停的节点列表。
                          默认在 presenter / opponent / referee 前全部暂停，
                          以便 UI 层逐步展示辩论过程。

    Returns:
        编译后的 LangGraph StateGraph，可直接在 Streamlit 等 UI 中调用。
    """
    if interrupt_before is None:
        interrupt_before = ["presenter", "opponent", "referee"]

    # 创建状态图
    workflow = StateGraph(AgentState)

    # 注册所有节点
    workflow.add_node("start", _start_node)
    workflow.add_node("presenter", presenter_node)
    workflow.add_node("opponent", opponent_node)
    workflow.add_node("referee", referee_node)
    workflow.add_node("next_round", _next_round_node)

    # 固定边
    workflow.set_entry_point("start")
    workflow.add_edge("start", "presenter")
    workflow.add_edge("presenter", "opponent")
    workflow.add_edge("opponent", "referee")

    # 裁判后的条件边
    workflow.add_conditional_edges(
        "referee",
        _route_after_referee,
        {
            END: END,
            "next_round": "next_round",
        },
    )

    # 下一轮 → 陈述者（形成循环）
    workflow.add_edge("next_round", "presenter")

    # 编译图，配置断点
    return workflow.compile(interrupt_before=interrupt_before)

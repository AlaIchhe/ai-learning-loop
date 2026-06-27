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

from collections.abc import Callable
from pathlib import Path

from langgraph.graph import END, StateGraph

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
    presenter_node: Callable[[AgentState], dict],
    opponent_node: Callable[[AgentState], dict],
    referee_node: Callable[[AgentState], dict],
    interrupt_before: list[str] | None = None,
    checkpointer=None,
):
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
        checkpointer:   LangGraph checkpointer 实例（如 MemorySaver）。
                        必须传入才能支持 interrupt_before 暂停/恢复和 get_state()。
                        未传入时，图仍可运行但中断和状态查询不可用。

    Returns:
        编译后的 CompiledStateGraph。
    """
    if interrupt_before is None:
        interrupt_before = ["presenter", "opponent", "referee"]

    # 创建状态图
    workflow = StateGraph(AgentState)

    # 注册所有节点
    # type: ignore 是因为 LangGraph 的类型桩要求 position-only 的 state 参数，
    # 但 Python 函数使用常规参数 —— 运行时完全兼容。
    workflow.add_node("start", _start_node)
    workflow.add_node("presenter", presenter_node)  # type: ignore[arg-type]
    workflow.add_node("opponent", opponent_node)  # type: ignore[arg-type]
    workflow.add_node("referee", referee_node)  # type: ignore[arg-type]
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

    # 编译图，配置断点和 checkpointer
    return workflow.compile(
        interrupt_before=interrupt_before,
        checkpointer=checkpointer,
    )


# =============================================================================
# 图结构导出（可通过 python -m workflow.graph 或 debate-graph 入口调用）
# =============================================================================


def export_graph(output_filename: str = "graph_architecture.png") -> Path:
    """导出当前 LangGraph 架构图为 PNG 文件。

    Args:
        output_filename: 输出文件名（默认 graph_architecture.png）。

    Returns:
        输出文件的绝对路径。
    """
    from agents.opponent import opponent_node
    from agents.presenter import presenter_node
    from agents.referee import referee_node

    graph = build_graph(presenter_node, opponent_node, referee_node)
    png_data = graph.get_graph().draw_mermaid_png()

    root_dir = Path(__file__).resolve().parent.parent
    output_path = root_dir / output_filename
    output_path.write_bytes(png_data)

    print(f"图结构已导出: {output_path} ({len(png_data):,} bytes)")
    return output_path


if __name__ == "__main__":
    export_graph()

"""
系统全局状态定义 —— 唯一的 TypedDict，所有模块共享此契约。

LangGraph 要求状态可序列化，因此字段类型限定为：
- 基础类型 (str, int, bool, float)
- 标准容器 (list, dict)
- Pydantic BaseModel（运行时会转为 dict）

状态分为两类：
1. 持久字段：跨轮次保留，跟踪论题演化全程
2. 轮次缓存字段（_ 前缀）：仅当前轮次有效，由 next_round 节点清空
"""

from collections.abc import Mapping
from typing import Literal, TypedDict, cast

from core.schemas import RoundRecord


class AgentState(TypedDict):
    """多智能体论题演化系统的全局状态。

    核心概念：current_thesis 是唯一需要持续维护的状态。
    每一轮辩论的目标是批判、精确化和拼合论题，使其逐步演化。

    所有 LangGraph 节点读取此 state 的字段，
    并通过返回 dict 来执行部分更新（仅更新变更字段）。
    """

    # === 核心论题（唯一跨轮次演化的内容） ===
    current_thesis: str
    """当前轮次的论题。由用户在首轮输入，后续由 Referee 拼合更新。"""

    # === 轮次控制 ===
    round: int
    """当前轮次编号（从 1 开始）。"""

    agent_temperature: float
    """Opponent 和 Presenter 的 LLM 温度（0.0-1.5）。Referee 始终使用 0.0。"""

    status: Literal[
        "idle",
        "opponent_computing",
        "awaiting_critique_response",
        "presenter_computing",
        "awaiting_thesis_confirmation",
        "referee_deliberating",
        "done",
    ]
    """当前工作流阶段。
    - idle:                           初始状态，等待开始
    - opponent_computing:             Opponent 正在 LLM 生成批判
    - awaiting_critique_response:     interrupt() 激活，等待用户回应批判
    - presenter_computing:            Presenter 正在 LLM 精确化表述
    - awaiting_thesis_confirmation:   interrupt() 激活，等待用户确认论题
    - referee_deliberating:           Referee 正在拼合论题并判定
    - done:                           论题已足够完善，辩论结束
    """

    # === 对话历史 ===
    messages: list[dict[str, object]]
    """全局消息列表。每条消息为 dict，包含 role / content / round 等字段。
    节点通过返回 {'messages': state['messages'] + [new_msg]} 来追加。
    角色包括：opponent / user / presenter / referee。"""

    # === 历史轮次归档 ===
    history: list[RoundRecord]
    """已完成的所有轮次记录，按 round 升序排列。
    每个元素为 RoundRecord（Pydantic 模型，序列化为 dict）。"""

    # === 最终汇总 ===
    final_result: str
    """辩论结束后的总结报告（纯文本）。"""

    # === 轮次缓存（_ 前缀：每轮清空，不跨轮持久） ===

    _critique: str
    """[轮次缓存] Opponent 生成的批判文本。
    由 opponent_compute 写入，opponent_interact 读取后通过 interrupt() 展示。"""

    _user_response: str
    """[轮次缓存] 用户对批判的回应。
    由 opponent_interact 在 resume 后写入，presenter_compute 读取。"""

    _draft_thesis: str
    """[轮次缓存] Presenter 精确化后的论题草稿。
    由 presenter_compute 写入，presenter_interact 读取后通过 interrupt() 展示。"""

    _confirmed_thesis: str
    """[轮次缓存] 用户确认（可能编辑）后的论题。
    由 presenter_interact 在 resume 后写入，referee_deliberate 读取。"""

    _improvement_hint: str
    """[轮次缓存] 裁判对下一轮批判方向的指引。
    由 referee_deliberate 写入（来自 RefereeJudgment.improvement_hint），
    opponent_compute 读取后传入 opponent_prompt()，由 _next_round_node 清除。"""

    _model_name: str
    """[持久] Per-tab 模型名覆盖。在辩论启动时从侧边栏/ModelStore 捕获，
    优先级高于全局环境变量。由 make_initial_state() 注入，agent compute 节点
    读取后传给 get_chat_model()。空串表示回退到全局配置。"""

    _model_base_url: str
    """[持久] Per-tab 模型端点覆盖。空串表示回退到全局配置。"""

    _model_api_key: str
    """[持久] Per-tab API Key 覆盖。空串表示回退到全局配置。
    与 _model_name/_model_base_url 一起在辩论启动时冻结，实现真正的 per-tab 隔离。"""

    _model_json_mode: bool
    """[持久] Per-tab 是否对 Referee 使用 JSON-mode。
    由 ModelProfile.supports_structured_output 取反冻结。
    DeepSeek 等不支持 with_structured_output 的提供商自动启用。"""

    max_rounds: int
    """[持久] 最大轮次安全阀。达到此轮次后 _route_after_referee 强制终止辩论。
    由 make_initial_state() 在辩论启动时从侧边栏捕获，默认 10。"""


def validate_state_shape(state: object) -> AgentState:
    """校验 state 包含 AgentState 定义的所有字段。

    这是轻量运行时护栏：只校验字段存在性，不做深层类型验证。
    """
    if not isinstance(state, Mapping):
        raise TypeError(f"AgentState 必须是 Mapping，实际: {type(state).__name__}")

    missing = set(AgentState.__annotations__) - set(state)
    if missing:
        missing_keys = ", ".join(sorted(missing))
        raise KeyError(f"AgentState 缺少字段: {missing_keys}")
    return cast(AgentState, state)


def make_initial_state(
    thesis: str,
    *,
    agent_temperature: float = 0.7,
    model_name: str = "",
    model_base_url: str = "",
    model_api_key: str = "",
    model_json_mode: bool = False,
    max_rounds: int = 10,
) -> AgentState:
    """构造工作流入口使用的完整初始 AgentState。

    所有入口（UI、脚本、测试）都应复用此工厂，避免手写 dict 漂移。

    Args:
        thesis: 初始论题文本。
        agent_temperature: Opponent/Presenter 的 LLM 温度。
        model_name: Per-tab 模型名覆盖（空串 = 使用全局环境变量）。
        model_base_url: Per-tab 端点覆盖（空串 = 使用全局环境变量）。
        model_api_key: Per-tab API Key 覆盖（空串 = 使用全局环境变量）。
        model_json_mode: Per-tab 是否强制 Referee 使用 JSON-mode。
        max_rounds: 最大轮次安全阀（默认 10）。
    """
    return cast(AgentState, {
        "current_thesis": thesis,
        "round": 1,
        "agent_temperature": agent_temperature,
        "status": "idle",
        "messages": [],
        "history": [],
        "final_result": "",
        "_critique": "",
        "_user_response": "",
        "_draft_thesis": "",
        "_confirmed_thesis": "",
        "_improvement_hint": "",
        "_model_name": model_name,
        "_model_base_url": model_base_url,
        "_model_api_key": model_api_key,
        "_model_json_mode": model_json_mode,
        "max_rounds": max_rounds,
    })


#: LangGraph 节点函数的返回类型 —— 部分状态更新字典。
#: 值类型为 object 因为各节点返回不同字段组合（str / int / Pydantic 模型 / list / None）。
NodeOutput = dict[str, object]

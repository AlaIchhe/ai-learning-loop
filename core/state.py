"""
系统全局状态定义 —— 唯一的 TypedDict，所有模块共享此契约。

LangGraph 要求状态可序列化，因此字段类型限定为：
- 基础类型 (str, int, bool, float)
- 标准容器 (list, dict)
- Pydantic BaseModel（运行时会转为 dict）
"""

from typing import TypedDict, Literal
from core.schemas import RoundRecord, RefereeJudgment


class AgentState(TypedDict):
    """多智能体辩论学习系统的全局状态。

    所有 LangGraph 节点读取此 state 的字段，
    并通过返回 dict 来执行部分更新（仅更新变更字段）。

    注意：messages 使用普通 list（非 add_messages reducer），
    因为我们使用了自定义角色（presenter/opponent/referee），
    这些角色不被 LangChain 标准消息类型所接受。
    各节点通过返回新的 messages 列表来实现追加。
    """

    # === 会话标识 ===
    topic: str
    """本轮辩论的主题/问题，由用户在 UI 层输入，进入 workflow 后不可变。"""

    # === 轮次控制 ===
    round: int
    """当前轮次编号（从 1 开始）。"""

    max_rounds: int
    """最大辩论轮次，默认为 3。裁判裁决后若 round >= max_rounds 则结束。"""

    status: Literal["idle", "presenting", "opposing", "judging", "done"]
    """当前工作流阶段。
    - idle:      初始状态，等待开始
    - presenting: 陈述者正在生成论点
    - opposing:   反驳者正在生成反驳
    - judging:    裁判正在评分
    - done:       辩论结束
    """

    # === 对话历史 ===
    messages: list[dict]
    """全局消息列表。每条消息为 dict，包含 role / content / round 等字段。
    节点通过返回 {'messages': state['messages'] + [new_msg]} 来追加。
    使用普通 list 的原因：LangChain add_messages 仅接受
    human/ai/system/tool 等标准角色，而我们自定义了 presenter/opponent/referee。"""

    # === 当前轮次缓存 ===
    presenter_argument: str
    """陈述者本轮生成的论点文本。"""

    opponent_rebuttal: str
    """反驳者本轮生成的反驳文本。"""

    referee_judgment: RefereeJudgment | None
    """裁判本轮的结构化评分结果（Pydantic 模型，运行时序列化为 dict）。"""

    # === 历史轮次归档 ===
    history: list[RoundRecord]
    """已完成的所有轮次记录，按 round 升序排列。
    每个元素为 RoundRecord（Pydantic 模型，序列化为 dict）。"""

    # === 最终汇总 ===
    final_result: str
    """辩论结束后的总结报告（纯文本，由裁判在最后一轮后生成）。"""

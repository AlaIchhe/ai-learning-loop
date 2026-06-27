"""
Pydantic 结构化输出模型 —— 系统的数据契约。

原则：
1. 所有模型继承 BaseModel，LangGraph 状态中自动序列化为 dict。
2. 字段使用严格类型标注，不允许多余字段（model_config 禁止 extra）。
3. 裁判输出（RefereeJudgment）是核心契约，不得被其他模块随意扩展。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# =============================================================================
# 消息模型
# =============================================================================


class Message(BaseModel):
    """单条会话消息。"""

    role: Literal["system", "presenter", "opponent", "referee", "user"]
    """消息发送方角色。user 用于标记用户在中继点输入的内容。"""

    content: str = Field(min_length=1)
    """消息正文，不可为空。"""

    round: int = Field(ge=1)
    """所属辩论轮次。"""

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    """消息时间戳（ISO 8601 格式），默认创建时自动生成。"""


# =============================================================================
# 裁判输出（核心契约）
# =============================================================================


class RefereeJudgment(BaseModel):
    """裁判对一轮论题演化的结构化判定。

    这是系统的核心契约 —— agents/referee.py 的 LLM 调用
    必须返回符合此 schema 的 JSON 输出。
    """

    round: int = Field(ge=1, description="判定对应的轮次编号")

    continue_debate: bool = Field(
        description="是否继续下一轮辩论。True = 论题仍需打磨，False = 论题已足够完善。"
    )

    new_thesis: str = Field(
        min_length=1,
        description="裁判将当前论题、草稿和确认版拼合后的新 current_thesis。",
    )

    reasoning: str = Field(min_length=1, description="判定理由，说明为何继续或结束。")

    improvement_hint: str = Field(
        default="",
        description="下一轮的改进方向，或对最终论题的肯定评价。",
    )


# =============================================================================
# 轮次 & 结果归档
# =============================================================================


class RoundRecord(BaseModel):
    """单轮论题演化的完整归档（存入 history 列表）。"""

    round_number: int = Field(ge=1)

    thesis_before: str = Field(min_length=1, description="本轮开始时的 current_thesis")
    critique: str = Field(min_length=1, description="Opponent 的批判文本")
    user_response: str = Field(min_length=1, description="用户对批判的回应")
    draft_thesis: str = Field(min_length=1, description="Presenter 精确化后的草稿")
    confirmed_thesis: str = Field(min_length=1, description="用户确认后的论题")
    thesis_after: str = Field(min_length=1, description="Referee 拼合后的新 current_thesis")

    continue_debate: bool = Field(description="裁判是否决定继续下一轮")
    referee_reasoning: str = Field(min_length=1, description="裁判的判定理由")

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class DebateResult(BaseModel):
    """整场辩论的最终汇总。"""

    initial_thesis: str = Field(min_length=1, description="用户最初提出的论题")
    final_thesis: str = Field(min_length=1, description="辩论结束时的最终论题")
    total_rounds: int = Field(ge=0, description="总轮次数")

    rounds: list[RoundRecord] = Field(default_factory=list)
    summary: str = Field(min_length=1, description="最终总结报告")

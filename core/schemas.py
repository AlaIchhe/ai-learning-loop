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

    role: Literal["system", "presenter", "opponent", "referee"]
    """消息发送方角色。"""

    content: str = Field(min_length=1)
    """消息正文，不可为空。"""

    round: int = Field(ge=1)
    """所属辩论轮次。"""

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    """消息时间戳（ISO 8601 格式），默认创建时自动生成。"""


# =============================================================================
# 裁判输出（核心契约）
# =============================================================================


class CategoryScores(BaseModel):
    """各维度的独立评分。"""

    clarity: float = Field(ge=0.0, le=10.0, description="论点清晰度 (0-10)")
    logic: float = Field(ge=0.0, le=10.0, description="逻辑严谨性 (0-10)")
    evidence: float = Field(ge=0.0, le=10.0, description="论据充分性 (0-10)")
    persuasiveness: float = Field(ge=0.0, le=10.0, description="说服力 (0-10)")


class RefereeJudgment(BaseModel):
    """裁判对一轮辩论的结构化评判。

    这是系统的核心契约 —— agents/referee.py 的 LLM 调用
    必须返回符合此 schema 的 JSON 输出。
    """

    round: int = Field(ge=1, description="评判对应的轮次编号")

    presenter_score: CategoryScores
    """陈述者的各维度得分。"""

    opponent_score: CategoryScores
    """反驳者的各维度得分。"""

    presenter_total: float = Field(ge=0.0, le=10.0, description="陈述者综合得分")
    opponent_total: float = Field(ge=0.0, le=10.0, description="反驳者综合得分")

    winner: Literal["presenter", "opponent", "draw"]
    """本轮胜者。"""

    reasoning: str = Field(min_length=1, description="裁判的评分理由，至少 20 字")

    presenter_strength: str = Field(default="", description="陈述者本轮亮点")
    presenter_weakness: str = Field(default="", description="陈述者本轮不足")

    opponent_strength: str = Field(default="", description="反驳者本轮亮点")
    opponent_weakness: str = Field(default="", description="反驳者本轮不足")

    improvement_hint: str = Field(default="", description="给双方的改进建议")


# =============================================================================
# 轮次 & 结果归档
# =============================================================================


class RoundRecord(BaseModel):
    """单轮辩论的完整归档（存入 history 列表）。"""

    round_number: int = Field(ge=1)

    presenter_argument: str = Field(min_length=1)
    opponent_rebuttal: str = Field(min_length=1)
    judgment: RefereeJudgment
    """本轮裁判的完整结构化评分。"""

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class DebateResult(BaseModel):
    """整场辩论的最终汇总。"""

    topic: str
    total_rounds: int

    winner: Literal["presenter", "opponent", "draw"]
    presenter_wins: int = Field(ge=0, description="陈述者获胜轮次数")
    opponent_wins: int = Field(ge=0, description="反驳者获胜轮次数")
    draws: int = Field(ge=0, description="平局轮次数")

    rounds: list[RoundRecord]
    summary: str = Field(min_length=1, description="最终总结报告")

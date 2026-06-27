"""
裁判节点 —— 无状态纯函数。

职责：
1. 读取 state 中本轮 presenter_argument 和 opponent_rebuttal。
2. 使用结构化输出调用 LLM，强制输出符合 RefereeJudgment schema 的 JSON。
3. 将本轮归档为 RoundRecord 追加到 history。
4. 判定是否继续下一轮或结束辩论。

契约：
- 输入：完整的 AgentState（TypedDict）
- 输出：dict，仅包含需要更新的字段
- 不修改 state 本身，不产生副作用
- referee_judgment 字段为 RefereeJudgment 实例（Pydantic 模型）
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from core.state import AgentState
from core.schemas import RefereeJudgment, RoundRecord
from core.prompts import REFEREE_SYSTEM_PROMPT, referee_prompt
from core.model import get_chat_model


def referee_node(state: AgentState, model: ChatOpenAI | None = None) -> dict:
    """裁判节点：对一轮辩论进行结构化评分。

    使用 with_structured_output 确保 LLM 输出严格符合 RefereeJudgment schema。
    评分后将本轮归档为 RoundRecord，并判定是否进入下一轮或结束。

    Args:
        state: 全局 AgentState，至少需包含 topic / round / max_rounds /
               presenter_argument / opponent_rebuttal / messages / history。
        model: 可注入的 LLM 实例。默认通过 get_chat_model() 从环境变量读取
               配置（支持 OpenAI / DeepSeek / 其他兼容供应商）。测试时传入 Mock。

    Returns:
        dict，包含以下键：
        - referee_judgment: RefereeJudgment  结构化评分结果
        - messages: list[dict]               追加了裁判消息的完整消息列表
        - history: list[RoundRecord]         追加了本轮归档的历史列表
        - status: "presenting" | "done"      下一轮或结束
    """
    if model is None:
        model = get_chat_model(temperature=0.0)

    # 结构化输出：绑定 RefereeJudgment schema
    structured_model = model.with_structured_output(RefereeJudgment)

    # 组装消息
    system_msg = SystemMessage(content=REFEREE_SYSTEM_PROMPT)
    user_msg = HumanMessage(
        content=referee_prompt(
            topic=state["topic"],
            round_num=state["round"],
            presenter_argument=state["presenter_argument"],
            opponent_rebuttal=state["opponent_rebuttal"],
        )
    )

    # 调用 LLM（返回 RefereeJudgment 实例）
    raw = structured_model.invoke([system_msg, user_msg])
    judgment = raw if isinstance(raw, RefereeJudgment) else RefereeJudgment(**raw)
    # 确保 round 字段与 state 一致（防御性修正）
    judgment.round = state["round"]

    # 构造裁判消息
    new_msg = {
        "role": "referee",
        "content": (
            f"【第 {judgment.round} 轮裁决】\n"
            f"陈述者得分: {judgment.presenter_total}/10 | "
            f"反驳者得分: {judgment.opponent_total}/10\n"
            f"胜者: {judgment.winner}\n"
            f"理由: {judgment.reasoning}\n"
            f"改进建议: {judgment.improvement_hint}"
        ),
        "round": state["round"],
    }

    # 本轮归档
    round_record = RoundRecord(
        round_number=state["round"],
        presenter_argument=state["presenter_argument"],
        opponent_rebuttal=state["opponent_rebuttal"],
        judgment=judgment,
    )

    # 判定下一状态
    next_status = "done" if state["round"] >= state["max_rounds"] else "presenting"

    return {
        "referee_judgment": judgment,
        "messages": state["messages"] + [new_msg],
        "history": state["history"] + [round_record],
        "status": next_status,
    }

"""
反驳者节点 —— 无状态纯函数。

职责：
1. 读取 state 中的 topic 和 presenter_argument。
2. 调用 LLM 生成系统性反驳。
3. 返回部分状态更新（opponent_rebuttal / messages / status）。

契约：
- 输入：完整的 AgentState（TypedDict）
- 输出：dict，仅包含需要更新的字段
- 不修改 state 本身，不产生副作用
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from core.state import AgentState
from core.prompts import OPPONENT_SYSTEM_PROMPT, opponent_prompt
from core.model import get_chat_model


def opponent_node(state: AgentState, model: ChatOpenAI | None = None) -> dict:
    """反驳者节点：针对陈述者论点生成反驳。

    Args:
        state: 全局 AgentState，至少需包含 topic / presenter_argument / messages / round。
        model: 可注入的 LLM 实例。默认通过 get_chat_model() 从环境变量读取
               配置（支持 OpenAI / DeepSeek / 其他兼容供应商）。测试时传入 Mock。

    Returns:
        dict，包含以下键：
        - opponent_rebuttal: str  反驳文本
        - messages: list[dict]    追加了反驳消息的完整消息列表
        - status: "judging"       状态转移至裁判阶段
    """
    if model is None:
        model = get_chat_model(temperature=0.7)

    # 组装消息
    system_msg = SystemMessage(content=OPPONENT_SYSTEM_PROMPT)
    user_msg = HumanMessage(
        content=opponent_prompt(
            topic=state["topic"],
            presenter_argument=state["presenter_argument"],
        )
    )

    # 调用 LLM
    response = model.invoke([system_msg, user_msg])
    content = response.content
    rebuttal = (content if isinstance(content, str) else str(content)).strip()

    # 构造新消息
    new_msg = {
        "role": "opponent",
        "content": rebuttal,
        "round": state["round"],
    }

    return {
        "opponent_rebuttal": rebuttal,
        "messages": state["messages"] + [new_msg],
        "status": "judging",
    }

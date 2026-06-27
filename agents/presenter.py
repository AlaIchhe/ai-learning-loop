"""
陈述者节点 —— 无状态纯函数。

职责：
1. 读取 state 中的 topic 和上一轮对手反驳（若有）。
2. 调用 LLM 生成有说服力的论点。
3. 返回部分状态更新（presenter_argument / messages / status）。

契约：
- 输入：完整的 AgentState（TypedDict）
- 输出：dict，仅包含需要更新的字段
- 不修改 state 本身，不产生副作用
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.model import get_chat_model
from core.prompts import PRESENTER_SYSTEM_PROMPT, presenter_prompt
from core.state import AgentState


def presenter_node(state: AgentState, model: ChatOpenAI | None = None) -> dict:
    """陈述者节点：围绕主题构建论点。

    第一轮时 opponent_previous 为空。
    后续轮次会传入上一轮反驳者的质疑，陈述者可据此调整论点。

    Args:
        state: 全局 AgentState，至少需包含 topic / messages / round。
        model: 可注入的 LLM 实例。默认通过 get_chat_model() 从环境变量读取
               配置（支持 OpenAI / DeepSeek / 其他兼容供应商）。测试时传入 Mock。

    Returns:
        dict，包含以下键：
        - presenter_argument: str  生成的论点文本
        - messages: list[dict]    追加了陈述消息的完整消息列表
        - status: "opposing"      状态转移至反驳阶段
    """
    if model is None:
        model = get_chat_model(temperature=0.7)

    # 定位上一轮反驳者的内容（第一轮为空）
    opponent_previous = ""
    for msg in reversed(state["messages"]):
        if msg.get("role") == "opponent":
            opponent_previous = str(msg["content"])
            break

    # 组装消息
    system_msg = SystemMessage(content=PRESENTER_SYSTEM_PROMPT)
    user_msg = HumanMessage(
        content=presenter_prompt(
            topic=state["topic"],
            opponent_previous=opponent_previous,
        )
    )

    # 调用 LLM
    response = model.invoke([system_msg, user_msg])
    content = response.content
    argument = (content if isinstance(content, str) else str(content)).strip()

    # 构造新消息
    new_msg = {
        "role": "presenter",
        "content": argument,
        "round": state["round"],
    }

    return {
        "presenter_argument": argument,
        "messages": state["messages"] + [new_msg],
        "status": "opposing",
    }

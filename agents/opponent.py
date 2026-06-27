"""
Opponent 节点 —— 批判者（分为 compute + interact 两个节点）。

职责：
1. opponent_compute_node: 读取 current_thesis，调用 LLM 生成批判。
2. opponent_interact_node: 将批判通过 interrupt() 展示给用户，收取回应。

拆分原因：LangGraph 的 interrupt() 在 resume 时会整节点重新执行。
将 LLM 调用放在 compute 节点中可避免 resume 时重复调用 LLM。

契约：
- 输入：完整的 AgentState（TypedDict）
- 输出：dict，仅包含需要更新的字段
- 不修改 state 本身，不产生副作用
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt

from core.model import get_chat_model
from core.prompts import OPPONENT_SYSTEM_PROMPT, opponent_prompt
from core.state import AgentState


def opponent_compute_node(
    state: AgentState, model: ChatOpenAI | None = None
) -> dict:
    """批判者计算节点：对 current_thesis 生成批判。

    Args:
        state: 全局 AgentState，至少需包含 current_thesis / round / messages。
        model: 可注入的 LLM 实例。默认通过 get_chat_model() 从环境变量读取。

    Returns:
        dict，包含以下键：
        - _critique: str               LLM 生成的批判文本
        - messages: list[dict]         追加了 opponent 消息的列表
        - status: "awaiting_critique_response"
    """
    if model is None:
        model = get_chat_model(temperature=0.7)

    system_msg = SystemMessage(content=OPPONENT_SYSTEM_PROMPT)
    user_msg = HumanMessage(
        content=opponent_prompt(current_thesis=state["current_thesis"])
    )

    response = model.invoke([system_msg, user_msg])
    content = response.content
    critique = (content if isinstance(content, str) else str(content)).strip()

    new_msg: dict[str, object] = {
        "role": "opponent",
        "content": critique,
        "round": state["round"],
    }

    return {
        "_critique": critique,
        "messages": state["messages"] + [new_msg],
        "status": "awaiting_critique_response",
    }


def opponent_interact_node(state: AgentState) -> dict:
    """批判者交互节点：展示批判并收取用户回应。

    此节点不含 LLM 调用，仅做两件事：
    1. 从 state 读取 _critique，通过 interrupt() 展示给用户
    2. resume 后将用户回应写入 _user_response

    resume 时 LangGraph 会重新执行本节点，但读取 _critique 是幂等的，
    interrupt() 在 resume 时返回 Command(resume=...) 的值，不会重复抛异常。

    Args:
        state: 全局 AgentState，至少需包含 _critique / round / messages。

    Returns:
        dict，包含以下键：
        - _user_response: str         用户对批判的回应
        - messages: list[dict]        追加了 user 消息的列表
        - status: "presenter_computing"
    """
    critique = state["_critique"]

    # interrupt() 首次调用抛出 GraphInterrupt 并暂停；
    # resume 时返回 Command(resume=...) 传回的用户输入。
    user_response = interrupt(critique)

    new_msg: dict[str, object] = {
        "role": "user",
        "content": user_response,
        "round": state["round"],
    }

    return {
        "_user_response": str(user_response),
        "messages": state["messages"] + [new_msg],
        "status": "presenter_computing",
    }

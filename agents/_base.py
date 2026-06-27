"""
Agent 节点共享基础工具 —— 消除 Compute/Interact 节点间的模板重复。

原则：
1. 只提取纯机械性重复（内容提取、消息构造、节点骨架），不引入不必要抽象。
2. 不对裁判节点强制套用模板 —— 其 with_structured_output + 双路径逻辑足够独特。
3. 所有函数无副作用，不访问全局状态。
"""

from collections.abc import Callable

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.model import get_chat_model
from core.state import AgentState

# =============================================================================
# 内容提取 & 消息构造（消除 3×/6× 重复）
# =============================================================================


def extract_content(response: BaseMessage) -> str:
    """从 LLM 响应中提取纯文本内容。

    兼容纯文本（response.content 为 str）和多模态（list[dict]）两种响应格式。
    """
    content = response.content
    return content if isinstance(content, str) else str(content)


def make_message(role: str, content: str, round_num: int) -> dict[str, object]:
    """构造符合 AgentState.messages 格式的消息字典。

    Args:
        role: 消息角色（opponent / presenter / referee / user）。
        content: 消息正文。
        round_num: 所属轮次编号。
    """
    return {"role": role, "content": content, "round": round_num}


# =============================================================================
# Compute 节点工厂（消除 Opponent/Presenter 间的 3× 模板重复）
# =============================================================================


def invoke_llm(
    model: ChatOpenAI | None,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """调用 LLM 并返回提取后的文本内容。

    封装 model 懒初始化 + SystemMessage/HumanMessage 构造 + invoke + 内容提取。

    Args:
        model: 可选的预注入模型（None 则从环境变量创建）。
        temperature: LLM 温度参数（0.0 = 确定性，0.7 = 创造性）。
        system_prompt: 系统提示。
        user_prompt: 用户提示。

    Returns:
        LLM 响应文本（已 strip）。
    """
    if model is None:
        model = get_chat_model(temperature=temperature)

    response = model.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return extract_content(response).strip()


# =============================================================================
# 类型别名
# =============================================================================

#: Agent 节点函数的类型签名。
NodeFunc = Callable[[AgentState], dict]

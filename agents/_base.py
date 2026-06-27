"""
Agent 节点共享基础工具 —— 消除 Compute/Interact 节点间的模板重复。

原则：
1. 只提取纯机械性重复（内容提取、消息构造、节点骨架），不引入不必要抽象。
2. 不对裁判节点强制套用模板 —— 其 with_structured_output + 双路径逻辑足够独特。
3. 所有函数无副作用，不访问全局状态。
"""

import logging
import time
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from core.model import get_chat_model
from core.state import AgentState

logger = logging.getLogger(__name__)

# =============================================================================
# LLM 调用重试配置
# =============================================================================

_MAX_RETRIES = 3
"""最大重试次数（含首次调用）。"""

_RETRY_BACKOFF_BASE = 1.0
"""指数退避基数（秒）：第 n 次重试等待 base * 2^(n-1) 秒。"""

_RETRYABLE_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
)
"""可重试的瞬时错误类型。"""


def _is_retryable(error: Exception) -> bool:
    """判断异常是否可重试（网络/超时问题，非逻辑/鉴权错误）。"""
    if isinstance(error, _RETRYABLE_ERRORS):
        return True
    # langchain / openai 的 RateLimitError, APITimeoutError 等
    error_name = type(error).__name__
    return any(
        keyword in error_name.lower()
        for keyword in ("timeout", "ratelimit", "connection", "apiconnection")
    )


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


def invoke_with_retry(
    invocable,  # BaseChatModel | structured model
    messages: list,
    *,
    label: str = "LLM",
) -> BaseMessage:
    """调用 invocable.invoke(messages)，失败时自动重试。

    对瞬时网络/超时/速率限制错误自动重试（最多 3 次，指数退避 1s/2s/4s）。

    Args:
        invocable: 可调用 .invoke(messages) 的对象（BaseChatModel 或 structured model）。
        messages: 消息列表。
        label: 日志标签（用于区分不同调用点）。

    Returns:
        invocable.invoke() 的原始返回值。

    Raises:
        最后一次尝试的异常（重试耗尽后）。
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return invocable.invoke(messages)
        except Exception as exc:
            last_error = exc
            if not _is_retryable(exc) or attempt == _MAX_RETRIES:
                raise
            wait = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(
                "%s 调用失败（第 %d/%d 次），%s 秒后重试: %s",
                label, attempt, _MAX_RETRIES, wait, exc,
            )
            time.sleep(wait)

    assert last_error is not None
    raise last_error


def invoke_llm(
    model: BaseChatModel | None,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """调用 LLM 并返回提取后的文本内容（含自动重试）。

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

    response = invoke_with_retry(
        model,
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ],
        label="LLM",
    )
    return extract_content(response).strip()


# =============================================================================
# 类型别名
# =============================================================================

#: Agent 节点函数的类型签名。
NodeFunc = Callable[[AgentState], dict]

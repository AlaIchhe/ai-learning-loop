"""
Agent 节点共享基础工具 —— 消除 Compute/Interact 节点间的模板重复。

原则：
1. 只提取纯机械性重复（内容提取、消息构造、节点骨架），不引入不必要抽象。
2. 不对裁判节点强制套用模板 —— 其 with_structured_output + 双路径逻辑足够独特。
3. 所有函数无副作用，不访问全局状态。
"""

import contextlib
import logging
import time
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from core.logging import TraceLogger
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

    返回的 dict 包含 timestamp 字段（float, time.time()），
    用于 UI 层在消息气泡底部显示时间。
    """
    return {
        "role": role,
        "content": content,
        "round": round_num,
        "timestamp": time.time(),
    }


# =============================================================================
# Compute 节点工厂（消除 Opponent/Presenter 间的 3× 模板重复）
# =============================================================================


def invoke_with_retry(
    invocable,  # BaseChatModel | structured model
    messages: list,
    *,
    label: str = "LLM",
    on_retry: Callable[[int, int, float, Exception], None] | None = None,
    trace: TraceLogger | None = None,
) -> BaseMessage:
    """调用 invocable.invoke(messages)，失败时自动重试。

    对瞬时网络/超时/速率限制错误自动重试（最多 3 次，指数退避 1s/2s/4s）。

    Args:
        invocable: 可调用 .invoke(messages) 的对象（BaseChatModel 或 structured model）。
        messages: 消息列表。
        label: 日志标签（用于区分不同调用点）。
        on_retry: 可选回调，签名 (attempt, max_retries, wait_seconds, exception) -> None。
                  在每次重试前调用，用于向 UI 层报告重试进度。
        trace: 可选的 TraceLogger，用于记录 LLM 调用耗时与结果。

    Returns:
        invocable.invoke() 的原始返回值。

    Raises:
        最后一次尝试的异常（重试耗尽后）。
    """
    retry_count = 0
    last_error: Exception | None = None

    # 记录 LLM 调用开始
    model_name = getattr(invocable, "model_name", "unknown")
    if trace:
        trace.llm_call_start(model=model_name, label=label)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = invocable.invoke(messages)
            if trace:
                trace.llm_call_end(success=True, retry_count=retry_count)
            return result
        except Exception as exc:
            last_error = exc
            retry_count += 1
            if not _is_retryable(exc) or attempt == _MAX_RETRIES:
                if trace:
                    trace.llm_call_end(
                        success=False,
                        retry_count=retry_count,
                        error=str(exc)[:200],
                    )
                raise
            wait = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(
                "%s 调用失败（第 %d/%d 次），%s 秒后重试: %s",
                label, attempt, _MAX_RETRIES, wait, exc,
            )
            if on_retry:
                with contextlib.suppress(Exception):
                    on_retry(attempt, _MAX_RETRIES, wait, exc)
            time.sleep(wait)

    assert last_error is not None
    if trace:
        trace.llm_call_end(success=False, retry_count=retry_count, error="unreachable")
    raise last_error


def invoke_llm(
    model: BaseChatModel | None,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
    *,
    on_retry: Callable[[int, int, float, Exception], None] | None = None,
    trace: TraceLogger | None = None,
    model_name: str | None = None,
    model_base_url: str | None = None,
    model_api_key: str | None = None,
) -> str:
    """调用 LLM 并返回提取后的文本内容（含自动重试）。

    封装 model 懒初始化 + SystemMessage/HumanMessage 构造 + invoke + 内容提取。

    Args:
        model: 可选的预注入模型（None 则从环境变量创建）。
        temperature: LLM 温度参数（0.0 = 确定性，0.7 = 创造性）。
        system_prompt: 系统提示。
        user_prompt: 用户提示。
        on_retry: 可选的重试进度回调。
        trace: 可选的 TraceLogger。
        model_name: 可选的模型名覆盖（per-tab 配置）。
        model_base_url: 可选的模型端点覆盖（per-tab 配置）。
        model_api_key: 可选的 API Key 覆盖（per-tab 配置）。空串等价于未传入。

    Returns:
        LLM 响应文本（已 strip）。
    """
    if model is None:
        model = get_chat_model(
            temperature=temperature,
            model_name=model_name,
            base_url=model_base_url,
            api_key=model_api_key,
        )

    response = invoke_with_retry(
        model,
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ],
        label="LLM",
        on_retry=on_retry,
        trace=trace,
    )
    return extract_content(response).strip()


# =============================================================================
# 类型别名
# =============================================================================

#: Agent 节点函数的类型签名。
NodeFunc = Callable[[AgentState], dict]

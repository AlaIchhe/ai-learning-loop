"""
模型工厂 —— 统一管理 LLM 实例的创建。

读取环境变量决定使用哪个模型供应商：
- 未设置 LLM_BASE_URL → 默认 OpenAI (gpt-4o)
- 设置了 LLM_BASE_URL → 使用对应供应商（如 DeepSeek）

Agent 节点通过 get_chat_model() 获取模型实例，
无需关心底层是 OpenAI 还是 DeepSeek。
"""

import os
import warnings

from langchain_openai import ChatOpenAI

#: 未配置 API Key 时使用的占位符值。
_PLACEHOLDER_API_KEY = "sk-not-configured"


def get_chat_model(temperature: float = 0.7) -> ChatOpenAI:
    """创建 ChatOpenAI 实例。

    通过环境变量切换供应商：

    OpenAI（默认）:
        LLM_MODEL=gpt-4o
        OPENAI_API_KEY=sk-...

    DeepSeek:
        LLM_MODEL=deepseek-chat
        LLM_BASE_URL=https://api.deepseek.com/v1
        LLM_API_KEY=sk-...

    其他 OpenAI 兼容供应商（如 Ollama、vLLM 等）同理。

    若未配置任何 API Key，会在标准错误流输出诊断信息，
    并将占位符传入 ChatOpenAI——真正调用 LLM 时才会因鉴权失败而报错。

    Args:
        temperature: 0.0 用于裁判（确定性评分），0.7 用于陈述者和反驳者。

    Returns:
        配置好的 ChatOpenAI 实例。
    """
    model_name = os.getenv("LLM_MODEL", "gpt-4o")
    base_url = os.getenv("LLM_BASE_URL") or None
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None

    if not api_key:
        warnings.warn(
            "未检测到 LLM_API_KEY 或 OPENAI_API_KEY 环境变量。"
            "请在项目根目录的 .env 文件中配置 API Key，"
            "或通过环境变量设置。示例：LLM_API_KEY=sk-your-key",
            RuntimeWarning,
            stacklevel=2,
        )
        api_key = _PLACEHOLDER_API_KEY

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        base_url=base_url,
        api_key=api_key,  # type: ignore[arg-type]  # langchain 类型桩使用 SecretStr
    )

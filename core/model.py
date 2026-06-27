"""
模型工厂 —— 统一管理 LLM 实例的创建。

读取环境变量决定使用哪个模型供应商：
- 未设置 LLM_BASE_URL → 默认 OpenAI (gpt-4o)
- 设置了 LLM_BASE_URL → 使用对应供应商（如 DeepSeek）

Agent 节点通过 get_chat_model() 获取模型实例，
无需关心底层是 OpenAI 还是 DeepSeek。
"""

import os
from langchain_openai import ChatOpenAI


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

    Args:
        temperature: 0.0 用于裁判（确定性评分），0.7 用于陈述者和反驳者。
    """
    model_name = os.getenv("LLM_MODEL", "gpt-4o")
    base_url = os.getenv("LLM_BASE_URL", None)
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None

    kwargs: dict = {"model": model_name, "temperature": temperature}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    else:
        # 未配置任何 API Key 时用占位符，避免 ChatOpenAI.__init__ 立即抛异常。
        # 真正调用 LLM 时才会因鉴权失败而报错。
        kwargs["api_key"] = "sk-not-configured"

    return ChatOpenAI(**kwargs)

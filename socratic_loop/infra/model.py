"""
模型工厂 —— 统一管理 LLM 实例的创建。

读取环境变量决定使用哪个模型供应商：
- 未设置 LLM_BASE_URL → 默认 OpenAI (gpt-4o)
- 设置了 LLM_BASE_URL → 使用对应供应商（如 DeepSeek）

Agent 节点通过 get_chat_model() 获取模型实例，
无需关心底层是 OpenAI 还是 DeepSeek。

支持两种使用方式：
1. 传统 env 路径：get_chat_model(temperature) —— 从 os.environ 读取配置（脚本与测试用）。
2. 显式参数路径：get_chat_model(temperature, model_name=..., base_url=..., api_key=...)
   —— per-tab 冻结配置，由 UI 的 ModelStore 注入（支持多提供商并行）。
"""

import os
import warnings
from collections.abc import Mapping
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

#: 未配置 API Key 时使用的占位符值。
_PLACEHOLDER_API_KEY = "sk-not-configured"


@dataclass(frozen=True)
class ModelConfig:
    """从环境变量解析出的模型配置。"""

    model_name: str
    base_url: str | None
    api_key: str | None


def _get_env_str(source: Mapping[str, object], key: str) -> str:
    """从环境变量映射读取字符串值；非字符串按缺失处理。"""
    value = source.get(key, "")
    return value if isinstance(value, str) else ""


def load_model_config(env: Mapping[str, object] | None = None) -> ModelConfig:
    """从环境变量映射读取模型配置。"""
    source = os.environ if env is None else env
    api_key = _get_env_str(source, "LLM_API_KEY") or _get_env_str(source, "OPENAI_API_KEY") or None
    if api_key == _PLACEHOLDER_API_KEY:
        api_key = None

    return ModelConfig(
        model_name=_get_env_str(source, "LLM_MODEL") or "gpt-4o",
        base_url=_get_env_str(source, "LLM_BASE_URL") or None,
        api_key=api_key,
    )


def has_configured_api_key(env: Mapping[str, object] | None = None) -> bool:
    """判断环境中是否配置了真实 API Key（占位符不算已配置）。"""
    return load_model_config(env).api_key is not None


def get_chat_model(
    temperature: float = 0.7,
    *,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> ChatOpenAI:
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
        model_name: 可选的模型名覆盖（per-tab 配置，优先级高于环境变量）。
        base_url: 可选的端点覆盖（per-tab 配置，优先级高于环境变量）。
        api_key: 可选的 API Key 覆盖（per-tab 配置，优先级高于环境变量）。
            空串 "" 视同未传入，会回退到环境变量。这样可以用 state.get(...) 的
            默认空串直接透传而无需额外判空。

    Returns:
        配置好的 ChatOpenAI 实例。
    """
    config = load_model_config()

    # 参数优先级：显式传入 api_key > 环境变量 config.api_key > placeholder
    # 注意：空串视为未传入（与 str | None 语义一致，方便 state.get 透传）
    effective_key = api_key if api_key else config.api_key

    if not effective_key:
        warnings.warn(
            "未检测到 LLM_API_KEY 或 OPENAI_API_KEY 环境变量。"
            "请在「模型设置」页面或项目根目录的 .env 文件中配置 API Key，"
            "或通过环境变量设置。示例：LLM_API_KEY=sk-your-key",
            RuntimeWarning,
            stacklevel=2,
        )
        effective_key = _PLACEHOLDER_API_KEY

    return ChatOpenAI(
        model=model_name or config.model_name,
        temperature=temperature,
        base_url=base_url if base_url is not None else config.base_url,
        api_key=effective_key,  # type: ignore[arg-type]  # langchain 类型桩使用 SecretStr
        streaming=True,  # 启用 token 级回调，供 graph.stream(mode="messages") 使用
    )


def get_chat_model_for_profile(
    profile,  # ModelProfile —— 不引入类型以避免模块循环
    temperature: float = 0.7,
) -> ChatOpenAI:
    """便捷方法：从 ModelProfile 创建 ChatOpenAI 实例。

    将 profile 的 model_name/base_url/api_key 全部透传，适合 UI 层
    通过 ModelStore.get_active_profile() 获取配置后创建模型使用。
    """
    return get_chat_model(
        temperature=temperature,
        model_name=profile.model_name,
        base_url=profile.base_url,
        api_key=profile.api_key,
    )

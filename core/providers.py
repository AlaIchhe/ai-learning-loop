"""
预设模型提供商注册表 —— 纯数据模块，无副作用。

定义所有内置支持的 OpenAI 兼容提供商及其默认配置：
- 基础端点 URL
- 预设模型列表
- 是否原生支持 with_structured_output（决定 Referee 是否需要 json_mode）
- API Key 获取链接与占位符

UI 层通过此注册表渲染「添加提供商」选择器；model_store 在迁移时
按 base_url 子串匹配到对应 preset。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderPreset:
    """单个预设提供商的静态元数据。"""

    id: str
    """唯一标识符（如 "openai"、"deepseek"）。"""

    label: str
    """中文显示名（如 "OpenAI"、"DeepSeek"）。"""

    icon: str
    """emoji 图标，用于 UI 显示。"""

    base_url: str | None
    """默认 API 端点。None = 使用 OpenAI 官方端点（SDK 默认）；
    空串 "" = 自定义端点（用户必须填写）；其他为预设端点。"""

    api_key_help_url: str
    """获取 API Key 的帮助文档链接。"""

    api_key_placeholder: str
    """API Key 输入框的占位提示。"""

    api_key_required: bool = True
    """是否必须配置 API Key（False 用于 Ollama 等本地无鉴权部署）。"""

    preset_models: tuple[str, ...] = ()
    """该提供商的已知模型列表（用户仍可添加自定义模型）。"""

    supports_structured_output: bool = True
    """是否原生支持 with_structured_output。
    False 时 Referee 自动切换到 JSON-mode 正则提取策略（如 DeepSeek）。"""

    default_model: str = field(init=False)
    """默认模型（preset_models 的第一个；若列表为空则为空串）。"""

    def __post_init__(self) -> None:
        # frozen dataclass 中通过 object.__setattr__ 赋值
        object.__setattr__(
            self,
            "default_model",
            self.preset_models[0] if self.preset_models else "",
        )


# =============================================================================
# 预设提供商定义
# =============================================================================

_PRESETS_ORDERED: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="openai",
        label="OpenAI",
        icon="🟢",
        base_url=None,
        api_key_help_url="https://platform.openai.com/api-keys",
        api_key_placeholder="sk-...",
        preset_models=(
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o4-mini",
        ),
        supports_structured_output=True,
    ),
    ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        icon="🟣",
        base_url="https://api.deepseek.com/v1",
        api_key_help_url="https://platform.deepseek.com/api_keys",
        api_key_placeholder="sk-...",
        preset_models=("deepseek-chat", "deepseek-reasoner"),
        # DeepSeek 不支持 with_structured_output，需走 JSON-mode
        supports_structured_output=False,
    ),
    ProviderPreset(
        id="siliconflow",
        label="硅基流动 (SiliconFlow)",
        icon="🔶",
        base_url="https://api.siliconflow.cn/v1",
        api_key_help_url="https://cloud.siliconflow.cn/account/ak",
        api_key_placeholder="sk-...",
        preset_models=(
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
            "Qwen/Qwen3-235B-A22B",
            "Qwen/Qwen2.5-72B-Instruct",
            "meta-llama/Llama-3.3-70B-Instruct",
        ),
        supports_structured_output=False,
    ),
    ProviderPreset(
        id="tongyi",
        label="通义千问 (DashScope)",
        icon="🟠",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_help_url="https://dashscope.console.aliyun.com/apiKey",
        api_key_placeholder="sk-...",
        preset_models=("qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"),
        supports_structured_output=False,
    ),
    ProviderPreset(
        id="zhipu",
        label="智谱 (GLM)",
        icon="🔵",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_help_url="https://open.bigmodel.cn/usercenter/apikeys",
        api_key_placeholder="xxxxxxxx.xxxxxxxx",
        preset_models=("glm-4-flash", "glm-4-plus", "glm-4-long"),
        supports_structured_output=False,
    ),
    ProviderPreset(
        id="moonshot",
        label="月之暗面 (Kimi)",
        icon="🌙",
        base_url="https://api.moonshot.cn/v1",
        api_key_help_url="https://platform.moonshot.cn/console/api-keys",
        api_key_placeholder="sk-...",
        preset_models=("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
        supports_structured_output=False,
    ),
    ProviderPreset(
        id="ollama",
        label="Ollama (本地)",
        icon="🦙",
        base_url="http://localhost:11434/v1",
        api_key_help_url="https://ollama.com/",
        api_key_placeholder="无需 API Key",
        api_key_required=False,
        preset_models=(),  # 本地模型由用户自行添加
        supports_structured_output=False,
    ),
    ProviderPreset(
        id="custom",
        label="自定义 OpenAI 兼容",
        icon="⚙️",
        base_url="",  # 用户自己填
        api_key_help_url="",
        api_key_placeholder="sk-...（如需要）",
        api_key_required=False,
        preset_models=(),
        supports_structured_output=False,
    ),
)


#: 以 id 为键的预设字典，便于快速查找。
PRESET_PROVIDERS: dict[str, ProviderPreset] = {p.id: p for p in _PRESETS_ORDERED}


def get_preset(preset_id: str) -> ProviderPreset:
    """按 id 获取预设。找不到时抛 KeyError。"""
    if preset_id not in PRESET_PROVIDERS:
        raise KeyError(f"未知的提供商预设: {preset_id}")
    return PRESET_PROVIDERS[preset_id]


def iter_presets() -> tuple[ProviderPreset, ...]:
    """按 UI 显示顺序遍历所有预设。"""
    return _PRESETS_ORDERED


def detect_preset_by_base_url(base_url: str | None) -> str:
    """根据 base URL 猜测匹配的 preset id（用于 .env 迁移）。

    匹配规则（按优先级）：
    - None / 空串 → "openai"
    - 包含 "deepseek" → "deepseek"
    - 包含 "siliconflow" → "siliconflow"
    - 包含 "dashscope" 或 "aliyuncs" → "tongyi"
    - 包含 "bigmodel" → "zhipu"
    - 包含 "moonshot" → "moonshot"
    - 包含 "ollama" 或 "localhost:11434" → "ollama"
    - 其他 → "custom"
    """
    if not base_url:
        return "openai"
    url_lower = base_url.lower()
    if "deepseek" in url_lower:
        return "deepseek"
    if "siliconflow" in url_lower:
        return "siliconflow"
    if "dashscope" in url_lower or "aliyuncs" in url_lower:
        return "tongyi"
    if "bigmodel" in url_lower:
        return "zhipu"
    if "moonshot" in url_lower:
        return "moonshot"
    if "ollama" in url_lower or ":11434" in url_lower:
        return "ollama"
    return "custom"

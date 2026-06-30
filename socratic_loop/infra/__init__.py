"""基础设施层 —— IO、副作用、外部交互。

包含系统的运行时基础设施:
    - env: 环境初始化（sys.path、.env 加载）
    - model: LLM 工厂（ChatOpenAI 实例创建）
    - providers: 预设提供商注册表（纯数据）
    - model_store: 模型配置持久化存储（JSON 文件 CRUD）
    - logging: 结构化日志与可观测性
    - connection_test: LLM API 连通性测试

本包依赖 core/（契约层），可被 agents/、workflow/、web/ 依赖。

公共 API:
    from socratic_loop.infra import (
        setup_environment,
        get_chat_model, get_chat_model_for_profile,
        load_model_config, has_configured_api_key,
        ModelConfig, ModelStore, ModelProfile, ProviderEntry,
        ProviderPreset, get_preset, iter_presets, detect_preset_by_base_url,
        check_connection, ConnectionResult,
        TraceLogger, trace_id_context, create_trace_logger,
    )
"""

from socratic_loop.infra.connection_test import ConnectionResult, check_connection
from socratic_loop.infra.env import setup_environment
from socratic_loop.infra.logging import TraceLogger, create_trace_logger, trace_id_context
from socratic_loop.infra.model import (
    ModelConfig,
    get_chat_model,
    get_chat_model_for_profile,
    has_configured_api_key,
    load_model_config,
)
from socratic_loop.infra.model_store import ModelProfile, ModelStore, ProviderEntry
from socratic_loop.infra.providers import (
    ProviderPreset,
    detect_preset_by_base_url,
    get_preset,
    iter_presets,
)

__all__ = [
    # —— env ——
    "setup_environment",
    # —— model ——
    "ModelConfig",
    "get_chat_model",
    "get_chat_model_for_profile",
    "load_model_config",
    "has_configured_api_key",
    # —— providers ——
    "ProviderPreset",
    "get_preset",
    "iter_presets",
    "detect_preset_by_base_url",
    # —— model_store ——
    "ModelStore",
    "ModelProfile",
    "ProviderEntry",
    # —— logging ——
    "TraceLogger",
    "trace_id_context",
    "create_trace_logger",
    # —— connection_test ——
    "check_connection",
    "ConnectionResult",
]

"""应用配置单一读取器 —— 所有环境变量的权威来源。

使用 pydantic_settings.BaseSettings 集中声明、验证、提供默认值。
环境变量由 infra/env.py:setup_environment() 通过 load_dotenv() 填充
os.environ，本模块仅读取 os.environ，不自动加载 .env（保持单一加载点）。

使用方式:
    from socratic_loop.core.settings import settings

    model_name = settings.llm_model
    port = settings.frontend_port
    transport = settings.effective_transport()
"""

import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: 未配置 API Key 时使用的占位符值（与 infra/model.py 保持一致）。
_PLACEHOLDER_API_KEY = "sk-not-configured"


class AppSettings(BaseSettings):
    """应用配置 —— 从 os.environ 读取，全部带有安全默认值。"""

    model_config = SettingsConfigDict(
        env_file=None,  # 由 setup_environment() 的 load_dotenv() 填充 os.environ
        populate_by_name=True,  # 允许同时用字段名和环境变量名赋值
        env_prefix="",  # 无前缀，直接使用 LLM_MODEL 等变量名
    )

    # ── 服务器 ──
    frontend_port: int = Field(
        default=3003,
        description="Reflex 前端开发服务器端口",
    )
    backend_port: int = Field(
        default=8003,
        description="Reflex 后端 API 端口",
    )
    db_url: str = Field(
        default="sqlite:///reflex.db",
        description="Reflex 框架 SQLite 数据库 URL",
    )
    transport: str = Field(
        default="auto",
        description="Reflex 传输协议：auto（按平台自动选择）/ polling / websocket",
    )

    # ── LLM ──
    llm_model: str = Field(
        default="gpt-4o",
        description="LLM 模型名称",
    )
    llm_base_url: str | None = Field(
        default=None,
        description="LLM API 端点（None = OpenAI 官方）",
    )
    llm_api_key: str | None = Field(
        default=None,
        description="LLM API Key（优先级高于 OPENAI_API_KEY）",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API Key（LLM_API_KEY 未设置时回退）",
    )

    # ── LangSmith 追踪 ──
    langchain_tracing_v2: bool = Field(
        default=False,
        description="是否启用 LangSmith V2 追踪",
    )
    langchain_api_key: str = Field(
        default="",
        description="LangSmith API Key",
    )
    langchain_project: str = Field(
        default="ai-learning-loop",
        description="LangSmith 项目名称",
    )

    # ── 网络/重试 ──
    llm_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="LLM 调用最大重试次数（含首次调用）",
    )
    llm_retry_backoff_base: float = Field(
        default=1.0,
        ge=0.0,
        description="指数退避基数（秒）：第 n 次重试等待 base * 2^(n-1) 秒",
    )
    connection_timeout: float = Field(
        default=10.0,
        ge=0.0,
        description="API 连通性测试超时秒数",
    )

    def effective_transport(self) -> str:
        """返回实际使用的传输协议。

        - transport != "auto" 时直接使用设定值
        - transport == "auto" 时按平台选择：Windows → polling，其他 → websocket
        """
        if self.transport != "auto":
            return self.transport
        return "polling" if sys.platform == "win32" else "websocket"

    def effective_api_key(self) -> str | None:
        """返回有效的 API Key（LLM_API_KEY 优先，OPENAI_API_KEY 回退）。

        空串和占位符 "sk-not-configured" 视为未配置，返回 None。
        """
        key = self.llm_api_key or self.openai_api_key
        if not key or key == _PLACEHOLDER_API_KEY:
            return None
        return key


#: 模块级配置单例 —— 整个应用共享。
settings = AppSettings()

"""
LLM API 连通性测试 —— 验证 API Key 与端点是否可用。

使用标准库 urllib 向 /models 端点发送 GET 请求，
根据响应状态码与网络错误分类给出中文诊断消息。

设计原则：
- 纯函数，无全局状态，不访问 os.environ
- 不依赖 httpx/requests（避免新增依赖）
- 所有异常都被捕获为 ConnectionResult，不向上抛
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ConnectionResult:
    """连通性测试结果。"""

    ok: bool
    """连接是否可用。"""

    message: str
    """中文描述消息，用于 UI 直接展示。"""

    tested_model: str = ""
    """可选：返回的一个模型 ID（用于确认认证通过）。"""

    status: Literal["ok", "auth", "timeout", "network", "server", "unknown"] = "ok"
    """机器可读的错误分类。ok=成功；auth=鉴权失败；timeout=超时；
    network=连接失败/DNS；server=5xx 服务端错误；unknown=未知错误。"""


def _build_request_url(base_url: str | None, is_ollama: bool) -> str:
    """构造用于连通性测试的 URL。"""
    if base_url is None or base_url == "":
        # OpenAI 官方端点
        return "https://api.openai.com/v1/models"
    base = base_url.rstrip("/")
    if is_ollama:
        # Ollama 使用 /api/tags 而非 /models
        return f"{base}/api/tags"
    if base.endswith("/v1"):
        return f"{base}/models"
    # 兜底：假设用户提供的 base_url 已包含 /v1 或需要附加 /models
    if "/models" in base:
        return base
    return f"{base}/models"


def check_connection(
    base_url: str | None,
    api_key: str,
    *,
    timeout: float | None = None,
    provider_id: str = "",
) -> ConnectionResult:
    """测试给定端点与 API Key 的连通性。

    注意：函数名不以 test_ 开头，避免被 pytest 误收集为测试用例。

    Args:
        base_url: API 端点。None 或空串表示 OpenAI 官方端点。
        api_key: API Key。Ollama 等无鉴权服务可传空串。
        timeout: 请求超时秒数。None 时使用 core/settings.py 的
                connection_timeout（可通过 CONNECTION_TIMEOUT 环境变量覆盖）。
        provider_id: 可选的 preset id，用于 Ollama 特殊路径判断。
                     未传时通过 base_url 子串自动判断。

    Returns:
        ConnectionResult，ok=True 表示配置可用。
    """
    # 延迟导入避免循环依赖；使用 settings 的运行时最新值
    from socratic_loop.core.settings import settings

    if timeout is None:
        timeout = settings.connection_timeout
    is_ollama = provider_id == "ollama" or (
        isinstance(base_url, str)
        and ("ollama" in base_url.lower() or "localhost:11434" in base_url.lower())
    )

    url = _build_request_url(base_url, is_ollama)

    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key and not is_ollama:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            status_code = resp.getcode()
            body_bytes = resp.read()
    except urllib.error.HTTPError as e:
        # HTTP 错误响应
        status_code = e.code
        body_bytes = e.read() if hasattr(e, "read") else b""
    except urllib.error.URLError as e:
        reason = e.reason
        reason_str = str(reason)
        # DNS 失败优先检测（在通用 OSError 之前）
        dns_markers = ("Name or service not known", "getaddrinfo", "nodename nor servname")
        if any(m in reason_str for m in dns_markers):
            return ConnectionResult(
                ok=False,
                message=f"无法解析域名，请检查 Base URL 是否正确：{base_url}",
                status="network",
            )
        if isinstance(reason, TimeoutError) or (
            isinstance(reason, str) and "timed out" in reason.lower()
        ):
            return ConnectionResult(
                ok=False,
                message=f"连接超时（{timeout}s）。请检查网络或端点 URL 是否正确。",
                status="timeout",
            )
        if isinstance(reason, (ConnectionRefusedError, OSError)):
            return ConnectionResult(
                ok=False,
                message=f"无法连接到端点：{url}。请检查 URL、本地服务是否启动，以及网络设置。",
                status="network",
            )
        return ConnectionResult(
            ok=False,
            message=f"网络错误：{reason_str}",
            status="network",
        )
    except TimeoutError:
        return ConnectionResult(
            ok=False,
            message=f"连接超时（{timeout}s）。",
            status="timeout",
        )
    except Exception as e:
        return ConnectionResult(
            ok=False,
            message=f"未知错误：{e}",
            status="unknown",
        )

    # 处理 HTTP 响应
    if status_code == 401 or status_code == 403:
        return ConnectionResult(
            ok=False,
            message=f"API Key 无效或无访问权限（HTTP {status_code}）。请检查 API Key 是否正确。",
            status="auth",
        )
    if status_code == 404:
        return ConnectionResult(
            ok=False,
            message=f"端点未找到（HTTP 404）：{url}。请检查 Base URL 是否正确（通常应形如 https://api.example.com/v1）。",
            status="network",
        )
    if 500 <= status_code < 600:
        return ConnectionResult(
            ok=False,
            message=f"服务端错误（HTTP {status_code}）。请稍后再试。",
            status="server",
        )
    if status_code < 200 or status_code >= 300:
        snippet = body_bytes[:200].decode("utf-8", errors="replace") if body_bytes else ""
        return ConnectionResult(
            ok=False,
            message=f"请求失败（HTTP {status_code}）：{snippet}",
            status="unknown",
        )

    # 2xx — 尝试解析返回体以确认 JSON 合法
    tested_model = ""
    try:
        data = json.loads(body_bytes.decode("utf-8", errors="replace"))
        # OpenAI 兼容：{"data": [{"id": "gpt-4o", ...}, ...]}
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list) and data["data"]:
                first = data["data"][0]
                if isinstance(first, dict) and "id" in first:
                    tested_model = str(first["id"])
            # Ollama /api/tags：{"models": [{"name": "llama3.1", ...}, ...]}
            elif "models" in data and isinstance(data["models"], list) and data["models"]:
                first = data["models"][0]
                if isinstance(first, dict):
                    tested_model = str(first.get("name") or first.get("model") or "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    if tested_model:
        return ConnectionResult(
            ok=True,
            message=f"连接成功！检测到可用模型，如 {tested_model}。",
            tested_model=tested_model,
            status="ok",
        )
    return ConnectionResult(
        ok=True,
        message="连接成功！端点返回有效响应。",
        status="ok",
    )

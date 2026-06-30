"""socratic_loop.infra.connection_test 连通性测试单元测试（mock HTTP，不访问真实网络）。"""

import io
import json
import urllib.error
from unittest.mock import patch

from socratic_loop.infra.connection_test import check_connection


class _FakeResponse:
    """模拟 urllib.urlopen 的返回值。"""

    def __init__(self, code: int, body: bytes | None = None):
        self._code = code
        self._body = body or b""

    def getcode(self) -> int:
        return self._code

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _models_response(models: list[str]) -> bytes:
    return json.dumps({"data": [{"id": m, "object": "model"} for m in models]}).encode()


def _ollama_tags_response(models: list[str]) -> bytes:
    return json.dumps({"models": [{"name": m} for m in models]}).encode()


class TestConnectionTestSuccess:
    """2xx 响应的各种情况。"""

    def test_openai_success_returns_ok(self):
        fake = _FakeResponse(200, _models_response(["gpt-4o", "gpt-4o-mini"]))
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", return_value=fake):
            result = check_connection(None, "sk-test")
        assert result.ok is True
        assert result.status == "ok"
        assert "gpt-4o" in result.tested_model
        assert "成功" in result.message

    def test_deepseek_with_base_url(self):
        fake = _FakeResponse(200, _models_response(["deepseek-chat"]))
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            return fake

        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=fake_urlopen):
            result = check_connection("https://api.deepseek.com/v1", "sk-deepseek")
        assert result.ok is True
        assert captured["url"] == "https://api.deepseek.com/v1/models"
        assert captured["auth"] == "Bearer sk-deepseek"
        assert result.tested_model == "deepseek-chat"

    def test_ollama_uses_api_tags_endpoint(self):
        fake = _FakeResponse(200, _ollama_tags_response(["llama3.1"]))
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            return fake

        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=fake_urlopen):
            result = check_connection("http://localhost:11434/v1", "", provider_id="ollama")
        assert result.ok is True
        assert captured["url"] == "http://localhost:11434/v1/api/tags"
        # Ollama 无鉴权头
        assert captured["auth"] is None
        assert "llama3.1" in result.tested_model

    def test_ollama_auto_detected_from_url(self):
        """未显式传 provider_id 时，根据 base_url 自动识别 ollama。"""
        fake = _FakeResponse(200, _ollama_tags_response(["llama3"]))
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            return fake

        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=fake_urlopen):
            result = check_connection("http://localhost:11434/v1", "")
        assert result.ok is True
        assert "/api/tags" in captured["url"]

    def test_json_body_without_data_key_still_ok(self):
        """服务端返回合法 JSON 但结构不符合 OpenAI 格式时，仍判为连接成功。"""
        fake = _FakeResponse(200, b'{"status":"ok"}')
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", return_value=fake):
            result = check_connection("https://example.com/v1", "sk-x")
        assert result.ok is True
        assert result.tested_model == ""


class TestConnectionTestErrors:
    """各种错误场景分类。"""

    def test_http_401_is_auth_error(self):
        error = urllib.error.HTTPError(
            "https://api.example.com/v1/models", 401, "Unauthorized", {}, io.BytesIO(b"{}")
        )
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=error):
            result = check_connection("https://api.example.com/v1", "sk-wrong")
        assert result.ok is False
        assert result.status == "auth"
        assert "API Key" in result.message or "401" in result.message

    def test_http_403_is_auth_error(self):
        error = urllib.error.HTTPError(
            "https://api.example.com/v1/models", 403, "Forbidden", {}, io.BytesIO(b"{}")
        )
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=error):
            result = check_connection("https://api.example.com/v1", "sk-x")
        assert result.status == "auth"

    def test_http_404_is_network_error(self):
        error = urllib.error.HTTPError(
            "https://example.com/wrong", 404, "Not Found", {}, io.BytesIO(b"{}")
        )
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=error):
            result = check_connection("https://example.com/wrong", "sk-x")
        assert result.ok is False
        assert result.status == "network"
        assert "404" in result.message or "端点" in result.message

    def test_http_500_is_server_error(self):
        error = urllib.error.HTTPError(
            "https://api.example.com/v1/models", 500, "Internal", {}, io.BytesIO(b"{}")
        )
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=error):
            result = check_connection("https://api.example.com/v1", "sk-x")
        assert result.ok is False
        assert result.status == "server"

    def test_connection_refused_is_network(self):
        import urllib.request
        # URLError with ConnectionRefusedError reason
        err = urllib.error.URLError(ConnectionRefusedError("refused"))
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=err):
            result = check_connection("http://localhost:9999/v1", "")
        assert result.ok is False
        assert result.status == "network"

    def test_dns_failure_is_network(self):
        import urllib.request
        err = urllib.error.URLError(OSError("Name or service not known"))
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=err):
            result = check_connection("https://nonexistent.invalid/v1", "sk-x")
        assert result.ok is False
        assert result.status == "network"
        assert "域名" in result.message or "解析" in result.message

    def test_socket_timeout_is_timeout(self):
        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = check_connection("https://api.example.com/v1", "sk-x", timeout=0.01)
        assert result.ok is False
        assert result.status == "timeout"
        assert "超时" in result.message


class TestConnectionTestEdgeCases:
    """边界情况。"""

    def test_empty_base_url_hits_openai(self):
        """空串应被视为未设置，走 OpenAI 官方端点。"""
        fake = _FakeResponse(200, _models_response(["gpt-4o"]))
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            return fake

        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=fake_urlopen):
            check_connection("", "sk-x")
        assert captured["url"] == "https://api.openai.com/v1/models"

    def test_base_url_without_v1_appends_models(self):
        """base_url 不以 /v1 结尾时，直接附加 /models（兼容性）。"""
        fake = _FakeResponse(200, _models_response(["x"]))
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            return fake

        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=fake_urlopen):
            check_connection("https://proxy.example.com", "sk-x")
        assert captured["url"] == "https://proxy.example.com/models"

    def test_base_url_with_trailing_slash_stripped(self):
        fake = _FakeResponse(200, _models_response(["x"]))
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            return fake

        with patch("socratic_loop.infra.connection_test.urllib.request.urlopen", side_effect=fake_urlopen):
            check_connection("https://api.example.com/v1/", "sk-x")
        assert captured["url"] == "https://api.example.com/v1/models"

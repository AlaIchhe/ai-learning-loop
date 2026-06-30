"""socratic_loop.infra.providers 预设提供商注册表单元测试。"""

import pytest

from socratic_loop.infra.providers import (
    PRESET_PROVIDERS,
    detect_preset_by_base_url,
    get_preset,
    iter_presets,
)


class TestProviderPresetInvariants:
    """预设的结构性约束，所有内置提供商必须满足。"""

    def test_all_preset_ids_unique(self):
        ids = [p.id for p in iter_presets()]
        assert len(ids) == len(set(ids))

    def test_preset_count(self):
        """至少包含 OpenAI、DeepSeek、Ollama、custom 四类核心提供商。"""
        assert len(PRESET_PROVIDERS) >= 6
        for required in ("openai", "deepseek", "ollama", "custom"):
            assert required in PRESET_PROVIDERS

    def test_default_model_is_first_preset(self):
        """default_model 应等于 preset_models[0]（若有模型），否则为空串。"""
        for p in iter_presets():
            if p.preset_models:
                assert p.default_model == p.preset_models[0]
            else:
                assert p.default_model == ""

    def test_icons_non_empty(self):
        for p in iter_presets():
            assert p.icon and len(p.icon) >= 1

    def test_labels_non_empty(self):
        for p in iter_presets():
            assert p.label and len(p.label) >= 2

    def test_openai_has_no_base_url(self):
        """OpenAI 应使用 SDK 默认端点（base_url=None）。"""
        assert PRESET_PROVIDERS["openai"].base_url is None

    def test_deepseek_does_not_support_structured_output(self):
        assert PRESET_PROVIDERS["deepseek"].supports_structured_output is False

    def test_deepseek_base_url(self):
        assert "deepseek" in (PRESET_PROVIDERS["deepseek"].base_url or "")

    def test_ollama_requires_no_api_key(self):
        assert PRESET_PROVIDERS["ollama"].api_key_required is False

    def test_custom_has_empty_base_url(self):
        """自定义提供商不预填 base_url。"""
        assert PRESET_PROVIDERS["custom"].base_url == ""

    def test_get_preset_returns_same_object(self):
        p = get_preset("openai")
        assert p is PRESET_PROVIDERS["openai"]

    def test_get_preset_unknown_raises(self):
        with pytest.raises(KeyError):
            get_preset("nonexistent-provider-xyz")

    def test_api_key_help_url_format(self):
        """设置了 help_url 的提供商，URL 须以 http 开头；允许留空（custom/ollama）。"""
        for p in iter_presets():
            if p.api_key_help_url:
                assert p.api_key_help_url.startswith("http"), f"{p.id} help_url 需为 http(s) URL"


class TestDetectPresetByBaseUrl:
    """通过 base URL 检测预设提供商的迁移辅助函数。"""

    def test_none_or_empty_is_openai(self):
        assert detect_preset_by_base_url(None) == "openai"
        assert detect_preset_by_base_url("") == "openai"

    def test_deepseek(self):
        assert detect_preset_by_base_url("https://api.deepseek.com/v1") == "deepseek"
        assert detect_preset_by_base_url("https://api.deepseek.com") == "deepseek"

    def test_siliconflow(self):
        assert detect_preset_by_base_url("https://api.siliconflow.cn/v1") == "siliconflow"

    def test_tongyi_by_dashscope(self):
        assert detect_preset_by_base_url(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ) == "tongyi"

    def test_tongyi_by_aliyuncs(self):
        assert detect_preset_by_base_url(
            "https://dashscope.aliyuncs.com/api/v1"
        ) == "tongyi"

    def test_zhipu(self):
        assert detect_preset_by_base_url(
            "https://open.bigmodel.cn/api/paas/v4"
        ) == "zhipu"

    def test_moonshot(self):
        assert detect_preset_by_base_url("https://api.moonshot.cn/v1") == "moonshot"

    def test_ollama_localhost(self):
        assert detect_preset_by_base_url("http://localhost:11434/v1") == "ollama"

    def test_ollama_by_name(self):
        assert detect_preset_by_base_url("http://192.168.1.10:11434/v1") == "ollama"

    def test_unknown_falls_back_to_custom(self):
        assert detect_preset_by_base_url("https://api.example.com/v1") == "custom"

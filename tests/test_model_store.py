"""socratic_loop.core.model_store 持久化与 CRUD 单元测试。"""

from pathlib import Path

import pytest

from socratic_loop.core.model import ModelConfig
from socratic_loop.core.model_store import ModelStore
from socratic_loop.core.providers import get_preset


class TestEmptyStore:
    def test_empty_store_has_no_providers(self):
        s = ModelStore()
        assert s.providers == {}
        assert s.active_profile_id is None
        assert s.get_active_profile() is None
        assert s.configured_providers() == {}

    def test_empty_to_dict_roundtrip(self):
        s = ModelStore()
        d = s.to_dict()
        s2 = ModelStore.from_dict(d)
        assert s2.providers == {}
        assert s2.active_profile_id is None

    def test_save_and_load(self, tmp_path: Path):
        s = ModelStore()
        p = tmp_path / "config.json"
        s.save(p)
        assert p.exists()
        s2 = ModelStore.load(p)
        assert s2.providers == {}

    def test_load_nonexistent_file_returns_empty(self, tmp_path: Path):
        s = ModelStore.load(tmp_path / "nonexistent.json")
        assert s.providers == {}

    def test_load_corrupt_file_returns_empty(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        s = ModelStore.load(p)
        assert s.providers == {}


class TestProviderCRUD:
    def test_add_provider_generates_default_entry_id(self):
        s = ModelStore()
        eid = s.add_provider("deepseek", api_key="sk-1")
        assert eid == "deepseek-default"
        assert "deepseek-default" in s.providers

    def test_add_provider_multiple_instances_increments_id(self):
        s = ModelStore()
        e1 = s.add_provider("deepseek", display_name="D1", api_key="sk-1")
        e2 = s.add_provider("deepseek", display_name="D2", api_key="sk-2")
        assert e1 == "deepseek-default"
        assert e2 == "deepseek-1"
        e3 = s.add_provider("deepseek", display_name="D3")
        assert e3 == "deepseek-2"

    def test_add_provider_uses_preset_defaults(self):
        s = ModelStore()
        eid = s.add_provider("deepseek")
        entry = s.providers[eid]
        assert entry.display_name == "DeepSeek"
        # 未显式传 base_url 时使用 preset.base_url
        preset = get_preset("deepseek")
        assert entry.effective_base_url() == preset.base_url
        assert entry.supports_structured_output() is False
        assert entry.api_key == ""

    def test_add_provider_custom_overrides(self):
        s = ModelStore()
        eid = s.add_provider(
            "custom",
            display_name="我的代理",
            base_url="https://my-proxy.example.com/v1",
            api_key="sk-proxy",
        )
        entry = s.providers[eid]
        assert entry.display_name == "我的代理"
        assert entry.base_url == "https://my-proxy.example.com/v1"
        assert entry.effective_base_url() == "https://my-proxy.example.com/v1"
        assert entry.api_key == "sk-proxy"

    def test_add_provider_duplicate_entry_id_raises(self):
        s = ModelStore()
        s.add_provider("deepseek", entry_id="dup")
        with pytest.raises(ValueError, match="已存在"):
            s.add_provider("openai", entry_id="dup")

    def test_remove_provider(self):
        s = ModelStore()
        eid = s.add_provider("openai", api_key="sk-x")
        s.set_active_profile(eid, "gpt-4o")
        assert s.get_active_profile() is not None
        s.remove_provider(eid)
        assert eid not in s.providers
        assert s.get_active_profile() is None  # active 被清除

    def test_remove_provider_preserves_other_active(self):
        s = ModelStore()
        e1 = s.add_provider("openai", api_key="sk-1")
        e2 = s.add_provider("deepseek", api_key="sk-2")
        s.set_active_profile(e1, "gpt-4o")
        s.remove_provider(e2)
        assert s.get_active_profile() is not None
        assert s.get_active_profile().provider_entry_id == e1


class TestCustomModels:
    def test_add_custom_model_deduplicates(self):
        s = ModelStore()
        eid = s.add_provider("ollama")
        s.add_custom_model(eid, "llama3.1")
        s.add_custom_model(eid, "llama3.1")  # duplicate
        s.add_custom_model(eid, "qwen2.5")
        entry = s.providers[eid]
        assert entry.custom_models == ["llama3.1", "qwen2.5"]

    def test_add_custom_model_strips_whitespace(self):
        s = ModelStore()
        eid = s.add_provider("ollama")
        s.add_custom_model(eid, "  llama3.1  ")
        assert entry_custom_models(s, eid) == ["llama3.1"]

    def test_add_custom_model_ignores_empty(self):
        s = ModelStore()
        eid = s.add_provider("ollama")
        s.add_custom_model(eid, "   ")
        assert entry_custom_models(s, eid) == []

    def test_remove_custom_model(self):
        s = ModelStore()
        eid = s.add_provider("ollama")
        s.add_custom_model(eid, "a")
        s.add_custom_model(eid, "b")
        s.remove_custom_model(eid, "a")
        assert entry_custom_models(s, eid) == ["b"]

    def test_list_models_combines_preset_and_custom(self):
        s = ModelStore()
        eid = s.add_provider("deepseek", api_key="sk-x")
        s.add_custom_model(eid, "my-finetune")
        models = s.list_models(eid)
        assert "deepseek-chat" in models
        assert "deepseek-reasoner" in models
        assert "my-finetune" in models
        # preset 在前，custom 在后
        assert models.index("deepseek-chat") < models.index("my-finetune")


class TestActiveProfile:
    def test_set_and_get_active_profile(self):
        s = ModelStore()
        eid = s.add_provider("openai", api_key="sk-x")
        s.set_active_profile(eid, "gpt-4o")
        p = s.get_active_profile()
        assert p is not None
        assert p.provider_entry_id == eid
        assert p.model_name == "gpt-4o"
        assert p.api_key == "sk-x"
        assert p.base_url is None  # openai 官方
        assert p.supports_structured_output is True

    def test_active_profile_deepseek_has_json_mode(self):
        s = ModelStore()
        eid = s.add_provider("deepseek", api_key="sk-ds")
        s.set_active_profile(eid, "deepseek-chat")
        p = s.get_active_profile()
        assert p.supports_structured_output is False

    def test_set_active_profile_nonexistent_entry_raises(self):
        s = ModelStore()
        with pytest.raises(KeyError):
            s.set_active_profile("nonexistent", "x")

    def test_configured_providers_only_status_ok(self):
        s = ModelStore()
        e1 = s.add_provider("openai", api_key="sk-x", status="ok")
        e2 = s.add_provider("deepseek", status="unconfigured")
        _ = e2
        configured = s.configured_providers()
        assert e1 in configured
        assert e2 not in configured


class TestSerializationRoundTrip:
    def test_full_store_roundtrip(self, tmp_path: Path):
        s = ModelStore()
        e1 = s.add_provider("openai", api_key="sk-openai", status="ok")
        e2 = s.add_provider("deepseek", api_key="sk-ds", status="ok")
        s.add_custom_model(e2, "my-model")
        s.set_active_profile(e1, "gpt-4o-mini")
        p = tmp_path / "config.json"
        s.save(p)
        s2 = ModelStore.load(p)
        assert set(s2.providers.keys()) == {e1, e2}
        assert s2.active_profile_id == f"{e1}:gpt-4o-mini"
        p2 = s2.get_active_profile()
        assert p2 is not None
        assert p2.model_name == "gpt-4o-mini"
        assert "my-model" in s2.list_models(e2)
        assert s2.providers[e1].status == "ok"

    def test_from_dict_tolerates_unknown_preset(self):
        """dict 包含未知 preset_id 时应回退到 custom 而不崩溃。"""
        d = {
            "version": 1,
            "active_profile_id": None,
            "providers": {
                "x-default": {
                    "preset_id": "future-provider-not-yet-known",
                    "display_name": "Future",
                    "base_url": "https://future.example.com/v1",
                    "api_key": "sk-f",
                    "custom_models": [],
                    "status": "ok",
                }
            }
        }
        s = ModelStore.from_dict(d)
        entry = s.providers["x-default"]
        assert entry.preset_id == "custom"  # 回退
        assert entry.display_name == "Future"

    def test_from_dict_tolerates_missing_fields(self):
        d = {"providers": {"x": {"preset_id": "openai"}}}
        s = ModelStore.from_dict(d)
        entry = s.providers["x"]
        assert entry.preset_id == "openai"
        assert entry.api_key == ""
        assert entry.custom_models == []
        assert entry.status == "unconfigured"

    def test_save_is_atomic(self, tmp_path: Path):
        """保存后不应遗留 .tmp 文件。"""
        s = ModelStore()
        s.add_provider("openai", api_key="sk-x")
        p = tmp_path / "c.json"
        s.save(p)
        assert p.exists()
        assert not (tmp_path / "c.json.tmp").exists()


class TestMigrateFromEnv:
    def test_openai_default(self):
        cfg = ModelConfig(model_name="gpt-4o", base_url=None, api_key="sk-x")
        s = ModelStore.migrate_from_env(cfg)
        eid = "openai-default"
        assert eid in s.providers
        entry = s.providers[eid]
        assert entry.preset_id == "openai"
        assert entry.status == "ok"
        p = s.get_active_profile()
        assert p is not None
        assert p.model_name == "gpt-4o"
        assert p.supports_structured_output is True

    def test_deepseek_migration(self):
        cfg = ModelConfig(
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-ds",
        )
        s = ModelStore.migrate_from_env(cfg)
        entry = s.providers["deepseek-default"]
        assert entry.preset_id == "deepseek"
        assert entry.status == "ok"
        p = s.get_active_profile()
        assert p is not None
        assert p.model_name == "deepseek-chat"
        assert p.supports_structured_output is False

    def test_custom_model_added_to_custom_models(self):
        """env 指定了预设外的模型 → 自动加入 custom_models。"""
        cfg = ModelConfig(
            model_name="my-custom-model",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-ds",
        )
        s = ModelStore.migrate_from_env(cfg)
        entry = s.providers["deepseek-default"]
        assert "my-custom-model" in entry.custom_models
        p = s.get_active_profile()
        assert p.model_name == "my-custom-model"

    def test_no_key_marks_unconfigured_and_no_active(self):
        cfg = ModelConfig(model_name="gpt-4o", base_url=None, api_key=None)
        s = ModelStore.migrate_from_env(cfg)
        entry = s.providers["openai-default"]
        assert entry.status == "unconfigured"
        assert s.get_active_profile() is None

    def test_ollama_no_key_is_ok(self):
        cfg = ModelConfig(
            model_name="llama3.1",
            base_url="http://localhost:11434/v1",
            api_key=None,
        )
        s = ModelStore.migrate_from_env(cfg)
        entry = s.providers["ollama-default"]
        assert entry.preset_id == "ollama"
        assert entry.status == "ok"
        assert "llama3.1" in entry.custom_models
        assert s.get_active_profile() is not None

    def test_unknown_base_url_uses_custom_preset(self):
        cfg = ModelConfig(
            model_name="my-model",
            base_url="https://unknown-proxy.example.com/v1",
            api_key="sk-x",
        )
        s = ModelStore.migrate_from_env(cfg)
        eid = "custom-default"
        assert eid in s.providers
        assert s.providers[eid].preset_id == "custom"
        assert s.providers[eid].base_url == "https://unknown-proxy.example.com/v1"


def entry_custom_models(s: ModelStore, eid: str) -> list[str]:
    return s.providers[eid].custom_models

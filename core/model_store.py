"""
模型配置持久化存储 —— 管理用户配置的提供商列表与活跃模型选择。

职责：
1. 将 ModelStore 序列化为 JSON 文件（.model-config.json），重启后保留
2. 提供提供商与模型的 CRUD 方法
3. 首次启动时从 .env 环境变量自动迁移
4. 输出 ModelProfile（当前活跃模型的完整参数：模型名/端点/key/json_mode）

存储文件路径由 UI 层传入（典型为项目根目录/.model-config.json）。
本模块不访问 st.session_state 或 os.environ（除迁移时显式传入 ModelConfig）。
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from core.model import ModelConfig
from core.providers import ProviderPreset, detect_preset_by_base_url, get_preset

#: 存储文件格式版本号 —— 未来不兼容变更时递增，做迁移
STORE_VERSION = 1

#: 支持的 ProviderEntry 状态
ProviderStatus = Literal["unconfigured", "ok", "error"]


@dataclass
class ProviderEntry:
    """用户已配置的一个提供商实例。"""

    preset_id: str
    """关联的预设 ID，如 "openai"、"deepseek"、"custom"。"""

    display_name: str
    """用户可自定义的显示名。"""

    base_url: str
    """实际端点。空串表示使用预设默认（如 OpenAI 官方端点）。"""

    api_key: str = ""
    """API Key。空串 = 未配置；对于 Ollama 等无鉴权服务允许空。"""

    custom_models: list[str] = field(default_factory=list)
    """用户添加的自定义模型名列表（如 Ollama 模型、微调模型）。"""

    status: ProviderStatus = "unconfigured"
    """当前连接状态。"""

    status_message: str = ""
    """状态描述（如错误原因）。"""

    def preset(self) -> ProviderPreset:
        return get_preset(self.preset_id)

    def effective_base_url(self) -> str | None:
        """返回实际使用的 base_url。

        - 若 self.base_url 非空 → 返回 self.base_url
        - 否则使用预设的 base_url（None 表示 OpenAI SDK 默认）
        """
        if self.base_url:
            return self.base_url
        return self.preset().base_url

    def all_models(self) -> list[str]:
        """返回此提供商可用的全部模型名（预设 + 自定义），去重保持顺序。"""
        seen: set[str] = set()
        result: list[str] = []
        for m in list(self.preset().preset_models) + list(self.custom_models):
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result

    def supports_structured_output(self) -> bool:
        """是否支持原生 with_structured_output（决定 Referee 的策略）。"""
        return self.preset().supports_structured_output


@dataclass(frozen=True)
class ModelProfile:
    """一个具体可选模型的完整可执行标识 —— 从 UI 贯穿到 LLM 工厂。"""

    provider_entry_id: str
    """指向 ModelStore.providers 中的 key。"""

    model_name: str
    """模型 ID（传给 ChatOpenAI 的 model 参数）。"""

    display_name: str
    """展示名，默认等于 model_name。"""

    base_url: str | None
    """端点。None = OpenAI SDK 默认。"""

    api_key: str
    """API Key。"""

    supports_structured_output: bool
    """是否使用 with_structured_output；False 时 Referee 走 JSON-mode。"""


@dataclass
class ModelStore:
    """模型配置持久化根对象。"""

    active_profile_id: str | None = None
    """当前活跃模型的 profile id，格式 "{entry_id}:{model_name}"；None 表示未选择。"""

    providers: dict[str, ProviderEntry] = field(default_factory=dict)
    """已配置的提供商，key = entry_id（如 "openai-default"、"deepseek-work"）。"""

    # =========================================================================
    # 序列化
    # =========================================================================

    def to_dict(self) -> dict:
        return {
            "version": STORE_VERSION,
            "active_profile_id": self.active_profile_id,
            "providers": {
                entry_id: {
                    "preset_id": e.preset_id,
                    "display_name": e.display_name,
                    "base_url": e.base_url,
                    "api_key": e.api_key,
                    "custom_models": list(e.custom_models),
                    "status": e.status,
                    "status_message": e.status_message,
                }
                for entry_id, e in self.providers.items()
            },
        }

    @classmethod
    def from_dict(cls, d: object) -> ModelStore:
        """从 dict 加载，容错未知字段与缺失字段。"""
        providers: dict[str, ProviderEntry] = {}
        data = d if isinstance(d, dict) else {}
        raw_providers = data.get("providers", {})
        if isinstance(raw_providers, dict):
            for entry_id, raw in raw_providers.items():
                if not isinstance(raw, dict):
                    continue
                preset_id = raw.get("preset_id", "custom")
                # 防御：若 preset_id 未知（老版本/拼写错误），回退到 custom
                from core.providers import PRESET_PROVIDERS  # 延迟导入避免循环
                if preset_id not in PRESET_PROVIDERS:
                    preset_id = "custom"
                providers[str(entry_id)] = ProviderEntry(
                    preset_id=str(preset_id),
                    display_name=str(raw.get("display_name") or get_preset(preset_id).label),
                    base_url=str(raw.get("base_url") or ""),
                    api_key=str(raw.get("api_key") or ""),
                    custom_models=list(raw.get("custom_models") or []),
                    status=_valid_status(raw.get("status", "unconfigured")),
                    status_message=str(raw.get("status_message") or ""),
                )
        active = data.get("active_profile_id")
        return cls(
            active_profile_id=str(active) if active else None,
            providers=providers,
        )

    def save(self, path: Path) -> None:
        """原子写入文件。先写 .tmp 再 rename，最后 best-effort chmod 600。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        data = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        tmp_path.write_text(data, encoding="utf-8")
        os.replace(tmp_path, path)
        # Best-effort: 限制为仅所有者可读写（Windows 下 chmod 可能不生效，忽略错误）
        with contextlib.suppress(Exception):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    @classmethod
    def load(cls, path: Path) -> ModelStore:
        """从文件加载；文件不存在时返回空 store。"""
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls.from_dict(raw)

    # =========================================================================
    # CRUD
    # =========================================================================

    def _allocate_entry_id(self, preset_id: str) -> str:
        """分配一个新的 entry_id。第一个实例用 "<preset>-default"，后续为 "<preset>-1"、"<preset>-2"..."""
        suffix_candidate = f"{preset_id}-default"
        if suffix_candidate not in self.providers:
            return suffix_candidate
        i = 1
        while f"{preset_id}-{i}" in self.providers:
            i += 1
        return f"{preset_id}-{i}"

    def add_provider(
        self,
        preset_id: str,
        *,
        display_name: str | None = None,
        base_url: str | None = None,
        api_key: str = "",
        custom_models: list[str] | None = None,
        entry_id: str | None = None,
        status: ProviderStatus = "unconfigured",
        status_message: str = "",
    ) -> str:
        """添加一个新的提供商实例，返回 entry_id。

        未指定 entry_id 时自动分配。未指定 display_name/base_url 时使用预设默认值。
        添加后如果当前 active_profile 为空，**不**自动设置（由 UI 决定默认逻辑）。
        """
        preset = get_preset(preset_id)
        if entry_id is None:
            entry_id = self._allocate_entry_id(preset_id)
        if entry_id in self.providers:
            raise ValueError(f"entry_id 已存在: {entry_id}")
        effective_base = base_url if base_url is not None else (preset.base_url or "")
        self.providers[entry_id] = ProviderEntry(
            preset_id=preset_id,
            display_name=display_name or preset.label,
            base_url=effective_base,
            api_key=api_key,
            custom_models=list(custom_models or []),
            status=status,
            status_message=status_message,
        )
        return entry_id

    def remove_provider(self, entry_id: str) -> None:
        """删除一个提供商实例。若其为 active 则清空 active_profile_id。"""
        self.providers.pop(entry_id, None)
        if self.active_profile_id and self.active_profile_id.startswith(f"{entry_id}:"):
            self.active_profile_id = None
        # 清理 active_profile_id 指向不存在 entry 的悬空引用
        if self.active_profile_id:
            eid = self.active_profile_id.split(":", 1)[0]
            if eid not in self.providers:
                self.active_profile_id = None

    def add_custom_model(self, entry_id: str, model_name: str) -> None:
        entry = self.providers.get(entry_id)
        if entry is None:
            raise KeyError(f"entry_id 不存在: {entry_id}")
        model_name = model_name.strip()
        if model_name and model_name not in entry.custom_models:
            entry.custom_models.append(model_name)

    def remove_custom_model(self, entry_id: str, model_name: str) -> None:
        entry = self.providers.get(entry_id)
        if entry is None:
            return
        if model_name in entry.custom_models:
            entry.custom_models.remove(model_name)

    def list_models(self, entry_id: str) -> list[str]:
        entry = self.providers.get(entry_id)
        if entry is None:
            return []
        return entry.all_models()

    # =========================================================================
    # 活跃配置
    # =========================================================================

    def configured_providers(self) -> dict[str, ProviderEntry]:
        """返回已连接可用（status == ok）的提供商字典。"""
        return {k: v for k, v in self.providers.items() if v.status == "ok"}

    def set_active_profile(self, entry_id: str, model_name: str) -> None:
        if entry_id not in self.providers:
            raise KeyError(f"entry_id 不存在: {entry_id}")
        self.active_profile_id = f"{entry_id}:{model_name}"

    def get_active_profile(self) -> ModelProfile | None:
        if not self.active_profile_id:
            return None
        return self._parse_profile_id(self.active_profile_id)

    def get_profile(self, entry_id: str, model_name: str) -> ModelProfile:
        entry = self.providers.get(entry_id)
        if entry is None:
            raise KeyError(f"entry_id 不存在: {entry_id}")
        return ModelProfile(
            provider_entry_id=entry_id,
            model_name=model_name,
            display_name=model_name,
            base_url=entry.effective_base_url(),
            api_key=entry.api_key,
            supports_structured_output=entry.supports_structured_output(),
        )

    def _parse_profile_id(self, profile_id: str) -> ModelProfile | None:
        if ":" not in profile_id:
            return None
        entry_id, _, model_name = profile_id.partition(":")
        if entry_id not in self.providers:
            return None
        return self.get_profile(entry_id, model_name)

    # =========================================================================
    # 从 .env 迁移
    # =========================================================================

    @classmethod
    def migrate_from_env(cls, env_config: ModelConfig) -> ModelStore:
        """从 .env 加载的 ModelConfig 创建初始 store。

        - 按 base_url 检测匹配的 preset
        - 创建一个默认 entry（entry_id = "<preset>-default"）
        - 若 API Key 存在则标记 status=ok；否则 unconfigured
        - 若 env 指定了 LLM_MODEL 且该模型不在预设列表里，自动加入 custom_models
        - 自动设为 active_profile
        """
        store = cls()
        preset_id = detect_preset_by_base_url(env_config.base_url)
        preset = get_preset(preset_id)

        entry_base_url = env_config.base_url or ""
        # 如果 preset 的 base_url 与 env base_url 相同，可在 entry 中存空（使用 preset 默认）
        if preset.base_url is not None and env_config.base_url == preset.base_url:
            entry_base_url = ""

        # 确定模型名
        model_name = env_config.model_name or preset.default_model
        custom_models: list[str] = []
        if model_name and model_name not in preset.preset_models:
            custom_models.append(model_name)

        # 确定状态
        has_key = bool(env_config.api_key)
        if not preset.api_key_required:
            status: ProviderStatus = "ok"
            status_msg = ""
        elif has_key:
            status = "ok"
            status_msg = "已从 .env 迁移"
        else:
            status = "unconfigured"
            status_msg = "请在「模型设置」中填写 API Key"

        entry_id = store.add_provider(
            preset_id,
            base_url=entry_base_url,
            api_key=env_config.api_key or "",
            custom_models=custom_models,
            status=status,
            status_message=status_msg,
        )

        if model_name and status == "ok":
            store.set_active_profile(entry_id, model_name)

        return store


def _valid_status(value: object) -> ProviderStatus:
    if value in ("ok", "error", "unconfigured"):
        return value  # type: ignore[return-value]
    return "unconfigured"

"""模型提供商管理 —— 将 provider CRUD 逻辑从 AppState 中分离。

本模块提供 ProviderMixin，包含:
    - refresh_providers / show_add_provider
    - add_provider / remove_provider / test_provider_connection
    - set_selected_model / set_setting_* 表单 setter

使用方式:
    class AppState(StreamingMixin, ProviderMixin, rx.State):
        ...
"""

import sys

from socratic_loop.infra.connection_test import check_connection
from socratic_loop.infra.providers import get_preset

from . import _globals


class ProviderMixin:
    """模型提供商管理 Mixin —— 为 AppState 提供 provider CRUD 能力。

    前置条件: 宿主类需定义 providers_list / setting_* 字段和
    selected_model_id 字段。
    """

    def refresh_providers(self):
        """将 _model_store 数据镜像到 UI 状态。"""
        store = _globals._model_store
        if store is None:
            return
        result = []
        for eid, entry in store.configured_providers().items():
            preset_models = list(entry.preset().preset_models)
            result.append({
                "entry_id": eid,
                "preset_id": entry.preset_id,
                "label": entry.display_name,
                "base_url": entry.base_url or entry.preset().base_url or "",
                "status": entry.status,
                "status_msg": entry.status_message,
                "models": preset_models + list(entry.custom_models),
            })
        self.providers_list = result

    def show_add_provider(self):
        """切换添加提供商表单的显示状态并重置表单字段。"""
        self.setting_show_add = not self.setting_show_add
        self.setting_new_preset = "deepseek"
        self.setting_new_name = ""
        self.setting_new_key = ""
        self.setting_new_url = ""

    def add_provider(self):
        """添加新的模型提供商实例。"""
        store = _globals._model_store
        if store is None:
            return
        try:
            preset = get_preset(self.setting_new_preset)
            store.add_provider(
                preset_id=self.setting_new_preset,
                display_name=self.setting_new_name.strip() or preset.label,
                base_url=self.setting_new_url.strip(),
                api_key=self.setting_new_key.strip(),
            )
            store.save(_globals.MODEL_CONFIG_PATH)
            if not self.selected_model_id and preset.preset_models:
                profile = store.get_active_profile()
                if profile:
                    self.selected_model_id = profile.model_name
            self.setting_show_add = False
            self.refresh_providers()
        except Exception as exc:
            print(f"[add_provider] error: {exc}", file=sys.stderr)

    def remove_provider(self, entry_id: str):
        """删除指定提供商实例。"""
        store = _globals._model_store
        if store is None:
            return
        try:
            store.remove_provider(entry_id)
            store.save(_globals.MODEL_CONFIG_PATH)
            self.refresh_providers()
        except Exception:
            import traceback
            traceback.print_exc(file=sys.stderr)

    def test_provider_connection(self, entry_id: str):
        """测试指定提供商的 API 连通性并更新状态。"""
        store = _globals._model_store
        if store is None:
            return
        try:
            provider = store.configured_providers().get(entry_id)
            if provider is None:
                return
            result = check_connection(
                base_url=provider.effective_base_url(),
                api_key=provider.api_key,
                provider_id=provider.preset_id,
            )
            provider.status = "ok" if result.ok else "error"
            provider.status_message = result.message
            store.save(_globals.MODEL_CONFIG_PATH)
            self.refresh_providers()
        except Exception:
            import traceback
            traceback.print_exc(file=sys.stderr)

    # ── 表单 setter ──

    def set_selected_model(self, model_name: str):
        self.selected_model_id = model_name

    def set_setting_preset(self, value: str):
        self.setting_new_preset = value

    def set_setting_name(self, value: str):
        self.setting_new_name = value

    def set_setting_key(self, value: str):
        self.setting_new_key = value

    def set_setting_url(self, value: str):
        self.setting_new_url = value

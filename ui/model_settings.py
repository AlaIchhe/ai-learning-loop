"""
模型设置页面 —— 提供商管理与默认模型选择。

作为 st.Page 的 callable 传入，与 ui/app.py 共享 st.session_state。
提供 Dify 风格的提供商列表、连接测试、添加/编辑/删除、自定义模型管理。
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.connection_test import check_connection
from core.model import load_model_config
from core.model_store import ModelProfile, ModelStore, ProviderEntry
from core.providers import iter_presets

#: 模型配置持久化文件路径（相对于项目根目录）
MODEL_CONFIG_FILENAME = ".model-config.json"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _config_path() -> Path:
    return _project_root() / MODEL_CONFIG_FILENAME


def _get_store() -> ModelStore:
    """获取或初始化持久化的 ModelStore（存入 st.session_state）。

    首次调用时：
    - 若 .model-config.json 存在 → 从磁盘加载
    - 否则从当前 .env 配置迁移并保存
    """
    if "model_store" not in st.session_state:
        path = _config_path()
        if path.exists():
            st.session_state["model_store"] = ModelStore.load(path)
        else:
            # 首次启动：从 .env 环境迁移
            store = ModelStore.migrate_from_env(load_model_config())
            store.save(path)
            st.session_state["model_store"] = store
    return st.session_state["model_store"]


def _save_store() -> None:
    """将当前 store 持久化到磁盘。"""
    store = st.session_state.get("model_store")
    if isinstance(store, ModelStore):
        store.save(_config_path())


def _status_icon(status: str) -> str:
    return {"ok": "🟢", "error": "🔴", "unconfigured": "⚪"}.get(status, "⚪")


def _parse_active_id(active_id: str | None) -> tuple[str | None, str | None]:
    if not active_id or ":" not in active_id:
        return None, None
    eid, _, mname = active_id.partition(":")
    return eid, mname


def _make_preset_format(preset_options: list[str]):
    """创建 selectbox 的 format_func（避免 lambda 被 pyright 报 unknown 类型）。"""
    def _fmt(i: int) -> str:
        return preset_options[i]
    return _fmt


# =============================================================================
# 添加提供商表单（expander）
# =============================================================================


def _render_add_provider_form(store: ModelStore) -> None:
    """渲染添加新提供商的 expander 表单。"""
    presets = list(iter_presets())
    preset_options = [f"{p.icon} {p.label}" for p in presets]

    with st.expander("➕ 添加模型提供商", expanded=not store.providers):
        selected_idx = st.selectbox(
            "选择提供商",
            range(len(presets)),
            format_func=_make_preset_format(preset_options),
            key="ms_add_preset_idx",
        )
        preset = presets[selected_idx]

        display_name = st.text_input(
            "显示名称", value=preset.label, key="ms_add_display_name"
        )

        # base_url: 有固定预设且不是 custom → 不可编辑；custom 必须填；其他用默认
        if preset.id == "custom":
            base_url_value = st.text_input(
                "API Base URL",
                value="",
                placeholder="https://api.example.com/v1",
                key="ms_add_base_url",
                help="OpenAI 兼容端点的根 URL（含 /v1 后缀）",
            )
        elif preset.base_url is None:
            # OpenAI 官方
            st.caption("API Base URL: `https://api.openai.com/v1`（官方端点）")
            base_url_value = ""
        else:
            base_url_value = st.text_input(
                "API Base URL",
                value=preset.base_url,
                key="ms_add_base_url",
                help="可修改为你的代理/中转地址",
            )

        if preset.api_key_required:
            api_key_value = st.text_input(
                "API Key",
                type="password",
                placeholder=preset.api_key_placeholder,
                key="ms_add_api_key",
                help=f"[获取 API Key]({preset.api_key_help_url})" if preset.api_key_help_url else None,
            )
        else:
            st.caption("此提供商无需 API Key（本地部署）。")
            api_key_value = ""

        col_test, col_add = st.columns(2)
        if col_test.button("🔍 测试连接", key="ms_add_test", use_container_width=True):
            with st.spinner("测试连接中…"):
                result = check_connection(
                    base_url_value or None,
                    api_key_value,
                    provider_id=preset.id,
                )
            if result.ok:
                st.success(result.message)
            else:
                st.error(result.message)

        if col_add.button("✅ 添加并保存", type="primary", key="ms_add_add", use_container_width=True):
            # 校验
            if preset.id == "custom" and not base_url_value.strip():
                st.error("自定义提供商必须填写 Base URL。")
                return
            if preset.api_key_required and not api_key_value.strip():
                st.error("请填写 API Key。")
                return

            # 添加
            entry_id = store.add_provider(
                preset.id,
                display_name=display_name.strip() or preset.label,
                base_url=base_url_value,
                api_key=api_key_value,
            )
            # 添加后自动测试连接以设置状态
            if not preset.api_key_required or api_key_value.strip():
                with st.spinner("验证连接中…"):
                    result = check_connection(
                        base_url_value or None,
                        api_key_value,
                        provider_id=preset.id,
                    )
                    entry = store.providers[entry_id]
                    entry.status = "ok" if result.ok else "error"
                    entry.status_message = result.message

            # 如果是第一个可用提供商，自动激活第一个模型
            active = store.get_active_profile()
            entry = store.providers[entry_id]
            if active is None and entry.status == "ok":
                models = entry.all_models()
                if models:
                    store.set_active_profile(entry_id, models[0])
                else:
                    st.info("提供商已添加。请先添加模型（在编辑面板中），然后设为默认。")

            _save_store()
            st.rerun()


# =============================================================================
# 提供商卡片渲染
# =============================================================================


def _render_provider_card(store: ModelStore, entry_id: str, entry: ProviderEntry) -> None:
    """渲染单个已配置提供商的卡片。"""
    preset = entry.preset()
    active_eid, active_model = _parse_active_id(store.active_profile_id)
    is_active = entry_id == active_eid

    with st.container(border=True):
        col1, col2, col3 = st.columns([6, 1, 1])
        with col1:
            status_ic = _status_icon(entry.status)
            st.markdown(f"**{preset.icon} {entry.display_name}** {status_ic}")
            effective_base = entry.effective_base_url() or "https://api.openai.com/v1 (OpenAI 官方)"
            st.caption(f"端点：`{effective_base}`")
            if entry.status == "error" and entry.status_message:
                st.error(f"⚠️ {entry.status_message}")
            elif not entry.api_key and preset.api_key_required:
                st.warning("⚪ 尚未配置 API Key")
            if is_active:
                st.caption(f"✓ 当前默认（模型：`{active_model}`）")

        with col2:
            if st.button("✏️", key=f"ms_edit_{entry_id}", help="编辑此提供商"):
                st.session_state[f"ms_editing_{entry_id}"] = \
                    not st.session_state.get(f"ms_editing_{entry_id}", False)
        with col3:
            if st.button("🗑️", key=f"ms_del_{entry_id}", help="删除此提供商"):
                store.remove_provider(entry_id)
                _save_store()
                st.rerun()

        # 模型列表
        all_models = entry.all_models()
        if all_models:
            shown = all_models[:8]
            extra = "…" if len(all_models) > 8 else ""
            st.caption("模型：" + "、".join(f"`{m}`" for m in shown) + extra)
        else:
            st.caption("尚未配置模型（请在编辑面板中添加自定义模型）。")

        # 设为默认按钮（仅 ok 状态且有模型）
        if entry.status == "ok" and all_models:
            if not is_active:
                if st.button("⭐ 设为默认", key=f"ms_activate_{entry_id}"):
                    store.set_active_profile(entry_id, all_models[0])
                    _save_store()
                    st.rerun()
            elif len(all_models) > 1:
                # 已激活时允许切换模型
                new_model = st.selectbox(
                    "默认模型",
                    all_models,
                    index=all_models.index(active_model) if active_model in all_models else 0,
                    key=f"ms_switch_model_{entry_id}",
                    label_visibility="collapsed",
                )
                if new_model != active_model:
                    store.set_active_profile(entry_id, new_model)
                    _save_store()
                    st.rerun()

        # 编辑面板
        if st.session_state.get(f"ms_editing_{entry_id}"):
            with st.form(key=f"ms_edit_form_{entry_id}"):
                st.subheader(f"编辑 {preset.label}")
                new_display = st.text_input("显示名称", value=entry.display_name)
                if preset.id == "custom" or preset.base_url is not None:
                    new_base = st.text_input(
                        "API Base URL",
                        value=entry.base_url or (preset.base_url or ""),
                    )
                else:
                    new_base = entry.base_url
                    st.caption("API Base URL：OpenAI 官方端点")
                if preset.api_key_required:
                    new_key = st.text_input(
                        "API Key",
                        type="password",
                        value=entry.api_key,
                        placeholder=preset.api_key_placeholder,
                    )
                else:
                    new_key = ""

                st.caption("自定义模型（适用于 Ollama、微调模型等）")
                to_remove: list[str] = []
                for cm in entry.custom_models:
                    cols = st.columns([8, 1])
                    cols[0].markdown(f"- `{cm}`")
                    if cols[1].form_submit_button("🗑️", key=f"ms_del_cm_{entry_id}_{cm}"):
                        to_remove.append(cm)
                for cm in to_remove:
                    entry.custom_models.remove(cm)
                new_cm = st.text_input(
                    "添加自定义模型",
                    key=f"ms_add_cm_{entry_id}",
                    placeholder="例如 llama3.1 或 ft:gpt-4o-mini:org:xxx",
                )

                col_t, col_s, col_c = st.columns(3)
                test_clicked = col_t.form_submit_button("🔍 测试连接")
                save_clicked = col_s.form_submit_button("💾 保存", type="primary")
                cancel_clicked = col_c.form_submit_button("取消")

                if cancel_clicked:
                    st.session_state.pop(f"ms_editing_{entry_id}", None)
                    st.rerun()

                if test_clicked:
                    result = check_connection(
                        new_base or None, new_key, provider_id=preset.id,
                    )
                    if result.ok:
                        st.success(result.message)
                    else:
                        st.error(result.message)

                if save_clicked:
                    entry.display_name = new_display.strip() or preset.label
                    entry.base_url = new_base or ""
                    entry.api_key = new_key
                    if new_cm and new_cm.strip() and new_cm.strip() not in entry.custom_models:
                        entry.custom_models.append(new_cm.strip())
                    # 测试连接更新状态
                    if not preset.api_key_required or new_key.strip():
                        result = check_connection(
                            new_base or None, new_key, provider_id=preset.id,
                        )
                        entry.status = "ok" if result.ok else "error"
                        entry.status_message = result.message
                    else:
                        entry.status = "unconfigured"
                        entry.status_message = ""
                    # 若当前激活但模型被删除，重置激活
                    aeid, am = _parse_active_id(store.active_profile_id)
                    if aeid == entry_id and am not in entry.all_models():
                        models = entry.all_models()
                        if models:
                            store.set_active_profile(entry_id, models[0])
                        else:
                            store.active_profile_id = None
                    _save_store()
                    st.session_state.pop(f"ms_editing_{entry_id}", None)
                    st.rerun()


# =============================================================================
# 主页面入口
# =============================================================================


def render_model_settings_page() -> None:
    """模型设置页面主渲染函数（作为 st.Page 目标）。"""
    st.title("🔧 模型设置")
    st.caption("管理 LLM 提供商、API Key 和默认模型。配置自动保存，重启后保留。")

    store = _get_store()
    profile: ModelProfile | None = store.get_active_profile()

    # 顶部当前默认模型
    if profile is not None:
        entry = store.providers.get(profile.provider_entry_id)
        if entry is not None:
            preset = entry.preset()
            st.info(
                f"**当前默认模型：** {preset.icon} {entry.display_name} "
                f"→ `{profile.model_name}`"
            )
    else:
        st.warning("尚未设置默认模型。请添加一个提供商并设为默认后开始辩论。")

    st.caption("此默认模型将用于所有**新启动的辩论**。运行中的辩论使用启动时的配置，不受影响。")
    st.divider()

    # 添加提供商
    _render_add_provider_form(store)

    st.divider()

    # 已配置提供商列表
    st.subheader(f"已配置的提供商 ({len(store.providers)})")
    if not store.providers:
        st.caption("尚未配置任何提供商。请使用上方表单添加。")
    else:
        for entry_id, entry in store.providers.items():
            _render_provider_card(store, entry_id, entry)


if __name__ == "__main__":
    # 允许直接运行（调试/快速预览）
    from core.env import setup_environment
    setup_environment(_project_root(), verbose=False)
    st.set_page_config(page_title="模型设置", page_icon="🔧", layout="wide")
    render_model_settings_page()

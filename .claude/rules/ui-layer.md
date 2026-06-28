---
description: ui/ 展现层 — Streamlit 纯渲染 + 主题系统 + 多页面导航
paths:
  - "ui/**"
  - ".streamlit/**"
---

# UI Layer — Pure Rendering + Theme

Four files, four responsibilities:

## `app.py` — Streamlit UI (rendering + input only, ZERO business logic)

Multi-page navigation via `st.navigation` / `st.Page`:
- **💬 辩论 page** (`render_chat_page`): main debate interface (default)
- **🔧 模型设置 page** (`render_model_settings_page` from `ui/model_settings.py`)

Shared sidebar rendered before `pg.run()` so it appears on both pages.

State stores:
- **`st.session_state`**: UI metadata — `sessions` tab registry, `checkpointer`, `graph`, `model_store` (ModelStore instance)
- **`.model-config.json`**: persisted model/provider configuration (atomic writes via ModelStore.save)
- **LangGraph `MemorySaver`**: actual learning session state, read-only via `graph.get_state(config)`

Key patterns:
- **Multi-tab**: Shared `MemorySaver` + compiled graph, different `thread_id` per tab, widget key namespacing
- **Per-tab model isolation**: `_capture_model_config()` freezes {model_name, base_url, api_key, json_mode} from ModelStore at debate start → `_model_api_key`/`_model_json_mode` fields in AgentState
- **First-run migration**: if `.model-config.json` doesn't exist, `ModelStore.migrate_from_env(load_model_config())` auto-imports `.env` settings
- **Streaming**: Flag-based `pending_start`/`pending_resume` decoupling; `graph.stream()` in main render thread
- **Error boundary**: Categorized Chinese-language error messages + checkpoint retry
- **Sidebar model selector**: cascaded selectboxes (provider → model), writes `active_profile_id` to ModelStore and saves to disk

Key functions: `_render_sidebar()`, `_capture_model_config()`, `_get_store()`, `_save_store()`, `_render_tab_content()`, `_run_stream()`, `_render_conversation()`, `_render_interrupt_ui()`, `_execute_stream_start()`, `_execute_stream_resume()`, tab lifecycle functions, `main()`.

## `model_settings.py` — Model Management Page (`render_model_settings_page`)

Dify-style provider management panel:
- **Add provider form** (expander): preset selector → display name → base URL → API key → "🔍 Test connection" / "✅ Add and save"
- **Provider cards** (bordered containers): icon + name + status dot (🟢/🔴/⚪), endpoint, error/needs-key warnings, edit/delete buttons, "⭐ Set as default", inline model switcher for active providers
- **Edit form**: display name, base URL, API key, custom model add/remove, test connection, save, cancel
- Connection test calls `check_connection()` on demand (on add and on save)
- All mutations go through ModelStore CRUD and `_save_store()` persists to disk
- Does NOT access LangGraph or session state beyond `model_store`

Exports: `MODEL_CONFIG_FILENAME`, `render_model_settings_page` (callable passed to `st.Page`).

## `style.py` — Global Style Injection

- `inject_global_css()` — loads `ui/style.css` + injects auto-scroll JavaScript. Cached via `st.session_state["_css_injected"]`. Called once in `render_chat_page()`.
- `typing_cursor_html()` — returns `<span class="typing-cursor">▍</span>` for blink animation during streaming.

## `style.css` — Global Stylesheet

Fonts (Inter + PingFang SC), message bubbles (12px radius, shadow), button hover animation (`cubic-bezier` lift), input focus rings (3px glow), expander rounded + hover, sidebar, scrollbar, metric cards, dark mode overrides, `@keyframes blink-cursor` (1s step-end), `.chat-timestamp`, hides Streamlit default toolbar.

## Theme Architecture (Three-Layer)

| Layer | File | Role |
|-------|------|------|
| 1 | `.streamlit/config.toml` | Brand colors, `[theme.light]`/`[theme.dark]` dual themes, base font |
| 2 | `ui/style.css` | Custom component styles, animations, dark mode overrides |
| 3 | Native properties | `type="primary"`, `use_container_width=True` |

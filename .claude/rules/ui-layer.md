---
description: ui/ 展现层 — Streamlit 纯渲染 + 主题系统（3 文件）
paths:
  - "ui/**"
  - ".streamlit/**"
---

# UI Layer — Pure Rendering + Theme

Three files, three responsibilities:

## `app.py` — Streamlit UI (rendering + input only, ZERO business logic)

Two separate state stores:
- **`st.session_state`**: UI metadata only — `sessions` tab registry, `checkpointer`, `graph`, `api_key`
- **LangGraph `MemorySaver`**: actual learning session state, read-only via `graph.get_state(config)`

Key patterns:
- **Multi-tab**: Shared `MemorySaver` + compiled graph, different `thread_id` per tab, widget key namespacing
- **Per-tab model isolation**: `_capture_model_config()` freezes config at debate start
- **Streaming**: Flag-based `pending_start`/`pending_resume` decoupling; `graph.stream()` in main render thread
- **Error boundary**: Categorized Chinese-language error messages + checkpoint retry
- **Flow**: Button → `pending_start` → `st.rerun()` → `graph.stream()` → `GraphInterrupt` → interrupt UI → `Command(resume=...)` → next interrupt or END

Key functions: `_render_sidebar()`, `_capture_model_config()`, `_render_tab_content()`, `_run_stream()`, `_render_conversation()`, `_render_interrupt_ui()`, `_execute_stream_start()`, `_execute_stream_resume()`, tab lifecycle functions.

## `style.py` — Global Style Injection

- `inject_global_css()` — loads `ui/style.css` + injects auto-scroll JavaScript. Cached via `st.session_state["_css_injected"]`. Called once in `main()`.
- `typing_cursor_html()` — returns `<span class="typing-cursor">▍</span>` for blink animation during streaming.

## `style.css` — Global Stylesheet (282 lines, 15 sections)

Fonts (Inter + PingFang SC), message bubbles (12px radius, shadow), button hover animation (`cubic-bezier` lift), input focus rings (3px glow), expander rounded + hover, sidebar, scrollbar, metric cards, dark mode overrides, `@keyframes blink-cursor` (1s step-end), `.chat-timestamp`, hides Streamlit default toolbar.

## Theme Architecture (Three-Layer)

| Layer | File | Role |
|-------|------|------|
| 1 | `.streamlit/config.toml` | Brand colors, `[theme.light]`/`[theme.dark]` dual themes, base font |
| 2 | `ui/style.css` | Custom component styles, animations, dark mode overrides |
| 3 | Native properties | `type="primary"`, `use_container_width=True` |

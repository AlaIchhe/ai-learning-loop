---
description: web/ 展现层 — Reflex 响应式UI + 状态管理 + 多Tab
paths:
  - "web/**"
  - "rxconfig.py"
---

# UI Layer — Reflex Reactive UI

## `rxweb/rxweb.py` — App Entry

Creates `rx.App` with routes `/` (chat) and `/settings` (model settings).

## `rxweb/state.py` — AppState

Core reactive state managing multi-tab sessions, LangGraph streaming, and provider CRUD.
- **Multi-tab**: `tabs: list[dict]` with mirrored `active_*` fields for UI access
- **LangGraph**: `_stream()` runs `graph.astream()` pushes tokens via `_update_tab` + `_sync_active`
- **Interrupt detection**: `graph.get_state(config)` after stream to check `status` field
- **Background tasks**: `@rx_event(background=True)` for `start_debate` / `submit_user_response`
- **Provider CRUD**: `add_provider`, `remove_provider`, `test_provider_connection`

## `rxweb/chat.py` — Chat Page

- `sidebar()`: tab list, add/close buttons, model settings link, dark mode toggle
- `start_view()`: topic input, temperature slider
- `active_chat_view()`: messages, interrupt prompt, response textarea
- `message_bubble()`: role avatars via `rx.match`, markdown, typing cursor

## `rxweb/model_settings.py` — Model Settings Page

Provider list + add form with preset selector, API key, base URL.

## `rxweb/styles.py` — Global Styles

Color system, message bubbles, animations, sidebar, input area, scrollbar, role config.

## `rxconfig.py` — Reflex Config

`transport="polling"` (Windows), `RadixThemesPlugin`, ports 3003/8003.

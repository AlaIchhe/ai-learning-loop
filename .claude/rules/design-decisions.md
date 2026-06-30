---
description: 关键设计决策 — Compute/Interact 拆分、拼合式演化、双策略引导者、UI 主题系统等
---

# Key Design Decisions

- **Compute/Interact split**: Each agent with an `interrupt()` is split into compute (LLM) + interact (human I/O) nodes. This prevents LLM re-execution on resume — compute nodes complete fully and are checkpointed before the interact node starts.
- **Shared LLM utilities (`agents/_base.py`)**: `extract_content()`, `make_message()`, `invoke_llm()`, `invoke_with_retry()`, and `_is_retryable()` eliminate 3×/6×/2× code duplication. All LLM calls go through `invoke_with_retry()` with 3-retry exponential backoff (1s/2s/4s).
- **Centralized API key detection (env path)**: `core.model` provides `load_model_config(env)` → `ModelConfig` and `has_configured_api_key(env)` for scripts and `.env` migration. Runtime model selection flows through `core.model_store.ModelStore`. `sk-not-configured` placeholder is consistently treated as missing.
- **State factory + runtime validation**: `core.state.make_initial_state(thesis)` is the single authoritative entry-state factory. `validate_state_shape(state)` at workflow entry catches malformed states before agent nodes.
- **Accretive understanding model**: `current_thesis` grows by accretion, not replacement. The guide layers new cognitive insights onto the user's original perspective. One sentence → one paragraph.
- **Guide silence during normal rounds**: The guide does NOT produce user-visible messages when `continue_debate=True`. It only updates `current_thesis` and routes. `improvement_hint` feeds forward to the next round's questioner via `_improvement_hint` cache field.
- **Guide dual strategy**: `with_structured_output` (OpenAI native) vs JSON-mode prompting + regex extraction + Pydantic validation (DeepSeek). Selectable via `json_mode` parameter OR automatically from `AgentState._model_json_mode` (frozen from `ModelProfile.supports_structured_output` at debate start). Explicit `json_mode=True` kwarg takes precedence.
- **Guide helper extraction**: `_build_round_record()` constructs `RoundRecord`; `_dump_round_record()` normalizes for JSON serialization.
- **Socratic questioning of boundaries**: The questioner probes the topic's weakest boundary or unstated assumption. Three strategies: logical exploration / boundary clarification / counterexample probing. Single-point, ≤80 chars.
- **Dynamic `interrupt()` only**: No `interrupt_before` configuration. Human interaction via `interrupt(value)` + `Command(resume=user_value)`.
- **Guide + safety valve termination**: `continue_debate: bool` + `max_rounds` force-terminate in `_route_after_referee` when `round >= max_rounds`.
- **`messages` is a plain `list`, not `add_messages`**: LangChain's reducer rejects custom roles. Agents append manually via `make_message()`.
- **Only `next_round_node` touches `round`**: Agents never increment the round counter — pure scheduling concern.
- **Provider-agnostic typing**: All agent function signatures use `BaseChatModel`, not `ChatOpenAI`.
- **Schemas enforce strict validation**: `_StrictModel` base class with `ConfigDict(extra='forbid')`. `round` field removed from `RefereeJudgment`.
- **Unified environment initialization**: `core/env.py` `setup_environment()` is the single entry point for all entry points.
- **Shared test infrastructure**: `tests/helpers.py` and `tests/mock_nodes.py` eliminate quadruple duplication.
- **`checkpointer` injected at graph build time**: `build_graph()` accepts it as a parameter.
- **Multi-provider via ModelStore**: Runtime model selection flows through `core.model_store.ModelStore` (persisted to `.model-config.json`), supporting multiple providers side-by-side with per-tab frozen isolation. Adding a new preset provider is a `ProviderPreset` entry in `core/providers.py`. Env-var path preserved for scripts/backward compatibility (`get_chat_model()` still reads `LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY` when called without explicit kwargs).
- **Static analysis enforced**: Ruff (lint), pyright (strict mode on `socratic_loop/`), and mypy (on `socratic_loop/core|agents|infra|workflow`) all pass with zero issues. `web/` and `tests/` are excluded from strict pyright due to Reflex metaclass limitations — they rely on ruff + runtime tests.
- **CI gate**: push/PR triggers automatic pytest + ruff + pyright + mypy without real API keys.
- **Type annotation policy**: All new public APIs in `socratic_loop/` must have full type annotations (params + return). Use `from __future__ import annotations` for forward references. `TYPE_CHECKING` guard for circular imports. `Protocol` for duck-typed interfaces (e.g. `_Invocable`). Minimize `Any` — use `cast()` with comment when interfacing with untyped third-party code (langchain stubs).
- **Multi-tab via shared graph**: One `MemorySaver` + compiled graph serve all tabs. Each tab gets a unique `thread_id`. Reflex state mirrors active tab via `_sync_active()`.
- **Streaming via async background tasks**: `@rx_event(background=True)` runs LangGraph streaming in background. Token updates pushed via `async with self` state mutations. No flag-based decoupling needed.
- **Configurable agent temperature**: `agent_temperature` (0.0–1.5, default 0.7) stored in `AgentState`. Referee stays at 0.0.
- **Per-tab model config isolation**: Model name/base URL/api key/json_mode frozen per-tab at debate start via `_model_cfg()` from `ModelStore.get_active_profile()`. Uses `_model_api_key` field for true key isolation.
- **Structured logging with trace IDs**: `trace_id_context()` + `TraceLogger` record LLM call timing, retry counts, error records. JSON-lines output format.
- **Streaming error boundary**: `_stream()` catches `GraphInterrupt` for normal pauses, logs other exceptions.
- **Tab checkpoint cleanup**: `remove_tab()` deletes the tab's `thread_id` from `MemorySaver.storage`.
- **Provider preset registry**: `core/providers.py` holds pure-data `ProviderPreset` entries (8 built-in). `supports_structured_output=False` triggers automatic JSON-mode.
- **Persistent model store**: `core/model_store.ModelStore` atomically saves to `.model-config.json`. First-run auto-migration from `.env`.
- **Connection test before save**: `check_connection()` (stdlib `urllib`) sets `ProviderEntry.status` to `ok`/`error` with Chinese diagnostic message.
- **UI theme system (`web/styles.py` + `web/assets/fonts.css`)**: Unified CSS-in-Python styling via Reflex `style` prop. Custom message bubbles, animations (`@keyframes blink-cursor`, `messageSlideIn`), sidebar, input area, scrollbar. Dark mode toggle via `AppState.dark_mode`. Typing cursor (`▍`) via CSS class. Auto-scroll via `rx.scroll_to()` anchor.
- **`rxconfig.py`**: Reflex config — `transport="polling"` (Windows granian WS not supported), `RadixThemesPlugin`, ports 3003/8003.

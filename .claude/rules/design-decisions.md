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
- **Static analysis enforced**: Ruff (lint), pyright (strict mode), and mypy all pass with zero issues.
- **CI gate**: push/PR triggers automatic pytest + ruff + pyright + mypy without real API keys.
- **Multi-tab via shared graph**: One `MemorySaver` + compiled graph serve all tabs. Each tab gets a unique `thread_id`.
- **Streaming via flag-based decoupling**: Button callbacks set `pending_start`/`pending_resume` flags; actual `graph.stream()` runs in the main render thread.
- **Configurable agent temperature**: `agent_temperature` (0.0–1.5, default 0.7) stored in `AgentState`. Referee stays at 0.0.
- **Per-tab model config isolation**: Model name/base URL/api key/json_mode frozen per-tab at debate start via `_capture_model_config()`. Sidebar changes only affect newly started debates. True key isolation via `_model_api_key` field (no more `os.environ` mutation).
- **Structured logging with trace IDs**: `trace_id_context()` + `TraceLogger` record LLM call timing, retry counts, error records. JSON-lines output format.
- **Streaming error boundary**: `_run_stream()` categorizes errors (auth/timeout/rate-limit/network/parse) with Chinese-language messages and checkpoint retry.
- **Tab checkpoint cleanup**: `_close_tab()` removes the tab's `thread_id` from `MemorySaver.storage` to prevent unbounded memory growth.
- **Provider preset registry**: `core/providers.py` holds pure-data `ProviderPreset` entries (8 built-in: openai/deepseek/siliconflow/tongyi/zhipu/moonshot/ollama/custom). `supports_structured_output=False` triggers automatic JSON-mode for the referee.
- **Persistent model store**: `core/model_store.ModelStore` atomically saves to `.model-config.json` (gitignored). First-run auto-migration from `.env` via `detect_preset_by_base_url()` heuristics.
- **Connection test before save**: Adding or editing a provider calls `check_connection()` (stdlib `urllib`) and sets `ProviderEntry.status` to `ok`/`error` with a Chinese diagnostic message.
- **UI theme system (`ui/style.py` + `ui/style.css` + `.streamlit/config.toml`)**: Three-layer styling architecture. Layer 1: `.streamlit/config.toml` — brand colors, `[theme.light]`/`[theme.dark]` dual themes. Layer 2: `ui/style.css` — custom component styles, animations, dark mode overrides, cursor blink keyframes. Layer 3: Streamlit native component properties. Auto-scroll JavaScript uses `MutationObserver` + user scroll detection. Typing cursor (`▍`) via CSS `@keyframes blink-cursor`. Toast notifications at lifecycle events; `st.balloons()` at completion (per-tab flag guarded). Message timestamps via `datetime.fromtimestamp()` with fallback for legacy messages.
- **Boy Scout — `make_message()` timestamp**: Now includes `timestamp` field (float, `time.time()`) for UI display — backward compatible.

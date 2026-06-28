# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Engineering Principles (MUST follow)

These principles govern every change to this codebase. No exceptions.

### 1. Boy Scout Rule
**Leave the code cleaner than you found it.** Each edit is an opportunity to improve: rename a vague variable, extract a magic number, add a missing docstring, delete dead code. The improvement must be minimal and obviously safe — if it risks breakage, it belongs in a separate PR.

### 2. Test-First & Characterization Tests
**Before modifying any behavior, write a test that pins the current behavior.** This applies even when the existing tests pass — write a *characterization test* that captures what the code actually does today. The test turns red only if your change breaks expectations. Existing mock-based tests (`tests/`) prove correctness in isolation; real-API tests (`scripts/`) prove correctness against the live provider. Both layers must pass.

### 3. Strangler Fig Pattern
**When replacing or refactoring a module, build the new implementation beside the old one, route to it incrementally, and delete the old code only after the new one has proven itself in production.** Never rip-and-replace. Always: build new → shadow or route incrementally → validate → delete old.

### 4. Small Commits + Verify After Each
**One logical change per commit. Run the full test suite after every commit.** The sequence is: make one change → `python -m pytest tests/ -v` (all mock tests must pass) → `ruff check .` (zero warnings) → commit. If any check fails, fix it before moving to the next change. Compound changes that touch multiple concerns are rejected — split them.

### 5. No Big Rewrites
**A big rewrite is forbidden unless you have: (a) a written plan approved by the user, (b) a characterization test suite that pins the current behavior, and (c) a rollback strategy.** "It felt simpler to start over" is not a valid reason. Incremental refactoring via Strangler Fig is always preferred.

### 6. Analyze Dependencies & Impact Before Every Change
**Before touching any file, answer these questions:**
- What other files import or depend on this module? (`grep -r "from core\.schemas import" .`)
- What downstream behavior relies on the current contract (function signature, return type, side effects)?
- If I change this, what tests will catch regressions? If the answer is "none," write the characterization test first.
- Who calls this function / reads this state field? Trace every call site.

When in doubt, spend the time to map the blast radius before making the edit. A 30-second grep that prevents a 2-hour debugging session is always worth it.

### 7. Learn from the Best Before Building UI
**Don't blindly build behind closed doors — first study how top-tier companies do it, then write code.** Before writing any UI component or interaction, research how the design leaders (Apple, OpenAI, Stripe, Linear, Vercel, Notion, etc.) handle similar patterns. Never invent UI from scratch without reference.

The workflow:
1. **Research first** — Search for English-language design patterns, open-source clones, and technical breakdowns. Use targeted queries like `"Apple style micro-interaction spring animation tailwind"` or `"OpenAI typewriter effect streaming UX"`. This is NOT about stealing commercial source code — it's about studying published design patterns and interaction models.
2. **Absorb the soul** — Extract the interaction logic that makes the experience feel premium: animation damping curves, breathing rhythm (timing/duration), error feedback micro-interactions, loading state choreography, focus/hover transition physics. These are the non-visual "bones" of the experience.
3. **Strip the skin, apply our own** — Implement the interaction mechanics using **our project's theme, color system, typography, and UI conventions**. The visual identity must be ours; the interaction quality should match the reference.
4. **Credit the inspiration** — In the commit message, note which company's feature inspired the interaction pattern: e.g., `"微交互灵感源自 Apple Messages 的 spring-animated send button"` or `"Loading skeleton pattern inspired by Linear's issue list"`.

Key search targets by category:
| Interaction Domain | Companies to Study |
|---|---|
| Micro-interactions & animation | Apple (spring physics), Linear (task transitions), Stripe (form feedback) |
| Streaming / real-time UI | OpenAI (typewriter/text streaming), Vercel (deploy log streaming) |
| Form & input UX | Stripe (checkout flow), Notion (rich text editing) |
| Loading & skeleton states | Linear, Vercel, Notion |
| Error & empty states | Stripe, GitHub (404/500 pages) |
| Navigation & layout | Apple (HIG patterns), Linear (keyboard-first nav) |

This principle applies to ALL frontend work — Streamlit widgets, HTML/CSS, Tailwind components, or any UI framework. A 15-minute research session before coding prevents hours of iterating toward what the industry already solved.

## Project Overview

A **Socratic learning guide** built with LangGraph. Three LLM agents — **Questioner** (提问者), **Refiner** (精确化者), and **Guide** (引导者) — iteratively deepen the user's understanding of a topic through Socratic questioning, collaborative refinement, and incremental synthesis. The user's understanding grows from an initial perspective into a well-scoped, multi-layered comprehension by accumulating cognitive layers each round. Human-in-the-loop control uses LangGraph's dynamic `interrupt()` + `Command(resume=...)` mechanism via a Streamlit UI. LangSmith provides full observability, and `core/model.py` enables switching between OpenAI, DeepSeek, and any OpenAI-compatible provider without code changes.

## Development Commands

```bash
source venv/Scripts/activate        # Activate virtual environment (Windows Git Bash)
# source venv/bin/activate          # macOS / Linux
pip install -e ".[dev]"            # Install runtime + development dependencies
cp .env.example .env                # Configure API keys (first time only)

# Testing (mock tests + real-API integration tests)
python -m pytest tests/ -v          # Mock LLM suite (no API needed)
python scripts/integration_test_real.py           # Real-API full suite (6 tests)
python scripts/integration_test_real.py --quick   # Real-API: single-agent only
python scripts/integration_test_real.py --workflow  # Real-API: LangGraph workflow only

# Ghost probe (live LLM environment diagnostics)
python scripts/ghost_probe.py       # Full: 7 probes (~1300 tokens)
python scripts/ghost_probe.py --quick  # Quick: env + connectivity only

# Code quality
ruff check .                        # Lint (zero warnings)
pyright .                           # Strict type check (zero errors)
mypy core/ agents/ workflow/ --ignore-missing-imports  # Type check (zero errors)

# Run the app (any of these work — all handle .env loading and path resolution)
python run.py                       # Universal launcher (recommended)
streamlit run ui/app.py             # Standard way (run from project root)

# Export graph architecture diagram
python run.py --export-graph        # → graph_architecture.png
python -m workflow.graph            # Equivalent
```

## Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Multi-provider LLM (pick one, leave others commented)
LLM_MODEL=deepseek-chat                          # or gpt-4o
LLM_BASE_URL=https://api.deepseek.com/v1         # omit for OpenAI
LLM_API_KEY=sk-your-key-here

# LangSmith tracing (optional; uncomment only with a real LangSmith key)
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=lsv2_pt_your-key
# LANGCHAIN_PROJECT=ai-learning-loop
```

The `LLM_API_KEY` falls back to `OPENAI_API_KEY` if not set. If neither is configured, `get_chat_model()` emits a `RuntimeWarning` with diagnostic instructions and uses a placeholder key — the real error surfaces when the LLM is first invoked.

## Project Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, dependencies, ruff/mypy/pyright/pytest config |
| `run.py` | Universal launcher — `python run.py` from any directory |
| `requirements.txt` | Runtime dependencies only (minimum version constraints; no dev tools) |
| `requirements-lock.txt` | Pinned dependency versions for reproducible deployments |

## Architecture: Four-Layer Separation

```
ui/app.py              ← Rendering + input only. ZERO business logic.
workflow/graph.py      ← Pure state routing. LLM nodes + checkpointer injected.
agents/{_base,opponent,presenter,referee}.py  ← Shared LLM tools + stateless pure functions (6 nodes) + dynamic interrupt(). These implement Socratic questioning, response refinement, and learning synthesis.
core/{env,state,schemas,prompts,model}.py     ← System contracts all layers depend on.
```

### 1. `core/` — Data Contracts (6 files)

**`env.py`** — `setup_environment(project_root, *, change_cwd, verbose)` — unified entry point for sys.path setup, `.env` loading, and optional cwd change. Used by `run.py` and all `scripts/*.py` to eliminate triplicate initialization code.

**`state.py`** — `AgentState(TypedDict)` with 15 fields (10 persistent + 5 round-cache), plus `NodeOutput = dict[str, object]` for node return types. Also exports `make_initial_state(thesis, *, agent_temperature, model_name, model_base_url, max_rounds)` — the single authoritative entry-state factory used by UI, scripts, and tests — and `validate_state_shape(state)` — runtime guard that rejects incomplete states before agent nodes.

| Group | Fields | Purpose |
|-------|--------|---------|
| Core topic | `current_thesis` | The ONLY persistent evolving content. Grows by accretion — the guide layers new cognitive insights onto the original core each round (one sentence → one paragraph), building the user's understanding through Socratic dialogue. |
| Round control | `round`, `agent_temperature`, `status`, `max_rounds` | State machine: `idle → opponent_computing → awaiting_critique_response → presenter_computing → awaiting_thesis_confirmation → referee_deliberating → done`. `agent_temperature` (0.0–1.5, default 0.7) controls Opponent and Presenter LLM creativity. `max_rounds` (default 10) is a safety valve — `_route_after_referee` force-terminates when `round >= max_rounds`. |
| Messages | `messages: list[dict]` | Custom roles (`opponent/user/presenter/referee`). Plain `list`, not `add_messages`. Append via `state["messages"] + [new_msg]`. |
| Per-tab config (`_` prefix, persistent) | `_model_name`, `_model_base_url` | Per-tab model overrides frozen at debate start from sidebar. NOT cleared by `next_round` node. Agent compute nodes read these and pass to `get_chat_model()` / `invoke_llm()` for provider isolation per tab. |
| Round cache (`_` prefix, ephemeral) | `_critique`, `_user_response`, `_draft_thesis`, `_confirmed_thesis`, `_improvement_hint` | Per-round ephemeral data. Cleared by `next_round` node (5 fields only — `_model_name` / `_model_base_url` are preserved). `_improvement_hint` feeds the guide's strategic direction forward to the next round's questioner. |
| Archive | `history: list[RoundRecord]`, `final_result` | Completed rounds + learning summary |

**`schemas.py`** — Pydantic v2 models with `_StrictModel` base class (`ConfigDict(extra='forbid')`). `RefereeJudgment` (with `continue_debate`/`new_thesis`/`reasoning`/`improvement_hint`) is the core contract — the guide uses this to decide whether to continue the learning session. `RoundRecord` archives each round (with `timestamp` field for audit trail). `round` field removed from `RefereeJudgment` (LLM output was always overwritten by code). `Message` and `DebateResult` models removed (never used in production).

**`prompts.py`** — Four system prompt constants and four template functions. Agents import these — no string hardcoding.
- `OPPONENT_SYSTEM_PROMPT` / `opponent_prompt(current_thesis, improvement_hint="")` — Socratic questioner: probes the topic's boundaries, assumptions, and implications through guided questioning (3 strategies: logical exploration / boundary clarification / counterexample probing). Single-point, ≤80 chars. `improvement_hint` carries the guide's strategic direction from the previous round.
- `PRESENTER_SYSTEM_PROMPT` / `presenter_prompt(current_thesis, critique, user_response)` — Response refiner: elevates the user's informal response into a well-scoped understanding statement while preserving core intent.
- `REFEREE_SYSTEM_PROMPT` / `referee_prompt(current_thesis, draft_thesis, confirmed_thesis, round_num, history_summary)` — Learning synthesizer: layers new insights onto the existing understanding (accretion, not replacement). Silent during normal rounds (JSON-only output for internal routing). JSON format description removed from prompt — `with_structured_output` handles schema enforcement.
- `FINAL_SUMMARY_PROMPT` / `final_summary_prompt(initial_thesis, final_thesis, history_json)` — End-of-session summary: traces how the user's understanding deepened layer by layer through Socratic dialogue.

**`model.py`** — `ModelConfig` dataclass captures model name, base URL, and API key. `load_model_config(env)` parses environment into a `ModelConfig` (treating `sk-not-configured` placeholder as missing). `has_configured_api_key(env)` provides centralized API-key detection shared by UI, scripts, and the model factory. `get_chat_model(temperature, *, model_name=None, base_url=None)` builds `ChatOpenAI` from the config with `streaming=True` enabled (required for `graph.stream(stream_mode=["messages"])` token-level output). The optional `model_name`/`base_url` kwargs enable per-tab model overrides (priority > env vars). Adding a new provider is a `.env` change, never a code change.

**`logging.py`** — Structured logging and observability infrastructure. `trace_id_context()` generates a unique 8-char trace ID per request. `get_current_trace_id()` reads the active trace ID from context. `create_trace_logger(trace_id=None)` is a convenience factory that pairs a trace ID with a `TraceLogger`. `TraceLogger` records LLM call timing (duration, success/failure, retry count) and request-level errors. Log output is JSON-lines format with `trace_id` for log aggregation. Used by `_run_stream()` in the UI and `invoke_with_retry()` in agents.

### 2. `agents/` — Stateless Pure Functions

```
(state: AgentState, model: BaseChatModel | None = None) → dict
```

**`_base.py`** — Shared LLM utilities extracted from duplicated agent code:
- `extract_content(response)` — extract string from BaseMessage (was 3 copies)
- `make_message(role, content, round_num)` — construct message dict (was 6 copies)
- `invoke_llm(model, temperature, system_prompt, user_prompt, *, on_retry=None, trace=None, model_name=None, model_base_url=None)` — shared compute node skeleton with auto-retry + per-tab model override support (was 2 copies). The `on_retry` callback reports progress to UI; `trace` (TraceLogger) records LLM call metrics.
- `invoke_with_retry(invocable, messages, *, label: str = "LLM", on_retry=None, trace=None)` — LLM call with 3-retry exponential backoff (1s/2s/4s) for transient errors. Accepts optional `on_retry` callback for UI progress updates and `trace` for structured logging.
- `_is_retryable(error)` — classifies exceptions as transient (timeout/rate-limit) vs permanent.
- `NodeFunc = Callable[[AgentState], dict]` — type alias for agent node function signatures.

Each agent is split into **compute + interact** nodes to prevent LLM re-execution on `interrupt()` resume:
- `opponent_compute_node` / `opponent_interact_node` (含 `interrupt()`) — Asks Socratic questions that probe the topic's boundaries and assumptions
- `presenter_compute_node` / `presenter_interact_node` (含 `interrupt()`) — Refines user responses into precise understanding statements
- `referee_deliberate_node(state, model=None, *, json_mode=False)` — Synthesizes new cognitive insights into the understanding (silent unless terminating). Supports two strategies: `with_structured_output` (default, OpenAI) and JSON-mode manual parsing (`json_mode=True`, DeepSeek). Internal helpers `_build_round_record()` and `_dump_round_record()` handle archive construction and RoundRecord/dict normalization, eliminating duplicated type-ignores.

Compute nodes call LLM and return results. Interact nodes read cached results and call `interrupt()` for human input. On resume, interact nodes re-execute but only do idempotent state reads — no LLM re-invocation.

- **Read only** from `state`, never mutate
- **Return** a partial update dict with only changed keys
- **`model` parameter**: default via `get_chat_model()`; Mock injected for tests; typed as `BaseChatModel` for provider-agnosticism
- **Depend only on `core/` and `agents/_base.py`**, never on `ui/` or `workflow/`

### 3. `workflow/graph.py` — Pure Scheduling

```
build_graph(opponent_compute_node, opponent_interact_node,
            presenter_compute_node, presenter_interact_node,
            referee_deliberate_node, checkpointer=None)
```

```
START → start → opponent_compute → opponent_interact [interrupt]
  → presenter_compute → presenter_interact [interrupt]
  → referee_deliberate ──→ END (done)
              │                   │
              └── next_round ←────┘ (continue learning)
```

- **`start_node`**: `idle → opponent_computing`, `round = 1`
- **`next_round_node`**: `round += 1`, clears 5 `_`-prefixed cache fields (`_critique`/`_user_response`/`_draft_thesis`/`_confirmed_thesis`/`_improvement_hint`). Preserves `_model_name` and `_model_base_url` (per-tab persistent config).
- **`_route_after_referee`**: `status == "done" → END`, `round >= max_rounds → END` (safety valve), else `"next_round"`
- **No `interrupt_before`**: Human interaction uses dynamic `interrupt()` inside interact nodes, not static interrupt configuration.
- **`export_graph()`**: Public function to export architecture diagram as PNG.
- **`checkpointer`**: Must be passed for `interrupt()` and `get_state()` to work.

### 4. `ui/app.py` — Pure Rendering

Two separate state stores:
- **`st.session_state`**: UI metadata only — `sessions` (tab registry: `{tab_id: {thread_id, initial_thesis, label, started}}`), `checkpointer` (shared `MemorySaver`), `graph` (shared `CompiledStateGraph`), `api_key`
- **LangGraph `MemorySaver`**: actual learning session state, read-only via `graph.get_state(config)`

**Multi-tab support**: One shared `MemorySaver` + compiled graph serves multiple independent debate sessions via different `thread_id` values. `st.tabs()` renders each session in its own tab, with tab-aware widget key namespacing (`f"critique_response_{tab_id}"`). "➕ 新辩论" button adds tabs, "✕" closes them (with checkpoint cleanup). Each tab maintains independent state. Tabs can be renamed via an inline text input. "🗑️ 清空" closes all tabs and clears all checkpoint data.

**Per-tab model config isolation**: When a debate starts, the current sidebar model config (model name, base URL, temperature, max rounds) is frozen into the tab's session and `AgentState`. Subsequent sidebar changes only affect newly started debates — running tabs continue with their captured config. Each tab displays its active model name, temperature, and max rounds. `_capture_model_config()` snapshots the config; `get_chat_model()` accepts optional `model_name`/`base_url` overrides with priority over env vars.

**Streaming**: LLM responses stream token-by-token in the UI via `graph.stream(stream_mode=["messages", "updates"])`. A flag-based pattern (`pending_start`/`pending_resume`) decouples button callbacks from heavy graph execution — streaming runs in the main render thread where `st.empty()` placeholders update progressively. `GraphInterrupt` is caught to detect interrupt points. The model is created with `streaming=True` (see `core/model.py`).

**Error boundary**: `_run_stream()` catches non-`GraphInterrupt` exceptions and displays categorized Chinese-language error messages (auth failure / timeout / rate limit / network / JSON parse error) with an expandable technical details panel (traceback + TraceLogger summary). A retry button leverages LangGraph's checkpoint to resume from the last saved state.

**Temperature slider**: Sidebar `st.slider("温度", 0.0, 1.5, 0.7, 0.1)` controls Opponent/Presenter LLM creativity. The value is captured into `AgentState.agent_temperature` at debate start and read by agent nodes. Referee stays at 0.0 (deterministic).

**Max rounds slider**: Sidebar `st.slider("最大轮次", 1, 20, 10, 1)` sets a safety valve — `_route_after_referee` force-terminates when `round >= max_rounds`, preventing infinite loops and unbounded API costs.

`setup_environment()` from `core/env.py` handles `.env` loading **before** any LangChain/LangGraph imports — this ordering is deliberate (enables `LANGCHAIN_TRACING_V2`). API key detection delegates to `core.model.has_configured_api_key()`, and env override side effects are concentrated in `_apply_api_key_override()` / `_apply_model_override()`.

Flow: Button sets `pending_start` → `st.rerun()` → `_render_tab_content()` detects flag → `graph.stream(initial_state, config)` → progressive token rendering → `GraphInterrupt` caught → `st.rerun()` → interrupt UI shown. Resume: button sets `pending_resume` → `graph.stream(Command(resume=...), config)` → next interrupt or END.

Key UI functions:
- `_render_sidebar()` — renders API Key config, provider info, model override, temperature slider, max rounds slider
- `_capture_model_config()` — snapshots current sidebar model config for per-tab freezing at debate start
- `_ensure_default_tab()`, `_add_new_tab()`, `_close_tab(tab_id)`, `_close_all_tabs()`, `_rename_tab(tab_id, new_label)` — tab lifecycle management (close now cleans up checkpointer storage)
- `_render_tab_content(tab_id)` — full debate UI for one tab: rename / thesis input / model info / interrupt UI / conversation + judgment / error recovery
- `_ensure_shared_graph()` — lazily creates the shared MemorySaver + CompiledStateGraph singleton
- `_on_start_debate(tab_id, initial_thesis)` — freezes per-tab model config and sets pending_start flag
- `_on_reset(tab_id)` — resets a tab's debate to initial state for a fresh start
- `_execute_stream_start(tab_id)` / `_execute_stream_resume(tab_id, user_value)` — streaming execution entry points (inject per-tab model config + max_rounds into initial state)
- `_run_stream(graph, input_data, config)` — core streaming loop: `graph.stream()` + `st.empty()` progressive rendering + `GraphInterrupt` handling + error boundary with retry
- `_node_label(node_name)` — maps graph node names to Chinese status labels for streaming display
- `_get_current_state(tab_id)` / `_get_interrupt_value(tab_id)` — tab-aware state reads from checkpointer
- `_render_interrupt_ui(tab_id, status, value)` — renders question response / thesis confirmation UI with tab-namespaced widget keys

## Testing (mock tests + 6 real-API tests + ghost probe)

### Pytest Suite (Mock LLMs, no real API)

Shared test infrastructure:
| File | Purpose |
|------|---------|
| `tests/helpers.py` | `make_state()`, `make_initial_state()`, `make_mock_model()` — shared factories |
| `tests/mock_nodes.py` | `mock_opponent_compute/interact`, `mock_presenter_compute/interact`, `make_mock_referee()` — shared mock agent nodes |

| File | Tests | Coverage |
|------|-------|----------|
| `test_agents.py` | 49 | Opponent compute (6), Opponent interact (3), Presenter compute (6), Presenter interact (4), Referee deliberate (9), Interrupt idempotency (2), Edge cases (19) — model=None path, empty/blank/non-string LLM responses, dict-format history from checkpoint, large round numbers, referee JSON extraction/summary helpers |
| `test_workflow.py` | 21 | Start/next_round scheduling, conditional routing (all 7 status values), graph compilation, export_graph PNG, missing/unknown status routing, build_graph without checkpointer, state validation at entry |
| `test_integration.py` | 6 | Single-round lifecycle (2 tests), multi-round thesis evolution (2 tests), interrupt state persistence (2 tests) |
| `test_interfaces.py` | 28 | Prompt injection (4+4), node output key validation (6, now covers all 3 nodes), Pydantic serialization round-trip (2, RefereeJudgment + RoundRecord), checkpoint fidelity (2), routing correctness (3+2), state merge safety (1), extra='forbid' validation (1) |
| `test_model.py` | 22 | `get_chat_model()` full branch coverage + `load_model_config()` + `has_configured_api_key()` — defaults, env var overrides, API key fallback, missing key warning, empty string → None, placeholder treated as missing, temperature parameter |
| `test_smoke.py` | 21 | Module imports (5), model factory (2), graph compilation with real nodes (2), prompt validity (2), state factory + validation (5), sidebar config behavior (2), launcher (1), end-to-end assembly to first interrupt (1), export_graph with real nodes (1) |
| `test_base.py` | 6 | Retry classification (`_is_retryable`: timeout, rate-limit, non-retryable) + retry loop behavior (success after retry, non-retryable bail, budget exhaust with backoff) |
| `test_scripts.py` | 1 | Ghost probe structured-output probe against current `RefereeJudgment` schema contract |

All tests use Mock LLMs — no real API calls required.

### Real-API Integration Tests (`scripts/integration_test_real.py`)

Uses live API keys to test the full system (no mocks). DeepSeek-compatible: uses the production `referee_deliberate_node(json_mode=True)` which performs JSON-mode prompting + manual parsing (DeepSeek doesn't support `response_format`).

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | Opponent Agent | Real LLM: ≤80 chars, single-point, natural expression — Socratic questioning quality |
| 2 | Presenter Agent | Real LLM: preserves core intent, resolves ambiguity — response refinement quality |
| 3 | Referee JSON-mode | Real LLM: production guide node with `json_mode=True` |
| 4 | LangGraph Single Round | Full workflow: idle → 2 interrupts → Guide → done/continue |
| 5 | LangGraph Multi-Round | 2+ rounds of understanding evolution, RoundRecord accumulation |
| 6 | Checkpoint Persistence | `get_state()` at interrupt, resume restores correctly |

Run modes: `--quick` (single agents), `--workflow` (LangGraph only), no args (all 6).

### Ghost Probe (`scripts/ghost_probe.py`)

Standalone diagnostic script (NOT in pytest). Uses live API keys to probe the LLM environment:

| Probe | Token Cost | What It Checks |
|-------|-----------|----------------|
| Environment diagnostics | 0 | Model config, API key status, LangSmith, Python version, dependencies |
| API connectivity | ~10 | Provider responds with HTTP 200 |
| Structured output | ~200 | `with_structured_output(RefereeJudgment)` returns valid JSON |
| Opponent prompt | ~100 | Socratic question quality: ≤80 chars, single-point, natural expression |
| Presenter prompt | ~100 | Response refinement: preserves core intent, resolves ambiguity |
| Referee prompt | ~300 | JSON judgment with valid `continue_debate` + `new_thesis` |
| Full round | ~600 | Questioner → Refiner → Guide collaboration end-to-end |

Run with `python scripts/ghost_probe.py` (full) or `--quick` (env + connectivity only).

## Key Design Decisions

- **Compute/Interact split**: Each agent with an `interrupt()` is split into compute (LLM) + interact (human I/O) nodes. This prevents LLM re-execution on resume — compute nodes complete fully and are checkpointed before the interact node starts.
- **Shared LLM utilities (`agents/_base.py`)**: `extract_content()`, `make_message()`, `invoke_llm()`, `invoke_with_retry()`, and `_is_retryable()` eliminate 3×/6×/2× code duplication across questioner, refiner, and guide nodes. All LLM calls go through `invoke_with_retry()` which retries on transient errors (network/timeout/rate-limit) up to 3 times with exponential backoff.
- **Centralized API key detection**: `core.model` provides `load_model_config(env)` → `ModelConfig` and `has_configured_api_key(env)` so UI, scripts, and the model factory all share the same logic for deciding whether a real API key is configured. The `sk-not-configured` placeholder is consistently treated as missing.
- **State factory + runtime validation**: `core.state.make_initial_state(thesis)` is the single authoritative entry-state factory used by UI, scripts, and tests. `validate_state_shape(state)` is called at workflow entry (`_start_node`) so malformed initial states fail before reaching agent nodes.
- **Accretive understanding model**: `current_thesis` grows by accretion, not replacement. The guide layers new cognitive insights (boundaries, scope limits, operational definitions) onto the user's original perspective. Original understanding: one sentence → final understanding: one paragraph. Core perspective preserved; wording may be微调 for coherence.
- **Guide silence during normal rounds**: The guide does NOT produce user-visible messages when `continue_debate=True`. It only updates `current_thesis` and routes. `reasoning` / `improvement_hint` are internal fields — `improvement_hint` is fed forward to the next round's questioner via the `_improvement_hint` cache field, creating a closed feedback loop.
- **Guide dual strategy**: The guide supports two output strategies selectable via `json_mode` parameter: (a) `with_structured_output(RefereeJudgment)` — native OpenAI tool-calling, (b) JSON-mode prompting + regex extraction + Pydantic validation — DeepSeek and other providers without `response_format` support. Both strategies live in `agents/referee.py`; the integration test uses `json_mode=True`.
- **Guide helper extraction**: `_build_round_record()` constructs `RoundRecord` from state + judgment, `_dump_round_record()` normalizes `RoundRecord | dict` for JSON serialization and history summary. Both reduce `type: ignore` noise and god-node complexity.
- **Socratic questioning of boundaries**: Philosophy — understanding deepens by probing the boundaries and assumptions of one's own perspective. The questioner probes the topic's weakest boundary or unstated assumption through guided inquiry. Three strategies: logical exploration / boundary clarification / counterexample probing. Single-point, ≤80 chars.
- **Dynamic `interrupt()` only**: No `interrupt_before` configuration. Human interaction happens precisely when an interact node calls `interrupt(value)`, and resumes with `Command(resume=user_value)`.
- **Guide + safety valve termination**: The guide LLM outputs `continue_debate: bool` via structured output. A configurable `max_rounds` safety valve (default 10, set via sidebar slider) force-terminates in `_route_after_referee` when `round >= max_rounds`, preventing infinite loops and unbounded API costs from degenerate LLM behavior.
- **`messages` is a plain `list`, not `add_messages`**: LangChain's reducer rejects custom roles (`opponent`/`presenter`/`referee`/`user`). Agents append manually via `make_message()`.
- **Only `next_round_node` touches `round`**: Agents never increment the round counter — pure scheduling concern.
- **Provider-agnostic typing**: All agent function signatures use `BaseChatModel` (from `langchain_core.language_models`), not `ChatOpenAI`. Adding a non-OpenAI provider is purely a `.env` and type-system change.
- **Schemas enforce strict validation**: `_StrictModel` base class with `ConfigDict(extra='forbid')` ensures Pydantic models reject unknown fields. `round` field removed from `RefereeJudgment` — it was always overwritten by code and never consumed from LLM output.
- **Unified environment initialization**: `core/env.py` provides `setup_environment()` as the single entry point for sys.path setup, `.env` loading, and cwd management. All entry points (`run.py`, `scripts/*.py`, `ui/app.py`) delegate to it.
- **Shared test infrastructure**: `tests/helpers.py` and `tests/mock_nodes.py` eliminate quadruple duplication of state factories and mock agent nodes across test files. `tests/helpers.make_initial_state()` delegates to `core.state.make_initial_state()`.
- **`checkpointer` is injected at graph build time**: `build_graph()` accepts it as a parameter and passes it to `workflow.compile()`.
- **Multi-provider via env vars**: `get_chat_model()` reads `LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY`. Adding a new provider is a `.env` edit, never a code change.
- **Static analysis enforced**: Ruff (lint), pyright (strict mode), and mypy all pass with zero issues across the entire project.
- **CI gate** (`.github/workflows/ci.yml`): push/PR triggers automatic pytest + ruff + pyright + mypy without real API keys.
- **Multi-tab via shared graph**: One `MemorySaver` and compiled graph serve all tabs. Each tab gets a unique `thread_id`; LangGraph namespaces checkpoint state by `thread_id` automatically. Widget keys are namespaced with `tab_id` to prevent cross-tab Streamlit collisions.
- **Streaming via flag-based decoupling**: Button callbacks only set `pending_start`/`pending_resume` flags and call `st.rerun()`. The actual `graph.stream()` loop runs in `_render_tab_content()` (main render thread), where `st.empty()` placeholders can update progressively. This avoids the Streamlit limitation that callbacks buffer all output until return.
- **Configurable agent temperature**: `agent_temperature` is stored in `AgentState` (default 0.7), captured from the sidebar slider at debate start. Opponent and Presenter read it from state; Referee stays at 0.0. Different tabs can have different temperatures if the slider is adjusted between starting debates.

- **Per-tab model config isolation**: Model name and base URL are frozen per-tab at debate start via `_capture_model_config()`, stored in `AgentState._model_name` / `_model_base_url`. Agent compute nodes pass these to `get_chat_model()` and `invoke_llm()`, which accept optional overrides with priority over global env vars. Sidebar model changes only affect newly started debates — running tabs are unaffected. API key remains global (shared across tabs).

- **Structured logging with trace IDs**: `core/logging.py` provides `trace_id_context()` (8-char trace ID per request) and `TraceLogger` (LLM call timing, retry counts, error records). `_run_stream()` creates a `TraceLogger` for each `graph.stream()` invocation. `invoke_with_retry()` records LLM call metrics when a `TraceLogger` is provided. Log output is JSON-lines format for log aggregation.

- **Streaming error boundary**: `_run_stream()` wraps `graph.stream()` in a general `except Exception` handler (beyond `GraphInterrupt`). Errors are categorized (auth/timeout/rate-limit/network/parse) and displayed as Chinese-language messages with expandable technical details. A retry button leverages LangGraph checkpoints to resume from the last saved state.

- **Tab checkpoint cleanup**: `_close_tab()` removes the tab's `thread_id` entry from `MemorySaver.storage` to prevent unbounded memory growth from closed tabs. `_close_all_tabs()` clears all checkpoint data and resets the tab counter.

## Adding a New Provider

1. Edit `.env`:
   ```
   LLM_MODEL=your-model-name
   LLM_BASE_URL=https://your-api/v1
   LLM_API_KEY=your-key
   ```
2. Done. `get_chat_model()` picks it up automatically. Any OpenAI-compatible API works (DeepSeek, Ollama, vLLM, SiliconFlow, etc.). If the provider doesn't support `with_structured_output`, use `referee_deliberate_node(json_mode=True)` for DeepSeek-compatible JSON-mode handling (the guide's synthesis judgment).

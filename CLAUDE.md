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
**One logical change per commit. Run the full test suite after every commit.** The sequence is: make one change → `python -m pytest tests/ -v` (all 126 must pass) → `ruff check .` (zero warnings) → commit. If any check fails, fix it before moving to the next change. Compound changes that touch multiple concerns are rejected — split them.

### 5. No Big Rewrites
**A big rewrite is forbidden unless you have: (a) a written plan approved by the user, (b) a characterization test suite that pins the current behavior, and (c) a rollback strategy.** "It felt simpler to start over" is not a valid reason. Incremental refactoring via Strangler Fig is always preferred.

### 6. Analyze Dependencies & Impact Before Every Change
**Before touching any file, answer these questions:**
- What other files import or depend on this module? (`grep -r "from core\.schemas import" .`)
- What downstream behavior relies on the current contract (function signature, return type, side effects)?
- If I change this, what tests will catch regressions? If the answer is "none," write the characterization test first.
- Who calls this function / reads this state field? Trace every call site.

When in doubt, spend the time to map the blast radius before making the edit. A 30-second grep that prevents a 2-hour debugging session is always worth it.

## Project Overview

A **cognitive deepening system** built with LangGraph. Three LLM agents — **Opponent** (批判者), **Presenter** (精确化者), and **Referee** (裁判) — iteratively deepen a thesis through boundary probing, precise reformulation, and accretive layering. The thesis grows from a single sentence into a well-scoped paragraph by accumulating cognitive layers each round. Human-in-the-loop control uses LangGraph's dynamic `interrupt()` + `Command(resume=...)` mechanism via a Streamlit UI. LangSmith provides full observability, and `core/model.py` enables switching between OpenAI, DeepSeek, and any OpenAI-compatible provider without code changes.

## Development Commands

```bash
source venv/Scripts/activate        # Activate virtual environment
pip install -r requirements.txt     # Install dependencies
cp .env.example .env                # Configure API keys (first time only)

# Testing (126 mock tests + real-API integration tests)
python -m pytest tests/ -v          # Mock LLM suite (126 tests, no API needed)
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

# LangSmith tracing (optional, recommended)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_your-key
LANGCHAIN_PROJECT=ai-learning-loop
```

The `LLM_API_KEY` falls back to `OPENAI_API_KEY` if not set. If neither is configured, `get_chat_model()` emits a `RuntimeWarning` with diagnostic instructions and uses a placeholder key — the real error surfaces when the LLM is first invoked.

## Project Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, dependencies, ruff/mypy/pyright/pytest config |
| `run.py` | Universal launcher — `python run.py` from any directory |
| `requirements.txt` | Runtime dependencies (minimum version constraints) |
| `requirements-lock.txt` | Pinned dependency versions for reproducible deployments |

## Architecture: Four-Layer Separation

```
ui/app.py              ← Rendering + input only. ZERO business logic.
workflow/graph.py      ← Pure state routing. LLM nodes + checkpointer injected.
agents/{_base,opponent,presenter,referee}.py  ← Shared LLM tools + stateless pure functions (6 nodes) + dynamic interrupt().
core/{env,state,schemas,prompts,model}.py     ← System contracts all layers depend on.
```

### 1. `core/` — Data Contracts (5 files)

**`env.py`** — `setup_environment(project_root, *, change_cwd, verbose)` — unified entry point for sys.path setup, `.env` loading, and optional cwd change. Used by `run.py` and all `scripts/*.py` to eliminate triplicate initialization code.

**`state.py`** — `AgentState(TypedDict)` with 11 fields (6 persistent + 5 round-cache), plus `NodeOutput = dict[str, object]` for node return types:

| Group | Fields | Purpose |
|-------|--------|---------|
| Core thesis | `current_thesis` | The ONLY persistent evolving content. Grows by accretion — referee layers new cognitive insights onto the original core each round (one sentence → one paragraph). |
| Round control | `round`, `status` | State machine: `idle → opponent_computing → awaiting_critique_response → presenter_computing → awaiting_thesis_confirmation → referee_deliberating → done` |
| Messages | `messages: list[dict]` | Custom roles (`opponent/user/presenter/referee`). Plain `list`, not `add_messages`. Append via `state["messages"] + [new_msg]`. |
| Round cache (`_` prefix) | `_critique`, `_user_response`, `_draft_thesis`, `_confirmed_thesis`, `_improvement_hint` | Per-round ephemeral data. Cleared by `next_round` node. `_improvement_hint` feeds the referee's strategic guidance forward to the next round's opponent. |
| Archive | `history: list[RoundRecord]`, `final_result` | Completed rounds + summary |

**`schemas.py`** — Pydantic v2 models with `_StrictModel` base class (`ConfigDict(extra='forbid')`). `RefereeJudgment` (with `continue_debate`/`new_thesis`/`reasoning`/`improvement_hint`) is the core contract. `RoundRecord` archives each round. `round` field removed from `RefereeJudgment` (LLM output was always overwritten by code). `Message` and `DebateResult` models removed (never used in production).

**`prompts.py`** — Four system prompt constants and four template functions. Agents import these — no string hardcoding.
- `OPPONENT_SYSTEM_PROMPT` / `opponent_prompt(current_thesis, improvement_hint="")` — Boundary attacker: probes the weakest assumption or scope limit (3 strategies: logical vulnerability / Socratic boundary-questioning / counterexample falsification). Single-point, ≤80 chars. `improvement_hint` carries referee's strategic guidance from the previous round.
- `PRESENTER_SYSTEM_PROMPT` / `presenter_prompt(current_thesis, critique, user_response)` — Precision refiner: elevates informal user response into a well-scoped thesis statement while preserving core intent.
- `REFEREE_SYSTEM_PROMPT` / `referee_prompt(current_thesis, draft_thesis, confirmed_thesis, round_num, history_summary)` — Cognitive accumulator: layers new insights onto the existing thesis (accretion, not replacement). Silent during normal rounds (JSON-only output for internal routing). JSON format description removed from prompt — `with_structured_output` handles schema enforcement.
- `FINAL_SUMMARY_PROMPT` / `final_summary_prompt(initial_thesis, final_thesis, history_json)` — End-of-debate summary: traces how the thesis grew layer by layer.

**`model.py`** — `get_chat_model(temperature)` reads `LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY` from env and returns a configured `ChatOpenAI`. If no API key is found, emits a `RuntimeWarning` with diagnostic instructions. Adding a new provider is a `.env` change, never a code change.

### 2. `agents/` — Stateless Pure Functions

```
(state: AgentState, model: BaseChatModel | None = None) → dict
```

**`_base.py`** — Shared LLM utilities extracted from duplicated agent code:
- `extract_content(response)` — extract string from BaseMessage (was 3 copies)
- `make_message(role, content, round_num)` — construct message dict (was 6 copies)
- `invoke_llm(model, temperature, system_prompt, user_prompt)` — shared compute node skeleton with auto-retry (was 2 copies)
- `invoke_with_retry(invocable, messages)` — LLM call with 3-retry exponential backoff (1s/2s/4s) for transient errors

Each agent is split into **compute + interact** nodes to prevent LLM re-execution on `interrupt()` resume:
- `opponent_compute_node` / `opponent_interact_node` (含 `interrupt()`) — Attacks thesis boundaries/assumptions
- `presenter_compute_node` / `presenter_interact_node` (含 `interrupt()`) — Refines user responses into precise thesis statements
- `referee_deliberate_node(state, model=None, *, json_mode=False)` — Layers new cognitive insights onto thesis (silent unless terminating). Supports two strategies: `with_structured_output` (default, OpenAI) and JSON-mode manual parsing (`json_mode=True`, DeepSeek).

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
              └── next_round ←────┘ (continue)
```

- **`start_node`**: `idle → opponent_computing`, `round = 1`
- **`next_round_node`**: `round += 1`, clears all `_`-prefixed cache fields (5 fields)
- **`_route_after_referee`**: `status == "done" → END`, else `"next_round"`
- **No `interrupt_before`**: Human interaction uses dynamic `interrupt()` inside interact nodes, not static interrupt configuration.
- **`export_graph()`**: Public function to export architecture diagram as PNG.
- **`checkpointer`**: Must be passed for `interrupt()` and `get_state()` to work.

### 4. `ui/app.py` — Pure Rendering

Two separate state stores:
- **`st.session_state`**: UI metadata only (`thread_id`, `graph`, `api_key`, `initial_thesis_input`, `debate_started`)
- **LangGraph `MemorySaver`**: actual debate state, read-only via `graph.get_state(config)`

`setup_environment()` from `core/env.py` handles `.env` loading **before** any LangChain/LangGraph imports — this ordering is deliberate (enables `LANGCHAIN_TRACING_V2`).

Flow: `graph.invoke(initial_state, config)` → runs until first `interrupt()` → UI shows critique/draft input → user submits → `graph.invoke(Command(resume=user_input), config)` → runs until next interrupt or END.

Key UI functions:
- `_render_interrupt_ui(status, interrupt_value)` — renders critique response or thesis confirmation UI
- `_resume_with_input(user_value)` — calls `graph.invoke(Command(resume=user_value), config)`
- `_get_interrupt_value()` — checks `graph.get_state(config).interrupts` for active interrupt data

## Testing (126 mock tests + 6 real-API tests + ghost probe)

### Pytest Suite (Mock LLMs, no real API)

Shared test infrastructure:
| File | Purpose |
|------|---------|
| `tests/helpers.py` | `make_state()`, `make_initial_state()`, `make_mock_model()` — shared factories |
| `tests/mock_nodes.py` | `mock_opponent_compute/interact`, `mock_presenter_compute/interact`, `make_mock_referee()` — shared mock agent nodes |

| File | Tests | Coverage |
|------|-------|----------|
| `test_agents.py` | 43 | Opponent compute (6), Opponent interact (3), Presenter compute (6), Presenter interact (4), Referee deliberate (9), Interrupt idempotency (2), Edge cases (13) — model=None path, empty/blank/non-string LLM responses, dict-format history from checkpoint, large round numbers |
| `test_workflow.py` | 21 | Start/next_round scheduling, conditional routing (all 7 status values), graph compilation, export_graph PNG, missing/unknown status routing, build_graph without checkpointer |
| `test_integration.py` | 5 | Single-round lifecycle (2 interrupts), multi-round thesis evolution, state survives interrupt, no message duplication on resume |
| `test_interfaces.py` | 28 | Prompt injection (4+4), node output key validation (6, now covers all 3 nodes), Pydantic serialization round-trip (2, RefereeJudgment + RoundRecord), checkpoint fidelity (2), routing correctness (3+2), state merge safety (1), extra='forbid' validation (1) |
| `test_model.py` | 16 | `get_chat_model()` full branch coverage: defaults, env var overrides, API key fallback, missing key warning, empty string → None, temperature parameter |
| `test_smoke.py` | 13 | Module imports (4), model factory (2), graph compilation with real nodes (2), prompt validity (2), state factory (1), end-to-end assembly to first interrupt (1), export_graph with real nodes (1) |

All tests use Mock LLMs — no real API calls required.

### Real-API Integration Tests (`scripts/integration_test_real.py`)

Uses live API keys to test the full system (no mocks). DeepSeek-compatible: uses the production `referee_deliberate_node(json_mode=True)` which performs JSON-mode prompting + manual parsing (DeepSeek doesn't support `response_format`).

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | Opponent Agent | Real LLM: ≤80 chars, single-point, natural expression |
| 2 | Presenter Agent | Real LLM: preserves core intent, resolves ambiguity |
| 3 | Referee JSON-mode | Real LLM: production referee node with `json_mode=True` |
| 4 | LangGraph Single Round | Full workflow: idle → 2 interrupts → Referee → done/continue |
| 5 | LangGraph Multi-Round | 2+ rounds of thesis evolution, RoundRecord accumulation |
| 6 | Checkpoint Persistence | `get_state()` at interrupt, resume restores correctly |

Run modes: `--quick` (single agents), `--workflow` (LangGraph only), no args (all 6).

### Ghost Probe (`scripts/ghost_probe.py`)

Standalone diagnostic script (NOT in pytest). Uses live API keys to probe the LLM environment:

| Probe | Token Cost | What It Checks |
|-------|-----------|----------------|
| Environment diagnostics | 0 | Model config, API key status, LangSmith, Python version, dependencies |
| API connectivity | ~10 | Provider responds with HTTP 200 |
| Structured output | ~200 | `with_structured_output(RefereeJudgment)` returns valid JSON |
| Opponent prompt | ~100 | Output ≤80 chars, single-point, no AI-speak |
| Presenter prompt | ~100 | Preserves core intent, resolves ambiguity |
| Referee prompt | ~300 | JSON judgment with valid `continue_debate` + `new_thesis` |
| Full round | ~600 | Opponent → Presenter → Referee collaboration end-to-end |

Run with `python scripts/ghost_probe.py` (full) or `--quick` (env + connectivity only).

## Key Design Decisions

- **Compute/Interact split**: Each agent with an `interrupt()` is split into compute (LLM) + interact (human I/O) nodes. This prevents LLM re-execution on resume — compute nodes complete fully and are checkpointed before the interact node starts.
- **Shared LLM utilities (`agents/_base.py`)**: `extract_content()`, `make_message()`, `invoke_llm()`, and `invoke_with_retry()` eliminate 3×/6×/2× code duplication across opponent, presenter, and referee nodes. All LLM calls go through `invoke_with_retry()` which retries on transient errors (network/timeout/rate-limit) up to 3 times with exponential backoff.
- **Accretive thesis model**: `current_thesis` grows by accretion, not replacement. The referee layers new cognitive insights (boundaries, scope limits, operational definitions) onto the original core claim. Original thesis: one sentence → final thesis: one paragraph. Core claim preserved; wording may be微调 for coherence.
- **Referee silence during normal rounds**: Referee does NOT produce user-visible messages when `continue_debate=True`. It only updates `current_thesis` and routes. `reasoning` / `improvement_hint` are internal fields — `improvement_hint` is fed forward to the next round's opponent via the `_improvement_hint` cache field, creating a closed feedback loop.
- **Referee dual strategy**: The referee supports two output strategies selectable via `json_mode` parameter: (a) `with_structured_output(RefereeJudgment)` — native OpenAI tool-calling, (b) JSON-mode prompting + regex extraction + Pydantic validation — DeepSeek and other providers without `response_format` support. Both strategies live in `agents/referee.py`; the integration test uses `json_mode=True`.
- **Opponent attacks boundaries, not truth**: Philosophy — truth is concrete and conditional (materialist dialectics). The opponent attacks the thesis's weakest boundary or unstated assumption, not its core truth value. Three strategies: logical vulnerability / Socratic boundary-questioning / counterexample falsification. Single-point, ≤80 chars.
- **Dynamic `interrupt()` only**: No `interrupt_before` configuration. Human interaction happens precisely when an interact node calls `interrupt(value)`, and resumes with `Command(resume=user_value)`.
- **Referee decides when to end**: No `max_rounds`. The referee LLM outputs `continue_debate: bool` via structured output to control the debate lifecycle. Decision criteria: stop when no meaningful new cognitive layers emerge, continue when new distinctions or boundaries are discovered.
- **`messages` is a plain `list`, not `add_messages`**: LangChain's reducer rejects custom roles (`opponent`/`presenter`/`referee`/`user`). Agents append manually via `make_message()`.
- **Only `next_round_node` touches `round`**: Agents never increment the round counter — pure scheduling concern.
- **Provider-agnostic typing**: All agent function signatures use `BaseChatModel` (from `langchain_core.language_models`), not `ChatOpenAI`. Adding a non-OpenAI provider is purely a `.env` and type-system change.
- **Schemas enforce strict validation**: `_StrictModel` base class with `ConfigDict(extra='forbid')` ensures Pydantic models reject unknown fields. `round` field removed from `RefereeJudgment` — it was always overwritten by code and never consumed from LLM output.
- **Unified environment initialization**: `core/env.py` provides `setup_environment()` as the single entry point for sys.path setup, `.env` loading, and cwd management. All entry points (`run.py`, `scripts/*.py`) delegate to it.
- **Shared test infrastructure**: `tests/helpers.py` and `tests/mock_nodes.py` eliminate quadruple duplication of state factories and mock agent nodes across 5 test files.
- **`checkpointer` is injected at graph build time**: `build_graph()` accepts it as a parameter and passes it to `workflow.compile()`.
- **Multi-provider via env vars**: `get_chat_model()` reads `LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY`. Adding a new provider is a `.env` edit, never a code change.
- **Static analysis enforced**: Ruff (lint), pyright (strict mode), and mypy all pass with zero issues across the entire project.

## Adding a New Provider

1. Edit `.env`:
   ```
   LLM_MODEL=your-model-name
   LLM_BASE_URL=https://your-api/v1
   LLM_API_KEY=your-key
   ```
2. Done. `get_chat_model()` picks it up automatically. Any OpenAI-compatible API works (DeepSeek, Ollama, vLLM, SiliconFlow, etc.). If the provider doesn't support `with_structured_output`, use `referee_deliberate_node(json_mode=True)` for DeepSeek-compatible JSON-mode handling.

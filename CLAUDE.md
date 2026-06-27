# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A **thesis evolution system** built with LangGraph. Three LLM agents — **Opponent** (批判者), **Presenter** (精确化者), and **Referee** (裁判) — iteratively refine a thesis through critique, reformulation, and synthesis. Human-in-the-loop control uses LangGraph's dynamic `interrupt()` + `Command(resume=...)` mechanism via a Streamlit UI. LangSmith provides full observability, and `core/model.py` enables switching between OpenAI, DeepSeek, and any OpenAI-compatible provider without code changes.

## Development Commands

```bash
source venv/Scripts/activate        # Activate virtual environment
pip install -r requirements.txt     # Install dependencies
cp .env.example .env                # Configure API keys (first time only)

# Testing (69 tests, all LLM calls mocked — no real API needed)
python -m pytest tests/ -v          # Run all tests

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
| `requirements.txt` | Runtime dependencies |

## Architecture: Four-Layer Separation

```
ui/app.py              ← Rendering + input only. ZERO business logic.
workflow/graph.py      ← Pure state routing. LLM nodes + checkpointer injected.
agents/{opponent,presenter,referee}.py  ← Stateless pure functions (6 nodes) + dynamic interrupt().
core/{state,schemas,prompts,model}.py   ← System contracts all layers depend on.
```

### 1. `core/` — Data Contracts (4 files)

**`state.py`** — `AgentState(TypedDict)` with 10 fields (6 persistent + 4 round-cache), plus `AgentStateOverrides(TypedDict, total=False)` for partial construction and `NodeOutput = dict[str, object]` for node return types:

| Group | Fields | Purpose |
|-------|--------|---------|
| Core thesis | `current_thesis` | The ONLY persistent evolving content. Referee synthesizes each round. |
| Round control | `round`, `status` | State machine: `idle → opponent_computing → awaiting_critique_response → presenter_computing → awaiting_thesis_confirmation → referee_deliberating → done` |
| Messages | `messages: list[dict]` | Custom roles (`opponent/user/presenter/referee`). Plain `list`, not `add_messages`. Append via `state["messages"] + [new_msg]`. |
| Round cache (`_` prefix) | `_critique`, `_user_response`, `_draft_thesis`, `_confirmed_thesis` | Per-round ephemeral data. Cleared by `next_round` node. `_` prefix distinguishes from persistent state. |
| Archive | `history: list[RoundRecord]`, `final_result` | Completed rounds + summary |

**`schemas.py`** — Pydantic v2 models. `RefereeJudgment` (with `continue_debate`/`new_thesis`/`reasoning`/`improvement_hint`) is the core contract; referee uses `with_structured_output(RefereeJudgment)`. Hierarchy: `Message → RefereeJudgment → RoundRecord → DebateResult`. `CategoryScores` removed (scoring no longer relevant).

**`prompts.py`** — Four system prompt constants and four template functions. Agents import these — no string hardcoding.
- `OPPONENT_SYSTEM_PROMPT` / `opponent_prompt(current_thesis)` — Critic role
- `PRESENTER_SYSTEM_PROMPT` / `presenter_prompt(current_thesis, critique, user_response)` — Formulator role
- `REFEREE_SYSTEM_PROMPT` / `referee_prompt(current_thesis, draft_thesis, confirmed_thesis, round_num, history_summary)` — Synthesizer role
- `FINAL_SUMMARY_PROMPT` / `final_summary_prompt(initial_thesis, final_thesis, history_json)` — End-of-debate summary

**`model.py`** — `get_chat_model(temperature)` reads `LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY` from env and returns a configured `ChatOpenAI`. If no API key is found, emits a `RuntimeWarning` with diagnostic instructions. Adding a new provider is a `.env` change, never a code change.

### 2. `agents/` — Stateless Pure Functions

```
(state: AgentState, model: ChatOpenAI | None = None) → dict
```

Each agent is split into **compute + interact** nodes to prevent LLM re-execution on `interrupt()` resume:
- `opponent_compute_node` / `opponent_interact_node` (含 `interrupt()`)
- `presenter_compute_node` / `presenter_interact_node` (含 `interrupt()`)
- `referee_deliberate_node` (single node, no interrupt)

Compute nodes call LLM and return results. Interact nodes read cached results and call `interrupt()` for human input. On resume, interact nodes re-execute but only do idempotent state reads — no LLM re-invocation.

- **Read only** from `state`, never mutate
- **Return** a partial update dict with only changed keys
- **`model` parameter**: default via `get_chat_model()`; Mock injected for tests
- **Depend only on `core/`**, never on `ui/` or `workflow/`

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
- **`next_round_node`**: `round += 1`, clears all `_`-prefixed cache fields
- **`_route_after_referee`**: `status == "done" → END`, else `"next_round"`
- **No `interrupt_before`**: Human interaction uses dynamic `interrupt()` inside interact nodes, not static interrupt configuration.
- **`export_graph()`**: Public function to export architecture diagram as PNG.
- **`checkpointer`**: Must be passed for `interrupt()` and `get_state()` to work.

### 4. `ui/app.py` — Pure Rendering

Two separate state stores:
- **`st.session_state`**: UI metadata only (`thread_id`, `graph`, `api_key`, `initial_thesis_input`, `debate_started`)
- **LangGraph `MemorySaver`**: actual debate state, read-only via `graph.get_state(config)`

`load_dotenv()` is called **before** any LangChain/LangGraph imports — this ordering is deliberate (enables `LANGCHAIN_TRACING_V2`).

Flow: `graph.invoke(initial_state, config)` → runs until first `interrupt()` → UI shows critique/draft input → user submits → `graph.invoke(Command(resume=user_input), config)` → runs until next interrupt or END.

Key UI functions:
- `_render_interrupt_ui(status, interrupt_value)` — renders critique response or thesis confirmation UI
- `_resume_with_input(user_value)` — calls `graph.invoke(Command(resume=user_value), config)`
- `_get_interrupt_value()` — checks `graph.get_state(config).interrupts` for active interrupt data

## Testing (69 tests, 4 files)

| File | Tests | Coverage |
|------|-------|----------|
| `test_agents.py` | 29 | Opponent compute (6), Opponent interact (3), Presenter compute (6), Presenter interact (4), Referee deliberate (8), Interrupt idempotency (2) |
| `test_workflow.py` | 14 | Start/next_round scheduling, conditional routing (all 7 status values), graph compilation, no interrupt_before assert |
| `test_integration.py` | 5 | Single-round lifecycle (2 interrupts), multi-round thesis evolution, state survives interrupt, no message duplication on resume |
| `test_interfaces.py` | 21 | Prompt injection (4), node output key validation (6), Pydantic serialization round-trip (4), checkpoint fidelity (2), routing correctness (3), state merge safety (1) |

All tests use Mock LLMs — no real API calls required.

## Key Design Decisions

- **Compute/Interact split**: Each agent with an `interrupt()` is split into compute (LLM) + interact (human I/O) nodes. This prevents LLM re-execution on resume — compute nodes complete fully and are checkpointed before the interact node starts.
- **`current_thesis` as sole persistent content**: Only `current_thesis` evolves across rounds. Critique, draft, and confirmation are round-cache fields (`_` prefix) cleared each round.
- **Dynamic `interrupt()` only**: No `interrupt_before` configuration. Human interaction happens precisely when an interact node calls `interrupt(value)`, and resumes with `Command(resume=user_value)`.
- **Referee decides when to end**: No `max_rounds`. The referee LLM outputs `continue_debate: bool` via structured output to control the debate lifecycle.
- **`messages` is a plain `list`, not `add_messages`**: LangChain's reducer rejects custom roles (`opponent`/`presenter`/`referee`/`user`). Agents append manually.
- **Only `next_round_node` touches `round`**: Agents never increment the round counter — pure scheduling concern.
- **Referee uses `with_structured_output(RefereeJudgment)`**: Pydantic model forces valid JSON. Temperature is 0.0 for deterministic output.
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
2. Done. `get_chat_model()` picks it up automatically. Any OpenAI-compatible API works (DeepSeek, Ollama, vLLM, SiliconFlow, etc.).

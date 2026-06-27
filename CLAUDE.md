# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A multi-agent debate learning system built with LangGraph. Three LLM agents — **Presenter** (陈述者), **Opponent** (反驳者), and **Referee** (裁判) — engage in multi-round structured debates with human-in-the-loop step-through control via a Streamlit UI. LangSmith provides full observability, and `core/model.py` enables switching between OpenAI, DeepSeek, and any OpenAI-compatible provider without code changes.

## Development Commands

```bash
source venv/Scripts/activate        # Activate virtual environment
pip install -r requirements.txt     # Install dependencies
cp .env.example .env                # Configure API keys (first time only)

# Testing (57 tests, all LLM calls mocked — no real API needed)
python -m pytest tests/ -v          # Run all tests

# Code quality
ruff check .                        # Lint (zero warnings)
mypy core/ agents/ workflow/ --ignore-missing-imports  # Type check (zero errors)

# Run the app
streamlit run ui/app.py

# Export graph architecture diagram
python -m workflow.graph            # → graph_architecture.png
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

The `LLM_API_KEY` falls back to `OPENAI_API_KEY` if not set. If neither is configured, `get_chat_model()` returns an instance with a placeholder key — the real error surfaces when the LLM is first invoked.

## Architecture: Four-Layer Separation

```
ui/app.py              ← Rendering + input only. ZERO business logic.
workflow/graph.py      ← Pure state routing. LLM nodes + checkpointer injected.
agents/{presenter,opponent,referee}.py  ← Stateless pure functions: state → dict.
core/{state,schemas,prompts,model}.py   ← System contracts all layers depend on.
```

### 1. `core/` — Data Contracts (4 files)

**`state.py`** — Single `AgentState(TypedDict)` with 10 fields:

| Group | Fields | Purpose |
|-------|--------|---------|
| Session | `topic` | Immutable debate topic |
| Round control | `round`, `max_rounds`, `status` | State machine: `idle → presenting → opposing → judging → done` |
| Messages | `messages: list[dict]` | Custom roles. Plain `list`, not `add_messages` (LangChain rejects non-standard roles). Append via `state["messages"] + [new_msg]`. |
| Current cache | `presenter_argument`, `opponent_rebuttal`, `referee_judgment` | Cleared between rounds by `next_round` node |
| Archive | `history: list[RoundRecord]`, `final_result` | Completed rounds + summary |

**`schemas.py`** — Pydantic v2 models. `RefereeJudgment` is the core contract; referee uses `with_structured_output(RefereeJudgment)`. Hierarchy: `CategoryScores → RefereeJudgment → RoundRecord → DebateResult → Message`.

**`prompts.py`** — Four system prompt constants and four template functions. Agents import these — no string hardcoding. Template functions only do string formatting.

**`model.py`** — `get_chat_model(temperature)` reads `LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY` from env and returns a configured `ChatOpenAI`. Adding a new provider is a `.env` change, never a code change.

### 2. `agents/` — Stateless Pure Functions

```
(state: AgentState, model: ChatOpenAI | None = None) → dict
```

- **Read only** from `state`, never mutate
- **Return** a partial update dict with only changed keys
- **`model` parameter**: default via `get_chat_model()`; Mock injected for tests
- **Depend only on `core/`**, never on `ui/` or `workflow/`

Type guards are present for LLM response handling: `response.content` may be `str | list` (mypy-enforced), and `with_structured_output` return variance is handled with `isinstance(RefereeJudgment)` fallback.

### 3. `workflow/graph.py` — Pure Scheduling

```
build_graph(presenter_node, opponent_node, referee_node,
            interrupt_before=None, checkpointer=None)
```

```
START → start_node → presenter → opponent → referee ──→ END (done)
                                    ↑                   │
                                    └── next_round ←────┘ (conditional)
```

- **`start_node`**: `idle → presenting` (boot)
- **`next_round_node`**: `round += 1`, clears current-round cache
- **`_route_after_referee`**: `status == "done" → END`, else `"next_round"`
- **`checkpointer`**: Must be passed for `interrupt_before` pause/resume and `get_state()` to work. Without it, the graph runs but interrupts will fail with `EmptyInputError`.
- Default `interrupt_before=["presenter", "opponent", "referee"]`

### 4. `ui/app.py` — Pure Rendering

Two separate state stores:
- **`st.session_state`**: UI metadata only (`thread_id`, `api_key`, `debate_started`)
- **LangGraph `MemorySaver`**: actual debate state, read-only via `graph.get_state(config)`

`load_dotenv()` is called **before** any LangChain/LangGraph imports — this ordering is deliberate (enables `LANGCHAIN_TRACING_V2`). The `# noqa: E402` comment suppresses the ruff warning for this intentional pattern.

Flow: `graph.invoke(initial_state, config)` → hits interrupt → user clicks "Continue" → `graph.invoke(None, config)` resumes from checkpoint.

## Testing (57 tests, 4 files)

| File | Tests | Coverage |
|------|-------|----------|
| `test_agents.py` | 22 | Opponent (6), Presenter (7), Referee (9) — return keys, status transitions, message appending, non-mutation, prompt content |
| `test_workflow.py` | 12 | Scheduling nodes, conditional routing, graph compilation, interrupt configuration |
| `test_integration.py` | 3 | Full 2-round lifecycle (7 invoke steps), single round, checkpoint state consistency |
| `test_interfaces.py` | 20 | Prompt injection, node output ↔ State merge safety, Pydantic serialization round-trip, checkpoint fidelity, routing correctness |

All tests use Mock LLMs — no real API calls required.

## Key Design Decisions

- **`messages` is a plain `list`, not `add_messages`**: LangChain's reducer rejects custom roles (`presenter`/`opponent`/`referee`). Agents append manually.
- **Only `next_round_node` touches `round`**: Agents never increment the round counter — pure scheduling concern.
- **Referee uses `with_structured_output(RefereeJudgment)`**: Pydantic model forces valid JSON. Temperature is 0.0 for deterministic scoring. Return type guarded with `isinstance`.
- **`checkpointer` is injected at graph build time**: Not an afterthought — `build_graph()` accepts it as a parameter and passes it to `workflow.compile()`.
- **Multi-provider via env vars**: `get_chat_model()` reads `LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY`. Adding a new provider is a `.env` edit, never a code change.
- **Static analysis enforced**: Ruff (lint) and mypy (type check) both pass with zero issues on the `core/`, `agents/`, and `workflow/` source directories.

## Adding a New Provider

1. Edit `.env`:
   ```
   LLM_MODEL=your-model-name
   LLM_BASE_URL=https://your-api/v1
   LLM_API_KEY=your-key
   ```
2. Done. `get_chat_model()` picks it up automatically. Any OpenAI-compatible API works (DeepSeek, Ollama, vLLM, SiliconFlow, etc.).

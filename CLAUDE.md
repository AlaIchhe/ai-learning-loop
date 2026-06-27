# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A multi-agent debate learning system built with LangGraph. Three LLM agents — **Presenter** (陈述者), **Opponent** (反驳者), and **Referee** (裁判) — engage in multi-round structured debates with human-in-the-loop step-through control via a Streamlit UI.

## Development Commands

```bash
source venv/Scripts/activate      # Activate virtual environment
pip install -r requirements.txt   # Install dependencies
python -m pytest tests/ -v        # Run all tests (34)
streamlit run ui/app.py           # Launch the app
```

## Architecture: Four-Layer Separation

```
ui/app.py              ← Rendering + input only. ZERO business logic.
workflow/graph.py      ← Pure state routing. LLM nodes injected as dependencies.
agents/{presenter,opponent,referee}.py  ← Stateless pure functions: state → dict.
core/{state,schemas,prompts}.py         ← System contracts all other layers depend on.
```

### 1. `core/` — Data Contracts

**`state.py`** — Single `AgentState(TypedDict)` with 10 fields:

| Group | Fields | Purpose |
|-------|--------|---------|
| Session | `topic` | Immutable debate topic |
| Round control | `round`, `max_rounds`, `status` | State machine: `idle → presenting → opposing → judging → done` |
| Messages | `messages: list[dict]` | Custom roles (presenter/opponent/referee). Plain `list`, not `add_messages`, because LangChain rejects non-standard roles. Append via `state["messages"] + [new_msg]`. |
| Current cache | `presenter_argument`, `opponent_rebuttal`, `referee_judgment` | Cleared between rounds by `next_round` node |
| Archive | `history: list[RoundRecord]`, `final_result` | Completed rounds + summary |

**`schemas.py`** — Pydantic v2 models. `RefereeJudgment` is the core contract; referee uses `with_structured_output(RefereeJudgment)` to force valid JSON. Hierarchy: `CategoryScores → RefereeJudgment → RoundRecord → DebateResult → Message`.

**`prompts.py`** — Four system prompt constants and four template functions (one per agent + final summary). Agent modules import these — no string hardcoding.

### 2. `agents/` — Stateless Pure Functions

Every agent node follows the same contract:
```
(state: AgentState, model: ChatOpenAI | None = None) → dict
```

- **Read** from `state`, never mutate (use `state["messages"] + [new_msg]`)
- **Return** a partial update dict with only changed keys
- **`model` parameter** enables Mock injection for tests; production defaults to `ChatOpenAI(model="gpt-4o")`
- Depend only on `core/schemas` and `core/prompts` — never on `ui/` or `workflow/`

Each agent sets the next `status`:
- `presenter_node` → `"opposing"`
- `opponent_node` → `"judging"`
- `referee_node` → `"done"` if `round >= max_rounds`, else `"presenting"`

### 3. `workflow/graph.py` — Pure Scheduling

`build_graph(presenter_node, opponent_node, referee_node, interrupt_before=None)` — LLM nodes injected as arguments. Zero LLM logic in the graph itself.

```
START → start_node → presenter → opponent → referee ──→ END (done)
                                    ↑                   │
                                    └── next_round ←────┘ (conditional)
```

- **`start_node`**: sets `status="presenting"` (boot)
- **`next_round_node`**: increments `round`, clears `presenter_argument`/`opponent_rebuttal`/`referee_judgment`
- **`_route_after_referee`**: `status == "done" → END`, else `"next_round"`
- Default `interrupt_before=["presenter", "opponent", "referee"]` — pauses before every LLM node

### 4. `ui/app.py` — Pure Rendering

Two separate state stores:
- **`st.session_state`**: UI metadata only (`thread_id`, `api_key`, `debate_started`)
- **LangGraph `MemorySaver`**: actual debate state, accessed read-only via `graph.get_state(config)`

Flow: `graph.invoke(initial_state, config)` → hits interrupt → user clicks "Continue" → `graph.invoke(None, config)` resumes from checkpoint. All `_render_*` functions accept data, return `None`, mutate nothing.

## Testing

34 tests across two files, all LLM calls mocked:
- **`test_agents.py`** (22): `TestOpponentNode` (6), `TestPresenterNode` (7), `TestRefereeNode` (9) — verifies return keys, status transitions, message appending, non-mutation, prompt content
- **`test_workflow.py`** (12): `TestStartNode` (2), `TestNextRoundNode` (3), `TestRouteAfterReferee` (2), `TestBuildGraph` (5) — verifies scheduling nodes, conditional routing, graph compilation, interrupt configuration

## Key Design Decisions

- **`messages` is a plain `list`, not `add_messages`**: LangChain's reducer rejects custom roles. Agents append manually.
- **Custom roles over LangChain standard types**: `presenter`/`opponent`/`referee` capture debate semantics better than `human`/`ai`/`system`.
- **Only `next_round_node` touches `round`**: Agents never increment the round counter — pure scheduling concern.
- **Referee uses `with_structured_output(RefereeJudgment)`**: Pydantic model forces valid JSON, eliminating parsing fragility. Temperature is 0.0 for deterministic scoring.
- **Graph caches with `st.cache_resource`**: Compiled graph is cached across Streamlit reruns for responsiveness.

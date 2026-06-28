---
description: core/ 层数据契约 — env, state, schemas, prompts, model, logging
paths:
  - "core/**"
---

# Core Layer — Data Contracts

`core/` is the root dependency shared by all other layers. System contracts only — no business logic.

## Files

**`env.py`** — `setup_environment(project_root, *, change_cwd, verbose)` — unified entry point for sys.path setup, `.env` loading, and optional cwd change.

**`state.py`** — `AgentState(TypedDict)` with 15 fields (10 persistent + 5 round-cache), plus `NodeOutput = dict[str, object]`. Exports `make_initial_state()` (authoritative entry-state factory) and `validate_state_shape()` (runtime guard).

| Group | Fields | Purpose |
|-------|--------|---------|
| Core topic | `current_thesis` | The ONLY persistent evolving content. Grows by accretion each round. |
| Round control | `round`, `agent_temperature`, `status`, `max_rounds` | State machine: `idle → opponent_computing → awaiting_critique_response → presenter_computing → awaiting_thesis_confirmation → referee_deliberating → done`. |
| Messages | `messages: list[dict]` | Custom roles (`opponent/user/presenter/referee`). Plain `list`, not `add_messages`. |
| Per-tab config | `_model_name`, `_model_base_url` | Persistent — NOT cleared by `next_round`. |
| Round cache | `_critique`, `_user_response`, `_draft_thesis`, `_confirmed_thesis`, `_improvement_hint` | Ephemeral — cleared by `next_round`. |
| Archive | `history: list[RoundRecord]`, `final_result` | Completed rounds + learning summary |

**`schemas.py`** — Pydantic v2 models with `_StrictModel` base class (`ConfigDict(extra='forbid')`). `RefereeJudgment` (core contract), `RoundRecord` (archive with `timestamp` field).

**`prompts.py`** — Four system prompt constants and four template functions. Agents import these; no string hardcoding.
- `OPPONENT_SYSTEM_PROMPT` / `opponent_prompt(current_thesis, improvement_hint="")` — Socratic questioner, ≤80 chars
- `PRESENTER_SYSTEM_PROMPT` / `presenter_prompt(current_thesis, critique, user_response)` — Response refiner
- `REFEREE_SYSTEM_PROMPT` / `referee_prompt(...)` — Learning synthesizer (silent unless terminating)
- `FINAL_SUMMARY_PROMPT` / `final_summary_prompt(...)` — End-of-session summary

**`model.py`** — `ModelConfig` dataclass. `load_model_config(env)` parses env. `has_configured_api_key(env)` centralized detection. `get_chat_model(temperature, *, model_name=None, base_url=None)` builds `ChatOpenAI` with `streaming=True`. Optional kwargs enable per-tab overrides.

**`logging.py`** — `trace_id_context()` (8-char trace ID), `TraceLogger` (LLM call timing/retry/error), JSON-lines output.

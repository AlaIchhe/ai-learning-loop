---
description: socratic_loop/core/ 层数据契约 — env, state, schemas, prompts, model, providers, model_store, connection_test, logging
paths:
  - "socratic_loop/core/**"
---

# Core Layer — Data Contracts

`core/` is the root dependency shared by all other layers. System contracts only — no business logic.

## Files

**`env.py`** — `setup_environment(project_root, *, change_cwd, verbose)` — unified entry point for sys.path setup, `.env` loading, and optional cwd change.

**`state.py`** — `AgentState(TypedDict)` with 17 fields (14 persistent + 5 round-cache? — actually 12 persistent + 5 round-cache = 17). Exports `make_initial_state()` (authoritative entry-state factory) and `validate_state_shape()` (runtime guard).

| Group | Fields | Purpose |
|-------|--------|---------|
| Core topic | `current_thesis` | The ONLY persistent evolving content. Grows by accretion each round. |
| Round control | `round`, `agent_temperature`, `status`, `max_rounds` | State machine: `idle → opponent_computing → awaiting_critique_response → presenter_computing → awaiting_thesis_confirmation → referee_deliberating → done`. |
| Messages | `messages: list[dict]` | Custom roles (`opponent/user/presenter/referee`). Plain `list`, not `add_messages`. |
| Per-tab config | `_model_name`, `_model_base_url`, `_model_api_key`, `_model_json_mode` | Persistent — NOT cleared by `next_round`. Frozen from ModelStore at debate start. |
| Round cache | `_critique`, `_user_response`, `_draft_thesis`, `_confirmed_thesis`, `_improvement_hint` | Ephemeral — cleared by `next_round`. |
| Archive | `history: list[RoundRecord]`, `final_result` | Completed rounds + learning summary |

**`schemas.py`** — Pydantic v2 models with `_StrictModel` base class (`ConfigDict(extra='forbid')`). `RefereeJudgment` (core contract), `RoundRecord` (archive with `timestamp` field).

**`prompts.py`** — Four system prompt constants and four template functions. Agents import these; no string hardcoding.
- `OPPONENT_SYSTEM_PROMPT` / `opponent_prompt(current_thesis, improvement_hint="")` — Socratic questioner, ≤80 chars
- `PRESENTER_SYSTEM_PROMPT` / `presenter_prompt(current_thesis, critique, user_response)` — Response refiner
- `REFEREE_SYSTEM_PROMPT` / `referee_prompt(...)` — Learning synthesizer (silent unless terminating)
- `FINAL_SUMMARY_PROMPT` / `final_summary_prompt(...)` — End-of-session summary

**`model.py`** — `ModelConfig` dataclass. `load_model_config(env)` parses env (scripts/CI path). `has_configured_api_key(env)` centralized detection. `get_chat_model(temperature, *, model_name=None, base_url=None, api_key=None)` builds `ChatOpenAI` with `streaming=True`. Explicit `api_key` kwarg enables true per-tab key isolation. `get_chat_model_for_profile(profile, temperature=0.7)` convenience wrapper takes a `ModelProfile`.

**`providers.py`** — Pure preset registry. `ProviderPreset` frozen dataclass (id, label, icon, base_url, api_key_help_url, api_key_placeholder, api_key_required, preset_models, supports_structured_output, default_model). Built-in presets: `openai`, `deepseek`, `siliconflow`, `tongyi`, `zhipu`, `moonshot`, `ollama`, `custom`. Exports `PRESET_PROVIDERS: dict[str, ProviderPreset]`, `get_preset(id)`, `iter_presets()`, `detect_preset_by_base_url(url)` for .env migration.

**`model_store.py`** — `ModelStore` (persisted root with atomic JSON save/load), `ProviderEntry` (one configured provider instance), `ModelProfile` (resolvable model pointer: entry_id + model_name + base_url + api_key + supports_structured_output). CRUD: `add_provider`, `remove_provider`, `add_custom_model`, `remove_custom_model`, `list_models`, `set_active_profile`, `get_active_profile`, `get_profile`, `configured_providers`. Migration: `ModelStore.migrate_from_env(env_config)`.

**`connection_test.py`** — `check_connection(base_url, api_key, *, timeout=10.0, provider_id="") → ConnectionResult`. Uses stdlib `urllib.request` to test `/models` endpoint (Ollama uses `/api/tags`). Classifies errors: auth/timeout/network/server/unknown with Chinese messages. Function intentionally named `check_connection` (not `test_connection`) to avoid pytest collection.

**`logging.py`** — `trace_id_context()` (8-char trace ID), `TraceLogger` (LLM call timing/retry/error), JSON-lines output.

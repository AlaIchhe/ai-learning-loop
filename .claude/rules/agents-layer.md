---
description: agents/ 层无状态纯函数 — opponent, presenter, referee, _base 共享工具
paths:
  - "agents/**"
---

# Agents Layer — Stateless Pure Functions

Signature: `(state: AgentState, model: BaseChatModel | None = None) → dict`

Each agent is split into **compute + interact** nodes to prevent LLM re-execution on `interrupt()` resume. Compute nodes call LLM and return results. Interact nodes read cached results and call `interrupt()`.

Constraints:
- **Read only** from `state`, never mutate
- **Return** a partial update dict with only changed keys
- **`model` parameter**: default via `get_chat_model()`; Mock injected for tests; typed as `BaseChatModel`
- **Depend only on `core/` and `agents/_base.py`**, never on `ui/` or `workflow/`

## `_base.py` — Shared LLM Utilities

- `extract_content(response)` — extract string from BaseMessage
- `make_message(role, content, round_num)` — construct message dict (includes `timestamp` field)
- `invoke_llm(model, temperature, system_prompt, user_prompt, *, on_retry, trace, model_name, model_base_url)` — shared compute node skeleton with auto-retry + per-tab model override
- `invoke_with_retry(invocable, messages, *, label, on_retry, trace)` — 3-retry exponential backoff (1s/2s/4s)
- `_is_retryable(error)` — classify transient vs permanent errors
- `NodeFunc = Callable[[AgentState], dict]` — type alias

## `opponent.py`
- `opponent_compute_node` — calls LLM to generate Socratic question (≤80 chars, single-point)
- `opponent_interact_node` — calls `interrupt(critique)`, reads `_user_response` from resume

## `presenter.py`
- `presenter_compute_node` — calls LLM to refine user response into precise thesis
- `presenter_interact_node` — calls `interrupt(draft)`, reads `_confirmed_thesis` from resume

## `referee.py`
- `referee_deliberate_node(state, model=None, *, json_mode=False)` — synthesizes cognitive insights
  - `json_mode=False` (default): `with_structured_output(RefereeJudgment)` — OpenAI native
  - `json_mode=True`: JSON-mode prompting + regex extraction + Pydantic validation — DeepSeek
- `_build_round_record()` — constructs `RoundRecord` from state + judgment
- `_dump_round_record()` — normalizes `RoundRecord | dict` for JSON serialization

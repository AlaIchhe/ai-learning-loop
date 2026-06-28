---
description: 测试体系 — pytest 154 用例 (Mock) + 6 真实 API 测试 + 幽灵探针
paths:
  - "tests/**"
  - "scripts/**"
---

# Testing

## Pytest Suite (Mock LLMs, no real API) — 154 tests

Shared infrastructure:
| File | Purpose |
|------|---------|
| `tests/helpers.py` | `make_state()`, `make_initial_state()`, `make_mock_model()` |
| `tests/mock_nodes.py` | `mock_opponent_compute/interact`, `mock_presenter_compute/interact`, `make_mock_referee()` |

| File | Tests | Coverage |
|------|-------|----------|
| `test_agents.py` | 49 | Opponent (9), Presenter (10), Referee (9), Idempotency (2), Edge cases (19) |
| `test_workflow.py` | 21 | Start/next_round, routing (7 status values), graph compilation, export_graph, edge cases |
| `test_integration.py` | 6 | Single/multi-round lifecycle, interrupt state persistence |
| `test_interfaces.py` | 28 | Prompt injection, node output keys, serialization round-trip, checkpoint, routing, extra='forbid' |
| `test_model.py` | 22 | `get_chat_model()` full branch + `load_model_config()` + `has_configured_api_key()` |
| `test_smoke.py` | 21 | Module imports, model factory, graph compilation, prompt validity, state factory, E2E assembly |
| `test_base.py` | 6 | `_is_retryable` classification + retry loop behavior |
| `test_scripts.py` | 1 | Ghost probe schema contract |

Command: `python -m pytest tests/ -v`

After every pytest invocation, `scripts/cleanup.py` runs automatically via `.claude/settings.json` PostToolUse hook to remove cache dirs, build artifacts, and other generated garbage.

## Real-API Integration Tests (`scripts/integration_test_real.py`)

6 tests, uses live API keys, DeepSeek-compatible (`json_mode=True`):
1. Opponent Agent — Socratic question quality
2. Presenter Agent — response refinement quality
3. Referee JSON-mode — production guide node
4. LangGraph Single Round — full workflow
5. LangGraph Multi-Round — understanding evolution
6. Checkpoint Persistence — `get_state()` + resume

Run modes: `--quick` (single agents), `--workflow` (LangGraph only), no args (all 6).

## Ghost Probe (`scripts/ghost_probe.py`)

Standalone diagnostic (NOT in pytest). 7 probes: environment diagnostics, API connectivity, structured output, opponent/presenter/referee prompts, full round. Run: `python scripts/ghost_probe.py` (full) or `--quick` (env + connectivity).

<!-- reflex managed begin (do not edit inside this block; add custom content outside the markers) -->
# Agents

This project uses the **Reflex agent skills** — up-to-date knowledge for building full-stack Python web apps with [Reflex](https://reflex.dev). Install them first, then use them as described below.

## Installing the Skills

Before working on this project, make sure the Reflex skills are available to you.

### Claude Code

If the skills are not already available, install them yourself by running these shell commands:

```bash
claude plugin marketplace add reflex-dev/agent-skills
claude plugin install reflex@reflex-agent-skills
```

Newly installed plugins load on the next session. After installing, tell the user to restart the session so the skills auto-load; until then, read the skill files directly from `~/.claude/plugins/` when you need them.

### Other agents (Cursor, OpenCode, Codex, Pi)

```
npx skills add reflex-dev/agent-skills
```

Or clone https://github.com/reflex-dev/agent-skills and copy the `skills/` folders into your agent's skill directory (see the repo README for paths).

### Verifying

Before writing or editing any Reflex code, confirm these three skills are available: `reflex-docs`, `setup-python-env`, and `reflex-process-management`. If they are not, STOP and run the install step above — do not proceed without them.

## Using the Skills

### Reflex documentation

For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs.

### Initializing a new Reflex project

When starting a new Reflex project or setting up a development environment, you **must** follow the **setup-python-env** skill before doing anything else.

Do not skip any steps. Do not assume a virtual environment or Reflex is already available — always verify first by following the skill's instructions in order.

After the environment is ready and Reflex is installed, run:

```bash
reflex init
```

Then proceed with the user's request.

### Managing a Reflex process

When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps.
<!-- reflex managed end -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Modular rules live in `.claude/rules/` — auto-loaded based on file paths.

## Project Overview

A **Socratic learning guide** built with LangGraph + Reflex. Three LLM agents — **Questioner** (提问者), **Refiner** (精确化者), and **Guide** (引导者) — iteratively deepen the user's understanding through Socratic questioning. Human-in-the-loop uses LangGraph's `interrupt()` + `Command(resume=...)`.

## Development Commands

```bash
source venv/Scripts/activate        # (Windows Git Bash)
pip install -e ".[dev]"
cp .env.example .env

# Testing
python -m pytest tests/ -v
python scripts/integration_test_real.py
python scripts/ghost_probe.py

# Cleanup (auto-runs after pytest via .claude/settings.json hook)
python scripts/cleanup.py              # clean all dev/test/build garbage
python scripts/cleanup.py --dry-run    # preview what would be removed

# Code quality
ruff check .                        # Zero warnings
pyright .                           # Zero errors
mypy core/ agents/ workflow/ --ignore-missing-imports

# Run the app
python run.py                       # → http://localhost:3003
reflex run                          # Equivalent
PYTHONUTF8=1 reflex run             # Windows: UTF-8 required

# Export graph
python run.py --export-graph
python -m workflow.graph
```

## Project Files

| Directory/File | Purpose |
|------|---------|
| `core/` | Data contracts, model config, providers, logging |
| `agents/` | LLM compute/interact nodes |
| `workflow/` | LangGraph graph building + routing |
| `rxweb/` | Reflex UI — state, pages, styles |
| `rxweb/rxweb.py` | App entry point (routes) |
| `rxweb/state.py` | AppState — multi-tab, LangGraph streaming, provider CRUD |
| `rxweb/chat.py` | Chat page — sidebar, messages, interrupt/resume UI |
| `rxweb/model_settings.py` | Model settings page — provider list + add form |
| `rxweb/styles.py` | Global styles, color system, role config |
| `rxconfig.py` | Reflex config — ports, plugins, transport |
| `run.py` | Universal launcher |
| `scripts/cleanup.py` | Post-test garbage cleanup (cache dirs, build artifacts) |
| `.model-config.json` | Persisted provider config (gitignored) |

## Key Design Notes

- **Windows transport**: `transport="polling"` in rxconfig.py (granian WS not supported)
- **State serialization**: Use `list[dict]` not pydantic models
- **Var operations**: Always use `rx.cond`/`rx.match`, never Python `if`/`else`
- **Background tasks**: `rx_event(background=True)` (not `rx.background`)
- **Interrupt detection**: `graph.get_state(config)` after stream ends
- **Multi-tab**: `tabs` list + mirrored `active_*` fields for UI access

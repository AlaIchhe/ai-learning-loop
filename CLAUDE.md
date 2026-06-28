# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Modular rules live in `.claude/rules/` — auto-loaded based on file paths. See individual files for domain-specific conventions.

## Project Overview

A **Socratic learning guide** built with LangGraph. Three LLM agents — **Questioner** (提问者), **Refiner** (精确化者), and **Guide** (引导者) — iteratively deepen the user's understanding of a topic through Socratic questioning, collaborative refinement, and incremental synthesis. Human-in-the-loop control uses LangGraph's dynamic `interrupt()` + `Command(resume=...)` mechanism via a Streamlit UI. LangSmith provides full observability, and `core/model.py` enables switching between OpenAI, DeepSeek, and any OpenAI-compatible provider without code changes.

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

The `LLM_API_KEY` falls back to `OPENAI_API_KEY` if not set. If neither is configured, `get_chat_model()` emits a `RuntimeWarning` and uses a placeholder key — the real error surfaces when the LLM is first invoked.

## Project Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, dependencies, ruff/mypy/pyright/pytest config |
| `run.py` | Universal launcher — `python run.py` from any directory |
| `requirements.txt` | Runtime dependencies only (minimum version constraints; no dev tools) |
| `requirements-lock.txt` | Pinned dependency versions for reproducible deployments |
| `.streamlit/config.toml` | Theme config: light/dark dual themes, academic blue brand color, hidden default menus |
| `ui/style.css` | Global stylesheet: fonts, message bubbles, button animations, dark mode, scrollbar, cursor blink |
| `ui/style.py` | `inject_global_css()` — CSS + auto-scroll JS injection; `typing_cursor_html()` — blink cursor fragment |

## Adding a New Provider

1. Edit `.env`:
   ```
   LLM_MODEL=your-model-name
   LLM_BASE_URL=https://your-api/v1
   LLM_API_KEY=your-key
   ```
2. Done. `get_chat_model()` picks it up automatically. Any OpenAI-compatible API works (DeepSeek, Ollama, vLLM, SiliconFlow, etc.). If the provider doesn't support `with_structured_output`, use `referee_deliberate_node(json_mode=True)` for DeepSeek-compatible JSON-mode handling.

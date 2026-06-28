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

# Frontend visual verification (Playwright MCP must be configured globally)
# 1. In a separate terminal: python run.py        # starts Streamlit on :8501
# 2. Ask Claude to use browser tools: navigate → screenshot → inspect
# Example prompts:
#   "Navigate to http://localhost:8501, take a screenshot, describe the UI"
#   "Type a topic into the input, click Start debate, wait 2s, screenshot"
```

## Model Configuration

Models are managed via the in-app **🔧 模型设置** page (recommended) or via `.env` (backward compatible for scripts/CI).

**Method A — UI (recommended):** Launch the app, navigate to "🔧 模型设置" in the sidebar. Add providers, test connections, select default model. Config persists to `.model-config.json` (gitignored) and survives restarts.

Built-in provider presets: OpenAI, DeepSeek, SiliconFlow (硅基流动), Tongyi Qwen (通义千问), Zhipu GLM (智谱), Moonshot Kimi (月之暗面), Ollama (本地), and a "custom OpenAI-compatible" option. Each preset includes known base URL, preset models, and `json_mode` auto-detection for providers that don't support native `with_structured_output`.

**Method B — `.env` (backward compatible):** Copy `.env.example` to `.env` and configure:

```bash
LLM_MODEL=deepseek-chat                          # or gpt-4o
LLM_BASE_URL=https://api.deepseek.com/v1         # omit for OpenAI
LLM_API_KEY=sk-your-key-here

# LangSmith tracing (optional)
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=lsv2_pt_your-key
# LANGCHAIN_PROJECT=ai-learning-loop
```

On first launch with a `.env` present, settings are auto-migrated to `.model-config.json`. The `LLM_API_KEY` falls back to `OPENAI_API_KEY` if not set. Scripts (`scripts/integration_test_real.py`, `scripts/ghost_probe.py`) continue to work purely via env vars.

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
| `core/providers.py` | Preset provider registry (8 built-in providers); `detect_preset_by_base_url()` for env migration |
| `core/model_store.py` | `ModelStore` / `ProviderEntry` / `ModelProfile` — JSON persistence, CRUD, env migration |
| `core/connection_test.py` | `test_connection()` — API connectivity test with Chinese error classification (auth/timeout/network/server) |
| `ui/model_settings.py` | `render_model_settings_page()` — model management page (add/edit/delete providers, connection test, custom models) |
| `.model-config.json` | Persisted model/provider configuration (gitignored; auto-migrated from `.env` on first run) |

## Adding a New Preset Provider

Add a `ProviderPreset` entry to `core/providers.py::_PRESETS_ORDERED` with: `id`, `label`, `icon`, `base_url` (None for OpenAI), `api_key_help_url`, `api_key_placeholder`, `api_key_required`, `preset_models` tuple, and `supports_structured_output=False` for providers that need JSON-mode (DeepSeek, most Chinese providers). No other code changes needed — the Model Store, migration, sidebar, and settings page pick up the new preset automatically.

Per-model `json_mode` is now handled automatically: the ModelStore's `ModelProfile.supports_structured_output` flag is frozen into `AgentState._model_json_mode` at debate start, and `referee_deliberate_node` OR's this with its explicit `json_mode` parameter. No code-level changes are needed when adding a new provider that requires JSON-mode — just set `supports_structured_output=False` on the preset.

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
pip install -e ".[dev,test]"
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
ruff format .                       # Auto-format
pyright .                           # Zero errors (strict mode)
mypy socratic_loop/core/ socratic_loop/infra/ socratic_loop/agents/ socratic_loop/workflow/ --ignore-missing-imports

# Run the app
ai-learning-loop                    # → http://localhost:3003 (console_scripts 入口)
python -m socratic_loop             # 等价
reflex run                          # 直接使用 Reflex CLI
PYTHONUTF8=1 reflex run             # Windows: UTF-8 required

# Export graph
debate-graph                        # console_scripts 入口
python -m socratic_loop.workflow.graph

# Build & publish
make build                          # 构建 wheel + sdist
make publish-test                   # 发布到 TestPyPI
make publish                        # 发布到 PyPI

# Docker
make docker-build                   # 构建 Docker 镜像
make docker-run                     # 运行容器
```

## Packaging & Distribution

- **构建系统**: setuptools + `pyproject.toml`（PEP 621 元数据）
- **包发现**: `socratic_loop*` + `web*`（扁平布局）
- **入口点**: `ai-learning-loop` → `socratic_loop.__main__:main`
- **包数据**: `web/assets/*` 通过 `package-data` 自动包含
- **版本**: 单一来源 `socratic_loop.__init__.__version__`
- **CI/CD**: GitHub Actions — test → build → publish（tag 触发）
- **发布目标**: PyPI（OIDC 可信发布，无需 API token）
- **容器**: 多阶段 Dockerfile + docker-compose.yml

## Project Files

| Directory/File | Purpose |
|------|---------|
| `socratic_loop/core/` | 契约层 — schemas, state, prompts（纯数据/纯函数） |
| `socratic_loop/infra/` | 基础设施层 — env, model, providers, model_store, logging, connection_test |
| `socratic_loop/agents/` | LLM compute/interact nodes |
| `socratic_loop/workflow/` | LangGraph graph building + routing |
| `socratic_loop/__main__.py` | CLI 入口（`ai-learning-loop` 命令） |
| `web/` | Reflex UI — state, pages, styles |
| `web/app.py` | App entry point (routes) |
| `web/state.py` | AppState — Tab 管理 + UI 状态 |
| `web/streaming.py` | LangGraph 流式管道（StreamingMixin） |
| `web/providers.py` | 模型提供商 CRUD（ProviderMixin） |
| `web/_globals.py` | Web 层全局单例 + 辅助函数 |
| `web/chat.py` | Chat page — sidebar, messages, interrupt/resume UI |
| `web/settings.py` | Model settings page — provider list + add form |
| `web/styles.py` | Global styles, color system, role config |
| `rxconfig.py` | Reflex config — ports, plugins, transport |
| `pyproject.toml` | ★ 单一权威配置（依赖、工具、入口点） |
| `Makefile` | 常用操作快捷方式 |
| `Dockerfile` | 多阶段构建（deps → runtime） |
| `docker-compose.yml` | 容器编排配置 |
| `MANIFEST.in` | sdist 内容控制 |
| `scripts/cleanup.py` | Post-test garbage cleanup (cache dirs, build artifacts) |
| `.model-config.json` | Persisted provider config (gitignored) |

## Key Design Notes

- **Layered architecture**: `core/` (contracts) → `infra/` (infrastructure) → `agents/` (LLM nodes) → `workflow/` (orchestration) → `web/` (UI). Dependencies flow downward only.
- **Windows transport**: `transport="polling"` in rxconfig.py (granian WS not supported)
- **State serialization**: Use `list[dict]` not pydantic models
- **Var operations**: Always use `rx.cond`/`rx.match`, never Python `if`/`else`
- **Background tasks**: `rx_event(background=True)` (not `rx.background`)
- **Interrupt detection**: `graph.get_state(config)` after stream ends
- **Multi-tab**: `tabs` list + mirrored `active_*` fields for UI access
- **Packaging**: `pyproject.toml` 是单一权威配置入口；`requirements.txt` / `requirements-lock.txt` 已废弃，不再使用

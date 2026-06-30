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
# ── uv 安装（首次） ──
uv sync --all-extras                # 安装所有依赖（含 dev + test）
cp .env.example .env

# ── 运行（uv run 自动使用项目 venv，无需手动 activate） ──
uv run ai-learning-loop             # → http://localhost:3003
uv run python -m socratic_loop      # 等价
uv run debate-graph                 # 导出架构图
uv run reflex run                   # 直接使用 Reflex CLI

# ── 测试 ──
uv run python -m pytest tests/ -v
uv run python scripts/integration_test_real.py
uv run python scripts/ghost_probe.py

# ── 静态检查 ──
uv run ruff check .                 # 零警告
uv run ruff format .                # 自动格式化
uv run pyright                      # strict 模式（仅扫描 socratic_loop/）
uv run mypy socratic_loop/core/ socratic_loop/infra/ socratic_loop/agents/ socratic_loop/workflow/ --ignore-missing-imports

# ── 依赖管理 ──
uv lock                             # 更新 uv.lock
uv sync --all-extras --frozen       # 精确安装（CI 用）
uv add <package>                    # 添加运行时依赖
uv add --dev <package>              # 添加开发依赖

# ── 构建 & 发布 ──
uv build                            # 构建 wheel + sdist
uv twine check dist/*               # 验证包完整性
uv publish dist/*                   # 发布到 PyPI

# ── Docker ──
docker compose build                # 多阶段构建（uv 驱动）
docker compose up -d                # 运行容器

# ── 清理（auto-runs after pytest via .claude/settings.json hook） ──
uv run python scripts/cleanup.py    # 清理所有开发/测试/构建垃圾
```

## Dependency Management（uv）

- **工具**: [uv](https://github.com/astral-sh/uv) — Rust 编写的极速 Python 包管理器（10-100x 快于 pip）
- **Python 版本**: `.python-version` 固定 3.11
- **锁文件**: `uv.lock`（自动生成，提交到 git，确保可重现构建）
- **依赖声明**: `pyproject.toml` 是唯一权威来源
  - `[project.dependencies]` — 运行时依赖
  - `[project.optional-dependencies]` — 可选组（dev/test/ci）
  - `[dependency-groups]` — uv 原生开发依赖（PEP 735）
- **虚拟环境**: uv 自动管理 `.venv/`，无需手动 `source activate`
- **命令模式**: `uv run <cmd>` 自动在项目 venv 中执行

## Packaging & Distribution

- **构建系统**: setuptools + `pyproject.toml`（PEP 621 元数据）
- **构建命令**: `uv build`（替代 `python -m build`）
- **包发现**: `socratic_loop*` + `web*`（扁平布局）
- **入口点**: `ai-learning-loop` → `socratic_loop.__main__:main`
- **包数据**: `web/assets/*` 通过 `package-data` 自动包含
- **版本**: 单一来源 `socratic_loop.__init__.__version__`
- **CI/CD**: GitHub Actions — test → build → publish（tag 触发，uv 驱动）
- **发布目标**: PyPI（OIDC 可信发布，无需 API token）
- **容器**: 多阶段 Dockerfile（`uv sync --frozen --no-dev`）

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

## 环境变量参考（core/settings.py 读取）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FRONTEND_PORT` | `3003` | Reflex 前端端口 |
| `BACKEND_PORT` | `8003` | Reflex 后端端口 |
| `DB_URL` | `sqlite:///reflex.db` | Reflex 数据库 |
| `REFLEX_TRANSPORT` | `auto` | 传输协议：`auto`/`polling`/`websocket` |
| `LLM_MODEL` | `gpt-4o` | LLM 模型名称 |
| `LLM_BASE_URL` |（空） | LLM API 端点（空=OpenAI 官方） |
| `LLM_API_KEY` |（空） | LLM API Key（优先级高于 OPENAI_API_KEY） |
| `OPENAI_API_KEY` |（空） | OpenAI API Key（回退） |
| `LANGCHAIN_TRACING_V2` | `false` | 启用 LangSmith 追踪 |
| `LANGCHAIN_API_KEY` |（空） | LangSmith API Key |
| `LANGCHAIN_PROJECT` | `ai-learning-loop` | LangSmith 项目名 |
| `LLM_MAX_RETRIES` | `3` | LLM 调用最大重试次数（1-10） |
| `LLM_RETRY_BACKOFF_BASE` | `1.0` | 指数退避基数（秒） |
| `CONNECTION_TIMEOUT` | `10.0` | API 连通性测试超时（秒） |

## Key Design Notes

- **Layered architecture**: `core/` (contracts) → `infra/` (infrastructure) → `agents/` (LLM nodes) → `workflow/` (orchestration) → `web/` (UI). Dependencies flow downward only.
- **统一配置管理**: `core/settings.py`（pydantic-settings `BaseSettings`）是所有环境变量的唯一读取器，集中声明、验证、提供默认值。`infra/model.py:load_model_config()` 和 `has_configured_api_key()` 是其薄封装；`agents/_base.py` 重试配置、`infra/connection_test.py` 超时、`rxconfig.py` 端口/传输均从中读取。`.env` 由 `infra/env.py:setup_environment()`（`load_dotenv`）单一加载——`settings` 不自行加载 `.env`。端口在 `rxconfig.py` 与 `docker-compose.yml` 间通过 `FRONTEND_PORT`/`BACKEND_PORT` 环境变量统一，消除三处重复。`transport` 默认 `auto`（Windows→polling，其他→websocket），可通过 `REFLEX_TRANSPORT` 覆盖。
- **Windows transport**: `transport="auto"` in rxconfig.py → `settings.effective_transport()`（Windows 自动 polling，其他平台 websocket，可用 `REFLEX_TRANSPORT` 覆盖）
- **State serialization**: Use `list[dict]` not pydantic models
- **Var operations**: Always use `rx.cond`/`rx.match`, never Python `if`/`else`
- **Background tasks**: `rx_event(background=True)` (not `rx.background`)
- **Interrupt detection**: `graph.get_state(config)` after stream ends
- **Multi-tab**: `tabs` list + mirrored `active_*` fields for UI access
- **Packaging**: `pyproject.toml` 是单一权威配置入口；`uv.lock` 是锁文件；`requirements.txt` / `requirements-lock.txt` 已废弃并移除

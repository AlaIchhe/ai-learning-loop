# Changelog

所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 项目结构重构：`core/` 拆分为 `core/`（契约层）+ `infra/`（基础设施层）
- `web/state.py` 拆分为 `state.py` + `streaming.py` + `providers.py` + `_globals.py`
- 新增 `build_default_graph()` 解除 web→agents 直接耦合
- 所有 `__init__.py` 添加显式 `__all__`
- 新增 `ai-learning-loop` CLI 入口（console_scripts）
- 新增 `py.typed` 标记文件（PEP 561）
- 新增 `MANIFEST.in` 控制 sdist 内容

### Changed
- `web/web.py` → `web/app.py`
- `web/model_settings.py` → `web/settings.py`
- pyproject.toml 整合为单一权威配置入口
- 移除 `requirements.txt` / `requirements-lock.txt`（以 pyproject.toml 为准）

## [1.0.0] - 2026-06-30

### Added
- 三智能体苏格拉底式学习引导系统初始版本
- Opponent（提问者）、Presenter（精确化者）、Referee（Referee）三节点
- LangGraph 状态图编排 + 动态 interrupt/resume
- Reflex 多 Tab 响应式 UI
- 多提供商支持（OpenAI / DeepSeek / SiliconFlow / 通义 / 智谱 / Kimi / Ollama / 自定义）
- Per-tab 模型配置隔离
- Token 级流式输出 + 打字光标动画
- 结构化日志与 trace_id 追踪
- 连通性测试 + 提供商 CRUD
- 211 个 mock 测试 + 真实 API 集成测试
- CI 流水线（pytest + ruff + pyright + mypy）

# 🎓 多智能体论题演化系统

基于 LangGraph 的三智能体认知深化系统。**批判者**攻击论题的边界与隐含前提、**精确化者**将用户回应转化为精确表述、**裁判**将每轮讨论揭示的新认知层次有机拼合到论题中（一句话逐步生长为一段话）。Streamlit 提供动态中断人机协作界面，LangSmith 提供全链路可观测性。

## 核心机制

```
每轮:
  批判者 攻击论题边界/前提 → 生成 critique → [动态中断: 用户回应]
  精确化者 读用户回应 → 生成 draft_thesis → [动态中断: 用户确认]
  裁判 拼合新认知层次 → 有机追加到 current_thesis → 继续/结束
       │
       └── improvement_hint 反馈到下一轮批判者（闭环比批评循环）
```

- **批判者（Opponent）**：攻击论题最薄弱的一个边界或隐含前提，三选一策略（逻辑漏洞 / 边界追问 / 反例证伪），单点突破，极简输出。裁判的 `improvement_hint` 为其提供上一轮的精准攻击方向。哲学基础：真理是具体的、有条件的。
- **精确化者（Presenter）**：将用户非正式回应转化为边界清晰的精确论题表述，保留核心意图、消解歧义、明确适用范围。
- **裁判（Referee）**：将每轮讨论中揭示的新边界、新限定有机拼合到论题中（保留核心主张，融入新层次）。正常轮次静默不输出，仅在辩论终止时生成总结报告。支持两种输出策略：`with_structured_output`（OpenAI 原生）和 JSON-mode 手动解析（DeepSeek 兼容）。

`current_thesis` 是唯一跨轮次持久化的状态。每轮经批判、回应、精确化、确认后，裁判将新认知层次拼合进去，论题从一句话逐步生长为一段逻辑递进的完整论述，直到裁判判定充分深化为止。

## 代码质量

项目通过三层静态分析，全部零告警：

| 工具 | 命令 | 严格度 |
|------|------|--------|
| Ruff | `ruff check .` | 零告警 |
| Pyright | `pyright .` | strict 模式零错误 |
| Mypy | `mypy core/ agents/ workflow/` | 零错误 |

## 图结构

运行 `python -m workflow.graph` 或 `python run.py --export-graph` 可导出最新架构图。

![Graph Architecture](graph_architecture.png)

## 快速开始

### 环境要求

- Python ≥ 3.11
- LLM API Key（DeepSeek / OpenAI / 其他兼容供应商任选其一）
- （可选）LangSmith API Key，用于链路追踪

### 配置

```bash
# 1. 克隆项目后，复制环境变量模板
cp .env.example .env

# 2. 编辑 .env，填入你的 API Key
#    默认配置为 DeepSeek，取消注释即可切换 OpenAI 或其他供应商
```

`.env` 示例：

```bash
# 方案 1: DeepSeek（默认）
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-your-deepseek-api-key

# 方案 2: OpenAI（取消注释下面三行，注释掉上面三行）
# LLM_MODEL=gpt-4o
# LLM_API_KEY=sk-your-openai-api-key

# 方案 3: 其他 OpenAI 兼容供应商（Ollama / vLLM / 硅基流动 等）
# LLM_MODEL=your-model
# LLM_BASE_URL=https://your-api-endpoint/v1
# LLM_API_KEY=your-api-key

# LangSmith 链路追踪（可选；需要真实 LangSmith Key 时再取消注释）
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=lsv2_pt_your-key-here
# LANGCHAIN_PROJECT=ai-learning-loop
```

### 安装

```bash
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
# source venv/bin/activate     # macOS / Linux
pip install -e ".[dev]"
```

依赖文件角色：

- `pyproject.toml` 是开发环境的权威入口，包含运行时依赖和 `pytest` / `ruff` / `pyright` / `mypy` 等开发工具。
- `requirements.txt` 仅保留运行时最小版本约束，适合不需要开发工具的轻量部署。
- `requirements-lock.txt` 固定已验证版本，适合需要可复现构建的环境。

### 启动界面

```bash
# 推荐：通用启动器，自动处理路径和 .env 加载
python run.py

# 或者标准 Streamlit 方式（需在项目根目录执行）
streamlit run ui/app.py
```

在侧边栏输入初始论题，点击「开始辩论」。系统会依次展示批判者的质疑（你需要回应）和精确化者的草稿（你需要确认），点击「提交回应」/「确认论题」推进演化。

### API Key 配置方式

**推荐：通过 `.env` 文件配置**（支持多供应商、LangSmith 追踪，配置持久化）：

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

启动后侧边栏会自动检测 `.env` 配置并展示供应商信息。如需临时切换 Key，展开「手动覆盖 API Key」折叠面板即可。

**备选：通过侧边栏直接输入**（适合临时演示、未配置 `.env` 时）：

未检测到 `.env` 时，侧边栏会自动显示 API Key 输入框和高级模型设置。这些设置仅当前会话有效，刷新后需重新输入。注意：LangSmith 追踪必须通过 `.env` 配置（需在 LangChain 导入前设置环境变量）。

> **提示**：`python run.py` 从任意目录执行都能自动定位项目根目录并加载 `.env`。环境初始化统一由 `core/env.py` 的 `setup_environment()` 处理。

### 运行测试

```bash
python -m pytest tests/ -v    # Mock LLM，无需真实 API
```

### 真实 API 集成测试

```bash
python scripts/integration_test_real.py           # 6 个集成测试全量运行（需 API Key）
python scripts/integration_test_real.py --quick   # 仅单 Agent 测试
python scripts/integration_test_real.py --workflow  # 仅 LangGraph 工作流测试
```

使用真实 API Key 测试完整系统（无 Mock）。覆盖 Opponent / Presenter / Referee 单 Agent 有效性、LangGraph 完整单轮/多轮工作流、Checkpoint 持久性。**适配 DeepSeek**：裁判直接使用生产代码 `referee_deliberate_node(json_mode=True)`，无需重复实现。

### 幽灵探针（环境诊断）

```bash
python scripts/ghost_probe.py           # 7 个探针全量运行，验证 LLM 环境健康
python scripts/ghost_probe.py --quick   # 仅快速探针（环境诊断 + API 连通性）
```

幽灵探针是独立的诊断脚本，用真实 API Key 探测 LLM 供应商环境：API 连通性、结构化输出合规、三个 Agent 提示词有效性、完整一轮协作。不纳入 pytest。

## 支持的大模型供应商

通过 `core/model.py` 的 `get_chat_model()` 工厂函数，无需修改任何代码即可切换 LLM：

| 供应商 | LLM_MODEL | LLM_BASE_URL |
|--------|-----------|--------------|
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| OpenAI | `gpt-4o` | （留空） |
| 硅基流动 | `Qwen/Qwen3-235B-A22B` | `https://api.siliconflow.cn/v1` |
| Ollama (本地) | `llama3` | `http://localhost:11434/v1` |
| 其他兼容供应商 | 任意 | 填入对应的 `/v1` 端点 |

> **DeepSeek 用户注意**：DeepSeek 不支持 `with_structured_output`（底层依赖 `response_format`）。系统已内置 JSON-mode 兼容策略，裁判节点通过 `json_mode=True` 参数自动切换到提示词引导 + 正则提取 + Pydantic 验证的方式，无需手动适配。

## 可观测性

开启 LangSmith 后，每次论题演化会自动记录：

- 每个 Node（opponent / presenter / referee）的**输入输出和耗时**
- LLM 调用的**完整 Prompt 和原始 Response**
- **Token 用量**统计
- Graph 节点间的**调用拓扑**

访问 [smith.langchain.com](https://smith.langchain.com) 查看追踪面板。

## 项目结构

```
ai-learning-loop/
├── core/                    # 核心契约（所有模块的依赖根）
│   ├── env.py               # 统一环境初始化（sys.path + .env 加载）
│   ├── state.py             # AgentState（6 持久字段 + 5 轮次缓存）+ make_initial_state + validate_state_shape + NodeOutput
│   ├── schemas.py           # Pydantic 结构化模型（_StrictModel 基类，extra='forbid'）
│   ├── prompts.py           # System Prompt 与模板函数（批判/精确化/拼合/总结）
│   └── model.py             # ModelConfig + load_model_config + has_configured_api_key + get_chat_model
├── agents/                  # 智能体节点（无状态纯函数，compute + interact 拆分）
│   ├── _base.py             # 共享 LLM 工具（内容提取/消息构造/调用重试）
│   ├── opponent.py          # 批判者：攻击论题边界/前提 → critique（compute）/ interrupt 展示（interact）
│   ├── presenter.py         # 精确化者：用户回应 → draft_thesis（compute）/ interrupt 确认（interact）
│   └── referee.py           # 裁判：双策略拼合 + _build_round_record / _dump_round_record 归档辅助 + 判定 + 总结
├── workflow/                # 编排层
│   └── graph.py             # LangGraph 图组装（8 节点）、条件路由、export_graph()
├── ui/                      # 展现层
│   └── app.py               # Streamlit 界面：复用 setup_environment + has_configured_api_key，env override 收敛至 _apply_* helper
├── tests/                   # 测试（Mock LLM，无需真实 API，154 个用例）
│   ├── helpers.py           # 共享工厂函数（make_state / make_mock_model / make_initial_state）
│   ├── mock_nodes.py        # 共享 Mock Agent 节点（含 interrupt()）
│   ├── test_agents.py       # agent 节点契约 + 中断幂等性 + 边界/错误路径 + referee helper 覆盖
│   ├── test_workflow.py     # 调度节点、路由、图编译、export_graph、边界值 + state validation 入口
│   ├── test_integration.py  # 中断/恢复多轮生命周期、论题演化链
│   ├── test_interfaces.py   # 跨层接口、序列化、checkpoint、路由、prompt 边界
│   ├── test_model.py        # get_chat_model() 全分支 + ModelConfig + has_configured_api_key
│   ├── test_smoke.py        # 模块导入、图编译、prompt 有效性、state factory、UI 侧边栏配置、端到端组装
│   ├── test_base.py         # retry/backoff 分类与重试循环行为
│   └── test_scripts.py      # ghost probe 与核心 schema 契约一致性
├── scripts/                 # 诊断与集成测试工具
│   ├── ghost_probe.py       # 幽灵探针：7 个 LLM 环境探针（诊断 / API / 提示词 / 完整流程）
│   └── integration_test_real.py  # 真实 API 集成测试（6 个用例，复用生产裁判节点）
├── .github/workflows/       # CI 工作流
│   └── ci.yml               # 自动运行 pytest + ruff + pyright + mypy（无真实 API Key）
├── pyproject.toml           # 项目元数据、依赖、ruff/mypy/pyright/pytest 配置
├── run.py                   # 通用启动器（从任意目录 python run.py，失败明确传播非零退出码）
├── .env.example             # 环境变量模板（LangSmith 默认关闭，需有真实 Key 再取消注释）
├── requirements.txt         # 运行时依赖（最小版本约束）
├── requirements-lock.txt    # 锁定依赖（可重现构建）
├── CLAUDE.md                # Claude Code 开发指南
└── graph_architecture.png   # 图结构（自动导出）
```

## 架构原则

| 层级 | 职责 | 禁止 |
|------|------|------|
| `core/` | 数据契约（State、Schema、Prompt、Model、Env） | 不得包含业务逻辑 |
| `agents/` | 调用 LLM 生成内容（compute），通过 interrupt() 交互（interact） | 不得修改 State、不得自行扩展字段 |
| `workflow/` | 状态流转、条件路由、节点编排 | 不得包含 LLM 调用、不得配置 interrupt_before |
| `ui/` | 渲染数据、收集输入、检测中断并展示对应 UI | 不得修改 graph state、不得包含业务逻辑 |

- **统一环境初始化**：`core/env.py` 的 `setup_environment()` 消除 `run.py`、`ui/app.py` 和 `scripts/*.py` 中的分散初始化代码重复
- **模型工厂**：`get_chat_model()` 读取环境变量创建 LLM 实例，支持任意 OpenAI 兼容供应商。`load_model_config()` 将 env 解析为 `ModelConfig`，`has_configured_api_key()` 集中判断是否配置了真实 API Key（占位符不算）
- **State 工厂与验证**：`make_initial_state(thesis)` 是唯一权威的初始状态构造入口（UI、脚本、测试均复用）。`validate_state_shape(state)` 在 workflow 入口提供运行时校验，不完整状态在调度层早失败
- **LLM 依赖注入**：Agent 节点的 `model` 参数使用 `BaseChatModel` 类型（不再耦合 `ChatOpenAI`），方便测试和切换供应商
- **LLM 调用自动重试**：`invoke_with_retry()` 对所有瞬时错误（网络/超时/速率限制）自动重试 3 次，指数退避（1s/2s/4s）。`_is_retryable()` 通过异常名匹配判断可重试性
- **动态中断（`interrupt()`）**：人工介入通过节点内部的 `interrupt()` 调用实现，搭配 `Command(resume=...)` 恢复，不使用静态 `interrupt_before`
- **Compute/Interact 拆分**：每个需要人工介入的 Agent 拆为 compute（LLM 调用，无中断）和 interact（无 LLM，含 `interrupt()`）两个节点，避免 resume 时 LLM 重复执行
- **状态分离**：`st.session_state` 仅存 UI 元数据，论题演化状态完全存储在 LangGraph checkpointer 中
- **`current_thesis` 拼合式演化**：论题以"层层叠加"方式生长（原始核心主张 + 每轮发现的新认知层次 → 一句话生长为一段话）。批判、草稿、确认、改进方向均为 `_` 前缀轮次缓存，每轮清空
- **裁判双策略**：`referee_deliberate_node(json_mode=False/True)` — 默认使用 `with_structured_output`，DeepSeek 等不支持 `response_format` 的提供商可切换到 JSON-mode 手动解析
- **裁判静默路由**：正常轮次中裁判不输出对用户可见的消息，仅静默更新 `current_thesis` 并判定路由。`improvement_hint` 通过 `_improvement_hint` 缓存字段反馈给下一轮批判者
- **Schema 严格验证**：`_StrictModel` 基类 `ConfigDict(extra='forbid')` 拒绝未定义字段；移除 `RefereeJudgment.round`（始终被代码覆盖）

## 依赖

| 包 | 用途 |
|----|------|
| `langgraph` | 状态图编排、动态中断、checkpointer |
| `langchain-core` | 消息类型（SystemMessage / HumanMessage）、BaseChatModel |
| `langchain-openai` | 模型调用（兼容 OpenAI / DeepSeek / 所有兼容 API） |
| `pydantic` | 结构化数据模型与校验 |
| `streamlit` | Web UI |
| `python-dotenv` | 加载 `.env` 环境变量 |

### 开发依赖

| 工具 | 用途 |
|------|------|
| `ruff` | 代码风格与 Lint（零告警） |
| `pyright` | Strict 模式类型检查（零错误） |
| `mypy` | 补充类型检查（零错误） |
| `pytest` | 单元测试（Mock LLM，无需真实 API） |

## License

MIT

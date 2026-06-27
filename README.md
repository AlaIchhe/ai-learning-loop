# 🎓 多智能体辩论学习系统

基于 LangGraph 的三智能体对抗与精炼模型。**陈述者**构建论点、**反驳者**寻找漏洞、**裁判**结构化评分，多轮迭代打磨观点。Streamlit 提供分步可控的人机协作界面，LangSmith 提供全链路可观测性。

## 核心机制

```
第 N 轮:  陈述者 → 反驳者 → 裁判 ──→ 继续/结束
第 N+1 轮:  陈述者（考虑上轮反驳）→ 反驳者 → 裁判 ──→ ...
```

- **陈述者**：围绕主题构建有说服力的论点，后续轮次会针对反驳做出回应
- **反驳者**：审视陈述者论点，指出逻辑漏洞、证据缺陷和推理谬误
- **裁判**：四维评分（清晰度/逻辑性/论据/说服力），输出结构化 JSON，判定胜负

每轮辩论结束后，裁判决定是进入下一轮还是终止辩论。

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

# LangSmith 链路追踪（可选，推荐开启）
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_your-key-here
LANGCHAIN_PROJECT=ai-learning-loop
```

### 安装

```bash
python -m venv venv
source venv/Scripts/activate   # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

### 启动界面

```bash
# 推荐：通用启动器，自动处理路径和 .env 加载
python run.py

# 或者标准 Streamlit 方式（需在项目根目录执行）
streamlit run ui/app.py
```

在侧边栏输入辩论主题，点击「开始辩论」，然后逐步点击「继续」观察三位智能体的对抗过程。

> **提示**：`python run.py` 从任意目录执行都能自动定位项目根目录并加载 `.env`。未找到 `.env` 时会给出提示，未配置 API Key 时会输出诊断警告。

### 运行测试

```bash
python -m pytest tests/ -v    # 57 个用例，Mock LLM，无需真实 API
```

## 支持的大模型供应商

通过 `core/model.py` 的 `get_chat_model()` 工厂函数，无需修改任何代码即可切换 LLM：

| 供应商 | LLM_MODEL | LLM_BASE_URL |
|--------|-----------|--------------|
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| OpenAI | `gpt-4o` | （留空） |
| 硅基流动 | `Qwen/Qwen3-235B-A22B` | `https://api.siliconflow.cn/v1` |
| Ollama (本地) | `llama3` | `http://localhost:11434/v1` |
| 其他兼容供应商 | 任意 | 填入对应的 `/v1` 端点 |

## 可观测性

开启 LangSmith 后，每次辩论会自动记录：

- 每个 Node（presenter / opponent / referee）的**输入输出和耗时**
- LLM 调用的**完整 Prompt 和原始 Response**
- **Token 用量**统计
- Graph 节点间的**调用拓扑**

访问 [smith.langchain.com](https://smith.langchain.com) 查看追踪面板。

## 项目结构

```
ai-learning-loop/
├── core/                    # 核心契约（所有模块的依赖根）
│   ├── state.py             # AgentState + AgentStateOverrides + NodeOutput
│   ├── schemas.py           # Pydantic 结构化模型（RefereeJudgment 等）
│   ├── prompts.py           # System Prompt 与模板函数
│   └── model.py             # LLM 模型工厂（多供应商切换，缺失 API Key 自动警告）
├── agents/                  # 智能体节点（无状态纯函数）
│   ├── presenter.py         # 陈述者：主题 → 论点
│   ├── opponent.py          # 反驳者：论点 → 反驳
│   └── referee.py           # 裁判：双方陈词 → 结构化评分
├── workflow/                # 编排层
│   └── graph.py             # LangGraph 图组装、条件路由、断点配置、export_graph()
├── ui/                      # 展现层
│   └── app.py               # Streamlit 界面（纯渲染，路径自适应 .env 加载）
├── tests/                   # 测试（Mock LLM，57 个用例）
│   ├── test_agents.py       # 22 个用例：节点输入输出契约
│   ├── test_workflow.py     # 12 个用例：调度节点、路由、图编译
│   ├── test_integration.py  # 3 个用例：多轮端到端生命周期
│   └── test_interfaces.py   # 20 个用例：跨层接口、序列化、checkpoint
├── pyproject.toml           # 项目元数据、依赖、ruff/mypy/pyright/pytest 配置
├── run.py                   # 通用启动器（从任意目录 python run.py）
├── .env.example             # 环境变量模板
├── requirements.txt
├── CLAUDE.md                # Claude Code 开发指南
└── graph_architecture.png   # 图结构（自动导出）
```

## 架构原则

| 层级 | 职责 | 禁止 |
|------|------|------|
| `core/` | 数据契约（State、Schema、Prompt、Model） | 不得包含业务逻辑 |
| `agents/` | 调用 LLM 生成内容，返回部分状态更新 | 不得修改 State、不得自行扩展字段 |
| `workflow/` | 状态流转、条件路由、断点调度 | 不得包含 LLM 调用 |
| `ui/` | 渲染数据、收集输入 | 不得修改 graph state、不得包含业务逻辑 |

- **模型工厂**：`get_chat_model()` 读取环境变量创建 LLM 实例，支持任意 OpenAI 兼容供应商
- **LLM 依赖注入**：Agent 节点的 `model` 参数可替换，方便测试和切换供应商
- **断点（interrupt_before）**：默认在每个 Agent 前暂停，用户可在 UI 中逐步推进
- **状态分离**：`st.session_state` 仅存 UI 元数据，辩论状态存储在 LangGraph checkpointer 中
- **自定义角色**：消息使用 `presenter`/`opponent`/`referee` 角色，而非 LangChain 标准类型

## 依赖

| 包 | 用途 |
|----|------|
| `langgraph` | 状态图编排、断点、checkpointer |
| `langchain-core` | 消息类型（SystemMessage / HumanMessage） |
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
| `pytest` | 单元测试（57 个用例） |

## License

MIT

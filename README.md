# 🎓 多智能体辩论学习系统

基于 LangGraph 的三智能体对抗与精炼模型。**陈述者**构建论点、**反驳者**寻找漏洞、**裁判**结构化评分，多轮迭代打磨观点。Streamlit 提供分步可控的人机协作界面。

## 核心机制

```
第 N 轮:  陈述者 → 反驳者 → 裁判 ──→ 继续/结束
第 N+1 轮:  陈述者（考虑上轮反驳）→ 反驳者 → 裁判 ──→ ...
```

- **陈述者**：围绕主题构建有说服力的论点，后续轮次会针对反驳做出回应
- **反驳者**：审视陈述者论点，指出逻辑漏洞、证据缺陷和推理谬误
- **裁判**：四维评分（清晰度/逻辑性/论据/说服力），输出结构化 JSON，判定胜负

每轮辩论结束后，裁判决定是进入下一轮还是终止辩论。

## 快速开始

### 环境要求

- Python ≥ 3.11
- OpenAI API Key

### 安装

```bash
python -m venv venv
source venv/Scripts/activate   # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

### 启动界面

```bash
streamlit run ui/app.py
```

在侧边栏输入 API Key 和辩论主题，点击「开始辩论」，然后逐步点击「继续」观察三位智能体的对抗过程。

### 运行测试

```bash
python -m pytest tests/ -v
```

## 项目结构

```
ai-learning-loop/
├── core/                    # 核心契约（所有模块的依赖根）
│   ├── state.py             # AgentState — 唯一的全局状态定义
│   ├── schemas.py           # Pydantic 结构化模型（RefereeJudgment 等）
│   └── prompts.py           # System Prompt 与模板函数
├── agents/                  # 智能体节点（无状态纯函数）
│   ├── presenter.py         # 陈述者：主题 → 论点
│   ├── opponent.py          # 反驳者：论点 → 反驳
│   └── referee.py           # 裁判：双方陈词 → 结构化评分
├── workflow/                # 编排层
│   └── graph.py             # LangGraph 图组装、条件路由、断点配置
├── ui/                      # 展现层
│   └── app.py               # Streamlit 界面（纯渲染，不含业务逻辑）
├── tests/                   # 测试（Mock LLM，不依赖真实 API）
│   ├── test_agents.py       # 22 个用例：节点输入输出契约
│   └── test_workflow.py     # 12 个用例：调度节点、路由、图编译
├── requirements.txt
├── CLAUDE.md                # Claude Code 开发指南
└── README.md
```

## 架构原则

| 层级 | 职责 | 禁止 |
|------|------|------|
| `core/` | 数据契约（State、Schema、Prompt） | 不得包含业务逻辑 |
| `agents/` | 调用 LLM 生成内容，返回部分状态更新 | 不得修改 State、不得自行扩展字段 |
| `workflow/` | 状态流转、条件路由、断点调度 | 不得包含 LLM 调用 |
| `ui/` | 渲染数据、收集输入 | 不得修改 graph state、不得包含业务逻辑 |

- **LLM 依赖注入**：Agent 节点的 `model` 参数可替换，方便测试
- **断点（interrupt_before）**：默认在每个 Agent 前暂停，用户可在 UI 中逐步推进
- **状态分离**：`st.session_state` 仅存 UI 元数据，辩论状态存储在 LangGraph checkpointer 中
- **自定义角色**：消息使用 `presenter`/`opponent`/`referee` 角色，而非 LangChain 标准类型

## 依赖

| 包 | 用途 |
|----|------|
| `langgraph` | 状态图编排、断点、checkpointer |
| `langchain-core` | 消息类型（SystemMessage / HumanMessage） |
| `langchain-openai` | ChatOpenAI 模型调用 |
| `pydantic` | 结构化数据模型与校验 |
| `streamlit` | Web UI |

## License

MIT

"""Web 子包共享的全局状态与辅助函数。

本模块集中管理 web/ 层级的模块级变量和纯工具函数，
避免 streaming.py ↔ state.py 之间的循环导入。

包含:
    - _graph / _checkpointer / _model_store: 全局单例
    - _mkmsg(): 构造 UI 消息字典
    - _new_tab(): 创建新 Tab 数据结构
    - MODEL_CONFIG_PATH: 持久化配置文件路径
"""

import time
import uuid
from pathlib import Path

from socratic_loop.infra.env import setup_environment
from socratic_loop.infra.model import load_model_config
from socratic_loop.infra.model_store import ModelStore

#: 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

#: 模型配置文件路径
MODEL_CONFIG_PATH = PROJECT_ROOT / ".model-config.json"

#: 全局 LangGraph 图单例（首次访问时通过 build_default_graph 构建）
_graph = None

#: 全局 checkpointer（MemorySaver 实例）
_checkpointer = None

#: 全局 ModelStore 单例（首次访问时从 .model-config.json 加载或从 .env 迁移）
_model_store = None


def _mkmsg(role: str, content: str, is_streaming: bool = False) -> dict:
    """构造符合 UI 层消息格式的消息字典。"""
    return {
        "role": role,
        "content": content,
        "is_streaming": is_streaming,
        "timestamp": time.time(),
    }


def _new_tab(label: str = "新对话") -> dict:
    """创建新 Tab 的数据结构。"""
    return {
        "id": str(uuid.uuid4()),
        "label": label,
        "thread_id": "",
        "topic": "",
        "messages": [],
        "is_generating": False,
        "interrupt_value": None,
        "awaiting_user_response": False,
        "current_node": "",
    }


def _initialize_graph():
    """初始化全局图单例（幂等）。"""
    global _graph, _checkpointer
    if _graph is not None:
        return
    from langgraph.checkpoint.memory import MemorySaver

    from socratic_loop.workflow.graph import build_default_graph

    _checkpointer = MemorySaver()
    _graph = build_default_graph(checkpointer=_checkpointer)


def _initialize_model_store():
    """初始化全局 ModelStore 单例（幂等）。"""
    global _model_store
    if _model_store is not None:
        return
    if MODEL_CONFIG_PATH.exists():
        _model_store = ModelStore.load(MODEL_CONFIG_PATH)
    else:
        _model_store = ModelStore.migrate_from_env(load_model_config())
        _model_store.save(MODEL_CONFIG_PATH)


def _get_model_store() -> ModelStore | None:
    """获取全局 ModelStore 单例（必要时初始化）。"""
    if _model_store is None:
        _initialize_model_store()
    return _model_store


def _get_graph():
    """获取全局图单例（必要时初始化）。"""
    if _graph is None:
        _initialize_graph()
    return _graph


# ── 环境初始化（模块加载时执行一次） ——

setup_environment(PROJECT_ROOT)

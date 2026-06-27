"""
环境初始化 —— 所有入口点统一的启动逻辑。

原则：
1. 一次导入，一次调用，消除 sys.path / load_dotenv 的分散重复。
2. 不自动执行任何操作——调用方显式调用 setup_environment()。
3. 模块级零副作用（无 import 时自动执行的代码）。
"""

import os
import sys
from pathlib import Path


def setup_environment(
    project_root: Path,
    *,
    change_cwd: bool = False,
    verbose: bool = True,
) -> Path:
    """设置项目运行环境：sys.path + .env 加载 + 可选的工作目录切换。

    所有入口点（run.py、scripts/*.py）应在项目导入之前调用此函数。

    Args:
        project_root: 项目根目录的绝对路径。
        change_cwd: 是否将当前工作目录切换到 project_root。
        verbose: 是否打印初始化信息。

    Returns:
        验证后的 project_root（与传入的相同）。

    Raises:
        FileNotFoundError: 如果 project_root 不存在或不是目录。
    """
    if not project_root.is_dir():
        raise FileNotFoundError(f"项目根目录不存在: {project_root}")

    # 1. 确保项目根目录在 sys.path 最前面，使得 from core.xxx 等导入总是指向本项目
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        if verbose:
            print(f"[init] sys.path ← {root_str}")

    # 2. 切换工作目录（Streamlit 等工具需要）
    if change_cwd:
        os.chdir(project_root)
        if verbose:
            print(f"[init] cwd ← {root_str}")

    # 3. 加载 .env 文件（必须在 LangChain/LangGraph 导入之前）
    env_path = project_root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)
        if verbose:
            print(f"[init] 已加载环境变量: {env_path}")
    elif verbose:
        print("[init] 提示: 未找到 .env 文件，请先执行 cp .env.example .env 并配置 API Key")

    return project_root

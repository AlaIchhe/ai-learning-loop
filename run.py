#!/usr/bin/env python3
"""
项目启动器 —— 确保从任意目录启动都能正确加载 .env 并运行 Streamlit。

用法:
    python run.py                  # 启动 Streamlit 界面
    python run.py --export-graph   # 导出图架构为 PNG

等价于:
    streamlit run ui/app.py        # 标准方式
    python -m workflow.graph       # 导出图
"""

import os
import subprocess
import sys
from pathlib import Path


def _find_project_root() -> Path:
    """通过本脚本的绝对路径定位项目根目录，避免依赖 cwd。"""
    return Path(__file__).resolve().parent


def _ensure_dotenv_loaded(project_root: Path) -> None:
    """在必要时加载 .env，确保 LANGCHAIN_TRACING_V2 等变量在 LangChain 导入前生效。"""
    env_path = project_root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)
        print(f"[init] 已加载环境变量: {env_path}")
    else:
        print("[init] 提示: 未找到 .env 文件，请先执行 cp .env.example .env 并配置 API Key")


def main() -> None:
    project_root = _find_project_root()

    # 确保项目根目录在 sys.path 中，使得 from core.xxx / from agents.xxx 等导入能找到模块
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # 切换工作目录到项目根，确保 Streamlit 等工具的相对路径行为一致
    os.chdir(project_root)

    if "--export-graph" in sys.argv:
        _ensure_dotenv_loaded(project_root)
        from workflow.graph import export_graph

        export_graph()
        return

    # 默认：启动 Streamlit 界面
    _ensure_dotenv_loaded(project_root)

    app_path = project_root / "ui" / "app.py"
    if not app_path.exists():
        print(f"错误: 找不到 {app_path}")
        sys.exit(1)

    print(f"[init] 启动 Streamlit → {app_path}")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        check=False,
    )


if __name__ == "__main__":
    main()

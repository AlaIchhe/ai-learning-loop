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

import subprocess
import sys
from pathlib import Path

from core.env import setup_environment


def main() -> None:
    project_root = Path(__file__).resolve().parent
    setup_environment(project_root, change_cwd=True)

    if "--export-graph" in sys.argv:
        from workflow.graph import export_graph

        export_graph()
        return

    # 默认：启动 Streamlit 界面
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

#!/usr/bin/env python3
"""
项目启动器 —— Reflex 版本。

用法:
    python run.py                  # 启动 Reflex 界面（生产/开发）
    python run.py --export-graph   # 导出 LangGraph 图架构为 PNG

等价于:
    reflex run                     # 启动 Reflex
    python -m workflow.graph       # 导出图
"""

import os
import subprocess
import sys
from pathlib import Path

from socratic_loop.core.env import setup_environment


def main() -> None:
    project_root = Path(__file__).resolve().parent
    setup_environment(project_root, change_cwd=True)

    if "--export-graph" in sys.argv:
        from socratic_loop.workflow.graph import export_graph
        export_graph()
        return

    # 默认：启动 Reflex 界面
    if "PYTHONUTF8" not in os.environ:
        os.environ["PYTHONUTF8"] = "1"

    print("[init] 启动 Reflex → http://localhost:3003")
    try:
        subprocess.run(
            [sys.executable, "-m", "reflex", "run"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"错误: Reflex 启动失败（退出码 {exc.returncode}）")
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()

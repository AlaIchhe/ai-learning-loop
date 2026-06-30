#!/usr/bin/env python3
"""ai-learning-loop 命令行入口 —— 由 pyproject.toml 的 [project.scripts] 注册。

用法:
    ai-learning-loop                  # 启动 Reflex 界面
    ai-learning-loop --export-graph   # 导出 LangGraph 架构图
    ai-learning-loop --version        # 显示版本
"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """CLI 主入口——处理参数并启动 Reflex 或导出图。"""
    project_root = Path(__file__).resolve().parent.parent

    # 延迟导入：确保 setup_environment 在 langchain 之前执行
    from socratic_loop.infra.env import setup_environment

    setup_environment(project_root, change_cwd=True)

    # ── 参数处理 ──
    if "--version" in sys.argv:
        from socratic_loop import __version__
        print(f"ai-learning-loop {__version__}")
        return

    if "--export-graph" in sys.argv:
        from socratic_loop.workflow.graph import export_graph
        export_graph()
        return

    # ── 默认：启动 Reflex ──
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
    except KeyboardInterrupt:
        print("\n[init] 已停止")


if __name__ == "__main__":
    main()

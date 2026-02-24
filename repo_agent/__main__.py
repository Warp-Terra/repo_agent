"""程序入口：支持 CLI 与 TUI 两种启动模式。"""

import argparse
import sys

from repo_agent.agent.loop import main as run_cli


def _run_tui_entry() -> None:
    """按需加载并运行 TUI。"""
    try:
        from repo_agent.ui import run_tui
    except ModuleNotFoundError as e:
        if e.name and e.name.startswith("textual"):
            print("TUI 需要额外依赖 `textual`。")
            print("请先执行：pip install -e .[tui]")
            sys.exit(1)
        raise
    run_tui()


def main() -> None:
    """命令行参数解析入口。"""
    parser = argparse.ArgumentParser(description="本地代码仓库问答 Agent")
    parser.add_argument("--tui", action="store_true", help="使用 Textual TUI 交互界面")
    args = parser.parse_args()

    if args.tui:
        _run_tui_entry()
        return
    run_cli()


if __name__ == "__main__":
    main()

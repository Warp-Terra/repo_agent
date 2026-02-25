"""程序入口：支持 service / CLI / TUI / local 四种模式。"""

from __future__ import annotations

import argparse
import sys

from repo_agent.agent.loop import main as run_local_cli
from repo_agent.cli import run_remote_cli
from repo_agent.config import load_agentd_host, load_agentd_port, load_agentd_token
from repo_agent.daemon import run_agent_daemon


def _run_tui_entry(endpoint: str, token: str | None, session_id: str | None) -> None:
    """按需加载并运行 TUI。"""
    try:
        from repo_agent.ui import run_tui
    except ModuleNotFoundError as e:
        if e.name and e.name.startswith("textual"):
            print("TUI 需要额外依赖 `textual`。")
            print("请先执行：pip install -e .[tui]")
            sys.exit(1)
        raise
    run_tui(endpoint=endpoint, token=token, session_id=session_id)


def _resolve_token(cli_token: str | None) -> str | None:
    """解析 token 参数，命令行优先于环境配置。"""
    if cli_token is not None:
        return cli_token
    return load_agentd_token()


def _resolve_endpoint(
    cli_endpoint: str | None,
    host: str,
    port: int,
) -> str:
    """解析服务访问地址。"""
    if cli_endpoint:
        return cli_endpoint
    return f"http://{host}:{port}"


def main() -> None:
    """命令行参数解析入口。"""
    default_host = load_agentd_host()
    default_port = load_agentd_port()

    parser = argparse.ArgumentParser(description="本地代码仓库问答 Agent")
    parser.add_argument(
        "--mode",
        choices=["cli", "tui", "service", "local"],
        default="cli",
        help="运行模式：cli(远程)、tui(远程)、service(常驻服务)、local(旧单进程模式)",
    )
    parser.add_argument("--host", default=default_host, help="service 模式监听地址")
    parser.add_argument("--port", type=int, default=default_port, help="service 模式监听端口")
    parser.add_argument("--endpoint", default=None, help="cli/tui 模式的服务地址，例如 http://127.0.0.1:8765")
    parser.add_argument("--token", default=None, help="服务访问令牌（请求头 X-Agent-Token）")
    parser.add_argument("--session-id", default=None, help="cli/tui 模式附着的会话 ID")
    parser.add_argument(
        "--max-events",
        type=int,
        default=2000,
        help="service 模式每个会话保留的最大事件数",
    )
    # 兼容旧参数
    parser.add_argument("--tui", action="store_true", help="兼容参数：等同于 --mode tui")

    args = parser.parse_args()
    mode = "tui" if args.tui else args.mode
    token = _resolve_token(args.token)
    endpoint = _resolve_endpoint(args.endpoint, host=args.host, port=args.port)

    if mode == "service":
        try:
            run_agent_daemon(
                host=args.host,
                port=args.port,
                token=token,
                max_events_per_session=max(200, args.max_events),
            )
        except Exception as e:
            print(f"启动失败：{e}")
            sys.exit(1)
        return

    if mode == "tui":
        try:
            _run_tui_entry(endpoint=endpoint, token=token, session_id=args.session_id)
        except Exception as e:
            print(f"启动失败：{e}")
            sys.exit(1)
        return

    if mode == "local":
        run_local_cli()
        return

    # 默认模式：远程 CLI
    try:
        run_remote_cli(endpoint=endpoint, token=token, session_id=args.session_id)
    except Exception as e:
        print(f"启动失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

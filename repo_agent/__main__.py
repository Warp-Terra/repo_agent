"""程序入口：默认启动托管式 TUI，并自动管理 agent 子进程。"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
import time

from repo_agent.config import load_agentd_host, load_agentd_port, load_agentd_token
from repo_agent.daemon import run_agent_daemon
from repo_agent.remote import RemoteAgentClient


def _run_tui_entry(endpoint: str, token: str | None, session_id: str | None) -> None:
    """按需加载并运行 TUI。"""
    try:
        from repo_agent.ui import run_tui
    except ModuleNotFoundError as e:
        if e.name and e.name.startswith("textual"):
            print("当前环境缺少基础依赖 `textual`。")
            print("请升级或重装 repo-agent；若使用 pipx，可执行：pipx inject repo-agent textual")
            sys.exit(1)
        raise
    run_tui(endpoint=endpoint, token=token, session_id=session_id)


def _resolve_token(cli_token: str | None) -> str | None:
    """解析 token 参数，命令行优先于环境配置。"""
    if cli_token is not None:
        return cli_token
    return load_agentd_token()


def _resolve_endpoint(host: str, port: int) -> str:
    """拼接本地 agent 服务地址。"""
    return f"http://{host}:{port}"


def _agent_process_main(host: str, port: int, token: str | None, max_events: int) -> None:
    """agent 子进程入口。"""
    run_agent_daemon(
        host=host,
        port=port,
        token=token,
        max_events_per_session=max(200, max_events),
    )


def _wait_agent_ready(
    *,
    endpoint: str,
    token: str | None,
    process: mp.Process,
    timeout_seconds: float,
) -> None:
    """等待 agent HTTP 服务就绪。"""
    client = RemoteAgentClient(endpoint=endpoint, token=token, timeout=2.0)
    deadline = time.monotonic() + max(0.5, timeout_seconds)
    last_error = "未知错误"

    while time.monotonic() < deadline:
        if not process.is_alive():
            raise RuntimeError(f"agent 子进程已退出（exitcode={process.exitcode}）。")
        try:
            client.health()
            return
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(0.2)

    raise RuntimeError(f"等待 agent 启动超时（{timeout_seconds:.1f}s）：{last_error}")


def _stop_agent_process(
    *,
    endpoint: str,
    token: str | None,
    process: mp.Process,
    shutdown_timeout_seconds: float = 5.0,
) -> None:
    """优先优雅关闭；失败时强制终止 agent 子进程。"""
    if not process.is_alive():
        return

    client = RemoteAgentClient(endpoint=endpoint, token=token, timeout=2.0)
    try:
        client.shutdown()
    except Exception:
        # 关闭接口不可达时，退化为强制结束。
        pass

    process.join(timeout=max(0.5, shutdown_timeout_seconds))
    if process.is_alive():
        process.terminate()
        process.join(timeout=max(0.5, shutdown_timeout_seconds))


def main() -> None:
    """命令行入口：自动托管 agent 子进程并运行 TUI。"""
    mp.freeze_support()

    default_host = load_agentd_host()
    default_port = load_agentd_port()

    parser = argparse.ArgumentParser(description="Repo Agent（自动托管模式）")
    parser.add_argument("--host", default=default_host, help="agent 服务监听地址")
    parser.add_argument("--port", type=int, default=default_port, help="agent 服务监听端口")
    parser.add_argument("--token", default=None, help="agent 服务访问令牌（请求头 X-Agent-Token）")
    parser.add_argument("--session-id", default=None, help="TUI 附着的会话 ID")
    parser.add_argument(
        "--max-events",
        type=int,
        default=2000,
        help="每个会话保留的最大事件数",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=15.0,
        help="等待 agent 服务启动的超时秒数",
    )
    # 内部参数：仅供子进程直启 agent 守护服务使用。
    parser.add_argument("--run-agentd", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()
    token = _resolve_token(args.token)

    if args.run_agentd:
        _agent_process_main(args.host, args.port, token, args.max_events)
        return

    endpoint = _resolve_endpoint(args.host, args.port)
    agent_process = mp.Process(
        target=_agent_process_main,
        kwargs={
            "host": args.host,
            "port": args.port,
            "token": token,
            "max_events": args.max_events,
        },
        name="repo-agentd",
        daemon=False,
    )

    try:
        agent_process.start()
        _wait_agent_ready(
            endpoint=endpoint,
            token=token,
            process=agent_process,
            timeout_seconds=args.startup_timeout,
        )
        _run_tui_entry(endpoint=endpoint, token=token, session_id=args.session_id)
    except Exception as e:
        print(f"启动失败：{e}")
        sys.exit(1)
    finally:
        _stop_agent_process(endpoint=endpoint, token=token, process=agent_process)


if __name__ == "__main__":
    main()

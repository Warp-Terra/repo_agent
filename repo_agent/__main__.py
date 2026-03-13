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


def _cmd_build_kb(args: argparse.Namespace) -> None:
    """执行知识库构建并打印结果。"""
    try:
        from repo_agent.kb import build_index
    except ImportError as e:
        print("构建知识库需要 RAG 依赖，请先执行：pip install 'repo-agent[rag]'")
        raise SystemExit(1) from e
    from pathlib import Path
    from repo_agent.config.settings import load_embedding_provider
    from repo_agent.rag.store import VectorStore
    root = Path.cwd()
    max_files = getattr(args, "max_files", None)
    max_chunks = getattr(args, "max_chunks", None)
    provider = load_embedding_provider()
    if provider == "openai":
        print("向量化：openai（云端 API），不加载本地模型，内存占用低。")
    else:
        print("向量化：local（本地模型）。")
        print("  若期望使用云端向量化，请在 .env 中设置 REPO_AGENT_EMBEDDING=openai 并配置 OPENAI_API_KEY。")
    store = VectorStore(project_root=root)
    backend = store.backend_name()
    print(f"存储后端：{backend}（默认 SimpleStore，按批落盘，内存 <100MB）。")
    if max_chunks is not None or max_files is not None:
        print(f"正在从 {root} 加载文档并构建索引（max_files={max_files}, max_chunks={max_chunks}）...")
    else:
        print(f"正在从 {root} 加载文档并构建索引（流式处理，内存占用可控）...")
    n = build_index(project_root=root, max_files=max_files, max_chunks=max_chunks, store=store)
    print(f"知识库构建完成，共写入 {n} 个文档块。索引目录：{root / '.repo_agent_kb'}")


def main() -> None:
    """命令行入口：默认托管 agent 子进程并运行 TUI；支持 build-kb 子命令。"""
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
    parser.add_argument("--run-agentd", action="store_true", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    build_parser = subparsers.add_parser("build-kb", help="构建当前项目知识库索引（供 RAG 检索）")
    build_parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        metavar="N",
        help="最多索引 N 个块，内存紧张时可设如 5000 或 10000",
    )
    build_parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="最多索引 N 个文件",
    )

    args = parser.parse_args()
    if getattr(args, "command", None) == "build-kb":
        _cmd_build_kb(args)
        return

    host = args.host
    port = args.port
    token = _resolve_token(args.token)
    session_id = args.session_id
    max_events = args.max_events
    startup_timeout = args.startup_timeout
    run_agentd = args.run_agentd

    if run_agentd:
        _agent_process_main(host, port, token, max_events)
        return

    endpoint = _resolve_endpoint(host, port)
    agent_process = mp.Process(
        target=_agent_process_main,
        kwargs={
            "host": host,
            "port": port,
            "token": token,
            "max_events": max_events,
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
            timeout_seconds=startup_timeout,
        )
        _run_tui_entry(endpoint=endpoint, token=token, session_id=session_id)
    except Exception as e:
        print(f"启动失败：{e}")
        sys.exit(1)
    finally:
        _stop_agent_process(endpoint=endpoint, token=token, process=agent_process)


if __name__ == "__main__":
    main()

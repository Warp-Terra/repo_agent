"""远程模式 CLI。"""

from __future__ import annotations

import json

from repo_agent.remote import RemoteAgentClient, RemoteAgentError


def _print_help() -> None:
    print("可用命令：")
    print("  /help   - 显示帮助")
    print("  /status - 查看会话状态")
    print("  /clear  - 清空会话")
    print("  /cancel - 取消等待中的任务")
    print("  /quit   - 退出程序")


def _render_event(event: dict) -> None:
    event_type = str(event.get("type", ""))
    turn_id = event.get("turn_id")
    payload = event.get("payload", {})
    prefix = f"[turn #{turn_id}] " if turn_id is not None else ""

    if event_type == "tool_call":
        args = payload.get("args", {})
        args_display = json.dumps(args, ensure_ascii=False)
        print(f"  {prefix}[工具调用 #{payload.get('index', '?')}] {payload.get('name', 'unknown')}({args_display})")
        return
    if event_type == "tool_deduplicated":
        print(f"  {prefix}[工具去重] 连续重复调用，复用上一次结果。")
        return
    if event_type == "tool_result":
        print(f"  {prefix}[工具结果] {payload.get('preview', '')}")
        return
    if event_type == "rate_limit_retry":
        print(
            f"  {prefix}[限流] 第 {payload.get('attempt', '?')} 次重试，"
            f"等待 {payload.get('delay_seconds', 0):.0f} 秒..."
        )
        return
    if event_type == "rate_limit_failed":
        print(f"  {prefix}[限流] 已重试 {payload.get('max_retries', '?')} 次仍失败。")
        return
    if event_type == "warning":
        print(f"  {prefix}[警告] {payload.get('message', '')}")
        return
    if event_type == "answer":
        print(f"Agent: {payload.get('text', '')}")
        return
    if event_type == "error":
        print(f"Agent 错误：{payload.get('message', '')}")


def run_remote_cli(endpoint: str, token: str | None, session_id: str | None = None) -> None:
    """运行远程控制模式 CLI。"""
    client = RemoteAgentClient(endpoint=endpoint, token=token)
    try:
        client.health()
    except RemoteAgentError as e:
        raise RuntimeError(
            f"无法连接 Agent 服务：{e}\n"
            "请先启动：python -m repo_agent --mode service"
        ) from e

    if session_id:
        session = client.get_session(session_id)
    else:
        created = client.create_session()
        session_id = str(created["session_id"])
        raw_session = created.get("session")
        session = raw_session if isinstance(raw_session, dict) else {}
    if session_id is None:
        raise RuntimeError("创建会话失败：未返回 session_id。")

    print("=" * 60)
    print("  Repo Agent CLI（远程模式）")
    print("=" * 60)
    print(f"  服务: {endpoint}")
    print(f"  会话: {session_id}")
    print(f"  提供商: {session.get('provider', '?')}")
    print(f"  模型: {session.get('model_id', '?')}")
    print("  输入问题开始对话，Ctrl+C 退出")
    print()

    event_cursor = int(session.get("last_event_id", 0))
    _print_help()
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if not user_input:
            continue
        lowered = user_input.lower()
        if lowered in ("/quit", "/exit", "/q"):
            print("\n再见！")
            break
        if lowered == "/help":
            _print_help()
            print()
            continue
        if lowered in ("/clear", "/reset"):
            result = client.clear_session(session_id)
            print(f"System: {result.get('message', '会话已清空。')}\n")
            continue
        if lowered == "/cancel":
            result = client.cancel_session(session_id)
            dropped = result.get("dropped_pending", 0)
            running = result.get("running", False)
            print(f"System: 已取消等待任务 {dropped} 条；当前执行中回合可取消={result.get('hard_cancel_supported', False)}")
            if running:
                print("System: 当前有执行中的回合，将在其结束后生效。")
            print()
            continue
        if lowered == "/status":
            status = client.get_session(session_id)
            print(
                "System: "
                f"busy={status.get('busy', False)} "
                f"pending={status.get('pending_count', 0)} "
                f"history={status.get('history_size', 0)} "
                f"last_turn={status.get('last_turn_id', 0)}"
            )
            print()
            continue

        turn = client.submit_turn(session_id, user_input)
        turn_id = int(turn.get("turn_id", 0))
        print(f"System: 回合 #{turn_id} 已提交，等待 Agent 结果...\n")

        finished = False
        while not finished:
            stream = client.get_events(session_id=session_id, after=event_cursor, wait_ms=1000, limit=200)
            dropped = int(stream.get("dropped_events", 0))
            if dropped > 0:
                print(f"System: 事件缓冲溢出，已跳过 {dropped} 条旧事件。")

            events = stream.get("events", [])
            event_cursor = int(stream.get("last_event_id", event_cursor))
            for event in events:
                _render_event(event)
                if int(event.get("turn_id") or 0) != turn_id:
                    continue
                if event.get("type") in {"answer", "error"}:
                    finished = True

        print()

"""Textual TUI：作为 Agent 服务的观察与遥控窗口。"""

from __future__ import annotations

import json
import time
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static

from repo_agent.config import load_agentd_host, load_agentd_port
from repo_agent.remote import RemoteAgentClient


class AgentTuiApp(App[None]):
    """Agent 的终端交互界面。"""

    CSS = """
    Screen {
        layout: vertical;
    }

    #hint {
        height: auto;
        margin: 0 1;
        color: #8a8a8a;
    }

    #main {
        layout: horizontal;
        height: 1fr;
        margin: 0 1;
    }

    #chat_log {
        width: 3fr;
        border: round #4f772d;
        margin-right: 1;
    }

    #tool_log {
        width: 2fr;
        border: round #0f4c5c;
    }

    #prompt_input {
        margin: 0 1 1 1;
        border: round #bc4749;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "退出"),
        ("ctrl+l", "clear_session", "清空会话"),
        ("ctrl+k", "cancel_turn", "取消等待"),
    ]

    TITLE = "Repo Agent TUI"
    SUB_TITLE = "远程会话观察与控制"

    def __init__(self, endpoint: str, token: str | None, session_id: str | None) -> None:
        super().__init__()
        self.client = RemoteAgentClient(endpoint=endpoint, token=token)
        self.endpoint = endpoint
        self.session_id = session_id
        self.connected = False
        self.busy = False
        self.current_turn_id: int | None = None
        self.event_cursor = 0
        self._stop_polling = False
        self._poll_error_notified = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("命令：/help  /status  /clear  /cancel  /quit", id="hint")
        with Horizontal(id="main"):
            yield RichLog(id="chat_log", wrap=True, highlight=False, markup=False, auto_scroll=True)
            yield RichLog(id="tool_log", wrap=True, highlight=False, markup=False, auto_scroll=True)
        yield Input(placeholder="输入问题后回车发送", id="prompt_input")
        yield Footer()

    def on_mount(self) -> None:
        self.prompt_input.disabled = True
        self.chat_log.write(f"System: 正在连接 Agent 服务 {self.endpoint} ...")
        self._connect_service()
        self._poll_events()

    def on_unmount(self) -> None:
        self._stop_polling = True

    @property
    def chat_log(self) -> RichLog:
        return self.query_one("#chat_log", RichLog)

    @property
    def tool_log(self) -> RichLog:
        return self.query_one("#tool_log", RichLog)

    @property
    def prompt_input(self) -> Input:
        return self.query_one("#prompt_input", Input)

    def action_clear_session(self) -> None:
        if not self.connected or not self.session_id:
            self.chat_log.write("System: 尚未连接会话。")
            return
        if self.busy:
            self.chat_log.write("System: 当前有请求正在执行，暂不能清空。")
            return
        self._clear_session_remote()

    def action_cancel_turn(self) -> None:
        if not self.connected or not self.session_id:
            self.chat_log.write("System: 尚未连接会话。")
            return
        self._cancel_session_remote()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        event.input.value = ""
        if not user_input:
            return

        if self._handle_command(user_input):
            return

        if not self.connected or not self.session_id:
            self.chat_log.write("System: 尚未连接服务，请稍候。")
            return
        if self.busy:
            self.chat_log.write("System: 正在处理上一条请求，请稍候。")
            return

        self.chat_log.write(f"You: {user_input}")
        self.busy = True
        self.prompt_input.disabled = True
        self.chat_log.write("System: 正在思考...")
        self._submit_turn(user_input)

    def _handle_command(self, user_input: str) -> bool:
        lowered = user_input.lower()
        if lowered in ("/quit", "/exit", "/q"):
            self.exit()
            return True
        if lowered in ("/clear", "/reset"):
            self.action_clear_session()
            return True
        if lowered == "/status":
            self._query_status_remote()
            return True
        if lowered == "/cancel":
            self.action_cancel_turn()
            return True
        if lowered == "/help":
            self.chat_log.write("System: 可用命令 /help /status /clear /cancel /quit")
            return True
        return False

    @work(thread=True)
    def _connect_service(self) -> None:
        try:
            self.client.health()
            if self.session_id:
                status = self.client.get_session(self.session_id)
            else:
                created = self.client.create_session()
                self.session_id = str(created["session_id"])
                raw_status = created.get("session")
                status = raw_status if isinstance(raw_status, dict) else {}
            self.event_cursor = int(status.get("last_event_id", 0))
        except Exception as e:
            self.call_from_thread(self._finish_connect_error, f"{type(e).__name__}: {e}")
            return
        self.call_from_thread(self._finish_connect_success, status)

    @work(thread=True)
    def _submit_turn(self, user_input: str) -> None:
        if not self.session_id:
            self.call_from_thread(self._finish_error, "会话不存在。")
            return
        try:
            result = self.client.submit_turn(self.session_id, user_input)
            turn_id = int(result.get("turn_id", 0))
        except Exception as e:
            self.call_from_thread(self._finish_error, f"{type(e).__name__}: {e}")
            return
        # 先在工作线程写入 turn_id，降低轮询线程先于 UI 回调处理事件的竞态概率。
        self.current_turn_id = turn_id
        self.call_from_thread(self._on_turn_submitted, turn_id)

    @work(thread=True)
    def _clear_session_remote(self) -> None:
        if not self.session_id:
            self.call_from_thread(self.chat_log.write, "System: 会话不存在。")
            return
        try:
            result = self.client.clear_session(self.session_id)
        except Exception as e:
            self.call_from_thread(self.chat_log.write, f"System: 清空失败：{type(e).__name__}: {e}")
            return
        self.call_from_thread(self._on_session_cleared, str(result.get("message", "会话已清空。")))

    @work(thread=True)
    def _cancel_session_remote(self) -> None:
        if not self.session_id:
            self.call_from_thread(self.chat_log.write, "System: 会话不存在。")
            return
        try:
            result = self.client.cancel_session(self.session_id)
        except Exception as e:
            self.call_from_thread(self.chat_log.write, f"System: 取消失败：{type(e).__name__}: {e}")
            return
        dropped = result.get("dropped_pending", 0)
        running = result.get("running", False)
        self.call_from_thread(
            self.chat_log.write,
            (
                "System: 已取消等待任务 "
                f"{dropped} 条；当前执行中回合可取消={result.get('hard_cancel_supported', False)}。"
            ),
        )
        if running:
            self.call_from_thread(self.chat_log.write, "System: 当前有执行中的回合，将在其结束后生效。")

    @work(thread=True)
    def _query_status_remote(self) -> None:
        if not self.session_id:
            self.call_from_thread(self.chat_log.write, "System: 会话不存在。")
            return
        try:
            status = self.client.get_session(self.session_id)
        except Exception as e:
            self.call_from_thread(self.chat_log.write, f"System: 查询状态失败：{type(e).__name__}: {e}")
            return
        self.call_from_thread(
            self.chat_log.write,
            (
                "System: "
                f"busy={status.get('busy', False)} "
                f"pending={status.get('pending_count', 0)} "
                f"history={status.get('history_size', 0)} "
                f"last_turn={status.get('last_turn_id', 0)}"
            ),
        )

    @work(thread=True)
    def _poll_events(self) -> None:
        while not self._stop_polling:
            if not self.connected or not self.session_id:
                time.sleep(0.2)
                continue
            try:
                payload = self.client.get_events(
                    session_id=self.session_id,
                    after=self.event_cursor,
                    wait_ms=1000,
                    limit=300,
                )
            except Exception as e:
                if not self._poll_error_notified:
                    self._poll_error_notified = True
                    self.call_from_thread(
                        self.chat_log.write,
                        f"System: 事件轮询失败：{type(e).__name__}: {e}",
                    )
                time.sleep(1.0)
                continue

            self._poll_error_notified = False
            dropped = int(payload.get("dropped_events", 0))
            events = payload.get("events", [])
            self.event_cursor = int(payload.get("last_event_id", self.event_cursor))

            if dropped > 0:
                self.call_from_thread(self.tool_log.write, f"[系统] 事件缓冲溢出，已跳过 {dropped} 条旧事件。")
            if events:
                self.call_from_thread(self._render_events, events)

    def _finish_connect_success(self, status: dict[str, Any]) -> None:
        self.connected = True
        provider = status.get("provider", "?")
        model_id = status.get("model_id", "?")
        self.chat_log.write(f"System: 已连接会话 {self.session_id}")
        self.chat_log.write(f"System: 提供商 {provider} / 模型 {model_id}")
        self.prompt_input.disabled = False
        self.prompt_input.focus()

    def _finish_connect_error(self, message: str) -> None:
        self.connected = False
        self.prompt_input.disabled = True
        self.chat_log.write(f"System: 连接失败：{message}")
        self.chat_log.write("System: 请先启动服务：python -m repo_agent --mode service")

    def _on_turn_submitted(self, turn_id: int) -> None:
        self.current_turn_id = turn_id
        self.chat_log.write(f"System: 已提交回合 #{turn_id}")

    def _on_session_cleared(self, message: str) -> None:
        self.chat_log.clear()
        self.tool_log.clear()
        self.chat_log.write(f"System: {message}")

    def _render_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            event_type = str(event.get("type", ""))
            payload = event.get("payload", {})
            turn_id = event.get("turn_id")

            if event_type == "tool_call":
                args = payload.get("args", {})
                args_display = json.dumps(args, ensure_ascii=False)
                self.tool_log.write(
                    f"[工具调用 #{payload.get('index', '?')}] {payload.get('name', 'unknown')}({args_display})"
                )
                continue
            if event_type == "tool_deduplicated":
                self.tool_log.write("[工具去重] 连续重复调用，复用上一次结果。")
                continue
            if event_type == "tool_result":
                self.tool_log.write(f"[工具结果] {payload.get('preview', '')}")
                continue
            if event_type == "rate_limit_retry":
                self.tool_log.write(
                    f"[限流] 第 {payload.get('attempt', '?')} 次重试，等待 {payload.get('delay_seconds', 0):.0f} 秒..."
                )
                continue
            if event_type == "rate_limit_failed":
                self.tool_log.write(f"[限流] 已重试 {payload.get('max_retries', '?')} 次仍失败。")
                continue
            if event_type == "warning":
                self.tool_log.write(f"[警告] {payload.get('message', '')}")
                continue
            if event_type == "session_cleared":
                self.chat_log.clear()
                self.tool_log.clear()
                self.chat_log.write("System: 会话与日志已清空。")
                continue
            if event_type == "answer":
                text = str(payload.get("text", ""))
                if turn_id == self.current_turn_id:
                    self.chat_log.write(f"Agent: {text}")
                    self._finish_turn()
                else:
                    self.chat_log.write(f"Agent(turn #{turn_id}): {text}")
                continue
            if event_type == "error":
                message = str(payload.get("message", ""))
                if turn_id == self.current_turn_id:
                    self.chat_log.write(f"System: Agent 错误：{message}")
                    self._finish_turn()
                else:
                    self.chat_log.write(f"System: turn #{turn_id} 错误：{message}")
                continue
            if event_type == "turn_finished" and turn_id == self.current_turn_id:
                # 兜底：如果异常路径没收到 answer/error，也恢复输入框。
                self._finish_turn()

    def _finish_turn(self) -> None:
        self.busy = False
        self.current_turn_id = None
        self.prompt_input.disabled = False
        self.prompt_input.focus()

    def _finish_error(self, message: str) -> None:
        self.chat_log.write(f"System: 提交失败：{message}")
        self.busy = False
        self.current_turn_id = None
        if self.connected:
            self.prompt_input.disabled = False
            self.prompt_input.focus()


def run_tui(endpoint: str | None = None, token: str | None = None, session_id: str | None = None) -> None:
    """运行 TUI 应用。"""
    resolved_endpoint = endpoint or f"http://{load_agentd_host()}:{load_agentd_port()}"
    AgentTuiApp(endpoint=resolved_endpoint, token=token, session_id=session_id).run()

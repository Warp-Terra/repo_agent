"""Textual TUI：提供类似 opencode 的双栏交互体验。"""

from __future__ import annotations

import json
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static

from repo_agent.agent.client import AgentRuntime, create_client
from repo_agent.agent.loop import agent_turn, build_tools


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
    ]

    TITLE = "Repo Agent TUI"
    SUB_TITLE = "聊天区 + 工具日志区"

    def __init__(self) -> None:
        super().__init__()
        self.runtime: AgentRuntime | None = None
        self.tools: Any = None
        self.history: list[Any] = []
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("命令：/help  /clear  /quit", id="hint")
        with Horizontal(id="main"):
            yield RichLog(id="chat_log", wrap=True, highlight=False, markup=False, auto_scroll=True)
            yield RichLog(id="tool_log", wrap=True, highlight=False, markup=False, auto_scroll=True)
        yield Input(placeholder="输入问题后回车发送", id="prompt_input")
        yield Footer()

    def on_mount(self) -> None:
        self.chat_log.write("System: 正在初始化模型客户端...")
        try:
            runtime = create_client()
            tools = build_tools(runtime.provider)
        except ValueError as e:
            self.chat_log.write(f"System: 初始化失败：{e}")
            self.prompt_input.disabled = True
            return

        self.runtime = runtime
        self.tools = tools
        self.chat_log.write(f"System: 已连接 {runtime.provider} / {runtime.model_id}")
        self.prompt_input.focus()

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
        if self.busy:
            self.chat_log.write("System: 当前有请求正在执行，暂不能清空。")
            return
        self.history.clear()
        self.chat_log.clear()
        self.tool_log.clear()
        self.chat_log.write("System: 会话与日志已清空。")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        event.input.value = ""
        if not user_input:
            return

        if self._handle_command(user_input):
            return

        if self.busy:
            self.chat_log.write("System: 正在处理上一条请求，请稍候。")
            return
        if self.runtime is None or self.tools is None:
            self.chat_log.write("System: 客户端尚未初始化完成。")
            return

        self.chat_log.write(f"You: {user_input}")
        self.busy = True
        self.prompt_input.disabled = True
        self.chat_log.write("System: 正在思考...")
        self._run_agent_turn(user_input)

    def _handle_command(self, user_input: str) -> bool:
        lowered = user_input.lower()
        if lowered in ("/quit", "/exit", "/q"):
            self.exit()
            return True
        if lowered in ("/clear", "/reset"):
            self.action_clear_session()
            return True
        if lowered == "/help":
            self.chat_log.write("System: 可用命令 /help /clear /quit")
            return True
        return False

    @work(thread=True)
    def _run_agent_turn(self, user_input: str) -> None:
        if self.runtime is None or self.tools is None:
            self.call_from_thread(self._finish_error, "客户端尚未初始化完成。")
            return

        try:
            answer = agent_turn(
                runtime=self.runtime,
                tools=self.tools,
                history=self.history,
                user_input=user_input,
                event_handler=self._on_agent_event,
            )
        except Exception as e:
            self._rollback_last_user_message()
            self.call_from_thread(self._finish_error, f"{type(e).__name__}: {e}")
            return

        self.call_from_thread(self._finish_success, answer)

    def _on_agent_event(self, event_type: str, payload: dict[str, Any]) -> None:
        # 该回调运行在工作线程，通过 call_from_thread 切回 UI 线程。
        self.call_from_thread(self._render_agent_event, event_type, payload)

    def _render_agent_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "tool_call":
            args = payload.get("args", {})
            args_display = json.dumps(args, ensure_ascii=False)
            self.tool_log.write(
                f"[工具调用 #{payload.get('index', '?')}] {payload.get('name', 'unknown')}({args_display})"
            )
            return
        if event_type == "tool_deduplicated":
            self.tool_log.write("[工具去重] 连续重复调用，复用上一次结果。")
            return
        if event_type == "tool_result":
            self.tool_log.write(f"[工具结果] {payload.get('preview', '')}")
            return
        if event_type == "rate_limit_retry":
            self.tool_log.write(
                f"[限流] 第 {payload.get('attempt', '?')} 次重试，等待 {payload.get('delay_seconds', 0):.0f} 秒..."
            )
            return
        if event_type == "rate_limit_failed":
            self.tool_log.write(f"[限流] 已重试 {payload.get('max_retries', '?')} 次仍失败。")
            return
        if event_type == "warning":
            self.tool_log.write(f"[警告] {payload.get('message', '')}")

    def _rollback_last_user_message(self) -> None:
        if not self.history:
            return
        last = self.history[-1]
        role = ""
        if hasattr(last, "role"):
            role = str(getattr(last, "role"))
        elif isinstance(last, dict):
            role = str(last.get("role", ""))
        if role == "user":
            self.history.pop()

    def _finish_success(self, answer: str) -> None:
        self.chat_log.write(f"Agent: {answer}")
        self.busy = False
        self.prompt_input.disabled = False
        self.prompt_input.focus()

    def _finish_error(self, message: str) -> None:
        self.chat_log.write(f"System: Agent 错误：{message}")
        self.busy = False
        self.prompt_input.disabled = False
        self.prompt_input.focus()


def run_tui() -> None:
    """运行 TUI 应用。"""
    AgentTuiApp().run()

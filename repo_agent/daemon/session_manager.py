"""Agent 会话管理与执行调度。"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Any

from repo_agent.agent.client import AgentRuntime, create_client
from repo_agent.agent.loop import agent_turn, build_tools
from repo_agent.daemon.models import AgentEvent, TurnRequest


def _message_role(message: Any) -> str:
    """读取历史消息中的 role。"""
    if hasattr(message, "role"):
        return str(getattr(message, "role"))
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return ""


class AgentSession:
    """单个会话上下文。"""

    def __init__(
        self,
        session_id: str,
        runtime: AgentRuntime,
        tools: Any,
        max_events: int,
    ) -> None:
        self.session_id = session_id
        self.runtime = runtime
        self.tools = tools
        self.history: list[Any] = []

        self._max_events = max_events
        self._events: list[AgentEvent] = []
        self._last_event_id = 0
        self._turn_counter = 0
        self._busy = False
        self._stopped = False

        self._queue: queue.Queue[TurnRequest | None] = queue.Queue()
        self._condition = threading.Condition(threading.RLock())
        self._worker = threading.Thread(
            target=self._worker_loop,
            name=f"agent-session-{session_id}",
            daemon=True,
        )

    def start(self) -> None:
        """启动会话工作线程。"""
        self._worker.start()
        self._append_event(
            event_type="session_created",
            payload={
                "provider": self.runtime.provider,
                "model_id": self.runtime.model_id,
            },
            turn_id=None,
        )

    def stop(self) -> None:
        """停止会话工作线程。"""
        if self._stopped:
            return
        self._stopped = True
        self._queue.put(None)
        self._worker.join(timeout=3)

    def submit_turn(self, user_input: str) -> int:
        """提交一条用户问题并返回 turn_id。"""
        text = user_input.strip()
        if not text:
            raise ValueError("输入不能为空。")

        with self._condition:
            self._turn_counter += 1
            turn_id = self._turn_counter

        request = TurnRequest.create(turn_id=turn_id, user_input=text)
        self._queue.put(request)
        self._append_event(
            event_type="turn_enqueued",
            payload={"queue_size": self._queue.qsize()},
            turn_id=turn_id,
        )
        return turn_id

    def clear(self) -> tuple[bool, str]:
        """清空当前会话历史和等待队列。"""
        dropped_pending = self._drop_pending_turns()
        with self._condition:
            if self._busy:
                return (False, "当前有请求正在执行，暂不允许清空。")
            self.history.clear()
        self._append_event(
            event_type="session_cleared",
            payload={"dropped_pending": dropped_pending},
            turn_id=None,
        )
        return (True, "会话已清空。")

    def cancel(self) -> dict[str, Any]:
        """
        取消等待中的任务。

        当前实现不支持强制中断已经在模型侧执行中的回合。
        """
        dropped_pending = self._drop_pending_turns()
        with self._condition:
            running = self._busy
        result = {
            "running": running,
            "dropped_pending": dropped_pending,
            "hard_cancel_supported": False,
        }
        self._append_event(event_type="cancel_requested", payload=result, turn_id=None)
        return result

    def get_status(self) -> dict[str, Any]:
        """返回当前会话状态。"""
        with self._condition:
            busy = self._busy
            last_event_id = self._last_event_id
            last_turn_id = self._turn_counter
            history_size = len(self.history)

        return {
            "session_id": self.session_id,
            "provider": self.runtime.provider,
            "model_id": self.runtime.model_id,
            "busy": busy,
            "pending_count": self._queue.qsize(),
            "history_size": history_size,
            "last_event_id": last_event_id,
            "last_turn_id": last_turn_id,
        }

    def get_events(self, after: int, wait_ms: int, limit: int) -> dict[str, Any]:
        """获取 after 之后的事件；支持短轮询等待。"""
        wait_seconds = max(wait_ms, 0) / 1000.0
        deadline = time.monotonic() + wait_seconds

        with self._condition:
            while self._last_event_id <= after and wait_seconds > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=remaining)

            events = [event for event in self._events if event.event_id > after]
            if limit > 0:
                events = events[:limit]

            oldest_event_id = self._events[0].event_id if self._events else self._last_event_id + 1
            dropped_events = max(0, oldest_event_id - after - 1)
            return {
                "session_id": self.session_id,
                "events": [event.to_dict() for event in events],
                "last_event_id": self._last_event_id,
                "oldest_event_id": oldest_event_id,
                "dropped_events": dropped_events,
            }

    def _worker_loop(self) -> None:
        """串行执行会话内的回合任务。"""
        while True:
            request = self._queue.get()
            if request is None:
                self._queue.task_done()
                break

            self._run_turn(request)
            self._queue.task_done()

    def _run_turn(self, request: TurnRequest) -> None:
        """执行一轮完整 Agent 调用。"""
        with self._condition:
            self._busy = True
            self._condition.notify_all()

        turn_id = request.turn_id
        user_input = request.user_input
        self._append_event(event_type="turn_started", payload={"input": user_input}, turn_id=turn_id)
        self._append_event(event_type="user", payload={"text": user_input}, turn_id=turn_id)

        status = "completed"
        try:
            answer = agent_turn(
                runtime=self.runtime,
                tools=self.tools,
                history=self.history,
                user_input=user_input,
                event_handler=lambda event_type, payload: self._append_event(
                    event_type=event_type,
                    payload=payload,
                    turn_id=turn_id,
                ),
            )
            self._append_event(event_type="answer", payload={"text": answer}, turn_id=turn_id)
        except Exception as e:
            status = "failed"
            self._rollback_last_user_message()
            self._append_event(
                event_type="error",
                payload={"message": f"{type(e).__name__}: {e}"},
                turn_id=turn_id,
            )
        finally:
            with self._condition:
                self._busy = False
                self._condition.notify_all()
            self._append_event(event_type="turn_finished", payload={"status": status}, turn_id=turn_id)

    def _rollback_last_user_message(self) -> None:
        """在失败时回滚最后一条 user 消息，避免污染历史。"""
        with self._condition:
            if not self.history:
                return
            if _message_role(self.history[-1]) == "user":
                self.history.pop()

    def _drop_pending_turns(self) -> int:
        """丢弃等待队列中的 turn。"""
        dropped = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break

            if item is None:
                # 兜底保护：停止哨兵直接放回。
                self._queue.put(None)
                self._queue.task_done()
                break

            dropped += 1
            self._queue.task_done()
        return dropped

    def _append_event(self, event_type: str, payload: dict[str, Any], turn_id: int | None) -> None:
        """写入事件缓冲并通知订阅者。"""
        with self._condition:
            self._last_event_id += 1
            event = AgentEvent(
                event_id=self._last_event_id,
                session_id=self.session_id,
                turn_id=turn_id,
                event_type=event_type,
                payload=payload,
                timestamp=time.time(),
            )
            self._events.append(event)
            overflow = len(self._events) - self._max_events
            if overflow > 0:
                del self._events[:overflow]
            self._condition.notify_all()


class SessionManager:
    """多会话管理器。"""

    def __init__(self, max_events_per_session: int = 2000) -> None:
        self._max_events_per_session = max_events_per_session
        self._sessions: dict[str, AgentSession | None] = {}
        self._lock = threading.Lock()

    def create_session(self, session_id: str | None = None) -> AgentSession:
        """创建并启动新会话。"""
        new_session_id = session_id or uuid.uuid4().hex[:12]
        with self._lock:
            if new_session_id in self._sessions:
                raise ValueError(f"会话已存在：{new_session_id}")
            # 先占位，避免并发下重复创建同一 session_id。
            self._sessions[new_session_id] = None

        try:
            runtime = create_client()
            tools = build_tools(runtime.provider)
            session = AgentSession(
                session_id=new_session_id,
                runtime=runtime,
                tools=tools,
                max_events=self._max_events_per_session,
            )
            session.start()
        except Exception:
            with self._lock:
                existing = self._sessions.get(new_session_id)
                if existing is None:
                    del self._sessions[new_session_id]
            raise

        with self._lock:
            self._sessions[new_session_id] = session
        return session

    def get_session(self, session_id: str) -> AgentSession:
        """按 ID 获取会话。"""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"会话不存在或仍在初始化：{session_id}")
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话状态。"""
        with self._lock:
            sessions = [session for session in self._sessions.values() if session is not None]
        return [session.get_status() for session in sessions]

    def stop_all(self) -> None:
        """停止所有会话。"""
        with self._lock:
            sessions = [session for session in self._sessions.values() if session is not None]
            self._sessions.clear()
        for session in sessions:
            session.stop()

"""Agent 服务远程客户端。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class RemoteAgentError(RuntimeError):
    """远程调用异常。"""

    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"[HTTP {self.status_code}] {self.message}"


class RemoteAgentClient:
    """用于访问 Agent 常驻服务的轻量客户端。"""

    def __init__(self, endpoint: str, token: str | None = None, timeout: float = 30.0) -> None:
        normalized = endpoint.strip().rstrip("/")
        if not normalized.startswith("http://") and not normalized.startswith("https://"):
            normalized = f"http://{normalized}"
        self.endpoint = normalized
        self.token = token
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        """健康检查。"""
        return self._request("GET", "/health")

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出服务中的会话。"""
        payload = self._request("GET", "/sessions")
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            raise RemoteAgentError("服务端返回了无效的 sessions 字段。")
        return sessions

    def create_session(self, session_id: str | None = None) -> dict[str, Any]:
        """创建新会话。"""
        body: dict[str, Any] = {}
        if session_id:
            body["session_id"] = session_id
        return self._request("POST", "/sessions", payload=body)

    def get_session(self, session_id: str) -> dict[str, Any]:
        """查询会话状态。"""
        payload = self._request("GET", f"/sessions/{session_id}")
        session = payload.get("session")
        if not isinstance(session, dict):
            raise RemoteAgentError("服务端返回了无效的 session 字段。")
        return session

    def submit_turn(self, session_id: str, user_input: str) -> dict[str, Any]:
        """提交一轮用户输入。"""
        return self._request(
            "POST",
            f"/sessions/{session_id}/turns",
            payload={"input": user_input},
        )

    def clear_session(self, session_id: str) -> dict[str, Any]:
        """清空会话历史。"""
        return self._request("POST", f"/sessions/{session_id}/clear", payload={})

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        """取消等待中的请求。"""
        return self._request("POST", f"/sessions/{session_id}/cancel", payload={})

    def shutdown(self) -> dict[str, Any]:
        """请求服务端优雅关闭。"""
        return self._request("POST", "/shutdown", payload={})

    def get_events(
        self,
        session_id: str,
        after: int,
        wait_ms: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        """拉取事件流。"""
        query = {
            "after": str(max(after, 0)),
            "wait_ms": str(max(wait_ms, 0)),
            "limit": str(max(limit, 1)),
        }
        return self._request("GET", f"/sessions/{session_id}/events", query=query)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.endpoint}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["X-Agent-Token"] = self.token

        request = Request(url=url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as e:
            message = self._parse_error_message(e)
            raise RemoteAgentError(message=message, status_code=e.code) from e
        except URLError as e:
            raise RemoteAgentError(message=f"连接服务失败：{e}") from e
        except TimeoutError as e:
            raise RemoteAgentError(message=f"请求超时：{e}") from e

        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise RemoteAgentError(message=f"服务端返回了非 JSON 内容：{e}") from e
        if not isinstance(parsed, dict):
            raise RemoteAgentError(message="服务端返回了非对象结构。")
        return parsed

    @staticmethod
    def _parse_error_message(error: HTTPError) -> str:
        try:
            raw = error.read()
        except Exception:
            return str(error)
        if not raw:
            return str(error)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return raw.decode("utf-8", errors="ignore")
        if isinstance(payload, dict):
            message = payload.get("error")
            if isinstance(message, str) and message:
                return message
        return str(error)

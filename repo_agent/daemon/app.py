"""Agent 常驻服务 HTTP API。"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from repo_agent.daemon.session_manager import SessionManager


def _to_int(value: str | None, default: int, min_value: int, max_value: int) -> int:
    """将字符串解析为受限整数。"""
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(min_value, min(max_value, parsed))


class AgentDaemonHandler(BaseHTTPRequestHandler):
    """服务端 HTTP 处理器。"""

    server_version = "RepoAgentDaemon/0.1"
    manager: SessionManager
    auth_token: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        if not self._check_auth():
            return

        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        try:
            if parts == ["health"]:
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return

            if parts == ["sessions"]:
                sessions = self.manager.list_sessions()
                self._send_json(HTTPStatus.OK, {"sessions": sessions})
                return

            if len(parts) == 2 and parts[0] == "sessions":
                session = self.manager.get_session(parts[1])
                self._send_json(HTTPStatus.OK, {"session": session.get_status()})
                return

            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "events":
                session = self.manager.get_session(parts[1])
                query = parse_qs(parsed.query)
                after = _to_int(query.get("after", [None])[0], default=0, min_value=0, max_value=10**12)
                wait_ms = _to_int(query.get("wait_ms", [None])[0], default=0, min_value=0, max_value=30_000)
                limit = _to_int(query.get("limit", [None])[0], default=200, min_value=1, max_value=1_000)
                payload = session.get_events(after=after, wait_ms=wait_ms, limit=limit)
                self._send_json(HTTPStatus.OK, payload)
                return
        except KeyError as e:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(e))
            return
        except Exception as e:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(e).__name__}: {e}")
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, f"未找到路径：{parsed.path}")

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_auth():
            return

        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        body = self._read_json_body()

        try:
            if parts == ["sessions"]:
                requested_id = body.get("session_id")
                if requested_id is not None and not isinstance(requested_id, str):
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "session_id 必须是字符串。")
                    return
                session = self.manager.create_session(session_id=requested_id)
                self._send_json(
                    HTTPStatus.CREATED,
                    {
                        "session_id": session.session_id,
                        "session": session.get_status(),
                    },
                )
                return

            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "turns":
                session = self.manager.get_session(parts[1])
                user_input = body.get("input")
                if not isinstance(user_input, str):
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "input 字段必须是字符串。")
                    return
                turn_id = session.submit_turn(user_input)
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {
                        "session_id": session.session_id,
                        "turn_id": turn_id,
                    },
                )
                return

            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "clear":
                session = self.manager.get_session(parts[1])
                ok, message = session.clear()
                status = HTTPStatus.OK if ok else HTTPStatus.CONFLICT
                self._send_json(status, {"ok": ok, "message": message})
                return

            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "cancel":
                session = self.manager.get_session(parts[1])
                result = session.cancel()
                self._send_json(HTTPStatus.OK, result)
                return
        except KeyError as e:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(e))
            return
        except ValueError as e:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(e))
            return
        except Exception as e:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(e).__name__}: {e}")
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, f"未找到路径：{parsed.path}")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        """使用默认 stderr 输出 HTTP 访问日志。"""
        super().log_message(format, *args)

    def _check_auth(self) -> bool:
        token = self.auth_token
        if not token:
            return True
        incoming = self.headers.get("X-Agent-Token", "")
        if incoming != token:
            self._send_error_json(HTTPStatus.UNAUTHORIZED, "认证失败：X-Agent-Token 无效。")
            return False
        return True

    def _read_json_body(self) -> dict[str, Any]:
        content_length = self.headers.get("Content-Length")
        if not content_length:
            return {}
        try:
            size = int(content_length)
        except ValueError:
            return {}
        if size <= 0:
            return {}
        raw = self.rfile.read(size)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message, "status": status.value})


def run_agent_daemon(
    host: str,
    port: int,
    token: str | None = None,
    max_events_per_session: int = 2000,
) -> None:
    """启动 Agent 常驻服务。"""
    manager = SessionManager(max_events_per_session=max_events_per_session)
    AgentDaemonHandler.manager = manager
    AgentDaemonHandler.auth_token = token

    try:
        server = ThreadingHTTPServer((host, port), AgentDaemonHandler)
    except OSError as e:
        manager.stop_all()
        raise RuntimeError(f"启动服务失败：{e}") from e

    print(f"Agent 服务已启动：http://{host}:{port}")
    if token:
        print("已启用 token 鉴权（请求头：X-Agent-Token）。")
    print("按 Ctrl+C 停止服务。")

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\n正在停止 Agent 服务...")
    finally:
        server.shutdown()
        server.server_close()
        manager.stop_all()
        print("Agent 服务已停止。")

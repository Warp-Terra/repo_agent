"""服务端会话模型定义。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentEvent:
    """单条事件记录。"""

    event_id: int
    session_id: str
    event_type: str
    payload: dict[str, Any]
    turn_id: int | None = None
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 可传输结构。"""
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


@dataclass
class TurnRequest:
    """会话中的一次用户提问任务。"""

    turn_id: int
    user_input: str
    created_at: float

    @classmethod
    def create(cls, turn_id: int, user_input: str) -> "TurnRequest":
        """创建任务对象并记录时间戳。"""
        return cls(turn_id=turn_id, user_input=user_input, created_at=time.time())

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionTask:
    source: str
    path: str
    session_id: str
    session_key: str


@dataclass
class SessionSummary:
    session_key: str
    source: str
    session_id: str
    path: str
    project_hint: str | None
    timestamp: str | None
    text: str
    tool_signals: list[str]
    metadata: dict[str, Any]

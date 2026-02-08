from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Iterable

from ..models import SessionTask
from ..utils import cutoff_epoch, file_mtime_epoch, make_session_key


def _safe_jsonl_lines(path: str):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def discover_sessions(days: int) -> tuple[list[SessionTask], list[str]]:
    cutoff = cutoff_epoch(days)
    tasks: list[SessionTask] = []
    skipped_sources: list[str] = [
        "gemini_pb_deferred",
    ]

    # Claude global history.jsonl (multiple sessions)
    claude_hist = str(Path("~/.claude/history.jsonl").expanduser())
    if os.path.isfile(claude_hist):
        seen: set[str] = set()
        for item in _safe_jsonl_lines(claude_hist):
            ts = item.get("timestamp")
            if isinstance(ts, (int, float)):
                ts_epoch = int(ts // 1000 if ts > 10**12 else ts)
                if ts_epoch < cutoff:
                    continue
            session_id = str(item.get("sessionId") or "unknown")
            if session_id in seen:
                continue
            seen.add(session_id)
            tasks.append(
                SessionTask(
                    source="claude_history",
                    path=claude_hist,
                    session_id=session_id,
                    session_key=make_session_key("claude_history", claude_hist, session_id),
                )
            )

    # Claude project files (one session per file)
    for path in glob.glob(str(Path("~/.claude/projects/*/*.jsonl").expanduser())):
        mtime = file_mtime_epoch(path)
        if mtime < cutoff:
            continue
        session_id = Path(path).stem
        tasks.append(
            SessionTask(
                source="claude_project",
                path=path,
                session_id=session_id,
                session_key=make_session_key("claude_project", path, session_id),
            )
        )

    # Codex history (multiple sessions)
    codex_hist = str(Path("~/.codex/history.jsonl").expanduser())
    if os.path.isfile(codex_hist):
        seen: set[str] = set()
        for item in _safe_jsonl_lines(codex_hist):
            ts = item.get("ts")
            if isinstance(ts, (int, float)) and int(ts) < cutoff:
                continue
            session_id = str(item.get("session_id") or "unknown")
            if session_id in seen:
                continue
            seen.add(session_id)
            tasks.append(
                SessionTask(
                    source="codex_history",
                    path=codex_hist,
                    session_id=session_id,
                    session_key=make_session_key("codex_history", codex_hist, session_id),
                )
            )

    # Cursor prompt history (single synthetic session)
    cursor_prompt = str(Path("~/.cursor/prompt_history.json").expanduser())
    if os.path.isfile(cursor_prompt) and file_mtime_epoch(cursor_prompt) >= cutoff:
        session_id = "prompt_history"
        tasks.append(
            SessionTask(
                source="cursor_prompt_history",
                path=cursor_prompt,
                session_id=session_id,
                session_key=make_session_key("cursor_prompt_history", cursor_prompt, session_id),
            )
        )

    # Cursor chat stores (one session per store.db)
    for path in glob.glob(str(Path("~/.cursor/chats/*/*/store.db").expanduser())):
        if file_mtime_epoch(path) < cutoff:
            continue
        session_id = str(Path(path).parent.name)
        tasks.append(
            SessionTask(
                source="cursor_store_db",
                path=path,
                session_id=session_id,
                session_key=make_session_key("cursor_store_db", path, session_id),
            )
        )

    # Gemini temp sessions (one session per file)
    for path in glob.glob(str(Path("~/.gemini/tmp/*/chats/session-*.json").expanduser())):
        if file_mtime_epoch(path) < cutoff:
            continue
        session_id = Path(path).stem
        tasks.append(
            SessionTask(
                source="gemini_tmp_session",
                path=path,
                session_id=session_id,
                session_key=make_session_key("gemini_tmp_session", path, session_id),
            )
        )

    return tasks, skipped_sources

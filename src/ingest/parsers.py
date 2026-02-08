from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models import SessionSummary, SessionTask
from ..signals import extract_tool_signals
from ..utils import cutoff_epoch, to_iso_from_any_timestamp


def _collect_strings(obj: Any, out: list[str]) -> None:
    if obj is None:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if s:
            out.append(s)
        return
    if isinstance(obj, (int, float, bool)):
        out.append(str(obj))
        return
    if isinstance(obj, list):
        for item in obj:
            _collect_strings(item, out)
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in {"token", "secret", "api_key", "password"}:
                continue
            _collect_strings(value, out)


def _finalize_text(parts: list[str], max_items: int = 500, max_chars: int = 60000) -> tuple[str, int]:
    cleaned = [p.replace("\x00", " ").strip()[:600] for p in parts if p and p.strip()]
    original_count = len(cleaned)
    if len(cleaned) > max_items:
        half = max_items // 2
        cleaned = cleaned[:half] + cleaned[-half:]
    text = "\n".join(cleaned)
    if len(text) > max_chars:
        text = text[: max_chars - 16] + "\n[TRUNCATED_TEXT]"
    return text, original_count


def _safe_jsonl(path: str):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def parse_session(task: SessionTask, days: int) -> SessionSummary:
    if task.source == "claude_history":
        return _parse_claude_history_session(task, days)
    if task.source == "claude_project":
        return _parse_claude_project_file(task)
    if task.source == "codex_history":
        return _parse_codex_history_session(task, days)
    if task.source == "cursor_prompt_history":
        return _parse_cursor_prompt_history(task)
    if task.source == "cursor_store_db":
        return _parse_cursor_store_db(task)
    if task.source == "gemini_tmp_session":
        return _parse_gemini_tmp_session(task)
    raise ValueError(f"unknown source: {task.source}")


def _parse_claude_history_session(task: SessionTask, days: int) -> SessionSummary:
    cutoff = cutoff_epoch(days)
    texts: list[str] = []
    latest_ts: str | None = None
    project_hint: str | None = None
    for item in _safe_jsonl(task.path):
        if str(item.get("sessionId") or "") != task.session_id:
            continue
        ts = item.get("timestamp")
        if isinstance(ts, (int, float)):
            ts_epoch = int(ts // 1000 if ts > 10**12 else ts)
            if ts_epoch < cutoff:
                continue
            latest_ts = to_iso_from_any_timestamp(ts)
        project_hint = project_hint or item.get("project")
        display = item.get("display")
        if isinstance(display, str):
            texts.append(display)
        pasted = item.get("pastedContents")
        if pasted:
            _collect_strings(pasted, texts)
    text, original_count = _finalize_text(texts)
    return SessionSummary(
        session_key=task.session_key,
        source=task.source,
        session_id=task.session_id,
        path=task.path,
        project_hint=project_hint,
        timestamp=latest_ts,
        text=text,
        tool_signals=extract_tool_signals(text),
        metadata={"line_count": original_count},
    )


def _parse_claude_project_file(task: SessionTask) -> SessionSummary:
    texts: list[str] = []
    latest_ts: str | None = None
    for item in _safe_jsonl(task.path):
        _collect_strings(item, texts)
        ts = item.get("timestamp") if isinstance(item, dict) else None
        maybe_iso = to_iso_from_any_timestamp(ts)
        if maybe_iso:
            latest_ts = maybe_iso
    text, original_count = _finalize_text(texts)
    return SessionSummary(
        session_key=task.session_key,
        source=task.source,
        session_id=task.session_id,
        path=task.path,
        project_hint=None,
        timestamp=latest_ts,
        text=text,
        tool_signals=extract_tool_signals(text),
        metadata={"line_count": original_count},
    )


def _parse_codex_history_session(task: SessionTask, days: int) -> SessionSummary:
    cutoff = cutoff_epoch(days)
    texts: list[str] = []
    latest_ts: str | None = None
    for item in _safe_jsonl(task.path):
        if str(item.get("session_id") or "") != task.session_id:
            continue
        ts = item.get("ts")
        if isinstance(ts, (int, float)) and int(ts) < cutoff:
            continue
        latest_ts = to_iso_from_any_timestamp(ts)
        text = item.get("text")
        if isinstance(text, str):
            texts.append(text)
    joined, original_count = _finalize_text(texts)
    return SessionSummary(
        session_key=task.session_key,
        source=task.source,
        session_id=task.session_id,
        path=task.path,
        project_hint=None,
        timestamp=latest_ts,
        text=joined,
        tool_signals=extract_tool_signals(joined),
        metadata={"line_count": original_count},
    )


def _parse_cursor_prompt_history(task: SessionTask) -> SessionSummary:
    with open(task.path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    texts: list[str] = []
    if isinstance(data, list):
        for item in data:
            _collect_strings(item, texts)
    else:
        _collect_strings(data, texts)
    text, original_count = _finalize_text(texts)
    return SessionSummary(
        session_key=task.session_key,
        source=task.source,
        session_id=task.session_id,
        path=task.path,
        project_hint=None,
        timestamp=to_iso_from_any_timestamp(Path(task.path).stat().st_mtime),
        text=text,
        tool_signals=extract_tool_signals(text),
        metadata={"item_count": original_count},
    )


def _decode_cursor_blob(data: bytes, out: list[str]) -> None:
    if not data:
        return
    decoded = data.decode("utf-8", errors="ignore").strip()
    if not decoded:
        return
    if decoded.startswith("{") or decoded.startswith("["):
        try:
            parsed = json.loads(decoded)
            _collect_strings(parsed, out)
            return
        except json.JSONDecodeError:
            pass
    # Keep non-JSON text blobs too; Cursor stores mixed formats.
    out.append(decoded)


def _parse_cursor_store_db(task: SessionTask) -> SessionSummary:
    texts: list[str] = []
    conn = sqlite3.connect(task.path)
    try:
        cur = conn.cursor()
        for row in cur.execute("SELECT value FROM meta"):
            value = row[0]
            if isinstance(value, str):
                # Some entries are hex-encoded JSON payloads.
                if value and len(value) % 2 == 0:
                    try:
                        decoded_bytes = bytes.fromhex(value)
                        _decode_cursor_blob(decoded_bytes, texts)
                        continue
                    except ValueError:
                        pass
                texts.append(value)
        for row in cur.execute("SELECT data FROM blobs"):
            data = row[0]
            if isinstance(data, bytes):
                _decode_cursor_blob(data, texts)
            elif isinstance(data, str):
                texts.append(data)
    finally:
        conn.close()

    text, original_count = _finalize_text(texts)
    return SessionSummary(
        session_key=task.session_key,
        source=task.source,
        session_id=task.session_id,
        path=task.path,
        project_hint=str(Path(task.path).parents[1].name),
        timestamp=to_iso_from_any_timestamp(Path(task.path).stat().st_mtime),
        text=text,
        tool_signals=extract_tool_signals(text),
        metadata={"item_count": original_count},
    )


def _parse_gemini_tmp_session(task: SessionTask) -> SessionSummary:
    with open(task.path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    texts: list[str] = []
    _collect_strings(data.get("messages", data), texts)
    text, original_count = _finalize_text(texts)
    start = data.get("startTime") or data.get("lastUpdated")
    return SessionSummary(
        session_key=task.session_key,
        source=task.source,
        session_id=data.get("sessionId", task.session_id),
        path=task.path,
        project_hint=str(data.get("projectHash")) if data.get("projectHash") else None,
        timestamp=to_iso_from_any_timestamp(start) or to_iso_from_any_timestamp(Path(task.path).stat().st_mtime),
        text=text,
        tool_signals=extract_tool_signals(text),
        metadata={
            "message_count": len(data.get("messages", [])) if isinstance(data, dict) else 0,
            "collected_items": original_count,
        },
    )

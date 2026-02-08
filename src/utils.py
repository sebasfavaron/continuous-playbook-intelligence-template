from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cutoff_epoch(days: int) -> int:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return int(dt.timestamp())


def to_iso_from_any_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            s = value.strip()
            if s.isdigit():
                num = int(s)
                if num > 10**12:
                    num //= 1000
                return datetime.fromtimestamp(num, tz=timezone.utc).isoformat()
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                return None
        if isinstance(value, (int, float)):
            num = int(value)
            if num > 10**12:
                num //= 1000
            return datetime.fromtimestamp(num, tz=timezone.utc).isoformat()
    except Exception:
        return None
    return None


def file_mtime_epoch(path: str) -> int:
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def make_session_key(source: str, path: str, session_id: str) -> str:
    return stable_hash(f"{source}|{Path(path).expanduser()}|{session_id}")


def compact_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)

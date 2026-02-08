from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..utils import stable_hash, utc_now_iso


def ensure_parent_dir(path: str) -> None:
    parent = Path(path).expanduser().resolve().parent
    os.makedirs(parent, exist_ok=True)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return json.load(f)


def write_json(path: str, payload: Any) -> None:
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)
        f.write("\n")


def new_id(prefix: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return f"{prefix}_{stable_hash(raw)[:12]}"


def iso_now() -> str:
    return utc_now_iso()


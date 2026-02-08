from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .secrets import find_secrets_in_text
from ..utils import stable_hash

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HOME_PATH_RE = re.compile(r"/Users/[A-Za-z0-9._-]+")
UNIX_PATH_RE = re.compile(r"\b/(?:[A-Za-z0-9._-]+/){2,}[A-Za-z0-9._-]+\b")
WIN_PATH_RE = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\){2,}[^\\\s]+\b")

SENSITIVE_KEYS = {
    "token",
    "secret",
    "api_key",
    "password",
    "authorization",
    "cookie",
    "credentials",
}


@dataclass
class SanitizationReport:
    redacted_fields: int = 0
    redacted_strings: int = 0
    dropped_items: int = 0
    secret_hits: int = 0


def _redact_string(text: str, report: SanitizationReport, salt: str) -> str:
    original = text
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = IP_RE.sub("[REDACTED_IP]", text)
    text = HOME_PATH_RE.sub("$HOME", text)
    text = UNIX_PATH_RE.sub("$WORKSPACE/PATH", text)
    text = WIN_PATH_RE.sub(lambda _: "$WORKSPACE\\PATH", text)
    findings = find_secrets_in_text(text)
    if findings:
        report.secret_hits += len(findings)
        text = "[REDACTED_SECRET]"
    if text != original:
        report.redacted_strings += 1
    if len(text) > 1200:
        text = text[:1200] + " [TRUNCATED]"
    return text


def _sanitize(value: Any, report: SanitizationReport, salt: str) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return _redact_string(value, report, salt)
    if isinstance(value, list):
        out = []
        for item in value:
            cleaned = _sanitize(item, report, salt)
            if cleaned is None and item is not None:
                report.dropped_items += 1
                continue
            out.append(cleaned)
        return out
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k.lower() in SENSITIVE_KEYS:
                out[k] = "[REDACTED_FIELD]"
                report.redacted_fields += 1
                continue
            if k in {"path", "session_key", "session_id", "run_id"} and isinstance(v, str):
                out[k] = f"anon_{stable_hash(f'{salt}:{v}')[:12]}"
                report.redacted_fields += 1
                continue
            out[k] = _sanitize(v, report, salt)
        return out
    return _redact_string(str(value), report, salt)


def sanitize_payload(payload: Any, salt: str | None = None) -> tuple[Any, SanitizationReport]:
    effective_salt = salt or os.environ.get("CPI_SALT", "template-default-salt")
    report = SanitizationReport()
    cleaned = _sanitize(payload, report, effective_salt)
    if isinstance(cleaned, dict):
        cleaned = dict(cleaned)
        cleaned["sanitization_report"] = {
            "redacted_fields": report.redacted_fields,
            "redacted_strings": report.redacted_strings,
            "dropped_items": report.dropped_items,
            "secret_hits": report.secret_hits,
        }
    return cleaned, report


def sanitize_json_file(in_path: str, out_path: str, salt: str | None = None) -> SanitizationReport:
    with open(in_path, "r", encoding="utf-8", errors="ignore") as f:
        payload = json.load(f)
    cleaned, report = sanitize_payload(payload, salt=salt)
    out_parent = Path(out_path).expanduser().resolve().parent
    out_parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=True, indent=2)
        f.write("\n")
    return report

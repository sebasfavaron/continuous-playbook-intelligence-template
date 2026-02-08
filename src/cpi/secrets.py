from __future__ import annotations

import math
import re
from dataclasses import dataclass

SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)token\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)secret\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
]

_ENTROPY_TOKEN = re.compile(r"\b[A-Za-z0-9_\-+/=]{24,}\b")


@dataclass
class SecretFinding:
    kind: str
    sample: str


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    freqs = {}
    for ch in text:
        freqs[ch] = freqs.get(ch, 0) + 1
    n = len(text)
    return -sum((count / n) * math.log2(count / n) for count in freqs.values())


def find_secrets_in_text(text: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    if not text:
        return findings
    for pattern in SECRET_PATTERNS:
        for m in pattern.finditer(text):
            findings.append(SecretFinding(kind="regex", sample=m.group(0)[:80]))
    for m in _ENTROPY_TOKEN.finditer(text):
        token = m.group(0)
        if _entropy(token) >= 4.0:
            findings.append(SecretFinding(kind="entropy", sample=token[:80]))
    return findings


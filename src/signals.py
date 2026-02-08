from __future__ import annotations

import re
from collections import Counter

COMMAND_PATTERNS = [
    r"\bgit\b",
    r"\bssh\b",
    r"\bdocker\b",
    r"\bkubectl\b",
    r"\bnpm\b",
    r"\bpnpm\b",
    r"\byarn\b",
    r"\bpython(?:3)?\b",
    r"\bpytest\b",
    r"\bpip\b",
    r"\buv\b",
    r"\bcargo\b",
    r"\bgo\b",
    r"\bmake\b",
    r"\bterraform\b",
    r"\bansible\b",
    r"\bgh\b",
    r"\baws\b",
    r"\bgcloud\b",
    r"\bffmpeg\b",
    r"\bsqlite3\b",
]

WORKFLOW_KEYWORDS = {
    "deploy": ["deploy", "release", "rollout", "ship"],
    "debug": ["debug", "trace", "error", "fix", "bug"],
    "test": ["test", "pytest", "unit test", "integration"],
    "refactor": ["refactor", "cleanup", "rename", "restructure"],
    "docs": ["docs", "documentation", "readme"],
    "setup": ["setup", "install", "bootstrap", "configure"],
    "automation": ["automate", "automation", "script", "workflow"],
    "data": ["sql", "query", "migration", "etl", "csv"],
}


COMMAND_REGEXES = [(p, re.compile(p, re.IGNORECASE)) for p in COMMAND_PATTERNS]


def extract_tool_signals(text: str) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    counts: Counter[str] = Counter()

    for raw, regex in COMMAND_REGEXES:
        hits = len(regex.findall(text))
        if hits:
            label = raw.replace(r"\b", "")
            label = label.replace("(?:3)?", "")
            counts[label] += hits

    for workflow, keywords in WORKFLOW_KEYWORDS.items():
        hit_count = sum(lower.count(keyword) for keyword in keywords)
        if hit_count:
            counts[f"wf:{workflow}"] += hit_count

    ranked = [k for k, _ in counts.most_common(12)]
    return ranked

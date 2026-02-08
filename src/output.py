from __future__ import annotations

import json
import os
import tempfile
from collections import Counter

from .cluster import Cluster
from .score import score_cluster
from .specs import build_automation_spec
from .utils import stable_hash, utc_now_iso


def build_output(
    clusters: list[Cluster],
    total_events: int,
    total_sessions: int,
    window_days: int,
    skipped_sources: list[str],
    max_examples: int,
) -> dict:
    patterns = []
    for c in clusters:
        scores = score_cluster(c)
        sources = sorted({s.source for s in c.sessions})
        examples = [
            {
                "session_key": s.session_key,
                "source": s.source,
                "session_id": s.session_id,
                "path": s.path,
            }
            for s in c.sessions[:max_examples]
        ]
        label = ", ".join(c.representative_signals[:3])
        patterns.append(
            {
                "pattern_id": stable_hash(c.key)[:16],
                "taxonomy": "tool_usage",
                "label": label,
                "frequency": c.frequency,
                "affected_sources": sources,
                "representative_signals": c.representative_signals,
                **scores,
                "automation_spec": build_automation_spec(c),
                "example_references": examples,
            }
        )

    patterns.sort(key=lambda p: p["priority_score"], reverse=True)

    return {
        "generated_at": utc_now_iso(),
        "window_days": window_days,
        "summary": {
            "total_events": total_events,
            "total_sessions": total_sessions,
            "patterns_found": len(patterns),
            "source_counts": dict(Counter([src for p in patterns for src in p["affected_sources"]])),
        },
        "patterns": patterns,
        "skipped_sources": skipped_sources,
    }


def write_atomic_json(output_path: str, payload: dict) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="backlog-", suffix=".json", dir=os.path.dirname(output_path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
            f.write("\n")
        os.replace(tmp_path, output_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return stable_hash(json.dumps(payload, sort_keys=True, ensure_ascii=True))

from __future__ import annotations

from typing import Any

from .io import iso_now, new_id


def candidate_bundle_from_backlog(backlog: dict[str, Any]) -> dict[str, Any]:
    summary = backlog.get("summary", {}) if isinstance(backlog, dict) else {}
    patterns = backlog.get("patterns", []) if isinstance(backlog, dict) else []
    condensed_patterns: list[dict[str, Any]] = []
    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue
        condensed_patterns.append(
            {
                "pattern_id": pattern.get("pattern_id"),
                "label": pattern.get("label"),
                "taxonomy": pattern.get("taxonomy"),
                "priority_score": pattern.get("priority_score"),
                "frequency": pattern.get("frequency"),
                "representative_signals": pattern.get("representative_signals", []),
                "trigger": (
                    pattern.get("automation_spec", {}).get("trigger")
                    if isinstance(pattern.get("automation_spec"), dict)
                    else None
                ),
            }
        )
    payload: dict[str, Any] = {
        "bundle_id": "pending",
        "created_at": iso_now(),
        "miner_version": "v1",
        "source_summary": {
            "total_events": summary.get("total_events"),
            "total_sessions": summary.get("total_sessions"),
            "patterns_found": summary.get("patterns_found"),
            "source_counts": summary.get("source_counts", {}),
            "window_days": backlog.get("window_days"),
        },
        "patterns": condensed_patterns,
        "notes": "Generated from local mining output. Contains no raw transcript content by design.",
    }
    payload["bundle_id"] = new_id("candidate_bundle", payload)
    return payload


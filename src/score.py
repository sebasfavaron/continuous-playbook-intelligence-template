from __future__ import annotations

from .cluster import Cluster


def _impact_from_signals(signals: list[str]) -> float:
    joined = " ".join(signals)
    if "deploy" in joined or "wf:deploy" in joined or "release" in joined:
        return 5.0
    if "wf:debug" in joined or "pytest" in joined or "test" in joined:
        return 4.0
    if "git" in joined or "refactor" in joined:
        return 3.5
    return 2.5


def _success_confidence(cluster: Cluster) -> float:
    unique = len(set(cluster.representative_signals))
    conf = 0.45 + min(0.25, cluster.frequency * 0.03) + min(0.2, unique * 0.02)
    return round(min(1.0, conf), 4)


def score_cluster(cluster: Cluster) -> dict[str, float]:
    impact = _impact_from_signals(cluster.representative_signals)
    frequency_norm = min(1.0, cluster.frequency / 10.0)
    confidence = _success_confidence(cluster)
    priority = round(impact * frequency_norm * confidence, 4)
    return {
        "impact_score": round(impact, 4),
        "success_confidence": confidence,
        "priority_score": priority,
    }

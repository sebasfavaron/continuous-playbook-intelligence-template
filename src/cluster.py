from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import SessionSummary


@dataclass
class Cluster:
    key: str
    frequency: int
    sessions: list[SessionSummary]
    representative_signals: list[str]


def build_clusters(summaries: list[SessionSummary], min_frequency: int = 2) -> list[Cluster]:
    buckets: dict[str, list[SessionSummary]] = defaultdict(list)
    for s in summaries:
        signals = [sig for sig in s.tool_signals if sig]
        if not signals:
            continue
        key = "|".join(sorted(signals[:4]))
        if not key:
            continue
        buckets[key].append(s)

    clusters: list[Cluster] = []
    for key, items in buckets.items():
        if len(items) < min_frequency:
            continue
        signal_counter: Counter[str] = Counter()
        for item in items:
            signal_counter.update(item.tool_signals)
        clusters.append(
            Cluster(
                key=key,
                frequency=len(items),
                sessions=items,
                representative_signals=[k for k, _ in signal_counter.most_common(8)],
            )
        )

    clusters.sort(key=lambda c: c.frequency, reverse=True)
    return clusters

from src.cluster import Cluster
from src.models import SessionSummary
from src.score import score_cluster


def _summary(key: str) -> SessionSummary:
    return SessionSummary(
        session_key=key,
        source="codex_history",
        session_id=key,
        path="/tmp/f",
        project_hint=None,
        timestamp=None,
        text="git pytest",
        tool_signals=["git", "pytest", "wf:test"],
        metadata={},
    )


def test_score_cluster_deterministic():
    c = Cluster(
        key="git|pytest|wf:test",
        frequency=4,
        sessions=[_summary("a"), _summary("b"), _summary("c"), _summary("d")],
        representative_signals=["git", "pytest", "wf:test"],
    )
    s1 = score_cluster(c)
    s2 = score_cluster(c)
    assert s1 == s2
    assert s1["priority_score"] > 0

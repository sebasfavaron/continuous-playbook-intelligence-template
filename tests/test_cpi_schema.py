from src.cpi.schema import validate_schema


def test_validate_candidate_bundle_minimal():
    payload = {
        "bundle_id": "candidate_bundle_abc",
        "created_at": "2026-02-08T00:00:00+00:00",
        "patterns": [],
        "source_summary": {},
    }
    validate_schema(payload, "candidate_bundle")


def test_validate_feedback_record_minimal():
    payload = {
        "feedback_id": "feedback_abc",
        "run_id": "run_abc",
        "playbook_id": "repo_triage_v1",
        "outcome": "success",
        "rating": 4,
        "created_at": "2026-02-08T00:00:00+00:00",
    }
    validate_schema(payload, "feedback_record")


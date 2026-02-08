from __future__ import annotations

from typing import Any


class SchemaError(ValueError):
    pass


def _require_fields(payload: dict[str, Any], fields: list[str], schema_name: str) -> None:
    missing = [f for f in fields if f not in payload]
    if missing:
        raise SchemaError(f"{schema_name}: missing required fields: {', '.join(missing)}")


def validate_candidate_bundle(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SchemaError("candidate_bundle: payload must be an object")
    _require_fields(
        payload,
        ["bundle_id", "created_at", "patterns", "source_summary"],
        "candidate_bundle",
    )
    if not isinstance(payload.get("patterns"), list):
        raise SchemaError("candidate_bundle: patterns must be a list")
    if not isinstance(payload.get("source_summary"), dict):
        raise SchemaError("candidate_bundle: source_summary must be an object")


def validate_playbook_spec(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SchemaError("playbook_spec: payload must be an object")
    _require_fields(
        payload,
        ["playbook_id", "version", "intent", "steps", "guardrails", "expected_outputs"],
        "playbook_spec",
    )
    if not isinstance(payload.get("steps"), list) or not payload["steps"]:
        raise SchemaError("playbook_spec: steps must be a non-empty list")
    for idx, step in enumerate(payload["steps"]):
        if not isinstance(step, dict):
            raise SchemaError(f"playbook_spec: step {idx} must be an object")
        _require_fields(step, ["id", "description", "command"], "playbook_spec.step")


def validate_run_record(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SchemaError("run_record: payload must be an object")
    _require_fields(
        payload,
        ["run_id", "playbook_id", "mode", "steps", "started_at", "finished_at"],
        "run_record",
    )
    if payload.get("mode") not in {"plan", "execute"}:
        raise SchemaError("run_record: mode must be one of: plan, execute")
    if not isinstance(payload.get("steps"), list):
        raise SchemaError("run_record: steps must be a list")


def validate_feedback_record(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SchemaError("feedback_record: payload must be an object")
    _require_fields(
        payload,
        ["feedback_id", "run_id", "playbook_id", "outcome", "rating", "created_at"],
        "feedback_record",
    )
    if payload.get("outcome") not in {"success", "partial", "failure"}:
        raise SchemaError("feedback_record: outcome must be success|partial|failure")
    rating = payload.get("rating")
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise SchemaError("feedback_record: rating must be an integer in [1, 5]")


VALIDATORS = {
    "candidate_bundle": validate_candidate_bundle,
    "playbook_spec": validate_playbook_spec,
    "run_record": validate_run_record,
    "feedback_record": validate_feedback_record,
}


def validate_schema(payload: Any, schema_name: str) -> None:
    validator = VALIDATORS.get(schema_name)
    if validator is None:
        raise SchemaError(
            f"unknown schema: {schema_name}. expected one of: {', '.join(sorted(VALIDATORS.keys()))}"
        )
    validator(payload)


from __future__ import annotations

import json
from pathlib import Path

from .schema import SchemaError, validate_schema
from .secrets import find_secrets_in_text


def _infer_schema_from_path(path: Path) -> str | None:
    parts = set(path.parts)
    if "candidates" in parts:
        return "candidate_bundle"
    if "playbooks" in parts and path.suffix == ".json":
        return "playbook_spec"
    if "feedback" in parts:
        return "feedback_record"
    if "runs" in parts:
        return "run_record"
    return None


def run_precommit_checks(root: str) -> tuple[bool, list[str]]:
    base = Path(root).expanduser().resolve()
    errors: list[str] = []
    include_roots = [
        base / "candidates",
        base / "feedback",
        base / "playbooks",
        base / "schemas",
        base / "policies",
        base / "docs",
    ]
    paths_to_check: list[Path] = []
    for inc in include_roots:
        if not inc.exists():
            continue
        paths_to_check.extend([p for p in inc.rglob("*") if p.is_file()])

    for path in paths_to_check:
        if path.is_dir():
            continue
        if ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        findings = find_secrets_in_text(text)
        if findings:
            errors.append(f"{path}: secret-like content detected ({len(findings)} matches)")
        if path.suffix != ".json":
            continue
        schema_name = _infer_schema_from_path(path)
        if not schema_name:
            continue
        try:
            payload = json.loads(text)
            validate_schema(payload, schema_name)
        except (json.JSONDecodeError, SchemaError) as exc:
            errors.append(f"{path}: schema check failed ({exc})")
    return len(errors) == 0, errors

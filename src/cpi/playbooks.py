from __future__ import annotations

import glob
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from .io import iso_now, new_id
from .sanitize import sanitize_payload
from ..utils import stable_hash


def load_playbook_specs(playbooks_dir: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for path in sorted(glob.glob(str(Path(playbooks_dir) / "*.json"))):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            payload = json.load(f)
            if isinstance(payload, dict):
                payload["_source_path"] = path
                specs.append(payload)
    return specs


def _score_playbook(task: str, spec: dict[str, Any]) -> float:
    haystack = " ".join(
        [
            str(spec.get("intent", "")),
            " ".join(map(str, spec.get("triggers", []))),
            " ".join(map(str, spec.get("tags", []))),
        ]
    ).lower()
    terms = [t for t in task.lower().split() if len(t) > 2]
    if not terms:
        return 0.0
    matches = sum(1 for t in terms if t in haystack)
    return round(matches / len(terms), 4)


def suggest_playbooks(task: str, playbooks_dir: str) -> dict[str, Any]:
    specs = load_playbook_specs(playbooks_dir)
    ranked = sorted(
        [
            {
                "playbook_id": s.get("playbook_id"),
                "version": s.get("version"),
                "fit_score": _score_playbook(task, s),
                "intent": s.get("intent"),
                "source_path": s.get("_source_path"),
            }
            for s in specs
        ],
        key=lambda x: x["fit_score"],
        reverse=True,
    )
    return {
        "ok": True,
        "task": task,
        "suggestions": ranked,
        "generated_at": iso_now(),
    }


def _render_command(template: str, repo_path: str, env_name: str) -> str:
    return template.replace("{{repo_path}}", shlex.quote(repo_path)).replace("{{env}}", shlex.quote(env_name))


def run_playbook(
    playbook: dict[str, Any],
    repo_path: str,
    env_name: str,
    execute: bool,
    logs_dir: str,
) -> dict[str, Any]:
    run_id = new_id("run", {"playbook_id": playbook.get("playbook_id"), "ts": time.time()})
    os.makedirs(logs_dir, exist_ok=True)
    started_at = iso_now()
    steps_out: list[dict[str, Any]] = []

    for idx, step in enumerate(playbook.get("steps", []), start=1):
        step_id = str(step.get("id") or f"step_{idx}")
        cmd = _render_command(str(step.get("command", "")), repo_path=repo_path, env_name=env_name)
        out_path = str(Path(logs_dir) / f"{run_id}-{step_id}.stdout.log")
        err_path = str(Path(logs_dir) / f"{run_id}-{step_id}.stderr.log")

        if not execute:
            steps_out.append(
                {
                    "id": step_id,
                    "description": step.get("description"),
                    "command": cmd,
                    "status": "planned",
                    "stdout_path": out_path,
                    "stderr_path": err_path,
                    "duration_ms": 0,
                    "exit_code": None,
                }
            )
            continue

        t0 = time.time()
        with open(out_path, "w", encoding="utf-8") as out_f, open(err_path, "w", encoding="utf-8") as err_f:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=repo_path,
                stdout=out_f,
                stderr=err_f,
                text=True,
                timeout=120,
            )
        duration_ms = int((time.time() - t0) * 1000)
        status = "success" if proc.returncode == 0 else "failed"
        steps_out.append(
            {
                "id": step_id,
                "description": step.get("description"),
                "command": cmd,
                "status": status,
                "stdout_path": out_path,
                "stderr_path": err_path,
                "duration_ms": duration_ms,
                "exit_code": proc.returncode,
            }
        )
        if proc.returncode != 0:
            break

    outcome = "success"
    if any(s["status"] == "failed" for s in steps_out):
        outcome = "failure"
    elif execute and any(s["status"] != "success" for s in steps_out):
        outcome = "partial"
    elif not execute:
        outcome = "planned"

    return {
        "ok": outcome != "failure",
        "run_id": run_id,
        "playbook_id": playbook.get("playbook_id"),
        "mode": "execute" if execute else "plan",
        "repo_hash": stable_hash(repo_path)[:12],
        "env": env_name,
        "steps": steps_out,
        "outcome": outcome,
        "started_at": started_at,
        "finished_at": iso_now(),
    }


def build_feedback_record(
    run_record: dict[str, Any],
    outcome: str,
    rating: int,
    notes: str | None = None,
) -> dict[str, Any]:
    payload = {
        "feedback_id": "pending",
        "run_id": run_record.get("run_id"),
        "playbook_id": run_record.get("playbook_id"),
        "outcome": outcome,
        "rating": rating,
        "notes": notes or "",
        "created_at": iso_now(),
        "run_summary": {
            "mode": run_record.get("mode"),
            "step_count": len(run_record.get("steps", [])),
            "run_outcome": run_record.get("outcome"),
        },
    }
    payload["feedback_id"] = new_id("feedback", payload)
    cleaned, _ = sanitize_payload(payload)
    return cleaned


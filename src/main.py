from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .cluster import build_clusters
from .cpi.candidates import candidate_bundle_from_backlog
from .cpi.checks import run_precommit_checks
from .cpi.io import iso_now, read_json, write_json
from .cpi.playbooks import build_feedback_record, load_playbook_specs, run_playbook, suggest_playbooks
from .cpi.sanitize import sanitize_json_file
from .cpi.schema import SchemaError, validate_schema
from .ingest.discovery import discover_sessions
from .ingest.parsers import parse_session
from .output import build_output, write_atomic_json
from .state import StateStore
from .utils import stable_hash


def _mine_parser_defaults(p: argparse.ArgumentParser) -> None:
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--out", type=str, required=True)
    p.add_argument("--min-frequency", type=int, default=2)
    p.add_argument("--max-examples", type=int, default=3)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--run-id", type=str, default=None)
    p.add_argument("--force-requeue-failed", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Continuous Playbook Intelligence CLI")
    sub = p.add_subparsers(dest="command")

    mine = sub.add_parser("mine", help="Mine local conversation history into backlog JSON")
    _mine_parser_defaults(mine)

    sanitize = sub.add_parser("sanitize", help="Sanitize a JSON artifact before sharing/committing")
    sanitize.add_argument("--in", dest="in_path", required=True)
    sanitize.add_argument("--out", required=True)

    validate = sub.add_parser("validate", help="Validate JSON artifact against built-in schema")
    validate.add_argument("--file", required=True)
    validate.add_argument(
        "--schema",
        required=True,
        choices=["candidate_bundle", "playbook_spec", "run_record", "feedback_record"],
    )

    cand = sub.add_parser("candidates", help="Candidate bundle workflows")
    cand_sub = cand.add_subparsers(dest="candidates_cmd")
    cand_build = cand_sub.add_parser("build", help="Build candidate bundle from mined backlog")
    cand_build.add_argument("--from", dest="from_path", required=True)
    cand_build.add_argument("--out", required=True)
    cand_publish = cand_sub.add_parser("publish", help="Publish sanitized candidate bundle")
    cand_publish.add_argument("--in", dest="in_path", required=True)
    cand_publish.add_argument("--dest-dir", default="candidates/published")

    pb = sub.add_parser("playbooks", help="Playbook suggestion/execution workflows")
    pb_sub = pb.add_subparsers(dest="playbooks_cmd")
    pb_suggest = pb_sub.add_parser("suggest", help="Suggest playbooks for a task")
    pb_suggest.add_argument("--task", required=True)
    pb_suggest.add_argument("--playbooks-dir", default="playbooks")
    pb_suggest.add_argument("--out", required=False)
    pb_suggest.add_argument("--pretty", action="store_true")

    pb_run = pb_sub.add_parser("run", help="Plan or execute a playbook explicitly")
    pb_run.add_argument("--playbook-id", required=True)
    pb_run.add_argument("--repo", required=True)
    pb_run.add_argument("--env", default="local")
    pb_run.add_argument("--playbooks-dir", default="playbooks")
    pb_run.add_argument("--out", required=True)
    pb_run.add_argument("--execute", action="store_true")
    pb_run.add_argument("--logs-dir", default="runs/logs")

    pb_feedback = pb_sub.add_parser("feedback", help="Create sanitized feedback from a run record")
    pb_feedback.add_argument("--run", required=True)
    pb_feedback.add_argument("--out", required=True)
    pb_feedback.add_argument("--outcome", required=True, choices=["success", "partial", "failure"])
    pb_feedback.add_argument("--rating", required=True, type=int)
    pb_feedback.add_argument("--notes", default="")

    pcheck = sub.add_parser("precommit-check", help="Run schema + secret checks before commit")
    pcheck.add_argument("--path", default=".")

    return p


def _is_legacy_mode(argv: list[str]) -> bool:
    if not argv:
        return True
    return argv[0].startswith("-")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argsv = list(sys.argv[1:] if argv is None else argv)
    if _is_legacy_mode(argsv):
        p = argparse.ArgumentParser(description="Conversation Pattern Miner (legacy mine mode)")
        _mine_parser_defaults(p)
        args = p.parse_args(argsv)
        setattr(args, "command", "mine")
        return args
    parser = _build_parser()
    args = parser.parse_args(argsv)
    if not args.command:
        parser.error("missing command")
    return args


def run_mine(args: argparse.Namespace) -> int:
    state_db = os.path.join(os.path.dirname(args.out), "..", "state", "progress.db")
    state_db = os.path.abspath(state_db)
    config_hash = stable_hash(
        json.dumps(
            {
                "days": args.days,
                "min_frequency": args.min_frequency,
                "max_examples": args.max_examples,
                "sources": [
                    "claude_history",
                    "claude_project",
                    "codex_history",
                    "cursor_prompt_history",
                    "cursor_store_db",
                    "gemini_tmp_session",
                ],
            },
            sort_keys=True,
        )
    )
    store = StateStore(state_db)
    lock_owner = None
    run_id: str | None = None
    try:
        lock_owner = store.acquire_lock("conversation_miner")
        if args.run_id:
            run_id = args.run_id
        elif args.resume:
            run_id = store.find_resumable_run(config_hash)
        if run_id is None:
            run_id = store.create_run(config_hash)
        if args.force_requeue_failed:
            store.requeue_failed(run_id)
        store.mark_stale_in_progress_pending(run_id)
        store.set_run_stage(run_id, "discover")
        tasks, skipped_sources = discover_sessions(args.days)
        store.upsert_sessions(run_id, tasks)
        store.set_run_stage(run_id, "ingest_normalize")
        while True:
            task = store.next_pending_session(run_id)
            if not task:
                break
            store.heartbeat_lock("conversation_miner", lock_owner)
            store.mark_session_in_progress(run_id, task.session_key)
            try:
                summary = parse_session(task, args.days)
                store.mark_session_done(run_id, summary)
            except Exception as exc:
                store.mark_session_failed(run_id, task.session_key, str(exc))
        counts = store.session_status_counts(run_id)
        if counts.get("pending", 0) or counts.get("in_progress", 0):
            store.set_run_status(run_id, "running")
            return 2
        store.set_run_stage(run_id, "cluster")
        summaries = store.get_all_summaries(run_id)
        clusters = build_clusters(summaries, min_frequency=args.min_frequency)
        store.set_run_stage(run_id, "score_emit")
        total_events = sum(len(s.text.splitlines()) for s in summaries)
        payload = build_output(
            clusters=clusters,
            total_events=total_events,
            total_sessions=len(summaries),
            window_days=args.days,
            skipped_sources=skipped_sources,
            max_examples=args.max_examples,
        )
        checksum = write_atomic_json(args.out, payload)
        store.add_artifact(run_id, "backlog_json", args.out, checksum)
        if counts.get("failed", 0) > 0:
            store.set_run_status(run_id, "running")
            print(
                json.dumps(
                    {
                        "run_id": run_id,
                        "status": "partial",
                        "failed_sessions": counts.get("failed", 0),
                        "output": args.out,
                    }
                )
            )
            return 3
        store.set_run_status(run_id, "completed")
        print(json.dumps({"run_id": run_id, "status": "completed", "output": args.out}))
        return 0
    finally:
        if lock_owner:
            try:
                store.release_lock("conversation_miner", lock_owner)
            except Exception:
                pass
        store.close()


def run_sanitize(args: argparse.Namespace) -> int:
    report = sanitize_json_file(args.in_path, args.out)
    print(
        json.dumps(
            {
                "ok": True,
                "input": args.in_path,
                "output": args.out,
                "sanitization_report": report.__dict__,
            }
        )
    )
    return 0


def run_validate(args: argparse.Namespace) -> int:
    payload = read_json(args.file)
    validate_schema(payload, args.schema)
    print(json.dumps({"ok": True, "file": args.file, "schema": args.schema}))
    return 0


def run_candidates(args: argparse.Namespace) -> int:
    if args.candidates_cmd == "build":
        backlog = read_json(args.from_path)
        payload = candidate_bundle_from_backlog(backlog)
        write_json(args.out, payload)
        print(json.dumps({"ok": True, "output": args.out, "bundle_id": payload.get("bundle_id")}))
        return 0
    if args.candidates_cmd == "publish":
        payload = read_json(args.in_path)
        validate_schema(payload, "candidate_bundle")
        os.makedirs(args.dest_dir, exist_ok=True)
        target = str(Path(args.dest_dir) / f"{payload.get('bundle_id', 'candidate')}.json")
        shutil.copyfile(args.in_path, target)
        print(json.dumps({"ok": True, "published_to": target}))
        return 0
    raise ValueError("unknown candidates subcommand")


def run_playbooks(args: argparse.Namespace) -> int:
    if args.playbooks_cmd == "suggest":
        payload = suggest_playbooks(args.task, args.playbooks_dir)
        if args.out:
            write_json(args.out, payload)
        if args.pretty:
            lines = [f"- {s['playbook_id']} (fit={s['fit_score']})" for s in payload.get("suggestions", [])]
            print("\n".join(lines))
        else:
            print(json.dumps(payload))
        return 0

    if args.playbooks_cmd == "run":
        specs = load_playbook_specs(args.playbooks_dir)
        selected = next((s for s in specs if s.get("playbook_id") == args.playbook_id), None)
        if not selected:
            raise ValueError(f"playbook not found: {args.playbook_id}")
        payload = run_playbook(
            selected,
            repo_path=args.repo,
            env_name=args.env,
            execute=args.execute,
            logs_dir=args.logs_dir,
        )
        validate_schema(payload, "run_record")
        write_json(args.out, payload)
        print(json.dumps({"ok": True, "output": args.out, "run_id": payload.get("run_id")}))
        return 0

    if args.playbooks_cmd == "feedback":
        run_record = read_json(args.run)
        payload = build_feedback_record(
            run_record=run_record,
            outcome=args.outcome,
            rating=args.rating,
            notes=args.notes,
        )
        validate_schema(payload, "feedback_record")
        write_json(args.out, payload)
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": args.out,
                    "feedback_id": payload.get("feedback_id"),
                }
            )
        )
        return 0
    raise ValueError("unknown playbooks subcommand")


def run_precommit(args: argparse.Namespace) -> int:
    ok, errors = run_precommit_checks(args.path)
    if ok:
        print(json.dumps({"ok": True, "path": str(Path(args.path).resolve()), "checked_at": iso_now()}))
        return 0
    print(json.dumps({"ok": False, "errors": errors}))
    return 1


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "mine":
            return run_mine(args)
        if args.command == "sanitize":
            return run_sanitize(args)
        if args.command == "validate":
            return run_validate(args)
        if args.command == "candidates":
            return run_candidates(args)
        if args.command == "playbooks":
            return run_playbooks(args)
        if args.command == "precommit-check":
            return run_precommit(args)
        raise ValueError(f"unknown command: {args.command}")
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())


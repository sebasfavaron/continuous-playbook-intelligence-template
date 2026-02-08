from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import SessionTask, SessionSummary
from .utils import compact_json, utc_now_iso


class StateStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self):
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")
            yield cur
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _init_schema(self) -> None:
        with self.tx() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    run_id TEXT NOT NULL,
                    session_key TEXT NOT NULL,
                    source TEXT NOT NULL,
                    path TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT,
                    PRIMARY KEY (run_id, session_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS session_summaries (
                    run_id TEXT NOT NULL,
                    session_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, session_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, kind, path)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS locks (
                    lock_name TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    lease_until INTEGER NOT NULL
                )
                """
            )

    def acquire_lock(self, lock_name: str, lease_seconds: int = 120) -> str:
        owner = str(uuid.uuid4())
        now = int(time.time())
        lease_until = now + lease_seconds
        with self.tx() as cur:
            row = cur.execute(
                "SELECT owner_id, lease_until FROM locks WHERE lock_name = ?",
                (lock_name,),
            ).fetchone()
            if row and row["lease_until"] > now:
                raise RuntimeError("another process holds active lock")
            cur.execute(
                "REPLACE INTO locks(lock_name, owner_id, lease_until) VALUES (?, ?, ?)",
                (lock_name, owner, lease_until),
            )
        return owner

    def heartbeat_lock(self, lock_name: str, owner_id: str, lease_seconds: int = 120) -> None:
        with self.tx() as cur:
            cur.execute(
                "UPDATE locks SET lease_until = ? WHERE lock_name = ? AND owner_id = ?",
                (int(time.time()) + lease_seconds, lock_name, owner_id),
            )

    def release_lock(self, lock_name: str, owner_id: str) -> None:
        with self.tx() as cur:
            cur.execute(
                "DELETE FROM locks WHERE lock_name = ? AND owner_id = ?",
                (lock_name, owner_id),
            )

    def create_run(self, config_hash: str) -> str:
        run_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.tx() as cur:
            cur.execute(
                "INSERT INTO runs(run_id, started_at, status, config_hash, stage, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, now, "running", config_hash, "discover", now),
            )
        return run_id

    def find_resumable_run(self, config_hash: str) -> str | None:
        row = self.conn.execute(
            "SELECT run_id FROM runs WHERE config_hash = ? AND status = 'running' ORDER BY started_at DESC LIMIT 1",
            (config_hash,),
        ).fetchone()
        return row["run_id"] if row else None

    def set_run_stage(self, run_id: str, stage: str) -> None:
        with self.tx() as cur:
            cur.execute(
                "UPDATE runs SET stage = ?, updated_at = ? WHERE run_id = ?",
                (stage, utc_now_iso(), run_id),
            )

    def set_run_status(self, run_id: str, status: str) -> None:
        with self.tx() as cur:
            cur.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, utc_now_iso(), run_id),
            )

    def upsert_sessions(self, run_id: str, tasks: Iterable[SessionTask]) -> None:
        now = utc_now_iso()
        with self.tx() as cur:
            for t in tasks:
                cur.execute(
                    """
                    INSERT INTO sessions(run_id, session_key, source, path, session_id, stage, status, updated_at, error)
                    VALUES (?, ?, ?, ?, ?, 'ingest_normalize', 'pending', ?, NULL)
                    ON CONFLICT(run_id, session_key) DO NOTHING
                    """,
                    (run_id, t.session_key, t.source, t.path, t.session_id, now),
                )

    def mark_stale_in_progress_pending(self, run_id: str, stale_seconds: int = 900) -> int:
        cutoff = int(time.time()) - stale_seconds
        rows = self.conn.execute(
            "SELECT session_key, updated_at FROM sessions WHERE run_id = ? AND status = 'in_progress'",
            (run_id,),
        ).fetchall()
        stale_keys: list[str] = []
        for row in rows:
            try:
                dt = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
                ts = int(dt.astimezone(timezone.utc).timestamp())
            except Exception:
                ts = 0
            if ts < cutoff:
                stale_keys.append(row["session_key"])
        if not stale_keys:
            return 0
        with self.tx() as cur:
            for key in stale_keys:
                cur.execute(
                    "UPDATE sessions SET status = 'pending', updated_at = ?, error = NULL WHERE run_id = ? AND session_key = ?",
                    (utc_now_iso(), run_id, key),
                )
        return len(stale_keys)

    def requeue_failed(self, run_id: str) -> int:
        with self.tx() as cur:
            cur.execute(
                "UPDATE sessions SET status = 'pending', error = NULL, updated_at = ? WHERE run_id = ? AND status = 'failed'",
                (utc_now_iso(), run_id),
            )
            return cur.rowcount

    def next_pending_session(self, run_id: str) -> SessionTask | None:
        row = self.conn.execute(
            """
            SELECT session_key, source, path, session_id
            FROM sessions
            WHERE run_id = ? AND status = 'pending'
            ORDER BY source, path, session_id
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return SessionTask(
            source=row["source"],
            path=row["path"],
            session_id=row["session_id"],
            session_key=row["session_key"],
        )

    def mark_session_in_progress(self, run_id: str, session_key: str) -> None:
        with self.tx() as cur:
            cur.execute(
                "UPDATE sessions SET status = 'in_progress', updated_at = ? WHERE run_id = ? AND session_key = ?",
                (utc_now_iso(), run_id, session_key),
            )

    def mark_session_done(self, run_id: str, summary: SessionSummary) -> None:
        now = utc_now_iso()
        payload = asdict(summary)
        with self.tx() as cur:
            cur.execute(
                "UPDATE sessions SET status = 'done', updated_at = ?, error = NULL WHERE run_id = ? AND session_key = ?",
                (now, run_id, summary.session_key),
            )
            cur.execute(
                """
                INSERT INTO session_summaries(run_id, session_key, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, session_key)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (run_id, summary.session_key, compact_json(payload), now),
            )

    def mark_session_failed(self, run_id: str, session_key: str, error: str) -> None:
        with self.tx() as cur:
            cur.execute(
                "UPDATE sessions SET status = 'failed', updated_at = ?, error = ? WHERE run_id = ? AND session_key = ?",
                (utc_now_iso(), error[:1000], run_id, session_key),
            )

    def get_all_summaries(self, run_id: str) -> list[SessionSummary]:
        import json

        rows = self.conn.execute(
            "SELECT payload_json FROM session_summaries WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        out: list[SessionSummary] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            out.append(SessionSummary(**payload))
        return out

    def session_status_counts(self, run_id: str) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS c FROM sessions WHERE run_id = ? GROUP BY status",
            (run_id,),
        ).fetchall()
        return {row["status"]: row["c"] for row in rows}

    def add_artifact(self, run_id: str, kind: str, path: str, checksum: str) -> None:
        with self.tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO artifacts(run_id, kind, path, checksum, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, kind, path, checksum, utc_now_iso()),
            )

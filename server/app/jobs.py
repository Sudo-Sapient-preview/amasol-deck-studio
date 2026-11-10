"""Job state and event log, persisted in Postgres (Neon). See Contracts in PLAN.md for the schema.

Used by both the API (create/get/list/delete, cancel, sweep) and the worker, which runs the pipeline against the
same `Job` interface: data, id, dir, work, save, emit, update, stage, public, cancel_requested.
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Json

from . import config

STAGES = [
    ("ingest", "Read inputs"),
    ("draft", "Storyline"),
    ("plan", "Visuals and layouts"),
    ("build", "Build and verify"),
    ("review", "Visual review"),
]

TERMINAL = ("done", "failed", "cancelled")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id text PRIMARY KEY,
    root_id text NOT NULL,
    parent_id text,
    version int NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    heartbeat_at timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    next_seq int NOT NULL DEFAULT 0,
    draft text,
    data jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    job_id text REFERENCES jobs(id) ON DELETE CASCADE,
    seq int NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (job_id, seq)
);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS sandbox_live boolean NOT NULL DEFAULT false;
"""

_schema_ready: set[str] = set()


def _conn() -> psycopg.Connection:
    """A short-lived connection, closed by the caller's `with` block. One per call: safe under a Vercel
    Function's concurrent requests, since no state is shared between them."""
    conn = psycopg.connect(config.DATABASE_URL)
    url = config.DATABASE_URL
    if url not in _schema_ready:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
        _schema_ready.add(url)
    return conn


class Job:
    def __init__(self, data: dict):
        self.data = data
        self._cr_checked = 0.0
        self._cr_value = False

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def dir(self) -> Path:
        return config.JOBS_DIR / self.id

    @property
    def work(self) -> Path:
        return self.dir / "work"

    def save(self):
        """Write the whole `data` dict back, unless the job already reached a terminal status (a terminal
        status is never replaced, enforced here in the WHERE)."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET data=%s, status=%s, updated_at=now() "
                "WHERE id=%s AND status NOT IN ('done','failed','cancelled')",
                (Json(self.data), self.data.get("status"), self.id),
            )

    def update(self, **kw):
        self.data.update(kw)
        self.data["updated_at"] = time.time()
        self.save()

    def emit(self, type_: str, **kw) -> dict | None:
        """Append an event; the seq comes from `next_seq+1 ... returning` in the same transaction as the
        insert, so concurrent emits never gap or duplicate (Postgres serializes the UPDATE per job row)."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE jobs SET next_seq = next_seq + 1, updated_at = now() WHERE id=%s RETURNING next_seq",
                       (self.id,))
            row = cur.fetchone()
            if row is None:
                return None
            seq = row[0]
            ev = {"seq": seq, "t": time.time(), "type": type_, **kw}
            cur.execute("INSERT INTO events (job_id, seq, data) VALUES (%s, %s, %s)", (self.id, seq, Json(ev)))
        return ev

    def stage(self, key: str, status: str, summary: str | None = None):
        for s in self.data["stages"]:
            if s["key"] == key:
                s["status"] = status
                if status == "running":
                    s["started_at"] = time.time()
                if status in ("done", "failed", "skipped"):
                    s["ended_at"] = time.time()
                if summary is not None:
                    s["summary"] = summary
        self.save()
        self.emit("stage", key=key, status=status, summary=summary)

    def public(self) -> dict:
        d = dict(self.data)
        d.pop("internal", None)
        return d

    @property
    def cancel_requested(self) -> bool:
        """Reads the DB, at most once every 3 s (the pipeline polls this often in tight loops)."""
        now = time.monotonic()
        if now - self._cr_checked >= 3:
            with _conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT cancel_requested FROM jobs WHERE id=%s", (self.id,))
                row = cur.fetchone()
            self._cr_value = bool(row[0]) if row else False
            self._cr_checked = now
        return self._cr_value


class JobStore:
    """create/get/list/delete, all in Postgres. No in-memory index: every call is a query."""

    def create(self, brief: str, options: dict, model: str, parent: Job | None = None,
               feedback: str | None = None) -> Job:
        jid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        now = time.time()
        data = {
            "id": jid, "created_at": now, "updated_at": now, "status": "queued", "error": None,
            "brief": brief, "options": options, "model": model,
            "title": (parent.data.get("title") if parent else None) or _title_guess(brief),
            "parent_id": parent.id if parent else None,
            "root_id": parent.data.get("root_id", parent.id) if parent else jid,
            "version": (parent.data.get("version", 1) + 1) if parent else 1,
            "feedback": feedback,
            "stages": [{"key": k, "label": l, "status": "pending", "summary": None} for k, l in STAGES],
            "files": [], "warnings": [], "usage": {}, "result": None,
        }
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (id, root_id, parent_id, version, status, created_at, updated_at, data) "
                "VALUES (%s,%s,%s,%s,%s,to_timestamp(%s),to_timestamp(%s),%s)",
                (jid, data["root_id"], data["parent_id"], data["version"], data["status"], now, now, Json(data)),
            )
        return Job(data)

    def get(self, jid: str) -> Job | None:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM jobs WHERE id=%s", (jid,))
            row = cur.fetchone()
        return Job(row[0]) if row else None

    def exists(self, jid: str) -> bool:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM jobs WHERE id=%s", (jid,))
            return cur.fetchone() is not None

    def list(self) -> list[dict]:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM jobs ORDER BY created_at DESC")
            rows = cur.fetchall()
        out = []
        for (d,) in rows:
            out.append({k: d.get(k) for k in ("id", "created_at", "status", "title", "version", "root_id",
                                              "parent_id", "model")} |
                       {"slides": (d.get("result") or {}).get("slide_count"),
                        "snippet": " ".join((d.get("feedback") or d.get("brief") or "").split())[:140]})
        return out

    def delete(self, jid: str) -> None:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE id=%s", (jid,))

    def cancel(self, jid: str) -> bool:
        """The API decides a cancel: a queued/running job becomes cancelled at once (the WHERE is the CAS), its
        running stages become skipped, and the caller stops the sandbox. The worker is killed, not asked, and
        its later writes cannot undo a terminal status (Job.save). True if this call cancelled the job."""
        job = self.get(jid)
        if job is None or job.data.get("status") not in ("queued", "running"):
            return False
        now = time.time()
        skipped = [s["key"] for s in job.data["stages"] if s["status"] == "running"]
        for s in job.data["stages"]:
            if s["key"] in skipped:
                s.update(status="skipped", ended_at=now)
        job.data.update(status="cancelled", error=None, finished_at=now, updated_at=now)
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE jobs SET data=%s, status='cancelled', cancel_requested=true, updated_at=now() "
                        "WHERE id=%s AND status IN ('queued','running') RETURNING id", (Json(job.data), jid))
            if cur.fetchone() is None:
                return False   # the worker reached a terminal status first
        for key in skipped:
            job.emit("stage", key=key, status="skipped", summary=None)
        job.emit("status", status="cancelled")
        return True

    def set_sandbox_live(self, jid: str, live: bool) -> None:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE jobs SET sandbox_live=%s WHERE id=%s", (live, jid))

    def sandboxes_to_stop(self) -> list[str]:
        """Jobs that are finished but whose sandbox was never stopped (a sandbox can't end itself)."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM jobs WHERE sandbox_live AND status IN ('done','failed','cancelled')")
            return [r[0] for r in cur.fetchall()]

    def get_draft(self, jid: str) -> tuple[bool, str | None]:
        """(found, draft). `found` is False for an unknown job id; `draft` is None when none has landed yet."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT draft FROM jobs WHERE id=%s", (jid,))
            row = cur.fetchone()
        return (False, None) if row is None else (True, row[0])

    def events_after(self, jid: str, after: int) -> tuple[list[dict], str | None]:
        """(events with seq>after, current status); status is None for an unknown job id."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM jobs WHERE id=%s", (jid,))
            row = cur.fetchone()
            status = row[0] if row else None
            cur.execute("SELECT data FROM events WHERE job_id=%s AND seq>%s ORDER BY seq", (jid, after))
            evs = [r[0] for r in cur.fetchall()]
        return evs, status

    def sweep_stale(self) -> None:
        """A queued/running job whose heartbeat (or created_at, before the first one) is older than 3 min is
        marked failed. The WHERE is itself the CAS: a job already terminal is never matched."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status='failed', updated_at=now(), "
                "data = jsonb_set(jsonb_set(data, '{status}', '\"failed\"'), '{error}', "
                "to_jsonb('The build machine stopped. Run it again.'::text)) "
                "WHERE status IN ('queued','running') "
                "AND coalesce(heartbeat_at, created_at) < now() - interval '3 minutes'"
            )

    def all_referenced_uploads(self) -> set[str]:
        """Every upload blob referenced by ANY job's data.uploads (the uploads sweep's keep-list)."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT elem->>'blob' FROM jobs, jsonb_array_elements(data->'uploads') elem "
                "WHERE elem->>'blob' IS NOT NULL")
            return {r[0] for r in cur.fetchall()}

    def upload_blobs_referenced_elsewhere(self, jid: str) -> set[str]:
        """Every upload blob referenced by some OTHER job's data.uploads (the deletion rule keeps these)."""
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT elem->>'blob' FROM jobs, jsonb_array_elements(data->'uploads') elem "
                "WHERE id != %s AND elem->>'blob' IS NOT NULL", (jid,))
            return {r[0] for r in cur.fetchall()}


def _title_guess(brief: str) -> str:
    b = " ".join((brief or "").split())
    return (b[:70] + "…") if len(b) > 70 else (b or "Untitled deck")

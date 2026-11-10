"""Runs one deck job to completion inside its own sandbox: `python -m app.worker <job_id>` (see PLAN.md
Contracts, slice 1.3). Restores the job's inputs from Blob (its own uploads; a follow-up's parent state),
keeps Postgres current while the pipeline runs (a heartbeat every 20s, the live draft pushed on change every
3s), then runs today's pipeline unchanged. Outputs and the work state tarball go to Blob before the pipeline
writes its terminal status, so "done" is never visible before its files are.
"""
from __future__ import annotations

import io
import sys
import tarfile
import threading
import traceback
from pathlib import Path

import psycopg

from . import blobs, config
from .jobs import JobStore
from .pipeline import GOOD_FILES, Runner

HEARTBEAT_SECONDS = 20
DRAFT_POLL_SECONDS = 3
STATE_DIRS = ("inputs", "sources", "images", "good")
STATE_FILES = ("intake.json", "request.txt", "combined-sources.txt", "overrides.json", *GOOD_FILES)


def _db() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)


def _heartbeat(job_id: str, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with _db() as conn:
                conn.execute("UPDATE jobs SET heartbeat_at = now() WHERE id = %s", (job_id,))
        except psycopg.Error:
            pass   # self-heals on the next tick


def _draft_pusher(job_id: str, draft_path: Path, stop: threading.Event) -> None:
    last_mtime, last_text = None, None
    while not stop.wait(DRAFT_POLL_SECONDS):
        try:
            mtime = draft_path.stat().st_mtime
        except OSError:
            continue
        if mtime == last_mtime:
            continue
        last_mtime = mtime
        text = draft_path.read_text(encoding="utf-8")
        if text == last_text:
            continue
        last_text = text
        try:
            with _db() as conn:
                conn.execute("UPDATE jobs SET draft = %s WHERE id = %s", (text, job_id))
        except psycopg.Error:
            pass   # the next change will retry; the live draft is best-effort


def _download_blob(pathname: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blobs.get_bytes(pathname))


def restore_inputs(job) -> None:
    """Downloads this job's own uploads (a retry's are the same blobs, already in its data.uploads), and - for
    a follow-up - the parent's saved work state."""
    for u in job.data.get("uploads") or []:
        if u.get("blob"):
            _download_blob(u["blob"], job.work / u["saved"])
    parent_id = job.data.get("parent_id")
    if not parent_id:
        return
    state_path = f"jobs/{parent_id}/state.tar.gz"
    if blobs.head(state_path) is None:
        return
    parent_work = config.JOBS_DIR / parent_id / "work"
    parent_work.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blobs.get_bytes(state_path)), mode="r:gz") as tar:
        tar.extractall(parent_work)   # trusted: our own tarball, written by this same worker for this same job tree


def _state_tarball(work: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in STATE_FILES:
            if (work / name).exists():
                tar.add(work / name, arcname=name)
        for name in STATE_DIRS:
            if (work / name).is_dir():
                tar.add(work / name, arcname=name)
    return buf.getvalue()


def upload_outputs_and_state(job) -> None:
    outdir = job.dir / "output"
    if outdir.is_dir():
        for f in outdir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(outdir).as_posix()
                blobs.put_file(f"jobs/{job.id}/output/{rel}", f)
    blobs.put_bytes(f"jobs/{job.id}/state.tar.gz", _state_tarball(job.work))


def run_job(job) -> None:
    # heartbeat first: a big input download must not look like a dead build machine
    stop = threading.Event()
    threads = [threading.Thread(target=_heartbeat, args=(job.id, stop), daemon=True),
               threading.Thread(target=_draft_pusher, args=(job.id, job.work / "draft.md", stop), daemon=True)]
    for t in threads:
        t.start()
    try:
        runner = Runner(job, on_done=lambda: upload_outputs_and_state(job))
        try:
            restore_inputs(job)
        except Exception as e:  # noqa: BLE001 - any failure here must end the job with a reason, not a silent hang
            job.update(internal={**(job.data.get("internal") or {}), "traceback": traceback.format_exc()})
            runner._fail_running("failed", f"Could not load this deck's files: {type(e).__name__}: {e}")
            return
        runner.run()
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=5)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m app.worker <job_id>", file=sys.stderr)
        sys.exit(2)
    job = JobStore().get(sys.argv[1])
    if job is None:
        print(f"no such job: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    run_job(job)


if __name__ == "__main__":
    main()

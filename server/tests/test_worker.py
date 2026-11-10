"""1.3 proof: app.worker's input restore, output/state upload, heartbeat, live draft and crash handling,
against real Neon (pg_schema) and real Blob (blob_cleanup for paths under test/; jobs/<id>/... paths outside
that prefix are deleted explicitly, since the Contract fixes that layout). No test here makes a real LLM
call: the crash test monkeypatches a stage to raise before any model call, which is the cheap way to prove
the traceback path. The full real build (real sandbox, real pipeline, done/verify-PASS/outputs-in-Blob) was
run once by hand from /tmp (see the worker report); it is not re-run here because it costs LLM tokens."""
from __future__ import annotations

import io
import shutil
import tarfile
import threading
import time
import types
from pathlib import Path

from app import blobs, config, worker
from app.jobs import JobStore
from app.pipeline import Runner


def _retry(fn, tries: int = 20, delay: float = 1.0):
    """Blob content reads can 404 for a while after a put even once head() finds it (also seen in
    test_store.py; worse right now with three agents' sandboxes and blob calls sharing the same account).
    Retry the read itself rather than pre-poll head(), which turned out not to predict it."""
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay)
    raise last


def _fake_job(job_id: str, work_root: Path, **data) -> types.SimpleNamespace:
    """A Job stand-in with just the attributes restore_inputs/upload_outputs_and_state touch: no DB needed."""
    j = types.SimpleNamespace()
    j.data = {"id": job_id, **data}
    j.id = job_id
    j.dir = work_root / job_id
    j.work = j.dir / "work"
    j.work.mkdir(parents=True, exist_ok=True)
    return j


def test_state_tarball_roundtrip(tmp_path):
    work = tmp_path / "work"
    (work / "sources").mkdir(parents=True)
    (work / "sources" / "a.txt").write_text("hello")
    (work / "draft.md").write_text("title: x\n")
    (work / "intake.json").write_text("{}")

    data = worker._state_tarball(work)

    out = tmp_path / "out"
    out.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(out)
    assert (out / "sources" / "a.txt").read_text() == "hello"
    assert (out / "draft.md").read_text() == "title: x\n"
    assert (out / "intake.json").exists()


def test_restore_inputs_downloads_uploads(tmp_path, blob_cleanup):
    blob_path = "test/worker-upload/notes.txt"
    blobs.put_bytes(blob_path, b"my notes")
    job = _fake_job("test-restore-uploads", tmp_path, uploads=[{"blob": blob_path, "saved": "inputs/notes.txt"}])
    _retry(lambda: worker.restore_inputs(job))   # restore_inputs is safe to retry: it only overwrites dest files
    assert (job.work / "inputs" / "notes.txt").read_bytes() == b"my notes"


def test_restore_inputs_parent_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    parent_id = "test-parent-state"
    # build the tarball the same way a real parent job's worker would, from its own work dir
    src_work = tmp_path / "src-work"
    src_work.mkdir(parents=True)
    (src_work / "draft.md").write_text("title: parent\n")
    tar_bytes = worker._state_tarball(src_work)
    state_path = f"jobs/{parent_id}/state.tar.gz"
    blobs.put_bytes(state_path, tar_bytes)
    try:
        job = _fake_job("test-restore-parent-child", tmp_path, parent_id=parent_id)
        restored = config.JOBS_DIR / parent_id / "work" / "draft.md"

        def attempt():
            worker.restore_inputs(job)   # a no-op (not an error) if the blob isn't visible to head() yet
            return restored.read_text()  # so check the actual result, and retry on that instead

        assert _retry(attempt) == "title: parent\n"
    finally:
        blobs.delete(state_path)


def test_restore_inputs_no_parent_state_blob_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    job = _fake_job("test-restore-missing-parent", tmp_path, parent_id="test-parent-does-not-exist")
    worker.restore_inputs(job)   # must not raise
    assert not (config.JOBS_DIR / "test-parent-does-not-exist").exists()


def test_upload_outputs_and_state(tmp_path):
    job = _fake_job("test-upload-outputs", tmp_path)
    (job.dir / "output" / "slides").mkdir(parents=True)
    (job.dir / "output" / "deck.pptx").write_bytes(b"pptx-bytes")
    (job.dir / "output" / "slides" / "slide-01.jpg").write_bytes(b"jpg-bytes")
    (job.work / "draft.md").write_text("title: x\n")
    try:
        worker.upload_outputs_and_state(job)
        assert _retry(lambda: blobs.get_bytes(f"jobs/{job.id}/output/deck.pptx")) == b"pptx-bytes"
        assert _retry(lambda: blobs.get_bytes(f"jobs/{job.id}/output/slides/slide-01.jpg")) == b"jpg-bytes"
        state = _retry(lambda: blobs.get_bytes(f"jobs/{job.id}/state.tar.gz"))
        assert state[:2] == b"\x1f\x8b"   # gzip magic
    finally:
        blobs.delete_prefix(f"jobs/{job.id}/")


def test_heartbeat_and_draft_pusher_write_to_postgres(pg_schema):
    store = JobStore()
    job = store.create("a test brief", {}, "claude-sonnet-5-5")
    try:
        job.work.mkdir(parents=True, exist_ok=True)
        draft = job.work / "draft.md"

        stop = threading.Event()
        t_hb = threading.Thread(target=worker._heartbeat, args=(job.id, stop), daemon=True)
        t_draft = threading.Thread(target=worker._draft_pusher, args=(job.id, draft, stop), daemon=True)
        t_hb.start()
        t_draft.start()
        time.sleep(worker.HEARTBEAT_SECONDS + 2)
        draft.write_text("first draft\n")
        time.sleep(worker.DRAFT_POLL_SECONDS + 2)
        stop.set()
        t_hb.join(timeout=5)
        t_draft.join(timeout=5)

        found, saved_draft = store.get_draft(job.id)
        assert found and saved_draft == "first draft\n"
        import psycopg
        with psycopg.connect(config.DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT heartbeat_at FROM jobs WHERE id=%s", (job.id,))
            (heartbeat_at,) = cur.fetchone()
        assert heartbeat_at is not None
    finally:
        shutil.rmtree(job.dir, ignore_errors=True)


def test_crash_puts_traceback_in_internal_data_and_fails(pg_schema, monkeypatch):
    """Forces an exception inside the ingest stage, before any model call, and checks the worker's contract:
    the traceback lands in data.internal.traceback and the status is failed."""
    store = JobStore()
    job = store.create("a test brief", {}, "claude-sonnet-5-5")
    try:
        job.work.mkdir(parents=True, exist_ok=True)

        def boom(self):
            raise RuntimeError("forced crash for the worker test")

        monkeypatch.setattr(Runner, "do_ingest", boom)
        Runner(job).run()

        assert job.data["status"] == "failed"
        tb = (job.data.get("internal") or {}).get("traceback", "")
        assert "RuntimeError" in tb and "forced crash for the worker test" in tb
    finally:
        shutil.rmtree(job.dir, ignore_errors=True)

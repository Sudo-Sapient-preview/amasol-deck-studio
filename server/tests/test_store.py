"""1.2 proof: the Postgres job store and the Blob helpers, against real Neon and real Blob. No mocks."""
from __future__ import annotations

import threading
import time

from app import blobs, jobs


def _read_with_retry(pathname: str, tries: int = 5, delay: float = 0.5) -> bytes:
    """A blob can lag a moment between put and its first read (observed in practice); retry briefly
    rather than let that infra timing flake a correctness test."""
    last = None
    for _ in range(tries):
        try:
            with blobs.stream(pathname) as chunks:
                return b"".join(chunks)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay)
    raise last


def test_create_emit_stage_list_delete(pg_schema):
    store = jobs.JobStore()
    job = store.create("Build a deck about widgets", {}, "claude-opus-5-5")
    assert job.data["status"] == "queued"

    ev = job.emit("log", kind="info", text="hello")
    assert ev["seq"] == 1
    job.stage("ingest", "running")
    job.stage("ingest", "done", "ok")
    assert job.data["stages"][0]["status"] == "done"

    fetched = store.get(job.id)
    assert fetched is not None
    assert fetched.data["stages"][0]["status"] == "done"
    evs, status = store.events_after(job.id, 0)
    assert status == "queued"
    assert [e["type"] for e in evs] == ["log", "stage", "stage"]

    listed = store.list()
    assert any(j["id"] == job.id for j in listed)

    store.delete(job.id)
    assert store.get(job.id) is None


def test_20_concurrent_emits_no_gaps_or_dupes(pg_schema):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")

    def emit_one(i):
        job.emit("log", kind="info", text=f"n{i}")

    threads = [threading.Thread(target=emit_one, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    evs, _ = store.events_after(job.id, 0)
    seqs = sorted(e["seq"] for e in evs)
    assert seqs == list(range(1, 21)), seqs


def test_terminal_status_never_replaced(pg_schema):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    job.update(status="done", result={"slide_count": 5})
    job.update(status="failed", error="should not apply")
    fresh = store.get(job.id)
    assert fresh.data["status"] == "done"
    assert fresh.data.get("error") != "should not apply"


def test_stale_heartbeat_marks_failed(pg_schema):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    with jobs._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE jobs SET created_at = now() - interval '10 minutes' WHERE id=%s", (job.id,))
    store.sweep_stale()
    fresh = store.get(job.id)
    assert fresh.data["status"] == "failed"
    assert "stopped" in fresh.data["error"]


def test_stale_sweep_does_not_touch_terminal_or_fresh_jobs(pg_schema):
    store = jobs.JobStore()
    done_job = store.create("brief", {}, "claude-opus-5-5")
    done_job.update(status="done")
    with jobs._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE jobs SET created_at = now() - interval '10 minutes' WHERE id=%s", (done_job.id,))
    fresh_job = store.create("brief", {}, "claude-opus-5-5")
    store.sweep_stale()
    assert store.get(done_job.id).data["status"] == "done"
    assert store.get(fresh_job.id).data["status"] == "queued"


def test_cancel_is_cas_guarded(pg_schema):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    assert store.cancel(job.id) is True
    assert job.cancel_requested is True            # the worker's in-loop check still sees it
    assert store.get(job.id).data["status"] == "cancelled"
    assert store.cancel(job.id) is False           # terminal: not changed


def test_blob_put_head_stream_delete(blob_ns):
    path = f"{blob_ns}hello.txt"
    blobs.put_bytes(path, b"hello world")
    meta = blobs.head(path)
    assert meta is not None and meta.size == len(b"hello world")
    body = _read_with_retry(path)
    assert body == b"hello world"
    blobs.delete(path)
    assert blobs.head(path) is None


def test_blob_delete_prefix(blob_ns):
    a, b = f"{blob_ns}dir/a.txt", f"{blob_ns}dir/b.txt"
    blobs.put_bytes(a, b"a")
    blobs.put_bytes(b, b"b")
    blobs.delete_prefix(f"{blob_ns}dir/")
    assert blobs.head(a) is None
    assert blobs.head(b) is None


def test_deletion_rule_keeps_shared_upload_blob(pg_schema, blob_ns):
    """Deleting a job removes jobs/<id>/ and only the upload blobs no other job references."""
    store = jobs.JobStore()
    shared, mine = f"{blob_ns}uploads/shared.txt", f"{blob_ns}uploads/only-mine.txt"
    blobs.put_bytes(shared, b"shared content")
    blobs.put_bytes(mine, b"mine only")

    job_a = store.create("brief", {}, "claude-opus-5-5")
    job_a.update(uploads=[{"name": "shared.txt", "saved": "inputs/shared.txt", "role": "content",
                           "blob": shared, "size": 14}])
    job_b = store.create("brief", {}, "claude-opus-5-5")
    job_b.update(uploads=[
        {"name": "shared.txt", "saved": "inputs/shared.txt", "role": "content", "blob": shared, "size": 14},
        {"name": "only-mine.txt", "saved": "inputs/only-mine.txt", "role": "content", "blob": mine, "size": 9},
    ])
    blobs.put_bytes(f"jobs/{job_b.id}/output/deck.pptx", b"pretend pptx")

    referenced = store.upload_blobs_referenced_elsewhere(job_b.id)
    assert referenced == {shared}

    my_blobs = {u["blob"] for u in job_b.data["uploads"]}
    orphan = [b for b in my_blobs if b not in referenced]
    assert orphan == [mine]
    blobs.delete(orphan)
    blobs.delete_prefix(f"jobs/{job_b.id}/")
    store.delete(job_b.id)

    assert blobs.head(shared) is not None   # kept: job_a still references it
    assert blobs.head(mine) is None         # gone: no one else referenced it
    assert blobs.head(f"jobs/{job_b.id}/output/deck.pptx") is None

    store.delete(job_a.id)

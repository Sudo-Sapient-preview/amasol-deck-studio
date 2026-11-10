"""1.5 proof: the read/control path - SSE, draft, file streaming, cancel, delete, stale-heartbeat - against
the real API, real Neon and real Blob. No mocks."""
from __future__ import annotations

import re

import pytest

from app import blobs, jobs

pytestmark = pytest.mark.anyio


def _ids(sse_text: str) -> list[int]:
    return [int(m) for m in re.findall(r"^id: (\d+)$", sse_text, re.M)]


async def test_sse_drains_then_ends_when_terminal(pg_schema, client):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    job.emit("log", kind="info", text="one")
    job.emit("log", kind="info", text="two")
    job.update(status="done", result={"slide_count": 3})
    job.emit("status", status="done")

    r = await client.get(f"/api/jobs/{job.id}/events?after=0")
    assert r.status_code == 200
    assert _ids(r.text) == [1, 2, 3]
    assert "event: end" in r.text


async def test_sse_reconnect_with_after_has_no_dupes(pg_schema, client):
    """The client's own reconnect contract: ?after=<last seq it saw> gets only what's new, never a repeat."""
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    job.emit("log", kind="info", text="one")
    job.emit("log", kind="info", text="two")
    job.update(status="done")
    job.emit("status", status="done")

    first = await client.get(f"/api/jobs/{job.id}/events?after=0")
    seen = _ids(first.text)
    assert seen == [1, 2, 3]

    second = await client.get(f"/api/jobs/{job.id}/events?after={max(seen)}")
    assert _ids(second.text) == []  # nothing new: no duplicate of 1, 2 or 3
    assert "event: end" in second.text

    third = await client.get(f"/api/jobs/{job.id}/events?after=1")
    assert _ids(third.text) == [2, 3]  # a reconnect that missed the tail only gets what it hasn't seen


async def test_sse_unknown_job_is_404(pg_schema, client):
    r = await client.get("/api/jobs/does-not-exist/events")
    assert r.status_code == 404


async def test_draft_before_and_after(pg_schema, client):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    r = await client.get(f"/api/jobs/{job.id}/draft")
    assert r.status_code == 404  # job exists, but no draft yet

    with jobs._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE jobs SET draft=%s WHERE id=%s", ("# Title\n- a point", job.id))
    r2 = await client.get(f"/api/jobs/{job.id}/draft")
    assert r2.status_code == 200
    assert r2.text == "# Title\n- a point"

    r3 = await client.get("/api/jobs/does-not-exist/draft")
    assert r3.status_code == 404


async def test_file_route_streams_from_blob_and_refuses_traversal(pg_schema, client):
    """Paths are relative to the job, exactly as the worker's result lists them (result.slides, result.pptx:
    "output/slides/slide-01.jpg"), and only files under output/ are served."""
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    blobs.put_bytes(f"jobs/{job.id}/output/slides/slide-01.jpg", b"fake-jpeg-bytes")
    blobs.put_bytes(f"jobs/{job.id}/state.tar.gz", b"private work state")

    try:
        ok = await client.get(f"/api/jobs/{job.id}/file/output/slides/slide-01.jpg")
        assert ok.status_code == 200
        assert ok.content == b"fake-jpeg-bytes"
        dl = await client.get(f"/api/jobs/{job.id}/file/output/slides/slide-01.jpg?download=1")
        assert dl.status_code == 200 and 'filename="slide-01.jpg"' in dl.headers["content-disposition"]

        missing = await client.get(f"/api/jobs/{job.id}/file/output/slides/does-not-exist.jpg")
        assert missing.status_code == 404

        # only output/ is served: not the work state, not a path without the output/ prefix, no traversal
        for bad in ("state.tar.gz", "../state.tar.gz", "output/../state.tar.gz", "..%2f..%2fsecret.txt",
                    "slides/slide-01.jpg"):
            r = await client.get(f"/api/jobs/{job.id}/file/{bad}")
            assert r.status_code == 404, bad
    finally:
        blobs.delete_prefix(f"jobs/{job.id}/")
        store.delete(job.id)


async def test_cancel_marks_cancelled_at_once_and_stops_the_sandbox(pg_schema, client):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    job.stage("ingest", "running")
    job.update(status="running")
    store.set_sandbox_live(job.id, True)

    r = await client.post(f"/api/jobs/{job.id}/cancel")
    assert r.status_code == 200

    fresh = store.get(job.id)
    assert fresh.data["status"] == "cancelled"          # the API decides; no wait for the worker
    assert fresh.data["stages"][0]["status"] == "skipped"
    evs, status = store.events_after(job.id, 0)
    assert status == "cancelled" and evs[-1] == {**evs[-1], "type": "status", "status": "cancelled"}
    assert store.sandboxes_to_stop() == []                # stopped (no such sandbox here: 404 counts as gone)

    fresh.update(status="running")                         # a late worker write must not undo the cancel
    assert store.get(job.id).data["status"] == "cancelled"


async def test_cancel_on_terminal_job_is_a_cas_noop(pg_schema, client):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    job.update(status="done")
    r = await client.post(f"/api/jobs/{job.id}/cancel")
    assert r.status_code == 200
    assert store.cancel(job.id) is False
    assert store.get(job.id).data["status"] == "done"


async def test_sweep_needs_the_cron_secret(pg_schema, client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret-for-test")
    assert (await client.get("/api/internal/sweep")).status_code == 401
    assert (await client.get("/api/internal/sweep", headers={"authorization": "Bearer wrong"})).status_code == 401
    monkeypatch.delenv("CRON_SECRET")
    assert (await client.get("/api/internal/sweep", headers={"authorization": "Bearer "})).status_code == 401


async def test_sweep_stops_sandboxes_of_finished_jobs_only(pg_schema, client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret-for-test")
    store = jobs.JobStore()
    done = store.create("brief", {}, "claude-opus-5-5")
    done.update(status="done")
    store.set_sandbox_live(done.id, True)
    live = store.create("brief", {}, "claude-opus-5-5")
    live.update(status="running")
    store.set_sandbox_live(live.id, True)

    r = await client.get("/api/internal/sweep", headers={"authorization": "Bearer s3cret-for-test"})
    assert r.status_code == 200 and r.json() == {"stopped": 1}
    assert store.sandboxes_to_stop() == []
    r = await client.get("/api/internal/sweep", headers={"authorization": "Bearer s3cret-for-test"})
    assert r.json() == {"stopped": 0}                     # idempotent: a second run finds nothing


async def test_delete_removes_row_and_output_blobs_but_keeps_shared_uploads(pg_schema, blob_ns, client):
    store = jobs.JobStore()
    shared = f"{blob_ns}uploads/shared.txt"
    blobs.put_bytes(shared, b"shared")
    other = store.create("brief", {}, "claude-opus-5-5")
    other.update(uploads=[{"name": "shared.txt", "saved": "inputs/shared.txt", "role": "content",
                           "blob": shared, "size": 6}])

    job = store.create("brief", {}, "claude-opus-5-5")
    job.update(status="done", uploads=[{"name": "shared.txt", "saved": "inputs/shared.txt", "role": "content",
                                        "blob": shared, "size": 6}])
    blobs.put_bytes(f"jobs/{job.id}/output/deck.pptx", b"pretend pptx")

    r = await client.delete(f"/api/jobs/{job.id}")
    assert r.status_code == 200

    assert store.get(job.id) is None
    assert blobs.head(f"jobs/{job.id}/output/deck.pptx") is None
    assert blobs.head(shared) is not None  # `other` still references it

    store.delete(other.id)


async def test_delete_refuses_a_running_job(pg_schema, client):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    job.update(status="running")
    r = await client.delete(f"/api/jobs/{job.id}")
    assert r.status_code == 400
    store.delete(job.id)


async def test_stale_heartbeat_sweep_runs_on_get_and_list(pg_schema, client):
    store = jobs.JobStore()
    job = store.create("brief", {}, "claude-opus-5-5")
    job.update(status="running")
    with jobs._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE jobs SET created_at = now() - interval '10 minutes' WHERE id=%s", (job.id,))

    r = await client.get(f"/api/jobs/{job.id}")
    assert r.status_code == 200
    assert r.json()["status"] == "failed"

"""1.4 proof: the JSON create/refine path's server-side checks, and the launcher, against the real API
(ASGI, no mocks), real Neon, real Blob, and (for the sandbox smoke test) the real Vercel Sandbox API.
"""
from __future__ import annotations

import subprocess

import pytest

from app import blobs, config, jobs

pytestmark = pytest.mark.anyio


async def test_create_rejects_wrong_blob_prefix(pg_schema, client):
    r = await client.post("/api/jobs", json={"brief": "x",
        "files": [{"blob": "not-uploads/x.txt", "name": "x.txt", "size": 1}]})
    assert r.status_code == 400


async def test_create_rejects_missing_blob(pg_schema, client):
    r = await client.post("/api/jobs", json={"brief": "x",
        "files": [{"blob": "uploads/none/does-not-exist.txt", "name": "x.txt", "size": 1}]})
    assert r.status_code == 400


async def test_create_rejects_oversize_file(pg_schema, upload_ns, client, monkeypatch):
    path = f"{upload_ns}big.bin"
    blobs.put_bytes(path, b"0" * 1024)
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 100)
    r = await client.post("/api/jobs", json={"brief": "x", "files": [{"blob": path, "name": "big.bin", "size": 1024}]})
    assert r.status_code == 400


async def test_create_rejects_oversize_total(pg_schema, upload_ns, client, monkeypatch):
    a, b = f"{upload_ns}a.bin", f"{upload_ns}b.bin"
    blobs.put_bytes(a, b"0" * 500)
    blobs.put_bytes(b, b"0" * 500)
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 600)
    r = await client.post("/api/jobs", json={"brief": "x",
        "files": [{"blob": a, "name": "a.bin", "size": 500}, {"blob": b, "name": "b.bin", "size": 500}]})
    assert r.status_code == 413


async def test_create_rejects_path_escape(pg_schema, upload_ns, client):
    path = f"{upload_ns}evil.txt"
    blobs.put_bytes(path, b"x")
    r = await client.post("/api/jobs", json={"brief": "x",
        "files": [{"blob": path, "name": "evil.txt", "path": "../../etc/passwd", "size": 1}]})
    assert r.status_code == 400


async def test_create_rejects_empty_body(pg_schema, client):
    r = await client.post("/api/jobs", json={})
    assert r.status_code == 400


async def test_unknown_job_id_is_404_everywhere(pg_schema, client):
    assert (await client.post("/api/jobs/does-not-exist/cancel")).status_code == 404
    assert (await client.post("/api/jobs/does-not-exist/refine", json={"feedback": "change it"})).status_code == 404
    assert (await client.post("/api/jobs/does-not-exist/retry")).status_code == 404
    assert (await client.delete("/api/jobs/does-not-exist")).status_code == 404
    assert (await client.get("/api/jobs/does-not-exist")).status_code == 404


async def test_create_accepts_good_file_and_starts_a_job(pg_schema, upload_ns, client):
    """A real job starts through HTTP: the row lands in Postgres with the checked upload attached.

    DECK_SANDBOX_SNAPSHOT isn't set yet (the build-plane agent is still building that snapshot), so the
    sandbox itself can't be launched here; `_launch` catches that and fails the job instead of the request
    (proved below) - this is NOT the "sandbox exists" proof, see test_sandbox_universal_image_smoke for that.
    """
    path = f"{upload_ns}report.txt"
    blobs.put_bytes(path, b"quarterly numbers")
    r = await client.post("/api/jobs", json={"brief": "Summarize this report",
        "files": [{"blob": path, "name": "report.txt", "role": "content", "size": 18}]})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] and body["root_id"] == body["id"]

    store = jobs.JobStore()
    job = store.get(body["id"])
    assert job is not None
    assert job.data["uploads"][0]["blob"] == path
    assert job.data["uploads"][0]["name"] == "report.txt"
    # no DECK_SANDBOX_SNAPSHOT configured in this environment: _launch's failure handling takes over
    assert config.DECK_SANDBOX_SNAPSHOT is None
    assert job.data["status"] == "failed"
    assert "build machine" in job.data["error"]


@pytest.mark.skipif(not __import__("os").environ.get("VERCEL_OIDC_TOKEN"), reason="no Sandbox credentials here")
async def test_sandbox_universal_image_smoke():
    """Proves the launcher's actual mechanism - create_sandbox, a detached create_command, stop - against
    the real Vercel Sandbox API, using the platform's universal image and a harmless command instead of the
    DECK_SANDBOX_SNAPSHOT code snapshot, which the build-plane agent hasn't published yet."""
    from vercel.sandbox import SandboxResources, create_sandbox, get_sandbox

    name = "deck-test-" + __import__("secrets").token_hex(4)
    sandbox = await create_sandbox(name=name, resources=SandboxResources(vcpus=1), execution_time_limit=120,
                                   persistent=False)
    try:
        result = await sandbox.run_command("echo", ["hello-from-sandbox"], capture_output=True)
        assert result.returncode == 0
        assert "hello-from-sandbox" in (result.stdout or "")
        # the detached form the launcher actually uses
        proc = await sandbox.create_command("echo", ["hello-detached"], stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
        await proc.wait()
    finally:
        found = await get_sandbox(name=name)
        await found.stop()

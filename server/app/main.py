"""HTTP API for amasol Deck Studio: a thin control plane (a Vercel Function). State lives in Postgres and
Blob; the build runs in a Vercel Sandbox, one per job (see Contracts in PLAN.md). This process never runs the
pipeline itself, so there are no background threads here beyond FastAPI's own per-request pool."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import blobs, config, jobs, launcher
from .ingest import safe_rel

app = FastAPI(title="amasol Deck Studio", docs_url=None, redoc_url=None)
store = jobs.JobStore()

ALLOWED_OPTIONS = {"language", "length", "format", "audience", "goal", "presenter", "instructions", "review"}
BRIEF_MAX = 2_000_000           # a chat message can hold whole meeting notes or an outline
FEEDBACK_INLINE_MAX = 20_000     # longer change requests are saved as a blob next to the uploads


def _clean_options(raw) -> dict:
    o = {k: v for k, v in (raw if isinstance(raw, dict) else {}).items() if k in ALLOWED_OPTIONS}
    if o.get("language") not in ("en", "de"):
        o.pop("language", None)
    if o.get("format") not in ("short", "full"):
        o.pop("format", None)
    try:
        n = int(o.get("length") or 0)
        o["length"] = n if 1 <= n <= 40 else None
    except (TypeError, ValueError):
        o["length"] = None
    if not o.get("length"):
        o.pop("length", None)
    for k in ("audience", "goal", "presenter", "instructions"):
        v = " ".join(str(o.get(k) or "").split())[:600]
        if v:
            o[k] = v
        else:
            o.pop(k, None)
    o["review"] = bool(o.get("review", True))
    return o


def _model(m: str | None) -> str:
    ids = [x["id"] for x in config.MODELS]
    return m if m in ids else config.DEFAULT_MODEL


async def _launch(job: jobs.Job) -> None:
    """Starts the job's sandbox; a launch failure fails the job instead of the request, so the client
    (already told {id, root_id}) sees it the same way it sees any other build failure."""
    try:
        await run_in_threadpool(store.set_sandbox_live, job.id, True)   # before create: a half-made sandbox still gets swept
        await launcher.launch(job.id)
    except Exception as e:  # noqa: BLE001 - any sandbox-start problem becomes this job's failure
        await run_in_threadpool(job.update, status="failed", error=f"Could not start the build machine: {e}")


async def _stop(jid: str) -> None:
    """Stop the job's sandbox and record that it is gone. Idempotent: a missing sandbox is fine."""
    await launcher.stop(jid)
    await run_in_threadpool(store.set_sandbox_live, jid, False)


def _job_or_404(jid: str) -> jobs.Job:
    job = store.get(jid)
    if not job:
        raise HTTPException(404, "No such job")
    return job


@app.get("/api/config")
def get_config():
    return {"models": config.MODELS, "default_model": config.DEFAULT_MODEL,
            "limits": {"file_mb": config.MAX_FILE_BYTES // 2**20, "total_mb": config.MAX_UPLOAD_BYTES // 2**20,
                       "files": config.MAX_FILES}}


@app.get("/api/jobs")
def list_jobs():
    store.sweep_stale()
    return store.list()


async def _read_json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body must be JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    return body


def _check_files(raw_files) -> list[dict]:
    """Re-checks every file the client says it already put in Blob: path via safe_rel, blob prefix
    'uploads/', blob exists (head), size <= MAX_FILE_BYTES, count <= MAX_FILES, total <= MAX_UPLOAD_BYTES."""
    if raw_files is None:
        raw_files = []
    if not isinstance(raw_files, list):
        raise HTTPException(400, "files must be a list")
    if len(raw_files) > config.MAX_FILES:
        raise HTTPException(400, f"Too many files (limit {config.MAX_FILES})")
    out, total, used = [], 0, set()
    for f in raw_files:
        if not isinstance(f, dict):
            raise HTTPException(400, "Each file must be an object")
        blob_path = str(f.get("blob") or "")
        name = str(f.get("name") or "")
        if not blob_path.startswith("uploads/"):
            raise HTTPException(400, f"Bad upload reference: {blob_path!r}")
        meta = blobs.head(blob_path)
        if meta is None:
            raise HTTPException(400, f"Upload not found: {name or blob_path}")
        size = meta.size
        if size > config.MAX_FILE_BYTES:
            raise HTTPException(400, f"{name or blob_path}: larger than {config.MAX_FILE_BYTES // 2**20} MB")
        total += size
        if total > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Upload too large (limit {config.MAX_UPLOAD_BYTES // 2**20} MB)")
        role = str(f.get("role") or "auto")
        if role not in ("content", "reference", "auto"):
            role = "auto"
        raw_path = str(f.get("path") or name or "file").replace("\\", "/")
        if raw_path.startswith("/") or any(part == ".." for part in raw_path.split("/")):
            raise HTTPException(400, f"Bad file path: {raw_path!r}")
        rel = safe_rel(raw_path)
        while rel in used:
            p = Path(rel)
            rel = str(p.with_name(f"{p.stem}-{len(used)}{p.suffix}"))
        used.add(rel)
        out.append({"name": rel, "saved": f"inputs/{rel}", "role": role, "blob": blob_path, "size": size})
    return out


@app.post("/api/jobs")
async def create_job(request: Request):
    body = await _read_json(request)
    brief = str(body.get("brief") or "").strip()[:BRIEF_MAX]
    content = str(body.get("content") or "")[:BRIEF_MAX]
    options = _clean_options(body.get("options"))
    model = _model(body.get("model"))
    uploads = await run_in_threadpool(_check_files, body.get("files"))
    if not brief and not content.strip() and not uploads:
        raise HTTPException(400, "Write a message or attach files")
    job = await run_in_threadpool(store.create, brief, options, model)
    await run_in_threadpool(job.update, uploads=uploads, content=content,
                            files=[{"name": u["name"], "role": u["role"], "bytes": u["size"]} for u in uploads])
    await _launch(job)
    return {"id": job.id, "root_id": job.data["root_id"]}


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    store.sweep_stale()
    job = _job_or_404(jid)
    d = job.public()
    d.pop("content", None)
    d.pop("uploads", None)
    d["brief_chars"] = len(d.get("brief") or "")
    if d["brief_chars"] > 8000:
        d["brief"] = d["brief"][:8000]
    d["content_chars"] = len(job.data.get("content") or "")
    return d


@app.get("/api/jobs/{jid}/events")
async def job_events(jid: str, request: Request, after: int = 0):
    if not await run_in_threadpool(store.exists, jid):
        raise HTTPException(404, "No such job")

    async def gen():
        sent = after
        idle = 0
        deadline = time.monotonic() + 300  # close after <=5 min; the client reconnects with ?after=N
        while True:
            if await request.is_disconnected():
                return
            evs, status = await run_in_threadpool(store.events_after, jid, sent)
            for ev in evs:
                yield f"id: {ev['seq']}\nevent: message\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            sent += len(evs)
            if status in jobs.TERMINAL:
                yield "event: end\ndata: {}\n\n"   # its sandbox is stopped by /api/internal/sweep
                return
            if time.monotonic() > deadline:
                return
            idle = 0 if evs else idle + 1
            if idle and idle % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/jobs/{jid}/cancel")
async def cancel_job(jid: str):
    await run_in_threadpool(_job_or_404, jid)
    if await run_in_threadpool(store.cancel, jid):
        await _stop(jid)
    return {"ok": True}


@app.post("/api/jobs/{jid}/refine")
async def refine_job(jid: str, request: Request):
    """A follow-up message in a deck's thread: builds the next version from this (finished) one."""
    parent = await run_in_threadpool(_job_or_404, jid)
    if parent.data["status"] != "done":
        raise HTTPException(400, "Only a finished deck can be revised")
    body = await _read_json(request)
    feedback = str(body.get("feedback") or "").strip()
    uploads = await run_in_threadpool(_check_files, body.get("files"))
    if len(feedback) < 3 and not uploads:
        raise HTTPException(400, "Describe the change you want")
    if not feedback:
        feedback = "Use the attached files: add what they contain to the deck where it fits."
    opts = dict(parent.data.get("options") or {})
    long_text = feedback if len(feedback) > FEEDBACK_INLINE_MAX else None
    if long_text:
        feedback = "Apply the change described in the attached file message.txt (the user's full message)."
    job = await run_in_threadpool(store.create, parent.data.get("brief", ""), opts,
                                  _model(body.get("model") or parent.data.get("model")), parent,
                                  feedback[:FEEDBACK_INLINE_MAX])
    if long_text:
        # the user's full message, too long to keep inline in job data: a blob the worker downloads like
        # any other upload (same uploads[] mechanism, just a server-written file instead of a browser one)
        blob_path = f"jobs/{job.id}/message.txt"
        data = long_text[:BRIEF_MAX].encode("utf-8")
        await run_in_threadpool(blobs.put_bytes, blob_path, data)
        uploads.append({"name": "message.txt", "saved": "inputs/message.txt", "role": "content",
                       "blob": blob_path, "size": len(data)})
    await run_in_threadpool(job.update, uploads=uploads,
                            files=[{"name": u["name"], "role": u["role"], "bytes": u["size"]} for u in uploads])
    await _launch(job)
    return {"id": job.id, "root_id": job.data["root_id"]}


@app.post("/api/jobs/{jid}/retry")
async def retry_job(jid: str):
    old = await run_in_threadpool(_job_or_404, jid)
    if old.data["status"] in ("queued", "running"):
        raise HTTPException(400, "This job is still running")
    if old.data.get("parent_id"):
        parent = await run_in_threadpool(_job_or_404, old.data["parent_id"])
        job = await run_in_threadpool(store.create, old.data.get("brief", ""), old.data.get("options") or {},
                                      old.data.get("model"), parent, old.data.get("feedback"))
        await run_in_threadpool(job.update, files=old.data.get("files", []), uploads=old.data.get("uploads", []))
    else:
        job = await run_in_threadpool(store.create, old.data.get("brief", ""), old.data.get("options") or {},
                                      old.data.get("model"))
        await run_in_threadpool(job.update, uploads=old.data.get("uploads", []), content=old.data.get("content", ""),
                                warnings=[w for w in old.data.get("warnings", []) if "larger than" in w])
    await _launch(job)
    return {"id": job.id, "root_id": job.data["root_id"]}


def _delete_blobs_and_row(jid: str, uploads: list[dict]) -> None:
    """The deletion rule: jobs/<id>/ goes, plus every upload blob no other job's data.uploads references."""
    my_blobs = {u["blob"] for u in uploads if u.get("blob")}
    referenced = store.upload_blobs_referenced_elsewhere(jid)
    orphan = [b for b in my_blobs if b not in referenced]
    if orphan:
        blobs.delete(orphan)
    blobs.delete_prefix(f"jobs/{jid}/")
    store.delete(jid)


@app.delete("/api/jobs/{jid}")
async def delete_job(jid: str):
    job = await run_in_threadpool(_job_or_404, jid)
    if job.data["status"] in ("queued", "running"):
        raise HTTPException(400, "Cancel the job first")
    await launcher.stop(jid)
    await run_in_threadpool(_delete_blobs_and_row, jid, job.data.get("uploads") or [])
    return {"ok": True}


@app.get("/api/jobs/{jid}/draft")
def get_draft(jid: str):
    found, draft = store.get_draft(jid)
    if not found:
        raise HTTPException(404, "No such job")
    if draft is None:
        raise HTTPException(404, "No draft yet")
    return PlainTextResponse(draft)


@app.get("/api/jobs/{jid}/file/{path:path}")
async def get_file(jid: str, path: str, download: int = 0):
    if not await run_in_threadpool(store.exists, jid):
        raise HTTPException(404, "No such job")
    rel = safe_rel(path)  # relative to the job, as result.slides/pptx/pdf list it: "output/slides/slide-01.jpg"
    if not rel.startswith("output/"):  # only the job's outputs are served, never its work state
        raise HTTPException(404, "No such file")
    target = f"jobs/{jid}/{rel}"
    meta = await run_in_threadpool(blobs.head, target)
    if meta is None:
        raise HTTPException(404, "No such file")
    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{Path(target).name}"'

    def body():
        with blobs.stream(target) as chunks:
            yield from chunks

    return StreamingResponse(body(), media_type=meta.content_type or "application/octet-stream", headers=headers)


@app.get("/api/internal/sweep")
async def sweep(request: Request):
    """Vercel Cron, every minute (vercel.json). A sandbox can't end itself, so this is what stops it: jobs whose
    heartbeat went quiet become failed, then every finished job's sandbox is stopped. Safe to run twice."""
    secret = os.environ.get("CRON_SECRET")
    if not secret or request.headers.get("authorization") != f"Bearer {secret}":
        raise HTTPException(401, "Unauthorized")
    await run_in_threadpool(store.sweep_stale)
    ids = await run_in_threadpool(store.sandboxes_to_stop)
    for jid in ids:
        await _stop(jid)
    return {"stopped": len(ids)}


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

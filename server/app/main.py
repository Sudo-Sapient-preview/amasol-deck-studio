"""HTTP API and static web app for amasol Deck Studio."""
from __future__ import annotations

import asyncio
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile

from . import config
from .ingest import safe_rel
from .jobs import JobStore
from .pipeline import Runner

app = FastAPI(title="amasol Deck Studio", docs_url=None, redoc_url=None)
# The Vercel-hosted UI sends uploads straight here (Vercel's proxy drops request bodies over a few MB).
app.add_middleware(CORSMiddleware, allow_origin_regex=r"https://amasol-deck-studio(-[a-z0-9-]+)?\.vercel\.app",
                   allow_methods=["GET", "POST"], allow_headers=["*"], max_age=86400)
store = JobStore()
pool = ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_JOBS, thread_name_prefix="deck")

ALLOWED_OPTIONS = {"language", "length", "format", "audience", "goal", "presenter", "instructions", "review"}


def _clean_options(raw: dict) -> dict:
    o = {k: v for k, v in (raw or {}).items() if k in ALLOWED_OPTIONS}
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


def _start(job):
    pool.submit(Runner(job).run)


@app.get("/api/config")
def get_config():
    return {"models": config.MODELS, "default_model": config.DEFAULT_MODEL,
            "limits": {"file_mb": config.MAX_FILE_BYTES // 2**20, "total_mb": config.MAX_UPLOAD_BYTES // 2**20,
                       "files": config.MAX_FILES}}


@app.get("/api/jobs")
def list_jobs():
    return store.list()


BRIEF_MAX = 2_000_000           # a chat message can hold whole meeting notes or an outline
FEEDBACK_INLINE_MAX = 20_000     # longer change requests are saved as a file next to the uploads


async def _read_form(request: Request):
    clen = int(request.headers.get("content-length") or 0)
    if clen > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Upload too large (limit {config.MAX_UPLOAD_BYTES // 2**20} MB)")
    form = await request.form(max_files=config.MAX_FILES + 5, max_fields=config.MAX_FILES * 3 + 20,
                              max_part_size=BRIEF_MAX * 4)
    files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    if len(files) > config.MAX_FILES:
        raise HTTPException(400, f"Too many files (limit {config.MAX_FILES})")
    return form, files


async def _save_uploads(job, form, files) -> list[dict]:
    paths = [str(p) for p in form.getlist("paths")]
    roles = [str(r) for r in form.getlist("roles")]
    uploads, used = [], set()
    for k, f in enumerate(files):
        rel = safe_rel(paths[k] if k < len(paths) and paths[k] else (f.filename or f"file-{k}"))
        while rel in used:
            p = Path(rel)
            rel = str(p.with_name(f"{p.stem}-{k}{p.suffix}"))
        used.add(rel)
        dest = job.work / "inputs" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with open(dest, "wb") as out:
            while chunk := await f.read(1 << 20):
                size += len(chunk)
                if size > config.MAX_FILE_BYTES:
                    break
                out.write(chunk)
        if size > config.MAX_FILE_BYTES:
            dest.unlink(missing_ok=True)
            job.data.setdefault("warnings", []).append(
                f"{rel}: larger than {config.MAX_FILE_BYTES // 2**20} MB, skipped")
            continue
        role = roles[k] if k < len(roles) and roles[k] in ("content", "reference", "auto") else "auto"
        uploads.append({"name": rel, "saved": f"inputs/{rel}", "role": role})
    return uploads


@app.post("/api/jobs")
async def create_job(request: Request):
    form, files = await _read_form(request)
    brief = str(form.get("brief") or "").strip()[:BRIEF_MAX]
    content = str(form.get("content") or "")[:BRIEF_MAX]
    try:
        options = _clean_options(json.loads(str(form.get("options") or "{}")))
    except json.JSONDecodeError:
        raise HTTPException(400, "options must be JSON")
    if not brief and not content.strip() and not files:
        raise HTTPException(400, "Write a message or attach files")
    job = store.create(brief, options, _model(str(form.get("model") or "")))
    uploads = await _save_uploads(job, form, files)
    job.update(uploads=uploads, content=content)
    _start(job)
    return {"id": job.id, "root_id": job.data["root_id"]}


def _job_or_404(jid: str):
    job = store.get(jid)
    if not job:
        raise HTTPException(404, "No such job")
    return job


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
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
    job = _job_or_404(jid)

    async def gen():
        sent = after
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            evs = job.events[sent:]
            for ev in evs:
                yield f"id: {ev['seq']}\nevent: message\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            sent += len(evs)
            if job.data.get("status") in ("done", "failed", "cancelled") and sent >= len(job.events):
                yield "event: end\ndata: {}\n\n"
                return
            idle = 0 if evs else idle + 1
            if idle and idle % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: str):
    job = _job_or_404(jid)
    if job.data["status"] in ("queued", "running"):
        job.cancel_requested = True
        if job.data["status"] == "queued":
            job.update(status="cancelled")
            job.emit("status", status="cancelled")
    return {"ok": True}


@app.post("/api/jobs/{jid}/refine")
async def refine_job(jid: str, request: Request):
    """A follow-up message in a deck's thread: builds the next version from this (finished) one. Accepts JSON
    {feedback} or multipart (feedback, files, paths, roles) so a follow-up can bring new files."""
    parent = _job_or_404(jid)
    if parent.data["status"] != "done":
        raise HTTPException(400, "Only a finished deck can be revised")
    files, form = [], None
    if (request.headers.get("content-type") or "").startswith("multipart/"):
        form, files = await _read_form(request)
        body = {k: form.get(k) for k in ("feedback", "model")}
    else:
        body = await request.json()
    feedback = str(body.get("feedback") or "").strip()
    if len(feedback) < 3 and not files:
        raise HTTPException(400, "Describe the change you want")
    if not feedback:
        feedback = "Use the attached files: add what they contain to the deck where it fits."
    opts = dict(parent.data.get("options") or {})
    long_text = feedback if len(feedback) > FEEDBACK_INLINE_MAX else None
    if long_text:
        feedback = "Apply the change described in the attached file message.txt (the user's full message)."
    job = store.create(parent.data.get("brief", ""), opts, _model(body.get("model") or parent.data.get("model")),
                       parent=parent, feedback=feedback[:FEEDBACK_INLINE_MAX])
    uploads = await _save_uploads(job, form, files) if form is not None else []
    if long_text:
        dest = job.work / "inputs" / "message.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(long_text[:BRIEF_MAX], encoding="utf-8")
        uploads.append({"name": "message.txt", "saved": "inputs/message.txt", "role": "content"})
    job.update(files=[{"name": u["name"], "role": u["role"], "bytes": (job.work / u["saved"]).stat().st_size}
                      for u in uploads], uploads=uploads)
    _start(job)
    return {"id": job.id, "root_id": job.data["root_id"]}


@app.post("/api/jobs/{jid}/retry")
def retry_job(jid: str):
    old = _job_or_404(jid)
    if old.data["status"] in ("queued", "running"):
        raise HTTPException(400, "This job is still running")
    if old.data.get("parent_id"):
        parent = _job_or_404(old.data["parent_id"])
        job = store.create(old.data.get("brief", ""), old.data.get("options") or {}, old.data.get("model"),
                           parent=parent, feedback=old.data.get("feedback"))
        if (old.work / "inputs").exists():
            shutil.copytree(old.work / "inputs", job.work / "inputs", dirs_exist_ok=True)
        job.update(files=old.data.get("files", []), uploads=old.data.get("uploads", []))
    else:
        job = store.create(old.data.get("brief", ""), old.data.get("options") or {}, old.data.get("model"))
        if (old.work / "inputs").exists():
            shutil.copytree(old.work / "inputs", job.work / "inputs", dirs_exist_ok=True)
        job.update(uploads=old.data.get("uploads", []), content=old.data.get("content", ""),
                   warnings=[w for w in old.data.get("warnings", []) if "larger than" in w])
    _start(job)
    return {"id": job.id, "root_id": job.data["root_id"]}


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str):
    job = _job_or_404(jid)
    if job.data["status"] in ("queued", "running"):
        raise HTTPException(400, "Cancel the job first")
    with store.lock:
        store.jobs.pop(jid, None)
    shutil.rmtree(job.dir, ignore_errors=True)
    return {"ok": True}


@app.get("/api/jobs/{jid}/draft")
def get_draft(jid: str):
    job = _job_or_404(jid)
    p = job.work / "draft.md"
    if not p.exists():
        raise HTTPException(404, "No draft yet")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@app.get("/api/jobs/{jid}/file/{path:path}")
def get_file(jid: str, path: str, download: int = 0):
    job = _job_or_404(jid)
    base = (job.dir / "output").resolve()
    target = (job.dir / path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(404, "No such file")
    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        return FileResponse(target, filename=target.name, headers=headers)
    return FileResponse(target, headers=headers)


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


# ---------------------------------------------------------------------------- web app
if config.WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.WEB_DIST / "assets"), name="assets")

    @app.get("/{full:path}")
    def spa(full: str):
        if full.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (config.WEB_DIST / full).resolve()
        if full and f.is_relative_to(config.WEB_DIST.resolve()) and f.is_file():
            return FileResponse(f)
        return FileResponse(config.WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})

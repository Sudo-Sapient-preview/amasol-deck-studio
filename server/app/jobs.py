"""Job state and event log, persisted under data/jobs/<id>/ (job.json + events.jsonl)."""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path

from . import config

STAGES = [
    ("ingest", "Read inputs"),
    ("draft", "Storyline"),
    ("plan", "Visuals and layouts"),
    ("build", "Build and verify"),
    ("review", "Visual review"),
]


class Job:
    def __init__(self, data: dict):
        self.data = data
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.events: list[dict] = []
        self.cancel_requested = False

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
        tmp = self.dir / "job.json.tmp"
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.dir / "job.json")

    def emit(self, type_: str, **kw):
        with self.cond:
            ev = {"seq": len(self.events) + 1, "t": time.time(), "type": type_, **kw}
            self.events.append(ev)
            with open(self.dir / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self.data["updated_at"] = ev["t"]
            self.cond.notify_all()
        return ev

    def update(self, **kw):
        with self.cond:
            self.data.update(kw)
            self.data["updated_at"] = time.time()
            self.save()
            self.cond.notify_all()

    def stage(self, key: str, status: str, summary: str | None = None):
        with self.cond:
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


class JobStore:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        for jf in sorted(config.JOBS_DIR.glob("*/job.json")):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            job = Job(data)
            ev = jf.parent / "events.jsonl"
            if ev.exists():
                for line in ev.read_text(encoding="utf-8").splitlines():
                    try:
                        job.events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            if data.get("status") in ("queued", "running"):
                data["status"] = "failed"
                data["error"] = "The server restarted while this deck was being built. Run it again."
                for s in data.get("stages", []):
                    if s.get("status") == "running":
                        s["status"] = "failed"
                job.save()
            self.jobs[job.id] = job

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
        job = Job(data)
        job.dir.mkdir(parents=True, exist_ok=True)
        job.work.mkdir(parents=True, exist_ok=True)
        job.save()
        with self.lock:
            self.jobs[jid] = job
        return job

    def get(self, jid: str) -> Job | None:
        return self.jobs.get(jid)

    def list(self) -> list[dict]:
        out = []
        for j in sorted(self.jobs.values(), key=lambda j: j.data["created_at"], reverse=True):
            d = j.data
            out.append({k: d.get(k) for k in ("id", "created_at", "status", "title", "version", "root_id",
                                              "parent_id", "model")} |
                       {"slides": (d.get("result") or {}).get("slide_count"),
                        "snippet": " ".join((d.get("feedback") or d.get("brief") or "").split())[:140]})
        return out


def _title_guess(brief: str) -> str:
    b = " ".join((brief or "").split())
    return (b[:70] + "…") if len(b) > 70 else (b or "Untitled deck")

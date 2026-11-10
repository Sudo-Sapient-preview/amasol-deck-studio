"""One deck job: ingest -> draft -> plan -> build -> review -> outputs. Each LLM stage is a tool loop whose end
is checked by a gate the pipeline runs itself (the skill's scripts), so a stage cannot claim success."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import traceback
from pathlib import Path

import anthropic

from . import config, prompts
from .ingest import Source, ingest, slug
from .webfetch import fetch_site, find_urls
from .jobs import Job
from .llm import Agent, Cancelled, StageFailed, Usage, make_client
from .report import build_report
from .tools import ToolError, Workspace

GOOD_FILES = ("draft.md", "plan.json", "spec.json", "match.json", "out.pptx", "verify.txt")
OVERRIDES = "overrides.json"   # user-requested text emphasis, applied after verify (see runner/apply_overrides.py)
LONG_MESSAGE = 1500     # a chat message longer than this is content (notes, an outline), stored as the source "Message"


def make_hd_slides(pdf: Path, outdir: Path, width: int = 2400) -> list[Path]:
    """Sharp slide images for the in-app viewer, rasterised straight from the deck PDF (the skill's render is
    110 dpi, about 1100 px wide; fine for thumbnails, soft on large or high-density screens)."""
    hd = outdir / "hd"
    if hd.exists():
        shutil.rmtree(hd)
    hd.mkdir(parents=True)
    try:
        subprocess.run(["pdftoppm", "-jpeg", "-jpegopt", "quality=88", "-scale-to-x", str(width), "-scale-to-y", "-1",
                        str(pdf), str(hd / "slide")], capture_output=True, timeout=300, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for k, f in enumerate(sorted(hd.glob("slide-*.jpg"), key=lambda p: int(re.findall(r"(\d+)", p.stem)[-1])), 1):
        target = hd / f"slide-{k:02d}.jpg"
        if f != target:
            f.rename(target)
        out.append(target)
    return out


def _first_line(out: str, *keys: str) -> str:
    """The most telling line of a script output: the first line matching the earliest key in `keys`."""
    lines = out.splitlines()
    for k in keys:
        for line in lines:
            if k in line:
                return " ".join(line.split())
    return ""


class Runner:
    def __init__(self, job: Job, on_done: callable = None):
        self.job = job
        self.work = job.work
        self.on_done = on_done   # called (no args) once the deck is built, before the terminal status is written
        self.usage = Usage()
        self.ws = Workspace(self.work)
        self.summaries: dict[str, str] = {}
        self.warnings: list[str] = list(job.data.get("warnings") or [])
        self.refine = job.data.get("feedback")
        self.ingested = None
        self.prompt_brief = job.data.get("brief", "")

    # ------------------------------------------------------------------ logging
    def log(self, kind: str, text: str):
        self.job.emit("log", kind=kind, text=text[:600])

    def cancelled(self) -> bool:
        return self.job.cancel_requested

    # ------------------------------------------------------------------ tool handler with gates
    def save_good(self):
        g = self.work / "good"
        g.mkdir(exist_ok=True)
        for f in GOOD_FILES:
            if (self.work / f).exists():
                shutil.copy2(self.work / f, g / f)

    def restore_good(self) -> bool:
        g = self.work / "good"
        if not (g / "out.pptx").exists():
            return False
        for f in GOOD_FILES:
            if (g / f).exists():
                shutil.copy2(g / f, self.work / f)
        for k in self.ws.versions:
            self.ws.versions[k] += 1
        snap = self.ws.full_snapshot()
        self.ws.state.update(match_of=snap[:2], built_of=snap, verified=snap)
        return True

    def handler(self, gate):
        ws = self.ws

        def handle(name: str, inp: dict):
            if name == "read_file":
                self.log("tool", f"Reading {inp.get('path', '')}")
                return ws.read_file(inp["path"], int(inp.get("offset") or 0), int(inp.get("limit") or 0))
            if name == "write_file":
                r = ws.write_file(inp["path"], inp["content"])
                self.log("tool", r[0].upper() + r[1:])
                return r
            if name == "edit_file":
                r = ws.edit_file(inp["path"], inp["old_string"], inp["new_string"], bool(inp.get("replace_all")))
                self.log("tool", r[0].upper() + r[1:])
                return r
            if name == "check_draft":
                ok, out = ws.check_draft(bool(inp.get("autofix")))
                self.log("ok" if ok else "warn", "Draft check: " + ("passed" if ok else
                         _first_line(out, "FAIL", "TOOL CHECK") or "needs fixes"))
                return out
            if name == "draftgen":
                out = ws.draftgen(inp["mode"])
                self.log("tool", f"Ran draftgen {inp['mode']}")
                return out
            if name == "check_plan":
                ok, out = ws.check_plan()
                n = len(re.findall(r"^\s*\d+ content ", out, re.M))
                self.log("ok" if ok else "warn", f"Plan and layouts: passed, {n} content slides placed" if ok else
                         "Plan and layouts: " + (_first_line(out, "FAIL", "problem") or "needs fixes"))
                return out
            if name == "build_deck":
                ok, out = ws.build_deck()
                if ok:
                    self.save_good()
                    self.log("ok", "Build and verify: " + (_first_line(out, "passed ·") or "RESULT: PASS"))
                else:
                    self.log("warn", "Build and verify: " + (_first_line(out, "GUIDE ERROR", "SPEC ERROR",
                             "BUILD ERROR", "FAIL ", "RESULT") or "needs fixes")[:300])
                return out
            if name == "render_preview":
                ok, out = ws.render_preview()
                self.log("ok" if ok else "warn", f"Rendered preview ({ws.state['render_dir']})" if ok else
                         "Render failed")
                return out
            if name == "view_images":
                paths = inp.get("paths") or []
                self.log("tool", "Looking at " + ", ".join(Path(p).name for p in paths[:6]))
                return ws.view_images(paths)
            if name == "finish_stage":
                ok, why = gate()
                if not ok:
                    self.log("warn", "Stage gate not met yet, continuing")
                    raise ToolError("Gate not met, the stage is not finished: " + why)
                return ("finished", inp.get("summary", ""))
            raise ToolError(f"unknown tool {name}")
        return handle

    def gate_draft(self):
        ok, out = self.ws.check_draft(False)
        return ok, out

    def gate_plan(self):
        return self.ws.check_plan()

    def gate_build(self):
        snap = self.ws.full_snapshot()
        if self.ws.state["verified"] == snap:
            return True, ""
        return False, ("build_deck has not passed for the current draft.md, plan.json and spec.json - run "
                       "build_deck until RESULT: PASS")

    def gate_review(self):
        ok, why = self.gate_build()
        if not ok:
            return ok, why
        if self.ws.state["rendered_of"] != self.ws.full_snapshot():
            return False, "the current build has not been rendered - run render_preview and look at the slides"
        return True, ""

    # ------------------------------------------------------------------ stages
    def stage(self, key: str, fn):
        self.job.stage(key, "running")
        try:
            summary = fn()
        except Exception:
            self.job.stage(key, "failed")
            raise
        self.summaries[key] = summary or ""
        self.job.stage(key, "done", summary)
        self.job.update(usage=self.usage.as_dict())
        return summary

    def agent(self, effort: str = "high") -> Agent:
        return Agent(client=self.client, model=self.job.data["model"], system=prompts.system_prompt(),
                     usage=self.usage, log=self.log, cancelled=self.cancelled, effort=effort)

    def do_ingest(self) -> str:
        j = self.job.data
        uploads = [(u["name"], self.work / u["saved"], u["role"]) for u in j.get("uploads", [])]
        brief = j.get("brief", "").strip()
        pasted = j.get("content", "")
        long_msg = len(brief) > LONG_MESSAGE and not pasted.strip()
        res = ingest(self.work, uploads, brief if long_msg else pasted, "Message" if long_msg else "Pasted content")
        self.fetch_links(brief + "\n" + pasted, res)
        self.prompt_brief = ("(The user's message is long, so it is stored as the source named \"Message\" below. "
                             "It holds both the request and the content: take the request from it.)") if long_msg else brief
        self.warnings += res.warnings
        for w in res.warnings:
            self.log("warn", w)
        self.ingested = res
        self.job.update(files=res.files, warnings=self.warnings,
                        internal={"sources": [s.__dict__ for s in res.sources],
                                  "images": [i.__dict__ for i in res.images]})
        if not res.sources and not brief:
            if res.images:
                brief = self.prompt_brief = "Build a deck from the attached images."
            else:
                raise StageFailed("Nothing to build from: no brief and no readable content in the uploads.")
        (self.work / "request.txt").write_text(brief + "\n", encoding="utf-8")
        args = [self.ws.script("intake.py"), "classify", *[str(self.work / s.path) for s in res.sources]]
        if brief and not long_msg:
            args += ["--text", brief]
        args += ["--out", str(self.work)]
        code, out = self.ws.run(args)
        if code != 0 or not (self.work / "intake.json").exists():
            raise StageFailed("Input classification failed: " + out[-800:])
        raw = (self.work / "intake.json").read_text(encoding="utf-8")
        (self.work / "intake.json").write_text(raw.replace(str(self.work) + "/", "work/"), encoding="utf-8")
        self.intake = json.loads((self.work / "intake.json").read_text(encoding="utf-8"))
        t = self.intake["type"]
        kind = {"structured": "a slide outline", "raw": "notes and documents", "bare": "a short brief"}.get(t, t)
        n_files = len([f for f in res.files])
        self.log("info", f"Read {n_files} file(s) and your message. Working from {kind}." if n_files
                 else f"Read your message. Working from {kind}.")
        self.log("tool", f"Intake: {t}. {self.intake.get('reason', '')}"[:400])
        # starting draft from the skill's own generator
        self.starter = "No starting draft: write work/draft.md from scratch by mapping the input field by field."
        draft = str(self.work / "draft.md")
        if t == "raw" and res.sources:
            src = self.work / res.sources[0].path
            if len(res.sources) > 1:
                src = self.work / "combined-sources.txt"
                src.write_text("\n\n".join(f"# Source: {s.name}\n\n" + (self.work / s.path).read_text(encoding="utf-8")
                                           for s in res.sources), encoding="utf-8")
            code, out = self.ws.run([self.ws.script("draftgen.py"), "raw", str(src), "--intake",
                                     str(self.work / "intake.json"), "-o", draft])
            if code == 0 and Path(draft).exists():
                self.starter = ("work/draft.md holds the draftgen raw output: facts grouped by keyword rules, "
                                "headlines are just the first fact and flagged to-be-filled. Treat it as raw "
                                "material: regroup, rewrite headlines as claims, fix buckets, then check.")
        elif t == "bare":
            args = [self.ws.script("draftgen.py"), "bare", "--text", brief or "a deck", "-o", draft]
            if j.get("options", {}).get("length"):
                args += ["--count", str(j["options"]["length"])]
            code, out = self.ws.run(args)
            if code == 0 and Path(draft).exists():
                self.starter = ("work/draft.md holds the draftgen bare skeleton (slide count, title, storyline "
                                "slots). Replace every slot with real generated content flagged assumption.")
        if Path(draft).exists():
            self.ws.bump("draft.md")
        n_chars = sum(s.chars for s in res.sources)
        parts = [f"{len(res.sources)} text source(s), {n_chars:,} characters"]
        if res.images:
            parts.append(f"{len(res.images)} image(s)")
        return f"{'; '.join(parts)}. Classified as {t}."

    def fetch_links(self, text: str, res):
        """Websites linked in the message become text sources (public addresses only)."""
        for url in find_urls(text):
            self.log("info", f"Reading {url}")
            body, notes = fetch_site(url)
            for n in notes:
                self.log("warn", n)
            self.warnings += notes
            k = len(list((self.work / "sources").glob("*.txt"))) + 1
            host = url.split("//", 1)[-1].split("/", 1)[0]
            fn = f"{k:02d}-website-{slug(host)}.txt"
            (self.work / "sources" / fn).write_text(body, encoding="utf-8")
            res.sources.append(Source(name=f"Website: {url}", path=f"sources/{fn}", chars=len(body), kind="web"))

    def sources_block(self) -> str:
        srcs = self.ingested.sources
        if not srcs:
            return "## Sources\nNo uploaded or pasted content: the brief is the only input.\n"
        total = sum(s.chars for s in srcs)
        out = [f"## Sources ({len(srcs)} file(s), {total:,} characters, converted to text in work/sources/)"]
        if total <= config.INLINE_SOURCE_CHARS:
            for s in srcs:
                text = (self.work / s.path).read_text(encoding="utf-8")
                out.append(f"<source name=\"{s.name}\" path=\"work/{s.path}\">\n{text}\n</source>")
        else:
            out.append("The sources are too long to show here. Read every one in full with read_file "
                       "(offset/limit in lines) before writing the draft; do not skip parts.")
            for s in srcs:
                text = (self.work / s.path).read_text(encoding="utf-8")
                out.append(f"- work/{s.path} - {s.name} ({s.chars:,} chars, {len(text.splitlines())} lines). "
                           f"Starts: {text[:400]!r}")
        return "\n".join(out) + "\n"

    def image_blocks(self) -> tuple[list[dict], str]:
        import base64
        imgs = self.ingested.images[: config.MAX_REFERENCE_IMAGES]
        if not imgs:
            return [], ""
        blocks, names = [], []
        for im in imgs:
            label = {"reference": "Design reference", "content": "Content image"}.get(im.role, "Uploaded image")
            blocks.append({"type": "text", "text": f"{label}: {im.name} (work/{im.path})"})
            data = base64.standard_b64encode((self.work / im.path).read_bytes()).decode()
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
            names.append(f"{label}: {im.name}")
        note = ("## Images\nThe images above were uploaded. Content images carry facts (read them like a source and "
                "cite their file name). Design references only hint at structure and visual choices; the amasol "
                "guide decides the look. For an uploaded image without a label, decide from what it shows: a photo "
                "of notes, a chart or a table is content; a slide or layout example is a design reference.\n"
                + "\n".join("- " + n for n in names) + "\n")
        return blocks, note

    def do_draft(self) -> str:
        today = time.strftime("%d %B %Y")
        if self.refine:
            n = len(list((self.work / "sources").glob("*.txt"))) if (self.work / "sources").exists() else 0
            added, blocks = "", []
            if self.ingested and (self.ingested.sources or self.ingested.images):
                blocks, note = self.image_blocks()
                added = ("## Files the user added with this change request\n"
                         + (self.sources_block() if self.ingested.sources else "") + note)
            original = self.job.data.get("brief", "")
            if len(original) > LONG_MESSAGE:
                original = "(long message, stored as the source \"Message\" in work/sources)"
            text = prompts.refine_draft_brief(self.refine, today, f"{n} file(s) in work/sources/", added, original)
        else:
            blocks, note = self.image_blocks()
            text = prompts.draft_brief(dict(self.job.data, brief=self.prompt_brief), self.intake,
                                       self.sources_block(), note, today, self.starter)
        content = blocks + [{"type": "text", "text": text}] if blocks else text
        summary = self.agent().run("Draft", content, self.handler(self.gate_draft), max_turns=40)
        title = self._draft_title()
        if title:
            self.job.update(title=title)
        return summary

    def _draft_title(self) -> str:
        m = re.search(r'^title:\s*"?(.*?)"?\s*$', (self.work / "draft.md").read_text(encoding="utf-8"), re.M)
        return m.group(1).strip() if m else ""

    def do_plan(self) -> str:
        return self.agent().run("Plan", prompts.plan_brief(self.job.data, self.refine),
                                self.handler(self.gate_plan), max_turns=40)

    def do_build(self) -> str:
        match = (self.work / "match.json").read_text(encoding="utf-8")
        plan = (self.work / "plan.json").read_text(encoding="utf-8")
        return self.agent().run("Build", prompts.build_brief(match, plan, self.refine),
                                self.handler(self.gate_build), max_turns=50)

    def do_review(self) -> str:
        try:
            return self.agent(effort="medium").run("Review", prompts.review_brief(),
                                                   self.handler(self.gate_review), max_turns=30)
        except StageFailed as e:
            # the deck that passed verify is kept; a review that cannot finish does not lose it
            self.log("warn", f"Review did not finish ({e}); keeping the last verified build")
            return "Review stopped early; the last build that passed verify is delivered."

    # ------------------------------------------------------------------ finish
    def finalize(self):
        ws = self.ws
        if ws.state["verified"] != ws.full_snapshot():
            if not self.restore_good():
                raise StageFailed("No verified build to deliver.")
            self.log("warn", "Restored the last build that passed verify")
        if ws.state["rendered_of"] != ws.full_snapshot() or not ws.state["render_dir"]:
            ok, out = ws.render_preview()
            if not ok:
                raise StageFailed("The preview could not be rendered: " + out[-400:])
        rdir = self.work / ws.state["render_dir"]
        deck = self.work / "out.pptx"
        overrides = self.apply_overrides()
        if overrides and overrides["total"]:
            deck = self.work / "final.pptx"
            fdir = self.work / "render-final"
            if fdir.exists():
                shutil.rmtree(fdir)
            code, out = ws.run([ws.script("render_deck.py"), str(deck), str(fdir)], timeout=420)
            if code != 0 or not list(fdir.glob("slide-*.jpg")):
                raise StageFailed("The deck with your requested emphasis could not be rendered: " + out[-400:])
            rdir = fdir
            shutil.copy2(fdir / "final.pdf", fdir / "out.pdf")
        outdir = self.job.dir / "output"
        if outdir.exists():
            shutil.rmtree(outdir)
        (outdir / "slides").mkdir(parents=True)
        title = self._draft_title() or "amasol deck"
        base = re.sub(r"[^\w\- ]+", "", title).strip().replace(" ", "-")[:60] or "amasol-deck"
        base = f"{base}-v{self.job.data.get('version', 1)}"
        shutil.copy2(deck, outdir / f"{base}.pptx")
        if (rdir / "out.pdf").exists():
            shutil.copy2(rdir / "out.pdf", outdir / f"{base}.pdf")
        slides = sorted(rdir.glob("slide-*.jpg"))
        for s in slides:
            shutil.copy2(s, outdir / "slides" / s.name)
        if (rdir / "contact.jpg").exists():
            shutil.copy2(rdir / "contact.jpg", outdir / "contact.jpg")
        hd = make_hd_slides(outdir / f"{base}.pdf", outdir) if (outdir / f"{base}.pdf").exists() else []
        report = build_report(ws, self.summaries, self.warnings)
        return {
            "pptx": f"output/{base}.pptx",
            "pdf": f"output/{base}.pdf" if (outdir / f"{base}.pdf").exists() else None,
            "slides": [f"output/slides/{s.name}" for s in slides],
            "slides_hd": [f"output/hd/{s.name}" for s in hd] if len(hd) == len(slides) else [],
            "contact": "output/contact.jpg" if (outdir / "contact.jpg").exists() else None,
            "slide_count": len(slides),
            "report": report,
            "overrides": overrides,
            "unchanged": self.unchanged_from_parent(),
        }

    def apply_overrides(self) -> dict | None:
        """User-requested text emphasis (work/overrides.json) on a copy of the verified deck."""
        p = self.work / OVERRIDES
        if not p.exists():
            return None
        try:
            rules = json.loads(p.read_text(encoding="utf-8")).get("emphasis") or []
        except (json.JSONDecodeError, AttributeError):
            self.log("warn", "overrides.json is not valid; the emphasis was not applied")
            return None
        if not rules:
            return None
        r = subprocess.run([str(config.SKILL_PY), str(config.RUNNER_DIR / "apply_overrides.py"),
                            str(self.work / "out.pptx"), str(p), str(self.work / "final.pptx")],
                           capture_output=True, text=True, timeout=300)
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            res = {"error": (r.stderr or r.stdout)[-300:]}
        if r.returncode != 0 or "error" in res:
            raise StageFailed("The requested emphasis could not be applied: " + str(res.get("error")))
        res["rules"] = rules
        missing = [t for t, n in res["per_rule"].items() if not n]
        if missing:
            self.log("warn", "Emphasis text not found on any slide (or already covered by another item): "
                     + ", ".join(missing))
        self.log("ok", f"Applied your emphasis in {res['total']} place(s), as an exception to the style guide")
        return res

    def unchanged_from_parent(self) -> bool:
        """A revision whose draft, plan, spec and emphasis equal the previous version's: nothing changed."""
        pid = self.job.data.get("parent_id")
        if not pid:
            return False
        pw = self.job.dir.parent / pid / "work"
        src = pw / "good" if (pw / "good" / "out.pptx").exists() else pw
        for f in ("draft.md", "plan.json", "spec.json"):
            a, b = self.work / f, src / f
            if not a.exists() or not b.exists() or a.read_bytes() != b.read_bytes():
                return False
        a, b = self.work / OVERRIDES, pw / OVERRIDES
        if a.exists() != b.exists() or (a.exists() and a.read_bytes() != b.read_bytes()):
            return False
        return True

    def copy_parent(self, parent_dir: Path):
        pw = parent_dir / "work"
        for name in ("sources", "images"):
            if (pw / name).exists():
                shutil.copytree(pw / name, self.work / name, dirs_exist_ok=True)
        for f in ("intake.json", "request.txt", "combined-sources.txt", OVERRIDES):
            if (pw / f).exists():
                shutil.copy2(pw / f, self.work / f)
        src = pw / "good" if (pw / "good" / "out.pptx").exists() else pw
        for f in GOOD_FILES:
            if (src / f).exists():
                shutil.copy2(src / f, self.work / f)
        for k in self.ws.versions:
            self.ws.versions[k] += 1
        self.save_good()

    def run(self):
        job = self.job
        if job.cancel_requested or job.data.get("status") == "cancelled":
            return
        t0 = time.time()
        job.update(status="running", started_at=t0)
        self.client = make_client()
        try:
            if self.refine:
                parent_dir = job.dir.parent / job.data["parent_id"]

                def reuse():
                    self.copy_parent(parent_dir)
                    msg = f"Reused the inputs and deck of version {job.data.get('version', 2) - 1}."
                    uploads = [(u["name"], self.work / u["saved"], u["role"]) for u in job.data.get("uploads", [])]
                    if uploads or find_urls(self.refine or ""):
                        res = ingest(self.work, uploads)
                        self.fetch_links(self.refine or "", res)
                        self.ingested = res
                        self.warnings += res.warnings
                        for w in res.warnings:
                            self.log("warn", w)
                        job.update(files=res.files, warnings=self.warnings)
                        msg += f" Added {len(res.sources)} text source(s) and {len(res.images)} image(s)."
                    return msg
                self.stage("ingest", reuse)
            else:
                self.stage("ingest", self.do_ingest)
            self.stage("draft", self.do_draft)
            self.stage("plan", self.do_plan)
            self.stage("build", self.do_build)
            if job.data.get("options", {}).get("review", True):
                self.stage("review", self.do_review)
            else:
                job.stage("review", "skipped", "Visual review was turned off.")
            result = self.finalize()
            result["duration"] = round(time.time() - t0)
            result["usage"] = self.usage.as_dict()
            if self.on_done:
                self.on_done()   # uploads outputs + work state to Blob before "done" can be seen anywhere
            job.update(status="done", result=result, usage=self.usage.as_dict(), finished_at=time.time())
            job.emit("status", status="done")
            self.log("ok", f"Deck ready: {result['slide_count']} slides")
        except Cancelled:
            self._fail_running("cancelled", "Cancelled.")
        except StageFailed as e:
            self._fail_running("failed", str(e))
        except anthropic.APIError as e:
            msg = getattr(e, "message", None) or str(e)
            self._fail_running("failed", f"The model call failed: {msg}")
        except Exception as e:  # noqa: BLE001
            # the sandbox's local disk does not outlive the job, so the traceback has to live in data itself
            job.update(internal={**(job.data.get("internal") or {}), "traceback": traceback.format_exc()})
            self._fail_running("failed", f"Unexpected error: {type(e).__name__}: {e}")

    def _fail_running(self, status: str, msg: str):
        for s in self.job.data["stages"]:
            if s["status"] == "running":
                self.job.stage(s["key"], "failed" if status == "failed" else "skipped")
        self.job.update(status=status, error=msg if status == "failed" else None, usage=self.usage.as_dict(),
                        finished_at=time.time())
        self.job.emit("status", status=status, error=msg)
        self.log("error" if status == "failed" else "info", msg)

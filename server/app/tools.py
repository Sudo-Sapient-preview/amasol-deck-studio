"""The tools the deck agent can call. Every tool runs inside one job's WORK folder; the skill folder is read-only.

The script tools wrap the skill's own checks (draft_check, planlib, matcher, matchbuild, verify_deck,
render_deck) and return their output verbatim, so the model reads exactly what the skill prints.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import config

SKILL = config.SKILL_DIR
PY = str(config.SKILL_PY)
WRITABLE = {"draft.md", "plan.json", "spec.json", "overrides.json", "review-notes.md"}
MAX_TOOL_OUTPUT = 24_000


def _trim(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 3]
    tail = text[-(limit * 2 // 3):]
    return f"{head}\n... ({len(text) - limit} characters cut) ...\n{tail}"


def _filter_warnings(text: str) -> str:
    """Drop the expected font-licence warning lines (the skill says they are normal)."""
    out, skip = [], False
    for line in text.splitlines():
        if "UserWarning: Embedded fonts removed" in line:
            skip = True
            continue
        if skip and line.strip().startswith("warnings.warn"):
            skip = False
            continue
        skip = False
        out.append(line)
    return "\n".join(out)


class ToolError(Exception):
    pass


def check_overrides(data):
    """overrides.json: {"emphasis": [{"text", "italic", "bold", "underline", "match_case"}]}."""
    if not isinstance(data, dict) or not isinstance(data.get("emphasis", []), list):
        raise ToolError('overrides.json must be {"emphasis": [{"text": "...", "italic": true}]}. Nothing was written.')
    for k, r in enumerate(data.get("emphasis", []), 1):
        if not isinstance(r, dict) or not str(r.get("text") or "").strip():
            raise ToolError(f"overrides.json emphasis item {k} needs a non-empty 'text'. Nothing was written.")
        if not any(r.get(x) is True for x in ("italic", "bold", "underline")):
            raise ToolError(f"overrides.json emphasis item {k} sets none of italic, bold, underline to true.")
        extra = set(r) - {"text", "italic", "bold", "underline", "match_case"}
        if extra:
            raise ToolError(f"overrides.json emphasis item {k}: unknown keys {sorted(extra)}. Only text emphasis "
                            "(italic, bold, underline) can be overridden.")


class Workspace:
    def __init__(self, work: Path, log=None):
        self.work = work
        self.log = log or (lambda *a, **k: None)
        self.versions = {"draft.md": 0, "plan.json": 0, "spec.json": 0}
        self.state = {"match_of": None, "built_of": None, "verified": None, "rendered_of": None,
                      "render_dir": None, "render_n": 0}
        self.build_count = 0

    # ------------------------------------------------------------------ helpers
    def run(self, args: list[str], timeout: int = 300) -> tuple[int, str]:
        try:
            r = subprocess.run([PY, *args], cwd=str(SKILL), capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout}s"
        return r.returncode, _filter_warnings((r.stdout or "") + ("\n" + r.stderr if r.stderr.strip() else ""))

    def script(self, name: str) -> str:
        return str(SKILL / "scripts" / name)

    def p(self, name: str) -> Path:
        return self.work / name

    def snapshot(self) -> tuple:
        return tuple(self.versions[k] for k in ("draft.md", "plan.json"))

    def full_snapshot(self) -> tuple:
        return tuple(self.versions[k] for k in ("draft.md", "plan.json", "spec.json"))

    def bump(self, name: str):
        if name in self.versions:
            self.versions[name] += 1

    def resolve_read(self, path: str) -> Path:
        path = path.strip().lstrip("/")
        if path.startswith("skill/"):
            base, rel = SKILL, path[len("skill/"):]
        elif path.startswith("work/"):
            base, rel = self.work, path[len("work/"):]
        else:
            base, rel = self.work, path
        target = (base / rel).resolve()
        if not target.is_relative_to(base.resolve()) or ".venv" in target.parts:
            raise ToolError(f"'{path}' is outside the readable folders (skill/..., work/...)")
        if not target.exists():
            raise ToolError(f"'{path}' does not exist")
        return target

    # ------------------------------------------------------------------ file tools
    def read_file(self, path: str, offset: int = 0, limit: int = 0) -> str:
        t = self.resolve_read(path)
        if t.is_dir():
            items = sorted(x.name + ("/" if x.is_dir() else "") for x in t.iterdir() if not x.name.startswith("."))
            return "\n".join(items[:300]) or "(empty folder)"
        if t.suffix.lower() in (".jpg", ".jpeg", ".png", ".pptx", ".pdf"):
            raise ToolError("binary file - use view_images for .jpg/.png; decks are checked with the script tools")
        text = t.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if offset or limit:
            start = max(0, offset)
            end = start + limit if limit else len(lines)
            chunk = lines[start:end]
            more = f"\n... ({len(lines) - end} more lines; continue with offset={end})" if end < len(lines) else ""
            return "\n".join(f"{start + i + 1:>5}  {l}" for i, l in enumerate(chunk)) + more
        if len(text) > 60_000:
            chunk = lines[:800]
            return "\n".join(chunk) + f"\n... ({len(lines) - 800} more lines; read with offset=800, limit=800)"
        return text

    def _check_writable(self, path: str) -> Path:
        name = path.strip().lstrip("/")
        if name.startswith("work/"):
            name = name[len("work/"):]
        if name not in WRITABLE:
            raise ToolError(f"you can only write {sorted(WRITABLE)} in the work folder, not '{path}'")
        return self.work / name

    def write_file(self, path: str, content: str) -> str:
        t = self._check_writable(path)
        if t.name.endswith(".json"):
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ToolError(f"{t.name} is not valid JSON: {e}. Nothing was written.")
            if t.name == "overrides.json":
                check_overrides(data)
        t.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        self.bump(t.name)
        return f"wrote work/{t.name} ({len(content.splitlines())} lines)"

    def edit_file(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        t = self._check_writable(path)
        if not t.exists():
            raise ToolError(f"work/{t.name} does not exist yet - use write_file")
        text = t.read_text(encoding="utf-8")
        count = text.count(old_string)
        if not old_string or count == 0:
            raise ToolError("old_string not found in the file (it must match exactly, including spaces)")
        if count > 1 and not replace_all:
            raise ToolError(f"old_string occurs {count} times - add surrounding lines to make it unique, or set "
                            "replace_all")
        new = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
        if t.name.endswith(".json"):
            try:
                json.loads(new)
            except json.JSONDecodeError as e:
                raise ToolError(f"the edit would make {t.name} invalid JSON: {e}. Nothing was changed.")
        t.write_text(new, encoding="utf-8")
        self.bump(t.name)
        return f"edited work/{t.name} ({count if replace_all else 1} replacement)"

    # ------------------------------------------------------------------ script tools
    def draft_placeholder_problems(self) -> list[str]:
        """Literal skeleton text the bare-request generator leaves behind ('to-be-filled: intro point 1')."""
        d = self.p("draft.md")
        if not d.exists():
            return ["work/draft.md does not exist"]
        probs = []
        for i, line in enumerate(d.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if re.match(r"^(###\s*SLIDE\s*\d+\s*:|key_point:|-\s|closing_message:)", s, re.I) and \
                    re.search(r"to[- ]be[- ]filled\s*:\s*(intro|problem|solution|proof|cta)\b|"
                              r"to[- ]be[- ]filled\s*:\s*the \w+ takeaway|skeleton slot", s, re.I):
                probs.append(f"line {i}: skeleton placeholder left in the draft: '{s[:80]}'")
        return probs

    def check_draft(self, autofix: bool = False) -> tuple[bool, str]:
        d = self.p("draft.md")
        if not d.exists():
            return False, "work/draft.md does not exist yet - write it first"
        out = ""
        if autofix:
            _, out = self.run([self.script("draft_check.py"), str(d), "--autofix"])
            self.bump("draft.md")
            out = "autofix run:\n" + out + "\n\nre-check:\n"
        code, o2 = self.run([self.script("draft_check.py"), str(d)])
        out += o2
        extra = self.draft_placeholder_problems() if self.input_type() == "bare" else []
        if extra:
            out += "\n\nTOOL CHECK FAIL (bare request): replace every skeleton slot with generated content " \
                   "flagged assumption:\n" + "\n".join("  " + x for x in extra[:20])
        return code == 0 and not extra, _trim(out)

    def input_type(self) -> str:
        d = self.p("draft.md")
        if d.exists():
            m = re.search(r"^input_type:\s*\"?(\w+)", d.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1)
        try:
            return json.loads(self.p("intake.json").read_text())["type"]
        except Exception:  # noqa: BLE001
            return ""

    def draftgen(self, mode: str) -> str:
        d = str(self.p("draft.md"))
        if mode == "suggest":
            code, out = self.run([self.script("draftgen.py"), "suggest", d, "--apply-merge", "--apply-shorten", "-o", d])
        elif mode == "topup":
            code, out = self.run([self.script("draftgen.py"), "topup", d, "-o", d])
        else:
            raise ToolError("mode must be 'suggest' or 'topup'")
        self.bump("draft.md")
        return _trim(out)

    def check_plan(self) -> tuple[bool, str]:
        """planlib check + matcher (writes match.json). The draft must pass first."""
        if not self.p("plan.json").exists():
            return False, "work/plan.json does not exist yet - write it first"
        ok_d, out_d = self.check_draft()
        parts = []
        if not ok_d:
            return False, "draft_check FAILS - fix draft.md first:\n" + out_d
        code_p, out_p = self.run([self.script("planlib.py"), "check", str(self.p("plan.json"))])
        parts.append("== planlib check ==\n" + out_p)
        if code_p != 0:
            return False, _trim("\n\n".join(parts))
        code_m, out_m = self.run([self.script("matcher.py"), str(self.p("draft.md")), str(self.p("plan.json")),
                                  "-o", str(self.p("match.json"))])
        parts.append("== matcher (storyboard: n, kind, plan id, layout, visual, reason) ==\n" + out_m)
        if code_m == 0:
            self.state["match_of"] = self.snapshot()
        return code_m == 0, _trim("\n\n".join(parts))

    def build_deck(self) -> tuple[bool, str]:
        """The full chain: draft_check -> planlib -> matcher -> build (spec.json) -> verify --strict."""
        if not self.p("spec.json").exists():
            return False, "work/spec.json does not exist yet - write it first"
        ok, out = self.check_plan()
        if not ok:
            return False, "Stopped before the build:\n" + out
        storyboard = out.split("== matcher", 1)[-1]
        r = subprocess.run([PY, str(config.RUNNER_DIR / "build_spec.py"), str(SKILL), str(self.work)],
                           cwd=str(self.work), capture_output=True, text=True, timeout=600)
        bout = _filter_warnings((r.stdout or "") + ("\n" + r.stderr if r.stderr.strip() else ""))
        self.build_count += 1
        if r.returncode != 0:
            self.state["built_of"] = None
            self.state["verified"] = None
            return False, _trim("== build FAILED ==\n" + bout + "\n\n== matcher" + storyboard)
        self.state["built_of"] = self.full_snapshot()
        code_v, out_v = self.run([self.script("verify_deck.py"), str(self.p("out.pptx")), "--plan",
                                  str(self.p("plan.json")), "--strict"])
        passed = code_v == 0 and "RESULT: PASS" in out_v
        self.state["verified"] = self.full_snapshot() if passed else None
        self.p("verify.txt").write_text(out_v, encoding="utf-8")
        return passed, _trim("== build ==\n" + bout + "\n\n== verify_deck --strict ==\n" + out_v)

    def render_preview(self) -> tuple[bool, str]:
        if not self.p("out.pptx").exists() or self.state["built_of"] is None:
            return False, "no current build - run build_deck first"
        self.state["render_n"] += 1
        rdir = self.work / f"render-{self.state['render_n']}"
        if rdir.exists():
            shutil.rmtree(rdir)
        code, out = self.run([self.script("render_deck.py"), str(self.p("out.pptx")), str(rdir)], timeout=420)
        slides = sorted(rdir.glob("slide-*.jpg")) if rdir.exists() else []
        if code != 0 or not slides:
            return False, _trim("render failed:\n" + out)
        self.state["render_dir"] = rdir.name
        self.state["rendered_of"] = self.state["built_of"]
        listing = ", ".join(s.name for s in slides)
        return True, (f"rendered {len(slides)} slides to work/{rdir.name}/ ({listing}) plus contact.jpg. "
                      f"Look at them with view_images, e.g. ['work/{rdir.name}/contact.jpg'].\n" + _trim(out, 2000))

    def view_images(self, paths: list[str]) -> list[dict]:
        if not paths:
            raise ToolError("give 1-6 image paths")
        blocks = []
        for p in paths[:6]:
            t = self.resolve_read(p)
            if t.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                raise ToolError(f"{p} is not an image")
            data = base64.standard_b64encode(t.read_bytes()).decode()
            media = "image/png" if t.suffix.lower() == ".png" else "image/jpeg"
            blocks.append({"type": "text", "text": p})
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
        return blocks


# ---------------------------------------------------------------------- tool schemas (stable order: cache prefix)
def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOLS = [
    {"name": "read_file",
     "description": "Read a text file. Paths start with 'skill/' (the deck skill, read-only: reference docs, RULES.md, "
                    "scripts) or 'work/' (this job: sources/, draft.md, plan.json, match.json, spec.json, intake.json, "
                    "verify.txt). A folder path lists its files. Use offset/limit (lines) for long files.",
     "input_schema": _obj({"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
                          ["path"])},
    {"name": "write_file",
     "description": "Create or replace a work file. Allowed: work/draft.md, work/plan.json, work/spec.json, "
                    "work/overrides.json (user-requested text emphasis, see the system prompt), "
                    "work/review-notes.md. JSON files are validated before writing.",
     "input_schema": _obj({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])},
    {"name": "edit_file",
     "description": "Replace an exact string in a work file (draft.md, plan.json, spec.json, overrides.json, "
                    "review-notes.md). "
                    "old_string must match exactly and be unique unless replace_all is true.",
     "input_schema": _obj({"path": {"type": "string"}, "old_string": {"type": "string"},
                           "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}},
                          ["path", "old_string", "new_string"])},
    {"name": "check_draft",
     "description": "Run scripts/draft_check.py on work/draft.md and return its PASS/FAIL report. autofix=true first "
                    "applies the safe autofixes (split >5 points, merge one-slide sections, rebuild agenda, renumber).",
     "input_schema": _obj({"autofix": {"type": "boolean"}}, ["autofix"])},
    {"name": "draftgen",
     "description": "Run scripts/draftgen.py on work/draft.md in place. mode 'suggest' applies safe merges and "
                    "shortenings for structured input (coverage-checked); 'topup' fills a short structured draft.",
     "input_schema": _obj({"mode": {"type": "string", "enum": ["suggest", "topup"]}}, ["mode"])},
    {"name": "check_plan",
     "description": "Validate work/plan.json (scripts/planlib.py check) and match layouts (scripts/matcher.py, writes "
                    "work/match.json). Runs draft_check first. Returns the planlib result and the matcher storyboard.",
     "input_schema": _obj({}, [])},
    {"name": "build_deck",
     "description": "Full build chain: draft_check, planlib check, matcher, the build from work/spec.json "
                    "(matchbuild.build), then verify_deck.py --strict. Returns every output; RESULT: PASS at the end "
                    "means the deck is valid.",
     "input_schema": _obj({}, [])},
    {"name": "render_preview",
     "description": "Render the current work/out.pptx with LibreOffice into a fresh work/render-N/ folder "
                    "(slide-NN.jpg, contact.jpg, out.pdf).",
     "input_schema": _obj({}, [])},
    {"name": "view_images",
     "description": "Look at up to 6 images: rendered slides (work/render-N/slide-NN.jpg, contact.jpg), uploaded "
                    "images (work/images/...), guide references (skill/reference/guide-slides/slide-NN.jpg, "
                    "skill/reference/diagram-gallery/slide-NN.jpg, skill/reference/layout-catalog-grid-N.jpg).",
     "input_schema": _obj({"paths": {"type": "array", "items": {"type": "string"}}}, ["paths"])},
    {"name": "finish_stage",
     "description": "Call when this stage's goal is met. The tool runs the stage's gate check itself; if the gate "
                    "fails you get the reason back and keep working. summary: 1-4 plain sentences on what you did.",
     "input_schema": _obj({"summary": {"type": "string"}}, ["summary"])},
]

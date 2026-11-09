"""The hand-off report (skill/reference/handoff.md), assembled from the scripts' own outputs."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .tools import Workspace

FONT_NOTE = ("Mark Pro / Mark Pro Light are not embedded; previews use Outfit; recipients need a licensed install.")


def _sections(report_text: str) -> dict[str, list[str]]:
    """draft_check --report: 'Heading (n):' followed by indented lines."""
    out, cur = {}, None
    for line in report_text.splitlines():
        m = re.match(r"^([A-Z][\w ]+?)\s*\((\d+)\):\s*$", line)
        if m:
            cur = m.group(1).strip().lower()
            out[cur] = []
            continue
        if cur and line.startswith("  ") and line.strip() and line.strip() != "none":
            out[cur].append(line.strip())
        elif line.strip() and not line.startswith(" "):
            cur = None
    return out


def build_report(ws: Workspace, stage_summaries: dict[str, str], warnings: list[str]) -> dict:
    work = ws.work
    code, report_text = ws.run([ws.script("draft_check.py"), str(work / "draft.md"), "--report"])
    _, js = ws.run([ws.script("draft_check.py"), str(work / "draft.md"), "--json"])
    try:
        D = json.loads(js[js.index("{"):])
    except (ValueError, json.JSONDecodeError):
        D = {"header": {}, "sections": []}
    plan = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    match = json.loads((work / "match.json").read_text(encoding="utf-8"))
    verify = (work / "verify.txt").read_text(encoding="utf-8") if (work / "verify.txt").exists() else ""
    intake = {}
    if (work / "intake.json").exists():
        intake = json.loads((work / "intake.json").read_text(encoding="utf-8"))

    draft_slides = {s["n"]: s for sec in D.get("sections", []) for s in sec.get("slides", [])}
    plan_by_id = {e["id"]: e for e in plan.get("slides", [])}
    seq = []
    for x in match.get("sequence", []):
        row = {"n": x.get("n"), "kind": x.get("kind"), "layout": x.get("layout"), "visual": x.get("visual") or ""}
        if x.get("kind") == "content":
            ds = draft_slides.get(x.get("draft_slide"), {})
            pe = plan_by_id.get(x.get("id"), {})
            row.update(id=x.get("id"), title=ds.get("headline", pe.get("title", "")),
                       purpose=ds.get("purpose"), flags=ds.get("flags", []), plan_reason=pe.get("reason", ""),
                       plan_visual=pe.get("visual"), visual_change=x.get("visual_change"))
        elif x.get("kind") == "divider":
            row["title"] = x.get("chapter")
        elif x.get("kind") == "cover":
            row["title"] = D.get("header", {}).get("title", "")
        elif x.get("kind") == "closing":
            row["title"] = (D.get("closing") or {}).get("closing_message", "")
        elif x.get("kind") == "agenda":
            row["title"] = "Agenda"
        seq.append(row)

    secs = _sections(report_text)
    m = re.search(r"(\d+) passed · (\d+) failed · (\d+) skipped", verify)
    infographics = sum(1 for e in plan.get("slides", []) if e.get("class") == "infographic")
    header = D.get("header", {})
    return {
        "title": header.get("title", ""),
        "subtitle": header.get("subtitle", ""),
        "audience": header.get("audience", ""),
        "goal": header.get("goal", ""),
        "language": header.get("language", ""),
        "input_type": header.get("input_type") or intake.get("type", ""),
        "input_reason": intake.get("reason", "").replace(str(work) + "/", ""),
        "assumed": secs.get("assumed header fields", []),
        "edits": secs.get("edits", []),
        "flagged": secs.get("flagged items", []),
        "intake_report": report_text.strip(),
        "slides": seq,
        "plan": {
            "infographics": infographics,
            "cap": plan.get("infographic_cap"),
            "short_pitch": bool(plan.get("short_pitch")),
            "waive": plan.get("waive") or {},
            "cut": plan.get("cut", []),
            "no_chart": plan.get("no_chart", []),
            "excluded": plan.get("excluded", []),
            "chapters": plan.get("chapters", []),
        },
        "layout_counts": match.get("layout_counts", {}),
        "verify": {
            "result": "PASS" if "RESULT: PASS" in verify else "FAIL",
            "passed": int(m.group(1)) if m else None,
            "failed": int(m.group(2)) if m else None,
            "skipped": int(m.group(3)) if m else None,
            "notes": [l.strip().lstrip("~ ").strip() for l in verify.splitlines()
                      if "~ WAIVED" in l or "~ SHORT-PITCH" in l],
            "lines": [l for l in verify.splitlines() if re.match(r"^(PASS|FAIL|SKIP)\s", l)],
        },
        "stage_summaries": stage_summaries,
        "warnings": warnings,
        "font_note": FONT_NOTE,
    }

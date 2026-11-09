"""The one build route: draft.md + plan.json + match.json (the matcher's layouts) + a small per-deck SPEC -> .pptx.

    from matchbuild import build
    build("draft.md", "plan.json", "match.json", SPEC, "out.pptx", logos=None)

The layout and visual of every slide come from match.json - the builder never picks one. Text comes from the
draft: headline -> title, key_point -> sub-line, content -> body / icon rows, data -> the info box number. Speaker
notes: the slide's draft notes, prefixed with SPEC['note_prefix'] when given. SPEC holds only what the draft
cannot say:

    SPEC = {
      "dividers": {"<chapter>": ("icon", "one chapter line")},          # one per chapter (not in short-pitch decks)
      "p01": {"icons": ["monitor-pulse", "layers", "alert-circle"]},     # icon_set: one icon per point
      "p02": {"icon": "trophy", "box_title": "AIOps"},                   # big_number (Inhalt & Infobox)
      "p03": {"args": {"groups": [...], "cols": 3}},                     # any diagram builder: its kwargs
      "p04": {"args": {"categories": [...], "series": {...}}},           # chart (idx: the layout's chart/right box)
      "p05": {"args": {"rows": [[...], ...], "col_w": (...)}},           # table
      "p06": {"args": {"x": 0.432, "y": 3.6, "w": 9.135, "h": 1.0,       # info_box (draft points go above it)
                       "items": ["One line"], "kind": "fill"}},
      # key_slide: the draft's 4 (Key Slide 1) or 6 (Key Slide 2) points fill the pills/tiles; quote: quote_lines
      # optional on any content slide:
      #   "kind": "service"        d.add(..., kind=)          "body": [lead("..."), "..."]  text box beside the visual
      #   "body_idx": 11           where "body" goes          "corner_icon": "dollar"       corner icon tile
      #   "texts": [...]           icon_set row texts         "quote_lines": [...]          quote text
      #   "photo": path            approved photo (RULES §8.2)
      #   "tracker": 1             s.tracker(n)               "custom": fn(s, draft_slide, match_entry)
      #     custom = escape hatch: draws the slide's visual by hand with sgdeck calls; layout still from match.json
      "closing_title": "...", "closing_subtitle": "...", "note_prefix": "...",
      "waive": {"<deck-level rule>": "written reason"},                # passed to d.save(); reported by verify;
                                                                         # "dividers"/"agenda" also drop those slides
    }
Short-pitch mode comes from plan.json ("short_pitch": true): the matcher places no agenda or dividers and the
deck is saved with short_pitch=True. On a chart, donut or pie in a two-column layout the draft points fill the
left column unless SPEC gives "body"."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import draft_check  # noqa: E402
import matcher  # noqa: E402
from sgdeck import Deck, GuideError  # noqa: E402
from pptx import Presentation  # noqa: E402
BANK = {l["name"]: l for l in matcher.bank()}
KEY_SLOTS = {"Key Slide 1": (14, 16, 17, 18), "Key Slide 2": (14, 16, 17, 18, 19, 20)}


def _chart_box(lay):
    """(chart idx, left text idx or None) for a layout: its chart placeholder, else the right box of a two-column
    layout (text left), else the main object box 11 (no text box)."""
    P = BANK[lay]["placeholders"]
    chart = next((p["idx"] for p in P if p["type"] == "chart"), None)
    objs = sorted(p["idx"] for p in P if p["type"] == "object")
    if chart is not None:
        return chart, (objs[0] if objs else None)
    if len(objs) >= 2:
        return objs[1], objs[0]
    return 11, None


def build(draft_path, plan_path, match_path, spec, out, logos=None):
    D = draft_check.parse(open(draft_path, encoding="utf-8").read())
    M = json.load(open(match_path, encoding="utf-8"))
    if M.get("problems"):
        raise GuideError("match.json has problems - fix the draft and rerun the matcher: " + "; ".join(M["problems"]))
    SL = matcher.draft_slides(D)
    plan = json.load(open(plan_path, encoding="utf-8"))
    short = bool(M.get("short_pitch", plan.get("short_pitch")))
    # agenda items = the plan's chapters (dividers may be waived, so they cannot be the source)
    chapters = plan.get("chapters") or [x["chapter"] for x in M["sequence"] if x["kind"] == "divider"]
    waive = {**(plan.get("waive") or {}), **(spec.get("waive") or {})}   # plan.json is the place for waivers
    d = Deck(); d.brand()
    notes = {}
    for x in M["sequence"]:
        k, lay = x["kind"], x["layout"]
        if k == "cover":
            s = d.add(lay); s.title(D["header"]["title"]); s.subtitle(D["header"].get("subtitle", "")); s.remove_empty()
        elif k == "agenda":
            if "agenda" not in waive:
                d.agenda(chapters)
        elif k == "divider":
            if "dividers" in waive:                  # waived with a written reason: no divider slides
                continue
            n = chapters.index(x["chapter"]) + 1
            s = d.add(lay); s.text(10, x["chapter"]); s.text(12, f"{n:02d}")
            icon, line = spec["dividers"][x["chapter"]]
            s.chapter_panel(icon, value=None, text=line); s.remove_empty()
        elif k == "closing":
            s = d.add(lay); s.text(10, spec.get("closing_title") or D["closing"].get("closing_message") or "Thank you")  # closing_title: short line when the draft message is too long
            s.subtitle(spec.get("closing_subtitle") or D["closing"].get("contact") or ""); s.remove_empty()
        else:
            pid, v, sl = x["id"], x["visual"], SL[x["draft_slide"]]
            sp = spec.get(pid, {})
            pts = [t for _, t in sl["content"]]
            kp = " ".join(t for _, t in sl["key_point"])
            s = d.add(lay, kind=sp.get("kind"), plan=pid)
            body = sp.get("body")
            if v == "quote":
                s.quote(sl["headline"], sp.get("quote_lines", pts), photo=sp.get("photo") or x.get("photo"))
            elif v == "key_slide":                       # Key Slide 1/2: headline 10, sub-line 13, pills/tiles
                slots = KEY_SLOTS[lay]
                texts = sp.get("texts", pts)
                if len(texts) != len(slots):
                    raise GuideError(f"{pid}: {lay} takes exactly {len(slots)} points, the draft gives {len(texts)}")
                s.text(10, sl["headline"]); s.text(13, kp)
                for idx, t in zip(slots, texts):
                    s.text(idx, t)
            else:
                s.title(sl["headline"]); s.subtitle(kp)
                if sp.get("custom"):                     # escape hatch: hand-drawn visual, layout from match.json
                    sp["custom"](s, sl, x)
                elif v == "icon_set":
                    s.icon_set(list(zip(sp.get("texts", pts), sp["icons"])), plan=pid)
                elif v == "big_number":
                    num = next(i for i in sl["data"] if any(c.isdigit() for c in str(i.get("value"))))
                    s.body(11, sp.get("body", pts))
                    s.text(15, sp.get("box_title", num["label"])); s.text(16, str(num["value"]))
                    s.text(17, sp.get("box_label", num["label"]))
                    s.icon(sp.get("icon", "bar-chart"), at="infobox", tile=True)
                elif v == "chart":                       # sgdeck.chart/table take no plan= (the slide carries it)
                    a = dict(sp["args"])
                    idx, left = _chart_box(lay)
                    s.chart(a.pop("idx", idx), **a)
                    if body is None and left is not None:
                        body = pts
                        sp = dict(sp, body_idx=sp.get("body_idx", left))
                elif v == "table":
                    s.table(**sp["args"])
                elif v in ("donut", "pie"):              # a pie is sgdeck's donut with pie=True
                    s.donut(plan=pid, pie=(v == "pie"), **sp["args"])
                    left = _chart_box(lay)[1]            # two-column layout: draft points in the left column
                    if body is None and left is not None and BANK[lay]["columns"] >= 2:
                        body = pts
                        sp = dict(sp, body_idx=sp.get("body_idx", left))
                elif v == "info_box":                    # free text box: geometry from SPEC, draft points beside it
                    if "args" not in sp:
                        raise GuideError(f"{pid}: info_box needs SPEC args x, y, w, h (inches, inside the content "
                                         "area) and items; the draft points go into body_idx (default 11)")
                    s.info_box(**sp["args"])
                    if body is None:
                        body = pts
                else:
                    a = dict(sp.get("args", {}))
                    if v == "tile_grid" and logos and a.pop("use_logos", False):
                        s.logo_grid(logos=logos, plan=pid, **a)
                    else:
                        getattr(s, v)(plan=pid, **a)
                if body is not None and v not in ("icon_set", "big_number"):   # those two place their own text
                    s.body(sp.get("body_idx", 11), body)
                if sp.get("corner_icon"):
                    s.icon(sp["corner_icon"], at="corner", tile=True)
                if sp.get("tracker"):
                    s.tracker(sp["tracker"])
            if v != "quote" and (sp.get("photo") or x.get("photo")):
                pic = next(p["idx"] for p in BANK[lay]["placeholders"] if p["type"] == "picture")
                s.picture(pic, sp.get("photo") or x.get("photo"))
            s.remove_empty()
            pre = spec.get("note_prefix", "")
            notes[pid] = (pre + ("\n" if pre and sl["notes"] else "") + (sl["notes"] or "")).strip()
    d.save(out, waive=waive or None, short_pitch=short)
    prs = Presentation(out)
    P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    for sl in prs.slides:
        nm = sl._element.find(P + "cSld").get("name", "")
        if nm.startswith("plan:") and notes.get(nm[5:]):
            sl.notes_slide.notes_text_frame.text = notes[nm[5:]]
    prs.save(out)
    return out

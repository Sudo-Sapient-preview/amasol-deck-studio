"""Infographic plan (plan.json) - schema, validation and deck conformance. Spec: reference/infographic-planner.md.

    python3 scripts/planlib.py check plan.json            # validate a plan before building (exit 1 on problems)

verify_deck.py imports check_deck() / invented_numbers() for its plan checks. Needs python-pptx + lxml."""
import json, math, os, re, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "sgdeck-plan/1"
VISUALS = {
    "infographic": {"donut", "pie", "wheel", "staircase", "tiers", "process"},
    "structured": {"tile_grid", "fact_chips", "band", "story_panel", "chart", "table", "picture"},
    "text-led": {"icon_set", "icon", "info_box", "big_number", "key_slide", "quote"},
}
CLASS_OF = {v: c for c, vs in VISUALS.items() for v in vs}
CHARTS = {"donut", "pie", "chart"}
MAX_REASON = 200                   # "one-line reason": longer means it is an essay, not a reason
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def cap(n):
    """Infographic cap for n content slides - the one rule in sgdeck.infographic_cap (~1/3)."""
    import sgdeck
    return sgdeck.infographic_cap(n)


def norm(t):
    """Whitespace, quote marks and dashes folded so a quote copied from the draft still matches."""
    t = unicodedata.normalize("NFKC", t or "")
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u2013", "-"), ("\u2014", "-")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip().casefold()


def numbers(text):
    out = set()
    for m in NUM_RE.findall(text or ""):
        m = m.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", m) else m.replace(",", "")
        try:
            out.add(float(m))
        except ValueError:
            pass
    return out


def load(path):
    try:
        plan = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"planlib: no such plan file: {path}")
    except ValueError as e:
        raise SystemExit(f"planlib: {path} is not valid JSON ({e})")
    src = plan.get("source", "")
    if src and not os.path.isabs(src):
        src = os.path.join(os.path.dirname(os.path.abspath(path)), src)
    text = open(src, encoding="utf-8").read() if src and os.path.isfile(src) else None
    return plan, text, src


def _walk_strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        yield str(x)
    elif isinstance(x, dict):
        for v in x.values():
            yield from _walk_strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _walk_strings(v)


def validate(plan, source_text):
    """Problems (strings) with the plan itself: schema, vocabulary, quotes verbatim in the source, numbers only from
    the quotes, infographic cap and no two infographics in a row."""
    p = []
    if plan.get("schema") != SCHEMA:
        p.append(f"schema must be '{SCHEMA}'")
    if source_text is None:
        p.append("source: the draft file is missing or unreadable - plan.json 'source' must point at it")
    slides = plan.get("slides") or []
    if not slides:
        p.append("slides: empty - one entry per content slide (cover, agenda, dividers, closing excluded)")
    src = norm(source_text or "")
    ids = [s.get("id") for s in slides]
    if len(set(ids)) != len(ids) or not all(ids):
        p.append("every slide needs a unique 'id'")
    for s in slides:
        sid = s.get("id", "?")
        v, c = s.get("visual"), s.get("class")
        if v not in CLASS_OF:
            p.append(f"{sid}: visual '{v}' is not one of {sorted(CLASS_OF)}")
        elif c != CLASS_OF[v]:
            p.append(f"{sid}: visual '{v}' is class '{CLASS_OF[v]}', plan says '{c}'")
        r = (s.get("reason") or "").strip()
        if not r or "\n" in r or len(r) > MAX_REASON:
            p.append(f"{sid}: 'reason' must be one line (<= {MAX_REASON} chars)")
        quotes = s.get("source_quotes") or []
        if not quotes:
            p.append(f"{sid}: 'source_quotes' empty - quote the exact draft lines the slide uses")
        for q in quotes:
            if source_text is not None and norm(q) not in src:
                p.append(f"{sid}: quote not found verbatim in the source: '{q[:70]}'")
        qnums = set().union(*[numbers(q) for q in quotes]) if quotes else set()
        for t in _walk_strings(s.get("data", {})):
            for n in numbers(t):
                if n not in qnums:
                    p.append(f"{sid}: number {n:g} in 'data' is not in this slide's source_quotes - never invent data")
        if v in CHARTS:
            d = s.get("data") or {}
            cats, vals = d.get("categories"), d.get("values")
            if not cats or not vals or len(cats) != len(vals):
                p.append(f"{sid}: a {v} needs data.categories and data.values of equal length")
            elif v in ("donut", "pie") and not (2 <= len(vals) <= 4):
                p.append(f"{sid}: a {v} takes 2-4 parts of one whole")
    excl = plan.get("excluded") or []
    used = {norm(q) for s in slides for q in s.get("source_quotes") or []}
    for e in excl:
        q = e.get("quote", "")
        if source_text is not None and norm(q) not in src:
            p.append(f"excluded quote not in the source: '{q[:70]}'")
        if norm(q) in used:
            p.append(f"excluded quote is also used by a slide: '{q[:70]}'")
        if not (e.get("reason") or "").strip():
            p.append(f"excluded '{q[:40]}': give a reason")
    inf = [k for k, s in enumerate(slides) if CLASS_OF.get(s.get("visual")) == "infographic"]
    if len(inf) > cap(len(slides)):
        p.append(f"{len(inf)} infographics for {len(slides)} content slides - cap is {cap(len(slides))}; cut the "
                 "weakest and record it under 'cut'")
    for a, b in zip(inf, inf[1:]):
        same_chapter = slides[a].get("chapter") == slides[b].get("chapter")    # a divider separates chapters
        if b == a + 1 and same_chapter:
            p.append(f"{slides[a]['id']} and {slides[b]['id']} are consecutive infographics - reorder or cut one")
    for c_ in plan.get("cut") or []:
        if not (c_.get("reason") or "").strip():
            p.append(f"cut {c_.get('id')}: give a reason")
    declared = plan.get("infographic_cap")
    if declared is not None and declared != cap(len(slides)):
        p.append(f"infographic_cap says {declared}, the rule gives {cap(len(slides))} for {len(slides)} slides")
    return p


def deck_text(prs, skip_numbers=True):
    """All slide text; with skip_numbers the agenda tiles and divider number squares are left out (structural)."""
    import sgdeck
    from pptx.oxml.ns import qn
    out = []
    for s in prs.slides:
        lname = sgdeck.base_layout(s.slide_layout.name)
        for sp in s.shapes._spTree.iter(qn("p:sp")):
            ph = sp.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}")
            if ph is not None and ph.get("type") in ("ftr", "sldNum", "dt"):
                continue
            idx = int(ph.get("idx", 0)) if ph is not None else None
            nm = sp.find(f"{qn('p:nvSpPr')}/{qn('p:cNvPr')}").get("name", "")
            if skip_numbers and ((lname == "Agenda" and idx in {n for n, _ in sgdeck.AGENDA_SLOTS}) or
                                 (lname in sgdeck.DIVIDERS and idx == 12) or nm == sgdeck.NUMBER_NAME):
                continue
            out.append(" ".join(t.text or "" for t in sp.iter(qn("a:t"))))
        for gf in s.shapes._spTree.iter(qn("p:graphicFrame")):
            out.append(" ".join(t.text or "" for t in gf.iter(qn("a:t"))))
        for shp in s.shapes:
            if getattr(shp, "has_chart", False) and shp.has_chart:
                cats, vals = sgdeck.chart_numbers(shp.chart)
                out.append(" ".join(cats + [f"{v:g}" for v in vals]))
    return "\n".join(out)


def check_deck(prs, plan, match=None):
    """Planned visual on its slide (slide name 'plan:<id>'), chart numbers equal the plan's data, excluded quotes
    absent from the deck. With match.json (scripts/matcher.py): each planned slide uses its matched layout and the
    matched visual (the matcher may settle `icon` into `icon_set` / `big_number`)."""
    M = {x["id"]: x for x in (match or {}).get("sequence", []) if x.get("id")}
    import sgdeck
    p = []
    by_id = {}
    for i, s in enumerate(prs.slides, 1):
        nm = s._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}cSld").get("name", "")
        if nm.startswith("plan:"):
            by_id[nm[5:]] = (i, s)
    for e in plan.get("slides") or []:
        sid, v = e.get("id"), e.get("visual")
        if sid not in by_id:
            p.append(f"{sid}: planned slide not in the deck (build it with d.add(..., plan='{sid}'))")
            continue
        i, s = by_id[sid]
        have = sgdeck.slide_visuals(s)
        if sid in M:
            want = M[sid].get("layout")
            if want and s.slide_layout.name != want:
                p.append(f"{sid} (slide {i}): layout '{s.slide_layout.name}' but match.json chose '{want}'")
            v = M[sid].get("visual") or v
        if v not in have:
            p.append(f"{sid} (slide {i}): planned '{v}' missing - slide has {sorted(have) or 'no visual'}")
        if v in CHARTS:
            d = e.get("data") or {}
            charts = [shp.chart for shp in s.shapes if getattr(shp, "has_chart", False) and shp.has_chart]
            if not charts:
                continue
            cats, vals = sgdeck.chart_numbers(charts[0])
            want = [float(x) for x in d.get("values", [])]
            if vals != want:
                p.append(f"{sid} (slide {i}): chart values {vals} differ from the plan {want}")
            if [norm(c) for c in cats] != [norm(str(c)) for c in d.get("categories", [])]:
                p.append(f"{sid} (slide {i}): chart categories {cats} differ from the plan {d.get('categories')}")
    for i, s in enumerate(prs.slides, 1):
        nm = s._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}cSld").get("name", "")
        if nm.startswith("plan:") and nm[5:] not in {e.get("id") for e in plan.get("slides") or []}:
            p.append(f"slide {i} carries plan id '{nm[5:]}' that plan.json does not list")
    text = norm(deck_text(prs, skip_numbers=False))
    for e in plan.get("excluded") or []:
        if norm(e.get("quote", "")) and norm(e["quote"]) in text:
            p.append(f"excluded line is on a slide: '{e['quote'][:70]}'")
    return p


def invented_numbers(prs, source_text):
    """Numbers on slides that do not occur in the source draft (agenda/divider numbering excluded)."""
    src = numbers(source_text)
    bad = sorted(numbers(deck_text(prs)) - src)
    return [f"number {n:g} is on a slide but not in the source" for n in bad]


def main(argv):
    if len(argv) != 3 or argv[1] != "check":
        sys.exit(__doc__)
    plan, text, src = load(argv[2])
    probs = validate(plan, text)
    slides = plan.get("slides") or []
    inf = sum(1 for s in slides if CLASS_OF.get(s.get("visual")) == "infographic")
    print(f"plan: {len(slides)} content slides, {inf} infographics (cap {cap(len(slides))}), "
          f"{len(plan.get('cut') or [])} cut, {len(plan.get('excluded') or [])} excluded lines; source {src}")
    for x in probs:
        print(f"  FAIL {x}")
    print("PASS plan.json" if not probs else f"{len(probs)} problem(s)")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

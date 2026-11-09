"""Verify a built deck against the style guide.
Usage: python3 scripts/verify_deck.py out.pptx [--plan plan.json] [--strict]
Runs 23 checks (including the sgdeck lint via lint_prs) and prints PASS/FAIL/SKIP per check, then a summary that is
always out of 23 and one verdict line:
    21 passed · 0 failed · 2 skipped (of 23)
    skipped: invented-numbers, coverage
    RESULT: PASS
Exit 0 on RESULT: PASS, 1 on RESULT: FAIL. A SKIP is not a failure unless --strict is given (use --strict in the full
workflow, where plan.json and a standard draft.md always exist). Read the verdict line, never the counts.
Checks 21-23 (keys plan, invented-numbers, coverage) need the infographic plan: pass --plan, or keep plan.json /
<deck>.plan.json next to the deck; without one they SKIP. Check 23 (content coverage, scripts/coverage.py) also needs
the plan's source to be a standard draft.md. parse_summary(stdout) reads the summary back (used by the evals). Waivers count only when Deck.save() recorded them in the deck (docProps/custom.xml) with a
reason and the rule is deck-level (sgdeck.WAIVABLE). Needs python-pptx and lxml; the schema check also runs
`office validate` when the office CLI is on PATH."""
import json, os, re, shutil, subprocess, sys, zipfile
from collections import Counter
from lxml import etree
from pptx import Presentation
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capacity
import sgdeck
import planlib
import coverage
import draft_check

TEMPLATE_BRAND = sgdeck.TEMPLATE_BRAND
FACES = {"+mj-lt", "+mn-lt", "+mj-ea", "+mn-ea", "+mj-cs", "+mn-cs", "Mark Pro", "Mark Pro Light"}
SIZES = {1, 7, 8, 9, 10, 12, 14, 18, 20, 24, 32, 36, 48}        # RULES.md §2 (1 pt = hidden tracker labels)
PALETTE = {"000000", "DB2F16", "0074A4", "8B8A7C", "C4A800", "EBEAE2", "FFFFFF", "D3F1F0", "F5E1EA", "FFF8DF"}
EFFECTS = ("alpha", "gradFill", "outerShdw", "innerShdw", "glow", "tint", "shade", "lumMod", "lumOff")
CONTENT = re.compile(r"^ppt/(slides/slide\d+|charts/chart\d+)\.xml$")
LAYOUTS = re.compile(r"^ppt/(slideLayouts/slideLayout\d+|slideMasters/slideMaster\d+)\.xml$")
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
CNS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
GROUPS = [("deck structure (cover, agenda, dividers, chapters, repeats, think-cell, footer)",
           {"cover", "closing", "agenda", "dividers", "divider-family", "repeat", "layout-reuse", "agenda-chapters",
            "thinkcell", "footer", "short-pitch-size"}),
          ("agenda numbering (01..n in reading order, one tile per item)", {"agenda-numbers"}),
          ("background family (one family for content slides)", {"background"}),
          ("slide content (no empty/prompt placeholders, bold lead lines first only, key-slide counts)",
           {"empty", "prompt", "lead", "key-count"}),
          ("text capacity (measured, reference/capacity.md; table cells one line)", {"capacity"}),
          ("tables (guide spec: style, rules, row height, size)", {"table"}),
          ("charts (guide spec, chart-wide size, units stated, one scale, valid axis ids)", {"chart"}),
          ("visuals (every content slide has an icon, diagram, chart, picture or key number; one main visual; "
           "diagrams inside the content area; infographics <= ~1/3, never consecutive)", {"visual", "infographics"}),
          ("icon tiles match their container (rounded square in rounded boxes, circle in pills/ovals/circles)",
           {"icon-tile"}),
          ("logos legible on their tile (>= 3:1 contrast on most of the mark), inside a tile, no overlaps", {"logo"})]


def values(xml):
    x = etree.fromstring(xml) if isinstance(xml, bytes) else xml
    out = Counter()
    for tag in ("rPr", "defRPr", "endParaRPr"):
        for el in x.iter(A + tag):
            if el.get("sz"):
                out[("sz", int(el.get("sz")) / 100)] += 1
    for el in x.iter(A + "srgbClr"):
        out[("clr", el.get("val", "").upper())] += 1
    for el in x.iter(A + "latin", A + "ea", A + "cs"):
        if el.get("typeface"):
            out[("face", el.get("typeface"))] += 1
    for t in EFFECTS:
        for _ in x.iter(A + t):
            out[("fx", t)] += 1
    return out


CHECK_COUNT = 23
SKIP_KEYS = ("plan", "invented-numbers", "coverage")     # the only checks that can SKIP


def parse_summary(text):
    """Read verify_deck output back: {passed, failed, skipped, total, skipped_keys, result}."""
    m = re.search(r"^(\d+) passed · (\d+) failed · (\d+) skipped \(of (\d+)\)$", text, re.M)
    r = re.search(r"^RESULT: (PASS|FAIL)", text, re.M)
    k = re.search(r"^skipped: (.+)$", text, re.M)
    if not (m and r):
        return None
    p_, f_, s_, t_ = map(int, m.groups())
    return {"passed": p_, "failed": f_, "skipped": s_, "total": t_, "result": r.group(1),
            "skipped_keys": k.group(1).split(", ") if k else []}


def main(path, plan_path=None, strict=False):
    results, skipped = [], []

    def check(name, problems, waived=(), notes=()):
        results.append(not problems)
        print(f"{'PASS' if not problems else 'FAIL'}  {name}")
        for p in problems[:15]:
            print(f"      - {p}")
        if len(problems) > 15:
            print(f"      ... {len(problems) - 15} more")
        for w in waived:
            print(f"      ~ WAIVED {w}")
        for n_ in notes:
            print(f"      ~ SHORT-PITCH {n_}  <- recorded, not a failure; report it")

    z = zipfile.ZipFile(path)
    names = z.namelist()
    tz = zipfile.ZipFile(sgdeck.TEMPLATE)
    br_p = sgdeck.foreign_branding(z)          # branding parts and copyright lines; client names in content are fine
    bprs = Presentation(path)
    master = bprs.slide_masters[0]
    mnames = {sh.name for sh in master.shapes}
    if not (sgdeck.LOGO_GROUPS & mnames):
        br_p.append("master: amasol logo group missing")
    if not any("\u00a9" in sh.text_frame.text and TEMPLATE_BRAND in sh.text_frame.text.lower()
               for sh in master.shapes if sh.has_text_frame):
        br_p.append("master: amasol copyright line missing")
    if any(sh.name.startswith("Wordmark") for m in [master] + list(bprs.slide_layouts) for sh in m.shapes):
        br_p.append("a replacement text wordmark is present (re-branding leftover)")
    check(f"{TEMPLATE_BRAND} branding intact (logo + copyright on master), no other company's branding", br_p)
    pres = z.read("ppt/presentation.xml").decode()
    check("no embedded fonts (fntdata / embeddedFontLst)",
          [n for n in names if n.endswith(".fntdata")] + (["embeddedFontLst in presentation.xml"] if "embeddedFontLst" in pres else []))

    # --- fonts / sizes / colours on slides and charts --------------------------------------------------------
    theme = z.read(next(n for n in names if n.startswith("ppt/theme/theme"))).decode()
    maj = re.search(r"<a:majorFont><a:latin typeface=\"([^\"]+)\"", theme); mnr = re.search(r"<a:minorFont><a:latin typeface=\"([^\"]+)\"", theme)
    font_p = [] if (maj and mnr and maj.group(1) == "Mark Pro" and mnr.group(1) == "Mark Pro Light") else ["theme fonts are not Mark Pro / Mark Pro Light"]
    size_p, col_p = [], []
    for n in sorted(n for n in names if CONTENT.match(n)):
        x = etree.fromstring(z.read(n))
        for el in x.iter(A + "latin", A + "ea", A + "cs"):
            tf = el.get("typeface")
            if tf and tf not in FACES:
                font_p.append(f"{n}: typeface '{tf}'")
        for tag in ("rPr", "defRPr", "endParaRPr"):
            for el in x.iter(A + tag):
                if el.get("sz") and int(el.get("sz")) / 100 not in SIZES:
                    size_p.append(f"{n}: {int(el.get('sz')) / 100:g} pt")
                if el.get("i") == "1":
                    font_p.append(f"{n}: italic run")
                if el.get("u") not in (None, "none"):
                    font_p.append(f"{n}: underline")
                if el.get("spc") not in (None, "0"):
                    font_p.append(f"{n}: letter spacing {el.get('spc')}")
        for el in x.iter(A + "srgbClr"):
            if el.get("val", "").upper() not in PALETTE:
                col_p.append(f"{n}: colour #{el.get('val')}")
        for t in EFFECTS:
            for el in x.iter(A + t):
                col_p.append(f"{n}: <a:{t}> (no transparency/tints/gradients/shadows)")
    check("fonts: Mark Pro / Mark Pro Light theme slots only, no italics/underline, tracking 0", font_p)
    check(f"type sizes from the guide scale {sorted(SIZES)} (slides and charts)", size_p)
    check("colours: guide palette only, no transparency/tints/gradients/shadows", col_p)

    # --- layouts / master: anything the build added must be on-spec; amasol logo + copyright fit ----------------
    prs = Presentation(path)
    tprs = Presentation(sgdeck.TEMPLATE)
    tparts = {l.name: str(l.part.partname).lstrip("/") for l in tprs.slide_layouts}
    tparts["__master__"] = str(tprs.slide_masters[0].part.partname).lstrip("/")
    lay_p = []
    objs = [(m.part, "__master__") for m in prs.slide_masters] + [(l.part, l.name) for l in prs.slide_layouts]
    for part, lname in objs:
        pn = str(part.partname).lstrip("/")
        lname_b = sgdeck.base_layout(lname)                 # build-time clones ('Agenda 7') -> guide layout
        base = values(tz.read(tparts[lname_b])) if lname_b in tparts else Counter()
        x = etree.fromstring(z.read(pn))
        for (kind, v), cnt in (values(x) - base).items():
            if (kind == "sz" and v not in SIZES) or (kind == "clr" and v not in PALETTE) or \
               (kind == "face" and v not in FACES) or kind == "fx":
                lay_p.append(f"{pn} ('{lname}'): added {kind} {v}")
        for sp in x.iter(P + "sp"):
            nm = sp.find(f"{P}nvSpPr/{P}cNvPr").get("name", "")
            t = "".join(e.text or "" for e in sp.iter(A + "t"))
            ext = sp.find(f"{P}spPr/{A}xfrm/{A}ext")
            r = sp.find(".//" + A + "rPr")
            if ext is None or not t:
                continue
            pt = int(r.get("sz", 800)) / 100 if r is not None and r.get("sz") else 8
            if nm.startswith("Wordmark") or nm == "Website":
                face = "+mj-lt" if nm.startswith("Wordmark") else "+mn-lt"
                w = capacity.text_width_pt(t, pt, face) * (1 + capacity.HEADROOM) / 72
                if w > int(ext.get("cx")) / 914400 + 0.005:
                    lay_p.append(f"{pn}: '{t}' at {pt:g} pt needs {w:.2f} in, footprint is {int(ext.get('cx')) / 914400:.3f} in")
                if pt not in SIZES:
                    lay_p.append(f"{pn}: '{t}' at {pt:g} pt is off the type scale")
            elif "\u00a9" in t:
                bp = sp.find(f"{P}txBody/{A}bodyPr")
                ins = sum(int(bp.get(a, 91440)) for a in ("lIns", "rIns")) if bp is not None else 182880
                w = capacity.text_width_pt(t, pt, "+mn-lt") * (1 + capacity.HEADROOM) / 72
                room = (int(ext.get("cx")) - ins) / 914400
                if w > room + 0.005:
                    lay_p.append(f"{pn}: copyright '{t}' needs {w:.2f} in, one line holds {room:.2f} in - it wraps")
    check("layouts/master: added values on spec; amasol logo and copyright intact (copyright on one line)", sorted(set(lay_p)))

    # --- sgdeck lint, grouped -------------------------------------------------------------------------------
    waivers = sgdeck.read_waivers(path)
    mode = sgdeck.read_mode(path)
    findings = sgdeck.lint_prs(prs, expect_thinkcell=True, mode=mode)
    notes = [m for k, m in findings if k == "short-pitch"]
    for gi, (title, keys) in enumerate(GROUPS):
        mine = [(k, m) for k, m in findings if k.split(":")[0] in keys]
        failed = [f"[{k}] {m}" for k, m in mine if k.split(":")[0] not in waivers]
        waived = [f"[{k}] {m} -- reason: {waivers[k.split(':')[0]]}" for k, m in mine if k.split(":")[0] in waivers]
        check(title, failed, waived, notes if gi == 0 else ())

    # --- metadata ---------------------------------------------------------------------------------------------
    meta_p = [n for n in names if n.startswith("customXml/")]
    meta_p = sorted({"customXml/* parts (template owner's SharePoint fields)"} if meta_p else set())
    if "docProps/custom.xml" in names:
        cx = etree.fromstring(z.read("docProps/custom.xml"))
        extra = [p.get("name") for p in cx if p.get("name") not in (sgdeck.WAIVER_PROP, sgdeck.MODE_PROP)]
        if extra:
            meta_p.append(f"docProps/custom.xml carries template properties {extra}")
    tcore = etree.fromstring(tz.read("docProps/core.xml")); core = etree.fromstring(z.read("docProps/core.xml"))
    tvals = {el.tag: (el.text or "").strip() for el in tcore}
    for el in core:
        v = (el.text or "").strip()
        if v and tvals.get(el.tag) == v and not el.tag.endswith(("created", "modified", "revision")):
            meta_p.append(f"core property {el.tag.split('}')[1]} still the template's: '{v[:50]}'")
    tthumb = tz.read("docProps/thumbnail.jpeg") if "docProps/thumbnail.jpeg" in tz.namelist() else None
    if tthumb and "docProps/thumbnail.jpeg" in names and z.read("docProps/thumbnail.jpeg") == tthumb:
        meta_p.append("docProps/thumbnail.jpeg is the template's thumbnail (template owner's cover)")
    app = z.read("docProps/app.xml").decode() if "docProps/app.xml" in names else ""
    m = re.search(r"<Slides>(\d+)</Slides>", app)
    if m and int(m.group(1)) != len(prs.slides):
        meta_p.append(f"app.xml says {m.group(1)} slides, deck has {len(prs.slides)}")
    if re.search(r"<Template>[^<]+</Template>", app):
        meta_p.append("app.xml names the template file")
    if "<TitlesOfParts>" in app:
        meta_p.append("app.xml lists stale slide titles (TitlesOfParts)")
    for n in names:
        if n.startswith(("docProps/", "customXml/")):
            for e in set(re.findall(rb"[\w.+-]+@[\w -]+\.[a-z]{2,}", z.read(n))):
                meta_p.append(f"{n}: e-mail address '{e.decode(errors='replace')}'")
    check("metadata clean (no template core/app/custom properties, no customXml, no e-mails)", meta_p)

    # --- schema / ids ---------------------------------------------------------------------------------------------
    sch_p = []
    for n in names:
        if re.match(r"^ppt/(slides/slide|slideLayouts/slideLayout|slideMasters/slideMaster)\d+\.xml$", n):
            ids = [e.get("id") for e in etree.fromstring(z.read(n)).iter(P + "cNvPr")]
            d = sorted({i for i in ids if ids.count(i) > 1 or not (i or "").isdigit()})
            if d:
                sch_p.append(f"{n}: duplicate/invalid shape ids {d}")
        if re.match(r"^ppt/charts/chart\d+\.xml$", n):
            x = etree.fromstring(z.read(n))
            ax = {e.get("val") for e in x.iter(CNS + "axId")}
            if any(int(v) < 0 for v in ax):
                sch_p.append(f"{n}: negative chart axis ids")
            if any(e.get("val") not in ax for e in x.iter(CNS + "crossAx")):
                sch_p.append(f"{n}: crossAx names no axis")
    ct = z.read("[Content_Types].xml").decode()
    for pn in re.findall(r'PartName="/([^"]+)"', ct):
        if pn not in names:
            sch_p.append(f"[Content_Types].xml overrides absent part {pn}")
    office = shutil.which("office")
    if office:
        r = subprocess.run([office, "validate", path, "--json"], capture_output=True, text=True)
        try:
            for i in json.loads(r.stdout).get("issues", []):
                sch_p.append(f"office validate: {i.get('part')}: {i.get('message', '')[:120]}")
        except ValueError:
            sch_p.append("office validate produced no JSON")
    name = "schema / ids (built-in" + (" + office validate)" if office else "; office CLI not on PATH)")
    check(name, sorted(set(sch_p)))

    # --- prompt / placeholder text anywhere (shapes, tables, groups, notes excluded) ---------------------------
    pr_p = []
    for i, n in enumerate(sorted((x for x in names if re.match(r"^ppt/slides/slide\d+\.xml$", x)),
                                 key=lambda x: int(re.findall(r"\d+", x)[0])), 1):
        x = etree.fromstring(z.read(n))
        for para in x.iter(A + "p"):
            t = "".join(r.text or "" for r in para.iter(A + "t")).strip()
            if t and (sgdeck.PROMPT_RE.search(t.lower()) or re.search(r"lorem ipsum|click to (add|edit)", t, re.I)):
                pr_p.append(f"{n}: prompt/placeholder text '{t[:60]}'")
    check("no template prompt or dummy text anywhere on slides", pr_p)

    # --- waivers ----------------------------------------------------------------------------------------------
    wv_p = [f"waiver '{k}' is not a deck-level rule (only {sorted(sgdeck.WAIVABLE)})" for k in waivers if k not in sgdeck.WAIVABLE]
    wv_p += [f"waiver '{k}' has no written reason" for k, v in waivers.items() if len(str(v).strip()) < 10]
    check("waivers recorded in the deck, deck-level only, each with a reason", wv_p,
          [f"{k}: {v}  <- report to the user" for k, v in waivers.items()])

    # --- infographic plan -------------------------------------------------------------------------------------
    if plan_path is None:
        for cand in (os.path.splitext(path)[0] + ".plan.json", os.path.join(os.path.dirname(os.path.abspath(path)), "plan.json")):
            if os.path.isfile(cand):
                plan_path = cand
                break
    t1 = "plan: every planned visual is on its slide, chart numbers equal the plan data, plan valid, excluded lines absent"
    t3 = (f"content coverage: every draft key point and content point is in the deck text or notes "
          f"(fuzzy, >= {coverage.THRESHOLD:.0%} of its words on one slide; excluded lines skipped)")
    t2 = "no invented numbers: every number on the slides occurs in the source draft"
    if plan_path:
        plan, src_text, src = planlib.load(plan_path)
        print(f"      (plan {plan_path}; source {src})")
        mp = os.path.join(os.path.dirname(os.path.abspath(plan_path)), "match.json")
        match = json.load(open(mp, encoding="utf-8")) if os.path.isfile(mp) else None
        print(f"      (match {mp})" if match else "      (no match.json next to the plan - matched layouts not checked)")
        check(t1, [f"plan.json: {x}" for x in planlib.validate(plan, src_text)] + planlib.check_deck(prs, plan, match))
        check(t2, planlib.invented_numbers(prs, src_text) if src_text is not None else ["source draft not readable"])
        D = draft_check.parse(src_text) if src_text else None
        if D and D.get("sections") and any(sec["slides"] for sec in D["sections"]):
            miss, n_ = coverage.coverage(prs, D, plan)
            check(t3 + f" ({n_ - len(miss)}/{n_} lines)", miss)
        else:
            print(f"SKIP  {t3} (plan source is not a standard draft)")
            skipped.append("coverage")
    else:
        for key, t in zip(SKIP_KEYS, (t1, t2, t3)):
            print(f"SKIP  {t} (no plan.json - pass --plan)")
            skipped.append(key)
    total = len(results) + len(skipped)
    if total != CHECK_COUNT:      # a check was added or removed without updating CHECK_COUNT / the docs
        print(f"\nverify_deck: internal error - ran {total} checks, CHECK_COUNT is {CHECK_COUNT}")
        return 2
    passed, failed = sum(results), len(results) - sum(results)
    ok = failed == 0 and not (strict and skipped)
    print(f"\n{passed} passed · {failed} failed · {len(skipped)} skipped (of {total})")
    if skipped:
        print("skipped: " + ", ".join(skipped))
        if strict:
            print("--strict: a skipped check fails the deck")
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    plan_arg = None
    strict = "--strict" in args
    if strict:
        args.remove("--strict")
    if "--plan" in args:
        k = args.index("--plan")
        if k + 1 >= len(args):
            sys.exit("verify_deck: --plan needs a path to plan.json")
        plan_arg = args[k + 1]
        del args[k:k + 2]
        if not os.path.isfile(plan_arg):
            sys.exit(f"verify_deck: no such plan file: {plan_arg}")
    if len(args) != 1:
        sys.exit(__doc__)
    if not os.path.isfile(args[0]):
        sys.exit(f"verify_deck: no such file: {args[0]} (did the build fail before d.save()?)")
    if not zipfile.is_zipfile(args[0]):
        sys.exit(f"verify_deck: {args[0]} is not a .pptx (zip) file")
    sys.exit(main(args[0], plan_arg, strict))

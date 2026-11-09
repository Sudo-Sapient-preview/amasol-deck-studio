"""Standard structured draft checker (reference/standard-draft.md).

    python3 scripts/draft_check.py draft.md                    # PASS/FAIL per rule with line refs, exit 1 on FAIL
    python3 scripts/draft_check.py draft.md --autofix [--out fixed.md]   # safe fixes, then re-check
    python3 scripts/draft_check.py draft.md --report           # input type, edits and flagged items (hand-off)
    python3 scripts/draft_check.py draft.md --json             # parsed draft as JSON (for the planner)

File layout (canonical form written by --autofix):
    ---                      YAML-style header: key: value lines (header may also be a ```yaml fenced block)
    title: "..."
    ...
    ---
    ## AGENDA                optional; '- item' lines; rebuilt from the sections by --autofix
    ## SECTION: <name>
    ### SLIDE <n>: <headline>
    purpose: ...
    key_point: ...
    content:
      - point
    data:
      - label: "..."   value: "..."   source: "..."   [flag: assumption]
    companies: [a, b]
    visual_hint: ...
    notes: |
      text
    flags: [edited]
    ## CLOSING
    closing_message: "..."
    contact: "..."

Safe autofixes (each recorded in the slide's notes and flagged 'edited'): split slides with more than 5 points,
merge one-slide sections into a neighbour, build/refresh the agenda from the sections, renumber slides.
Not auto-fixable (need a human or the intake step): missing header fields, < 3 points, long points or headlines,
bad enum values, data without a source, assumed title without title_reason, topic-label headlines."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_HEADER = ("title", "audience", "goal", "length", "language", "input_type")
HEADER_KEYS = REQUIRED_HEADER + ("assumed", "subtitle", "presenter", "date", "source_files", "title_reason")
ASSUMABLE = ("audience", "goal", "title", "length")  # filled by the agent when not stated in the input
# title: bare-request forged titles; length: bare count picked from topic breadth
PLACEHOLDER_RE = re.compile(r"^\s*(to[- ]be[- ]filled|tbd|tbc|todo|tba|n/?a|none|unknown|\?+|\.\.\.|…|-+|"
                            r"<[^>]*>|\[[^\]]*\]|\{[^}]*\}|structured \| raw \| bare|who it is for|"
                            r"what the audience should think or do after it|deck title)\s*(\(.*\)|[-–:;,].*)?\s*$", re.I)
# a trailing note does not make a placeholder a value: "to-be-filled (notes do not name the audience)" still fails
PURPOSES = {"intro", "problem", "solution", "proof", "process", "comparison", "data", "team", "summary", "cta"}
VISUALS = {"none", "infographic", "chart", "icons", "key-number", "key-points", "image", "table", "quote"}
KEY_POINTS = (4, 6)        # visual_hint key-points: exactly 4 (Key Slide 1) or 6 (Key Slide 2) short points
FLAGS = {"assumption", "needs-source", "to-be-filled", "edited", "excluded"}
TYPES = {"structured", "raw", "bare"}
MIN_PTS, MAX_PTS = 3, 5
PT_WORDS, PT_WORDS_HARD = 15, 18          # "about 15": 16-18 warn, > 18 fail
HEAD_CH, HEAD_CH_HARD = 60, 66            # "max ~60": 61-66 warn, > 66 fail
SLIDE_FIELDS = ("purpose", "key_point", "content", "data", "companies", "visual_hint", "notes", "flags")


def unq(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def strip_comment(v):
    # drop '# comment' outside quotes
    out, q = [], None
    for i, c in enumerate(v):
        if q:
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c == "#" and (i == 0 or v[i - 1].isspace()):
            break
        out.append(c)
    return "".join(out).strip()


def parse_list(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [unq(x) for x in v[1:-1].split(",") if x.strip()]
    return [unq(v)] if v else []


def parse_data_item(s):
    item = {}
    for m in re.finditer(r'(\w+)\s*:\s*("[^"]*"|\'[^\']*\'|[^\s"\']+(?:\s+(?!\w+\s*:)[^\s"\']+)*)', s):
        item[m.group(1)] = unq(m.group(2))
    return item


def parse(text):
    lines = text.splitlines()
    d = {"header": {}, "header_line": {}, "agenda": None, "agenda_line": None, "sections": [], "closing": {},
         "closing_line": None, "errors": []}
    i, n = 0, len(lines)
    while i < n and not lines[i].strip():
        i += 1
    # ---- header
    if i < n and lines[i].strip() in ("---", "```yaml", "```yml"):
        end = "---" if lines[i].strip() == "---" else "```"
        i += 1
        while i < n and lines[i].strip() != end:
            m = re.match(r"^\s*([A-Za-z_]+)\s*:\s*(.*)$", lines[i])
            if m:
                k, v = m.group(1), strip_comment(m.group(2))
                d["header"][k] = parse_list(v) if k in ("source_files", "assumed") else unq(v)
                d["header_line"][k] = i + 1
            i += 1
        i += 1
    else:
        d["errors"].append((i + 1, "no header block ('---' front matter or ```yaml) at the top"))
    sec = slide = None
    field = None
    mode = None   # agenda | slide | closing
    while i < n:
        raw = lines[i]; s = raw.strip(); ln = i + 1; i += 1
        if s.startswith("```"):
            continue
        m = re.match(r"^##\s+AGENDA\s*$", s, re.I)
        if m:
            d["agenda"], d["agenda_line"], mode, slide = [], ln, "agenda", None
            continue
        m = re.match(r"^##\s+SECTION\s*:\s*(.+)$", s, re.I)
        if m:
            sec = {"name": m.group(1).strip(), "line": ln, "slides": []}
            d["sections"].append(sec); mode, slide = "section", None
            continue
        m = re.match(r"^###\s+SLIDE\s*(\d*)\s*:\s*(.*)$", s, re.I)
        if m:
            if sec is None:
                d["errors"].append((ln, "SLIDE before any SECTION"))
                sec = {"name": "", "line": ln, "slides": []}; d["sections"].append(sec)
            slide = {"n": int(m.group(1)) if m.group(1) else None, "headline": m.group(2).strip(), "line": ln,
                     "purpose": None, "key_point": [], "content": [], "data": [], "companies": [],
                     "visual_hint": None, "notes": "", "flags": [], "lines": {}}
            sec["slides"].append(slide); mode, field = "slide", None
            continue
        if re.match(r"^##\s+CLOSING\s*$", s, re.I):
            d["closing_line"], mode, slide = ln, "closing", None
            continue
        if re.match(r"^#{1,2}\s", s):     # other heading: ignore
            mode, slide = None, None
            continue
        if not s:
            if field == "notes" and slide is not None:
                slide["notes"] += "\n"
            continue
        if mode == "agenda":
            if s.startswith("- "):
                d["agenda"].append(s[2:].strip())
            continue
        if mode == "closing":
            m = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", s)
            if m:
                d["closing"][m.group(1)] = unq(strip_comment(m.group(2)))
            continue
        if mode != "slide":
            continue
        m = re.match(r"^([a-z_]+)\s*:\s*(.*)$", raw)   # field lines start at column 0
        if m and m.group(1) in SLIDE_FIELDS:
            k, v = m.group(1), m.group(2)
            field = k; slide["lines"].setdefault(k, ln)
            if k == "notes":
                slide["notes"] = "" if v.strip() in ("|", ">") else unq(v.strip())
            elif k == "key_point":
                if v.strip():
                    slide["key_point"].append((ln, unq(v.strip())))
            elif k in ("companies", "flags"):
                slide[k] = parse_list(strip_comment(v))
            elif k in ("purpose", "visual_hint"):
                slide[k] = unq(strip_comment(v)) or None
            continue
        if field == "notes":
            slide["notes"] += (("\n" if slide["notes"] and not slide["notes"].endswith("\n") else "") + s)
        elif field == "content" and s.startswith("- "):
            slide["content"].append((ln, s[2:].strip()))
        elif field == "data" and s.startswith("- "):
            it = parse_data_item(s[2:]); it["_line"] = ln
            slide["data"].append(it)
        elif field == "key_point":
            slide["key_point"].append((ln, s))
    for sec in d["sections"]:
        for sl in sec["slides"]:
            sl["notes"] = sl["notes"].strip()
    return d


def words(t):
    return len(re.findall(r"\S+", t))

# Claim-like headlines need a verb, a colon claim, or more than 3 content words.
CLAIM_VERBS = re.compile(
    r"\b(is|are|was|were|be|been|being|has|have|had|will|can|must|need|needs|make|makes|made|"
    r"turn|turns|run|runs|build|builds|deliver|delivers|show|shows|help|helps|let|lets|"
    r"keep|keeps|bring|brings|give|gives|get|gets|take|takes|put|puts|set|sets|lead|leads|"
    r"drive|drives|enable|enables|reduce|reduces|increase|increases|improve|improves|"
    r"create|creates|provide|provides|offer|offers|support|supports|transform|transforms|"
    r"outgrow|outgrows|become|becomes|mean|means|do|does|did|should|would|could|to|"
    r"goes|go|going|comes|come|works|work|working)\b", re.I)


def is_topic_label(headline):
    """1-3 word noun-phrase with no verb/claim -> topic label (WARN, agent should rewrite).

    Skeleton slots that still start with 'to-be-filled:' are skipped – they are unfinished, not labels.
    """
    raw = (headline or "").strip()
    if re.match(r"^to[- ]be[- ]filled\s*:", raw, re.I):
        return False
    h = raw.strip().strip("\"'")
    if not h:
        return False
    # colon / dash claims ("Monitoring: one view") count as messages
    if re.search(r"[:–—]", h):
        return False
    toks = re.findall(r"[A-Za-z0-9][\w'%-]*", h)
    if len(toks) > 3:
        return False
    if CLAIM_VERBS.search(h):
        return False
    return True



def intake_for(path):
    """intake.json next to draft.md (written by intake.py classify), or None"""
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(path)), "intake.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def check(d, intake=None):
    """returns list of (rule, status, [(line, msg)]) with status PASS/WARN/FAIL"""
    R = []
    def rule(name, fails, warns=()):
        R.append((name, "FAIL" if fails else ("WARN" if warns else "PASS"), list(fails) + list(warns)))
    h, hl = d["header"], d["header_line"]
    f = [(ln, m) for ln, m in d["errors"]]
    for k in REQUIRED_HEADER:
        v = h.get(k, "")
        if isinstance(v, list) or not str(v).strip():
            f.append((hl.get(k, 1), f"header field '{k}' missing or empty"))
        elif PLACEHOLDER_RE.match(str(v)):
            f.append((hl.get(k, 1), f"header field '{k}' is a placeholder ('{v}'), not a value - a required field "
                      f"cannot be to-be-filled; write a best value and list '{k}' in 'assumed: [...]'"
                      if k in ASSUMABLE else f"header field '{k}' is a placeholder ('{v}'), not a value"))
    if h.get("input_type") and h["input_type"] not in TYPES:
        f.append((hl["input_type"], f"input_type '{h['input_type']}' not one of {sorted(TYPES)}"))
    if h.get("length") and not str(h["length"]).isdigit():
        f.append((hl["length"], "length must be a whole number of slides"))
    if h.get("language") and h["language"] not in ("en", "de"):
        f.append((hl["language"], "language must be en or de"))
    rule("1 header: required fields", f)
    f = []
    asm = h.get("assumed") or []
    if isinstance(asm, str):
        asm = parse_list(asm)
    for a in asm:
        if a not in ASSUMABLE:
            f.append((hl.get("assumed", 1), f"assumed: '{a}' not one of {list(ASSUMABLE)}"))
    if intake:
        for k in intake.get("assume_header") or []:
            if k not in asm:
                f.append((hl.get(k, 1), f"the input does not state the {k} (intake.json) but the header fills it "
                          f"silently - add '{k}' to 'assumed: [...]'"))
    rule("1b header: assumed fields flagged", f)
    slides = [s for sec in d["sections"] for s in sec["slides"]]
    rule("2 at least one section and slide", [] if slides else [(1, "no SECTION/SLIDE blocks found")])
    f, w = [], []
    for s in slides:
        k = len(s["content"])
        if s["visual_hint"] == "quote" and 1 <= k <= 2:          # a quote slide: the quote (+ attribution line)
            continue
        if s["visual_hint"] == "key-points":                     # a key-message slide: 4 pills or 6 tiles
            if k not in KEY_POINTS:
                f.append((s["line"], f"SLIDE {s['n']}: visual_hint key-points takes 4 or 6 points, not {k}"))
            continue
        if not MIN_PTS <= k <= MAX_PTS:
            f.append((s["line"], f"SLIDE {s['n']}: {k} points (needs {MIN_PTS}-{MAX_PTS})" +
                      (" - autofix splits it" if k > MAX_PTS else "")))
    rule("3 3-5 points per slide", f)
    f, w = [], []
    for s in slides:
        for ln, p in s["content"]:
            c = words(p)
            if c > PT_WORDS_HARD:
                f.append((ln, f"point has {c} words (about {PT_WORDS} max): '{p[:50]}...'"))
            elif c > PT_WORDS:
                w.append((ln, f"point has {c} words (about {PT_WORDS}): tighten if possible"))
    rule("4 points about 15 words each", f, w)
    f, w = [], []
    for s in slides:
        c = len(s["headline"])
        if not c:
            f.append((s["line"], "empty headline"))
        elif c > HEAD_CH_HARD:
            f.append((s["line"], f"headline {c} chars (max ~{HEAD_CH})"))
        elif c > HEAD_CH:
            w.append((s["line"], f"headline {c} chars (max ~{HEAD_CH})"))
    rule("5 headline max ~60 characters", f, w)
    f = []
    for s in slides:
        if len(s["key_point"]) != 1 or not s["key_point"][0][1].strip():
            f.append((s["line"], f"SLIDE {s['n']}: needs exactly one key_point line (has {len(s['key_point'])})"))
    rule("6 one key_point per slide", f)
    f = [(sec["line"], f"section '{sec['name']}' has {len(sec['slides'])} slide(s) - autofix merges it")
         for sec in d["sections"] if len(sec["slides"]) < 2]
    rule("7 at least 2 slides per section", f)
    f = []
    for s in slides:
        L = s["lines"]
        if s["purpose"] is None:
            f.append((s["line"], f"SLIDE {s['n']}: purpose missing"))
        elif s["purpose"] not in PURPOSES:
            f.append((L.get("purpose", s["line"]), f"purpose '{s['purpose']}' not in {sorted(PURPOSES)}"))
        if s["visual_hint"] is not None and s["visual_hint"] not in VISUALS:
            f.append((L.get("visual_hint", s["line"]), f"visual_hint '{s['visual_hint']}' not in {sorted(VISUALS)}"))
        for fl in s["flags"]:
            if fl not in FLAGS:
                f.append((L.get("flags", s["line"]), f"flag '{fl}' not in {sorted(FLAGS)}"))
        for it in s["data"]:
            if it.get("flag") and it["flag"] not in FLAGS:
                f.append((it["_line"], f"data flag '{it['flag']}' not in {sorted(FLAGS)}"))
    rule("8 purpose / visual_hint / flags values", f)
    f = []
    for s in slides:
        for it in s["data"]:
            if not it.get("label") or not it.get("value"):
                f.append((it["_line"], "data item needs label and value"))
            assumed = it.get("flag") == "assumption" or "assumption" in s["flags"]
            if not it.get("source", "").strip() and not assumed:
                f.append((it["_line"], f"data '{it.get('label', '?')}' has no source and is not flagged assumption"))
    rule("9 data items have a source (or are flagged assumption)", f)
    f, w = [], []
    if not d["closing"].get("closing_message"):
        f.append((d["closing_line"] or 1, "CLOSING block with closing_message missing"))
    rule("10 closing", f)
    names = [sec["name"] for sec in d["sections"]]
    if d["agenda"] is not None and d["agenda"] != names:
        rule("11 agenda matches the sections", [], [(d["agenda_line"], "agenda differs from section names - autofix rebuilds it")])
    else:
        rule("11 agenda matches the sections", [])
    ns = [s["n"] for s in slides]
    rule("12 slides numbered 1..n", [], [] if ns == list(range(1, len(ns) + 1)) else [(slides[0]["line"] if slides else 1, "slide numbers not 1..n - autofix renumbers")])
    # 13: bare-request forged title must carry a one-line title_reason (header field or notes)
    f = []
    asm = h.get("assumed") or []
    if isinstance(asm, str):
        asm = parse_list(asm)
    if "title" in asm:
        reason = (h.get("title_reason") or "").strip()
        if not reason:
            blob = "\n".join(s.get("notes") or "" for s in slides)
            m = re.search(r"(?im)^\s*title_reason\s*:\s*(.+)$", blob)
            reason = (m.group(1).strip() if m else "")
        if not reason:
            f.append((hl.get("title", 1), "assumed title has no title_reason - add a one-line reason tying the "
                      "title to the ask (topic / audience / goal) in the header field 'title_reason:' "
                      "or as 'title_reason: ...' in a slide's notes"))
    rule("13 assumed title has a title_reason", f)
    # 14: topic-label headlines (WARN) - agent must rewrite as a claim using only input facts
    w = []
    for s in slides:
        if is_topic_label(s.get("headline") or ""):
            w.append((s["line"], f"SLIDE {s['n']}: headline looks like a topic label ('{s['headline']}') - "
                      "rewrite as a claim that suits the slide and audience (keep user wording when it already works)"))
    rule("14 headlines are claims, not topic labels", [], w)
    # 15: key-points slides - Key Slide boxes are much smaller than the general limits (WARN; the matcher enforces)
    w = []
    try:
        import capacity
        boxes = capacity.CAP.get("layouts", {})
    except Exception:                                  # capacity data unavailable: skip the measured check
        boxes = {}
    for s in slides:
        if s["visual_hint"] != "key-points" or len(s["content"]) not in KEY_POINTS or not boxes:
            continue
        lay = "Key Slide 1" if len(s["content"]) == 4 else "Key Slide 2"
        kp = " ".join(t for _, t in s["key_point"])
        for what, idx, text in [("headline", 10, s["headline"]), ("key point", 13, kp)] + [
                (f"point {k + 1}", idx, t) for k, (idx, (_, t)) in enumerate(zip((14, 16, 17, 18, 19, 20), s["content"]))]:
            spec = boxes.get(lay, {}).get(str(idx))
            msg = spec and text and capacity.check_box([(text, 0, None, None, False, None)], spec)
            if msg:
                w.append((s["line"], f"SLIDE {s['n']}: {what} will not fit {lay} ({msg}) - shorten it now"))
    rule("15 key-points text fits the Key Slide boxes", [], w)
    return R


def note(s, msg):
    s["notes"] = (s["notes"] + "\n" if s["notes"] else "") + "[edited] " + msg
    if "edited" not in s["flags"]:
        s["flags"].append("edited")


def autofix(d):
    log = []
    for sec in d["sections"]:                      # split slides with > 5 points
        out = []
        for s in sec["slides"]:
            pts = s["content"]
            if len(pts) <= MAX_PTS or (s["visual_hint"] == "key-points" and len(pts) in KEY_POINTS):
                out.append(s); continue
            k = -(-len(pts) // MAX_PTS)
            size = -(-len(pts) // k)
            chunks = [pts[j:j + size] for j in range(0, len(pts), size)]
            if len(chunks[-1]) < MIN_PTS and len(chunks) > 1:   # rebalance
                size = -(-len(pts) // len(chunks)); chunks = [pts[j:j + size] for j in range(0, len(pts), size)]
            base = s["headline"]
            for ci, ch in enumerate(chunks):
                t = dict(s, content=ch, flags=list(s["flags"]), data=s["data"] if ci == 0 else [],
                         companies=s["companies"] if ci == 0 else [], lines=dict(s["lines"]))
                t["headline"] = f"{base} ({ci + 1}/{len(chunks)})"
                note(t, f"split from one slide with {len(pts)} points into {len(chunks)} slides (part {ci + 1}).")
                out.append(t)
            log.append(f"split slide '{base}' ({len(pts)} points) into {len(chunks)} slides")
        sec["slides"] = out
    changed = True                                  # merge one-slide sections
    while changed and len(d["sections"]) > 1:
        changed = False
        for idx, sec in enumerate(d["sections"]):
            if len(sec["slides"]) < 2:
                tgt = d["sections"][idx - 1] if idx > 0 else d["sections"][idx + 1]
                for s in sec["slides"]:
                    note(s, f"section '{sec['name']}' had one slide; merged into section '{tgt['name']}'.")
                if idx > 0:
                    tgt["slides"].extend(sec["slides"])
                else:
                    tgt["slides"][:0] = sec["slides"]
                log.append(f"merged one-slide section '{sec['name']}' into '{tgt['name']}'")
                del d["sections"][idx]; changed = True
                break
    names = [sec["name"] for sec in d["sections"]]
    if d["agenda"] != names:
        log.append("agenda built from the sections" if d["agenda"] is None else "agenda rebuilt to match the sections")
        d["agenda"] = names
    k = 0
    for sec in d["sections"]:
        for s in sec["slides"]:
            k += 1
            if s["n"] != k:
                s["n"] = k
    return log


def q(v):
    return '"' + str(v).replace('"', "'") + '"'


def dump(d):
    h = d["header"]; o = ["---"]
    for k in HEADER_KEYS + tuple(x for x in h if x not in HEADER_KEYS):
        if k in h:
            v = h[k]
            o.append(f"{k}: " + ("[" + ", ".join(q(x) for x in v) + "]" if isinstance(v, list)
                                 else (str(v) if k in ("length", "language", "input_type") else q(v))))
    o += ["---", ""]
    if d["agenda"] is not None:
        o += ["## AGENDA"] + [f"- {a}" for a in d["agenda"]] + [""]
    for sec in d["sections"]:
        o += [f"## SECTION: {sec['name']}", ""]
        for s in sec["slides"]:
            o.append(f"### SLIDE {s['n']}: {s['headline']}")
            if s["purpose"]: o.append(f"purpose: {s['purpose']}")
            for _, kp in s["key_point"]: o.append(f"key_point: {kp}")
            o.append("content:"); o += [f"  - {p}" for _, p in s["content"]]
            if s["data"]:
                o.append("data:")
                for it in s["data"]:
                    o.append("  - " + "   ".join(f"{k}: {q(v)}" for k, v in it.items() if k != "_line"))
            if s["companies"]: o.append("companies: [" + ", ".join(s["companies"]) + "]")
            if s["visual_hint"]: o.append(f"visual_hint: {s['visual_hint']}")
            if s["notes"]:
                o.append("notes: |"); o += [("  " + l) if l.strip() else "" for l in s["notes"].splitlines()]
            o.append("flags: [" + ", ".join(s["flags"]) + "]")
            o.append("")
    o += ["## CLOSING"] + [f"{k}: {q(v)}" for k, v in d["closing"].items()] + [""]
    return "\n".join(o)


def report(d):
    h = d["header"]; o = [f"Input type: {h.get('input_type', '?')}", f"Deck: {h.get('title', '?')} ({sum(len(s['slides']) for s in d['sections'])} slides)"]
    ed, fl = [], []
    for sec in d["sections"]:
        for s in sec["slides"]:
            if "edited" in s["flags"]:                 # an edit is a notes line starting with [edited]
                lines = [l[9:].strip() for l in s["notes"].splitlines() if l.startswith("[edited]")]
                ed += [f"SLIDE {s['n']}: {l}" for l in lines] or [f"SLIDE {s['n']}: edited (no [edited] note line - "
                                                                 "see the slide notes)"]
            others = [x for x in s["flags"] if x != "edited"]
            dfl = [f"{it.get('label')}={it.get('flag')}" for it in s["data"] if it.get("flag")]
            if others or dfl: fl.append(f"SLIDE {s['n']} '{s['headline']}': " + ", ".join(others + dfl))
    asm = h.get("assumed") or []
    o.append(f"Assumed header fields ({len(asm)}):")
    o += [f"  {k}: '{h.get(k, '')}' - assumption, not stated in the input; confirm with the user" for k in asm] or ["  none"]
    o.append(f"Edits ({len(ed)}):"); o += ["  " + x for x in ed] or ["  none"]
    o.append(f"Flagged items ({len(fl)}):"); o += ["  " + x for x in fl] or ["  none"]
    return "\n".join(o)


def print_check(R, path):
    bad = 0
    for name, st, items in R:
        print(f"{'  ' if st == 'PASS' else ('~ ' if st == 'WARN' else 'X ')}{st:4} {name}")
        for ln, m in items:
            print(f"        {path}:{ln}: {m}")
        bad += st == "FAIL"
    print(f"\n{'PASS' if not bad else 'FAIL'}: {len(R) - bad}/{len(R)} rules pass" + (f", {bad} fail" if bad else ""))
    return bad


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    path = argv[0]
    d = parse(open(path, encoding="utf-8").read())
    if "--json" in argv:
        print(json.dumps(d, indent=1, ensure_ascii=False, default=str)); return 0
    if "--report" in argv:
        print(report(d)); return 0
    if "--autofix" in argv:
        log = autofix(d)
        out = argv[argv.index("--out") + 1] if "--out" in argv else path
        open(out, "w", encoding="utf-8").write(dump(d))
        print(f"autofix: {len(log)} content change(s) -> {out}" + ("" if log else " (formatting normalised: header "
              "order, quotes)")); [print("  - " + x) for x in log]
        path = out; d = parse(open(out, encoding="utf-8").read())
    return 1 if print_check(check(d, intake_for(path)), path) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

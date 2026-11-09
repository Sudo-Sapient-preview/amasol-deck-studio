"""Intake step 0: classify the input as structured, raw or bare and record why (reference/standard-draft.md).

    python3 scripts/intake.py classify INPUT [INPUT ...] --out DIR     # files (draft, notes, article text, ...)
    python3 scripts/intake.py classify --text "a 10 slide deck on ..." [INPUT ...] --out DIR
    python3 scripts/intake.py classify brochure.pdf https://example.com/article --out DIR   # PDF / URL inputs

PDF and URL inputs are converted to text first and saved next to intake.json (DIR/source-<n>.txt): a PDF with
`pdftotext -layout` (poppler-utils), a URL fetched with urllib and stripped to its main text (<article>/<main> if
present, else <body>; script, style, nav, header, footer, aside and forms dropped). A PDF/URL text or a long pasted
article (>= 400 words of running prose) is classified RAW: real facts without a slide shape, even when it has
headings - its headings are document structure, not slides. A PDF whose pages are 'Slide N' / 'Folie N' units is
classified STRUCTURED: keep its slide order, validate against reference/standard-draft.md; if it meets or exceeds
the standard, use it as is; if it falls short (missing header fields, < 3 points, no agenda, one-slide sections),
fill the gaps to the standard (draftgen topup / draft_check --autofix + agent edits) and flag each fix 'edited'.

Rules (in this order):
  structured - the input already has a slide or section shape: >= 3 slide/section units ('Slide 3', '## heading',
               '## SECTION:'), >= 70 % of them with content under them;
  bare       - a short ask: under ~150 words, no slide units, < 4 bullets, no facts beyond the topic
               (no numbers, at most 3 capitalised names besides the topic);
  raw        - everything else: real facts but no slide shape (notes, a pasted article, a PDF/URL text dump).
Mixed input (several parts, e.g. a short ask + notes): each part is measured and the most content-rich part
(most content words) decides the type. Writes DIR/intake.json with the type, the reason and the signals; the
intake also records whether the input states the deck's audience and goal ("stated", "assume_header"); fields
it does not state are still filled in the draft, but listed in the header as 'assumed: [audience, goal]'. The
agent then writes DIR/draft.md in the standard format and runs scripts/draft_check.py on it."""
import json, os, re, sys

STRUCT_MIN_UNITS, STRUCT_MIN_FILLED, BARE_MAX_WORDS = 3, 0.7, 150
UNIT_RE = re.compile(r"^\s{0,3}(#{1,4}\s*)?(slide|folie|page|seite)\s*\d+\b", re.I)
SECTION_RE = re.compile(r"^\s{0,3}#{2,3}\s+(SECTION|SLIDE)\b", re.I)
HEAD_RE = re.compile(r"^\s{0,3}#{2,4}\s+\S")
BULLET_RE = re.compile(r"^\s*([-*•·]|\d+[.)])\s+\S")
NUM_RE = re.compile(r"(?<![\w-])\d[\d.,]*\s*(%|\+|k|m|years?)?", re.I)
AUD_RE = re.compile(r"(\baudience\s*[:=]|target audience|\bfor (an? |the |our )?(cio|cto|ceo|cfo|board|management|"
                    r"leadership|executives?|client|customers?|partners?|investors?|team|sales|it (leadership|team)s?)\b|"
                    r"\b(aimed at|intended for|presented to|pitch to)\b)", re.I)
GOAL_RE = re.compile(r"(\b(deck|presentation|pitch|talk)\s+goal\b|\bgoal of (the|this) (deck|presentation|talk)\b|"
                     r"^\s*(deck )?goal\s*:|\bobjective\s*:|\bso that (they|the audience|the client|the board)\b|"
                     r"\b(to convince|call to action|we want (them|the audience) to|desired outcome)\b)", re.I | re.M)
REQ_STOP = {"deck", "slide", "slides", "cio", "ceo", "cto", "it", "a", "i", "the", "we", "make", "create", "please"}


def measure(text):
    lines = text.splitlines()
    explicit = any(UNIT_RE.match(l) or SECTION_RE.match(l) for l in lines)
    starts = (lambda l: UNIT_RE.match(l) or SECTION_RE.match(l)) if explicit else HEAD_RE.match
    units, cur = [], None
    for l in lines:
        if starts(l):
            cur = {"head": l.strip(), "content": 0}; units.append(cur)
        elif cur is not None and l.strip() and not re.match(r"^\s*(---+|\[.*\])\s*$", l):
            cur["content"] += 1
    su = units if (explicit or len(units) >= STRUCT_MIN_UNITS) else []
    words = re.findall(r"\w+", text)
    caps = {w for w in re.findall(r"\b[A-Z][\w&-]+", text) if w.lower() not in REQ_STOP}
    return {"words": len(words), "slide_units": len(su),
            "units_with_content": sum(1 for u in su if u["content"]), "explicit_markers": explicit,
            "bullets": sum(1 for l in lines if BULLET_RE.match(l)),
            "numbers": len([m for m in NUM_RE.findall(text)]) - len(re.findall(r"\b\d+\s*slides?\b", text, re.I)),
            "names": sorted(caps),
            "states_audience": bool(AUD_RE.search(text)), "states_goal": bool(GOAL_RE.search(text))}


def propose(m):
    if m["slide_units"] >= STRUCT_MIN_UNITS and m["units_with_content"] >= STRUCT_MIN_FILLED * m["slide_units"]:
        return "structured", (f"{m['slide_units']} slide/section units, {m['units_with_content']} with content -> "
                              "already has a slide shape: map field by field, keep wording and order")
    if m["words"] < BARE_MAX_WORDS and m["slide_units"] == 0 and m["bullets"] < 4 and m["numbers"] <= 0 \
            and len(m["names"]) <= 3:
        return "bare", (f"{m['words']} words, no slide units, {m['bullets']} bullets, no numbers, names "
                        f"{m['names'] or 'none'} = topic only -> short ask: generate content, flag every fact assumption")
    return "raw", (f"{m['words']} words, {m['numbers']} numbers, {m['bullets']} bullets but "
                   f"{m['slide_units']} slide units -> real facts without a slide shape: group into the storyline "
                   "from input facts only, mark gaps")


def pdf_text(path):
    import subprocess
    r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"intake: pdftotext failed on {path}: {r.stderr.strip()[:200]} (apt install poppler-utils)")
    return re.sub(r"[ \t]{3,}", "  ", r.stdout.replace("\f", "\n"))


def url_text(url):
    import html as H, urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (sgdeck intake)", "Accept-Language": "en,de"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
    for tag in ("script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "template"):
        raw = re.sub(rf"(?is)<{tag}\b.*?</{tag}\s*>", " ", raw)
    tw = lambda h: len(re.sub(r"<[^>]+>", " ", h).split())
    cands = [m.group(0) for m in re.finditer(r"(?is)<(main|article)\b.*?</\1\s*>", raw)]
    best = max(cands, key=tw) if cands else ""
    if tw(best) < 150:                       # a teaser card, not the page's main text: use the whole body
        m = re.search(r"(?is)<body\b.*?</body\s*>", raw)
        best = m.group(0) if m else raw
    body = best
    body = re.sub(r"(?i)<li\b[^>]*>", "\n- ", body)
    body = re.sub(r"(?i)<h([1-4])\b[^>]*>", lambda k: "\n\n" + "#" * (int(k.group(1)) + 1) + " ", body)
    body = re.sub(r"(?i)</?(p|div|section|br|tr|h[1-6]|ul|ol|table)\b[^>]*>", "\n", body)
    body = H.unescape(re.sub(r"<[^>]+>", " ", body))
    lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in body.splitlines()]
    out, prev = [], None
    for l in lines:
        if l and l != prev and (len(l.split()) >= 3 or l.startswith(("#", "-"))):
            out.append(l)
        prev = l
    return "\n".join(out)


def load_input(a, out, k):
    """(name, text, origin): files as-is; .pdf via pdftotext; http(s) URLs fetched and stripped to the main text."""
    if re.match(r"^https?://", a):
        t, origin = url_text(a), "url"
    elif a.lower().endswith(".pdf"):
        t, origin = pdf_text(a), "pdf"
    else:
        return os.path.abspath(a), open(a, encoding="utf-8").read(), "text"
    p = os.path.join(out, f"source-{k}.txt")
    open(p, "w", encoding="utf-8").write(t)
    return f"{a} -> {p}", t, origin


def classify(argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else "."
    os.makedirs(out, exist_ok=True)
    parts = []
    if "--text" in argv:
        t = argv[argv.index("--text") + 1]
        open(os.path.join(out, "request.txt"), "w", encoding="utf-8").write(t.strip() + "\n")
        parts.append(("request.txt (typed)", t))
    skip = {argv.index(k) + 1 for k in ("--out", "--text") if k in argv}
    for i, a in enumerate(argv):
        if i not in skip and not a.startswith("--"):
            parts.append(load_input(a, out, len(parts) + 1))
    parts = [p if len(p) == 3 else (p[0], p[1], "text") for p in parts]
    res = []
    for name, t, origin in parts:
        m = measure(t); k, why = propose(m)
        prose = m["words"] >= 400 and m["bullets"] < m["words"] / 60
        if k == "structured" and (origin in ("pdf", "url") or prose) and not m.get("explicit_markers"):
            k, why = "raw", (f"{origin if origin != 'text' else 'long pasted article'}: {m['words']} words with "
                             f"{m['slide_units']} headings but no 'Slide N' units -> document structure, not slides: "
                             "treat as raw notes")
        elif k == "structured" and origin == "pdf" and m.get("explicit_markers"):
            why = (f"slide-marked PDF: {m['slide_units']} 'Slide N' units -> structured; validate against the "
                   "standard draft - use as is if it meets/exceeds it, otherwise fill gaps and flag each fix edited")
        elif k == "raw" and origin != "text":
            why = f"{origin} text: " + why
        elif k == "raw" and prose:
            why = "long pasted article: " + why
        res.append({"part": name, "type": k, "reason": why, "signals": m,
                    "content_words": m["words"] if k != "bare" else 0})
    win = max(res, key=lambda r: (r["content_words"], r["signals"]["words"]))
    reason = win["reason"] + (f"; mixed input ({len(res)} parts): the most content-rich part '{win['part']}' decides"
                              if len(res) > 1 else "")
    stated = {k: any(r["signals"][f"states_{k}"] for r in res) for k in ("audience", "goal")}
    assume = [k for k, v in stated.items() if not v]
    rec = {"schema": "sgdeck-intake/3", "type": win["type"], "reason": reason, "parts": res,
           "stated": stated, "assume_header": assume,
           "draft": "draft.md", "next": "write draft.md in reference/standard-draft.md format, then "
                                         "python3 scripts/draft_check.py draft.md [--autofix]"}
    json.dump(rec, open(os.path.join(out, "intake.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if assume:
        reason += ("; NOT STATED in the input: " + ", ".join(assume) + " -> fill them in the draft header and list "
                   "them in 'assumed: [" + ", ".join(assume) + "]' (draft_check fails a silent fill)")
    print(f"{win['type'].upper()}: {reason}\nwrote {out}/intake.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] != "classify":
        print(__doc__); sys.exit(0)
    sys.exit(classify(a[1:]))

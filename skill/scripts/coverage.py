"""Content coverage: every key_point and content point of draft.md must appear in the deck text or the speaker notes.

    python3 scripts/coverage.py deck.pptx draft.md [--plan plan.json] [--threshold 0.6]
    verify_deck.py runs it as check 23 when the plan's source is a standard draft.

Matching is fuzzy and per slide: a draft line is covered when ONE slide (its shapes, tables, diagrams and notes)
contains >= THRESHOLD of the line's content words (lower-case, stop words dropped, light stemming: plural -s,
-ing, -ed; numbers must match exactly) - or a difflib ratio >= 0.8 against a sentence on that slide.
Intentionally left out (not checked): slides flagged `excluded` in draft.md, points that start with '(excluded)'
or carry '[excluded]', lines listed in plan.json `excluded` or `cut`, and header-like parts of 'Head: text'
points (the text after the colon must be covered)."""
import difflib, json, re, sys
from pptx import Presentation

THRESHOLD = 0.6
STOP = set("a an the and or of to in on for with by from at as is are be was were it its this that these those our "
           "we you they their your not no into than then so per via vs also each every all any one".split())


def stem(w):
    for suf in ("ings", "ing", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


ABBR = {"infra": "infrastructure", "govt": "government", "cos": "companies", "yrs": "years", "mgmt": "management",
        "w/": "with", "approx": "approximately", "vwfs": "volkswagen financial services", "&": "and"}


def words(t):
    t = t.lower()
    for k, v in ABBR.items():
        t = re.sub(r"(?<![\w])" + re.escape(k) + r"(?![\w])", v, t).replace("–", " ").replace("-", " ")
    return [w if w[0].isdigit() else stem(w) for w in re.findall(r"[a-z0-9äöüß][a-z0-9äöüß+%.]*", t)
            if w not in STOP]


LOGO_PREFIX = "sgdeck logo: "      # sgdeck names logo pictures this way (alt text = company name)


def _shape_text(sh):
    out = []
    if sh.shape_type == 6:                                    # group
        for s in sh.shapes:
            out += _shape_text(s)
    if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
        out.append(sh.text_frame.text)
    if getattr(sh, "has_table", False) and sh.has_table:
        out += [c.text for r in sh.table.rows for c in r.cells]
    if getattr(sh, "has_chart", False) and sh.has_chart:   # the chart's data is on the slide: categories,
        try:                                               # series names and values (legend / axis / slices)
            for plot in sh.chart.plots:
                out += [str(c) for c in plot.categories]
                for ser in plot.series:
                    out.append(str(ser.name or ""))
                    out += [f"{v:g}" for v in ser.values if v is not None]
        except Exception:
            pass
    if sh.shape_type == 13 and sh.name.startswith(LOGO_PREFIX):   # a company logo shows that company's name
        out.append(sh.name[len(LOGO_PREFIX):])
    return out



def line_score(line, haystack_words, haystack_sents, threshold=THRESHOLD):
    """Return coverage ratio of one draft line against a bag of words + sentences (same rules as coverage())."""
    body = line.split(":", 1)[1] if re.match(r"^[^:]{2,40}:\s+\S", line) else line
    w = [x for x in words(body)] or words(line)
    if not w:
        return 1.0
    r = sum(1 for x in w if x in haystack_words) / len(w)
    nums = [x for x in w if x[0].isdigit()]
    if nums and not all(x in haystack_words for x in nums):
        r = min(r, threshold - 0.01)
    if r < threshold and haystack_sents:
        q = max(difflib.SequenceMatcher(None, body.lower(), x.lower()).ratio() for x in haystack_sents)
        r = max(r, 1.0 if q >= 0.8 else 0)
    return r


def draft_points_retained(source_points, target_text, threshold=THRESHOLD):
    """True iff every source point is still covered by target_text (content + notes of a merged slide).

    Used by draftgen --apply-merge before a merge is committed: no deck yet, so we check the draft itself.
    Returns (ok, missing_list).
    """
    hw = set(words(target_text))
    hs = [x.strip() for x in re.split(r"[\n.;•]", target_text) if len(x.strip()) > 8]
    missing = []
    for t in source_points:
        if line_score(t, hw, hs, threshold) < threshold:
            missing.append(t)
    return (not missing, missing)


def deck_slides(prs):
    res = []
    for s in prs.slides:
        t = []
        for sh in s.shapes:
            t += _shape_text(sh)
        if s.has_notes_slide:
            t.append(s.notes_slide.notes_text_frame.text)
        txt = "\n".join(t)
        res.append({"text": txt, "words": set(words(txt)),
                    "sents": [x.strip() for x in re.split(r"[\n.;•]", txt) if len(x.strip()) > 8]})
    return res


def draft_lines(D, plan=None):
    skip = {re.sub(r"\s+", " ", x.strip().lower()) for x in ((plan or {}).get("excluded") or []) + ((plan or {}).get("cut") or [])
            if isinstance(x, str)}
    for sec in D["sections"]:
        for sl in sec["slides"]:
            if "excluded" in (sl.get("flags") or []):
                continue
            for kind, items in (("key_point", sl.get("key_point") or []), ("content", sl.get("content") or [])):
                for _, t in items:
                    if t.strip().lower().startswith("(excluded)") or "[excluded]" in t.lower():
                        continue
                    if re.sub(r"\s+", " ", t.strip().lower()) in skip:
                        continue
                    yield sl["n"], sl["headline"], kind, t


def coverage(prs, D, plan=None, threshold=THRESHOLD):
    S = deck_slides(prs)
    missing, n = [], 0
    for sn, head, kind, t in draft_lines(D, plan):
        body = t.split(":", 1)[1] if re.match(r"^[^:]{2,40}:\s+\S", t) else t
        w = [x for x in words(body)] or words(t)
        if not w:
            continue
        n += 1
        best, where = 0.0, None
        for i, s in enumerate(S, 1):
            r = sum(1 for x in w if x in s["words"]) / len(w)
            nums = [x for x in w if x[0].isdigit()]
            if nums and not all(x in s["words"] for x in nums):
                r = min(r, threshold - 0.01)
            if r < threshold and s["sents"]:
                q = max(difflib.SequenceMatcher(None, body.lower(), x.lower()).ratio() for x in s["sents"])
                r = max(r, 1.0 if q >= 0.8 else 0)
            if r > best:
                best, where = r, i
        if best < threshold:
            missing.append(f"draft slide {sn} '{head[:40]}' {kind} not in the deck or notes "
                           f"(best {best:.0%} on slide {where}): '{t[:80]}'")
    return missing, n


def main(a):
    import draft_check
    deck, draft = a[0], a[1]
    plan = json.load(open(a[a.index("--plan") + 1])) if "--plan" in a else None
    th = float(a[a.index("--threshold") + 1]) if "--threshold" in a else THRESHOLD
    miss, n = coverage(Presentation(deck), draft_check.parse(open(draft, encoding="utf-8").read()), plan, th)
    for m in miss:
        print("MISSING", m)
    print(f"{n - len(miss)}/{n} draft lines covered")
    return 1 if miss else 0


if __name__ == "__main__":
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    sys.exit(main(sys.argv[1:]))

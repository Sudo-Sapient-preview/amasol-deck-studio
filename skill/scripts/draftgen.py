"""Step 0b: write draft.md (reference/standard-draft.md) from raw or bare input, and suggest edits for a structured one.

    python3 scripts/draftgen.py raw  INPUT.txt [--intake intake.json] [--title T] [--audience A] [--goal G] -o draft.md
    python3 scripts/draftgen.py bare --text "a 10 slide deck on X for a CIO audience" [--count N] -o draft.md
    python3 scripts/draftgen.py suggest draft.md [--apply-shorten] [--apply-merge] [-o draft.md]  # structured
    python3 scripts/draftgen.py topup  draft.md [-o draft.md]   # fill structured shortfalls up to the standard

SCRIPTED (deterministic, repeatable):
  raw     - split the input into fact units (bullets, else sentences); expand note shorthand (w/, govt, cos, yrs, ...);
            give each unit a storyline bucket (intro / problem / solution / proof / cta) by keyword rules (BUCKETS);
            a quote line becomes its own quote slide (quote + attribution); TODO/'?' lines become to-be-filled cta points;
            chunk each bucket into slides of 3-5 points, buckets with < 2 slides share a section; points > 15 words
            are shortened at a clause boundary (full text kept in notes, flag edited); slides with < 3 facts are padded
            with 'to-be-filled: ...' points (flag to-be-filled); every point comes from the input, nothing is added.
            Headline / key_point = the slide's first fact (flag to-be-filled: the agent rewrites them as messages).
  bare    - a skeleton: slide count from the request ('10 slide', '8-slide', 'N slides'), else --count, else a
            topic-breadth heuristic (propose_count; no fixed 10). Reason goes in notes and 'length' is listed in
            'assumed' when the count was proposed. Title is always generated + listed in 'assumed' with a one-line
            title_reason tying it to the ask. Context ~30 % (intro + problem), solution, proof + cta ~30 %; every
            slot 'to-be-filled', flag assumption; audience/goal assumed when not stated.
  suggest - structured: pairs of slides with high fact overlap (>= 50 % shared content words) -> MERGE suggestion;
            pairs with similar headlines and shared numbers -> 'two versions of the same story'; points > 15 words ->
            a shortened version. --apply-shorten applies shortenings (full text in notes, flag edited).
            --apply-merge applies MERGE pairs only when coverage.draft_points_retained confirms every source point
            is still on the merged slide or in its notes (threshold 60 %); each applied merge is flagged edited and
            listed in --report. If coverage would drop, the merge is skipped and reported as MERGE-SKIPPED.
AGENT JUDGMENT (not scripted): message headlines and key points (never plain topic labels; when the user wrote a
headline, judge whether its wording suits the slide and audience - keep it if it works, otherwise improve it using
only input facts and flag edited), which facts to cut, choosing one of two story versions, filling to-be-filled
points from the user, writing bare-request content (every fact flagged assumption), overriding the proposed bare
slide count when the topic warrants it. The output always passes scripts/draft_check.py; run it after every hand edit."""
import json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draft_check

SHORT = [(r"\bw/\s*", "with "), (r"\bgovt\b", "government"), (r"\bcos\b", "companies"), (r"\byrs\b", "years"),
         (r"\bincl\b\.?", "including"), (r"\bapps\b", "applications"), (r"\bmgmt\b", "management"),
         (r"\s*->\s*", " to "), (r"\s+=\s+", " is "), (r"\s*&\s*", " and "), (r"\s+\+\s+", " and ")]
BUCKETS = [  # first match wins; the order matters (a story's outcome is proof, not cta)
    ("cta", r"\b(todo|next steps?|contact person|call to action|get in touch|book a|let'?s talk)\b|\?\s*$"),
    ("proof", r"\b(story|case|reviewed|workshops?|live since|outcome|results?|quote|references?|testimonial|"
              r"key customers?|\d+ of \d+|saved|reduced|increased)\b"),
    ("intro", r"\b(founded|since \d{4}|employees|people|offices?|headquarters?|hq|consultancy|company|partners?|"
              r"clients|expertise)\b"),
    ("solution", r"\b(approach|levels?|maturity|capabilit\w*|platforms?|tiers?|center|standards?|goal|services?|"
                 r"governance|method|framework)\b"),
    ("problem", r"\b(problem|challenge|pain|risk|isolated|fragmented|no central|lack|silo|manual|outage|downtime)\b"),
    ("solution", r".")]
ORDER = ["intro", "problem", "solution", "proof", "cta"]
SECTION_NAMES = {"intro": "About us", "problem": "The challenge", "solution": "Our approach", "proof": "Proof",
                 "cta": "Next steps"}
QUOTE_RE = re.compile(r'(?:quote\s+)?([^:"“]*?)\s*:?\s*["“](.+?)["”]\s*(?:[-–]\s*(.+))?$', re.I)


def norm(t):
    t = t.strip().strip("-*•· ").strip()
    for a, b in SHORT:
        t = re.sub(a, b, t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


BOILER = re.compile(r"lorem ipsum|consectetur|skip to (main )?content|cookie|privacy policy|all rights reserved|"
                    r"add the date to your calendar|reminder e-?mail|subscribe|newsletter|read more|learn more$", re.I)


def units(text):
    """Fact units: bullet lines when the input is mostly bullets; otherwise every non-heading line split into
    sentences (headings are document structure, not facts). Boilerplate (cookie, lorem ipsum, 'skip to content',
    calendar/newsletter prompts) and fragments under 4 words are dropped."""
    lines = [l for l in text.splitlines() if l.strip()]
    bullets = [l for l in lines if draft_check_bullet(l)]
    if len(bullets) >= max(3, len(lines) // 2):
        head = [l for l in lines if not draft_check_bullet(l)]
        return [norm(l) for l in bullets if not BOILER.search(l)], head
    out = []
    for l in lines:
        l = l.strip()
        if re.match(r"^#{1,6}\s", l) or re.match(r"^\s*(slide|page|seite)\s*\d+\b.*:?\s*$", l, re.I):
            continue
        l = re.sub(r"^\s*(slide|page|seite)\s*\d+[^:]*:\s*", "", l, flags=re.I)
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", l):
            sent = norm(sent)
            if len(sent.split()) >= 4 and not BOILER.search(sent):
                out.append(sent)
    return list(dict.fromkeys(out)), []


def draft_check_bullet(l):
    return bool(re.match(r"^\s*([-*•·]|\d+[.)])\s+\S", l))


def nwords(t):
    return len(t.split())


def shorten(t, limit=15, hard=18):
    """Clause-boundary shortening: keep leading clauses up to the limit; None when it cannot be shortened cleanly."""
    if nwords(t) <= hard:        # 16-18 words: draft_check only warns; keep the fact whole
        return t
    parts = re.split(r"(?<=[,;:])\s+|\s+(?=\()|\s+[-–]\s+", t)
    out = ""
    for p in parts:
        cand = (out + " " + p).strip() if out else p
        if nwords(cand) > limit:
            break
        out = cand
    out = out.rstrip(",;: ")
    return out if out and nwords(out) >= 4 else " ".join(t.split()[:limit]).rstrip(",;:") + " ..."


def headline(t):
    t = re.sub(r"^[^:]{2,30}:\s+", lambda m: m.group(0) if len(t) < 60 else "", t)
    t = t[0].upper() + t[1:] if t else t
    if len(t) <= 60:
        return t.rstrip(".")
    cl = re.split(r"(?<=[,;])\s+", t)
    if len(cl[0]) <= 60 and len(cl[0].split()) >= 3:
        return cl[0].rstrip(",;")
    return t[:60].rsplit(" ", 1)[0].rstrip(",;:-– ")


def chunks(items, lo=3, hi=5):
    n = len(items)
    if n <= hi:
        return [items]
    k = -(-n // hi)
    size = -(-n // k)
    return [items[i:i + size] for i in range(0, n, size)]


def q(v):
    return draft_check.q(v)


def emit(header, sections, closing):
    o = ["---"]
    for k, v in header.items():
        o.append(f"{k}: " + ("[" + ", ".join(q(x) for x in v) + "]" if isinstance(v, list) else q(v) if isinstance(v, str) else str(v)))
    o += ["---", "", "## AGENDA"] + [f"- {name}" for name, _ in sections] + [""]
    n = 0
    for name, slides in sections:
        o += [f"## SECTION: {name}", ""]
        for s in slides:
            n += 1
            o += [f"### SLIDE {n}: {s['headline']}", f"purpose: {s['purpose']}", f"key_point: {s['key_point']}", "content:"]
            o += [f"  - {p}" for p in s["content"]]
            if s.get("visual_hint"):
                o.append(f"visual_hint: {s['visual_hint']}")
            if s.get("notes"):
                o += ["notes: |"] + [f"  {l}" for l in s["notes"]]
            o += [f"flags: [{', '.join(s['flags'])}]", ""]
    o += ["## CLOSING", f"closing_message: {q(closing.get('closing_message', ''))}", f"contact: {q(closing.get('contact', ''))}", ""]
    return "\n".join(o)


def bucket(t):
    for b, rx in BUCKETS:
        if re.search(rx, t, re.I):
            return b
    return "solution"


def topic_of(text, head):
    for l in head + text.splitlines()[:3]:
        m = re.search(r"\b(?:on|about|for)\s+(.+?)(?:\s+(?:for|to)\s+(?:an?|the)\s+.*)?$", l, re.I) if "deck" in l.lower() else None
        if m:
            return m.group(1).strip(" .")
    names = Counter(w for w in re.findall(r"\b[a-zA-Z][\w-]{2,}\b", text) if w[0].islower() and w.lower() not in
                    {"and", "the", "for", "with", "notes", "from", "call", "team", "deck", "input", "each", "level"})
    return None


_ASK = re.compile(r"^(?:please\s+)?(?:can you\s+|could you\s+)?(?:make|create|build|prepare|write|draft|do|give|put together)"
                  r"\s+(?:me|us)?\s*", re.I)
SHORT_ASK = re.compile(r"\b(?:short|brief|quick|compact)\b", re.I)


def bare_topic(text):
    """The topic of a one-line ask, with the request wording, deck words, style phrase and audience clause removed:
    'Make me a short deck in our amasol style on why mid-sized companies should invest in observability, for a
    CIO audience' -> 'Why mid-sized companies should invest in observability'. None when nothing is left."""
    t = " ".join(text.split())
    t = _ASK.sub("", t)
    t = re.sub(r"^(?:an?|the)?\s*(?:short|quick|brief|compact|small|\d{1,2}[- ]?(?:slides?|pages?))?\s*"
               r"(?:slide\s+)?(?:deck|presentation|pitch|slides?|ppt)\b", "", t, flags=re.I)
    t = re.sub(r"^\s*(?:in|on|using)\s+(?:our|the)\s+[\w -]*?(?:style guide|style|template|look)\b", "", t, flags=re.I)
    t = re.sub(r"^\s*(?:on|about|covering|explaining|for)\s+", "", t, flags=re.I)
    t = re.sub(r"[,;]?\s+for\s+(?:an?|the|our)?\s*[\w &/-]*?\s*(?:audience|board|team|leadership|leaders|executives?|"
               r"managers?)\b.*$", "", t, flags=re.I)
    t = re.sub(r"[,;]?\s+for\s+(?:an?|the|our)?\s*(?:cio|cto|ceo|cfo|ciso)s?\b.*$", "", t, flags=re.I)
    t = t.strip(" .,;:")
    if not t:
        return None
    return t if re.match(r"amasol\b", t) else t[0].upper() + t[1:]      # the brand is always lower-case


def header_fields(text, intake, a, kind):
    req = intake.get("parts", [{}])[0] if intake else {}
    assumed = []
    title = a.get("title") or (bare_topic(text) if kind == "bare" else None)
    if not title:
        m = re.search(r"\b(?:deck|presentation|pitch)\s+(?:on|about)\s+(.+?)(?:\s+for\s+(?:an?|the)?\s*.+)?$", text.strip().splitlines()[0], re.I)
        m2 = re.search(r"([\w-]+)\s+(?:team\s+)?-?\s*(company intro|intro|overview)", text.splitlines()[0], re.I)
        hd = next((re.sub(r"^#+\s*", "", l).strip() for l in text.splitlines() if re.match(r"^#{1,3}\s+\w", l)), None)
        first = next((l.strip(" -:") for l in text.splitlines()
                      if len(l.split()) >= 2 and not re.match(r"^\s*(slide|page|seite)\s*\d", l, re.I)), "Overview")
        title = m.group(1).strip(" .") if m else (f"{m2.group(1)} {m2.group(2)}" if m2 else (hd or first))
        title = headline(re.sub(r"^(headline|title)\s*:\s*", "", re.sub(r"\s+", " ", title), flags=re.I))
        title = title[0].upper() + title[1:] if title[0].islower() and not re.match(r"[a-z]+[A-Z]|amasol", title) else title
        # title is not an 'assumed' field in draft_check; a derived title is reported in the slide-1 notes instead
    aud = a.get("audience")
    if not aud:
        m = re.search(r"\bfor\s+(?:an?|the|our)?\s*([\w &/-]+?)\s+audience\b|\bfor\s+(?:an?|the|our)\s+(cio|cto|ceo|board|"
                      r"management|leadership|executives?|clients?|customers?)\b", text, re.I)
        aud = (m.group(1) or m.group(2)).strip() if m else "Prospective client IT leadership"
        if not m:
            assumed.append("audience")
    goal = a.get("goal") or "Agree on a concrete next step after the presentation"
    if not a.get("goal"):
        assumed.append("goal")
    return {"title": title, "audience": aud, "goal": goal, "assumed": assumed}


def gen_raw(text, a, intake):
    U, head = units(text)
    H = header_fields(text, intake, a, "raw")
    B = {k: [] for k in ORDER}
    quotes = []
    for u in U:
        m = QUOTE_RE.search(u) if ('"' in u or "“" in u) else None
        if m and nwords(m.group(2)) >= 4:
            who = (m.group(3) or m.group(1) or "").strip(" :-–")
            who = re.sub(r"^quote\s+", "", who, flags=re.I)
            quotes.append((u, m.group(2).strip(), who))
            continue
        B[bucket(u)].append(u)
    slides = {k: [] for k in ORDER}
    for k in ORDER:
        for ch in (chunks(B[k]) if B[k] else []):
            pts, notes, fl = [], [], set()
            for u in ch:
                if re.search(r"\btodo\b|\?\s*$", u, re.I):
                    pts.append("to-be-filled: " + re.sub(r"^todo:?\s*", "", u, flags=re.I).rstrip("?")); fl.add("to-be-filled"); continue
                s = shorten(u)
                if s != u:
                    notes.append(f"Shortened from the input: \"{u}\""); fl.add("edited")
                pts.append(s)
            while len(pts) < 3:
                pts.append(f"to-be-filled: further {k} point (not in the input)"); fl.add("to-be-filled")
            first = next((p for p in pts if not p.startswith("to-be-filled")), pts[0])
            fl.add("to-be-filled")      # headline/key point are the first fact until the agent writes the message
            notes.append("Headline and key point start from the first fact (scripted). Rewrite as a claim that suits "
                         "the slide and audience - never a plain topic label; if the user already wrote a headline, "
                         "keep it when the wording works, otherwise improve it using only input facts (flag edited).")
            slides[k].append({"purpose": k, "headline": headline(first), "key_point": first,
                              "content": pts, "notes": notes, "flags": sorted(fl),
                              "visual_hint": "key-number" if k == "proof" and re.search(r"\d", " ".join(pts)) else None})
    for full, qt, who in quotes:
        slides["proof"].append({"purpose": "proof", "headline": "What the customer says", "key_point": shorten(qt, 18),
                                "content": [f"\"{qt}\"", f"– {who}" if who else "– to-be-filled: attribution"],
                                "visual_hint": "quote", "notes": [f"Quote from the input: {full}"], "flags": ["edited"]})
    sections, pend = [], []
    for k in ORDER:
        pend += slides[k]
        if len(pend) >= 2:
            names = [SECTION_NAMES[x] for x in ORDER if any(s in slides[x] for s in pend)]
            sections.append((" and ".join(dict.fromkeys(names)) if len(names) <= 2 else names[0], pend)); pend = []
    if pend:
        if sections:
            sections[-1] = (sections[-1][0], sections[-1][1] + pend)
        else:
            sections.append(("Overview", pend))
    n = sum(len(s) for _, s in sections)
    header = {"title": H["title"], "audience": H["audience"], "goal": H["goal"], "assumed": H["assumed"],
              "length": n, "language": "en", "input_type": "raw", "source_files": a.get("sources", [])}
    return emit(header, sections, {"closing_message": "Thank you", "contact": ""})


def parse_count(text):
    """Return an explicit slide count from the ask, or None when the ask does not name one."""
    m = re.search(r"\b(\d{1,2})\s*[- ]?\s*(?:slides?|folien|pages?)\b", text, re.I)
    return int(m.group(1)) if m else None


# Facets that widen a bare-request topic; more hits -> more slides. No fixed default of 10.
TOPIC_FACETS = [
    r"\bobservab\w*", r"\bmonitor(ing)?\b", r"\breliab\w*", r"\bsecurity|secure\b", r"\bcloud\b",
    r"\baiops?\b", r"\bplatform\w*", r"\bservice\w*", r"\bmanaged\b", r"\bconsult\w*",
    r"\bmaturity|levels?\b", r"\bgovernance\b", r"\bcase stud(?:y|ies)|customer stor\w*|references?\b",
    r"\broadmap|next steps?|cta\b", r"\bpricing|cost|roi\b", r"\bintegrat\w*", r"\bmigrat\w*",
    r"\bcompliance|audit\b", r"\bteam|organisation|organization\b", r"\barchitect\w*",
]


def propose_count(text):
    """Pick a slide count from the topic's breadth. Returns (n, reason). Agent may override with --count."""
    hits = sum(1 for rx in TOPIC_FACETS if re.search(rx, text, re.I))
    words = len(re.findall(r"\w+", text))
    # named audience / goal clauses also widen the ask a little
    if re.search(r"\bfor\s+(?:an?|the|our)?\s*\w+", text, re.I):
        hits += 1
    if re.search(r"\b(and|plus|including|with)\b", text, re.I):
        hits += 0  # no-op; kept for readability
    if hits <= 1 and words < 16:
        n, reason = 6, "narrow single-topic ask"
    elif hits <= 3:
        n, reason = 8, f"focused topic ({hits} facets)"
    elif hits <= 5:
        n, reason = 10, f"multi-facet topic ({hits} facets)"
    else:
        n, reason = 12, f"broad multi-aspect topic ({hits} facets)"
    n = max(6, min(14, n))
    return n, reason + "; agent may override with --count"


def gen_bare(text, a, intake):
    explicit = a.get("count") if a.get("count") is not None else parse_count(text)
    count_assumed = explicit is None
    if explicit is not None:
        n, count_reason = max(int(explicit), 6), f"count taken from the ask ({explicit} slides)"
    elif SHORT_ASK.search(text):
        n, count_reason = 6, "the ask says short: the minimum skeleton (3 sections of 2 slides)"
    else:
        n, count_reason = propose_count(text)
    H = header_fields(text, intake, a, "bare")
    topic = H["title"]
    # bare titles are always generated from the ask -> assumed, with a title_reason
    assumed = list(H["assumed"])
    if "title" not in assumed:
        assumed.append("title")
    if count_assumed and "length" not in assumed:
        assumed.append("length")
    title_reason = (f"Forged from the bare ask: topic '{topic}'"
                    + (f", audience '{H['audience']}'" if H.get("audience") else "")
                    + (f", goal '{H['goal']}'" if H.get("goal") else ""))
    ctx = max(2, round(n * 0.3)); prf = max(2, round(n * 0.3)); sol = max(2, n - ctx - prf)
    plan = [("Context", ["intro"] + ["problem"] * (ctx - 1)), ("Our approach", ["solution"] * sol),
            ("Proof and next steps", ["proof"] * (prf - 1) + ["cta"])]
    sections = []
    first = True
    for name, purposes in plan:
        sl = []
        for i, p in enumerate(purposes, 1):
            notes = ["Skeleton slot (scripted). Write the content as assumptions: every generated fact stays "
                     "flagged assumption until the user confirms it.",
                     "Headline must be a claim (not a topic label); rewrite before the build."]
            if first:
                notes.append(f"title_reason: {title_reason}")
                notes.append(f"Slide count: {n} ({count_reason}).")
                first = False
            sl.append({"purpose": p, "headline": f"to-be-filled: {p} message {i}"[:60],
                       "key_point": f"to-be-filled: the {p} takeaway on {topic}"[:110],
                       "content": [f"to-be-filled: {p} point {j}" for j in (1, 2, 3)],
                       "notes": notes,
                       "flags": ["assumption", "to-be-filled"]})
        sections.append((name, sl))
    header = {"title": topic, "audience": H["audience"], "goal": H["goal"], "assumed": assumed,
              "length": n, "language": "en", "input_type": "bare", "source_files": [],
              "title_reason": title_reason}
    return emit(header, sections, {"closing_message": "to-be-filled: next step", "contact": ""})


def cwords(t):
    return {w for w in re.findall(r"[a-z0-9][a-z0-9+%-]+", t.lower()) if w not in
            {"the", "and", "for", "with", "our", "from", "into", "are", "its", "this", "that", "per", "via"}}


def _slide_points(s):
    return [t for _, t in (s.get("content") or [])] + [t for _, t in (s.get("key_point") or [])]


def _merge_pair(a, b):
    """Build a candidate merged slide from a+b, keeping every unique point (overflow -> notes)."""
    import coverage as cov
    pts_a, pts_b = _slide_points(a), _slide_points(b)
    # prefer a's headline/key_point; unique content points in order, drop near-duplicates
    seen, uniq = set(), []
    for t in [p for _, p in a["content"]] + [p for _, p in b["content"]]:
        key = " ".join(sorted(cwords(t)))
        if key and key not in seen:
            seen.add(key); uniq.append(t)
    keep, overflow = uniq[:draft_check.MAX_PTS], uniq[draft_check.MAX_PTS:]
    notes = []
    if a.get("notes"):
        notes += [x for x in a["notes"].splitlines() if x.strip()]
    if b.get("notes"):
        notes += [x for x in b["notes"].splitlines() if x.strip()]
    if overflow:
        notes.append("Points moved into notes on merge: " + " | ".join(overflow))
    notes.append(f"Merged slide {b['n']} ('{b['headline'][:40]}') into slide {a['n']}; coverage-checked.")
    # target text the coverage helper will see
    kp = (a["key_point"][0][1] if a.get("key_point") else "")
    target = "\n".join([a["headline"], kp] + keep + notes)
    ok, missing = cov.draft_points_retained(pts_a + pts_b, target)
    if not ok:
        return None, missing
    m = dict(a)
    m["content"] = [(a["line"], t) for t in keep]
    m["notes"] = "\n".join(notes)
    m["flags"] = list(dict.fromkeys(list(a.get("flags") or []) + list(b.get("flags") or []) + ["edited"]))
    m["data"] = list(a.get("data") or []) + [d for d in (b.get("data") or []) if d not in (a.get("data") or [])]
    m["companies"] = list(dict.fromkeys(list(a.get("companies") or []) + list(b.get("companies") or [])))
    # visual_hint: keep non-none preference
    if not m.get("visual_hint") or m.get("visual_hint") == "none":
        m["visual_hint"] = b.get("visual_hint")
    return m, []


def suggest(path, apply_shorten=False, apply_merge=False, out=None):
    import coverage  # noqa: F401  - used by _merge_pair
    D = draft_check.parse(open(path, encoding="utf-8").read())
    S = [s for sec in D["sections"] for s in sec["slides"]]
    rep = []
    merge_pairs = []  # (a_n, b_n, overlap)
    for i, a in enumerate(S):
        for b in S[i + 1:]:
            A = cwords(" ".join(t for _, t in a["content"] + a["key_point"]))
            Bw = cwords(" ".join(t for _, t in b["content"] + b["key_point"]))
            if not A or not Bw:
                continue
            ov = len(A & Bw) / min(len(A), len(Bw))
            hs = len(cwords(a["headline"]) & cwords(b["headline"])) / max(1, min(len(cwords(a["headline"])), len(cwords(b["headline"]))))
            nums = set(re.findall(r"\d[\d.,]*\+?", " ".join(t for _, t in a["content"]))) & \
                   set(re.findall(r"\d[\d.,]*\+?", " ".join(t for _, t in b["content"])))
            if ov >= 0.5:
                rep.append(f"MERGE? slides {a['n']} + {b['n']}: {ov:.0%} of the facts overlap ('{a['headline'][:40]}' / "
                           f"'{b['headline'][:40]}') - keep one, move unique points into it")
                merge_pairs.append((a["n"], b["n"], ov))
            elif hs >= 0.5 and len(nums) >= 2:
                rep.append(f"TWO VERSIONS? slides {a['n']} + {b['n']}: similar headlines and shared numbers {sorted(nums)} "
                           f"- likely the same story told twice; choose one version")
    changes = 0
    merges_applied = 0
    if apply_merge and merge_pairs:
        # apply highest-overlap pairs first; skip a slide already consumed
        consumed = set()
        by_n = {s["n"]: s for s in S}
        # rebuild sections after merges
        for an, bn, ov in sorted(merge_pairs, key=lambda x: -x[2]):
            if an in consumed or bn in consumed:
                continue
            a, b = by_n[an], by_n[bn]
            merged, missing = _merge_pair(a, b)
            if merged is None:
                rep.append(f"MERGE-SKIPPED slides {an} + {bn}: coverage would drop ({len(missing)} point(s) lost), e.g. '{missing[0][:60]}'")
                continue
            # replace a with merged; drop b from its section
            for sec in D["sections"]:
                ns = []
                for s in sec["slides"]:
                    if s["n"] == an:
                        ns.append(merged)
                    elif s["n"] == bn:
                        continue
                    else:
                        ns.append(s)
                sec["slides"] = ns
            consumed.add(an); consumed.add(bn)
            by_n[an] = merged
            draft_check.note(merged, f"Merged slide {bn} into this slide (overlap {ov:.0%}); every source point kept on the slide or in notes.")
            rep.append(f"MERGED slides {an} + {bn} (overlap {ov:.0%}) -> slide {an}, flagged edited")
            merges_applied += 1
        # renumber + refresh agenda
        draft_check.autofix(D)
        S = [s for sec in D["sections"] for s in sec["slides"]]
    for s in S:
        for k, (ln, t) in enumerate(s["content"]):
            if nwords(t) > getattr(draft_check, "PT_WORDS", 15):
                sh = shorten(t)
                rep.append(f"SHORTEN slide {s['n']} line {ln}: '{t}' -> '{sh}'")
                if apply_shorten:
                    s["content"][k] = (ln, sh)
                    draft_check.note(s, f"Shortened point; full text: \"{t}\"")
                    if "edited" not in s["flags"]:
                        s["flags"].append("edited")
                    changes += 1
    print("\n".join(rep) if rep else "no merge or shortening suggestions")
    if (apply_shorten or apply_merge) and out:
        open(out, "w", encoding="utf-8").write(draft_check.dump(D))
        print(f"applied {changes} shortenings, {merges_applied} merges -> {out}")
    elif apply_merge and not out:
        print("(pass -o DRAFT.md with --apply-merge to write the merged draft)")
    return 0


def topup(path, out):
    """Fill a structured draft up to the standard (slide-marked PDFs that fall short).

    Pads slides with < 3 points (to-be-filled), ensures required header fields (listed in assumed when invented),
    runs draft_check.autofix (agenda, renumber, one-slide section merges, >5 splits). Each fix is flagged edited.
    Does not invent facts beyond to-be-filled placeholders.
    """
    D = draft_check.parse(open(path, encoding="utf-8").read())
    log = []
    h = D["header"]
    for k, default in (("title", "Overview"), ("audience", "Prospective client IT leadership"),
                       ("goal", "Understand what we offer and agree on a next step"),
                       ("language", "en"), ("input_type", "structured")):
        v = h.get(k, "")
        if not str(v).strip() or draft_check.PLACEHOLDER_RE.match(str(v)):
            h[k] = default
            asm = h.get("assumed") or []
            if isinstance(asm, str):
                asm = draft_check.parse_list(asm)
            if k in draft_check.ASSUMABLE and k not in asm:
                asm.append(k)
            h["assumed"] = asm
            log.append(f"filled header '{k}' -> '{default}' (assumed)" if k in draft_check.ASSUMABLE
                       else f"filled header '{k}' -> '{default}'")
    if not str(h.get("length", "")).isdigit():
        n = sum(len(sec["slides"]) for sec in D["sections"]) or 6
        h["length"] = str(n); log.append(f"filled header 'length' -> {n}")
    for sec in D["sections"]:
        for s in sec["slides"]:
            while len(s["content"]) < draft_check.MIN_PTS:
                s["content"].append((s["line"], f"to-be-filled: further point for '{s['headline'][:40]}'"))
                draft_check.note(s, "Padded to 3 points (structured input fell short of the standard).")
                if "to-be-filled" not in s["flags"]:
                    s["flags"].append("to-be-filled")
                log.append(f"SLIDE {s['n']}: padded to {draft_check.MIN_PTS} points")
            if not s.get("key_point"):
                first = s["content"][0][1] if s["content"] else s["headline"]
                s["key_point"] = [(s["line"], first)]
                draft_check.note(s, "Added key_point from the first content point (structured input fell short).")
                log.append(f"SLIDE {s['n']}: added key_point")
            if not s.get("purpose"):
                s["purpose"] = "solution"
                draft_check.note(s, "Defaulted purpose to 'solution' (structured input fell short).")
                log.append(f"SLIDE {s['n']}: defaulted purpose")
    log += draft_check.autofix(D)
    open(out, "w", encoding="utf-8").write(draft_check.dump(D))
    print(f"topup: {len(log)} change(s) -> {out}")
    for x in log:
        print("  - " + x)
    return 0


def main(a):
    if not a or a[0] not in ("raw", "bare", "suggest", "topup") or "-h" in a or "--help" in a:
        print(__doc__); return 2
    kind, rest = a[0], a[1:]
    opt = lambda k: rest[rest.index(k) + 1] if k in rest else None
    if kind == "topup":
        return topup(rest[0], opt("-o") or rest[0])
    if kind == "suggest":
        return suggest(rest[0], apply_shorten="--apply-shorten" in rest,
                       apply_merge="--apply-merge" in rest, out=opt("-o"))
    intake = json.load(open(opt("--intake"))) if opt("--intake") else None
    args = {"title": opt("--title"), "audience": opt("--audience"), "goal": opt("--goal"),
            "count": int(opt("--count")) if opt("--count") else None}
    if kind == "raw":
        src = rest[0]; args["sources"] = [os.path.basename(src)]
        md = gen_raw(open(src, encoding="utf-8").read(), args, intake)
    else:
        text = opt("--text") or open(rest[0], encoding="utf-8").read()
        md = gen_bare(text, args, intake)
    out = opt("-o") or "draft.md"
    open(out, "w", encoding="utf-8").write(md)
    D = draft_check.parse(md); R = draft_check.check(D)
    fails = [r for r in R if r[1]] if isinstance(R, list) else None
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

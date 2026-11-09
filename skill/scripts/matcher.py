"""Layout matcher: draft.md + plan.json -> match.json (one template-bank layout per slide, with a reason).

Usage: python3 scripts/matcher.py draft.md plan.json [-o match.json] [--family Weiß] [--photos photos-map.json]
(--photos: {plan id: approved image path} from scripts/photos.py; picture layouts only for slides with a photo)

The template bank (reference/template-bank.json, built from the amasol style guide's 50 layouts) is the only
source of layouts. For every planned content slide the matcher
  1. settles the visual: a text-led `icon` slide with 2-5 points becomes `icon_set` (one icon per point), or
     `big_number` on `Inhalt & Infobox` when the draft gives it a key number - never a lone corner icon (sparse);
  2. keeps the layouts of the content family that host that visual (key/quote visuals use their own layouts);
  3. drops layouts the text does not fit: headline <= title capacity, key point <= sub-line capacity, body points
     <= the body placeholder's lines (chars per line x lines, one-line bullets) or the visual's own limit;
  4. scores the rest: bank rank, suits the slide's `purpose` and `visual_hint`, one vs two columns (comparison,
     two-part charts -> 2 columns; full-width diagrams, logos -> 1 column), point count and word load;
  5. enforces variety: never the previous slide's layout, at most max(2, ceil(2n/12)) uses (RULES §11), and a
     penalty for the layout two slides back.
It also places cover, closing and - when the deck runs over 5 slides, the deck lint's threshold - the agenda and one
divider per chapter; a deck over 5 slides with one chapter is a problem (split it or go short-pitch). A plan with
"short_pitch": true gets no agenda and no dividers, and matchbuild saves it with short_pitch=True.
Exit 1 when a slide fits no layout (split or shorten it in draft.md, then rerun).
Builders read match.json: `M = matcher.load("match.json"); s = d.add(M[pid]["layout"], plan=pid)` and draw
M[pid]["visual"]. verify_deck checks every planned slide uses its matched layout and visual."""
import json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import draft_check  # noqa: E402
import capacity  # noqa: E402  - the deck lint's own text measure, so the matcher and the build agree

BANK = os.path.join(HERE, "..", "reference", "template-bank.json")
TWO_COL_VISUALS = {"donut", "pie", "story_panel"}
FULL_VISUALS = {"process", "staircase", "tiers", "wheel", "band", "tile_grid", "table", "fact_chips"}
ICON_SET_CPL, ICON_SET_LINES = {1: 80, 2: 34}, 2      # chars per line / lines per row at 14 pt (full / half width)
DIGIT = re.compile(r"\d")


def bank():
    return json.load(open(BANK, encoding="utf-8"))["layouts"]


def ph(layout, idx):
    return next((p for p in layout["placeholders"] if p["idx"] == idx), None)


def lines_needed(texts, cpl):
    return sum(max(1, math.ceil(len(t) / max(cpl, 1))) for t in texts)


def draft_slides(D):
    out = {}
    for sec in D["sections"]:
        for s in sec["slides"]:
            s = dict(s, chapter=sec["name"])
            out[s["n"]] = s
    return out


def slide_for(entry, slides, k):
    m = re.search(r"(\d+)", str(entry.get("source_ref", "")))
    if m and int(m.group(1)) in slides:
        return slides[int(m.group(1))]
    return list(slides.values())[k] if k < len(slides) else None


def settle_visual(v, s):
    pts = [t for _, t in s.get("content", [])]
    nums = [x for x in s.get("data") or [] if DIGIT.search(str(x.get("value", "")))]
    if v == "icon":
        if nums or s.get("visual_hint") == "key-number":
            if nums:
                return "big_number", "text-led with a key number in the draft -> big_number in the info box"
        if 2 <= len(pts) <= 5:
            return "icon_set", f"text-led list of {len(pts)} points -> icon_set (one icon per point, not a lone corner icon)"
    return v, None


def box_overflow(layout_name, idx, text):
    """The deck lint's capacity check (scripts/capacity.py) for one text in one placeholder: None or a message.
    Falls back to None when the placeholder has no measured spec."""
    spec = capacity.CAP.get("layouts", {}).get(layout_name, {}).get(str(idx))
    if not spec or not text:
        return None
    return capacity.check_box([(text, 0, None, None, False, None)], spec)


def fit(layout, s, visual):
    """None when the slide fits, else a reason string. Text is measured exactly as the deck lint measures it."""
    pts = [t for _, t in s.get("content", [])]
    kp = " ".join(t for _, t in s.get("key_point", []))
    name = layout["name"]
    if layout["role"] == "content":
        boxes = [("headline", 0, s["headline"]), ("key point", 10, kp)]
    elif layout["role"] == "key":                     # headline 10, sub-line 13, one pill/tile per point
        boxes = [("headline", 10, s["headline"]), ("key point", 13, kp)] + [
            (f"point {k + 1}", idx, p) for k, (idx, p) in enumerate(zip((14, 16, 17, 18, 19, 20), pts))]
    elif layout["role"] == "quote":
        boxes = [("headline", 10, s["headline"])]
    else:
        boxes = []
    for what, idx, text in boxes:
        msg = box_overflow(name, idx, text)
        if msg:
            return f"{what} too long for {name}: {msg} - text starts '{text[:40]}'"
    if layout["role"] == "key":
        from sgdeck import key_count_problems    # same rule as the deck lint
        cnt = key_count_problems(s["headline"], kp, 4 if name == "Key Slide 1" else 6)
        if cnt:
            return f"{name}: {cnt[0]}"
    cols = layout["columns"]
    if visual == "table" and cols == 2:
        return "a table needs a full-width layout (cells must stay on one line)"
    if visual == "icon_set":
        if not 2 <= len(pts) <= 5:
            return f"icon_set takes 2-5 points, slide has {len(pts)}"
        cpl = ICON_SET_CPL[1 if layout["name"].startswith("Inhalt") else 1]
        long = [p for p in pts if len(p) > cpl * ICON_SET_LINES]
        if long:
            return f"point over {cpl * ICON_SET_LINES} chars for an icon row: '{long[0][:40]}'"
    elif visual in ("big_number", "icon", "info_box") or (visual == "chart" and layout["name"].startswith("Inhalt & Tracker")):
        body = ph(layout, 11)
        if body and body.get("chars_per_line"):
            need = lines_needed(pts, body["chars_per_line"])
            if need > body["lines"] or len(pts) > (body.get("one_line_bullets") or 99):
                return f"{len(pts)} points need {need} lines, body holds {body['lines']}"
        if visual == "big_number":
            num = next((x for x in s.get("data") or [] if DIGIT.search(str(x.get("value", "")))), None)
            v, lab = ph(layout, 16), ph(layout, 17)
            if not (num and v and lab):
                return "big_number needs a number from the draft and the Infobox value/label placeholders"
            if len(str(num["value"])) > v["max_chars"] or len(num.get("label", "")) > lab["max_chars"]:
                return "key number or its label over the info box capacity"
    elif visual == "key_slide":
        want = 4 if layout["name"] == "Key Slide 1" else 6
        if len(pts) != want:
            return f"{layout['name']} takes exactly {want} points"
    elif visual == "quote":
        q = ph(layout, 13)
        if sum(len(p) for p in pts) > q["max_chars"]:
            return "quote over the quote placeholder capacity"
    if cols == 2 and visual in FULL_VISUALS and len(pts) > 6:
        return "too many items for a diagram in a two-column layout"
    return None


def score(layout, s, visual, uses, prev2, n_planned):
    sc, why = layout["rank"] * 2.0, []
    pur, hint = s.get("purpose"), s.get("visual_hint")
    if pur in layout.get("suits_purpose", []):
        sc -= 2; why.append(f"suits purpose '{pur}'")
    else:
        sc += 3
    if hint in layout.get("suits_visual_hint", []):
        sc -= 1; why.append(f"suits visual_hint '{hint}'")
    else:
        sc += 2
    cols = layout["columns"]
    if pur == "comparison" or visual in TWO_COL_VISUALS:
        sc += -3 if cols == 2 else 2
        why.append("two columns for the comparison / two-part visual" if cols == 2 else "")
    if visual in FULL_VISUALS or s.get("companies"):
        sc += -1 if cols == 1 else 1
        if cols == 1:
            why.append("full width for the diagram/logos")
    words = sum(len(t.split()) for _, t in s.get("content", []))
    if visual == "icon_set" and cols == 2 and len(s.get("content", [])) <= 3 and words <= 30:
        sc -= 0.5
    sc += 1.5 * uses.get(layout["name"], 0)
    if layout["name"] == prev2:
        sc += 2
    return sc, [w for w in why if w]


def match(D, plan, family="Weiß", beam=400, photos=None):
    """photos: {plan id: approved image path} from scripts/photos.py (user image first, then free-licence stock).
    Layouts with a picture placeholder are only offered to slides that HAVE a photo; quotes without one get the
    no-photo variant (s.quote(..., photo=None)). Never an empty picture frame."""
    photos = photos or {}
    L = bank()
    slides = draft_slides(D)
    planned = plan.get("slides") or []
    content = [l for l in L if l["role"] == "content" and l["family"] == family]
    chapters = plan.get("chapters") or [sec["name"] for sec in D["sections"]]
    problems, skel, chapter = [], [], None
    skel.append({"kind": "cover", "layout": "Titelfolie ohne Bild", "reason": "no licensed cover photo -> default pink cover"})
    short = bool(plan.get("short_pitch"))      # short-pitch deck: no agenda, no dividers (Deck.save(short_pitch=True))
    # same threshold as the deck lint: a deck over 5 slides (cover + content + closing) needs agenda + dividers
    structure = not short and len(planned) + 2 > 5
    waived = plan.get("waive") or {}          # deck-level waivers with a reason: no divider / agenda slides
    if structure and len(chapters) < 2:
        problems.append(f"{len(planned)} content slides in one chapter: a deck over 5 slides needs an agenda of 2-8 "
                        "chapters - split draft.md into 2+ sections, or set plan short_pitch (decks of 10 slides or fewer)")
    if structure and len(chapters) > 1 and "agenda" not in waived:
        skel.append({"kind": "agenda", "layout": "Agenda", "reason": f"{len(planned)} content slides, {len(chapters)} chapters"})
    work = []                                   # (skeleton index, plan entry, draft slide, visual, why, pool)
    for k, e in enumerate(planned):
        s = slide_for(e, slides, k)
        if s is None:
            problems.append(f"{e.get('id')}: no draft slide for source_ref '{e.get('source_ref')}'"); continue
        ch = e.get("chapter") or s["chapter"]
        if structure and len(chapters) > 1 and ch != chapter and "dividers" not in waived:
            skel.append({"kind": "divider", "layout": "Kapiteltrenner - Blau", "chapter": ch,
                         "reason": "chapter start -> default mint divider with chapter panel"})
            chapter = ch
        visual, vwhy = settle_visual(e.get("visual"), s)
        role = {"key_slide": "key", "quote": "quote"}.get(visual)
        pool = [l for l in L if l["role"] == role] if role else [l for l in content if visual in l["visuals"]]
        has_photo = bool(photos.get(e["id"]))
        if not has_photo and role != "quote":
            pool = [l for l in pool if l.get("picture") in (None, "none", False, "")]
        skel.append({"kind": "content", "id": e["id"], "draft_slide": s["n"], "layout": None, "visual": visual,
                     "plan_visual": e.get("visual"), "photo": photos.get(e["id"]),
                     **({"picture_variant": "no-photo"} if role == "quote" and not has_photo else {}),
                     **({"visual_change": vwhy} if vwhy else {})})
        work.append((len(skel) - 1, e, s, visual, pool))
    skel.append({"kind": "closing", "layout": "Schlussfolie - Blau", "reason": "default closing"})
    warnings = []
    msg = box_overflow("Titelfolie ohne Bild", 0, D["header"].get("title", ""))
    if msg:
        problems.append(f"title too long for the cover: {msg} - shorten it in draft.md")
    msg = box_overflow("Schlussfolie - Blau", 10, (D.get("closing") or {}).get("closing_message", ""))
    if msg:                                   # SPEC closing_title can replace it, so a warning, not a stop
        warnings.append(f"closing_message too long for the closing slide: {msg} - shorten it in draft.md or give "
                        "SPEC a short closing_title")
    total = len(skel)
    limit = max(2, math.ceil(2 * total / 12))   # same rule as the build lint (RULES §11), over the whole deck
    # per slide: fitting candidates with their base score (fit is independent of the sequence)
    opts = []
    for si, e, s, visual, pool in work:
        ok, rej = [], []
        for l in pool:
            why = fit(l, s, visual)
            (rej.append(f"{l['name']}: {why}") if why else ok.append(l))
        if not ok:
            problems.append(f"{e['id']} (draft slide {s['n']}): no layout fits '{visual}' - " + "; ".join(rej) +
                            " - split or shorten the slide in draft.md")
        opts.append((si, e, s, visual, ok, rej))
    # beam search over the sequence: variety constraints are hard, the score is soft
    states = [(0.0, [], {})]
    for j, (si, e, s, visual, ok, rej) in enumerate(opts):
        nxt = []
        prev_is_content = j > 0 and opts[j - 1][0] == si - 1
        for sc, path, uses in states:
            prev = path[-1][0]["name"] if path and prev_is_content and path[-1] else None
            prev2 = path[-2][0]["name"] if len(path) > 1 and path[-2] and opts[j - 2][0] == si - 2 else None
            if not ok:
                nxt.append((sc + 100, path + [None], uses)); continue
            for l in ok:
                if l["name"] == prev and l["name"] != "Inhalt & Tracker":
                    continue
                if uses.get(l["name"], 0) >= limit:
                    continue
                c, why = score(l, s, visual, uses, prev2, len(opts))
                u = dict(uses); u[l["name"]] = u.get(l["name"], 0) + 1
                nxt.append((sc + c, path + [(l, why, c)], u))
        if not nxt:
            problems.append(f"{e['id']}: every fitting layout is blocked by the variety rules (limit {limit}x, no repeat)")
            nxt = [(sc + 100, path + [None], uses) for sc, path, uses in states]
        nxt.sort(key=lambda t: t[0])
        states = nxt[:beam]
    best = states[0]
    counts = {}
    for (si, e, s, visual, ok, rej), pick in zip(opts, best[1]):
        x = skel[si]
        if pick is None:
            x.update(reason="NO FIT", rejected=rej); continue
        l, why, c = pick
        counts[l["name"]] = counts.get(l["name"], 0) + 1
        pts = [t for _, t in s.get("content", [])]
        x.update(layout=l["name"], layout_index=l["index"],
                 reason=(f"{visual} ({len(pts)} points, {sum(len(t.split()) for t in pts)} words"
                         + (f", {len(s.get('companies') or [])} logos" if s.get("companies") else "") + ")"
                         + (": " + ", ".join(why) if why else "") + f"; fits; score {c:g}"),
                 alternatives=[o["name"] for o in ok if o["name"] != l["name"]], rejected=rej)
    for i, x in enumerate(skel, 1):
        x["n"] = i
    return {"schema": "sgdeck-match/1", "source": plan.get("source"), "family": family, "reuse_limit": limit,
            "short_pitch": short, "warnings": warnings,
            "total_score": round(best[0], 2),
            "layout_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])), "sequence": skel, "problems": problems}


def load(path):
    """{plan id: match entry} for builders."""
    M = json.load(open(path, encoding="utf-8"))
    return {x["id"]: x for x in M["sequence"] if x.get("id")}


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    dpath, ppath = argv[0], argv[1]
    out = argv[argv.index("-o") + 1] if "-o" in argv else os.path.join(os.path.dirname(os.path.abspath(ppath)), "match.json")
    fam = argv[argv.index("--family") + 1] if "--family" in argv else "Weiß"
    D = draft_check.parse(open(dpath, encoding="utf-8").read())
    plan = json.load(open(ppath, encoding="utf-8"))
    photos = json.load(open(argv[argv.index("--photos") + 1])) if "--photos" in argv else None
    M = match(D, plan, fam, photos=photos)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(M, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for x in M["sequence"]:
        print(f"{x['n']:>2} {x['kind']:<8} {x.get('id', ''):<4} {str(x['layout']):<26} {x.get('visual', '')}  {x['reason']}")
    print("layout counts:", M["layout_counts"])
    for w in M.get("warnings", []):
        print("WARN", w)
    for p in M["problems"]:
        print("FAIL", p)
    print(f"-> {out}")
    return 1 if M["problems"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Photo / illustration sourcing for layouts that need a picture (Zitat, Titelfolie mit Bild, Bild & Diagramm, Kapiteltrenner photo).

    from photos import select_image, needs_picture, select_or_illustrate
    pick = select_image("data centre servers", user_images=["/path/user.jpg"], cache="WORK/photos")
    # -> {"path", "source", "licence", "licence_url", "credit", "landing_url", "query"} or None

    python3 scripts/photos.py "data centre servers" --cache WORK/photos [--user img.jpg ...]

Order (RULES §8.2) – content leads, layout follows:
  1. an image the USER supplied (rights are the user's) – always first;
  2. if the content needs a picture: a generated ILLUSTRATION that represents the content
     (TODO: implement illustration generation in the visuals/infographics work; see select_or_illustrate);
  3. a free-licence stock image from Openverse only (CC0 / Public Domain Mark; CC BY stays OFF –
     `--allow-by` is accepted for emergency overrides but defaults to off and is not used by the skill);
     Unsplash / Pexels key paths are disabled (unused);
  4. None -> the caller uses the layout WITHOUT a picture: the matcher drops picture layouts
     (matcher.match(..., photos=False)) and s.quote(..., photo=None) removes the frame.
Rules: queries describe objects, places or abstract scenes only – never a named person, customer or brand
(BLOCKED_QUERY refuses capitalised names from the draft's companies list and person-like queries); results whose
title/tags name a brand or a person are skipped; nothing is generated or edited except via the illustration TODO.
Every pick is logged to <cache>/photos.json with its licence so the hand-off can list it. No network -> None
(logged), never an error."""
import json, os, re, sys, urllib.parse, urllib.request

UA = {"User-Agent": "sgdeck-photo-picker/1.0"}
FREE = {"cc0", "pdm"}
PERSONISH = re.compile(r"\b(portrait|ceo|cio|founder|person|man|woman|people named|headshot|selfie)\b", re.I)
BRANDISH = re.compile(r"(logo|brand|trademark|®|™)", re.I)

# Content that typically needs a picture on the slide (quote / cover / chapter photo slots).
NEEDS_PICTURE_HINTS = re.compile(
    r"\b(quote|testimonial|cover|title.?slide|chapter|divider|photo|portrait-of-place|architecture|"
    r"data.?centre|office|skyline)\b", re.I)


def needs_picture(slide_or_hint):
    """True when the slide\'s content calls for a picture (content leads; layout follows)."""
    if isinstance(slide_or_hint, dict):
        blob = " ".join([
            str(slide_or_hint.get("visual_hint") or ""),
            str(slide_or_hint.get("purpose") or ""),
            str(slide_or_hint.get("headline") or ""),
            " ".join(t for _, t in (slide_or_hint.get("content") or [])),
        ])
    else:
        blob = str(slide_or_hint or "")
    return bool(NEEDS_PICTURE_HINTS.search(blob) or (isinstance(slide_or_hint, dict)
                and slide_or_hint.get("visual_hint") in ("image", "quote")))


def blocked(query, names=()):
    if PERSONISH.search(query):
        return "query asks for a person - never source photos of people for a deck"
    for n in names:
        if n and re.search(r"\b" + re.escape(n) + r"\b", query, re.I):
            return f"query names '{n}' - never source photos of a named company or brand"
    if BRANDISH.search(query):
        return "query asks for a logo/brand"
    return None


def _get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _unsplash(q):
    """DISABLED – Unsplash key path unused (decision: Openverse only). Kept as a no-op stub."""
    return []


def _pexels(q):
    """DISABLED – Pexels key path unused (decision: Openverse only). Kept as a no-op stub."""
    return []


def _openverse(q, allow_by=False):
    # CC BY off by default (decision). allow_by kept for emergency CLI override only.
    lic = "cc0,pdm" + (",by" if allow_by else "")
    d = json.loads(_get("https://api.openverse.org/v1/images/?page_size=10&aspect_ratio=wide&mature=false&license="
                        + lic + "&q=" + urllib.parse.quote(q), timeout=40))   # the API often takes > 15 s
    out = []
    for r in d.get("results", []):
        tags = " ".join(t.get("name", "") for t in (r.get("tags") or []))
        out.append({"url": r["url"], "licence": r["license"] + (" " + r.get("license_version", "") if r.get("license_version") else ""),
                    "licence_url": r.get("license_url"), "credit": f"{r.get('creator') or 'unknown'} / {r.get('provider')}",
                    "landing_url": r.get("foreign_landing_url"), "title": (r.get("title") or "") + " " + tags,
                    "source": "openverse"})
    return out


def generate_illustration(query, cache="photos", slide=None):
    """TODO(visuals): generate an illustration that represents the slide content.

    Hook for the deferred infographics/visuals work. Must return the same dict shape as select_image
    ({path, source=\'illustration\', licence, ...}) or None. Until implemented, always returns None so the
    caller falls through to Openverse / no-picture layout.
    """
    # Intentionally unimplemented – content-led illustration generation lands with the visuals backlog.
    return None


REVIEW_NOTE = ("NOT YET APPROVED: open the image and reject it if it shows people, faces or brand names/logos "
               "(RULES §8.2). The title/tag filter cannot see the picture; a tested 'warehouse shelves' pick showed "
               "five people and branded boxes. Only after looking may it go into --photos.")


def select_image(query, user_images=(), cache="photos", names=(), allow_by=False, min_px=1000):
    """Return the first acceptable image as a dict, or None (-> layout without a picture).

    Order: user image -> Openverse CC0/PDM (CC BY off) -> None.
    Illustration generation is exposed via select_or_illustrate(), not here.
    """
    os.makedirs(cache, exist_ok=True)
    log_p = os.path.join(cache, "photos.json")
    log = json.load(open(log_p)) if os.path.exists(log_p) else []
    def done(rec):
        log.append({"query": query, **(rec or {"result": None})}); json.dump(log, open(log_p, "w"), indent=1)
        return rec
    for pth in user_images or ():
        if pth and os.path.exists(pth):
            return done({"path": os.path.abspath(pth), "source": "user", "licence": "user-supplied", "licence_url": None,
                         "credit": "supplied by the user", "landing_url": None, "query": query})
    why = blocked(query, names)
    if why:
        return done({"result": None, "reason": why}) and None
    errors = []
    # Openverse only (Unsplash / Pexels key paths are unused stubs – decision).
    try:
        cands = _openverse(query, allow_by)
    except Exception as e:
        errors.append(f"openverse: {e}"); cands = []
    for c in cands:
        if PERSONISH.search(c["title"]) or BRANDISH.search(c["title"]) or any(
                n and re.search(r"\b" + re.escape(n) + r"\b", c["title"], re.I) for n in names):
            continue
        try:
            data = _get(c["url"], timeout=25)
            ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
            path = os.path.join(cache, re.sub(r"\W+", "-", query)[:40] + f"-{c['source']}{ext}")
            open(path, "wb").write(data)
            from PIL import Image
            w, h = Image.open(path).size
            if w < min_px or w < h:
                os.remove(path); continue
            return done({"path": path, "query": query, **{k: c[k] for k in
                         ("source", "licence", "licence_url", "credit", "landing_url")},
                         "review": REVIEW_NOTE})
        except Exception as e:
            errors.append(str(e)); continue
    done({"result": None, "reason": "no acceptable free-licence image", "errors": errors[:5]})
    return None


def select_or_illustrate(query, user_images=(), cache="photos", names=(), slide=None, allow_by=False):
    """Content-led picker (RULES §8.2): user image -> illustration (if content needs a picture) -> Openverse -> None.

    Illustration generation is a TODO hook (generate_illustration); until the visuals work lands it is a no-op.
    """
    # 1. user image
    for pth in user_images or ():
        if pth and os.path.exists(pth):
            return select_image(query, user_images=[pth], cache=cache, names=names, allow_by=allow_by)
    # 2. illustration when content needs a picture
    if needs_picture(slide or query):
        ill = generate_illustration(query, cache=cache, slide=slide)
        if ill:
            return ill
    # 3. Openverse / 4. None
    return select_image(query, user_images=(), cache=cache, names=names, allow_by=allow_by)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(0)
    q = a[0]; cache = a[a.index("--cache") + 1] if "--cache" in a else "photos"
    users = [a[i + 1] for i, x in enumerate(a) if x == "--user"]
    r = select_or_illustrate(q, users, cache, allow_by="--allow-by" in a)
    print(json.dumps(r, indent=1) if r else "None -> use a layout without a picture")
    if r and r.get("review"):
        print("\n" + r["review"], file=sys.stderr)

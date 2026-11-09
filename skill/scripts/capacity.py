"""Text-capacity model shared by sgdeck.py (lint) and verify_deck.py.

Widths come from reference/outfit-metrics.json: real advance widths of Outfit, the preview proxy for the
unlicensed Mark Pro (+mj-lt -> Outfit 500, +mn-lt -> Outfit 300, bold -> 700). Line height uses LINE_FACTOR,
measured from the guide's own auto-fit placeholders (Mark Pro). Every width limit keeps HEADROOM (10 %)
because Mark Pro and Outfit widths differ slightly and kerning is ignored."""
import json, os
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_M = json.load(open(os.path.join(B, "reference", "outfit-metrics.json")))
_T = json.load(open(os.path.join(B, "tokens.json")))
CAP = _T.get("capacity", {})
# HEADROOM: every width limit is cut by this fraction. Outfit (the preview font) and the unlicensed Mark Pro
# differ by a few percent in advance widths, and kerning is ignored; 10 % covers the worst measured gap so a line
# that fits in the Outfit preview still fits in real Mark Pro. Stored in tokens.json -> capacity.safety.
HEADROOM = CAP.get("safety", 0.10)
SAFETY = HEADROOM   # legacy alias used by sgdeck/verify_deck
LINE_FACTOR = CAP.get("line_factor", 1.2)
EMU_PT = 12700
WEIGHT = {"+mj-lt": "500", "+mn-lt": "300", "bold": "700"}


def text_width_pt(text, size_pt, face="+mn-lt", bold=False):
    w = _M["weights"][WEIGHT["bold"] if bold else WEIGHT.get(face, "300")]
    return sum(w.get(c, w["_default"]) for c in text) * size_pt / _M["units_per_em"]


def wrap_lines(text, width_pt, size_pt, face="+mn-lt", bold=False):
    """Greedy word wrap like PowerPoint; returns number of lines (>=1). Over-long words break by character."""
    n = 0
    for hard in (text.split("\n") or [""]):
        n += 1; cur = 0.0
        sp = text_width_pt(" ", size_pt, face, bold)
        for word in hard.split(" "):
            ww = text_width_pt(word, size_pt, face, bold)
            if cur and cur + sp + ww > width_pt:
                n += 1; cur = 0.0
            while ww > width_pt:              # word longer than the line
                n += 1; ww -= width_pt
            cur = ww if not cur else cur + sp + ww
    return n


def avg_char_pt(size_pt, face="+mn-lt"):
    """Average advance of typical English business copy (letters, spaces, digits, punctuation)."""
    sample = ("Our platform helps teams plan, build and ship faster. Revenue grew 42% in 2025, and "
              "customers cut onboarding time from weeks to days with guided setup and shared dashboards.")
    return text_width_pt(sample, size_pt, face) / len(sample)


def used_height_pt(paras, spec, width_emu=None):
    """Height (pt, insets included) the paragraphs take in a placeholder/shape described by spec."""
    w_emu = width_emu or spec["w_emu"]
    inner_w = (w_emu - spec["ins"][0] - spec["ins"][2]) / EMU_PT * (1 - SAFETY)
    used = 0.0
    for i, (text, lvl, face, size, bold, marl) in enumerate(paras):
        lv = spec["levels"][min(lvl, len(spec["levels"]) - 1)]
        size = size or lv["size"]; face = face or lv["face"]
        marl = lv["marL_pt"] if marl is None else marl
        n = wrap_lines(text, inner_w - marl, size, face, bold)
        used += n * size * LINE_FACTOR * spec.get("ln_spc", 1.0) + (spec.get("spc_aft_pt", 0) if i else 0)
    return used + (spec["ins"][1] + spec["ins"][3]) / EMU_PT


def check_box(paras, spec, width_emu=None, height_emu=None):
    """paras: list of (text, level, face|None, size_pt|None, bold, marL_pt|None). spec: tokens.json capacity entry.
    Returns None if it fits, else a message."""
    w_emu = width_emu or spec["w_emu"]; h_emu = height_emu or spec["avail_h_emu"]
    inner_w = (w_emu - spec["ins"][0] - spec["ins"][2]) / EMU_PT * (1 - SAFETY)
    inner_h = (h_emu - spec["ins"][1] - spec["ins"][3]) / EMU_PT
    used, total_lines = 0.0, 0
    for i, (text, lvl, face, size, bold, marl) in enumerate(paras):
        lv = spec["levels"][min(lvl, len(spec["levels"]) - 1)]
        size = size or lv["size"]; face = face or lv["face"]
        marl = lv["marL_pt"] if marl is None else marl
        n = wrap_lines(text, inner_w - marl, size, face, bold)
        total_lines += n
        used += n * size * LINE_FACTOR * spec.get("ln_spc", 1.0) + (spec.get("spc_aft_pt", 0) if i else 0)
    if used > inner_h + 0.5:
        return (f"{total_lines} line(s) need {used:.0f} pt but the placeholder holds {inner_h:.0f} pt "
                f"(max {spec['lines']} line(s) of ~{spec['cpl']} chars)")
    return None


# ---------------------------------------------------------------------------------------------- slide scan
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
CONTENT_H_EMU = 3563937


def _paras(txBody):
    out = []
    for p in txBody.findall(_A + "p"):
        text = "".join((t.text or "") if t.tag == _A + "t" else "\n" for t in p.iter(_A + "t", _A + "br"))
        if not text.strip():
            continue
        pPr = p.find(_A + "pPr")
        lvl = int(pPr.get("lvl", 0)) if pPr is not None else 0
        marl = int(pPr.get("marL")) / EMU_PT if pPr is not None and pPr.get("marL") is not None else None
        r = p.find(_A + "r"); face = size = None; bold = False
        if r is not None and r.find(_A + "rPr") is not None:
            rp = r.find(_A + "rPr"); lt = rp.find(_A + "latin")
            face = lt.get("typeface") if lt is not None else None
            size = int(rp.get("sz")) / 100 if rp.get("sz") else None
            bold = rp.get("b") == "1"
        out.append((text, lvl, face, size, bold, marl))
    return out


def _own_spec(sp, size_default=18.0):
    bp = sp.find(f"{_P}txBody/{_A}bodyPr")
    if bp is not None and bp.get("wrap") == "none":
        return None
    xf = sp.find(f"{_P}spPr/{_A}xfrm")
    if xf is None:
        return None
    ext = xf.find(_A + "ext")
    ins = [int(bp.get(a, d)) if bp is not None else d for a, d in (("lIns", 91440), ("tIns", 45720), ("rIns", 91440), ("bIns", 45720))]
    w, h = int(ext.get("cx")), int(ext.get("cy"))
    return {"w_emu": w, "avail_h_emu": h, "ins": ins, "bullet": False, "spc_aft_pt": 0, "ln_spc": 1.0,
            "levels": [{"size": size_default, "face": "+mn-lt", "marL_pt": 0}], "cpl": "?", "lines": "?"}


def scan_slide(slide, layout_name):
    """Return a list of capacity findings (strings) for one python-pptx slide."""
    found, lay = [], CAP.get("layouts", {}).get(layout_name, {})
    tree = slide.shapes._spTree
    for sp in tree.iter(_P + "sp"):
        tx = sp.find(_P + "txBody")
        if tx is None:
            continue
        paras = _paras(tx)
        if not paras:
            continue
        ph = sp.find(f"{_P}nvSpPr/{_P}nvPr/{_P}ph")
        name = sp.find(f"{_P}nvSpPr/{_P}cNvPr").get("name")
        spec = None
        if ph is not None:
            if ph.get("type") in ("ftr", "sldNum", "dt"):
                continue
            spec = lay.get(ph.get("idx", "0"))
        if spec is None:
            spec = _own_spec(sp)
        if spec is None or spec["levels"][0]["size"] < 4:
            continue                        # unwrapped wordmark / hidden 1 pt tracker labels
        own = sp.find(f"{_P}spPr/{_A}xfrm/{_A}ext")
        w = int(own.get("cx")) if (own is not None and ph is not None) else None
        msg = check_box(paras, spec, width_emu=w)
        if msg:
            where = f"idx {ph.get('idx', '0')}" if ph is not None else f"shape '{name}'"
            found.append(f"{where}: {msg} - text starts '{paras[0][0][:40]}'")
    for gf in tree.iter(_P + "graphicFrame"):
        tbl = gf.find(f".//{_A}tbl")
        if tbl is None:
            continue
        widths = [int(c.get("w")) for c in tbl.find(_A + "tblGrid").findall(_A + "gridCol")]
        total = 0.0
        for r, tr in enumerate(tbl.findall(_A + "tr")):
            rh = int(tr.get("h")); worst = 1
            for c, tc in enumerate(tr.findall(_A + "tc")):
                pr = tc.find(_A + "tcPr"); g = lambda a, d: int(pr.get(a, d)) if pr is not None else d
                paras = _paras(tc.find(_A + "txBody"))
                if not paras:
                    continue
                spec = {"w_emu": widths[c], "avail_h_emu": 10 ** 9, "ins": [g("marL", 91440), 0, g("marR", 91440), 0],
                        "levels": [{"size": 14.0 if r == 0 else 12.0, "face": "+mn-lt", "marL_pt": 0}], "spc_aft_pt": 0}
                inner = (widths[c] - spec["ins"][0] - spec["ins"][2]) / EMU_PT * (1 - SAFETY)
                n = sum(wrap_lines(t, inner, s or spec["levels"][0]["size"], f or "+mn-lt", b) for t, _, f, s, b, _m in paras)
                worst = max(worst, n)
                if n > 1:
                    found.append(f"table r{r + 1}c{c + 1}: {n} lines - every cell fits ONE line (fixed 0.393 in rows); "
                                 f"shorten it or set col_w ('{paras[0][0][:30]}')")
            size = 14.0 if r == 0 else 12.0
            total += max(rh / EMU_PT, worst * size * LINE_FACTOR + 7.4)
        if total > CONTENT_H_EMU / EMU_PT + 1:
            found.append(f"table: {total / 72:.2f} in tall, content area is {CONTENT_H_EMU / 914400:.2f} in - split it")
    return found

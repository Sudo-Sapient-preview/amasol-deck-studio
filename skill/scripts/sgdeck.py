"""sgdeck - build decks that follow the saved style guide, starting from template.pptx.

Usage (python3):
    import sys; sys.path.insert(0, "<bundle>/scripts"); from sgdeck import *
    d = Deck()                                   # template.pptx, guide slides removed, embedded fonts stripped
                                                 # amasol branding (logo, copyright, links) is kept as designed
    d.agenda(["Topic one", "Topic two", "Topic three"])   # exactly 3 slots; > 8 items continue on 'Agenda (continued)'
    s = d.add("Inhalt - Weiß")                   # exact layout name; footer + hidden think-cell object added
    s.title("Claim-style title"); s.subtitle("Optional subtitle")
    s.body(11, [lead("Lead line"), "Bullet", ("Sub bullet", 1)])   # lead (bold Mark Pro) only as FIRST paragraph
    s.remove_empty()
    d.save("out.pptx")                           # lint, metadata reset, waivers recorded, foreign-brand guard
Only theme colours / theme fonts are written; nothing outside the guide is introduced.
Guard rails raise GuideError; deck-level rules can be waived only with a written reason
(d.save(path, waive={"dividers": "reason"})); waivers are stored in the deck and a sidecar
<out>.waivers.json and must be reported to the user. scripts/verify_deck.py re-runs lint_prs() on any file.
"""
import copy, datetime, difflib, json, math, os, re, sys, zipfile, shutil, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capacity
from lxml import etree
from pptx import Presentation
from pptx.util import Emu, Pt, Inches
from pptx.oxml.ns import qn
from pptx.enum.shapes import PP_PLACEHOLDER, MSO_SHAPE
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(BUNDLE, "template.pptx")
TOKENS = json.load(open(os.path.join(BUNDLE, "tokens.json")))
ICONS = os.path.join(BUNDLE, "assets", "icons")
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
NSMAP = {"a": A}

# theme colour slots - use these names, never raw hex for text/fills
RED, BLUE, WARMGREY, OLIVE, BLACK, LIGHTGREY, WHITE = "accent1", "accent2", "accent3", "accent4", "tx1", "bg1", "bg2"
SECONDARY_HEX = {"mint": "D3F1F0", "pink": "F5E1EA", "cream": "FFF8DF"}
SLOT_HEX = {"bg1": "EBEAE2", "bg2": "FFFFFF", "lt1": "EBEAE2", "lt2": "FFFFFF", "tx1": "000000", "dk1": "000000",
            "accent1": "DB2F16", "accent2": "0074A4", "accent3": "8B8A7C", "accent4": "C4A800"}
TYPE_SCALE = sorted({7, 8, 9, 10, 12, 14, 18, 20, 24, 32, 36, 48})

# --- template brand (the company that owns template.pptx) ---------------------------------------
TEMPLATE_BRAND = "amasol"                       # the deck brand: kept as-is in every built deck
KEPT_BRAND = {"name": "amasol", "company": "amasol GmbH", "kept": True}
FOREIGN_BRANDS = ("sudosapient",)              # leftover re-branding that must never appear AS BRANDING
BRAND_PARTS = ("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")   # where branding lives
BRAND_META = re.compile(rb"<(dc:creator|cp:lastModifiedBy|Company|Manager)>([^<]*)</")   # who made it, not the title


def foreign_branding(z):
    """Re-branding leftovers in a saved deck (zipfile): a foreign brand in the master, layouts or theme, as the
    author/company in the file metadata, or in a copyright line (©) anywhere. Naming a company in slide text or notes - e.g. the client of a
    proposal - is content, not branding, and is allowed."""
    hits = []
    for n in z.namelist():
        data = z.read(n).lower()
        if not any(f.encode() in data for f in FOREIGN_BRANDS):
            continue
        if n.startswith(BRAND_PARTS):
            hits.append(f"{n}: foreign brand in a branding part")
        elif n.startswith("docProps/"):
            who = [v for _, v in BRAND_META.findall(data) if any(f.encode() in v for f in FOREIGN_BRANDS)]
            if who:
                hits.append(f"{n}: foreign brand as author/company in the file metadata")
        elif n.endswith(".xml") and re.search(rb"(\xc2\xa9|&#169;|\(c\))[^<]{0,80}(" + b"|".join(
                f.encode() for f in FOREIGN_BRANDS) + rb")", data):
            hits.append(f"{n}: foreign brand in a copyright line")
    return hits
LOGO_GROUPS = {"Grafik 8"}                      # top-level logo groups on master + layouts
SOCIAL_GROUPS = {"Gruppieren 12"}               # closing-slide social/web icons (amasol links, kept)
THINKCELL_NAME = "think-cell data - do not delete"
TAGS_CT = "application/vnd.openxmlformats-officedocument.presentationml.tags+xml"
RT_TAGS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/tags"
RT_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
RT_HLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
RT_CUSTOMXML = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
RT_CUSTPROPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
RT_APPPROPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
CT_CUSTPROPS = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
WAIVER_PROP = "sgdeck_waivers"
MODE_PROP = "sgdeck_mode"                       # 'short-pitch' when the deck was saved in short-pitch mode
SHORT_PITCH_SKIPS = {"agenda", "dividers", "agenda-chapters"}   # rules short-pitch mode records instead of failing

COVERS = {"Titelfolie mit Bild", "Titelfolie ohne Bild"}
CLOSINGS = {"Schlussfolie - Blau", "Schlussfolie - Weiß"}
DIVIDERS = {"Kapiteltrenner - Gelb", "Kapiteltrenner - Weiß", "Kapiteltrenner - Blau"}
QUOTES = {"Zizat - Gelb", "Zitat- Rosa", "Zitat - Blau"}
KEYS = {"Key Slide 1", "Key Slide 2"}
CONTENT_PREFIXES = ("Inhalt", "2 Inhalte", "Bild & Diagramm", "Diagramm & Inhalt")
# sub-line / headline placeholders the guide always shows filled - never delete them
KEEP_FILLED = {**{n: (10, 13) for n in KEYS | QUOTES | {"Kapiteltrenner - Gelb", "Kapiteltrenner - Weiß"}},
               "Kapiteltrenner - Blau": (10, 12), "Agenda": (0,)}
MAX_ROWS = 9                                     # floor(3.898 in content height / 0.393 in row)
TILE_IDX = {"Key Slide 1": (14, 16, 17, 18), "Key Slide 2": (14, 16, 17, 18, 19, 20)}
# Agenda: (number tile idx, item idx) in the guide's reading order 01 02 / 03 04 / 05 06 / 07 08
AGENDA_SLOTS = [(12, 13), (28, 29), (19, 16), (31, 30), (23, 20), (33, 32), (27, 24), (35, 34)]
AGENDA_IDX = {i for pair in AGENDA_SLOTS for i in pair}
AGENDA_RE = re.compile(r"^Agenda( [2-7])?$")   # 'Agenda' (8 slots, the guide's) or per-count clones 'Agenda 2'..'Agenda 7'
AGENDA_CONT = "Agenda (continued)"


def is_agenda(layout_name):
    return bool(AGENDA_RE.match(layout_name or ""))


def base_layout(layout_name):
    """Guide layout a build-time clone derives from ('Agenda 7' -> 'Agenda')."""
    return "Agenda" if is_agenda(layout_name) else layout_name


def agenda_pages(n):
    """Split n agenda items over ceil(n/8) slides, balanced (11 -> 6 + 5; 9 -> 5 + 4) so no page is a stub."""
    pages = math.ceil(n / 8)
    per, extra = divmod(n, pages)
    return [per + (1 if p < extra else 0) for p in range(pages)]
# deck-level rules that may be waived with a written reason; everything else must be fixed
WAIVABLE = {"dividers", "agenda", "repeat", "layout-reuse", "background", "agenda-chapters", "infographics"}
PROMPT_RE = re.compile(r"(mastertitel|mastertext|textformat bearbeiten|untertitelformat|^untertitel$|lorem ipsum|"
                       r"^punkt \d$|klicken sie|click to add)", re.I)
UNIT_RE = re.compile(r"(\$|€|£|%|\bpercent\b|\bbillions?\b|\bmillions?\b|\bthousands?\b|\bbn\b|\bmn\b|\(k\)|"
                     r"\bEUR\b|\bUSD\b|\bGBP\b|\bunits?\b|\bhours?\b|\bdays?\b|\bweeks?\b|\bmonths?\b|\bFTEs?\b|"
                     r"\bnumber of\b|\bcount\b|\bpeople\b|\btonnes?\b|\bkWh\b|\bMWh\b)", re.I)
NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def key_count_problems(headline, subline, tiles):
    """Key Slide rule (lint and matcher): in the headline and in the sub-line, the count words ('two'..'ten') either
    add up to the number of pills/tiles ('four priorities and two targets' = 6) or each one names it ('six checks').
    Repeating the count in the other line is fine. Returns a list of messages (empty = fine)."""
    out = []
    for part, tx in (("headline", headline or ""), ("sub-line", subline or "")):
        said = [NUM_WORDS[w] for w in re.findall(r"[a-z]+", tx.lower()) if w in NUM_WORDS]
        if said and sum(said) != tiles and set(said) != {tiles}:
            out.append(f"the {part} says {' + '.join(map(str, said))} but {tiles} pills/tiles are filled - make the "
                       "count words match the tiles")
    return out


# Named icon positions (inches, top-left of the tile) measured from the guide's own examples.
ICON_SPOTS = {
    "infobox": (5.392, 4.20),   # Inhalt & Infobox: tile in the grey panel, under the big number (guide slide example)
    # "corner": bottom-right of the content area (computed below from the grid); for text-led slides whose text
    # or table ends above it - icon() refuses the spot if anything on the slide reaches into it.
}


class GuideError(Exception):
    """A style-guide rule was broken. Fix the content/structure - do not work around the check."""


def _sub(parent, tag, **attrs):
    el = etree.SubElement(parent, qn(tag))
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


def _scheme_fill(parent_spPr_or_rPr, slot):
    for old in parent_spPr_or_rPr.findall(qn("a:solidFill")):
        parent_spPr_or_rPr.remove(old)
    sf = etree.Element(qn("a:solidFill"))
    _sub(sf, "a:schemeClr", val=slot)
    return sf


class lead(str):
    """A lead line: Mark Pro (+mj-lt) BOLD, no bullet, flush left - exactly like the guide's 'Ebene 1, Mark Pro'
    example (guide slide 'Aufzählungszeichen'). Only allowed as the FIRST paragraph of a placeholder."""


class Para:
    def __init__(self, text, level=0, bold=False, heading_font=False, color=None, no_bullet=False, is_lead=False):
        self.text, self.level, self.bold, self.heading_font, self.color, self.no_bullet = text, level, bold, heading_font, color, no_bullet
        self.is_lead = is_lead


def _as_para(item):
    if isinstance(item, Para):
        return item
    if isinstance(item, lead):
        return Para(str(item), 0, heading_font=True, no_bullet=True, is_lead=True)
    if isinstance(item, tuple):
        return Para(item[0], item[1])
    return Para(item)


def _check_body_items(items, where):
    """Guide: one lead line max, only as the first paragraph; no other bold/heading-font paragraphs."""
    if isinstance(items, (str, Para)):
        items = [items]
    for i, it in enumerate(items):
        p = _as_para(it)
        if (p.heading_font or p.bold or p.is_lead) and i > 0:
            raise GuideError(f"{where}: bold/heading-font paragraph at position {i + 1} ('{p.text[:40]}'). "
                             "Mini-headings inside a body box are not a guide pattern - split into the second "
                             "column, the info box or another slide.")
        if p.bold and not p.is_lead:
            raise GuideError(f"{where}: bold runs are only used for lead lines (use lead()) and agenda numbers.")


def fill_text(shape, items, no_bullets=False):
    """Replace the text of a placeholder/shape. items: str | list of str/lead/(text, level)/Para.
    Paragraph formatting is inherited from the layout; only lead/bullet overrides are written."""
    if isinstance(items, (str, Para)):
        items = [items]
    tf = shape.text_frame
    txBody = tf._txBody
    for p in txBody.findall(qn("a:p")):
        txBody.remove(p)
    for it in items:
        it = _as_para(it)
        if "\u2192" in it.text or "\u2190" in it.text:
            raise GuideError(f"arrow glyph in '{it.text[:40]}': use words or an en dash (fonts may lack arrows)")
        p = _sub(txBody, "a:p")
        if it.level or it.no_bullet or no_bullets:
            pPr = _sub(p, "a:pPr")
            if it.level:
                pPr.set("lvl", str(it.level))
            if it.no_bullet or no_bullets:
                pPr.set("marL", "0"); pPr.set("indent", "0")
                _sub(pPr, "a:buNone")
        lines = it.text.split("\n")
        for i, line in enumerate(lines):
            if i:
                _sub(p, "a:br")
            r = _sub(p, "a:r")
            rPr = _sub(r, "a:rPr", lang="en-US", dirty="0")
            if it.bold or it.is_lead:
                rPr.set("b", "1")
            if it.color:
                rPr.append(_scheme_fill(rPr, it.color))
            if it.heading_font:
                _sub(rPr, "a:latin", typeface="+mj-lt")
            t = _sub(r, "a:t"); t.text = line
    return shape


def layout_bg_hex(layout):
    """Resolved background colour of a layout (falls back to the master)."""
    for el in (layout._element, layout.slide_master._element):
        bg = el.find(".//" + qn("p:bg"))
        if bg is not None:
            for c in bg.iter(qn("a:srgbClr"), qn("a:schemeClr")):
                v = c.get("val")
                return v.upper() if c.tag == qn("a:srgbClr") else SLOT_HEX.get(v, v)
    return "EBEAE2"


def fit_size(text, box_w_emu, box_h_emu, face="+mj-lt", min_pt=7, safety=None):
    """Largest guide type-scale size <= the box height that fits text on one line in the box width."""
    safety = capacity.HEADROOM if safety is None else safety
    h_pt, w_pt = box_h_emu / 12700, box_w_emu / 12700
    for sz in sorted((s for s in TYPE_SCALE if s <= h_pt + 0.01), reverse=True):
        if sz < min_pt:
            break
        if capacity.text_width_pt(text, sz, face) * (1 + safety) <= w_pt:
            return sz
    return None


# ================================================================================================ diagrams
# Diagram builders (RULES.md §17). Every value below is taken from tokens.json / the guide's layouts or derived from
# them; nothing is a free design choice. All builders draw inside the content area only, in theme colour slots,
# theme fonts and type-scale sizes, and group their shapes as 'sgdeck diagram: <type>' so lint/verify can find them.
_G = TOKENS["grid"]
CONTENT_BOX = (_G["margin_left_in"], _G["content_top_in"], _G["content_width_in"], _G["content_height_in"])
REGIONS = {                                     # named diagram regions (RULES §1 grid)
    "full": CONTENT_BOX,
    "left": (_G["two_column"]["left_x"], _G["content_top_in"], _G["two_column"]["col_w"], _G["content_height_in"]),
    "right": (_G["two_column"]["right_x"], _G["content_top_in"], _G["two_column"]["col_w"], _G["content_height_in"]),
    "text": (_G["margin_left_in"], _G["content_top_in"], _G["text_plus_visual"]["text_w"], _G["content_height_in"]),
    "visual": (_G["text_plus_visual"]["visual_x"], _G["content_top_in"], _G["text_plus_visual"]["visual_w"],
               _G["content_height_in"]),
}
_SHP = TOKENS["shapes"]
ADJ_PILL = _SHP["key_pill"]["adj"] / 100000               # pills (fully rounded ends)
ADJ_ICON_TILE = _SHP["icon_tile"]["adj"] / 100000
ICON_TILE_IN = _SHP["icon_tile"]["size_in"]                # guide showcase tile 0.727 in


def _decor_in(layout, name):
    lay = next(l for l in TOKENS["layouts"] if l["name"] == layout)
    return next(d["in"] for d in lay["decor"] if d["name"] == name)


# Absolute corner radii (inches) of the guide's own shapes; every diagram box uses one of them, so corners look the
# same at any box size (a fixed adj would give big boxes bigger corners).
_IBX = _decor_in("Inhalt & Infobox", "Rechteck: abgerundete Ecken 7")
R_PANEL = round(_SHP["panel_full"]["adj"] / 100000 * min(_IBX[2], _IBX[3]), 3)     # info-box panel, ~0.19 in
R_SMALL = round(ADJ_ICON_TILE * ICON_TILE_IN, 3)                                      # icon tile, ~0.12 in
VISUAL_SHARE = REGIONS["visual"][2] / CONTENT_BOX[2]       # guide text+visual split: visual takes ~43 % of the width
WHEEL_RING = 0.22               # ring thickness as a share of the wheel diameter (leaves a 2-line centre label)
WHEEL_GAP_DEG = 3               # white gap between wheel segments, degrees
BAND_SHARES = (0.25, 0.5, 0.25)  # goal | approach | result: the approach carries the list, so it gets half
ICON_RATIO = _SHP["icon_tile"]["icon_in"] / ICON_TILE_IN   # icon = half the tile (0.363 / 0.727)
HERO_ICON_IN = 1.5 * ICON_TILE_IN                          # divider hero icon; PNGs are 128 px -> keep <= ~1.1 in
INSET_X, INSET_Y = 108000 / 914400, 72000 / 914400         # guide text-box padding (one cap height)


def _key_gap():
    """Gutter between the guide's Key Slide 2 tiles - the guide's own spacing for side-by-side boxes."""
    lay = {l["name"]: {p["idx"]: p["in"] for p in l["placeholders"]} for l in TOKENS["layouts"]}["Key Slide 2"]
    return round(lay[16][0] - lay[14][0] - lay[14][2], 3)


GAP_IN = _key_gap()                                         # 0.119 in
ICON_SPOTS["corner"] = (round(CONTENT_BOX[0] + CONTENT_BOX[2] - ICON_TILE_IN, 3),
                        round(CONTENT_BOX[1] + CONTENT_BOX[3] - ICON_TILE_IN, 3))
ROW_GAP_IN = GAP_IN / 2                                     # stacked rows inside one column
ARROW_GAP_IN = 3 * GAP_IN                                   # room for a connector arrow between two boxes
LINE_PT = {"thin": 1, "mid": 1.5, "bold": 3}                # the guide's line weights (RULES §4)
DIAGRAM_SIZES = (12, 10)        # label sizes: 12 pt reading size, 10 pt = the guide's chart-text size (RULES §17)
HEAD_SIZES = (14, 12)           # box headings: lead-line size, then subtitle size
VALUE_SIZES = (32, 24)          # key numbers: info-box number size, then section-number size
SPACE_AFTER_PT = 3              # guide paragraph spacing (RULES §2)
_HEX_SLOT = {"DB2F16": RED, "0074A4": BLUE, "8B8A7C": WARMGREY, "C4A800": OLIVE, "000000": BLACK,
             "EBEAE2": LIGHTGREY, "FFFFFF": WHITE}
PILL_FILLS = [_HEX_SLOT[h] for h in _SHP["key_pill"]["fills"]]   # red, blue, olive, black (Key Slide 1 order)
TILE_FILLS = [_HEX_SLOT[h] for h in _SHP["key_tile"]["fills"]]   # red, warm grey, blue, olive, black, light grey
CHART_FILLS = [_HEX_SLOT[h] for h in TOKENS["colors"]["chart_series_order"]]
WHITE_TEXT_ON = {RED, BLUE, WARMGREY, OLIVE, BLACK}               # RULES §3.4
INFOGRAPHICS = {"donut", "pie", "wheel", "staircase", "tiers", "process"}     # shape-led visuals (capped)
STRUCTURED = {"tile_grid", "fact_chips", "band", "story_panel", "icon_set"}
DIAGRAM_PREFIX = "sgdeck diagram: "
ICON_PREFIX = "sgdeck icon: "
INFOBOX_NAME = "sgdeck info box"
ICON_TILE_NAME = "sgdeck icon tile"
LOGO_PREFIX = "sgdeck logo: "          # logo pictures (alt text = company name), RULES §8.1
LOGO_CHIP_NAME = "sgdeck logo chip"
TILE_SHAPES = ("auto", "rounded", "circle")   # icon backing: auto = match the container (RULES §7)
FULL_ROUND_ADJ = 0.49           # roundRect adj (radius / short side) from which both ends are fully rounded (pill)
LOGO_MIN_RATIO = 3.0            # WCAG 2.x non-text contrast (1.4.11) for a logo against what it sits on
LOGO_MIN_SHARE = 0.5            # share of a logo's visible marks that must reach LOGO_MIN_RATIO
LOGO_VISIBLE_RATIO = 1.25       # below this a pixel is indistinguishable from the background
LOGO_MAX_LOST = 0.1             # a logo fails if more than 10 % of it vanishes into the background
LOGO_CHIP_FILLS = (WHITE, BLUE, BLACK)        # palette chips tried, in order, when a logo fails on its tile
LOGO_MAX_SIDE_IN = 0.55         # sqrt(area) cap: a square logo is at most 0.55 in
LOGO_GAP_X, LOGO_GAP_Y = 1.5 * GAP_IN, GAP_IN / 2   # space between logos in a row / between rows
LOGO_H_RANGE = (0.45, 0.8)      # logo height as a share of the size s: equal area, clamped so square marks do not
                                # tower over wordmarks and long wordmarks keep a readable height
LOGO_CHIP_PAD = 0.2             # chip padding around a logo, share of the logo height (at least LOGO_CHIP_PAD_MIN)
LOGO_CHIP_PAD_MIN = 0.03
NUMBER_NAME = "sgdeck sequence number"   # step/stage numbers a builder adds (structural, like agenda numbers)
INFOGRAPHIC_SHARE = 1 / 3       # cap: about one content slide in three may be an infographic (RULES §17.2)
SHORT_PITCH_MAX = 10            # decks up to this many slides may skip agenda + dividers (short-pitch mode)


def container_kind(el):
    """Roundness of a p:sp element: 'full' (ellipse/circle, or a pill/stadium = roundRect whose corner radius is
    at least half its short side), 'round' (rounded rectangle), 'square' (rectangle) or None (no preset)."""
    g = el.find(f"{qn('p:spPr')}/{qn('a:prstGeom')}") if el is not None else None
    if g is None:
        return None
    prst = g.get("prst")
    if prst in ("ellipse", "flowChartConnector", "flowChartTerminator"):
        return "full"
    if prst == "roundRect":
        adj = 16667
        for gd in g.iter(qn("a:gd")):
            if gd.get("name") == "adj":
                adj = int(gd.get("fmla", "val 16667").split()[-1])
        return "full" if adj / 100000 >= FULL_ROUND_ADJ else "round"
    if prst in ("round1Rect", "round2SameRect", "round2DiagRect", "snipRoundRect"):
        return "round"
    if prst == "rect":
        return "square"
    return None


def tile_for(container_el):
    """Icon backing that matches a container: 'circle' in pills, ovals and circles, else 'rounded' (the guide's
    rounded-square icon tile, adj 16667)."""
    return "circle" if container_kind(container_el) == "full" else "rounded"


def _walk_abs(parent, T=(0.0, 0.0, 1.0, 1.0)):
    """(element, (x, y, w, h) in inches) for every sp/pic/cxnSp/graphicFrame under parent, group transforms applied."""
    ox, oy, sx, sy = T
    for el in parent:
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "grpSp":
            xf = el.find(f"{qn('p:grpSpPr')}/{qn('a:xfrm')}")
            inner = T
            if xf is not None and xf.find(qn("a:off")) is not None:
                off, ext = xf.find(qn("a:off")), xf.find(qn("a:ext"))
                co, ce = xf.find(qn("a:chOff")), xf.find(qn("a:chExt"))
                gx, gy = int(off.get("x")), int(off.get("y"))
                cx0, cy0 = (int(co.get("x")), int(co.get("y"))) if co is not None else (gx, gy)
                kx = int(ext.get("cx")) / int(ce.get("cx")) if ce is not None and int(ce.get("cx")) else 1.0
                ky = int(ext.get("cy")) / int(ce.get("cy")) if ce is not None and int(ce.get("cy")) else 1.0
                inner = (ox + sx * (gx - cx0 * kx) / 914400, oy + sy * (gy - cy0 * ky) / 914400, sx * kx, sy * ky)
            yield from _walk_abs(el, inner)
        elif tag in ("sp", "pic", "cxnSp", "graphicFrame"):
            xf = el.find(f"{qn('p:spPr')}/{qn('a:xfrm')}") if tag != "graphicFrame" else el.find(qn("p:xfrm"))
            if xf is None or xf.find(qn("a:off")) is None:
                continue
            off, ext = xf.find(qn("a:off")), xf.find(qn("a:ext"))
            yield el, (ox + sx * int(off.get("x")) / 914400, oy + sy * int(off.get("y")) / 914400,
                       sx * int(ext.get("cx")) / 914400, sy * int(ext.get("cy")) / 914400)


def _painted(el):
    """True if a p:sp draws a visible fill or outline (text boxes and invisible frames are not containers)."""
    if el.tag != qn("p:sp"):
        return False
    spPr = el.find(qn("p:spPr"))
    if spPr is None:
        return False
    if any(spPr.find(qn(t)) is not None for t in ("a:solidFill", "a:gradFill", "a:pattFill", "a:blipFill")):
        return True
    ln = spPr.find(qn("a:ln"))
    if ln is not None and ln.find(qn("a:solidFill")) is not None:
        return True
    return spPr.find(qn("a:noFill")) is None and el.find(qn("p:style")) is not None


def _fill_hex(el):
    """Solid fill colour of a p:sp as hex (theme slots resolved with the guide theme), else None."""
    sf = el.find(f"{qn('p:spPr')}/{qn('a:solidFill')}") if el is not None else None
    if sf is None or not len(sf):
        return None
    c = sf[0]
    if c.tag == qn("a:srgbClr"):
        return c.get("val", "").upper()
    if c.tag == qn("a:schemeClr"):
        return SLOT_HEX.get(c.get("val"))
    return None


def _contains(outer, inner, tol=0.01):
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1] and
            inner[0] + inner[2] <= outer[0] + outer[2] + tol and inner[1] + inner[3] <= outer[1] + outer[3] + tol)


def _container_of(box, candidates, exclude=()):
    """Smallest painted shape whose box holds `box` (candidates: [(el, bbox)]); None on the bare slide."""
    best = None
    for el, b in candidates:
        if el in exclude or not _painted(el) or not _contains(b, box) or b[2] * b[3] <= box[2] * box[3] * 1.05:
            continue
        if _name(el) == ICON_TILE_NAME:          # a tile never contains another tile
            continue
        if best is None or b[2] * b[3] < best[1][2] * best[1][3]:
            best = (el, b)
    return best


def _rel_lum(rgb):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def logo_legibility(img, bg_hex, ratio=LOGO_MIN_RATIO):
    """Share (0-1) of a logo's visible marks that reach `ratio` contrast with the background bg_hex.
    Pixels that vanish into the background (< LOGO_VISIBLE_RATIO) count as failures when they connect to the
    outside (white lettering on a light tile is lost), but not when they are enclosed by the logo's own shapes
    (the white inside a box or oval logo belongs to the mark). Opaque logo boxes are measured as drawn."""
    from PIL import Image
    import numpy as np
    if not hasattr(img, "convert"):
        img = Image.open(img)
    im = img.convert("RGBA")
    im.thumbnail((240, 240))
    a = np.pad(np.asarray(im, dtype=float), ((1, 1), (1, 1), (0, 0)))      # transparent frame = the outside
    bg = np.array([int(bg_hex[k:k + 2], 16) for k in (0, 2, 4)], dtype=float)
    lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    lb = float(lin(bg / 255.0) @ np.array([0.2126, 0.7152, 0.0722]))
    alpha = a[..., 3] / 255.0
    ink = alpha >= 0.5
    if not ink.any():
        return 0.0
    comp = (a[..., :3] * alpha[..., None] + bg * (1 - alpha[..., None])) / 255.0
    L = lin(comp) @ np.array([0.2126, 0.7152, 0.0722])
    cr = (np.maximum(L, lb) + 0.05) / (np.minimum(L, lb) + 0.05)
    open_ = ~ink | (cr < LOGO_VISIBLE_RATIO)             # background or indistinguishable from it
    outside = np.zeros_like(open_)
    stack = [(0, 0)]
    outside[0, 0] = True
    H, W = open_.shape
    while stack:                                          # flood fill from the frame through open pixels
        y, x = stack.pop()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < H and 0 <= xx < W and open_[yy, xx] and not outside[yy, xx]:
                outside[yy, xx] = True
                stack.append((yy, xx))
    enclosed = ink & open_ & ~outside
    kept = ink & ~enclosed
    if not kept.any():
        return 0.0
    lost = (ink & open_ & outside).sum() / kept.sum()     # lettering that merges with the background
    return 0.0 if lost > LOGO_MAX_LOST else float((cr[kept] >= ratio).mean())


def _logo_ink(path):
    """(PIL image, crop box) of a logo file trimmed to its opaque pixels (transparent margins removed)."""
    from PIL import Image
    im = Image.open(path)
    rgba = im.convert("RGBA")
    box = rgba.getchannel("A").point(lambda v: 255 if v >= 8 else 0).getbbox() or (0, 0) + rgba.size
    return rgba, box


def infographic_cap(n_content):
    """Max infographic slides for n content slides (cover, agenda, dividers and closing excluded)."""
    return max(1, math.floor(n_content * INFOGRAPHIC_SHARE + 1e-9)) if n_content else 0


def _paras_height_pt(paras, w_in, insets=True):
    """Height a list of (text, size, heading) paragraphs needs in a box of width w_in (Outfit metrics + HEADROOM)."""
    inner = (w_in - (2 * INSET_X if insets else 0)) * 72 * (1 - capacity.HEADROOM)    # same rule as capacity.check_box
    if inner <= 0:
        return float("inf")
    h = 0.0
    for k, (text, size, heading) in enumerate(paras):
        lines = capacity.wrap_lines(text, inner, size, "+mj-lt" if heading else "+mn-lt")
        h += lines * size * capacity.LINE_FACTOR + (SPACE_AFTER_PT if k else 0)
    return h + (2 * INSET_Y * 72 if insets else 0)


def _valign(y, h, used, valign):
    """Top of a block of height `used` inside a region (y, h): 'top' | 'middle' | 'bottom'."""
    if valign not in ("top", "middle", "bottom"):
        raise GuideError(f"valign must be 'top', 'middle' or 'bottom', got {valign!r}")
    return y + {"top": 0, "middle": (h - used) / 2, "bottom": h - used}[valign]


def _one_line_in(text, size, face="+mn-lt"):
    """Width (in) a zero-inset box needs to hold text on one line, headroom included."""
    return capacity.text_width_pt(text, size, face) / (1 - capacity.HEADROOM) / 72 + 0.01


def _fits(paras, w_in, h_in, insets=True):
    return _paras_height_pt(paras, w_in, insets) <= h_in * 72 + 0.5


class _Diagrams:
    """Mixin for Slide: guide-styled diagram builders. Each returns the group shape it drew."""

    # --- primitives ---------------------------------------------------------------------------------
    def _region(self, region):
        box = REGIONS.get(region) if isinstance(region, str) else region
        if box is None:
            raise GuideError(f"unknown region '{region}'; use one of {sorted(REGIONS)} or (x, y, w, h) in inches")
        x, y, w, h = box
        X, Y, W, H = CONTENT_BOX
        tol = 0.005
        if x < X - tol or y < Y - tol or x + w > X + W + tol or y + h > Y + H + tol:
            raise GuideError(f"region {tuple(round(v, 3) for v in box)} leaves the content area "
                             f"x {X}-{X + W:.3f}, y {Y}-{Y + H:.3f} in (RULES §1)")
        return x, y, w, h

    def _box(self, x, y, w, h, fill=None, line=None, line_pt=LINE_PT["thin"], radius=R_SMALL, shape="round", adj=None):
        """Rounded box with a guide corner radius (inches) - or adj for pills; shape 'rect' for plain text boxes."""
        kind = {"round": MSO_SHAPE.ROUNDED_RECTANGLE, "rect": MSO_SHAPE.RECTANGLE, "oval": MSO_SHAPE.OVAL}[shape]
        sh = self.s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
        if shape == "round":
            sh.adjustments[0] = adj if adj is not None else min(0.5, radius / min(w, h))
        _plain_fill(sh, fill, line=line, line_w=int(line_pt * 12700))
        return sh

    def _write(self, sh, paras, color=BLACK, anchor="t", insets=True, align="l"):
        """paras: [(text, size, heading)] - theme fonts, type-scale sizes, one theme colour, no bullets."""
        tf = sh.text_frame
        tf.word_wrap = True
        bp = tf._txBody.find(qn("a:bodyPr"))
        ins = (108000, 72000) if insets else (0, 0)
        for k, v in (("lIns", ins[0]), ("tIns", ins[1]), ("rIns", ins[0]), ("bIns", ins[1]), ("anchor", anchor)):
            bp.set(k, str(v))
        for old in list(bp):
            bp.remove(old)
        _sub(bp, "a:noAutofit")
        txBody = tf._txBody
        for p in txBody.findall(qn("a:p")):
            txBody.remove(p)
        for k, (text, size, heading) in enumerate(paras):
            if size not in TYPE_SCALE:
                raise GuideError(f"{size} pt is not on the guide type scale {TYPE_SCALE}")
            if "\u2192" in text or "\u2190" in text:
                raise GuideError(f"arrow glyph in '{text[:40]}': use words or an en dash (fonts may lack arrows)")
            p = _sub(txBody, "a:p")
            pPr = _sub(p, "a:pPr", marL="0", indent="0", algn=align)
            ls = _sub(pPr, "a:lnSpc"); _sub(ls, "a:spcPct", val="100000")
            sb = _sub(pPr, "a:spcBef"); _sub(sb, "a:spcPts", val="0")
            sa = _sub(pPr, "a:spcAft"); _sub(sa, "a:spcPts", val=str(SPACE_AFTER_PT * 100 if k < len(paras) - 1 else 0))
            _sub(pPr, "a:buNone")
            r = _sub(p, "a:r")
            rPr = _sub(r, "a:rPr", lang="en-US", sz=str(int(size * 100)), b="0", dirty="0")
            sf = _sub(rPr, "a:solidFill"); _sub(sf, "a:schemeClr", val=color)
            _sub(rPr, "a:latin", typeface="+mj-lt" if heading else "+mn-lt")
            t = _sub(r, "a:t"); t.text = text
        return sh

    def _text_box(self, x, y, w, h, paras, color=BLACK, anchor="t", fill=None, line=None, radius=R_SMALL,
                  shape="round", insets=True, what="label", align="l", name=None):
        if not _fits(paras, w, h, insets):
            need = _paras_height_pt(paras, w, insets) / 72
            raise GuideError(f"{what}: '{paras[0][0][:40]}...' needs {need:.2f} in height, box is {w:.2f} x {h:.2f} in - "
                             "shorten the copy (split or rephrase from the source) or use fewer items")
        sh = self._box(x, y, w, h, fill=fill, line=line, radius=radius, shape=shape)
        if name:
            sh.name = name
        return self._write(sh, paras, color=color, anchor=anchor, insets=insets, align=align)

    def _fit(self, make, w, h, sizes=DIAGRAM_SIZES, insets=True, what="label"):
        """make(size) -> paras; first size in `sizes` whose paragraphs fit w x h; GuideError otherwise."""
        for sz in sizes:
            paras = make(sz)
            if _fits(paras, w, h, insets):
                return paras
        need = _paras_height_pt(make(sizes[-1]), w, insets) / 72
        raise GuideError(f"{what}: text needs {need:.2f} in at {sizes[-1]} pt but the box is {w:.2f} x {h:.2f} in - "
                         "shorten the copy (never below the type scale) or use fewer items")

    def _tile_kind(self, x, y, tile_in, container=None, tile_shape=None):
        """'rounded' or 'circle' for an icon tile at (x, y): explicit tile_shape wins; else it matches the container
        (the shape given, or the smallest painted slide/layout shape around the tile; none -> rounded)."""
        ts = tile_shape or getattr(self, "_ts", "auto")
        if ts not in TILE_SHAPES:
            raise GuideError(f"tile_shape must be one of {TILE_SHAPES}, got {ts!r}")
        if ts != "auto":
            return ts
        if container is not None:
            return tile_for(getattr(container, "_element", container))
        box = (x, y, tile_in, tile_in)
        cands = list(_walk_abs(self.s.shapes._spTree)) + [
            (el, b) for el, b in _walk_abs(self.layout.shapes._spTree) if el.find(".//" + qn("p:ph")) is None]
        hit = _container_of(box, cands)
        return tile_for(hit[0]) if hit else "rounded"

    def _tile_shape(self, x, y, tile_in, kind):
        """The white icon backing: the guide's rounded square (adj 16667) or a circle of the same size."""
        if kind == "circle":
            t = self.s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(tile_in), Inches(tile_in))
        else:
            t = self.s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(tile_in), Inches(tile_in))
            t.adjustments[0] = ADJ_ICON_TILE
        _plain_fill(t, WHITE)
        t.name = ICON_TILE_NAME
        return t

    def _icon_shapes(self, name, x, y, tile_in, container=None, tile_shape=None):
        """Guide icon on a white tile (icon = half the tile) whose shape matches its container: rounded square in
        rounded boxes, circle in pills/ovals (RULES §7). Returns [tile, picture]."""
        path = os.path.join(ICONS, name if name.endswith(".png") else name + ".png")
        if not os.path.exists(path):
            close = difflib.get_close_matches(name, [f[:-4] for f in os.listdir(ICONS) if f.endswith(".png")], n=3)
            raise GuideError(f"icon '{name}' is not in the guide set" + (f"; did you mean {close}?" if close else "")
                             + " - see assets/icons/index.json")
        size = round(tile_in * ICON_RATIO, 3)
        key = (size, True)
        if self.icon_sizes and key not in self.icon_sizes:
            raise GuideError(f"'{self.name}': icons must share one size/treatment per slide (have "
                             f"{sorted(self.icon_sizes)}, asked {key}) - use one builder or one icon size per slide")
        self.icon_sizes.add(key)
        t = self._tile_shape(x, y, tile_in, self._tile_kind(x, y, tile_in, container, tile_shape))
        off = (tile_in - size) / 2
        pic = self.s.shapes.add_picture(path, Inches(x + off), Inches(y + off), Inches(size), Inches(size))
        pic.name = ICON_PREFIX + os.path.basename(path)[:-4]
        return [t, pic]

    def _arrow(self, x1, y1, x2, y2, pt=LINE_PT["mid"], slot=BLUE, head=False, tail=True):
        """Straight guide line (blue, 1/1.5/3 pt) with triangle arrowheads."""
        from pptx.enum.shapes import MSO_CONNECTOR
        c = self.s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
        st = c._element.find(qn("p:style"))
        if st is not None:
            c._element.remove(st)
        spPr = c._element.spPr
        for old in spPr.findall(qn("a:ln")):
            spPr.remove(old)
        ln = _sub(spPr, "a:ln", w=str(int(pt * 12700)), cap="flat")
        sf = _sub(ln, "a:solidFill"); _sub(sf, "a:schemeClr", val=slot)
        _sub(ln, "a:prstDash", val="solid"); _sub(ln, "a:round")
        _sub(ln, "a:headEnd", type="triangle" if head else "none")
        _sub(ln, "a:tailEnd", type="triangle" if tail else "none")
        return c

    def _group(self, shapes, kind, plan=None):
        if kind in INFOGRAPHICS | STRUCTURED and any(v in INFOGRAPHICS | STRUCTURED for v in self.visuals):
            raise GuideError(f"'{self.name}': one main visual per slide (already has {self.visuals}) - "
                             "move the second visual to its own slide (RULES §17.2)")
        g = self.s.shapes.add_group_shape(shapes)
        g.name = DIAGRAM_PREFIX + kind + (f" [{plan}]" if plan else "")
        self.visuals.append(kind)
        self.free_shapes.append(kind)
        return g

    @staticmethod
    def _items(items, keys, what):
        out = []
        for it in items:
            if isinstance(it, dict):
                out.append({k: it.get(k) for k in keys})
            else:
                it = tuple(it) + (None,) * (len(keys) - len(it))
                out.append(dict(zip(keys, it)))
        for k, it in enumerate(out, 1):
            if not it[keys[0]]:
                raise GuideError(f"{what}: item {k} has no '{keys[0]}'")
        return out

    # --- 1 process row --------------------------------------------------------------------------------
    def process(self, steps, region="full", numbered=True, valign="middle", plan=None, tile_shape="auto"):
        """Sequential steps left to right: light-grey panels, icon tile, number, title, text; blue arrows between.
        steps: [(title, text, icon)] or dicts; 2-6 steps; every step needs a guide icon (RULES §7)."""
        self._ts = tile_shape
        st = self._items(steps, ("title", "text", "icon"), "process")
        if not 2 <= len(st) <= 6:
            raise GuideError(f"process: 2-6 steps, got {len(st)} - split into two slides or use a table")
        if any(not s["icon"] for s in st):
            raise GuideError("process: every step needs a guide icon (assets/icons/index.json)")
        x, y, w, h = self._region(region)
        n = len(st)
        pw = (w - (n - 1) * ARROW_GAP_IN) / n
        tile = min(ICON_TILE_IN, pw - 2 * INSET_X)
        text_h = h - 2 * INSET_Y - tile - GAP_IN
        made, bodies = [], []
        for s_ in st:
            def mk(sz, s_=s_):
                p = [(s_["title"], sz + 2 if sz + 2 in TYPE_SCALE else sz, True)]
                return p + ([(s_["text"], sz, False)] if s_["text"] else [])
            bodies.append(mk)
        sizes = next((sz for sz in DIAGRAM_SIZES if all(_fits(b(sz), pw, text_h) for b in bodies)), None)
        if sizes is None:
            raise GuideError("process: step text does not fit even at 10 pt - shorten each step to one short line")
        need = max(_paras_height_pt(b(sizes), pw) for b in bodies) / 72
        ph = min(h, INSET_Y + tile + GAP_IN + need)
        y = _valign(y, h, ph, valign)
        for k, s_ in enumerate(st):
            px = x + k * (pw + ARROW_GAP_IN)
            made.append(self._box(px, y, pw, ph, fill=LIGHTGREY))
            made += self._icon_shapes(s_["icon"], px + INSET_X, y + INSET_Y, tile, container=made[-1])
            if numbered:
                made.append(self._text_box(px + INSET_X + tile + GAP_IN, y + INSET_Y, pw - 2 * INSET_X - tile - GAP_IN,
                                           tile, [(f"{k + 1:02d}", 24, True)], anchor="ctr", insets=False,
                                           shape="rect", what="process number", name=NUMBER_NAME))
            made.append(self._text_box(px, y + INSET_Y + tile + GAP_IN - INSET_Y, pw, need, bodies[k](sizes),
                                       shape="rect", what=f"process step {k + 1}"))
            if k < n - 1:
                ay = y + INSET_Y + tile / 2
                made.append(self._arrow(px + pw + GAP_IN / 2, ay, px + pw + ARROW_GAP_IN - GAP_IN / 2, ay))
        return self._group(made, "process", plan)

    # --- 2 staircase with arrow -----------------------------------------------------------------------
    def staircase(self, levels, region="full", axis=None, highlight_new=True, plan=None, tile_shape="auto"):
        """Maturity levels as rising columns, bottom-aligned. levels: [{'label': 'Level 1', 'name': 'Standardized',
        'items': [(text, icon), ...]}] with items bottom to top. An item that first appears at a level is a red
        Fläche box (from level 2 on; level 1 is the baseline), items carried over are blue Rahmen boxes
        (highlight_new=False: all Rahmen). axis=('Reactive','Proactive')
        draws the blue 3 pt arrow under the labels with the two words at its ends. Only levels the source gives."""
        self._ts = tile_shape
        lv = [dict(label=l["label"], name=l.get("name", ""), items=self._items(l["items"], ("text", "icon"), "staircase"))
              for l in levels]
        if not 2 <= len(lv) <= 5:
            raise GuideError(f"staircase: 2-5 levels, got {len(lv)}")
        if any(not it["icon"] for l in lv for it in l["items"]):
            raise GuideError("staircase: every item needs a guide icon (RULES §7: icons on lists of levels/items)")
        x, y, w, h = self._region(region)
        n, m = len(lv), max(len(l["items"]) for l in lv)
        cw = (w - (n - 1) * GAP_IN) / n
        label_h = 12 * capacity.LINE_FACTOR / 72
        axis_h = (10 * capacity.LINE_FACTOR / 72 + GAP_IN) if axis else 0
        rows_h = h - label_h - GAP_IN - axis_h
        rh = min(ICON_TILE_IN, (rows_h - (m - 1) * ROW_GAP_IN) / m)     # rows never taller than a showcase tile
        tile = round(rh - INSET_Y, 3)
        tw = cw - 2 * INSET_X - tile - GAP_IN / 2
        texts = [it["text"] for l in lv for it in l["items"]]
        sz = next((s for s in DIAGRAM_SIZES if all(_fits([(t, s, False)], tw, rh - 2 * INSET_Y, insets=False)
                                                    for t in texts)), None)
        if sz is None:
            raise GuideError(f"staircase: item labels do not fit {tw:.2f} x {rh:.2f} in even at 10 pt - shorten them "
                             "or reduce the number of items per level")
        made, prev = [], set()
        base = y + rows_h
        for k, l in enumerate(lv):
            cx = x + k * (cw + GAP_IN)
            for r, it in enumerate(l["items"]):
                ry = base - (r + 1) * rh - r * ROW_GAP_IN
                new = highlight_new and k > 0 and it["text"] not in prev
                box = self._box(cx, ry, cw, rh, fill=RED if new else None, line=None if new else BLUE)
                made.append(box)
                made += self._icon_shapes(it["icon"], cx + INSET_X / 2, ry + (rh - tile) / 2, tile, container=box)
                made.append(self._text_box(cx + INSET_X / 2 + tile + GAP_IN / 2, ry, tw + INSET_X, rh,
                                           [(it["text"], sz, False)], color=WHITE if new else BLACK, anchor="ctr",
                                           insets=False, shape="rect", what="staircase item"))
            prev = {it["text"] for it in l["items"]}
            lab = [(f"{l['label']} {l['name']}".strip(), 12, True)]
            made.append(self._text_box(cx, base + GAP_IN, cw, label_h, lab, insets=False, shape="rect",
                                       what="staircase level label"))
        if axis:
            ay = y + h - axis_h / 2 + GAP_IN / 2
            left, right = axis
            lw = _one_line_in(left, 10)
            rw = _one_line_in(right, 10)
            th = 10 * capacity.LINE_FACTOR / 72
            made.append(self._text_box(x, ay - th / 2, lw, th, [(left, 10, False)], insets=False, shape="rect",
                                       anchor="ctr", what="axis label"))
            made.append(self._text_box(x + w - rw, ay - th / 2, rw, th, [(right, 10, False)], insets=False,
                                       shape="rect", anchor="ctr", what="axis label"))
            made.append(self._arrow(x + lw + GAP_IN, ay, x + w - rw - GAP_IN, ay, pt=LINE_PT["bold"]))
        return self._group(made, "staircase", plan)

    # --- 3 stacked tiers with connectors ------------------------------------------------------------
    def tiers(self, tiers, links=None, note=None, region="full", plan=None, tile_shape="auto"):
        """Layers top to bottom as guide pills (Key Slide 1 fills red, blue, olive, black) with a white icon tile,
        name, sub-line and the tier number; optional side panel per tier (light grey: icon, title, text);
        links[k] = labels between tier k and k+1, drawn with two-way blue arrows; note = one sentence underneath.
        tiers: [{'name','sub','number','icon','side': (title, text, icon)}]. Icons in the pills sit on white circles
        (pill = fully rounded container), icons in the side panels on rounded squares - tile_shape= overrides both."""
        self._ts = tile_shape
        tr = self._items(tiers, ("name", "sub", "number", "icon", "side"), "tiers")
        if not 2 <= len(tr) <= 4:
            raise GuideError(f"tiers: 2-4 tiers, got {len(tr)} (the guide's pill fills are four)")
        if any(not t["icon"] for t in tr):
            raise GuideError("tiers: every tier needs a guide icon")
        links = links or []
        if len(links) > len(tr) - 1:
            raise GuideError("tiers: links are the labels BETWEEN tiers - at most len(tiers) - 1 groups")
        x, y, w, h = self._region(region)
        n = len(tr)
        sides = any(t["side"] for t in tr)
        side_w = w * VISUAL_SHARE - ARROW_GAP_IN if sides else 0
        bar_w = w - side_w - (ARROW_GAP_IN if sides else 0)
        note_h = 0
        if note:
            note_p = self._fit(lambda s: [(note, s, False)], w, h / 4, what="tiers note", insets=False)
            note_h = _paras_height_pt(note_p, w, insets=False) / 72 + GAP_IN
        link_h = (2 * 10 * capacity.LINE_FACTOR / 72 + 2 * GAP_IN) if links else GAP_IN
        bar_h = (h - note_h - (n - 1) * link_h) / n
        tile = round(min(ICON_TILE_IN, bar_h - 2 * INSET_Y), 3)
        num_w = ICON_TILE_IN if any(t["number"] for t in tr) else 0
        made = []
        for k, t in enumerate(tr):
            by = y + k * (bar_h + link_h)
            fill = PILL_FILLS[k % len(PILL_FILLS)]
            pill = self._box(x, by, bar_w, bar_h, fill=fill, adj=ADJ_PILL)
            made.append(pill)
            ix = x + bar_h / 2 - tile / 2           # centred in the pill's round end
            made += self._icon_shapes(t["icon"], ix, by + (bar_h - tile) / 2, tile, container=pill)
            tx = ix + tile + GAP_IN
            tw = bar_w - (tx - x) - num_w - bar_h / 2
            paras = self._fit(lambda s, t=t: [(t["name"], s + 2, True)] + ([(t["sub"], s, False)] if t["sub"] else []),
                              tw, bar_h, sizes=(12, 10), insets=False, what=f"tier {k + 1}")
            made.append(self._text_box(tx, by, tw, bar_h, paras, color=WHITE, anchor="ctr", insets=False,
                                       shape="rect", what=f"tier {k + 1}"))
            if t["number"]:
                made.append(self._text_box(x + bar_w - bar_h / 2 - num_w, by, num_w, bar_h, [(str(t["number"]), 24, True)],
                                           color=WHITE, anchor="ctr", insets=False, shape="rect", what="tier number"))
            if t["side"]:
                stitle, stext, sicon = (tuple(t["side"]) + (None, None))[:3]
                sx = x + bar_w + ARROW_GAP_IN
                made.append(self._arrow(x + bar_w + GAP_IN / 2, by + bar_h / 2, sx - GAP_IN / 2, by + bar_h / 2))
                side_box = self._box(sx, by, side_w, bar_h, fill=LIGHTGREY)
                made.append(side_box)
                stx = sx + INSET_X
                if sicon:
                    made += self._icon_shapes(sicon, sx + INSET_X, by + (bar_h - tile) / 2, tile, container=side_box)
                    stx += tile + GAP_IN
                sw = sx + side_w - stx - INSET_X
                sp = self._fit(lambda s: [(stitle, s, True)] + ([(stext, s, False)] if stext else []), sw, bar_h,
                               insets=False, what=f"tier {k + 1} side panel")
                made.append(self._text_box(stx, by, sw, bar_h, sp, anchor="ctr", insets=False, shape="rect",
                                           what="tier side panel"))
            if k < len(links) and links[k]:
                labels = links[k]
                ly = by + bar_h
                slot = (bar_w - bar_h / 2) / len(labels)          # labels start under the icon tile
                lw_ = slot - 2 * GAP_IN
                for j, lab in enumerate(labels):
                    lx = x + bar_h / 2 + j * slot
                    made.append(self._arrow(lx, ly + GAP_IN, lx, ly + link_h - GAP_IN, head=True, tail=True))
                    lp = self._fit(lambda s: [(lab, s, False)], lw_, link_h - GAP_IN,
                                   sizes=(10,), insets=False, what="tier link label")
                    made.append(self._text_box(lx + GAP_IN, ly, lw_, link_h, lp, anchor="ctr",
                                               insets=False, shape="rect", what="tier link label"))
        if note:
            made.append(self._text_box(x, y + h - note_h + GAP_IN, w, note_h - GAP_IN, note_p, insets=False,
                                       shape="rect", what="tiers note"))
        return self._group(made, "tiers", plan)

    # --- 4 wheel / cycle ------------------------------------------------------------------------------
    def wheel(self, items, center=None, region="full", plan=None, tile_shape="auto"):
        """A repeating cycle: ring of block-arc segments (guide tile fills) numbered clockwise from the top, the
        cycle name in a light-grey centre, and a legend (number, icon tile, label) beside it. 3-6 items."""
        self._ts = tile_shape
        it = self._items(items, ("label", "icon"), "wheel")
        if not 3 <= len(it) <= 6:
            raise GuideError(f"wheel: 3-6 stages, got {len(it)}")
        if any(not i["icon"] for i in it):
            raise GuideError("wheel: every stage needs a guide icon")
        x, y, w, h = self._region(region)
        n = len(it)
        d = min(h, REGIONS["visual"][2], w * VISUAL_SHARE)
        cx, cy = x + d / 2, y + h / 2
        ring = d * WHEEL_RING
        gap_deg = WHEEL_GAP_DEG
        made = []
        for k in range(n):
            st = (270 + k * 360 / n + gap_deg / 2) % 360
            en = (270 + (k + 1) * 360 / n - gap_deg / 2) % 360
            sh = self.s.shapes.add_shape(MSO_SHAPE.BLOCK_ARC, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d))
            av = sh._element.spPr.find(qn("a:prstGeom")).find(qn("a:avLst"))
            for g in list(av):
                av.remove(g)
            for nm, v in (("adj1", int(st * 60000)), ("adj2", int(en * 60000)), ("adj3", int(ring / d * 100000))):
                _sub(av, "a:gd", name=nm, fmla=f"val {v}")
            fill = TILE_FILLS[k % len(TILE_FILLS)]
            _plain_fill(sh, fill)
            made.append(sh)
            mid = math.radians((270 + (k + 0.5) * 360 / n) % 360)
            r = d / 2 - ring / 2
            nb = ring * 0.8
            made.append(self._text_box(cx + r * math.cos(mid) - nb / 2, cy + r * math.sin(mid) - nb / 2, nb, nb,
                                       [(str(k + 1), 14, True)], color=WHITE if fill in WHITE_TEXT_ON else BLACK,
                                       anchor="ctr", insets=False, shape="rect", align="ctr", what="wheel number", name=NUMBER_NAME))
        if center:
            cd = d - 2 * ring - 2 * GAP_IN
            cp = self._fit(lambda s: [(center, s + 2, True)], cd * 0.7, cd * 0.7, insets=False, what="wheel centre")
            made.append(self._box(cx - cd / 2, cy - cd / 2, cd, cd, fill=LIGHTGREY, shape="oval"))
            made.append(self._text_box(cx - cd * 0.35, cy - cd * 0.35, cd * 0.7, cd * 0.7, cp, anchor="ctr",
                                       insets=False, shape="rect", align="ctr", what="wheel centre"))
        lx = x + d + ARROW_GAP_IN
        lw = x + w - lx
        rowh = min(ICON_TILE_IN + GAP_IN, h / n)
        tile = round(min(ICON_TILE_IN, rowh - GAP_IN), 3)
        top = cy - n * rowh / 2
        for k, i in enumerate(it):
            ry = top + k * rowh
            fill = TILE_FILLS[k % len(TILE_FILLS)]
            made.append(self._text_box(lx, ry + (rowh - tile) / 2, tile, tile, [(str(k + 1), 14, True)], fill=fill,
                                       color=WHITE if fill in WHITE_TEXT_ON else BLACK, anchor="ctr", insets=False,
                                       align="ctr", what="wheel legend number", name=NUMBER_NAME))
            made += self._icon_shapes(i["icon"], lx + tile + GAP_IN, ry + (rowh - tile) / 2, tile)
            tx = lx + 2 * (tile + GAP_IN)
            lp = self._fit(lambda s: [(i["label"], s, False)], lw - 2 * (tile + GAP_IN), rowh, insets=False,
                           what="wheel legend")
            made.append(self._text_box(tx, ry, lw - 2 * (tile + GAP_IN), rowh, lp, anchor="ctr", insets=False,
                                       shape="rect", what="wheel legend"))
        return self._group(made, "wheel", plan)

    # --- 5 tile grid (names or logos) ----------------------------------------------------------------
    def tile_grid(self, groups, cols=3, region="full", plan=None, logos=None, chips="auto", tile_shape="auto"):
        """Groups of names or categories: light-grey tiles with a Mark Pro heading and the names (Light), optional
        icon tile top-right. groups: [(title, [names], icon)] or dicts. Names exactly as the source gives them.
        logos={name: png_path} draws those names as logos instead (RULES §8.1): one visual size for every logo on
        the slide (equal area, aspect kept, transparent margins trimmed), rows in source order, no overlaps; a
        name without a logo stays text. chips='auto' puts a logo that fails the contrast check on its tile onto a
        rounded palette chip (white, blue, black - first that passes); 'all' chips every logo on white; 'none'
        raises instead. Logos only from the user or the company's official sources."""
        self._ts = tile_shape
        gr = self._items(groups, ("title", "items", "icon"), "tile_grid")
        if logos:
            return self._logo_tiles(gr, cols, region, plan, logos, chips)
        x, y, w, h = self._region(region)
        n = len(gr)
        rows = math.ceil(n / cols)
        tw = (w - (cols - 1) * GAP_IN) / cols
        th = (h - (rows - 1) * GAP_IN) / rows
        tile = round(min(ICON_TILE_IN, th / 3), 3)
        has_icon = any(g["icon"] for g in gr)
        made = []
        mk = lambda g, s: [(g["title"], s + 2 if s + 2 in TYPE_SCALE else s, True)] + (
            [(" \u00b7 ".join(g["items"]), s, False)] if g["items"] else [])
        inner_w = tw - (tile + GAP_IN if has_icon else 0)
        sz = next((s for s in DIAGRAM_SIZES if all(_fits(mk(g, s), inner_w, th) for g in gr)), None)
        if sz is None:
            raise GuideError("tile_grid: names do not fit the tiles even at 10 pt - split the grid over two slides")
        if sz == DIAGRAM_SIZES[0] and all(_fits(mk(g, 14), inner_w, th * 0.4) for g in gr):
            sz = 14          # few short lines: lead-line size (heading 18 pt) so the tiles do not look empty
            mk = lambda g, s: [(g["title"], 18 if s == 14 else (s + 2 if s + 2 in TYPE_SCALE else s), True)] + (
                [(" \u00b7 ".join(g["items"]), s, False)] if g["items"] else [])
        # short text must not sit in tall empty tiles (sparse): 'card' mode - a large icon tile on top, heading and
        # text under it, tile height = what that needs (at least 55 % of the region), grid centred in the region
        need = max(_paras_height_pt(mk(g, sz), inner_w) / 72 for g in gr) + 2 * INSET_Y
        card = has_icon and need < 0.6 * th
        if card:
            big = round(min(1.0, th / 3), 3)
            tneed = max(_paras_height_pt(mk(g, sz), tw) / 72 for g in gr)
            th_fit = min(th, max(2 * INSET_Y + big + 0.15 + tneed, 0.55 * th))
            y += (th - th_fit) * rows / 2
            th = th_fit
        for k, g in enumerate(gr):
            gx, gy = x + (k % cols) * (tw + GAP_IN), y + (k // cols) * (th + GAP_IN)
            made.append(self._box(gx, gy, tw, th, fill=LIGHTGREY, radius=R_PANEL))
            if card:
                made += self._icon_shapes(g["icon"], gx + INSET_X, gy + INSET_Y, big, container=made[-1])
                ty = gy + INSET_Y + big + 0.15
                made.append(self._text_box(gx, ty, tw, gy + th - ty, mk(g, sz), shape="rect", what=f"tile '{g['title']}'"))
                continue
            if g["icon"]:
                made += self._icon_shapes(g["icon"], gx + tw - tile - INSET_X, gy + INSET_Y, tile, container=made[-1])
            made.append(self._text_box(gx, gy, inner_w, th, mk(g, sz), shape="rect", what=f"tile '{g['title']}'"))
        return self._group(made, "tile_grid", plan)

    def logo_grid(self, groups, logos, cols=3, region="full", chips="auto", plan=None, tile_shape="auto"):
        """tile_grid() with logos: groups [(title, [names], icon)], logos {name: png path}. Same rules."""
        if not logos:
            raise GuideError("logo_grid: pass logos={name: path} (official files only) - or use tile_grid for names")
        return self.tile_grid(groups, cols=cols, region=region, plan=plan, logos=logos, chips=chips, tile_shape=tile_shape)

    @staticmethod
    def _rows(items, k):
        """Split items (each with 'w') into k contiguous rows, minimising the widest row (source order kept)."""
        n = len(items)
        best = None

        def width(seq):
            return sum(i["w"] for i in seq) + LOGO_GAP_X * (len(seq) - 1)

        def rec(start, left, acc):
            nonlocal best
            if left == 1:
                rows = acc + [items[start:]]
                m = max(width(r) for r in rows)
                if best is None or m < best[0] - 1e-9:
                    best = (m, rows)
                return
            for end in range(start + 1, n - left + 2):
                rec(end, left - 1, acc + [items[start:end]])
        rec(0, k, [])
        return best[1]

    def _logo_layout(self, items, s, aw, ah, k):
        """Rows for k rows at visual size s (sqrt of logo area, inches) or None if they do not fit aw x ah."""
        for it in items:
            if it["kind"] == "logo":
                it["lh"] = min(max(s / math.sqrt(it["a"]), LOGO_H_RANGE[0] * s), LOGO_H_RANGE[1] * s)
                it["lw"] = it["lh"] * it["a"]
                it["pad"] = max(LOGO_CHIP_PAD * it["lh"], LOGO_CHIP_PAD_MIN) if it["chip"] else 0
                pad = 2 * it["pad"]
                it["w"], it["h"] = it["lw"] + pad, it["lh"] + pad
        if k > len(items):
            return None
        rows = self._rows(items, k)
        wide = max(sum(i["w"] for i in r) + LOGO_GAP_X * (len(r) - 1) for r in rows)
        tall = sum(max(i["h"] for i in r) for r in rows) + LOGO_GAP_Y * (k - 1)
        return rows if wide <= aw + 1e-6 and tall <= ah + 1e-6 else None

    def _logo_tiles(self, gr, cols, region, plan, logos, chips):
        if chips not in ("auto", "all", "none"):
            raise GuideError(f"tile_grid: chips must be 'auto', 'all' or 'none', got {chips!r}")
        x, y, w, h = self._region(region)
        n = len(gr)
        rows_n = math.ceil(n / cols)
        tw = (w - (cols - 1) * GAP_IN) / cols
        th = (h - (rows_n - 1) * GAP_IN) / rows_n
        tile = round(min(ICON_TILE_IN, th / 3), 3)
        panel_hex = SLOT_HEX[LIGHTGREY]
        hs = next((s for s in HEAD_SIZES if all(_fits([(g["title"], s, True)], tw - (tile + GAP_IN if g["icon"] else 0), th / 3)
                                                 for g in gr)), None)
        if hs is None:
            raise GuideError("tile_grid: a group heading does not fit one third of its tile - shorten it")
        groups = []
        for g in gr:
            items = []
            for nm in g["items"]:
                path = logos.get(nm)
                if path:
                    if not os.path.isfile(path):
                        raise GuideError(f"tile_grid: logo file for '{nm}' not found: {path}")
                    img, box = _logo_ink(path)
                    ink = img.crop(box)
                    chip = None
                    if chips == "all":
                        chip = WHITE
                    elif logo_legibility(ink, panel_hex) < LOGO_MIN_SHARE:
                        if chips == "none":
                            raise GuideError(f"tile_grid: logo '{nm}' is not legible on the light-grey tile "
                                             f"(< {LOGO_MIN_RATIO}:1) - use the company's official variant for light "
                                             "backgrounds, or chips='auto'")
                        chip = next((c for c in LOGO_CHIP_FILLS if logo_legibility(ink, SLOT_HEX[c]) >= LOGO_MIN_SHARE), None)
                        if chip is None:
                            raise GuideError(f"tile_grid: logo '{nm}' is not legible on any guide colour - get another "
                                             "official variant (colour, dark or white) from the company")
                    W, H = img.size
                    items.append(dict(kind="logo", name=nm, path=path, chip=chip, a=(box[2] - box[0]) / (box[3] - box[1]),
                                      crop=(box[0] / W, box[1] / H, 1 - box[2] / W, 1 - box[3] / H)))
                else:
                    items.append(dict(kind="text", name=nm))
            gw = tw - 2 * INSET_X
            head_h = _paras_height_pt([(g["title"], hs, True)], gw - (tile + GAP_IN if g["icon"] else 0), insets=False) / 72
            ah = th - 2 * INSET_Y - head_h - ROW_GAP_IN
            tsz = next((s for s in (10,) if all(_one_line_in(i["name"], s) <= gw for i in items if i["kind"] == "text")), None)
            if tsz is None:
                raise GuideError(f"tile_grid: a name without a logo in '{g['title']}' does not fit one line of its tile")
            for i in items:
                if i["kind"] == "text":
                    i["w"], i["h"] = _one_line_in(i["name"], tsz), tsz * capacity.LINE_FACTOR / 72
            groups.append(dict(g=g, items=items, aw=gw, ah=ah, head_h=head_h, tsz=tsz))

        def best_s(G):
            if not G["items"]:
                return LOGO_MAX_SIDE_IN
            top = 0.0
            for k in range(1, len(G["items"]) + 1):
                lo, hi = 0.0, LOGO_MAX_SIDE_IN
                if self._logo_layout(G["items"], 0.02, G["aw"], G["ah"], k) is None:
                    continue
                for _ in range(30):
                    mid = (lo + hi) / 2
                    lo, hi = (mid, hi) if self._logo_layout(G["items"], mid, G["aw"], G["ah"], k) else (lo, mid)
                top = max(top, lo)
            return top
        s = min(best_s(G) for G in groups)
        if s < 0.15:
            raise GuideError(f"tile_grid: logos would be only {s:.2f} in (sqrt of area) - too small to read; split the "
                             "grid over two slides or use fewer logos per tile")
        made = []
        for k, G in enumerate(groups):
            g = G["g"]
            gx, gy = x + (k % cols) * (tw + GAP_IN), y + (k // cols) * (th + GAP_IN)
            panel = self._box(gx, gy, tw, th, fill=LIGHTGREY, radius=R_PANEL)
            made.append(panel)
            hw = tw - (tile + GAP_IN if g["icon"] else 0)
            if g["icon"]:
                made += self._icon_shapes(g["icon"], gx + tw - tile - INSET_X, gy + INSET_Y, tile, container=panel)
            made.append(self._text_box(gx, gy, hw, G["head_h"] + 2 * INSET_Y, [(g["title"], hs, True)], shape="rect",
                                       what=f"tile '{g['title']}'"))
            if not G["items"]:
                continue
            rows = next(r for r in (self._logo_layout(G["items"], s, G["aw"], G["ah"], kk)
                                    for kk in range(1, len(G["items"]) + 1)) if r)
            ax, ay = gx + INSET_X, gy + INSET_Y + G["head_h"] + ROW_GAP_IN
            heights = [max(i["h"] for i in r) for r in rows]
            block = sum(heights) + LOGO_GAP_Y * (len(rows) - 1)
            ry = ay + (G["ah"] - block) / 2
            for r, rh in zip(rows, heights):
                used = sum(i["w"] for i in r)
                gap = LOGO_GAP_X if len(r) == 1 else min((G["aw"] - used) / (len(r) - 1), 3 * LOGO_GAP_X)
                cx = ax
                for it in r:
                    iy = ry + (rh - it["h"]) / 2
                    if it["kind"] == "text":
                        made.append(self._text_box(cx, iy, it["w"], it["h"], [(it["name"], G["tsz"], False)],
                                                   insets=False, shape="rect", what=f"name '{it['name']}'"))
                    else:
                        lx, ly = cx, iy
                        if it["chip"]:
                            c = self._box(cx, iy, it["w"], it["h"], fill=it["chip"], adj=ADJ_ICON_TILE)   # rounded, like an icon tile
                            c.name = LOGO_CHIP_NAME
                            made.append(c)
                            lx, ly = cx + it["pad"], iy + it["pad"]
                        pic = self.s.shapes.add_picture(it["path"], Inches(lx), Inches(ly), Inches(it["lw"]), Inches(it["lh"]))
                        pic.crop_left, pic.crop_top, pic.crop_right, pic.crop_bottom = it["crop"]
                        pic.name = LOGO_PREFIX + it["name"]
                        pic._element.nvPicPr.cNvPr.set("descr", it["name"])
                        made.append(pic)
                    cx += it["w"] + gap
                ry += rh + LOGO_GAP_Y
        self.logo_report = [(i["name"], i["kind"], i.get("chip")) for G in groups for i in G["items"]]
        return self._group(made, "tile_grid", plan)

    # --- 6 fact chips / big numbers -------------------------------------------------------------------
    def fact_chips(self, facts, region="full", valign="top", stack=False, plan=None, tile_shape="auto"):
        """Key numbers in a row: light-grey chips, value in red Mark Pro (the info-box number style), label below,
        optional icon tile. stack=True puts the chips under each other (value left, label right) - for a column.
        facts: [(value, label, icon)]; 2-5 facts; every value must be in the source."""
        self._ts = tile_shape
        fc = self._items(facts, ("value", "label", "icon"), "fact_chips")
        if not 2 <= len(fc) <= 5:
            raise GuideError(f"fact_chips: 2-5 facts, got {len(fc)}")
        x, y, w, h = self._region(region)
        if stack:
            return self._fact_stack(fc, x, y, w, h, valign, plan)
        n = len(fc)
        cw = (w - (n - 1) * GAP_IN) / n
        has_icon = any(f["icon"] for f in fc)
        tile = ICON_TILE_IN if has_icon else 0
        vs = next((s for s in VALUE_SIZES if all(_fits([(f["value"], s, True)], cw, h) and
                   capacity.text_width_pt(max(f["value"].split(), key=len), s, "+mj-lt") * (1 + capacity.HEADROOM) / 72
                   <= cw - 2 * INSET_X for f in fc)), None)
        if vs is None:
            raise GuideError("fact_chips: a value is too long for a chip - keep values to a number and a short unit")
        val_h = max(_paras_height_pt([(f["value"], vs, True)], cw) for f in fc) / 72 - 2 * INSET_Y
        lab_h = h - 2 * INSET_Y - (tile + GAP_IN if has_icon else 0) - val_h - GAP_IN
        lsz = next((s for s in DIAGRAM_SIZES if all(_fits([(f["label"], s, False)], cw, lab_h, insets=True) for f in fc)), None)
        if lsz is None:
            raise GuideError("fact_chips: a label does not fit - shorten it to a few words")
        lab_need = max(_paras_height_pt([(f["label"], lsz, False)], cw) for f in fc) / 72 - 2 * INSET_Y
        ch = min(h, 2 * INSET_Y + (tile + GAP_IN if has_icon else 0) + val_h + GAP_IN + lab_need)
        y = _valign(y, h, ch, valign)
        made = []
        for k, f in enumerate(fc):
            fx = x + k * (cw + GAP_IN)
            made.append(self._box(fx, y, cw, ch, fill=LIGHTGREY))
            vy = y + INSET_Y
            if f["icon"]:
                made += self._icon_shapes(f["icon"], fx + INSET_X, vy, tile, container=made[-1])
                vy += tile + GAP_IN
            made.append(self._text_box(fx, vy - INSET_Y, cw, val_h + 2 * INSET_Y, [(f["value"], vs, True)], color=RED,
                                       shape="rect", what="fact value"))
            made.append(self._text_box(fx, vy + val_h + GAP_IN - INSET_Y, cw, lab_need + 2 * INSET_Y,
                                       [(f["label"], lsz, False)], shape="rect", what="fact label"))
        return self._group(made, "fact_chips", plan)

    def _fact_stack(self, fc, x, y, w, h, valign, plan):
        n = len(fc)
        ch = min(ICON_TILE_IN + 2 * INSET_Y, (h - (n - 1) * GAP_IN) / n)      # a showcase tile plus padding
        tile = round(min(ICON_TILE_IN, ch - 2 * INSET_Y), 3)
        has_icon = any(f["icon"] for f in fc)
        vs = next((s for s in VALUE_SIZES if all(_one_line_in(f["value"], s, "+mj-lt") <= w / 2 for f in fc)), None)
        if vs is None:
            raise GuideError("fact_chips: a value is too long for a chip - keep values to a number and a short unit")
        vw = max(_one_line_in(f["value"], vs, "+mj-lt") for f in fc)
        lx0 = INSET_X + (tile + GAP_IN if has_icon else 0) + vw + GAP_IN
        lw = w - lx0 - INSET_X
        lp = [self._fit(lambda s, f=f: [(f["label"], s, False)], lw, ch - 2 * INSET_Y, insets=False,
                        what=f"fact label '{f['label'][:30]}'") for f in fc]
        total = n * ch + (n - 1) * GAP_IN
        y = _valign(y, h, total, valign)
        made = []
        for k, f in enumerate(fc):
            fy = y + k * (ch + GAP_IN)
            chip = self._box(x, fy, w, ch, fill=LIGHTGREY)
            made.append(chip)
            vx = x + INSET_X
            if has_icon:
                if f["icon"]:
                    made += self._icon_shapes(f["icon"], vx, fy + (ch - tile) / 2, tile, container=chip)
                vx += tile + GAP_IN
            made.append(self._text_box(vx, fy, vw, ch, [(f["value"], vs, True)], color=RED, anchor="ctr", insets=False,
                                       shape="rect", what="fact value"))
            made.append(self._text_box(x + lx0, fy, lw, ch, lp[k], anchor="ctr", insets=False, shape="rect",
                                       what="fact label"))
        return self._group(made, "fact_chips", plan)

    # --- 6b icon set: a text-led list as rows of light-grey boxes, one guide icon tile per point ------------
    def icon_set(self, items, region="full", valign="top", plan=None, tile_shape="auto"):
        """Text-led slides without a shape (RULES §17.4): each point becomes a light-grey rounded row with a white
        rounded icon tile (it matches the rounded container) and the point at 14/12 pt. items: [(text, icon)],
        2-5 items, every icon from assets/icons. Use it instead of body text + a lone corner icon (sparse)."""
        self._ts = tile_shape
        it = self._items(items, ("text", "icon"), "icon_set")
        if not 2 <= len(it) <= 5:
            raise GuideError(f"icon_set: 2-5 points, got {len(it)}")
        if any(not i["icon"] for i in it):
            raise GuideError("icon_set: every point needs an icon")
        x, y, w, h = self._region(region)
        n = len(it)
        rh = min(ICON_TILE_IN + 4 * INSET_Y, (h - (n - 1) * GAP_IN) / n)
        tile = round(min(ICON_TILE_IN, rh - 2 * INSET_Y), 3)
        tx = INSET_X + tile + GAP_IN
        tw = w - tx - INSET_X
        paras = [self._fit(lambda sz, i=i: [(i["text"], sz, False)], tw, rh, sizes=HEAD_SIZES, insets=False,
                           what=f"icon_set point '{i['text'][:30]}'") for i in it]
        sz = min(p[0][1] for p in paras)
        total = n * rh + (n - 1) * GAP_IN
        y = _valign(y, h, total, valign)
        made = []
        for k, i in enumerate(it):
            ry = y + k * (rh + GAP_IN)
            row = self._box(x, ry, w, rh, fill=LIGHTGREY)
            made.append(row)
            made += self._icon_shapes(i["icon"], x + INSET_X, ry + (rh - tile) / 2, tile, container=row)
            made.append(self._text_box(x + tx, ry, tw, rh, [(i["text"], sz, False)], anchor="ctr", insets=False,
                                       shape="rect", what="icon_set point"))
        return self._group(made, "icon_set", plan)

    # --- 7 goal - approach - result band --------------------------------------------------------------
    def band(self, goal, approach, result, region="full", heads=("Goal", "Approach", "Result"),
             icons=("target", "workflow", "trophy"), valign="middle", plan=None, tile_shape="auto"):
        """Goal (blue Rahmen) -> approach (light-grey panel, one line per item) -> result (red Fläche, white text),
        joined by blue arrows. Each part: str or list of str. heads= renames the three parts (e.g. 'Context',
        'Our role', 'Outcome'); headings and texts come from the source."""
        self._ts = tile_shape
        goal, approach, result = ([v] if isinstance(v, str) else list(v) for v in (goal, approach, result))
        x, y, w, h = self._region(region)
        avail = w - 2 * ARROW_GAP_IN
        ws = [avail * f for f in BAND_SHARES]
        tile = round(ICON_TILE_IN * 3 / 4, 3)   # three-quarter showcase tile: leaves the band its text height
        body_h = h - INSET_Y - tile - GAP_IN
        cols = [[(heads[k], 14, True)] + [(t, None, False) for t in part] for k, part in enumerate((goal, approach, result))]

        def mk(col, s):
            return [(t, sz if sz else s, hd) for t, sz, hd in col]
        sz = next((s for s in DIAGRAM_SIZES if all(_fits(mk(c, s), ws[i], body_h) for i, c in enumerate(cols))), None)
        if sz is None:
            raise GuideError("band: goal/approach/result text does not fit at 10 pt - shorten each item to one line")
        need = max(_paras_height_pt(mk(c, sz), ws[i]) for i, c in enumerate(cols)) / 72
        bh = min(h, INSET_Y + tile + GAP_IN + need)
        y = _valign(y, h, bh, valign)
        made, bx = [], x
        styles = [dict(fill=None, line=BLUE, color=BLACK), dict(fill=LIGHTGREY, line=None, color=BLACK),
                  dict(fill=RED, line=None, color=WHITE)]
        for i, c in enumerate(cols):
            st = styles[i]
            made.append(self._box(bx, y, ws[i], bh, fill=st["fill"], line=st["line"], radius=R_PANEL))
            if icons and icons[i]:
                made += self._icon_shapes(icons[i], bx + INSET_X, y + INSET_Y, tile, container=made[-1])
            made.append(self._text_box(bx, y + tile + GAP_IN, ws[i], need, mk(c, sz), color=st["color"], shape="rect",
                                       what=f"band {heads[i]}"))
            if i < 2:
                made.append(self._arrow(bx + ws[i] + GAP_IN / 2, y + bh / 2, bx + ws[i] + ARROW_GAP_IN - GAP_IN / 2, y + bh / 2))
            bx += ws[i] + ARROW_GAP_IN
        return self._group(made, "band", plan)

    # --- 8 story panel ---------------------------------------------------------------------------------
    def story_panel(self, fields, picture=None, icon=None, caption=None, region="full", plan=None, tile_shape="auto"):
        """Case story: left square = the user's picture (crop to fill) or, without one, a light-grey frame with a
        guide icon and an optional caption from the source; right = labelled fields in a blue Rahmen box.
        fields: [(label, text)]. Never stock or AI imagery."""
        self._ts = tile_shape
        fl = self._items(fields, ("label", "text"), "story_panel")
        x, y, w, h = self._region(region)
        vw = min(h, REGIONS["visual"][2])
        made = []
        if picture:
            pic = self.s.shapes.add_picture(picture, Inches(x), Inches(y), Inches(vw), Inches(h))
            made.append(pic)
        else:
            made.append(self._box(x, y, vw, h, fill=LIGHTGREY, radius=R_PANEL))
            if icon:
                made += self._icon_shapes(icon, x + INSET_X * 2, y + INSET_Y * 2, ICON_TILE_IN, container=made[-1])
            if caption:
                cy = y + INSET_Y * 2 + (ICON_TILE_IN + GAP_IN if icon else 0)
                cp = self._fit(lambda s: [(caption, s + 2, True)], vw - 4 * INSET_X, y + h - cy - 2 * INSET_Y,
                               insets=False, what="story caption")
                made.append(self._text_box(x + 2 * INSET_X, cy, vw - 4 * INSET_X, y + h - cy - 2 * INSET_Y, cp,
                                           insets=False, shape="rect", what="story caption"))
        fx = x + vw + ARROW_GAP_IN
        fw = x + w - fx
        mk = lambda s: [p for f in fl for p in ((f["label"], s, True), (f["text"], s, False))]
        paras = self._fit(mk, fw, h, what="story fields")
        made.append(self._text_box(fx, y, fw, h, paras, line=BLUE, radius=R_PANEL, what="story fields"))
        return self._group(made, "story_panel", plan)

    # --- 9 donut / pie (native chart) -------------------------------------------------------------------
    def donut(self, categories, values, region="visual", pie=False, plan=None):
        """Parts of a whole as a native doughnut (or pie) chart: one series, slices red, blue, warm grey, olive,
        legend at the bottom, no title, no data labels - the legend names carry the values. 2-4 parts of ONE
        whole; state the unit in the subtitle. Only numbers that are in the source."""
        if not 2 <= len(categories) <= len(CHART_FILLS):
            raise GuideError(f"donut: 2-{len(CHART_FILLS)} parts (the guide's four chart colours), got {len(categories)}")
        if len(categories) != len(values) or any(v is None or v < 0 for v in values):
            raise GuideError("donut: one non-negative value per category")
        x, y, w, h = self._region(region)
        cd = CategoryChartData(); cd.categories = categories; cd.add_series("Share", values)
        kind = XL_CHART_TYPE.PIE if pie else XL_CHART_TYPE.DOUGHNUT
        gf = self.s.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), cd)
        gf.name = DIAGRAM_PREFIX + ("pie" if pie else "donut") + (f" [{plan}]" if plan else "")
        style_round_chart(gf.chart, full_width=w > 6)
        if any(v in INFOGRAPHICS | STRUCTURED for v in self.visuals):
            raise GuideError(f"'{self.name}': one main visual per slide (already has {self.visuals})")
        self.visuals.append("pie" if pie else "donut")
        return gf

    # --- section divider: hero icon + one key fact -------------------------------------------------------
    def chapter_panel(self, icon, value=None, text=None, idx=11):
        """Section divider without a photo: the layout's rounded picture frame (white on colour) with a large guide
        icon and, optionally, one key fact from the chapter (value in red Mark Pro, line in Mark Pro Light).
        Facts only from the source; omit them rather than invent one."""
        if self.name not in DIVIDERS:
            raise GuideError("chapter_panel() is for Kapiteltrenner layouts")
        fr = self.picture_frame(idx)
        fx, fy, fw, fh = (v / 914400 for v in (fr.left, fr.top, fr.width, fr.height))
        pad = 3 * INSET_X
        if container_kind(fr._element) == "full":       # circle/pill frame: keep icon and text inside the curve
            k = (1 - 1 / math.sqrt(2)) / 2                # inset of the inscribed square
            fx, fy, fw, fh = fx + fw * k, fy + fh * k, fw * (1 - 2 * k), fh * (1 - 2 * k)
            pad = INSET_X
        made = [fr]
        path = os.path.join(ICONS, icon + ".png")
        if not os.path.exists(path):
            raise GuideError(f"icon '{icon}' is not in the guide set - see assets/icons/index.json")
        pic = self.s.shapes.add_picture(path, Inches(fx + pad), Inches(fy + pad), Inches(HERO_ICON_IN), Inches(HERO_ICON_IN))
        pic.name = ICON_PREFIX + icon
        self.icon_sizes.add((HERO_ICON_IN, False))
        made.append(pic)
        # keep clear of the section-number square (Blau) - it sits in the frame's lower right corner
        sq = next((p for p in self.s.placeholders if p.placeholder_format.idx == 12), None)
        right = (sq.left / 914400 - GAP_IN) if sq is not None and sq.left / 914400 > fx else fx + fw - pad
        tw = right - fx - pad
        paras = ([(value, 32, True)] if value else []) + ([(text, 14, False)] if text else [])
        if paras:
            top = fy + pad + HERO_ICON_IN + GAP_IN
            th = fy + fh - pad - top
            if value and capacity.text_width_pt(value, 32, "+mj-lt") * (1 + capacity.HEADROOM) / 72 > tw:
                raise GuideError(f"chapter_panel: value '{value}' is too wide for the frame - use a shorter number")
            tb = self._text_box(fx + pad, top, tw, th, paras, anchor="b", insets=False, shape="rect", what="chapter fact")
            if value:
                tb.text_frame.paragraphs[0].runs[0]._r.get_or_add_rPr().find(qn("a:solidFill"))[0].set("val", RED)
            made.append(tb)
        g = self.s.shapes.add_group_shape(made)
        g.name = DIAGRAM_PREFIX + "chapter_panel"
        sq_el = sq._element if sq is not None else None
        if sq_el is not None:                      # number square stays on top of the frame
            sq_el.getparent().remove(sq_el); self.s.shapes._spTree.append(sq_el)
        return g


def style_round_chart(chart, full_width=False):
    """Guide styling for a doughnut/pie: slice colours in the guide's chart order, legend bottom 10/12 pt Light,
    no title, no data labels, transparent chart area, chart-wide size."""
    from pptx.oxml.ns import qn as q
    cs = chart._chartSpace
    pt = 12 if full_width else 10
    chart.has_title = False
    ser = chart.plots[0].series[0]
    for i in range(len(list(ser.values))):
        pnt = ser.points[i]
        pnt.format.fill.solid()
        sf = pnt.format.fill._xPr.find(q("a:solidFill"))
        for ch in list(sf):
            sf.remove(ch)
        _sub(sf, "a:schemeClr", val=CHART_FILLS[i])
        pnt.format.line.fill.solid()
        lf = pnt.format.line._get_or_add_ln().find(q("a:solidFill"))
        for ch in list(lf):
            lf.remove(ch)
        _sub(lf, "a:schemeClr", val=WHITE)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM; chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(pt); _font_slot(chart.legend.font)
    for e in list(cs.iter(_c("dLbls"))):
        e.getparent().remove(e)
    vc = cs.find(".//" + _c("varyColors"))
    if vc is not None:
        vc.set("val", "1")
    hole = cs.find(".//" + _c("holeSize"))
    if hole is not None:
        hole.set("val", "60")
    sp = cs.find(q("c:spPr"))
    if sp is None:
        sp = etree.SubElement(cs, q("c:spPr")); cs.find(q("c:chart")).addnext(sp)
    for ch in list(sp):
        sp.remove(ch)
    _sub(sp, "a:noFill"); ln = _sub(sp, "a:ln"); _sub(ln, "a:noFill")
    tx = cs.find(q("c:txPr"))
    if tx is not None:
        cs.remove(tx)
    tx = etree.fromstring(f'<c:txPr xmlns:c="{C}" xmlns:a="{A}"><a:bodyPr/><a:lstStyle/><a:p><a:pPr>'
                         f'<a:defRPr sz="{pt * 100}"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
                         f'<a:latin typeface="+mn-lt"/></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>')
    sp.addnext(tx)
    if cs.find(_c("roundedCorners")) is None:
        anchor = cs.find(_c("date1904"))
        rc = etree.Element(_c("roundedCorners"), val="0")
        anchor.addnext(rc) if anchor is not None else cs.insert(0, rc)


class Slide(_Diagrams):
    def __init__(self, deck, slide, layout, kind=None):
        self.deck, self.s, self.layout, self.kind = deck, slide, layout, kind
        self.icon_sizes, self.free_shapes, self.visuals = set(), [], []
        self._ts = "auto"           # icon backing for the next builder: auto | rounded | circle

    @property
    def name(self):
        return self.layout.name

    # --- placeholders -------------------------------------------------
    def ph(self, idx):
        for p in self.s.placeholders:
            if p.placeholder_format.idx == idx:
                return p
        have = sorted(p.placeholder_format.idx for p in self.s.placeholders)
        raise GuideError(f"layout '{self.layout.name}' has no placeholder idx {idx} on this slide (available: {have}; "
                         f"it may have been removed by remove_empty() already). See RULES.md §9 for each layout's placeholders.")

    def title(self, text):
        return fill_text(self.ph(0), text)

    def subtitle(self, text, idx=None):
        if idx is None:
            idx = 1 if any(p.placeholder_format.idx == 1 for p in self.s.placeholders) else (16 if self.layout.name == "Bild & Diagramm" else 10)
        return fill_text(self.ph(idx), text)

    def text(self, idx, items, **kw):
        where = f"'{self.name}' idx {idx}"
        _check_body_items(items, where)
        if idx in TILE_IDX.get(self.name, ()):
            if isinstance(items, list) and len(items) > 1:
                raise GuideError(f"{where}: one short phrase per tile, no heading + text")
        return fill_text(self.ph(idx), items, **kw)

    body = text

    def agenda(self, items, start=1):
        """Fill the Agenda: any number of items (>= 2). Items go into the guide's reading-order slots
        01 02 / 03 04 / ... and the number tiles are written automatically.
        * <= 8 items: the slide is moved onto a per-count clone of the guide's Agenda layout ('Agenda 7', ...)
          that has exactly that many slots, so no unused tile or item line is drawn anywhere (PowerPoint and
          LibreOffice). Geometry, spacing and positions are the guide's; unused slots are simply absent.
        * > 8 items: balanced pages (agenda_pages), continuation slides titled 'Agenda (continued)' are inserted
          right after this one, numbering carries on (09, 10, ...).
        Returns the list of agenda slides."""
        if not is_agenda(self.name):
            raise GuideError("s.agenda() only on the 'Agenda' layout")
        items = list(items)
        if len(items) < 2:
            raise GuideError(f"an agenda needs at least 2 items, got {len(items)}")
        sizes = agenda_pages(len(items))
        first, rest = items[:sizes[0]], items[sizes[0]:]
        self._use_agenda_layout(len(first))
        t = self.ph(0)
        if t is not None and not t.text_frame.text.strip():
            fill_text(t, "Agenda" if start == 1 else AGENDA_CONT)
        for k, ((n_idx, t_idx), item) in enumerate(zip(AGENDA_SLOTS, first)):
            fill_text(self.ph(n_idx), f"{start + k:02d}")
            fill_text(self.ph(t_idx), item)
        out, prev, nxt = [self], self, start + len(first)
        for size in sizes[1:]:
            chunk, rest = rest[:size], rest[size:]
            c = self.deck._add_after(prev, "Agenda")
            fill_text(c.ph(0), AGENDA_CONT)
            c.agenda(chunk, start=nxt)
            c.remove_empty()
            out.append(c); prev, nxt = c, nxt + size
        return out

    def _use_agenda_layout(self, k):
        """Re-point this slide to the k-slot Agenda layout and drop the slide's placeholders for absent slots."""
        lay = self.deck._agenda_layout(k)
        if lay is self.layout:
            return
        for rel in self.s.part.rels.values():
            if rel.reltype.endswith("/slideLayout"):
                rel._target = lay.part
                rel.__dict__.pop("target_part", None)            # lazyproperty cache of the old target
        for obj in (self.s.part, self.s):                       # python-pptx caches the layout lookup
            obj.__dict__.pop("slide_layout", None)
        keep = {p.placeholder_format.idx for p in lay.placeholders}
        for p in list(self.s.placeholders):
            if p.placeholder_format.idx in AGENDA_IDX and p.placeholder_format.idx not in keep:
                p._element.getparent().remove(p._element)
        self.layout = lay

    def picture(self, idx, path):
        """Insert a photo into a rounded picture placeholder (crop-to-fill, keeps the placeholder geometry).
        Only user-supplied photos with clear rights; the guide photo belongs to the template brand."""
        self.visuals.append("picture")
        return self.ph(idx).insert_picture(path)

    def quote(self, headline, lines, photo=None, idx=11):
        """Zitat layouts. photo = path of an APPROVED image (user-supplied first, else a free-licence stock pick from
        scripts/photos.py with its licence recorded) -> fills the picture placeholder. photo=None -> the picture
        placeholder is removed (no empty frame) and the headline/quote boxes span the content width.
        Never invent people or brands: a photo must show what the quote is about or nothing at all."""
        if self.name not in QUOTES:
            raise GuideError("quote() is for the Zitat layouts")
        self.text(10, headline); self.text(13, lines, no_bullets=True)
        if photo:
            self.picture(idx, photo)
        else:
            ph = self.ph(idx); ph._element.getparent().remove(ph._element)
            lay = {q.placeholder_format.idx: q for q in self.layout.placeholders}
            for t in (10, 13):                    # copy the layout's top/height, then span the content width
                p, lp = self.ph(t), lay[t]
                p.left, p.top, p.width, p.height = Inches(0.432), lp.top, Inches(8.6), lp.height
            self.free_shapes.append("quote_no_photo")
        return self

    def picture_frame(self, idx):
        """No licensed photo: keep the layout's rounded picture frame as a plain panel (white on colour, light grey
        on white) - the guide's own empty state. Never stock photos or the template owner's photo."""
        ph = self.ph(idx)
        lay_el = next((p._element for p in self.layout.placeholders if p.placeholder_format.idx == idx), None)
        sh = self.s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, ph.left, ph.top, ph.width, ph.height)
        geom = lay_el.find(f"{qn('p:spPr')}/{qn('a:prstGeom')}") if lay_el is not None else None
        if geom is not None:
            old = sh._element.spPr.find(qn("a:prstGeom"))
            old.addprevious(copy.deepcopy(geom)); sh._element.spPr.remove(old)
        _plain_fill(sh, LIGHTGREY if layout_bg_hex(self.layout) == "FFFFFF" else WHITE)
        sh.name = "Picture frame (no photo)"
        ph._element.addprevious(sh._element)       # keep z-order: frame below the number tile
        ph._element.getparent().remove(ph._element)
        self.free_shapes.append("picture_frame")
        return sh

    def remove_empty(self):
        """Delete every placeholder left empty - an empty placeholder must never ship - but never the
        headline/sub-line placeholders the guide keeps (KEEP_FILLED) and never an agenda number tile whose
        item is filled: those must be filled instead."""
        keep = KEEP_FILLED.get(base_layout(self.name), ())
        filled = {p.placeholder_format.idx for p in self.s.placeholders
                  if p.has_text_frame and p.text_frame.text.strip()}
        if is_agenda(self.name):
            for n_idx, t_idx in AGENDA_SLOTS:
                if t_idx in filled and n_idx not in filled:
                    raise GuideError(f"Agenda: item idx {t_idx} is filled but its number tile idx {n_idx} is empty - use s.agenda()")
        for p in list(self.s.placeholders):
            pf = p.placeholder_format
            if pf.type == PP_PLACEHOLDER.FOOTER or not p._element.tag.endswith("}sp"):
                continue
            if not (p.has_text_frame and p.text_frame.text.strip()):
                if pf.idx in keep:
                    raise GuideError(f"'{self.name}': placeholder idx {pf.idx} (headline/sub-line) must be filled, not deleted")
                p._element.getparent().remove(p._element)

    # --- tracker (layout 'Inhalt & Tracker') ---------------------------
    def tracker(self, active, labels=None):
        """Right-edge 4-step tracker: tab `active` (1-4) red, others light grey. Labels are 1pt (hidden) like the guide."""
        for n, idx in enumerate((14, 15, 16, 17), 1):
            p = self.ph(idx)
            spPr = p._element.spPr
            for old in spPr.findall(qn("a:solidFill")) + spPr.findall(qn("a:ln")):
                spPr.remove(old)
            sf = _scheme_fill(spPr, RED if n == active else LIGHTGREY)
            spPr.append(sf)
            ln = _sub(spPr, "a:ln"); _sub(ln, "a:noFill")
            fill_text(p, (labels[n - 1] if labels else " "))

    # --- chart (into a chart or object placeholder) ---------------------
    def chart(self, idx, categories, series, legend=None):
        """Clustered column chart styled like the guide. series: dict name -> values (max 4). Only real numbers.
        State the unit in the slide subtitle (lint); values on one axis must be of one scale (max/min <= 10)."""
        if len(series) > 4:
            raise GuideError("max 4 series (red, blue, warm grey, olive)")
        vals = [abs(v) for vs in series.values() for v in vs if v]
        if vals and max(vals) / min(vals) > 10:
            raise GuideError(f"chart mixes scales on one axis (max/min = {max(vals) / min(vals):.0f}x > 10x) - "
                             "split the chart or chart one measure; put the other numbers in the text")
        cd = CategoryChartData(); cd.categories = categories
        for name, vs in series.items():
            cd.add_series(name, vs)
        ph = self.ph(idx)
        full = ph.width > Inches(6)
        if ph.placeholder_format.type == PP_PLACEHOLDER.CHART:
            gf = ph.insert_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, cd)
        else:                                   # object placeholder (guide slide 'Diagramm' does this)
            gf = self.s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, ph.left, ph.top, ph.width, ph.height, cd)
            ph._element.getparent().remove(ph._element)
            nvPr = gf._element.find(qn("p:nvGraphicFramePr")).find(qn("p:nvPr"))
            _sub(nvPr, "p:ph", idx=str(idx))
        style_chart(gf.chart, legend=(len(series) > 1) if legend is None else legend, full_width=full)
        self.visuals.append("chart")
        return gf

    # --- table ---------------------------------------------------------
    def table(self, rows, total_row=False, col_w=None, ph_idx=11):
        """Guide table placed INTO the content placeholder (idx 11): exact placeholder x/y/w, graphicFrame carries
        <p:ph idx=11>. rows[0] = header. No grid; 1.5pt red header rule; 1pt warm-grey rules between rows and
        under the last row; optional light-grey total row with a warm-grey top rule. Max 9 rows (what fits the
        3.898 in content area at 0.393 in) x 6 cols.
        Every cell must fit ONE line (fixed 0.393 in rows) - set col_w (relative widths) for uneven columns."""
        nr, nc = len(rows), len(rows[0])
        if nr > MAX_ROWS or nc > 6:
            raise GuideError(f"table {nr}x{nc} exceeds {MAX_ROWS} rows x 6 cols - split it")
        ph = self.ph(ph_idx)
        x, y, w = ph.left, ph.top, ph.width
        ph_el = ph._element
        rh = TOKENS["table"]["row_h_emu"]
        gf = self.s.shapes.add_table(nr, nc, x, y, w, Emu(rh * nr))
        ph_el.getparent().remove(ph_el)
        nvPr = gf._element.find(qn("p:nvGraphicFramePr")).find(qn("p:nvPr"))
        _sub(nvPr, "p:ph", idx=str(ph_idx))
        tbl = gf.table
        tblPr = tbl._tbl.tblPr
        for k in list(tblPr.attrib):
            del tblPr.attrib[k]
        tblPr.set("firstRow", "1"); tblPr.set("bandRow", "1")
        sid = tblPr.find(qn("a:tableStyleId"))
        if sid is None: sid = _sub(tblPr, "a:tableStyleId")
        sid.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
        if col_w:
            tot = sum(col_w); widths = [int(w * c / tot) for c in col_w]
        else:
            widths = [int(w / nc)] * nc
        widths[-1] = w - sum(widths[:-1])
        for c, cw in enumerate(widths):
            tbl.columns[c].width = Emu(cw)

        def line(tcPr, tag, w_emu, slot):
            ln = _sub(tcPr, tag, w=w_emu, cap="flat", cmpd="sng", algn="ctr")
            sf = _sub(ln, "a:solidFill"); _sub(sf, "a:schemeClr", val=slot)
            _sub(ln, "a:prstDash", val="solid"); _sub(ln, "a:round")
            _sub(ln, "a:headEnd", type="none", w="med", len="med"); _sub(ln, "a:tailEnd", type="none", w="med", len="med")

        for r in range(nr):
            tbl.rows[r].height = Emu(rh)
            is_head, is_total = r == 0, total_row and r == nr - 1
            for c in range(nc):
                cell = tbl.cell(r, c)
                fill_text(cell, str(rows[r][c]))
                for run in cell.text_frame.paragraphs[0].runs:
                    run.font.size = Pt(14 if is_head else 12)
                    if is_head or is_total:
                        _sub(run._r.get_or_add_rPr(), "a:latin", typeface="+mj-lt")
                tcPr = cell._tc.get_or_add_tcPr()
                for old in list(tcPr):
                    tcPr.remove(old)
                for k in list(tcPr.attrib):
                    del tcPr.attrib[k]
                tcPr.set("marL", "90000" if is_total else "0"); tcPr.set("marR", "90000")
                tcPr.set("marT", "46800"); tcPr.set("marB", "46800"); tcPr.set("anchor", "ctr")
                if is_head:
                    line(tcPr, "a:lnB", 19050, RED)
                elif is_total:
                    line(tcPr, "a:lnT", 12700, WARMGREY)
                    sf = _sub(tcPr, "a:solidFill"); _sub(sf, "a:schemeClr", val=LIGHTGREY)
                else:
                    line(tcPr, "a:lnT", 19050 if r == 1 else 12700, RED if r == 1 else WARMGREY)
                    line(tcPr, "a:lnB", 12700, WARMGREY)     # incl. last row (guide keeps the closing rule)
        return gf

    # --- icons ---------------------------------------------------------
    def icon(self, name, x=None, y=None, size=0.363, tile=False, tile_size=0.727, at=None, tile_shape="auto"):
        """Position: give x, y in inches, or at=<name in ICON_SPOTS> (e.g. at="infobox").
        Place a guide icon (assets/icons/<name>.png), black, ONE size per slide. tile=True draws a white tile behind
        it - use tiles on grey/colour backgrounds or grey panels. The tile matches its container (RULES §7): the
        guide's rounded square (adj 16667) in rounded boxes, panels and on the bare slide; a circle inside a pill,
        oval or circle. tile_shape='rounded' | 'circle' overrides the detection."""
        if at is not None:
            if at not in ICON_SPOTS:
                raise GuideError(f"unknown icon spot '{at}'; known: {sorted(ICON_SPOTS)}")
            x, y = ICON_SPOTS[at]
            if at == "corner":
                self._check_corner_free(x, y, tile_size if tile else size)
        if x is None or y is None:
            raise GuideError("icon(): give x and y in inches, or at=<spot> from ICON_SPOTS")
        path = os.path.join(ICONS, name if name.endswith(".png") else name + ".png")
        if not os.path.exists(path):
            raise FileNotFoundError(f"icon '{name}' is not in the guide set; see assets/icons/index.json")
        if self.icon_sizes and (size, tile) not in self.icon_sizes:
            raise GuideError(f"'{self.name}': icons must share one size/treatment per slide")
        self.icon_sizes.add((size, tile))
        self.visuals.append("icon")
        if tile:
            self._tile_shape(x, y, tile_size, self._tile_kind(x, y, tile_size, tile_shape=tile_shape))
            off = (tile_size - size) / 2
            x, y = x + off, y + off
        pic = self.s.shapes.add_picture(path, Inches(x), Inches(y), Inches(size), Inches(size))
        pic.name = ICON_PREFIX + os.path.basename(path)[:-4]
        return pic

    def _check_corner_free(self, x, y, side):
        """The corner icon may only sit where no text, table or chart reaches (measured like the capacity lint)."""
        spec_l = capacity.CAP.get("layouts", {}).get(self.name, {})
        for el in self.s.shapes._spTree:
            tag = el.tag.split("}")[1]
            if tag not in ("sp", "graphicFrame"):
                continue
            ph = el.find(f".//{qn('p:nvPr')}/{qn('p:ph')}")
            if ph is not None and (ph.get("type") in ("ftr", "sldNum", "dt", "title") or ph.get("idx") in ("0", "10")):
                continue
            if tag == "sp":
                tx = el.find(qn("p:txBody"))
                paras = capacity._paras(tx) if tx is not None else []
                if not paras:
                    continue
                spec = spec_l.get(ph.get("idx", "0")) if ph is not None else None
                lay_ph = next((p for p in self.layout.placeholders if ph is not None and
                               str(p.placeholder_format.idx) == ph.get("idx")), None)
                if spec is None or lay_ph is None:
                    continue
                left, top, width = lay_ph.left / 914400, lay_ph.top / 914400, lay_ph.width / 914400
                bottom = top + capacity.used_height_pt(paras, spec) / 72
            else:
                b = _bbox_in(el)
                if b is None or _name(el) == THINKCELL_NAME:
                    continue
                left, top, width, bottom = b[0], b[1], b[2], b[1] + b[3]
            if left + width > x - GAP_IN and bottom > y - GAP_IN:
                raise GuideError(f"'{self.name}': the corner icon would overlap content ending at y {bottom:.2f} in "
                                 f"(icon from y {y:.2f} in) - shorten the text, add the icon after a shorter table, or "
                                 "use 'Inhalt & Infobox' (at='infobox')")

    def icon_row(self, names, x, y, pitch=0.841, size=0.363, tile_size=0.727, tile_shape="auto"):
        """Guide showcase: icons in white tiles, pitch 0.841 in."""
        for i, n in enumerate(names):
            self.icon(n, x + i * pitch, y, size=size, tile=True, tile_size=tile_size, tile_shape=tile_shape)

    # --- guide text boxes ----------------------------------------------
    def info_box(self, x, y, w, h, items, kind="fill"):
        """Guide 'Textfelder': kind='fill' -> solid red, white text; kind='frame' -> no fill, 1pt blue outline.
        Only on content layouts (Inhalt*/2 Inhalte*), max one per slide - never combined with pills/tiles."""
        if not (self.name.startswith("Inhalt") or self.name.startswith("2 Inhalte")):
            raise GuideError(f"info_box is not a guide pattern on '{self.name}'")
        if "info_box" in self.free_shapes:
            raise GuideError(f"'{self.name}': one info box per slide")
        self.free_shapes.append("info_box"); self.visuals.append("info_box")
        sh = self.s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        sh.name = INFOBOX_NAME
        if kind == "fill":
            _plain_fill(sh, RED)
        else:
            _plain_fill(sh, None, line=BLUE, line_w=12700)
        tf = sh.text_frame; tf.word_wrap = True
        bp = tf._txBody.find(qn("a:bodyPr"))
        for k, v in (("lIns", 108000), ("tIns", 72000), ("rIns", 108000), ("bIns", 72000), ("anchor", "t")):
            bp.set(k, str(v))
        fill_text(sh, items)
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.size = Pt(12)
                rPr = r._r.get_or_add_rPr()
                rPr.insert(0, _scheme_fill(rPr, WHITE if kind == "fill" else BLACK))
        return sh

    def rounded(self, x, y, w, h, slot, adj=0.13529, text=None, size=12, color=WHITE, heading=False, align="l", anchor="t"):
        """Rounded tile/pill in a guide colour. Not on Key Slide layouts (they bring their own tiles/pills)."""
        if self.name in KEYS:
            raise GuideError("Key Slide layouts already carry their pills/tiles - fill the placeholders instead")
        self.free_shapes.append("rounded")
        sh = self.s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        sh.adjustments[0] = adj
        _plain_fill(sh, slot)
        if text is not None:
            tf = sh.text_frame; tf.word_wrap = True
            bp = tf._txBody.find(qn("a:bodyPr"))
            for k, v in (("lIns", 108000), ("tIns", 72000), ("rIns", 108000), ("bIns", 72000), ("anchor", anchor)):
                bp.set(k, str(v))
            fill_text(sh, [Para(text, heading_font=heading)])
            for p in tf.paragraphs:
                p.alignment = {"l": 1, "ctr": 2}[align]
                for r in p.runs:
                    r.font.size = Pt(size)
                    rPr = r._r.get_or_add_rPr(); rPr.insert(0, _scheme_fill(rPr, color))
        return sh


def _plain_fill(sh, slot, line=None, line_w=None):
    spPr = sh._element.spPr
    for old in spPr.findall(qn("a:solidFill")) + spPr.findall(qn("a:noFill")) + spPr.findall(qn("a:ln")):
        spPr.remove(old)
    if slot:
        sf = _scheme_fill(spPr, slot); spPr.append(sf)
    else:
        _sub(spPr, "a:noFill")
    ln = _sub(spPr, "a:ln")
    if line:
        ln.set("w", str(line_w or 12700)); sf = _sub(ln, "a:solidFill"); _sub(sf, "a:schemeClr", val=line)
    else:
        _sub(ln, "a:noFill")
    st = sh._element.find(qn("p:style"))
    if st is not None:
        sh._element.remove(st)


def _c(tag):
    return "{%s}%s" % (C, tag)


def style_chart(chart, legend=True, full_width=None):
    """Guide chart styling (see RULES.md §6), plus a valid package: positive axis ids, chart-wide text size."""
    from pptx.oxml.ns import qn as q
    cs = chart._chartSpace
    plot = chart.plots[0]
    plot.gap_width = 219; plot.overlap = -27
    slots = [RED, BLUE, WARMGREY, OLIVE]
    for i, s in enumerate(plot.series):
        s.format.fill.solid()
        sf = s._element.spPr.find(q("a:solidFill"))
        for ch in list(sf): sf.remove(ch)
        _sub(sf, "a:schemeClr", val=slots[i % 4])
        s.format.line.fill.background()
        s.invert_if_negative = False
    chart.has_title = False
    ca, va = chart.category_axis, chart.value_axis
    va.has_major_gridlines = False; va.has_minor_gridlines = False
    ca.has_major_gridlines = False
    va.format.line.fill.background()
    ca.format.line.width = Emu(9525); ca.format.line.fill.solid()
    lnf = ca._element.find(q("c:spPr")).find(q("a:ln")).find(q("a:solidFill"))
    for ch in list(lnf): lnf.remove(ch)
    _sub(lnf, "a:schemeClr", val="tx1")
    from pptx.enum.chart import XL_TICK_MARK
    full_width = bool(full_width)
    axis_pt = 12 if full_width else 10
    for ax, slot in ((ca, "+mn-lt" if full_width else "+mj-lt"), (va, "+mn-lt")):
        ax.major_tick_mark = XL_TICK_MARK.NONE; ax.minor_tick_mark = XL_TICK_MARK.NONE
        ax.tick_labels.font.size = Pt(axis_pt)
        _font_slot(ax.tick_labels.font, slot)
    va.minimum_scale = 0
    try:
        top = max(v for pl in chart.plots for se in pl.series for v in se.values if v is not None)
        if top <= 10:
            va.major_unit = 1
    except ValueError:
        pass
    chart.has_legend = bool(legend)
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM; chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(10); _font_slot(chart.legend.font)
    sp = cs.find(q("c:spPr"))
    if sp is None:
        sp = etree.SubElement(cs, q("c:spPr"))
        chart_el = cs.find(q("c:chart")); chart_el.addnext(sp)
    for ch in list(sp): sp.remove(ch)
    _sub(sp, "a:noFill"); ln = _sub(sp, "a:ln"); _sub(ln, "a:noFill")
    # chart-wide default text: guide size + theme font (python-pptx leaves 18 pt)
    tx = cs.find(q("c:txPr"))
    if tx is not None:
        cs.remove(tx)
    tx = etree.fromstring(f'<c:txPr xmlns:c="{C}" xmlns:a="{A}"><a:bodyPr/><a:lstStyle/><a:p><a:pPr>'
                         f'<a:defRPr sz="{axis_pt * 100}"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
                         f'<a:latin typeface="+mn-lt"/></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>')
    sp.addnext(tx)
    # schema hygiene: positive axis ids, varyColors/roundedCorners/crossBetween like the guide chart
    ids = {}
    for el in cs.iter(_c("axId"), _c("crossAx")):
        v = el.get("val")
        ids.setdefault(v, str(50000000 + 1000 * len(ids)))
        el.set("val", ids[v])
    bar = cs.find(".//" + _c("barChart"))
    if bar is not None and bar.find(_c("varyColors")) is None:
        bar.find(_c("grouping")).addnext(etree.Element(_c("varyColors"), val="0"))
    if cs.find(_c("roundedCorners")) is None:
        anchor = cs.find(_c("date1904"))
        rc = etree.Element(_c("roundedCorners"), val="0")
        anchor.addnext(rc) if anchor is not None else cs.insert(0, rc)
    for vax in cs.iter(_c("valAx")):
        if vax.find(_c("crossBetween")) is None:
            cr = vax.find(_c("crosses")) if vax.find(_c("crosses")) is not None else vax.find(_c("crossesAt"))
            cr.addnext(etree.Element(_c("crossBetween"), val="between"))


def _font_slot(font, typeface="+mn-lt"):
    rPr = font._rPr if hasattr(font, "_rPr") else font._element
    for old in rPr.findall(qn("a:solidFill")) + rPr.findall(qn("a:latin")):
        rPr.remove(old)
    sf = etree.SubElement(rPr, qn("a:solidFill")); _sub(sf, "a:schemeClr", val="tx1")
    _sub(rPr, "a:latin", typeface=typeface)


def _next_id(tree):
    return max([int(e.get("id")) for e in tree.iter(qn("p:cNvPr")) if (e.get("id") or "").isdigit()] + [1]) + 1


# ================================================================================================ lint
def _txt(sp_el):
    return "".join((t.text or "") if t.tag == qn("a:t") else "\n" for t in sp_el.iter(qn("a:t"), qn("a:br"))).strip()


def _ph_texts(slide):
    out = {}
    for p in slide.placeholders:
        if p.has_text_frame:
            out[p.placeholder_format.idx] = p.text_frame.text.strip()
    return out


def _norm(t):
    return re.sub(r"\s+", " ", t.replace("&", "and")).strip().casefold()


def agenda_items(slide):
    texts = _ph_texts(slide)
    return [texts[t] for _, t in AGENDA_SLOTS if texts.get(t)]


def _check_agenda(slide, start=1):
    """Numbering start..start+k-1 in reading order, no gaps, and no visible empty slot: every number tile or
    item line the slide's LAYOUT carries must be filled on the slide (LibreOffice draws unfilled layout
    placeholders, tile fill and prompt number included) - use s.agenda(), which picks the k-slot layout."""
    texts, msgs = _ph_texts(slide), []
    filled = [k for k, (_, t) in enumerate(AGENDA_SLOTS) if texts.get(t)]
    if filled != list(range(len(filled))):
        msgs.append(f"items must fill the slots in reading order 01 02 / 03 04 / ... without gaps (filled slots {[k + 1 for k in filled]})")
    for k, (n_idx, t_idx) in enumerate(AGENDA_SLOTS):
        item, num = texts.get(t_idx), texts.get(n_idx)
        if item and num != f"{start + k:02d}":
            msgs.append(f"item '{item}' (idx {t_idx}) carries number {num!r} in tile idx {n_idx}, expected '{start + k:02d}'")
        if num and not item:
            msgs.append(f"number tile idx {n_idx} ('{num}') has no item")
    lay_idx = {p.placeholder_format.idx for p in slide.slide_layout.placeholders}
    for k, (n_idx, t_idx) in enumerate(AGENDA_SLOTS):
        if (n_idx in lay_idx or t_idx in lay_idx) and not (texts.get(n_idx) and texts.get(t_idx)):
            msgs.append(f"slot {k + 1} (tile idx {n_idx}) is empty but its layout '{slide.slide_layout.name}' draws it "
                        f"(visible empty tile) - use s.agenda(items), which selects the {len(filled)}-slot layout")
    if not 2 <= len(filled) <= 8:
        msgs.append(f"an agenda slide takes 2-8 items, found {len(filled)}")
    title = texts.get(0, "")
    want = "Agenda" if start == 1 else AGENDA_CONT
    if title != want:
        msgs.append(f"title {title!r} - expected {want!r}")
    return msgs


def _check_table(gf):
    msgs = []
    tbl = gf.find(".//" + qn("a:tbl"))
    if gf.find(f"{qn('p:nvGraphicFramePr')}/{qn('p:nvPr')}/{qn('p:ph')}") is None:
        msgs.append("table is not placed in the content placeholder (use s.table())")
    sid = tbl.find(f"{qn('a:tblPr')}/{qn('a:tableStyleId')}")
    if sid is None or sid.text != "{2D5ABB26-0587-4C30-8999-92F81FD0307C}":
        msgs.append("table style must be 'No Style, No Grid' {2D5ABB26-...}")
    rows = tbl.findall(qn("a:tr")); cols = tbl.find(qn("a:tblGrid")).findall(qn("a:gridCol"))
    if len(rows) > MAX_ROWS or len(cols) > 6:
        msgs.append(f"table {len(rows)}x{len(cols)} exceeds {MAX_ROWS} rows x 6 cols")
    rh = TOKENS["table"]["row_h_emu"]

    def ln(tc, tag):
        pr = tc.find(qn("a:tcPr")); l = pr.find(qn(tag)) if pr is not None else None
        if l is None or l.find(qn("a:noFill")) is not None:
            return None
        c = l.find(f"{qn('a:solidFill')}/{qn('a:schemeClr')}")
        return (int(l.get("w", 0)), c.get("val") if c is not None else None)
    for r, tr in enumerate(rows):
        if abs(int(tr.get("h")) - rh) > 2:
            msgs.append(f"row {r + 1} height {int(tr.get('h')) / 914400:.3f} in, guide 0.393 in")
        for tc in tr.findall(qn("a:tc")):
            pr = tc.find(qn("a:tcPr"))
            total = pr is not None and pr.find(f"{qn('a:solidFill')}/{qn('a:schemeClr')}") is not None
            if ln(tc, "a:lnL") or ln(tc, "a:lnR"):
                msgs.append(f"row {r + 1}: vertical lines are not used"); break
            if r == 0 and ln(tc, "a:lnB") != (19050, RED):
                msgs.append("header row needs a 1.5 pt red rule below"); break
            if r > 0 and total and ln(tc, "a:lnT") != (12700, WARMGREY):
                msgs.append("total row needs a 1 pt warm-grey rule above"); break
            if r > 0 and not total and ln(tc, "a:lnB") != (12700, WARMGREY):
                msgs.append(f"row {r + 1} needs a 1 pt warm-grey rule below (incl. the last row)"); break
    return msgs


def _check_round_chart(cs, unit_text):
    """Doughnut / pie (parts of a whole): one series, slices in the guide's chart colour order, legend bottom,
    no title, no data labels, chart-wide 10/12 pt, unit stated."""
    msgs = []
    sers = cs.findall(".//" + _c("ser"))
    if len(sers) != 1:
        msgs.append("a doughnut/pie shows ONE whole - one series only")
    pts = sers[0].findall(_c("dPt")) if sers else []
    vals = [v for v in sers[0].iter(_c("v")) if v.getparent().getparent().tag in (_c("numCache"),)] if sers else []
    if len(pts) > len(CHART_FILLS) or len(vals) > len(CHART_FILLS):
        msgs.append(f"max {len(CHART_FILLS)} slices (the guide's chart colours)")
    for i, p in enumerate(pts):
        clr = p.find(f"{_c('spPr')}/{qn('a:solidFill')}/{qn('a:schemeClr')}")
        if clr is None or clr.get("val") != CHART_FILLS[i % len(CHART_FILLS)]:
            msgs.append(f"slice {i + 1} colour must be {['red', 'blue', 'warm grey', 'olive'][i % 4]} (theme slot)")
    leg = cs.find(".//" + _c("legend"))
    if leg is None or leg.find(_c("legendPos")).get("val") != "b":
        msgs.append("doughnut/pie needs the legend at the bottom (it names the slices)")
    if cs.find(".//" + _c("title")) is not None:
        msgs.append("no chart title (the slide title carries it)")
    if any(e.get("val") == "1" for e in cs.iter(_c("showVal"), _c("showPercent"))):
        msgs.append("no data labels - put the values in the category names")
    tx = cs.find(_c("txPr"))
    d = tx.find(".//" + qn("a:defRPr")) if tx is not None else None
    if d is None or d.get("sz") not in ("1000", "1200"):
        msgs.append("chart-wide text size must be 10 or 12 pt")
    cats = " ".join(v.text or "" for c in cs.iter(_c("cat")) for v in c.iter(_c("v")))
    if not UNIT_RE.search(unit_text + " " + cats):
        msgs.append("state the unit (e.g. '%', 'people') in the slide subtitle or the category names")
    return msgs


def chart_kind(chart):
    cs = chart._chartSpace
    if cs.find(".//" + _c("doughnutChart")) is not None:
        return "donut"
    if cs.find(".//" + _c("pieChart")) is not None:
        return "pie"
    return "chart"


def chart_numbers(chart):
    """(categories, values) of the first series - used by verify_deck.py --plan."""
    ser = chart.plots[0].series[0]
    return [str(c) for c in chart.plots[0].categories], [float(v) for v in ser.values]


def _check_chart(chart, unit_text):
    msgs, cs = [], chart._chartSpace
    if chart_kind(chart) != "chart":
        return _check_round_chart(cs, unit_text)
    bar = cs.find(".//" + _c("barChart"))
    if bar is None or bar.find(_c("barDir")).get("val") != "col" or bar.find(_c("grouping")).get("val") != "clustered":
        return ["only clustered column charts (and doughnut/pie for parts of a whole) are guide patterns"]
    g, o = bar.find(_c("gapWidth")), bar.find(_c("overlap"))
    if g is None or g.get("val") != "219" or o is None or o.get("val") != "-27":
        msgs.append("gap width 219 % and overlap -27 % required")
    sers = bar.findall(_c("ser"))
    for i, s in enumerate(sers):
        clr = s.find(f"{_c('spPr')}/{qn('a:solidFill')}/{qn('a:schemeClr')}")
        if clr is None or clr.get("val") != [RED, BLUE, WARMGREY, OLIVE][i % 4]:
            msgs.append(f"series {i + 1} colour must be {['red', 'blue', 'warm grey', 'olive'][i % 4]} (theme slot)")
    if len(sers) > 4:
        msgs.append("max 4 series")
    if cs.find(".//" + _c("majorGridlines")) is not None:
        msgs.append("no gridlines")
    leg = cs.find(".//" + _c("legend"))
    if len(sers) > 1 and (leg is None or leg.find(_c("legendPos")).get("val") != "b"):
        msgs.append("legend at the bottom for 2+ series")
    if len(sers) == 1 and leg is not None:
        msgs.append("omit the legend for one series")
    if cs.find(".//" + _c("title")) is not None:
        msgs.append("no chart title (the slide title carries it)")
    if any(e.get("val") == "1" for e in cs.iter(_c("showVal"))):
        msgs.append("no data labels")
    tx = cs.find(_c("txPr"))
    d = tx.find(".//" + qn("a:defRPr")) if tx is not None else None
    if d is None or d.get("sz") not in ("1000", "1200"):
        msgs.append(f"chart-wide text size must be 10 or 12 pt (found {d.get('sz') if d is not None else 'none'}; python-pptx default is 18 pt)")
    if any(int(e.get("val")) < 0 for e in cs.iter(_c("axId"), _c("crossAx"))):
        msgs.append("negative chart axis ids (schema-invalid)")
    names = " ".join(v.text or "" for s in sers for v in s.iter(_c("v")) if s.find(_c("tx")) is not None and v in list(s.find(_c("tx")).iter(_c("v"))))
    if not UNIT_RE.search(unit_text + " " + names):
        msgs.append("state the unit (e.g. '$ billion', '%', 'in thousands') in the slide subtitle or series names")
    vals = [abs(float(v.text)) for s in sers for v in s.iter(_c("v")) if s.find(_c("val")) is not None
            and v in list(s.find(_c("val")).iter(_c("v"))) and v.text and float(v.text) != 0]
    if vals and max(vals) / min(vals) > 10:
        msgs.append(f"values span {max(vals) / min(vals):.0f}x on one axis - one scale per chart (split or chart one measure)")
    return msgs


VISUAL_ANY = INFOGRAPHICS | STRUCTURED | {"icon", "logo", "picture", "chart", "table", "big_number", "info_box"}   # a guide table fills the content area, so it counts as the data visual
STRUCTURAL = COVERS | CLOSINGS | DIVIDERS


def _name(el):
    c = el.find(".//" + qn("p:cNvPr"))
    return (c.get("name") if c is not None else "") or ""


def slide_visuals(slide):
    """Visual types present on a built slide (any saved deck): diagram types from 'sgdeck diagram: <type>' groups,
    'donut'/'pie'/'chart', 'table', 'icon' (named sgdeck icons, or any picture <= 0.6 in in decks built elsewhere),
    'picture', 'big_number' (filled Inhalt & Infobox number), 'info_box', 'key_slide', 'quote'."""
    out, tree = set(), slide.shapes._spTree
    for el in tree.iter(qn("p:grpSp"), qn("p:graphicFrame")):
        nm = _name(el)
        if nm.startswith(DIAGRAM_PREFIX):
            out.add(nm[len(DIAGRAM_PREFIX):].split(" [")[0])
    for shp in slide.shapes:
        if getattr(shp, "has_chart", False) and shp.has_chart:
            out.add(chart_kind(shp.chart))
        if getattr(shp, "has_table", False) and shp.has_table:
            out.add("table")
    for pic in tree.iter(qn("p:pic")):
        if any(a.tag == qn("p:graphicFrame") for a in pic.iterancestors()):
            continue                         # the hidden think-cell object's OLE preview is not a visual
        nm = _name(pic)
        ext = pic.find(f"{qn('p:spPr')}/{qn('a:xfrm')}/{qn('a:ext')}")
        small = ext is not None and int(ext.get("cx", 0)) <= Inches(0.6) and int(ext.get("cy", 0)) <= Inches(0.6)
        out.add("logo" if nm.startswith(LOGO_PREFIX) else "icon" if nm.startswith(ICON_PREFIX) or small else "picture")
    lname = base_layout(slide.slide_layout.name)
    if lname == "Inhalt & Infobox" and _ph_texts(slide).get(16):
        out.add("big_number")
    if any(_name(sp) == INFOBOX_NAME for sp in tree.iter(qn("p:sp"))):
        out.add("info_box")
    if lname in KEYS:
        out.add("key_slide")
    if lname in QUOTES:
        out.add("quote")
    return out


def _bbox_in(el):
    xf = el.find(f"{qn('p:grpSpPr')}/{qn('a:xfrm')}")
    if xf is None:
        xf = el.find(f"{qn('p:xfrm')}")
    if xf is None:
        return None
    off, ext = xf.find(qn("a:off")), xf.find(qn("a:ext"))
    return tuple(int(v) / 914400 for v in (off.get("x"), off.get("y"), ext.get("cx"), ext.get("cy")))


def _is_icon_pic(el, b):
    return el.tag == qn("p:pic") and (_name(el).startswith(ICON_PREFIX) or (b[2] <= 0.6 and b[3] <= 0.6 and
                                                                             not _name(el).startswith(LOGO_PREFIX)))


def check_icon_tiles(slide):
    """Icon backings that do not match their container (RULES §7): a rounded-square tile inside a pill, oval or
    circle, or a circle inside a rounded/square box. Tiles = shapes named 'sgdeck icon tile', or (decks built
    elsewhere) a small square painted shape that holds an icon picture. Returns messages."""
    items = list(_walk_abs(slide.shapes._spTree))
    lay = [(el, b) for el, b in _walk_abs(slide.slide_layout.shapes._spTree) if el.find(".//" + qn("p:ph")) is None]
    pics = [b for el, b in items if _is_icon_pic(el, b)]
    out = []
    for el, b in items:
        if el.tag != qn("p:sp") or not _painted(el):
            continue
        named = _name(el) == ICON_TILE_NAME
        squareish = 0.15 <= b[2] <= 1.0 and abs(b[2] - b[3]) <= 0.02 * max(b[2], 0.1)
        holds = any(_contains(b, p) and abs((p[0] + p[2] / 2) - (b[0] + b[2] / 2)) < 0.03 and
                    abs((p[1] + p[3] / 2) - (b[1] + b[3] / 2)) < 0.03 and p[2] < b[2] for p in pics)
        if not (named or (squareish and holds)):
            continue
        cont = _container_of(b, items + lay, exclude=(el,))
        want = tile_for(cont[0]) if cont else "rounded"
        have = "circle" if container_kind(el) == "full" else "rounded"
        if want != have:
            where = (f"a {'pill/oval' if container_kind(cont[0]) == 'full' else 'rounded box'} '{_name(cont[0])}'"
                     if cont else "the bare slide")
            out.append(f"icon tile at ({b[0]:.2f}, {b[1]:.2f}) in is a {'circle' if have == 'circle' else 'rounded square'} "
                       f"inside {where} - use a {'circle' if want == 'circle' else 'rounded square'} (tile_shape='auto')")
    return out


def _pic_image(slide, el):
    """PIL image of a p:pic as drawn (srcRect crop applied)."""
    from PIL import Image
    import io
    blip = el.find(".//" + qn("a:blip"))
    rid = blip.get(qn("r:embed")) if blip is not None else None
    if not rid:
        return None
    img = Image.open(io.BytesIO(slide.part.related_part(rid).blob)).convert("RGBA")
    sr = el.find(".//" + qn("a:srcRect"))
    if sr is not None:
        W, H = img.size
        l, t, r, b_ = (int(sr.get(k, 0)) / 100000 for k in ("l", "t", "r", "b"))
        img = img.crop((round(l * W), round(t * H), round(W - r * W), round(H - b_ * H)))
    return img


def check_logos(slide):
    """Logos (pictures named 'sgdeck logo: <name>'): legible on what they sit on (>= LOGO_MIN_SHARE of the pixels
    at >= LOGO_MIN_RATIO contrast), inside a tile, no two overlapping. Returns messages."""
    items = list(_walk_abs(slide.shapes._spTree))
    lay = [(el, b) for el, b in _walk_abs(slide.slide_layout.shapes._spTree) if el.find(".//" + qn("p:ph")) is None]
    out, feet = [], []
    for el, b in items:
        nm = _name(el)
        if el.tag != qn("p:pic") or not nm.startswith(LOGO_PREFIX):
            continue
        cont = _container_of(b, items + lay)
        bg = (_fill_hex(cont[0]) if cont else None) or layout_bg_hex(slide.slide_layout) or "FFFFFF"
        img = _pic_image(slide, el)
        share = logo_legibility(img, bg) if img is not None else 0.0
        if share < LOGO_MIN_SHARE:
            out.append(f"logo '{nm[len(LOGO_PREFIX):]}' is not legible on #{bg}: {share:.0%} of it reaches "
                       f"{LOGO_MIN_RATIO:g}:1 (min {LOGO_MIN_SHARE:.0%}) - use an official variant for this background "
                       "or a palette chip (chips='auto')")
        if cont is None:
            out.append(f"logo '{nm[len(LOGO_PREFIX):]}' sits on the bare slide - put logos in tiles (tile_grid logos=)")
        foot = cont[1] if cont and _name(cont[0]) == LOGO_CHIP_NAME else b
        feet.append((nm[len(LOGO_PREFIX):], foot))
    for k, (n1, a) in enumerate(feet):
        for n2, c in feet[k + 1:]:
            ix = min(a[0] + a[2], c[0] + c[2]) - max(a[0], c[0])
            iy = min(a[1] + a[3], c[1] + c[3]) - max(a[1], c[1])
            if ix > 0.005 and iy > 0.005:
                out.append(f"logos '{n1}' and '{n2}' overlap")
    return out


def lint_prs(prs, expect_thinkcell=True, mode=None):
    """Deck-level and per-slide guide rules for ANY built deck (used by Deck.save and verify_deck.py).
    Returns [(key, message)]; keys before ':' are rule ids (see WAIVABLE). mode='short-pitch' turns the agenda/
    divider findings of decks <= SHORT_PITCH_MAX slides into ('short-pitch', ...) notes, which are not failures."""
    out = _lint_prs(prs, expect_thinkcell)
    n = len(prs.slides)
    if mode == "short-pitch":
        if n > SHORT_PITCH_MAX:
            out.append(("short-pitch-size", f"short-pitch mode is for decks of <= {SHORT_PITCH_MAX} slides, this one "
                                            f"has {n} - add the agenda and dividers"))
        else:
            out = [(("short-pitch", f"(short pitch, {n} slides) {m}") if k.split(":")[0] in SHORT_PITCH_SKIPS else (k, m))
                   for k, m in out]
    return out


def _lint_prs(prs, expect_thinkcell=True):
    out = []
    slides = list(prs.slides)
    names = [s.slide_layout.name for s in slides]
    n = len(names)
    if n and names[0] not in COVERS:
        out.append(("cover", "first slide must be a cover layout"))
    if n and names[-1] not in CLOSINGS:
        out.append(("closing", "last slide must be a Schlussfolie"))
    for i in {0, n - 1} if n else ():                     # cover / closing subtitle: 1-2 lines (14 pt)
        for p in slides[i].placeholders:
            if p.placeholder_format.idx == 1 and p.has_text_frame and p.text_frame.text.strip():
                w_pt = p.width / 12700 if p.width else 9.135 * 72
                lines = capacity.wrap_lines(p.text_frame.text.strip().replace("\v", "\n"),
                                            w_pt / (1 + capacity.HEADROOM), 14.0)
                if lines > 2:
                    out.append((f"prompt:{i + 1}", f"slide {i + 1}: cover/closing subtitle takes {lines} lines (max 2)"))
    if n > 5 and (n < 2 or not is_agenda(names[1])):
        out.append(("agenda", "decks over 5 slides need the Agenda right after the cover"))
    divs = [i for i, x in enumerate(names) if x in DIVIDERS]
    if n > 5 and not divs:
        out.append(("dividers", "decks over 5 slides need a Kapiteltrenner before each chapter (one family)"))
    fams = {names[i] for i in divs}
    if len(fams) > 1:
        out.append(("divider-family", f"mixed divider families {sorted(fams)}"))
    for i, s_ in enumerate(slides, 1):                     # RULES §17.4: no sparse text-only content slide
        if names[i - 1].startswith(CONTENT_PREFIXES) and names[i - 1] not in KEYS | QUOTES:
            vis = slide_visuals(s_)
            icons = [p for p in s_.shapes._spTree.iter(qn("p:pic")) if _name(p).startswith(ICON_PREFIX)]
            if vis <= {"icon"} and len(icons) <= 1:
                out.append((f"sparse:{i}", f"slide {i} '{names[i - 1]}': text-only slide with at most one corner icon "
                            "looks sparse - use s.icon_set(points) (one icon per point) or a key number "
                            "(Inhalt & Infobox big number / fact_chips) from the source"))
    for i in range(1, n):
        if names[i] == names[i - 1] and names[i] != "Inhalt & Tracker" and not is_agenda(names[i]):
            out.append(("repeat", f"slides {i} and {i + 1} share layout '{names[i]}'"))
    limit = max(2, math.ceil(2 * n / 12))
    for nm in sorted(set(names) - DIVIDERS):
        if names.count(nm) > limit:
            out.append(("layout-reuse", f"layout '{nm}' used {names.count(nm)}x (max {limit} in {n} slides)"))
    bgs = {}
    for i, s in enumerate(slides, 1):
        if names[i - 1].startswith(CONTENT_PREFIXES):
            bgs.setdefault(layout_bg_hex(s.slide_layout), []).append(i)
    if len(bgs) > 1:
        out.append(("background", "content slides mix background families: " +
                    "; ".join(f"#{k} on slides {v}" for k, v in bgs.items()) + " - use one family (white is the default)"))
    items, ag = [], [i for i, nm in enumerate(names) if is_agenda(nm)]
    if ag and ag != list(range(ag[0], ag[0] + len(ag))):
        out.append(("agenda-numbers", f"agenda slides {[i + 1 for i in ag]} must follow each other"))
    for i in ag:
        for m in _check_agenda(slides[i], start=len(items) + 1):     # numbering continues across agenda slides
            out.append((f"agenda-numbers:{i + 1}", f"slide {i + 1} Agenda: {m}"))
        items += agenda_items(slides[i])
    if divs and items:
        titles = [_ph_texts(slides[i]).get(10, "") for i in divs]
        if [_norm(t) for t in titles] != [_norm(t) for t in items]:
            out.append(("agenda-chapters", f"divider titles {titles} must match the agenda items {items} in order"))
    for i, s in enumerate(slides, 1):
        nm = names[i - 1]
        tree = s.shapes._spTree
        if expect_thinkcell and not [c for c in tree.iter(qn("p:cNvPr")) if c.get("name") == THINKCELL_NAME]:
            out.append((f"thinkcell:{i}", f"slide {i} lacks the hidden think-cell data object"))
        lay_ftr = any(p.placeholder_format.type == PP_PLACEHOLDER.FOOTER for p in s.slide_layout.placeholders)
        has_ftr = any(p.placeholder_format.type == PP_PLACEHOLDER.FOOTER and p.text_frame.text.strip() for p in s.placeholders)
        if lay_ftr and nm not in COVERS and not has_ftr:
            out.append((f"footer:{i}", f"slide {i} lacks the 'Internal' footer placeholder"))
        texts = _ph_texts(s)
        # picture placeholders: never ship an empty one or a bare 'no photo' frame (dividers carry an icon panel)
        for el in tree.iter(qn("p:pic"), qn("p:sp")):
            php = el.find(f".//{qn('p:nvPr')}/{qn('p:ph')}")
            if php is not None and php.get("type") == "pic" and el.find(f".//{qn('a:blip')}") is None:
                out.append((f"picture:{i}", f"slide {i}: picture placeholder idx {php.get('idx')} left empty - "
                                            "s.picture(idx, approved_image) or remove it (s.quote(..., photo=None))"))
            if _name(el) == "Picture frame (no photo)" and nm not in DIVIDERS:
                out.append((f"picture:{i}", f"slide {i}: empty picture frame shipped on '{nm}' - use an approved "
                                            "image (photos.select_image) or a layout/variant without a picture"))
        for sp in tree.iter(qn("p:sp")):
            ph = sp.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}")
            if ph is None or ph.get("type") in ("ftr", "sldNum", "dt"):
                continue
            t = _txt(sp)
            if nm == "Inhalt & Tracker" and ph.get("idx") in ("14", "15", "16", "17"):
                continue                     # tracker tabs: hidden labels by design
            if not t:
                out.append((f"empty:{i}", f"slide {i}: empty placeholder idx {ph.get('idx', '0')} - fill it or remove_empty()"))
            elif PROMPT_RE.search(t):
                out.append((f"prompt:{i}", f"slide {i}: template prompt/lorem text '{t[:40]}'"))
            for k, p in enumerate(sp.iter(qn("a:p"))):
                r = p.find(qn("a:r"))
                rp = r.find(qn("a:rPr")) if r is not None else None
                if rp is None:
                    continue
                lt = rp.find(qn("a:latin"))
                heading, bold = lt is not None and lt.get("typeface") == "+mj-lt", rp.get("b") == "1"
                if not (heading or bold):
                    continue
                if k > 0:
                    out.append((f"lead:{i}", f"slide {i} idx {ph.get('idx', '0')}: heading/bold paragraph at position {k + 1} - lead only first"))
                else:
                    pPr = p.find(qn("a:pPr"))
                    if not (heading and bold and pPr is not None and pPr.find(qn("a:buNone")) is not None):
                        out.append((f"lead:{i}", f"slide {i} idx {ph.get('idx', '0')}: lead line '{_txt(p)[:30]}' must be bold Mark Pro without bullet (use lead())"))
        if nm in KEYS:
            tiles = sum(1 for idx in TILE_IDX[nm] if texts.get(idx))
            for msg in key_count_problems(texts.get(10, ""), texts.get(13, ""), tiles):
                out.append((f"key-count:{i}", f"slide {i} {nm}: {msg}"))
        for msg in capacity.scan_slide(s, nm):
            out.append((f"capacity:{i}", f"slide {i} ('{nm}') {msg}"))
        for gf in tree.iter(qn("p:graphicFrame")):
            if gf.find(".//" + qn("a:tbl")) is not None:
                for m in _check_table(gf):
                    out.append((f"table:{i}", f"slide {i}: {m}"))
        unit_text = texts.get(16 if nm == "Bild & Diagramm" else 10, "")
        for shp in s.shapes:
            if getattr(shp, "has_chart", False) and shp.has_chart:
                for m in _check_chart(shp.chart, unit_text):
                    out.append((f"chart:{i}", f"slide {i}: {m}"))
        vis = slide_visuals(s)
        if nm.startswith(CONTENT_PREFIXES) and not (vis & VISUAL_ANY):
            out.append((f"visual:{i}", f"slide {i} ('{nm}'): content slide with no icon, diagram, chart, table, picture, "
                                       "info box or key number - add one (RULES §17.3)"))
        for m in check_icon_tiles(s):
            out.append((f"icon-tile:{i}", f"slide {i}: {m}"))
        for m in check_logos(s):
            out.append((f"logo:{i}", f"slide {i}: {m}"))
        main = vis & (INFOGRAPHICS | STRUCTURED)
        if len(main) > 1:
            out.append((f"visual:{i}", f"slide {i}: more than one main visual {sorted(main)} - one per slide"))
        X, Y, W, H = CONTENT_BOX
        for el in tree.iter(qn("p:grpSp"), qn("p:graphicFrame")):
            nm_ = _name(el)
            if nm_.startswith(DIAGRAM_PREFIX) and "chapter_panel" not in nm_:
                b = _bbox_in(el)
                if b and (b[0] < X - 0.01 or b[1] < Y - 0.01 or b[0] + b[2] > X + W + 0.01 or b[1] + b[3] > Y + H + 0.01):
                    out.append((f"visual:{i}", f"slide {i}: '{nm_}' leaves the content area ({', '.join(f'{v:.2f}' for v in b)} in)"))
    content = [i for i, nm in enumerate(names) if nm not in STRUCTURAL and not is_agenda(nm)]
    inf = [i for i in content if slide_visuals(slides[i]) & INFOGRAPHICS]
    cap = infographic_cap(len(content))
    if len(inf) > cap:
        out.append(("infographics", f"{len(inf)} infographic slides {[i + 1 for i in inf]} for {len(content)} content "
                                    f"slides - cap is {cap} (~1/3); turn the weakest into text-led slides (RULES §17.2)"))
    for a, b in zip(inf, inf[1:]):
        if b == a + 1:
            out.append(("infographics", f"slides {a + 1} and {b + 1} are consecutive infographics - put a text-led or "
                                        "structured slide (or a divider) between them"))
    return out


def read_mode(path):
    """'short-pitch' if Deck.save(short_pitch=True) recorded it, else None."""
    with zipfile.ZipFile(path) as z:
        if "docProps/custom.xml" not in z.namelist():
            return None
        x = etree.fromstring(z.read("docProps/custom.xml"))
    return next((p[0].text for p in x if p.get("name") == MODE_PROP), None)


def read_waivers(prs_or_path):
    """Waivers recorded by Deck.save() in docProps/custom.xml (property sgdeck_waivers)."""
    path = prs_or_path if isinstance(prs_or_path, str) else None
    if path is None:
        return {}
    with zipfile.ZipFile(path) as z:
        if "docProps/custom.xml" not in z.namelist():
            return {}
        x = etree.fromstring(z.read("docProps/custom.xml"))
    for p in x:
        if p.get("name") == WAIVER_PROP:
            try:
                return json.loads(p[0].text or "{}")
            except ValueError:
                return {"_unreadable": ""}
    return {}


# ================================================================================================ deck
class Deck:
    def __init__(self, template=TEMPLATE, strip_fonts=True):
        if not os.path.isfile(template):
            raise GuideError(f"template not found: {template}. It ships as template.pptx in the skill folder; "
                             "pass Deck(template=<path>) if you moved it.")
        try:
            self.prs = Presentation(template)
        except Exception as e:
            raise GuideError(f"template {template} is not a readable .pptx ({e.__class__.__name__}: {e})") from e
        self.notices, self.slides_meta, self.branded = [], [], dict(KEPT_BRAND)
        self._tc = self._capture_thinkcell()
        lst = self.prs.slides._sldIdLst
        for sid in list(lst):
            self.prs.part.drop_rel(sid.get(qn("r:id")))
            lst.remove(sid)
        self.layouts = {l.name: l for l in self.prs.slide_layouts}
        if strip_fonts:
            self._strip_embedded_fonts()
        self._dedupe_ids()

    def _dedupe_ids(self):
        """template.pptx repeats shape ids inside master/layouts (schema-invalid); renumber the duplicates."""
        for obj in list(self.prs.slide_masters) + list(self.prs.slide_layouts):
            els = list(obj._element.iter(qn("p:cNvPr")))
            nxt = max([int(e.get("id")) for e in els if (e.get("id") or "").isdigit()] + [1]) + 1
            seen = set()
            for e in els:
                v = e.get("id")
                if not (v or "").isdigit() or v in seen:
                    e.set("id", str(nxt)); v = str(nxt); nxt += 1
                seen.add(v)

    # --- fonts -----------------------------------------------------------
    def _strip_embedded_fonts(self):
        """The template embeds the template brand's licensed Mark Pro subsets - they are NOT licensed for
        other decks. Remove the .fntdata parts + embeddedFontLst; keep the theme font NAMES."""
        pres = self.prs.part._element
        lst = pres.find(qn("p:embeddedFontLst"))
        n = 0
        if lst is not None:
            rids = [e.get(qn("r:id")) for e in lst.iter() if e.get(qn("r:id"))]
            pres.remove(lst)
            for rid in rids:
                if rid in self.prs.part.rels:
                    self.prs.part.rels.pop(rid); n += 1
        for att in ("embedTrueTypeFonts", "saveSubsetFonts"):
            if att in pres.attrib:
                del pres.attrib[att]
        self.notices.append(f"Embedded fonts removed ({n} font parts): the template's Mark Pro subsets are "
                            "licensed to the template owner only. The deck names Mark Pro / Mark Pro Light; "
                            "recipients need their own licensed install, otherwise PowerPoint substitutes.")

    # --- think-cell --------------------------------------------------------
    def _capture_thinkcell(self):
        for sl in self.prs.slides:
            for gf in sl.shapes._spTree.iter(qn("p:graphicFrame")):
                c = gf.find(qn("p:nvGraphicFramePr")).find(qn("p:cNvPr"))
                if c is not None and c.get("name") == THINKCELL_NAME:
                    rels = {}
                    for el in gf.iter():
                        for att in (qn("r:id"), qn("r:embed")):
                            rid = el.get(att)
                            if rid:
                                rels[rid] = sl.part.rels[rid]
                    return {"xml": copy.deepcopy(gf), "rels": {k: (r.reltype, r.target_part) for k, r in rels.items()}}
        return None

    def _add_thinkcell(self, slide):
        if not self._tc:
            return
        el = copy.deepcopy(self._tc["xml"])
        mapping = {}
        for old, (rt, part) in self._tc["rels"].items():
            if rt == RT_TAGS:   # one tag part per slide, like the guide
                pn = self.prs.part.package.next_partname("/ppt/tags/tag%d.xml")
                part = Part(pn, TAGS_CT, self.prs.part.package, part.blob)
            mapping[old] = slide.part.relate_to(part, rt)
        for e in el.iter():
            for att in (qn("r:id"), qn("r:embed")):
                if e.get(att) in mapping:
                    e.set(att, mapping[e.get(att)])
        tree = slide.shapes._spTree
        nid = str(_next_id(tree))
        for c in el.iter(qn("p:cNvPr")):
            if c.get("name") == THINKCELL_NAME:
                c.set("id", nid)
        tree.insert(2, el)

    # --- brand -------------------------------------------------------------
    def brand(self, name=None, website=None, **_ignored):
        """Decks keep the amasol style guide's own branding: the template's amasol logo groups, copyright line,
        closing social/web icons and links stay exactly as designed. Nothing is replaced. Kept for backwards
        compatibility; any other brand name is refused (no re-branding)."""
        if name and name.strip().lower() != TEMPLATE_BRAND:
            raise GuideError(f"decks keep the {TEMPLATE_BRAND} branding - re-branding to '{name}' is not supported")
        self.branded = dict(KEPT_BRAND)
        return self

    def _textmark(self, tree, shape_name, text, x, y, cx, cy, font, sz):
        algn = "r" if x + cx / 2 > 9144000 / 2 else "l"
        esc = text.replace("&", "&amp;").replace("<", "&lt;")
        return etree.fromstring(
            f'<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            f'xmlns:a="{A}"><p:nvSpPr><p:cNvPr id="{_next_id(tree)}" name="{shape_name}"/>'
            f'<p:cNvSpPr txBox="1"/><p:nvPr userDrawn="1"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
            f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="b"><a:noAutofit/></a:bodyPr>'
            f'<a:lstStyle/><a:p><a:pPr algn="{algn}"><a:lnSpc><a:spcPct val="100000"/></a:lnSpc></a:pPr>'
            f'<a:r><a:rPr lang="en-US" sz="{sz * 100}" b="0" dirty="0"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
            f'<a:latin typeface="{font}"/></a:rPr><a:t>{esc}</a:t></a:r></a:p></p:txBody></p:sp>')

    # --- slides --------------------------------------------------------------
    def add(self, layout_name, footer=None, kind=None, plan=None):
        """kind: 'service' | 'process' | 'team' -> the guide icon pattern is required on that slide (lint).
        plan: the plan.json slide id this slide realises (stored as the slide name 'plan:<id>'; verify_deck.py
        --plan checks the planned visual is on it)."""
        if layout_name not in self.layouts:
            close = difflib.get_close_matches(layout_name, list(self.layouts), n=3, cutoff=0.5)
            raise GuideError(f"'{layout_name}' is not a guide layout name" + (f"; did you mean {close}?" if close else "")
                             + f" Valid names (exact, case- and umlaut-sensitive): {list(self.layouts)}")
        if footer is None:
            footer = layout_name not in COVERS
        lay = self.layouts[layout_name]
        s = self.prs.slides.add_slide(lay)
        if footer:
            tree = s.shapes._spTree
            next_id = _next_id(tree)
            for ph in lay.placeholders:
                if ph.placeholder_format.type == PP_PLACEHOLDER.FOOTER:
                    el = copy.deepcopy(ph._element)
                    el.find(".//" + qn("p:cNvPr")).set("id", str(next_id)); next_id += 1
                    tree.append(el)
        self._add_thinkcell(s)
        if plan:
            s._element.find(qn("p:cSld")).set("name", f"plan:{plan}")
        sl = Slide(self, s, lay, kind)
        self.slides_meta.append(sl)
        return sl

    def agenda(self, items):
        """Deck helper: add the Agenda (plus continuation slides when > 8 items), filled and cleaned."""
        s = self.add("Agenda")
        pages = s.agenda(items)
        for p in pages:
            p.remove_empty()
        return pages

    def _add_after(self, after, layout_name):
        """Add a slide and move it (and its lint metadata) directly after `after`."""
        new = self.add(layout_name)
        lst = self.prs.slides._sldIdLst
        ids = list(lst)
        pos = [i for i, sl in enumerate(self.prs.slides) if sl.slide_id == after.s.slide_id][0]
        el = ids[-1]
        lst.remove(el); lst.insert(pos + 1, el)
        self.slides_meta.remove(new)
        self.slides_meta.insert(self.slides_meta.index(after) + 1, new)
        return new

    def _agenda_layout(self, k):
        """The guide's Agenda layout with exactly k slots (k = 8: the guide layout itself). Built on first use as
        a clone of 'Agenda' - same geometry, fills, spacing and reading-order positions - with the placeholders of
        slots k+1..8 removed, so nothing of an unused slot exists to be drawn."""
        if not 2 <= k <= 8:
            raise GuideError(f"an agenda slide takes 2-8 items, got {k}")
        name = "Agenda" if k == 8 else f"Agenda {k}"
        if name in self.layouts:
            return self.layouts[name]
        from pptx.opc.package import _Relationship
        from pptx.parts.slide import SlideLayoutPart
        base = self.layouts["Agenda"]
        el = copy.deepcopy(base._element)
        el.find(qn("p:cSld")).set("name", name)
        drop = {i for pair in AGENDA_SLOTS[k:] for i in pair}
        for sp in list(el.iter(qn("p:sp"))):
            ph = sp.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}")
            if ph is not None and ph.get("idx") and int(ph.get("idx")) in drop:
                sp.getparent().remove(sp)
        pkg = self.prs.part.package
        part = SlideLayoutPart(pkg.next_partname("/ppt/slideLayouts/slideLayout%d.xml"), base.part.content_type, pkg, el)
        for rId, rel in base.part.rels.items():                  # same rIds -> the XML references stay valid
            part.rels._rels[rId] = _Relationship(part.partname.baseURI, rId, rel.reltype, rel._target_mode, rel._target)
        master = base.slide_master
        rid = master.part.relate_to(part, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout")
        lst = master._element.find(qn("p:sldLayoutIdLst"))
        used = [int(e.get("id")) for m in self.prs.slide_masters for e in m._element.find(qn("p:sldLayoutIdLst"))]
        used += [int(e.get("id")) for e in self.prs.part._element.find(qn("p:sldMasterIdLst"))]
        lid = etree.SubElement(lst, qn("p:sldLayoutId"))
        lid.set("id", str(max(used) + 1)); lid.set(qn("r:id"), rid)
        lay = [l for l in master.slide_layouts if l.part is part][0]
        self.layouts[name] = lay
        return lay

    # --- lint ------------------------------------------------------------------
    def lint(self, mode=None):
        """All guide rules (lint_prs) plus build-session checks (brand call, icon kinds)."""
        out = []
        for i, m in enumerate(self.slides_meta, 1):
            if m.kind in ("service", "process", "team") and not m.icon_sizes and m.name not in KEYS:
                out.append((f"icons:{i}", f"slide {i} ({m.kind}) needs guide icons (white tile pattern)"))
        return out + lint_prs(self.prs, expect_thinkcell=bool(self._tc), mode=mode)

    # --- metadata ----------------------------------------------------------------
    def _reset_metadata(self, waive, mode=None):
        """Never ship the template owner's metadata: drop customXml (SharePoint fields, names, e-mails) and the
        template's custom properties, rewrite core + app properties, record waivers as sgdeck_waivers."""
        for rid, rel in list(self.prs.part.rels.items()):
            if rel.reltype == RT_CUSTOMXML:
                self.prs.part.rels.pop(rid)
        pkg = self.prs.part.package
        for rid, rel in list(pkg._rels.items()):
            if rel.reltype == RT_CUSTPROPS:
                pkg._rels.pop(rid)
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
        cp = self.prs.core_properties
        title = ""
        if self.slides_meta:
            first = self.slides_meta[0].s
            title = next((p.text_frame.text.replace("\n", " ") for p in first.placeholders
                          if p.placeholder_format.idx == 0 and p.has_text_frame), "")
        brand = KEPT_BRAND["name"]
        cp.title, cp.author, cp.last_modified_by = title[:250], brand, brand
        for att in ("subject", "keywords", "comments", "category", "content_status", "identifier", "language", "version"):
            setattr(cp, att, "")
        cp.revision, cp.created, cp.modified = 1, now, now
        for el in list(cp._element):
            if el.tag.endswith("}lastPrinted"):
                cp._element.remove(el)
        for rid, rel in list(pkg._rels.items()):         # template thumbnail shows the template owner's cover
            if rel.reltype.endswith("/metadata/thumbnail"):
                pkg._rels.pop(rid)
        n = len(self.slides_meta)
        app = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.'
               f'openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/'
               f'officeDocument/2006/docPropsVTypes"><TotalTime>0</TotalTime><Application>Microsoft Office PowerPoint'
               f'</Application><PresentationFormat>On-screen Show (16:9)</PresentationFormat><Slides>{n}</Slides>'
               f'<Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips><ScaleCrop>false</ScaleCrop>'
               f'<LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged>'
               f'<Company>{KEPT_BRAND['company']}</Company><AppVersion>16.0000</AppVersion></Properties>').encode()
        for rel in pkg._rels.values():
            if rel.reltype == RT_APPPROPS:
                rel.target_part._blob = app
        props = ([(WAIVER_PROP, json.dumps(waive, ensure_ascii=False))] if waive else []) + \
                ([(MODE_PROP, mode)] if mode else [])
        if props:
            esc = lambda v: v.replace("&", "&amp;").replace("<", "&lt;")
            body = "".join(f'<property fmtid="{{D5CDD505-2E9C-101B-9397-08002B2CF9AE}}" pid="{k + 2}" name="{n}">'
                           f'<vt:lpwstr>{esc(v)}</vt:lpwstr></property>' for k, (n, v) in enumerate(props))
            blob = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.'
                    'openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/'
                    f'officeDocument/2006/docPropsVTypes">{body}</Properties>').encode()
            part = Part(PackURI("/docProps/custom.xml"), CT_CUSTPROPS, pkg, blob)
            pkg.relate_to(part, RT_CUSTPROPS)

    def save(self, path, waive=None, short_pitch=False):
        """Lint (raise GuideError unless every finding is waived with a reason), reset metadata, record waivers,
        save, then fail if any leftover foreign (e.g. SudoSapient) branding is in the package; amasol branding is kept.
        short_pitch=True (decks <= SHORT_PITCH_MAX slides): no agenda/dividers needed; recorded in the deck as
        sgdeck_mode='short-pitch' and printed, never counted as a failure."""
        waive = dict(waive or {})
        mode = "short-pitch" if short_pitch else None
        bad = [k for k in waive if k not in WAIVABLE]
        if bad:
            raise GuideError(f"only deck-level rules can be waived ({sorted(WAIVABLE)}); fix these instead: {bad}")
        short = [k for k, v in waive.items() if len(str(v).strip()) < 10]
        if short:
            raise GuideError(f"every waiver needs a written reason (>= 10 chars): {short}")
        findings = self.lint(mode)
        self.notes = [m for k, m in findings if k == "short-pitch"]
        problems = [(k, m) for k, m in findings if k.split(":")[0] not in waive and k != "short-pitch"]
        if problems:
            raise GuideError("deck lint failed:\n  " + "\n  ".join(f"[{k}] {m}" for k, m in problems))
        self.waivers = waive
        self._reset_metadata(waive, mode)
        self.prs.save(path)
        with zipfile.ZipFile(path) as z:
            hits = foreign_branding(z)
        if hits:
            raise GuideError(f"foreign branding {FOREIGN_BRANDS}: {hits} - decks keep the {TEMPLATE_BRAND} branding "
                             "(naming a client in slide text is fine)")
        side = path + ".waivers.json"
        if waive:
            json.dump(waive, open(side, "w"), indent=1, ensure_ascii=False)
        elif os.path.exists(side):
            os.remove(side)
        for msg in self.notices:
            warnings.warn(msg)
        for k, v in self.waivers.items():
            print(f"WAIVED [{k}]: {v}  <- report this to the user")
        for m in self.notes:
            print(f"SHORT-PITCH: {m}  <- recorded, not a failure; report it")
        return path

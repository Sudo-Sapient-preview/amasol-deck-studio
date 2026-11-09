# Style guide – full rule set

Rules for building decks from `template.pptx` (the style-guide deck: 1 master, 50 layouts, 63 slides).
SKILL.md holds the workflow only; every rule lives here, once. Machine-readable values: `tokens.json`;
measured text capacity: `reference/capacity.md` (generated, also in `tokens.json → capacity`).

**Labels.** Every rule carries one label:
* **[GUIDE]** – stated in the guide, or measured directly from its master/layout/slide XML (positions, sizes,
  colours, insets, the capacity table).
* **[DERIVED]** – inferred by us from the guide's examples, from licensing, or from layout logic. Follow it,
  but if the user's own guide material contradicts it, the user wins.

## Contents
1. Canvas and grid
2. Typography
3. Colour
4. Shapes, lines, boxes
5. Tables
6. Charts
7. Icons
8. Imagery, logo and amasol branding (8.1 Third-party logos)
9. Layout archetypes and placeholder indices (9.1 Agenda slots and item counts)
10. Content mapping
11. Deck structure
12. Text capacity and density
13. Footer and think-cell object
14. Do's and don'ts stated in the guide
15. Glossary
16. Verification and packaging
17. Infographics and diagrams (17.1 builders · 17.2 middle ground · 17.3 a visual per slide · 17.4 dividers ·
    17.5 plan and verify)

## 1. Canvas and grid

| Item | Value | Label |
|---|---|---|
| Slide size | 16:9, 10 × 5.625 in (9 144 000 × 5 143 500 EMU) | [GUIDE] |
| Left / right margin | 0.432 in (≈395 000 EMU) each side; content width 9.135 in | [GUIDE] |
| Title placeholder | x 0.432, y 0.374, w 9.135, h 0.303 in, top-anchored, zero insets | [GUIDE] |
| Subtitle placeholder | x 0.432, y 0.755, w 9.135, h 0.202 in | [GUIDE] |
| Content area ("Inhaltsbereich", guide slide 2) | x 0.432 → 9.567, y 1.198 → 5.096 in (w 9.135, h 3.898); never place content outside it (layout decor excepted) | [GUIDE] |
| Two columns | left x 0.432, right x 5.196, each w 4.372, gutter 0.392 in | [GUIDE] |
| Text + visual | text w 4.844 at x 0.432; picture/visual w 3.898 at x 5.67 (square 3.898 × 3.898) | [GUIDE] |
| Footer row | y 5.248 in, 8 pt: slide number (x 0.432) · copyright (x 0.884) · "Internal" (x 3.661) · amasol logo (x 8.456, w 1.112) | [GUIDE] |
| Text insets | 0 on title/body placeholders; 0.118 × 0.079 in (108 000 × 72 000 EMU) inside filled shapes | [GUIDE] |

## 2. Typography

* [DERIVED] **Fonts are never embedded in built decks.** template.pptx embeds Mark Pro subsets licensed to the
  template owner only; `Deck()` strips the `.fntdata` parts and `embeddedFontLst`. Keep the theme font NAMES;
  recipients need a licensed Mark Pro install. Previews use Outfit (`reference/fonts-preview.conf`).
* [GUIDE] **Two faces only**: `Mark Pro` (theme major, `+mj-lt`) and `Mark Pro Light` (theme minor, `+mn-lt`).
  Always reference the theme slots, never type a font name, never add another family. Bullets use the
  master's `Arial` "•" – leave as is.
* [GUIDE] Weight logic: Mark Pro = titles, headlines, lead lines, numbers, table header/total, key pills.
  Mark Pro Light = running text, subtitles, bullets, table body, values. Bold only on agenda numbers (layout)
  and on lead lines (the guide's bullet example, slide 3, sets `b="1"` on its lead line; `lead=` writes it).
  No italics, no underline.
* [GUIDE] Letter spacing 0, line spacing 100 %, space before 0, space after 3 pt (body levels).
* [DERIVED] No all-caps styles (caps only in proper nouns/abbreviations). No arrow glyphs (→ ←) – the font
  may lack them; use words or an en dash (sgdeck raises).
* [GUIDE] Alignment left everywhere; centred only in key pills and agenda number tiles (layout defaults).
* [DERIVED] Minimum reading size 12 pt (footers/annotations 7–9 pt excepted).

[GUIDE] Type scale (from master/layout XML):

| Role | Size | Face | Colour |
|---|---|---|---|
| Cover title (`Titelfolie mit Bild`) | 48 pt, bottom-anchored | Mark Pro | black |
| Cover title (`Titelfolie ohne Bild`) | 48 pt | Mark Pro | blue 0074A4 |
| Cover subtitle / date | 14 pt | Mark Pro Light | black |
| Closing headline (`Schlussfolie`) | 48 pt | Mark Pro | red (mint bg) / black (white bg) |
| Section title (`Kapiteltrenner`) | 36 pt, bottom-anchored | Mark Pro | olive C4A800 on cream; red on white & mint |
| Section number (Blau) | 24 pt in white rounded square | Mark Pro Light | black |
| Section / quote / key sub-line | 12–14 pt | Mark Pro Light | black |
| Agenda title | 32 pt on red panel | Mark Pro | white |
| Agenda number / item | 18 pt bold / 18 pt | Mark Pro Light | black |
| Quote / key headline | 20 pt | Mark Pro | per layout: olive (`Zizat - Gelb`) · blue (`Zitat- Rosa`, `Key Slide 2` on cream) · red (`Zitat - Blau`) · black (`Key Slide 1`) – inherited, never set |
| Slide title | 18 pt | Mark Pro | black |
| Slide subtitle | 12 pt | Mark Pro Light | black |
| Body level 1 | 14 pt, bullet •, marL 0.197 in hanging | Mark Pro Light | black |
| Body level 2–5 | 12 pt, each level +0.197 in | Mark Pro Light | black |
| Lead line (first line of a block, no bullet) | 14 pt **bold** | Mark Pro | black |
| Info-box big number | 32 pt | Mark Pro | red |
| Key pill text | 14 pt centred | Mark Pro | white |
| Key tile text | 12 pt top-left | Mark Pro Light | white (black on light-grey tile) |
| Table header / body / total | 14 / 12 / 12 pt | Mark Pro / Light / Mark Pro | black |
| Chart axis labels | 10 pt half-width (category labels Mark Pro), 12 pt full-width – set chart-wide, never the 18 pt default | Light | black |
| Chart legend | 10 pt, bottom | Mark Pro Light | black |
| Diagram labels (§17) | 12 pt, 10 pt where 12 pt does not fit; headings 14/12 pt; values 32/24 pt | Light / Mark Pro | black / red values |
| Footer, annotations | 7–9 pt (8 pt standard) | Mark Pro Light | black |

## 3. Colour

[GUIDE] **Primary** (guide slide "Farben"): `#000000` black · `#DB2F16` red · `#0074A4` blue · `#8B8A7C` warm
grey · `#C4A800` olive yellow · `#EBEAE2` light grey. **Secondary** (backgrounds only): `#D3F1F0` mint ·
`#F5E1EA` pink · `#FFF8DF` cream. Plus white `#FFFFFF`.

[GUIDE] Theme mapping: dk1/dk2/accent6 = 000000, lt1/bg1 = EBEAE2, lt2/bg2 = FFFFFF, accent1/accent5/hlink =
DB2F16, accent2/folHlink = 0074A4, accent3 = 8B8A7C, accent4 = C4A800; custom colours Mint/Pink/Yellow.

1. [GUIDE] Only these ten values, written as theme slots wherever possible.
2. [GUIDE] *Guide states*: no tints/shades (the tint grid is crossed out), no Office standard colours.
3. [GUIDE] *Guide states*: "Niemals Transparenzen!" – never transparency on any fill.
4. [GUIDE] Text is black; white only on red/blue/black/warm-grey/olive fills; coloured text only for the
   layout-defined headlines (section, quote, key, cover-without-image, closing).
5. [GUIDE] Red is the lead accent (info box, first chart series, table header rule, active tracker tab, agenda panel).
6. [GUIDE] Chart series order red → blue → warm grey → olive. [DERIVED] max 4 series.
7. [GUIDE] Backgrounds come from the layout: Weiß, Grau (master default), Gelb, Rosa, Blau. Never set one by hand.
8. [GUIDE] Panels on white use light grey; panels/tiles/picture frames on grey or colour use white.
9. [DERIVED] No gradients, shadows, glows or bevels anywhere (none appear in the guide).

## 4. Shapes, lines, boxes

* [GUIDE] Rounded rectangles throughout (picture frames adj 5121, panels 4646, chart panels top-rounded 6136,
  key tiles 13529, agenda tiles 8428, icon tiles 16667, pills 50000).
* [DERIVED] **The icon tile follows its container** (§7): a rounded square in a rounded rectangle, a circle in
  a pill, stadium, oval or circle. "Fully round" = ellipse, or a roundRect whose radius (adj) is at least half
  the short side (adj ≥ 0.49). Logo chips (§8.1) are rounded like icon tiles.
* [GUIDE] *Guide states*: lines 1, 1.5, 3 or 6 pt, blue `#0074A4` or black; 1.5 pt black dashed allowed.
* [GUIDE] *Guide states*: text boxes only as **Fläche** (solid red, white text) or **Rahmen** (no fill, 1 pt blue
  outline, black text); padding at least one cap height (0.118 × 0.079 in).
* [GUIDE] "Form" tab (vertical pill off the edge: red on white/grey, blue on cream, black on pink, olive on mint)
  comes only from the `… & Form` layouts; never draw it.
* [GUIDE] Tracker (`Inhalt & Tracker`): four right-edge tabs, active red, others light grey, labels 1 pt (hidden).
* [DERIVED] Info box only on content layouts (`Inhalt*`, `2 Inhalte*`), max one per slide (sgdeck raises).
* [DERIVED] No shape combinations the guide does not show: no outlined shapes under pills/tiles, no extra tiles
  on Key Slides (sgdeck raises).
* [DERIVED] A picture placeholder the layout shows (section dividers, quotes) is never left as an empty prompt:
  fill it with a photo the user supplied, else `s.picture_frame(idx)` draws the guide's rounded frame in the
  layout geometry (white on colour backgrounds, light grey on white – rule 3.8). Never stock or AI imagery.

## 5. Tables

* [GUIDE] Tables sit in the content placeholder (idx 11): x 395288, y 1095375, w 8353425 EMU, graphicFrame
  carries `<p:ph idx="11"/>` – `s.table()` does this.
* [GUIDE] No vertical lines, no zebra, table style "No Style, No Grid". Header 14 pt Mark Pro, 1.5 pt red rule
  below; body 12 pt Light, 1 pt warm-grey rule under every row **including the last**; optional total row with
  light-grey fill, warm-grey rule above, Mark Pro. Row height 0.393 in, cell padding L 0 / R 0.098 / T,B 0.051 in.
  Line props: cap flat, cmpd sng, solid, round join, no head/tail.
* [GUIDE] Full content width, equal columns unless the data needs otherwise; set `col_w=` when a text column
  needs more width so every cell stays on one line.
* [GUIDE] One line per cell: the guide's row height (0.393 in) holds exactly one 12 pt line (lint fails 2+).
* [DERIVED] ≤ 9 rows incl. header and total (9 × 0.393 in fills the 3.898 in content area) × 6 columns
  (sgdeck raises). Amount tables get a total row only when the total is the arithmetic sum of the rows.
  Capacity: see §12.

## 6. Charts [GUIDE]

Clustered columns, gap width 219 %, overlap −27 %. Series colours red, blue, warm grey, olive. No gridlines,
no value-axis line, 0.75 pt black category-axis line, no tick marks, whole-number steps, no data labels, no
chart title (the slide title carries it), legend at bottom (omit for one series), transparent chart area.
Half-width charts sit in the rounded grey (on white) or white (on colour) panel of the chart layouts.
[GUIDE] Chart text is 10 pt (half-width) / 12 pt (full-width) chart-wide, Mark Pro Light, category labels Mark
Pro; axis ids positive (`style_chart()` does all of this).
[DERIVED] Charts only for real numbers. The unit is stated in the slide subtitle or a category/series name
(e.g. "$ billion"); one scale per value axis – series whose max/min ratio exceeds 10 go into separate charts or
the text (sgdeck raises, lint fails); the slide title states what the chart shows, nothing it does not show.
[DERIVED] Parts of ONE whole (2–4 shares) may be a native doughnut or pie (`s.donut(cats, values, pie=)`): one
series, slices in the series order, legend at the bottom, no title, no data labels; never from an open bound
("200+") or from counted logos/names (§17.5).

## 7. Icons

* [GUIDE] Monoline, rounded caps/joins, uniform stroke, black, no fill, square. 106 files in `assets/icons/`
  (index `assets/icons/index.json`, overview `assets/icons/_icon-sheet.png`).
* [GUIDE] Showcase treatment: icon 0.363 in centred in a 0.727 in white rounded tile (adj 16667), pitch 0.841 in.
* [DERIVED] **Adaptive tile**: the white tile repeats the shape of what holds it – rounded square (adj 16667) in
  rounded rectangles and panels, **circle** in pills, stadiums, ovals and circles (a rounded square in a pill
  looks off). sgdeck reads this from the geometry (`tile_shape="auto"`, the default in `icon()`, `icon_row()`
  and every diagram builder; the container is the smallest painted shape on the slide or layout that holds the
  tile). Override with `tile_shape="rounded"|"circle"` only for a reason; lint `icon-tile:i` fails a tile that
  does not match its container. A fully round divider panel insets `chapter_panel` to its inscribed square.
* [DERIVED] Black, 0.36–0.5 in, one size per slide (sgdeck raises); never recolour, never another set or
  emoji; if no guide icon fits, use none.
* [DERIVED] Icons are **required** on service/offer slides (one icon tile) and process slides (one tile per
  step, same order) – `d.add(..., kind="service"|"process")` makes the lint enforce it. Not on Key Slide tiles.
* [DERIVED] Lists of steps, levels and items carry icons by default (the diagram builders put one per item).
  Compact tile = the showcase tile; hero icon (divider panel) = 1.5 × the tile. Text-led slides without another
  visual get `s.icon_set()` (one tile per point) or a key number; a lone `at="corner"` tile only next to a body
  that already fills the area (the sparse lint fails it otherwise).

## 8. Imagery, logo and amasol branding

* [GUIDE] Photography: desaturated, cool-grey, architectural. Full-bleed only on `Titelfolie mit Bild`;
  elsewhere inside the rounded picture placeholders (crop to fill, never stretch).
* [DERIVED] Photos only in this order (§8.2): the user's own image, else (when content needs a picture) a
  generated illustration, else Openverse CC0 stock, else the layout without a picture. The guide's own photos
  belong to the template owner and are not shipped.
* [DERIVED] **Keep the amasol branding**: the template's amasol logo groups, copyright line, closing social/web
  icons and amasol hyperlinks stay exactly as designed on master and layouts. No re-branding: `d.brand()` is
  optional, keeps everything, and raises for any other company name. `d.save()` fails on foreign
  branding (e.g. "SudoSapient") in the master, layouts or theme, as metadata author/company, or in a © line.
  Naming a company in slide text or notes - e.g. the client of a proposal - is content and is allowed.
* [DERIVED] **Metadata is reset on save**: template customXml (SharePoint fields, e-mail addresses), custom
  properties, thumbnail, last-printed date, core title/creator/lastModifiedBy and app.xml (slide count, template
  name, slide titles) are removed or rewritten from the deck's own title; author, lastModifiedBy and company are "amasol".
* [GUIDE] amasol logo position: large 2.041 × 0.236 in (top-left of the image cover, top-right of the
  plain cover/section slides), small 1.112 × 0.128 in in the footer. Never move, rescale or add a second one.

### 8.2 Photo sourcing [DERIVED]
Content leads; the layout is matched to the content, not the other way round.
* **Order**: (1) an image the user supplied – always first; (2) if the content needs a picture, a generated
  illustration that represents the content (`photos.generate_illustration` – TODO, lands with the
  infographics/visuals work; until then this step is a no-op); (3) a free-licence stock photo from Openverse
  only via `scripts/photos.py` (CC0 / Public Domain Mark; **CC BY stays off**; Unsplash / Pexels key paths are
  disabled / unused); (4) none – use a layout without a picture (frameless quote when there is no photo).
* **Never invent people or brands**: queries describe objects, places or abstract scenes; never a named person,
  customer, product or brand; results whose title/tags name one are skipped. **That text filter cannot see the
  picture**: every stock pick comes back with `review` set and must be opened and rejected if it shows people,
  faces or brand names/logos before it goes into `--photos` (a tested pick for "warehouse shelves" showed five
  people and branded boxes). Query again with a narrower object or scene, or use a layout without a picture. Illustrations (when implemented)
  depict the content, never a named person or brand mark.
* **No photo → no picture layout**: `matcher.match(..., photos=map)` keeps picture layouts only for slides with an
  approved photo; `s.quote(head, lines, photo=None)` removes the Zitat picture frame and widens the text. The lint
  `picture:i` fails any empty picture placeholder left in the deck.
* Every pick is logged with its licence in `<cache>/photos.json`; list it in the hand-off.

### 8.1 Third-party logos (customers, partners) [DERIVED]
The guide shows none; these rules keep them legible and honest.
* **Source**: only files the user supplies or the company's own official artwork – its website or brand/press
  kit, or Wikimedia Commons files of the official mark (check that the file really is that company – names
  collide). Prefer SVG; render to a transparent PNG (≥ 1200 px wide) and trim to the ink. Keep a `sources.md`
  next to the logos with the download URL per logo. Never redraw, trace, generate or take a logo from a
  third-party "logo download" site. Some companies require written consent before their logo is shown as a
  reference – when their terms say so, leave the logo out and tell the user.
* **No recolouring**: use the colour, dark or white variant the company publishes, as is.
* **Legibility**: a logo must reach ≥ 3:1 contrast (WCAG non-text) against what is behind it on most of its
  ink (`LOGO_MIN_SHARE` 50 %), and lose ≤ 10 % of its ink to the background. If it does not on the tile, it
  sits on a rounded chip in a guide colour – white, blue, black in that order (`chips="auto"`).
* **Size and placement**: one visual size for the whole grid (height from the logo's aspect ratio, so wide and
  square marks look alike – never stretch), padding all round, aligned rows, no overlaps; all logos on one slide
  in tiles (`s.logo_grid` / `s.tile_grid(..., logos=)`, `reference/diagrams.md`).
* **No logo found**: the company name stays as plain text in the same grid; say which names have no logo.
* Lint `logo:i` (verify "logos"): contrast, inside a tile, no overlapping logos. Logos are named
  `sgdeck logo: <company>` with the company as alt text.

## 9. Layout archetypes and placeholder indices [GUIDE]

Families repeat in five backgrounds: Weiß (white), Grau (light grey), Gelb (cream), Rosa (pink), Blau (mint).

| Archetype | Layouts |
|---|---|
| Cover | `Titelfolie mit Bild` (full-bleed photo, black 48 pt), `Titelfolie ohne Bild` (pink bg, blue 48 pt) |
| Agenda | `Agenda` (red panel + up to 8 numbered items, reading order 01 02 / 03 04 / …); per-count clones `Agenda 2`…`Agenda 7` are made at build time (§9.1) |
| Section divider | `Kapiteltrenner - Gelb` / `- Weiß` (photo left, title right), `Kapiteltrenner - Blau` (title left, photo right, number square) |
| Quote | `Zizat - Gelb` (photo left), `Zitat- Rosa`, `Zitat - Blau` (photo right) – idx 10 quote, idx 13 source |
| Key message | `Key Slide 1` (headline + 4 coloured pills: process/steps/4 facts), `Key Slide 2` (headline left + 6 coloured tiles: 6 points) |
| Content + info box | `Inhalt & Infobox` (text left; grey panel right with heading idx 15, big red number idx 16, text idx 17) |
| Content full width | `Inhalt - <bg>` (also used for tables, charts, colour/icon grids) |
| Two columns / comparison | `2 Inhalte - <bg>` |
| Content + chart | `Inhalt & Diagramm - <bg>`, `Diagramm & Inhalt - <bg>`, `Inhalt & Tracker` (white, with 4-step tracker) |
| Picture + chart | `Bild & Diagramm` |
| Content + picture | `Inhalt & Bild - Rosa`, `Inhalt, Bild & Form - Blau` |
| Variants with Form tab | `Inhalt & Form`, `2 Inhalte & Form`, `Inhalt, Diagramm & Form` (each per background) |
| Closing | `Schlussfolie - Blau` (red headline), `Schlussfolie - Weiß` (black headline) |

Placeholder indices (idx) per layout:

| # | Layout name (exact) | Placeholders (idx=type; footer omitted) |
|---|---|---|
| L0 | `Titelfolie mit Bild` | 10=picture, 0=center_title, 1=subtitle |
| L1 | `Titelfolie ohne Bild` | 0=center_title, 1=subtitle |
| L2 | `Agenda` | 0=title, 12=body, 13=body, 16=body, 19=body, 20=body, 23=body, 24=body, 27=body, 28=body, 29=body, 30=body, 31=body, 32=body, 33=body, 34=body, 35=body |
| L3 | `Kapiteltrenner - Gelb` | 10=body, 11=picture, 13=body |
| L4 | `Kapiteltrenner - Weiß` | 10=body, 11=picture, 13=body |
| L5 | `Kapiteltrenner - Blau` | 10=body, 11=picture, 12=body |
| L6 | `Zizat - Gelb` | 10=body, 13=body, 11=picture |
| L7 | `Zitat- Rosa` | 10=body, 13=body, 11=picture |
| L8 | `Zitat - Blau` | 10=body, 13=body, 11=picture |
| L9 | `Key Slide 1` | 10=body, 13=body, 14=body, 16=body, 17=body, 18=body |
| L10 | `Key Slide 2` | 10=body, 13=body, 14=body, 16=body, 17=body, 18=body, 19=body, 20=body |
| L11 | `Inhalt & Infobox` | 10=body, 0=title, 11=object, 15=body, 16=body, 17=body |
| L12 | `Inhalt - Weiß` | 10=body, 0=title, 11=object |
| L13 | `2 Inhalte - Weiß` | 10=body, 0=title, 11=object, 12=object |
| L14 | `Inhalt & Form - Weiß` | 10=body, 0=title, 11=object |
| L15 | `2 Inhalte & Form - Weiß` | 10=body, 0=title, 11=object, 12=object |
| L16 | `Inhalt & Tracker` | 14=body, 10=body, 0=title, 11=object, 12=chart, 15=body, 16=body, 17=body |
| L17 | `Bild & Diagramm` | 11=picture, 0=title, 16=body, 12=chart |
| L18 | `Inhalt - Grau` | 10=body, 0=title, 11=object |
| L19 | `2 Inhalte - Grau` | 10=body, 0=title, 11=object, 12=object |
| L20 | `Inhalt & Diagramm - Grau` | 10=body, 0=title, 11=object, 12=chart |
| L21 | `Diagramm & Inhalt - Grau` | 10=body, 0=title, 11=object, 12=chart |
| L22 | `Inhalt & Form - Grau` | 10=body, 0=title, 11=object |
| L23 | `2 Inhalte & Form - Grau` | 10=body, 0=title, 11=object, 12=object |
| L24 | `Inhalt, Diagramm & Form - Grau` | 10=body, 0=title, 11=object, 12=chart |
| L25 | `Inhalt - Gelb` | 10=body, 0=title, 11=object |
| L26 | `2 Inhalte - Gelb` | 10=body, 0=title, 11=object, 12=object |
| L27 | `Inhalt & Diagramm - Gelb` | 10=body, 0=title, 11=object, 12=chart |
| L28 | `Diagramm & Inhalt - Gelb` | 10=body, 0=title, 11=object, 12=chart |
| L29 | `Inhalt & Form - Gelb` | 10=body, 0=title, 11=object |
| L30 | `2 Inhalte & Form - Gelb` | 10=body, 0=title, 11=object, 12=object |
| L31 | `Inhalt, Diagramm & Form - Gelb` | 10=body, 0=title, 11=object, 12=chart |
| L32 | `Inhalt - Rosa` | 10=body, 0=title, 11=object |
| L33 | `2 Inhalte - Rosa` | 10=body, 0=title, 11=object, 12=object |
| L34 | `Inhalt & Diagramm - Rosa` | 10=body, 0=title, 11=object, 12=chart |
| L35 | `Diagramm & Inhalt - Rosa` | 10=body, 0=title, 11=object, 12=chart |
| L36 | `Inhalt & Bild - Rosa` | 11=picture, 0=title, 13=object |
| L37 | `Inhalt & Form - Rosa` | 10=body, 0=title, 11=object |
| L38 | `2 Inhalte & Form - Rosa` | 10=body, 0=title, 11=object, 12=object |
| L39 | `Inhalt, Diagramm & Form - Rosa` | 10=body, 0=title, 11=object, 12=chart |
| L40 | `Inhalt - Blau` | 10=body, 0=title, 11=object |
| L41 | `2 Inhalte - Blau` | 10=body, 0=title, 11=object, 12=object |
| L42 | `Inhalt & Diagramm - Blau` | 10=body, 0=title, 11=object, 12=chart |
| L43 | `Diagramm & Inhalt - Blau` | 10=body, 0=title, 11=object, 12=chart |
| L44 | `Inhalt & Form - Blau` | 10=body, 0=title, 11=object |
| L45 | `2 Inhalte & Form - Blau` | 10=body, 0=title, 11=object, 12=object |
| L46 | `Inhalt, Digramm & Form - Blau` | 10=body, 0=title, 11=object, 12=chart |
| L47 | `Inhalt, Bild & Form - Blau` | 11=picture, 0=title, 13=object |
| L48 | `Schlussfolie - Blau` | 1=subtitle, 10=body |
| L49 | `Schlussfolie - Weiß` | 1=subtitle, 10=body |

### 9.1 Agenda slots and item counts

* [GUIDE] Reading order (number tile idx, item idx): 01 (12, 13) · 02 (28, 29) · 03 (19, 16) · 04 (31, 30) ·
  05 (23, 20) · 06 (33, 32) · 07 (27, 24) · 08 (35, 34) – two columns, filled row by row, rows 0.781 in apart.
  The guide shows only the full 8-slot state (guide slide 16).
* [DERIVED] **Fewer than 8 items – no empty slot anywhere.** The number tiles are layout placeholders with their
  own light-grey fill and prompt number, so LibreOffice draws every one the slide does not fill. `s.agenda()`
  therefore moves the slide onto a per-count clone of the guide's layout (`Agenda 2` … `Agenda 7`, made on first
  use, `Agenda` itself for 8): identical XML, geometry, fills and spacing, with only the placeholders of slots
  k+1…8 deleted. Nothing of an unused slot exists, so neither PowerPoint nor LibreOffice can draw it.
* [DERIVED] **Positions stay in the guide's reading order, not rebalanced.** The guide gives one grid (two
  columns from the top row down) and no example of other counts; keeping 01 at top-left and filling row by row
  keeps every tile on the guide's grid and the numbering legible. 7 items leave the 4th row's right cell empty,
  3 items fill 01 02 / 03 – exactly as the full layout would look with the last slots omitted.
* [DERIVED] **More than 8 items – continuation slides.** The guide has no list-style agenda layout, so items are
  split over ⌈n/8⌉ Agenda slides, balanced so no page is a stub (9 → 5 + 4, 11 → 6 + 5, 16 → 8 + 8). The first
  slide is titled "Agenda", every further one "Agenda (continued)"; numbering carries on (07, 08 … 11). The
  slides follow each other directly; the dividers and the agenda-chapter match read the items across all of
  them. `d.agenda(items)` (or `s.agenda(items)` on a fresh Agenda slide) does all of this.
* [DERIVED] Lint (`agenda-numbers`): numbering continuous from 01 across agenda slides; 2–8 items per slide;
  every slot the slide's layout carries is filled (a visible empty tile fails); titles "Agenda" / "Agenda
  (continued)"; agenda slides consecutive. Two agenda slides in a row are not a layout repeat.

Common idx: 0 title · 10 subtitle on content layouts (headline on section/quote/key/closing) · 1 subtitle on
covers/closings · 11 main content (picture on section/quote layouts) · 12 second column or chart · 13 sub-line
on section/quote/key · 14–20 pills/tiles/tracker tabs.

## 10. Content mapping [DERIVED]

| Content | Layout |
|---|---|
| Deck title + date/author | `Titelfolie mit Bild` (photo with rights) else `Titelfolie ohne Bild` |
| List of topics | `Agenda` via `d.agenda(items)` – any count ≥ 2; > 8 continues on 'Agenda (continued)' (§9.1) |
| New chapter | a `Kapiteltrenner` (one family per deck; Blau carries a 2-digit number) |
| A testimonial/quote | `Zitat`/`Zizat` layouts – only for a genuine quote or statement |
| 4 steps / 4 key facts | `Key Slide 1` · 6 points → `Key Slide 2` |
| One metric + explanation | `Inhalt & Infobox` (number in idx 16) |
| Narrative bullets | `Inhalt - <bg>` (two levels) |
| Comparison / before–after / pros–cons | `2 Inhalte - <bg>` |
| Numeric series | `Inhalt & Diagramm`/`Diagramm & Inhalt`; inside a 4-part story `Inhalt & Tracker` |
| Tabular data | table on `Inhalt - Weiß` (the guide's example) |
| Photo + text | `Inhalt & Bild - Rosa` / `Inhalt, Bild & Form - Blau` |
| End | `Schlussfolie - Blau` or `- Weiß` |

One background family as the deck's base (white is the guide's content default; `Inhalt & Infobox`, `Inhalt &
Tracker`, `Bild & Diagramm` and the `Weiß` layouts all count as white); colour backgrounds for rhythm (sections,
quotes, key slides), not randomly. The lint fails content slides (`Inhalt*`, `2 Inhalte*`, `Diagramm*`, `Bild &
Diagramm`) on more than one background colour.

## 11. Deck structure [DERIVED] (cover, closing, agenda, dividers, repeats, icons and boxes are linted)

* Cover first, closing last.
* Decks > 5 slides: `Agenda` right after the cover and a `Kapiteltrenner` (one family) before each chapter; the
  divider titles match the agenda items in order, and every agenda item is a chapter. If the source caps the
  page count, the agenda wins; deck-level rules (`dividers`, `agenda`, `agenda-chapters`, `repeat`,
  `layout-reuse`, `background`) may be waived only with a written reason (`save(waive={"dividers": "…"})`).
  Waivers are stored in the deck (custom property `sgdeck_waivers`) and a `<deck>.waivers.json` sidecar, shown by
  verify_deck and reported to the user. Content rules (capacity, colours, charts, tables, fonts) cannot be waived.
* No two identical layouts in a row (tracker sequences excepted); each layout at most max(2, ⌈2n/12⌉) times in an
  n-slide deck; section dividers do not count (one per chapter is required).
* One slide per agenda chapter at least; never merge two chapters onto one slide.
* Body placeholders: at most ONE lead line, only as the first paragraph; no bold/heading-font mini-headings inside a
  placeholder (sgdeck raises). Second topic → second column, info box (idx 15/16/17) or another slide. L1 bullets for
  every list item; lead lines and info-box text carry no bullet; no single-item lists.
* Key Slide pills/tiles: one phrase each, no heading + text (sgdeck raises).
* Headline/sub-line placeholders the guide shows filled (idx 10/13 on key, quote, section; 12 on Blau section;
  agenda title) are never deleted – fill them (sgdeck raises).
* Never invent facts or numbers.
* **Short pitch** [DERIVED]: decks of ≤ 10 slides may skip the agenda and dividers with
  `d.save(out, short_pitch=True)`. The mode is stored (custom property `sgdeck_mode`), the skipped rules print as
  `~ SHORT-PITCH` notes (not failures) and must be reported; > 10 slides in short-pitch mode fails.

## 12. Text capacity and density

* [GUIDE] Capacity is **measured**, not guessed: `reference/capacity.md` lists, for every text placeholder of
  every layout, characters per line, lines, one-line bullet paragraphs, max characters and max words at the
  guide's size, face, line spacing (100 %), space after (3 pt), insets and bullet indent. Line height
  (1.212 × size) is measured from the guide's own grow-to-fit placeholders.
* [DERIVED] Widths use Outfit metrics as a proxy for Mark Pro (not licensed) with a 10 % headroom (`capacity.HEADROOM`)
  margin. The sgdeck lint (`capacity:<slide>`) and `scripts/verify_deck.py` word-wrap the real text and fail
  any placeholder that would overflow; table cells may take one line (§5) and the table must fit the content area.
* [GUIDE] Grow-to-fit placeholders (titles, subtitles, headlines) may grow only until the next element below; that
  room is what the table reports.
* Key limits (measured, see the table for all layouts):

| Placeholder | Measured capacity |
|---|---|
| Slide title (18 pt) | 1 line, ~71 chars |
| Slide subtitle (12 pt) | 2 lines × ~107 chars (aim for 1) |
| Full-width body (14 pt) | 16 lines × ~90 chars; 14 one-line bullets |
| Half-width body / column (14 pt) | 16 lines × ~42 chars; 14 one-line bullets |
| Cover title (48 pt) | 2 lines × ~26 chars |
| Agenda item (18 pt) | 1 line, ~17 chars |
| Section title (36 pt, Blau) | 3 lines × ~19 chars |
| Quote (20 pt, Rosa) | 2 lines × ~34 chars |
| Key Slide 1 headline / pill | 1 line × ~35 chars / 2 lines × ~19 chars |
| Key Slide 2 headline / tile | 2 lines × ~20 chars / 8 lines × ~19 chars |
| Info-box number / heading / text | 2 × ~17 / 3 × ~40 / 7 × ~40 chars |
| Closing headline (48 pt) | 1 line, ~26 chars |
| Cover / closing subtitle (14 pt) | 1–2 lines (lint fails 3+) |

* [DERIVED] Capacity is the ceiling, not the target: keep bullets to one or two lines, keep key pills/tiles to
  one short phrase, use one subtitle line.

## 13. Footer and think-cell object

* [GUIDE] Slide number, copyright line and amasol logo come from the master. The classification "Internal" is a
  footer placeholder on every slide except the covers (`add()` copies it).
* [GUIDE] Every content slide carries the hidden "think-cell data – do not delete" object (`add()` adds it).
  The guide's own cover, divider, quote, key and closing samples carry none; `add()` adds it everywhere, which is
  harmless (hidden) and never removed.

## 14. Do's and don'ts stated in the guide [GUIDE]

* Work only in text placeholders or formatted text boxes from the master, not plain inserted text boxes, so
  bullets/indents stay correct; indent only via list levels.
* Reuse placeholders from the master ("Titel und Inhalt" layout) when a text box is needed.
* Keep content inside the content area.
* Set footer/classification via Insert → Header & Footer, do not type it.
* Lines only in the listed weights and colours. Text boxes only as Fläche or Rahmen.
* Never use transparency, tints/shades or Office standard colours.
* Do not delete the hidden think-cell object.

## 15. Glossary

| Term | Meaning |
|---|---|
| Agenda | layout with a red title panel and up to 8 numbered items (`Agenda k` = build-time clone with k slots) |
| Blau / Gelb / Grau / Rosa / Weiß | layout background families: mint, cream, light grey, pink, white |
| Bild / Diagramm / Inhalt / Inhalte | picture / chart / content / contents (two columns) |
| EMU | English Metric Unit; 914 400 EMU = 1 in, 12 700 EMU = 1 pt |
| Fläche / Rahmen | the guide's two text-box styles: solid red fill / 1 pt blue outline |
| Form | decorative vertical pill bleeding off the slide edge (`… & Form` layouts) |
| Grow-to-fit | placeholder that expands with its text (`spAutoFit`) |
| idx | placeholder index used by `s.text(idx, …)` |
| Placeholder | a layout's text, picture or chart frame, addressed by idx; the only place copy goes (never call it "box" or "field") |
| Slot | one agenda item = its number-tile placeholder plus its text placeholder |
| Text box | a free shape drawn by `s.info_box()` (Fläche / Rahmen); not a placeholder |
| Headroom | the 10 % width margin every capacity limit keeps (`capacity.HEADROOM`) |
| Infographic | a slide whose main visual is a diagram with a shape: donut, pie, wheel, staircase, tiers, process (§17) |
| Main visual | the one diagram, chart, table or picture a content slide is built around (§17.2) |
| plan.json | the infographic planner's output: one entry per content slide (§17.5, `reference/infographic-planner.md`) |
| Short pitch | ≤ 10-slide deck built without agenda/dividers, recorded in the deck (§11) |
| Infobox | grey panel with heading (idx 15), big red number (idx 16), text (idx 17) |
| Kapiteltrenner | section divider |
| Key Slide 1 / 2 | key-message layouts with 4 pills / 6 tiles |
| Lead line | first paragraph of a placeholder in bold Mark Pro, no bullet (`lead()`) |
| `+mj-lt` / `+mn-lt` | theme major (Mark Pro) / minor (Mark Pro Light) font slots |
| Outfit | free preview font standing in for the unlicensed Mark Pro |
| Schlussfolie | closing slide |
| think-cell object | hidden data object on every guide slide; must stay |
| Titelfolie mit / ohne Bild | cover with / without photo |
| Tracker | four right-edge progress tabs on `Inhalt & Tracker` |
| Waiver | written reason for skipping a deck-level rule; stored in the deck and reported (§11) |
| Zitat / Zizat | quote layouts (`Zizat` is the guide's own spelling) |
| [GUIDE] / [DERIVED] | rule stated or measured in the guide / rule inferred by us |

## 16. Verification and packaging [DERIVED]

`python3 scripts/verify_deck.py deck.pptx [--plan plan.json] [--strict]` exits 1 on any failure. It runs 23 checks, against the guide's tokens and the
template baseline: amasol branding intact (logo + copyright on master, no foreign branding in branding positions) · no embedded fonts · fonts (two theme faces, no italic/underline/tracking) ·
type-scale sizes · palette colours · layouts/master (no values added beyond the template, copyright
fit) · the full sgdeck lint grouped as structure, agenda numbering, background family, slide content, capacity,
tables, charts · no template prompt or dummy text anywhere · metadata clean · schema and unique shape ids (plus `office validate` when on PATH) · waivers
(deck-level keys only, each with a reason; waived findings print as `~ WAIVED`) · visuals (§17.3, cap and
consecutive rule) · icon tiles match their container (§7) · logos legible, in tiles, no overlaps (§8.1) · plan (§17.5) · no invented numbers · content coverage. Without a plan (`--plan`, or `plan.json` /
`<deck>.plan.json` next to the deck) the last three print SKIP. The summary is always out of 23 and ends with
`RESULT: PASS` or `RESULT: FAIL`; read that line, not the counts. `--strict` turns any SKIP into a FAIL.

Optional package step, only where the `office` CLI exists: `office validate --repair`, `office pptx clean`,
`office pptx check-overlap`, then verify again. `office pptx check-fonts` reports Mark Pro missing wherever it is
not licensed – expected (licensing, §2). Without `office`, `verify_deck.py`'s built-in schema check is enough.

Preview: `python3 scripts/render_deck.py deck.pptx render/` sets the font config as an absolute path itself
(a relative `FONTCONFIG_FILE` is ignored silently) and warns if Mark Pro does not map to Outfit; it uses `office`
if present, else LibreOffice + pdftoppm. LibreOffice draws a
layout's filled placeholders (key pills/tiles, section number square) even when the slide removed them;
PowerPoint does not. Agenda slots are exempt – the per-count layouts (§9.1) leave nothing to draw.

## 17. Infographics and diagrams [DERIVED]

The guide shows no diagram slides; these rules build diagrams only from what it does show (panels, pills, tiles,
Fläche/Rahmen boxes, icons, 3 pt arrows). Signatures and pictures: `reference/diagrams.md`.

### 17.1 Builders and styling
`s.process`, `s.staircase`, `s.tiers`, `s.wheel`, `s.tile_grid` (with `logos=`: `s.logo_grid`, §8.1),
`s.fact_chips`, `s.band`, `s.story_panel`, `s.donut` and, for dividers, `s.chapter_panel`. All of them:
* guide palette only, as solid theme colours (no transparency, tints or shades); Mark Pro theme fonts;
* light-grey panels on white layouts (never on Grau); red Fläche or 1 pt blue Rahmen boxes; key pills in the
  Key Slide 1 fill order; arrows and connectors blue;
* guide radii (info-box panel 0.188 in, icon tile 0.121 in) and gutters (Key Slide 2 tile gap 0.119 in);
* type scale only: labels 12 pt, 10 pt where 12 pt does not fit (the builder picks; below 10 pt it raises),
  headings 14/12 pt, values 32/24 pt red;
* guide monoline icons on white tiles shaped like their container (§7: circle in pills, rounded square
  elsewhere; `tile_shape=` overrides), one icon size per diagram;
* inside the content area (x 0.432–9.567 in, y 1.198–5.096 in), in a region: `full`, `left`, `right`,
  `text`, `visual`. Text that would not fit raises `GuideError` – shorten or split, never shrink.
* each builder is one named group (`sgdeck diagram: <type>`), so verify can find it.

### 17.2 Middle ground
* Infographics only where the content has a shape: parts of a whole, a cycle, levels, layers, steps.
  Structured visuals (tile grid, fact chips, band, story panel, chart, table) for groups, key numbers,
  goal-approach-result and stories; text-led slides for arguments, quotes, single statements.
* At most ⌊n/3⌋ (min. 1) infographic slides for n content slides; never two infographic slides in a row
  (a divider or another slide between them is fine); one main visual per slide.
* Over the cap: the planner cuts the weakest shapes and records each cut with its reason (`plan.json → cut`).
  Calibration: the client's six finished amasol slides = 2 infographics, 2 structured, 2 text-led.

### 17.3 A visual on every content slide
Every content slide (layouts `Inhalt…`, `2 Inhalte…`, `Bild & Diagramm…`, `Diagramm & Inhalt…`; Key Slide and
Zitat layouts are their own visual) has at least one of: icon, diagram,
chart, table, picture, info box / big number. Lint finding `visual:i` fails a slide with none, with more than
one main visual, or with a diagram outside the content area.
Text-only slides must not look sparse: a lone corner icon next to short text fails the sparse lint - use
`s.icon_set()` (one icon per point), a key number in `Inhalt & Infobox`, or an info box plus icon. Icon tiles
follow their container; chart series run red, blue, warm grey, olive.

### 17.4a Layout matching
The layout of every content slide comes from `match.json` (`scripts/matcher.py`, template bank
`reference/template-bank.json`); verify fails a slide whose layout or visual differs from it.

### 17.4 Dividers
The empty picture panel of `Kapiteltrenner - Blau` takes `s.chapter_panel(icon, value=, text=)`: a hero guide
icon plus ONE key fact or line from that chapter's source (red 32 pt value + 14 pt line, or the line alone).
Never a fact that is not in the source; use `picture()` instead when the user supplies a photo.

### 17.5 Plan and verify
* Raw drafts go through the infographic planner first (`reference/infographic-planner.md`): `plan.json` with one
  entry per content slide – visual, the exact source data quoted from the draft, a one-line reason – plus
  `cut`, `no_chart` and `excluded`. `python3 scripts/planlib.py check plan.json` validates it.
* No chart where the data does not support one: names are not quantities; open bounds ("200+") are not totals;
  no shares that the source does not state. Interpretive lines not backed by the source go to `excluded`.
* The build passes the ids: `d.add(layout, plan="p03")` and `s.process(..., plan="p03")`.
* verify `plan`: every planned visual is on its slide, chart categories and values equal the plan data, no unknown
  ids, excluded lines absent. verify `no invented numbers`: every number on the slides (structural agenda,
  divider and step numbers excepted) occurs in the source draft.

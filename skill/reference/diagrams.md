# Diagram builders (sgdeck v8)

All builders are `Slide` methods, draw ONE named group (`sgdeck diagram: <type> [plan id]`) inside the content
area and follow RULES §17.1 (palette, theme fonts, type scale, radii, monoline icons on white tiles shaped like their container). They
raise `GuideError` with the fix when text does not fit, an icon name is unknown or a count is out of range.
Previews: `reference/diagram-gallery/slide-NN.jpg` (built by `evals/diagram_gallery.py`).

## Contents
1. Regions and common arguments
2. Infographics: process, staircase, tiers, wheel, donut / pie
3. Structured: tile_grid, logo_grid, fact_chips, band, story_panel
4. Dividers: chapter_panel
5. Icons on text-led slides
6. Which layout hosts a visual

## 1. Regions and common arguments
`region=` takes `"full"` (whole content area, x 0.432–9.567, y 1.198–5.096 in), `"left"` / `"right"` (halves
with one gutter), `"text"` / `"visual"` (≈ 57 / 43 % split for text beside a visual) or an `(x, y, w, h)` tuple in
inches that must lie inside the content area. `plan="p03"` tags the group with the plan id (also pass it to
`d.add(layout, plan="p03")`). Item tuples may also be dicts with the same keys. Use white layouts – panels are
light grey and vanish on `… - Grau`.

`tile_shape="auto"` (every builder, `icon()`, `icon_row()`): the white icon tile is a circle when its container
is a pill, stadium, oval or circle (ellipse, or roundRect radius ≥ half the short side) and a rounded square
otherwise (RULES §7). `"rounded"` / `"circle"` force a shape; lint `icon-tile` fails a mismatch. `s.tiers`
therefore draws circles in its pills and rounded squares in its side panels.

## 2. Infographics (count towards the cap, RULES §17.2)
| Builder | Content shape | Data | Gallery |
|---|---|---|---|
| `s.process(steps, region="full", numbered=True, valign="middle")` | sequential steps | `[(title, text, icon)]`, 2–6; text may be `""` | slide 3 |
| `s.staircase(levels, region="full", axis=None, highlight_new=True)` | maturity levels | `[{"label", "name", "items": [(text, icon)]}]` items bottom to top; `axis=("Reactive", "Proactive")` | slide 4 |
| `s.tiers(tiers, links=None, note=None, region="full")` | layers | `[{"name", "sub", "number", "icon", "side": (title, text, icon)}]`, 2–4, top first; `links[k]` = labels between tier k and k+1 | slide 5 |
| `s.wheel(items, center=None, region="full")` | repeating cycle | `[(label, icon)]`, 3–6, clockwise from the top | slide 6 |
| `s.donut(categories, values, region="visual", pie=False)` | parts of one whole | 2–4 categories, numbers from the source; unit in the subtitle | slide 11 |

Staircase colours: red Fläche = item new at this level (from level 2), blue Rahmen = carried over; level 1 is
the baseline. `highlight_new=False` draws every box as Rahmen (use it when "new" would be an interpretation).

## 3. Structured visuals (no cap)
| Builder | Content shape | Data | Gallery |
|---|---|---|---|
| `s.tile_grid(groups, cols=3, region="full")` | groups of names | `[(title, [names], icon)]` – names exactly as given | slide 7 |
| `s.logo_grid(groups, logos, cols=3, region="full", chips="auto")` = `s.tile_grid(..., logos=)` | groups of companies with logos | `logos={name: png path}`; names without a file stay text | slide 12 |
| `s.fact_chips(facts, region="full", valign="top", stack=False)` | 2–5 key numbers | `[(value, label, icon)]`; `stack=True` for a column (`region="right"`) | slide 8 |
| `s.band(goal, approach, result, heads=("Goal", "Approach", "Result"), icons=(…), valign="middle")` | goal → approach → result | each part a str or list of str | slide 9 |
| `s.story_panel(fields, picture=None, icon=None, caption=None)` | case story | `[(label, text)]`; `picture=` only the user's own photo | slide 10 |

Logo grid (RULES §8.1): logos only from the user or official sources, transparent PNG trimmed to the ink. One
size for the whole slide (height = clamp(s/√aspect, 0.45 s, 0.8 s), aspect kept), rows balanced and justified,
padding all round, no overlaps; the block is centred in each tile under the heading. A logo below 3:1 contrast
on the tile goes on a rounded chip – white, blue, black, first that passes (`chips="none"` raises instead).
Logos are named `sgdeck logo: <name>` with alt text; `s.logo_report` lists `(name, "logo"|"text", chip)`.
It raises if the logos would get smaller than 0.15 in – split the groups over two slides.

Charts (`s.chart`), tables (`s.table`) and the info box (`Inhalt & Infobox`) remain the guide's own structured
visuals (RULES §5, §6, §9).

## 4. Dividers
`s.chapter_panel(icon, value=None, text=None, idx=11)` on `Kapiteltrenner - Blau` (tested there; other divider
families need a picture placeholder at `idx`): hero icon (1.5 × the icon tile) plus one fact from the chapter's source – `value` in red 32 pt
with `text` under it, or `text` alone. The section number square (idx 12) stays on top. A fully round panel
(circle) insets the content to its inscribed square and uses a circle tile. Gallery slide 2.

## 5. Icons on text-led slides
`s.icon_set([(text, icon), ...], plan=pid)` (2–5 points, ≤ 160 chars each) is the default for a text-only list:
one light-grey row per point with its icon tile, filling the content area. A lone corner icon on a text-only
slide fails the sparse lint – use icon_set, a key number (`Inhalt & Infobox`) or an info box plus icon.
`s.icon(name, at="corner", tile=True, tile_shape="auto")` puts one tile bottom right of the content area; it raises if body text,
a table or a chart reaches that spot (move the icon or shorten). `at="infobox"` places it in the info box.
Every content slide needs one visual (RULES §17.3).

## 6. Which layout hosts a visual
The matcher picks the layout (`match.json`); this table is for reading its choice or writing a `custom` slide.

| Visual | Layout |
|---|---|
| full-width diagram (process, staircase, tiers, wheel, band, tile grid, chips) | `Inhalt - Weiß`, `Inhalt & Form - Weiß`, `2 Inhalte & Form - Weiß` (placeholders not used are removed) |
| text beside a visual (donut, stacked chips) | `2 Inhalte - Weiß` with `region="right"` / `"visual"` |
| story | `2 Inhalte - Weiß` or `Inhalt - Weiß` |
| key number | `Inhalt & Infobox` (guide info box) |
The matcher enforces variety: no two identical in a row, each at most max(2, ⌈2n/12⌉) times (RULES §11).

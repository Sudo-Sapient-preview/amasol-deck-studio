# Infographic planner (workflow step 1)

Turns a raw draft into `plan.json`: one entry per content slide with its main visual, the exact draft lines it uses
and a one-line reason. The build follows the plan; `verify_deck.py --plan plan.json` checks the deck against it.

## Contents
1. How to run it
2. Procedure
3. Shape → visual mapping
4. Middle-ground rules (how much infographic)
5. No invention
6. plan.json schema
7. Icon hints
8. Validate

## 1. How to run it
* **With a subagent/Task tool**: start one planning subagent. Give it only: this file, the draft path, the output
  path (`<deck folder>/plan.json`). Ask it to follow §2–§8 and to return the plan path plus the `planlib.py check`
  output. It does not build slides.
* **Without one**: the main agent runs §2–§8 itself, inline, before matching layouts (step 2).
* Either way the plan is written *before* any slide is built, and the builder may not add visuals it does not list.

## 2. Procedure
1. Read the whole draft. Split it into content units in source order. Where a brief and a finished version cover
   the same slide, merge them into one unit (brief headline as title, finished content as body).
2. Group units into chapters (these become the agenda items and dividers). Record each unit's `chapter`.
3. For each unit decide whether the content **has a shape** (§3). If it does, pick that visual; if not, it is
   text-led (narrative, arguments, quotes) and gets an accent: `icon`, `info_box`, `big_number`, `key_slide` or `quote`.
4. Apply the middle-ground rules (§4): count, cap, cut the weakest, no two infographics in a row.
5. Quote the exact draft lines each slide uses (§5). List lines you deliberately leave out under `excluded`.
6. Write `plan.json` (§6) and validate it (§8). Fix and re-run until it prints `PASS plan.json`.

## 3. Shape → visual mapping
| Content shape in the draft | `visual` | class | Builder |
|---|---|---|---|
| Parts of one whole, with numbers that add up (shares, splits) | `donut` (or `pie`) | infographic | `s.donut()` – native chart |
| A repeating cycle (stages that loop back) | `wheel` | infographic | `s.wheel()` |
| Levels / maturity / stages that build on each other | `staircase` | infographic | `s.staircase(axis=…)` |
| Layers stacked on each other, with flows between them | `tiers` | infographic | `s.tiers(links=…)` |
| Sequential steps (do A, then B, then C) | `process` | infographic | `s.process()` |
| Groups of names or categories (customers by sector, partners) | `tile_grid` | structured | `s.tile_grid()` |
| 2–5 key numbers or facts | `fact_chips` (or `big_number` for one) | structured | `s.fact_chips()` / `Inhalt & Infobox` |
| Goal → approach → result; context → role → outcome | `band` | structured | `s.band(heads=…)` |
| A case story with labelled fields (company, challenge, solution) | `story_panel` | structured | `s.story_panel()` |
| A numeric series over categories/time | `chart` | structured | `s.chart()` |
| Tabular data | `table` | structured | `s.table()` – the table is the visual; corner icon optional |
| Narrative, arguments, lists without a shape | `icon` / `info_box` / `big_number` | text-led | `s.icon_set()` (one icon per point) or `Inhalt & Infobox` key number – the matcher settles `icon` into `icon_set` / `big_number`; never a lone corner icon on a text-only slide |
| 4 or 6 short key points | `key_slide` | text-led | `Key Slide 1` / `Key Slide 2` |
| A genuine quote | `quote` | text-led | `Zitat` layouts |

`icon` = a guide icon/tile on the slide; `info_box` = a drawn `s.info_box()` text box; the guide's `Inhalt & Infobox`
panel with its red number is `big_number`. Builder signatures and previews: `reference/diagrams.md`.

Pick the visual the **data** supports, not the one that looks best. A list of names is never a chart; a count
you would have to make up (e.g. "customers per sector" from a logo selection) is not data.

## 4. Middle-ground rules
Calibrated on a finished client deck: of 6 content slides, 2 were true infographics (a staircase, stacked tiers),
2 structured visuals (a category tile grid, a story with picture) and 2 text-led with icons/panels; none plain text.
* An infographic only where the content has a shape (§3). Narrative, arguments and quotes stay text.
* **Cap**: at most ⌊n/3⌋ infographics for n content slides (minimum 1) – `sgdeck.infographic_cap(n)`.
  Content slides = every entry in `slides` (cover, agenda, dividers and closing are not listed).
* Never two infographics in consecutive slides of the same chapter (the deck lint also fails two adjacent
  infographic slides; a divider between them is fine).
* One main visual per slide.
* Every non-infographic content slide still gets an accent: icon, info box, key number, chart or picture.
* Over the cap: keep the infographics whose shape is clearest and whose data is richest; turn the weakest into
  text-led slides and record each under `cut` with the reason.

## 5. No invention
* `source_quotes` are copied **verbatim** from the draft (whitespace and typographic quotes may differ).
* Every number in `data` must occur in that slide's quotes; chart `values` are the draft's numbers, unchanged.
* Never derive new facts: no counts of logos, no totals the draft does not state, no claims like "each level adds…"
  unless the draft says it and the user agrees. Interpretive lines that are not in the finished material go under
  `excluded` with a reason, and the build leaves them out.
* If the data does not support a chart, do not make one – record it under `no_chart` with the reason.
* A chart has one scale: series whose values differ by more than 10× (e.g. revenue ~44 and cash flow ~2, in the
  same unit) fail the build (`chart` lint, RULES §6). Chart the comparable measures and keep the other in the text.
* `data` is needed only where verify compares numbers: chart, donut, pie (`categories` + `values`), table (`rows`),
  fact_chips and big_number (the figures). Text-led and diagram visuals may leave it out.
* `data.values` is the chart's **first** series (verify compares it); further series may go under
  `data.series` (`{"name": [values]}`) for the record – they are not checked, and SPEC carries the full series.

## 6. plan.json schema
```json
{
  "schema": "sgdeck-plan/1",
  "source": "raw-draft.md",
  "deck": "short deck name",
  "short_pitch": false,
  "infographic_cap": 3,
  "chapters": ["About", "Customers"],
  "slides": [
    {"id": "p01", "chapter": "About", "source_ref": "Slide 3 – Profile",
     "title": "Working title (claim) from the draft",
     "visual": "fact_chips", "class": "structured",
     "data": {"facts": [["100+", "employees"]]},
     "source_quotes": ["> 100 employees"],
     "reason": "three key numbers -> fact chips"}
  ],
  "cut": [{"id": "p05", "wanted": "process", "now": "icon", "reason": "over cap; weakest shape"}],
  "no_chart": [{"source_ref": "Slide 5", "reason": "names only, no quantities"}],
  "excluded": [{"quote": "exact draft line", "reason": "interpretive, not in the finished slide"}]
}
```
| Field | Rule |
|---|---|
| `id` | unique; the build passes it as `d.add(layout, plan=id)` and builder `plan=id` |
| `visual` / `class` | from §3; `class` must match the visual |
| `data` | what the builder draws; for `donut`/`pie`/`chart`: `categories` + `values` (numbers) |
| `source_quotes` | ≥ 1 verbatim draft line per slide |
| `reason` | one line, ≤ 200 characters |
| `chapter` | the agenda item the slide belongs to (enables the consecutive rule across dividers) |
| `short_pitch` | true for decks ≤ 10 slides built without agenda/dividers (`d.save(short_pitch=True)`); for a page cap keep the agenda and use `waive` instead |
| `waive` | optional `{"dividers": "written reason"}` (deck-level rules only, RULES §11); the matcher and matchbuild read it |
| `chapters` | the agenda items, in order; may be finer than the draft sections (one page per agenda item) |

## 7. Icon hints
Pick from `assets/icons/index.json` (106 guide icons; sheet `_icon-sheet.png`). If none fits, use none.
servers/infrastructure `server-stack` · health/pulse `monitor-pulse` · alerts `alert-circle`, `bell` ·
performance `dashboard-analytics` · logs/documents `document` · business process/KPIs `bar-chart` ·
teams `team`, `users` · network/CoE `network-gear`, `hierarchy-gear` · operations `gear` · learning `lightbulb` ·
standards `checklist` · goal `target` · approach `workflow` · result `trophy` · security `shield-check` ·
locations `location-pin` · experience/awards `award` · cloud `cloud-network` · search/review `document-search`.

## 8. Validate
`python3 scripts/planlib.py check plan.json` – schema, vocabulary, verbatim quotes, numbers only from quotes,
cap, consecutive rule, excluded lines. Exit 1 on any problem. After the build,
`python3 scripts/verify_deck.py deck.pptx --plan plan.json` re-checks the deck against the same plan.

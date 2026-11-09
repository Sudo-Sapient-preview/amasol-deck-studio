# Step 3 – Build with `matchbuild`

There is one build route: `matchbuild.build()` turns `draft.md` + `plan.json` + `match.json` + a small SPEC into
the deck. The layout and visual of every slide come from `match.json`; text comes from the draft. Copy
`scripts/example_build.py`, which runs the whole chain on a sample and passes `verify_deck.py --strict`.

```python
import sys; sys.path.insert(0, "<skill>/scripts")
from matchbuild import build
from sgdeck import lead
SPEC = {
  "dividers": {"Adoption": ("users", "One chapter line")},   # one per chapter (none in short-pitch decks)
  "p01": {"args": {"categories": ["Jul", "Aug"], "series": {"Teams (k)": [2.4, 3.6]}},   # chart
          "body": [lead("What drove the jump"), "Point", "Point"]},                     # text beside it
  "p02": {"kind": "service", "icon": "calendar", "box_title": "Typical timeline",       # big_number
          "box_label": "From kickoff to live"},
  "p03": {"args": {"rows": [["Plan", "2025"], ["Team", "199"]]}, "corner_icon": "dollar"},   # table
  "p04": {"args": {"steps": [("Book a slot", "", "calendar"), ("Join the beta", "", "rating-thumbs-up")]}},
  "p05": {"icons": ["monitor-pulse", "layers", "alert-circle"]},                        # icon_set: one per point
}
build("WORK/draft.md", "WORK/plan.json", "WORK/match.json", SPEC, "WORK/out.pptx")
```

SPEC holds only what the draft cannot say. The full key list is in the `scripts/matchbuild.py` docstring:
`args` (the visual builder's kwargs), `icons`, `texts`, `icon`, `box_title`, `box_label`, `body`, `body_idx`, `kind`,
`corner_icon`, `tracker`, `photo`, `quote_lines`, `closing_title`, `closing_subtitle`, `note_prefix`, `waive`, and
`custom`.

* **Page cap**: keep the agenda and waive the dividers in `plan.json`: `"waive": {"dividers": "written reason"}`
  (RULES §11: the agenda wins). The matcher then places no divider slides and checks layout repeats without them;
  matchbuild passes the waiver to `d.save()`. Waivers are deck-level only; verify shows them as `~ WAIVED` and the
  hand-off must report them. (SPEC `"waive"` still works but plan.json is the place: the matcher reads it.)
* **Short pitch** (`plan.json` `"short_pitch": true`) is for short decks of 10 slides or fewer that need no
  agenda and no dividers at all; the deck is saved with `short_pitch=True`.
* **Chapters**: the agenda items are `plan.json` `chapters`. They may be finer than the draft's sections, e.g. a
  board pack with one page per agenda item uses 3 draft sections (each needs 2+ slides) and 6 plan chapters.
* **A visual SPEC can't express**: give that slide `"custom": fn(s, draft_slide, match_entry)` and draw it with
  the `sgdeck` calls below. The layout still comes from `match.json`; do not hand-build whole decks.
* **Lint errors** from `d.save()` (a `GuideError`) are fixed by changing content or structure: shorten or split
  in `draft.md`, then rerun the matcher and the build. The matcher measures text exactly as the lint does, so most
  overflow already shows up at step 2.
* **Table slides** carry only the table; draft points do not go beside it. Put highlights in a `custom` slide
  (table + `s.info_box(..., kind="frame")`) or on their own slide. Size an info box to its text - nothing checks
  for a half-empty box, so look at the render.
* **Corner icons** need free space: on a table that fills the content area (about 7+ rows) `corner_icon` raises -
  leave it off.
* The "Embedded fonts removed" warning on save is expected: the template's licensed fonts are stripped.

## Builders for `args` and `custom`
Diagram builders, their data shapes and gallery previews: `reference/diagrams.md`. Other slide calls:

| Call | Notes |
|---|---|
| `s.title(t)`, `s.subtitle(t)`, `s.text(idx, t)` | Titles are claims; units go in the subtitle |
| `s.body(idx, [lead("Lead line"), "Bullet", ("Sub bullet", 1)])` | `lead` (bold Mark Pro) only as the first paragraph |
| `s.chart(idx, categories, series)` | One scale; unit in the subtitle (RULES §6) |
| `s.table(rows, total_row=False, col_w=(…))` | Cells on one line, at most 9 rows (RULES §5) |
| `s.donut(cats, values)`, `s.tracker(n)`, `s.info_box(...)` | |
| `s.icon(name, at="infobox"\|"corner", tile=True)` | Icons from `assets/icons/index.json` |
| `s.icon_set([(text, icon), ...])` | Text-led lists; never a lone corner icon on a text-only slide |
| `s.quote(head, lines, photo=None)` | Zitat layouts; no photo removes the empty frame |
| `s.picture(idx, path)` | Photos only via RULES §8.2 (`scripts/photos.py`) |
| `s.logo_grid(groups, logos={name: png})` | Logos only from the user or official sources (RULES §8.1) |
| `s.chapter_panel(icon, value=None, text=None)` | Dividers (`Kapiteltrenner - Blau`) |
| `s.remove_empty()` | Always last per slide (matchbuild does this) |

Photo order (RULES §8.2): the user's image → a generated illustration if the content needs a picture (not built
yet) → Openverse CC0 (`python3 scripts/photos.py "query" --cache WORK/photos`) → a layout without a picture.
Never people or brands; CC BY stays off. **Open every stock pick before using it** and reject people, faces and
brand names/logos – the picker's text filter cannot see the image. Approved photos go to the matcher as
`--photos photos-map.json` (`{plan id: path}`) and into SPEC as `"photo"`.

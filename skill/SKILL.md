---
name: amasol-deck
description: >-
  Builds amasol PowerPoint decks (.pptx, with PDF preview) from any input - notes, documents, outlines, data, a
  PDF or URL, or a one-line ask - in the exact look of the amasol Style Guide 2025: its template and 50 layouts
  (Titelfolie, Agenda, Kapiteltrenner, Inhalt, Key Slide, Zitat, Schlussfolie), red/blue/grey/olive palette,
  Mark Pro type, icons, tables, charts and diagrams, keeping amasol's own branding. Plans one visual per slide,
  matches layouts, fits copy to measured capacity, and proves the deck with a 23-check verify. Also audits an
  existing deck against the guide. Use whenever someone asks for an amasol presentation, deck, slides, pitch or
  board pack, or slides "in our style", "on our template" or "in the style guide".
---
# amasol deck

Builds decks that look exactly like the amasol style guide, follow only its rules, and keep the amasol branding.
Paths are relative to this skill's folder. Work in a `WORK/` folder outside it; nothing is written into the skill.

## Setup
Run `bash scripts/setup.sh` once: it creates the skill's own `.venv` (python-pptx, lxml, Pillow, numpy) and
installs the Outfit preview font. **Below, `python3` means `<this skill>/.venv/bin/python`.** Previews also need
LibreOffice (`soffice`) and poppler (`pdftoppm`). Always build from `template.pptx` through `scripts/matchbuild.py` -
never a library template or PptxGenJS, even if another slides skill also triggers.

## Non-negotiables (details in RULES.md)
* Keep the amasol branding: logo on covers, sections and footer, "© amasol", closing-slide links, amasol metadata.
  Never re-brand to another company; `d.save()` fails on foreign branding in the master, layouts, metadata author
  or a © line (§8). Naming a client in slide text is content, not branding, and is fine. If the input asks for
  another brand or copyright line, keep amasol's and say so at the top of the hand-off.
* Never embed Mark Pro; keep the font names; previews use Outfit (§2).
* Only the 50 layouts, the theme fonts, the guide palette and type scale (§2, §3, §9).
* Copy fits the measured capacity; fix overflow by shortening or splitting, never by shrinking type (§12).
* One agenda, one divider per agenda item, one background family for content slides (§9–11). Decks of 10 slides
  or fewer may use short-pitch mode instead.
* One main visual per content slide; infographics only where the content has a shape, at most a third of content
  slides, never two in a row (§17).
* Charts state their unit and use one scale; table cells stay on one line (§5–6).
* Company logos only from the user or official sources, never recoloured or redrawn (§8.1).
* Never invent facts or numbers. Shorten, split or rephrase only; unbacked lines go to `plan.json → excluded`.
* Waive only deck-level rules, each with a written reason. Waivers and short-pitch mode are always reported.

## Workflow
Copy this checklist and tick it off. Each step stops until its check passes.
```
- [ ] 0 Intake     input -> WORK/draft.md            draft_check.py PASS
- [ ] 1 Plan       draft.md -> WORK/plan.json        planlib.py check PASS
- [ ] 2 Match      draft + plan -> WORK/match.json   matcher.py exit 0
- [ ] 3 Build      draft + plan + match + SPEC       d.save() lint passes
- [ ] 4 Verify     out.pptx                          verify_deck.py --strict: RESULT: PASS
- [ ] 5 Render     contact sheet + slides            compared with the guide, fixed once
- [ ] 6 Hand-off   report
```
0. **Intake** – follow `reference/intake.md`. Classify with `scripts/intake.py`, draft with `scripts/draftgen.py`,
   then `python3 scripts/draft_check.py WORK/draft.md --autofix` until PASS. From here on draft.md is the only source.
1. **Plan visuals** – follow `reference/infographic-planner.md`. With a subagent tool, give one planning subagent
   that file, the draft path and the output path; otherwise run it inline. Then
   `python3 scripts/planlib.py check WORK/plan.json` until PASS. Page cap: keep the agenda and waive the dividers
   in plan.json (`"waive": {"dividers": "the reason"}`, RULES §11). Short pitch (`"short_pitch": true`, no agenda
   and no dividers) when the user asks for a short deck or pitch and it stays at 10 slides or fewer; otherwise keep
   both.
2. **Match layouts** – `python3 scripts/matcher.py WORK/draft.md WORK/plan.json`. Read its one line per slide as
   the storyboard. It measures text exactly as the build lint does. Exit 1 means a slide fits no layout: shorten
   or split it in draft.md (or fix the plan) and rerun. Fix any WARN line too, or plan the SPEC override it names.
3. **Build** – follow `reference/build.md`: copy `scripts/example_build.py`, write the SPEC (icons, chart series,
   table rows, diagram parts) and call `matchbuild.build()`. A lint error means changing content, then repeating
   from step 2.
4. **Verify** – `python3 scripts/verify_deck.py WORK/out.pptx --plan WORK/plan.json --strict` until the last line is
   `RESULT: PASS`. Details and the optional `office` package checks: `reference/review.md`.
5. **Render and review** – `python3 scripts/render_deck.py WORK/out.pptx WORK/render/` into an empty folder, then
   the per-slide review in `reference/review.md`.
6. **Hand-off** – report as listed in `reference/handoff.md`.

## What to read when
| Step | Read |
|---|---|
| 0 | `reference/standard-draft.md` (format and rules), `reference/intake.md` |
| 1 | `reference/infographic-planner.md`, `assets/icons/index.json` for icon names |
| 2 | Nothing extra; `reference/template-bank.md` explains a layout choice |
| 3 | `reference/build.md`, `reference/diagrams.md`; RULES.md only for the section a lint error names |
| 4–5 | `reference/review.md`, `reference/guide-slides/`, `reference/diagram-gallery/`, `layout-catalog-grid-*.jpg` |
| 6 | `reference/handoff.md` |

`RULES.md` holds every rule, labelled [GUIDE] or [DERIVED]. The scripts enforce them, so read a section when a
check names it rather than up front. `tokens.json` and `reference/capacity.md` are the machine-readable values.

## Auditing a deck built elsewhere
`python3 scripts/verify_deck.py their.pptx` (with `--plan` if they have one), render it, and compare each slide
with the guide slide of its layout. Report every FAIL and visual deviation; do not edit their file.

## Maintaining the skill
`evals/` (run `evals/builders/run_all.py` and the other `*_evals.py`; see `evals/evals.json`) and `maintenance/`
(rebuilds tokens, metrics, capacity, template bank and catalogue after the template changes) ship only in the
`./make_bundle.sh --dev` bundle.

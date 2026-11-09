# Steps 4–5 – Verify, package, render and review

## Verify
`python3 scripts/verify_deck.py WORK/out.pptx --plan WORK/plan.json --strict`

Fix and rebuild until the last line is `RESULT: PASS`. Read that line, not the counts. The summary is always
out of 23; `--strict` makes any skipped check a failure, which is right whenever plan.json and a standard
draft.md exist. Waived findings show as `~ WAIVED` and short-pitch skips as `~ SHORT-PITCH`; both go in the
hand-off.

Check 23 (content coverage) fails when a draft point, such as a customer quote, is on no slide and in no notes.
Put it on a slide, or mark it `(excluded)` in the draft / list it under plan `excluded` with a reason.

## Package (only if an `office` CLI is on PATH)
`office validate out.pptx --repair` → `office pptx clean out.pptx` → `office pptx check-overlap out.pptx` →
`office pptx check-fonts out.pptx` → verify again. Without it, skip this: verify already covers fonts, prompt
text, metadata and capacity.

## Render
`python3 scripts/render_deck.py WORK/out.pptx WORK/render/` – always into a fresh, empty folder; it does not
overwrite an existing one, so a stale render can look like a bug. It sets the font config itself, warns if Mark
Pro does not map to Outfit, and writes `out.pdf`, `slide-NN.jpg` and `contact.jpg`.

Open `contact.jpg`, then each slide next to the guide slide of the same layout (`reference/guide-slides/`) and
each diagram next to `reference/diagram-gallery/`. The guide slides of a layout are listed in
`reference/template-bank.json` → `guide_examples` (slide numbers of `guide-slides/slide-NN.jpg`). If you fixed
anything, re-render once; if nothing needed fixing, don't.

## Per-slide review
- [ ] Layout matches the content type (RULES §10); no repeat of the previous slide's layout.
- [ ] The slide's visual is the one in plan.json; one main visual; numbers equal the source.
- [ ] Nothing clipped, outside the content area, or over the Form tab, tracker, logo or footer.
- [ ] No empty placeholder or prompt text (verify checks this; still glance at the render).
- [ ] Icons on service/process slides and on lists of steps, levels and items; no shapes the guide does not show.
- [ ] Lead lines bold; chart units visible and the title matches the chart; table rows one line each.
- [ ] Every stock photo was opened and shows no people, faces or brand names/logos (RULES §8.2).
- [ ] No text repeated inside one element (for example an info box heading and label saying the same thing).
- [ ] Looks like the guide slide of the same layout.

## Preview quirks (not defects)
* LibreOffice draws a layout's filled placeholders even when the slide removed them (key pills and tiles, the
  "00" section square). PowerPoint hides them. Agenda slots never show empty: `d.agenda()` uses a layout with
  exactly as many slots as items (RULES §9.1).
* Without the Outfit font installed, previews fall back to another face and text widths look off. Install Outfit
  (Google Fonts, OFL) for faithful previews.
* `office pptx check-fonts` reports Mark Pro missing. That is expected; see the font note in `handoff.md`.
* Capacity uses Outfit widths plus 10 % headroom (`capacity.HEADROOM`), so a placeholder can fail the check while
  the preview still looks fine. Shorten the copy anyway. Diagram labels use the same measure.

## Auditing a deck built elsewhere
Run `python3 scripts/verify_deck.py their.pptx` (add `--plan` and the source if they have one), render it, and
compare each slide with the guide slide of its layout. Report every FAIL line and every visual deviation; do not
edit their file.

# Step 0 – Intake: any input → `draft.md`

Read `reference/standard-draft.md` in full first. It defines the format and its rules. This file says how to get
there. Work in a `WORK/` folder outside the skill.

## a. Classify
`python3 scripts/intake.py classify INPUT... [--text "typed ask"] --out WORK/`

Rules, in order:
* **structured** – the input already has a slide or section shape. A slide-marked PDF ('Slide N' / 'Folie N')
  stays structured and is validated against the standard: use it as is if it meets or exceeds the standard,
  otherwise top it up and flag each fix.
* **raw** – real facts but no slide shape: notes, a pasted article, PDF or URL text. `intake.py` converts PDFs and
  URLs to `WORK/source-<n>.txt` itself. Headings in a document are document structure, not slides.
* **bare** – a short ask, under ~150 words, with no facts beyond the topic.

Mixed input: the most content-rich part decides. The script proposes; you may override it with a one-line reason.
Record the type and reason in `intake.json`, and `input_type` in the draft header.

## b. Write `WORK/draft.md`
Canonical layout: the `scripts/draft_check.py` docstring.

| Type | Start from | Then apply judgment |
|---|---|---|
| raw | `python3 scripts/draftgen.py raw WORK/source-1.txt --intake WORK/intake.json -o WORK/draft.md` | Group facts into intro → problem → solution → proof → cta using input facts only. Mark gaps `to-be-filled` and unsourced claims `needs-source`. Never invent. |
| bare | `python3 scripts/draftgen.py bare --text "the ask" [--count N] -o WORK/draft.md` | Slide count from the ask or topic breadth (no fixed 10; reason in notes; `length` in `assumed` when proposed). Forge the title with a one-line `title_reason` (title in `assumed`). Generate the storyline and content, flag every generated fact `assumption`, and build straight away, without asking questions first. |
| structured | No script converts a structured file into the standard format: write `WORK/draft.md` by mapping the input field by field, then run `python3 scripts/draftgen.py suggest WORK/draft.md --apply-merge --apply-shorten -o WORK/draft.md` (plus `draftgen.py topup WORK/draft.md` for a slide-marked PDF that falls short) | Map the input field by field and keep the user's wording and order. Only shorten, split, merge or top up what breaks a rule, and note every change in `notes` with flag `edited`. Merges apply only when coverage confirms every source point is still on the merged slide or in its notes; skipped merges are reported. |

For every type:
* Record each change you make to the user's content as a notes line starting with `[edited]` and flag the slide
  `edited`; `draft_check --report` lists exactly those lines as the edits.
* **One slide per agenda item** (board packs, page caps): every draft section needs 2+ slides, so group the slides
  into fewer sections (e.g. 6 agenda items → 3 sections of 2) and keep the real agenda items for `plan.json`
  `chapters` in step 1. Do not let `--autofix` merge one-slide sections of such a deck.
* **Key slides** (`visual_hint: key-points`, 4 or 6 points): the boxes are small - Key Slide 1 headline ~35 chars on
  one line, pills ~2 lines × 19 chars; Key Slide 2 headline 2 × ~20 chars. `draft_check` warns (rule 15) when
  they will not fit, and count words in the headline or key point must match the points ("six checks" over 6).
* Headlines are claims, never topic labels. Keep a user-written headline when its wording suits the slide and
  audience; otherwise improve it from input facts only and flag `edited`.
* Re-bucket misplaced facts and fill audience and goal (listing them under `assumed` when not stated).
* Real data needs `source:`; anything else is flagged `assumption`.

## c. Check
`python3 scripts/draft_check.py WORK/draft.md --autofix` until it prints PASS. Autofix splits slides with more
than 5 points, merges one-slide sections, rebuilds the agenda and renumbers. Fix the rest by editing the draft:
missing header fields, fewer than 3 points, long points or headlines, enum values, data without a source.
Do not start step 1 before PASS. A short-pitch deck still has sections and an agenda in draft.md; they just don't
become slides.

From here on `draft.md` is the only source. The planner quotes it verbatim (`plan.json → "source": "draft.md"`),
and the build takes titles, points and notes from it. `purpose` and `visual_hint` are hints for the planner and
the matcher, not orders. Each slide's `notes` and flags end up in its speaker notes.

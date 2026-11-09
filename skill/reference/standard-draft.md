# Standard Structured Draft (v0.1, for review)

Every deck input ends up in this format before the build.
- A **structured draft** is checked against it and filled in where needed.
- **Raw notes or references** are shaped into it, using only facts from the input.
- A **bare request** has it generated, with every assumption flagged.

---

## 1. Deck header (once, at the top)

```yaml
title:        "Deck title"              # required, shown on the title slide (Titelfolie)
title_reason: "..."                     # required when title is in assumed: one line tying title to topic/audience/goal
subtitle:     "One-line subtitle"       # optional
audience:     "Who it is for"           # required, e.g. client leadership, internal team
goal:         "What the audience should think or do after it"   # required
assumed:      [ ]                       # header fields not stated in the input (audience, goal, title, length):
                                        # fill a best value and list the field here; draft_check FAILs an unstated
                                        # field missing here. Assumed title also needs title_reason.
presenter:    "Name, role"              # optional
date:         "November 2026"           # optional, defaults to the current month
length:       12                        # target number of content slides (not cover, agenda, dividers, closing)
                                        # bare ask with no count: draftgen proposes from topic breadth (no fixed 10)
language:     en                        # en or de
input_type:   structured | raw | bare   # set by the classifier
source_files: [ ]                       # references the content came from
```

## 2. Agenda (optional, built automatically from the sections if left out)

```
- Section 1 name
- Section 2 name
```

## 3. Sections and slides

Sections become chapter dividers (Kapiteltrenner). Each slide block is one slide.

```
## SECTION: <section name>

### SLIDE <n>: <headline, ideally a full message, max ~60 characters>
purpose:   intro | problem | solution | proof | process | comparison | data | team | summary | cta
key_point: <the one sentence the audience must remember>
content:
  - <point 1, max ~15 words>
  - <point 2>
  - <point 3, 3 to 5 points per slide>
data:              # optional, only real numbers
  - label: "..."   value: "..."   source: "..."
companies: [ ]     # optional, company names that need a real logo
visual_hint: none | infographic | chart | icons | key-number | key-points | image | table | quote
             # quote: 1-2 points (quote, attribution); key-points: exactly 4 or 6 short points (Key Slide 1 / 2)
             # optional, the planner decides if left out
notes: |
  Speaker notes. Changes made to the input and any assumptions go here.
flags: [ ]         # e.g. [assumption, needs-source, to-be-filled, edited, excluded]  (excluded: kept in the draft, deliberately not in the deck; the coverage check skips it)
```

## 4. Closing

```yaml
closing_message: "Thank you / next step"   # one short line: ~26 characters fit the closing slide
contact:         "name, email"   # optional
```

---

## Rules every draft must meet

1. One idea per slide, and one key point per slide. Headlines are claims, not topic labels (1-3 word noun
   phrases with no verb); draft_check WARNs on topic-label headlines. When the user wrote a headline, keep it
   if the wording suits the slide and audience, otherwise improve it using only input facts (flag `edited`).
2. 3 to 5 content points, about 15 words each. Anything longer is split into two slides. Exceptions: a quote
   slide has 1-2 points; a `key-points` slide has exactly 4 or 6 short points (one Key Slide pill or tile each).
3. Only real data in the `data` field. Anything invented is flagged `assumption`.
4. Gaps are marked `to-be-filled`, never silently invented. That applies to raw input. **Exception: required
   header fields** (title, audience, goal, language, input_type) can never be `to-be-filled`, `TBD`, `TODO` or a
   placeholder with a note (e.g. "to-be-filled (ask client)") - draft_check FAILs it. Write the best value and list
   the field under `assumed`; the report and the intake show it as assumed. An assumed title also needs a
   one-line `title_reason` (header or notes) or draft_check FAILs.
5. Every section has at least 2 slides; otherwise it is merged into a neighbouring section. Overlapping
   structured slides are merged automatically (`draftgen suggest --apply-merge`) only when every source point
   is still on the merged slide or in its notes (coverage 60 %); otherwise the merge is skipped.
6. `purpose` and `visual_hint` are what the planner and the template matcher use to pick a layout.
7. Slide-marked PDFs are structured: use as is when they meet/exceed this standard; if short, fill the gaps
   (`draftgen topup`) and flag each fix `edited`.

## How each input type reaches this format

| Input | What happens | Flags used |
|---|---|---|
| Structured draft | The input is mapped field by field; overlong slides are split, overlapping slides are merge-checked, shortfalls are topped up; every change is noted in `notes` | `edited` |
| Raw notes or references | Content is grouped into the storyline (intro, problem, solution, proof, cta) and fields are filled from the input only; headlines rewritten as claims | `to-be-filled`, `needs-source`, `edited` |
| Bare request | Slide count from the ask or from topic-breadth heuristics (no fixed 10); title forged with `title_reason`; storyline and content generated | `assumption` on every generated fact; `title`/`length` in `assumed` |

The output is one `.md` file in this format, which is then passed to the planner, the template matcher, the build and the verify step.

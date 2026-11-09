"""Worked example of the one build route: a SAMPLE deck (fictional product update) from
reference/example/ (notes.md -> draft.md -> plan.json -> match.json; ships in the runtime bundle). Copy this file, point it at your
WORK/ folder and replace SPEC.

    python3 scripts/example_build.py /tmp/demo/out.pptx
    python3 scripts/verify_deck.py /tmp/demo/out.pptx --plan /tmp/demo/out-work/plan.json --strict   # RESULT: PASS

The inputs are copied into <out>-work/ (the WORK folder of a real build) and match.json is written there, never
into the skill folder.

Each step stops on failure, exactly like the workflow in SKILL.md: draft_check -> planlib check -> matcher ->
matchbuild.build. SPEC holds only what the draft cannot say (icons, chart series, table rows); see matchbuild.py."""
import json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import matcher                       # noqa: E402
from matchbuild import build         # noqa: E402
from sgdeck import lead              # noqa: E402

SRC = os.path.join(HERE, "..", "reference", "example")
out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/sgdeck-evals/sample-deck.pptx")
WORK = os.path.splitext(out)[0] + "-work"
os.makedirs(WORK, exist_ok=True)
for f in ("notes.md", "draft.md", "plan.json"):
    shutil.copy(os.path.join(SRC, f), WORK)
DRAFT, PLAN, MATCH = (os.path.join(WORK, f) for f in ("draft.md", "plan.json", "match.json"))


def step(*cmd):
    r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{os.path.basename(cmd[0])} failed:\n{r.stdout}{r.stderr}")


step(os.path.join(HERE, "draft_check.py"), DRAFT)                # step 0: draft passes the standard
step(os.path.join(HERE, "planlib.py"), "check", PLAN)            # step 1: plan is valid
D = matcher.draft_check.parse(open(DRAFT, encoding="utf-8").read())
M = matcher.match(D, json.load(open(PLAN, encoding="utf-8")))     # step 2: layouts (written next to the plan)
json.dump(M, open(MATCH, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
if M["problems"]:
    sys.exit("matcher: " + "; ".join(M["problems"]))

SPEC = {                                                          # step 3: only what the draft cannot say
    "p01": {"args": {"categories": ["Jul", "Aug", "Sep", "Oct"],
                     "series": {"Teams on 3.2 (k)": [2.4, 3.6, 4.3, 4.7], "Teams on 3.1 (k)": [2.1, 2.2, 2.3, 2.2]}},
            "body": [lead("What drove the jump"), "Guided onboarding cut setup time from days to hours",
                     "Shared dashboards for whole teams", "Usage-based alerts re-engage dormant accounts"]},
    "p02": {"kind": "service", "icon": "calendar", "box_title": "Typical timeline", "box_label": "Sample figure, not real data"},
    "p03": {"args": {"rows": [["Plan", "Seats", "2025", "2026"], ["Starter", "up to 5", "49", "49"],
                              ["Team", "up to 25", "199", "179"], ["Business", "up to 100", "690", "590"]]},
            "corner_icon": "dollar"},
    "p04": {"args": {"steps": [("Book a migration slot", "", "calendar"), ("Join the 3.3 beta", "", "rating-thumbs-up"),
                               ("Read the 3.2 release notes", "", "document")]}},
}
build(DRAFT, PLAN, MATCH, SPEC, out)
print(out)
print("verify: python3 scripts/verify_deck.py", out, "--plan", PLAN, "--strict")

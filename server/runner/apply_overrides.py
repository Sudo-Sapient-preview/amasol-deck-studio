"""Apply user-requested text emphasis to a finished, verified deck.

    python apply_overrides.py in.pptx overrides.json out.pptx

The amasol guide allows no italics or underline and bold only on lead lines, so verify_deck runs on the deck
BEFORE this step. When a user explicitly asks for emphasis on certain words, the tool honours it here, on a copy,
and reports it as a deliberate exception. overrides.json:

    {"emphasis": [{"text": "sudosapient.com", "italic": true, "bold": false, "underline": false,
                   "match_case": false}]}

Every slide text run (shapes, groups, tables) is searched; a run containing the text is split so only the match
gets the style. Speaker notes, layouts and the master are left alone. Prints JSON {"total": n, "per_rule": {...}}.
Exit 0 on success, 1 on a bad overrides file."""
import copy
import json
import re
import sys

from pptx import Presentation

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def load_rules(path):
    data = json.load(open(path, encoding="utf-8"))
    rules = []
    for r in data.get("emphasis") or []:
        text = str(r.get("text") or "").strip()
        if not text:
            continue
        style = {k: bool(r.get(k)) for k in ("italic", "bold", "underline")}
        if not any(style.values()):
            continue
        rules.append({"text": text, "match_case": bool(r.get("match_case")), **style})
    return rules


def styled(run, rule):
    rpr = run.find(A + "rPr")
    if rpr is None:
        rpr = run.makeelement(A + "rPr", {})
        run.insert(0, rpr)
    if rule["italic"]:
        rpr.set("i", "1")
    if rule["bold"]:
        rpr.set("b", "1")
    if rule["underline"]:
        rpr.set("u", "sng")


def apply_rule(root, rule):
    flags = 0 if rule["match_case"] else re.I
    pat = re.compile(re.escape(rule["text"]), flags)
    count = 0
    for run in list(root.iter(A + "r")):
        t = run.find(A + "t")
        if t is None or not t.text or not pat.search(t.text):
            continue
        rpr = run.find(A + "rPr")
        have = {} if rpr is None else rpr.attrib
        if ((not rule["italic"] or have.get("i") == "1") and (not rule["bold"] or have.get("b") == "1")
                and (not rule["underline"] or have.get("u") == "sng")):
            continue                                # already styled by an earlier rule: no split, no count
        parts, last = [], 0
        for m in pat.finditer(t.text):
            if m.start() > last:
                parts.append((t.text[last:m.start()], False))
            parts.append((m.group(0), True))
            last = m.end()
        if last < len(t.text):
            parts.append((t.text[last:], False))
        parent = run.getparent()
        idx = list(parent).index(run)
        new_runs = []
        for text, hit in parts:
            r = copy.deepcopy(run)
            r.find(A + "t").text = text
            if hit:
                styled(r, rule)
                count += 1
            new_runs.append(r)
        parent.remove(run)
        for k, r in enumerate(new_runs):
            parent.insert(idx + k, r)
    return count


def main():
    src, rules_path, out = sys.argv[1:4]
    try:
        rules = load_rules(rules_path)
    except (OSError, ValueError) as e:
        print(json.dumps({"error": f"bad overrides file: {e}"}))
        return 1
    prs = Presentation(src)
    per_rule = {}
    for rule in rules:
        n = 0
        for slide in prs.slides:
            n += apply_rule(slide.shapes._spTree, rule)
        per_rule[rule["text"]] = n
    prs.save(out)
    print(json.dumps({"total": sum(per_rule.values()), "per_rule": per_rule}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

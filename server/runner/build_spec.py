"""Build a deck from a WORK folder with a JSON SPEC (runs under the skill's own .venv).

    python build_spec.py <skill_dir> <work_dir>

Reads work/draft.md, work/plan.json, work/match.json and work/spec.json, converts the JSON SPEC into the Python
SPEC that scripts/matchbuild.py expects, and writes work/out.pptx.

JSON conventions (Python-only values in matchbuild's SPEC):
  body items     "text" -> bullet, {"lead": "text"} -> sgdeck.lead (first item only), ["text", 1] -> sub bullet
  dividers       {"Chapter": ["icon", "line"]} -> tuple
  region/col_w   lists -> tuples
Exit 0 on success, 2 on a GuideError (content must change), 1 on anything else."""
import json
import os
import sys
import traceback


def main():
    skill, work = sys.argv[1], sys.argv[2]
    sys.path.insert(0, os.path.join(skill, "scripts"))
    from matchbuild import build  # noqa: E402
    from sgdeck import GuideError, lead  # noqa: E402

    def body_items(items):
        if isinstance(items, str):
            items = [items]
        out = []
        for it in items:
            if isinstance(it, dict) and "lead" in it:
                out.append(lead(str(it["lead"])))
            elif isinstance(it, (list, tuple)) and len(it) == 2 and isinstance(it[1], int):
                out.append((str(it[0]), int(it[1])))
            else:
                out.append(str(it))
        return out

    def tupled(v):
        return tuple(tupled(x) for x in v) if isinstance(v, list) else v

    raw = json.load(open(os.path.join(work, "spec.json"), encoding="utf-8"))
    if not isinstance(raw, dict):
        print("SPEC ERROR: spec.json must be a JSON object")
        return 1
    spec = {}
    for key, val in raw.items():
        if key == "dividers":
            spec[key] = {ch: tuple(v) for ch, v in (val or {}).items()}
        elif isinstance(val, dict) and key.startswith("p"):
            e = dict(val)
            if "custom" in e:
                print(f"SPEC ERROR: {key}: 'custom' is not available in this tool - use a builder via 'args'")
                return 1
            if "body" in e and e["body"] is not None:
                e["body"] = body_items(e["body"])
            if isinstance(e.get("args"), dict):
                a = dict(e["args"])
                for k in ("region", "col_w", "axis", "heads", "icons"):
                    if isinstance(a.get(k), list):
                        a[k] = tupled(a[k])
                e["args"] = a
            spec[key] = e
        else:
            spec[key] = val
    out = os.path.join(work, "out.pptx")
    tmp = os.path.join(work, "out.building.pptx")
    try:
        build(os.path.join(work, "draft.md"), os.path.join(work, "plan.json"), os.path.join(work, "match.json"),
              spec, tmp)
    except GuideError as e:
        print(f"GUIDE ERROR: {e}")
        return 2
    except KeyError as e:
        print(f"SPEC ERROR: missing key {e} - check spec.json against match.json (dividers for every chapter, "
              "args/icons for every slide that needs them)")
        print("".join(traceback.format_exc().splitlines(True)[-6:]))
        return 1
    except Exception as e:  # noqa: BLE001 - reported back to the agent verbatim
        print(f"BUILD ERROR: {type(e).__name__}: {e}")
        print("".join(traceback.format_exc().splitlines(True)[-8:]))
        return 1
    os.replace(tmp, out)
    print(f"built {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

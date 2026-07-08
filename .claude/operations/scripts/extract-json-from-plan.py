#!/usr/bin/env python3
"""Extract the ops.json config embedded in a planner output / plan document.

Headless planner spawns cannot write into .claude/ (sensitive-path gate), so
their stdout is the delivery contract: the plan text plus the ops config in a
fenced ```json block. This script pulls the config back out so the invoking
command can save and validate it.

Usage:
    python3 extract-json-from-plan.py <plan-file> [--output <ops-file>]

Prints the extracted JSON to stdout (and writes --output when given).
Exit codes: 0 extracted; 1 no valid ops config found; 2 bad invocation.
"""
import json
import re
import sys


def extract(text):
    """Return the best ops-config candidate in *text*, or None.

    An ops config is a JSON object with an "operations" array (modern schema
    also requires a "plan" key, but the validator owns schema enforcement —
    we only locate and parse). Fenced blocks are preferred; the largest valid
    candidate wins so prose snippets don't shadow the real config.
    """
    candidates = []
    # Fenced blocks, line-anchored so a closing fence is never mistaken for an
    # opening one (mixed ```markdown / ```json documents mis-pair otherwise).
    for match in re.finditer(r"^```[a-zA-Z]*[ \t]*\n(.*?)^```", text, re.S | re.M):
        candidates.append(match.group(1))
    # The whole file may already be bare JSON.
    candidates.append(text)

    best = None
    for cand in candidates:
        cand = cand.strip()
        if '"operations"' not in cand:
            continue
        try:
            data = json.loads(cand)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("operations"), list):
            if best is None or len(cand) > len(best):
                best = cand
    if best is not None:
        return best

    # Last resort: scan for any balanced JSON object in the raw text (fences
    # may be malformed or absent). raw_decode parses the first JSON value at
    # each candidate position.
    decoder = json.JSONDecoder()
    for idx in [m.start() for m in re.finditer(r"\{", text)]:
        if '"operations"' not in text[idx:idx + 20000]:
            continue
        try:
            data, _end = decoder.raw_decode(text[idx:])
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("operations"), list):
            cand = json.dumps(data)
            if best is None or len(cand) > len(best):
                best = cand
    return best


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    plan_path = argv[0]
    out_path = None
    if "--output" in argv:
        idx = argv.index("--output")
        if idx + 1 >= len(argv):
            print("ERROR: --output requires a path", file=sys.stderr)
            return 2
        out_path = argv[idx + 1]

    try:
        with open(plan_path) as fh:
            text = fh.read()
    except OSError as exc:
        print(f"ERROR: cannot read {plan_path}: {exc}", file=sys.stderr)
        return 2

    extracted = extract(text)
    if extracted is None:
        print(f"ERROR: no valid ops config (JSON object with an 'operations' "
              f"array) found in {plan_path}", file=sys.stderr)
        return 1

    # Normalize formatting so downstream diffs are stable.
    pretty = json.dumps(json.loads(extracted), indent=2) + "\n"
    if out_path:
        with open(out_path, "w") as fh:
            fh.write(pretty)
        print(f"Extracted ops config -> {out_path}")
    else:
        sys.stdout.write(pretty)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

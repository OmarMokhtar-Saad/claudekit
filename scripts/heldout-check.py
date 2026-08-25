#!/usr/bin/env python3
"""heldout-check.py - integrity and regression scoring for the frozen held-out review set.

Two deterministic halves of a three-part protocol (`.claude/knowledge/heldout/README.md`);
the third - replaying the reviewer over the fixtures - is manual and owner-invoked, because
it spawns `claude -p` once per fixture, costs real tokens and is non-deterministic. This
script never spawns anything.

  heldout-check.py --verify                 # every fixture still hashes true
  heldout-check.py --results verdicts.json  # score a replay against the baseline

Exit codes:
  0  clean
  1  usage / unreadable manifest
  4  a fixture is MISSING or DRIFTED -- the frozen set is not intact, measure nothing
  5  a fixture regressed: APPROVED -> non-APPROVED, or a verdict is missing from --results

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import hashlib
import json
import os
import sys

MANIFEST = os.path.join(".claude", "knowledge", "heldout", "MANIFEST.json")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(root):
    path = os.path.join(root, MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        print("Error: cannot read %s (%s)" % (MANIFEST, exc), file=sys.stderr)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("fixtures"), list):
        print("Error: %s has no fixtures list" % MANIFEST, file=sys.stderr)
        return None
    return data


def verify(root, manifest):
    """Every frozen artifact still hashes to what was frozen.

    A DRIFTED fixture is REPORTED, never silently accepted and never auto-re-frozen:
    re-freezing to make a red run green is exactly the failure a held-out set exists to
    prevent, so that decision stays with a human.
    """
    bad = 0
    for fixture in manifest["fixtures"]:
        for key, sha_key in (("plan", "plan_sha256"), ("snapshot", "snapshot_sha256")):
            path = os.path.join(root, fixture.get(key, ""))
            if not os.path.isfile(path):
                print("MISSING  %-34s %s" % (fixture.get("id"), fixture.get(key)))
                bad += 1
                continue
            if sha256_of(path) != fixture.get(sha_key):
                print("DRIFTED  %-34s %s" % (fixture.get("id"), fixture.get(key)))
                bad += 1
            else:
                print("OK       %-34s %s" % (fixture.get("id"), fixture.get(key)))
    print("")
    print("%d fixture(s), %d artifact problem(s)" % (len(manifest["fixtures"]), bad))
    if bad:
        print("The frozen set is not intact. Re-freeze deliberately, or measure nothing: "
              "a comparison against artifacts that moved is not a comparison.",
              file=sys.stderr)
        return 4
    return 0


def score(root, manifest, results_path):
    try:
        with open(results_path, "r", encoding="utf-8") as handle:
            results = json.load(handle)
    except (OSError, ValueError) as exc:
        print("Error: cannot read %s (%s)" % (results_path, exc), file=sys.stderr)
        return 1
    verdicts = results.get("verdicts") if isinstance(results, dict) else None
    if not isinstance(verdicts, dict):
        print("Error: results file needs a \"verdicts\" object keyed by fixture id.",
              file=sys.stderr)
        return 1

    regressions, deltas, missing = [], [], []
    print("%-34s %-10s %-10s %s" % ("fixture", "baseline", "replay", "delta"))
    for fixture in manifest["fixtures"]:
        fid = fixture.get("id")
        got = verdicts.get(fid)
        if not isinstance(got, dict) or "decision" not in got:
            missing.append(fid)
            print("%-34s %-10s %-10s %s" % (fid, fixture.get("decision"), "-", "MISSING"))
            continue
        base_decision = fixture.get("decision")
        new_decision = str(got.get("decision"))
        delta = ""
        if isinstance(got.get("score"), int) and isinstance(fixture.get("score"), int):
            diff = got["score"] - fixture["score"]
            deltas.append(diff)
            delta = "%+d" % diff
        if base_decision == "APPROVED" and new_decision != "APPROVED":
            regressions.append((fid, new_decision))
            delta = (delta + "  REGRESSION").strip()
        print("%-34s %-10s %-10s %s" % (fid, base_decision, new_decision, delta))

    print("")
    if deltas:
        # REPORTED, never gated: the same plan can score 92 or 94 across runs, and a gate
        # on that is a coin toss wearing a threshold.
        print("mean score delta: %+.2f over %d fixture(s) -- reported, NOT a gate."
              % (sum(deltas) / float(len(deltas)), len(deltas)))
    if missing:
        print("MISSING verdicts for %d fixture(s): %s" % (len(missing), ", ".join(missing)),
              file=sys.stderr)
        print("A fixture absent from the replay is a failure, not a skip.", file=sys.stderr)
    if regressions:
        for fid, decision in regressions:
            print("REGRESSION: %s went APPROVED -> %s" % (fid, decision), file=sys.stderr)
        print("The edit does not ship. The decision flip is the gate.", file=sys.stderr)
    if regressions or missing:
        return 5
    print("No decision regressed against the frozen set.")
    print("NOTE: all baselines are APPROVED, so this proves only that the edit did not "
          "become HARSHER. It cannot detect a laxer reviewer -- no recorded rejection "
          "exists to hold out. Quote that with the result.")
    return 0


def refreeze(root, manifest):
    """Re-record the hashes of the pinned artifacts, reporting every one that moved.

    Re-freezing is a COMMAND rather than hand-transcription because a hash typed into a
    plan goes stale the moment the tree moves -- it did, twice, between writing this set
    and executing it. It is deliberately loud: re-freezing to turn a red run green is the
    one failure a held-out set exists to prevent, so every change is named and the
    operator has to justify it in the commit.
    """
    changed = []
    for fixture in manifest["fixtures"]:
        for key, sha_key in (("plan", "plan_sha256"), ("snapshot", "snapshot_sha256")):
            path = os.path.join(root, fixture.get(key, ""))
            if not os.path.isfile(path):
                print("MISSING  %-34s %s" % (fixture.get("id"), fixture.get(key)),
                      file=sys.stderr)
                return 4
            digest = sha256_of(path)
            if digest != fixture.get(sha_key):
                changed.append((fixture.get("id"), fixture.get(key),
                               fixture.get(sha_key), digest))
                fixture[sha_key] = digest
    path = os.path.join(root, MANIFEST)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    for fid, key, old, new in changed:
        # The hashes are the whole audit trail. "RE-FROZE <id> <key>" proves only that
        # something moved; old -> new is what lets a reader check WHICH content was
        # re-pinned against the diff the commit is required to carry. Without them the
        # command's own justification is unverifiable, which is exactly the misuse the
        # warning below cautions against.
        print("RE-FROZE %-34s %s" % (fid, key))
        print("         %s -> %s" % (str(old)[:16], str(new)[:16]))
    print("")
    print("%d artifact(s) re-frozen." % len(changed))
    if changed:
        print("State in the commit WHY each moved. A held-out set re-frozen to make a "
              "failing run pass measures nothing.", file=sys.stderr)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Verify the frozen held-out set, or score a replay against it")
    parser.add_argument("--root", default=".", help="project root (default: cwd)")
    parser.add_argument("--verify", action="store_true", help="check fixture integrity")
    parser.add_argument("--freeze", action="store_true",
                        help="re-record the hashes, naming every artifact that moved")
    parser.add_argument("--results", default=None, help="replay verdicts JSON to score")
    args = parser.parse_args()

    manifest = load_manifest(args.root)
    if manifest is None:
        return 1
    if args.freeze:
        return refreeze(args.root, manifest)
    if args.results:
        # Integrity ALWAYS runs first: scoring against artifacts that moved is not a
        # comparison, and reporting a clean run over a drifted set is worse than no run.
        code = verify(args.root, manifest)
        if code:
            return code
        print("")
        return score(args.root, manifest, args.results)
    return verify(args.root, manifest)


if __name__ == "__main__":
    sys.exit(main())

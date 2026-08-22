#!/usr/bin/env python3
"""
review-record.py - Bind a reviewer verdict to the exact ops.json it approved.

A review score is only meaningful for the artifact that was reviewed. This records
sha256(ops.json) with the verdict and its findings, snapshots the approved config,
and lets a later stage prove the file has not drifted.

Usage:
  review-record.py resolve <plan.md>
  review-record.py write   <plan.md> <ops.json> --from-review <file|->
  review-record.py write   <plan.md> <ops.json> --score N --decision D
  review-record.py check   <plan.md> <ops.json>
  review-record.py diff    <plan.md> <ops.json>

Exit codes:
  0  success / ops.json matches an APPROVED record
  1  usage or I/O error
  2  DRIFT - ops.json changed since approval (blocking)
  3  no approval record / could not resolve
  4  record exists and matches, but the verdict does not authorise execution

Verdict parsing lives here rather than in shell so it can be validated and tested:
strict anchored patterns mean an echoed format template ('SCORE: <integer 0-100>')
never parses as a real score.

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RECORDS_DIR = Path(".claude/reports/reviews")
APPROVAL_THRESHOLD = 90
VALID_DECISIONS = ("APPROVED", "CONDITIONAL", "REVISE", "REJECTED")

# A re-review used to overwrite the verdict it replaced, so a record could only
# ever show the round that passed. Measured on the corpus that produced this
# change: 51 records, 51 APPROVED, scores 90-96 -- not because review always
# passes, but because only the passing round survived. Rounds-to-clean and score
# trajectory are exactly the signals that make review outcomes measurable, and
# both were destroyed at write time.
ROUND_KEYS = ("score", "decision", "findings", "recorded_utc", "ops_sha256")
# The review loop's documented ceiling is 3 rounds; 20 is far above any real run
# while still bounding a pathological loop. Dropping is announced, never silent.
MAX_ROUNDS = 20

# Delta review stops being a saving once the change is sweeping; past this share of
# changed lines the reviewer is told to do a full review instead.
DELTA_CEILING = 0.25
DELTA_FLOOR = 40  # lines: below this, delta mode always applies regardless of ratio
FULL_REVIEW_MARKER = "# FULL REVIEW REQUIRED"

_BLOCK_RE = re.compile(r"===\s*REVIEW\s*===(.*?)===\s*END\s+REVIEW\s*===", re.S)
_SCORE_RE = re.compile(r"^SCORE:\s*(\d{1,3})\s*$", re.M)
_DECISION_RE = re.compile(r"^DECISION:\s*(%s)\s*$" % "|".join(VALID_DECISIONS), re.M)
_FINDING_RE = re.compile(r"^-\s*\[(CRITICAL|MAJOR|MINOR)\]\s*(.+)$", re.M)


def plan_slug(plan_path: str) -> str:
    stem = Path(plan_path).stem
    return stem[5:] if stem.startswith("plan-") else stem


def ops_slug(ops_path) -> str:
    """Record key derived from the OPS config's own filename.

    Records used to be keyed by the plan slug, but the executor's approval gate is
    handed an ops.json and resolves candidates from ITS filename
    (execute-json-ops.py _approval_slugs). The two disagreed whenever an ops file
    was named differently from its plan, so an addendum could not be approved
    through the sanctioned path at all, and two configs under one plan collapsed
    onto one record path where the second write destroyed the first. Both were hit
    live on approved Tier 3 plans.

    Keying by ops identity makes the two sides agree by construction. This inverts
    exactly the filename forms resolve_ops() emits, so plan-x.ops.json, ops-x.json,
    x.ops.json and x.json all key as "x".
    """
    name = Path(ops_path).name
    for suffix in (".ops.json", ".json"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    for prefix in ("plan-", "ops-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name or "_"


def resolve_ops(plan_path: str):
    """Find the ops.json a plan owns, across every naming convention in use.

    /plan and /refine both derive it as ${PLAN_FILE%.md}.ops.json -- the UN-stripped
    stem, "plan-" prefix and all (plan.md:63, refine.md:229). hooks/lib.sh separately
    matches `*.ops.json` and `ops-*.json`. Guessing one form silently disables the
    mechanism for the others -- try every form and report failure loudly.
    """
    stem = Path(plan_path).stem
    slug = plan_slug(plan_path)
    plans_dir = Path(plan_path).parent
    seen = []
    for name in (f"{stem}.ops.json", f"ops-{slug}.json",
                f"{slug}.ops.json", f"{slug}.json"):
        candidate = plans_dir / name
        if candidate.exists() and candidate not in seen:
            seen.append(candidate)
    if len(seen) > 1:
        print(f"AMBIGUOUS: multiple ops.json candidates for '{slug}':", file=sys.stderr)
        for cand in seen:
            print(f"           {cand}", file=sys.stderr)
        return None
    return seen[0] if seen else None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def record_paths(slug: str):
    # Record filenames are derived, not user paths: collapse anything outside
    # [A-Za-z0-9._-] and strip leading dots so a hostile plan filename (e.g.
    # "plan-...md" -> slug "..") cannot produce dot-files or reserved names.
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", slug).lstrip(".") or "_"
    d = _records_dir()
    return d / f"{safe}.json", d / f"{safe}.ops.json"


def parse_verdict(text: str):
    """Extract (score, decision, findings) from a reviewer's output.

    Only the last '=== REVIEW ===' block counts, and both fields must match their
    strict anchored form. A prompt that merely quotes the template does not parse.
    Returns (None, None, []) when the verdict cannot be read with confidence.
    """
    blocks = _BLOCK_RE.findall(text)
    body = blocks[-1] if blocks else text

    scores = _SCORE_RE.findall(body)
    decisions = _DECISION_RE.findall(body)
    if not scores or not decisions:
        return None, None, []

    score = int(scores[-1])
    if not 0 <= score <= 100:
        return None, None, []

    findings = [f"[{sev}] {txt.strip()[:200]}" for sev, txt in _FINDING_RE.findall(body)]
    return score, decisions[-1], findings[:40]


def load_ops_summary(ops_path: Path) -> dict:
    try:
        cfg = json.loads(ops_path.read_text(encoding="utf-8"))
        ops = cfg.get("operations", cfg.get("files", []))
        return {
            "operations": len(ops),
            "edits": sum(len(o.get("edits", [])) for o in ops if isinstance(o, dict)),
        }
    except Exception:
        return {"operations": None, "edits": None}


def _records_dir() -> Path:
    """Nearest .claude/reports/reviews walking up from cwd, so `check` run from a
    subdirectory does not silently report NO RECORD instead of an error."""
    cur = Path.cwd()
    for candidate in (cur, *cur.parents):
        if (candidate / ".claude").is_dir():
            return candidate / RECORDS_DIR
    return RECORDS_DIR


def _safe_write(path: Path, text: str) -> bool:
    """Refuse to write through a symlink anywhere on the records path — the leaf
    file, the reviews/ dir, reports/, or .claude/ itself. Checking only the leaf
    and its parent leaves an arbitrary-write primitive one level up: a symlink
    planted at .claude/reports would be followed by mkdir -p and the write would
    land outside the repo."""
    for p in (path, path.parent, path.parent.parent, path.parent.parent.parent):
        if p.is_symlink():
            print(f"Error: refusing to write through symlink: {p}", file=sys.stderr)
            return False
    path.write_text(text, encoding="utf-8")
    return True


def cmd_resolve(args) -> int:
    ops_path = resolve_ops(args.plan)
    if ops_path is None:
        stem = Path(args.plan).stem
        slug = plan_slug(args.plan)
        print(f"NO OPS: could not resolve an unambiguous ops.json for '{slug}'",
              file=sys.stderr)
        print(f"        tried {stem}.ops.json, ops-{slug}.json, "
              f"{slug}.ops.json, {slug}.json", file=sys.stderr)
        print("        (see any AMBIGUOUS listing above if more than one exists)",
              file=sys.stderr)
        return 3
    print(str(ops_path))
    return 0


def cmd_write(args) -> int:
    ops_path = Path(args.ops)
    if not ops_path.exists():
        print(f"Error: ops.json not found: {ops_path}", file=sys.stderr)
        return 1

    findings = []
    if args.from_review:
        raw = sys.stdin.read() if args.from_review == "-" else \
            Path(args.from_review).read_text(encoding="utf-8")
        score, decision, findings = parse_verdict(raw)
        if score is None:
            print("Error: could not parse SCORE/DECISION from the review output.",
                  file=sys.stderr)
            print("       Nothing recorded — /implement will report NO RECORD.",
                  file=sys.stderr)
            return 1
    else:
        score, decision = args.score, args.decision
        if score is None or decision is None:
            print("Error: provide --from-review, or both --score and --decision",
                  file=sys.stderr)
            return 1
        if not 0 <= score <= 100 or decision not in VALID_DECISIONS:
            print(f"Error: invalid score/decision: {score} {decision}", file=sys.stderr)
            return 1

    slug = ops_slug(ops_path)
    rec_path, snap_path = record_paths(slug)
    rec_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "plan": os.path.relpath(args.plan),
        "slug": slug,
        "ops_path": os.path.relpath(str(ops_path)),
        "ops_sha256": sha256_of(ops_path),
        "score": score,
        "decision": decision,
        "findings": findings,
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    record.update(load_ops_summary(ops_path))

    # Fold the verdict being replaced into this one's history. `rounds` is purely
    # additive: cmd_check reads score/decision/ops_sha256 off the TOP level, which
    # is written exactly as before, so nothing here can change what the gate does.
    rounds: list = []
    prior_round = 0
    if rec_path.exists():
        # The whole read AND the structural walk live inside the try. Parsing is
        # not the only way a corrupt record bites: a file holding `"rounds": 5`
        # is valid JSON, so it clears json.loads and then raises TypeError on
        # list(), which -- if the walk sat outside -- would brick every future
        # approval for this slug. That is the same failure the broad catch below
        # exists to prevent, so the guard has to cover the untrusted READ, not
        # just the untrusted PARSE.
        try:
            prior = json.loads(rec_path.read_text(encoding="utf-8"))
            if not isinstance(prior, dict):
                raise TypeError(f"record is {type(prior).__name__}, not an object")
            prior_rounds = prior.get("rounds")
            # Every element is re-checked: a round entry that is not an object
            # would reach the trail printer below, which would then fail a write
            # that already succeeded.
            rounds = [r for r in prior_rounds
                      if isinstance(r, dict)] if isinstance(prior_rounds, list) else []
            rounds.append({k: prior[k] for k in ROUND_KEYS if k in prior})
            # Counted from the PRIOR record's own number, not from len(rounds),
            # so the count stays true after the cap starts dropping entries --
            # otherwise round 30 would report itself as 21 and rounds-to-clean,
            # the entire point of this history, would quietly stop being a fact.
            pr = prior.get("round")
            prior_round = pr if isinstance(pr, int) and pr > 0 else len(rounds)
        except Exception as e:
            # Deliberately broad, matching cmd_check (:309) and cmd_diff (:380),
            # which use `except Exception` for this same "read an existing record"
            # operation. Narrowing it to (JSONDecodeError, OSError) looks tighter
            # but is not: a record holding invalid UTF-8 raises UnicodeDecodeError
            # -- a ValueError, neither of those -- and would crash the write,
            # bricking every future approval for this slug. Losing history
            # silently is how the corpus got into this state, so it is announced.
            print(f"WARNING: existing record for '{slug}' is unreadable ({e}); "
                  "its verdict history is lost.", file=sys.stderr)
            rounds, prior_round = [], 0
    if len(rounds) > MAX_ROUNDS:
        print(f"NOTE: {len(rounds) - MAX_ROUNDS} oldest round(s) dropped "
              f"(MAX_ROUNDS={MAX_ROUNDS}).", file=sys.stderr)
        rounds = rounds[-MAX_ROUNDS:]
    record["rounds"] = rounds
    record["round"] = prior_round + 1

    if not _safe_write(rec_path, json.dumps(record, indent=2) + "\n"):
        return 1
    if not _safe_write(snap_path, ops_path.read_text(encoding="utf-8")):
        return 1

    gate = "authorises execution" if (
        decision == "APPROVED" and score >= APPROVAL_THRESHOLD) else \
        "does NOT authorise execution"
    print(f"Recorded {decision} ({score}) for {slug} — {gate}")
    print(f"  sha256: {record['ops_sha256'][:16]}...  ops={record['operations']} "
          f"edits={record['edits']}  findings={len(findings)}")
    if rounds:
        trail = " -> ".join(
            f"{r.get('score')}/{r.get('decision')}" for r in rounds)
        print(f"  round {record['round']}: {trail} -> {score}/{decision}")
    return 0


def _record_covers(rec_path: Path, ops_path: Path) -> bool:
    """Whether a record was written FOR this ops file, by recorded path.

    Used to keep the legacy read path from lending one config's snapshot to
    another. Identity here is by path, not hash: a drifted-but-correct config must
    still resolve, so that `check` can report DRIFT rather than NO RECORD.
    """
    try:
        record = json.loads(rec_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    recorded = record.get("ops_path")
    if not recorded:
        return False
    try:
        return Path(recorded).resolve() == ops_path.resolve()
    except OSError:
        return str(recorded) == str(ops_path)


def cmd_check(args) -> int:
    ops_path = Path(args.ops)
    slug = ops_slug(ops_path)
    rec_path, _ = record_paths(slug)

    if not rec_path.exists():
        # Records written before keying moved to ops identity live under the plan
        # slug. The legacy path is READ-only: nothing writes it any more, so it
        # drains as plans are archived instead of needing a migration step. A miss
        # on both keys still fails CLOSED below.
        legacy = plan_slug(args.plan)
        legacy_path, _ = record_paths(legacy)
        if legacy_path.exists():
            print(f"NOTE: no record under ops key '{slug}'; using the legacy "
                  f"plan-slug record '{legacy}'.", file=sys.stderr)
            slug, rec_path = legacy, legacy_path

    if not rec_path.exists():
        print(f"NO RECORD: no review record for '{slug}'.", file=sys.stderr)
        print("           Run /review before /implement.", file=sys.stderr)
        return 3
    if not ops_path.exists():
        print(f"Error: ops.json not found: {ops_path}", file=sys.stderr)
        return 1

    try:
        record = json.loads(rec_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error: unreadable review record {rec_path}: {e}", file=sys.stderr)
        print("        Treated as no usable record — run /review again.", file=sys.stderr)
        return 3

    if sha256_of(ops_path) != record.get("ops_sha256"):
        print("DRIFT: ops.json changed after it was reviewed.", file=sys.stderr)
        print(f"       approved: {str(record.get('ops_sha256'))[:16]}...", file=sys.stderr)
        print(f"       current:  {sha256_of(ops_path)[:16]}...", file=sys.stderr)
        print("       The recorded score does not apply to this file.", file=sys.stderr)
        print("       Most likely cause: --stamp-baseline was run AFTER the verdict",
              file=sys.stderr)
        print("       was recorded. Stamping writes a 'baseline' key into the config,",
              file=sys.stderr)
        print("       and this binding is over raw bytes. Stamp FIRST, then record,",
              file=sys.stderr)
        print("       then execute — that order needs no other change.", file=sys.stderr)
        print("       Otherwise re-run /review (it scores only the delta), then retry.",
              file=sys.stderr)
        return 2

    score = record.get("score")
    decision = record.get("decision")
    if decision != "APPROVED" or not isinstance(score, int) or score < APPROVAL_THRESHOLD:
        print(f"NOT APPROVED: recorded verdict is {decision} ({score}).", file=sys.stderr)
        print(f"              Execution needs APPROVED and >= {APPROVAL_THRESHOLD}.",
              file=sys.stderr)
        print("              Address the findings and re-run /review.", file=sys.stderr)
        return 4

    print(f"OK: ops.json matches the reviewed artifact ({decision} {score}).")
    return 0


def _normalized(path: Path):
    """Canonical text for diffing, so pure formatting churn is not a delta.

    A raw line diff of JSON is worthless once indentation, key order, or ascii
    escaping shifts — measured on a 60 KB config, a formatting-only change produced
    a diff LARGER than the file, which would make delta review cost more than a full
    one. Hashing still uses raw bytes; only this human/model-facing view is canonical.
    """
    text = path.read_text(encoding="utf-8")
    try:
        canon = json.dumps(json.loads(text), indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        canon = text
    return canon.splitlines(keepends=True)


def cmd_diff(args) -> int:
    ops_path = Path(args.ops)
    slug = ops_slug(ops_path)
    rec_path, snap_path = record_paths(slug)

    if not (rec_path.exists() and snap_path.exists()):
        legacy = plan_slug(args.plan)
        legacy_rec, legacy_snap = record_paths(legacy)
        # Only adopt a legacy record that is bound to THIS config. Without the
        # ops_path check the fallback happily rendered a delta against an unrelated
        # config's approved snapshot, labelled "approved/<slug>.json" — a diff that
        # invites a reviewer to score the wrong artifact.
        if legacy_rec.exists() and legacy_snap.exists() and _record_covers(legacy_rec, ops_path):
            slug, rec_path, snap_path = legacy, legacy_rec, legacy_snap

    if not rec_path.exists() or not snap_path.exists():
        print(f"NO RECORD: no approved snapshot for '{slug}'", file=sys.stderr)
        return 3

    try:
        record = json.loads(rec_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error: unreadable review record {rec_path}: {e}", file=sys.stderr)
        return 3

    # Delta review is only sound relative to an APPROVED baseline -- a REVISE-level
    # plan's defects live in the bulk that "do not re-derive the unchanged plan"
    # would then skip re-deriving. Force a full review in that case.
    if record.get("decision") != "APPROVED" or not isinstance(record.get("score"), int) \
            or record["score"] < APPROVAL_THRESHOLD:
        print(FULL_REVIEW_MARKER)
        print(f"# previous verdict was {record.get('decision')} {record.get('score')} "
              f"(not approved) -- review this plan in full, not as a delta.")
        return 0

    approved = _normalized(snap_path)
    current = _normalized(ops_path)
    lines = list(difflib.unified_diff(
        approved, current,
        fromfile=f"approved/{slug}.json", tofile=f"current/{slug}.json", lineterm=""
    ))

    if not lines:
        print("(no changes since approval)")
        if sha256_of(ops_path) != record.get("ops_sha256"):
            print("# formatting-only change: no semantic difference to review")
        return 0

    changed = sum(1 for ln in lines
                 if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")))
    if approved and changed > max(DELTA_FLOOR, DELTA_CEILING * len(approved)):
        print(FULL_REVIEW_MARKER)
        print(f"# {changed} of {len(approved)} canonical lines changed "
              f"(> {int(DELTA_CEILING * 100)}%) — review this plan in full, not as a delta.")
        return 0

    # Prior findings, so the reviewer can tell whether the delta reopens one.
    # The prior SCORE is deliberately not printed here: anchoring the reviewer on
    # it biases toward reaffirming rather than re-judging.
    prior = record.get("findings") or []
    if prior:
        print("# Findings recorded at the previous review:")
        for item in prior:
            print(f"#   {item}")
    print(f"# Delta since the verdict recorded {record.get('recorded_utc')}:")
    for line in lines:
        print(line.rstrip("\n"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind a review verdict to an ops.json")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("resolve", help="Print the ops.json path a plan owns")
    r.add_argument("plan")
    r.set_defaults(func=cmd_resolve)

    w = sub.add_parser("write", help="Record a verdict against the current ops.json")
    w.add_argument("plan")
    w.add_argument("ops")
    w.add_argument("--from-review", help="File containing reviewer output, or '-' for stdin")
    w.add_argument("--score", type=int)
    w.add_argument("--decision", choices=VALID_DECISIONS)
    w.set_defaults(func=cmd_write)

    c = sub.add_parser("check", help="Verify ops.json matches an APPROVED record")
    c.add_argument("plan")
    c.add_argument("ops")
    c.set_defaults(func=cmd_check)

    d = sub.add_parser("diff", help="Unified diff: approved snapshot -> current ops.json")
    d.add_argument("plan")
    d.add_argument("ops")
    d.set_defaults(func=cmd_diff)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

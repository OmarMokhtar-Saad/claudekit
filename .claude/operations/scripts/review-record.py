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
  review-record.py write   ... [--session-id UUID]   (records a rejection brief)
  review-record.py write   ... --only-non-approving   (records rejections only)
  review-record.py check   <plan.md> <ops.json>
  review-record.py diff    <plan.md> <ops.json>
  review-record.py rejections search "<keywords>"

Exit codes:
  0  success / ops.json matches an APPROVED record
  1  usage or I/O error
  2  DRIFT - ops.json changed since approval (blocking)
  3  no approval record / could not resolve (rejections search: no match)
  4  record exists and matches, but the verdict does not authorise execution
  5  write refused: --only-non-approving given and the parsed verdict is an approval

Verdict parsing lives here rather than in shell so it can be validated and tested:
strict anchored patterns mean an echoed format template ('SCORE: <integer 0-100>')
never parses as a real score.

`write` also emits a rejection brief on the 2nd non-approving round for one ops slug
(see the `rejections` section below). That emission is FAIL-SOFT by construction: it runs
only after the record and snapshot are already on disk, it is wrapped so nothing inside it
can change this command's return value, and every sub-failure has a defined non-fatal
outcome. cmd_write is the write half of the execution-approval gate; a retro feature must
never be able to withhold an approval.

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
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
ROUND_KEYS = ("score", "decision", "findings", "recorded_utc", "ops_sha256",
               "verdict_origin")
# The review loop's documented ceiling is 3 rounds; 20 is far above any real run
# while still bounding a pathological loop. Dropping is announced, never silent.
MAX_ROUNDS = 20
# The ceiling above was documented and unenforced: nothing counted consecutive
# rejections, so a plan could be rejected six times and no machinery said a word.
# Measured case (AppiumLens, 2026-08-28): 79 -> 78 -> 72 -> 86 -> 86 -> 81 across six
# rounds and three different concurrency mechanisms, each change silently falsifying
# the javadoc, constants and tests written for its predecessor. It was caught by a
# human writing a retrospective afterwards.
#
# Note the shared window: `rounds` is already capped to MAX_ROUNDS before the tripwire
# sees it, so the peak comparison below reads the same truncated history. Harmless while
# the ceiling is 3 and the cap is 20; raising either without re-reading this is not.
LOOP_TRIPWIRE_ROUNDS = 3


def loop_advisory(rounds, decision, score):
    """Advisory lines for a plan that is not converging. Never raises, never blocks.

    Returns [] unless this write makes LOOP_TRIPWIRE_ROUNDS *consecutive* rejecting
    rounds. Consecutive, not cumulative: a plan approved once and reopened months later
    for an unrelated reason is not in a loop, and calling it one trains people to ignore
    the message.

    "Rejecting" is `is_rejecting`, not a decision-word test. `write` will record
    `SCORE: 85 / DECISION: APPROVED` -- a real verdict that does NOT authorise execution
    -- and a word-only predicate would read that as an approval and reset a live streak.
    One predicate for the whole file is the point of `is_rejecting` existing.
    """
    if not is_rejecting(score, decision):
        return []
    trail = [r for r in rounds if isinstance(r, dict)] + [
        {"score": score, "decision": decision}]
    streak = 0
    for entry in reversed(trail):
        if not is_rejecting(entry.get("score"), entry.get("decision")):
            break
        streak += 1
    if streak < LOOP_TRIPWIRE_ROUNDS:
        return []

    recent = trail[-streak:]
    scores = [e.get("score") for e in recent if isinstance(e.get("score"), int)]
    lines = [
        "LOOP TRIPWIRE: %d consecutive non-approving rounds on this plan." % streak,
        "  trail: %s" % " -> ".join(
            "%s/%s" % (e.get("score"), e.get("decision")) for e in recent),
        "  Three strikes is the documented ceiling. More rounds are the wrong tool for a",
        "  scope problem: split the user-visible fix from the latent defect, ship the fix,",
        "  and file the defect with the analysis these rounds already produced.",
    ]
    # Peaked-then-fell, which includes a PLATEAU then a fall (86 -> 86 -> 81, the shape
    # the motivating retro actually names). Testing `max > scores[0]` would miss that,
    # and testing `scores[-1] < max` alone would call a plain monotonic decline
    # non-monotonic. The discriminator is where the peak LAST occurs: after the first
    # entry means the score held or climbed before it dropped.
    if len(scores) >= 3:
        peak = max(scores)
        last_peak_idx = len(scores) - 1 - scores[::-1].index(peak)
        if last_peak_idx > 0 and scores[-1] < peak:
            lines.append(
                "  NON-MONOTONIC: the score held or rose to %d and then fell to %d -- "
                "evidence the plan is too large to converge, not that this round was "
                "sloppy." % (peak, scores[-1]))
    return lines


# Delta review stops being a saving once the change is sweeping; past this share of
# changed lines the reviewer is told to do a full review instead.
DELTA_CEILING = 0.25
DELTA_FLOOR = 40  # lines: below this, delta mode always applies regardless of ratio
FULL_REVIEW_MARKER = "# FULL REVIEW REQUIRED"

_BLOCK_RE = re.compile(r"===\s*REVIEW\s*===(.*?)===\s*END\s+REVIEW\s*===", re.S)
_SCORE_RE = re.compile(r"^SCORE:\s*(\d{1,3})\s*$", re.M)
_DECISION_RE = re.compile(r"^DECISION:\s*(%s)\s*$" % "|".join(VALID_DECISIONS), re.M)
_FINDING_RE = re.compile(r"^-\s*\[(CRITICAL|MAJOR|MINOR)\]\s*(.+)$", re.M)


# The one decision --only-non-approving refuses to record. Keyed on the DECISION WORD
# and not on the score: cmd_check authorises execution on `decision == "APPROVED"` plus a
# threshold, so refusing every APPROVED regardless of score sits strictly on the
# conservative side of that gate and needs no second opinion about numbers.
#
# CONDITIONAL is deliberately NOT here. cmd_check cannot authorise it (:395 requires the
# literal "APPROVED"), so refusing it would protect nothing -- it would only discard a
# genuinely non-approving round from the rejection corpus this feature exists to build.
# The predicate means exactly one thing: "could this verdict authorise execution?"
NON_RECORDABLE_DECISIONS = ("APPROVED",)


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


def _project_root() -> Path:
    """Nearest ancestor holding a .claude/ directory, walking up from cwd.

    Extracted so the record store and the brief store resolve the root through ONE
    function. Two copies of an ancestor walk drift the first time either changes, and a
    brief written into a different tree than its record is worse than no brief.
    """
    cur = Path.cwd()
    for candidate in (cur, *cur.parents):
        if (candidate / ".claude").is_dir():
            return candidate
    return cur


def _records_dir() -> Path:
    """Nearest .claude/reports/reviews walking up from cwd, so `check` run from a
    subdirectory does not silently report NO RECORD instead of an error."""
    return _project_root() / RECORDS_DIR


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


# --------------------------------------------------------------------------- rejections
#
# A plan can be rejected repeatedly and, until this existed, the repo kept no durable
# record of WHY. Measured on the live corpus: 80 records, 80 APPROVED, 79 of 80
# single-round -- not because review always passes, but because only the round that
# passed was ever written. The rejection signal was produced and discarded.
#
# EVERYTHING BELOW IS FAIL-SOFT BY CONSTRUCTION. cmd_write is the write half of the
# execution-approval gate: /implement and execute-json-ops.py both read what it produces.
# Three independent properties keep a retro feature from ever withholding an approval:
#   ordering    -- emit_brief runs only AFTER the record and snapshot are on disk;
#   containment -- its call site is wrapped, and nothing inside can change a return code;
#   degradation -- every sub-failure has a defined non-fatal outcome (sanitizers missing
#                  => brief skipped rather than written unsanitised; corrupt index line
#                  => skipped with a note; no session id => "unknown"; no git =>
#                  prompt_version "unknown"; symlink on the path => refuse and note).

REJECTIONS_DIR = Path(".claude/knowledge/rejections")
# Owner decision: trigger on the 2nd non-approving round for one ops slug. One rejection
# is a plan being revised; two is a pattern worth a durable record.
BRIEF_TRIGGER = 2
# A session id is recorded RAW and deliberately: it is a local transcript filename
# (~/.claude*/projects/<project>/<uuid>.jsonl), so a hash would be unresolvable and
# root-cause analysis dies. It is a filename, not a credential -- but only if it looks
# like one. Anything else is dropped rather than committed to a tracked file.
_SESSION_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
MAX_BRIEF_FINDINGS = 20


def is_rejecting(score, decision) -> bool:
    """A round whose verdict did not authorise execution.

    Deliberately the exact complement of cmd_check's gate rather than a second opinion,
    so "rejection" means one thing in this file and the brief trigger can never disagree
    with the gate about what happened.
    """
    return not (decision == "APPROVED"
                and isinstance(score, int) and score >= APPROVAL_THRESHOLD)


def _rejections_dir() -> Path:
    return _project_root() / REJECTIONS_DIR


def _sanitizers():
    """bounded_token / _safe_text from .claude/hooks/reflection.py.

    Imported by path (hooks/ is not a package) rather than reimplemented: there is ONE
    answer in this repo to "is this text safe to commit", and a second copy would drift
    from it silently. Returns None when unavailable -- in which case the brief is SKIPPED
    entirely. Writing a brief unsanitised would be the one failure mode worse than not
    writing one at all, because briefs are tracked files.
    """
    # Resolved from THIS script's own tree first, not from the analysed project's cwd:
    # reflection.py ships beside this file in every install, whereas the tree being
    # analysed may be any directory holding a .claude/. Getting that backwards silently
    # disables brief emission wherever the two differ -- and a silently disabled retro
    # feature is indistinguishable from a working one that never triggers.
    here = Path(__file__).resolve()
    candidates = []
    if len(here.parents) >= 3:
        candidates.append(here.parents[2] / "hooks" / "reflection.py")
    candidates.append(_project_root() / ".claude" / "hooks" / "reflection.py")
    path = next((c for c in candidates if c.is_file()), None)
    if path is None:
        return None
    spec = importlib.util.spec_from_file_location("_ck_reflection_sanitizers", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        # BaseException, not Exception, and deliberately: exec_module runs another
        # file's module-level code inside the process that is gating an execution
        # approval. A future top-level sys.exit() in reflection.py raises SystemExit,
        # which is NOT an Exception subclass -- it would propagate through the call
        # site's guard and make cmd_write exit non-zero AFTER the verdict is already on
        # disk, so /review would report a recording failure that actually succeeded.
        spec.loader.exec_module(module)
    except BaseException:
        return None
    if not (hasattr(module, "_safe_text") and hasattr(module, "bounded_token")):
        return None
    return module


def _digest(module, value) -> str:
    """Render one finding safely for a TRACKED file.

    _safe_text REJECTS unsafe text; bounded_token DIGESTS it. Both behaviours are wanted
    here in that order: prefer the readable original, but an absolute path or a
    credential-shaped token must never land verbatim -- and dropping the finding would
    lose the very signal the brief exists to keep. So: validate, else digest.
    """
    try:
        return module._safe_text("finding", value)
    except Exception:
        return module.bounded_token(value, "unreadable-finding")


#: Mirrors reflection.py's `_POINTER_MAX_DEPTH`: a match further away than this is
#: coincidence (a shared terminal or launchd), not a shared session.
POINTER_MATCH_MAX_DEPTH = 4


def _session_from_pointers() -> str:
    """Resolve the session id by PROOF of shared process tree, or "unknown".

    A WRONG id is strictly worse than none. transcript-miner.py would slice an unrelated
    session and flow-analyst would reason about someone else's work as the cause of this
    rejection, with nothing downstream able to detect it -- while "unknown" is honest and
    recoverable. So recency is NOT used, and that is a measurement, not a preference: on
    this host 21 transcripts were touched in two hours, the newest of them a SUBAGENT
    transcript (agent-*.jsonl), and several of the rest belonged to concurrent sessions.

    What is used: reflection.py's SessionStart hook -- the only place in the repo that
    ever sees an authoritative session id, because it arrives in the hook payload --
    records (session_id, that hook process's ancestor pids). This process intersects its
    OWN ancestor chain with those. A hit is common ancestry, not a guess, and it must be
    UNIQUE at the nearest depth: nesting resolves correctly (an inner `claude -p` shares
    the outer session's ancestors, so the nearest match wins) while two genuinely
    concurrent sessions match at the same depth and the answer is "unknown".
    """
    module = _sanitizers()
    if module is None or not hasattr(module, "session_pointers"):
        return "unknown"
    try:
        pointers = module.session_pointers()
        mine = module._ancestor_pids()
    except Exception:
        return "unknown"
    # _ancestor_pids lives in reflection.py and is NOT reimplemented here: "who is in my
    # process tree" gets one definition, the same discipline that keeps redact_secrets in
    # one file. A second copy would drift from the writer's and match nothing.
    if not mine:
        return "unknown"
    best_depth, matches = None, []
    for row in pointers:
        sid = str(row.get("session_id") or "")
        depths = [mine.index(p) for p in (row.get("pids") or []) if p in mine]
        # Bounded: everything on a host shares launchd and a terminal, so an unbounded
        # chain would make a manual invocation in the same terminal as a live session
        # "related" to it. A real caller is 1-3 hops away.
        depths = [d for d in depths if d < POINTER_MATCH_MAX_DEPTH]
        if not depths:
            continue
        # POISON, not skip. If a pointer shares my ancestry but its id is not a transcript
        # filename, the writer and reader disagree about what a valid id IS -- and skipping
        # it was demonstrated to fall through to an older, stale pointer that also shares
        # ancestry and return ITS id: a wrong answer, silently. Refusing is the only safe
        # reading of "I found something I do not understand in my own process tree".
        # The startswith is redundant while the regex is hex-and-dashes, and is kept so a
        # future widening cannot quietly re-admit subagent transcripts.
        if sid.startswith("agent-") or not _SESSION_ID_RE.match(sid):
            return "unknown"
        depth = min(depths)
        if best_depth is None or depth < best_depth:
            best_depth, matches = depth, [sid]
        elif depth == best_depth and sid not in matches:
            matches.append(sid)
    if len(matches) != 1:
        return "unknown"
    return matches[0]


def _session_id(explicit=None) -> str:
    """Explicit flag, then the env vars the hooks already agree on (dispatch.sh:185,
    lib.sh:168), then a PROVEN process-tree match, then "unknown". Never invented.

    "unknown" is a correct answer -- announced by the caller, never silent. The one live
    brief this store held was written with both env vars unset, which is the normal
    condition rather than an edge case: nothing exports them.
    """
    raw = (explicit or os.environ.get("CLAUDE_SESSION_ID")
           or os.environ.get("CLAUDEKIT_SESSION_ID") or "").strip()
    if _SESSION_ID_RE.match(raw):
        return raw
    if raw:
        print("NOTE: ignoring a session id that is not a transcript filename (%r)." % raw[:16],
              file=sys.stderr)
    return _session_from_pointers()


def _prompt_version() -> str:
    """Which prompt corpus produced this rejection.

    Without it an improvement cannot be attributed to a prompt edit at all -- the whole
    loop reduces to anecdote. Short git HEAD of the tree holding the prompts; the literal
    "unknown" when git is unavailable, never a guess.
    """
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=str(_project_root()), capture_output=True,
                             text=True, timeout=5)
    except Exception:
        return "unknown"
    value = out.stdout.strip()
    if out.returncode != 0 or not _GIT_SHA_RE.match(value):
        return "unknown"
    return value


def _index_rows(path: Path) -> list:
    """Every parseable row of INDEX.jsonl, with corrupt lines announced and skipped.

    A hand-edited, truncated or half-written index line must never be able to crash a
    write that is gating execution -- and it must never vanish silently either, because
    silent loss of history is how the corpus reached 80-of-80.
    """
    rows: list = []
    if not path.is_file():
        return rows
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print("NOTE: rejection index unreadable (%s); treated as empty." % e,
              file=sys.stderr)
        return rows
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            print("NOTE: skipping corrupt INDEX.jsonl line %d" % lineno, file=sys.stderr)
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            print("NOTE: skipping non-object INDEX.jsonl line %d" % lineno,
                  file=sys.stderr)
    return rows


def _brief_name(slug: str) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]", "_", slug).lstrip(".") or "_") + ".md"


def _append_brief(path: Path, slug: str, row: dict) -> None:
    """One appended markdown section per rejecting round.

    The `<!-- round: N -->` marker is the idempotency key on the markdown side, mirroring
    slug+round in the index, so re-running `write` for a round cannot duplicate a section.
    """
    marker = "<!-- round: %s -->" % row.get("round")
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if marker in existing:
        return
    if not existing:
        existing = (
            "# Rejection brief — `%s`\n\n"
            "Append-only; one section per non-approving review round. The session id is a "
            "local transcript filename (`transcript-miner.py <session-id> --around %s`), "
            "never a credential. Absolute paths and session tokens never appear here.\n"
            % (slug, slug)
        )
    parts = [
        existing.rstrip("\n"), "", marker,
        "## Round %s — %s (%s)" % (row.get("round"), row.get("decision"), row.get("score")),
        "",
        "- recorded: %s" % row.get("recorded_utc"),
        "- session: %s" % row.get("session_id"),
        "- prompt_version: %s" % row.get("prompt_version"),
        "- trail: %s" % " -> ".join(row.get("trail") or []),
        "- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a "
        "guessed classification is worse than an absent one)",
        "",
    ]
    if row.get("findings"):
        parts.append("### Findings")
        parts.extend("- %s" % item for item in row["findings"])
        parts.append("")
    parts.append("### 5-whys (a writing template, not a clustering method)")
    parts.extend(["1. Why was this rejected? ", "2. Why? ", "3. Why? ", "4. Why? ",
                  "5. Root cause: ", ""])
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def emit_brief(slug: str, record: dict, rounds: list,
               explicit_session_id=None) -> None:
    """Write/refresh the rejection brief for `slug`. Callers MUST wrap this (see the
    section header): it is allowed to fail, never to propagate."""
    # Trigger FIRST, sanitizers second. The order is load-bearing on a hot path: every
    # APPROVED write goes through here too, and importing another module to decide
    # nothing is pure cost -- worse, in a tree without reflection.py it would print a
    # NOTE onto the approval path about a brief that was never going to be written.
    history = list(rounds) + [{k: record.get(k) for k in ROUND_KEYS}]
    rejecting = [r for r in history if is_rejecting(r.get("score"), r.get("decision"))]
    # Both conditions matter: enough rejections to be a pattern, AND this round is one of
    # them. A plan that was rejected twice and then approved does not get a third section.
    if len(rejecting) < BRIEF_TRIGGER:
        return
    if not is_rejecting(record.get("score"), record.get("decision")):
        return

    # Resolved HERE, after the trigger and for the same reason the sanitizers are: every
    # APPROVED write reaches this function too, and spawning `ps` to decide nothing is
    # pure cost on the execution-approval path.
    session_id = _session_id(explicit_session_id)
    if session_id == "unknown":
        # VISIBLE, never silent. An unresolved id is recoverable only if someone knows it
        # happened; the one live brief in this store says "unknown" and nothing said so.
        print("WARNING: rejection brief for '%s' records session: unknown -- "
              "transcript-miner.py cannot resolve it, so /flow-retro degrades to "
              "brief-only for this round. Pass --session-id, or check that the "
              "SessionStart hook ran." % slug, file=sys.stderr)

    module = _sanitizers()
    if module is None:
        print("NOTE: reflection.py sanitizers unavailable; rejection brief skipped "
              "(briefs are tracked files and are never written unsanitised).",
              file=sys.stderr)
        return

    directory = _rejections_dir()
    for p in (directory, directory.parent, directory.parent.parent):
        if p.is_symlink():
            print("NOTE: refusing to write a brief through a symlink: %s" % p,
                  file=sys.stderr)
            return
    directory.mkdir(parents=True, exist_ok=True)
    index_path = directory / "INDEX.jsonl"
    brief_path = directory / _brief_name(slug)
    if brief_path.is_symlink() or index_path.is_symlink():
        print("NOTE: refusing to write a brief through a symlink: %s" % directory,
              file=sys.stderr)
        return

    round_no = record.get("round")
    if any(r.get("row_type", "brief") == "brief"
           and r.get("slug") == slug and r.get("round") == round_no
           for r in _index_rows(index_path)):
        return  # already indexed: re-running `write` for one round is a no-op

    row = {
        "slug": slug,
        "round": round_no,
        "session_id": session_id,
        "score": record.get("score"),
        "decision": record.get("decision"),
        "recorded_utc": record.get("recorded_utc"),
        "trail": ["%s/%s" % (r.get("score"), r.get("decision")) for r in history],
        "rejecting_rounds": len(rejecting),
        # ODC's two orthogonal axes. Recorded EMPTY on purpose: cmd_write cannot classify
        # a defect, and a wrong type label corrupts the distribution shift that is the
        # whole process signal. /flow-retro or a human fills them.
        "defect_type": "",
        "trigger": "",
        "prompt_version": _prompt_version(),
        # Provenance of the number. A reviewer-judged 60 and a code-reviewer table-derived
        # 60 are the same integer and mean nothing alike; without this field they are
        # indistinguishable in the corpus and any score trend the analyst reads is an
        # artefact of which agent happened to review.
        "verdict_origin": record.get("verdict_origin", "rubric"),
        "findings": [_digest(module, f) for f in
                     (record.get("findings") or [])][:MAX_BRIEF_FINDINGS],
    }
    with open(index_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    _append_brief(brief_path, slug, row)


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
    """argparse adapter. `write_verdict` below is the real entry point.

    cmd_record_code_review used to hand-build an argparse.Namespace to call this. It was
    correct as shipped -- every attribute the body reads happened to be present, and two
    getattr defaults covered the rest -- but correct BY INSPECTION, re-verified by hand
    every time either side changes. A keyword function is correct by construction, and
    the adapter is the one place that knows about Namespaces.
    """
    return write_verdict(
        plan=args.plan, ops=args.ops, from_review=args.from_review,
        score=args.score, decision=args.decision,
        session_id=getattr(args, "session_id", None),
        verdict_origin=getattr(args, "verdict_origin", None) or "rubric",
        only_non_approving=getattr(args, "only_non_approving", False))


def write_verdict(plan, ops, from_review=None, score=None, decision=None,
                  session_id=None, verdict_origin="rubric",
                  only_non_approving=False) -> int:
    """Record one verdict against one ops.json. The write half of the approval gate.

    Behaviour is unchanged from the argparse-driven version; the proof is that
    tests/test_review_record.py passes untouched.
    """
    ops_path = Path(ops)
    if not ops_path.exists():
        print(f"Error: ops.json not found: {ops_path}", file=sys.stderr)
        return 1

    findings = []
    if from_review:
        raw = sys.stdin.read() if from_review == "-" else \
            Path(from_review).read_text(encoding="utf-8")
        score, decision, findings = parse_verdict(raw)
        if score is None:
            print("Error: could not parse SCORE/DECISION from the review output.",
                  file=sys.stderr)
            print("       Nothing recorded — /implement will report NO RECORD.",
                  file=sys.stderr)
            return 1
    else:
        if score is None or decision is None:
            print("Error: provide --from-review, or both --score and --decision",
                  file=sys.stderr)
            return 1
        if not 0 <= score <= 100 or decision not in VALID_DECISIONS:
            print(f"Error: invalid score/decision: {score} {decision}", file=sys.stderr)
            return 1

    # ONE parser, ONE scope. Callers that may record only rejections -- /code-review,
    # where an APPROVE would otherwise authorise execution of an ops.json that review
    # never scored -- used to re-derive the decision in shell (sed/grep over the review
    # text). That duplicate parse read a DIFFERENT BLOCK than parse_verdict on any input
    # whose anchors differ in whitespace: `===\tREVIEW\t===` matches _BLOCK_RE's `\s*`
    # but not a shell glob, so a two-block review handed the filter a REJECTED from the
    # first block while this function wrote the APPROVED from the last one. Measured on
    # the shipped snippet, not theorised. Patching the shell pattern only moves the
    # mismatch to the next character class, so the decision is made HERE, from the same
    # parse that gets written, and the shell keeps no verdict logic at all.
    if only_non_approving and decision in NON_RECORDABLE_DECISIONS:
        print("REFUSED: --only-non-approving, but the parsed verdict is %s (%s)."
              % (decision, score), file=sys.stderr)
        print("         Nothing recorded. On a review path that may only record "
              "rejections this is the EXPECTED outcome, not a failure.", file=sys.stderr)
        return 5

    slug = ops_slug(ops_path)
    rec_path, snap_path = record_paths(slug)
    rec_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "plan": os.path.relpath(plan),
        "slug": slug,
        "ops_path": os.path.relpath(str(ops_path)),
        "ops_sha256": sha256_of(ops_path),
        "score": score,
        "decision": decision,
        "findings": findings,
        # How this score was arrived at: "rubric" = a reviewer judged it against the
        # 90-point rubric; "gate-token" = it was derived mechanically from a
        # blocking-finding count (code-reviewer's mapping table), where the integer is a
        # recording device and carries no quality judgement at all.
        "verdict_origin": verdict_origin or "rubric",
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

    # Advisory only. This runs BEFORE the write so the lines land in the record, and it
    # must never change what cmd_write returns: the caller's verdict has to stay durable
    # on exactly the round where knowing about the loop matters most. Same contract the
    # rejections block below documents at length.
    try:
        advisory = loop_advisory(rounds, record.get("decision"), record.get("score"))
    except Exception as e:                      # pragma: no cover - defensive
        print("WARNING: loop tripwire skipped (%s); the verdict IS recorded." % e,
              file=sys.stderr)
        advisory = []
    if advisory:
        record["loop_advisory"] = advisory
        for line in advisory:
            print(line, file=sys.stderr)

    if not _safe_write(rec_path, json.dumps(record, indent=2) + "\n"):
        return 1
    if not _safe_write(snap_path, ops_path.read_text(encoding="utf-8")):
        return 1

    # The verdict is already durable at this point. NOTHING below may change what this
    # function returns -- see the rejections section header. A bare `except Exception` is
    # correct here rather than lax: the alternative is a retro feature that can withhold
    # an execution approval, which is strictly worse than a missing brief. BaseException
    # rather than Exception because this path imports and executes another module
    # (reflection.py); a SystemExit raised there is not an Exception and would otherwise
    # escape, failing a write that has already succeeded.
    try:
        emit_brief(slug, record, rounds, session_id)
    except BaseException as e:
        print("WARNING: rejection brief not written (%s); the verdict IS recorded." % e,
              file=sys.stderr)
        # BaseException catches SystemExit, which is the point -- but it also catches
        # KeyboardInterrupt, and silently ignoring Ctrl-C on the approval path would be
        # its own defect. Warn, then let the operator's interrupt through.
        if isinstance(e, KeyboardInterrupt):
            raise

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


# ODC's two axes, adapted -- and the ONLY writer of them is `rejections classify`.
#
# The TYPE vocabulary is flow-analyst.md's own list rather than IBM's: one definition with
# two consumers (the prompt that proposes a label, the script that records it), because a
# distribution whose categories differ between writer and reader is not a distribution.
DEFECT_TYPES = ("missing-ops-json", "file-ownership", "security-surface", "scope-overflow",
                "drifted-anchor", "missing-rollback", "untested-behaviour", "other")
# TRIGGER is deliberately NOT a closed set: flow-analyst defines it as "which reviewer
# rubric line caught it", and those lines are not a stable enumeration -- a closed list
# would go stale silently and quietly mislabel. Shape is validated; membership is not.
_TRIGGER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")


def _folded_rows(rows: list) -> list:
    """Brief rows with the LATEST classification applied.

    Classifications are APPENDED, never merged in place: a correction that rewrites what
    it corrects destroys the only history this corpus has, and history is the whole point
    of the store. Readers fold; the file keeps every version.
    """
    latest: dict = {}
    for row in rows:
        if row.get("row_type") == "classification":
            latest[(row.get("slug"), row.get("round"))] = row
    out = []
    for row in rows:
        if row.get("row_type") == "classification":
            continue
        found = latest.get((row.get("slug"), row.get("round")))
        if found:
            row = dict(row, defect_type=found.get("defect_type", ""),
                       trigger=found.get("trigger", ""),
                       classified_utc=found.get("classified_utc"),
                       classified_by=found.get("classified_by"))
        out.append(row)
    return out


def _print_distribution(field: str, rows: list) -> None:
    """Counts over CLASSIFIED rows only, with the unclassified count beside them.

    Never imputed. An unclassified round is not "other": folding absent into a bucket
    produces a confident distribution over data that does not exist, which is exactly the
    failure ODC classification exists to prevent.
    """
    counts: dict = {}
    missing = 0
    for row in rows:
        value = str(row.get(field) or "").strip()
        if not value:
            missing += 1
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        print("by %s: none classified yet (`rejections classify` is the only writer; "
              "%d unclassified)" % (field, missing))
        return
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    print("by %s: %s   (unclassified=%d, NOT imputed)"
          % (field, "  ".join("%s=%d" % kv for kv in ordered), missing))


def _append_classification_section(path: Path, row: dict) -> None:
    """Mirror the classification into the markdown brief.

    Without this the brief keeps saying "(unclassified -- assigned by /flow-retro or a
    human)" while the index says otherwise, and the two readers of one fact disagree.
    """
    if not path.is_file() or path.is_symlink():
        return
    marker = "<!-- classification: round %s -->" % row.get("round")
    text = path.read_text(encoding="utf-8")
    parts = [text.rstrip("\n"), "", marker,
             "### Classification (round %s)" % row.get("round"), "",
             "- defect_type: %s" % row.get("defect_type"),
             "- trigger: %s" % row.get("trigger"),
             "- classified: %s by %s"
             % (row.get("classified_utc"), row.get("classified_by")),
             ""]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def cmd_rejections_classify(args) -> int:
    """Assign the two ODC axes to one recorded round.

    cmd_write cannot classify a defect and never tries -- a guessed label is worse than an
    absent one, because the distribution SHIFT over these axes is the entire process
    signal, and a distribution polluted by inference measures the inference. Until this
    subcommand existed the two fields shipped empty with nothing able to fill them, so the
    analytic they exist for could not run at all.

    Every write is an EXPLICIT human or analyst call, and everything unverifiable is
    refused:
      exit 3  no recorded round (slug, round) -- nothing to classify, nothing invented
      exit 1  a type outside the vocabulary, or a trigger that is not a kebab token
    """
    directory = _rejections_dir()
    index_path = directory / "INDEX.jsonl"
    rows = _index_rows(index_path)
    briefs = [r for r in rows
              if r.get("row_type", "brief") == "brief"
              and r.get("slug") == args.slug and r.get("round") == args.round]
    if not briefs:
        print("NO BRIEF: no recorded round %s for '%s'; nothing classified."
              % (args.round, args.slug), file=sys.stderr)
        print("          A classification is never written for a round that was never "
              "recorded -- see `rejections stats` for the corpus.", file=sys.stderr)
        return 3
    if args.type not in DEFECT_TYPES:
        print("Error: --type must be one of: %s" % ", ".join(DEFECT_TYPES),
              file=sys.stderr)
        return 1
    trigger = str(args.trigger or "").strip().casefold()
    if not _TRIGGER_RE.match(trigger):
        print("Error: --trigger must be a kebab-case token (3-40 chars) naming the "
              "reviewer rubric line that caught it.", file=sys.stderr)
        return 1
    for candidate in (directory, index_path):
        if candidate.is_symlink():
            print("Error: refusing to write through a symlink: %s" % candidate,
                  file=sys.stderr)
            return 1
    row = {
        "row_type": "classification",
        "slug": args.slug,
        "round": args.round,
        "defect_type": args.type,
        "trigger": trigger,
        "classified_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classified_by": str(args.by or "human").strip()[:40],
    }
    with open(index_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    _append_classification_section(directory / _brief_name(args.slug), row)
    print("Classified %s round %s: defect_type=%s trigger=%s"
          % (args.slug, args.round, args.type, trigger))
    print("  Appended. Earlier classifications are kept; readers take the last.")
    return 0


#: Hard cap on entries read from any single transcript. A transcript is routinely tens of
#: megabytes; backfill streams, but a runaway file must not turn a report into a hang.
BACKFILL_MAX_ENTRIES = 20000
#: How much run-up is searched for the ops/plan the verdict is about.
BACKFILL_WINDOW = 6
#: The whole FILENAME is captured and then normalised through ops_slug()/plan_slug().
#: Capturing the stem directly produced "contract-layer-c-pin.ops" for
#: ops-contract-layer-c-pin.ops.json while the live record keys it "contract-layer-c-pin"
#: -- a backfilled row under a slug that can never join its own live history, so trend
#: folding would silently never happen.
_SLUG_MENTION_RE = re.compile(
    r"\b((?:ops|plan)-[A-Za-z0-9][A-Za-z0-9._-]{2,60}\.(?:json|md))\b")


def _miner():
    """transcript-miner.py, imported by path.

    Imported rather than reimplemented: this repo has exactly ONE reader of Claude Code's
    transcript format, written against a survey of the real corpus after a synthetic
    fixture hid a raw-JSON dump and a host-path leak. A second parser here would be a
    second thing to get that wrong.
    """
    path = Path(__file__).resolve().parent / "transcript-miner.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_ck_transcript_miner", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        return None
    needed = ("iter_project_transcripts", "iter_texts", "VERDICT_RE")
    return module if all(hasattr(module, name) for name in needed) else None


def cmd_rejections_backfill(args) -> int:
    """Reconstruct briefs for rejections that predate the capture path.

    166 session transcripts hold every review this repo ran before `cmd_write` started
    emitting briefs. That history is real and it is the only source for it -- but a
    transcript-derived verdict is RECONSTRUCTED, not recorded, and it is marked as such
    everywhere it lands. Four properties keep it honest:

      - **Dry run is the default.** Writing requires --write. The report states what it
        WOULD write, and why each skip was skipped, before anything is written.
      - **Rows are distinguishable.** `source="backfill"`, `verdict_origin="reconstructed"`
        and a NEGATIVE round. The transcript does not carry a round number; a negative
        ordinal (oldest first per slug) preserves the one (slug, round) idempotency key
        every other reader already uses and can never collide with a live round.
      - **It writes ONLY the brief store.** A reconstructed verdict must never reach
        `.claude/reports/reviews/`, because that is the file `cmd_check` authorises
        execution from.
      - **Attribution refuses rather than guesses.** Zero or more than one candidate slug
        in the verdict's window means SKIPPED and counted -- never the likeliest one.

    Only non-approving verdicts are taken (`is_rejecting`, the same predicate as
    everywhere else), so backfill cannot introduce a row that reads as an approval.
    """
    miner = _miner()
    if miner is None:
        print("Error: transcript-miner.py is unavailable; nothing can be read.",
              file=sys.stderr)
        return 1
    module = _sanitizers()
    scrub = getattr(module, "redact_secrets", None) if module is not None else None
    if module is None or not callable(scrub):
        # FAIL CLOSED, never a silent downgrade: transcripts carry .env reads, `env`
        # dumps and git remotes with tokens, and this output goes to stdout AND into a
        # tracked file. No scrubber, no read.
        print("Error: reflection.py's redact_secrets is unavailable; refusing to read "
              "transcript text at all.", file=sys.stderr)
        return 1

    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(
                tzinfo=timezone.utc).timestamp()
        except ValueError:
            print("Error: --since expects YYYY-MM-DD.", file=sys.stderr)
            return 1

    directory = _rejections_dir()
    index_path = directory / "INDEX.jsonl"
    existing = {(r.get("slug"), r.get("round")) for r in _index_rows(index_path)}
    project_root = args.project_root or str(_project_root())
    roots = miner.transcript_roots(project_root)
    available = miner.iter_project_transcripts(project_root)
    # Counted BEFORE slicing: reporting "200 (of 200 offered)" would hide that 1819 of
    # 2019 were dropped, and a scope the operator cannot see is a scope they cannot check.
    transcripts = available[:args.limit]

    scanned = skipped_old = blocks = unparseable = approving = unattributable = 0
    per_slug: dict = {}
    rows: list = []
    for path in transcripts:
        try:
            if since is not None and path.stat().st_mtime < since:
                skipped_old += 1
                continue
        except OSError:
            continue
        session_id = path.stem
        if not _SESSION_ID_RE.match(session_id):
            continue
        scanned += 1
        window: list = []
        for index, text in miner.iter_texts(path):
            if index > BACKFILL_MAX_ENTRIES:
                break
            if not text:
                continue
            window.append(text)
            window = window[-BACKFILL_WINDOW:]
            if not miner.VERDICT_RE.search(text):
                continue
            blocks += 1
            score, decision, findings = parse_verdict(text)
            if score is None:
                unparseable += 1
                continue
            if not is_rejecting(score, decision):
                approving += 1
                continue
            slugs = set()
            for chunk in window:
                slugs.update(_SLUG_MENTION_RE.findall(chunk))
            if len(slugs) != 1:
                unattributable += 1
                continue
            slug = slugs.pop()
            slug = plan_slug(slug) if slug.endswith(".md") else ops_slug(slug)
            sequence = per_slug.get(slug, 0) + 1
            per_slug[slug] = sequence
            round_no = -sequence
            if (slug, round_no) in existing:
                continue
            rows.append({
                "slug": slug,
                "round": round_no,
                "session_id": session_id,
                "score": score,
                "decision": decision,
                "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trail": ["%s/%s" % (score, decision)],
                "rejecting_rounds": sequence,
                "defect_type": "",
                "trigger": "",
                "prompt_version": "unknown",
                # Excluded from every score trend, exactly like gate-token rows: this
                # integer was reconstructed from text, not judged against a rubric.
                "verdict_origin": "reconstructed",
                "source": "backfill",
                "confidence": "reconstructed-from-transcript",
                "findings": [_digest(module, scrub(f)) for f in (findings or [])
                             ][:MAX_BRIEF_FINDINGS],
            })

    print("project scope:           %s" % miner.project_dir_name(project_root))
    for root in roots:
        # The ACCOUNT directory, not the project directory: this repo is driven from two
        # logins, so both roots have the identical project name and printing it twice
        # reads like a bug. Home-relative by construction -- no host path is emitted.
        print("  account root:          %s" % root.parent.parent.name)
    if not roots:
        print("  root:                  (none resolved -- scanning nothing, by design)")
    print("transcripts available:   %d for THIS project (agent-* excluded)"
          % len(available))
    print("transcripts scanned:     %d (--limit %d, %d older than --since)"
          % (scanned, args.limit, skipped_old))
    print("verdict blocks found:    %d" % blocks)
    print("  unparseable:           %d" % unparseable)
    print("  approving (skipped):   %d" % approving)
    print("  unattributable:        %d  (0 or >1 candidate slug -- never guessed)"
          % unattributable)
    print("rows to write:           %d  (source=backfill, negative rounds)" % len(rows))
    for row in rows[:3]:
        print("  sample: %s round %s  %s/%s  session=%s"
              % (row["slug"], row["round"], row["score"], row["decision"],
                 row["session_id"]))
    if not args.write:
        print("")
        print("DRY RUN: nothing was written. Re-run with --write to record these rows.")
        return 0
    if not rows:
        print("Nothing to write.")
        return 0
    for candidate in (directory, directory.parent, index_path):
        if candidate.is_symlink():
            print("Error: refusing to write through a symlink: %s" % candidate,
                  file=sys.stderr)
            return 1
    directory.mkdir(parents=True, exist_ok=True)
    with open(index_path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in rows:
        _append_brief(directory / _brief_name(row["slug"]), row["slug"], row)
    print("")
    print("Wrote %d reconstructed row(s). They are marked source=backfill and carry "
          "negative rounds; nothing was written to .claude/reports/reviews/." % len(rows))
    return 0


def cmd_rejections_search(args) -> int:
    """Keyword retrieval over the rejection briefs.

    Mirrors `knowledge-ledger.py search` deliberately -- same exit contract (0 = hit,
    3 = no match), same "this is a prior, not a proof" close, same "silence is not
    evidence" note -- so planner.md's Phase 0 reads identically for both stores and a
    model cannot learn two different retrieval habits.

    Without this subcommand and its caller the briefs are an archive, not a feedback
    loop: writing history that nothing ever reads changes no behaviour at all.
    """
    query = " ".join(args.query).strip()
    if not query:
        print("rejections search: empty query", file=sys.stderr)
        return 1
    tokens = {t for t in re.findall(r"[a-z0-9_.-]{3,}", query.casefold())}
    if not tokens:
        print("rejections search: no searchable token in query", file=sys.stderr)
        return 1

    directory = _rejections_dir()
    scored = []
    for row in _folded_rows(_index_rows(directory / "INDEX.jsonl")):
        blob = json.dumps(row, ensure_ascii=False).casefold()
        hits = sorted(t for t in tokens if t in blob)
        if hits:
            scored.append((len(hits), row, hits))

    if not scored:
        print("REJECTIONS: no match for %r." % query)
        print("            Silence is NOT evidence: this means unknown, not "
              "'never rejected for this'.")
        return 3

    scored.sort(key=lambda item: (-item[0], str(item[1].get("slug"))))
    print("REJECTIONS: %d match(es) for %r" % (len(scored), query))
    blind = sum(1 for _, row, _ in scored
                if (row.get("session_id") or "unknown") == "unknown")
    if blind:
        print("            %d of them record session: unknown -- brief-only, with no "
              "transcript to mine." % blind)
    for _, row, hits in scored[:args.limit]:
        print("")
        print("  slug:       %s (round %s, %s %s)"
              % (row.get("slug"), row.get("round"), row.get("decision"), row.get("score")))
        # Relative, like transcript-miner.py's output and for the same reason: this
        # lands in planner.md's Phase 0, whose output routinely ends up in a committed
        # plan file. An absolute path there trips the secret self-scan.
        brief_path = directory / _brief_name(str(row.get("slug")))
        try:
            shown = os.path.relpath(str(brief_path), str(_project_root()))
        except ValueError:
            shown = brief_path.name
        print("  brief:      %s" % shown)
        print("  session:    %s   prompt_version: %s"
              % (row.get("session_id"), row.get("prompt_version")))
        print("  trail:      %s" % " -> ".join(row.get("trail") or []))
        print("  ODC:        defect_type=%s trigger=%s"
              % (row.get("defect_type") or "(unclassified)",
                 row.get("trigger") or "(unclassified)"))
        print("  matched:    %s" % ", ".join(hits))
        for finding in (row.get("findings") or [])[:3]:
            print("    - %s" % finding)
    print("")
    print("These are PRIORS, not proofs: verify each against the current tree before "
          "acting on it. A brief describes a plan that was rejected, not a rule.")
    return 0


def cmd_record_code_review(args) -> int:
    """Record a code review's verdict against the ops.json behind the implementation.

    Every line of this used to be bash inside /code-review -- which is why that command
    ran 86 lines over its budget, and shell was the wrong home for it anyway: each skip
    has to be ANNOUNCED (a silent skip is how this path stayed dead through three review
    rounds), and the decision has to come from parse_verdict rather than a second reader.

    Returns 0 for every normal outcome -- recorded, or deliberately not recorded. A code
    review must not fail because there was nothing to record.
    """
    report = Path(args.report)
    if not report.is_file() or report.stat().st_size == 0:
        print("no review report at %s; nothing recorded (run Step 5b first)." % report,
              file=sys.stderr)
        return 0
    plan = (args.plan or "").strip()
    if not plan:
        print("no plan found in .claude/plans/; nothing recorded.", file=sys.stderr)
        return 0
    ops_path = resolve_ops(plan)
    if ops_path is None:
        print("no ops.json resolved for %s; nothing recorded."
              % os.path.basename(plan), file=sys.stderr)
        return 0

    # Say WHICH artifacts the defaults resolved to: the caller's `ls -t` picks the newest
    # plan, and a mis-bind here would record a verdict against the wrong ops.json.
    print("code-review verdict -> plan: %s" % os.path.basename(plan), file=sys.stderr)
    print("code-review verdict -> ops:  %s" % os.path.basename(str(ops_path)),
          file=sys.stderr)

    code = write_verdict(
        plan=plan, ops=str(ops_path), from_review=str(report),
        session_id=getattr(args, "session_id", None),
        verdict_origin="gate-token", only_non_approving=True)
    # 5 = the verdict was approving and was deliberately NOT recorded: the expected,
    # quiet outcome of a passing review, never a warning.
    if code not in (0, 5):
        print("WARNING: code-review verdict not recorded (write exit %d)." % code,
              file=sys.stderr)
    return 0


def cmd_rejections_stats(args) -> int:
    """Corpus size, plus the ODC distributions when --by-type is given.

    A thin wrapper rather than an edit inside the counter: the two concerns land in
    different phases, and a distribution printer bolted into the middle of the
    sample-size counter would make neither reviewable on its own.
    """
    code = _stats_core(args)
    rows = _folded_rows(_index_rows(_rejections_dir() / "INDEX.jsonl"))
    print("classified=%d of %d brief(s)"
          % (sum(1 for r in rows if str(r.get("defect_type") or "").strip()), len(rows)))
    if getattr(args, "by_type", False):
        _print_distribution("defect_type", rows)
        _print_distribution("trigger", rows)
    return code


def _stats_core(args) -> int:
    """Corpus size for /flow-retro's sample-size gate.

    Here rather than as a python heredoc inside the command: _index_rows already skips a
    corrupt INDEX line with a note, and a second copy of that logic in shell is one more
    place for the two readers to disagree.
    """
    # Folded: a classification row is a correction to a brief, never a brief
    # itself, so it must not inflate the sample-size gate the retro reads.
    rows = _folded_rows(_index_rows(_rejections_dir() / "INDEX.jsonl"))
    sessions = {r.get("session_id") for r in rows} - {None, "", "unknown"}
    # Unresolvable briefs are REPORTED, not quietly excluded from the session count. A
    # brief whose session cannot be reached is brief-only for root-cause mining, and the
    # sample-size gate should be read knowing how much of the corpus is in that state.
    unresolved = sum(1 for r in rows
                     if (r.get("session_id") or "unknown") == "unknown")
    print("briefs=%d slugs=%d sessions=%d unresolved_sessions=%d"
          % (len(rows), len({r.get("slug") for r in rows}), len(sessions), unresolved))
    if unresolved:
        print("NOTE: %d brief(s) record session: unknown -- no transcript can be mined "
              "for them; those rounds are brief-only." % unresolved, file=sys.stderr)
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
    w.add_argument("--session-id", dest="session_id", default=None,
                   help="Session UUID for the rejection brief (default: $CLAUDE_SESSION_ID)")
    w.add_argument("--verdict-origin", dest="verdict_origin",
                   choices=("rubric", "gate-token"), default="rubric",
                   help="How the score was arrived at: judged against the rubric, or "
                        "derived from a blocking-finding count (code-reviewer)")
    w.add_argument("--only-non-approving", dest="only_non_approving",
                   action="store_true",
                   help="Refuse to write an approving verdict (exit 5): for callers that "
                        "may record rejections but must never authorise execution")
    w.set_defaults(func=cmd_write)

    rcr = sub.add_parser("record-code-review",
                         help="Record a code review's non-approving verdict "
                              "(an approving one is never recorded)")
    rcr.add_argument("--report", required=True, help="File holding the review verbatim")
    rcr.add_argument("--plan", default="", help="Plan whose ops.json produced the code")
    rcr.add_argument("--session-id", dest="session_id", default=None,
                     help="Session UUID for the rejection brief; resolved from the "
                          "SessionStart pointer when omitted, else recorded as unknown")
    rcr.set_defaults(func=cmd_record_code_review)

    c = sub.add_parser("check", help="Verify ops.json matches an APPROVED record")
    c.add_argument("plan")
    c.add_argument("ops")
    c.set_defaults(func=cmd_check)


    rej = sub.add_parser("rejections", help="Query the rejection-brief store")
    rej_sub = rej.add_subparsers(dest="rejections_command", required=True)
    rej_search = rej_sub.add_parser("search", help="keyword retrieval over the briefs")
    rej_search.add_argument("query", nargs="+")
    rej_search.add_argument("--limit", type=int, default=5)
    rej_search.set_defaults(func=cmd_rejections_search)
    rej_stats = rej_sub.add_parser("stats",
                                   help="corpus size for the retro sample-size gate")
    rej_stats.add_argument("--by-type", dest="by_type", action="store_true",
                           help="also print the ODC defect_type/trigger distributions")
    rej_stats.set_defaults(func=cmd_rejections_stats)
    rej_cls = rej_sub.add_parser(
        "classify", help="assign ODC defect_type/trigger to one recorded round")
    rej_cls.add_argument("slug")
    rej_cls.add_argument("round", type=int)
    rej_cls.add_argument("--type", dest="type", required=True, choices=DEFECT_TYPES)
    rej_cls.add_argument("--trigger", dest="trigger", required=True,
                         help="kebab token naming the rubric line that caught it")
    rej_cls.add_argument("--by", dest="by", default="human",
                         help="who made the call (human | flow-analyst | ...)")
    rej_cls.set_defaults(func=cmd_rejections_classify)
    rej_bf = rej_sub.add_parser(
        "backfill", help="reconstruct briefs from session transcripts (dry run by default)")
    rej_bf.add_argument("--limit", type=int, default=200,
                        help="most recent transcripts to scan (default 200)")
    rej_bf.add_argument("--since", default=None, help="ignore transcripts older than YYYY-MM-DD")
    rej_bf.add_argument("--project-root", dest="project_root", default=None,
                        help="project whose transcripts to scan (default: this repo). "
                             "Transcripts of OTHER projects are never read.")
    rej_bf.add_argument("--write", action="store_true",
                        help="actually write; without it this reports and writes NOTHING")
    rej_bf.set_defaults(func=cmd_rejections_backfill)
    d = sub.add_parser("diff", help="Unified diff: approved snapshot -> current ops.json")
    d.add_argument("plan")
    d.add_argument("ops")
    d.set_defaults(func=cmd_diff)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

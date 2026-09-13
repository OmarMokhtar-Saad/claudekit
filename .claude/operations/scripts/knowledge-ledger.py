#!/usr/bin/env python3
"""knowledge-ledger.py - project-local, per-issue knowledge ledger.

Stores one markdown entry per diagnosed-and-fixed issue under
`.claude/knowledge/issues/<slug>.md` so a later session can look up a known root
cause instead of re-diagnosing a bug this project already fixed.

Subcommands:
  search   keyword / error-signature retrieval (debugger agent, Phase 0)
  open     record a finding at DISCOVERY time (status: open, verified: false)
  record   write gate - fires only at the Verifier PASS checkpoint (status: fixed)
  close    retire a finding deliberately not fixed (status: wontfix)
  list     show every entry (filterable by --status / --origin)
  prune    archive entries whose referenced files no longer exist

`open` and `record` are deliberately DIFFERENT subcommands, not one command with a
flag: `verified: true` has exactly one writer (`record`), and `record` keeps both of
its refusals (--verified required, combined rubric score >= threshold). `open` never
relaxes them - it only gives the ledger an upstream earlier than the Verifier.

Exit codes:
  0  success (search: at least one match; prune: nothing stale / archived)
  1  refused by the write gate, or prune found stale entries without --apply
  2  usage or input error
  3  search ran fine but found no match -> caller diagnoses from scratch

Scoring is NOT invented here: the reusability/novelty rubric comes from
`.claude/skills/continuous-learning/SKILL.md` (combined >= 10 => extract). The
threshold is read at runtime from `.claude/hooks/config.json`
(`continuous_learning.issue_ledger.min_combined_score`) so the documented config
block and this gate cannot drift apart; an absent or invalid key falls back to 10.
Python stdlib only, Python 3.9+, no vector store, no index - plain keyword grep.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date as _date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
TOKEN_RE = re.compile(r"[a-z0-9_.]{2,}")
DEFAULT_MIN_COMBINED_SCORE = 10  # continuous-learning rubric: reusability + novelty
CONFIG_REL = (".claude", "hooks", "config.json")
# A file token carrying any of these would corrupt the `files: [a, b]` frontmatter
# line that prune's split_files() reads back, so it is refused at write time.
FORBIDDEN_FILE_CHARS = "[],\"'\r\n"
DEFAULT_LIMIT = 5
# Lifecycle. An entry with NO `status:` key reads as "fixed" - every entry written
# before this key existed carries `verified: true`, so that is the only honest reading.
STATUSES = ("open", "fixed", "wontfix", "regressed")
# A `status:` value that is present but unrecognized (a typo, or the tail of a
# corrupted frontmatter block). It is NOT "fixed": reading it as fixed made prune
# archive live findings on a one-character typo, so it reads as unfixed instead.
MALFORMED_STATUS = "malformed"
UNFIXED = ("open", "regressed", MALFORMED_STATUS)  # never archived by prune; a live signal
# `date:` is the ONE frontmatter value that cannot be flattened by scalar() into
# something inert: a single line containing `---` still terminates the frontmatter
# block early, which hides the real status/verified lines from parse_entry() and makes
# an unverified entry read as a verified fix. A whitelist is the only safe contract.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TERMINAL = ("fixed", "wontfix")      # `open` refuses over these unless --reopen
DEFAULT_STATUS = "fixed"
ORIGINS = ("code", "workflow", "project")
DEFAULT_ORIGIN = "code"


def project_root() -> Path:
    """Repo root: explicit env override, else git toplevel, else cwd."""
    env = os.environ.get("CLAUDEKIT_PROJECT_ROOT")
    if env:
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except Exception:
        pass
    return Path.cwd()


def ledger_dir() -> Path:
    env = os.environ.get("CLAUDEKIT_LEDGER_DIR")
    if env:
        return Path(env)
    return project_root() / ".claude" / "knowledge" / "issues"


def min_combined_score() -> int:
    """Rubric threshold, read from `.claude/hooks/config.json`.

    Key: `continuous_learning.issue_ledger.min_combined_score`. The same block is
    documented in `.claude/skills/continuous-learning/SKILL.md`; reading it here is
    what stops that doc and this gate from drifting apart. A missing file, malformed
    JSON, a missing key or a non-integer value all fall back to the rubric default
    (10) - configuration is never allowed to break the gate open.
    """
    try:
        data = json.loads(project_root().joinpath(*CONFIG_REL).read_text(encoding="utf-8"))
        value = data["continuous_learning"]["issue_ledger"]["min_combined_score"]
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_MIN_COMBINED_SCORE
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_MIN_COMBINED_SCORE
    return value


DEFAULT_TTL_DAYS = 90
PROPOSAL_MIN_CLUSTER = 3
# Signature tokens too common to mean two findings are the same class.
_STOPWORDS = frozenset({"the", "and", "for", "with", "not", "was", "from", "that", "this"})


# Evidence beats a clock. `ck memory` (src/claudekit/memory.py) already decides staleness
# by re-hashing the files a claim rests on, and an `open` finding gets the same rule here:
# a finding is retired because the code it described moved on, not because time passed.
# The TTL is the FALLBACK for an entry citing no evidence - there is nothing to re-derive,
# so a clock is all that is left. Stdlib hashlib, not an import of src/: ops scripts stay
# standalone (hard rule 8).
def evidence_hash(root: Path, rel: str) -> str:
    """`<rel>@sha256:<hex>` for one repo-relative path, or `<rel>@missing`."""
    try:
        digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    except OSError:
        return "%s@missing" % rel
    return "%s@sha256:%s" % (rel, digest)


def split_evidence(stamp: str) -> Tuple[str, str]:
    """(path, hash) for one stamp; a stamp with no '@' reads as an unhashable path."""
    rel, _, digest = stamp.partition("@")
    return rel.strip(), digest.strip()


def evidence_superseded(root: Path, meta: Dict[str, str]) -> bool:
    """True when EVERY cited evidence file has moved on (changed or gone).

    All, never any: one unchanged file means the finding still describes live code. An
    entry citing no evidence is never superseded by this rule - it falls to the TTL.
    """
    stamps = split_files(meta.get("evidence", ""))
    if not stamps:
        return False
    for stamp in stamps:
        rel, digest = split_evidence(stamp)
        if not rel or evidence_hash(root, rel) == "%s@%s" % (rel, digest):
            return False
    return True


def entry_age_days(meta: Dict[str, str], today: _date) -> int:
    """Whole days since `date:`; -1 when the date is unusable, so it never expires."""
    raw = safe_date(meta.get("date", ""))
    if not raw:
        return -1
    try:
        return (today - _date.fromisoformat(raw)).days
    except ValueError:
        return -1


def entry_paths(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.md") if p.name != "README.md")


def parse_entry(path: Path) -> Dict[str, str]:
    """Parse the `key: value` frontmatter of an entry. Never raises."""
    meta: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return meta
    meta["_body"] = text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return meta
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta


def split_files(value: str) -> List[str]:
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [f.strip().strip("'\"") for f in raw.split(",") if f.strip()]


def parse_files(raw: str) -> List[str]:
    """Split and validate --files so the written `files:` line round-trips.

    prune reads that line back with split_files(), which strips one surrounding
    bracket pair and splits on commas. A path containing '[', ']', ',', a quote or a
    newline would therefore be misparsed on read-back - and a misparsed file list can
    make prune archive an entry whose files are all still present. Such tokens are
    rejected at write time (exit 2) rather than silently mangled.

    Raises ValueError carrying the offending token.
    """
    files: List[str] = []
    for token in raw.split(","):
        token = token.strip().strip("'\"")
        if not token:
            continue
        if any(ch in token for ch in FORBIDDEN_FILE_CHARS):
            raise ValueError(token)
        files.append(token)
    return files


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def tokenize(text: str) -> Set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def scalar(value: str) -> str:
    """Flatten a value so it is safe on one frontmatter line."""
    return " ".join(value.replace('"', "'").split())


def entry_status(meta: Dict[str, str]) -> str:
    """Lifecycle status of a parsed entry.

    Two readings that must NOT be conflated:
      * key ABSENT   -> `fixed`. Every entry written before this key existed carries
        `verified: true`, so that is the only honest reading of history.
      * key PRESENT but unrecognized -> `malformed`, which counts as UNFIXED. Reading a
        typo as `fixed` let prune archive a live finding, which is the silent-retirement
        failure this lane exists to prevent. Fail closed on the data-destroying path.
    """
    if "status" not in meta:
        return DEFAULT_STATUS
    value = meta.get("status", "").strip()
    return value if value in STATUSES else MALFORMED_STATUS


def safe_date(value: str) -> str:
    """An ISO date, or "" if the value is anything else. Never raises."""
    value = value.strip()
    return value if DATE_RE.match(value) else ""


def safe_origin(value: str) -> str:
    """Normalize a parsed `origin:` value; anything unrecognized reads as the default."""
    value = value.strip()
    return value if value in ORIGINS else DEFAULT_ORIGIN


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def score_entry(meta: Dict[str, str], tokens: Set[str], phrase: str) -> Tuple[int, Set[str]]:
    signature = meta.get("signature", "").lower()
    body = meta.get("_body", "").lower()
    hit = {t for t in tokens if t in body}
    score = len(hit) + 2 * len({t for t in tokens if t in signature})
    if phrase and phrase in signature:
        score += 5
    return score, hit


def cmd_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip()
    if not query:
        print("search: empty query", file=sys.stderr)
        return 2
    tokens = tokenize(query)
    phrase = normalize(query)
    directory = ledger_dir()
    scored = []
    for path in entry_paths(directory):
        meta = parse_entry(path)
        score, hit = score_entry(meta, tokens, phrase)
        if score > 0:
            scored.append((score, path, meta, hit))
    if not scored:
        print("LEDGER: no match - diagnose from scratch (and record the result on PASS).")
        return 3
    scored.sort(key=lambda item: (-item[0], item[1].name))
    print("LEDGER: %d match(es) for %r" % (len(scored), query))
    for score, path, meta, hit in scored[: args.limit]:
        print("")
        print("  entry:      %s" % path)
        print("  score:      %d (matched: %s)" % (score, ", ".join(sorted(hit)) or "-"))
        print("  signature:  %s" % meta.get("signature", "?"))
        print("  root_cause: %s" % meta.get("root_cause", "?"))
        print("  fix:        %s" % meta.get("fix", "?"))
        print("  files:      %s" % meta.get("files", "?"))
        print("  status:     %s  origin: %s  plan: %s"
              % (entry_status(meta), safe_origin(meta.get("origin", "")),
                 meta.get("plan", "-") or "-"))
        print("  date:       %s  verified: %s" % (meta.get("date", "?"), meta.get("verified", "?")))
    print("")
    if any(entry_status(m) in UNFIXED for _, _, m, _ in scored[: args.limit]):
        print("At least one match is UNFIXED (status: open/regressed): report the finding and "
              "the plan: that closes it - do not re-diagnose it as new.")
    print("Report the known root cause/fix above; re-diagnose only if the evidence contradicts it.")
    return 0


# ---------------------------------------------------------------------------
# record (the write gate)
# ---------------------------------------------------------------------------

def render_entry_text(slug: str, signature: str, root_cause: str, fix: str,
                      files: List[str], date: str, status: str, origin: str,
                      plan: str, severity: str, verified: bool,
                      extra: List[str],
                      evidence: Optional[List[str]] = None) -> str:
    """Render one entry. Every free-text value passes through scalar() before it lands
    on a frontmatter line, so no writer can break the one-line `key: value` contract.

    `date` is whitelisted rather than flattened: scalar() cannot make a `---` inert, and
    a stray `---` inside frontmatter terminates the block early, hiding the real
    status/verified lines from every reader. A caller that reaches here with a bad date
    has already been refused at the CLI boundary; this is the second line of defense."""
    if not DATE_RE.match(date):
        raise ValueError("date must be ISO YYYY-MM-DD, got %r" % date)
    head = [
        "---",
        'signature: "%s"' % scalar(signature),
        'root_cause: "%s"' % scalar(root_cause),
        'fix: "%s"' % scalar(fix),
        "files: [%s]" % ", ".join(files),
        "date: %s" % date,
        "status: %s" % status,
        "origin: %s" % origin,
    ]
    if evidence:
        # Same one-line `key: [a, b]` contract as `files:`, read back by
        # split_files(). Each stamp is `<path>@sha256:<hex>`.
        head.append("evidence: [%s]" % ", ".join(evidence))
    if plan:
        head.append("plan: %s" % scalar(plan))
    if severity:
        head.append("severity: %s" % scalar(severity))
    head.extend([
        "verified: %s" % ("true" if verified else "false"),
        "---",
        "",
        "# %s" % slug,
        "",
        "## Signature",
        "",
        scalar(signature),
        "",
        "## Root cause",
        "",
        root_cause.strip() or "(not diagnosed yet - status: %s)" % status,
        "",
        "## Fix",
        "",
        fix.strip() or "(not fixed yet - status: %s)" % status,
        "",
        "## Files",
        "",
    ])
    head.extend(["- %s" % f for f in files] or ["- (none recorded)"])
    head.extend(extra)
    return "\n".join(head)


def render_fixed(args: argparse.Namespace, files: List[str], combined: int, threshold: int,
                 origin: str, plan: str, severity: str,
                 evidence: Optional[List[str]] = None) -> str:
    return render_entry_text(
        args.slug, args.signature, args.root_cause, args.fix, files,
        args.date or _date.today().isoformat(), "fixed", origin, plan, severity, True,
        [
            "",
            "## Scoring (continuous-learning rubric)",
            "",
            "reusability: %d | novelty: %d | combined: %d (threshold %d)"
            % (args.reusability, args.novelty, combined, threshold),
            "",
            "Recorded at the Verifier PASS checkpoint.",
            "",
        ],
        evidence=evidence,
    )


def render_open(args: argparse.Namespace, files: List[str], origin: str, plan: str,
                severity: str, status: str,
                evidence: Optional[List[str]] = None) -> str:
    return render_entry_text(
        args.slug, args.signature, "", "", files,
        args.date or _date.today().isoformat(), status, origin, plan, severity, False,
        [
            "",
            "## Status",
            "",
            "Opened at discovery time and NOT verified. Only `record --verified` with a "
            "combined rubric score at or above the threshold may move this entry to "
            "`fixed`; `close --status wontfix --reason \"...\"` retires it unfixed.",
            "",
        ],
        evidence=evidence,
    )


def render_closed(slug: str, meta: Dict[str, str], files: List[str], status: str,
                  reason: str) -> str:
    return render_entry_text(
        slug, meta.get("signature", ""), meta.get("root_cause", ""), meta.get("fix", ""),
        files, safe_date(meta.get("date", "")) or _date.today().isoformat(), status,
        safe_origin(meta.get("origin", "")), meta.get("plan", ""),
        meta.get("severity", ""), False,
        [
            "",
            "## Not fixed (%s)" % status,
            "",
            scalar(reason),
            "",
        ],
        # Closing a finding must not drop its provenance: the evidence
        # stamps are what tell a later prune that the code this entry
        # described has moved on.
        evidence=split_files(meta.get("evidence", "")) or None,
    )


# ---------------------------------------------------------------------------
# open / close (discovery-time writers - they can never write verified: true)
# ---------------------------------------------------------------------------

def cmd_open(args: argparse.Namespace) -> int:
    if not SLUG_RE.match(args.slug):
        print("open: invalid slug %r (expected ^[a-z0-9][a-z0-9._-]{0,63}$)" % args.slug,
              file=sys.stderr)
        return 2
    if not args.signature.strip():
        print("open: --signature must be non-empty", file=sys.stderr)
        return 2
    if args.origin not in ORIGINS:
        print("open: invalid --origin %r (expected one of %s)"
              % (args.origin, ", ".join(ORIGINS)), file=sys.stderr)
        return 2
    if args.date and not DATE_RE.match(args.date.strip()):
        print("open: invalid --date %r - expected ISO YYYY-MM-DD. A date carrying a "
              "newline or '---' terminates the frontmatter block early, which makes an "
              "unverified entry read as a verified fix." % args.date, file=sys.stderr)
        return 2
    try:
        files = parse_files(args.files or "")
    except ValueError as exc:
        print("open: invalid --files entry %r - a file path may not contain '[', ']', "
              "',', a quote or a newline; those corrupt the `files:` frontmatter that "
              "prune parses back." % str(exc), file=sys.stderr)
        return 2

    directory = ledger_dir()
    target = directory / ("%s.md" % args.slug)
    signature = normalize(args.signature)
    for path in entry_paths(directory):
        if path.name == target.name:
            continue
        if normalize(parse_entry(path).get("signature", "")) == signature:
            print("open: REFUSED - signature already recorded in %s (update that entry "
                  "instead of opening a second one)." % path.name, file=sys.stderr)
            return 1

    status = "open"
    if target.exists():
        prior = entry_status(parse_entry(target))
        if prior in TERMINAL and not args.reopen:
            print("open: REFUSED - %s already exists with status: %s (use --reopen to "
                  "record a regression)." % (target.name, prior), file=sys.stderr)
            return 1
        if args.reopen and prior == "fixed":
            status = "regressed"

    root = project_root()
    try:
        stamps = [evidence_hash(root, rel)
                  for rel in parse_files(",".join(args.evidence or []))]
    except ValueError as exc:
        print("open: invalid --evidence entry %r - same character rule as "
              "--files." % str(exc), file=sys.stderr)
        return 2
    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_open(args, files, args.origin, args.plan, args.severity, status,
                    stamps),
        encoding="utf-8")
    print("OPENED %s (status: %s, verified: false)" % (target, status))
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    if not SLUG_RE.match(args.slug):
        print("close: invalid slug %r (expected ^[a-z0-9][a-z0-9._-]{0,63}$)" % args.slug,
              file=sys.stderr)
        return 2
    if not args.reason.strip():
        print("close: --reason must be non-empty - a finding is retired unfixed only with "
              "a stated reason.", file=sys.stderr)
        return 2
    target = ledger_dir() / ("%s.md" % args.slug)
    if not target.is_file():
        print("close: REFUSED - no entry %s to close." % target.name, file=sys.stderr)
        return 1
    meta = parse_entry(target)
    files = split_files(meta.get("files", ""))
    bad = [f for f in files if any(ch in f for ch in FORBIDDEN_FILE_CHARS)]
    if bad:
        print("close: REFUSED - %s carries a file token %r that would not round-trip "
              "through the `files:` line prune parses back." % (target.name, bad[0]),
              file=sys.stderr)
        return 2
    target.write_text(render_closed(args.slug, meta, files, args.status, args.reason),
                      encoding="utf-8")
    print("CLOSED %s (status: %s, verified: false)" % (target, args.status))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    if not SLUG_RE.match(args.slug):
        print("record: invalid slug %r (expected ^[a-z0-9][a-z0-9._-]{0,63}$)" % args.slug,
              file=sys.stderr)
        return 2
    if not args.signature.strip() or not args.root_cause.strip() or not args.fix.strip():
        print("record: --signature, --root-cause and --fix must be non-empty", file=sys.stderr)
        return 2
    if args.date and not DATE_RE.match(args.date.strip()):
        print("record: invalid --date %r - expected ISO YYYY-MM-DD (a date carrying a "
              "newline or '---' truncates the frontmatter it is written into)."
              % args.date, file=sys.stderr)
        return 2
    try:
        files = parse_files(args.files or "")
    except ValueError as exc:
        print("record: invalid --files entry %r - a file path may not contain '[', ']', "
              "',', a quote or a newline; those corrupt the `files:` frontmatter that "
              "prune parses back." % str(exc), file=sys.stderr)
        return 2
    if not args.verified:
        print("record: REFUSED - the ledger is written only at the Verifier PASS "
              "checkpoint; --verified is required.", file=sys.stderr)
        return 1
    threshold = min_combined_score()
    combined = args.reusability + args.novelty
    if combined < threshold:
        print("record: REFUSED - reusability(%d) + novelty(%d) = %d < %d "
              "(continuous-learning rubric: skip)."
              % (args.reusability, args.novelty, combined, threshold), file=sys.stderr)
        return 1

    directory = ledger_dir()
    target = directory / ("%s.md" % args.slug)
    signature = normalize(args.signature)
    for path in entry_paths(directory):
        if path.name == target.name:
            continue
        if normalize(parse_entry(path).get("signature", "")) == signature:
            print("record: REFUSED - signature already recorded in %s (use --force to "
                  "overwrite that entry instead)." % path.name, file=sys.stderr)
            return 1
    prior: Dict[str, str] = parse_entry(target) if target.exists() else {}
    prior_status = entry_status(prior) if prior else ""
    # An entry sitting at `open`/`regressed` is this command's own upstream, so it is
    # overwritten in place. `fixed`/`wontfix` keep the pre-existing --force rule.
    if target.exists() and prior_status not in UNFIXED and not args.force:
        print("record: REFUSED - %s already exists (use --force to update)." % target.name,
              file=sys.stderr)
        return 1
    origin = scalar(args.origin)
    if origin and origin not in ORIGINS:
        print("record: invalid --origin %r (expected one of %s)"
              % (origin, ", ".join(ORIGINS)), file=sys.stderr)
        return 2
    if not origin:
        origin = safe_origin(prior.get("origin", ""))
    plan = scalar(args.plan) or prior.get("plan", "")
    severity = scalar(args.severity) or prior.get("severity", "")

    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_fixed(args, files, combined, threshold, origin, plan, severity,
                     # Promotion inherits the upstream `open` entry's evidence.
                     split_files(prior.get("evidence", "")) or None),
        encoding="utf-8")
    if prior_status in UNFIXED:
        print("TRANSITION %s: %s -> fixed" % (target.name, prior_status))
    print("RECORDED %s" % target)
    return 0


# ---------------------------------------------------------------------------
# list / prune
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    paths = entry_paths(ledger_dir())
    if not paths:
        print("LEDGER: empty (%s)" % ledger_dir())
        return 0
    rows = []
    for path in paths:
        meta = parse_entry(path)
        status = entry_status(meta)
        origin = safe_origin(meta.get("origin", ""))
        if args.status and status != args.status:
            continue
        if args.origin and origin != args.origin:
            continue
        rows.append((path, meta, status, origin))
    if not rows:
        print("LEDGER: 0 of %d entr(ies) match the filter (%s)" % (len(paths), ledger_dir()))
        return 0
    print("LEDGER: %d entr(ies) in %s" % (len(rows), ledger_dir()))
    for path, meta, status, origin in rows:
        print("  %-40s %-9s %-8s %s  %s"
              % (path.stem, status, origin, meta.get("date", "?"),
                 meta.get("signature", "?")[:60]))
    return 0



# ----------------------------------------------------------------- distill ---
# Distilling turns accumulated receipts into an agent's durable memory. The write
# target is auto-injected into that agent's system prompt, so every rule below is
# load-bearing, not ceremony.
MEMORY_NAME = "MEMORY.md"
DRAFT_SUFFIX = ".draft"
MEMORY_LINE_CAP = 200  # Claude Code loads the first 200 lines / 25 KB, then truncates
# Declared routing, never guessed. An unmapped origin lands on the default and says so.
ORIGIN_TO_AGENT = {"code": "code-reviewer", "workflow": "planner", "project": "planner"}
DEFAULT_AGENT = "planner"


def _load_sanitizers():
    """Load reflection.py's redaction rules by path.

    REUSED, never re-implemented: a second copy of these regexes drifts from the
    originals the first time either changes, and the copy that silently stops
    matching is indistinguishable from one that never had to. Follows
    review-record.py:380's loader exactly, including its BaseException guard --
    exec_module runs another file's module-level code, and a future top-level
    sys.exit() there raises SystemExit, which is not an Exception subclass.
    """
    import importlib.util
    here = Path(__file__).resolve()
    # ORDER MATTERS, and differs from review-record.py's on purpose. distill only ever
    # operates on the project it is pointed at, so the TARGET PROJECT's reflection.py
    # is the authority; resolving the script's own tree first made the installed copy
    # shadow it, which silently disarmed every test that mutates the target's rules to
    # prove they are live. The own-tree path stays as a fallback for an install whose
    # hooks/ was not shipped, never as an override.
    candidates = [project_root() / ".claude" / "hooks" / "reflection.py"]
    if len(here.parents) >= 3:
        candidates.append(here.parents[2] / "hooks" / "reflection.py")
    path = next((c for c in candidates if c.is_file()), None)
    if path is None:
        return None
    spec = importlib.util.spec_from_file_location("_ck_reflection_distill", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        return None
    return module


def _unsafe(text: str, san) -> str:
    """Name what is still unsafe after redaction, or "" if the text is clean.

    REFUSE, never redact-and-ship. A draft that quietly swallowed a secret is worse
    than one that refused: the human reviewing it cannot see what was removed, so
    they approve text they never read.
    """
    for attr, label in (("_ABSOLUTE_PATH", "an absolute path"),
                        ("_SECRET", "a secret-shaped string"),
                        ("_VENDOR_SECRET", "a vendor token")):
        rx = getattr(san, attr, None)
        if rx is not None and rx.search(text):
            return label
    checker = getattr(san, "looks_like_credential", None)
    if callable(checker) and checker(text):
        return "a credential-shaped string"
    return ""


def _normalize_signature(value: str) -> str:
    """Grouping key: exact match after whitespace normalization. No fuzzy matching.

    v1 is deliberately literal. A similarity threshold inside a system-prompt write
    path is an unreviewed judgement call; two receipts that should have grouped and
    did not are a pruning problem, which is cheap, while two that grouped and should
    not have silently merge unrelated lessons, which is not.
    """
    return " ".join(value.split()).strip().lower()


def cmd_distill(args: argparse.Namespace) -> int:
    san = _load_sanitizers()
    if san is None:
        # FAIL CLOSED. An unloadable sanitizer must never mean "nothing to redact".
        print("distill: REFUSED - could not load reflection.py's redaction rules; "
              "refusing to draft unsanitized text into a system-prompt file.",
              file=sys.stderr)
        return 3

    entries = []
    for path in entry_paths(ledger_dir()):
        meta = parse_entry(path)
        # entry_status(), not a raw meta.get(): it maps an unrecognized status to
        # MALFORMED_STATUS, which counts as UNFIXED. Reading a typo literally would
        # drop a live finding out of distillation silently -- the same
        # silent-retirement failure this file already learned from in prune.
        if entry_status(meta) not in UNFIXED:
            continue
        if args.origin and meta.get("origin", DEFAULT_ORIGIN) != args.origin:
            continue
        entries.append((path, meta))
    if not entries:
        print("distill: nothing to do - no unfixed entries match.")
        return 0

    groups: Dict[str, List] = {}
    for path, meta in entries:
        key = _normalize_signature(meta.get("signature", ""))
        if not key:
            continue
        groups.setdefault(key, []).append((path, meta))
    if not groups:
        print("distill: nothing to do - no entry carries a signature.")
        return 0

    agent = args.agent or ORIGIN_TO_AGENT.get(args.origin or "", DEFAULT_AGENT)
    if not args.agent and args.origin not in ORIGIN_TO_AGENT:
        print("distill: origin %r is unmapped; routing to %s"
              % (args.origin, agent), file=sys.stderr)
    if not SLUG_RE.match(agent):
        print("distill: invalid agent name %r" % agent, file=sys.stderr)
        return 2

    root = project_root().resolve()
    mem_root = (root / ".claude" / "agent-memory").resolve()
    target = (mem_root / agent / MEMORY_NAME).resolve()
    # Defence in depth. v1 derives no path component from receipt data -- the agent
    # name comes from the closed routing table or an explicit flag, and the filename
    # is fixed -- so this guards a future change reintroducing derived names, not a
    # live hole today.
    if mem_root not in target.parents:
        print("distill: REFUSED - %s escapes %s" % (target, mem_root), file=sys.stderr)
        return 2

    existing = ""
    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8")
        except OSError:
            existing = ""

    blocks, consumed = [], []
    for key in sorted(groups):
        members = groups[key]
        signature = members[0][1].get("signature", "").strip()
        slugs = sorted(p.stem for p, _ in members)
        body = "- **%s** (%d receipt%s: %s)" % (
            signature, len(members), "" if len(members) == 1 else "s", ", ".join(slugs))
        rendered = san.redact_secrets(body)
        unsafe = _unsafe(rendered, san)
        if unsafe:
            print("distill: REFUSED - receipt %s still carries %s after redaction."
                  % (slugs[0], unsafe), file=sys.stderr)
            return 4
        blocks.append(rendered)
        consumed.extend(slugs)

    draft_body = existing.rstrip("\n") + "\n" if existing.strip() else ""
    draft_body += "\n".join(blocks) + "\n"
    if len(draft_body.splitlines()) > MEMORY_LINE_CAP:
        print("distill: REFUSED - the result would be %d lines, past the %d-line "
              "truncation cliff. Prune %s first; past the cap Claude Code loads half "
              "a memory the agent believes is whole."
              % (len(draft_body.splitlines()), MEMORY_LINE_CAP, target),
              file=sys.stderr)
        return 5

    draft = Path(str(target) + DRAFT_SUFFIX)
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(draft_body, encoding="utf-8")
    print("DRAFT %s (%d group(s), %d receipt(s))" % (draft, len(blocks), len(consumed)))
    print("--- draft ---")
    print(draft_body, end="")
    print("--- end ---")
    print("%s is NOT modified. Review the draft, then move it yourself." % target.name)
    # Deliberately NOT closed here. The draft is a proposal; closing its receipts now
    # would destroy the source material for any draft the human discards or rewrites.
    print("After accepting, close the receipts it consumed:")
    for slug in consumed:
        print("  knowledge-ledger.py close %s --reason 'distilled into %s memory'"
              % (slug, agent))
    return 0

def cmd_prune(args: argparse.Namespace) -> int:
    root = project_root()
    directory = ledger_dir()
    stale: List[Path] = []
    stale_open: List[Path] = []
    for path in entry_paths(directory):
        meta = parse_entry(path)
        files = split_files(meta.get("files", ""))
        if not files:
            continue  # nothing to check against - never prune on absence of data
        if not all(not (root / f).exists() for f in files):
            continue
        # Archiving an UNFIXED finding because its files moved would silently retire a
        # live bug. Those are reported separately and never touched.
        (stale_open if entry_status(meta) in UNFIXED else stale).append(path)
    superseded: List[Path] = []
    # OPT-IN. Archiving an unfixed finding is exactly the failure the
    # stale_open split above exists to prevent, so default prune output and
    # exit codes are unchanged unless an operator asks for --supersede.
    if getattr(args, "supersede", False):
        ttl = getattr(args, "ttl_days", DEFAULT_TTL_DAYS)
        today = _date.today()
        for path in entry_paths(directory):
            if path in stale or path in stale_open:
                continue
            meta = parse_entry(path)
            if entry_status(meta) not in UNFIXED:
                continue  # `fixed`/`wontfix` are never retired by this rule
            if evidence_superseded(root, meta):
                superseded.append(path)
            elif not split_files(meta.get("evidence", "")):
                age = entry_age_days(meta, today)
                if ttl > 0 and age >= ttl:
                    superseded.append(path)
        if superseded:
            print("SUPERSEDED: %d open entr(ies) whose evidence moved on "
                  "(or aged past the TTL fallback):" % len(superseded))
            for path in superseded:
                print("  %s" % path.name)
            if args.apply:
                archive = directory / "archive"
                archive.mkdir(parents=True, exist_ok=True)
                for path in superseded:
                    path.rename(archive / path.name)
                    print("ARCHIVED %s" % (archive / path.name))
                superseded = []
            else:
                print("Re-run with --apply --supersede to archive them.")
    if not stale and not stale_open and not superseded:
        print("LEDGER: clean - 0 stale entries")
        return 0
    if stale_open:
        print("STALE-OPEN: %d unfixed entr(ies) whose referenced files are all gone - NOT "
              "archived; re-scope the finding or close it:" % len(stale_open))
        for path in stale_open:
            print("  %s" % path.name)
    if stale:
        print("LEDGER: %d stale entr(ies) - every referenced file is gone:" % len(stale))
        for path in stale:
            print("  %s" % path.name)
    if not stale:
        return 1
    if not args.apply:
        print("Re-run with --apply to archive them.")
        return 1
    archive = directory / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    for path in stale:
        path.rename(archive / path.name)
        print("ARCHIVED %s" % (archive / path.name))
    return 1 if stale_open else 0


def cmd_propose(args: argparse.Namespace) -> int:
    """Propose - never write - a candidate skill for a repeated class of finding.

    `cmd_open` REFUSES a duplicate signature, so "the same signature three times" is
    unreachable by construction; the reachable equivalent is a cluster of open findings
    sharing signature tokens. Nothing here writes into `.claude/skills/` and nothing here
    runs a generator: promotion is a human step (hard rule 5).
    """
    directory = ledger_dir()
    live: List[Tuple[Path, Set[str]]] = []
    for path in entry_paths(directory):
        meta = parse_entry(path)
        if entry_status(meta) not in UNFIXED:
            continue
        tokens = {t for t in tokenize(meta.get("signature", "")) if t not in _STOPWORDS}
        if tokens:
            live.append((path, tokens))
    clusters: List[Tuple[Set[str], List[str]]] = []
    used: Set[str] = set()
    for index, (path, tokens) in enumerate(live):
        if path.stem in used:
            continue
        members = [path.stem]
        shared = set(tokens)
        for other, other_tokens in live[index + 1:]:
            if other.stem in used:
                continue
            common = shared & other_tokens
            if len(common) >= 2:
                members.append(other.stem)
                shared = common
        if len(members) >= args.min_cluster:
            used.update(members)
            clusters.append((shared, sorted(members)))
    if not clusters:
        print("PROPOSE: no cluster of %d+ open findings shares a signature"
              % args.min_cluster)
        return 0
    out = project_root() / ".claude" / "knowledge" / "proposals"
    out.mkdir(parents=True, exist_ok=True)
    for shared, members in clusters:
        # Shared tokens alone are not a unique name: two different clusters can share
        # their top three tokens, and the second would then be silently skipped as
        # "already proposed". A short hash of the MEMBER SET makes the name identify the
        # cluster it actually describes.
        stem = re.sub(r"[^a-z0-9._-]", "-", "-".join(sorted(shared)[:3]).lower())
        digest = hashlib.sha256("\x00".join(members).encode("utf-8")).hexdigest()[:8]
        slug = (stem[:48].strip("-") or "proposal") + "-" + digest
        target = out / ("%s.md" % slug)
        if target.exists():
            print("PROPOSE: %s already proposed" % target.name)
            continue
        target.write_text("\n".join([
            "# Candidate skill: %s" % slug,
            "",
            "%d open findings share the signature tokens `%s`."
            % (len(members), ", ".join(sorted(shared))),
            "",
            "## Members",
            "",
        ] + ["- `%s`" % member for member in members] + [
            "",
            "## Next step (human)",
            "",
            "This is a PROPOSAL. Nothing was written to `.claude/skills/`. Read the member",
            "entries, decide whether one reusable skill covers them, and if it does create",
            "it with `ck skill new` - which charges its description against the always-on",
            "context floor, so the decision has a price.",
            "",
        ]), encoding="utf-8")
        print("PROPOSED %s" % target)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project-local per-issue knowledge ledger.")
    sub = parser.add_subparsers(dest="command")

    search = sub.add_parser("search", help="keyword / error-signature retrieval")
    search.add_argument("query", nargs="+")
    search.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    search.set_defaults(func=cmd_search)

    record = sub.add_parser("record", help="record an issue (Verifier PASS checkpoint only)")
    record.add_argument("--slug", required=True)
    record.add_argument("--signature", required=True)
    record.add_argument("--root-cause", dest="root_cause", required=True)
    record.add_argument("--fix", required=True)
    record.add_argument("--files", default="")
    record.add_argument("--reusability", type=int, required=True)
    record.add_argument("--novelty", type=int, required=True)
    record.add_argument("--date", default="")
    record.add_argument("--origin", default="", choices=("",) + ORIGINS,
                        help="lane of the issue; carried forward from an open entry")
    record.add_argument("--plan", default="", help="plan slug that closed this finding")
    record.add_argument("--severity", default="")
    record.add_argument("--verified", action="store_true",
                        help="assert the Verifier returned PASS for this fix")
    record.add_argument("--force", action="store_true")
    record.set_defaults(func=cmd_record)

    opening = sub.add_parser("open", help="record a finding at discovery time (unverified)")
    opening.add_argument("--slug", required=True)
    opening.add_argument("--signature", required=True)
    opening.add_argument("--origin", required=True, choices=ORIGINS)
    opening.add_argument("--plan", default="", help="plan slug expected to close this")
    opening.add_argument("--severity", default="")
    opening.add_argument("--files", default="")
    opening.add_argument("--date", default="")
    opening.add_argument("--reopen", action="store_true",
                        help="a fixed entry regressed: rewrite it as status: regressed")
    opening.add_argument("--evidence", action="append", default=[],
                        help="repo-relative file this finding rests on "
                             "(repeatable); stamped with its sha256 so "
                             "prune can tell when the code moved on")
    opening.set_defaults(func=cmd_open)

    closing = sub.add_parser("close", help="retire a finding deliberately not fixed")
    closing.add_argument("--slug", required=True)
    closing.add_argument("--status", required=True, choices=("wontfix",))
    closing.add_argument("--reason", required=True)
    closing.set_defaults(func=cmd_close)

    listing = sub.add_parser("list", help="show every entry")
    listing.add_argument("--status", default="", choices=("",) + STATUSES)
    listing.add_argument("--origin", default="", choices=("",) + ORIGINS)
    listing.set_defaults(func=cmd_list)

    propose = sub.add_parser(
        "propose", help="propose a candidate skill for a repeated finding")
    propose.add_argument("--min-cluster", dest="min_cluster", type=int,
                         default=PROPOSAL_MIN_CLUSTER)
    propose.set_defaults(func=cmd_propose)

    distill = sub.add_parser(
        "distill", help="draft an agent memory entry from unfixed receipts")
    distill.add_argument("--agent", default="",
                         help="target agent (default: routed from --origin)")
    distill.add_argument("--origin", default="", choices=("",) + ORIGINS,
                         help="only distill receipts of this origin")
    distill.set_defaults(func=cmd_distill)

    prune = sub.add_parser("prune", help="archive entries whose files no longer exist")
    prune.add_argument("--apply", action="store_true")
    prune.add_argument("--supersede", action="store_true",
                       help="also retire OPEN entries whose evidence hashes "
                            "no longer match (or, absent evidence, that are "
                            "older than --ttl-days)")
    prune.add_argument("--ttl-days", dest="ttl_days", type=int,
                       default=DEFAULT_TTL_DAYS,
                       help="fallback age gate for open entries citing no "
                            "evidence (0 disables)")
    prune.set_defaults(func=cmd_prune)
    return parser


def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

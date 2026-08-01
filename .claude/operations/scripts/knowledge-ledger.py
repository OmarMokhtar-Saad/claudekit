#!/usr/bin/env python3
"""knowledge-ledger.py - project-local, per-issue knowledge ledger.

Stores one markdown entry per diagnosed-and-fixed issue under
`.claude/knowledge/issues/<slug>.md` so a later session can look up a known root
cause instead of re-diagnosing a bug this project already fixed.

Subcommands:
  search   keyword / error-signature retrieval (debugger agent, Phase 0)
  record   write gate - fires only at the Verifier PASS checkpoint
  list     show every entry
  prune    archive entries whose referenced files no longer exist

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
import json
import os
import re
import subprocess
import sys
from datetime import date as _date
from pathlib import Path
from typing import Dict, List, Set, Tuple

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
TOKEN_RE = re.compile(r"[a-z0-9_.]{2,}")
DEFAULT_MIN_COMBINED_SCORE = 10  # continuous-learning rubric: reusability + novelty
CONFIG_REL = (".claude", "hooks", "config.json")
# A file token carrying any of these would corrupt the `files: [a, b]` frontmatter
# line that prune's split_files() reads back, so it is refused at write time.
FORBIDDEN_FILE_CHARS = "[],\"'\r\n"
DEFAULT_LIMIT = 5


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
        print("  date:       %s  verified: %s" % (meta.get("date", "?"), meta.get("verified", "?")))
    print("")
    print("Report the known root cause/fix above; re-diagnose only if the evidence contradicts it.")
    return 0


# ---------------------------------------------------------------------------
# record (the write gate)
# ---------------------------------------------------------------------------

def render_entry(args: argparse.Namespace, files: List[str], combined: int,
                 threshold: int) -> str:
    today = args.date or _date.today().isoformat()
    lines = [
        "---",
        'signature: "%s"' % scalar(args.signature),
        'root_cause: "%s"' % scalar(args.root_cause),
        'fix: "%s"' % scalar(args.fix),
        "files: [%s]" % ", ".join(files),
        "date: %s" % today,
        "verified: true",
        "---",
        "",
        "# %s" % args.slug,
        "",
        "## Signature",
        "",
        scalar(args.signature),
        "",
        "## Root cause",
        "",
        args.root_cause.strip(),
        "",
        "## Fix",
        "",
        args.fix.strip(),
        "",
        "## Files",
        "",
    ]
    lines.extend(["- %s" % f for f in files] or ["- (none recorded)"])
    lines.extend([
        "",
        "## Scoring (continuous-learning rubric)",
        "",
        "reusability: %d | novelty: %d | combined: %d (threshold %d)"
        % (args.reusability, args.novelty, combined, threshold),
        "",
        "Recorded at the Verifier PASS checkpoint.",
        "",
    ])
    return "\n".join(lines)


def cmd_record(args: argparse.Namespace) -> int:
    if not SLUG_RE.match(args.slug):
        print("record: invalid slug %r (expected ^[a-z0-9][a-z0-9._-]{0,63}$)" % args.slug,
              file=sys.stderr)
        return 2
    if not args.signature.strip() or not args.root_cause.strip() or not args.fix.strip():
        print("record: --signature, --root-cause and --fix must be non-empty", file=sys.stderr)
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
    if target.exists() and not args.force:
        print("record: REFUSED - %s already exists (use --force to update)." % target.name,
              file=sys.stderr)
        return 1

    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(render_entry(args, files, combined, threshold), encoding="utf-8")
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
    print("LEDGER: %d entr(ies) in %s" % (len(paths), ledger_dir()))
    for path in paths:
        meta = parse_entry(path)
        print("  %-40s %s  %s" % (path.stem, meta.get("date", "?"),
                                  meta.get("signature", "?")[:60]))
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    root = project_root()
    directory = ledger_dir()
    stale: List[Path] = []
    for path in entry_paths(directory):
        files = split_files(parse_entry(path).get("files", ""))
        if not files:
            continue  # nothing to check against - never prune on absence of data
        if all(not (root / f).exists() for f in files):
            stale.append(path)
    if not stale:
        print("LEDGER: clean - 0 stale entries")
        return 0
    print("LEDGER: %d stale entr(ies) - every referenced file is gone:" % len(stale))
    for path in stale:
        print("  %s" % path.name)
    if not args.apply:
        print("Re-run with --apply to archive them.")
        return 1
    archive = directory / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    for path in stale:
        path.rename(archive / path.name)
        print("ARCHIVED %s" % (archive / path.name))
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
    record.add_argument("--verified", action="store_true",
                        help="assert the Verifier returned PASS for this fix")
    record.add_argument("--force", action="store_true")
    record.set_defaults(func=cmd_record)

    listing = sub.add_parser("list", help="show every entry")
    listing.set_defaults(func=cmd_list)

    prune = sub.add_parser("prune", help="archive entries whose files no longer exist")
    prune.add_argument("--apply", action="store_true")
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

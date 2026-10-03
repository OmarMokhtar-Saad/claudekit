#!/usr/bin/env python3
"""learn-verify.py - the opt-in `/learn --verify` gate: three skeptic checks, all must pass.

A pending learning candidate (a memory candidate in `.claude/agent-memory/<agent>/_inbox/` or a
proposal in `.claude/knowledge/proposals/`) is only worth promoting when a skeptic cannot
knock it down. Three checks, each trying to REFUTE the candidate:

  1. grounded  - it cites at least one repo path, and every cited path exists. A lesson with
                 no checkable evidence, or evidence that is gone, is an opinion.
  2. novel     - it is not already recorded: no existing memory entry or skill description
                 overlaps it past the duplicate threshold.
  3. portable  - it carries no absolute path, secret-shaped string, UUID or other session
                 residue, and no instruction aimed at the model ("ignore previous...",
                 "you must always..."). Memory is injected into prompts; a directive in it is
                 a finding, not an order.

FAIL CLOSED: an unreadable, empty or unknown candidate, or any internal error, is a failed
check. Exit 0 only when all three pass; 1 when any fails; 2 for usage errors (also not a pass).

PROPOSE-ONLY: this script reads files and prints a verdict. It writes nothing, promotes
nothing and applies nothing; the human `/learn --promote` decision stays separate and
follows it.

Usage:
    python3 .claude/operations/scripts/learn-verify.py <candidate-name> [--agent A] [--json]
    python3 .claude/operations/scripts/learn-verify.py --file PATH [--json]

Root: $CLAUDEKIT_PROJECT_ROOT, else the git toplevel, else cwd. Stdlib only, py3.9.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DUPLICATE_THRESHOLD = 0.6   # Jaccard over content tokens
MIN_TOKENS = 4              # below this a token-overlap verdict means nothing
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,80}$")
PATH_RE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,6})(?![\w/])")
ABS_PATH_RE = re.compile(r"(?<![\w.-])(?:/(?:Users|home|private|tmp|var|etc|opt)/[\w./-]+|[A-Za-z]:\\[\w\\.-]+)")
SECRET_RE = re.compile(r"(?i)(?:\b(?:sk|ghp|gho|xox[bp]|AKIA)[-_A-Za-z0-9]{12,}|"
                       r"\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*\S{6,})")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
DIRECTIVE_RE = re.compile(
    r"(?i)\b(?:ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules)|"
    r"disregard (?:the |all )?(?:system|previous|above)|you (?:must|should) (?:always|never)|"
    r"from now on,? (?:you|always|never)|do not tell the user|override (?:the )?(?:rules|policy|hooks?))")
STOP = frozenset("the a an and or of to in on for with is are was were be it this that as at by from not no "
                 "when then if use used using run runs file files".split())


def project_root() -> Path:
    env = os.environ.get("CLAUDEKIT_PROJECT_ROOT")
    if env:
        return Path(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except Exception:
        pass
    return Path.cwd()


def tokens(text: str) -> frozenset:
    return frozenset(t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2 and t not in STOP)


def body_of(text: str) -> str:
    """The candidate text without its `---` frontmatter fence, keeping the `index:` hook."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front, rest = text[3:end], text[end + 4:]
            hooks = [ln.split(":", 1)[1].strip() for ln in front.splitlines()
                     if ln.split(":", 1)[0].strip() in ("index", "description")]
            return "\n".join(hooks) + "\n" + rest
    return text


def find_candidate(root: Path, name: str, agent: str = "") -> list:
    found = sorted((root / ".claude" / "agent-memory").glob("%s/_inbox/%s.md" % (agent or "*", name)))
    proposal = root / ".claude" / "knowledge" / "proposals" / ("%s.md" % name)
    if proposal.is_file():
        found.append(proposal)
    return found


def check_grounded(root: Path, text: str) -> tuple:
    cited = sorted(set(PATH_RE.findall(text)))
    if not cited:
        return False, "cites no repo path: nothing a skeptic can check"
    missing = [p for p in cited if not (root / p).exists()]
    if missing:
        return False, "cites paths that do not exist: " + ", ".join(missing[:5])
    return True, "%d cited path(s) exist" % len(cited)


def _existing_texts(root: Path, own: Path):
    for path in sorted((root / ".claude" / "agent-memory").glob("*/*.md")):
        if path.name != "MEMORY.md" and path.name.lower() != "readme.md":
            yield path
    for path in sorted((root / ".claude" / "agent-memory").glob("*/MEMORY.md")):
        yield path
    for path in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
        yield path


def check_novel(root: Path, own: Path, text: str) -> tuple:
    mine = tokens(text)
    if len(mine) < MIN_TOKENS:
        return False, "too little content (%d token(s)) to judge novelty" % len(mine)
    best, best_path = 0.0, None
    for path in _existing_texts(root, own):
        if path.resolve() == own.resolve():
            continue
        try:
            other = tokens(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not other:
            continue
        # Containment of the candidate in a big file would flag every long skill; use Jaccard
        # against the whole file plus against each index-sized line of MEMORY.md.
        scores = [len(mine & other) / len(mine | other)]
        if path.name == "MEMORY.md":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                lt = tokens(line)
                if len(lt) >= MIN_TOKENS:
                    # An index line is a one-line summary: it is a duplicate when the
                    # candidate CONTAINS it, even though Jaccard against the body is low.
                    scores.append(max(len(mine & lt) / len(mine | lt), len(mine & lt) / len(lt)))
        score = max(scores)
        if score > best:
            best, best_path = score, path
    if best >= DUPLICATE_THRESHOLD:
        return False, "overlaps %s at %.2f (threshold %.2f)" % (best_path.relative_to(root), best,
                                                                DUPLICATE_THRESHOLD)
    return True, "closest existing text overlaps at %.2f" % best


def check_portable(text: str) -> tuple:
    for rx, label in ((ABS_PATH_RE, "an absolute path"), (SECRET_RE, "a secret-shaped string"),
                      (UUID_RE, "a session/uuid identifier"),
                      (DIRECTIVE_RE, "an instruction aimed at the model")):
        match = rx.search(text)
        if match:
            return False, "contains %s: %r" % (label, match.group(0)[:40])
    return True, "no absolute path, secret, identifier or directive"


def verify(root: Path, path: Path) -> list:
    """[(check name, passed, reason)]; any exception is a failed check."""
    try:
        text = body_of(path.read_text(encoding="utf-8"))
        if not text.strip():
            raise ValueError("candidate is empty")
    except (OSError, ValueError) as exc:
        return [(n, False, "cannot read candidate: %s" % exc) for n in ("grounded", "novel", "portable")]
    out = []
    for name, fn in (("grounded", lambda: check_grounded(root, text)),
                     ("novel", lambda: check_novel(root, path, text)),
                     ("portable", lambda: check_portable(text))):
        try:
            ok, why = fn()
        except Exception as exc:  # fail closed
            ok, why = False, "check crashed: %s" % exc
        out.append((name, bool(ok), why))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("name", nargs="?", default="", help="pending candidate or proposal name")
    ap.add_argument("--agent", default="")
    ap.add_argument("--file", default="", help="verify this file instead of looking a name up")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = project_root()
    if args.file:
        path = Path(args.file)
    elif args.name and SLUG_RE.match(args.name):
        found = find_candidate(root, args.name, args.agent)
        if len(found) != 1:
            sys.stderr.write("verify: %s pending item named %r%s\n" % (
                "no" if not found else "several", args.name, "" if not found else "; pass --agent"))
            return 2
        path = found[0]
    else:
        sys.stderr.write("verify: give a candidate name or --file\n")
        return 2
    results = verify(root, path)
    passed = all(ok for _, ok, _ in results)
    if args.json:
        sys.stdout.write(json.dumps({"passed": passed, "checks": [
            {"check": n, "passed": ok, "reason": why} for n, ok, why in results]}, indent=2) + "\n")
    else:
        for n, ok, why in results:
            sys.stdout.write("%s %-9s %s\n" % ("PASS" if ok else "FAIL", n, why))
        sys.stdout.write("VERIFIED: all 3 skeptic checks passed; promotion is still a human decision\n"
                         if passed else "REFUSED: a skeptic check failed; do not promote\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Single source of truth for ClaudeKit component counts.

The filesystem is authoritative. This script:

  * computes the real counts of agents / commands / skills / hooks, and
  * regenerates the "component inventory" block in README.md (between the
    ``<!-- BEGIN GENERATED:inventory -->`` / ``<!-- END GENERATED:inventory -->``
    markers), and
  * with ``--check``, verifies both that the generated block is current and that
    no doc hard-codes a stale count (the docs-drift gate used by CI).

Usage:
    python3 scripts/gen-docs.py            # rewrite generated blocks in place
    python3 scripts/gen-docs.py --check    # exit 1 if anything is stale
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BEGIN = "<!-- BEGIN GENERATED:inventory -->"
END = "<!-- END GENERATED:inventory -->"

# Files whose prose is scanned for stale "<n> <noun>" counts.
DRIFT_FILES = [
    "README.md",
    "docs/AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/SKILLS.md",
    "docs/HOOKS.md",
]

# A number followed by (optionally one adjective) one of the tracked nouns:
#   "28 agents", "39 slash commands", "73 domain skills", "18 workflow hooks".
_DRIFT_RE = re.compile(r"(\d+)\s+(?:[\w-]+\s+)?(agents?|commands?|skills?|hooks?)\b")

# Escape hatch: a line carrying this marker is neither drift-checked nor rewritten
# (for genuine examples like "add 2 hooks of your own").
IGNORE_MARKER = "gen-docs:ignore"


def count_agents() -> int:
    d = ROOT / ".claude" / "agents"
    return len([p for p in d.glob("*.md")
                if p.name not in ("HANDOFF_PROTOCOL.md", "QUICK_START.md")])


def count_commands() -> int:
    return len(list((ROOT / ".claude" / "commands").glob("*.md")))


def count_skills() -> int:
    return len(list((ROOT / ".claude" / "skills").glob("*/SKILL.md")))


# Hooks ship as shell OR python (`reflection-gate.py` is wired in settings.json).
HOOK_GLOBS = ("*.sh", "*.py")


def _hook_files() -> list:
    d = ROOT / ".claude" / "hooks"
    return sorted({p for pat in HOOK_GLOBS for p in d.glob(pat)})


def _is_helper_module(path, siblings) -> bool:
    """True when another hook sources/imports `path` (so it is a library, not a hook).

    Structural, not a hard-coded name list: `lib.sh` is sourced by every shell hook
    and `reflection.py` is imported by `reflection-gate.py`, so both drop out
    automatically, and a future helper needs no edit here.
    """
    if path.suffix == ".sh":
        # re.M so a line-initial `source "$SCRIPT_DIR/lib.sh"` is detected too; without
        # it a helper could masquerade as a hook and inflate the published count.
        pat = re.compile(r"(?:^|[;&|]\s*)(?:\.|source)\s+\S*" + re.escape(path.name), re.M)
    else:
        stem = re.escape(path.stem)
        pat = re.compile(r"^\s*(?:import\s+%s|from\s+%s\s+import)\b" % (stem, stem), re.M)
    for other in siblings:
        if other == path:
            continue
        try:
            text = other.read_text(errors="replace")
        except OSError:
            continue
        if pat.search(text):
            return True
    return False


def count_hooks() -> int:
    files = _hook_files()
    return len([p for p in files if not _is_helper_module(p, files)])


def counts() -> dict:
    return {
        "agent": count_agents(),
        "command": count_commands(),
        "skill": count_skills(),
        "hook": count_hooks(),
    }


def render_block(c: dict) -> str:
    return (
        f"{BEGIN}\n"
        f"| Component | Count |\n"
        f"|-----------|------:|\n"
        f"| Agents    | {c['agent']} |\n"
        f"| Commands  | {c['command']} |\n"
        f"| Skills    | {c['skill']} |\n"
        f"| Hooks     | {c['hook']} |\n"
        f"{END}"
    )


def _replace_block(text: str, block: str) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if pattern.search(text):
        return pattern.sub(lambda _m: block, text)
    return text  # no markers -> nothing to update


def scan_drift(c: dict) -> list:
    """Return a list of (file, line_no, text, found, expected) mismatches."""
    plural = {"agent": c["agent"], "command": c["command"],
              "skill": c["skill"], "hook": c["hook"]}
    problems = []
    for rel in DRIFT_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if IGNORE_MARKER in line:
                continue
            for m in _DRIFT_RE.finditer(line):
                found = int(m.group(1))
                noun = m.group(2).rstrip("s")
                expected = plural[noun]
                if found != expected:
                    problems.append((rel, i, line.strip(), found, expected))
    return problems


def _fix_line(line: str, c: dict) -> str:
    def repl(m):
        expected = c[m.group(2).rstrip("s")]
        return m.group(0).replace(m.group(1), str(expected), 1)
    return _DRIFT_RE.sub(repl, line)


def fix_drift(c: dict) -> list:
    """Rewrite stale prose counts in DRIFT_FILES in place; return files changed.

    Counts are generator-owned (CLAUDE.md hard rule 8: never hand-edit them), so
    prose outside the generated block is corrected here rather than by a human.
    Only the matched number is replaced; the rest of the line is preserved.
    """
    changed = []
    for rel in DRIFT_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text()
        new = "".join(line if IGNORE_MARKER in line else _fix_line(line, c)
                      for line in text.splitlines(keepends=True))
        if new != text:
            path.write_text(new)
            changed.append(rel)
    return changed


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    c = counts()

    readme = ROOT / "README.md"
    text = readme.read_text()
    new_text = _replace_block(text, render_block(c))

    block_stale = new_text != text
    drift = scan_drift(c)

    print(f"Counts: agents={c['agent']} commands={c['command']} "
          f"skills={c['skill']} hooks={c['hook']}")

    if check:
        rc = 0
        if block_stale:
            print("ERROR: README generated inventory block is out of date. "
                  "Run: python3 scripts/gen-docs.py", file=sys.stderr)
            rc = 1
        if drift:
            print("ERROR: stale component counts in docs:", file=sys.stderr)
            for rel, ln, txt, found, expected in drift:
                print(f"  {rel}:{ln}: says {found}, should be {expected} "
                      f"-> {txt}", file=sys.stderr)
            rc = 1
        if rc == 0:
            print("OK: docs counts are current.")
        return rc

    if block_stale:
        readme.write_text(new_text)
        print("Updated README generated inventory block.")
    else:
        print("README generated inventory block already current.")
    if drift:
        for rel in fix_drift(c):
            print(f"Updated stale counts in {rel}.")
        remaining = scan_drift(c)
        if remaining:
            print("ERROR: could not auto-fix these counts:", file=sys.stderr)
            for rel, ln, txt, found, expected in remaining:
                print(f"  {rel}:{ln}: says {found}, should be {expected}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

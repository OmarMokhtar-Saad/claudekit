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


def count_agents() -> int:
    d = ROOT / ".claude" / "agents"
    return len([p for p in d.glob("*.md")
                if p.name not in ("HANDOFF_PROTOCOL.md", "QUICK_START.md")])


def count_commands() -> int:
    return len(list((ROOT / ".claude" / "commands").glob("*.md")))


def count_skills() -> int:
    return len(list((ROOT / ".claude" / "skills").glob("*/SKILL.md")))


def count_hooks() -> int:
    # lib.sh is a sourced helper library, not a hook.
    return len([p for p in (ROOT / ".claude" / "hooks").glob("*.sh")
                if p.name != "lib.sh"])


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
            for m in _DRIFT_RE.finditer(line):
                found = int(m.group(1))
                noun = m.group(2).rstrip("s")
                expected = plural[noun]
                if found != expected:
                    problems.append((rel, i, line.strip(), found, expected))
    return problems


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
        print("WARNING: prose still hard-codes stale counts (fix manually):")
        for rel, ln, txt, found, expected in drift:
            print(f"  {rel}:{ln}: says {found}, should be {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

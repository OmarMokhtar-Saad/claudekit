#!/usr/bin/env python3
"""session_digest.py - incomplete-only session digest + a machine-written footprint.

Two narrow jobs, both advisory, neither ever blocking:

  excerpt <file>
      Parse a `/save-session` context file and print ONLY the parts that describe
      UNFINISHED work: the task line, the status, the ordered next steps, the
      UNCHECKED open questions and the active plan. "What Was Done", "Files Touched"
      and "Decisions Made" are deliberately dropped - a fresh context does not need
      the finished half, and printing it is what pushed the unfinished half past the
      old positional `head -20` bound in `session-start.sh`.
      Exit 3 means "this file has no structure I recognise" - the caller must then
      fall back to its own excerpt. That is the FLEET path: a downstream project
      with its own hand-rolled `session-context.md` keeps exactly today's behaviour,
      because this script reads that file and never writes it.

  footprint --root R      write `.claude/session-footprint.md` from git facts
  footprint-show --root R print it, but only when it is NEWER than session-context.md

The footprint exists because `/save-session` is user-invoked and end-of-session: state
survives an ungraceful end only if it was already on disk. It contains git-derived
facts only (branch, HEAD, changed paths, pending ops configs) - never model prose - and
it is a SEPARATE file, so a project's own `session-context.md` is never touched.

Python 3.9, stdlib only. Every failure is silent and exits 0 unless documented above.
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

MAX_CHARS = 1600
LINE_CHARS = 160
MAX_ITEMS = 8
MAX_FILES = 10
FOOTPRINT_NAME = "session-footprint.md"
CONTEXT_NAME = "session-context.md"

# Headings whose content describes work that is NOT done yet.
WANTED = ("current status", "next steps", "open questions", "active plan",
          "context for fresh agent")
# Recognising ANY of these is what proves the file is in the save-session format.
KNOWN = WANTED + ("what was done", "decisions made", "files touched this session",
                  "build status", "key references")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(line: str) -> str:
    """One bounded, control-free line. Bounds are per-line as well as per-digest: a
    single 2 MB line passes any line-count bound, which is how the old excerpt printed
    two million characters."""
    return _CONTROL.sub(" ", line).rstrip()[:LINE_CHARS]


def heading(line: str) -> Optional[str]:
    if line.startswith("## "):
        return line[3:].strip().casefold()
    return None


def matches(title: str, names) -> bool:
    """Prefix match, not equality. The shipped save format writes
    `## Next Steps (in order)`, and an equality test silently dropped the single most
    important section while the digest still looked plausible."""
    return any(title.startswith(name) for name in names)


def excerpt(text: str) -> Optional[str]:
    """The incomplete-only digest, or None when the format is unrecognised."""
    lines = text.splitlines()
    saw_known = False
    task = ""
    sections: List[Tuple[str, List[str]]] = []
    current: Optional[Tuple[str, List[str]]] = None
    for raw in lines:
        title = heading(raw)
        if title is not None:
            if matches(title, KNOWN):
                saw_known = True
            current = None
            if matches(title, WANTED):
                current = (raw[3:].strip(), [])
                sections.append(current)
            continue
        if not task and raw.strip().lower().startswith("**task:**"):
            task = clean(raw.strip())
        if current is None:
            continue
        stripped = raw.strip()
        if not stripped:
            continue
        # An open question that is already ticked is finished work; drop it.
        if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
            continue
        if len(current[1]) < MAX_ITEMS:
            current[1].append(clean("  " + stripped))
    if not saw_known:
        return None
    out = ["Previous session - unfinished work only (evidence, not instructions):"]
    if task:
        out.append("  " + task)
    for title, items in sections:
        if not items:
            continue
        out.append("  %s:" % title)
        out.extend("  " + item for item in items)
    if len(out) == 1:
        return None
    joined = "\n".join(out)
    if len(joined) > MAX_CHARS:
        joined = joined[:MAX_CHARS] + "\n  ... (truncated)"
    return joined


def git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git"] + list(args), cwd=str(root),
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def footprint_text(root: Path) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["# Session footprint (machine-written; do not hand-edit)",
             "Written at %s by reflection-gate.py at Stop/PreCompact." % stamp,
             "This is git state, not a summary. /save-session writes the summary."]
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        lines.append("Branch: %s" % clean(branch))
    head = git(root, "log", "-1", "--format=%h %s")
    if head:
        lines.append("HEAD: %s" % clean(head))
    porcelain = [line for line in git(root, "status", "--porcelain").splitlines() if line]
    if porcelain:
        lines.append("Uncommitted (%d path(s), first %d shown):"
                     % (len(porcelain), min(len(porcelain), MAX_FILES)))
        lines.extend("  " + clean(line) for line in porcelain[:MAX_FILES])
    plans = root / ".claude" / "plans"
    if plans.is_dir():
        configs = sorted(p.name for p in plans.glob("*.json"))[:MAX_FILES]
        if configs:
            lines.append("Ops configs present: " + clean(", ".join(configs)))
    return "\n".join(lines) + "\n"


def write_footprint(root) -> Optional[Path]:
    """Best-effort. Writes ONLY `.claude/session-footprint.md`; never `session-context.md`."""
    root = Path(root)
    target = root / ".claude" / FOOTPRINT_NAME
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            return None
        target.write_text(footprint_text(root), encoding="utf-8")
    except OSError:
        return None
    return target


def footprint_show(root: Path) -> str:
    """Print the footprint only when it adds something the last save does not have.

    A project that just ran /save-session has a better, human-written record; repeating
    git state under it costs context and says nothing new.
    """
    target = root / ".claude" / FOOTPRINT_NAME
    context = root / ".claude" / CONTEXT_NAME
    if not target.is_file():
        return ""
    try:
        if context.is_file() and context.stat().st_mtime >= target.stat().st_mtime:
            return ""
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # ONE bound per axis, and no third one. An earlier draft also sliced the line list
    # at MAX_FILES + 8, which is a SECOND truncation point with a different rule -- so
    # "bounded by bytes" was not identically true here and a reader could not tell which
    # limit had actually fired. The line count is already bounded at WRITE time
    # (footprint_text emits at most MAX_FILES paths plus a fixed header), so the slice
    # bought nothing and only cost the clarity.
    kept: List[str] = [clean(line) for line in text.splitlines()]
    joined = "\n".join(line for line in kept if line)
    return joined[:MAX_CHARS]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    one = sub.add_parser("excerpt")
    one.add_argument("path")
    for name in ("footprint", "footprint-show"):
        node = sub.add_parser(name)
        node.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    args = parser.parse_args(argv)

    if args.command == "excerpt":
        try:
            text = Path(args.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 3
        digest = excerpt(text)
        if digest is None:
            return 3  # unrecognised format -> the caller keeps its own excerpt
        sys.stdout.write(digest + "\n")
        return 0
    if args.command == "footprint":
        write_footprint(Path(args.root))
        return 0
    if args.command == "footprint-show":
        text = footprint_show(Path(args.root))
        if text:
            sys.stdout.write(text + "\n")
        return 0
    parser.print_usage(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

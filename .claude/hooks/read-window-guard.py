#!/usr/bin/env python3
"""read-window-guard.py - PreToolUse/Read: refuse an UNWINDOWED read of a large file.

WHY THIS EXISTS
---------------
`output_filter.py` caps Bash stdout at 12,000 chars. `Read` has no such cap, and the
planner/reviewer prompts only *ask* for region reads. Measured across planner subagent runs:
Read results totalled 16.2M bytes, 5.0M of it in single results over 12K; in the last 40
planner/reviewer runs 83 of 284 Reads carried no `limit`. A prompt rule that is ignored 29% of
the time is not a control. This hook makes the region-read rule mechanical.

THE DECISION, ONCE
------------------
Block only when ALL of these hold: the tool is `Read`, `CK_RAW_READ` is not `1`, a `file_path`
is present, there is no integer `limit` in 1..200, the path is not allowlisted, the path is a
readable regular file, and it has more than 200 lines. Anything else -> exit 0.

FAIL DIRECTION
--------------
Every unexpected exception -> exit 0. A guard that breaks must not break `Read` for every agent
in the fleet; that is the fail-soft convention `output_filter.py` documents for the output path.
But a *decision* to block is `exit 2` with one line on stderr and nothing on stdout - project
hard rule 2. Never exit 1, never stdout-as-decision.

ESCAPE HATCH
------------
`CK_RAW_READ=1` in the environment disables the guard for that process tree, and the block
message names it. A control with no documented override becomes a reason to disable the whole
hook chain.

stdlib only, py3.9 target.
"""

import fnmatch
import json
import os
import sys

# More than this many lines and a Read must declare a window.
THRESHOLD = 200

# Paths an agent is EXPECTED to read whole: its own contract documents and the artifacts it
# is being handed. Windowing these would force a second Read to reassemble one document.
ALLOWLIST = (
    ".claude/plans/plan-*.md",
    ".claude/plans/ops-*.json",
    ".claude/agents/_shared/*.md",
    "CLAUDE.md",
    ".ai/*.md",
)


def _relative(path):
    """Project-relative, forward-slashed. Falls back to the input on any failure."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        rel = os.path.relpath(os.path.abspath(path), root)
    except Exception:
        rel = path
    return rel.replace(os.sep, "/")


def _allowlisted(path):
    rel = _relative(path)
    base = rel.rsplit("/", 1)[-1]
    for pattern in ALLOWLIST:
        if fnmatch.fnmatch(rel, pattern):
            return True
        # A bare-basename pattern (CLAUDE.md) applies at any depth.
        if "/" not in pattern and fnmatch.fnmatch(base, pattern):
            return True
    return False


# Read renders these itself (images visually, PDFs by page), so a line count is meaningless:
# a screenshot "has" thousands of lines of compressed bytes and was being blocked.
NON_TEXT_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".ico", ".pdf",
)


def _not_text(path):
    """True for a known image/PDF extension, or a NUL byte in the first 8 KiB (binary)."""
    if path.lower().endswith(NON_TEXT_EXTENSIONS):
        return True
    with open(path, "rb") as handle:
        return b"\0" in handle.read(8192)


def _longer_than_threshold(path):
    """True when the file has more than THRESHOLD lines. Short-circuits at THRESHOLD+1,
    so a multi-million-line file costs 201 iterations, not a full scan."""
    count = 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for _ in handle:
            count += 1
            if count > THRESHOLD:
                return True
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    try:
        if payload.get("tool_name") != "Read":
            return 0
        if os.environ.get("CK_RAW_READ") == "1":
            return 0

        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        path = tool_input.get("file_path")
        if not isinstance(path, str) or not path.strip():
            return 0
        # Resolve ONCE, against the same root `_relative()` uses. Otherwise a relative
        # `file_path` is allowlist-matched against CLAUDE_PROJECT_DIR but stat'd against the
        # hook process cwd, and the guard silently fails open whenever they differ.
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        if not os.path.isabs(path):
            path = os.path.join(root, path)

        limit = tool_input.get("limit")
        if isinstance(limit, bool):
            limit = None
        if isinstance(limit, int) and 0 < limit <= THRESHOLD:
            return 0

        if _allowlisted(path):
            return 0
        if not os.path.isfile(path):
            # Missing or not a regular file: let Read report it in its own words.
            return 0
        if _not_text(path):
            return 0
        if not _longer_than_threshold(path):
            return 0
    except Exception:
        # The guard's own bug must never block a read.
        return 0

    sys.stderr.write(
        "BLOCKED read-window-guard: %s has more than %d lines and this Read declares no "
        "usable limit. Re-issue it with limit<=%d (plus offset), or read the region with "
        "grep -n -C3 / sed -n 'a,bp'. Override for one process tree with CK_RAW_READ=1.\n"
        % (path, THRESHOLD, THRESHOLD)
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

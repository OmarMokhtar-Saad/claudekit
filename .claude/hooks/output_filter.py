#!/usr/bin/env python3
"""
output_filter.py - PostToolUse stdout filter for noisy Bash commands (adoption item B1).

WHY IT LIVES HERE AND NOT IN .claude/hooks/: scripts/gen-docs.py:75 sets
HOOK_GLOBS = ("*.sh", "*.py") and counts every matching file in .claude/hooks/, so a new
hook script there would move the published component count and redden the docs-drift gate.
heal_local_settings.py set the precedent for hook-shaped scripts that live in
.claude/operations/scripts/ instead; this follows it. install.sh:222-223 already copies
*.py AND *.json out of this directory, so the engine and its filter file reach every kitted
project with no installer change and no new entry in the mkdir list at install.sh:204.

WHAT IT DOES: Claude Code's PostToolUse hook may return
hookSpecificOutput.updatedToolOutput, which "Replaces the tool output before it is sent to
the model" (verified against the 2.1.273 binary, not assumed). This script rewrites ONLY
the `stdout` field of a Bash tool_response, driven by declarative JSON filters.

FOUR SAFETY PROPERTIES, strongest first:

1. It cannot touch a failed command. The host does not run PostToolUse for a Bash call that
   exits non-zero -- PostToolUseFailure does, and that event's hook schema has no
   updatedToolOutput field at all. Verified empirically 2026-09-16: a deliberate
   `false; exit 3` produced no [post-tool-use] entry in .claude/hooks/hooks.log while the
   successful calls either side of it did.
2. stderr is never touched. Only tool_response["stdout"] is rewritten; every other key of
   the response object is echoed back unchanged, which also makes the rewrite schema-valid
   by construction.
3. Fail-soft, twice over. Any exception here exits 0 printing nothing, so the original
   output stands. Independently the host validates updatedToolOutput against the tool's
   output schema and logs "using original output" on a mismatch.
4. NEVER_FILTER denies filtering for commands whose stdout a gate or a reviewer reads
   verbatim (the generator --check gates, validate-config-json.py, review-record.py,
   execute-json-ops.py, ck doctor, the linters). It is applied AFTER the local-override
   merge, so a project-local filter file can never re-enable them.

ESCAPE HATCH: prefix the command with CK_RAW_OUTPUT=1, e.g.
`CK_RAW_OUTPUT=1 python3 -m pytest tests/ -q`, and no filter runs. Every summary line this
script emits names that hatch, so the escape is discoverable from the filtered output
itself. CK_OUTPUT_FILTER=off in the hook's own environment disables the script wholesale.

HIERARCHY, two levels and deliberately not three: output-filters.json ships with the kit;
output-filters.local.json is created per project and overrides base filters by `id`. The
local file is never shipped, so it never appears in .claudekit-manifest.json -- which is
precisely what makes preserve_assets.py classify it as custom and keep it across upgrades.

Zero third-party dependencies; Python 3.9+ (no tomllib, no TOML: JSON is parseable today).
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Pattern, Tuple

SCHEMA_VERSION = 1
BASE_NAME = "output-filters.json"
LOCAL_NAME = "output-filters.local.json"

# Bounds. A filter file is data, and unbounded data on a hot path is a denial of service
# against every Bash call in the session.
MAX_FILTERS = 64
MAX_PATTERN_CHARS = 400

# Commands whose stdout is read verbatim by a gate, a generator check, or a reviewer.
# Applied after the local-override merge: a downstream filter file cannot override this.
NEVER_FILTER: Tuple[str, ...] = (
    r"gen-docs\.py",
    r"gen-registry\.py",
    r"gen-model-policy\.py",
    r"gen-plan-index\.py",
    r"check-context-floor\.py",
    r"check-plan-artifacts\.py",
    r"validate-config-json\.py",
    r"execute-json-ops\.py",
    r"review-record\.py",
    r"\bck\s+doctor\b",
    r"\bclaudekit\s+doctor\b",
    r"\bshellcheck\b",
    r"\bmypy\b",
    r"\bruff\b",
)

_NEVER: Tuple[Pattern[str], ...] = tuple(re.compile(p) for p in NEVER_FILTER)
_RAW_MARKER = re.compile(r"(^|\s)CK_RAW_OUTPUT=1(\s|$)")
_LEADING_MARKS = re.compile(r"^\S+")


def filters_dir() -> str:
    """Where the two filter files live. CK_OUTPUT_FILTERS_DIR is a test-only seam."""
    return os.environ.get("CK_OUTPUT_FILTERS_DIR") or os.path.dirname(os.path.abspath(__file__))


def _read_filter_file(path: str) -> List[Dict[str, Any]]:
    """Filters from one file, or [] for anything at all wrong with it. A malformed or
    hostile filter file must degrade to 'no filtering', never to an exception."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        return []
    raw = doc.get("filters")
    if not isinstance(raw, list):
        return []
    return [f for f in raw[:MAX_FILTERS] if isinstance(f, dict)]


def load_filters(directory: str) -> List[Dict[str, Any]]:
    """Base filters, overridden by id from the project-local file; local-only ids append."""
    base = _read_filter_file(os.path.join(directory, BASE_NAME))
    local = _read_filter_file(os.path.join(directory, LOCAL_NAME))
    by_id: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for spec in base + local:
        fid = spec.get("id")
        if not isinstance(fid, str) or not fid:
            continue
        if fid not in by_id:
            order.append(fid)
        by_id[fid] = spec
    return [by_id[f] for f in order][:MAX_FILTERS]


def compile_filter(spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A usable filter, or None. Invalid regex is dropped, never silently prefix-matched:
    a filter that quietly means something other than what it says is worse than no filter."""
    match = spec.get("match")
    if not isinstance(match, str) or not match or len(match) > MAX_PATTERN_CHARS:
        return None
    ops = spec.get("operations")
    if not isinstance(ops, list) or not ops:
        return None
    try:
        compiled_match = re.compile(match)
    except re.error:
        return None
    strip: Optional[Pattern[str]] = None
    tail: Optional[int] = None
    for op in ops:
        if not isinstance(op, dict):
            return None
        if "strip_lines_matching" in op:
            pat = op["strip_lines_matching"]
            if not isinstance(pat, str) or len(pat) > MAX_PATTERN_CHARS:
                return None
            try:
                strip = re.compile(pat)
            except re.error:
                return None
        elif "tail_lines" in op:
            # Lossy by definition: it drops the head, which is where a stack trace starts.
            # Only a filter that declares itself lossy may use it.
            if spec.get("lossy") is not True:
                return None
            n = op["tail_lines"]
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                return None
            tail = n
        else:
            return None
    if strip is None and tail is None:
        return None
    summary = spec.get("summary")
    return {
        "id": spec["id"],
        "match": compiled_match,
        "strip": strip,
        "tail": tail,
        "summary": summary if isinstance(summary, str) else "",
    }


def select(command: str, specs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The first filter matching this command, or None. NEVER_FILTER wins over everything,
    and is checked here -- after the merge in load_filters -- on purpose."""
    for never in _NEVER:
        if never.search(command):
            return None
    for spec in specs:
        compiled = compile_filter(spec)
        if compiled is not None and compiled["match"].search(command):
            return compiled
    return None


def apply_filter(compiled: Dict[str, Any], text: str) -> Tuple[str, bool]:
    """The rewritten stdout and whether anything actually changed."""
    lines = text.split("\n")
    kept: List[str] = []
    removed = 0
    marks = 0
    strip = compiled["strip"]
    for line in lines:
        if strip is not None and strip.search(line):
            removed += 1
            lead = _LEADING_MARKS.match(line)
            if lead is not None:
                marks += len(lead.group(0))
            continue
        kept.append(line)
    dropped = 0
    tail = compiled["tail"]
    if tail is not None and len(kept) > tail:
        dropped = len(kept) - tail
        kept = kept[-tail:]
    if removed == 0 and dropped == 0:
        return text, False
    summary = compiled["summary"] or (
        "[ck output-filter: " + compiled["id"] + "] {removed} line(s) removed. "
        "Prefix the command with CK_RAW_OUTPUT=1 for raw output."
    )
    summary = (summary.replace("{removed}", str(removed))
                      .replace("{marks}", str(marks))
                      .replace("{dropped}", str(dropped))
                      .replace("{id}", str(compiled["id"])))
    return "\n".join([summary] + kept), True


def rewrite(payload: Dict[str, Any], directory: str) -> Optional[Dict[str, Any]]:
    """The replacement tool_response, or None to leave the output alone."""
    if payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command:
        return None
    if _RAW_MARKER.search(command):
        return None
    response = payload.get("tool_response")
    if not isinstance(response, dict):
        return None
    stdout = response.get("stdout")
    if not isinstance(stdout, str) or not stdout:
        return None
    compiled = select(command, load_filters(directory))
    if compiled is None:
        return None
    new_stdout, changed = apply_filter(compiled, stdout)
    if not changed:
        return None
    # Echo the whole response with stdout swapped. Returning a partial object would fail the
    # host's output-schema check, and stderr must survive byte-for-byte.
    updated = dict(response)
    updated["stdout"] = new_stdout
    return updated


def main() -> int:
    if os.environ.get("CK_OUTPUT_FILTER", "").lower() == "off":
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        updated = rewrite(payload, filters_dir())
        if updated is None:
            # No identity rewrite, ever: the host runs PostToolUse hooks in parallel against
            # the ORIGINAL output and resolves rewrites last-write-wins, so an identity
            # rewrite here could clobber a sibling hook's real one.
            return 0
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": updated,
            }
        }))
    except Exception:
        # Fail-soft: say nothing and the original output is what Claude receives.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

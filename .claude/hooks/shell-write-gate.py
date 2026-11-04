#!/usr/bin/env python3
"""shell-write-gate.py - PreToolUse/Bash: deny obvious shell writes to protected paths.

Protected: .claude/reports/reviews/ (the authoritative plan-approval records), the
settings files (.claude/settings.json, .claude/settings.local.json) and
.claude/plan-gate.globs. plan-gate.sh already denies Edit/Write there; this closes the
same paths against the cheapest shell forms: > >> tee, sed -i, touch, cp, mv, and
`python -c` / heredoc scripts that open-for-write.

HONEST LIMIT (kit hard rule 6): a denylist speed bump, not a sandbox. Obvious forms
only; an obfuscated command can still forge a record. The owner approval step is the
real control.

FAILS CLOSED, unlike bash-payload-gate: a payload that cannot be parsed blocks. No
ECC_HOOK_PROFILE early exit - it binds under `minimal` too.
Blocking = exit 2 + stderr (kit hard rule 2).
"""
import json
import re
import sys

PROTECTED = (
    r"\.claude/reports/reviews",
    r"\.claude/settings(?:\.local)?\.json",
    r"\.claude/plan-gate\.globs",
    r"plan-gate\.globs",
)
_PATH = "(?:%s)" % "|".join(PROTECTED)
# Verbs that write to (or replace) their destination argument.
_WRITE_VERB = re.compile(
    r"(?:^|[;&|(`]|\s)(?:tee|touch|cp|mv|install|ln|dd|truncate|rm|rsync|perl|sed|"
    r"awk|python3?|ruby|node)\b")
_REDIRECT = re.compile(r">>?\s*['\"]?[^\s;&|'\"]*" + _PATH)
_SED_I = re.compile(r"\bsed\b[^;&|\n]*\s-[A-Za-z]*i")
_PY_WRITE = re.compile(r"open\([^)]*['\"][wax]\+?b?['\"]|write_text|write_bytes|\.write\(")


def _violates(command: str) -> str:
    """Name the matched form, or '' when the command is not an obvious protected write."""
    if not re.search(_PATH, command):
        return ""
    if _REDIRECT.search(command):
        return "redirect (> / >>)"
    for segment in re.split(r"[;&|\n]+", command):
        if not re.search(_PATH, segment):
            continue
        if re.search(r"\b(?:tee|touch|cp|mv|install|ln|dd|truncate|rm|rsync)\b", segment):
            return "write verb"
        if _SED_I.search(segment):
            return "sed -i"
        if re.search(r"\b(?:python3?|ruby|node|perl)\b", segment) and _PY_WRITE.search(command):
            return "script open-for-write"
    if re.search(r"\b(?:python3?|ruby|node|perl)\b", command) and _PY_WRITE.search(command):
        return "script open-for-write"
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            raise ValueError("no command string")
    except Exception as exc:  # fail CLOSED
        sys.stderr.write("BLOCKED shell-write-gate: could not parse the Bash payload (%s); "
                         "refusing an unverified command.\n" % exc)
        return 2
    form = _violates(command)
    if not form:
        return 0
    sys.stderr.write(
        "BLOCKED shell-write-gate: %s targets a protected path (review records, settings "
        "files or plan-gate.globs). These are owner-only: ask the owner to run it with "
        "`! <command>`. (Speed bump, not a sandbox.)\n" % form)
    return 2


if __name__ == "__main__":
    # A literal sys.exit(2) path exists in main(); never exit 1 for a block.
    sys.exit(main())

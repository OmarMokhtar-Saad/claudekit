#!/usr/bin/env python3
"""memory-first.py - PreToolUse (WARN ONLY, never blocks): one line when the session is about to make
its FIRST edit without having looked at project memory.

WHY: memory is only worth anything if it is read before the work it would change. Nothing
else notices a session that edits straight away and ignores what earlier sessions recorded.

HOW A LOOKUP IS OBSERVED (this hook sees every tool call and keeps a per-session flag):
  * Read/Grep/Glob whose path or pattern is inside a memory directory (`.claude/memory`, which is
    `claudekit.memory.memory_dir(root)`, or `.claude/agent-memory`); or
  * a Bash command that runs `ck memory` / `claudekit memory` or names a memory directory.
The SessionStart slice (session-memory-context.py) is NOT a lookup: it is a bounded excerpt
the session did not choose.

WHEN IT SPEAKS: only on the first Edit/Write/MultiEdit/NotebookEdit of a session, only when
the project actually has memory to look up (a store or a memory directory with content), only
once. Silent otherwise.

MODE (`"memory_first": {"mode": "warn"|"off"}` in .claude/settings.local.json, then
.claude/settings.json; env CK_MEMORY_FIRST overrides; default `warn`). It never blocks and always
exits 0, errors included:
  warn  - one short additionalContext line.
  off   - nothing.

DELIVERY: `hookSpecificOutput.additionalContext` JSON on stdout - the only form that reaches the
model - so it runs DIRECTLY from settings.json. Its dispatch-registry row passes `--dispatched`,
which exits 0 at once (test_dispatch_merge requires every settings hook to be listed, and
dispatch.sh would otherwise run it twice). Subagent calls (agent_id in the payload) are ignored.
`CK_NO_MEMORY_FIRST=1` silences it. State: .claude/hooks/.state/memfirst-<session>.
stdlib only, py3.9.
"""

import json
import os
import re
import sys

MEMORY_DIRS = (".claude/memory", ".claude/agent-memory")
LOOKUP_TOOLS = ("Read", "Grep", "Glob", "Bash")
MUTATION_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
MODES = ("warn", "off")
DEFAULT_MODE = "warn"
_CLI = re.compile(r"(?:^|[\s;&|(])(?:ck|claudekit)\s+memory\b")


def _root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _state_path(root, session_id):
    if not os.path.isdir(os.path.join(root, ".claude", "hooks")):
        return None
    safe = "".join(ch for ch in str(session_id or "unknown") if ch.isalnum() or ch in "-_.")[:64]
    return os.path.join(root, ".claude", "hooks", ".state", "memfirst-%s" % (safe or "unknown"))


def _load(path):
    state = {"lookup": False, "mutated": False}
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
        if isinstance(value, dict):
            state.update({k: bool(value.get(k)) for k in state})
    except (OSError, ValueError):
        pass
    return state


def _save(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def mode(root):
    env = os.environ.get("CK_MEMORY_FIRST", "").strip().lower()
    if env in MODES:
        return env
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(root, ".claude", name), encoding="utf-8") as fh:
                value = (json.load(fh).get("memory_first") or {}).get("mode")
        except Exception:
            continue
        if value in MODES:
            return value
    return DEFAULT_MODE


def _in_memory(text):
    text = str(text or "").replace("\\", "/")
    return any(d in text for d in MEMORY_DIRS)


def is_lookup(tool, tool_input):
    """True when this call reads project memory."""
    data = tool_input if isinstance(tool_input, dict) else {}
    if tool in ("Read", "Grep", "Glob"):
        return any(_in_memory(data.get(k)) for k in ("file_path", "path", "pattern"))
    if tool == "Bash":
        command = str(data.get("command") or "")
        return bool(_CLI.search(command)) or _in_memory(command)
    return False


def has_memory(root):
    """A memory store or memory directory with something in it."""
    for rel in MEMORY_DIRS:
        path = os.path.join(root, *rel.split("/"))
        try:
            names = [n for n in os.listdir(path) if n.lower() != "readme.md" and not n.startswith(".")]
        except OSError:
            continue
        if names:
            return True
    return False


NOTE = ("[ck memory-first] first edit this session and no memory lookup yet: read .claude/memory "
        "(`ck memory list`) or .claude/agent-memory before changing code. Silence: "
        "CK_NO_MEMORY_FIRST=1.")

def decide(payload, root):
    """Return (exit_code, stdout_line or None, stderr_line or None); the exit code is always 0."""
    tool = payload.get("tool_name")
    if payload.get("agent_id") or tool not in LOOKUP_TOOLS + MUTATION_TOOLS:
        return 0, None, None
    path = _state_path(root, payload.get("session_id"))
    if path is None:
        return 0, None, None
    state = _load(path)
    if tool in LOOKUP_TOOLS:
        if not state["lookup"] and is_lookup(tool, payload.get("tool_input")):
            state["lookup"] = True
            _save(path, state)
        return 0, None, None
    if state["lookup"] or state["mutated"]:
        return 0, None, None
    chosen = mode(root)
    if chosen == "off" or not has_memory(root):
        state["mutated"] = True
        _save(path, state)
        return 0, None, None
    state["mutated"] = True
    _save(path, state)
    note = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": NOTE}})
    return 0, note, None


def main():
    if "--dispatched" in sys.argv[1:] or os.environ.get("CK_NO_MEMORY_FIRST") == "1":
        return 0
    root = _root()
    try:
        payload = json.load(sys.stdin)
        code, out, err = decide(payload, root)
    except Exception:
        return 0
    if out:
        sys.stdout.write(out + "\n")
    if err:
        sys.stderr.write(err + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())

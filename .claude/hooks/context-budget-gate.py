#!/usr/bin/env python3
"""context-budget-gate.py - PreToolUse: a ceiling on session context, and on who may be spawned.

WHY THIS EXISTS
---------------
Measured 2026-09-18 across live sessions: one main session reached 842K tokens of context over
428 turns (202M cumulative) with zero compactions; two others sat at 283K/159 turns and
241K/131 turns; a fourth reached 209K in 43 turns and then routed a redesign to the built-in
`general-purpose` agent, which burned 56 turns to 246K (8.7M tokens) on its own. Every cap this
kit shipped the same day - the 12,000-char Bash stdout cap, read-window-guard, per-agent
`maxTurns`, per-role `effort` - is declared in OUR agent frontmatter. None of them can reach
the main agent (it has no frontmatter) or a built-in agent (we do not author its definition).
A PreToolUse hook can: it fires for the main agent and for every subagent, and its payload
carries `session_id` and `transcript_path`.

THE TWO DECISIONS
-----------------
1. CONTEXT BUDGET. The payload names the caller's OWN transcript. Each assistant line in that
   JSONL carries `message.usage`; input_tokens + cache_read_input_tokens +
   cache_creation_input_tokens on the LAST assistant line is the context in force right now.
   At or above CK_CONTEXT_WARN (200,000) the call is allowed and one advisory line is printed,
   at most once per 20 guarded calls per session. At or above CK_CONTEXT_BLOCK (400,000) the
   call is refused: past that size every further tool call re-reads the whole window, so the
   cheapest correct move is /save-session and then /compact, or a fresh session.
   Subagents get this per-agent for free: a subagent's transcript_path is its own
   `<project>/<session-id>/subagents/agent-*.jsonl`, so the number read here is THAT agent's
   context, never the parent's, and no cross-process bookkeeping is needed.
   A subagent is NEVER hard-blocked, though: it can run neither /compact nor /save-session, and
   the hatch is read from the hook process's inherited environment, which a subagent cannot set
   for itself. Blocking it would leave it with no route out, so at or above the block line a
   subagent gets one advisory telling it to hand its findings back, and the call is allowed.
2. SPAWN GUARD. `general-purpose` is a built-in agent: no maxTurns, no effort, no model pin and
   no prompt of ours. It is the one dispatch this kit cannot bound, so an Agent/Task call that
   names it - or names nothing - is refused and the scoped alternatives are named instead.
   Every kit agent, and the other built-ins (Explore, Plan, claude-code-guide), fall through.

ONLY THE TAIL IS READ
---------------------
A long session's transcript reaches tens of megabytes, and this handler runs before EVERY
guarded tool call. It seeks to the last TAIL_BYTES and parses only that window, discarding the
leading partial line. When no usage record falls inside the window the hook ALLOWS - a missed
block, never a false one. Widening the window on a miss was considered and rejected: it buys
little and it costs the only cheap property this design has.

INSTRUMENTATION
---------------
`CK_CONTEXT_TRACE=1` prints one extra stderr line, `read_bytes=<N>`, counting every byte this
process read from the transcript. It exists so the tail-read property is TESTABLE: a whole-file
refactor is invisible in the verdict on most transcripts (the last usage record is the same
either way) but changes read_bytes from 65,536 to the size of the file. The knob is off by
default, never changes an exit code, and is the mechanism `test_only_the_tail_is_read` asserts.

FAIL DIRECTION
--------------
Every unexpected condition - unparseable payload, missing or rotated or malformed transcript,
no usage in the window, unwritable state directory - exits 0. A broken budget gate must not
stop the fleet from working; that is the fail-soft convention read-window-guard.py and
output_filter.py already document. A DECISION to block is `exit 2` with one line on stderr and
nothing on stdout - project hard rule 2. Never exit 1, never stdout-as-decision.

ESCAPE HATCHES
--------------
`CK_RAW_CONTEXT=1` disables the context budget (warn and block) for that process tree.
`CK_ALLOW_GENERAL_PURPOSE=1` disables the spawn guard. Both are named in the message that
blocks, because a control with no documented override becomes a reason to disable the whole
hook chain.

stdlib only, py3.9 target.
"""

import json
import os
import sys

# Bytes of transcript tail parsed per call. 64 KB covers many assistant turns and costs one
# seek + one read regardless of how large the file has grown.
TAIL_BYTES = 65536

DEFAULT_WARN = 200000
DEFAULT_BLOCK = 400000

# One advisory line per this many guarded calls, per session.
WARN_EVERY = 20

# Tools this gate decides on. Everything else -> exit 0. `Task` is guarded alongside `Agent`
# because agent dispatch has shipped under both names; guarding both costs nothing and is the
# difference between a live guard and an inert one. `NotebookEdit` is here because the registry
# matcher is an unanchored re.search, so the dispatcher already routes it to this handler - a
# tool the dispatcher sends here but this table omits is a hole, not a default.
GUARDED_TOOLS = ("Write", "Edit", "NotebookEdit", "Bash", "Agent", "Task")
SPAWN_TOOLS = ("Agent", "Task")

UNBOUNDED_AGENT = "general-purpose"

# Subagent transcripts live under <project>/<session-id>/subagents/agent-*.jsonl.
SUBAGENT_MARKER = "/subagents/"

USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

# Bytes read from the transcript by this process; reported only under CK_CONTEXT_TRACE=1.
_READ_BYTES = [0]


def _threshold(name, default):
    """Env override, or the default. A non-integer or non-positive value falls back rather
    than silently disabling the gate."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _is_subagent(path):
    """True when this transcript belongs to a spawned agent rather than a main session."""
    if not isinstance(path, str):
        return False
    return SUBAGENT_MARKER in path.replace("\\", "/")


def _tail_lines(path):
    """The last TAIL_BYTES of `path` as lines, with the leading fragment dropped."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        if size > TAIL_BYTES:
            handle.seek(size - TAIL_BYTES)
        blob = handle.read(TAIL_BYTES)
    _READ_BYTES[0] += len(blob)
    lines = blob.decode("utf-8", errors="replace").split("\n")
    if size > TAIL_BYTES and lines:
        # The window almost never starts on a line boundary; the first element is a fragment.
        # It is dropped unparsed: a fragment whose tail happens to be valid JSON would
        # otherwise be read as a whole record and could decide a block on half a line.
        lines = lines[1:]
    return lines


def _context_size(path):
    """Tokens of context from the LAST assistant usage record in the tail, else None."""
    if not isinstance(path, str) or not path.strip():
        return None
    if not os.path.isfile(path):
        return None
    for line in reversed(_tail_lines(path)):
        line = line.strip()
        if not line or '"usage"' not in line:
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        if (record.get("type") not in (None, "assistant")
                and message.get("role") not in (None, "assistant")):
            continue
        total = 0
        for key in USAGE_KEYS:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                total += value
        if total > 0:
            return total
    return None


def _state_dir():
    """Where the warn counters live, or None when there is no project root to write under.

    `CLAUDE_PROJECT_DIR` is the only authority. Falling back to `os.getcwd()` unconditionally
    made the hook create `.claude/hooks/.state/` under whatever directory it happened to be
    invoked from; cwd is accepted now only when it already looks like a kitted project.
    """
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if not root:
        root = os.getcwd()
        if not os.path.isdir(os.path.join(root, ".claude", "hooks")):
            return None
    return os.path.join(root, ".claude", "hooks", ".state")


def _should_warn(session_id):
    """True at most once per WARN_EVERY guarded calls that are already over the warn line.

    State is one counter file per session under .claude/hooks/.state/. No writable project
    root, or any failure -> True: the advisory is one line and cannot change a verdict, so
    repeating it is the safer failure.
    """
    state_dir = _state_dir()
    if state_dir is None:
        return True
    try:
        os.makedirs(state_dir, exist_ok=True)
        safe = "".join(
            ch for ch in str(session_id or "unknown") if ch.isalnum() or ch in "-_."
        )[:64] or "unknown"
        state = os.path.join(state_dir, "context-budget-%s" % safe)
        seen = 0
        if os.path.isfile(state):
            with open(state, "r", encoding="utf-8", errors="replace") as handle:
                try:
                    seen = int(handle.read().strip() or "0")
                except ValueError:
                    seen = 0
        with open(state, "w", encoding="utf-8") as handle:
            handle.write("%d\n" % (seen + 1))
        return seen % WARN_EVERY == 0
    except Exception:
        return True


def _spawns_unbounded_agent(tool_input):
    """True when this Agent/Task call dispatches to the one agent this kit cannot bound."""
    if os.environ.get("CK_ALLOW_GENERAL_PURPOSE") == "1":
        return False
    if not isinstance(tool_input, dict):
        return False
    subagent = tool_input.get("subagent_type")
    if subagent is None:
        return True
    if not isinstance(subagent, str):
        return False
    return not subagent.strip() or subagent.strip() == UNBOUNDED_AGENT


# The block message names /save-session as the way out, and /save-session is a Write to this
# file. Refusing it would leave the way out blocked. Only the session brief is exempt.
SESSION_SAVE_SUFFIX = os.path.join(".claude", "session-context.md")


def _is_session_save(tool_name, tool_input):
    if tool_name not in ("Write", "Edit") or not isinstance(tool_input, dict):
        return False
    path = tool_input.get("file_path")
    return isinstance(path, str) and os.path.normpath(path).endswith(SESSION_SAVE_SUFFIX)


def _decide(payload):
    """(exit_code, stderr_line) or None. Nothing is emitted from here."""
    tool_name = payload.get("tool_name") or payload.get("name")
    if tool_name not in GUARDED_TOOLS:
        return None

    # A warning is HELD, not returned, so a de-duplicated advisory can never swallow the
    # spawn check below it.
    note = None

    if os.environ.get("CK_RAW_CONTEXT") != "1":
        transcript_path = payload.get("transcript_path")
        size = _context_size(transcript_path)
        if size is not None:
            block = _threshold("CK_CONTEXT_BLOCK", DEFAULT_BLOCK)
            warn = _threshold("CK_CONTEXT_WARN", DEFAULT_WARN)
            if size >= block and _is_subagent(transcript_path):
                # Not a block: a subagent has no /compact, no /save-session and no way to set
                # the hatch in its own environment. The only move it CAN make is to stop.
                note = (0,
                        "context-budget-gate: this subagent is at %dK tokens of context "
                        "(block line %dK). A subagent cannot run /compact or /save-session - "
                        "stop exploring, write up what you already have and hand it back to "
                        "your caller now.\n" % (size // 1000, block // 1000))
            elif size >= block and not _is_session_save(tool_name, payload.get("tool_input")):
                return (2,
                        "BLOCKED context-budget-gate: this session is at %dK tokens of "
                        "context (block at %dK). Type /compact now - it is not a tool call, so "
                        "this gate never blocks it; /save-session works once you are back under "
                        "the line. Set /autocompact below %dK so this never fires. Override for "
                        "one process tree with CK_RAW_CONTEXT=1.\n"
                        % (size // 1000, block // 1000, block // 1000))
            elif size >= warn and _should_warn(payload.get("session_id")):
                note = (0,
                        "context-budget-gate: context %dK tokens (warn %dK, block %dK) - run "
                        "/save-session then /compact, or start a new session.\n"
                        % (size // 1000, warn // 1000, block // 1000))

    if tool_name in SPAWN_TOOLS and _spawns_unbounded_agent(payload.get("tool_input")):
        return (2,
                "BLOCKED context-budget-gate: `general-purpose` is a built-in agent - the "
                "maxTurns, model and effort in this kit's frontmatter cannot reach it, and one "
                "measured dispatch ran 56 turns to 246K tokens. Spawn a scoped agent instead: "
                "explore (search), planner (plans), code-reviewer (review), docs (writing). "
                "Override for one process tree with CK_ALLOW_GENERAL_PURPOSE=1.\n")

    return note


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        decision = _decide(payload)
    except Exception:
        # The gate's own bug must never stop a tool call.
        decision = None
    if os.environ.get("CK_CONTEXT_TRACE") == "1":
        # Instrumentation only; never a decision, never on by default.
        sys.stderr.write("read_bytes=%d\n" % _READ_BYTES[0])
    if decision is None:
        return 0
    code, message = decision
    sys.stderr.write(message)
    return code


if __name__ == "__main__":
    sys.exit(main())

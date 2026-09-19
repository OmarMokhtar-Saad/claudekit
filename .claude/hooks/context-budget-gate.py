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
   A subagent's hook receives the PARENT's transcript_path plus `agent_id`, so the file read
   for it is `<session>/subagents/agent-<agent_id>.jsonl` beside the parent's - THAT agent's
   context, never the parent's (measuring the parent's blocked every subagent of a big session).
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
`CK_RAW_CONTEXT=1` disables the context budget (warn, block and the per-agent spend cap)
for that process tree.
`CK_AGENT_BUDGET=<tokens>` moves the per-subagent spend line (default 15,000,000).
`CK_ALLOW_MODEL_OVERRIDE=1` lets an Agent call spawn a scoped agent on a higher tier than its
frontmatter declares.

AGENT CONTRACTS (subagents only)
--------------------------------
For a spawned agent whose type names a file under .claude/agents/, the frontmatter is enforced
here because nothing else enforces it: `tools:` (with Write/Edit scoped to the agent's own
.claude/agent-memory/<type>/ when `memory:` is declared), `maxTurns:` (counted as tool calls
including Read/Grep/Glob), and, at spawn time, `model:` against the Agent call's model param.
Read, Grep and Glob are never refused.
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

DEFAULT_WARN = 150000
DEFAULT_BLOCK = 400000

# One advisory line per this many guarded calls, per session.
WARN_EVERY = 20

# A subagent's cost is turns x context, not context alone, and the context cap can only ever
# see one of the two factors. Measured on one 297M-token session: the planner that dominated
# it (45.8M) sat at a 234K median for 118 guarded calls and NEVER crossed the 400K context
# line, so no context threshold could have fired on it. The product is what ran away, so the
# product is what is capped. calls x context predicted the six measured agents to within 10%
# (planner 216 turns x 234K = 50M vs 45.8M actual), which is what makes it a usable proxy and
# not a guess. 15M is a first calibration against that session, not a law: an explore agent
# there (34 guarded calls x 63K = 2.1M) stays far under it, and the runaway planner trips it
# roughly halfway through.
DEFAULT_AGENT_BUDGET = 15000000

# The harness grants Write+Edit to every agent that declares `memory:` so it can keep its own
# notes; on the measured session that turned a read-only reviewer into a 17-Write author and a
# planner into a 64-Edit implementer. Those tools are scoped back to the agent's own memory
# directory here, so memory keeps working and the frontmatter contract means what it says.
MEMORY_DIR_PARTS = (".claude", "agent-memory")

# Frontmatter `model:` values and Agent-call `model` params both name a capability tier by
# substring; anything unrecognised is not judged.
MODEL_TIERS = (("haiku", 0), ("sonnet", 1), ("opus", 2))

# Tools this gate decides on. Everything else -> exit 0. `Task` is guarded alongside `Agent`
# because agent dispatch has shipped under both names; guarding both costs nothing and is the
# difference between a live guard and an inert one. `NotebookEdit` is here because the registry
# matcher is an unanchored re.search, so the dispatcher already routes it to this handler - a
# tool the dispatcher sends here but this table omits is a hole, not a default.
GUARDED_TOOLS = ("Write", "Edit", "NotebookEdit", "Bash", "Agent", "Task")
SPAWN_TOOLS = ("Agent", "Task")

# Read, Grep and Glob are COUNTED for a subagent (they are most of a reviewer's turns: one
# measured reviewer made 3 guarded calls and 70 reads) but are never refused, for anyone. Every
# refusal in this file ends "read what you have and hand it back", and a gate that closed the
# read path would turn its own advice into a trap.
COUNTED_TOOLS = GUARDED_TOOLS + ("Read", "Grep", "Glob")
NEVER_REFUSED = ("Read", "Grep", "Glob")

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


def _caller_transcript(payload):
    """(transcript to measure, is-subagent) for the agent that made THIS call.

    A hook fired inside a subagent receives the PARENT's transcript_path plus `agent_id`.
    Measuring that path read the parent's context, so a large main session blocked its own
    subagents. With an agent_id the caller's transcript is
    `<session>/subagents/agent-<agent_id>.jsonl` beside the parent's file.
    """
    path = payload.get("transcript_path")
    agent_id = payload.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        if not agent_id.isalnum() or not isinstance(path, str):
            return None, True
        own = os.path.join(os.path.splitext(path)[0], "subagents", "agent-%s.jsonl" % agent_id)
        return own, True
    return path, _is_subagent(path)


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


def _bump_agent_calls(transcript_path):
    """Guarded calls this subagent has made, including this one, or None when uncountable.

    Keyed by the caller's OWN transcript basename, never by session_id: a subagent inherits
    its parent's session_id, so a session-keyed counter would pool every agent in the tree
    into one running total and refuse the third agent's first call for the first agent's
    spend. The basename is `agent-<id>.jsonl` and is unique per agent.

    Any failure returns None, which skips the cap. A counter that cannot be read is not
    evidence of overspend.
    """
    state_dir = _state_dir()
    if state_dir is None or not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        os.makedirs(state_dir, exist_ok=True)
        safe = "".join(
            ch for ch in os.path.basename(transcript_path)
            if ch.isalnum() or ch in "-_."
        )[:80]
        if not safe:
            return None
        state = os.path.join(state_dir, "agent-spend-%s" % safe)
        seen = 0
        if os.path.isfile(state):
            with open(state, "r", encoding="utf-8", errors="replace") as handle:
                try:
                    seen = int(handle.read().strip() or "0")
                except ValueError:
                    seen = 0
        seen += 1
        with open(state, "w", encoding="utf-8") as handle:
            handle.write("%d\n" % seen)
        return seen
    except Exception:
        return None


def _project_root():
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    return root if root else os.getcwd()


def _agent_type(payload, transcript_path):
    """The spawned agent's type: the payload field when present, else the `agentType` the
    harness writes to `agent-<id>.meta.json` beside the agent's transcript. None for a main
    session or when neither source has it."""
    value = payload.get("agent_type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(transcript_path, str) and transcript_path.endswith(".jsonl"):
        try:
            with open(transcript_path[:-6] + ".meta.json", "r", encoding="utf-8") as handle:
                meta = json.load(handle)
            value = meta.get("agentType") if isinstance(meta, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:
            pass
    return None


def _agent_contract(agent_type):
    """{tools: set|None, maxTurns: int|None, model: str|None, memory: bool} parsed from
    `<root>/.claude/agents/<type>.md` frontmatter, or None when there is no such agent (a
    built-in like Explore, or a name this project does not define). Anything unparseable in a
    field leaves that field None: a contract we cannot read is not one we enforce."""
    if not isinstance(agent_type, str):
        return None
    name = agent_type.strip()
    if not name or not all(ch.isalnum() or ch in "-_" for ch in name):
        return None
    path = os.path.join(_project_root(), ".claude", "agents", name + ".md")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(65536)
    except Exception:
        return None
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line or line[:1] in (" ", "\t", "#"):
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    contract = {"tools": None, "maxTurns": None, "model": None, "memory": False}
    raw = fields.get("tools")
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = [part.strip().strip("\"'") for part in raw.strip("[]").split(",")]
        if isinstance(parsed, list):
            names = set(str(part).strip() for part in parsed if str(part).strip())
            contract["tools"] = names or None
    raw = fields.get("maxTurns")
    if raw:
        try:
            cap = int(raw)
            if cap > 0:
                contract["maxTurns"] = cap
        except ValueError:
            pass
    raw = fields.get("model")
    if raw:
        contract["model"] = raw.strip("\"'") or None
    contract["memory"] = bool(fields.get("memory"))
    return contract


def _is_memory_write(tool_name, tool_input, agent_type):
    """True when this Write/Edit targets a file inside THIS agent's own memory directory.
    The path is normalised first, so `agent-memory/planner/../../src/x.py` is `src/x.py`."""
    if tool_name not in ("Write", "Edit", "NotebookEdit") or not isinstance(tool_input, dict):
        return False
    if not isinstance(agent_type, str) or not agent_type:
        return False
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path.strip():
        return False
    parts = os.path.normpath(path).replace("\\", "/").split("/")
    for index in range(len(parts) - 3):
        if tuple(parts[index:index + 2]) == MEMORY_DIR_PARTS and parts[index + 2] == agent_type:
            return True
    return False


def _model_tier(name):
    if not isinstance(name, str):
        return None
    lowered = name.lower()
    for key, rank in MODEL_TIERS:
        if key in lowered:
            return rank
    return None


def _model_escalation(tool_input):
    """(requested, declared, agent) when an Agent call asks for a HIGHER tier than the target
    agent's frontmatter declares, else None. The measured reviewer declares sonnet and was
    spawned with model=opus by its caller; the frontmatter was right and simply overridden.
    A downgrade is allowed - degrading a tier is this kit's stated response to limits."""
    if os.environ.get("CK_ALLOW_MODEL_OVERRIDE") == "1" or not isinstance(tool_input, dict):
        return None
    requested = tool_input.get("model")
    target = tool_input.get("subagent_type")
    contract = _agent_contract(target)
    if contract is None or not contract.get("model"):
        return None
    asked, declared = _model_tier(requested), _model_tier(contract["model"])
    if asked is None or declared is None or asked <= declared:
        return None
    return (requested, contract["model"], target)


def _subagent_verdict(tool_name, tool_input, payload, transcript_path, size):
    """The three refusals that only apply inside a spawned agent, in the order they bind:
    contract scope (call 1), frontmatter maxTurns, then the calls x context spend line.
    Read/Grep/Glob are counted here and then allowed unconditionally."""
    agent_type = _agent_type(payload, transcript_path)
    contract = _agent_contract(agent_type)
    calls = _bump_agent_calls(transcript_path)
    if tool_name in NEVER_REFUSED:
        return None

    if contract is not None:
        allowed = contract.get("tools")
        if allowed is not None and tool_name not in allowed:
            if not (contract.get("memory") and _is_memory_write(tool_name, tool_input, agent_type)):
                memory_note = (
                    " `memory:` is declared, so Write/Edit are allowed ONLY under "
                    ".claude/agent-memory/%s/." % agent_type if contract.get("memory") else "")
                return (2,
                        "BLOCKED context-budget-gate: `%s` is not in %s's contract (tools: %s).%s "
                        "Changes ship as ops.json for the implementer, never as this agent's "
                        "edits. Override for one process tree with CK_RAW_CONTEXT=1.\n"
                        % (tool_name, agent_type, ", ".join(sorted(allowed)), memory_note))
        cap = contract.get("maxTurns")
        if cap and calls is not None and calls >= cap:
            return (2,
                    "BLOCKED context-budget-gate: %s has made %d tool calls and its frontmatter "
                    "says maxTurns: %d. This gate is what makes that number bind (measured "
                    "without it: 216 turns against 40). Stop here, write up what you have and "
                    "hand it back; Read, Grep, Glob and the handback stay open. Override for one "
                    "process tree with CK_RAW_CONTEXT=1.\n" % (agent_type, calls, cap))

    if size is not None and calls is not None:
        budget = _threshold("CK_AGENT_BUDGET", DEFAULT_AGENT_BUDGET)
        if calls * size >= budget:
            return (2,
                    "BLOCKED context-budget-gate: this subagent has spent roughly %dM "
                    "tokens (%d tool calls at %dK context; budget %dM). Neither factor "
                    "alone is over its line - the PRODUCT is, and the product is the bill. "
                    "Stop here: write up what you already have and hand it back to your "
                    "caller. Handback is not a guarded tool, and neither is Read, Grep or "
                    "Glob, so this refusal cannot trap you. If the work genuinely needs "
                    "more, your caller should split it across fresh agents that each "
                    "start at a small context rather than let one agent re-read a large "
                    "one on every turn. Raise the line with CK_AGENT_BUDGET, or drop the "
                    "whole budget for one process tree with CK_RAW_CONTEXT=1.\n"
                    % (calls * size // 1000000, calls, size // 1000, budget // 1000000))
    return None


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
    if tool_name not in COUNTED_TOOLS:
        return None
    tool_input = payload.get("tool_input")

    # A warning is HELD, not returned, so a de-duplicated advisory can never swallow the
    # spawn check below it.
    note = None

    if os.environ.get("CK_RAW_CONTEXT") != "1":
        transcript_path, subagent_call = _caller_transcript(payload)
        if tool_name not in GUARDED_TOOLS and not subagent_call:
            # A main-session read is neither counted nor budgeted; nothing to measure.
            return None
        size = _context_size(transcript_path) if transcript_path else None
        if subagent_call:
            verdict = _subagent_verdict(tool_name, tool_input, payload, transcript_path, size)
            if verdict is not None:
                return verdict
            if tool_name not in GUARDED_TOOLS:
                return None
        if size is not None:
            block = _threshold("CK_CONTEXT_BLOCK", DEFAULT_BLOCK)
            warn = _threshold("CK_CONTEXT_WARN", DEFAULT_WARN)
            if size >= block and subagent_call:
                # Not a block: a subagent has no /compact, no /save-session and no way to set
                # the hatch in its own environment. The only move it CAN make is to stop.
                note = (0,
                        "context-budget-gate: this subagent is at %dK tokens of context "
                        "(block line %dK). A subagent cannot run /compact or /save-session - "
                        "stop exploring, write up what you already have and hand it back to "
                        "your caller now.\n" % (size // 1000, block // 1000))
            elif size >= block and not _is_session_save(tool_name, tool_input):
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
    elif tool_name not in GUARDED_TOOLS:
        return None

    if tool_name in SPAWN_TOOLS:
        if _spawns_unbounded_agent(tool_input):
            return (2,
                    "BLOCKED context-budget-gate: `general-purpose` is a built-in agent - the "
                    "maxTurns, model and effort in this kit's frontmatter cannot reach it, and one "
                    "measured dispatch ran 56 turns to 246K tokens. Spawn a scoped agent instead: "
                    "explore (search), planner (plans), code-reviewer (review), docs (writing). "
                    "Override for one process tree with CK_ALLOW_GENERAL_PURPOSE=1.\n")
        escalation = _model_escalation(tool_input)
        if escalation is not None:
            requested, declared, target = escalation
            return (2,
                    "BLOCKED context-budget-gate: this spawn asks for model=%s but %s's "
                    "frontmatter routes it to %s. .claude/model-policy.json chooses the tier per "
                    "role; a caller-side override is how a sonnet reviewer ran 137 opus turns. Drop "
                    "the model param, or degrade it - a lower tier is always allowed. Override for "
                    "one process tree with CK_ALLOW_MODEL_OVERRIDE=1.\n"
                    % (requested, target, declared))

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

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
   At or above CK_CONTEXT_WARN (120,000) the call is allowed and `--advise` (PostToolUse) delivers one advisory,
   at most once per 20 guarded calls per session. At or above CK_CONTEXT_BLOCK (200,000) the
   call is refused: past that size every further tool call re-reads the whole window, so the
   cheapest correct move is /compact, then /save-session, or a fresh session.
   The block line was 400,000 until 2026-09-19. It never fired: an audit of two qa-agents
   sessions (89.9M tokens, 184 turns) found 72 turns above 200K and 9.5M tokens spent above
   250K, with the ceiling never reached, so the advisory at 150K was the only thing the model
   ever saw and it compacted zero times. A warning the model may ignore is not a budget; the
   line is now where the spend actually is.
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

TWO ENTRY POINTS
----------------
Without arguments this is the PreToolUse handler, run through dispatch.sh: it BLOCKS (exit 2,
one stderr line) or stays silent. It never advises from there, because exit-0 stderr and plain
stdout from a PreToolUse/PostToolUse hook are recorded as a `hook_success` attachment and never
enter model context (measured 2026-09-19 over 227 sessions: 18,345 such attachments, 0 in
context - the WARN this hook printed for months was a dead letter with a passing test).
`--advise` is the PostToolUse handler, wired DIRECTLY in settings.json - dispatch.sh prefixes
each handler's stdout with `[id] `, which breaks the JSON. It prints
`{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ...}}`, the one
PostToolUse form the model reads, for the warn band (once per WARN_EVERY counted calls per
session) and for a subagent at or over the block line (every call: its one move is to stop),
and always exits 0. A main session at or over the block line gets nothing from `--advise`:
the PreToolUse block already carries that message, and a block does reach the model.

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
`CK_RAW_CONTEXT=1` disables the context budget (warn, block, the per-agent spend line and the
handback cap) for that process tree.
`CK_AGENT_BUDGET=<tokens>` replaces every per-role spend line (ROLE_BUDGETS, default 15,000,000).
`CK_HANDBACK_MAX=<chars>` replaces both handback caps.
`CK_ALLOW_MODEL_OVERRIDE=1` lets an Agent call spawn a scoped agent on a higher tier than its
frontmatter declares.

AGENT CONTRACTS (subagents only)
--------------------------------
For a spawned agent whose type names a file under .claude/agents/, the frontmatter is enforced
here because nothing else enforces it: `tools:` (with Write/Edit scoped to the agent's own
.claude/agent-memory/<type>/ when `memory:` is declared) and, at spawn time, `model:` against
the Agent call's model param. `maxTurns:` is the harness's own cap and binds natively (it
counts turns); this gate only warns when an agent is WIND_DOWN_TURNS short of it. It used to
count tool calls against it as well and refuse Write at the cap. Measured 2026-09-24 over 1391
subagent runs, that stopped 75% of planners and 80% of explore agents; 34 of the 49 it stopped
wrote nothing and sent their plan back as a 15-40K-char handback. Those capped runs held 3% of
subagent tokens.

SPEND LINE AND WIND-DOWN (subagents only)
-----------------------------------------
Spend is charged once per assistant turn (deduplicated by message id, so a parallel batch of
reads costs one turn, as it does on the bill) at that turn's context size. The line is
per role (ROLE_BUDGETS). From WIND_DOWN_SHARE of it `--advise` tells the agent to write its
deliverable. Past the line the order reverses: Read, Grep, Glob, Bash and spawns close, and
Write/Edit stay open for GRACE_WRITES calls so the deliverable lands on disk. The handback
itself is never refused for spend, only for size (HANDBACK_MAX_*): everything in it is re-read
on every later turn of the caller.
`CK_ALLOW_GENERAL_PURPOSE=1` disables the spawn guard. Both are named in the message that
blocks, because a control with no documented override becomes a reason to disable the whole
hook chain.

stdlib only, py3.9 target.
"""

import argparse
import json
import os
import sys

# Bytes of transcript tail parsed per call. 64 KB covers many assistant turns and costs one
# seek + one read regardless of how large the file has grown.
TAIL_BYTES = 65536

DEFAULT_WARN = 120000
DEFAULT_BLOCK = 200000

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

# Per-role lines, measured 2026-09-24 over 1391 subagent runs: near the p90 of runs that
# finished (planner p50 5.9M, code-reviewer p90 7.5M, reviewer p90 3.1M, explore p90 3.8M), so
# an ordinary run never meets its line while the runaway tail does - runs over 8M held 58% of
# all subagent tokens. A role missing here gets DEFAULT_AGENT_BUDGET.
ROLE_BUDGETS = {
    "planner": 8000000,
    "implementer": 10000000,
    "code-reviewer": 6000000,
    "reviewer": 3000000,
    "explore": 3000000,
}

# `--advise` starts the wind-down at this share of the line, or this many turns short of the
# frontmatter maxTurns, and repeats it once per WIND_DOWN_EVERY counted calls.
WIND_DOWN_SHARE = 0.7
WIND_DOWN_TURNS = 5
WIND_DOWN_EVERY = 4

# Past the line exploration closes and the deliverable stays writable for this many calls.
GRACE_WRITES = 6
EXPLORATION_TOOLS = ("Read", "Grep", "Glob", "Bash", "Agent", "Task")
WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")

# The harness tool a spawned agent returns through. Its whole message lands in the caller's
# context; an agent that can write puts the detail in a file and hands back the path.
HANDBACK_TOOL = "SubagentHandback"
HANDBACK_MAX_WRITER = 3000
HANDBACK_MAX_READER = 8000

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
# measured reviewer made 3 guarded calls and 70 reads). They are outside every contract check
# and are refused only to a subagent past its spend line, whose way out is Write + handback -
# never a read.
COUNTED_TOOLS = GUARDED_TOOLS + ("Read", "Grep", "Glob")
CONTRACT_EXEMPT = ("Read", "Grep", "Glob")

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
    return _last_usage(path)[0]


def _last_usage(path):
    """(tokens of context, message id or None) from the LAST assistant usage record in the
    tail, else (None, None). The id is what lets a parallel batch be charged as one turn."""
    if not isinstance(path, str) or not path.strip():
        return None, None
    if not os.path.isfile(path):
        return None, None
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
            message_id = message.get("id")
            return total, (message_id if isinstance(message_id, str) and message_id else None)
    return None, None


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


def _agent_state_path(transcript_path):
    """`.state/agent-spend-<transcript basename>`, or None when there is nowhere to keep it.

    Keyed by the caller's OWN transcript basename, never by session_id: a subagent inherits
    its parent's session_id, so a session-keyed counter would pool every agent in the tree
    into one running total and refuse the third agent's first call for the first agent's
    spend. The basename is `agent-<id>.jsonl` and is unique per agent, and a SendMessage
    resume continues the same file - so resumes add to one line instead of resetting it.
    """
    state_dir = _state_dir()
    if state_dir is None or not isinstance(transcript_path, str) or not transcript_path:
        return None
    safe = "".join(
        ch for ch in os.path.basename(transcript_path) if ch.isalnum() or ch in "-_."
    )[:80]
    return os.path.join(state_dir, "agent-spend-%s" % safe) if safe else None


def _load_agent_state(path):
    """The agent's ledger. A pre-2026-09-24 file holds a bare call count; it is read as calls
    with no spend, so a running agent loses its history once rather than failing."""
    state = {"calls": 0, "turns": 0, "spend": 0, "last_id": None, "grace": 0, "advised": None}
    if path is None or not os.path.isfile(path):
        return state
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        raw = handle.read().strip()
    try:
        loaded = json.loads(raw or "{}")
    except ValueError:
        return state
    if isinstance(loaded, int) and not isinstance(loaded, bool):
        state["calls"] = loaded
    elif isinstance(loaded, dict):
        for key in state:
            if key in loaded:
                state[key] = loaded[key]
    return state


def _save_agent_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(state) + "\n")


def _charge_agent(transcript_path, size, message_id, tool_name, budget):
    """Count this call and charge its turn; returns the updated ledger, or None.

    A turn is charged once at its context size: every call of a parallel batch carries the
    same message id, and the bill charges the context once per turn, not once per tool. A
    record without an id (older harnesses, the tests) is charged per call. Write calls made
    after the line are counted separately - they are the grace window.

    Any failure returns None, which skips the spend line. A ledger that cannot be read is not
    evidence of overspend.
    """
    path = _agent_state_path(transcript_path)
    if path is None:
        return None
    try:
        state = _load_agent_state(path)
        state["calls"] += 1
        if size is not None and (message_id is None or message_id != state["last_id"]):
            state["turns"] += 1
            state["spend"] += size
            state["last_id"] = message_id
        if state["spend"] >= budget and tool_name in WRITE_TOOLS:
            state["grace"] += 1
        _save_agent_state(path, state)
        return state
    except Exception:
        return None


def _agent_budget(agent_type):
    """CK_AGENT_BUDGET when set, else the role's line, else the default."""
    if os.environ.get("CK_AGENT_BUDGET") is not None:
        return _threshold("CK_AGENT_BUDGET", DEFAULT_AGENT_BUDGET)
    return ROLE_BUDGETS.get(agent_type, DEFAULT_AGENT_BUDGET)


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


def _can_write(contract):
    """True when the agent has somewhere to put a long deliverable other than its handback."""
    if contract is None:
        return False
    tools = contract.get("tools")
    return tools is None or any(tool in tools for tool in ("Write", "Edit"))


def _handback_verdict(tool_input, contract):
    """Refuse an oversize handback. Measured: planner handbacks of 15-40K chars that the caller
    then carried, and re-read, on every later turn."""
    message = tool_input.get("message") if isinstance(tool_input, dict) else None
    if not isinstance(message, str):
        return None
    writer = _can_write(contract)
    limit = _threshold("CK_HANDBACK_MAX", HANDBACK_MAX_WRITER if writer else HANDBACK_MAX_READER)
    if len(message) <= limit:
        return None
    if writer:
        move = ("Put the detail in the file you own (the plan, ops.json, the report) and hand "
                "back its path plus a summary of at most %d chars." % limit)
    else:
        move = ("Cut it to the verdict and the findings that change what your caller does "
                "next, each with file:line, in at most %d chars." % limit)
    return (2,
            "BLOCKED context-budget-gate: this handback is %d chars (line %d). All of it lands "
            "in your caller's context and is re-read on every one of its later turns. %s "
            "Override for one process tree with CK_RAW_CONTEXT=1.\n"
            % (len(message), limit, move))


def _subagent_verdict(tool_name, tool_input, payload, transcript_path, size, message_id):
    """The refusals that only apply inside a spawned agent, in the order they bind: handback
    size, contract scope, then the spend line."""
    agent_type = _agent_type(payload, transcript_path)
    contract = _agent_contract(agent_type)
    budget = _agent_budget(agent_type)
    state = _charge_agent(transcript_path, size, message_id, tool_name, budget)

    if tool_name == HANDBACK_TOOL:
        return _handback_verdict(tool_input, contract)

    if contract is not None and tool_name not in CONTRACT_EXEMPT:
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

    if state is None or state["spend"] < budget:
        return None
    spent = ("BLOCKED context-budget-gate: %s has spent about %.1fM tokens over %d turns "
             "(context now %dK; its line is %gM)."
             % (agent_type or "this subagent", state["spend"] / 1e6, state["turns"],
                (size or 0) // 1000, budget / 1e6))
    hatch = (" Override for one process tree with CK_RAW_CONTEXT=1, or move the line with "
             "CK_AGENT_BUDGET.\n")
    if tool_name in WRITE_TOOLS:
        if state["grace"] <= GRACE_WRITES:
            return None
        return (2, spent + " The %d-call write window after the line is used up: hand back "
                "now, a short summary that names the file you wrote." % GRACE_WRITES + hatch)
    if tool_name in EXPLORATION_TOOLS:
        if _can_write(contract):
            move = ("Write your deliverable now - Write/Edit stay open for %d calls past the "
                    "line - then hand back a short summary that names the file." % GRACE_WRITES)
        else:
            move = ("Hand back what you have now: the verdict and the findings that matter, "
                    "each with file:line.")
        return (2, spent + " Exploring is over: Read, Grep, Glob, Bash and spawns are closed "
                "from here. " + move + hatch)
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
    if tool_name not in COUNTED_TOOLS and tool_name != HANDBACK_TOOL:
        return None
    tool_input = payload.get("tool_input")

    if os.environ.get("CK_RAW_CONTEXT") != "1":
        transcript_path, subagent_call = _caller_transcript(payload)
        if tool_name not in GUARDED_TOOLS and not subagent_call:
            # A main-session read is neither counted nor budgeted; nothing to measure.
            return None
        size, message_id = _last_usage(transcript_path) if transcript_path else (None, None)
        if subagent_call:
            verdict = _subagent_verdict(tool_name, tool_input, payload, transcript_path, size,
                                        message_id)
            if verdict is not None:
                return verdict
            if tool_name not in GUARDED_TOOLS:
                return None
        if size is not None and not subagent_call:
            # A subagent is never blocked: it can run neither /compact nor /save-session and
            # cannot set the hatch in its own environment. Its over-the-line advisory, and the
            # main session's warn-band one, are `--advise`'s (PostToolUse): the only path whose
            # output the model reads. From here a decision is a block or nothing.
            block = _threshold("CK_CONTEXT_BLOCK", DEFAULT_BLOCK)
            if size >= block and not _is_session_save(tool_name, tool_input):
                return (2,
                        "BLOCKED context-budget-gate: this session is at %dK tokens of "
                        "context (block at %dK). Type /compact now - it is not a tool call, so "
                        "this gate never blocks it; /save-session works once you are back under "
                        "the line. Auto-compact fires about 33K below autoCompactWindow, so a window "
                        "of at most %dK compacts before this gate is reached (the documented "
                        "minimum window is 100K; if that is still above the line, raise "
                        "CK_CONTEXT_BLOCK instead). Override for one process tree with "
                        "CK_RAW_CONTEXT=1.\n"
                        % (size // 1000, block // 1000, (block + 33000) // 1000))
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

    return None


def _subagent_note(size, block):
    return ("context-budget-gate: this subagent is at %dK tokens of context (block line %dK). "
            "A subagent cannot run /compact or /save-session - stop exploring, write up what "
            "you already have and hand it back to your caller now."
            % (size // 1000, block // 1000))


def _wind_down_note(payload, transcript_path):
    """The advisory that comes BEFORE the spend line or the native maxTurns, or None.

    Reads the ledger the PreToolUse path keeps (never charges it) and records when it last
    advised, so the note repeats once per WIND_DOWN_EVERY calls instead of on every one. Past
    the line it is silent: the PreToolUse refusal carries that message, and it reaches the
    model.
    """
    path = _agent_state_path(transcript_path)
    if path is None:
        return None
    try:
        state = _load_agent_state(path)
        agent_type = _agent_type(payload, transcript_path)
        budget = _agent_budget(agent_type)
        if state["spend"] >= budget:
            return None
        contract = _agent_contract(agent_type) or {}
        cap = contract.get("maxTurns")
        turns_left = cap - state["turns"] if cap else None
        near_turns = turns_left is not None and turns_left <= WIND_DOWN_TURNS
        if state["spend"] < budget * WIND_DOWN_SHARE and not near_turns:
            return None
        advised = state["advised"]
        if isinstance(advised, int) and state["calls"] - advised < WIND_DOWN_EVERY:
            return None
        state["advised"] = state["calls"]
        _save_agent_state(path, state)
    except Exception:
        return None
    turns_note = (" and %d turn(s) short of its maxTurns %d, where the harness stops it mid-work"
                  % (max(turns_left, 0), cap) if near_turns else "")
    return ("context-budget-gate: wind down. This subagent has spent about %.1fM of its %gM "
            "token line (%d%%)%s. Stop exploring: write your deliverable now (the plan, ops.json "
            "or report file), then hand back a short summary that names it. Past the line Read, "
            "Grep, Glob and Bash close and only Write/Edit stay open, for %d calls."
            % (state["spend"] / 1e6, budget / 1e6, 100 * state["spend"] // budget,
               turns_note, GRACE_WRITES))


def _warn_note(size, warn, block):
    return ("context-budget-gate: context %dK tokens (warn %dK, block %dK) - run /save-session "
            "then /compact, or start a new session."
            % (size // 1000, warn // 1000, block // 1000))


def _advise(payload):
    """`--advise` (PostToolUse): the advisory the model should read, or None.

    Never a decision - the caller always exits 0 - and never through dispatch.sh. The warn-band
    advisory is rate-limited by the same per-session counter the PreToolUse path used to spend
    on a message nobody received; a subagent over the block line is told to stop on every call,
    and one nearing its spend line or maxTurns gets the wind-down note.
    """
    if os.environ.get("CK_RAW_CONTEXT") == "1":
        return None
    tool_name = payload.get("tool_name") or payload.get("name")
    if tool_name not in COUNTED_TOOLS:
        return None
    transcript_path, subagent_call = _caller_transcript(payload)
    if not transcript_path:
        return None
    size = _context_size(transcript_path)
    if size is None:
        return None
    block = _threshold("CK_CONTEXT_BLOCK", DEFAULT_BLOCK)
    warn = _threshold("CK_CONTEXT_WARN", DEFAULT_WARN)
    if subagent_call:
        if size >= block:
            return _subagent_note(size, block)
        return _wind_down_note(payload, transcript_path)
    if size >= block:
        return None  # the PreToolUse block carries this, and a block reaches the model
    if size >= warn and _should_warn(payload.get("session_id")):
        return _warn_note(size, warn, block)
    return None


def _parse_args(argv):
    # parse_known_args, never parse_args: an unexpected flag from a future registry row must
    # not turn this fail-soft gate into a crash (argparse exits 2 - the block code).
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--advise", action="store_true",
                    help="PostToolUse mode: print hookSpecificOutput.additionalContext JSON, exit 0")
    args, _unknown = ap.parse_known_args(argv)
    return args


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    if args.advise:
        try:
            note = _advise(payload)
        except Exception:
            note = None  # the gate's own bug must never cost the model an advisory it can act on
        if note:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": note}}) + "\n")
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

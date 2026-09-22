"""Behavioural tests for the compaction-cadence hook (.claude/hooks).

Every test drives the real script as a subprocess with a real hook payload on stdin and
asserts on what the process writes -- never on its internals. The mutation that turns each
test red is named in its docstring, because a passing check that was never shown capable
of failing measures nothing.

The hook reads its thresholds from the environment at import time, so each test sets
CK_COMPACT_MIN_INTERVAL / CK_COMPACT_MAX_CYCLES on the subprocess rather than patching a
module global -- that is the same path a real session takes through `settings.json.env`.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".claude" / "hooks" / "compaction-cadence.py"
LEDGER = "compaction-cadence.jsonl"

SESSION = "sess-A"
OTHER = "sess-B"


def run(payload, state_dir, **env):
    """Drive the hook exactly as Claude Code does: JSON on stdin, JSON or nothing out."""
    environ = dict(os.environ)
    environ["CK_COMPACT_STATE_DIR"] = str(state_dir)
    environ.update({k: str(v) for k, v in env.items()})
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env=environ,
        timeout=30,
    )
    return proc


def context_of(proc):
    """The text the hook injects after a compaction, or None when it stayed silent."""
    if not proc.stdout.strip():
        return None
    body = json.loads(proc.stdout)
    return body["hookSpecificOutput"]["additionalContext"]


def pre_compact(session=SESSION, trigger="auto"):
    return {
        "hook_event_name": "PreCompact",
        "session_id": session,
        "cwd": "/tmp/project",
        "trigger": trigger,
    }


def session_start(session=SESSION, source="compact"):
    return {
        "hook_event_name": "SessionStart",
        "session_id": session,
        "source": source,
    }


def seed(state_dir, stamps, session=SESSION):
    """Write a ledger describing compactions at the given epoch seconds."""
    path = Path(state_dir) / LEDGER
    with open(path, "a", encoding="utf-8") as fh:
        for ts in stamps:
            fh.write(json.dumps({
                "ts": int(ts),
                "session": session,
                "cwd": "/tmp/project",
                "trigger": "auto",
            }) + "\n")
    return path


# --- PreCompact: records, never blocks ------------------------------------------------

def test_precompact_records_a_row_and_stays_silent(tmp_path):
    """Red if PreCompact stopped appending -- SessionStart would then have no history."""
    proc = run(pre_compact(), tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == "", "PreCompact must not print; only SessionStart injects"
    rows = [json.loads(ln) for ln in (tmp_path / LEDGER).read_text().splitlines() if ln]
    assert len(rows) == 1
    assert rows[0]["session"] == SESSION
    assert rows[0]["trigger"] == "auto"
    assert abs(rows[0]["ts"] - time.time()) < 60


def test_precompact_never_blocks_however_hot_the_cadence(tmp_path):
    """Red if PreCompact ever exits 2: blocking a compaction overflows the very context
    the compaction was called to relieve. This hook is advisory by construction."""
    now = time.time()
    seed(tmp_path, [now - 120, now - 60, now - 30, now - 10])

    proc = run(pre_compact(), tmp_path, CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    assert proc.returncode == 0
    assert proc.stdout == ""


# --- SessionStart: the one channel that reaches the model -----------------------------

def test_startup_session_is_never_warned(tmp_path):
    """Red if the source check is dropped -- every new session would open with a warning
    about compactions that belong to an earlier run of the same id."""
    now = time.time()
    seed(tmp_path, [now - 120, now - 30])

    proc = run(session_start(source="startup"), tmp_path,
               CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_a_single_compaction_is_not_a_spiral(tmp_path):
    """Red if the hook warned on the first compaction -- one compaction is normal, healthy
    behaviour and a warning there is pure noise that trains the model to ignore it."""
    seed(tmp_path, [time.time() - 10])

    proc = run(session_start(), tmp_path,
               CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_two_compactions_inside_the_floor_warn(tmp_path):
    """Red if the interval test is dropped. This is the measured failure: on session
    hermes-agent-20260920-2108 the last two compactions were 2.2 min apart."""
    now = time.time()
    seed(tmp_path, [now - 132, now])

    proc = run(session_start(), tmp_path,
               CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    text = context_of(proc)
    assert text is not None, "a 2.2-minute gap must be reported"
    assert "compaction-cadence" in text
    assert "min apart" in text
    assert "hand back to the user" in text
    assert "Do NOT respond by reading more files" in text, (
        "the advice must name the wrong reaction, or the model will take it")


def test_a_healthy_cadence_stays_silent(tmp_path):
    """Red if the hook warned whenever a session compacts twice. Two compactions an hour
    apart are a long session doing its job, not a spiral."""
    now = time.time()
    seed(tmp_path, [now - 7200, now - 3600])

    proc = run(session_start(), tmp_path,
               CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_the_cycle_ceiling_warns_even_with_healthy_gaps(tmp_path):
    """Red if only the interval were checked. Four well-spaced compactions still mean the
    session has re-summarised itself four times; the summaries compound regardless."""
    now = time.time()
    seed(tmp_path, [now - 14400, now - 10800, now - 7200, now - 3600])

    proc = run(session_start(), tmp_path,
               CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    text = context_of(proc)
    assert text is not None, "4 cycles is over the ceiling of 3"
    assert "compacted 4 times" in text


def test_another_sessions_compactions_do_not_count(tmp_path):
    """Red if the session filter is dropped -- the ledger is shared across every session
    on the account, so a busy neighbour would warn a session that never compacted."""
    now = time.time()
    seed(tmp_path, [now - 120, now - 60, now - 30], session=OTHER)
    seed(tmp_path, [now], session=SESSION)

    proc = run(session_start(), tmp_path,
               CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_thresholds_come_from_the_environment(tmp_path):
    """Red if the tunables were hard-coded. A 10-minute gap is healthy at the 5-minute
    default and a spiral at a 20-minute floor; the operator sets which."""
    now = time.time()
    seed(tmp_path, [now - 600, now])

    quiet = run(session_start(), tmp_path, CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)
    loud = run(session_start(), tmp_path, CK_COMPACT_MIN_INTERVAL=1200, CK_COMPACT_MAX_CYCLES=3)

    assert quiet.stdout == ""
    assert context_of(loud) is not None


# --- failure modes --------------------------------------------------------------------

def test_garbage_stdin_fails_open(tmp_path):
    """Red if the hook raised on malformed input: a non-zero exit from a SessionStart hook
    is visible to the user for no benefit, and on PreCompact it would block a compaction."""
    proc = run("not json at all", tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_a_corrupt_ledger_line_is_skipped_not_fatal(tmp_path):
    """Red if one truncated write poisoned the whole ledger -- appends are not atomic, so
    a half-written line is an expected state, not an exceptional one."""
    now = time.time()
    path = seed(tmp_path, [now - 132])
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"ts": 1, "sess\n')
    seed(tmp_path, [now])

    proc = run(session_start(), tmp_path,
               CK_COMPACT_MIN_INTERVAL=300, CK_COMPACT_MAX_CYCLES=3)

    assert proc.returncode == 0
    assert context_of(proc) is not None, "the two intact rows must still be read"


def test_an_unreadable_state_dir_costs_nothing(tmp_path):
    """Red if a missing ledger dir raised. The hook runs in every folder on the account,
    including ones where the state dir has not been created yet."""
    proc = run(session_start(), tmp_path / "does" / "not" / "exist")

    assert proc.returncode == 0
    assert proc.stdout == ""


# --- wiring ---------------------------------------------------------------------------

def test_the_hook_is_wired_for_both_events():
    """Red if the hook shipped inert. It needs BOTH events: PreCompact writes the history
    and SessionStart is the only place the warning can reach the model."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    for event in ("PreCompact", "SessionStart"):
        commands = [
            hook["command"]
            for entry in settings["hooks"].get(event, [])
            for hook in entry["hooks"]
        ]
        assert any("compaction-cadence.py" in c for c in commands), (
            "compaction-cadence.py is not wired for %s" % event)


def test_the_hook_is_wired_directly_not_through_the_dispatcher():
    """Red if the hook were routed through dispatch.sh, which prefixes advisory stdout
    with `[<id>] ` -- that prefix would make this hook's JSON unparseable and the warning
    would be silently dropped."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    for event in ("PreCompact", "SessionStart"):
        for entry in settings["hooks"].get(event, []):
            for hook in entry["hooks"]:
                if "compaction-cadence.py" in hook["command"]:
                    assert "dispatch.sh" not in hook["command"]

"""The PreToolUse ceiling on Bash command TEXT (`.claude/hooks/bash-payload-gate.py`).

Every cap this kit ships measures tool OUTPUT -- `output_filter.py` bounds a
Bash stdout, `read-window-guard.py` bounds a Read, `context-budget-gate.py`
bounds the window. Nothing bounded what the model WRITES, and a measurement on
2026-09-20 found `tool_use` parameters were 40.3% of a session transcript's
body, very nearly equal to all tool results combined. This file pins the gate
that closes that gap.

It pins the two directions the hook must fail in, which are opposite on purpose:
an oversized command is refused with `exit 2` (hard rule 2, fail closed), while
an unreadable payload, a foreign tool, or a bug in the hook is allowed through.
A false positive here denies the main agent its Bash tool for the rest of the
session; a false negative costs a few thousand tokens.

It also pins the registry row. A hook file that exists but is unregistered is
invisible until a token bill arrives -- and `dispatch.sh` runs the registry, not
the directory.

Every case runs the hook as a subprocess over a payload on stdin. Nothing
touches the repository or the environment of the running session.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "bash-payload-gate.py"
THRESHOLD = 1500


def run(payload, env=None):
    """Run the hook with `payload` on stdin; return (returncode, stderr)."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=text,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stderr


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def test_the_hook_is_present_and_executable():
    assert HOOK.is_file(), f"{HOOK} is missing - a vendor sync may have removed it"


def test_an_ordinary_command_is_allowed():
    code, err = run(bash("python3 -m pytest tests/ -q"))
    assert code == 0
    assert err == ""


def test_a_command_exactly_at_the_ceiling_is_allowed():
    code, _ = run(bash("x" * THRESHOLD))
    assert code == 0


def test_a_command_over_the_ceiling_is_refused_with_exit_2():
    code, err = run(bash("x" * (THRESHOLD + 1)))
    assert code == 2, "project hard rule 2: a block is exit 2, never exit 1"
    assert "bash-payload-gate" in err


def test_the_refusal_names_the_cheaper_route():
    """A block the model cannot act on is a block it will retry verbatim."""
    _, err = run(bash("y" * 9000))
    assert "9000" in err and str(THRESHOLD) in err
    assert "scratchpad" in err.lower()
    assert "CK_RAW_INPUT=1" in err


def test_nothing_is_written_to_stdout_on_a_block():
    """PreToolUse stdout is parsed as hook JSON; a bare line there corrupts it."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(bash("z" * 9000)),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'subject' -m '" + "body " * 400 + "'",
        "FOO=bar git commit -m '" + "x" * 3000 + "'",
        "git apply <<'EOF'\n" + "+line\n" * 900 + "EOF",
        "gh pr create --title t --body '" + "x" * 3000 + "'",
    ],
)
def test_payload_carrying_commands_are_exempt(command):
    """A commit message IS the payload; there is no cheaper spelling of it."""
    assert len(command) > THRESHOLD
    code, _ = run(bash(command))
    assert code == 0


def test_a_merely_similar_command_is_not_exempt():
    """The exemption is anchored, so it cannot be borrowed by a prefix trick."""
    code, _ = run(bash("echo 'git commit -m' && python3 -c \"" + "x" * 3000 + '"'))
    assert code == 2


def test_the_override_hatch_works():
    env = dict(os.environ, CK_RAW_INPUT="1")
    code, _ = run(bash("x" * 9000), env=env)
    assert code == 0


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        "",
        json.dumps([1, 2, 3]),
        json.dumps({"tool_name": "Bash"}),
        json.dumps({"tool_name": "Bash", "tool_input": "a string"}),
        json.dumps({"tool_name": "Bash", "tool_input": {"command": None}}),
    ],
)
def test_an_unreadable_payload_fails_open(payload):
    """Denying every Bash call on a malformed payload is the catastrophic direction."""
    code, _ = run(payload)
    assert code == 0


@pytest.mark.parametrize("tool", ["Read", "Edit", "Write", "Agent", "Task"])
def test_other_tools_are_invisible_to_this_hook(tool):
    code, _ = run({"tool_name": tool, "tool_input": {"command": "x" * 9000}})
    assert code == 0


def test_the_hook_is_registered_as_blocking_on_pretooluse():
    """The hook file existing is not enough - dispatch.sh runs the registry."""
    registry = json.loads(
        (
            Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "dispatch-registry.json"
        ).read_text()
    )
    rows = [r for r in registry["events"]["PreToolUse"] if r["id"] == "bash-payload-gate"]
    assert len(rows) == 1, "bash-payload-gate is not wired on PreToolUse"
    row = rows[0]
    assert row["tier"] == "blocking"
    assert row["file"] == "bash-payload-gate.py"
    assert row["runner"] == "python3"
    assert "Bash" in row["matcher"]
    # Registry invariant: only an advisory row may declare a command_matcher.
    assert "command_matcher" not in row

"""Behavioural coverage for .claude/hooks/read-window-guard.py and the agent maxTurns caps.

Every case runs the hook as a REAL subprocess with a synthetic PreToolUse payload on stdin and
asserts the exit code the dispatcher would see. Nothing is imported from the hook, so the
shipped artifact is what is measured.

Mutants these tests must catch (apply them, do not assume them):
  * THRESHOLD = 200 -> 20000            => test_blocks_unwindowed_read_of_a_long_file RED
  * delete the `_allowlisted` branch    => test_allows_an_allowlisted_path RED
  * registry row tier -> \"advisory\"      => test_registry_registers_the_guard_as_blocking RED
                                           and test_dispatch_blocks_an_unwindowed_read RED

ENV DISCIPLINE: CK_RAW_READ is POPPED from the inherited environment. A developer with the
hatch exported would otherwise turn every block assertion silently green - the same class of
mistake recorded in .claude/knowledge/issues ("assumed subprocess.run inherited the parent env").
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "read-window-guard.py"
DISPATCH = ROOT / ".claude" / "hooks" / "dispatch.sh"
REGISTRY = ROOT / ".claude" / "hooks" / "dispatch-registry.json"

AGENT_MAX_TURNS = {
    "planner.md": 40,
    "reviewer.md": 25,
    "implementer.md": 30,
    "code-reviewer.md": 30,
}


def run_hook(file_path, limit=None, tool_name="Read", extra_env=None):
    tool_input = {"file_path": str(file_path)}
    if limit is not None:
        tool_input["limit"] = limit
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})

    env = dict(os.environ)
    env.pop("CK_RAW_READ", None)
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )


def write_lines(tmp_path, name, count):
    target = tmp_path / name
    target.write_text("".join("line %d\n" % i for i in range(count)), encoding="utf-8")
    return target


def test_hook_ships():
    assert HOOK.is_file(), "the guard must exist on disk for the registry row to resolve"


def test_blocks_unwindowed_read_of_a_long_file(tmp_path):
    target = write_lines(tmp_path, "long.py", 201)
    result = run_hook(target)
    assert result.returncode == 2, result.stderr
    assert "limit" in result.stderr
    assert result.stdout == "", "a block is stderr-only; stdout is never the decision"


def test_allows_a_windowed_read_of_the_same_file(tmp_path):
    target = write_lines(tmp_path, "long.py", 201)
    assert run_hook(target, limit=100).returncode == 0


def test_allows_a_file_at_the_threshold(tmp_path):
    target = write_lines(tmp_path, "exactly200.py", 200)
    assert run_hook(target).returncode == 0


def fake_root_file(tmp_path, relpath, count=250):
    """A >THRESHOLD file inside a FAKE project root, so length never depends on a real file."""
    target = tmp_path / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join("line %d\n" % i for i in range(count)), encoding="utf-8")
    return target


def test_allows_an_allowlisted_path(tmp_path):
    """250 lines AND allowlisted -> allowed. This is the ONLY branch that can allow it, so
    deleting `if _allowlisted(path): return 0` turns this RED (mutant 2)."""
    target = fake_root_file(tmp_path, ".claude/plans/plan-x.md")
    result = run_hook(target, extra_env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0, result.stderr


def test_blocks_a_same_length_file_outside_the_allowlist(tmp_path):
    """The negative twin: identical length, non-allowlisted prefix -> exit 2. Without it, an
    allowlist widened to everything would still pass the positive case."""
    target = fake_root_file(tmp_path, "docs/notes-x.md")
    result = run_hook(target, extra_env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 2, result.stderr
    assert "limit" in result.stderr


def test_ck_raw_read_overrides(tmp_path):
    target = write_lines(tmp_path, "long.py", 500)
    assert run_hook(target, extra_env={"CK_RAW_READ": "1"}).returncode == 0


def test_allows_a_missing_file(tmp_path):
    assert run_hook(tmp_path / "nope.py").returncode == 0


def test_ignores_other_tools(tmp_path):
    target = write_lines(tmp_path, "long.py", 500)
    assert run_hook(target, tool_name="Grep").returncode == 0


def test_allows_on_unparseable_payload():
    env = dict(os.environ)
    env.pop("CK_RAW_READ", None)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json at all",
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode == 0


@pytest.mark.parametrize("agent,expected", sorted(AGENT_MAX_TURNS.items()))
def test_agent_declares_max_turns(agent, expected):
    text = (ROOT / ".claude" / "agents" / agent).read_text(encoding="utf-8")
    head = text.split("\n---", 1)[0]
    assert ("maxTurns: %d" % expected) in head, (
        "%s must declare maxTurns: %d inside its frontmatter so a runaway run stops with a "
        "PARTIAL handback instead of burning context." % (agent, expected)
    )


# ------------------------------------------------- the guard, through dispatch.sh ----
# Every test above spawns the hook directly. That proves the SCRIPT works and proves nothing
# about whether Claude Code ever runs it: the shipped control is the registry row, which
# settings.json reaches only via `dispatch.sh PreToolUse`. These two drive the real path.


def run_dispatch(file_path, limit=None):
    tool_input = {"file_path": str(file_path)}
    if limit is not None:
        tool_input["limit"] = limit
    payload = json.dumps({"tool_name": "Read", "tool_input": tool_input})

    env = dict(os.environ)
    env.pop("CK_RAW_READ", None)
    env["ECC_HOOK_PROFILE"] = "standard"
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    env["CLAUDEKIT_SESSION_ID"] = "pytest-read-window-guard"

    return subprocess.run(
        ["bash", str(DISPATCH), "PreToolUse"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )


def test_registry_registers_the_guard_as_blocking():
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))["events"]["PreToolUse"]
    matches = [row for row in rows if row.get("id") == "read-window-guard"]
    assert matches, "the guard is not registered for PreToolUse; the script is inert"
    row = matches[0]
    assert row["file"] == "read-window-guard.py"
    assert row["matcher"] == "Read"
    assert row["tier"] == "blocking", (
        "an advisory row cannot deny a Read; the guard would be observable but powerless"
    )


def test_dispatch_blocks_an_unwindowed_read(tmp_path):
    """End to end, exactly as settings.json invokes it: payload -> dispatch.sh -> exit 2."""
    target = write_lines(tmp_path, "long.py", 201)
    result = run_dispatch(target)
    assert result.returncode == 2, (
        "dispatch.sh did not block an unwindowed Read (rc=%s, stderr=%r)"
        % (result.returncode, result.stderr)
    )


def test_dispatch_allows_a_windowed_read(tmp_path):
    target = write_lines(tmp_path, "long.py", 201)
    result = run_dispatch(target, limit=100)
    assert result.returncode == 0, result.stderr

"""Behavioural coverage for .claude/hooks/review-round-cap.py (PreToolUse, blocking).

Each case runs the hook as a real subprocess with a PreToolUse Agent payload. The
observable is the exit code (0 allow / 2 block) and stderr.

Mutants these must catch (apply them, do not assume them):
  * CAP = 3 -> 30                             => test_fourth_reviewer_is_refused RED
  * count every agent type                    => test_other_agents_are_never_counted RED
  * key the counter on nothing (global)       => test_rounds_are_per_session RED
  * increment before deciding                 => test_a_refused_spawn_does_not_count RED
  * exit 1 / stdout on block                  => test_fourth_reviewer_is_refused RED
  * ignore CK_REVIEW_ROUND_CAP                => test_owner_can_raise_the_cap RED
  * drop the registry row                     => test_registry_wires_the_hook_on_agent RED
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "review-round-cap.py"
REGISTRY = ROOT / ".claude" / "hooks" / "dispatch-registry.json"


def run(tmp_path, agent="code-reviewer", session="s1", tool="Agent", env_extra=None,
        raw_payload=None):
    payload = raw_payload if raw_payload is not None else json.dumps(
        {"session_id": session, "tool_name": tool,
         "tool_input": {"subagent_type": agent, "prompt": "review it", "description": "r"}})
    env = dict(os.environ)
    env.pop("CK_REVIEW_ROUND_CAP", None)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                          text=True, env=env, cwd=str(tmp_path))


def test_hook_ships():
    assert HOOK.is_file()


def test_three_reviewers_pass(tmp_path):
    for _ in range(3):
        r = run(tmp_path)
        assert r.returncode == 0 and r.stderr == "", r.stderr


def test_fourth_reviewer_is_refused(tmp_path):
    for _ in range(3):
        assert run(tmp_path).returncode == 0
    r = run(tmp_path)
    assert r.returncode == 2
    assert r.stdout == ""
    assert "[review-round-cap] BLOCKED" in r.stderr
    assert "round 4" in r.stderr and "ceiling is 3" in r.stderr
    assert "OWNER escalation" in r.stderr


def test_a_refused_spawn_does_not_count(tmp_path):
    for _ in range(3):
        run(tmp_path)
    run(tmp_path)
    r = run(tmp_path)
    assert r.returncode == 2 and "round 4" in r.stderr, "a refused spawn must not inflate"


def test_other_agents_are_never_counted(tmp_path):
    for agent in ("planner", "explore", "reviewer", "tester", "general-purpose"):
        for _ in range(5):
            r = run(tmp_path, agent=agent)
            assert r.returncode == 0 and r.stderr == ""
    r = run(tmp_path)
    assert r.returncode == 0, "20 non-reviewer spawns must leave the reviewer count at 0"


def test_rounds_are_per_session(tmp_path):
    for _ in range(3):
        run(tmp_path, session="a")
    assert run(tmp_path, session="a").returncode == 2
    assert run(tmp_path, session="b").returncode == 0


def test_task_tool_name_is_also_counted(tmp_path):
    for _ in range(3):
        assert run(tmp_path, tool="Task").returncode == 0
    assert run(tmp_path, tool="Task").returncode == 2


def test_owner_can_raise_the_cap(tmp_path):
    for _ in range(3):
        run(tmp_path)
    assert run(tmp_path).returncode == 2
    assert run(tmp_path, env_extra={"CK_REVIEW_ROUND_CAP": "5"}).returncode == 0
    assert run(tmp_path, env_extra={"CK_REVIEW_ROUND_CAP": "0"}).returncode == 0


def test_garbage_payload_allows(tmp_path):
    r = run(tmp_path, raw_payload="not json")
    assert r.returncode == 0 and r.stderr == ""
    r = run(tmp_path, raw_payload=json.dumps({"tool_name": "Agent", "tool_input": "x"}))
    assert r.returncode == 0


def test_unreadable_counter_allows_with_advisory(tmp_path):
    state = tmp_path / ".claude" / "hooks" / ".state"
    state.mkdir(parents=True)
    (state / "review-rounds-s1").write_text("not-a-number")
    r = run(tmp_path)
    assert r.returncode == 0
    assert "advisory" in r.stderr and "not counting" in r.stderr


def test_registry_wires_the_hook_on_agent():
    reg = json.loads(REGISTRY.read_text())
    rows = [h for h in reg["events"]["PreToolUse"] if h["id"] == "review-round-cap"]
    assert len(rows) == 1, "review-round-cap must be registered exactly once on PreToolUse"
    row = rows[0]
    assert row["file"] == "review-round-cap.py"
    assert row["tier"] == "blocking"
    assert "Agent" in row["matcher"] and "Task" in row["matcher"]

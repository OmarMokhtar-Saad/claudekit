"""Behavioural coverage for .claude/hooks/batch-reads-nudge.py (PostToolUse, advisory).

Each case runs the hook as a real subprocess with a PostToolUse payload. The observable is
stdout (what the model sees) and the exit code (always 0). CK_NO_READ_NUDGE is popped.

Mutants these must catch (apply them, do not assume them):
  * NUDGE_AT = 5 -> 50                        => test_nudges_on_the_fifth_consecutive_read RED
  * a write no longer resets the streak       => test_a_write_resets_the_streak RED
  * drop the WRITES_FILE check                => test_a_redirect_to_a_file_is_not_a_read RED
  * `sub not in GIT_READ` -> always read      => test_git_read_subcommands_count_but_writes
                                                 _do_not RED
  * treat an unknown binary as a read         => test_an_unknown_command_resets RED
  * key the streak on nothing (global)        => test_streaks_are_per_session RED
  * exit non-zero on nudge                    => every nudging test RED on returncode
  * remove the settings.json PostToolUse entry => test_settings_json_wires_the_hook_on_bash
                                                 RED (the registry row alone is NOT wiring)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "batch-reads-nudge.py"
REGISTRY = ROOT / ".claude" / "hooks" / "dispatch-registry.json"


def run(tmp_path, command, session="s1", project_dir=True, tool="Bash", raw_payload=None):
    payload = raw_payload if raw_payload is not None else json.dumps(
        {"session_id": session, "tool_name": tool, "tool_input": {"command": command}})
    env = dict(os.environ)
    env.pop("CK_NO_READ_NUDGE", None)
    if project_dir:
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                          text=True, env=env, cwd=str(tmp_path))


def reads(tmp_path, n, session="s1"):
    out = []
    for i in range(n):
        r = run(tmp_path, "cat file%d.py" % i, session=session)
        assert r.returncode == 0 and r.stderr == ""
        out.append(r.stdout)
    return out


def test_hook_ships():
    assert HOOK.is_file()


def test_silent_below_the_threshold(tmp_path):
    assert all(o == "" for o in reads(tmp_path, 4))


def test_nudges_on_the_fifth_consecutive_read(tmp_path):
    outs = reads(tmp_path, 5)
    assert outs[:4] == ["", "", "", ""]
    assert "[ck batch-reads] 5 consecutive" in outs[4], outs[4]
    assert "one call" in outs[4]


def test_nudges_again_every_five(tmp_path):
    outs = reads(tmp_path, 10)
    assert "[ck batch-reads]" in outs[4] and "[ck batch-reads]" in outs[9]
    assert all(o == "" for o in outs[5:9])


def test_a_write_resets_the_streak(tmp_path):
    reads(tmp_path, 4)
    w = run(tmp_path, "sed -i '' 's/a/b/' x.py")
    assert w.returncode == 0 and w.stdout == ""
    assert all(o == "" for o in reads(tmp_path, 4)), "the streak must restart after a write"


def test_a_redirect_to_a_file_is_not_a_read(tmp_path):
    reads(tmp_path, 4)
    assert run(tmp_path, "cat a.py > b.py").stdout == ""
    assert run(tmp_path, "cat c.py").stdout == "", "the redirect reset the streak"


def test_stderr_redirects_are_still_reads(tmp_path):
    reads(tmp_path, 4)
    r = run(tmp_path, "ls missing 2>/dev/null; cat x 2>&1")
    assert "[ck batch-reads]" in r.stdout


def test_compound_read_pipelines_count_as_one_read(tmp_path):
    for i in range(4):
        assert run(tmp_path, "cd %s && grep -n foo a.py | head -20 && sed -n '1,40p' b.py" % tmp_path).stdout == ""
    assert "[ck batch-reads]" in run(tmp_path, "find . -name '*.py' | wc -l").stdout


def test_git_read_subcommands_count_but_writes_do_not(tmp_path):
    for _ in range(4):
        assert run(tmp_path, "git status --short && git log -3 --oneline").stdout == ""
    assert run(tmp_path, "git commit -m x").stdout == "", "a commit is work, not a read"
    assert run(tmp_path, "git diff --stat").stdout == "", "the streak restarted at 1"


def test_an_unknown_command_resets(tmp_path):
    reads(tmp_path, 4)
    assert run(tmp_path, "python3 -m pytest tests/ -q").stdout == ""
    assert run(tmp_path, "cat x.py").stdout == ""


def test_streaks_are_per_session(tmp_path):
    reads(tmp_path, 4, session="A")
    assert run(tmp_path, "cat z.py", session="B").stdout == "", "session B starts at 1"
    assert "[ck batch-reads]" in run(tmp_path, "cat z.py", session="A").stdout


def test_non_bash_tools_are_ignored(tmp_path):
    for _ in range(6):
        r = run(tmp_path, None, tool="Read", raw_payload=json.dumps(
            {"session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": "x"}}))
        assert r.returncode == 0 and r.stdout == ""


def test_the_hatch_silences_it(tmp_path):
    env_reads = []
    for i in range(5):
        env = dict(os.environ)
        env["CK_NO_READ_NUDGE"] = "1"
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(
            {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "cat f"}}),
            capture_output=True, text=True, env=env, cwd=str(tmp_path))
        env_reads.append(r.stdout)
    assert env_reads == [""] * 5


def test_no_project_root_writes_no_state_and_stays_silent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    for _ in range(6):
        r = run(outside, "cat f", project_dir=False)
        assert r.returncode == 0 and r.stdout == ""
    assert not (outside / ".claude").exists()


def test_malformed_payload_exits_zero(tmp_path):
    r = run(tmp_path, None, raw_payload="{not json")
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_settings_json_wires_the_hook_on_bash():
    """THE wiring. settings.json routes only PreToolUse through dispatch.sh; every PostToolUse
    hook is its own entry. A registry row alone left this hook inert in live sessions - the
    first version shipped that way and a real session with seven consecutive reads never saw
    the nudge. This test reads what Claude Code reads."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    groups = settings["hooks"]["PostToolUse"]
    wired = [g for g in groups if any("batch-reads-nudge.py" in h.get("command", "") for h in g.get("hooks", []))]
    assert wired, "batch-reads-nudge.py is not in settings.json PostToolUse; live sessions never run it"
    assert wired[0].get("matcher") == "Bash", "the nudge must run on Bash only"
    cmd = wired[0]["hooks"][0]["command"]
    assert "CLAUDE_PROJECT_DIR" in cmd and "python3" in cmd, cmd


def test_the_settings_command_string_runs_the_hook(tmp_path):
    """Execute the exact command string settings.json carries, as Claude Code would."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = next(h["command"] for g in settings["hooks"]["PostToolUse"] for h in g["hooks"]
               if "batch-reads-nudge.py" in h.get("command", ""))
    env = dict(os.environ)
    env.pop("CK_NO_READ_NUDGE", None)
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    session = "settings-string-%d" % os.getpid()
    outs = []
    for i in range(5):
        payload = json.dumps({"session_id": session, "tool_name": "Bash",
                              "tool_input": {"command": "cat f%d.py" % i}, "tool_response": {"stdout": "x"}})
        r = subprocess.run(["bash", "-c", cmd], input=payload, capture_output=True, text=True, env=env, cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr
        outs.append(r.stdout)
    state = ROOT / ".claude" / "hooks" / ".state" / ("read-streak-" + session)
    try:
        assert "[ck batch-reads]" in outs[4], outs
        assert all("[ck batch-reads]" not in o for o in outs[:4])
    finally:
        if state.exists():
            state.unlink()


def test_registry_row_is_advisory_on_bash():
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))["events"]["PostToolUse"]
    row = next((r for r in rows if r.get("id") == "batch-reads-nudge"), None)
    assert row, "the hook is not registered; it is inert"
    assert row["tier"] == "advisory", "a nudge must never be able to block"
    assert row["matcher"] == "Bash" and row["file"] == "batch-reads-nudge.py"

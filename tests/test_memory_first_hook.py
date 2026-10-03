"""Behavioral tests for memory-first.py: warn (default) / off; never blocks on the first edit."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "memory-first.py"


def project(tmp_path, memory=True):
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    if memory:
        mem = tmp_path / ".claude" / "memory"
        mem.mkdir()
        (mem / "entries.jsonl").write_text("{}\n")
    return tmp_path


def call(root, tool, tool_input=None, session="s1", env=None, args=(), **extra):
    payload = {"session_id": session, "tool_name": tool, "tool_input": tool_input or {}, **extra}
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("CK_")}
    full_env.update({"CLAUDE_PROJECT_DIR": str(root), **(env or {})})
    return subprocess.run([sys.executable, str(HOOK), *args], input=json.dumps(payload),
                          capture_output=True, text=True, env=full_env, timeout=30)


def note(p):
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"] if p.stdout.strip() else ""


def test_first_edit_without_lookup_warns_once_and_is_short(tmp_path):
    root = project(tmp_path)
    p = call(root, "Edit", {"file_path": "a.py"})
    assert p.returncode == 0 and "memory lookup" in note(p)
    assert len(note(p)) < 260
    again = call(root, "Write", {"file_path": "b.py"})
    assert again.returncode == 0 and again.stdout.strip() == ""


def test_read_of_memory_dir_counts_as_lookup(tmp_path):
    root = project(tmp_path)
    call(root, "Read", {"file_path": str(root / ".claude" / "memory" / "entries.jsonl")})
    p = call(root, "Edit", {"file_path": "a.py"})
    assert p.returncode == 0 and p.stdout.strip() == ""


def test_grep_agent_memory_and_ck_memory_cli_count(tmp_path):
    root = project(tmp_path)
    call(root, "Grep", {"pattern": "x", "path": ".claude/agent-memory"}, session="g")
    assert call(root, "Edit", {}, session="g").stdout.strip() == ""
    call(root, "Bash", {"command": "ck memory list"}, session="c")
    assert call(root, "Edit", {}, session="c").stdout.strip() == ""


def test_unrelated_reads_and_lookalike_commands_are_not_lookups(tmp_path):
    root = project(tmp_path)
    call(root, "Read", {"file_path": "src/app.py"})
    call(root, "Bash", {"command": "echo ck memoryless"})
    assert "memory lookup" in note(call(root, "Edit", {"file_path": "a.py"}))


def test_sessions_are_independent(tmp_path):
    root = project(tmp_path)
    call(root, "Read", {"file_path": ".claude/memory/entries.jsonl"}, session="one")
    assert "memory lookup" in note(call(root, "Edit", {}, session="two"))


def test_silent_when_project_has_no_memory(tmp_path):
    root = project(tmp_path, memory=False)
    assert call(root, "Edit", {"file_path": "a.py"}).stdout.strip() == ""


def test_block_is_not_a_mode_and_never_blocks(tmp_path):
    root = project(tmp_path)
    p = call(root, "Edit", {"file_path": "a.py"}, env={"CK_MEMORY_FIRST": "block"})
    assert p.returncode == 0 and "memory-first" in p.stdout  # unknown mode falls back to warn


def test_mode_from_settings_file_and_off(tmp_path):
    root = project(tmp_path)
    (root / ".claude" / "settings.json").write_text(json.dumps({"memory_first": {"mode": "off"}}))
    assert call(root, "Edit", {}).stdout.strip() == ""
    assert call(root, "Edit", {}, env={"CK_MEMORY_FIRST": "warn"}).returncode == 0


def test_silencer_dispatched_and_subagent_calls_do_nothing(tmp_path):
    root = project(tmp_path)
    assert call(root, "Edit", {}, env={"CK_NO_MEMORY_FIRST": "1"}).stdout.strip() == ""
    assert call(root, "Edit", {}, args=("--dispatched",)).stdout.strip() == ""
    assert call(root, "Edit", {}, agent_id="a1").stdout.strip() == ""


def test_malformed_payload_is_harmless(tmp_path):
    root = project(tmp_path)
    p = subprocess.run([sys.executable, str(HOOK)], input="{nope", capture_output=True, text=True,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)}, timeout=30)
    assert p.returncode == 0


def test_registered_in_settings_and_registry_and_memory_dirs_match_store():
    from claudekit import memory

    registry = json.loads((REPO / ".claude" / "hooks" / "dispatch-registry.json").read_text())
    row = [h for h in registry["events"]["PreToolUse"] if h["id"] == "memory-first"]
    assert row and row[0]["args"] == ["--dispatched"]
    settings = (REPO / ".claude" / "settings.json").read_text()
    assert "memory-first.py" in settings
    rel = memory.memory_dir(Path(".")).as_posix()
    spec = importlib.util.spec_from_file_location("mf", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert rel in mod.MEMORY_DIRS

"""Behavioral tests for scripts/gen-agent-hooks.py: Codex/Cursor configs derived from the registry."""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "gen-agent-hooks.py"
REGISTRY = REPO / ".claude" / "hooks" / "dispatch-registry.json"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=30)


def tiny_registry(tmp_path):
    reg = {"schema_version": 1, "blocking_events": ["PreToolUse"], "events": {
        "PreToolUse": [
            {"id": "g", "file": "g.sh", "runner": "bash", "tier": "blocking", "matcher": "Bash"},
            {"id": "r", "file": "r.py", "runner": "python3", "matcher": "Read", "args": ["--x", "a b"]},
            {"id": "all", "file": "all.py", "runner": "python3", "matcher": ""},
        ],
        "PostToolUse": [{"id": "e", "file": "e.py", "runner": "python3", "matcher": "Edit|Write"},
                        {"id": "w", "file": "w.py", "runner": "python3", "matcher": "WebFetch"}],
        "SessionStart": [{"id": "s", "file": "s.sh", "runner": "bash", "matcher": ""}],
        "UserPromptSubmit": [{"id": "u", "file": "u.sh", "runner": "bash", "matcher": ""}],
        "Stop": [{"id": "st", "file": "st.sh", "runner": "bash", "matcher": ""}],
        "PreCompact": [{"id": "pc", "file": "pc.sh", "runner": "bash", "matcher": ""}],
        "PostToolUseFailure": [{"id": "pf", "file": "pf.sh", "runner": "bash", "matcher": ""}],
    }}
    path = tmp_path / "reg.json"
    path.write_text(json.dumps(reg))
    return path


def files_in(cfg):
    return re.findall(r'\.claude/hooks/([\w.-]+)', json.dumps(cfg))


def test_codex_maps_events_and_skips_unsupported(tmp_path):
    out = json.loads(run("--target", "codex", "--registry", str(tiny_registry(tmp_path))).stdout)
    hooks = out["hooks"]
    assert set(hooks) == {"PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit", "Stop",
                          "PreCompact"}
    assert [e.get("matcher") for e in hooks["PreToolUse"]] == ["Bash", "Read", None]
    entry = hooks["PreToolUse"][1]["hooks"][0]
    assert entry["type"] == "command" and "r.py" in entry["command"] and "'a b'" in entry["command"]
    assert "pf.sh" not in json.dumps(out)


def test_cursor_maps_by_tool_name(tmp_path):
    out = json.loads(run("--target", "cursor", "--registry", str(tiny_registry(tmp_path))).stdout)
    assert out["version"] == 1
    h = out["hooks"]
    assert files_in(h["beforeShellExecution"]) == ["g.sh", "all.py"]
    assert files_in(h["beforeReadFile"]) == ["r.py", "all.py"]
    assert files_in(h["afterFileEdit"]) == ["e.py"]  # WebFetch row is not an edit
    assert files_in(h["beforeSubmitPrompt"]) == ["u.sh"] and files_in(h["stop"]) == ["st.sh"]
    assert files_in(h["sessionStart"]) == ["s.sh"] and files_in(h["preCompact"]) == ["pc.sh"]


def test_skipped_lists_rows_with_reasons(tmp_path):
    out = run("--skipped", "--registry", str(tiny_registry(tmp_path))).stdout
    assert "codex: skip PostToolUseFailure/pf" in out
    assert "cursor: skip PostToolUse/w" in out and "cursor: skip PostToolUseFailure/pf" in out
    assert "skip SessionStart/s" not in out and "skip PreCompact/pc" not in out


def test_out_then_check_roundtrip_and_drift(tmp_path):
    reg = tiny_registry(tmp_path)
    dest = tmp_path / "dest"
    assert run("--out", str(dest), "--registry", str(reg)).returncode == 0
    assert (dest / ".codex" / "hooks.json").is_file() and (dest / ".cursor" / "hooks.json").is_file()
    assert run("--check", str(dest), "--registry", str(reg)).returncode == 0
    (dest / ".cursor" / "hooks.json").write_text("{}")
    p = run("--check", str(dest), "--registry", str(reg))
    assert p.returncode == 1 and "DRIFT" in p.stdout and "cursor" in p.stdout
    assert run("--check", str(tmp_path / "nowhere"), "--registry", str(reg)).returncode == 1


def test_unreadable_registry_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    assert run("--registry", str(bad)).returncode == 1
    assert run("--registry", str(tmp_path / "missing.json")).returncode == 1


def test_real_registry_every_codex_event_row_is_present_and_command_runs_a_real_file():
    out = json.loads(run("--target", "codex").stdout)["hooks"]
    registry = json.loads(REGISTRY.read_text())["events"]
    for event, entries in out.items():
        assert len(entries) == len(registry[event])
        for item in entries:
            name = files_in(item)[0]
            assert (REPO / ".claude" / "hooks" / name).is_file()


def test_generated_command_executes_the_hook_from_the_project_root(tmp_path):
    reg = {"schema_version": 1, "blocking_events": [], "events": {"Stop": [
        {"id": "x", "file": "probe.sh", "runner": "bash", "matcher": "", "args": ["hello"]}]}}
    regp = tmp_path / "reg.json"
    regp.write_text(json.dumps(reg))
    cmd = json.loads(run("--target", "codex", "--registry", str(regp)).stdout)["hooks"]["Stop"][0]["hooks"][0]["command"]
    proj = tmp_path / "proj"
    (proj / ".claude" / "hooks").mkdir(parents=True)
    (proj / ".claude" / "hooks" / "probe.sh").write_text('echo "ran $1 in $(basename "$PWD")"\n')
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    sub = proj / "sub"
    sub.mkdir()
    p = subprocess.run(cmd, shell=True, cwd=sub, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and p.stdout.strip() == "ran hello in sub"

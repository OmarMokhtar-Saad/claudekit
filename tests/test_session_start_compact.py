"""SessionStart source=compact prints ONE line and stops after the concurrency check.

SessionStart stdout reaches the model and is re-sent on every later turn. On a compaction
everything session-start.sh prints (banner, graph, hygiene, previous-session excerpt, footprint,
durable memory: ~40 lines measured 2026-09-19) was already in context before the compaction, so
re-injecting it taxed every turn until the next one. startup / resume / clear, and a run with no
payload at all (the pre-payload behaviour every older test relies on), keep the full output.

Mutants this file kills:
  - ignore `source`            -> the compact run prints the banner and the excerpt
  - exit before the lock write -> the compact run leaves no lock (concurrency check lost)
  - `cat` instead of a bounded read -> a run with inherited, open stdin hangs (timeout)
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "session-start.sh"

CONTEXT = """# Session Context

**Task:** planted by test_session_start_compact

## Current Status
IN_PROGRESS.

## Next Steps
1. a planted step
"""


def project(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "session-context.md").write_text(CONTEXT, encoding="utf-8")
    return tmp_path


def run(tmp_path, payload):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env.pop("CK_RAW_OUTPUT", None)
    kwargs = {"input": payload} if payload is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run(
        ["bash", str(HOOK)], cwd=tmp_path, capture_output=True, text=True, env=env,
        timeout=60, **kwargs,
    )


def locks(tmp_path):
    d = tmp_path / ".claude" / "locks"
    return sorted(p.name for p in d.glob("session-*")) if d.is_dir() else []


def test_compact_prints_one_line_and_re_injects_nothing(tmp_path):
    result = run(project(tmp_path), json.dumps({"hook_event_name": "SessionStart", "source": "compact"}))
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "ClaudeKit session compacted" in out
    assert "ClaudeKit session started" not in out
    assert "Previous session context found" not in out, "the excerpt was in context before the compaction"
    assert "Session footprint" not in out and "Durable project memory" not in out
    assert "Graph:" not in out and "Hygiene:" not in out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) <= 2, out


def test_compact_still_takes_the_session_lock(tmp_path):
    """The concurrency check is the one thing a compaction must keep: its lock is how the
    next session learns this one is still alive."""
    run(project(tmp_path), json.dumps({"source": "compact"}))
    assert locks(tmp_path), "the compact path exited before the lock write"


@pytest.mark.parametrize("payload", [
    json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
    json.dumps({"hook_event_name": "SessionStart", "source": "resume"}),
    json.dumps({"hook_event_name": "SessionStart", "source": "clear"}),
    "",          # an empty pipe
    None,        # no stdin at all (a developer running the hook by hand)
    "not json",  # a payload extract_json_field cannot parse
])
def test_every_other_start_keeps_the_full_output(tmp_path, payload):
    result = run(project(tmp_path), payload)
    assert result.returncode == 0, result.stderr
    assert "ClaudeKit session started" in result.stdout
    assert "Previous session context found" in result.stdout, result.stdout
    assert "session compacted" not in result.stdout
    assert locks(tmp_path)


def test_a_source_field_inside_tool_input_does_not_count(tmp_path):
    """extract_json_field also looks inside tool_input/input; only the top-level `source`
    Claude Code sends on SessionStart may trim the output. A top-level `source` wins, and a
    payload whose only `source` is nested is a startup like any other."""
    nested = json.dumps({"hook_event_name": "SessionStart", "source": "startup",
                         "tool_input": {"source": "compact"}})
    result = run(project(tmp_path), nested)
    assert "ClaudeKit session started" in result.stdout

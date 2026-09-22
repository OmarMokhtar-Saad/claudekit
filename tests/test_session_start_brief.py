"""CK_SESSION_START_BRIEF=1 trims a startup to the header line; default off keeps everything.

Upstreamed 2026-09-22 from qa-agents (commit 824264b1), where `ck update` kept undoing it.
SessionStart stdout is re-sent on every later turn, so a project that has its build/test/lint
in CLAUDE.md and uses /resume-session can opt out of the ~40-line startup dump. The option is
an env var so a project sets it once in settings.json `env`; the kit default is unchanged.

Mutants this file kills:
  - ignore the variable            -> the brief run prints the excerpt and the footprint
  - exit before the lock write     -> the brief run leaves no lock (concurrency check lost)
  - default flipped to on          -> the unset run loses the excerpt
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "session-start.sh"

CONTEXT = """# Session Context

**Task:** planted by test_session_start_brief

## Current Status
IN_PROGRESS.

## Next Steps
1. a planted step
"""

STARTUP = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})


def project(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "session-context.md").write_text(CONTEXT, encoding="utf-8")
    return tmp_path


def run(tmp_path, brief):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env.pop("CK_RAW_OUTPUT", None)
    env.pop("CK_SESSION_START_BRIEF", None)
    if brief is not None:
        env["CK_SESSION_START_BRIEF"] = brief
    return subprocess.run(
        ["bash", str(HOOK)], cwd=tmp_path, capture_output=True, text=True, env=env,
        timeout=60, input=STARTUP,
    )


def locks(tmp_path):
    d = tmp_path / ".claude" / "locks"
    return sorted(p.name for p in d.glob("session-*")) if d.is_dir() else []


def test_brief_prints_the_header_line_only(tmp_path):
    result = run(project(tmp_path), "1")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "ClaudeKit session started" in out
    assert f"project: {tmp_path.name}" in out
    assert "Previous session context found" not in out, out
    assert "Session footprint" not in out and "Durable project memory" not in out
    assert "Graph:" not in out and "Hygiene:" not in out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) <= 2, out


def test_brief_still_takes_the_session_lock(tmp_path):
    run(project(tmp_path), "1")
    assert locks(tmp_path), "the brief path exited before the lock write"


@pytest.mark.parametrize("value", [None, "0", ""])
def test_default_is_off_and_keeps_the_full_output(tmp_path, value):
    result = run(project(tmp_path), value)
    assert result.returncode == 0, result.stderr
    assert "ClaudeKit session started" in result.stdout
    assert "Previous session context found" in result.stdout, result.stdout
    assert locks(tmp_path)

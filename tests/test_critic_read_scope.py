"""critic-read-scope.py: a zero-context critic reads the plan and named repo files, nothing else."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "critic-read-scope.py"
_spec = importlib.util.spec_from_file_location("critic_read_scope", HOOK)
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("target", [
    ".claude/plans/plan-x.md",
    "src/app.py",
    "README.md",
    ".claude/agents/reviewer.md",
])
def test_in_scope_allowed(root, target):
    assert cr.blocked(target, str(root)) == ""
    assert cr.blocked(str(root / target), str(root)) == ""
    assert cr.decide({"tool_input": {"file_path": target}}) == (0, "")


@pytest.mark.parametrize("target, reason", [
    (".claude/plans/plan-x.review.md", ".review.md"),
    (".claude/plans/plan-x.panel-design.md", ".panel-"),
    (".claude/hooks/.state/review-panel.jsonl", ".state"),
    (".claude/reports/reviews/x.plan.json", "reports"),
    ("docs/brief-reviewer.md", "brief"),
    (".claude/session-context.md", "session-context"),
    ("notes/handoffs/2026-11-11.md", "handoffs"),
    ("../outside.md", "outside"),
    ("/etc/hosts", "outside"),
])
def test_out_of_scope_blocked(root, target, reason):
    assert reason in cr.blocked(target, str(root))
    code, err = cr.decide({"tool_input": {"path": target}})
    assert code == 2 and "critic-read-scope" in err


def test_symlink_escape_blocked(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("x")
    os.symlink(str(outside), str(root / "link.md"))
    assert cr.blocked("link.md", str(root)) == "outside the project"


def test_root_falls_back_to_payload_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    code, _ = cr.decide({"cwd": str(tmp_path), "tool_input": {"file_path": "src/a.py"}})
    assert code == 0
    code, _ = cr.decide({"cwd": str(tmp_path), "tool_input": {"file_path": "/etc/hosts"}})
    assert code == 2


@pytest.mark.parametrize("payload", [
    {"tool_input": {"pattern": "foo"}},  # Grep/Glob with no path = cwd
    {"tool_input": {"file_path": "  "}},
    {"tool_input": {"file_path": 7}},
    {"tool_input": "x"},
    {},
    [],
])
def test_odd_input_allowed(root, payload):
    assert cr.decide(payload) == (0, "")


def test_main_exit_codes(root):
    def run(stdin):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
        return subprocess.run([sys.executable, str(HOOK)], input=stdin, env=env,
                              capture_output=True, text=True, timeout=10)
    r = run(json.dumps({"tool_input": {"file_path": ".claude/plans/p.review.md"}}))
    assert r.returncode == 2 and "out of scope" in r.stderr
    assert run(json.dumps({"tool_input": {"file_path": "src/a.py"}})).returncode == 0
    assert run("nope").returncode == 0

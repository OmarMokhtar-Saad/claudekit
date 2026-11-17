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
def root(tmp_path, tmp_path_factory, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    home = tmp_path_factory.mktemp("home")
    assert tmp_path not in home.parents and home != tmp_path
    monkeypatch.setenv("HOME", str(home))
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


def test_plan_in_another_repo_allowed_but_not_its_siblings(root, tmp_path_factory):
    plans = tmp_path_factory.mktemp("kit") / ".claude" / "plans"
    plans.mkdir(parents=True)
    for n in ("plan-x.md", "plan-x.review.md", "plan-x.panel-plan-design-critic.md", "notes.md"):
        (plans / n).write_text("x")
    assert cr.blocked(str(plans / "plan-x.md"), str(root)) == ""
    for n in ("plan-x.review.md", "plan-x.panel-plan-design-critic.md", "notes.md"):
        assert cr.blocked(str(plans / n), str(root)) == "outside the project", n
    assert cr.blocked(str(plans.parent / "hooks.md"), str(root)) == "outside the project"


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


# ---------------------------------------------------------------- S2: symlinked plans dir

def test_plan_behind_symlinked_plans_dir_allowed(root, tmp_path_factory):
    notes = tmp_path_factory.mktemp("store") / "notes"
    notes.mkdir()
    for n in ("plan-a.md", "plan-a.review.md", "plan-a.panel-plan-design-critic.md"):
        (notes / n).write_text("x")
    (root / ".claude").mkdir()
    os.symlink(str(notes), str(root / ".claude" / "plans"))
    assert cr.blocked(".claude/plans/plan-a.md", str(root)) == ""
    # siblings stay denied (pre-existing behaviour; regression guard)
    assert cr.blocked(".claude/plans/plan-a.review.md", str(root)) == "outside the project"
    assert cr.blocked(".claude/plans/plan-a.panel-plan-design-critic.md",
                      str(root)) == "outside the project"


def test_leaf_plan_symlink_not_allowed(root, tmp_path_factory):
    secret = tmp_path_factory.mktemp("outside") / "secret.txt"
    secret.write_text("x")
    plans = root / ".claude" / "plans"
    plans.mkdir(parents=True)
    state = root / ".claude" / "hooks" / ".state"
    state.mkdir(parents=True)
    (state / "x.jsonl").write_text("x")
    os.symlink(str(secret), str(plans / "plan-evil.md"))
    os.symlink(str(state / "x.jsonl"), str(plans / "plan-evil2.md"))
    assert cr.blocked(".claude/plans/plan-evil.md", str(root)) == "outside the project"
    assert ".state" in cr.blocked(".claude/plans/plan-evil2.md", str(root))


def test_symlinked_plans_dir_into_denied_dir(root):
    state = root / ".claude" / "hooks" / ".state"
    state.mkdir(parents=True)
    (state / "plan-x.md").write_text("x")
    os.symlink(str(state), str(root / ".claude" / "plans"))
    assert ".state" in cr.blocked(".claude/plans/plan-x.md", str(root))


def test_nested_file_under_symlinked_plans_dir_denied(root, tmp_path_factory):
    notes = tmp_path_factory.mktemp("store") / "notes"
    (notes / "plan-x").mkdir(parents=True)
    (notes / "plan-x" / "secret.md").write_text("x")
    (root / ".claude").mkdir()
    os.symlink(str(notes), str(root / ".claude" / "plans"))
    assert cr.blocked(".claude/plans/plan-x/secret.md", str(root)) == "outside the project"


# Account plans dir ($CLAUDE_CONFIG_DIR/plans, default ~/.claude/plans): free-named plans.

@pytest.fixture
def acct(root, tmp_path_factory, monkeypatch):
    base = tmp_path_factory.mktemp("acct")
    assert "/.claude/" not in str(base)
    (base / "plans").mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(base))
    return base


def test_account_plan_any_name_allowed(root, acct):
    plan = acct / "plans" / "hermes-learning-loop.md"
    plan.write_text("x")
    assert cr.blocked(str(plan), str(root)) == ""
    assert cr.decide({"tool_input": {"file_path": str(plan)}}) == (0, "")


@pytest.mark.parametrize("rel", [
    "plans/x.review.md",
    "plans/x.panel-design.md",
    "plans/brief-x.md",
    "plans/session-context.md",
    "plans/notes.txt",
    "plans/sub/plan-x.md",
    "settings.json",
])
def test_account_plan_siblings_denied(root, acct, rel):
    target = acct / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")
    assert cr.blocked(str(target), str(root)) == "outside the project"


def test_account_plan_missing_denied(root, acct):
    assert cr.blocked(str(acct / "plans" / "nope.md"), str(root)) == "outside the project"


def test_account_plan_symlink_leaf_denied(root, acct):
    real = acct / "plans" / "real.md"
    real.write_text("x")
    os.symlink("real.md", str(acct / "plans" / "p.md"))
    assert cr.blocked(str(acct / "plans" / "p.md"), str(root)) == "outside the project"
    assert cr.blocked(str(real), str(root)) == ""


@pytest.mark.parametrize("config_dir", [None, "", "  "])
def test_account_dir_default_home(root, monkeypatch, config_dir):
    if config_dir is not None:
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", config_dir)
    plans = Path(os.environ["HOME"]) / ".claude" / "plans"
    plans.mkdir(parents=True)
    (plans / "free-name.md").write_text("x")
    assert cr.blocked(str(plans / "free-name.md"), str(root)) == ""


def test_account_dir_symlinked(root, acct, tmp_path_factory, monkeypatch):
    (acct / "plans" / "free.md").write_text("x")
    link = tmp_path_factory.mktemp("links") / "acct_link"
    os.symlink(str(acct), str(link))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(link))
    assert cr.blocked(str(link / "plans" / "free.md"), str(root)) == ""
    assert cr.blocked(str(acct / "plans" / "free.md"), str(root)) == ""

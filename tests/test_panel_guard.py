"""panel-guard.py: critics take only `Plan: <abs path>.md. Review it.`; reviewer gets a nudge."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "panel-guard.py"
_spec = importlib.util.spec_from_file_location("panel_guard", HOOK)
pg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pg)


def call(kind, prompt):
    return pg.decide({"tool_input": {"subagent_type": kind, "prompt": prompt}})


@pytest.fixture
def plan(tmp_path):
    path = tmp_path / ".claude" / "plans" / "plan-x.md"
    path.parent.mkdir(parents=True)
    path.write_text("# x\n")
    return str(path)


@pytest.mark.parametrize("kind", sorted(pg.CRITICS))
def test_critic_exact_prompt_allowed(kind, plan):
    assert call(kind, "Plan: %s. Review it." % plan) == (0, "", "")
    assert call(kind, "  Plan: %s. Review it.\n" % plan)[0] == 0


@pytest.mark.parametrize("kind", sorted(pg.CRITICS))
@pytest.mark.parametrize("prompt", [
    "Plan: {p}. Review it. Keep it under 300 words.",
    "## Objective\nreview {p}",
    "Plan: relative/plan-x.md. Review it.",
    "Plan: /no/such/plan-x.md. Review it.",
    "",
])
def test_critic_other_prompts_denied(kind, plan, prompt):
    code, out, err = call(kind, prompt.format(p=plan))
    assert code == 2 and out == "" and "zero-context" in err


def test_critic_non_string_prompt_denied():
    assert pg.decide({"tool_input": {"subagent_type": "plan-design-critic", "prompt": 5}})[0] == 2


def test_reviewer_on_plan_gets_nudge(monkeypatch):
    monkeypatch.delenv("CK_REVIEW_PANEL", raising=False)
    code, out, err = call("reviewer", "Review .claude/plans/plan-x.md")
    assert code == 0 and err == ""
    ctx = json.loads(out)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "PreToolUse"
    assert "plan-design-critic" in ctx["additionalContext"]


@pytest.mark.parametrize("value", ["0", "off", "False"])
def test_reviewer_nudge_off_by_env(monkeypatch, value):
    monkeypatch.setenv("CK_REVIEW_PANEL", value)
    assert call("reviewer", "Review .claude/plans/plan-x.md") == (0, "", "")


@pytest.mark.parametrize("payload", [
    {"tool_input": {"subagent_type": "reviewer", "prompt": "review src/app.py"}},
    {"tool_input": {"subagent_type": "explore", "prompt": "Plan: x.md. Review it."}},
    {"tool_input": "nope"},
    {},
    [],
])
def test_everything_else_allowed(payload):
    assert pg.decide(payload) == (0, "", "")


def _main(stdin):
    return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True,
                          text=True, timeout=10)


def test_main_exit_codes(plan):
    bad = json.dumps({"tool_input": {"subagent_type": "plan-readiness-critic", "prompt": "hi"}})
    r = _main(bad)
    assert r.returncode == 2 and "panel-guard" in r.stderr
    good = json.dumps({"tool_input": {"subagent_type": "plan-readiness-critic",
                                      "prompt": "Plan: %s. Review it." % plan}})
    assert _main(good).returncode == 0
    assert _main("not json").returncode == 0
    assert _main("").returncode == 0

"""panel-format-check.py: critic Stop hook asks for one reformat when the PANEL contract breaks."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "panel-format-check.py"
_spec = importlib.util.spec_from_file_location("panel_format_check", HOOK)
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


def msg(text, **extra):
    return dict({"last_assistant_message": text}, **extra)


@pytest.mark.parametrize("text", [
    "- [Blocker] x\nPANEL: 1 blocker, 0 major",
    "PANEL: 0 blocker, 0 major  \n\n",
    "PANEL: incomplete - plan file missing",
    "a" * (3000 - 27) + "\nPANEL: 0 blocker, 0 major",
])
def test_valid_replies_allowed(text):
    assert pf.decide(msg(text)) == ""


@pytest.mark.parametrize("text", [
    "- [Blocker] x\nno summary",
    "PANEL: 1 blocker\n",
    "PANEL: 0 blocker, 0 major\ntrailing words",
    "",
    "   \n",
    "x" * 3001 + "\nPANEL: 0 blocker, 0 major",
])
def test_bad_replies_blocked_once(text):
    out = json.loads(pf.decide(msg(text)))
    assert out["decision"] == "block" and "PANEL:" in out["reason"]


def test_stop_hook_active_allows():
    assert pf.decide(msg("garbage", stop_hook_active=True)) == ""


@pytest.mark.parametrize("payload", [{}, {"last_assistant_message": 3}, [], "x"])
def test_odd_payloads_allowed(payload):
    assert pf.decide(payload) == ""


def _main(stdin):
    return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True,
                          text=True, timeout=10)


def test_main_always_exits_0():
    r = _main(json.dumps(msg("no panel")))
    assert r.returncode == 0 and json.loads(r.stdout)["decision"] == "block"
    r = _main(json.dumps(msg("PANEL: 0 blocker, 0 major")))
    assert r.returncode == 0 and r.stdout == ""
    assert _main("{broken").returncode == 0


def handback(text, **extra):
    return dict({"hook_event_name": "PreToolUse", "tool_name": "SubagentHandback",
                 "tool_input": {"message": text}, "session_id": "s", "agent_id": "a"}, **extra)


def test_handback_valid_allowed(tmp_path):
    assert pf.decide_handback(handback("PANEL: 0 blocker, 0 major"), str(tmp_path / "m")) == ""


@pytest.mark.parametrize("text", ["- [Major] x\nno panel", "x" * 3001 + "\nPANEL: 0 blocker, 0 major"])
def test_handback_bad_denied_once_then_allowed(text, tmp_path):
    marker = str(tmp_path / "d" / "m")
    out = json.loads(pf.decide_handback(handback(text), marker))["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "SubagentHandback" in out["permissionDecisionReason"]
    assert pf.decide_handback(handback(text), marker) == ""


@pytest.mark.parametrize("payload", [
    handback("no panel", tool_name="Read"), handback(3), {"tool_name": "SubagentHandback"}, []])
def test_handback_other_payloads_allowed(payload, tmp_path):
    assert pf.decide_handback(payload, str(tmp_path / "m")) == ""


def test_handback_marker_is_per_agent():
    assert pf._marker(handback("x")) != pf._marker(handback("x", agent_id="b"))
    assert pf._marker(handback("x")) == pf._marker(handback("y"))


def test_main_handback_denies_once(tmp_path):
    env = dict(os.environ, TMPDIR=str(tmp_path))
    stdin = json.dumps(handback("no panel", agent_id="main-test"))

    def run():
        return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True,
                              text=True, timeout=10, env=env)

    r = run()
    assert r.returncode == 0
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    r = run()
    assert r.returncode == 0 and r.stdout == ""

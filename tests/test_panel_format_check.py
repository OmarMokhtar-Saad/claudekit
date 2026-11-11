"""panel-format-check.py: critic Stop hook asks for one reformat when the PANEL contract breaks."""

import importlib.util
import json
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

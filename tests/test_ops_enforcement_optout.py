"""`ECC_OPS_ENFORCEMENT=off` is a per-project opt-out of the ops-enforcement hook.

Added 2026-09-19 (owner-applied hook edit). A project that wants the kit's other
hooks under the `standard` profile but not the Edit/Write source gate sets the
variable in `.claude/settings.local.json` `env`. Anything but the literal `off`
(unset, `on`, `0`, `false`) leaves the gate binding: the opt-out is spelled one
way so a typo fails closed, not open.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "ops-enforcement.sh"
SOURCE_EDIT = {"tool_name": "Edit", "tool_input": {"file_path": "src/claudekit/cli/main.py"}}


def _run(env_extra):
    env = dict(os.environ, ECC_HOOK_PROFILE="standard")
    env.pop("ECC_OPS_ENFORCEMENT", None)
    env.update(env_extra)
    return subprocess.run(["bash", str(HOOK)], input=json.dumps(SOURCE_EDIT),
                          capture_output=True, text=True, cwd=str(REPO), env=env, timeout=30)


def test_positive_control_the_gate_blocks_a_source_edit_without_the_opt_out():
    p = _run({})
    assert p.returncode == 2, p.stderr
    assert "OPS ENFORCEMENT" in p.stderr


def test_off_lets_the_same_edit_through():
    p = _run({"ECC_OPS_ENFORCEMENT": "off"})
    assert p.returncode == 0, p.stderr
    assert p.stderr == ""


@pytest.mark.parametrize("value", ["on", "OFF", "0", "false", "no", ""])
def test_only_the_literal_off_opts_out(value):
    p = _run({"ECC_OPS_ENFORCEMENT": value})
    assert p.returncode == 2, (value, p.stderr)


def test_the_hook_text_names_the_variable_once_and_documents_it():
    text = HOOK.read_text(encoding="utf-8")
    assert text.count('[ "${ECC_OPS_ENFORCEMENT:-on}" = "off" ] && exit 0') == 1
    assert "/refine" not in text, "ops-enforcement still advertises the retired /refine command"

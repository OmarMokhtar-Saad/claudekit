"""Behavioral tests for pre-plan.sh: warns on a near-duplicate plan, never blocks."""

import os
import shutil
import subprocess
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def _run(tmp_path, plan_name, existing=()):
    project = tmp_path / "proj"
    plans = project / ".claude" / "plans"
    plans.mkdir(parents=True)
    for name in existing:
        (plans / name).write_text("# plan\n")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    shutil.copy(HOOKS / "pre-plan.sh", hooks / "pre-plan.sh")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project), "ECC_HOOK_PROFILE": "standard"}
    return subprocess.run(
        ["bash", str(hooks / "pre-plan.sh"), plan_name],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=30,
    )


def test_near_duplicate_plan_warns_but_exits_zero(tmp_path):
    p = _run(tmp_path, "add-caching-layer", ["plan-add-caching-layer.md"])
    assert p.returncode == 0, p.stderr
    assert "Potential duplicate plan" in p.stdout
    assert "plan-add-caching-layer.md" in p.stdout


def test_unrelated_plan_is_silent(tmp_path):
    p = _run(tmp_path, "rotate-api-keys", ["plan-add-caching-layer.md"])
    assert p.returncode == 0, p.stderr
    assert "WARNING" not in p.stdout


def test_no_plan_name_skips_check(tmp_path):
    p = _run(tmp_path, "", ["plan-add-caching-layer.md"])
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == ""

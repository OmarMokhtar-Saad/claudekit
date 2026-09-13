"""The skill-fit refresh loop runs itself: the Stop hook and the doctor line.

Behavioural, not structural: every test EXECUTES `.claude/hooks/skill-fit-refresh.sh`
from a copy inside a tmp project (so `$CK_ROOT` is the tmp project, never this repo) or
runs `ck doctor` there, with `ECC_HOOK_PROFILE` forced and HOME / CLAUDEKIT_REGISTRY
pointed into tmp_path, so the developer's real user-level registry is never touched.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "skill-fit-refresh.sh"


def make_project(tmp_path, name="refresh-proj"):
    root = tmp_path / name
    skills = root / ".claude" / "skills"
    (skills / "house-style").mkdir(parents=True)
    (skills / "house-style" / "SKILL.md").write_text(
        '---\nname: house-style\ndescription: "Use when naming things in this project"\n'
        "stack_tags: [gradle]\n---\n\n# house-style\n", encoding="utf-8")
    (skills / "skills-registry.json").write_text(json.dumps(
        {"version": "2.0", "skills": [], "agentMapping": {}}), encoding="utf-8")
    (root / ".claude" / ".claudekit-manifest.json").write_text(
        json.dumps({"files": {}}), encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'p'\n", encoding="utf-8")
    hooks = root / ".claude" / "hooks"
    hooks.mkdir()
    shutil.copy2(HOOK, hooks / HOOK.name)
    return root


def env_for(tmp_path, profile, **extra):
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"), ECC_HOOK_PROFILE=profile,
               HOME=str(tmp_path / "home"), CLAUDEKIT_REGISTRY=str(tmp_path / "registry"))
    for key in ("CLAUDEKIT_SKILL_REFRESH", "CLAUDEKIT_SKILL_REFRESH_INTERVAL_MIN",
                "CLAUDEKIT_SKILL_REFRESH_TIMEOUT"):
        env.pop(key, None)
    env.update(extra)
    return env


def run_hook(root, env, timeout=120):
    # cwd is deliberately NOT the project: the hook must resolve it from its own path.
    return subprocess.run(["bash", str(root / ".claude" / "hooks" / HOOK.name)],
                          capture_output=True, text=True, cwd=str(root.parent),
                          env=env, timeout=timeout)


def audit_file(root):
    return root / ".claude" / "reports" / "skills" / "audit.json"


def card_file(tmp_path, name="refresh-proj"):
    return tmp_path / "registry" / f"{name}.json"


def hook_log(root):
    path = root / ".claude" / "hooks" / "hooks.log"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


@pytest.mark.parametrize("profile", ["standard", "strict"])
def test_refreshes_audit_and_card_silently(tmp_path, profile):
    root = make_project(tmp_path)
    proc = run_hook(root, env_for(tmp_path, profile))
    assert proc.returncode == 0
    assert proc.stdout == "" and proc.stderr == ""
    assert json.loads(audit_file(root).read_text())["skills"]
    card = json.loads(card_file(tmp_path).read_text())
    assert [c["name"] for c in card["cards"]] == ["house-style"]
    assert "[skill-fit-refresh] [INFO] skill card --publish: ok" in hook_log(root)


def test_minimal_profile_does_nothing(tmp_path):
    root = make_project(tmp_path)
    proc = run_hook(root, env_for(tmp_path, "minimal"))
    assert proc.returncode == 0 and proc.stdout == ""
    assert not audit_file(root).exists()
    assert not card_file(tmp_path).exists()
    assert not (root / ".claude" / "reports").exists()


def test_opt_out_env_does_nothing(tmp_path):
    root = make_project(tmp_path)
    proc = run_hook(root, env_for(tmp_path, "standard", CLAUDEKIT_SKILL_REFRESH="0"))
    assert proc.returncode == 0
    assert not audit_file(root).exists()


def test_rate_limited_until_the_stamp_ages(tmp_path):
    root = make_project(tmp_path)
    env = env_for(tmp_path, "standard")
    assert run_hook(root, env).returncode == 0
    audit_file(root).unlink()
    assert run_hook(root, env).returncode == 0
    assert not audit_file(root).exists(), "second run inside 24h must stand down"
    stamp = root / ".claude" / "reports" / "skills" / "refresh.stamp"
    old = time.time() - 25 * 3600
    os.utime(stamp, (old, old))
    assert run_hook(root, env).returncode == 0
    assert audit_file(root).exists(), "a stamp older than the interval must re-run"


def test_a_failing_step_is_logged_not_raised(tmp_path):
    root = make_project(tmp_path)
    (root / ".claude" / ".claudekit-manifest.json").unlink()  # card refuses without it
    proc = run_hook(root, env_for(tmp_path, "standard"))
    assert proc.returncode == 0 and proc.stdout == "" and proc.stderr == ""
    assert not card_file(tmp_path).exists()
    assert "[skill-fit-refresh] [WARN] skill card --publish: exit 1" in hook_log(root)


def test_a_hung_cli_is_killed_by_the_timeout(tmp_path):
    root = make_project(tmp_path)
    fake = tmp_path / "fakepkg" / "claudekit" / "cli"
    fake.mkdir(parents=True)
    (fake.parent / "__init__.py").write_text("", encoding="utf-8")
    (fake / "__init__.py").write_text("", encoding="utf-8")
    (fake / "main.py").write_text(
        "import time\nif __name__ == '__main__':\n    time.sleep(60)\n", encoding="utf-8")
    env = env_for(tmp_path, "standard", PYTHONPATH=str(tmp_path / "fakepkg"),
                  CLAUDEKIT_SKILL_REFRESH_TIMEOUT="1")
    started = time.monotonic()
    proc = run_hook(root, env, timeout=50)
    assert proc.returncode == 0
    assert time.monotonic() - started < 30
    assert "skill audit --save: timed out after 1s" in hook_log(root)


def test_not_a_skills_project_does_nothing(tmp_path):
    root = make_project(tmp_path)
    shutil.rmtree(root / ".claude" / "skills")
    assert run_hook(root, env_for(tmp_path, "standard")).returncode == 0
    assert not (root / ".claude" / "reports").exists()


# ----------------------------------------------------------------- doctor line

def doctor(root, env, *args):
    proc = subprocess.run([sys.executable, "-m", "claudekit.cli.main", "doctor", *args],
                          capture_output=True, text=True, cwd=str(root), env=env,
                          timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def summary(out):
    keep = ("Passed:", "Skipped:", "Warnings:", "Failed:", "Readiness:")
    return [line for line in out.splitlines() if line.strip().startswith(keep)]


def publish_other_card(tmp_path):
    reg = tmp_path / "registry"
    reg.mkdir(exist_ok=True)
    (reg / "other.json").write_text(json.dumps({"card_version": 1, "project": "other",
        "cards": [{"card_version": 1, "name": "gradle-build",
                   "stack_tags": ["gradle", "java"],
                   "description": "Use when building with Gradle", "tokens": 7}]}),
        encoding="utf-8")


def test_doctor_reports_suggestions_as_info_without_touching_strict(tmp_path):
    root = make_project(tmp_path)
    env = env_for(tmp_path, "minimal")
    code_before, out_before = doctor(root, env, "--strict")
    assert "skill suggestion" not in out_before
    publish_other_card(tmp_path)
    code_after, out_after = doctor(root, env, "--strict")
    assert "1 skill suggestion(s) from other projects" in out_after
    assert "ck skill match" in out_after
    assert code_after == code_before
    assert summary(out_after) == summary(out_before)


def test_doctor_is_silent_without_a_registry(tmp_path):
    root = make_project(tmp_path)
    env = env_for(tmp_path, "minimal")
    _, out = doctor(root, env)
    assert "skill suggestion" not in out

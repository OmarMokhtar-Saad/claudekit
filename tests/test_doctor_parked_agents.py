"""`ck doctor` counts parked agents toward the expected set.

install.sh honours `agents-unused/<name>.md` and the manifest's `parked`/`removed` lists
(tests/test_install_overrides.py), so an agent the project deliberately parked is a decision,
not a missing file. Measured 2026-09-22 on qa-agents: 12 parked agents made every doctor run
report `Agents installed: 19 — Expected ≥22`.

Mutants this file kills:
  - parked agents ignored            -> the parked project fails the agents check
  - any file in agents-unused counts -> a parked agent that is ALSO installed is double-counted
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from claudekit.cli.main import EXPECTED_AGENTS  # noqa: E402


def ck(*args, cwd):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), ECC_HOOK_PROFILE="minimal")
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main", *args],
                          capture_output=True, text=True, cwd=str(cwd), env=env,
                          timeout=300)


def installed(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    r = subprocess.run(["bash", str(ROOT / "install.sh"), str(tmp_path), "--full", "--yes"],
                       capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr + r.stdout
    return tmp_path / ".claude"


def agents_line(result):
    # ok() prints to stdout, err() to stderr.
    out = result.stdout + result.stderr
    return next(ln for ln in out.splitlines() if "Agents installed" in ln)


def park(claude, names):
    (claude / "agents-unused").mkdir(exist_ok=True)
    for name in names:
        shutil.move(str(claude / "agents" / name), str(claude / "agents-unused" / name))


def test_parked_agents_count_toward_the_expected_set(tmp_path):
    claude = installed(tmp_path)
    park(claude, ["planner.md", "reviewer.md", "coordinator.md"])
    line = agents_line(ck("doctor", cwd=tmp_path))
    assert "✓" in line, line
    assert "(+3 parked)" in line, line


def test_manifest_removed_agents_count_too(tmp_path):
    claude = installed(tmp_path)
    (claude / "agents" / "planner.md").unlink()
    m = json.loads((claude / ".claudekit-manifest.json").read_text())
    m["removed"] = ["agents/planner.md"]
    (claude / ".claudekit-manifest.json").write_text(json.dumps(m))
    line = agents_line(ck("doctor", cwd=tmp_path))
    assert "✓" in line and "(+1 parked)" in line, line


def test_a_parked_copy_of_an_installed_agent_is_not_double_counted(tmp_path):
    claude = installed(tmp_path)
    # Delete three, but "park" only a copy of one that is still installed: the two
    # genuinely missing agents are missing, and the parked copy adds nothing.
    for name in ("planner.md", "reviewer.md", "coordinator.md"):
        (claude / "agents" / name).unlink()
    (claude / "agents-unused").mkdir()
    shutil.copy(str(claude / "agents" / "tester.md"), str(claude / "agents-unused" / "tester.md"))
    line = agents_line(ck("doctor", cwd=tmp_path))
    assert "✗" in line, line
    assert f"Expected ≥{EXPECTED_AGENTS}" in line, line


def test_an_actually_missing_agent_still_fails(tmp_path):
    claude = installed(tmp_path)
    (claude / "agents" / "planner.md").unlink()
    line = agents_line(ck("doctor", cwd=tmp_path))
    assert "✗" in line, line

"""`ck implement <ops.json>` — the implementer agent's sequence as one CLI command.

Behavioural throughout: every test drives `python -m claudekit.cli.main implement` as a
subprocess against a REAL ops config and the REAL operations engine in a throwaway project,
then asserts what landed on disk and what the single RESULT line says. Nothing here reads
the CLI source.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / ".claude" / "operations" / "scripts"
ORIGINAL = "VALUE = 1\n"


@pytest.fixture
def project(tmp_path):
    """A throwaway project carrying the live operations engine."""
    proj = tmp_path / "proj"
    (proj / ".claude" / "operations").mkdir(parents=True)
    shutil.copytree(SCRIPTS, proj / ".claude" / "operations" / "scripts")
    (proj / ".claude" / "plans").mkdir()
    (proj / "src").mkdir()
    (proj / "src" / "app.py").write_text(ORIGINAL, encoding="utf-8")
    return proj


def write_config(project, slug, edits, validation=(), heading="Validation commands"):
    """A real plan + ops config pair, named so the CLI's own resolution finds the plan."""
    fence = "\n".join(validation)
    plan = project / ".claude" / "plans" / f"plan-{slug}.md"
    plan.write_text(
        f"# Plan: {slug}\n\n## Scope\n\n- `src/app.py`\n\n"
        f"## {heading}\n\n```bash\n{fence}\n```\n",
        encoding="utf-8")
    config = project / ".claude" / "plans" / f"ops-{slug}.json"
    config.write_text(json.dumps({
        "plan": f"ops-{slug}",
        "operations": [{"type": "code_edit", "path": "src/app.py",
                        "description": "bump the fixture constant",
                        "edits": edits}],
    }, indent=2), encoding="utf-8")
    return config


def run_implement(project, config, *extra):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        [sys.executable, "-m", "claudekit.cli.main", "implement",
         str(config.relative_to(project)), "--no-approval", *extra],
        cwd=str(project), capture_output=True, text=True, env=env, timeout=300)


def result_line(proc):
    lines = [ln for ln in (proc.stdout + proc.stderr).splitlines()
             if ln.startswith("RESULT: ")]
    assert len(lines) == 1, (
        f"expected exactly one RESULT line, got {len(lines)}: {lines}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return lines[0]


BUMP = [{"find": "VALUE = 1", "replace": "VALUE = 2"}]


def test_implement_executes_the_config_then_the_plans_validation_commands(project):
    """The whole point of the command: the edit lands AND the plan's own checks run after
    it. The check asserts the post-state, so a run that executed the validation commands
    before the executor would fail here rather than pass vacuously."""
    config = write_config(project, "bump", BUMP, validation=[
        "python3 -c \"assert open('src/app.py').read() == 'VALUE = 2\\n'\"",
    ])

    proc = run_implement(project, config)

    assert (project / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert proc.returncode == 0, proc.stdout + proc.stderr
    line = result_line(proc)
    assert "validation 1/1 passed" in line
    # The engine reports "operations" as a list of records; the summary must say how many,
    # not print them. Unasserted, that regression shipped green once already.
    assert "applied 1 operation(s)" in line, line


def test_a_failing_validation_command_fails_the_command(project):
    """A green RESULT line after a red check would make the command worse than useless:
    it is the only thing the caller reads."""
    config = write_config(project, "redcheck", BUMP, validation=[
        "python3 -c \"import sys; sys.exit(3)\"",
    ])

    proc = run_implement(project, config)

    assert (project / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n", \
        "precondition lost: the execute stage did not run, so the failing check proves nothing"
    assert proc.returncode != 0
    assert "1 failed" in result_line(proc)


def test_a_config_that_fails_validation_writes_nothing(project):
    """Stage order is the safety property: a config the validator refuses must never reach
    the executor."""
    config = project / ".claude" / "plans" / "ops-bad.json"
    config.write_text(json.dumps({"plan": "ops-bad", "operations": [
        {"type": "code_edit", "path": "src/app.py"},  # no edits key
    ]}), encoding="utf-8")

    proc = run_implement(project, config)

    assert (project / "src" / "app.py").read_text(encoding="utf-8") == ORIGINAL
    assert proc.returncode != 0
    assert "FAILED at validate" in result_line(proc)
    assert "[3/4]" not in proc.stdout, "the executor ran after the validator refused"


def test_baseline_drift_stops_before_the_real_execute(project):
    """Baseline drift is the failure the validator cannot catch -- it hashes nothing -- so
    it is the case that proves the dry-run stage is a real gate and not decoration."""
    config = write_config(project, "drift", BUMP)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["baseline"] = {"src/app.py": "sha256:" + "0" * 64}
    config.write_text(json.dumps(data, indent=2), encoding="utf-8")

    proc = run_implement(project, config)

    assert (project / "src" / "app.py").read_text(encoding="utf-8") == ORIGINAL
    assert proc.returncode != 0
    assert "FAILED at dry-run" in result_line(proc), \
        "a config the validator passes and the executor refuses must fail at the dry run"


def test_a_shell_only_validation_command_is_skipped_not_shelled_out(project):
    """Plan text is never handed to a shell. The canary file proves it: if the pipeline ran
    composed, the second half would have created it."""
    canary = project / "canary.txt"
    config = write_config(project, "pipeline", BUMP, validation=[
        f"python3 -c \"print(1)\" | python3 -c \"open('{canary.name}','w').write('x')\"",
    ])

    proc = run_implement(project, config)

    assert not canary.exists(), "the validation command was composed by a shell"
    assert proc.returncode == 0
    assert "1 skipped" in result_line(proc)


def test_a_plan_with_no_validation_fence_still_runs_the_engine(project):
    """Missing checks are a warning, never a reason to skip the operations engine."""
    config = write_config(project, "noplan", BUMP)
    (project / ".claude" / "plans" / "plan-noplan.md").unlink()

    proc = run_implement(project, config)

    assert (project / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert proc.returncode == 0
    assert "validation 0/0 passed" in result_line(proc)


def test_the_plan_is_resolved_from_the_config_name(project):
    """`ops-<slug>-followup.json` walks back to `plan-<slug>.md`; without the walk the
    follow-up config would silently run no checks."""
    write_config(project, "resolve", BUMP, validation=[
        "python3 -c \"assert open('src/app.py').read() == 'VALUE = 2\\n'\"",
    ], heading="Testing Strategy")
    config = project / ".claude" / "plans" / "ops-resolve-followup.json"
    config.write_text((project / ".claude" / "plans" / "ops-resolve.json")
                      .read_text(encoding="utf-8"), encoding="utf-8")

    proc = run_implement(project, config)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "validation 1/1 passed" in result_line(proc)

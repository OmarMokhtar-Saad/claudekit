"""`ck skill new` — behavioural proof that creation and registration are one act.

Each test drives the real CLI in a real temp project and then runs the repo's own
gates against what the generator emitted. The point of proof 4 is that a
generator whose output fails our own lint is worse than no generator: it
manufactures drift at scale.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FLOOR = os.path.join(REPO_ROOT, "scripts", "check-context-floor.py")
# The gate CLI cannot measure without its module, and the temp project has no
# src/ tree; planting it beside the script is the supported second lookup path.
FLOOR_MODULE = os.path.join(REPO_ROOT, "src", "claudekit", "context_floor.py")
GEN_REGISTRY = os.path.join(REPO_ROOT, "scripts", "gen-registry.py")
GEN_DOCS = os.path.join(REPO_ROOT, "scripts", "gen-docs.py")


@pytest.fixture()
def project(tmp_path):
    """A minimal installed-shape project: skills registry, agents, CLAUDE.md."""
    root = tmp_path / "proj"
    (root / ".claude" / "skills").mkdir(parents=True)
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# project\n")
    (root / ".claude" / "skills" / "skills-registry.json").write_text(json.dumps({
        "version": "1.0.0", "lastUpdated": "2026-01-01", "description": "test",
        "skills": [], "agentMapping": {}, "agentsWithoutSkills": [],
    }, indent=2) + "\n")
    shutil.copy(FLOOR, root / "scripts" / "check-context-floor.py")
    shutil.copy(FLOOR_MODULE, root / "scripts" / "context_floor.py")
    shutil.copy(GEN_REGISTRY, root / "scripts" / "gen-registry.py")
    shutil.copy(GEN_DOCS, root / "scripts" / "gen-docs.py")
    # gen-docs.py owns the component counts (CLAUDE.md hard rule 8) and needs the
    # two blocks it generates: the README inventory table and the counts block in
    # the CLI. Both are synthetic here, so this fixture depends on the generator
    # rather than on today's wording of the real README.
    (root / "README.md").write_text(
        "# proj\n\n<!-- BEGIN GENERATED:inventory -->\n<!-- END GENERATED:inventory -->\n")
    (root / "src" / "claudekit" / "cli").mkdir(parents=True)
    (root / "src" / "claudekit" / "cli" / "main.py").write_text(
        "# BEGIN GENERATED:counts\n# END GENERATED:counts\n")
    # Baseline the generated blocks, so a later red gate is caused by the skill
    # this test creates and by nothing else.
    subprocess.run([sys.executable, str(root / "scripts" / "gen-docs.py")],
                   capture_output=True, text=True, check=True)
    return root


def ck(root, *args):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "src"))
    return subprocess.run(
        [sys.executable, "-m", "claudekit.cli.main", *args],
        capture_output=True, text=True, cwd=str(root), env=env,
    )


def gen_docs(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "gen-docs.py"), *args],
        capture_output=True, text=True, cwd=str(root))


def registry(root):
    return json.loads((root / ".claude" / "skills" / "skills-registry.json").read_text())


def test_creates_and_registers_in_one_act(project):
    result = ck(project, "skill", "new", "widget-forge",
                "--description", "Use when forging widgets")
    assert result.returncode == 0, result.stdout + result.stderr
    skill_md = project / ".claude" / "skills" / "widget-forge" / "SKILL.md"
    assert skill_md.exists()
    ids = [s["id"] for s in registry(project)["skills"]]
    assert ids == ["widget-forge"]
    entry = registry(project)["skills"][0]
    assert entry["path"] == "skills/widget-forge/SKILL.md"
    assert entry["usedBy"] == []


def test_there_is_no_way_to_hand_set_used_by(project):
    """A generator must not be able to put a gate red. `--used-by` could.

    `usedBy` is DERIVED by gen-registry.py from each agent's `## Skill Loading`
    section. The flag let the operator assert it instead, and the assertion could
    only disagree: `ck skill new x --used-by planner` produced
    `DRIFT usedBy x: registry=['planner'] derived=[]`, and the remedy the CLI
    printed (`gen-registry.py`) resolved it by discarding the stated intent
    without a word. The flag is gone; the derivation is the only writer.
    """
    rejected = ck(project, "skill", "new", "widget-forge",
                  "--description", "Use when forging widgets",
                  "--used-by", "planner")
    assert rejected.returncode != 0, rejected.stdout
    assert "used-by" in rejected.stderr, rejected.stderr
    assert not (project / ".claude" / "skills" / "widget-forge").exists()


def test_creation_leaves_the_registry_gate_green(project):
    """The whole point: what the generator writes is what the gate derives."""
    assert ck(project, "skill", "new", "widget-forge",
              "--description", "Use when forging widgets").returncode == 0
    assert registry(project)["skills"][0]["usedBy"] == []
    check = subprocess.run(
        [sys.executable, str(project / "scripts" / "gen-registry.py"), "--check"],
        capture_output=True, text=True, cwd=str(project))
    assert check.returncode == 0, check.stdout + check.stderr


def test_generated_skill_passes_the_repos_own_gates(project):
    """PROOF 4: the emitted asset survives EVERY gate the corpus enforces.

    Three of the eight gates apply to a tree this small: the registry gate, the
    context-floor gate and the docs-count gate. The count gate needs the
    generator re-run first -- see the test below, which pins that as a required
    follow-up rather than letting it look optional.
    """
    assert ck(project, "skill", "new", "widget-forge",
              "--description", "Use when forging widgets").returncode == 0
    assert gen_docs(project).returncode == 0  # counts are generator-owned, not hand-set
    for script in ("gen-registry.py", "check-context-floor.py", "gen-docs.py"):
        result = subprocess.run(
            [sys.executable, str(project / "scripts" / script), "--check"],
            capture_output=True, text=True, cwd=str(project),
        )
        assert result.returncode == 0, f"{script}: {result.stdout}{result.stderr}"


def test_a_new_skill_leaves_the_count_gate_red_until_gen_docs_reruns(project):
    """The count drift is unavoidable BY DESIGN, so it is pinned, not hidden.

    `gen-docs.py` owns the component counts and the skill count just changed;
    hard rule 8 forbids hand-editing them, so the only honest remedy is to
    re-run the generator. What must never happen is that this passes unnoticed:
    the gate goes red immediately, and green again only after regeneration.
    """
    assert gen_docs(project, "--check").returncode == 0, "fixture baseline is not clean"
    assert ck(project, "skill", "new", "widget-forge",
              "--description", "Use when forging widgets").returncode == 0
    stale = gen_docs(project, "--check")
    assert stale.returncode == 1, stale.stdout + stale.stderr
    assert "out of date" in stale.stderr, stale.stderr
    assert gen_docs(project).returncode == 0
    fixed = gen_docs(project, "--check")
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr


def test_the_cli_names_gen_docs_as_the_next_step(project):
    """The hint has to name the gate the command just invalidated."""
    result = ck(project, "skill", "new", "widget-forge",
                "--description", "Use when forging widgets")
    assert result.returncode == 0, result.stderr
    assert "scripts/gen-docs.py" in result.stdout, result.stdout


def test_the_hint_is_omitted_where_the_script_does_not_exist(project):
    """An installed user project has no scripts/gen-docs.py; do not name it."""
    os.remove(project / "scripts" / "gen-docs.py")
    result = ck(project, "skill", "new", "widget-forge",
                "--description", "Use when forging widgets")
    assert result.returncode == 0, result.stderr
    assert "gen-docs.py" not in result.stdout
    assert "ck doctor" in result.stdout


def test_an_unrelated_over_budget_category_warns_but_does_not_block(project):
    """A CLAUDE.md over its own budget must not make skills uncreatable.

    The first draft refused on ANY over-budget category, so a project whose
    CLAUDE.md was too big could not create a skill at all -- for a reason the
    skill did not cause. It warns now, and proceeds.
    """
    (project / "CLAUDE.md").write_text("x" * 20000)  # x4 delivery weight > 31000
    result = ck(project, "skill", "new", "still-allowed",
                "--description", "Use when x")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLAUDE.md" in result.stdout
    assert "over budget" in result.stdout
    assert (project / ".claude" / "skills" / "still-allowed" / "SKILL.md").exists()


def test_the_floor_remedy_names_a_command_the_project_actually_has(tmp_path):
    """An installed project has no scripts/check-context-floor.py to run."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from claudekit import context_floor

    bulky = tmp_path / ".claude" / "skills" / "bulky"
    bulky.mkdir(parents=True)
    (bulky / "SKILL.md").write_text(
        '---\nname: bulky\ndescription: "%s"\n---\nbody\n' % ("x" * 9100))
    refusal, warnings = context_floor.check_new_skill(tmp_path, "Use when x")
    assert refusal and "ck doctor" in refusal
    assert "scripts/check-context-floor.py" not in refusal
    assert warnings == ()


def test_description_that_would_breach_the_floor_is_refused(project):
    """PROOF 1: named cause, real numbers, and nothing written."""
    filler = "x" * 8900
    (project / ".claude" / "skills" / "bulky").mkdir()
    (project / ".claude" / "skills" / "bulky" / "SKILL.md").write_text(
        f'---\nname: bulky\ndescription: "{filler}"\n---\nbody\n')
    result = ck(project, "skill", "new", "one-too-many",
                "--description", "y" * 200)
    assert result.returncode == 1, result.stdout
    assert "context floor" in result.stderr
    assert "skill descriptions" in result.stderr
    assert "9000" in result.stderr
    assert not (project / ".claude" / "skills" / "one-too-many").exists()
    assert [s["id"] for s in registry(project)["skills"]] == []


def test_invisible_skill_is_not_charged_to_the_floor(project):
    """disable-model-invocation costs no always-on context, so it is admitted."""
    filler = "x" * 8900
    (project / ".claude" / "skills" / "bulky").mkdir()
    (project / ".claude" / "skills" / "bulky" / "SKILL.md").write_text(
        f'---\nname: bulky\ndescription: "{filler}"\n---\nbody\n')
    result = ck(project, "skill", "new", "invisible-one",
                "--description", "y" * 200, "--invisible")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (project / ".claude" / "skills" / "invisible-one" / "SKILL.md").read_text()
    assert "disable-model-invocation: true" in text


def test_refuses_a_name_that_already_exists(project):
    (project / ".claude" / "skills" / "taken").mkdir()
    (project / ".claude" / "skills" / "taken" / "SKILL.md").write_text(
        '---\nname: taken\ndescription: "x"\n---\nbody\n')
    result = ck(project, "skill", "new", "taken", "--description", "Use when x")
    assert result.returncode == 1
    assert "already exists" in result.stderr


@pytest.mark.parametrize("name", ["Bad-Name", "-leading", "has space", ""])
def test_refuses_invalid_names(project, name):
    result = ck(project, "skill", "new", name, "--description", "Use when x")
    assert result.returncode != 0


def test_refuses_when_there_is_no_registry(tmp_path):
    root = tmp_path / "bare"
    (root / ".claude" / "skills").mkdir(parents=True)
    result = ck(root, "skill", "new", "x-skill", "--description", "Use when x")
    assert result.returncode == 1
    assert "registers as it creates" in result.stderr
    assert not (root / ".claude" / "skills" / "x-skill").exists()


def test_a_failed_registry_write_leaves_no_orphan_directory(project, monkeypatch):
    """The atomicity claim, exercised in-process rather than asserted."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from claudekit import skills

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(skills, "_write_json", boom)
    with pytest.raises(OSError):
        skills.new_skill(project, "half-written", "Use when x")
    assert not (project / ".claude" / "skills" / "half-written").exists()

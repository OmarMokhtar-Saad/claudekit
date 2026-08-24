"""Behavioral tests for the three gates that were scoped past the code they cover.

Each gate is proven the same way: point it at real drift and assert it goes red,
remove the drift and assert it goes green. A gate that cannot fail is a
`vacuous-check`, which is the class of defect this module exists to prevent.

Nothing here mutates the real tree: the gen-docs case runs against a `tmp_path`
mirror whose heavyweight asset directories are symlinks back to the repo, and the
doctor case builds a throwaway project + fake install root.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GEN_DOCS = REPO / "scripts" / "gen-docs.py"
MAIN_PY = REPO / "src" / "claudekit" / "cli" / "main.py"
SCHEMA = REPO / "config.schema.json"
HOOKS_CONFIG = REPO / ".claude" / "hooks" / "config.json"

# The hook profile is read from the environment by every ClaudeKit entry point;
# tests pin it so a developer's `.claude/settings.local.json` cannot change results.
ENV = dict(os.environ, ECC_HOOK_PROFILE="minimal")

# doctor prints status marks; match the verdict line, not the exit code.
# NOT colourised here on purpose: `_run` captures through a pipe, and since
# 2026-08-24 doctor honours NO_COLOR and a non-tty stdout, so no escape codes are
# emitted into a capture. The previous form embedded the raw ANSI and therefore
# asserted the old defect -- that colour was unconditional -- as if it were the
# contract. Set FORCE_COLOR in the env if a test ever needs the coloured form.
OK_MARK = "[\u2713]"
FAIL_MARK = "[\u2717]"
SCHEMA_LABEL = "Hooks config.json matches config.schema.json"


def _run(args, cwd, env=None):
    return subprocess.run([sys.executable, *args], cwd=str(cwd), capture_output=True,
                          text=True, timeout=300, env=env or ENV)


# --------------------------------------------------------------------------
# Gate 1: mypy must cover .claude/operations/scripts/, not just src/claudekit
# --------------------------------------------------------------------------

class TestMypyScope:
    def test_config_lists_the_operations_scripts(self):
        text = (REPO / "pyproject.toml").read_text()
        block = text.split("[tool.mypy]", 1)[1]
        files = re.search(r"files\s*=\s*\[(.*?)\]", block, re.DOTALL).group(1)
        assert "src/claudekit" in files
        assert ".claude/operations/scripts" in files, (
            "the operations engine is ~4.7k lines of shipped Python; leaving it out "
            "of `files` makes the mypy DoD gate vacuous"
        )

    def test_gate_is_green_and_actually_reaches_the_ops_scripts(self):
        pytest.importorskip("mypy")
        proc = _run(["-m", "mypy"], REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        checked = re.search(r"in (\d+) source files?", proc.stdout)
        assert checked and int(checked.group(1)) >= 18, (
            "mypy reported %s - the ops scripts are not in scope" % proc.stdout.strip()
        )

    def test_gate_fails_on_a_type_error_in_an_ops_script(self, tmp_path):
        """Red arm: a type error planted in the widened path must break the gate."""
        pytest.importorskip("mypy")
        scripts = tmp_path / ".claude" / "operations" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "planted.py").write_text("def f() -> int:\n    return 'not an int'\n")
        cfg = tmp_path / "pyproject.toml"
        cfg.write_text('[tool.mypy]\npython_version = "3.9"\n'
                       'ignore_missing_imports = true\n'
                       'files = [".claude/operations/scripts"]\n')
        proc = _run(["-m", "mypy", "--config-file", str(cfg)], tmp_path)
        assert proc.returncode != 0
        assert "planted.py" in proc.stdout


# --------------------------------------------------------------------------
# Gate 2: gen-docs must own the count floors baked into the CLI
# --------------------------------------------------------------------------

def _mirror(tmp_path):
    """A writable repo mirror: real assets by symlink, gated files by copy."""
    root = tmp_path / "mirror"
    (root / "scripts").mkdir(parents=True)
    (root / "src" / "claudekit" / "cli").mkdir(parents=True)
    for name in ("docs", "config.schema.json"):
        os.symlink(REPO / name, root / name)
    (root / ".claude").mkdir()
    for name in ("agents", "commands", "skills", "hooks", "settings.json"):
        os.symlink(REPO / ".claude" / name, root / ".claude" / name)
    shutil.copy(REPO / "README.md", root / "README.md")
    shutil.copy(GEN_DOCS, root / "scripts" / "gen-docs.py")
    shutil.copy(MAIN_PY, root / "src" / "claudekit" / "cli" / "main.py")
    return root


class TestGenDocsCoversTheCli:
    def test_cli_carries_no_hand_written_count(self):
        assert "# BEGIN GENERATED:counts" in MAIN_PY.read_text()
        for literal in ("≥9 agents", "≥8 commands", "≥27 skills"):
            assert literal not in MAIN_PY.read_text(), (
                "hard rule 8: %r is a hand-edited component count" % literal
            )

    def test_check_is_green_on_the_real_tree(self):
        """Couples the suite to the live asset inventory on purpose: that is the gate."""
        proc = _run([str(GEN_DOCS), "--check"], REPO)
        assert proc.returncode == 0, (
            "docs-drift gate is red - run `python3 scripts/gen-docs.py` to regenerate, "
            "then re-run.\n" + proc.stdout + proc.stderr
        )

    def test_check_fails_when_the_generated_block_goes_stale(self, tmp_path):
        root = _mirror(tmp_path)
        main = root / "src" / "claudekit" / "cli" / "main.py"
        main.write_text(re.sub(r"EXPECTED_AGENTS = \d+", "EXPECTED_AGENTS = 1",
                               main.read_text()))
        red = _run([str(root / "scripts" / "gen-docs.py"), "--check"], root)
        assert red.returncode == 1, red.stdout + red.stderr
        assert "main.py" in red.stderr

        fix = _run([str(root / "scripts" / "gen-docs.py")], root)
        assert fix.returncode == 0, fix.stdout + fix.stderr
        green = _run([str(root / "scripts" / "gen-docs.py"), "--check"], root)
        assert green.returncode == 0, green.stdout + green.stderr

    def test_check_fails_on_a_hardcoded_count_in_cli_prose(self, tmp_path):
        root = _mirror(tmp_path)
        main = root / "src" / "claudekit" / "cli" / "main.py"
        main.write_text(main.read_text() + "\n# drift probe: 5 agents\n")
        red = _run([str(root / "scripts" / "gen-docs.py"), "--check"], root)
        assert red.returncode == 1
        assert "says 5, should be" in red.stderr

    def test_check_fails_when_the_generated_block_is_deleted(self, tmp_path):
        """The gate must not be disableable by deleting the marker it keys on.

        `_replace_block` returns text unchanged when it finds no markers, so without an
        explicit missing-marker error the whole count gate degrades to a silent pass -
        the exact `vacuous-check` class this module exists to prevent.
        """
        root = _mirror(tmp_path)
        main = root / "src" / "claudekit" / "cli" / "main.py"
        main.write_text(re.sub(r"# BEGIN GENERATED:counts.*?# END GENERATED:counts\n", "",
                               main.read_text(), flags=re.DOTALL))
        assert "# BEGIN GENERATED:counts" not in main.read_text()
        red = _run([str(root / "scripts" / "gen-docs.py"), "--check"], root)
        assert red.returncode == 1, red.stdout + red.stderr
        assert "has no" in red.stderr and "BEGIN GENERATED:counts" in red.stderr

        # A plain run cannot regenerate a block that is not there either: refuse loudly.
        fix = _run([str(root / "scripts" / "gen-docs.py")], root)
        assert fix.returncode == 1
        assert "nothing to regenerate" in fix.stderr

    def test_code_counts_are_never_auto_rewritten(self, tmp_path):
        """A bare number in Python has no safe in-place fix: report, never rewrite."""
        root = _mirror(tmp_path)
        main = root / "src" / "claudekit" / "cli" / "main.py"
        main.write_text(main.read_text() + "\n# drift probe: 5 agents\n")
        proc = _run([str(root / "scripts" / "gen-docs.py")], root)
        assert proc.returncode == 1
        assert "could not auto-fix" in proc.stderr
        assert "# drift probe: 5 agents" in main.read_text()


# --------------------------------------------------------------------------
# Gate 3: ck doctor must apply the shipped config.schema.json
# --------------------------------------------------------------------------

def _fake_install(tmp_path, config):
    """A project dir plus an install root holding the schema, wired via CLAUDEKIT_HOME."""
    home = tmp_path / "install"
    (home / ".claude" / "agents").mkdir(parents=True)
    shutil.copy(SCHEMA, home / "config.schema.json")
    proj = tmp_path / "proj"
    (proj / ".claude" / "hooks").mkdir(parents=True)
    (proj / ".claude" / "hooks" / "config.json").write_text(json.dumps(config, indent=2))
    env = dict(ENV, CLAUDEKIT_HOME=str(home))
    return proj, env


class TestDoctorAppliesConfigSchema:
    def test_shipped_config_satisfies_shipped_schema(self):
        """Regression for the 46-day drift: nothing had ever run this pairing."""
        jsonschema = pytest.importorskip("jsonschema")
        errors = list(jsonschema.Draft7Validator(
            json.loads(SCHEMA.read_text())).iter_errors(json.loads(HOOKS_CONFIG.read_text())))
        assert errors == [], [e.message for e in errors]

    def test_doctor_passes_the_shipped_config(self, tmp_path):
        """GREEN control for the test below: same skeleton project, valid config."""
        pytest.importorskip("jsonschema")
        proj, env = _fake_install(tmp_path, json.loads(HOOKS_CONFIG.read_text()))
        proc = _run(["-m", "claudekit.cli.main", "doctor"], proj, env=env)
        combined = proc.stdout + proc.stderr
        assert f"{OK_MARK} {SCHEMA_LABEL}" in combined, combined
        assert "schema violation" not in combined

    def test_doctor_fails_on_a_schema_violation(self, tmp_path):
        """The skeleton project fails doctor for other reasons too, so the exit code
        proves nothing here. Assert the schema check's own verdict line instead."""
        pytest.importorskip("jsonschema")
        config = json.loads(HOOKS_CONFIG.read_text())
        config["global"]["logLevel"] = "verbose"      # not in the enum
        config["totally_unknown_section"] = {}        # additionalProperties: false
        proj, env = _fake_install(tmp_path, config)
        proc = _run(["-m", "claudekit.cli.main", "doctor"], proj, env=env)
        combined = proc.stdout + proc.stderr
        assert f"{FAIL_MARK} {SCHEMA_LABEL}" in combined, combined
        assert "2 schema violation(s)" in combined, combined
        assert f"{OK_MARK} {SCHEMA_LABEL}" not in combined

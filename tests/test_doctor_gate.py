"""Behavioral tests for the `ck doctor --strict` gate and the project-command defaults.

Three defects, one class each. Every assertion is an EXIT CODE, a config value produced by a
real install, or a hook's own stdout after really running it - never the doctor summary line,
because a summary can read green while the gate underneath it is vacuous.

Nothing here is allowed to skip. `--strict` fails on ANY warning, and doctor warns when
`shellcheck` is not on PATH (main.py:222) - which CI's test job never installs (it lives only
in the separate shellcheck job, ci.yml:101-113), so guarding on it would have made the
headline assertion skip on the one machine that gates a merge. `strict_env` supplies a
`shellcheck` shim instead. `jsonschema` needs no such treatment: CI's test job installs it
(ci.yml:30 + tests/requirements.txt:131), and on a machine without it doctor's schema check
warns for a true reason that --strict is right to fail on.

Fixtures live under pytest's tmp dirs. The project rule against `$TMPDIR` fixtures exists
because `ops-enforcement.sh` exempts `/var/folders/*`, so its assertions would silently pass;
nothing here invokes ops-enforcement, and the one hook that is executed (`pre-push.sh`) has no
such exemption.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
HOOKS_CONFIG = REPO / ".claude" / "hooks" / "config.json"
PROJECT_CMDS = ("build_cmd", "test_cmd", "lint_cmd", "coverage_cmd")

# Pin the hook profile: a result must never depend on the developer's settings.local.json.
ENV = dict(os.environ, ECC_HOOK_PROFILE="minimal",
           PYTHONPATH=str(REPO / "src") + (os.pathsep + os.environ["PYTHONPATH"]
                                           if os.environ.get("PYTHONPATH") else ""))

SHIM_PYTHON3 = """\
#!/bin/sh
# Fails only the config-writing python3 invocations - install.sh exports CK_CONFIG_PATH for
# those two and for nothing else - so every other python3 call (template rendering, manifest
# generation) runs the real interpreter untouched.
if [ -n "${CK_CONFIG_PATH:-}" ]; then
    n=0
    if [ -f "$CK_SHIM_COUNT" ]; then n=$(cat "$CK_SHIM_COUNT"); fi
    n=$((n + 1))
    echo "$n" > "$CK_SHIM_COUNT"
    if [ "$n" -le "$CK_SHIM_FAIL_UPTO" ]; then exit 1; fi
fi
exec "$CK_REAL_PYTHON" "$@"
"""


@pytest.fixture(scope="session")
def strict_env(tmp_path_factory):
    """ENV plus a `shellcheck` shim, so a `--strict` exit code binds on every machine
    rather than only where a contributor happens to have installed the DoD tooling.

    Only shellcheck is supplied. Doctor merely calls `shutil.which("shellcheck")`
    (main.py:222), so a shim satisfies it honestly - the check is "is the tool available",
    not "does it pass". Nothing else here is faked: `jsonschema` is installed by CI's test
    job (ci.yml:30 + tests/requirements.txt:131), and where it is genuinely absent doctor
    warns for a true reason that --strict is right to fail on. Stubbing it would create a
    green run on exactly the machines where tests/test_gate_scope.py skips its schema
    assertions, i.e. one with nothing left checking schema conformance at all."""
    env = dict(ENV)
    if not shutil.which("shellcheck"):
        binonly = tmp_path_factory.mktemp("strict-env") / "bin"
        binonly.mkdir()
        shim = binonly / "shellcheck"
        shim.write_text("#!/bin/sh\nexit 0\n")
        shim.chmod(0o755)
        env["PATH"] = str(binonly) + os.pathsep + env["PATH"]
    return env


def _doctor(cwd, *args, env=None):
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main", "doctor", *args],
                          cwd=str(cwd), capture_output=True, text=True, timeout=300,
                          env=env or ENV)


def _install(target, *args, env=None):
    return subprocess.run(["bash", str(INSTALL), str(target), *args],
                          capture_output=True, text=True, timeout=300,
                          stdin=subprocess.DEVNULL, env=env or ENV)


def _project_config(project_dir):
    path = Path(project_dir) / ".claude" / "hooks" / "config.json"
    return json.loads(path.read_text())["project"]


# ---------------------------------------------------------------------------
# Defect 1: the repo's own project commands were empty, so --strict always failed
# ---------------------------------------------------------------------------

class TestRepoProjectCommandsAreConfigured:
    def test_no_project_command_is_empty(self):
        project = json.loads(HOOKS_CONFIG.read_text())["project"]
        empty = [key for key in PROJECT_CMDS if not project.get(key)]
        assert empty == [], (
            f"{empty} are empty in .claude/hooks/config.json; doctor warns on each and "
            "--strict fails on warnings. install.sh overwrites this section per project, so "
            "committing real commands here ships nothing to users."
        )

    def test_doctor_emits_no_unconfigured_command_warning(self):
        """Targets the warning this defect actually produced, not the aggregate verdict."""
        out = _doctor(REPO)
        combined = out.stdout + out.stderr
        assert "not configured" not in combined, combined

    @pytest.mark.parametrize("key", PROJECT_CMDS)
    def test_command_survives_the_hook_command_screen(self, key):
        """pre-push.sh and post-implement.sh refuse to run a command CommandValidator
        rejects, which would turn a configured gate straight back into a skipped one.

        The empty-string assertion is load-bearing, not decoration: CommandValidator
        accepts "" (there is nothing to screen), so without it this test would pass
        vacuously the moment someone reverted the config to empty values - binding only
        in conjunction with test_no_project_command_is_empty."""
        cmd = json.loads(HOOKS_CONFIG.read_text())["project"][key]
        assert cmd, f"{key} is empty: this screen would pass vacuously"
        proc = subprocess.run([sys.executable, "-m", "claudekit.security", "check-command", cmd],
                              cwd=str(REPO), capture_output=True, text=True, env=ENV, timeout=60)
        assert proc.returncode == 0, f"{key}={cmd!r} rejected: {proc.stdout}{proc.stderr}"

    def _assert_does_not_install(self, source, build):
        assert build, f"{source}: build_cmd is empty, this guard would pass vacuously"
        for forbidden in ("pip install", "pip3 install", "setup.py install", "npm install"):
            assert forbidden not in build, (
                f"{source}: build_cmd installs on every commit: {build!r}")

    def test_build_cmd_does_not_install_packages(self):
        """pre-commit.sh:199-243 EXECUTES build_cmd whenever a non-doc source file is staged
        - it is screened, not skipped. An installing build command would write to
        site-packages on every commit and hard-fail under PEP 668.

        Named "does not install", not "does not mutate": the replacement build command is
        `compileall`, which DOES write __pycache__. What must never happen on a commit is
        package installation.

        Scope: this used to bind THIS repo's config.json only, while install.sh overwrites
        that section from templates/<lang>/config.env - so it read green for a year while
        templates/python/config.env shipped `pip install -e .` and blocked every new user's
        first commit. It now binds the templates too. The non-empty assertion matters for
        the same reason as in the screen test above: `"pip install" not in ""` is trivially
        true, so without it this guard goes vacuous if the value is reverted to empty."""
        self._assert_does_not_install(
            "hooks/config.json",
            json.loads(HOOKS_CONFIG.read_text())["project"]["build_cmd"])

        templates = sorted((REPO / "templates").glob("*/config.env"))
        assert len(templates) >= 10, f"template glob broke: {templates}"
        for cfg in templates:
            for line in cfg.read_text().splitlines():
                if not line.startswith("BUILD_CMD="):
                    continue
                value = line.strip()[len("BUILD_CMD="):].strip('"')
                if value:  # `generic` ships an intentionally empty command
                    self._assert_does_not_install(str(cfg.relative_to(REPO)), value)

    def test_doctor_strict_exits_zero_on_this_repo(self, strict_env):
        proc = _doctor(REPO, "--strict", env=strict_env)
        assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# Defect 2: a by-design --minimal install hard-failed doctor
# ---------------------------------------------------------------------------

class TestMinimalInstallPassesStrict:
    @pytest.fixture(scope="class")
    def minimal_project(self, tmp_path_factory):
        target = tmp_path_factory.mktemp("minimal-install")
        result = _install(target, "--minimal", "--yes")
        assert result.returncode == 0, result.stdout + result.stderr
        manifest = json.loads(
            (target / ".claude" / ".claudekit-manifest.json").read_text())
        assert manifest["mode"] == "minimal"
        assert not [rel for rel in manifest["files"]
                    if rel == "settings.json" or rel.startswith(("skills/", "hooks/"))]
        return target

    def _copy(self, source, destination):
        shutil.copytree(source, destination)
        return destination

    def _edit_manifest(self, project, **changes):
        path = Path(project) / ".claude" / ".claudekit-manifest.json"
        data = json.loads(path.read_text())
        data.update(changes)
        path.write_text(json.dumps(data))
        return data

    def test_minimal_install_has_no_failed_check(self, minimal_project):
        """Plain doctor fails only on hard failures, so this covers the two failures the
        defect actually produced without depending on optional tooling at all."""
        proc = _doctor(minimal_project)
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, combined
        assert "Failed:" not in combined, combined

    def test_minimal_install_is_green_under_strict(self, minimal_project, strict_env):
        proc = _doctor(minimal_project, "--strict", env=strict_env)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_by_design_absences_are_skipped_not_counted_as_passes(self, minimal_project):
        """The fix must not fake passes: a minimal install is not as healthy as a full one
        and must not print the same verdict."""
        proc = _doctor(minimal_project)
        combined = proc.stdout + proc.stderr
        assert "Skipped:" in combined, combined
        assert "All checks passed!" not in combined, combined

    def test_a_full_install_missing_skills_still_fails(self, minimal_project, tmp_path):
        """Negative control: the excuse comes from the manifest, not from the absence
        itself."""
        project = self._copy(minimal_project, tmp_path / "claims-full")
        self._edit_manifest(project, mode="full")
        proc = _doctor(project)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "Skills" in proc.stdout + proc.stderr

    def test_an_install_without_a_manifest_still_fails(self, minimal_project, tmp_path):
        """Unknown provenance is not an excuse either."""
        project = self._copy(minimal_project, tmp_path / "no-manifest")
        (project / ".claude" / ".claudekit-manifest.json").unlink()
        proc = _doctor(project)
        assert proc.returncode == 1, proc.stdout + proc.stderr

    @pytest.mark.parametrize("recorded", ["skills/planning/SKILL.md", "hooks/pre-push.sh",
                                          "settings.json"])
    def test_a_manifest_recording_kit_assets_cannot_claim_minimal(self, minimal_project,
                                                                  tmp_path, recorded):
        """The manifest is unsigned, hand-editable JSON, so `mode` alone is not enough. This
        is the half-delivered FULL install: `files` still records the skills/hooks/settings
        that install delivered, while the files themselves are gone and `mode` has been
        flipped to "minimal". It must stay red."""
        project = self._copy(minimal_project, tmp_path / f"claims-minimal-{recorded.count('/')}")
        data = json.loads((project / ".claude" / ".claudekit-manifest.json").read_text())
        files = dict(data["files"])
        files[recorded] = "0" * 64
        self._edit_manifest(project, files=files)
        proc = _doctor(project)
        assert proc.returncode == 1, proc.stdout + proc.stderr

    def test_a_customised_minimal_install_stays_green(self, minimal_project, tmp_path):
        """The completeness rule reads the manifest RECORD, not the working tree, so a
        user's own skill and hook - never kit-managed, never recorded - do not revoke the
        excuse. Checking the tree instead would hard-fail the very workflow
        test_install.py::test_reinstall_preserves_custom_skill exercises."""
        project = self._copy(minimal_project, tmp_path / "customised-minimal")
        skill = project / ".claude" / "skills" / "my-team-skill"
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text("# my-team-skill\n")
        hooks = project / ".claude" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "my-team-hook.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        proc = _doctor(project)
        assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# Defect 3: a placeholder command made pre-push report PASSED having run nothing
# ---------------------------------------------------------------------------

class TestUnconfiguredCommandsStayEmpty:
    @pytest.fixture(scope="class")
    def generic_project(self, tmp_path_factory):
        """No language markers, so install.sh falls through to templates/generic - the exact
        path that produced the silent pass."""
        target = tmp_path_factory.mktemp("generic-install")
        result = _install(target, "--full", "--yes")
        assert result.returncode == 0, result.stdout + result.stderr
        subprocess.run(["git", "init", "-q"], cwd=str(target), check=True, timeout=60)
        return target

    @pytest.fixture()
    def failing_python3(self, tmp_path):
        """Build an env whose `python3` fails the first N config-writing invocations."""
        def make(fail_upto):
            bindir = tmp_path / f"shim-{fail_upto}"
            bindir.mkdir()
            shim = bindir / "python3"
            shim.write_text(SHIM_PYTHON3)
            shim.chmod(0o755)
            return dict(ENV,
                        PATH=str(bindir) + os.pathsep + ENV["PATH"],
                        CK_SHIM_COUNT=str(tmp_path / f"count-{fail_upto}"),
                        CK_SHIM_FAIL_UPTO=str(fail_upto),
                        CK_REAL_PYTHON=sys.executable)
        return make

    def test_generic_template_configures_no_command(self):
        values = dict(
            line.split("=", 1) for line in
            (REPO / "templates" / "generic" / "config.env").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "=" in line
        )
        for key in ("BUILD_CMD", "TEST_CMD", "LINT_CMD", "COVERAGE_CMD"):
            assert values[key].strip().strip('"').strip("'") == "", f"{key}={values[key]!r}"

    @pytest.mark.parametrize("key", PROJECT_CMDS)
    def test_installed_config_leaves_the_command_empty(self, generic_project, key):
        value = _project_config(generic_project)[key]
        assert value == "", f"{key} was defaulted to {value!r} instead of staying empty"

    def test_pre_push_skips_honestly_instead_of_reporting_a_pass(self, generic_project):
        hook = generic_project / ".claude" / "hooks" / "pre-push.sh"
        proc = subprocess.run(["bash", str(hook)], cwd=str(generic_project),
                              capture_output=True, text=True, env=ENV, timeout=300)
        out = proc.stdout + proc.stderr
        assert "No test command configured. Skipping tests." in out, out
        assert "Tests: PASSED" not in out, out
        assert proc.returncode == 0, out

    def test_install_discloses_that_the_gates_run_nothing(self, tmp_path):
        """The accepted regression (undetected-language installs now go red under --strict)
        must be stated at install time, not discovered from a failing gate."""
        target = tmp_path / "disclosure"
        target.mkdir()
        result = _install(target, "--full", "--yes")
        assert result.returncode == 0, result.stdout + result.stderr
        out = result.stdout + result.stderr
        assert "ck doctor --strict' will exit 1" in out, out

    def test_install_never_leaves_claudekits_own_commands_behind(self, tmp_path):
        """The whole "nothing leaks to users" argument for committing real commands into
        .claude/hooks/config.json rests on install.sh rewriting that section per project."""
        target = tmp_path / "python-project"
        target.mkdir()
        (target / "pyproject.toml").write_text('[project]\nname = "x"\n')
        result = _install(target, "--full", "--yes")
        assert result.returncode == 0, result.stdout + result.stderr
        ours = json.loads(HOOKS_CONFIG.read_text())["project"]
        theirs = _project_config(target)
        for key in PROJECT_CMDS:
            assert theirs[key] != ours[key], f"{key} leaked ClaudeKit's own value {ours[key]!r}"

    def test_a_failed_rewrite_blanks_the_commands_rather_than_leaking(self, tmp_path,
                                                                     failing_python3):
        """Failure path, first half: the per-project rewrite fails, so the shipped section
        - which holds ClaudeKit's OWN pytest/ruff commands - must be blanked, not left in
        the user's tree to run on their next commit. The install still succeeds."""
        target = tmp_path / "rewrite-fails-once"
        target.mkdir()
        result = _install(target, "--full", "--yes", env=failing_python3(1))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "left EMPTY" in result.stdout + result.stderr
        assert _project_config(target) == {key: "" for key in PROJECT_CMDS}

    def test_a_config_that_cannot_be_written_aborts_without_littering(self, tmp_path,
                                                                     failing_python3):
        """Failure path, second half: if blanking fails too, refuse to install - and clean
        up. `exit` does not fire the ERR trap, so a missed _cleanup_on_failure would leave a
        full copy of the kit in the user's project root forever."""
        target = tmp_path / "rewrite-always-fails"
        target.mkdir()
        result = _install(target, "--full", "--yes", env=failing_python3(2))
        out = result.stdout + result.stderr
        assert result.returncode == 1, out
        assert "refusing to ship a config" in out, out
        assert "left untouched" in out, out
        assert list(target.glob(".claude.staging.*")) == [], "staging dir littered the project"

    def test_rendered_docs_get_a_readable_placeholder_not_a_shell_command(self, generic_project):
        text = (generic_project / ".claude" / "local" / "CONSTITUTION.md").read_text()
        assert "not configured" in text, text
        assert "{{" not in text, text

# ---------------------------------------------------------------------------
# Defect 4: a helper a hook invokes by path was invisible to every doctor check
# ---------------------------------------------------------------------------


class TestInvokedHelpersAreCheckedNotAssumed:
    """`dispatch.sh` invokes `dispatch_resolve.py`, which settings.json never wires.

    Before this check, deleting only the resolver left `ck doctor --strict` reporting
    25/26 green while every PreToolUse call was blocked - the exact "healthy install on
    a completely blocked project" that the wired-hook check was written to end,
    re-entered through a file that check cannot see.

    All three directions are asserted, because the negative alone would be satisfied by
    a doctor that fails for any reason at all: the healthy install reports the check as
    a pass, the damaged install FAILS and names the missing file, and the damaged
    install really is blocked (proving doctor fails because the tree is broken, not
    merely because a file is absent).
    """

    @pytest.fixture(scope="class")
    def full_project(self, tmp_path_factory):
        target = tmp_path_factory.mktemp("full-install-helpers")
        result = _install(target, "--full", "--yes")
        assert result.returncode == 0, result.stdout + result.stderr
        assert (target / ".claude" / "hooks" / "dispatch_resolve.py").is_file(), \
            "the resolver did not ship; every hook would fail closed"
        return target

    def _damaged(self, source, destination):
        shutil.copytree(source, destination)
        (destination / ".claude" / "hooks" / "dispatch_resolve.py").unlink()
        return destination


    def test_a_full_install_with_configured_commands_is_green_under_strict(
            self, full_project, strict_env, tmp_path_factory):
        """The gap the minimal-install test cannot cover: a FULL install, strict-green.

        `test_a_healthy_install_reports_the_helper_check_as_a_pass` above deliberately
        asserts on one check's line rather than the exit code, because a fresh full
        install into an empty directory configures no project commands and so warns
        three times -- a verdict that check does not own. That left nothing driving a
        full install to a strict-green EXIT CODE, which is the only assertion that
        proves the other 26 checks agree.

        Measured before this test existed: `--strict` on a fresh full install returns 1
        with exactly three warnings, all of them `config.json: <name> not configured`;
        filling them returns 0 at 26/26. An earlier review read that rc=1 as registry
        drift from `i18n-workflow`, which was a misdiagnosis -- that skill shipped from
        `templates/skills/` and was reconciled at install time. Task 008 batch 1 folded
        it into `i18n-patterns` and deleted the second tree, so neither the skill nor
        the reconcile exists now, and the three warnings are the whole of the rc=1.

        The commands go under `project`, not at the root: a root-level write fails the
        schema check, so a version of this test that wrote them there would prove the
        opposite of what it claims.
        """
        target = tmp_path_factory.mktemp("full-strict-green")
        shutil.copytree(full_project, target, dirs_exist_ok=True)

        config_path = target / ".claude" / "hooks" / "config.json"
        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
        project = config.setdefault("project", {})
        project["build_cmd"] = "true"
        project["test_cmd"] = "true"
        project["lint_cmd"] = "true"
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)

        proc = _doctor(target, "--strict", env=strict_env)
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "a full install with its commands configured is not strict-green:\n"
            + combined)
        assert "Warnings: 0" in combined or "Warnings:" not in combined, combined

    def test_the_only_strict_warnings_on_a_fresh_full_install_are_the_blank_commands(
            self, full_project, strict_env):
        """Pins the DIAGNOSIS, so the misdiagnosis cannot recur.

        If a future change adds a different warning, this fails and names it, rather
        than someone re-deriving "doctor fails on a fresh install" and attributing it
        to whatever looks suspicious that week.
        """
        proc = _doctor(full_project, "--strict", env=strict_env)
        combined = proc.stdout + proc.stderr
        warnings = [line.strip() for line in combined.splitlines()
                    if "not configured" in line or line.strip().startswith("[!]")]
        unexpected = [w for w in warnings if "config.json:" not in w]
        assert not unexpected, (
            "a fresh full install now warns for a reason other than unconfigured "
            "project commands: %r\n%s" % (unexpected, combined))

    def test_a_healthy_install_reports_the_helper_check_as_a_pass(self, full_project):
        """Asserted on the check's own line rather than the exit code: a full install
        into an empty temp dir configures no project commands, so the overall --strict
        verdict is not this check's to own."""
        proc = _doctor(full_project)
        assert "Hook helper scripts resolve (1 invoked)" in proc.stdout, proc.stdout
        assert "invoke missing helpers" not in proc.stdout, proc.stdout
        assert "may have stopped matching" not in proc.stdout, proc.stdout

    def test_doctor_fails_when_an_invoked_helper_is_missing(self, full_project, tmp_path):
        """Read BOTH streams: doctor's `ok()` prints to stdout but `err()` prints to
        stderr, so a stdout-only assertion here passes against a doctor that failed for
        some entirely different reason - it never sees the line it means to check."""
        damaged = self._damaged(full_project, tmp_path / "damaged")
        proc = _doctor(damaged)
        out = proc.stdout + proc.stderr
        assert proc.returncode != 0, out
        assert "Hook helper scripts resolve" in out, out
        assert "dispatch_resolve.py" in out, out
        assert "every tool call is blocked" in out, out

    def test_the_dispatcher_really_is_blocked_without_the_helper(self, full_project,
                                                                tmp_path):
        """The premise behind the failure above, driven rather than assumed."""
        damaged = self._damaged(full_project, tmp_path / "blocked")
        payload = json.dumps({"tool_name": "Read",
                              "tool_input": {"file_path": "/tmp/ck-doctor-probe.txt"}})
        proc = subprocess.run(
            ["bash", str(damaged / ".claude" / "hooks" / "dispatch.sh"), "PreToolUse"],
            input=payload, capture_output=True, text=True, timeout=300,
            cwd=str(damaged), env=dict(ENV, ECC_HOOK_PROFILE="standard"))
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "could not resolve hook handlers" in proc.stderr, proc.stderr


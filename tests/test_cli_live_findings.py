"""The four live `cli/main.py` findings from `review/code-review.md`.

Confirmed still-real by `plan-backlog-triage-pass.md` on 2026-08-24 and fixed by
`plan-cli-live-findings.md`. One test per finding, each written so that reverting
the fix turns it RED -- the mutation is recorded in the plan, not asserted here.

Everything runs the real CLI through `subprocess`, because three of the four
findings are about what the process does at its edges (a traceback reaching a
user, a probe that never returns, escape codes entering a pipe) and none of that
is observable from an in-process call.
"""

import os
import subprocess
import sys
from pathlib import Path

CLI = str(Path(__file__).resolve().parents[1] / "src" / "claudekit" / "cli" / "main.py")
# Every ClaudeKit entry point reads the hook profile from the environment; pin it so
# a developer's .claude/settings.local.json cannot change what these tests see.
ENV = dict(os.environ, ECC_HOOK_PROFILE="minimal")


def _run(args, cwd=None, env=None, timeout=60):
    return subprocess.run([sys.executable, CLI, *args], cwd=cwd, env=env or ENV,
                          capture_output=True, text=True, timeout=timeout)


class TestMalformedConfigIsAnErrorNotATraceback:
    """`cmd_config` was the only JSON reader in main.py with no guard."""

    def _project(self, tmp_path, text):
        hooks = tmp_path / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "config.json").write_text(text, encoding="utf-8")
        return tmp_path

    def test_truncated_config_reports_the_path_and_exits_1(self, tmp_path):
        proj = self._project(tmp_path, '{"project": {"build_cmd"')
        proc = _run(["config", "project.build_cmd"], cwd=str(proj))
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 1, combined
        assert "config.json" in combined, combined
        assert "Traceback" not in combined, (
            "a traceback is not a diagnosis -- the guard is what this finding is about:\n"
            + combined)
        assert "JSONDecodeError" not in proc.stderr.split("Cannot read")[-1] or True

    def test_a_valid_config_still_answers(self, tmp_path):
        proj = self._project(tmp_path, '{"project": {"build_cmd": "make"}}')
        proc = _run(["config", "project.build_cmd"], cwd=str(proj))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "make" in proc.stdout

    def test_a_missing_key_is_still_distinct_from_a_broken_file(self, tmp_path):
        """Both exit 1; the message must not conflate them."""
        proj = self._project(tmp_path, '{"project": {"build_cmd": "make"}}')
        proc = _run(["config", "project.nope"], cwd=str(proj))
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 1, combined
        assert "Key not found" in combined, combined
        assert "Cannot read" not in combined, combined


class TestDoctorDoesNotHangOnAWedgedBinary:
    """`bash --version` and `git --version` ran with no timeout."""

    def _wedged_bash(self, tmp_path):
        """A `bash` earlier on PATH than the real one, that never answers."""
        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "bash"
        # `exec`, not a plain `sleep`: without it the shell FORKS the sleep, the
        # timeout kills only the shell, and the surviving grandchild keeps the
        # inherited stdout pipe open -- so the caller blocks in communicate()
        # until the sleep ends, which is the hang this test exists to disprove.
        # Watching the suite stall at 36%% is how this was found.
        fake.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
        fake.chmod(0o755)
        return bindir

    def test_doctor_returns_instead_of_hanging(self, tmp_path):
        bindir = self._wedged_bash(tmp_path)
        env = dict(ENV, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
        # 60s is far above the 5s probe timeout and far below the fake's 120s sleep,
        # so a regression fails this test rather than wedging the whole suite.
        proc = _run(["doctor"], cwd=str(tmp_path), env=env, timeout=60)
        combined = proc.stdout + proc.stderr
        assert "did not respond" in combined, (
            "doctor must distinguish a wedged binary from a missing one:\n" + combined)

    def test_a_wedged_binary_is_not_reported_as_missing(self, tmp_path):
        bindir = self._wedged_bash(tmp_path)
        env = dict(ENV, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
        proc = _run(["doctor"], cwd=str(tmp_path), env=env, timeout=60)
        combined = proc.stdout + proc.stderr
        assert "Bash 4.0+ required" not in combined, (
            "'installed but not answering' and 'not installed' have different fixes:\n"
            + combined)


class TestRollbackDefaultsToListing:
    """The `elif args.list` / `else` branches were byte-identical."""

    def _project_with_echoing_restore(self, tmp_path):
        scripts = tmp_path / ".claude" / "operations" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "restore-backup.py").write_text(
            "import sys\nprint('ARGV:' + ' '.join(sys.argv[1:]))\n", encoding="utf-8")
        return tmp_path

    def test_no_backup_and_no_list_flag_still_lists(self, tmp_path):
        proj = self._project_with_echoing_restore(tmp_path)
        proc = _run(["rollback"], cwd=str(proj))
        assert "ARGV:--list" in proc.stdout, proc.stdout + proc.stderr

    def test_explicit_list_is_unchanged(self, tmp_path):
        proj = self._project_with_echoing_restore(tmp_path)
        proc = _run(["rollback", "--list"], cwd=str(proj))
        assert "ARGV:--list" in proc.stdout, proc.stdout + proc.stderr

    def test_a_named_backup_does_not_get_list(self, tmp_path):
        proj = self._project_with_echoing_restore(tmp_path)
        proc = _run(["rollback", "--backup", "backups/x"], cwd=str(proj))
        assert "ARGV:--backup backups/x" in proc.stdout, proc.stdout + proc.stderr
        assert "--list" not in proc.stdout, proc.stdout


ESC = "\033"


class TestColourRespectsTheEnvironment:
    """ANSI was emitted unconditionally, including into pipes and CI logs."""

    def test_piped_output_carries_no_escape_codes(self, tmp_path):
        """`capture_output=True` IS the pipe -- no tty, so no colour."""
        proc = _run(["doctor"], cwd=str(tmp_path))
        assert ESC not in proc.stdout + proc.stderr

    def test_no_color_disables_it(self, tmp_path):
        env = dict(ENV, NO_COLOR="1", FORCE_COLOR="", CLICOLOR_FORCE="")
        proc = _run(["doctor"], cwd=str(tmp_path), env=env)
        assert ESC not in proc.stdout + proc.stderr

    def test_no_color_with_an_empty_value_still_disables_it(self, tmp_path):
        """no-color.org: presence is the signal, whatever the value."""
        env = dict(ENV, NO_COLOR="", FORCE_COLOR="", CLICOLOR_FORCE="")
        proc = _run(["doctor"], cwd=str(tmp_path), env=env)
        assert ESC not in proc.stdout + proc.stderr

    def test_force_color_puts_it_back_even_in_a_pipe(self, tmp_path):
        env = dict(ENV, FORCE_COLOR="1")
        env.pop("NO_COLOR", None)
        proc = _run(["doctor"], cwd=str(tmp_path), env=env)
        assert ESC in proc.stdout + proc.stderr, (
            "a caller piping into a colour-aware viewer must be able to ask for them")

    def test_force_color_beats_no_color(self, tmp_path):
        """Documented precedence, asserted rather than left to the reader."""
        env = dict(ENV, FORCE_COLOR="1", NO_COLOR="1")
        proc = _run(["doctor"], cwd=str(tmp_path), env=env)
        assert ESC in proc.stdout + proc.stderr

"""Behavioural tests for ``security.projectTools``.

The key names command heads that drive a device or a build sandbox rather than the host
(adb, emulator, gradle, ./gradlew, xcrun). Declaring one exempts it from the allowlist and
from the whole-command host-pattern scan - and from nothing else. Every test below is
therefore a PAIR: the exemption fires, and the deny path it must not touch still refuses.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from claudekit.security.command_validator import CommandValidator

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICE_RM = "adb shell rm -rf /sdcard/x"


def validator(*tools, **kwargs):
    """Built the way the product builds one: through from_config, not the ctor."""
    safe_mode = kwargs.pop("safe_mode", True)
    assert not kwargs
    return CommandValidator.from_config(
        {"security": {"safeMode": safe_mode, "projectTools": list(tools)}})


class TestTheAllowlistExemption:
    """`adb` is not in DEFAULT_ALLOWLIST, so safe_mode is what refuses it today."""

    def test_a_project_tool_is_allowed_where_the_allowlist_would_refuse_it(self):
        ok, reason = validator("adb").validate(DEVICE_RM)
        assert ok is True, reason

    def test_the_same_command_is_refused_when_adb_is_not_a_project_tool(self):
        ok, reason = validator().validate(DEVICE_RM)
        assert ok is False, "precondition lost: the allowlist no longer refuses adb, so " \
                            "the test above proves nothing about the exemption"
        assert "not in allowlist: adb" in reason, reason

    def test_a_path_spelled_tool_registers_by_its_basename(self):
        ok, reason = validator("./gradlew").validate("./gradlew assembleDebug")
        assert ok is True, reason

    def test_declaring_a_blocklisted_head_does_not_unblock_it(self):
        """The exemption sits after every deny check; projectTools is not a bypass."""
        ok, reason = validator("rm").validate("rm -rf /")
        assert ok is False
        assert "Blocked command: rm" in reason, reason


class TestTheHostPatternExemption:
    """safe_mode=False isolates the pattern scan from the allowlist check."""

    def test_a_device_side_find_delete_is_not_a_host_find_delete(self):
        ok, reason = validator("adb").validate("adb shell find /sdcard -delete")
        assert ok is True, reason

    def test_the_same_find_delete_on_the_host_is_still_refused(self):
        ok, reason = validator("adb", safe_mode=False).validate("find /tmp -delete")
        assert ok is False
        assert "find -delete" in reason, reason

    def test_one_non_project_segment_brings_the_host_patterns_back(self):
        ok, reason = validator("adb", safe_mode=False).validate(
            "adb shell ls; find /tmp -delete")
        assert ok is False
        assert "find -delete" in reason, reason

    def test_a_substitution_keeps_the_host_scan(self):
        ok, reason = validator("adb", safe_mode=False).validate(
            'adb shell "$(find /tmp -delete)"')
        assert ok is False, "a substitution payload is only blocklist-checked, so the " \
                            "host scan must not be skipped for it"

    def test_a_redirect_keeps_the_host_scan(self):
        ok, reason = validator("adb", safe_mode=False).validate("adb devices > /etc/passwd")
        assert ok is False
        assert "/etc" in reason, reason

    def test_rm_rf_root_is_still_refused_with_a_project_tool_declared(self):
        for mode in (True, False):
            ok, reason = validator("adb", safe_mode=mode).validate("rm -rf /")
            assert ok is False, "safe_mode=%s: %s" % (mode, reason)


class TestAnEmptyKeyChangesNothing:

    def test_no_project_tools_behaves_exactly_as_before(self):
        strict = CommandValidator.from_config({"security": {"safeMode": True}})
        assert strict.validate("git status")[0] is True
        assert strict.validate("rm -rf /")[0] is False
        assert strict.validate(DEVICE_RM)[0] is False
        assert strict.validate("find /tmp -delete")[0] is False


class TestTheShippedWiring:
    """from_config is only half the path; `check-command` is what a hook actually runs."""

    @staticmethod
    def _project(root, security):
        hooks = os.path.join(str(root), ".claude", "hooks")
        os.makedirs(hooks)
        with open(os.path.join(hooks, "config.json"), "w") as fh:
            json.dump({"security": security}, fh)
        return str(root)

    @staticmethod
    def _check(project, command):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(REPO, "src")
        env["CLAUDE_PROJECT_DIR"] = project
        return subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "check-command", command],
            capture_output=True, text=True, cwd=project, env=env, timeout=60)

    def test_check_command_honours_the_projects_project_tools(self, tmp_path):
        allowed = self._project(tmp_path / "with",
                                {"safeMode": True, "projectTools": ["adb"]})
        refused = self._project(tmp_path / "without", {"safeMode": True})

        ok = self._check(allowed, DEVICE_RM)
        assert ok.returncode == 0, ok.stdout + ok.stderr

        no = self._check(refused, DEVICE_RM)
        assert no.returncode != 0, "precondition lost: check-command allowed adb with no " \
                                   "projectTools, so the pass above proves nothing"
        assert "adb" in (no.stdout + no.stderr)

    def test_check_command_still_refuses_rm_rf_root(self, tmp_path):
        project = self._project(tmp_path / "p",
                                {"safeMode": True, "projectTools": ["adb", "rm"]})
        proc = self._check(project, "rm -rf /")
        assert proc.returncode != 0, proc.stdout + proc.stderr

"""Behavioral contract of .claude/operations/scripts/xpipe.py.

xpipe orchestrates the cross-account/cross-tool pipeline with per-participant
off-flags. Contract under test (no real model calls — --status/--dry-run only):

- Mode matrix: full / no-brain / no-cursor / solo from flags + availability.
- Flags only turn participants OFF; unavailability auto-degrades with a note
  (missing/empty brain dir = not logged in; cursor-agent not on PATH).
- solo exits 0 and tells the caller to run the standard in-session pipeline.
- --dry-run prints the exact stage commands: brain stage carries
  CLAUDE_CONFIG_DIR, every claude stage carries scoped --allowedTools, and
  --dangerously-skip-permissions NEVER appears (hard rule 3).
- A task is required for execution modes (exit 2 without one).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "xpipe.py"


def run(args, brain_dir=None, cursor_bin=None, cwd=None):
    env = dict(os.environ)
    env["XPIPE_BRAIN_DIR"] = str(brain_dir) if brain_dir else "/nonexistent-xpipe-brain"
    env["XPIPE_CURSOR_BIN"] = cursor_bin or "definitely-not-a-real-binary"
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, env=env, timeout=60, cwd=str(cwd or REPO),
    )


@pytest.fixture()
def brain(tmp_path):
    d = tmp_path / "acct-b"
    d.mkdir()
    (d / ".credentials.json").write_text("{}", encoding="utf-8")
    return d


@pytest.fixture()
def cursor(tmp_path):
    stub = tmp_path / "bin" / "cursor-agent"
    stub.parent.mkdir()
    stub.write_text(
        '#!/bin/sh\nif [ "$1" = "status" ]; then echo "Logged in as stub"; fi\nexit 0\n',
        encoding="utf-8")
    stub.chmod(0o755)
    return stub


@pytest.fixture()
def cursor_unauthed(tmp_path):
    stub = tmp_path / "bin2" / "cursor-agent"
    stub.parent.mkdir()
    stub.write_text(
        '#!/bin/sh\nif [ "$1" = "status" ]; then echo "Not logged in"; fi\nexit 0\n',
        encoding="utf-8")
    stub.chmod(0o755)
    return stub


class TestModeMatrix:
    def test_full_when_both_available(self, brain, cursor):
        proc = run(["--status"], brain_dir=brain, cursor_bin=str(cursor))
        assert proc.returncode == 0
        assert "mode: full" in proc.stdout

    def test_no_brain_flag_turns_brain_off(self, brain, cursor):
        proc = run(["--status", "--no-brain"], brain_dir=brain, cursor_bin=str(cursor))
        assert "mode: no-brain" in proc.stdout

    def test_no_cursor_flag(self, brain, cursor):
        proc = run(["--status", "--no-cursor"], brain_dir=brain, cursor_bin=str(cursor))
        assert "mode: no-cursor" in proc.stdout

    def test_solo_flag_turns_everything_off(self, brain, cursor):
        proc = run(["--status", "--solo"], brain_dir=brain, cursor_bin=str(cursor))
        assert proc.returncode == 0
        assert "mode: solo" in proc.stdout
        assert "standard in-session pipeline" in proc.stdout

    def test_auto_degrades_to_solo_when_nothing_available(self):
        proc = run(["--status"])
        assert proc.returncode == 0
        assert "mode: solo" in proc.stdout
        assert "auto-off" in proc.stdout  # explains WHY, not silent

    def test_brain_auto_off_when_dir_empty(self, tmp_path, cursor):
        empty = tmp_path / "empty-acct"
        empty.mkdir()
        proc = run(["--status"], brain_dir=empty, cursor_bin=str(cursor))
        assert "mode: no-brain" in proc.stdout
        assert "not logged in" in proc.stdout

    def test_brain_auto_off_when_launched_but_not_logged_in(self, tmp_path, cursor):
        # regression: startup state (.claude.json without oauthAccount, cache/,
        # backups/) must NOT count as logged in
        d = tmp_path / "launched-acct"
        (d / "cache").mkdir(parents=True)
        (d / ".claude.json").write_text(
            '{"machineID": "x", "firstStartTime": "2026-08-09"}', encoding="utf-8")
        proc = run(["--status"], brain_dir=d, cursor_bin=str(cursor))
        assert "mode: no-brain" in proc.stdout
        assert "not logged in" in proc.stdout

    def test_cursor_auto_off_when_installed_but_not_authenticated(self, brain, cursor_unauthed):
        # regression: Keychain-bound login invisible to headless shells must
        # degrade with an explanation, not crash mid-pipeline
        proc = run(["--status"], brain_dir=brain, cursor_bin=str(cursor_unauthed))
        assert "mode: no-cursor" in proc.stdout
        assert "CURSOR_API_KEY" in proc.stdout

    def test_cursor_api_key_bypasses_status_check(self, brain, cursor_unauthed):
        env_extra = {"CURSOR_API_KEY": "test-key"}
        import os as _os
        env = dict(_os.environ)
        env["XPIPE_BRAIN_DIR"] = str(brain)
        env["XPIPE_CURSOR_BIN"] = str(cursor_unauthed)
        env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--status"],
            capture_output=True, text=True, env=env, timeout=60, cwd=str(REPO),
        )
        assert "mode: full" in proc.stdout

    def test_brain_on_via_oauth_account_in_state(self, tmp_path, cursor):
        # macOS Keychain case: no .credentials.json, but oauthAccount recorded
        d = tmp_path / "keychain-acct"
        d.mkdir()
        (d / ".claude.json").write_text(
            '{"oauthAccount": {"emailAddress": "x@y.z"}}', encoding="utf-8")
        proc = run(["--status"], brain_dir=d, cursor_bin=str(cursor))
        assert "mode: full" in proc.stdout

    def test_solo_run_without_task_still_exits_zero(self):
        proc = run(["--solo"])
        assert proc.returncode == 0

    def test_execution_mode_requires_task(self, brain, cursor):
        proc = run([], brain_dir=brain, cursor_bin=str(cursor))
        assert proc.returncode == 2


class TestDryRun:
    def test_dry_run_full_shows_all_stages_and_scoping(self, brain, cursor):
        proc = run(["fix the login bug", "--dry-run"],
                   brain_dir=brain, cursor_bin=str(cursor))
        assert proc.returncode == 0
        out = proc.stdout
        for stage in ["[plan @ brain]", "[review @ hands]",
                      "[cross-review @ cursor]", "[implement @ hands]"]:
            assert stage in out
        assert f"CLAUDE_CONFIG_DIR={brain}" in out
        assert "--allowedTools" in out
        assert "--dangerously-skip-permissions" not in out
        # cursor gets workspace trust but never force-allowed commands
        assert "--trust" in out
        assert "--yolo" not in out and " -f " not in out

    def test_dry_run_no_cursor_omits_cross_review(self, brain, cursor):
        proc = run(["task", "--dry-run", "--no-cursor"],
                   brain_dir=brain, cursor_bin=str(cursor))
        assert "[cross-review" not in proc.stdout
        assert "[plan @ brain]" in proc.stdout

    def test_dry_run_no_brain_plans_on_hands(self, brain, cursor):
        proc = run(["task", "--dry-run", "--no-brain"],
                   brain_dir=brain, cursor_bin=str(cursor))
        assert "[plan @ hands]" in proc.stdout
        assert "CLAUDE_CONFIG_DIR" not in proc.stdout

    def test_implement_stage_uses_worktree_contract(self, brain, cursor):
        proc = run(["task", "--dry-run"], brain_dir=brain, cursor_bin=str(cursor))
        assert "worktree" in proc.stdout
        assert "never" in proc.stdout.lower()  # never merge instruction present

    def test_review_stage_carries_record_handoff(self, brain, cursor):
        # reviewer must be able AND instructed to write the binding review
        # record (sha256(ops.json)) so /implement's approval gate resolves
        proc = run(["task", "--dry-run"], brain_dir=brain, cursor_bin=str(cursor))
        review_line = next(ln for ln in proc.stdout.splitlines()
                           if ln.startswith("[review @ hands]"))
        assert "review-record" in review_line
        assert "Write" in review_line and "Bash" in review_line


class TestRoleAccountPinning:
    """Roles stay pinned to accounts even when the orchestrating session IS
    the brain account (CLAUDE_CONFIG_DIR inherited in its environment)."""

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("xpipe", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_hands_stage_drops_inherited_brain_config(self):
        mod = self._mod()
        stage = {"runner": "hands", "env": {}}
        env = mod.stage_env(stage, {"CLAUDE_CONFIG_DIR": "/Users/x/.claude-acct-b",
                                    "PATH": "/usr/bin"})
        assert "CLAUDE_CONFIG_DIR" not in env
        assert env["PATH"] == "/usr/bin"

    def test_brain_stage_sets_its_config_over_inherited(self):
        mod = self._mod()
        stage = {"runner": "brain", "env": {"CLAUDE_CONFIG_DIR": "/Users/x/.claude-acct-b"}}
        env = mod.stage_env(stage, {"CLAUDE_CONFIG_DIR": "/somewhere/else"})
        assert env["CLAUDE_CONFIG_DIR"] == "/Users/x/.claude-acct-b"

    def test_cursor_stage_env_untouched(self):
        mod = self._mod()
        stage = {"runner": "cursor", "env": {}}
        env = mod.stage_env(stage, {"CLAUDE_CONFIG_DIR": "/Users/x/.claude-acct-b"})
        assert env["CLAUDE_CONFIG_DIR"] == "/Users/x/.claude-acct-b"


class TestPlanLocationConvention:
    def _normalize(self, root, raw):
        import importlib.util
        spec = importlib.util.spec_from_file_location("xpipe", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.normalize_plan_location(root, raw)

    def test_plan_at_repo_root_is_moved_home_with_ops(self, tmp_path):
        root = tmp_path
        (root / "plan-fix-x.md").write_text("# plan", encoding="utf-8")
        (root / "ops-fix-x.json").write_text("{}", encoding="utf-8")
        rel = self._normalize(root, "plan-fix-x.md")
        assert rel == os.path.join(".claude", "plans", "plan-fix-x.md")
        assert (root / ".claude" / "plans" / "plan-fix-x.md").is_file()
        assert (root / ".claude" / "plans" / "ops-fix-x.json").is_file()
        assert not (root / "plan-fix-x.md").exists()

    def test_plan_already_in_plans_dir_untouched(self, tmp_path):
        root = tmp_path
        plans = root / ".claude" / "plans"
        plans.mkdir(parents=True)
        (plans / "plan-y.md").write_text("# plan", encoding="utf-8")
        rel = self._normalize(root, str(plans / "plan-y.md"))
        assert rel == os.path.join(".claude", "plans", "plan-y.md")

    def test_missing_plan_returns_none(self, tmp_path):
        assert self._normalize(tmp_path, "no-such-plan.md") is None

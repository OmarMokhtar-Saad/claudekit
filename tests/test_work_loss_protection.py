"""Behavioral tests for the work-loss protections (concurrent-session wipe incident).

Contract under test (plan-work-loss-protection):
- Baseline binding: `validate-config-json.py --stamp-baseline` records sha256 per
  target file; the executor refuses (no writes, RESULT-JSON failed) when any
  stamped file changed since — external git checkout/restore, concurrent edit.
- Post-execution checkpoints: a successful run snapshots the RESULT of every
  touched file under <backup>/post/; `restore-backup.py --post` restores it
  (forward recovery), while plain restore still rolls back to pre-state.
- Concurrent-session warning: session-start.sh warns when another live session
  pid holds a lock in .claude/locks/, and prunes dead-pid locks.

All tests run the real scripts via subprocess in isolated tmp project dirs.
(The destructive-git command screening lives in tests/test_security.py.)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / ".claude" / "operations" / "scripts"
EXECUTOR = SCRIPTS / "execute-json-ops.py"
VALIDATOR = SCRIPTS / "validate-config-json.py"
RESTORE = SCRIPTS / "restore-backup.py"
HOOK = REPO / ".claude" / "hooks" / "session-start.sh"


def _run(script, args, cwd):
    return subprocess.run([sys.executable, str(script)] + args,
                          cwd=str(cwd), capture_output=True, text=True, timeout=120)


def _project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    return project


def _ops_config(project, name="wlp-test"):
    ops = {
        "plan": name,
        "operations": [{
            "type": "code_edit",
            "path": "target.py",
            "edits": [{"find": "VALUE = 1", "replace": "VALUE = 2"}],
        }],
    }
    path = project / "ops.json"
    path.write_text(json.dumps(ops), encoding="utf-8")
    return path


class TestBaselineBinding:
    def test_stamp_writes_baseline_hashes(self, tmp_path):
        project = _project(tmp_path)
        ops = _ops_config(project)
        result = _run(VALIDATOR, [str(ops), "--stamp-baseline"], project)
        assert result.returncode == 0, result.stdout + result.stderr
        stamped = json.loads(ops.read_text(encoding="utf-8"))
        assert stamped["baseline"]["target.py"].startswith("sha256:")

    def test_executor_verifies_clean_baseline(self, tmp_path):
        project = _project(tmp_path)
        ops = _ops_config(project)
        assert _run(VALIDATOR, [str(ops), "--stamp-baseline"], project).returncode == 0
        result = _run(EXECUTOR, [str(ops)], project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Baseline: verified" in result.stdout
        assert "VALUE = 2" in (project / "target.py").read_text(encoding="utf-8")

    def test_executor_aborts_on_drift_without_writes(self, tmp_path):
        project = _project(tmp_path)
        ops = _ops_config(project)
        assert _run(VALIDATOR, [str(ops), "--stamp-baseline"], project).returncode == 0
        # Simulate the incident: an external actor resets the file after stamping.
        (project / "target.py").write_text("VALUE = 1  # reset by other session\n",
                                           encoding="utf-8")
        result = _run(EXECUTOR, [str(ops)], project)
        assert result.returncode != 0
        assert "BASELINE DRIFT" in result.stdout
        assert "target.py" in result.stdout
        # No partial writes: the drifted content is untouched.
        assert "reset by other session" in (project / "target.py").read_text(encoding="utf-8")

    def test_drift_gate_applies_to_dry_run(self, tmp_path):
        project = _project(tmp_path)
        ops = _ops_config(project)
        assert _run(VALIDATOR, [str(ops), "--stamp-baseline"], project).returncode == 0
        (project / "target.py").write_text("drifted\n", encoding="utf-8")
        result = _run(EXECUTOR, [str(ops), "--dry-run"], project)
        assert result.returncode != 0
        assert "BASELINE DRIFT" in result.stdout

    def test_missing_stamped_file_reported(self, tmp_path):
        project = _project(tmp_path)
        ops = _ops_config(project)
        assert _run(VALIDATOR, [str(ops), "--stamp-baseline"], project).returncode == 0
        (project / "target.py").unlink()
        result = _run(EXECUTOR, [str(ops)], project)
        assert result.returncode != 0
        assert "MISSING" in result.stdout

    def test_unstamped_config_still_executes_with_warning(self, tmp_path):
        project = _project(tmp_path)
        ops = _ops_config(project)
        result = _run(EXECUTOR, [str(ops)], project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Baseline: none" in result.stdout


class TestPostExecutionCheckpoint:
    def _execute(self, project, ops):
        result = _run(EXECUTOR, [str(ops)], project)
        assert result.returncode == 0, result.stdout + result.stderr
        backups = sorted((project / "backups").iterdir())
        assert backups, "no backup dir created"
        return backups[-1]

    def test_post_state_snapshot_written(self, tmp_path):
        project = _project(tmp_path)
        backup = self._execute(project, _ops_config(project))
        post = backup / "post" / "target.py"
        assert post.is_file()
        assert "VALUE = 2" in post.read_text(encoding="utf-8")
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["post_state"] is True

    def test_forward_recovery_after_external_wipe(self, tmp_path):
        project = _project(tmp_path)
        backup = self._execute(project, _ops_config(project))
        # The incident: an external actor resets the file to pre-plan state.
        (project / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
        result = _run(RESTORE, ["--backup", str(backup), "--post", "--force"], project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "VALUE = 2" in (project / "target.py").read_text(encoding="utf-8")

    def test_plain_restore_still_rolls_back(self, tmp_path):
        project = _project(tmp_path)
        backup = self._execute(project, _ops_config(project))
        result = _run(RESTORE, ["--backup", str(backup), "--force"], project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "VALUE = 1" in (project / "target.py").read_text(encoding="utf-8")

    def test_post_restore_covers_created_files(self, tmp_path):
        project = _project(tmp_path)
        ops = {
            "plan": "wlp-create",
            "operations": [{"type": "file_create", "path": "made.py",
                            "content": "MADE = True\n"}],
        }
        path = project / "ops.json"
        path.write_text(json.dumps(ops), encoding="utf-8")
        backup = self._execute(project, path)
        (project / "made.py").unlink()  # external wipe
        result = _run(RESTORE, ["--backup", str(backup), "--post", "--force"], project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (project / "made.py").read_text(encoding="utf-8") == "MADE = True\n"

    def test_post_flag_refused_on_pre_checkpoint_backup(self, tmp_path):
        project = _project(tmp_path)
        backup = self._execute(project, _ops_config(project))
        manifest_path = backup / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["post_state"]  # simulate an older backup
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = _run(RESTORE, ["--backup", str(backup), "--post", "--force"], project)
        assert result.returncode != 0
        assert "no post-execution checkpoint" in result.stdout


class TestConcurrentSessionWarning:
    def _run_hook(self, project):
        result = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True,
                                cwd=str(project), timeout=60)
        assert result.returncode == 0
        return result.stdout

    def test_single_session_no_warning(self, tmp_path):
        project = _project(tmp_path)
        assert "WARNING:" not in self._run_hook(project)
        locks = list((project / ".claude" / "locks").glob("session-*"))
        assert locks, "hook did not write its own session lock"

    def test_other_live_session_warns(self, tmp_path):
        project = _project(tmp_path)
        locks = project / ".claude" / "locks"
        locks.mkdir(parents=True)
        # A live pid we own (kill -0 must succeed) that is neither the hook
        # shell nor its parent — a short-lived sleep child of the test process.
        other = subprocess.Popen(["sleep", "30"])
        try:
            (locks / f"session-{other.pid}").write_text("x", encoding="utf-8")
            out = self._run_hook(project)
        finally:
            other.terminate()
            other.wait()
        assert "WARNING: 1 other session(s)" in out

    def test_dead_pid_lock_pruned_silently(self, tmp_path):
        project = _project(tmp_path)
        locks = project / ".claude" / "locks"
        locks.mkdir(parents=True)
        # Find a pid that is certainly dead.
        dead = 99999
        while True:
            try:
                os.kill(dead, 0)
                dead -= 1
            except ProcessLookupError:
                break
            except PermissionError:
                dead -= 1
        (locks / f"session-{dead}").write_text("x", encoding="utf-8")
        out = self._run_hook(project)
        assert "WARNING:" not in out
        assert not (locks / f"session-{dead}").exists()

    def test_garbage_lock_name_removed(self, tmp_path):
        project = _project(tmp_path)
        locks = project / ".claude" / "locks"
        locks.mkdir(parents=True)
        (locks / "session-notapid").write_text("x", encoding="utf-8")
        out = self._run_hook(project)
        assert "WARNING:" not in out
        assert not (locks / "session-notapid").exists()

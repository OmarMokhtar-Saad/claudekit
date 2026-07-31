"""Behavioral tests for the ops-engine hardening.

Covers the fail-closed apply-time guards, first-write-wins backups, dry-run
state threading, execution evidence (diff + RESULT-JSON), and cumulative
validator simulation added by plan-ops-hardening-implementer-contract.

All tests run the real scripts via subprocess in an isolated tmp project dir.
"""

import json
import os
import pathlib
import subprocess
import sys

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '.claude', 'operations', 'scripts')
)
EXECUTOR = os.path.join(SCRIPTS_DIR, 'execute-json-ops.py')
VALIDATOR = os.path.join(SCRIPTS_DIR, 'validate-config-json.py')

RESULT_PREFIX = 'RESULT-JSON: '


def _run(script, ops_path, cwd, *flags):
    return subprocess.run(
        [sys.executable, script, str(ops_path)] + list(flags),
        cwd=str(cwd), capture_output=True, text=True, timeout=120,
    )


def _result_json(stdout):
    """Extract the single RESULT-JSON payload, with an informative failure."""
    lines = [ln for ln in stdout.splitlines() if ln.startswith(RESULT_PREFIX)]
    assert len(lines) == 1, f"expected exactly 1 RESULT-JSON line, got {len(lines)}"
    return json.loads(lines[0][len(RESULT_PREFIX):])


def _ops(tmp_path, operations, name='test-hardening'):
    path = tmp_path / 'ops.json'
    path.write_text(json.dumps({'plan': name, 'operations': operations}),
                    encoding='utf-8')
    return path


def _edit(path, find, replace):
    return {'type': 'code_edit', 'path': path,
            'edits': [{'find': find, 'replace': replace}]}


class TestApplyTimeGuards:
    def test_ambiguous_anchor_aborts_without_writing(self, tmp_path):
        target = tmp_path / 'app.py'
        original = 'x = 1\nx = 1\n'
        target.write_text(original, encoding='utf-8')
        ops = _ops(tmp_path, [_edit('app.py', 'x = 1', 'x = 2')])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 1
        assert 'ambiguous' in (res.stdout + res.stderr).lower()
        assert target.read_text(encoding='utf-8') == original

    def test_missing_anchor_aborts_and_rolls_back_prior_ops(self, tmp_path):
        a = tmp_path / 'a.py'
        b = tmp_path / 'b.py'
        a.write_text('alpha\n', encoding='utf-8')
        b.write_text('other\n', encoding='utf-8')
        ops = _ops(tmp_path, [
            _edit('a.py', 'alpha', 'beta'),
            _edit('b.py', 'not-present', 'anything'),
        ])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 1
        # The first (successful) op must be rolled back after the second fails.
        assert a.read_text(encoding='utf-8') == 'alpha\n'


class TestBackupFirstWriteWins:
    def test_same_file_twice_rollback_restores_pristine(self, tmp_path):
        """Regression: op 2's backup must not clobber op 1's pristine copy.

        Before first-write-wins backups, the second operation on a file copied
        the ALREADY-MUTATED content over the backup, so rollback restored the
        intermediate state and the original was lost.
        """
        target = tmp_path / 'app.py'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [
            _edit('app.py', 'alpha', 'beta'),
            _edit('app.py', 'NO_SUCH_ANCHOR', 'x'),
        ])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 1
        assert target.read_text(encoding='utf-8') == 'alpha\n', \
            'rollback restored a mutated intermediate instead of the original'

    def test_backup_file_itself_holds_pristine_content(self, tmp_path):
        target = tmp_path / 'app.py'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [
            _edit('app.py', 'alpha', 'beta'),
            _edit('app.py', 'beta', 'gamma'),
        ])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        assert target.read_text(encoding='utf-8') == 'gamma\n'
        backups = list((tmp_path / 'backups').glob('*/app.py'))
        assert len(backups) == 1
        assert backups[0].read_text(encoding='utf-8') == 'alpha\n', \
            'backup must hold pre-run content so restore-backup.py is correct'

    def test_delete_after_edit_keeps_pristine_backup(self, tmp_path):
        """file_delete must not overwrite the backup an earlier code_edit made."""
        target = tmp_path / 'app.py'
        other = tmp_path / 'b.py'
        target.write_text('alpha\n', encoding='utf-8')
        other.write_text('other\n', encoding='utf-8')
        ops = _ops(tmp_path, [
            _edit('app.py', 'alpha', 'beta'),
            {'type': 'file_delete', 'path': 'app.py',
             'reason': 'superseded by the rewritten module'},
            _edit('b.py', 'NO_SUCH_ANCHOR', 'x'),
        ])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 1
        assert target.exists(), 'rollback must recreate the deleted file'
        assert target.read_text(encoding='utf-8') == 'alpha\n'

    def test_root_manifest_json_is_refused_not_silently_unbacked(self, tmp_path):
        """A project-root manifest.json collides with the engine's own manifest."""
        target = tmp_path / 'manifest.json'
        target.write_text('{"name": "app"}\n', encoding='utf-8')
        ops = _ops(tmp_path, [_edit('manifest.json', '"app"', '"renamed"')])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 1
        assert 'collides' in res.stdout
        assert target.read_text(encoding='utf-8') == '{"name": "app"}\n'


class TestDryRunFidelity:
    def test_dry_run_threads_state_across_ops_on_same_file(self, tmp_path):
        target = tmp_path / 'app.py'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [
            _edit('app.py', 'alpha', 'beta'),
            _edit('app.py', 'beta', 'gamma'),  # 'beta' exists only after op 1
        ])
        res = _run(EXECUTOR, ops, tmp_path, '--dry-run')
        assert res.returncode == 0, res.stdout + res.stderr
        # Dry run must not touch the file.
        assert target.read_text(encoding='utf-8') == 'alpha\n'


class TestExecutionEvidence:
    def test_execute_prints_diff_and_result_json(self, tmp_path):
        target = tmp_path / 'app.py'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [_edit('app.py', 'alpha', 'beta')])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        assert target.read_text(encoding='utf-8') == 'beta\n'
        assert 'Diff preview' in res.stdout
        payload = _result_json(res.stdout)
        assert payload['status'] == 'success'
        assert payload['mode'] == 'execute'
        assert payload['operations'][0]['status'] == 'edited'
        assert payload['backup_dir']

    def test_failed_run_reports_failed_status_in_result_json(self, tmp_path):
        target = tmp_path / 'app.py'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [_edit('app.py', 'missing', 'beta')])
        res = _run(EXECUTOR, ops, tmp_path)
        assert res.returncode == 1
        payload = _result_json(res.stdout)
        assert payload['status'] == 'failed'
        assert payload['operations'][0]['status'] == 'pattern-not-found'

    def test_engine_level_abort_still_emits_result_json(self, tmp_path):
        """An unreadable config aborts before execution but must still report."""
        bad = tmp_path / 'ops.json'
        bad.write_text('{not valid json', encoding='utf-8')
        res = _run(EXECUTOR, bad, tmp_path)
        assert res.returncode == 1
        payload = _result_json(res.stdout)
        assert payload['status'] == 'failed'
        assert 'config-load-error' in payload['reason']


class TestValidatorCumulativeSimulation:
    def test_flags_edit_made_ambiguous_by_prior_edit(self, tmp_path):
        target = tmp_path / 'app.py'
        target.write_text('A\nB\n', encoding='utf-8')
        ops = _ops(tmp_path, [{
            'type': 'code_edit', 'path': 'app.py',
            'edits': [
                {'find': 'A', 'replace': 'B'},   # makes 'B' ambiguous
                {'find': 'B', 'replace': 'C'},
            ],
        }])
        res = _run(VALIDATOR, ops, tmp_path)
        assert res.returncode != 0
        assert 'appears 2 times' in (res.stdout + res.stderr)

    def test_accepts_edit_dependent_on_prior_edit_same_op(self, tmp_path):
        target = tmp_path / 'app.py'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [{
            'type': 'code_edit', 'path': 'app.py',
            'edits': [
                {'find': 'alpha', 'replace': 'beta'},
                {'find': 'beta', 'replace': 'gamma'},  # exists only post-edit-1
            ],
        }])
        res = _run(VALIDATOR, ops, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_threads_state_across_operations_on_same_file(self, tmp_path):
        target = tmp_path / 'app.py'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [
            _edit('app.py', 'alpha', 'beta'),
            _edit('app.py', 'beta', 'gamma'),
        ])
        res = _run(VALIDATOR, ops, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr


class TestPostLoopFailureDoesNotRevert:
    """A crash AFTER the operation loop must not roll back a committed batch.

    Verified by copying the engine into the tmp project and injecting a fault at
    the exact point the loop finishes — the only way to isolate this path, since
    a real BrokenPipeError lands non-deterministically (with small output none
    fires; with large output it lands inside the loop, where rollback is right).
    """

    def _engine_with_injection(self, tmp_path, injected):
        src = pathlib.Path(EXECUTOR).read_text(encoding='utf-8')
        marker = '        loop_completed = True\n'
        assert marker in src, 'engine no longer has the loop_completed marker'
        patched = tmp_path / 'engine_injected.py'
        patched.write_text(src.replace(marker, marker + injected, 1), encoding='utf-8')
        return patched

    def test_crash_after_loop_keeps_applied_changes(self, tmp_path):
        target = tmp_path / 'f.txt'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [_edit('f.txt', 'alpha', 'beta')])
        engine = self._engine_with_injection(
            tmp_path, "        raise RuntimeError('injected post-loop failure')\n")
        env = dict(os.environ, PYTHONPATH=SCRIPTS_DIR)
        res = subprocess.run([sys.executable, str(engine), str(ops)], cwd=str(tmp_path),
                             capture_output=True, text=True, timeout=120, env=env)
        assert res.returncode != 0
        assert target.read_text(encoding='utf-8') == 'beta\n', \
            'a committed batch was reverted by a post-loop failure'
        assert _result_json(res.stdout)['status'] == 'crashed'

    def test_transaction_retired_before_summary(self, tmp_path):
        """_active_txn must be cleared before the summary prints.

        Otherwise a signal arriving during the summary would roll back a finished
        run, and _result_emitted would suppress the 'interrupted' verdict — leaving
        success evidence over a reverted tree.
        """
        target = tmp_path / 'f.txt'
        target.write_text('alpha\n', encoding='utf-8')
        ops = _ops(tmp_path, [_edit('f.txt', 'alpha', 'beta')])
        engine = self._engine_with_injection(
            tmp_path,
            "        assert _active_txn is None, 'txn still live during summary'\n")
        env = dict(os.environ, PYTHONPATH=SCRIPTS_DIR)
        res = subprocess.run([sys.executable, str(engine), str(ops)], cwd=str(tmp_path),
                             capture_output=True, text=True, timeout=120, env=env)
        assert res.returncode == 0, res.stdout + res.stderr
        assert target.read_text(encoding='utf-8') == 'beta\n'

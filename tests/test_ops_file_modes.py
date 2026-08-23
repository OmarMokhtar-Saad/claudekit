"""Behavioral tests: the ops engine must preserve file permission bits."""

import json
import os
import stat
import subprocess
import sys

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '.claude', 'operations', 'scripts')
)
EXECUTOR = os.path.join(SCRIPTS_DIR, 'execute-json-ops.py')
RESTORE = os.path.join(SCRIPTS_DIR, 'restore-backup.py')

SCRIPT_BODY = '#!/bin/sh\necho hi\n'
EDITED_BODY = '#!/bin/sh\necho bye\n'


def _env():
    env = os.environ.copy()
    env['ECC_HOOK_PROFILE'] = 'minimal'
    return env


def _run(script, cwd, *args):
    return subprocess.run([sys.executable, script] + [str(a) for a in args],
                          cwd=str(cwd), capture_output=True, text=True,
                          timeout=120, env=_env())


def _ops(tmp_path, operations, name='file-modes'):
    path = tmp_path / 'ops.json'
    path.write_text(json.dumps({'plan': name, 'operations': operations}), encoding='utf-8')
    return path


def _edit(path, find, replace):
    return {'type': 'code_edit', 'path': path,
            'edits': [{'find': find, 'replace': replace}]}


def _mode(path):
    return stat.S_IMODE(os.stat(str(path)).st_mode)


def _process_umask():
    current = os.umask(0)
    os.umask(current)
    return current


def _write(path, text, mode):
    path.write_text(text, encoding='utf-8')
    os.chmod(str(path), mode)
    assert _mode(path) == mode
    return path


class TestCodeEditPreservesMode:
    def test_executable_script_stays_executable(self, tmp_path):
        target = _write(tmp_path / 's.sh', SCRIPT_BODY, 0o755)
        ops = _ops(tmp_path, [_edit('s.sh', 'echo hi', 'echo bye')])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert target.read_text(encoding='utf-8') == EDITED_BODY
        assert _mode(target) == 0o755

    def test_plain_file_keeps_0644(self, tmp_path):
        target = _write(tmp_path / 'a.txt', 'alpha\n', 0o644)
        ops = _ops(tmp_path, [_edit('a.txt', 'alpha', 'beta')])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert _mode(target) == 0o644

    def test_group_writable_mode_is_not_normalised(self, tmp_path):
        target = _write(tmp_path / 'g.txt', 'alpha\n', 0o664)
        ops = _ops(tmp_path, [_edit('g.txt', 'alpha', 'beta')])
        assert _run(EXECUTOR, tmp_path, ops).returncode == 0
        assert _mode(target) == 0o664


class TestFileCreateMode:
    def test_created_file_respects_umask(self, tmp_path):
        expected = 0o666 & ~_process_umask()
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'new.txt', 'content': 'x\n'}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        created = tmp_path / 'new.txt'
        assert _mode(created) == expected
        assert not _mode(created) & stat.S_IXUSR


class TestRollbackPreservesMode:
    def test_rollback_after_midbatch_failure_keeps_0755(self, tmp_path):
        target = _write(tmp_path / 's.sh', SCRIPT_BODY, 0o755)
        _write(tmp_path / 'b.txt', 'other\n', 0o644)
        ops = _ops(tmp_path, [
            _edit('s.sh', 'echo hi', 'echo bye'),
            _edit('b.txt', 'not-present', 'anything'),
        ])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 1
        assert target.read_text(encoding='utf-8') == SCRIPT_BODY
        assert _mode(target) == 0o755


class TestPostStateRestorePreservesMode:
    def test_post_checkpoint_and_forward_restore_keep_0755(self, tmp_path):
        target = _write(tmp_path / 's.sh', SCRIPT_BODY, 0o755)
        ops = _ops(tmp_path, [_edit('s.sh', 'echo hi', 'echo bye')])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr

        backups = sorted((tmp_path / 'backups').iterdir())
        assert len(backups) == 1, backups
        assert _mode(backups[0] / 'post' / 's.sh') == 0o755

        _write(target, 'wiped\n', 0o600)
        res = _run(RESTORE, tmp_path, '--backup', backups[0], '--post', '--force')
        assert res.returncode == 0, res.stdout + res.stderr
        assert target.read_text(encoding='utf-8') == EDITED_BODY
        assert _mode(target) == 0o755


class TestCreateOverExistingFile:
    def test_create_over_existing_file_inherits_its_mode(self, tmp_path):
        """A create over an existing path keeps that path's mode, not the default.

        execute_file_create does not check existence, so this is the behavior
        that keeps a re-authored executable script executable.
        """
        target = _write(tmp_path / 'hook.sh', SCRIPT_BODY, 0o755)
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'hook.sh',
                               'content': EDITED_BODY}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert target.read_text(encoding='utf-8') == EDITED_BODY
        assert _mode(target) == 0o755

class TestDeclaredCreateMode:
    """`file_create` may declare a POSIX mode.

    Without it a NEW file always landed 0644 (atomic_write falls back to
    DEFAULT_CREATE_MODE when the target does not exist), so promoting a 0755 hook
    script through the engine produced a hook nothing could run. Found in review of
    task 008 batch 1, where four `.claude/hooks/*.sh` would have landed
    non-executable; `install.sh` chmods by shebang, so CONSUMERS self-healed and
    this repo's own tree did not -- the worst shape of bug to find later."""

    def test_declared_0755_is_applied_to_a_new_file(self, tmp_path):
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'hook.sh',
                               'content': SCRIPT_BODY, 'mode': '0755'}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert _mode(tmp_path / 'hook.sh') == 0o755
        assert os.access(str(tmp_path / 'hook.sh'), os.X_OK)

    def test_declared_0644_is_applied_regardless_of_umask(self, tmp_path):
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'doc.txt',
                               'content': 'x\n', 'mode': '0644'}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert _mode(tmp_path / 'doc.txt') == 0o644

    def test_omitting_mode_keeps_the_previous_default(self, tmp_path):
        """The field is optional and its absence must not change what shipped."""
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'plain.txt',
                               'content': 'x\n'}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert _mode(tmp_path / 'plain.txt') == 0o666 & ~_process_umask()

    def test_setuid_is_refused_by_the_executor(self, tmp_path):
        """The schema enum is the contract; this is the enforcement. A config that
        never went through the validator must still not be able to set setuid.
        Asserted on the FILE, not just the exit code: a refusal that still wrote"""
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'evil.sh',
                               'content': SCRIPT_BODY, 'mode': '4755'}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode != 0, res.stdout + res.stderr
        assert 'unsupported create mode' in (res.stdout + res.stderr).lower()
        assert not (tmp_path / 'evil.sh').exists(), 'refused the mode but wrote the file'

    def test_world_writable_is_refused(self, tmp_path):
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'open.txt',
                               'content': 'x\n', 'mode': '0777'}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode != 0, res.stdout + res.stderr
        assert not (tmp_path / 'open.txt').exists()

    def test_the_validator_rejects_a_bad_mode_before_execution(self, tmp_path):
        """Reported where every other operation defect is reported."""
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'evil.sh',
                               'content': SCRIPT_BODY, 'mode': '4755'}])
        res = _run(os.path.join(SCRIPTS_DIR, 'validate-config-json.py'), tmp_path, ops)
        assert res.returncode != 0, res.stdout + res.stderr
        assert '4755' in res.stdout and 'REJECTED' in res.stdout

    def test_the_mode_guard_holds_without_jsonschema(self, tmp_path):
        """ClaudeKit has ZERO runtime dependencies, so `jsonschema` is absent on a
        default install and the validator says so and carries on with its own
        guards (validate-config-json.py:883). The schema enum is therefore NOT the
        control in the common case -- the hand-rolled check is. Simulated by
        blocking the import, which is what an unpatched machine actually does.
        """
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'evil.sh',
                               'content': SCRIPT_BODY, 'mode': '4755'}])
        blocker = tmp_path / 'jsonschema.py'
        blocker.write_text('raise ImportError("blocked for this test")\n',
                           encoding='utf-8')
        env = _env()
        env['PYTHONPATH'] = str(tmp_path)
        res = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, 'validate-config-json.py'),
             str(ops)],
            cwd=str(tmp_path), capture_output=True, text=True, timeout=120, env=env)
        assert 'schema validation skipped' in res.stdout.lower(), (
            'fixture did not actually remove jsonschema: ' + res.stdout)
        assert res.returncode != 0, res.stdout + res.stderr
        assert 'unsupported mode' in res.stdout.lower(), res.stdout

    def test_the_promoted_hooks_declare_0755(self):
        """The batch-1 configs this feature exists for. Reads the shipped configs, so
        dropping the mode from a promotion goes red here."""
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        batch = os.path.join(repo, '.claude', 'plans', 'ops-008-batch1')
        if not os.path.isdir(batch):
            import pytest
            pytest.skip('batch 1 configs already spent and archived')
        found = 0
        for name in sorted(os.listdir(batch)):
            with open(os.path.join(batch, name), encoding='utf-8') as fh:
                cfg = json.load(fh)
            for op in cfg.get('operations', []):
                if op.get('type') == 'file_create' and op['path'].endswith('.sh'):
                    assert op.get('mode') == '0755', (
                        f"{name}: {op['path']} promoted without the executable bit")
                    found += 1
        assert found == 4, f'expected the 4 hook promotions, found {found}'

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

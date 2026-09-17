"""Behavioral: install.sh prunes old .claude.bak-* backups and gitignores the pattern.

Measured 2026-09-17: every install/fleet update moved the previous .claude aside as
.claude.bak-<timestamp> and never cleaned up; fleet repos held 11-27 untracked backup
dirs each. These tests run the real installer against a tmp project.
"""
import os
import subprocess
import tempfile

INSTALL_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'install.sh')


def _install(tmpdir, env_extra=None):
    env = dict(os.environ)
    env.pop('CLAUDEKIT_KEEP_BACKUPS', None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                          capture_output=True, text=True, timeout=120, env=env)


def _seed_backups(tmpdir, n):
    names = []
    for i in range(n):
        name = os.path.join(tmpdir, '.claude.bak-2026010%d-000000' % (i + 1))
        os.makedirs(os.path.join(name, 'agents'))
        with open(os.path.join(name, 'marker.txt'), 'w') as f:
            f.write(str(i))
        names.append(name)
    return names


def _backups(tmpdir):
    return sorted(d for d in os.listdir(tmpdir) if d.startswith('.claude.bak-'))


def test_install_prunes_to_newest_three_backups_by_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        _seed_backups(tmpdir, 5)
        os.makedirs(os.path.join(tmpdir, '.claude'))  # so the install creates one more backup
        r = _install(tmpdir)
        assert r.returncode == 0, r.stderr
        left = _backups(tmpdir)
        assert len(left) == 3, left
        # The newest three survive: the two most recent seeds plus the one this install made.
        assert '.claude.bak-20260104-000000' in left and '.claude.bak-20260105-000000' in left
        assert '.claude.bak-20260101-000000' not in left
        assert 'Pruned 3 old .claude.bak-* backup(s)' in r.stdout


def test_keep_backups_all_disables_pruning():
    with tempfile.TemporaryDirectory() as tmpdir:
        _seed_backups(tmpdir, 5)
        os.makedirs(os.path.join(tmpdir, '.claude'))
        r = _install(tmpdir, {'CLAUDEKIT_KEEP_BACKUPS': 'all'})
        assert r.returncode == 0, r.stderr
        assert len(_backups(tmpdir)) == 6
        assert 'Pruned' not in r.stdout


def test_gitignore_covers_backup_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        r = _install(tmpdir)
        assert r.returncode == 0, r.stderr
        with open(os.path.join(tmpdir, '.gitignore')) as f:
            lines = f.read().splitlines()
        assert '.claude.bak-*/' in lines

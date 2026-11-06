"""Behavioral tests for plan-gate.sh, checkpoint-gate.sh and shell-write-gate.py.

Each hook is run for real, with ECC_HOOK_PROFILE both unset and `minimal`: none of the
three may stand down under `minimal`.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
HOOKS = os.path.join(ROOT, '.claude', 'hooks')
RECORDER = os.path.join(ROOT, '.claude', 'operations', 'scripts', 'review-record.py')
PLAN = "# Plan: demo\n- **Files:** `app.py`\n- **Tier:** 3\n"


def _git(cwd, *a):
    return subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                          cwd=str(cwd), capture_output=True, text=True, check=True)


@pytest.fixture
def proj(tmp_path):
    """A git project with the kit's hooks + recorder copied in and a plans dir."""
    _git(tmp_path, 'init', '-q')
    # the hooks run `git stash create` / `git tag -a`, which need an identity on a bare CI runner
    _git(tmp_path, 'config', 'user.email', 't@t')
    _git(tmp_path, 'config', 'user.name', 't')
    (tmp_path / '.claude' / 'plans').mkdir(parents=True)
    (tmp_path / '.claude' / 'hooks').mkdir()
    (tmp_path / '.claude' / 'operations' / 'scripts').mkdir(parents=True)
    for name in ('lib.sh', 'plan-lib.sh', 'plan-gate.sh', 'checkpoint-gate.sh',
                 'shell-write-gate.py'):
        data = open(os.path.join(HOOKS, name)).read()
        dest = tmp_path / '.claude' / 'hooks' / name
        dest.write_text(data)
        dest.chmod(0o755)
    rec = tmp_path / '.claude' / 'operations' / 'scripts' / 'review-record.py'
    rec.write_text(open(RECORDER).read())
    (tmp_path / 'app.py').write_text('a = 1\nb = 2\n')
    _git(tmp_path, 'add', '.')
    _git(tmp_path, 'commit', '-qm', 'init')
    return tmp_path


def _hook(proj, name, payload, profile=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith('ECC_')}
    if profile:
        env['ECC_HOOK_PROFILE'] = profile
    path = str(proj / '.claude' / 'hooks' / name)
    cmd = [sys.executable, path] if name.endswith('.py') else ['bash', path]
    return subprocess.run(cmd, cwd=str(proj), input=json.dumps(payload), env=env,
                          capture_output=True, text=True, timeout=60)


def _edit(proj, path='app.py', old='a = 1', new='a = 2', tool='Edit'):
    return {'tool_name': tool, 'tool_input': {
        'file_path': str(proj / path), 'old_string': old, 'new_string': new}}


def _write_payload(proj, path='app.py'):
    return {'tool_name': 'Write', 'tool_input': {
        'file_path': str(proj / path), 'content': 'x = 1\n'}}


def _approve(proj, files='`app.py`'):
    plan = proj / '.claude' / 'plans' / 'plan-demo.md'
    plan.write_text(PLAN.replace('`app.py`', files))
    subprocess.run([sys.executable, str(proj / '.claude/operations/scripts/review-record.py'),
                    'plan-write', str(plan), '--score', '95', '--decision', 'APPROVED',
                    '--owner-approved'], cwd=str(proj), check=True, capture_output=True)
    return plan


PROFILES = [None, 'minimal']


@pytest.mark.parametrize('profile', PROFILES)
class TestPlanGate:
    def test_t3_write_without_plan_blocked(self, proj, profile):
        r = _hook(proj, 'plan-gate.sh', _write_payload(proj), profile)
        assert r.returncode == 2 and 'PLAN GATE' in r.stderr

    def test_approved_plan_allows_listed_path_only(self, proj, profile):
        _approve(proj)
        assert _hook(proj, 'plan-gate.sh', _write_payload(proj), profile).returncode == 0
        (proj / 'other.py').write_text('')
        r = _hook(proj, 'plan-gate.sh', _write_payload(proj, 'other.py'), profile)
        assert r.returncode == 2

    def test_plan_drift_blocks(self, proj, profile):
        plan = _approve(proj)
        plan.write_text(plan.read_text() + 'more\n')
        assert _hook(proj, 'plan-gate.sh', _write_payload(proj), profile).returncode == 2

    def test_single_line_carveout_default_tier(self, proj, profile):
        assert _hook(proj, 'plan-gate.sh', _edit(proj), profile).returncode == 0
        multi = _edit(proj, old='a = 1\nb = 2', new='a = 1')
        assert _hook(proj, 'plan-gate.sh', multi, profile).returncode == 2

    def test_carveout_never_beats_globs_file(self, proj, profile):
        (proj / '.claude' / 'plan-gate.globs').write_text('app.py\n')
        assert _hook(proj, 'plan-gate.sh', _edit(proj), profile).returncode == 2

    def test_deny_list_before_carveout(self, proj, profile):
        for rel in ('.claude/reports/reviews/x.plan.json', '.claude/settings.local.json',
                    '.claude/plan-gate.globs'):
            payload = _edit(proj, path=rel, old='a', new='b')
            assert _hook(proj, 'plan-gate.sh', payload, profile).returncode == 2, rel

    def test_files_line_of_approved_plan_frozen(self, proj, profile):
        plan = _approve(proj)
        payload = _edit(proj, path=str(plan.relative_to(proj)),
                        old='- **Files:** `app.py`', new='- **Files:** `app.py`, `x.py`')
        r = _hook(proj, 'plan-gate.sh', payload, profile)
        assert r.returncode == 2 and 'FROZEN' in r.stderr

    def test_unparseable_payload_fails_closed(self, proj, profile):
        env = {k: v for k, v in os.environ.items() if not k.startswith('ECC_')}
        if profile:
            env['ECC_HOOK_PROFILE'] = profile
        r = subprocess.run(['bash', str(proj / '.claude/hooks/plan-gate.sh')], cwd=str(proj),
                           input='not json', env=env, capture_output=True, text=True)
        assert r.returncode == 2

    def test_non_t3_docs_pass(self, proj, profile):
        assert _hook(proj, 'plan-gate.sh', _write_payload(proj, 'README.md'),
                     profile).returncode == 0


def test_inactive_without_plans_dir(proj):
    os.rmdir(proj / '.claude' / 'plans')
    assert _hook(proj, 'plan-gate.sh', _write_payload(proj)).returncode == 0


@pytest.mark.parametrize('profile', PROFILES)
class TestCheckpointGate:
    def _tags(self, proj):
        return _git(proj, 'tag', '-l', 'ck-checkpoint/*').stdout.split()

    def test_creates_then_reuses_checkpoint(self, proj, profile):
        (proj / 'app.py').write_text('a = 9\n')
        (proj / 'new_untracked.txt').write_text('u')
        assert _hook(proj, 'checkpoint-gate.sh', _write_payload(proj), profile).returncode == 0
        tags = self._tags(proj)
        assert len(tags) == 1
        assert 'new_untracked.txt' in _git(proj, 'tag', '-n9', tags[0]).stdout
        assert _hook(proj, 'checkpoint-gate.sh', _write_payload(proj), profile).returncode == 0
        assert self._tags(proj) == tags

    def test_non_t3_makes_no_checkpoint(self, proj, profile):
        _hook(proj, 'checkpoint-gate.sh', _write_payload(proj, 'README.md'), profile)
        assert self._tags(proj) == []

    def test_prunes_to_twenty(self, proj, profile):
        for i in range(25):
            _git(proj, 'tag', '-a', '-m', 'm', 'ck-checkpoint/%d' % (1000 + i))
        assert _hook(proj, 'checkpoint-gate.sh', _write_payload(proj), profile).returncode == 0
        assert len(self._tags(proj)) == 20


@pytest.mark.parametrize('profile', PROFILES)
class TestShellWriteGate:
    @pytest.mark.parametrize('cmd', [
        'echo x > .claude/reports/reviews/a.plan.json',
        'echo x >> .claude/settings.local.json',
        'tee .claude/reports/reviews/a.plan.json < /dev/null',
        'sed -i s/a/b/ .claude/settings.json',
        'touch .claude/reports/reviews/a.plan.json',
        'cp /tmp/x .claude/plan-gate.globs',
        'mv /tmp/x .claude/reports/reviews/a.plan.json',
        "python3 -c \"open('.claude/reports/reviews/a.plan.json','w').write('x')\"",
    ])
    def test_denies(self, proj, profile, cmd):
        r = _hook(proj, 'shell-write-gate.py', {'tool_input': {'command': cmd}}, profile)
        assert r.returncode == 2, cmd

    @pytest.mark.parametrize('cmd', [
        'ls .claude/reports/reviews', 'cat .claude/settings.json',
        'git status', 'echo hi > /tmp/x',
    ])
    def test_allows_reads_and_unrelated(self, proj, profile, cmd):
        r = _hook(proj, 'shell-write-gate.py', {'tool_input': {'command': cmd}}, profile)
        assert r.returncode == 0, (cmd, r.stderr)

    def test_unparseable_fails_closed(self, proj, profile):
        r = subprocess.run([sys.executable, str(proj / '.claude/hooks/shell-write-gate.py')],
                           input='garbage', capture_output=True, text=True,
                           env={**os.environ, **({'ECC_HOOK_PROFILE': profile} if profile else {})})
        assert r.returncode == 2


def _empty_write(proj, path='app.py'):
    return {'tool_name': 'Write', 'tool_input': {'file_path': str(proj / path), 'content': ''}}


def _bash(proj, cmd):
    return {'tool_input': {'command': cmd}, 'cwd': str(proj)}


@pytest.mark.parametrize('profile', PROFILES)
class TestDeleteMarker:
    def test_write_to_empty_needs_marker(self, proj, profile):
        _approve(proj)
        r = _hook(proj, 'plan-gate.sh', _empty_write(proj), profile)
        assert r.returncode == 2 and '(delete)' in r.stderr
        _approve(proj, '`app.py` (delete)')
        assert _hook(proj, 'plan-gate.sh', _empty_write(proj), profile).returncode == 0

    def test_nonempty_write_and_new_file_unchanged(self, proj, profile):
        _approve(proj, '`app.py` `new.py`')
        assert _hook(proj, 'plan-gate.sh', _write_payload(proj), profile).returncode == 0
        assert _hook(proj, 'plan-gate.sh', _empty_write(proj, 'new.py'), profile).returncode == 0

    @pytest.mark.parametrize('cmd', ['rm app.py', 'git rm app.py', 'unlink app.py',
                                     'rm -f -- app.py', 'rm *.py'])
    def test_shell_delete_blocked_then_allowed(self, proj, profile, cmd):
        r = _hook(proj, 'shell-write-gate.py', _bash(proj, cmd), profile)
        assert r.returncode == 2, r.stderr
        _approve(proj, '`app.py` (delete)')
        r = _hook(proj, 'shell-write-gate.py', _bash(proj, cmd), profile)
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize('cmd', ['rm -rf build dist', 'rm src/x.pyc', 'rm -rf /tmp/ck-nope'])
    def test_untracked_deletes_allowed(self, proj, profile, cmd):
        (proj / 'build').mkdir()
        assert _hook(proj, 'shell-write-gate.py', _bash(proj, cmd), profile).returncode == 0

    def test_non_t3_and_no_plans_dir_allowed(self, proj, profile):
        (proj / 'notes.md').write_text('n')
        _git(proj, 'add', '.')
        r = _hook(proj, 'shell-write-gate.py', _bash(proj, 'rm notes.md'), profile)
        assert r.returncode == 0
        import shutil
        shutil.rmtree(proj / '.claude' / 'plans')
        r = _hook(proj, 'shell-write-gate.py', _bash(proj, 'rm app.py'), profile)
        assert r.returncode == 0

    def test_protected_path_still_blocked_with_marker(self, proj, profile):
        _approve(proj, '`app.py` (delete)')
        r = _hook(proj, 'shell-write-gate.py',
                  _bash(proj, 'rm .claude/settings.local.json'), profile)
        assert r.returncode == 2

    def test_hostile_filename_not_injected(self, proj, profile):
        (proj / 'a;touch PWNED;.py').write_text('x')
        _git(proj, 'add', '.')
        r = _hook(proj, 'shell-write-gate.py', _bash(proj, "rm 'a;touch PWNED;.py'"), profile)
        assert r.returncode == 2
        assert not (proj / 'PWNED').exists()

    @pytest.mark.parametrize('cmd', [
        "echo don't; rm app.py", 'sudo -u root rm app.py', 'env rm app.py', '/bin/rm app.py',
        'bash -c "rm app.py"', '(rm app.py)', '{ rm app.py; }', 'git -C . rm app.py',
        'mkdir -p d && cd d && rm ../app.py'])
    def test_review_bypass_forms_blocked(self, proj, profile, cmd):
        (proj / 'd').mkdir(exist_ok=True)
        _git(proj, 'add', '.')
        assert _hook(proj, 'shell-write-gate.py', _bash(proj, cmd), profile).returncode == 2

    def test_large_untracked_dir_and_cached_allowed(self, proj, profile):
        (proj / 'build').mkdir()
        for i in range(250):
            (proj / 'build' / ('f%d.js' % i)).write_text('x')
        _git(proj, 'add', 'app.py')
        for cmd in ('rm -rf build', 'git rm --cached app.py'):
            assert _hook(proj, 'shell-write-gate.py', _bash(proj, cmd), profile).returncode == 0

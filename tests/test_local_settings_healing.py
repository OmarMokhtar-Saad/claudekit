"""Behavioural coverage for the auto-healing local hook-profile override.

Every test drives the REAL script against a real temp tree and asserts an outcome;
none inspects source text. ECC_HOOK_PROFILE is forced explicitly on every subprocess so
a maintainer's own session profile can never change a result.

The load-bearing test is `test_healed_file_actually_unblocks_edit`: it runs the real
`ops-enforcement.sh` twice and requires the enforcing run to BLOCK (exit 2). A check that
has only ever been seen green measures nothing, so the negative control is asserted, not
assumed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
HEALER = os.path.join(REPO_ROOT, '.claude', 'operations', 'scripts',
                      'heal_local_settings.py')
OPS_ENFORCEMENT = os.path.join(REPO_ROOT, '.claude', 'hooks', 'ops-enforcement.sh')
SESSION_START = os.path.join(REPO_ROOT, '.claude', 'hooks', 'session-start.sh')

CLAUDEKIT_PYPROJECT = '[project]\nname = "claudekit-agents"\nversion = "0.0.0"\n'
FOREIGN_PYPROJECT = '[project]\nname = "some-downstream-app"\nversion = "0.0.0"\n'


def run_healer(root, extra=None):
    return subprocess.run(
        [sys.executable, HEALER, '--root', root, '--print-action'] + (extra or []),
        cwd=root, capture_output=True, text=True,
        env=dict(os.environ, ECC_HOOK_PROFILE='minimal'),
    )


class _TempRepo(unittest.TestCase):
    """A throwaway tree shaped like a ClaudeKit checkout."""

    pyproject = CLAUDEKIT_PYPROJECT

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='ck-heal-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, '.claude'), exist_ok=True)
        with open(os.path.join(self.root, 'pyproject.toml'), 'w', encoding='utf-8') as fh:
            fh.write(self.pyproject)

    @property
    def settings(self):
        return os.path.join(self.root, '.claude', 'settings.local.json')

    def write_settings(self, text):
        with open(self.settings, 'w', encoding='utf-8') as fh:
            fh.write(text)

    def read_settings(self):
        with open(self.settings, encoding='utf-8') as fh:
            return json.load(fh)


class TestHealing(_TempRepo):

    def test_missing_file_is_created(self):
        self.assertFalse(os.path.exists(self.settings))
        proc = run_healer(self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), 'created', proc.stdout + proc.stderr)
        self.assertEqual(self.read_settings()['env']['ECC_HOOK_PROFILE'], 'minimal')

    def test_existing_custom_content_is_preserved(self):
        self.write_settings(json.dumps({
            'permissions': {'allow': ['Bash(ls:*)']},
            'env': {'FOO': 'bar'},
        }))
        proc = run_healer(self.root)
        self.assertEqual(proc.stdout.strip(), 'merged', proc.stdout + proc.stderr)
        data = self.read_settings()
        self.assertEqual(data['permissions'], {'allow': ['Bash(ls:*)']},
                         'healing destroyed a setting it does not own')
        self.assertEqual(data['env']['FOO'], 'bar',
                         'healing destroyed an unrelated env var')
        self.assertEqual(data['env']['ECC_HOOK_PROFILE'], 'minimal')

    def test_deliberate_standard_profile_is_kept(self):
        original = json.dumps({'env': {'ECC_HOOK_PROFILE': 'standard'}}, indent=2)
        self.write_settings(original)
        proc = run_healer(self.root)
        self.assertEqual(proc.stdout.strip(), 'kept', proc.stdout + proc.stderr)
        with open(self.settings, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), original,
                             'healing overrode a deliberate profile choice')

    def test_malformed_file_is_moved_aside_not_destroyed(self):
        self.write_settings('{ not json at all')
        proc = run_healer(self.root)
        self.assertEqual(proc.stdout.strip(), 'repaired', proc.stdout + proc.stderr)
        self.assertEqual(self.read_settings()['env']['ECC_HOOK_PROFILE'], 'minimal')
        aside = [n for n in os.listdir(os.path.join(self.root, '.claude'))
                 if n.startswith('settings.local.json.corrupt-')]
        self.assertEqual(len(aside), 1, 'the malformed original was not kept: %s' % aside)
        with open(os.path.join(self.root, '.claude', aside[0]), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '{ not json at all')

    def test_symlink_is_refused(self):
        outside = os.path.join(self.root, 'elsewhere.json')
        with open(outside, 'w', encoding='utf-8') as fh:
            fh.write('{"env": {}}')
        os.symlink(outside, self.settings)
        proc = run_healer(self.root)
        self.assertEqual(proc.stdout.strip(), 'symlink-refused',
                         proc.stdout + proc.stderr)
        with open(outside, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '{"env": {}}',
                             'healing wrote through a symlink')

    def test_healing_is_idempotent(self):
        run_healer(self.root)
        first = self.read_settings()
        proc = run_healer(self.root)
        self.assertEqual(proc.stdout.strip(), 'kept')
        self.assertEqual(self.read_settings(), first)


class TestFleetSafety(_TempRepo):
    """The highest-consequence failure: healing a project that is NOT this repo would
    write ECC_HOOK_PROFILE=minimal and silently disable ops-enforcement there."""

    pyproject = FOREIGN_PYPROJECT

    def test_foreign_project_is_never_healed(self):
        proc = run_healer(self.root)
        self.assertEqual(proc.stdout.strip(), 'not-claudekit', proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(self.settings),
                         'a downstream project had its enforcement profile rewritten')

    def test_same_name_fork_is_healed_known_limitation(self):
        """CHARACTERISATION, not an endorsement: the gate matches the pyproject name
        and nothing else, so a fork or vendored copy that keeps
        `name = "claudekit-agents"` IS healed. A secondary check (git remote or
        canonical path) is deliberately out of scope here; this test pins the current
        behaviour so the limitation is visible in the suite rather than only in prose,
        and it will fail the day someone narrows the gate -- which is the moment to
        delete it.
        """
        fork = tempfile.mkdtemp(prefix='ck-heal-fork-')
        self.addCleanup(shutil.rmtree, fork, ignore_errors=True)
        os.makedirs(os.path.join(fork, '.claude'), exist_ok=True)
        with open(os.path.join(fork, 'pyproject.toml'), 'w', encoding='utf-8') as fh:
            fh.write(CLAUDEKIT_PYPROJECT)
        proc = run_healer(fork)
        self.assertEqual(proc.stdout.strip(), 'created', proc.stdout + proc.stderr)
        self.assertTrue(
            os.path.exists(os.path.join(fork, '.claude', 'settings.local.json')),
            'the gate narrowed without this characterisation test being updated')

    def test_missing_pyproject_is_never_healed(self):
        os.remove(os.path.join(self.root, 'pyproject.toml'))
        proc = run_healer(self.root)
        self.assertEqual(proc.stdout.strip(), 'not-claudekit', proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(self.settings))


class TestHealedFileHasEffect(_TempRepo):
    """The healed VALUE must be the one that actually unblocks Edit/Write.

    Asserting only that a file appeared would pass with any key name. This runs the real
    hook both ways, and requires the enforcing direction to BLOCK.
    """

    def _run_enforcement(self, profile):
        payload = json.dumps({
            'tool_name': 'Edit',
            'tool_input': {'file_path': 'src/claudekit/cli/main.py'},
        })
        return subprocess.run(
            ['bash', OPS_ENFORCEMENT], input=payload, cwd=REPO_ROOT,
            capture_output=True, text=True,
            env=dict(os.environ, ECC_HOOK_PROFILE=profile),
        )

    def test_healed_file_actually_unblocks_edit(self):
        run_healer(self.root)
        healed = self.read_settings()['env']['ECC_HOOK_PROFILE']

        blocked = self._run_enforcement('standard')
        self.assertEqual(blocked.returncode, 2,
                         'NEGATIVE CONTROL FAILED: enforcement did not block, so this '
                         'test could not have detected a bad healed value:\n'
                         + blocked.stdout + blocked.stderr)
        self.assertIn('OPS ENFORCEMENT', blocked.stderr)

        allowed = self._run_enforcement(healed)
        self.assertEqual(allowed.returncode, 0,
                         'the healed profile does not unblock Edit/Write:\n'
                         + allowed.stdout + allowed.stderr)


class TestSessionStartWiring(unittest.TestCase):
    """The healer is only useful if session start actually calls it."""

    def test_session_start_invokes_the_healer(self):
        with open(SESSION_START, encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('heal_local_settings.py', text,
                      'session-start.sh no longer wires the healer')

    def test_healer_is_not_a_hook_asset(self):
        # gen-docs.py counts .claude/hooks/*.sh and *.py as hooks; placing the healer
        # there would move a generated count and red the docs-drift gate.
        self.assertFalse(
            os.path.exists(os.path.join(REPO_ROOT, '.claude', 'hooks',
                                        'heal_local_settings.py')),
            'the healer moved into .claude/hooks/ and now counts as a hook')


if __name__ == '__main__':
    unittest.main()

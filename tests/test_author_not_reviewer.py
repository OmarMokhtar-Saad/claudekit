"""Behavioural coverage for the runtime author != reviewer gate.

CLAUDE.md's review floor ("fresh code-reviewer instance, never the author") was
prompt-enforced only, and the quality-gates section conceded it. These tests drive the
REAL scripts against a real temp tree and assert outcomes; none inspects source text.

Three disciplines this repo learned the hard way are applied here:

  * REAL executions, never --dry-run. The executor skips check_approval entirely when
    nothing will be written, so a dry run cannot exercise the gate at all.
  * A demonstrated FAILURE, not only a pass. `test_self_review_refuses_execution` and
    `test_distinct_reviewer_authorises_execution` differ in exactly one byte-level fact --
    the reviewer's session id -- so removing the comparison in cmd_check flips the first
    from a refusal to an execution and the test fails loudly.
  * ECC_HOOK_PROFILE is forced per subprocess, so a maintainer's session profile cannot
    change a result.

Identity is supplied through CLAUDEKIT_SESSION_ID, which review-record.py's _session_id
accepts directly; the tests therefore do not depend on SessionStart pointers existing.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCRIPTS = os.path.join(REPO_ROOT, '.claude', 'operations', 'scripts')
REVIEW_RECORD = os.path.join(SCRIPTS, 'review-record.py')
EXECUTOR = os.path.join(SCRIPTS, 'execute-json-ops.py')

SESSION_A = '11111111-2222-3333-4444-555555555555'
SESSION_B = '66666666-7777-8888-9999-aaaaaaaaaaaa'
SELF_REVIEW_EXIT = 6


def _run(args, cwd, session=None):
    env = dict(os.environ, ECC_HOOK_PROFILE='minimal')
    env.pop('CLAUDE_SESSION_ID', None)
    env.pop('CLAUDEKIT_SESSION_ID', None)
    if session:
        env['CLAUDEKIT_SESSION_ID'] = session
    return subprocess.run([sys.executable] + args, cwd=cwd,
                          capture_output=True, text=True, env=env)


class _TempProject(unittest.TestCase):
    """A throwaway tree with the layout the scripts expect."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='ck-authgate-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for rel in (('.claude', 'plans'), ('.claude', 'reports', 'reviews')):
            os.makedirs(os.path.join(self.root, *rel), exist_ok=True)
        self.plan = self._write_plan('plan-gate.md')
        self.ops = self._write_ops('plan-gate.ops.json')

    def _plans(self, *parts):
        return os.path.join(self.root, '.claude', 'plans', *parts)

    def _write_plan(self, name):
        path = self._plans(name)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('# plan\n\n- payload.txt\n')
        return path

    def _write_ops(self, name):
        target = os.path.join(self.root, 'payload.txt')
        with open(target, 'w', encoding='utf-8') as fh:
            fh.write('alpha\n')
        config = {
            'plan': 'gate',
            'operations': [{
                'type': 'code_edit',
                'path': 'payload.txt',
                'edits': [{'find': 'alpha', 'replace': 'ALPHA'}],
            }],
        }
        path = self._plans(name)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(config, fh, indent=2)
            fh.write('\n')
        return path

    # -- helpers -----------------------------------------------------------
    def record_author(self, session):
        proc = _run([REVIEW_RECORD, 'author', self.ops], self.root, session=session)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def record_verdict(self, session, score=95, decision='APPROVED'):
        proc = _run([REVIEW_RECORD, 'write', self.plan, self.ops,
                     '--score', str(score), '--decision', decision],
                    self.root, session=session)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def check(self, session=None):
        return _run([REVIEW_RECORD, 'check', self.plan, self.ops], self.root,
                    session=session)

    def execute(self):
        return _run([EXECUTOR, self.ops], self.root)

    def payload(self):
        with open(os.path.join(self.root, 'payload.txt'), encoding='utf-8') as fh:
            return fh.read()


class TestSelfReview(_TempProject):

    def test_self_review_refuses_execution(self):
        """The failure case: one session authored AND approved this config."""
        self.record_author(SESSION_A)
        self.record_verdict(SESSION_A)

        checked = self.check()
        self.assertEqual(checked.returncode, SELF_REVIEW_EXIT,
                         'a self-reviewed verdict authorised execution:\n'
                         + checked.stdout + checked.stderr)
        self.assertIn('SELF-REVIEW', checked.stderr)

        # A REAL execution, deliberately not --dry-run: the executor skips the
        # approval gate entirely when nothing will be written.
        ran = self.execute()
        self.assertNotEqual(ran.returncode, 0,
                            'the executor applied a self-reviewed config:\n'
                            + ran.stdout + ran.stderr)
        self.assertIn('alpha', self.payload(),
                      'the self-reviewed edit was applied anyway')

    def test_distinct_reviewer_authorises_execution(self):
        """Positive control: identical setup, one different session id."""
        self.record_author(SESSION_A)
        self.record_verdict(SESSION_B)

        checked = self.check()
        self.assertEqual(checked.returncode, 0,
                         'an independently reviewed config was refused:\n'
                         + checked.stdout + checked.stderr)
        ran = self.execute()
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn('ALPHA', self.payload(), 'the approved edit never applied')

    def test_self_review_is_not_reported_as_drift(self):
        """Exit 2 means DRIFT and exit 4 means a rejecting verdict; neither is true
        here, and reporting either would send the operator to the wrong remedy."""
        self.record_author(SESSION_A)
        self.record_verdict(SESSION_A)
        checked = self.check()
        self.assertNotIn('DRIFT', checked.stderr)
        self.assertNotIn('NOT APPROVED', checked.stderr)

    def test_rejecting_verdict_still_reports_its_own_cause(self):
        """Ordering pin: the self-review test must not mask a real rejection."""
        self.record_author(SESSION_A)
        self.record_verdict(SESSION_A, score=70, decision='REVISE')
        checked = self.check()
        self.assertEqual(checked.returncode, 4,
                         'a rejecting verdict was reported as a self-review:\n'
                         + checked.stderr)


class TestBackwardCompatibility(_TempProject):

    def test_unknown_identity_does_not_block(self):
        """No author sidecar (every record written before this change): the gate must
        stay open and SAY that it did not bind."""
        self.record_verdict(SESSION_A)
        checked = self.check()
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn('did not bind', checked.stderr.lower(),
                      'the gate was silently inert; the limitation must be printed:\n'
                      + checked.stderr)
        self.assertEqual(self.execute().returncode, 0)

    def test_unresolvable_sessions_do_not_block(self):
        """Both sides record "unknown" -- today's normal condition, since nothing
        exports the session env vars. Two unknowns are not a proven match."""
        self.record_author(None)
        self.record_verdict(None)
        checked = self.check()
        self.assertEqual(checked.returncode, 0,
                         'two unresolved identities were treated as the same person:\n'
                         + checked.stdout + checked.stderr)


class TestHashIsUnmoved(_TempProject):
    """The recorded trap: anything written into the ops.json after a verdict reads as
    DRIFT and deadlocks the gate. Authorship is a sidecar for exactly this reason."""

    def _sha(self):
        with open(self.ops, 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def test_author_sidecar_never_touches_the_ops_json(self):
        before = self._sha()
        self.record_author(SESSION_A)
        self.assertEqual(self._sha(), before,
                         'recording authorship rewrote the ops.json')
        self.record_verdict(SESSION_B)
        self.assertEqual(self._sha(), before,
                         'recording the verdict rewrote the ops.json')
        self.assertEqual(self.check().returncode, 0)

    def test_sidecar_lands_beside_the_record(self):
        self.record_author(SESSION_A)
        sidecar = os.path.join(self.root, '.claude', 'reports', 'reviews',
                               'gate.author.json')
        self.assertTrue(os.path.exists(sidecar),
                        'the author sidecar was not keyed by the ops slug')
        with open(sidecar, encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['session'], SESSION_A)

    def test_first_known_author_wins(self):
        self.record_author(SESSION_A)
        self.record_author(SESSION_B)
        sidecar = os.path.join(self.root, '.claude', 'reports', 'reviews',
                               'gate.author.json')
        with open(sidecar, encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['session'], SESSION_A,
                             'a second session overwrote the recorded author, which '
                             'would let an author launder their own review')


if __name__ == '__main__':
    unittest.main()

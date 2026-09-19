"""Behavioural coverage for the runtime author != reviewer identity gate.

Replaces tests/test_author_not_reviewer.py, whose session-identity assertions pinned a
model that could not work: review-record.py's _session_id resolves a subagent to its
PARENT session, so the author (main agent stamping the baseline) and the reviewer (main
agent recording a reviewer subagent's verdict) always collided and the gate refused every
legitimate run.

The identity axis here is the agent ROLE the caller asserts. That makes this ATTESTATION,
not enforcement: nothing observes which agent produced the verdict text, so a caller may
assert a role it does not have. What the tests pin is that the refusal fires on a
positively asserted non-reviewing role, that it never fires on absent data, and that an
independent role still executes.

Three disciplines this repo learned the hard way are applied:

  * REAL executions, never --dry-run. The executor skips check_approval entirely when
    nothing will be written, so a dry run cannot exercise the gate at all.
  * A demonstrated FAILURE, not only a pass. The refusal and authorisation tests differ in
    exactly one asserted role, so deleting the comparison in cmd_check flips the first from
    a refusal to an execution and the test fails loudly.
  * ECC_HOOK_PROFILE is forced per subprocess, so a maintainer's session profile cannot
    change a result.
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
VALIDATOR = os.path.join(SCRIPTS, 'validate-config-json.py')
EXECUTOR = os.path.join(SCRIPTS, 'execute-json-ops.py')

SESSION_A = '11111111-2222-3333-4444-555555555555'
SESSION_B = '66666666-7777-8888-9999-aaaaaaaaaaaa'
SELF_REVIEW_EXIT = 6


def _run(args, cwd, session=None):
    env = dict(os.environ, ECC_HOOK_PROFILE='minimal')
    env.pop('CLAUDE_SESSION_ID', None)
    env.pop('CLAUDEKIT_SESSION_ID', None)
    env.pop('CLAUDEKIT_AGENT_ROLE', None)
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
    def record_author(self, session, role=None):
        args = [REVIEW_RECORD, 'author', self.ops]
        if role:
            args += ['--author-role', role]
        proc = _run(args, self.root, session=session)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def record_verdict(self, session, score=95, decision='APPROVED', role=None):
        args = [REVIEW_RECORD, 'write', self.plan, self.ops,
                '--score', str(score), '--decision', decision]
        if decision == 'APPROVED':
            args.append('--owner-approved')
        if role:
            args += ['--reviewer-role', role]
        proc = _run(args, self.root, session=session)
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

    def sidecar(self):
        path = os.path.join(self.root, '.claude', 'reports', 'reviews',
                            'gate.author.json')
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)

    def record(self):
        path = os.path.join(self.root, '.claude', 'reports', 'reviews', 'gate.json')
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)


class TestRoleComparison(_TempProject):

    def test_author_role_reviewing_itself_is_refused(self):
        """The failure case: the verdict is attributed to the authoring role."""
        self.record_author(SESSION_A, role='author')
        self.record_verdict(SESSION_B, role='author')

        checked = self.check()
        self.assertEqual(checked.returncode, SELF_REVIEW_EXIT,
                         'a self-attributed verdict authorised execution:\n'
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

    def test_reviewer_role_authorises_execution(self):
        """Positive control: identical setup, one different asserted role."""
        self.record_author(SESSION_A, role='author')
        self.record_verdict(SESSION_B, role='reviewer')

        checked = self.check()
        self.assertEqual(checked.returncode, 0,
                         'an independently reviewed config was refused:\n'
                         + checked.stdout + checked.stderr)
        ran = self.execute()
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn('ALPHA', self.payload(), 'the approved edit never applied')

    def test_same_session_no_longer_blocks(self):
        """Regression test for the shipped defect: the whole pipeline runs in ONE
        session, so one session id on both sides must not refuse."""
        self.record_author(SESSION_A, role='author')
        self.record_verdict(SESSION_A, role='code-reviewer')
        checked = self.check()
        self.assertEqual(checked.returncode, 0,
                         'one session on both sides still refuses:\n'
                         + checked.stdout + checked.stderr)
        self.assertEqual(self.execute().returncode, 0)
        self.assertIn('ALPHA', self.payload())

    def test_role_refusal_is_not_called_enforcement(self):
        """Honesty pin: this is attestation. A caller can assert any role, and the
        refusal text must not claim more than it does."""
        self.record_author(SESSION_A, role='author')
        self.record_verdict(SESSION_B, role='author')
        stderr = self.check().stderr.lower()
        self.assertIn('attest', stderr)
        self.assertNotIn('enforc', stderr)

    def test_self_review_is_not_reported_as_drift(self):
        """Exit 2 means DRIFT and exit 4 means a rejecting verdict; neither is true
        here, and reporting either would send the operator to the wrong remedy."""
        self.record_author(SESSION_A, role='author')
        self.record_verdict(SESSION_B, role='author')
        checked = self.check()
        self.assertNotIn('DRIFT', checked.stderr)
        self.assertNotIn('NOT APPROVED', checked.stderr)

    def test_rejecting_verdict_still_reports_its_own_cause(self):
        """Ordering pin: the role check must not mask a real rejection."""
        self.record_author(SESSION_A, role='author')
        self.record_verdict(SESSION_B, score=70, decision='REVISE', role='author')
        checked = self.check()
        self.assertEqual(checked.returncode, 4,
                         'a rejecting verdict was reported as a self-review:\n'
                         + checked.stderr)


class TestRoleIsRecorded(_TempProject):

    def test_role_is_recorded_in_both_artifacts(self):
        self.record_author(SESSION_A, role='author')
        self.record_verdict(SESSION_B, role='reviewer')
        self.assertEqual(self.sidecar().get('role'), 'author')
        self.assertEqual(self.record().get('reviewer_role'), 'reviewer')

    def test_stamp_baseline_records_the_author_role(self):
        """--stamp-baseline is the real author-side writer; it must assert a role."""
        proc = _run([VALIDATOR, self.ops, '--stamp-baseline'], self.root,
                    session=SESSION_A)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.sidecar().get('role'), 'author',
                         'stamping recorded no author role, so the gate cannot bind')

    def test_an_unparseable_role_is_recorded_as_unknown(self):
        """Never invented: a role that is not a plain slug is refused, not guessed."""
        self.record_author(SESSION_A, role='NOT A ROLE!!')
        self.assertEqual(self.sidecar().get('role'), 'unknown')


class TestBackwardCompatibility(_TempProject):

    def test_missing_reviewer_role_does_not_block(self):
        """Every record written before this change carries no role. The gate must stay
        open and SAY that it did not bind -- this is what keeps already-approved plans
        executable without a re-review."""
        self.record_author(SESSION_A)
        self.record_verdict(SESSION_A)
        checked = self.check()
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn('did not bind', checked.stderr.lower(),
                      'the gate was silently inert; the limitation must be printed:\n'
                      + checked.stderr)
        self.assertEqual(self.execute().returncode, 0)
        self.assertIn('ALPHA', self.payload())

    def test_no_author_sidecar_does_not_block(self):
        self.record_verdict(SESSION_A, role='reviewer')
        checked = self.check()
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(self.execute().returncode, 0)


class TestHashIsUnmoved(_TempProject):
    """The recorded trap: anything written into the ops.json after a verdict reads as
    DRIFT and deadlocks the gate. Identity is a sidecar for exactly this reason."""

    def _sha(self):
        with open(self.ops, 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def test_author_sidecar_never_touches_the_ops_json(self):
        before = self._sha()
        self.record_author(SESSION_A, role='author')
        self.assertEqual(self._sha(), before,
                         'recording authorship rewrote the ops.json')
        self.record_verdict(SESSION_B, role='reviewer')
        self.assertEqual(self._sha(), before,
                         'recording the verdict rewrote the ops.json')
        self.assertEqual(self.check().returncode, 0)

    def test_sidecar_lands_beside_the_record(self):
        self.record_author(SESSION_A, role='author')
        sidecar = os.path.join(self.root, '.claude', 'reports', 'reviews',
                               'gate.author.json')
        self.assertTrue(os.path.exists(sidecar),
                        'the author sidecar was not keyed by the ops slug')
        with open(sidecar, encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['session'], SESSION_A)

    def test_first_known_author_wins(self):
        self.record_author(SESSION_A, role='author')
        self.record_author(SESSION_B, role='reviewer')
        data = self.sidecar()
        self.assertEqual(data['session'], SESSION_A,
                         'a second caller overwrote the recorded author, which '
                         'would let an author launder their own review')
        self.assertEqual(data['role'], 'author',
                         'a second caller overwrote the recorded author ROLE')


if __name__ == '__main__':
    unittest.main()

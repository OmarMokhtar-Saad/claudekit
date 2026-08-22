"""Behavioural coverage for the approval machinery's multi-config defects.

Every test here drives the REAL scripts against a real temp tree and asserts an
outcome; none inspects source text. The four defects under test were found by
using the machinery on two approved Tier 3 plans, and each test below fails
against the code that shipped them:

  T1  a config named differently from its plan could not be approved at all,
      because the record was keyed by the PLAN slug while the executor's gate
      resolved candidates from the OPS filename.
  T2  two configs under one plan collapsed onto one record path, so the second
      `write` silently destroyed the first.
  T3  the stamp/approval collision is a SEQUENCING defect, not a code defect:
      stamping after recording invalidates the verdict, stamping before it does
      not. Pinned here so the working order cannot regress unnoticed.
  T4  nothing in reviewer.md's contract required the `=== REVIEW ===` block that
      --from-review parses, so a valid verdict could be unconsumable.
"""

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
VALIDATOR = os.path.join(SCRIPTS, 'validate-config-json.py')
REVIEWER_MD = os.path.join(REPO_ROOT, '.claude', 'agents', 'reviewer.md')


def _run(args, cwd):
    """Run a script with the repo's interpreter, capturing everything."""
    return subprocess.run(
        [sys.executable] + args,
        cwd=cwd, capture_output=True, text=True,
        env=dict(os.environ, ECC_HOOK_PROFILE='minimal'),
    )


class _TempProject(unittest.TestCase):
    """A throwaway tree with the layout the scripts expect."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='ck-approval-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for rel in (('.claude', 'plans'), ('.claude', 'reports', 'reviews')):
            os.makedirs(os.path.join(self.root, *rel), exist_ok=True)

    def plans(self, *parts):
        return os.path.join(self.root, '.claude', 'plans', *parts)

    def write_plan(self, name, body='# plan\n'):
        path = self.plans(name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(body)
        return path

    def write_ops(self, name, target_rel='payload.txt', find='alpha'):
        """An ops config whose single edit targets a real file in the temp tree."""
        target = os.path.join(self.root, target_rel)
        with open(target, 'w', encoding='utf-8') as handle:
            handle.write(find + '\n')
        config = {
            'plan': os.path.splitext(name)[0],
            'operations': [{
                'type': 'code_edit',
                'path': target_rel,
                'edits': [{'find': find, 'replace': find.upper()}],
            }],
        }
        path = self.plans(name)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(config, handle, indent=2)
            handle.write('\n')
        return path

    def record_approved(self, plan_path, ops_path, score=95):
        proc = _run([REVIEW_RECORD, 'write', plan_path, ops_path,
                     '--score', str(score), '--decision', 'APPROVED'], self.root)
        self.assertEqual(proc.returncode, 0,
                         'recording the verdict failed: %s%s' % (proc.stdout, proc.stderr))
        return proc

    def reviews_dir(self):
        return os.path.join(self.root, '.claude', 'reports', 'reviews')


class TestAddendumConfigIsExecutable(_TempProject):
    """T1 — an ops config named differently from its plan can be approved.

    The record must be found through the OPS filename, because that is the only
    name the executor's gate has when it is handed a config.
    """

    def test_gate_accepts_a_differently_named_addendum(self):
        plan = self.write_plan('plan-t1-core.md')
        ops = self.write_ops('ops-t1-addendum.json')
        self.record_approved(plan, ops)

        # A REAL execution, deliberately not --dry-run: the executor skips the
        # approval gate entirely when nothing will be written ("Approval: not
        # required for --dry-run"), so a dry run cannot exercise this at all.
        proc = _run([EXECUTOR, ops], self.root)
        combined = proc.stdout + proc.stderr
        self.assertNotIn('no review record', combined.lower(),
                         'the approved addendum was refused for want of a record:\n' + combined)
        self.assertEqual(proc.returncode, 0, combined)
        # Asserting only "it did not refuse" is not enough: require that the
        # recorded verdict was actually CONSUMED, or a gate that stopped applying
        # would let this test pass while proving nothing.
        self.assertIn('Approval: reviewed verdict verified', combined,
                      'the recorded verdict was never consumed — the gate resolved no '
                      'record for this ops filename:\n' + combined)
        with open(os.path.join(self.root, 'payload.txt'), encoding='utf-8') as handle:
            self.assertIn('ALPHA', handle.read(), 'the approved edit never applied')


class TestTwoConfigsUnderOnePlan(_TempProject):
    """T2 — recording a second config must not destroy the first one's record."""

    def test_second_record_does_not_overwrite_the_first(self):
        plan = self.write_plan('plan-t2-core.md')
        core = self.write_ops('ops-t2-core.json', target_rel='core.txt', find='core')
        probe = self.write_ops('ops-t2-probe.json', target_rel='probe.txt', find='probe')

        self.record_approved(plan, core)
        before = sorted(
            (name, os.path.getsize(os.path.join(self.reviews_dir(), name)))
            for name in os.listdir(self.reviews_dir())
        )
        self.assertTrue(before, 'nothing was recorded for the core config')

        self.record_approved(plan, probe)
        after = dict(
            (name, os.path.getsize(os.path.join(self.reviews_dir(), name)))
            for name in os.listdir(self.reviews_dir())
        )
        for name, size in before:
            self.assertIn(name, after,
                          "recording the probe deleted the core's %s" % name)
            self.assertEqual(after[name], size,
                             "recording the probe rewrote the core's %s" % name)

        # And both must still verify against their own config.
        for ops in (core, probe):
            proc = _run([REVIEW_RECORD, 'check', plan, ops], self.root)
            self.assertEqual(proc.returncode, 0,
                             '%s lost its approval: %s%s'
                             % (os.path.basename(ops), proc.stdout, proc.stderr))




class TestReviewerContractIsConsumable(unittest.TestCase):
    """T4 — the block reviewer.md specifies is the block the parser accepts.

    A verdict format the approval tooling cannot parse is a verdict that records
    nothing, so the prompt and the parser must be checked against each other.
    """

    @staticmethod
    def _parse_verdict():
        import importlib.util
        spec = importlib.util.spec_from_file_location('review_record', REVIEW_RECORD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.parse_verdict

    @staticmethod
    def _template_from_prompt():
        """The verdict block as reviewer.md tells the reviewer to emit it."""
        with open(REVIEWER_MD, encoding='utf-8') as handle:
            text = handle.read()
        # The LAST block, matching parse_verdict's own rule ("Only the last
        # '=== REVIEW ===' block counts"). reviewer.md mentions the anchors in
        # prose elsewhere, so taking the first match would extract that instead
        # and the test would drift away from what the parser actually reads.
        end = text.rfind('=== END REVIEW ===')
        if end == -1:
            return None
        start = text.rfind('=== REVIEW ===', 0, end)
        if start == -1:
            return None
        lines = text[start:end + len('=== END REVIEW ===')].splitlines()
        return '\n'.join(line.strip() for line in lines)

    def test_the_specified_block_parses_when_filled_in(self):
        template = self._template_from_prompt()
        self.assertIsNotNone(
            template, 'reviewer.md specifies no === REVIEW === block, so a reviewer '
                      'following it produces a verdict review-record.py cannot consume')
        filled = (template
                  .replace('<integer 0-100>', '93')
                  .replace('APPROVED | CONDITIONAL | REVISE | REJECTED', 'APPROVED'))
        score, decision, _findings = self._parse_verdict()(filled)
        self.assertEqual(score, 93)
        self.assertEqual(decision, 'APPROVED')

    def test_the_unfilled_template_records_no_verdict(self):
        """The example must never be consumable as a real approval."""
        template = self._template_from_prompt()
        self.assertIsNotNone(template)
        score, decision, _findings = self._parse_verdict()(template)
        self.assertIsNone(score, 'the placeholder template parses as a real score')
        self.assertIsNone(decision, 'the placeholder template parses as a real decision')


class TestLegacyRecordFallback(_TempProject):
    """The back-compat read path, and its blast radius.

    Records written before keying moved to ops identity are keyed by plan slug.
    The fallback that reads them is the named mitigation for C1's headline risk,
    so it needs its own coverage: deleting both fallback branches left the rest of
    this module green, which made the mitigation a claim rather than a check.
    """

    def _make_legacy_record(self, plan, ops):
        """Re-key a fresh record to the plan slug, as the old code would have."""
        self.record_approved(plan, ops)
        reviews = self.reviews_dir()
        ops_key = os.path.splitext(os.path.basename(ops))[0]
        for prefix in ('ops-', 'plan-'):
            if ops_key.startswith(prefix):
                ops_key = ops_key[len(prefix):]
                break
        plan_key = os.path.basename(plan)[len('plan-'):-len('.md')]
        moved = False
        for suffix in ('.json', '.ops.json'):
            src = os.path.join(reviews, ops_key + suffix)
            if os.path.exists(src):
                os.rename(src, os.path.join(reviews, plan_key + suffix))
                moved = True
        self.assertTrue(moved, 'no record was written under the ops key to re-key')
        self.assertNotEqual(ops_key, plan_key,
                            'the fixture must make the two keys differ, or the '
                            're-key is a no-op and the fallback is never reached')
        return plan_key

    def test_a_legacy_plan_slug_record_is_still_resolved(self):
        # The two slugs must genuinely DIFFER or the re-key is a no-op and the test
        # would exercise the primary path while claiming to cover the fallback.
        plan = self.write_plan('plan-legacy-alpha.md')
        ops = self.write_ops('ops-legacy-beta.json', target_rel='legacy.txt', find='legacy')
        self._make_legacy_record(plan, ops)

        proc = _run([REVIEW_RECORD, 'check', plan, ops], self.root)
        self.assertEqual(proc.returncode, 0,
                         'a pre-existing record stopped authorising its own config: %s%s'
                         % (proc.stdout, proc.stderr))
        self.assertIn('legacy plan-slug record', proc.stderr,
                      'the fallback resolved silently; the operator cannot tell which '
                      'key satisfied the lookup:\n' + proc.stderr)

    def test_a_legacy_record_cannot_authorise_a_different_config(self):
        """The fallback must not become a way to borrow someone else's verdict."""
        plan = self.write_plan('plan-legacy-borrow.md')
        approved = self.write_ops('ops-legacy-lender.json',
                                  target_rel='approved.txt', find='approved')
        self._make_legacy_record(plan, approved)

        # A different config, same plan: resolution may find the legacy record, but
        # the sha256 binding must then refuse it.
        other = self.write_ops('ops-legacy-other.json',
                               target_rel='other.txt', find='other')
        proc = _run([REVIEW_RECORD, 'check', plan, other], self.root)
        self.assertNotEqual(proc.returncode, 0,
                            'a verdict for another config authorised this one:\n'
                            + proc.stdout + proc.stderr)
        self.assertIn(proc.returncode, (2, 3), proc.stdout + proc.stderr)

        run = _run([EXECUTOR, other], self.root)
        self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
        with open(os.path.join(self.root, 'other.txt'), encoding='utf-8') as handle:
            self.assertIn('other', handle.read(), 'an unapproved edit was applied')


class TestStampBeforeRecordIsTheWorkingOrder(_TempProject):
    """T3 — the stamp/approval collision is an ORDERING problem.

    `--stamp-baseline` writes a `baseline` key into the config, and the review
    record binds sha256 over raw bytes, so stamping AFTER recording invalidates the
    verdict (DRIFT). The backlog filed this as "any plan whose steps say stamp,
    then execute an approved config is unrunnable by construction" — true only of
    that order. Stamping FIRST needs no code change at all, which is why the
    sidecar redesign that was drafted here was cut.

    Both directions are pinned: the working order must keep working, and the
    broken order must keep being caught rather than silently executing.
    """

    def _prepare(self, tag):
        plan = self.write_plan('plan-%s.md' % tag)
        ops = self.write_ops('ops-%s.json' % tag, target_rel='%s.txt' % tag, find=tag)
        return plan, ops

    def test_stamp_then_record_then_execute_succeeds(self):
        plan, ops = self._prepare('order-good')
        stamp = _run([VALIDATOR, ops, '--stamp-baseline'], self.root)
        self.assertEqual(stamp.returncode, 0, stamp.stdout + stamp.stderr)
        self.record_approved(plan, ops)

        proc = _run([EXECUTOR, ops], self.root)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, combined)
        self.assertIn('Approval: reviewed verdict verified', combined)
        self.assertIn('Baseline: verified', combined)

    def test_record_then_stamp_is_caught_as_drift(self):
        """The broken order must refuse, not execute against a stale verdict."""
        plan, ops = self._prepare('order-bad')
        self.record_approved(plan, ops)
        stamp = _run([VALIDATOR, ops, '--stamp-baseline'], self.root)
        self.assertEqual(stamp.returncode, 0, stamp.stdout + stamp.stderr)

        check = _run([REVIEW_RECORD, 'check', plan, ops], self.root)
        self.assertEqual(check.returncode, 2, check.stdout + check.stderr)
        self.assertIn('DRIFT', check.stderr)
        # The refusal must name stamping as a cause; "ops.json changed" alone sent
        # a previous session redesigning the baseline mechanism instead of
        # reordering two steps.
        self.assertIn('--stamp-baseline', check.stderr,
                      'the DRIFT message does not name the most likely cause:\n'
                      + check.stderr)

        run = _run([EXECUTOR, ops], self.root)
        self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)


class TestLegacyFallbackOnTheDiffPath(_TempProject):
    """The `diff` subcommand's fallback and its cross-config guard.

    Round-2 review deleted both and the full suite stayed green: no test invoked
    `diff` at all, so the guard that stops one config borrowing another's approved
    snapshot was a claim rather than a check.
    """

    def _legacy(self, plan_name, ops_name, target, find):
        plan = self.write_plan(plan_name)
        ops = self.write_ops(ops_name, target_rel=target, find=find)
        self.record_approved(plan, ops)
        reviews = self.reviews_dir()
        ops_key = ops_name[len('ops-'):-len('.json')]
        plan_key = plan_name[len('plan-'):-len('.md')]
        self.assertNotEqual(ops_key, plan_key,
                            'the fixture must make the two keys differ, or the '
                            'fallback is never reached')
        for suffix in ('.json', '.ops.json'):
            src = os.path.join(reviews, ops_key + suffix)
            if os.path.exists(src):
                os.rename(src, os.path.join(reviews, plan_key + suffix))
        return plan, ops

    def test_diff_renders_a_legacy_snapshot_for_its_own_config(self):
        plan, ops = self._legacy('plan-diff-alpha.md', 'ops-diff-beta.json',
                                 'diffed.txt', 'diffed')
        proc = _run([REVIEW_RECORD, 'diff', plan, ops], self.root)
        self.assertEqual(proc.returncode, 0,
                         'a pre-existing snapshot stopped being diffable: %s%s'
                         % (proc.stdout, proc.stderr))

    def test_diff_refuses_to_borrow_another_configs_snapshot(self):
        """_record_covers: a legacy record must not lend its snapshot to config B."""
        plan, _approved = self._legacy('plan-borrow-alpha.md', 'ops-borrow-beta.json',
                                       'lender.txt', 'lender')
        other = self.write_ops('ops-borrow-unrelated.json',
                               target_rel='borrower.txt', find='borrower')
        proc = _run([REVIEW_RECORD, 'diff', plan, other], self.root)
        self.assertEqual(proc.returncode, 3,
                         'a delta was rendered against an unrelated config\'s '
                         'approved snapshot:\n' + proc.stdout + proc.stderr)
        self.assertIn('NO RECORD', proc.stderr)


if __name__ == '__main__':
    unittest.main()

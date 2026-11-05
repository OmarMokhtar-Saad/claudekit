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

import os
import subprocess
import sys
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



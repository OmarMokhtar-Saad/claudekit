"""`ck doctor` grades an install instead of only passing or failing it.

Pass/fail cannot distinguish a bare install that clears the floor from a fully
configured one, so every kitted project reads identically green and `/adapt`
has no numeric exit gate. The score supplies one; these tests pin both the
arithmetic and the gate's interaction with the existing exit codes.
"""
import inspect
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from claudekit.cli.main import _readiness_score  # noqa: E402


def ck(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "claudekit.cli.main", *args],
        capture_output=True, text=True, cwd=cwd or str(ROOT),
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")), timeout=300)


class TestReadinessScore(unittest.TestCase):
    """The arithmetic, pinned at its boundaries."""

    def test_all_passing_is_full_marks(self):
        self.assertEqual(100, _readiness_score(12, 0, 0))

    def test_all_failing_is_zero(self):
        self.assertEqual(0, _readiness_score(0, 0, 7))

    def test_no_checks_at_all_is_not_a_division_by_zero(self):
        self.assertEqual(100, _readiness_score(0, 0, 0))

    def test_a_warning_is_half_credit(self):
        # One clean check and one warned check: the warning must move the number
        # without zeroing it, because a warning is a deficiency, not a breakage.
        self.assertEqual(75, _readiness_score(1, 1, 0))

    def test_a_failure_outweighs_a_warning(self):
        self.assertLess(_readiness_score(1, 0, 1), _readiness_score(1, 1, 0))

    def test_skipped_checks_cannot_reach_the_score(self):
        # The contract is structural, not arithmetic: a check that does not apply
        # to this install must be unable to influence the number at all, and the
        # only way to guarantee that is for the function to have nowhere to put
        # it. Asserting on values would be vacuous -- there is no skipped input
        # to vary -- so this pins the signature that makes the guarantee.
        params = list(inspect.signature(_readiness_score).parameters)
        self.assertEqual(["passed", "warned", "failed"], params)


class TestScoreReporting(unittest.TestCase):

    def test_doctor_prints_a_readiness_line(self):
        self.assertIn("Readiness:", ck("doctor").stdout)


class TestMinScoreGate(unittest.TestCase):

    def setUp(self):
        if ck("doctor").returncode != 0:
            self.skipTest("this checkout's doctor is not healthy; "
                          "the floor's interaction with a PASS cannot be tested")

    def test_a_floor_the_install_clears_still_exits_zero(self):
        self.assertEqual(0, ck("doctor", "--min-score", "0").returncode)

    def test_an_unreachable_floor_fails_and_names_both_numbers(self):
        result = ck("doctor", "--min-score", "101")
        self.assertEqual(1, result.returncode)
        self.assertIn("below the required minimum", result.stderr)
        self.assertIn("101", result.stderr)


class TestMinScoreCannotMaskAFailure(unittest.TestCase):

    def test_a_satisfied_floor_does_not_rescue_a_broken_install(self):
        # A floor of 0 is satisfied by definition. A directory with no .claude/
        # still has to fail, because --min-score may only ADD failures.
        target = tempfile.mkdtemp(prefix="ck-score-bare-")
        self.addCleanup(lambda: __import__("shutil").rmtree(target, True))
        result = ck("doctor", "--min-score", "0", cwd=target)
        self.assertEqual(1, result.returncode, result.stdout)


if __name__ == "__main__":
    unittest.main()

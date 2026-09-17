"""Pipeline session-hygiene rules (2026-09-16 findings) are present in the prompts.

STRUCTURE TESTS, named honestly: these assert that prompt TEXT exists. They cannot
prove any agent obeys it -- no test in this repo can, because the reader is a model.
They exist so a future edit cannot silently delete a rule that was added in response
to a measured incident:

  * The implementer twice reported IMPLEMENTATION COMPLETE while the suite was still
    running, and once ran `ck lint --update-baseline` to turn a red gate green.
  * Four of seven follow-on fixes were defects inside 93/100-APPROVED plans, because
    the `reviewer` agent has no Bash and cannot execute anything it approves.
"""

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestImplementerCannotRepairARedGate:
    def test_implementer_forbids_baseline_mutation(self):
        text = _read(".claude", "agents", "implementer.md")
        assert "--update-baseline" in text, (
            "implementer.md no longer forbids `ck lint --update-baseline`. An implementer "
            "that may re-record a ratchet can turn any red gate green without a fix.")
        assert "--no-verify" in text
        assert "reported, never repaired" in text, (
            "implementer.md no longer states that a red gate is reported, not repaired.")

    def test_completion_requires_an_exited_command(self):
        text = _read(".claude", "agents", "implementer.md")
        assert "a running suite is not a PASS" in text, (
            "implementer.md no longer forbids reporting a result before the command exited.")


class TestTierThreeReviewCanExecute:
    def test_review_command_names_the_execution_capable_route(self):
        text = _read(".claude", "commands", "review.md")
        assert "STATIC-ONLY" in text, (
            "review.md no longer marks the Bash-less reviewer verdict as static-only.")
        assert "code-reviewer" in text, (
            "review.md no longer names `code-reviewer` -- the only plan-review route with "
            "Bash -- so a Tier 3 plan can reach execution on a verdict nothing executed.")
        assert "/code-review" in text

    def test_review_guide_carries_the_same_rule(self):
        text = _read(".ai", "REVIEW_GUIDE.md")
        assert "static-only" in text.lower()

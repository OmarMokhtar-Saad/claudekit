"""Structure test: code-reviewer.md must require running new tests and applying mutants.

Written 2026-09-17 after the third instance in one day of a mutation control that passed on
its own mutant (e2e-lane-a, hook-stdin-and-reflection round 1, qa-agents-hardening round 1).
This pins the instruction text; it cannot prove the agent obeys it.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODE_REVIEWER = REPO / ".claude/agents/code-reviewer.md"


def test_code_reviewer_must_run_new_test_files_before_a_verdict():
    text = CODE_REVIEWER.read_text(encoding="utf-8")
    assert "Run every new or changed test file on the unmutated tree" in text


def test_code_reviewer_must_apply_claimed_mutants():
    text = CODE_REVIEWER.read_text(encoding="utf-8")
    assert "Hand-apply at least two of the claimed mutation controls" in text


def test_a_surviving_mutant_is_a_high_finding_not_a_medium():
    """The severity matters: a Medium never forces another round under the exit rule."""
    text = CODE_REVIEWER.read_text(encoding="utf-8")
    assert "is a **High**\n   finding, never a Medium" in text


def test_the_rule_precedes_the_exit_rule():
    """Ordering is the point - the exit rule must not be reachable before the proofs are run."""
    text = CODE_REVIEWER.read_text(encoding="utf-8")
    rule = text.index("## Before the verdict: RUN the tests, APPLY the mutants")
    exit_rule = text.index("## Exit Rule -- what ends the review")
    assert rule < exit_rule

"""Task 008 batch 4: the taxonomy and the routing table are single-sourced.

Both of these were duplicated across many files and the duplicates had DRIFTED into
contradiction -- `commands/review.md` mapped score < 70 to REVISE while
`agents/reviewer.md` mapped it to REJECTED, and the two coordinator routing tables
disagreed on five of eight intents. Deduplicating is only half the fix; without a gate
the copies come back, which is what the corpus did between the 008 spec being written
and batch 1 running.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL = os.path.join(ROOT, ".claude", "agents", "HANDOFF_PROTOCOL.md")
AGENT_COORD = os.path.join(ROOT, ".claude", "agents", "coordinator.md")
CMD_COORD = os.path.join(ROOT, ".claude", "commands", "coordinator.md")

#: The four spellings review-record.py's VALID_DECISIONS enforces.
DECISIONS = ("APPROVED", "CONDITIONAL", "REVISE", "REJECTED")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestTheTaxonomyHasOneDefinition:
    def test_the_protocol_defines_all_four_decisions(self):
        body = _read(PROTOCOL)
        assert "## Reviewer Decision Taxonomy" in body
        for decision in DECISIONS:
            assert decision in body, decision

    def test_the_definition_matches_what_the_parser_accepts(self):
        """A verdict the parser cannot read cannot gate execution, so the prose and
        review-record.py must name the same four values -- no more, no fewer."""
        script = _read(os.path.join(
            ROOT, ".claude", "operations", "scripts", "review-record.py"))
        match = re.search(r"VALID_DECISIONS = \(([^)]*)\)", script)
        assert match, "VALID_DECISIONS not found"
        parsed = tuple(re.findall(r'"([A-Z]+)"', match.group(1)))
        assert parsed == DECISIONS, parsed

    def test_findings_gate_before_score(self):
        """The ambiguity that let batch 2's round-1 verdict be REVISE at 84 while both
        files' own bands said CONDITIONAL. An open blocker must outrank a high score."""
        body = _read(PROTOCOL)
        assert "at any score" in body.lower()

    @pytest.mark.parametrize("path", [
        os.path.join(".claude", "commands", "review.md"),
        os.path.join(".claude", "commands", "refine.md"),
        os.path.join(".claude", "agents", "reviewer.md"),
    ])
    def test_no_file_restates_the_score_bands_as_its_own_rule(self, path):
        """The specific contradicting formulas, gone. `REVISE = score < 70` was the
        one that disagreed outright with reviewer.md."""
        body = _read(os.path.join(ROOT, path))
        assert "REVISE = score < 70" not in body
        assert "CONDITIONAL = score 70-89 OR" not in body

    @pytest.mark.parametrize("path", [
        os.path.join(".claude", "commands", "review.md"),
        os.path.join(".claude", "commands", "refine.md"),
        os.path.join(".claude", "agents", "reviewer.md"),
    ])
    def test_each_points_at_the_one_definition(self, path):
        assert "HANDOFF_PROTOCOL.md" in _read(os.path.join(ROOT, path)), path


class TestTheRoutingTableHasOneDefinition:
    def test_the_agent_file_owns_the_table(self):
        body = _read(AGENT_COORD)
        assert "single routing source" in body
        assert "| **Feature** |" in body

    def test_the_command_file_no_longer_carries_a_second_table(self):
        """It is the duplication that caused the drift, so its absence is the fix --
        and this is the assertion that keeps a helpful copy from being pasted back."""
        body = _read(CMD_COORD)
        assert '| "Build feature X"' not in body
        assert "agents/coordinator.md" in body

    def test_nothing_the_deleted_table_uniquely_said_was_lost(self):
        """Two conventions lived only in the deleted copy. Losing them to a
        deduplication would be exactly the batch-1 mistake in a new costume."""
        body = _read(CMD_COORD)
        assert "planner" in body.lower() and "refine" in body
        assert "doc-updater" in body and "documenter" in body

    def test_the_docs_route_distinguishes_create_from_update(self):
        """The old single Docs row named one destination while HANDOFF_PROTOCOL.md has
        always carried two Docs pipelines."""
        body = _read(AGENT_COORD)
        assert "Docs (new)" in body and "Docs (update)" in body

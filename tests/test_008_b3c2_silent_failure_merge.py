"""Task 008 batch 3 cluster 2: `silent-failure-hunter` merged into `code-reviewer`.

**This merge changes routing and the eval suite does NOT cover it.** `/audit` spawned
silent-failure-hunter as one of three parallel agents; it now spawns `code-reviewer` for
Dimension 6 instead. The cassettes that would prove the fan-out still behaves the same
do not exist, so this file proves the CONTENT survived, the name resolves, and the
fan-out WIDTH is unchanged -- not that the routing is equivalent. Recorded plainly
because implying eval coverage would be worse than having none.
"""

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, ".claude", "agents")

UNION = [
    'Async-specific patterns:',
    'CRITICAL',
    'Categories to scan:',
    'HIGH',
    'Indicators:',
    'MEDIUM',
    'Red flags:',
    'Search patterns:',
    '`# noqa: silent-failure`',
    '`.catch()`',
    '`Promise`',
    '`async`',
    '`asyncio.gather()`',
    '`await`',
    '`catch.*=> {}`',
    '`catch.*\\{\\s*\\}`',
    '`except ... return ""`',
    '`except ... return 0`',
    '`except ... return []`',
    '`except ... return {}`',
    '`except KeyboardInterrupt: pass`',
    '`except SystemExit: pass`',
    '`except.*: return None`',
    '`except.*:\\s*pass`',
    '`or default_value`',
    '`return_exceptions=True`',
    '`try/except/pass`',
    '`with pytest.raises(...)`',
    'asyncio.gather',
    'db.execute',
    'db.query',
    'e.g',
    'f.read',
    'logger.debug',
    'logger.error',
    'os.getenv',
    'pytest.raises',
    'requests.get',
    'Silent Failures (P1)',
    'Empty Catch Blocks',
    'Inadequate Logging',
    'Dangerous Fallbacks',
    'Error Propagation Issues',
    'Missing Error Handling',
    'Investigation Workflow',
    'Empty Catch Hunt',
    'Logging Quality Check',
    'Dangerous Fallback Detection',
    'Async Error Propagation',
    'Silent Failure Audit Summary',
    'Highest-Risk Files',
]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class TestTheMergeIsComplete:
    def test_the_merged_away_agent_is_gone(self):
        assert not os.path.isfile(os.path.join(AGENTS, "silent-failure-hunter.md"))

    @pytest.mark.parametrize("fragment", UNION)
    def test_the_union_survived(self, fragment):
        assert fragment in _read(".claude/agents/code-reviewer.md"), fragment

    def test_the_core_philosophy_is_carried_verbatim(self):
        body = _read(".claude/agents/code-reviewer.md")
        assert "**A failure that is silent is worse than a failure that is loud.**" in body

    def test_it_is_a_numbered_dimension_not_an_appendix(self):
        """The merge claim is that it became a review DIMENSION. If it only appended
        prose, the reviewer would never apply it in Phase 3."""
        body = _read(".claude/agents/code-reviewer.md")
        assert "### 6. Silent Failures (P1)" in body
        assert body.index("### 6. Silent Failures") < body.index("## Workflow")


class TestTheRoutingChangeIsHonest:
    def test_audit_still_fans_out_three_ways(self):
        """The width is the part that CAN be checked without cassettes."""
        body = _read(".claude/commands/audit.md")
        assert "parallel" in body
        assert "Security Scanner" in body and "Code Reviewer" in body
        assert "Silent Failure Hunter" not in body
        assert "Dimension 6" in body or "dim 6" in body

    def test_the_uncovered_risk_is_stated_in_the_agent_itself(self):
        """Not in a plan a consumer will never read -- in the merged agent."""
        body = _read(".claude/agents/code-reviewer.md")
        assert "not covered by the eval suite" in body

    def test_the_alias_resolves(self):
        registry = json.loads(_read(".claude/skills/skills-registry.json"))
        assert registry["renamedAgents"]["silent-failure-hunter"] == {
            "to": "code-reviewer", "kind": "agent"}

    def test_no_live_consumer_names_the_removed_agent(self):
        allowed = os.path.abspath(os.path.join(AGENTS, "code-reviewer.md"))
        hits = []
        for rel in (".claude/agents", ".claude/commands", ".claude/skills", "docs",
                    "src/claudekit", "scripts", "tests"):
            base = os.path.join(ROOT, rel)
            if not os.path.isdir(base):
                continue
            for dirpath, _dirs, files in os.walk(base):
                for name in files:
                    if not name.endswith((".md", ".json", ".py")):
                        continue
                    if name == "skills-registry.json":
                        continue
                    if name == os.path.basename(__file__):
                        # This file names the removed agent throughout, by design.
                        # Batch 2 hit the same self-reference trap.
                        continue
                    path = os.path.join(dirpath, name)
                    if os.path.abspath(path) == allowed:
                        continue
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        if "silent-failure-hunter" in fh.read():
                            hits.append(os.path.relpath(path, ROOT))
        assert hits == [], hits

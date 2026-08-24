"""Task 008 batch 3 cluster 6: `model-router` folds into coordinator + /model-route.

The rubric was TRANSLATED, not transplanted. `model-router.md` named Haiku/Sonnet/Opus
throughout while CLAUDE.md's own policy says capability tiers only and
`.claude/model-policy.json` is the single place a tier becomes a model. Folding the table
in verbatim would have imported exactly what that policy exists to prevent -- into the
coordinator, which every pipeline reads.

`/model-route` also carried its OWN copy of the score table, in vendor names: both the
duplication task 008 exists to remove and the forbidden vocabulary, in one file.
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COORD = os.path.join(ROOT, ".claude", "agents", "coordinator.md")
CMD = os.path.join(ROOT, ".claude", "commands", "model-route.md")

#: Every dimension and band the removed agent scored on.
RUBRIC = [
    "Reasoning depth", "Output complexity", "Error cost", "Domain novelty",
    "0\u20133", "4\u201310", "11\u201312",
    "fast", "balanced", "most-capable",
]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestTheRubricSurvived:
    def test_the_agent_is_gone(self):
        assert not os.path.isfile(
            os.path.join(ROOT, ".claude", "agents", "model-router.md"))

    @pytest.mark.parametrize("fragment", RUBRIC)
    def test_the_rubric_is_inline_in_the_coordinator(self, fragment):
        assert fragment in _read(COORD), fragment

    def test_every_override_survived(self):
        """Overrides beat the score, so losing one silently changes routing for the
        exact cases that matter most."""
        body = _read(COORD)
        for override in ("Security review", "merge approval", "Documentation update"):
            assert override in body, override

    def test_the_alias_resolves(self):
        path = os.path.join(ROOT, ".claude", "skills", "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            registry = json.load(fh)
        assert registry["renamedAgents"]["model-router"] == {
            "to": "coordinator", "kind": "agent"}


class TestTheVocabularyIsTiersNotVendorNames:
    #: `model:` frontmatter is the one legitimate place a vendor name appears -- it is
    #: what the harness reads. Everything else must speak in tiers.
    VENDOR = re.compile(r"\b(haiku|sonnet|opus)\b", re.I)

    def _offending_lines(self, path):
        out = []
        for n, line in enumerate(_read(path).splitlines(), 1):
            if not self.VENDOR.search(line):
                continue
            if line.startswith("model:"):
                continue
            if "named Haiku/Sonnet/Opus" in line or "Sonnet (heavy)" in line:
                continue          # the seam explaining the translation
            out.append("%s:%d: %s" % (os.path.basename(path), n, line.strip()))
        return out

    def test_the_command_speaks_in_tiers(self):
        assert self._offending_lines(CMD) == []

    def test_the_coordinator_rubric_speaks_in_tiers(self):
        assert self._offending_lines(COORD) == []

    def test_the_command_does_not_repeat_the_table(self):
        """It carried its own copy. One rubric, in one place."""
        body = _read(CMD)
        assert "not repeated here" in body
        assert "| Reasoning depth |" not in body

    def test_the_collapsed_band_is_explained_not_silent(self):
        """The old table had an 8-10 "Sonnet (heavy)" row naming the same model as the
        row above it -- a distinction the tier vocabulary cannot express. Collapsing it
        is a judgement call, so it is recorded rather than done quietly."""
        assert "collapsed into `balanced` on purpose" in _read(COORD)

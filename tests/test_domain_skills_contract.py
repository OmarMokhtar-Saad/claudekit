"""Domain skills: /plan, /review and /implement read a user-owned domain-skills.md map.

The commands are prompt text with no runtime of their own, so this is a contract test on
the shipped text: each command states the matching, cap, allowed-path and not-found rules,
and both double-quoted bash messages (PLANNER_MSG, REVIEWER_MSG) carry the rule in plain
text that cannot break the string.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMDS = os.path.join(ROOT, ".claude", "commands")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _section(text, heading):
    """Body of the markdown section starting at `heading`, up to the next heading of the same
    or higher level."""
    start = text.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    m = re.compile(r"^#{1,%d} " % level, re.M).search(text, start + len(heading))
    return text[start:m.start() if m else len(text)]


def _block(text, name):
    """A double-quoted bash variable: from NAME=" to the first line that ends in a quote."""
    m = re.search(r'^%s="(.*?)"$' % name, text, re.S | re.M)
    assert m, "%s block not found" % name
    return m.group(1)


def _domain_paragraphs(block):
    return [p for p in re.split(r"\n\s*\n", block) if "Domain skills" in p]


def _assert_shell_safe(paragraphs):
    # Scope is deliberately narrow: only the domain-skills paragraphs. REVIEWER_MSG already
    # carries $PLAN_FILE elsewhere, so a whole-block check for `$` would be wrong. Do not widen.
    assert paragraphs, "no Domain skills paragraph in the block"
    for p in paragraphs:
        for ch in ("`", "$", '"'):
            assert ch not in p, "%r inside a double-quoted bash string: %s" % (ch, p)


class TestPlanCommand:
    text = _read(".claude", "commands", "plan.md")

    def test_domain_step_sits_between_name_files_and_write_plan(self):
        default = _section(self.text, "## Default (no `--deep`)")
        name_at = default.index("Name every file")
        write_at = default.index("Write `.claude/plans/plan-<slug>.md`")
        domain_at = default.index("domain-skills.md")
        assert name_at < domain_at < write_at

    def test_states_every_rule(self):
        default = _section(self.text, "## Default (no `--deep`)")
        for s in ("Domain skills:", "Domain skills skipped:", "at most 3",
                  "domain skill not found", "path not allowed", "~/.claude/plugins/",
                  "whole word", "\"shortcut\""):
            assert s in default, s

    def test_planner_msg_carries_the_rule_safely(self):
        block = _block(self.text, "PLANNER_MSG")
        assert "domain-skills.md" in block
        assert "Domain skills:" in block
        _assert_shell_safe(_domain_paragraphs(block))


class TestReviewCommand:
    text = _read(".claude", "commands", "review.md")

    def test_reviewer_msg_carries_the_rule_safely(self):
        block = _block(self.text, "REVIEWER_MSG")
        assert "=== END REVIEW ===" in block, "extraction truncated"
        paras = _domain_paragraphs(block)
        assert any("MAJOR" in p for p in paras)
        assert any("~/.claude/plugins/" in p for p in paras)
        assert any("whole" in p and "word" in p for p in paras)
        _assert_shell_safe(paras)


class TestImplementCommand:
    def test_mandatory_skills_reads_domain_skills(self):
        sec = _section(_read(".claude", "commands", "implement.md"), "## Mandatory Skills")
        for s in ("Domain skills:", "before Phase 2", "domain skill not found",
                  "~/.claude/plugins/", "path not allowed"):
            assert s in sec, s


class TestDocsAndShipping:
    def test_customization_documents_it(self):
        sec = _section(_read("docs", "CUSTOMIZATION.md"),
                       "### Domain skills for /plan, /review, /implement")
        for s in ("at most 3", "path not allowed", "domain skill not found"):
            assert s in sec, s

    def test_changelog_unreleased_mentions_it(self):
        assert "domain-skills.md" in _section(_read("CHANGELOG.md"), "## [Unreleased]")

    def test_kit_ships_no_map(self):
        assert not os.path.exists(os.path.join(ROOT, ".claude", "domain-skills.md"))

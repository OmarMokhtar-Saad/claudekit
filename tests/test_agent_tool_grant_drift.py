"""Agent tool grants must match what the harness will actually read.

Regression gate for the 2026-08-19 finding: `.claude/agents/_shared/INVOCATION.md`
documented scoped `--allowedTools` per role while three agents' frontmatter granted
something different. The Task-tool spawn path reads the FRONTMATTER, so the documented
scoping was never applied there and the implementer held unrestricted Bash.

Measured on Claude Code 2.1.235 via a differential test with the spawn path held constant
(both arms loaded through `--agent`): the identical rule `Bash(python3 *)` was APPLIED when
passed via `--allowedTools` (a write ran unapproved) and NOT APPLIED when declared in
frontmatter `tools:` (the same write demanded approval), under `permission_mode: "default"`
with an empty allow/deny list.

That establishes the frontmatter-declared specifier is not applied. It does NOT establish
*why* — stripping at parse time vs retained-but-ignored was not separated, and the
interactive Task-tool path was not isolated. See INVOCATION.md for the named missing arm.
The operational conclusion survives either way: frontmatter cannot scope Bash, so scoping
exists only on the `--allowedTools` path and the interactive implementer holds bare Bash.

SCOPE OF THESE TESTS — read before trusting a green run:

* Nothing here is behavioral. All four tests are TEXTUAL/STRUCTURAL checks over file
  contents. A green suite does NOT prove the harness enforces anything; proving that needs
  an authenticated, networked `claude` session, which is not admissible in this suite. The
  manual probe recorded in INVOCATION.md is that evidence. These tests are the ratchet.
* `test_documented_grants_match_frontmatter` is genuinely BOUND: it checks all ten
  documented rows against real frontmatter and fails on injected drift.
* `test_no_specifier_in_any_frontmatter_tools` passes VACUOUSLY today — no agent frontmatter
  contains a `(` at all. It is a preventive ratchet, not a control.
* The two `TestDocumentedContractsSurviveEdits` tests gate DELETION ONLY: they fail if the
  corrected text is removed, not if it is wrong.
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, ".claude", "agents")
INVOCATION = os.path.join(AGENTS, "_shared", "INVOCATION.md")

TABLE_HEADING = "### Actual frontmatter grants"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _frontmatter(text):
    """Return the YAML frontmatter block, or None if the file has none."""
    if not text.startswith("---\n"):
        return None
    end = text.index("\n---", 3)
    return text[4:end + 1]


def _declared_tools(path):
    """Parse a frontmatter `tools:` line into a list of raw entries."""
    fm = _frontmatter(_read(path))
    if fm is None:
        return None
    match = re.search(r"^tools:\s*\[(.*)\]\s*$", fm, re.MULTILINE)
    if not match:
        return None
    return [item.strip().strip('"').strip("'")
            for item in match.group(1).split(",") if item.strip()]


def _agent_files():
    for name in sorted(os.listdir(AGENTS)):
        path = os.path.join(AGENTS, name)
        if name.endswith(".md") and os.path.isfile(path):
            yield name[:-3], path


def _documented_grants():
    """Parse the frontmatter-grants table out of INVOCATION.md."""
    text = _read(INVOCATION)
    assert TABLE_HEADING in text, (
        "INVOCATION.md lost the %r section: the frontmatter grants are no longer "
        "documented, so drift is silent again." % TABLE_HEADING)
    body = text[text.index(TABLE_HEADING):]
    grants = {}
    for line in body.split("\n"):
        row = re.match(r"^\|\s*([A-Za-z-]+)\s*\|\s*`([^`]+)`\s*\|\s*$", line)
        if not row:
            continue
        if row.group(1) == "Agent":
            continue
        grants[row.group(1)] = [t.strip() for t in row.group(2).split(",") if t.strip()]
    assert grants, "frontmatter grants table parsed empty — format changed?"
    return grants


class TestFrontmatterMatchesInvocation(unittest.TestCase):
    """BOUND: the documented grant must equal the grant the Task tool actually reads."""

    def test_documented_grants_match_frontmatter(self):
        documented = _documented_grants()
        for agent, expected in documented.items():
            path = os.path.join(AGENTS, agent + ".md")
            self.assertTrue(os.path.isfile(path),
                            "INVOCATION.md documents grants for %r but "
                            ".claude/agents/%s.md does not exist" % (agent, agent))
            actual = _declared_tools(path)
            self.assertIsNotNone(actual,
                                 "%s.md has no parseable frontmatter `tools:` line, but "
                                 "INVOCATION.md documents one" % agent)
            self.assertEqual(
                sorted(expected), sorted(actual),
                "grant drift for %r: INVOCATION.md says %s, frontmatter says %s. The "
                "Task-tool spawn path reads the FRONTMATTER, so the frontmatter wins at "
                "runtime — fix whichever one is wrong, but never leave them disagreeing."
                % (agent, sorted(expected), sorted(actual)))


class TestNoFakeScoping(unittest.TestCase):
    """PREVENTIVE RATCHET (vacuous today): frontmatter cannot scope a tool."""

    def test_no_specifier_in_any_frontmatter_tools(self):
        checked = 0
        for agent, path in _agent_files():
            tools = _declared_tools(path)
            if tools is None:
                continue
            checked += 1
            for tool in tools:
                self.assertNotIn(
                    "(", tool,
                    "%s.md declares %r in frontmatter `tools:`. Measured on Claude Code "
                    "2.1.235, frontmatter accepts BARE NAMES ONLY — the specifier is "
                    "silently stripped and the bare, unrestricted tool is granted. Use a "
                    "bare name here and scope on the `--allowedTools` headless path (or a "
                    "PreToolUse hook) instead." % (agent, tool))
        self.assertTrue(checked, "no agent frontmatter found — wrong path?")


class TestDocumentedContractsSurviveEdits(unittest.TestCase):
    """DELETION GATE ONLY: fails if the corrected text is removed, not if it is wrong."""

    def test_code_reviewer_row_grants_phase_0_git_verbs(self):
        text = _read(INVOCATION)
        row = [ln for ln in text.split("\n") if ln.startswith("| code-reviewer ")]
        self.assertTrue(row, "code-reviewer row missing from the --allowedTools table")
        joined = row[0]
        for verb in ("git show", "git diff", "git rev-parse", "git ls-files",
                     "git worktree", "gh pr"):
            self.assertIn(
                "Bash(%s" % verb, joined,
                "code-reviewer's --allowedTools row no longer grants %r, which its Phase 0 "
                "(Confirm the Revision) requires. A reviewer that cannot pin the revision "
                "must emit CANNOT REVIEW instead of a confidently wrong clean report."
                % verb)

    def test_implementer_iron_law_covers_all_bash_mutation(self):
        text = _read(os.path.join(AGENTS, "implementer.md"))
        self.assertIn(
            "any command that writes, creates, deletes, moves, or otherwise mutates ANY",
            text,
            "implementer.md's IRON LAW no longer states the general rule. Banning only "
            "Edit/Write, or only an enumerated list of commands, is insufficient: the agent "
            "holds unrestricted Bash and any list can be evaded (sh -c, heredocs, perl -pi, "
            "git apply).")
        self.assertIn(
            "illustrative, NOT exhaustive", text,
            "implementer.md no longer marks its mutation examples as non-exhaustive, "
            "inviting the list to be read as a denylist to work around.")


if __name__ == "__main__":
    unittest.main()

"""Task 008 batch 3 cluster 4: `documenter` + `doc-updater` -> one `docs` agent.

They were split by TENSE, not capability: same code reading, same extraction rules, same
quality bar, differing only in whether the target file already existed. Two agents meant
two spawns, two contexts and two sets of drift, and HANDOFF_PROTOCOL.md carried two
near-identical Docs pipelines to route between them.

The mode split is PRESERVED, not erased -- `/docs` is create, `/doc-updater` is update,
and the coordinator table (which batch 4 had just split by mode) now routes both intents
to one agent. **Routing is not demonstrated unchanged**; the eval cassettes do not exist.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, ".claude", "agents")

GONE = ["documenter", "doc-updater"]

UNION = [
    "- NEVER copy-paste code without verifying it's current",
    '- NEVER document implementation details that change frequently (focus on interfaces)',
    '- NEVER include placeholder text ("TODO: fill this in")',
    '- NEVER include sensitive information (secrets, credentials, internal URLs)',
    '- NEVER modify source code (you can only modify documentation)',
    '- NEVER omit error handling from code examples',
    '- NEVER skip code examples for API documentation',
    '- NEVER use jargon without explanation',
    '- NEVER write docs without reading the source code first',
    '- NEVER write documentation that contradicts the source code',
    '- NEVER write walls of text without structure (use headings, lists, tables)',
    'Always update for:',
    'Architecture change',
    'Bug fix with lessons learned',
    'CHANGELOG.md',
    'CONTRIBUTING.md',
    'Common support question',
    'Dependencies:',
    'Dependency update',
    'Description:',
    'Doc Updater CAN:',
    'Doc Updater CANNOT:',
    'Errors:',
    'Example:',
    'Find the affected section',
    "Generate from code, don't manually write.",
    'INDEX.md',
    'Last Updated:',
    'Location:',
    'Mandatory (load before any work, in order):',
    'New feature added',
    'Note:',
    'On demand (load when the trigger fires — do NOT preload; preloading burns context):',
    'Optional for:',
    'Parameters:',
    'Performance optimization',
    'Purpose:',
    'README.md',
    'Read the current README',
    'Returns:',
    'Security fix',
    'Status:',
    'Tip:',
    'Update in place',
    'Verify code examples compile:',
    'Warning:',
    '`*.md`',
    '`*.txt`',
    '`.claude/`',
    '`CHANGELOG.md`',
    '`CONTRIBUTING.md`',
    '`METHOD /path`',
    '`README.md`',
    '`ReturnType`',
    '`docs/CODEMAPS/<area>.md`',
    '`docs/CODEMAPS/INDEX.md`',
    '`docs/`',
    '`docs/adr/`',
    '`docs/api/`',
    '`docs/architecture/`',
    '`docs/kb/`',
    '`docs/runbooks/`',
    '`docs/setup.md`',
    '`docs/troubleshooting.md`',
    '`functionName(params)`',
    '`path/to/file`',
    '`src/[path]`',
    'area.md',
    'backend.md',
    'd.ts',
    'database.md',
    'documentation-standards',
    'e.g',
    'example.com',
    'frontend.md',
    'golden-rule',
    'graph.svg',
    'package.json',
    'settings.json',
    'setup.md',
    'troubleshooting.md',
    'using-superpowers',
    'Mode: create',
    'Mode: update',
    'Codemap Generation',
    'Inline Documentation Updates',
    'README Updates',
    'Quality Checklist',
    'Scope Boundaries',
    'When to Update Documentation',
]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class TestTheMergeIsComplete:
    @pytest.mark.parametrize("old", GONE)
    def test_the_old_agent_is_gone(self, old):
        assert not os.path.isfile(os.path.join(AGENTS, old + ".md"))

    def test_the_merged_agent_exists(self):
        assert os.path.isfile(os.path.join(AGENTS, "docs.md"))

    @pytest.mark.parametrize("fragment", UNION)
    def test_the_union_survived(self, fragment):
        assert fragment in _read(".claude/agents/docs.md"), fragment

    def test_the_rule_the_signoff_required_is_carried_verbatim(self):
        """The sign-off named this rule specifically as one that must survive the
        merge. It is hoisted ABOVE both modes, because it constrains both."""
        body = _read(".claude/agents/docs.md")
        assert "**Generate from code, don't manually write.**" in body
        assert body.index("Generate from code") < body.index("# Mode: create")

    def test_mode_is_mandatory_and_unguessed(self):
        """Choosing create for a file that exists overwrites human edits; choosing
        update for one that does not diffs against nothing."""
        body = _read(".claude/agents/docs.md")
        assert "mode: create" in body and "mode: update" in body
        assert "Never guess the mode" in body


class TestBothEntryPointsStillWork:
    def test_docs_command_routes_to_create(self):
        body = _read(".claude/commands/docs.md")
        assert "mode: create" in body
        assert "agents/docs.md" in body, "dangling @-path to a deleted agent file"

    def test_doc_updater_command_survives_and_routes_to_update(self):
        """The COMMAND keeps its name and its flags; only the agent it hands off to
        moved. Deleting the command would have been a user-visible removal the
        sign-off never authorised."""
        body = _read(".claude/commands/doc-updater.md")
        assert "mode: update" in body
        assert "--docstrings" in body and "--readme" in body

    def test_the_coordinator_still_distinguishes_the_two_intents(self):
        body = _read(".claude/agents/coordinator.md")
        assert "Docs (new)" in body and "Docs (update)" in body
        assert "DocUpdater" not in body

    @pytest.mark.parametrize("old", GONE)
    def test_each_name_resolves(self, old):
        registry = json.loads(_read(".claude/skills/skills-registry.json"))
        assert registry["renamedAgents"][old] == {"to": "docs", "kind": "agent"}


class TestTheCommandNameExemptionStaysNarrow:
    """Cluster 4 taught the alias scan that a COMMAND may keep a merged-away AGENT's
    name (`/doc-updater` survives; the agent does not). Two exemptions were added, and
    an exemption that is wider than its reason is how a scan stops meaning anything."""

    def _fixture(self, tmp_path, files):
        claude = tmp_path / ".claude"
        for sub in ("agents", "commands", "skills"):
            (claude / sub).mkdir(parents=True)
        (claude / "agents" / "survivor.md").write_text(
            "---\nname: survivor\ndescription: d\n---\n\n# S\n", encoding="utf-8")
        registry = {
            "version": "1.0", "renamed": {},
            "renamedAgents": {"gone": {"to": "survivor", "kind": "agent"}},
            "skills": [], "agentsWithoutSkills": ["survivor"], "agentMapping": {},
        }
        (claude / "skills" / "skills-registry.json").write_text(
            json.dumps(registry, indent=2), encoding="utf-8")
        for rel, body in files.items():
            (claude / rel).write_text(body, encoding="utf-8")
        return tmp_path

    def _doctor(self, cwd):
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
        return subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "doctor", "--strict"],
            cwd=str(cwd), capture_output=True, text=True, env=env)

    def test_the_command_file_of_the_same_name_is_exempt(self, tmp_path):
        """`/doc-updater`'s own command file says "doc-updater" throughout -- its
        frontmatter name, its usage examples. Flagging it would be permanent noise."""
        root = self._fixture(tmp_path, {
            "commands/gone.md": "---\nname: gone\ndescription: d\n---\n\n"
                                "Usage: gone --flag\n"})
        assert "became the agent" not in self._doctor(root).stdout

    def test_a_same_named_file_OUTSIDE_commands_is_not_exempt(self, tmp_path):
        """The exemption is keyed on the commands/ directory. A skill or agent file
        that happens to share the name gets no pass."""
        root = self._fixture(tmp_path, {
            "agents/gone-notes.md": "The gone agent did this.\n"})
        out = self._doctor(root).stdout
        assert "became the agent" in out, out

    def test_a_slash_reference_is_a_command_not_an_agent(self, tmp_path):
        root = self._fixture(tmp_path, {"commands/other.md": "Run `/gone` for that.\n"})
        assert "became the agent" not in self._doctor(root).stdout

    def test_a_BARE_reference_elsewhere_is_still_flagged(self, tmp_path):
        """The exemption covers `/gone`, not `gone`. Without this the narrowing would
        have silenced the half of the scan a consumer can act on."""
        root = self._fixture(tmp_path, {"commands/other.md": "Load the gone agent.\n"})
        out = self._doctor(root).stdout
        assert "became the agent" in out and "commands/other.md" in out

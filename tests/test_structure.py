"""Tests for ClaudeKit directory structure and file integrity."""

import glob
import json
import os

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CLAUDE_DIR = os.path.join(ROOT, '.claude')


class TestDirectoryStructure:
    """Verify the expected directory structure exists."""

    def test_claude_dir_exists(self):
        assert os.path.isdir(CLAUDE_DIR)

    def test_agents_dir(self):
        assert os.path.isdir(os.path.join(CLAUDE_DIR, 'agents'))

    def test_agents_shared_dir(self):
        assert os.path.isdir(os.path.join(CLAUDE_DIR, 'agents', '_shared'))

    def test_commands_dir(self):
        assert os.path.isdir(os.path.join(CLAUDE_DIR, 'commands'))

    def test_skills_dir(self):
        assert os.path.isdir(os.path.join(CLAUDE_DIR, 'skills'))

    def test_hooks_dir(self):
        assert os.path.isdir(os.path.join(CLAUDE_DIR, 'hooks'))

    def test_operations_dir(self):
        assert os.path.isdir(os.path.join(CLAUDE_DIR, 'operations', 'scripts'))

    def test_local_dir(self):
        assert os.path.isdir(os.path.join(CLAUDE_DIR, 'local'))

    def test_templates_dir(self):
        templates_dir = os.path.join(ROOT, 'templates')
        assert os.path.isdir(templates_dir)
        for lang in ['python', 'typescript', 'java', 'go', 'kotlin', 'swift', 'generic', 'rust', 'csharp', 'ruby', 'php']:
            assert os.path.isdir(os.path.join(templates_dir, lang)), f"Missing template: {lang}"

    def test_docs_dir(self):
        docs_dir = os.path.join(ROOT, 'docs')
        assert os.path.isdir(docs_dir)

    def test_examples_dir(self):
        examples_dir = os.path.join(ROOT, 'examples')
        assert os.path.isdir(os.path.join(examples_dir, 'python-fastapi'))
        assert os.path.isdir(os.path.join(examples_dir, 'typescript-nextjs'))


class TestAgentFiles:
    """Verify all 13 agents exist and have valid frontmatter."""

    EXPECTED_AGENTS = [
        'coordinator', 'debugger', 'documenter', 'explore',
        'gitOps', 'implementer', 'planner', 'reviewer', 'verifier',
        'tester', 'security-scanner', 'devops', 'database-architect'
    ]

    @pytest.mark.parametrize("agent", EXPECTED_AGENTS)
    def test_agent_exists(self, agent):
        path = os.path.join(CLAUDE_DIR, 'agents', f'{agent}.md')
        assert os.path.exists(path), f"Missing agent: {agent}"

    @pytest.mark.parametrize("agent", EXPECTED_AGENTS)
    def test_agent_has_frontmatter(self, agent):
        path = os.path.join(CLAUDE_DIR, 'agents', f'{agent}.md')
        with open(path) as f:
            content = f.read()
        assert content.startswith('---'), f"Agent {agent} missing frontmatter"
        # Should have closing ---
        assert content.count('---') >= 2, f"Agent {agent} has unclosed frontmatter"


class TestCommandFiles:
    """Verify all 17 commands exist."""

    EXPECTED_COMMANDS = [
        'coordinator', 'debug', 'docs', 'git',
        'implement', 'plan', 'review', 'verify',
        'explore', 'security', 'deps', 'rollback',
        'test', 'deploy', 'performance', 'migrate', 'batch'
    ]

    @pytest.mark.parametrize("cmd", EXPECTED_COMMANDS)
    def test_command_exists(self, cmd):
        path = os.path.join(CLAUDE_DIR, 'commands', f'{cmd}.md')
        assert os.path.exists(path), f"Missing command: {cmd}"

    @pytest.mark.parametrize("cmd", EXPECTED_COMMANDS)
    def test_command_has_frontmatter(self, cmd):
        path = os.path.join(CLAUDE_DIR, 'commands', f'{cmd}.md')
        with open(path) as f:
            content = f.read()
        assert content.startswith('---'), f"Command {cmd} missing frontmatter"


class TestOperationsScripts:
    """Verify operations scripts are present and valid."""

    def test_validator_exists(self):
        assert os.path.exists(os.path.join(CLAUDE_DIR, 'operations', 'scripts', 'validate-config-json.py'))

    def test_executor_exists(self):
        assert os.path.exists(os.path.join(CLAUDE_DIR, 'operations', 'scripts', 'execute-json-ops.py'))

    def test_restore_exists(self):
        assert os.path.exists(os.path.join(CLAUDE_DIR, 'operations', 'scripts', 'restore-backup.py'))

    def test_shared_exists(self):
        assert os.path.exists(os.path.join(CLAUDE_DIR, 'operations', 'scripts', 'shared.py'))

    def test_schema_exists(self):
        path = os.path.join(CLAUDE_DIR, 'operations', 'scripts', 'operations-schema.json')
        assert os.path.exists(path)
        with open(path) as f:
            schema = json.load(f)
        assert schema['type'] == 'object'


class TestTemplateFiles:
    """Verify template files exist."""

    def test_claude_template(self):
        assert os.path.exists(os.path.join(CLAUDE_DIR, 'local', 'CLAUDE.template.md'))

    def test_constitution_template(self):
        assert os.path.exists(os.path.join(CLAUDE_DIR, 'local', 'CONSTITUTION.template.md'))

    @pytest.mark.parametrize("lang", ['python', 'typescript', 'java', 'go', 'kotlin', 'swift', 'generic', 'rust', 'csharp', 'ruby', 'php'])
    def test_language_template_has_config(self, lang):
        path = os.path.join(ROOT, 'templates', lang, 'config.env')
        assert os.path.exists(path), f"Missing config.env for {lang}"

    @pytest.mark.parametrize("lang", ['python', 'typescript', 'java', 'go', 'kotlin', 'swift', 'generic', 'rust', 'csharp', 'ruby', 'php'])
    def test_language_template_has_claude_md(self, lang):
        path = os.path.join(ROOT, 'templates', lang, 'CLAUDE.md')
        assert os.path.exists(path), f"Missing CLAUDE.md for {lang}"


class TestDocFiles:
    """Verify documentation files exist."""

    EXPECTED_DOCS = [
        'ARCHITECTURE.md', 'AGENTS.md', 'SKILLS.md',
        'HOOKS.md', 'CUSTOMIZATION.md', 'CONSTITUTION-GUIDE.md'
    ]

    @pytest.mark.parametrize("doc", EXPECTED_DOCS)
    def test_doc_exists(self, doc):
        path = os.path.join(ROOT, 'docs', doc)
        assert os.path.exists(path), f"Missing doc: {doc}"


class TestOneCanonicalTree:
    """`templates/` must not carry a second copy of any component class.

    install.sh copies `templates/` and `.claude/` into the SAME destination, so a
    name present in both is resolved by copy order, not by intent. That shipped a
    five-month-stale `token-optimization` to every `--full` install. Task 008
    batch 1 promoted what was unique and deleted what was duplicated; this test is
    what stops the second tree growing back.

    Everything here asserts on component FILES or on executable installer lines.
    `file_delete` leaves the directory behind and git does not track an empty
    directory, so `isdir` is True in the tree that ran the batch and False in a
    fresh clone -- a check whose answer depends on which one you are in.
    """

    COMPONENT_GLOBS = {
        "agents": ("agents", "*.md"),
        "commands": ("commands", "*.md"),
        "hooks": ("hooks", "*.sh"),
        "modes": ("modes", "*.md"),
        "skills": ("skills", "*", "SKILL.md"),
    }

    @pytest.mark.parametrize("kind", sorted(COMPONENT_GLOBS))
    def test_no_second_tree(self, kind):
        stale = glob.glob(os.path.join(ROOT, "templates", *TestOneCanonicalTree.COMPONENT_GLOBS[kind]))
        assert stale == [], (
            f"templates/{kind}/ holds components again: two trees, one install "
            f"destination, and the winner decided by copy order: {stale}")

    EXPECTED_MODES = {"default", "brainstorm", "token-efficient", "deep-research",
                      "implementation", "orchestration", "review"}

    def test_modes_live_in_the_canonical_tree(self):
        """Named, not counted. `.claude/modes/` arrived in task 008 batch 1 and is the
        one component class no generator counts, so a mode deleted by accident would
        go unnoticed -- an existence check on the directory passes with six of seven."""
        modes = os.path.join(CLAUDE_DIR, "modes")
        assert os.path.isdir(modes)
        found = {os.path.basename(p)[:-3] for p in
                 glob.glob(os.path.join(modes, "*.md"))}
        missing = sorted(TestOneCanonicalTree.EXPECTED_MODES - found)
        assert missing == [], f"modes lost: {missing}"

    def test_the_installer_reads_no_second_tree(self):
        """Reads install.sh, because the file checks above pass just as well against
        an installer that still names a tree that is gone.

        Comments are stripped first: the installer legitimately EXPLAINS the old
        two-tree bug in prose, and a raw substring search flags that explanation as
        the bug itself. Measured -- the first version of this test failed on
        install.sh's own changelog comment."""
        with open(os.path.join(ROOT, "install.sh"), encoding="utf-8") as fh:
            code = "\n".join(line for line in fh.read().splitlines()
                             if not line.lstrip().startswith("#"))
        for kind in sorted(TestOneCanonicalTree.COMPONENT_GLOBS):
            assert f"templates/{kind}" not in code, (
                f"install.sh still copies templates/{kind}")

class TestHookWiringIsHonest:
    """A shipped hook is wired, resolved by a wrapper, or declared inert -- never
    silently none of the three.

    `README.md` and `docs/HOOKS.md` said "26 hooks ship ... all are wired" while two of
    them were referenced by nothing at all. The count moved 22 -> 26 with the promotion
    in task 008 batch 1 and the prose around it did not, so a generated number turned a
    true sentence into a false one. A reader who believes `auto-checkpoint.sh` is
    protecting their session and never configures a real checkpoint is exactly the
    failure hard rule 6 exists to prevent: inert scripts advertised as active
    guardrails.

    Adding a hook to UNWIRED is a deliberate, reviewable act. Adding one to neither
    fails here.
    """

    UNWIRED = {
        # Opt-in material: promoted out of templates/hooks/, where nothing invoked them
        # either. Promotion changed where they live, not whether they run.
        "auto-checkpoint.sh",
        "check-comment-replacement.sh",
        # Ships deliberately unwired, and said so in docs/HOOKS.md long before this
        # test existed -- which is how that file came to contradict its own opening
        # sentence. Found by this test, not by a reader.
        "post-implement.sh",
        # Shared library, not a hook.
        "lib.sh",
    }

    def _hooks(self):
        return sorted(os.path.basename(p) for p in
                      glob.glob(os.path.join(CLAUDE_DIR, "hooks", "*.sh")))

    def test_every_hook_is_wired_or_declared_inert(self):
        settings = os.path.join(CLAUDE_DIR, "settings.json")
        with open(settings, encoding="utf-8") as fh:
            wiring = fh.read()
        registry = os.path.join(CLAUDE_DIR, "hooks", "dispatch-registry.json")
        if os.path.isfile(registry):
            with open(registry, encoding="utf-8") as fh:
                wiring += fh.read()
        # A wrapper resolving a hook by name counts as reachable.
        for path in glob.glob(os.path.join(CLAUDE_DIR, "hooks", "*.sh")):
            with open(path, encoding="utf-8") as fh:
                wiring += fh.read().replace(os.path.basename(path), "")

        unreachable = [h for h in self._hooks()
                       if h not in TestHookWiringIsHonest.UNWIRED and h not in wiring]
        assert unreachable == [], (
            f"hooks reachable from nothing and not declared inert: {unreachable}")

    def test_the_inert_list_does_not_hide_a_wired_hook(self):
        """The allowlist must not grow to cover hooks that ARE wired -- that would
        make the test pass by shrinking what it checks."""
        with open(os.path.join(CLAUDE_DIR, "settings.json"), encoding="utf-8") as fh:
            settings = fh.read()
        wired_but_listed = [h for h in TestHookWiringIsHonest.UNWIRED if h in settings]
        assert wired_but_listed == [], (
            f"declared inert but wired in settings.json: {wired_but_listed}")

    def test_the_docs_do_not_claim_every_hook_is_wired(self):
        """The specific false sentence, pinned. Reads the docs, because the two tests
        above pass just as well beside prose that contradicts them."""
        for rel in ("README.md", "docs/HOOKS.md"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                body = fh.read()
            assert "all are wired" not in body, f"{rel} claims every hook is wired"
            assert "library), all\nwired" not in body, f"{rel} claims every hook is wired"

class TestRootFiles:
    """Verify root-level files exist."""

    def test_readme(self):
        assert os.path.exists(os.path.join(ROOT, 'README.md'))

    def test_license(self):
        assert os.path.exists(os.path.join(ROOT, 'LICENSE'))

    def test_contributing(self):
        assert os.path.exists(os.path.join(ROOT, 'CONTRIBUTING.md'))

    def test_changelog(self):
        assert os.path.exists(os.path.join(ROOT, 'CHANGELOG.md'))

    def test_security(self):
        assert os.path.exists(os.path.join(ROOT, 'SECURITY.md'))

    def test_install_script(self):
        path = os.path.join(ROOT, 'install.sh')
        assert os.path.exists(path)
        assert os.access(path, os.X_OK)

    def test_gitignore(self):
        assert os.path.exists(os.path.join(ROOT, '.gitignore'))

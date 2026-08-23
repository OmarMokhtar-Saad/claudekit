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

    def test_modes_live_in_the_canonical_tree(self):
        modes = os.path.join(CLAUDE_DIR, "modes")
        assert os.path.isdir(modes)
        assert [f for f in os.listdir(modes) if f.endswith(".md")]

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

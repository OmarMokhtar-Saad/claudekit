"""Tests for ClaudeKit directory structure and file integrity."""

import glob
import json
import os
import re

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

    `README.md` and `docs/HOOKS.md` said "26 hooks ship ... all are wired" while three
    were referenced by nothing. A reader who believes `auto-checkpoint.sh` is protecting
    their session and never configures a real checkpoint is exactly the failure hard
    rule 6 exists to prevent: inert scripts advertised as active guardrails.

    Reachability is derived STRUCTURALLY. The first version of this test concatenated
    every hook's source and asked whether a name appeared anywhere in the blob, which
    granted reachability from prose. Review demonstrated two holes with it green:
    deleting every `pre-push.sh` row from settings.json AND dispatch-registry.json left
    it passing, because `dispatch.sh` mentions `pre-push.sh` in a COMMENT; and a
    brand-new inert `.py` hook passed while `gen-docs` counted it into the published
    number, because the glob was `*.sh` only.

    The hook set is taken from `gen-docs` itself, so what is tested is exactly what is
    counted -- a hook that is published but untested is the gap that let a `.py` file
    through.
    """

    UNWIRED = {
        # Opt-in material, promoted out of templates/hooks/ in task 008 batch 1 where
        # nothing invoked them either. Promotion changed where they live, not whether
        # they run.
        "auto-checkpoint.sh",
        "check-comment-replacement.sh",
        # Ships deliberately unwired and said so at docs/HOOKS.md long before this test
        # existed -- which is how that file came to contradict its own opening sentence.
        "post-implement.sh",
    }

    @staticmethod
    def _gen_docs():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_gen_docs", os.path.join(ROOT, "scripts", "gen-docs.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _published_hooks():
        """Exactly the set gen-docs publishes a count for: every hook file minus the
        helper libraries it already excludes structurally."""
        gd = TestHookWiringIsHonest._gen_docs()
        files = gd._hook_files()
        return sorted(p.name for p in files if not gd._is_helper_module(p, files))

    #: A hook invocation, as opposed to a mention. Requires the name to sit in COMMAND
    #: position -- after an interpreter, `exec`, `source`/`.`, or as a `$SCRIPT_DIR/x`
    #: style path -- so prose that happens to contain a filename is not an invocation.
    _INVOCATION = re.compile(
        r"(?:bash|sh|zsh|python3?|exec|source|\.)\s+[^\s;|&]*?"
        r"([A-Za-z0-9._-]+\.(?:sh|py))"
        r"|[\"']?\$(?:SCRIPT_DIR|ROOT|CLAUDE_DIR|HOOKS_DIR)[^\s\"';|&]*/"
        r"([A-Za-z0-9._-]+\.(?:sh|py))")

    @staticmethod
    def _strip_comments(text):
        """Comment text is documentation, not an invocation.

        The first version split on `" #"` only, so a comment preceded by a TAB -- or by
        nothing at all -- survived and was then substring-matched as a call. Round 3
        re-exploited exactly that: `true\t#resolves pre-push.sh` appended to dispatch.sh
        kept a fully unwired `pre-push.sh` looking reachable, with the whole class green.
        Any `#` outside a single- or double-quoted span now ends the line.
        """
        out = []
        for line in text.splitlines():
            quote = None
            cut = len(line)
            for pos, ch in enumerate(line):
                if quote:
                    if ch == quote:
                        quote = None
                elif ch in "\"'":
                    quote = ch
                elif ch == "#":
                    cut = pos
                    break
            out.append(line[:cut])
        return "\n".join(out)

    @classmethod
    def _wired(cls):
        """Names reachable from a declaration: a settings.json command string or a
        dispatch-registry row. Parsed, not grepped."""
        wired = set()
        with open(os.path.join(CLAUDE_DIR, "settings.json"), encoding="utf-8") as fh:
            settings = fh.read()
        wired.update(re.findall(r"\.claude/hooks/([A-Za-z0-9._-]+)", settings))

        registry = os.path.join(CLAUDE_DIR, "hooks", "dispatch-registry.json")
        if os.path.isfile(registry):
            with open(registry, encoding="utf-8") as fh:
                doc = json.load(fh)
            for rows in doc.get("events", {}).values():
                for row in rows:
                    if isinstance(row, dict) and row.get("file"):
                        wired.add(row["file"])
        return wired

    @classmethod
    def _wrapper_resolved(cls, published):
        """Names a REACHABLE hook actually INVOKES. A hook that is itself unreachable
        cannot confer reachability, so the inert set is excluded.

        Matched by extracting invocations, not by asking whether a name appears
        somewhere in the byte stream. The substring form let a SHORTER name inherit a
        LONGER one's wiring -- round 3 renamed `command-log-audit.sh` to `guard.sh`,
        dropped its registry row, and every test stayed green because `guard.sh` is a
        substring of the `file-guard.sh` that a wrapper legitimately names.
        """
        resolved = set()
        known = set(published)
        for name in published:
            if name in cls.UNWIRED:
                continue
            path = os.path.join(CLAUDE_DIR, "hooks", name)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                body = cls._strip_comments(fh.read())
            for match in cls._INVOCATION.finditer(body):
                called = match.group(1) or match.group(2)
                if called and called != name and called in known:
                    resolved.add(called)
        return resolved
    def test_every_hook_is_wired_or_declared_inert(self):
        published = self._published_hooks()
        reachable = self._wired() | self._wrapper_resolved(published)
        unreachable = [h for h in published
                       if h not in reachable and h not in TestHookWiringIsHonest.UNWIRED]
        assert unreachable == [], (
            f"hooks reachable from nothing and not declared inert: {unreachable}")

    def test_the_inert_list_does_not_hide_a_wired_hook(self):
        """The allowlist must not grow to cover hooks that ARE wired -- that would make
        the test pass by shrinking what it checks. Reads the dispatch registry too: the
        first version checked only settings.json, so a dispatcher-wired hook could be
        declared inert unchallenged."""
        wired_but_listed = sorted(TestHookWiringIsHonest.UNWIRED & self._wired())
        assert wired_but_listed == [], (
            f"declared inert but actually wired: {wired_but_listed}")

    def test_the_inert_list_names_only_hooks_that_exist(self):
        """A stale entry silently shrinks the checked set."""
        published = set(self._published_hooks())
        ghosts = sorted(TestHookWiringIsHonest.UNWIRED - published)
        assert ghosts == [], f"UNWIRED names hooks that do not ship: {ghosts}"

    def test_the_published_reachable_count_matches_the_docs(self):
        """The prose carries a hand-written "23 are reachable" next to a generated 26.
        That pairing is exactly how "26 ... all are wired" went stale. Derived here so
        the sentence cannot drift from the tree."""
        published = self._published_hooks()
        reachable = len(published) - len(TestHookWiringIsHonest.UNWIRED)
        for rel in ("README.md", "docs/HOOKS.md"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                # Normalised: the docs hard-wrap, so "23 are\nreachable" is the same
                # sentence as "23 are reachable" and a raw substring misses it.
                body = " ".join(fh.read().split())
            assert f"{reachable} are reachable" in body, (
                f"{rel} does not state the derived reachable count ({reachable})")

    def test_the_docs_do_not_claim_every_hook_is_wired(self):
        """The specific false sentence, pinned. The tests above pass just as well beside
        prose that contradicts them."""
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

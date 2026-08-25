"""Task 008 batch 2: the five merged-away skills, asserted by content.

Each merge kept the UNION of operative rules. The only copy of the merged-away
text is now the survivor, so a silent regression is a `git show` away and
nobody notices. These fragments are what a regression would drop.

The fragment lists were DERIVED, not typed: every backtick span and dotted
identifier present in the deleted file and absent from the survivor before the
merge. Headings are asserted too, but never instead of the tokens -- checking
headings alone is exactly how batch 1 shipped a fold that had lost three
sections and the per-language formatting APIs.
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
SKILLS_DIR = os.path.join(ROOT, ".claude", "skills")
MIRROR_DIR = os.path.join(ROOT, ".agents", "skills")

REMOVED = [
    ("autonomous-loops", "autonomous-loop"),
    ("verification-loop", "verification-before-completion"),
    ("dependency-audit", "supply-chain-audit"),
    ("session-continuity", "context-keeper"),
    ("context-priming", "context-keeper"),
]

AUTONOMOUS_LOOP_UNION = [
    'Do NOT use when:',
    'Use when:',
    'UserService.get',
    '`flake8 src/`',
    '`max_iterations: 5`',
    '`npm test`',
    'e.g',
    'Convergence Criteria',
    'Hard Convergence',
    'Soft Convergence',
    'Iteration Budget',
    'Loop Design Patterns',
    'Test-Fix Loop',
    'Quality-Improve Loop',
    'Search-Refine Loop',
    'Safety Guards',
    'Progress Validation',
    'Idempotency Check',
    'Destructive Operation Block',
    'Loop State Tracking',
    'Anti-Patterns',
]

VERIFICATION_BEFORE_COMPLETION_UNION = [
    'Cargo.toml',
    'Manual review checklist:',
    'Node.js',
    'On failure:',
    'Pass criteria:',
    'Run this skill:',
    'Warnings:',
    '`.env`',
    'eslint.config',
    'go.mod',
    'hooks.log',
    'mypy.ini',
    'package-lock.json',
    'package.json',
    'pom.xml',
    'pyproject.toml',
    'pytest.ini',
    'quick-verify.sh',
    'setup.py',
    'tsconfig.json',
    'verify-loop.sh',
    'The Six Phases',
    'Build Verification',
    'Type Checking',
    'Linting',
    'Test Suite + Coverage',
    'Security Scan',
    'Diff Review',
    'Continuous Mode',
    'Integration with PostToolUse Hook',
]

SUPPLY_CHAIN_AUDIT_UNION = [
    'Cargo.toml',
    'Dependencies are liabilities, not just features.',
    'Gemfile.lock',
    'One dependency at a time. One version bump at a time. Tests after every change.',
    'Python',
    'Ruby',
    'Rust',
    '`bundle-audit check`',
    '`cargo audit`',
    '`govulncheck ./...`',
    '`npm audit`',
    '`pip-audit`',
    '`pnpm audit`',
    '`safety check`',
    '`yarn audit`',
    'build.gradle',
    'go.mod',
    'go.sum',
    'pnpm-lock.yaml',
    'poetry.lock',
    'pom.xml',
    'pyproject.toml',
    'CVE Assessment Process',
    'Semver Compatibility Analysis',
    'Upgrade Risk Matrix',
    'Changelog Review Checklist',
    'Safe Incremental Upgrade Process',
    'Rollback Strategy',
    'Dependency Health Signals',
    'When to Replace a Dependency',
    'Anti-Patterns',
]

CONTEXT_KEEPER_UNION = [
    '- ALWAYS check if state file exists before attempting to load',
    '- ALWAYS overwrite the previous session state (keep history array for past sessions)',
    '- ALWAYS save before the session ends if any meaningful work was done',
    '- ALWAYS use relative paths (relative to project root)',
    '- ALWAYS verify file integrity before resuming work',
    '- NEVER assume the codebase is unchanged since last session',
    "- NEVER re-read files that haven't changed since last read",
    '- NEVER save secrets, credentials, or API keys in the state file',
    'CLAUDE.md',
    'CONSTITUTION.md',
    'Capture gotchas',
    'Cargo.toml',
    'Check for state file',
    'Confirm to user',
    'Display context summary',
    'Flag conflicts',
    'Identify blockers',
    'Load key files',
    'Node.js',
    'Record decisions',
    'Resume or restart',
    'Summarize progress',
    'Track modifications',
    'Verify file state',
    'Write state file',
    '`.claude/project-graph.json`',
    '`.claude/project-index.md`',
    '`.claude/session-state.json`',
    '`.env.example`',
    '`.env`',
    '`.eslintrc`',
    '`.github/workflows/*.yml`',
    '`.prettierrc`',
    '`/prime`',
    '`/session load`',
    '`/session save`',
    '`CLAUDE.md`',
    '`CONSTITUTION.md`',
    '`Cargo.toml`',
    '`Dockerfile`',
    '`context.key_files`',
    '`docker-compose.yml`',
    '`git merge`',
    '`git pull`',
    '`hubs`',
    '`package.json`',
    '`path`',
    '`pyproject.toml`',
    '`python3 .claude/operations/scripts/project-graph.py`',
    '`query`',
    '`ruff.toml`',
    '`rustfmt.toml`',
    '`setup.cfg`',
    '`tsconfig.json`',
    'auth.ts',
    'codebase-mapping',
    'context.key_files',
    'coordinator',
    'docker-compose.yml',
    'index.ts',
    'planner',
    'project-graph.json',
    'project-graph.py',
    'project-index.md',
    'ruff.toml',
    'rustfmt.toml',
    'session-state.json',
    'setup.cfg',
    'tsconfig.json',
    'user.ts',
    'Session State File',
    'Save Rules',
    'Load Rules',
    'Session Summary Format',
    'Priming Sequence',
    'Load Project Identity',
    'Identify Tech Stack',
    'Load Active Conventions',
    'Priming Template',
    'Selective Priming',
    'Refresh Triggers',
]


def _body(skill):
    with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as fh:
        return fh.read()


class TestTheMergedNamesAreGone:
    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_removed_from_the_canonical_tree(self, old, survivor):
        assert not os.path.isfile(os.path.join(SKILLS_DIR, old, "SKILL.md"))

    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_removed_from_the_codex_mirror(self, old, survivor):
        """Owner decision 3: the deletions land in both trees. `.agents/skills/` is
        unshipped, but leaving the name there keeps the mis-routing hazard alive for
        anything reading that tree."""
        assert not os.path.isfile(os.path.join(MIRROR_DIR, old, "SKILL.md"))

    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_survivor_exists(self, old, survivor):
        assert os.path.isfile(os.path.join(SKILLS_DIR, survivor, "SKILL.md"))

    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_every_removed_name_still_resolves(self, old, survivor):
        """The sign-off requires a consumer to see a rename, not a deletion, for one
        release. `ck doctor` reads this map; gen-registry.py validates it."""
        import json
        path = os.path.join(SKILLS_DIR, "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            registry = json.load(fh)
        assert registry["renamed"].get(old) == survivor

    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_no_registry_row_left_behind(self, old, survivor):
        import json
        path = os.path.join(SKILLS_DIR, "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            registry = json.load(fh)
        assert old not in {s["id"] for s in registry["skills"]}


class TestTheUnionSurvived:
    @pytest.mark.parametrize("fragment", AUTONOMOUS_LOOP_UNION)
    def test_autonomous_loop_kept_the_union(self, fragment):
        """`autonomous-loops` merged into `autonomous-loop`."""
        assert fragment in _body("autonomous-loop"), (
            "autonomous-loops lost from autonomous-loop: " + fragment)

    @pytest.mark.parametrize("fragment", VERIFICATION_BEFORE_COMPLETION_UNION)
    def test_verification_before_completion_kept_the_union(self, fragment):
        """`verification-loop` merged into `verification-before-completion`."""
        assert fragment in _body("verification-before-completion"), (
            "verification-loop lost from verification-before-completion: " + fragment)

    @pytest.mark.parametrize("fragment", SUPPLY_CHAIN_AUDIT_UNION)
    def test_supply_chain_audit_kept_the_union(self, fragment):
        """`dependency-audit` merged into `supply-chain-audit`."""
        assert fragment in _body("supply-chain-audit"), (
            "dependency-audit lost from supply-chain-audit: " + fragment)

    @pytest.mark.parametrize("fragment", CONTEXT_KEEPER_UNION)
    def test_context_keeper_kept_the_union(self, fragment):
        """`session-continuity` + `context-priming` merged into `context-keeper`."""
        assert fragment in _body("context-keeper"), (
            "session-continuity + context-priming lost from context-keeper: " + fragment)


class TestTheSurvivorsCanRunWhatTheyNowTeach:
    def test_verification_survivor_declares_bash(self):
        """The grafted half is an executable runbook. The survivor declared no
        tools at all before the merge, so the frontmatter had to widen with it --
        a runbook in a skill that cannot run anything is decoration."""
        head = _body("verification-before-completion").split("---")[1]
        assert "allowed-tools:" in head and "Bash" in head

    def test_the_loop_skill_has_exactly_one_iteration_budget(self):
        """Two caps in one skill (5 from the pipeline, 10 from the quality pattern)
        is how a runaway loop gets argued into being legitimate. The seam has to
        say which one binds."""
        body = _body("autonomous-loop")
        assert "The cap that" in body and "unless the invoker raises it" in body

    def test_the_session_survivor_points_at_the_file_the_hook_reads(self):
        """context-keeper survived and session-continuity did not for exactly one
        reason: session-start.sh reads session-context.md and nothing reads
        session-state.json. If that stops being true, this merge was wrong."""
        hook = os.path.join(ROOT, ".claude", "hooks", "session-start.sh")
        with open(hook, encoding="utf-8") as fh:
            assert "session-context.md" in fh.read()
        assert "session-context.md" in _body("context-keeper")

    def test_the_onboarding_pair_was_not_merged(self):
        """Owner decision 2. codebase-mapping is the authoring contract for
        project-graph.py; it stays a separate skill and keeps its machinery."""
        assert os.path.isfile(os.path.join(SKILLS_DIR, "codebase-mapping", "SKILL.md"))
        assert os.path.isfile(
            os.path.join(SKILLS_DIR, "codebase-onboarding", "SKILL.md"))
        body = _body("codebase-mapping")
        assert "project-graph.py" in body and "project-graph.json" in body

    def test_token_budget_advisor_was_kept(self):
        """The sign-off folded it into a token-accounting skill. Measured: it shares
        no section with either survivor -- it is a response-depth menu. Owner
        decision 1 kept it standing."""
        body = _body("token-budget-advisor")
        assert "25% Essential" in body and "100% Exhaustive" in body


class TestNoConsumerPointsAtADeletedSkill:
    """A removed name may still be *narrated*. What may not survive is a name in
    load position, or a live document still describing it as a component that exists.

    The first version of this class scanned only `.claude/agents|commands|skills`,
    which was narrower than the plan it was meant to prove -- and review found a real
    stale reference sitting outside that scope. LIVE_ROOTS is the promised scope.

    RECORD_ROOTS are excluded on a stated principle, not for convenience: a dated
    record of what was true when it was written is falsified by being edited. Spent
    plans, review records, CHANGELOG history, `.ai/` session logs and `review/` are
    records. `.claude/plans/plan-skill-loading-contract.md` is one of them -- its ops
    are already in `plans/archive/`, and its table is a measurement of the corpus as
    it stood, not an instruction to load anything.
    """

    LIVE_ROOTS = (".claude/agents", ".claude/commands", ".claude/skills",
                  ".claude/hooks", ".claude/operations", "docs", "src/claudekit",
                  "scripts")
    LIVE_FILES = ("README.md",)
    #: The survivor is allowed to name its own sources in prose.
    OWN_SEAM = {
        "autonomous-loops": "autonomous-loop",
        "verification-loop": "verification-before-completion",
        "dependency-audit": "supply-chain-audit",
        "session-continuity": "context-keeper",
        "context-priming": "context-keeper",
    }

    # A RENAME MAP has to name both sides. `fleet-sync.py` carries the old -> new
    # table that drives the downstream dedupe, so every removed id appears in it by
    # design -- and it appeared there only after this gate last ran green, because
    # the file was added to the tree after that suite run (521f4b9).
    #
    # Allowed by exact path, not by directory or glob: the gate's real target is a
    # CONSUMER pointing at a deleted skill, and a blanket exemption for
    # `.claude/operations/` would stop catching exactly that. If a second tool ever
    # needs the same allowance, add it here by name and say why.
    RENAME_MAP_FILES = (".claude/operations/scripts/fleet-sync.py",)

    def _live_files(self):
        for rel in self.LIVE_ROOTS:
            base = os.path.join(ROOT, rel)
            if not os.path.isdir(base):
                continue
            for dirpath, _dirnames, filenames in os.walk(base):
                for fname in filenames:
                    if not fname.endswith((".md", ".json", ".py", ".sh")):
                        continue
                    if fname == "skills-registry.json":
                        # The `renamed` map is the ONE place a removed name belongs.
                        continue
                    if fname.endswith(".log"):
                        continue
                    yield os.path.join(dirpath, fname)
        for rel in self.LIVE_FILES:
            yield os.path.join(ROOT, rel)

    def test_the_promised_scope_is_actually_the_scope(self):
        """The scope claim is itself asserted, because the first version of this
        class quietly checked three directories while the plan promised eight."""
        assert set(self.LIVE_ROOTS) >= {
            ".claude/agents", ".claude/commands", ".claude/skills", "docs",
            "src/claudekit", "scripts"}
        assert "README.md" in self.LIVE_FILES

    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_no_load_directive_names_a_deleted_skill(self, old, survivor):
        """`**skill-name**` is the form every agent, command and skill Integration
        list uses to tell the model what to load."""
        hits = []
        for path in self._live_files():
            with open(path, encoding="utf-8", errors="replace") as fh:
                if "**%s**" % old in fh.read():
                    hits.append(os.path.relpath(path, ROOT))
        assert hits == [], "%s still in load position: %s" % (old, hits)

    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_no_bare_reference_in_a_live_document(self, old, survivor):
        allowed = {os.path.abspath(
            os.path.join(SKILLS_DIR, self.OWN_SEAM[old], "SKILL.md"))}
        allowed |= {os.path.abspath(os.path.join(ROOT, rel))
                    for rel in self.RENAME_MAP_FILES}
        hits = []
        for path in self._live_files():
            if os.path.abspath(path) in allowed:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                if old in fh.read():
                    hits.append(os.path.relpath(path, ROOT))
        assert hits == [], "%s still referenced by: %s" % (old, hits)

    @pytest.mark.parametrize("old,survivor", REMOVED)
    def test_the_rename_map_allowance_still_earns_itself(self, old, survivor):
        """An exemption that stops being needed becomes a hole nobody notices. Every
        allowed file must still carry BOTH sides of the mapping -- if it no longer
        names the old id, delete its entry from RENAME_MAP_FILES."""
        for rel in self.RENAME_MAP_FILES:
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            body = open(path, encoding="utf-8", errors="replace").read()
            assert old in body and survivor in body, (
                "%s no longer maps %s -> %s; drop it from RENAME_MAP_FILES rather "
                "than leaving an exemption that guards nothing" % (rel, old, survivor))

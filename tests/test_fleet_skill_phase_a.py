"""Phase A of plan-fleet-skill-enhancement: the JVM checklists, and three repairs.

`code-reviewer` routed per-language checklists for Python and TypeScript only, while
9 of the 17 fleet projects are Java/Maven or Kotlin/Gradle -- so the reviewer that
loads a checklist by extension had nothing to load for `.java` or `.kt`.

The three repairs in the same phase are all "the asset exists but does not do its
job": `using-superpowers` routed code review at two PR-etiquette skills instead of
`code-reviewer`, `mcp-integration` documented a server roster this environment does
not have, and `security-checklist` carried zero executable detection content.

What these tests prove: the assets exist, are shaped like their siblings, are routed
to, and carry the specific content each defect was about. What they do NOT prove:
that a reviewer handed a real Java diff produces a better review -- no eval cassettes
exist for that, same gap the cluster-3 tests recorded.
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".claude", "skills")
AGENTS = os.path.join(ROOT, ".claude", "agents")

NEW = ["java-review-checklist", "kotlin-review-checklist"]
ALL_FOUR = ["python-review-checklist", "typescript-review-checklist"] + NEW

# The description is the only part of a skill that is ALWAYS in context. The floor
# row it lands in has ~1000 bytes of headroom; a long description spends it.
DESCRIPTION_CEILING = 160


def _skill(name):
    with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as fh:
        return fh.read()


def _agent(name):
    with open(os.path.join(AGENTS, name + ".md"), encoding="utf-8") as fh:
        return fh.read()


def _frontmatter(body):
    """The frontmatter block as a dict of raw string values. Deliberately not YAML:
    the corpus has no yaml dependency and these files are flat key: value."""
    assert body.startswith("---\n"), "no frontmatter"
    block = body.split("---\n", 2)[1]
    out = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out



# Every quoted pattern operand of every grep on a line -- not just the first, and not
# only single-quoted ones. The first version anchored with `re.match` and a greedy
# `'(.*)'`, which had three proven holes: a double-quoted broken ERE shipped green, the
# second grep of a `... | grep -v '...'` filter was never validated, and the greedy
# capture swallowed trailing `--include='...'` operands so 6 of 25 patterns were
# validated as something other than themselves. `'"'"'` inside a single-quoted pattern
# is matched explicitly, since that idiom is exactly what these blocks use.
_GREP_PATTERN = re.compile(
    r"""grep\s+((?:-[a-zA-Z]+\s+)*)(?:'((?:[^']|'"'"')*)'|"([^"]*)")"""
)


def _detect_blocks():
    """Every fenced `# Detect` block in the security checklist, as raw shell."""
    return re.findall(r"```bash\n# Detect\n(.*?)```", _skill("security-checklist"), re.S)


class TestTheJvmChecklistsExistAndAreShapedLikeTheirSiblings:
    @pytest.mark.parametrize("name", NEW)
    def test_the_skill_exists(self, name):
        assert os.path.isfile(os.path.join(SKILLS, name, "SKILL.md"))

    @pytest.mark.parametrize("name", NEW)
    def test_frontmatter_matches_the_sibling_contract(self, name):
        fm = _frontmatter(_skill(name))
        assert fm["name"] == name
        assert fm["user-invocable"] == "false", "a checklist is loaded, never invoked"
        assert fm["allowed-tools"] == "Read, Grep, Glob, Bash"
        assert fm["description"]

    @pytest.mark.parametrize("name", NEW)
    def test_the_description_stays_inside_the_always_on_budget(self, name):
        """NEW only, deliberately. The two incumbent checklists predate this ceiling
        and measure 243 and 216 -- parameterizing this over all four would red the
        suite on arrival and say nothing about the change under test. Trimming them
        is a separate, separately-reviewed edit; the floor row below is what actually
        binds for all of them."""
        desc = _frontmatter(_skill(name))["description"]
        assert len(desc) <= DESCRIPTION_CEILING, (name, len(desc))

    @pytest.mark.parametrize("name", NEW)
    def test_it_says_what_loads_it_and_when(self, name):
        body = _skill(name)
        assert "code-reviewer" in body
        assert "diff under review contains" in body

    @pytest.mark.parametrize("name", NEW)
    def test_it_carries_the_sibling_sections(self, name):
        body = _skill(name)
        for heading in ("## Review Dimensions", "## Automated Checks", "## Report Format"):
            assert heading in body, (name, heading)
        assert "APPROVE | REQUEST_CHANGES | BLOCK" in body

    @pytest.mark.parametrize("name", NEW)
    def test_every_dimension_shows_the_bad_and_the_good(self, name):
        """A checklist that names an anti-pattern without showing the fix is a
        vocabulary list. Each of the seven dimensions carries a contrasting pair."""
        body = _skill(name)
        dimensions = re.findall(r"^### \d+\. ", body, re.M)
        assert len(dimensions) == 7, dimensions
        assert body.count("// Bad") >= 7, body.count("// Bad")
        assert body.count("// Good") >= 7, body.count("// Good")

    def test_the_java_checklist_covers_its_named_security_patterns(self):
        body = _skill("java-review-checklist")
        for pattern in ("PreparedStatement", "ProcessBuilder", "disallow-doctype-decl",
                        "ObjectInputStream", "InterruptedException", "hashCode",
                        "volatile", "SimpleDateFormat"):
            assert pattern in body, pattern

    def test_the_kotlin_checklist_covers_its_named_security_patterns(self):
        body = _skill("kotlin-review-checklist")
        for pattern in ("CancellationException", "GlobalScope", "runBlocking",
                        "prepareStatement", "ProcessBuilder", "ObjectInputStream",
                        "@JvmStatic", "lateinit"):
            assert pattern in body, pattern

    @pytest.mark.parametrize("name,build", [("java-review-checklist", "mvn"),
                                            ("kotlin-review-checklist", "gradlew")])
    def test_automated_checks_detect_the_toolchain_instead_of_assuming_it(self, name, build):
        """A fleet project may have no SpotBugs and no detekt. Invoking one that is
        not configured produces a failure the reviewer then has to explain away."""
        checks = _skill(name).split("## Automated Checks", 1)[1]
        assert build in checks
        assert "ONLY if" in checks, "static analysis must be guarded by a detection"


class TestCodeReviewerRoutesAllFourLanguages:
    @pytest.mark.parametrize("name", ALL_FOUR)
    def test_the_checklist_is_declared(self, name):
        assert name in _agent("code-reviewer"), name

    @pytest.mark.parametrize("name,ext", [("java-review-checklist", "`.java`"),
                                          ("kotlin-review-checklist", "`.kt`")])
    def test_the_routing_line_names_the_extension(self, name, ext):
        line = [ln for ln in _agent("code-reviewer").splitlines() if name in ln][0]
        assert ext in line, line

    @pytest.mark.parametrize("name", ALL_FOUR)
    def test_they_are_on_demand_not_mandatory(self, name):
        body = _agent("code-reviewer")
        assert body.index(name) > body.index("**On demand")

    def test_the_registry_is_in_sync_with_what_the_agent_declares(self):
        """Asserting the two rows are present would assert a fact no ops.json can
        produce: `run_command` is allowlisted to formatters only, so no operations
        config can invoke a generator, and `gen-registry.py` is an out-of-band A7
        step by design. So assert the INVARIANT instead of the post-state -- this
        goes red both when the regen was skipped and when someone hand-edits the
        registry, which asserting the rows directly would not catch."""
        import subprocess
        proc = subprocess.run(
            ["python3", os.path.join(ROOT, "scripts", "gen-registry.py"), "--check"],
            capture_output=True, text=True, cwd=ROOT)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    @pytest.mark.parametrize("name", NEW)
    def test_the_registry_records_the_dependency(self, name):
        """Binds only after the A7 regen above passes -- which is the point: the
        checklist is dead prose until `code-reviewer` is recorded as loading it."""
        with open(os.path.join(SKILLS, "skills-registry.json"), encoding="utf-8") as fh:
            registry = json.load(fh)
        rows = {s["id"]: s for s in registry["skills"]}
        assert name in rows, name
        assert "code-reviewer" in rows[name]["usedBy"], name


class TestNoChecklistEmitsAScoreTheReviewerForbids:
    """`code-reviewer.md` Exit Rule: "The code-review gate is a blocking-finding count,
    not a score. Do not emit a numeric score: a number invites another round over
    findings that do not block." All four checklists shipped a `### Score: XX/100`
    line anyway -- the two new ones inherited it from the two incumbents."""

    @pytest.mark.parametrize("name", ALL_FOUR)
    def test_the_report_format_asks_for_no_number(self, name):
        body = _skill(name)
        assert "Score: XX/100" not in body, name
        assert "Blocking findings:" in body, name

    def test_the_agent_still_says_so(self):
        """If the rule is ever relaxed in the agent, this pair should be revisited
        together rather than drifting apart again."""
        assert "not a score" in _agent("code-reviewer")


class TestSecurityChecklistIsExecutableNotJustProse:
    """It shipped with zero commands: every risk section said 'what to look for' and
    then named no pattern. A reviewer cannot run prose."""

    def test_every_risk_section_carries_a_detect_block(self):
        body = _skill("security-checklist")
        risks = body.count("### Risk: Severity")
        detects = body.count("# Detect")
        assert risks >= 9, risks
        assert detects >= risks, (detects, risks)

    def test_the_detect_blocks_parse_as_shell(self):
        """Balanced quoting only. This is the weaker of the two checks and is NOT
        what catches a wrong regex -- the next test is."""
        import subprocess
        blocks = _detect_blocks()
        assert len(blocks) >= 9, len(blocks)
        for block in blocks:
            proc = subprocess.run(["bash", "-n"], input=block, text=True,
                                  capture_output=True)
            assert proc.returncode == 0, (proc.stderr, block)

    def test_every_detect_pattern_is_a_regex_grep_accepts(self):
        """`bash -n` proves the quoting balances, NOT that the pattern is valid ERE --
        and ERE is where this actually broke. An early draft carried
        `yaml\\.load\\((?!.*SafeLoader)`, a PCRE lookahead: bash parsed it happily and
        grep rejected it with `repetition-operator operand invalid`. So hand every
        pattern to grep itself, against /dev/null so nothing is searched. grep exits
        2 on a bad pattern, 1 on no match, 0 on match -- only 2 is a failure here.

        Python's `re` is NOT a substitute: it accepts the lookahead grep refuses, so
        compiling with `re` would have passed the exact bug this test exists for.
        """
        import subprocess
        patterns = []
        for block in _detect_blocks():
            for line in block.splitlines():
                for m in _GREP_PATTERN.finditer(line):
                    flags = "-E" if "E" in m.group(1) else ""
                    single, double = m.group(2), m.group(3)
                    patterns.append((flags, single if single is not None else double))
        assert len(patterns) >= 25, len(patterns)
        # A count floor alone would not notice a NEW line the regex cannot see:
        # unquoted patterns, backticks, or a --long-opt before the pattern are all
        # silently skipped rather than mis-validated. So assert COVERAGE -- every
        # `grep ` token in every block is accounted for by an extracted pattern.
        greps = sum(b.count("grep ") for b in _detect_blocks())
        assert len(patterns) == greps, (
            "%d grep invocations but %d patterns extracted -- a Detect line is written "
            "in a form _GREP_PATTERN cannot see" % (greps, len(patterns)))
        for flags, pattern in patterns:
            argv = ["grep"] + ([flags] if flags else []) + [pattern, "/dev/null"]
            proc = subprocess.run(argv, capture_output=True, text=True)
            assert proc.returncode != 2, (pattern, proc.stderr)

    def test_it_escalates_to_the_skills_that_go_deeper(self):
        body = _skill("security-checklist")
        assert "## Escalation" in body
        for target in ("differential-security-review", "insecure-defaults",
                       "supply-chain-audit", "prompt-injection-defense",
                       "verification-gap-lens"):
            assert target in body, target
            assert os.path.isdir(os.path.join(SKILLS, target)), target

    def test_it_still_frames_the_patterns_honestly(self):
        """Hard rule 6: a grep list is a speed bump, not a sandbox. A clean grep is
        not evidence of absence, and the skill has to say so."""
        assert "not a sandbox" in _skill("security-checklist")


class TestMcpIntegrationDescribesDetectionNotAFixedRoster:
    def test_the_absent_servers_are_gone_as_sections(self):
        body = _skill("mcp-integration")
        for ghost in ("### When to Use Sequential Thinking", "### When to Use Playwright",
                      "### When to Use Memory", "### When to Use Filesystem"):
            assert ghost not in body, ghost

    def test_it_tells_you_to_measure_the_roster(self):
        body = _skill("mcp-integration")
        assert "claude mcp list" in body
        assert "ToolSearch" in body

    def test_it_agrees_with_the_token_policy_on_context7(self):
        """CLAUDE.md: the main agent calls context7 itself, because web-researcher has
        no MCP access and delegating spends a web search for nothing."""
        body = _skill("mcp-integration")
        assert "context7" in body
        assert "web-researcher" in body

    def test_the_rewrite_did_not_grow_the_file(self):
        """It is a description-bearing skill on the always-on floor; the repair had to
        pay for itself."""
        size = os.path.getsize(os.path.join(SKILLS, "mcp-integration", "SKILL.md"))
        assert size <= 6575, size


class TestUsingSuperpowersRoutesCodeReviewAtTheReviewer:
    def test_review_this_code_reaches_code_reviewer(self):
        row = [ln for ln in _skill("using-superpowers").splitlines()
               if '"Review this code"' in ln][0]
        assert "code-reviewer" in row, row
        assert "review-checklist" in row, row

    def test_the_pr_etiquette_skills_kept_the_case_they_cover(self):
        body = _skill("using-superpowers")
        assert "requesting-code-review" in body
        assert "receiving-code-review" in body

    def test_the_priority_list_names_the_current_verification_skills(self):
        body = _skill("using-superpowers")
        for name in ("verification-gap-lens", "context-budget"):
            assert name in body, name
            assert os.path.isdir(os.path.join(SKILLS, name)), name

    def test_it_no_longer_claims_an_irrelevant_skill_is_free(self):
        """It said 'There is no penalty for invoking a skill that turns out to be
        irrelevant' -- which contradicts context-budget, the skill that exists
        because loading is exactly what costs."""
        body = _skill("using-superpowers")
        assert "There is no penalty for invoking a skill" not in body
        assert "context-budget" in body


# ---------------------------------------------------------------------------
# A2b + D1/D3: the testing-skill trio, prompt-evaluation, and the ToB
# enrichment of differential-security-review.
# ---------------------------------------------------------------------------

A2B = ["whitebox-invariant-testing", "defect-pinning", "ai-agent-testing"]
NEW_SKILLS = A2B + ["prompt-evaluation"]
# ToB authoring convention (plan D2). The trio are method skills, not encyclopedias.
TOB_LINE_CEILING = 500


class TestTheTestingSkillTrioExists:
    @pytest.mark.parametrize("name", NEW_SKILLS)
    def test_the_skill_exists(self, name):
        assert os.path.isfile(os.path.join(SKILLS, name, "SKILL.md"))

    @pytest.mark.parametrize("name", NEW_SKILLS)
    def test_frontmatter_is_complete(self, name):
        """D2 requires allowed-tools declared. Two of the three A2b specs originally
        omitted it -- caught in plan review round 1, so it is asserted here."""
        fm = _frontmatter(_skill(name))
        assert fm["name"] == name
        assert fm["allowed-tools"], name
        assert fm["user-invocable"] == ("true" if name == "prompt-evaluation" else "false")

    @pytest.mark.parametrize("name", NEW_SKILLS)
    def test_the_description_stays_inside_the_always_on_budget(self, name):
        """<=150, not the <=160 the per-language checklists use. The row measured
        8233/9000 BEFORE these four (767 headroom); adding 584 chars lands it at
        8817/9000, leaving ~183 -- about one more skill. The floor test below is what
        binds; this cap is what keeps the floor test from ever having to fail."""
        assert len(_frontmatter(_skill(name))["description"]) <= 150, name

    @pytest.mark.parametrize("name", NEW_SKILLS)
    def test_it_obeys_the_tob_line_ceiling(self, name):
        n = len(_skill(name).splitlines())
        assert n <= TOB_LINE_CEILING, (name, n)

    @pytest.mark.parametrize("name", NEW_SKILLS)
    def test_the_registry_records_it(self, name):
        with open(os.path.join(SKILLS, "skills-registry.json"), encoding="utf-8") as fh:
            rows = {s["id"] for s in json.load(fh)["skills"]}
        assert name in rows, name


class TestDefectPinningCarriesTheProtocolItPromises:
    """The plan specifies five things by name. A skill that names a protocol without
    stating it is the class of defect security-checklist shipped with."""

    def test_the_five_state_coverage_legend_is_present(self):
        body = _skill("defect-pinning")
        for mark in ("\u2705", "\U0001f534", "\u2b1c", "\U0001f527", "\u26d4"):
            assert mark in body, mark

    def test_it_states_the_quarantine_and_restore_protocol(self):
        body = _skill("defect-pinning")
        assert "@Ignore" in body
        assert "verbatim" in body.lower()
        # the step that makes pinning pay: a fixed pin loses its mark, it is not deleted
        assert "regression proof" in body

    def test_it_names_a_quarantine_mark_for_more_than_one_stack(self):
        body = _skill("defect-pinning")
        for mark in ("@Ignore", "@Disabled", "xfail", "t.Skip"):
            assert mark in body, mark

    def test_it_says_why_it_is_not_folded_into_the_invariant_skill(self):
        """Plan review round 1 asked for this justification explicitly."""
        body = _skill("defect-pinning")
        assert "regardless of how it was found" in body
        assert "whitebox-invariant-testing" in body


class TestTheTrioCrossLinksInsteadOfDuplicating:
    """This repo is consolidating near-duplicates (task 008). Three skills from one
    method must point at each other rather than restate each other."""

    def test_the_method_skill_points_at_the_protocol(self):
        assert "defect-pinning" in _skill("whitebox-invariant-testing")

    def test_the_agent_skill_points_at_both_and_at_its_eval_neighbours(self):
        body = _skill("ai-agent-testing")
        for target in ("whitebox-invariant-testing", "defect-pinning",
                       "prompt-evaluation", "eval-harness", "verification-gap-lens"):
            assert target in body, target

    @pytest.mark.parametrize("name", NEW_SKILLS)
    def test_every_cross_referenced_skill_actually_exists(self, name):
        """gen-registry validates registry rows, NOT prose cross-links -- so a skill
        named in a body but absent from disk ships as a broken pointer with nothing
        catching it. Plan review round 1 flagged exactly this risk for D3."""
        body = _skill(name)
        referenced = set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+){1,4})`", body))
        known = {d for d in os.listdir(SKILLS)
                 if os.path.isdir(os.path.join(SKILLS, d))}
        # Superset direction, NOT an intersection against a fixed name list. An
        # allowlist can only re-confirm names we already know exist; the pointer that
        # actually breaks is the one nobody listed -- a typo, or a skill renamed after
        # this test was written. Anything hyphenated that is not a known skill must be
        # declared here as deliberate non-skill prose.
        NOT_SKILL_IDS = {
            "eval-set-vy", "known-defects-test", "read-only", "line-by-line",
            "merge-gate", "one-liner", "fail-closed", "anti-fabrication",
            "position-swapped", "reference-match", "structured-output",
        }
        unknown = {t for t in referenced if t not in known} - NOT_SKILL_IDS
        assert not unknown, (
            f"{name} references hyphenated token(s) that are not skills on disk and are "
            f"not declared as prose: {sorted(unknown)}")


class TestPromptEvaluationIsPositionedAgainstEvalHarness:
    def test_it_says_it_does_not_gate_ci(self):
        body = _skill("prompt-evaluation")
        assert "eval-harness" in body
        assert "exploratory" in body.lower()

    def test_it_carries_the_one_judge_per_criterion_rule(self):
        """The whole reason the method works; a compound rubric halos."""
        body = _skill("prompt-evaluation")
        assert "halo" in body.lower()
        assert "criterion" in body

    def test_it_is_a_reimplementation_not_a_copy(self):
        """Upstream license is unstated, so provenance has to be on the file."""
        body = _skill("prompt-evaluation")
        assert "license is unstated" in body
        assert "46ki75" in body


class TestDifferentialSecurityReviewCarriesItsAttribution:
    def test_the_cc_by_sa_block_is_present_and_names_the_source(self):
        body = _skill("differential-security-review")
        assert "CC BY-SA 4.0" in body
        assert "trailofbits/skills" in body
        assert "Do not strip this attribution." in body

    def test_the_methodology_actually_landed(self):
        body = _skill("differential-security-review")
        assert "Risk-First Order" in body
        assert "ATTACKER:" in body and "OUTCOME:" in body

    def test_the_enrichment_stayed_inside_its_budget(self):
        """Plan D1 caps growth at 1.5 KB. The 7948 baseline is the pre-D1 size; this
        asserts the ceiling, so an unrelated future edit to the file will trip it --
        deliberately. Re-baseline consciously rather than letting the cap drift."""
        size = os.path.getsize(os.path.join(SKILLS, "differential-security-review", "SKILL.md"))
        assert size <= 7948 + 1536, (size, "re-baseline this cap if the growth is intended")


class TestTheAlwaysOnFloorDidNotRegress:
    def test_the_skill_description_row_is_within_budget(self):
        """Two new descriptions land in this row. It had ~1066 bytes of headroom."""
        import subprocess
        proc = subprocess.run(
            ["python3", os.path.join(ROOT, "scripts", "check-context-floor.py"),
             "--json"],
            capture_output=True, text=True, cwd=ROOT)
        data = json.loads(proc.stdout)
        assert data["sizes"]["skill descriptions"] <= data["budgets"]["skill descriptions"], (
            data["sizes"]["skill descriptions"], data["budgets"]["skill descriptions"])

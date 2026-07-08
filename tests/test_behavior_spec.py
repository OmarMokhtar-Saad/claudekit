"""Frontier-behavior spec anchors in the prompt corpus.

The 2026-07 corpus audit encoded ten operating patterns (parallel batching,
persistence, verification, adversarial self-check, evidence integrity, ...)
at specific high-leverage points. These tests pin the anchors so later edits
can't silently regress them. Each test names the pattern it guards.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
SHARED = os.path.join(ROOT, ".claude", "agents", "_shared")
AGENTS = os.path.join(ROOT, ".claude", "agents")
COMMANDS = os.path.join(ROOT, ".claude", "commands")
SKILLS = os.path.join(ROOT, ".claude", "skills")


def _read(*parts):
    with open(os.path.join(*parts)) as f:
        return f.read()


def _frontmatter_field(path, field):
    text = _read(path)
    match = re.search(rf"^{field}:\s*(.+)$", text.split("---", 2)[1], re.MULTILINE)
    return match.group(1).strip() if match else None


class TestParallelBatching:
    """Pattern 1: independent tool calls fire in ONE message."""

    def test_agent_template_mandates_batching(self):
        text = _read(SHARED, "AGENT_TEMPLATE.md")
        assert "ONE message" in text and "Batch independent tool calls" in text

    def test_using_superpowers_mandates_batching(self):
        text = _read(SKILLS, "using-superpowers", "SKILL.md")
        assert "ONE message" in text

    def test_task_spec_parallel_dispatch_is_single_message(self):
        text = _read(SHARED, "TASK_TOOL_SPECIFICATION.md")
        assert "ONE message" in text

    def test_no_three_problem_gate_in_dispatching(self):
        text = _read(SKILLS, "dispatching-parallel-agents", "SKILL.md")
        assert "Three or more independent problems" not in text
        assert "Only 1-2 problems" not in text

    def test_verify_command_batches_independent_phases(self):
        text = " ".join(_read(COMMANDS, "verify.md").split())
        assert "ONE batched message" in text


class TestPersistence:
    """Pattern 2: retry differently, never end a turn on a resolvable question."""

    def test_agent_template_retry_is_not_verbatim(self):
        text = _read(SHARED, "AGENT_TEMPLATE.md")
        assert "DIFFERENT approach" in text
        assert "Never retry more than once" not in text

    def test_coordinator_error_recovery_amends_inputs(self):
        text = _read(AGENTS, "coordinator.md")
        assert "never" in text.lower() and "amended inputs" in text
        assert "re-run the agent once with the same inputs" not in text.lower()

    def test_executing_plans_has_no_permission_loop(self):
        text = _read(SKILLS, "executing-plans", "SKILL.md")
        assert "Continue with the next batch?" not in text
        assert "continue autonomously" in text.lower()


class TestAdversarialSelfCheck:
    """Pattern 4: refute your own conclusion before claiming done."""

    def test_verification_protocol_has_refutation_pass(self):
        text = _read(SHARED, "VERIFICATION_PROTOCOL.md")
        assert "Refutation" in text and "What did I NOT run?" in text

    def test_verification_skill_has_refute_step(self):
        text = _read(SKILLS, "verification-before-completion", "SKILL.md")
        assert "REFUTE" in text

    def test_reviewer_refutes_against_filesystem(self):
        text = _read(AGENTS, "reviewer.md")
        assert "Refute" in text and "CRITICAL" in text


class TestEvidenceIntegrity:
    """Pattern 5: numbers come from executed output; templates never fake evidence."""

    def test_output_template_bans_invented_numbers(self):
        text = _read(SHARED, "OUTPUT_TEMPLATE.md")
        assert "did not compute or measure" in text
        assert "exempt from the caps" in text

    def test_token_optimization_exempts_evidence(self):
        text = _read(SKILLS, "token-optimization", "SKILL.md")
        assert "Verification evidence" in text

    def test_refine_success_banner_is_earned(self):
        text = _read(COMMANDS, "refine.md")
        assert "ops.json: validated and dry-run clean" not in text
        assert "execute-json-ops.py" in text  # post-approval dry-run actually runs

    def test_loop_start_gate_lines_require_real_output(self):
        text = _read(COMMANDS, "loop-start.md")
        assert "tests PASS (12/12)" not in text  # templated fake evidence removed


class TestModelRouting:
    """Routing corollary: judgment-dense roles on opus; gates never on haiku."""

    def test_planner_is_opus(self):
        assert _frontmatter_field(os.path.join(AGENTS, "planner.md"), "model") == "opus"

    def test_verifier_is_sonnet(self):
        assert _frontmatter_field(os.path.join(AGENTS, "verifier.md"), "model") == "sonnet"

    def test_reviewer_stays_opus(self):
        assert _frontmatter_field(os.path.join(AGENTS, "reviewer.md"), "model") == "opus"

    def test_plan_command_spawns_planner_on_opus(self):
        assert "--agent planner --model opus" in _read(COMMANDS, "plan.md")
        assert "--agent planner --model opus" in _read(COMMANDS, "refine.md")


class TestAgentRegistration:
    """Agent frontmatter must be valid YAML or Claude Code silently drops the
    agent from BOTH the Task tool and `claude -p --agent` ("agent not found").
    Root-caused 2026-07-08: bare <example> blocks between YAML fields had
    unregistered all 28 agents. Examples belong inside the description block
    scalar. Structural check (no pyyaml dependency): every frontmatter line is
    a known key, blank, or an indented block-scalar continuation."""

    KNOWN_KEYS = ("name", "description", "model", "color", "tools")

    def _frontmatters(self):
        for fname in sorted(os.listdir(AGENTS)):
            path = os.path.join(AGENTS, fname)
            if not fname.endswith(".md") or not os.path.isfile(path):
                continue
            text = _read(path)
            if not text.startswith("---\n"):
                continue  # shared docs without frontmatter (QUICK_START etc.)
            yield fname, text[4:text.index("\n---", 3) + 1]

    def test_frontmatter_is_structurally_valid_yaml(self):
        key_re = re.compile(r"^(%s):(\s|$)" % "|".join(self.KNOWN_KEYS))
        found_any = False
        for fname, fm in self._frontmatters():
            found_any = True
            for line in fm.split("\n"):
                if not line.strip():
                    continue
                if key_re.match(line) or line.startswith("  "):
                    continue
                raise AssertionError(
                    f"{fname}: frontmatter line is neither a known key nor an "
                    f"indented continuation (this un-registers the agent): {line!r}")
        assert found_any, "no agent frontmatter found — wrong path?"

    def test_frontmatter_parses_as_yaml_when_available(self):
        try:
            import yaml
        except ImportError:
            return  # structural test above still guards the bug class
        for fname, fm in self._frontmatters():
            data = yaml.safe_load(fm)
            assert isinstance(data, dict), f"{fname}: frontmatter not a mapping"
            for key in ("name", "description", "model"):
                assert data.get(key), f"{fname}: missing frontmatter key {key!r}"
            assert set(data) <= set(self.KNOWN_KEYS), \
                f"{fname}: unexpected frontmatter keys {set(data) - set(self.KNOWN_KEYS)}"


class TestContextBudget:
    """Task 009: agents preload at most 3 skills; depth loads on trigger.
    The 2026-07 audit measured 16,120 preloaded lines across 18 agents
    (coordinator alone: 12 skills / 2,397 lines) — this gate keeps it fixed."""

    MANDATORY_RE = re.compile(
        r"\*\*Mandatory \(load before any work, in order\):\*\*\n(.*?)(?=\n\*\*On demand|\nIf a mandatory)",
        re.S)
    SECTION_RE = re.compile(r"## Skill Loading\n(.*?)(?=\n## |\n---)", re.S)

    def _agents_with_skills(self):
        for fname in sorted(os.listdir(AGENTS)):
            path = os.path.join(AGENTS, fname)
            if not fname.endswith(".md") or not os.path.isfile(path):
                continue
            text = _read(path)
            if text.startswith("---\n") and self.SECTION_RE.search(text):
                yield fname, self.SECTION_RE.search(text).group(1)

    def test_no_agent_preloads_more_than_three_skills(self):
        found = 0
        for fname, section in self._agents_with_skills():
            found += 1
            m = self.MANDATORY_RE.search(section)
            assert m, f"{fname}: Skill Loading section lacks the Mandatory block"
            mandatory = re.findall(r"^\d+\. \*\*([a-z0-9-]+)\*\*", m.group(1), re.M)
            assert 1 <= len(mandatory) <= 3, \
                f"{fname}: {len(mandatory)} mandatory skills (max 3): {mandatory}"
            assert mandatory[0] == "using-superpowers", \
                f"{fname}: using-superpowers must be the first mandatory skill"
        assert found >= 15, f"only {found} agents with Skill Loading sections — wrong regex?"

    def test_on_demand_entries_declare_triggers(self):
        for fname, section in self._agents_with_skills():
            if "**On demand" not in section:
                continue
            on_demand = section.split("**On demand", 1)[1]
            for line in on_demand.split("\n"):
                if line.startswith("- **"):
                    assert "— load " in line, \
                        f"{fname}: on-demand skill without a load trigger: {line!r}"

    def test_registry_matches_agent_files(self):
        # gen-registry --check is the drift gate (same pattern as gen-docs).
        script = os.path.join(ROOT, "scripts", "gen-registry.py")
        result = subprocess.run(
            [sys.executable, script, "--check"],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, \
            f"registry drifted from agent files:\n{result.stdout}{result.stderr}"


class TestContractConsistency:
    """The written workflows must be executable as specified."""

    def test_no_broken_agents_references_in_commands(self):
        for name in os.listdir(COMMANDS):
            if not name.endswith(".md"):
                continue
            text = _read(COMMANDS, name)
            for line in text.splitlines():
                if "@agents/" in line:
                    raise AssertionError(f"{name}: broken '@agents/' ref (real path is .claude/agents/): {line.strip()}")

    def test_planner_frontmatter_matches_invocation_contract(self):
        # INVOCATION.md: planner gets Write (saves plan/ops) and NO Agent tool
        # (nested spawning banned); Bash is scoped to the ops validator.
        tools = _frontmatter_field(os.path.join(AGENTS, "planner.md"), "tools")
        assert "Write" in tools and "Agent" not in tools

    def test_reviewer_does_not_self_spawn_dual_reviewers(self):
        text = _read(AGENTS, "reviewer.md")
        assert "Spawn two independent sub-reviewers" not in text
        assert "orchestrated by the command layer" in text

    def test_invocation_table_covers_spawned_roles(self):
        text = _read(SHARED, "INVOCATION.md")
        for role in ("planner", "reviewer", "explore", "debugger", "verifier",
                     "implementer", "security-scanner", "silent-failure-hunter"):
            assert f"| {role}" in text, f"INVOCATION.md tool table missing row: {role}"

    def test_implementer_reads_validation_from_plan_not_opsjson(self):
        text = _read(AGENTS, "implementer.md")
        assert "from ops.json validation section" not in text
        assert "plan.md" in text

    def test_headless_stdout_delivery_contract(self):
        # Verified 2026-07-08: claude -p cannot write into .claude/** (platform
        # sensitive-path gate) — stdout is the delivery contract, commands save.
        assert "Headless fallback" in _read(AGENTS, "planner.md")
        assert "extract-json-from-plan.py" in _read(COMMANDS, "plan.md")
        assert "extract-json-from-plan.py" in _read(COMMANDS, "refine.md")
        assert "verification pending" in _read(AGENTS, "implementer.md")

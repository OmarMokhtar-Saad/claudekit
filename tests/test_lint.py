"""Behavioural tests for `ck lint`.

`duplicate-triggers` flags nothing against the corpus as it stands -- batch 2 removed
the overlapping skill descriptions -- so for that rule "the suite is green" and "the
rule does not run" look identical from the outside.

`skill-agent-costume` is NOT clean, and an earlier draft of this docstring claimed it
was. Two skills really do grant `Agent` (`gan-harness`, `opensource-pipeline`); they are
waived by name in `.claude/lint-baseline.json`, and the rule fires on any un-waived
grant. Review caught the false claim in `lint.py`'s docstring and in the plan; it
survived HERE for one more round, which is its own small lesson about correcting a
statement in every place it was made rather than the first place it was found.

Every rule is therefore proven by MUTATION: build a tree that violates it, assert the
finding, then assert the clean tree is silent. A gate that cannot be made to fail is
decoration -- this repo has shipped three of those, one of them this rule's first draft.
"""

import json
import os
import subprocess
import sys

import pytest

from claudekit import lint

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _corpus(tmp_path, commands=None, skills=None):
    """A minimal tree with the two directories the rules read."""
    cmd_dir = tmp_path / ".claude" / "commands"
    skill_dir = tmp_path / ".claude" / "skills"
    cmd_dir.mkdir(parents=True)
    skill_dir.mkdir(parents=True)
    for name, lines in (commands or {}).items():
        (cmd_dir / name).write_text("\n".join("line %d" % i for i in range(lines)) + "\n",
                                    encoding="utf-8")
    for name, body in (skills or {}).items():
        (skill_dir / name).mkdir()
        (skill_dir / name / "SKILL.md").write_text(body, encoding="utf-8")
    return str(tmp_path)


def _skill(description, allowed_tools=None):
    head = ["---", "name: x", "description: %s" % description]
    if allowed_tools:
        head.append("allowed-tools: %s" % allowed_tools)
    head += ["---", "", "# X", "", "body"]
    return "\n".join(head) + "\n"


class TestCommandBudgetRatchet:
    def test_a_new_command_over_budget_is_flagged(self, tmp_path):
        root = _corpus(tmp_path, commands={"big.md": lint.NEW_COMMAND_BUDGET + 1})
        findings = lint.check_command_budget(root)
        assert [f.rule for f in findings] == ["command-budget"]
        assert "is a new command" in findings[0].message

    def test_a_new_command_within_budget_is_silent(self, tmp_path):
        root = _corpus(tmp_path, commands={"small.md": lint.NEW_COMMAND_BUDGET})
        assert lint.check_command_budget(root) == []

    def test_an_existing_oversized_command_is_held_not_flagged(self, tmp_path):
        """The whole point of the ratchet. 0 of 55 commands met <=40 when this
        landed; a rule that failed on all of them is a rule someone disables."""
        root = _corpus(tmp_path, commands={"legacy.md": 466})
        lint.write_baseline(root, lint.current_command_lines(root))
        assert lint.check_command_budget(root) == []

    def test_growth_past_the_ratchet_is_flagged(self, tmp_path):
        root = _corpus(tmp_path, commands={"legacy.md": 100})
        lint.write_baseline(root, lint.current_command_lines(root))
        path = tmp_path / ".claude" / "commands" / "legacy.md"
        path.write_text(path.read_text(encoding="utf-8") + "one more line\n",
                        encoding="utf-8")
        findings = lint.check_command_budget(root)
        assert len(findings) == 1
        assert "grew to 101 lines; the ratchet allows 100" in findings[0].message

    def test_shrinking_is_always_allowed(self, tmp_path):
        root = _corpus(tmp_path, commands={"legacy.md": 100})
        lint.write_baseline(root, lint.current_command_lines(root))
        (tmp_path / ".claude" / "commands" / "legacy.md").write_text(
            "just one line\n", encoding="utf-8")
        assert lint.check_command_budget(root) == []

    def test_an_unreadable_baseline_fails_loud_not_open(self, tmp_path):
        """Fail-closed. If a corrupt baseline read as empty, every existing command
        would look new and a 466-line file would 'pass' a 40-line budget."""
        root = _corpus(tmp_path, commands={"legacy.md": 466})
        with open(lint.baseline_path(root), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with pytest.raises(RuntimeError):
            lint.check_command_budget(root)


class TestSkillAgentCostume:
    @pytest.mark.parametrize("declared", ["Read, Agent", "Agent", "Read, Task, Grep",
                                          "Read | Agent"])
    def test_a_skill_granted_agent_spawning_is_flagged(self, tmp_path, declared):
        root = _corpus(tmp_path, skills={"impostor": _skill("does things", declared)})
        findings = lint.check_skill_agent_costume(root)
        assert [f.rule for f in findings] == ["skill-agent-costume"], declared

    def test_the_yaml_BLOCK_LIST_form_is_read_too(self, tmp_path):
        """Review found this as a live false negative, not a hypothetical: the first
        version matched only a same-line value, and `gan-harness` and
        `opensource-pipeline` BOTH declare `allowed-tools` as a block list containing
        `Agent`. The rule skipped the exact grant it exists to catch, and the
        corpus-is-clean test passed over two real violations."""
        body = ("---\nname: impostor\ndescription: d\n"
                "allowed-tools:\n  - Agent\n  - Read\n---\n\n# X\n\nbody\n")
        root = _corpus(tmp_path, skills={"impostor": body})
        assert lint.declared_tools(body) == {"Agent", "Read"}
        assert len(lint.check_skill_agent_costume(root)) == 1

    #: Every YAML spelling of `allowed-tools` that must not evade the rule. Derived by
    #: PROBING the parser, not by reasoning about it: four of these (inline flow list,
    #: quoted value, quoted block item, trailing comment) each produced a token like
    #: `[Agent` or `Agent"` or `Agent # why` that did not equal "Agent", and every one
    #: was a silent evasion of a rule whose entire job is not being evaded.
    SPELLINGS = [
        "allowed-tools: Read, Agent",
        "allowed-tools: Read | Agent",
        "allowed-tools: [Agent, Read]",
        'allowed-tools: ["Agent"]',
        'allowed-tools: "Read, Agent"',
        "allowed-tools: 'Agent'",
        "allowed-tools: Read, Agent # why",
        "allowed-tools:\n  - Agent\n  - Read",
        "allowed-tools:\n    - Agent",
        "allowed-tools:\n- Agent",
        'allowed-tools:\n  - "Agent"',
        "allowed-tools: # nope\n  - Agent",
        "allowed-tools:\n  - Task",
    ]

    @pytest.mark.parametrize("declaration", SPELLINGS)
    def test_no_yaml_spelling_evades_the_rule(self, tmp_path, declaration):
        body = "---\nname: impostor\ndescription: d\n%s\n---\n\n# X\n\nbody\n" % declaration
        root = _corpus(tmp_path, skills={"impostor": body})
        assert len(lint.check_skill_agent_costume(root)) == 1, declaration

    def test_a_skill_with_no_spawning_tool_stays_silent(self, tmp_path):
        """The negative case, so the parametrized sweep above cannot pass by flagging
        everything it reads."""
        body = ("---\nname: fine\ndescription: d\nallowed-tools: Read, Bash\n"
                "---\n\n# X\n\nbody\n")
        root = _corpus(tmp_path, skills={"fine": body})
        assert lint.check_skill_agent_costume(root) == []

    def test_the_two_real_corpus_offenders_are_detected_when_unwaived(self):
        """The regression fixture for the finding above, against the SHIPPED files
        rather than a synthetic one -- so a future regex change that stops reading the
        block form goes red here even if the synthetic case still passes."""
        for name in ("gan-harness", "opensource-pipeline"):
            path = os.path.join(REPO, ".claude", "skills", name, "SKILL.md")
            with open(path, encoding="utf-8") as fh:
                assert "Agent" in lint.declared_tools(fh.read()), name

    def test_a_waiver_silences_only_the_named_skill(self, tmp_path):
        root = _corpus(tmp_path, skills={
            "waived": _skill("d", "Read, Agent"),
            "not-waived": _skill("d", "Read, Agent")})
        lint.write_baseline(root, {}, waivers={"waived": "deliberate, reason here"})
        findings = lint.check_skill_agent_costume(root)
        assert len(findings) == 1
        assert "not-waived" in findings[0].path

    def test_update_baseline_cannot_silently_drop_a_waiver(self, tmp_path):
        """Otherwise `--update-baseline` becomes a way to un-document a real
        violation while the suite stays green."""
        root = _corpus(tmp_path, skills={"waived": _skill("d", "Read, Agent")})
        lint.write_baseline(root, {}, waivers={"waived": "deliberate"})
        lint.write_baseline(root, {})          # re-record the ratchet only
        assert lint.load_waivers(root) == {"waived"}
        assert lint.check_skill_agent_costume(root) == []

    def test_ordinary_tool_grants_are_silent(self, tmp_path):
        root = _corpus(tmp_path, skills={
            "fine": _skill("does things", "Read, Bash, Grep, Glob")})
        assert lint.check_skill_agent_costume(root) == []

    def test_a_long_description_cannot_push_the_grant_out_of_view(self, tmp_path):
        """The frontmatter is parsed to its closing fence, not to a line cap. A rule
        that stopped reading after N lines could be evaded by padding the
        description -- which is exactly the length real descriptions have."""
        root = _corpus(tmp_path, skills={
            "impostor": _skill("x " * 400, "Read, Agent")})
        assert len(lint.check_skill_agent_costume(root)) == 1

    def test_the_shipped_corpus_has_exactly_the_two_known_waivers(self):
        """NOT "the corpus is clean" -- it is not. Two skills genuinely grant `Agent`
        and are waived by name with a reason. Asserting cleanliness here is what made
        the first version of this test vacuous."""
        assert lint.load_waivers(REPO) == {"gan-harness", "opensource-pipeline"}
        assert lint.check_skill_agent_costume(REPO) == []


class TestDuplicateTriggers:
    def test_two_skills_competing_for_one_prompt_are_flagged(self, tmp_path):
        shared = ("Use when auditing dependency trees for typosquatting, abandoned "
                  "packages and known vulnerabilities")
        root = _corpus(tmp_path, skills={
            "first": _skill(shared),
            "second": _skill(shared + " today"),
        })
        findings = lint.check_duplicate_triggers(root)
        assert [f.rule for f in findings] == ["duplicate-triggers"]
        assert "overlaps" in findings[0].message

    def test_unrelated_skills_are_silent(self, tmp_path):
        root = _corpus(tmp_path, skills={
            "first": _skill("Use when writing database migrations safely"),
            "second": _skill("Use when styling an accessible React component"),
        })
        assert lint.check_duplicate_triggers(root) == []

    def test_the_shipped_corpus_is_clean(self):
        """Batch 2 merged five names away precisely to reach this state; the rule is
        what stops it drifting back. Recorded so a future regression has a date."""
        assert lint.check_duplicate_triggers(REPO) == []


class TestTheCliEntrypoint:
    def _ck(self, cwd, *args):
        env = dict(os.environ, PYTHONPATH=os.path.join(REPO, "src"))
        return subprocess.run([sys.executable, "-m", "claudekit.cli.main", "lint", *args],
                              cwd=cwd, capture_output=True, text=True, env=env)

    def test_exit_zero_and_a_rule_count_on_a_clean_tree(self, tmp_path):
        root = _corpus(tmp_path, commands={"small.md": 10},
                       skills={"fine": _skill("Use when doing one specific thing")})
        proc = self._ck(root)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "3 rules" in proc.stdout

    def test_exit_one_and_the_finding_is_named(self, tmp_path):
        root = _corpus(tmp_path, commands={"big.md": 99})
        proc = self._ck(root)
        assert proc.returncode == 1
        assert "command-budget" in proc.stdout
        assert "big.md" in proc.stdout

    def test_update_baseline_makes_the_same_tree_pass(self, tmp_path):
        root = _corpus(tmp_path, commands={"big.md": 99})
        assert self._ck(root).returncode == 1
        stamp = self._ck(root, "--update-baseline")
        assert stamp.returncode == 0, stamp.stdout + stamp.stderr
        assert json.loads(
            open(lint.baseline_path(root), encoding="utf-8").read()
        )["command_lines"]["big.md"] == 99
        assert self._ck(root).returncode == 0

    def test_only_runs_the_named_rule(self, tmp_path):
        root = _corpus(tmp_path, commands={"big.md": 99})
        proc = self._ck(root, "--rule", "duplicate-triggers")
        assert proc.returncode == 0, proc.stdout
        assert "1 rule" in proc.stdout

    def test_this_repo_passes_its_own_lint(self):
        proc = self._ck(REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr

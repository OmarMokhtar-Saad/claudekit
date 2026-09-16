"""Behavioral tests for the learning loop's TRIGGER layer (learning-loop-v2).

The store layer already worked; nothing fired it. Every test here runs the real hook or
the real script as a subprocess and asserts an outcome on disk or an exit code -- never
the presence of a phrase in a prompt. ECC_HOOK_PROFILE is forced explicitly, so no result
depends on the developer's own session profile.

Contract under test:
  * STOP GATE: a session with mutation activity and an undecided memory candidate blocks
    once (exit 2 + stderr), and the retry with `stop_hook_active` is allowed through --
    the interrupt-once semantics the gate already had, extended to a new duty.
  * DISTILL --INBOX: writes one candidate file per group under
    `.claude/agent-memory/<agent>/_inbox/`, carrying the `index:` line accept will use.
  * INBOX --ACCEPT: moves the candidate out of `_inbox/` and appends exactly that index
    line to the agent's MEMORY.md. --reject deletes it and writes no memory.
  * SESSION MEMORY CONTEXT: over budget it prints whole entries plus the consolidate
    line, and never a partial entry.
  * PROPOSE --PATCH: writes `patch-<skill>-<hash>.md` naming the skill, the section and
    the proposed text, and writes nothing into `.claude/skills/`.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".claude" / "hooks"
GATE = HOOKS / "reflection-gate.py"
LEDGER = REPO / ".claude" / "operations" / "scripts" / "knowledge-ledger.py"
SESSION = "learning-loop-v2-0001"


@pytest.fixture()
def project(tmp_path, reflection_env):
    """An isolated project root with an isolated reflection ledger."""
    root = tmp_path / "project"
    (root / ".claude" / "knowledge" / "issues").mkdir(parents=True)
    return root


@pytest.fixture()
def env(project, tmp_path):
    return dict(
        os.environ,
        CLAUDEKIT_HOOK_LOG=str(tmp_path / "hooks.log"),
        CLAUDE_PROJECT_DIR=str(project),
        CLAUDEKIT_PROJECT_ROOT=str(project),
        CLAUDEKIT_LEDGER_DIR=str(project / ".claude" / "knowledge" / "issues"),
        ECC_HOOK_PROFILE="standard",
    )


def run_gate(event_name, payload, env):
    return subprocess.run(
        [sys.executable, str(GATE), "--event", event_name],
        input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=60,
    )


def run_ledger(env, *args):
    return subprocess.run(
        [sys.executable, str(LEDGER), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


def open_finding(env, slug, signature):
    proc = run_ledger(env, "open", "--slug", slug, "--signature", signature,
                      "--origin", "workflow")
    assert proc.returncode == 0, proc.stderr
    return proc


def write_candidate(project, agent="planner", name="candidate-one",
                    index="- [A thing](candidate-one.md) - a thing worth keeping"):
    inbox = project / ".claude" / "agent-memory" / agent / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / ("%s.md" % name)
    path.write_text("---\nname: %s\ncandidate: memory\n---\nindex: %s\n\nbody\n"
                    % (name, index), encoding="utf-8")
    return path


# ------------------------------------------------------------------ (a) the Stop gate

class TestStopDemandsAnInboxDecision:
    def test_undecided_candidate_blocks_stop_once(self, project, env):
        """The whole point of v2: a candidate nobody decided is a reason to interrupt."""
        run_gate("PostToolUse", {
            "hook_event_name": "PostToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "a", "content": "b"},
        }, env)
        write_candidate(project)
        proc = run_gate("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 2, proc.stdout
        assert "MEMORY INBOX" in proc.stderr
        assert "candidate-one" in proc.stderr
        assert "inbox --accept" in proc.stderr and "inbox --reject" in proc.stderr

    def test_the_block_is_an_interrupt_not_a_trap(self, project, env):
        run_gate("PostToolUse", {
            "hook_event_name": "PostToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "a", "content": "b"},
        }, env)
        write_candidate(project)
        first = run_gate("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert first.returncode == 2
        second = run_gate("Stop", {
            "hook_event_name": "Stop", "session_id": SESSION, "stop_hook_active": True,
        }, env)
        assert second.returncode == 0, second.stderr

    def test_a_subagent_stop_never_carries_the_inbox_duty(self, project, env):
        """Reviewer MAJOR: a subagent may have no Bash and no memory dir, so a candidate
        that belongs to another agent must not interrupt it."""
        run_gate("PostToolUse", {
            "hook_event_name": "PostToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "a", "content": "b"},
        }, env)
        write_candidate(project)
        proc = run_gate("SubagentStop", {
            "hook_event_name": "SubagentStop", "session_id": SESSION,
        }, env)
        assert "MEMORY INBOX" not in proc.stderr, proc.stderr

    def test_a_decided_inbox_is_not_a_duty(self, project, env):
        """No candidate on disk, no duty -- the state is the files, not a flag."""
        proc = run_gate("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 0, proc.stderr
        assert "MEMORY INBOX" not in proc.stderr

    def test_the_learning_loop_duty_names_the_distill_step(self, project, env):
        """The old duty said 'route a learning' and named no command to run."""
        run_gate("PostToolUse", {
            "hook_event_name": "PostToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "a", "content": "b"},
        }, env)
        proc = run_gate("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 2
        assert "distill --agent" in proc.stderr and "--inbox" in proc.stderr


# ------------------------------------------------------ (b) distill writes candidates

class TestDistillInbox:
    def test_distill_inbox_writes_one_candidate_per_group(self, project, env):
        open_finding(env, "gate-never-fires", "the stop gate never demanded a distill")
        proc = run_ledger(env, "distill", "--agent", "planner", "--inbox")
        assert proc.returncode == 0, proc.stderr
        inbox = project / ".claude" / "agent-memory" / "planner" / "_inbox"
        files = sorted(inbox.glob("*.md"))
        assert len(files) == 1, proc.stdout
        text = files[0].read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "index: - [" in text
        assert "the stop gate never demanded a distill" in text

    def test_distill_without_inbox_still_writes_only_a_draft(self, project, env):
        """The default path is unchanged: no flag, no candidate, no new Stop duty."""
        open_finding(env, "some-finding", "a signature that is not yet fixed")
        proc = run_ledger(env, "distill", "--agent", "planner")
        assert proc.returncode == 0, proc.stderr
        assert not (project / ".claude" / "agent-memory" / "planner" / "_inbox").exists()
        assert (project / ".claude" / "agent-memory" / "planner" / "MEMORY.md.draft").is_file()


# -------------------------------------------------- (d) accept produces an index line

class TestInboxAcceptReject:
    def test_accept_moves_the_file_and_appends_its_index_line(self, project, env):
        write_candidate(project)
        proc = run_ledger(env, "inbox", "--accept", "candidate-one")
        assert proc.returncode == 0, proc.stderr
        agent_dir = project / ".claude" / "agent-memory" / "planner"
        assert (agent_dir / "candidate-one.md").is_file()
        assert not (agent_dir / "_inbox" / "candidate-one.md").exists()
        index = (agent_dir / "MEMORY.md").read_text(encoding="utf-8")
        assert "- [A thing](candidate-one.md) - a thing worth keeping" in index

    def test_accept_appends_rather_than_replacing(self, project, env):
        agent_dir = project / ".claude" / "agent-memory" / "planner"
        agent_dir.mkdir(parents=True)
        (agent_dir / "MEMORY.md").write_text("# planner memory\n\n- [Old](old.md) - kept\n",
                                             encoding="utf-8")
        write_candidate(project)
        assert run_ledger(env, "inbox", "--accept", "candidate-one").returncode == 0
        index = (agent_dir / "MEMORY.md").read_text(encoding="utf-8")
        assert "- [Old](old.md) - kept" in index
        assert "- [A thing](candidate-one.md)" in index

    def test_reject_deletes_and_writes_no_memory(self, project, env):
        write_candidate(project)
        proc = run_ledger(env, "inbox", "--reject", "candidate-one")
        assert proc.returncode == 0, proc.stderr
        agent_dir = project / ".claude" / "agent-memory" / "planner"
        assert not (agent_dir / "_inbox" / "candidate-one.md").exists()
        assert not (agent_dir / "candidate-one.md").exists()
        assert not (agent_dir / "MEMORY.md").exists()

    def test_a_candidate_with_no_index_line_is_refused(self, project, env):
        """A memory file no MEMORY.md points at is invisible: refuse, never guess a line."""
        inbox = project / ".claude" / "agent-memory" / "planner" / "_inbox"
        inbox.mkdir(parents=True)
        (inbox / "bare.md").write_text("---\nname: bare\n---\nbody\n", encoding="utf-8")
        proc = run_ledger(env, "inbox", "--accept", "bare")
        assert proc.returncode == 4, proc.stdout
        assert (inbox / "bare.md").is_file()

    def test_inbox_list_reports_candidates_and_proposals(self, project, env):
        write_candidate(project)
        proposals = project / ".claude" / "knowledge" / "proposals"
        proposals.mkdir(parents=True)
        (proposals / "some-cluster-abcd1234.md").write_text("x\n", encoding="utf-8")
        proc = run_ledger(env, "inbox")
        assert proc.returncode == 0, proc.stderr
        assert "candidate-one" in proc.stdout
        assert "some-cluster-abcd1234" in proc.stdout


# ------------------------------------------- (c) over-budget injection never truncates

class TestOverBudgetInjection:
    def _render(self):
        spec = importlib.util.spec_from_file_location(
            "ck_session_memory_ll2", HOOKS / "session-memory-context.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_over_budget_names_consolidate_and_keeps_whole_lines(self):
        module = self._render()
        findings = [("2026-01-0%d" % (i % 9 + 1), "slug-%03d" % i, "S" * 140)
                    for i in range(60)]
        text = module.render(findings, [])
        assert "MEMORY OVER BUDGET" in text
        assert "consolidate --agent" in text
        assert "truncated at the 600-token cap" not in text
        for line in text.splitlines():
            if line.strip().startswith("- slug-"):
                assert line.endswith("S" * 140), "an entry was cut mid-line"

    def test_under_budget_is_unchanged(self):
        module = self._render()
        text = module.render([("2026-01-01", "slug-a", "a short signature")], [])
        assert "MEMORY OVER BUDGET" not in text
        assert "slug-a" in text


# -------------------------------------------------------- (e) patch proposal file shape

class TestPatchProposals:
    def _skill(self, project):
        skill = project / ".claude" / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\n---\n\n# Example\n\n## Pitfalls\n\n- one\n",
            encoding="utf-8")
        return skill

    def test_patch_proposal_names_skill_section_and_text(self, project, env):
        self._skill(project)
        proc = run_ledger(env, "propose", "--patch", "example-skill",
                          "--section", "Pitfalls", "--text", "check the thing first")
        assert proc.returncode == 0, proc.stderr
        files = sorted((project / ".claude" / "knowledge" / "proposals")
                       .glob("patch-example-skill-*.md"))
        assert len(files) == 1, proc.stdout
        body = files[0].read_text(encoding="utf-8")
        assert ".claude/skills/example-skill/SKILL.md" in body
        assert "## Pitfalls" in body
        assert "check the thing first" in body
        assert "/learn --promote" in body

    def test_the_proposer_never_touches_the_skill(self, project, env):
        skill = self._skill(project)
        before = (skill / "SKILL.md").read_text(encoding="utf-8")
        run_ledger(env, "propose", "--patch", "example-skill",
                   "--section", "Verification", "--text", "run the suite")
        assert (skill / "SKILL.md").read_text(encoding="utf-8") == before

    def test_an_unknown_section_is_refused(self, project, env):
        self._skill(project)
        proc = run_ledger(env, "propose", "--patch", "example-skill",
                          "--section", "Anything", "--text", "nope")
        assert proc.returncode == 2
        assert not (project / ".claude" / "knowledge" / "proposals").exists()

    def test_a_missing_skill_is_refused(self, project, env):
        proc = run_ledger(env, "propose", "--patch", "no-such-skill",
                          "--section", "Pitfalls", "--text", "nope")
        assert proc.returncode == 3


# ------------------------------------------------------------------- consolidate

class TestConsolidate:
    def test_consolidate_reports_merge_groups_and_rewrites_nothing(self, project, env):
        agent_dir = project / ".claude" / "agent-memory" / "planner"
        agent_dir.mkdir(parents=True)
        memory = agent_dir / "MEMORY.md"
        original = ("# planner memory\n\n"
                    "- [Hook order](a.md) - the installer writes before preservation runs\n"
                    "- [Hook order two](b.md) - the installer writes another file first\n"
                    "- [Unrelated](c.md) - zsh never splits words\n")
        memory.write_text(original, encoding="utf-8")
        proc = run_ledger(env, "consolidate", "--agent", "planner")
        assert proc.returncode == 0, proc.stderr
        assert "group 1" in proc.stdout
        assert "a.md" in proc.stdout and "b.md" in proc.stdout
        assert memory.read_text(encoding="utf-8") == original

    def test_missing_memory_is_reported_not_created(self, project, env):
        proc = run_ledger(env, "consolidate", "--agent", "planner")
        assert proc.returncode == 3
        assert not (project / ".claude" / "agent-memory" / "planner" / "MEMORY.md").exists()

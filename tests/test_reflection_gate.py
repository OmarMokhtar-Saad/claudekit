"""Behavioral tests for .claude/hooks/reflection-gate.py.

Every test runs the real hook as a subprocess with a real JSON payload on stdin and
asserts the exit code and stderr - the only contract Claude Code honours (exit 2 +
stderr blocks; exit 1 / stdout does not). ECC_HOOK_PROFILE is forced explicitly so the
result never depends on the developer's own session profile.
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
SESSION = "gate-session-0001"


@pytest.fixture()
def env(tmp_path, reflection_env):
    """Isolated ledger, isolated hook log, isolated project root, blocking ON.

    The ledger and inbox come from `reflection_env`, which also puts them in
    `os.environ` for the in-process `ref` module and restores the caller's values on
    teardown."""
    project = tmp_path / "project"
    project.mkdir()
    return dict(
        os.environ,
        CLAUDEKIT_HOOK_LOG=str(tmp_path / "hooks.log"),
        CLAUDE_PROJECT_DIR=str(project),
        ECC_HOOK_PROFILE="standard",
    )


@pytest.fixture()
def ref(env):
    spec = importlib.util.spec_from_file_location("ck_reflection_gate_lib",
                                                  HOOKS / "reflection.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(event_name, payload, env, raw=None):
    body = raw if raw is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(GATE), "--event", event_name],
        input=body, capture_output=True, text=True, env=env, timeout=60,
    )


def failure_payload(command="pytest -q tests/test_thing.py", tool_use_id=None):
    return {
        "hook_event_name": "PostToolUseFailure",
        "session_id": SESSION,
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": tool_use_id,
    }


def seed_two_failures(env):
    run("PostToolUseFailure", failure_payload("pytest -q tests/a.py", "t1"), env)
    run("PostToolUseFailure", failure_payload("pytest -q tests/b.py", "t2"), env)


# ------------------------------------------------------------ G4: failure state


class TestFailureRecording:
    def test_failure_is_persisted(self, env, ref):
        proc = run("PostToolUseFailure", failure_payload(), env)
        assert proc.returncode == 0, proc.stderr
        kinds = [e.get("kind") for e in ref.entries(SESSION)]
        assert "task-failure" in kinds

    def test_second_failure_announces_the_checkpoint_on_stdout(self, env, ref):
        seed_two_failures(env)
        proc = run("PostToolUseFailure", failure_payload("pytest -q tests/c.py", "t3"), env)
        assert proc.returncode == 0
        assert "REFLECTION CHECKPOINT PENDING" in proc.stdout

    def test_hook_path_does_not_leak_absolute_paths_or_secrets(self, env, ref):
        run("PostToolUseFailure",
            failure_payload("psql 'password=hunter2' -f /Users/someone/prod/dump.sql"),
            env)
        blob = ref.ledger_path(SESSION).read_text(encoding="utf-8")
        assert "hunter2" not in blob
        assert "/Users/someone" not in blob
        assert "dump.sql" not in blob

    def test_missing_session_id_is_survivable(self, env):
        proc = run("PostToolUseFailure", {"hook_event_name": "PostToolUseFailure"}, env)
        assert proc.returncode == 0


# ------------------------------------------------------ PreToolUse availability


class TestPreToolUseGate:
    def test_mutation_is_blocked_while_a_checkpoint_is_pending(self, env):
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "src/x.py", "content": "x"},
        }, env)
        assert proc.returncode == 2, proc.stdout
        assert "REFLECTION CHECKPOINT PENDING" in proc.stderr
        assert proc.stdout.strip() == ""

    def test_ops_executor_counts_as_mutation(self, env):
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash",
            "tool_input": {
                "command": "python3 .claude/operations/scripts/execute-json-ops.py p.json"
            },
        }, env)
        assert proc.returncode == 2

    def test_read_only_diagnosis_stays_available(self, env):
        seed_two_failures(env)
        for tool, tool_input in (
            ("Read", {"file_path": "src/x.py"}),
            ("Grep", {"pattern": "def foo"}),
            ("Bash", {"command": "git status"}),
            ("Bash", {"command": "grep -rn foo src/"}),
        ):
            proc = run("PreToolUse", {
                "hook_event_name": "PreToolUse", "session_id": SESSION,
                "tool_name": tool, "tool_input": tool_input,
            }, env)
            assert proc.returncode == 0, (tool, proc.stderr)

    def test_plan_writing_stays_available(self, env):
        """Planning must never be blocked - it is the way out of the checkpoint."""
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash",
            "tool_input": {
                "command": "python3 .claude/operations/scripts/validate-config-json.py p.json"
            },
        }, env)
        assert proc.returncode == 0, proc.stderr

    def test_receipt_cli_is_never_blocked(self, env):
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash",
            "tool_input": {"command": "python3 %s receipt --session-id %s "
                                      "--session-token t --json {}" % (
                                          HOOKS / "reflection.py", SESSION)},
        }, env)
        assert proc.returncode == 0, proc.stderr

    def test_receipt_cli_escape_hatch_cannot_be_forged_by_a_compound_command(self, env):
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash",
            "tool_input": {"command": "python3 %s status --session-id %s ; rm -rf build" % (
                HOOKS / "reflection.py", SESSION)},
        }, env)
        assert proc.returncode == 2, proc.stdout

    def test_unchanged_rerun_is_blocked(self, env):
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash",
            "tool_input": {"command": "pytest -q tests/a.py"},
        }, env)
        assert proc.returncode == 2
        assert "unchanged" in proc.stderr

    def test_a_different_test_command_is_not_blocked(self, env):
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash",
            "tool_input": {"command": "pytest -q tests/never_run_before.py"},
        }, env)
        assert proc.returncode == 0, proc.stderr

    def test_nothing_is_blocked_without_a_checkpoint(self, env):
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "a", "content": "b"},
        }, env)
        assert proc.returncode == 0, proc.stderr

    def test_receipt_inbox_write_is_allowed_while_a_checkpoint_is_pending(self, env, ref):
        """MAJOR-3 decoupling: the receipt payload travels via Write, not via a shell
        command line that command-guard.sh would also scan."""
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Write",
            "tool_input": {"file_path": str(ref.inbox_path(SESSION)),
                           "content": "{\"schemaVersion\": 1}"},
        }, env)
        assert proc.returncode == 0, proc.stderr

    def test_the_inbox_allowance_is_one_exact_path_not_a_directory(self, env, ref):
        """BOUND TEST: a sibling file in the same directory must still be blocked, so the
        allowance cannot be widened into a general write escape."""
        seed_two_failures(env)
        sibling = ref.inbox_path(SESSION).parent / "not-the-inbox.json"
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Write",
            "tool_input": {"file_path": str(sibling), "content": "{}"},
        }, env)
        assert proc.returncode == 2, proc.stdout

    def test_a_symlinked_inbox_cannot_launder_a_source_write(self, env, ref, tmp_path):
        """BOUND TEST for the Iron Law (hard rule 1).

        An earlier revision realpath'd BOTH sides, so a symlinked inbox laundered the
        allowance into an arbitrary source write that also cleared ops-enforcement.sh
        (which only sees a `.claude/` path). Neutralise the islink refusal and this test
        fails.
        """
        victim = tmp_path / "victim_source.py"
        victim.write_text("ORIGINAL\n")
        inbox = ref.inbox_path(SESSION)
        inbox.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(victim), str(inbox))
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Write",
            "tool_input": {"file_path": str(inbox), "content": "PWNED"},
        }, env)
        assert proc.returncode == 2, proc.stdout
        assert victim.read_text() == "ORIGINAL\n"

    def test_a_path_whose_parent_is_symlinked_to_the_inbox_dir_is_blocked(
        self, env, ref, tmp_path
    ):
        """The parent-realpath comparison must not be defeated by linking the directory
        to somewhere else - only the real inbox directory + exact basename passes."""
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Write",
            "tool_input": {"file_path": str(elsewhere / ref.inbox_path(SESSION).name),
                           "content": "{}"},
        }, env)
        assert proc.returncode == 2, proc.stdout

    def test_creating_the_symlink_is_itself_blocked(self, env, ref):
        """Defence in depth: `ln` is a mutation, so the first step of the bypass never
        runs while a checkpoint is pending."""
        seed_two_failures(env)
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash",
            "tool_input": {"command": "ln -s ../../src/claudekit/x.py %s" % (
                ref.inbox_path(SESSION))},
        }, env)
        assert proc.returncode == 2, proc.stdout

    def test_the_inbox_allowance_admits_write_only(self, env, ref):
        """Scope is `Write`, not the whole MUTATING_TOOLS set: Edit/MultiEdit/
        apply_patch operate on existing content and cannot legitimately create a
        receipt."""
        seed_two_failures(env)
        for tool in ("Edit", "MultiEdit", "NotebookEdit", "apply_patch", "write_file",
                     "str_replace_based_edit_tool"):
            proc = run("PreToolUse", {
                "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": tool,
                "tool_input": {"file_path": str(ref.inbox_path(SESSION)), "content": "{}"},
            }, env)
            assert proc.returncode == 2, (tool, proc.stdout)

    def test_the_gate_creates_no_directories_even_when_it_denies(self, env, ref):
        """A blocking gate must be free of filesystem side effects."""
        inbox_dir = ref.inbox_path(SESSION).parent
        assert not inbox_dir.exists()
        seed_two_failures(env)
        run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Write",
            "tool_input": {"file_path": "src/x.py", "content": "x"},
        }, env)
        assert not inbox_dir.exists(), "the gate created the inbox directory as a side effect"

    def test_another_sessions_inbox_is_blocked(self, env, ref):
        seed_two_failures(env)
        other = str(ref.inbox_path("some-other-session"))
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Write",
            "tool_input": {"file_path": other, "content": "{}"},
        }, env)
        assert proc.returncode == 2, proc.stdout

    def test_minimal_profile_suppresses_blocking(self, env):
        seed_two_failures(env)
        minimal = dict(env, ECC_HOOK_PROFILE="minimal")
        proc = run("PreToolUse", {
            "hook_event_name": "PreToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "a", "content": "b"},
        }, minimal)
        assert proc.returncode == 0, proc.stderr

    def test_minimal_profile_still_records(self, env, ref):
        """Deliberate divergence from the wholesale `minimal` short-circuit: recording
        must survive a profile flip, or the ledger develops holes that mis-reduce."""
        minimal = dict(env, ECC_HOOK_PROFILE="minimal")
        run("PostToolUseFailure", failure_payload("pytest -q tests/z.py", "z1"), minimal)
        kinds = [e.get("kind") for e in ref.entries(SESSION)]
        assert "task-failure" in kinds

    def test_unparsable_pretooluse_payload_fails_closed(self, env):
        proc = run("PreToolUse", None, env, raw="{not json at all")
        assert proc.returncode == 2
        assert "BLOCKED" in proc.stderr

    def test_unparsable_stop_payload_fails_open(self, env):
        """A stop we cannot justify blocking must not strand the turn."""
        proc = run("Stop", None, env, raw="{not json at all")
        assert proc.returncode == 0


# ------------------------------------------------------------- G3: Stop duties


class TestStopGate:
    def test_clean_session_stops_freely(self, env):
        proc = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 0, proc.stderr

    def test_unmet_reflection_duty_blocks_the_stop(self, env):
        seed_two_failures(env)
        proc = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 2
        assert "STOP BLOCKED" in proc.stderr

    def test_interrupt_once_stop_hook_active_is_honoured(self, env):
        seed_two_failures(env)
        first = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert first.returncode == 2
        second = run("Stop", {
            "hook_event_name": "Stop", "session_id": SESSION, "stop_hook_active": True,
        }, env)
        assert second.returncode == 0, second.stderr

    def test_learning_loop_duty_blocks_after_a_mutation(self, env):
        run("PostToolUse", {
            "hook_event_name": "PostToolUse", "session_id": SESSION,
            "tool_name": "Write", "tool_input": {"file_path": "a", "content": "b"},
        }, env)
        proc = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 2
        assert "LEARNING LOOP" in proc.stderr

    def test_inbox_write_does_not_arm_the_learning_loop_duty(self, env, ref):
        """Writing a receipt is not 'mutation or delivery'; it must not create the very
        duty it exists to discharge."""
        run("PostToolUse", {
            "hook_event_name": "PostToolUse", "session_id": SESSION, "tool_name": "Write",
            "tool_input": {"file_path": str(ref.inbox_path(SESSION)), "content": "{}"},
        }, env)
        assert ref.learning_loop_pending(SESSION) is False

    def test_a_receipt_clears_the_stop(self, env, ref):
        seed_two_failures(env)
        token = ref.read_session_token(SESSION)
        cp = ref.pending_checkpoint(SESSION)
        ref.record_receipt(SESSION, {
            "schemaVersion": ref.SCHEMA_VERSION, "taskId": "t",
            "trigger": cp["trigger"], "failureFingerprints": cp["failureFingerprints"],
            "failedAssumption": "assumed the fixture seeded the ledger",
            "approachesCompared": ["seed in fixture", "seed at call site"],
            "chosenExperiment": "seed in the fixture", "proofCommandOrCheck": "pytest -q",
            "proofOutcome": "the failing assertion now passes",
            "durableDisposition": "nothing-durable",
        }, token)
        proc = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 0, proc.stderr

    def test_minimal_profile_suppresses_the_stop_block(self, env):
        seed_two_failures(env)
        minimal = dict(env, ECC_HOOK_PROFILE="minimal")
        proc = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, minimal)
        assert proc.returncode == 0

    def test_subagent_stop_carries_the_same_duties(self, env):
        seed_two_failures(env)
        proc = run("SubagentStop",
                   {"hook_event_name": "SubagentStop", "session_id": SESSION}, env)
        assert proc.returncode == 2
        assert "SUBAGENT STOP BLOCKED" in proc.stderr

    def test_uncommitted_work_warns_but_never_blocks(self, env, tmp_path):
        project = Path(env["CLAUDE_PROJECT_DIR"])
        subprocess.run(["git", "init", "-q"], cwd=project, timeout=30)
        (project / "dirty.txt").write_text("uncommitted\n")
        proc = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 0
        assert "Uncommitted changes" in proc.stderr


# ------------------------------------------------- G7: duties survive compaction


class TestPreCompact:
    def test_precompact_never_blocks(self, env):
        seed_two_failures(env)
        proc = run("PreCompact", {
            "hook_event_name": "PreCompact", "session_id": SESSION, "trigger": "auto",
        }, env)
        assert proc.returncode == 0, proc.stderr

    def test_duties_are_persisted_for_the_post_compaction_context(self, env, ref):
        seed_two_failures(env)
        run("PreCompact", {
            "hook_event_name": "PreCompact", "session_id": SESSION, "trigger": "auto",
        }, env)
        assert ref.carryover_path(SESSION).is_file()

    def test_session_start_replays_the_carry_over_then_consumes_it(self, env, ref):
        seed_two_failures(env)
        run("PreCompact", {
            "hook_event_name": "PreCompact", "session_id": SESSION, "trigger": "auto",
        }, env)
        first = run("SessionStart", {
            "hook_event_name": "SessionStart", "session_id": SESSION, "source": "compact",
        }, env)
        assert first.returncode == 0
        assert "survived compaction" in first.stdout
        assert not ref.carryover_path(SESSION).is_file()

    def test_session_start_emits_the_session_token(self, env):
        proc = run("SessionStart", {
            "hook_event_name": "SessionStart", "session_id": SESSION, "source": "startup",
        }, env)
        assert proc.returncode == 0
        assert "Reflection session token" in proc.stdout

    def test_pending_duty_is_still_pending_after_compaction(self, env, ref):
        seed_two_failures(env)
        run("PreCompact", {
            "hook_event_name": "PreCompact", "session_id": SESSION, "trigger": "auto",
        }, env)
        assert ref.pending_checkpoint(SESSION) is not None
        proc = run("Stop", {"hook_event_name": "Stop", "session_id": SESSION}, env)
        assert proc.returncode == 2

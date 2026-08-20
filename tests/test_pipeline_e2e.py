"""LANE A of task 015: end-to-end PIPELINE COMPOSITION, deterministic and offline.

What this module is for, and what it deliberately is not. Every stage of the pipeline
already has a unit suite that is stronger than anything written here: the approval-gate
matrix lives in `test_ops_approval_gate.py`, the Iron Law command allowlist in
`test_iron_law_hook.py` (174 cases), rollback and forward recovery in
`test_ops_hardening.py` / `test_work_loss_protection.py`, the reflection checkpoint in
`test_reflection_gate.py`. Re-asserting any of that here would inflate the count and slow
CI without adding signal.

What no unit test can see is the SEAM:

  * the artifact of stage N being consumed as the input of stage N+1 (extract -> validate
    -> record -> execute -> the project's own suite), rather than each script being fed a
    hand-built input;
  * the hooks running as `settings.json` actually WIRES them - through the `bash -c`
    wrapper with its `ROOT=` resolution - instead of being invoked by file path, which is
    what every existing hook test does. A hook unwired from settings.json passes every
    existing test and protects nothing;
  * two independently-correct gates composing on one tool call: `iron-law-gate.py` permits
    the implementer's ops command, and the reflection checkpoint must still be able to
    stop it. Each gate is proven alone; their PRECEDENCE is proven only here.

Hermeticity rules (all load-bearing):
  * `ECC_HOOK_PROFILE` is passed explicitly to every subprocess. The maintainer default is
    `minimal`, under which `ops-enforcement.sh` returns at line 13 of its body and this
    whole module would go vacuously green.
  * The fixture project is created BESIDE the repo, never under `$TMPDIR`: on macOS
    `tempfile` returns `/var/folders/...`, which `ops-enforcement.sh` exempts outright as
    OS scratch (same reasoning as `test_ops_enforcement_scope.py`).
  * The reflection ledger and hook log are redirected per test; the real tree is never
    written to, and no test creates `<repo>/.claude/**`.
"""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from conftest import scoped_env

REPO = Path(__file__).resolve().parents[1]
CLAUDE = REPO / ".claude"
SCRIPTS = CLAUDE / "operations" / "scripts"
SETTINGS = CLAUDE / "settings.json"

EXTRACTOR = SCRIPTS / "extract-json-from-plan.py"
VALIDATOR = SCRIPTS / "validate-config-json.py"
RECORDER = SCRIPTS / "review-record.py"
EXECUTOR = SCRIPTS / "execute-json-ops.py"

ORIGINAL = "VALUE = 1\n"
PATCHED = "VALUE = 99\n"
REVISED = "VALUE = 123\n"


# --------------------------------------------------------------------------- fixtures

def _ops_payload(plan="fixture", replace="VALUE = 99"):
    return {
        "plan": plan,
        "operations": [{
            "type": "code_edit",
            "path": "src/app.py",
            "edits": [{"find": "VALUE = 1", "replace": replace}],
        }],
    }


def _plan_doc(payload):
    return (
        "# Implementation Plan: Fixture\n\n## Overview\nBump the constant.\n\n"
        "```json\n" + json.dumps(payload, indent=2) + "\n```\n"
    )


@pytest.fixture()
def project(tmp_path):
    """A throwaway ClaudeKit-shaped project carrying the LIVE tree's hooks, ops scripts
    and settings.json - copied at test time, so a fixture can never go stale against the
    thing it is meant to guard.

    DO NOT "TIDY" THIS INTO `tmp_path`. The project is created BESIDE the repo, not under
    $TMPDIR, and that is load-bearing: `ops-enforcement.sh` exits 0 outright for
    `/private/var/folders/*` and `/var/folders/*` (its OS-scratch exemption), which is
    exactly what macOS `tempfile` returns. Moving this to `tmp_path` looks like cleanup,
    passes CI, and silently voids every hook assertion in this module.
    """
    root = Path(tempfile.mkdtemp(prefix=".ck-e2e-", dir=str(REPO.parent)))
    try:
        shutil.copytree(CLAUDE / "hooks", root / ".claude" / "hooks",
                        ignore=shutil.ignore_patterns("*.log", "*.txt", "__pycache__"))
        shutil.copytree(SCRIPTS, root / ".claude" / "operations" / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(SETTINGS, root / ".claude" / "settings.json")
        (root / ".claude" / "plans").mkdir()
        (root / ".claude" / "reports" / "reviews").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text(ORIGINAL, encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "test_app.py").write_text(
            "import sys, pathlib\n"
            "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))\n"
            "import app\n\n"
            "def test_value_is_the_post_state():\n"
            "    assert app.VALUE == 99\n",
            encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True, timeout=60)
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def env_for(project, profile, tmp_path, **extra):
    """Explicit environment for every subprocess. Nothing about the result may depend on
    the maintainer's own session profile or real reflection ledger."""
    env = dict(os.environ)
    env.update({
        "CLAUDE_PROJECT_DIR": str(project),
        "CLAUDEKIT_HOOK_LOG": str(tmp_path / "hooks.log"),
        "CLAUDEKIT_REFLECTION_DIR": str(tmp_path / "ledger"),
        "CLAUDEKIT_REFLECTION_INBOX": str(tmp_path / "inbox"),
    })
    env.pop("ECC_OPS_GATE_ALL", None)
    env.pop("ECC_OPS_SOURCE_GLOBS", None)
    if profile is None:
        env.pop("ECC_HOOK_PROFILE", None)
    else:
        env["ECC_HOOK_PROFILE"] = profile
    env.update(extra)
    return env


def run_script(script, args, project, env):
    return subprocess.run([sys.executable, str(script), *args], cwd=str(project),
                          capture_output=True, text=True, timeout=120, env=env)


def result_json(stdout):
    lines = [ln for ln in stdout.splitlines() if ln.startswith("RESULT-JSON:")]
    assert lines, f"no RESULT-JSON line in:\n{stdout}"
    return json.loads(lines[-1][len("RESULT-JSON:"):])


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_reflection():
    """The shipped reflection library, loaded by path (it is a hook, not a package)."""
    spec = importlib.util.spec_from_file_location("ck_e2e_reflection",
                                                  CLAUDE / "hooks" / "reflection.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------- the wired hook chain, as wired

def wired_commands(matcher_tool):
    """The PreToolUse hook command strings settings.json actually wires for a tool.

    Parsed from settings.json rather than hardcoded, so a hook silently unwired from
    settings turns the chain tests red - the failure mode where the hook file is present,
    fully unit-tested, and never invoked.
    """
    config = json.loads(SETTINGS.read_text(encoding="utf-8"))
    out = []
    for entry in config["hooks"]["PreToolUse"]:
        matcher = entry.get("matcher") or ""
        if matcher and matcher_tool not in matcher.split("|"):
            continue
        for hook in entry.get("hooks", []):
            command = hook.get("command", "")
            if command:
                out.append((_hook_name(command), command))
    return out


def _hook_name(command):
    for token in command.replace('"', " ").replace("'", " ").split():
        base = token.rsplit("/", 1)[-1]
        if base.endswith((".sh", ".py")) and "hooks" in token:
            return base
    return command[:40]


def run_chain(project, tool_name, tool_input, profile, tmp_path, **payload_extra):
    """Run every wired PreToolUse hook for `tool_name` exactly as settings.json invokes
    it, and return {hook_name: CompletedProcess}. Claude Code's semantics: any exit 2
    blocks the call."""
    payload = {"hook_event_name": "PreToolUse", "session_id": "e2e-session-0001",
               "cwd": str(project), "permission_mode": "default",
               "tool_name": tool_name, "tool_input": tool_input}
    payload.update(payload_extra)
    body = json.dumps(payload)
    env = env_for(project, profile, tmp_path)
    results = {}
    for name, command in wired_commands(tool_name):
        results[name] = subprocess.run(["bash", "-c", command], input=body, cwd=str(project),
                                       capture_output=True, text=True, timeout=120, env=env)
    return results


def blockers(results):
    return sorted(name for name, proc in results.items() if proc.returncode == 2)


# ------------------------------------------------------------------- Group A: the spine

def test_plan_artifacts_flow_through_extract_validate_record_execute(project, tmp_path):
    """E2E-01+02+03 composed: the ONLY test in the suite where each stage's real output
    is the next stage's real input. Unit tests feed every one of these scripts a
    hand-built input, so a seam that changes shape (extractor output the validator
    rejects, a record the executor cannot resolve from the plan path) is invisible to
    them."""
    env = env_for(project, "minimal", tmp_path)
    plan = project / ".claude" / "plans" / "plan-fixture.md"
    plan.write_text(_plan_doc(_ops_payload()), encoding="utf-8")
    ops = project / ".claude" / "plans" / "plan-fixture.ops.json"

    extract = run_script(EXTRACTOR, [str(plan), "--output", str(ops)], project, env)
    assert extract.returncode == 0, extract.stderr
    assert ops.exists(), "extractor reported success but wrote no ops file"

    validate = run_script(VALIDATOR, [str(ops)], project, env)
    assert validate.returncode == 0, validate.stdout + validate.stderr

    write = run_script(RECORDER, ["write", str(plan), str(ops), "--score", "95",
                                  "--decision", "APPROVED"], project, env)
    assert write.returncode == 0, write.stderr
    reviews = project / ".claude" / "reports" / "reviews"
    record, snapshot = reviews / "fixture.json", reviews / "fixture.ops.json"
    assert record.exists() and snapshot.exists(), sorted(reviews.iterdir())
    # The verdict is bound to CONTENT, not to a name: recompute the digest here rather
    # than trusting the recorder's own report of it.
    assert sha256_of(ops) in record.read_text(encoding="utf-8")

    check = run_script(RECORDER, ["check", str(plan), str(ops)], project, env)
    assert check.returncode == 0, check.stdout + check.stderr

    execute = run_script(EXECUTOR, [str(ops)], project, env)
    assert execute.returncode == 0, execute.stdout + execute.stderr
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == PATCHED
    verdict = result_json(execute.stdout)
    assert verdict["status"] == "success", verdict
    assert verdict["backup_dir"], "a successful run must leave a restorable backup"

    # The seam that matters to a human: the project's own suite now passes.
    suite = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/"],
                           cwd=str(project), capture_output=True, text=True,
                           timeout=300, env=env)
    assert suite.returncode == 0, suite.stdout + suite.stderr


def test_conditional_revise_reapprove_roundtrip(project, tmp_path):
    """E2E-41: the daily workflow, end to end, with the two failure directions that
    matter. A CONDITIONAL verdict must not authorise execution; revising the ops file to
    address the finding must not be smugglable through the stale verdict (it drifts);
    and re-approval must re-bind to the REVISED digest and then execute.

    Both directions are asserted because a gate can fail either way: approval laundering
    (get CONDITIONAL, edit freely, execute) or a dead end (no forward path, so the gate
    gets disabled in practice)."""
    env = env_for(project, "minimal", tmp_path)
    plan = project / ".claude" / "plans" / "plan-fixture.md"
    plan.write_text(_plan_doc(_ops_payload()), encoding="utf-8")
    ops = project / ".claude" / "plans" / "plan-fixture.ops.json"
    ops.write_text(json.dumps(_ops_payload(), indent=2) + "\n", encoding="utf-8")

    run_script(RECORDER, ["write", str(plan), str(ops), "--score", "88",
                          "--decision", "CONDITIONAL"], project, env)
    refused = run_script(EXECUTOR, [str(ops)], project, env)
    assert refused.returncode != 0
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == ORIGINAL
    verdict_reason = result_json(refused.stdout)["reason"]
    assert verdict_reason.startswith("approval-gate:"), verdict_reason

    # Revise to address the finding: the digest changes, so the stale CONDITIONAL record
    # now ALSO drifts. The refusal reason must change with it - an operator who cannot
    # tell "wrong verdict" from "stale artifact" cannot act.
    ops.write_text(json.dumps(_ops_payload(replace="VALUE = 123"), indent=2) + "\n",
                   encoding="utf-8")
    still_refused = run_script(EXECUTOR, [str(ops)], project, env)
    assert still_refused.returncode != 0
    drift_reason = result_json(still_refused.stdout)["reason"]
    assert drift_reason != verdict_reason, (
        "verdict-refusal and drift-refusal are indistinguishable: %r" % drift_reason)
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == ORIGINAL

    reapprove = run_script(RECORDER, ["write", str(plan), str(ops), "--score", "92",
                                      "--decision", "APPROVED"], project, env)
    assert reapprove.returncode == 0, reapprove.stderr
    record = project / ".claude" / "reports" / "reviews" / "fixture.json"
    assert sha256_of(ops) in record.read_text(encoding="utf-8"), \
        "re-approval did not re-bind to the revised digest"

    executed = run_script(EXECUTOR, [str(ops)], project, env)
    assert executed.returncode == 0, executed.stdout + executed.stderr
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == REVISED


# ------------------------------------------------------- Group C/D: the chain AS WIRED

def test_wired_edit_chain_blocks_a_source_edit_under_standard(project, tmp_path):
    """E2E-13/17 as composition: the hooks are run through settings.json's own `bash -c`
    wrapper (ROOT resolution included), not by file path. Attribution is asserted per
    hook, so "blocked" can never be satisfied by some unrelated hook in the chain."""
    results = run_chain(project, "Edit", {"file_path": str(project / "src" / "app.py")},
                        "standard", tmp_path)
    assert "ops-enforcement.sh" in results, \
        "ops-enforcement.sh is not wired for Edit in settings.json - it never fires"
    gate = results["ops-enforcement.sh"]
    assert gate.returncode == 2, gate.stdout + gate.stderr
    assert gate.stderr.strip(), "a block with no stderr gives the agent nothing to act on"
    assert "OPS ENFORCEMENT" in gate.stderr
    assert gate.stdout == "", "a PreToolUse decision must never travel on stdout"
    assert blockers(results) == ["ops-enforcement.sh"], blockers(results)


def test_wired_edit_chain_is_inert_under_minimal(project, tmp_path):
    """E2E-14: `minimal` (this repo's maintainer default) must be genuinely inert -
    partial bypass would make maintainer sessions behave unlike anything documented."""
    results = run_chain(project, "Edit", {"file_path": str(project / "src" / "app.py")},
                        "minimal", tmp_path)
    noisy = {name: (p.returncode, p.stderr) for name, p in results.items()
             if p.returncode != 0}
    assert not noisy, noisy
    # ...and the sanctioned path still works under the same profile.
    (project / "src" / "app.py").write_text(ORIGINAL, encoding="utf-8")
    ops = project / "ops.json"
    ops.write_text(json.dumps(_ops_payload(plan="inert-check")), encoding="utf-8")
    execute = run_script(EXECUTOR, [str(ops)], project,
                         env_for(project, "minimal", tmp_path))
    assert execute.returncode == 0, execute.stdout + execute.stderr


def test_wired_edit_chain_defaults_to_enforcing_when_profile_is_unset(project, tmp_path):
    """E2E-15: an unset profile must NOT silently disable enforcement for anyone who did
    not read the setup gotcha. `${ECC_HOOK_PROFILE:-standard}` is the whole guard."""
    results = run_chain(project, "Edit", {"file_path": str(project / "src" / "app.py")},
                        None, tmp_path)
    assert results["ops-enforcement.sh"].returncode == 2, \
        "an unset ECC_HOOK_PROFILE left the Iron Law dormant"


def test_wired_bash_chain_permits_the_ops_path_and_blocks_direct_mutation(project,
                                                                         tmp_path):
    """Iron Law composition, both directions in ONE test so that "blocked" can never be
    satisfied by "nothing works": for agent_type=implementer the wired Bash chain must
    let the ops executor through and must stop an equivalent direct mutation.

    Attribution is per hook: the block has to come from iron-law-gate.py specifically,
    not from any other hook that happens to dislike the command."""
    sanctioned = ("python3 .claude/operations/scripts/execute-json-ops.py "
                  ".claude/plans/plan-fixture.ops.json")
    allowed = run_chain(project, "Bash", {"command": sanctioned}, "standard", tmp_path,
                        agent_type="implementer")
    assert blockers(allowed) == [], (
        "the implementer's own documented command was blocked, leaving it no possible "
        "action: %s" % {n: p.stderr for n, p in allowed.items() if p.returncode == 2})

    denied = run_chain(project, "Bash", {"command": "sed -i '' s/1/99/ src/app.py"},
                       "standard", tmp_path, agent_type="implementer")
    assert "iron-law-gate.py" in blockers(denied), \
        {n: (p.returncode, p.stderr) for n, p in denied.items()}
    assert denied["iron-law-gate.py"].stdout == ""
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == ORIGINAL


def test_reflection_checkpoint_outranks_the_iron_law_allowance(project, tmp_path):
    """Gate PRECEDENCE - the one thing neither gate's own suite can assert.

    iron-law-gate.py PERMITS the ops executor command (it is the sanctioned path);
    reflection-gate.py must still be able to stop that same call while a checkpoint is
    pending, and must release it once a real receipt exists. Both gates are wired on
    PreToolUse/Bash, so the composed verdict is what the agent actually experiences."""
    env = env_for(project, "standard", tmp_path)
    gate = project / ".claude" / "hooks" / "reflection-gate.py"
    command = ("python3 .claude/operations/scripts/execute-json-ops.py "
               ".claude/plans/plan-fixture.ops.json")

    # Seed the checkpoint through the real failure path, never by hand-writing state.
    for _ in range(3):
        failure = {"hook_event_name": "PostToolUseFailure", "session_id": "e2e-session-0001",
                   "cwd": str(project), "tool_name": "Bash",
                   "tool_input": {"command": "pytest -q tests/test_app.py"},
                   "tool_response": {"stderr": "AssertionError"}}
        subprocess.run([sys.executable, str(gate), "--event", "PostToolUseFailure"],
                       input=json.dumps(failure), capture_output=True, text=True,
                       cwd=str(project), env=env, timeout=60)

    pending = run_chain(project, "Bash", {"command": command}, "standard", tmp_path,
                        agent_type="implementer")
    assert "iron-law-gate.py" not in blockers(pending), \
        "precondition lost: the Iron Law gate blocked, so this proves nothing about the " \
        "reflection checkpoint"
    assert "reflection-gate.py" in blockers(pending), (
        "the reflection checkpoint did not stop the sanctioned ops path: %s"
        % {n: (p.returncode, p.stderr[:200]) for n, p in pending.items()})

    # Discharge it the way the product does: a REAL receipt, HMAC-bound to this
    # session's token and to the exact pending active set. Minted through the shipped
    # library (as `test_reflection_gate.py` does) rather than hand-written, because a
    # hand-written receipt is exactly what the gate is supposed to reject.
    with scoped_env(CLAUDEKIT_REFLECTION_DIR=str(tmp_path / "ledger"),
                    CLAUDEKIT_REFLECTION_INBOX=str(tmp_path / "inbox"),
                    ECC_HOOK_PROFILE="standard"):
        reflection = _load_reflection()
        token = reflection.read_session_token("e2e-session-0001")
        checkpoint = reflection.pending_checkpoint("e2e-session-0001")
        assert token and checkpoint, "precondition lost: no checkpoint to discharge"
        reflection.record_receipt("e2e-session-0001", {
            "schemaVersion": reflection.SCHEMA_VERSION, "taskId": "e2e",
            "trigger": checkpoint["trigger"],
            "failureFingerprints": checkpoint["failureFingerprints"],
            "failedAssumption": "assumed the fixture asserted the pre-state value",
            "approachesCompared": ["edit the fixture", "run the approved ops config"],
            "chosenExperiment": "run the approved ops config",
            "proofCommandOrCheck": "pytest -q tests/test_app.py",
            "proofOutcome": "the failing assertion now passes",
            "durableDisposition": "nothing-durable",
        }, token)

    released = run_chain(project, "Bash", {"command": command}, "standard", tmp_path,
                         agent_type="implementer")
    assert blockers(released) == [], (
        "a valid receipt did not release the gate - agents wedge permanently: %s"
        % {n: p.stderr[:200] for n, p in released.items() if p.returncode == 2})


# ------------------------------------ Group F/G: the executor lock and the hook's root

def _lock_holder(project, ready, hold):
    """A child that takes the executor's own lock and holds it until `hold` disappears.

    Deterministic by construction: no sleeps, no races on who wins. The lock is held
    until this test says otherwise, so the executor run below ALWAYS meets a held lock.
    """
    code = (
        "import fcntl, os, sys, time\n"
        "fd = os.open(sys.argv[1], os.O_CREAT | os.O_WRONLY)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "open(sys.argv[2], 'w').write('held')\n"
        "while os.path.exists(sys.argv[3]):\n"
        "    time.sleep(0.02)\n"
    )
    return subprocess.Popen([sys.executable, "-c", code, str(project / ".codemanifest.lock"),
                             str(ready), str(hold)], cwd=str(project))


def test_executor_lock_refuses_a_second_run_and_leaves_no_stale_lock(project, tmp_path):
    """E2E-31/33, reconciled to the property the design actually has.

    `ExecutionLock` (execute-json-ops.py) is project-wide and non-blocking, and NOTHING
    in tests/ references it: `ExecutionLock` and `.codemanifest.lock` appear in no test
    file. Two halves matter and neither is timing-dependent: a run that meets a held lock
    must refuse rather than interleave, and a refused run must not poison the next one
    (E2E-31's "no stale lock left behind that blocks the next run")."""
    env = env_for(project, "minimal", tmp_path)
    config = project / "ops.json"
    config.write_text(json.dumps(_ops_payload(plan="locked")), encoding="utf-8")

    ready, hold = tmp_path / "held", tmp_path / "hold"
    hold.write_text("x", encoding="utf-8")
    child = _lock_holder(project, ready, hold)
    try:
        for _ in range(500):
            if ready.exists():
                break
            child.poll()
            assert child.returncode is None, "lock holder died before taking the lock"
            __import__("time").sleep(0.02)
        assert ready.exists(), "lock holder never acquired the lock"

        blocked = run_script(EXECUTOR, [str(config)], project, env)
        assert blocked.returncode != 0, blocked.stdout + blocked.stderr
        # The exact shipped string, quoted from execute-json-ops.py - a paraphrase would
        # let the message drift out from under the operator who has to act on it.
        assert "Another CodeManifest executor is running" in blocked.stdout + blocked.stderr
        assert (project / "src" / "app.py").read_text(encoding="utf-8") == ORIGINAL, \
            "a run that could not take the lock still mutated the tree"
    finally:
        hold.unlink()
        child.wait(timeout=30)

    # The refused run must not have poisoned the next one.
    recovered = run_script(EXECUTOR, [str(config)], project, env)
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == PATCHED
    assert not (project / ".codemanifest.lock").exists(), \
        "a completed run left its lock behind; the next run would be blocked by it"


def test_wired_edit_chain_blocks_a_cross_project_edit(project, tmp_path):
    """E2E-34's HOOK half. `test_worktree_manager.py` and `test_security.py` cover the
    EXECUTOR's path guard; `ops-enforcement.sh`'s cross-project deny branch is referenced
    by no test in the suite (`CROSS-PROJECT` appears nowhere under tests/). Same
    unit-vs-composition distinction as Group A, applied to the hook."""
    other = Path(tempfile.mkdtemp(prefix=".ck-e2e-other-", dir=str(REPO.parent)))
    try:
        (other / "src").mkdir(parents=True)
        (other / "src" / "app.py").write_text(ORIGINAL, encoding="utf-8")
        escape = f"../{other.name}/src/app.py"
        results = run_chain(project, "Edit", {"file_path": escape}, "standard", tmp_path)
        gate = results["ops-enforcement.sh"]
        assert gate.returncode == 2, gate.stdout + gate.stderr
        assert "CROSS-PROJECT" in gate.stderr, gate.stderr
        assert (other / "src" / "app.py").read_text(encoding="utf-8") == ORIGINAL
    finally:
        shutil.rmtree(other, ignore_errors=True)


def test_sigint_mid_batch_reports_exactly_once_and_rolls_back(project, tmp_path):
    """E2E-28, narrowed to the timing-INDEPENDENT invariants.

    The interrupt is aimed at a `run_command` sleep that sits after the file operations,
    so "mid-batch" is guaranteed rather than raced. What is asserted is the part no unit
    test reaches: an interrupt rolls the batch back and reports exit 130 with a single
    `interrupted` verdict.

    Honest limit, measured rather than assumed: the `len(verdicts) == 1` assertion is a
    consistency check, NOT a proof of the `_result_emitted` latch. Neutering that latch
    leaves this test green (the handler exits via SystemExit, so no second emit is
    reachable on this path). The guard this case is bound to is the handler's rollback -
    disabling it turns the case red. The broader "consistent at an arbitrary instant"
    property is out of scope until the executor grows a deterministic injection point.
    """
    env = env_for(project, "minimal", tmp_path,
                  CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW="sleep")
    created = [f"src/gen_{index}.py" for index in range(5)]
    config = project / "ops.json"
    config.write_text(json.dumps({
        "plan": "interrupted-batch",
        "operations": [{"type": "file_create", "path": path, "content": "X = 1\n"}
                       for path in created]
        + [{"type": "run_command", "command": ["sleep", "10"],
            "reason": "hold the batch open so the signal lands mid-run"}],
    }), encoding="utf-8")

    proc = subprocess.Popen([sys.executable, str(EXECUTOR), str(config)], cwd=str(project),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=env)
    try:
        for _ in range(1500):
            if all((project / path).exists() for path in created):
                break
            assert proc.poll() is None, "executor exited before the file ops were applied"
            __import__("time").sleep(0.02)
        else:
            raise AssertionError("file operations never landed; nothing to interrupt")
        proc.send_signal(__import__("signal").SIGINT)
        stdout, stderr = proc.communicate(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()

    assert proc.returncode == 130, (proc.returncode, stdout, stderr)
    verdicts = [line for line in stdout.splitlines() if line.startswith("RESULT-JSON:")]
    assert len(verdicts) == 1, "the _result_emitted latch let a second verdict out:\n" + stdout
    assert json.loads(verdicts[0][len("RESULT-JSON:"):])["status"] == "interrupted"
    leftover = [path for path in created if (project / path).exists()]
    assert not leftover, f"interrupt left half a plan on disk: {leftover}"


# ------------------------------------------------------ Group H: the delivery contract

REPRINT_PATTERNS = (
    "return the complete plan", "return the entire plan", "return the full plan",
    "print the full ops.json", "print the complete ops.json", "print the entire ops.json",
    "output the entire file", "output the entire plan", "paste the full ops.json",
)


def _uncited(line):
    """Drop quoted spans. A phrase inside quotes is the rule being CITED - INVOCATION.md
    line 64 says never to tell a subagent to "return the complete plan" - not an
    instruction to do it. Matching a citation would make the guard unfixable without
    deleting the prohibition itself."""
    return re.sub(r'"[^"]*"|`[^`]*`', " ", line)


def _reprint_violations(text):
    """The ONE matcher. Both the corpus scan and the seeded-violation self-check below
    call this, so a future change to the scan is actually falsified by the seed - an
    inline copy in the self-check would keep passing while the real scan rotted."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        lowered = _uncited(line).lower()
        if any(pattern in lowered for pattern in REPRINT_PATTERNS):
            hits.append((number, line.strip()))
    return hits


def test_no_shipped_agent_or_command_instructs_a_payload_reprint(tmp_path):
    """E2E-36: the 80.3M-token burn came from handoffs reprinting plan/ops payloads.
    INVOCATION.md now forbids it; this is the guard against contract erosion by prompt
    drift. Only QUOTED occurrences are exempt (the sanctioned carve-out in INVOCATION.md
    states the rule by quoting it); no keyword allowlist, because "never"/"not" anywhere
    on a line is broad enough to swallow a genuine instruction."""
    hits = []
    for path in sorted(list((CLAUDE / "agents").rglob("*.md"))
                       + list((CLAUDE / "commands").rglob("*.md"))):
        for number, line in _reprint_violations(path.read_text(encoding="utf-8")):
            hits.append(f"{path.relative_to(REPO)}:{number}: {line}")
    assert not hits, "payload-reprint instructions found:\n" + "\n".join(hits)

    # The lint must be able to fail, through the same predicate the scan uses.
    seeded = tmp_path / "rogue.md"
    seeded.write_text("Then return the complete plan to the caller.\n", encoding="utf-8")
    assert _reprint_violations(seeded.read_text(encoding="utf-8")), \
        "the exemption logic swallows a genuine violation"

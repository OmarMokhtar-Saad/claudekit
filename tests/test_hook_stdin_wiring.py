"""Behavioral proof that the WIRED hook commands actually receive their stdin payload.

A backgrounded command in a non-interactive shell gets stdin from /dev/null (POSIX), so
`bash -c '... hook.sh &'` silently starves any hook that reads its payload. These tests
run the EXACT command strings out of `.claude/settings.json`, never a paraphrase - a test
that retypes the wiring proves nothing about the wiring.

Every test runs against a tmp sandbox: `reflection-gate.py` writes a recovery footprint
ABOVE the profile gate, so pointing `CLAUDE_PROJECT_DIR` at the real repo would mutate
this repo's own state from the suite.
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTINGS = REPO / ".claude" / "settings.json"
GATE = REPO / ".claude" / "hooks" / "reflection-gate.py"

# The pre-fix wiring, kept verbatim as a mutation control (see the second test).
OLD_BACKGROUNDED_FORM = (
    "bash -c 'ROOT=\"${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel "
    "2>/dev/null || pwd)}\"; bash \"$ROOT/.claude/hooks/command-log-audit.sh\" &'"
)


def wired_command(event: str, needle: str) -> str:
    cfg = json.loads(SETTINGS.read_text())
    for entry in cfg.get("hooks", {}).get(event, []):
        for hook in entry.get("hooks", []):
            if needle in hook.get("command", ""):
                return hook["command"]
    raise AssertionError("no %s hook wired for %s" % (needle, event))


def hook_sandbox(tmp_path: Path) -> Path:
    """A throwaway project root holding a copy of `.claude/hooks/`.

    `.claude/knowledge/` is deliberately NOT created: the ledger's issue-opening path is
    a documented no-op unless `.claude/knowledge/issues/` already exists, and a test must
    not hand it a directory to write into.
    """
    root = tmp_path / "proj"
    (root / ".claude").mkdir(parents=True)
    shutil.copytree(REPO / ".claude" / "hooks", root / ".claude" / "hooks")
    for stale in ("bash-commands.log", "hooks.log"):
        path = root / ".claude" / "hooks" / stale
        if path.exists():
            path.unlink()
    return root


def sandbox_env(root: Path, tmp_path: Path, profile: str) -> dict:
    """Env that keeps BOTH the project state and the ledger inside the sandbox.

    The reflection ledger is keyed by the project dir under `$TMPDIR`, so seeding and
    reading must share both variables or they address different ledgers.
    """
    ledger_tmp = tmp_path / "tmpdir"
    ledger_tmp.mkdir(exist_ok=True)
    env = dict(
        os.environ,
        CLAUDE_PROJECT_DIR=str(root),
        ECC_HOOK_PROFILE=profile,
        TMPDIR=str(ledger_tmp),
    )
    env.pop("CLAUDEKIT_HOOK_LOG", None)
    return env


def run_hook(command: str, root: Path, payload: str, env: dict):
    return subprocess.run(
        ["bash", "-c", command], input=payload, text=True, cwd=str(root),
        env=env, timeout=60, capture_output=True,
    )


def wait_for_marker(path: Path, marker: str, timeout: float = 10.0) -> bool:
    """The hook is backgrounded on purpose, so the parent returns before it writes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists() and marker in path.read_text(errors="replace"):
            return True
        time.sleep(0.2)
    return False


def bash_payload(marker: str) -> str:
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo %s" % marker},
    })


def test_wired_command_log_audit_receives_stdin(tmp_path):
    marker = "hello-stdin-%s" % uuid.uuid4().hex[:8]
    root = hook_sandbox(tmp_path)
    env = sandbox_env(root, tmp_path, "standard")
    run_hook(wired_command("PostToolUse", "command-log-audit.sh"), root,
             bash_payload(marker), env)
    audit = root / ".claude" / "hooks" / "bash-commands.log"
    assert wait_for_marker(audit, marker), (
        "the wired PostToolUse command never recorded the payload; "
        "bash-commands.log exists=%s" % audit.exists()
    )


def test_backgrounding_before_reading_stdin_starves_the_hook(tmp_path):
    """Mutation control. The pre-fix form MUST NOT record - and must fail for the RIGHT
    reason: the hook has to actually run and fail closed on an empty payload. Without the
    hooks.log assertion a hook that crashed on startup would pass as a control."""
    marker = "starved-%s" % uuid.uuid4().hex[:8]
    root = hook_sandbox(tmp_path)
    env = sandbox_env(root, tmp_path, "standard")
    run_hook(OLD_BACKGROUNDED_FORM, root, bash_payload(marker), env)
    audit = root / ".claude" / "hooks" / "bash-commands.log"
    assert not wait_for_marker(audit, marker, timeout=3.0)
    hooks_log = root / ".claude" / "hooks" / "hooks.log"
    assert wait_for_marker(
        hooks_log, "JSON parse failure extracting 'command'", timeout=5.0
    ), "the control hook did not run and fail closed - it proves nothing about stdin"


def seed_learning_loop_duty(session_id: str, env: dict) -> None:
    """Record a mutation with no routed learning: `learning_loop_pending()` then reports
    an unmet duty. Run as a subprocess in the SAME env so it writes the same ledger."""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import reflection\n"
        "assert reflection.record_activity(%r, 'mutation-or-delivery')\n"
        "assert reflection.learning_loop_pending(%r)\n"
        % (str(GATE.parent), session_id, session_id)
    )
    proc = subprocess.run(["python3", "-c", code], env=env, text=True,
                          timeout=60, capture_output=True)
    assert proc.returncode == 0, "could not seed an unmet duty: %s" % proc.stderr


def test_minimal_profile_still_prompts_the_stop_duty(tmp_path):
    """`minimal` suppresses BLOCKING, not the duty prompt. Before the fix the Stop branch
    logged `blocking suppressed` and returned, so a session with a real unmet duty was
    never told - which is why a 317-turn session produced zero receipts in the profile
    this repo actually runs."""
    root = hook_sandbox(tmp_path)
    env = sandbox_env(root, tmp_path, "minimal")
    log = tmp_path / "hooks.log"
    env["CLAUDEKIT_HOOK_LOG"] = str(log)
    session_id = str(uuid.uuid4())
    seed_learning_loop_duty(session_id, env)

    payload = json.dumps({"hook_event_name": "Stop", "session_id": session_id})
    proc = subprocess.run(
        ["python3", str(GATE), "--event", "Stop"],
        input=payload, text=True, cwd=str(root), env=env, timeout=60, capture_output=True,
    )
    assert proc.returncode == 0, "minimal must never block: %s" % proc.stderr
    assert "stop advisory" in log.read_text(errors="replace"), (
        "the Stop advisory path was never reached under ECC_HOOK_PROFILE=minimal"
    )
    assert proc.stdout.strip(), "an unmet duty produced no advisory on stdout"
    emitted = json.loads(proc.stdout.strip().splitlines()[-1])
    assert "decision" not in emitted, "an advisory must not carry a blocking decision"
    assert "LEARNING LOOP" in emitted["systemMessage"], (
        "the advisory did not name the seeded duty: %r" % emitted
    )

#!/usr/bin/env python3
"""reflection-gate.py - the one hook entrypoint for the reflection lifecycle.

Dispatches on `hook_event_name` and implements four previously-missing enforcement
points. It is Python, not shell, because the state it reduces (an append-only ledger,
HMAC'd receipts, sanitized fingerprints) is not expressible in bash-3.2 safely.

EVENT                 BEHAVIOUR
--------------------  ------------------------------------------------------------------
SessionStart          Mint/read the session token, replay any post-compaction carry-over
                      duty on stdout (SessionStart stdout IS injected into context).
PostToolUseFailure    Record ONE sanitized failure into the external ledger (gap G4).
PostToolUse           Note mutation/delivery activity (drives the Stop learning duty).
PreToolUse            BLOCK implementation-mutation and unchanged reruns while a
                      checkpoint is pending. exit 2 + stderr, fails closed (gap G4).
PreCompact            Persist the unmet duties as a carry-over file, never blocks (G7).
Stop / SubagentStop   BLOCK once on an unmet duty; honour `stop_hook_active` (gap G3).

THE BLOCKING CONTRACT (project hard rule 2)
-------------------------------------------
A block is `exit 2` with the reason on STDERR. Never exit 1, never stdout-as-decision.

WHAT STAYS AVAILABLE WHILE A CHECKPOINT IS PENDING
--------------------------------------------------
Read, Grep, Glob, Task, WebFetch, every non-mutating Bash command, plan writing, and -
critically - the `reflection.py receipt|trigger|non-attempt` CLI itself. Only
implementation mutation (Write/Edit/NotebookEdit, destructive/VCS shell, the ops
executor) and reruns of a test whose target already failed are blocked. A gate that
blocks diagnosis would be uninstalled within a day; this one blocks only the actions
that *cannot* be correct before the reflection happens.

HONEST FRAMING (project hard rule 6)
------------------------------------
This is an integrity speed bump against accidental and lazy discharge, NOT an adversarial
control. The agent holds Bash and Read and runs under the same uid as the 0o600 session
token, so it can always read the token and mint a valid receipt. What the gate buys is
that clearing a checkpoint takes a deliberate, auditable act naming the exact duty owed.
Do not describe it as unforgeable.

PROFILE CONVENTION  ***DELIBERATE DIVERGENCE - DO NOT "FIX" THIS BACK***
------------------------------------------------------------------------
Every other hook in this repo short-circuits wholesale at line 1
(`[ "$ECC_HOOK_PROFILE" = minimal ] && exit 0`). This one does NOT. `minimal` suppresses
BLOCKING only; recording keeps running. Reason: a developer who flips profiles
mid-session would otherwise end up with a ledger full of holes that later mis-reduces
(a missing failure silently lowers the active count below the checkpoint threshold).
Both halves are covered by tests - `test_minimal_profile_suppresses_blocking` and
`test_minimal_profile_still_records`. If you convert this to a wholesale `exit 0`, those
tests are what will tell you why you should not.

Python 3.9, stdlib only.
"""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reflection  # noqa: E402  (path shim above must run first)

HOOK_NAME = "reflection-gate"
# `CLAUDEKIT_HOOK_LOG` lets the behavioral tests assert on log lines without appending
# to the developer's real .claude/hooks/hooks.log.
LOG_FILE = Path(os.environ.get("CLAUDEKIT_HOOK_LOG")
                or (Path(__file__).resolve().parent / "hooks.log"))

MUTATING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "str_replace_based_edit_tool",
                  "write_file", "apply_patch"}

_MUTATING_SHELL = re.compile(
    r"\b(?:rm|mv|cp|ln|touch|truncate|install|sed\s+-i|tee)\b"
    r"|\bgit\s+(?:add|commit|push|merge|rebase|reset|revert|checkout|switch|clean|stash)\b"
    r"|\bexecute-json-ops\.py\b"
)
_TEST_MARKERS = ("pytest", "-m unittest", "npm test", "yarn test", "go test",
                 "mvn test", "mvn verify", "gradle test", "cargo test")


def hlog(level: str, message: str) -> None:
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write("[%s] [%s] [%s] %s\n" % (stamp, HOOK_NAME, level, message))
    except OSError:
        pass


def deny(reason: str) -> int:
    """The ONLY blocking contract Claude Code honours: exit 2 with stderr."""
    hlog("BLOCK", reason.splitlines()[0])
    sys.stderr.write(reason.rstrip("\n") + "\n")
    return 2


def blocking_enabled() -> bool:
    return os.environ.get("ECC_HOOK_PROFILE", "standard") != "minimal"


def read_event() -> Tuple[Optional[Dict[str, Any]], str]:
    # .buffer + surrogateescape: text-mode stdin decodes with errors='strict' under a
    # normal user locale, so ONE invalid UTF-8 byte raised UnicodeDecodeError out of
    # this function. Nothing here catches it, so the hook died with a traceback and
    # emitted rc 1 -- which is neither 0 nor 2, breaks hard rule 2, and is read by the
    # host as NON-blocking. Measured on the unpatched hook: rc 1 + traceback; after:
    # rc 2 with "the reflection gate could not parse the tool payload".
    # surrogateescape cannot raise, so the payload reaches the existing unparseable
    # branch, which is what the fail-closed contract is actually written against.
    raw = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")
    try:
        event = json.loads(raw)
    except ValueError:
        return None, raw
    return (event, raw) if isinstance(event, dict) else (None, raw)


def field(event: Dict[str, Any], *names: str) -> Any:
    for name in names:
        if event.get(name) not in (None, ""):
            return event[name]
    return None


def tool_command(event: Dict[str, Any]) -> str:
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        return str(tool_input.get("command") or tool_input.get("cmd") or "")
    if isinstance(tool_input, str):
        return tool_input
    return ""


def tool_target(event: Dict[str, Any]) -> str:
    """Low-cardinality identity of what was attempted.

    A normalized digest of the command (or the tool name) - never the command text, so
    the ledger cannot leak host paths or arguments.
    """
    command = tool_command(event)
    if command:
        normalized = re.sub(r"\s+", " ", command.strip().casefold())
        return "command-" + hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()[:20]
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        path = tool_input.get("file_path") or tool_input.get("path")
        if path:
            return "file-" + hashlib.sha256(
                str(path).casefold().encode("utf-8")
            ).hexdigest()[:20]
    return reflection.bounded_token(event.get("tool_name"), "unknown-target")


def split_tokens(command: str) -> List[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def is_receipt_cli(command: str) -> bool:
    """True for `python3 <this dir>/reflection.py receipt|trigger|non-attempt ...`.

    Resolved by absolute path, not by substring, so the escape hatch cannot be forged by
    naming an unrelated script `reflection.py`. Compound commands (`;`, `&&`, pipes) are
    refused outright - the escape hatch is a single, inspectable invocation.
    """
    if re.search(r"[;&|><`]|\$\(", command):
        return False
    parts = split_tokens(command)
    if len(parts) < 3:
        return False
    index = 0
    while index < len(parts) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", parts[index]):
        index += 1
    if index >= len(parts):
        return False
    head = re.split(r"[/\\]", parts[index])[-1].casefold()
    if head not in {"python", "python3", "py"}:
        return False
    index += 1
    while index < len(parts) and parts[index] in {"-u", "-B", "-3", "-E"}:
        index += 1
    if index + 1 >= len(parts):
        return False
    script = Path(parts[index])
    if not script.is_absolute():
        script = Path.cwd() / script
    try:
        resolved = script.resolve()
    except OSError:
        return False
    if resolved != Path(__file__).resolve().with_name("reflection.py"):
        return False
    return parts[index + 1] in {"receipt", "trigger", "non-attempt", "status"}


def is_receipt_inbox_write(event: Dict[str, Any], session_id: str) -> bool:
    """True for a `Write` aimed at EXACTLY this session's receipt drop box.

    This is the decoupling required so a receipt never has to travel through a shell
    command line (where `command-guard.sh` would refuse free text mentioning
    `subprocess.run`, `os.system(` or `__import__(`).

    *** THIS FUNCTION IS AN EXCEPTION CARVED OUT OF A BLOCKING GATE. TREAT EVERY LINE AS
    ATTACK SURFACE. *** An earlier revision compared `os.path.realpath()` on BOTH sides.
    That resolved symlinks on both, so a symlinked inbox laundered the allowance into an
    arbitrary write:

        ln -s ../../src/claudekit/x.py .claude/reflection/inbox-<key>.json
        Write .claude/reflection/inbox-<key>.json   # realpaths compared equal

    and `ops-enforcement.sh:47` also passed it, because the `file_path` it saw was under
    `.claude/`. Content landed in a source file having cleared BOTH guards - a straight
    breach of hard rule 1 (the Iron Law). Three controls close it, and none may be
    dropped without re-opening it:

      1. Refuse outright if either the candidate or the expected path IS a symlink.
      2. Resolve only the PARENT directory, then compare `realpath(parent) + name`.
         Never `realpath()` the full path - that is precisely what launders the link.
      3. `ln` is in `_MUTATING_SHELL`, so creating the link is itself blocked first.

    Scope is `Write` ONLY - not the whole `MUTATING_TOOLS` set. `Edit`/`MultiEdit`/
    `apply_patch` operate on existing content and have no business creating a receipt.

    Side-effect free by contract: a blocking gate must not touch the filesystem, so this
    never creates the inbox directory (the receipt CLI does that).
    """
    if str(event.get("tool_name") or "") != "Write":
        return False
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return False
    target = tool_input.get("file_path") or tool_input.get("path")
    if not target:
        return False
    candidate = Path(str(target))
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        expected = reflection.inbox_path(session_id)
    except OSError:
        return False
    # Control 1: a symlink on either side is refused, never followed.
    if os.path.islink(str(candidate)) or os.path.islink(str(expected)):
        hlog("BLOCK", "refused a symlinked receipt inbox path")
        return False
    # Control 2: realpath the PARENT only, then compare parent + exact basename.
    try:
        candidate_key = (os.path.realpath(str(candidate.parent)), candidate.name)
        expected_key = (os.path.realpath(str(expected.parent)), expected.name)
    except OSError:
        return False
    return candidate_key == expected_key


def is_mutation(event: Dict[str, Any]) -> bool:
    if str(event.get("tool_name") or "") in MUTATING_TOOLS:
        return True
    command = tool_command(event)
    return bool(command) and bool(_MUTATING_SHELL.search(command.casefold()))


def is_unchanged_rerun(event: Dict[str, Any], session_id: str) -> bool:
    """A test command whose target already sits in the active failure set.

    Rerunning a test you have not changed anything about is the archetypal loop step -
    it is the single most useful thing to interrupt.
    """
    command = tool_command(event)
    if not command:
        return False
    lowered = command.casefold()
    if not any(marker in lowered for marker in _TEST_MARKERS):
        return False
    target = tool_target(event)
    active_targets = {
        item.get("target") for item in reflection.active_entries(session_id)
        if item.get("kind") == "task-failure"
    }
    return reflection.bounded_token(target, "unknown-target") in active_targets


def checkpoint_reason(checkpoint: Dict[str, Any], extra: str = "") -> str:
    return (
        "REFLECTION CHECKPOINT PENDING (%s / %s)\n"
        "%d active failure(s); sanitized fingerprints: %s.\n"
        "%s"
        "Read-only diagnosis, planning and receipt creation remain available; "
        "implementation mutation and unchanged reruns are paused.\n%s" % (
            checkpoint["depth"], checkpoint["trigger"], checkpoint["attemptCount"],
            ",".join(checkpoint["failureFingerprints"]),
            (extra + "\n") if extra else "",
            reflection.receipt_instructions(),
        )
    )


# ----------------------------------------------------------------- event handlers


def handle_session_start(event: Dict[str, Any], session_id: str) -> int:
    token = reflection.record_session_start(session_id)
    # The ONLY place an authoritative session id exists in this repo: it arrives in the
    # payload and reaches nothing else. Recorded so review-record.py can PROVE which
    # session a rejection brief belongs to instead of guessing from file mtimes.
    # Best-effort by construction -- a SessionStart hook must not fail because a retro
    # feature could not write a pointer.
    try:
        reflection.record_session_pointer(
            session_id, field(event, "transcript_path", "transcriptPath"))
    except Exception:
        pass
    lines: List[str] = []
    if token:
        lines.append(
            "Reflection session token (session-scoped; never log, print or commit it): %s"
            % token
        )
    carry = reflection.carryover_path(session_id)
    try:
        # Carry-over text is echoed to stdout, i.e. straight into the model's context, so
        # never read it out of a ledger root another uid could have written.
        if reflection.ledger_dir_trusted() and carry.is_file():
            text = carry.read_text(encoding="utf-8").strip()
            if text:
                lines.append(text)
            carry.unlink()
    except OSError:
        pass
    duties, _ = reflection.duty_summary(session_id)
    if duties:
        lines.append("Unmet reflection duties carried into this context:")
        lines.extend("  - " + duty for duty in duties)
    if lines:
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_failure(event: Dict[str, Any], session_id: str) -> int:
    """Gap G4: a failure now leaves durable, sanitized state."""
    entry = reflection.record_failure(
        session_id,
        phase="tool-outcome",
        target=tool_target(event),
        failure_class="interrupted" if field(event, "is_interrupt") else "tool-failure",
        platform=sys.platform,
        invariant="command-outcome",
        head=reflection.bounded_token(event.get("tool_name"), "unknown"),
        observation_id=field(event, "tool_use_id", "toolUseId"),
    )
    if entry is None:
        hlog("WARN", "could not record failure (no session id or unwritable ledger)")
        return 0
    hlog("INFO", "recorded failure %s fingerprint=%s" % (
        entry["failureId"], entry["fingerprint"]))
    checkpoint = reflection.pending_checkpoint(session_id)
    if checkpoint is not None:
        sys.stdout.write(checkpoint_reason(checkpoint) + "\n")
    return 0


def handle_post_tool_use(event: Dict[str, Any], session_id: str) -> int:
    command = tool_command(event)
    if is_receipt_cli(command) or is_receipt_inbox_write(event, session_id):
        return 0
    if is_mutation(event):
        reflection.record_activity(session_id, "mutation-or-delivery")
    return 0


def handle_pre_tool_use(event: Dict[str, Any], session_id: str) -> int:
    checkpoint = reflection.pending_checkpoint(session_id)
    if checkpoint is None:
        return 0
    command = tool_command(event)
    if is_receipt_cli(command):
        return 0
    if is_receipt_inbox_write(event, session_id):
        return 0
    if is_mutation(event):
        return deny(checkpoint_reason(checkpoint, "Blocked action: implementation mutation."))
    if is_unchanged_rerun(event, session_id):
        return deny(checkpoint_reason(
            checkpoint,
            "Blocked action: rerunning a command that already failed, unchanged.",
        ))
    return 0


def handle_pre_compact(event: Dict[str, Any], session_id: str) -> int:
    """Gap G7: duties survive compaction.

    The ledger itself is external and already survives; what does NOT survive is the
    model's awareness of it. So persist a carry-over note that SessionStart (source
    `compact`) replays into the fresh context. This hook never blocks - refusing to
    compact is how you strand a session with no way out.
    """
    duties, _ = reflection.duty_summary(session_id)
    reflection.append_entry(session_id, {
        "schemaVersion": reflection.SCHEMA_VERSION,
        "kind": "compaction",
        "trigger": reflection.bounded_token(event.get("trigger"), "unknown"),
        "dutyCount": len(duties),
        "observedAt": reflection.now_iso(),
    })
    if duties:
        text = "\n".join(
            ["Reflection duties that survived compaction (the ledger is external "
             "to this transcript):"]
            + ["  - " + duty for duty in duties]
            + [reflection.receipt_instructions()]
        )
        try:
            # The ledger root is created and ownership-checked in exactly one place.
            if reflection.ensure_ledger_dir() is None:
                raise OSError("reflection ledger root is not private to this user")
            path = reflection.carryover_path(session_id)
            path.write_text(text + "\n", encoding="utf-8")
        except OSError:
            hlog("WARN", "could not persist compaction carry-over")
        sys.stdout.write(text + "\n")
    hlog("INFO", "pre-compact: %d unmet duty(ies) persisted" % len(duties))
    return 0


def git_porcelain(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(root),
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def advisory_warnings(root: Path) -> List[str]:
    """Non-blocking checks preserved from the Stop entry this hook replaces.

    Uncommitted work stays a WARNING, never a block: stopping mid-change is normal and
    legitimate, so blocking on it would train the operator to hit the second attempt
    reflexively and hollow out the duties that *do* block.
    """
    warnings: List[str] = []
    if git_porcelain(root):
        warnings.append("Uncommitted changes remain in the working tree (git status).")
    plans = root / ".claude" / "plans"
    if plans.is_dir():
        for path in sorted(plans.glob("*.json")):
            name = path.name
            if not (name.endswith(".ops.json") or name.startswith("ops-")):
                continue
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                warnings.append("Invalid ops config JSON: %s" % name)
    return warnings


def handle_stop(event: Dict[str, Any], session_id: str, subagent: bool) -> int:
    """Gap G3: a turn can no longer end on an unmet duty - once.

    `stop_hook_active` is true on the retry after this hook already blocked. Honouring it
    is what turns the gate into an interrupt instead of a trap: one forced pause, then
    the operator is always able to proceed.
    """
    root = project_root()
    for warning in advisory_warnings(root):
        hlog("WARN", warning)
        sys.stderr.write("WARNING: %s\n" % warning)
    duties, _ = reflection.duty_summary(session_id)
    if not duties:
        hlog("INFO", "stop: all duties met")
        return 0
    if bool(field(event, "stop_hook_active", "stopHookActive")):
        hlog("INFO", "stop: duties unmet but stop_hook_active - allowing (interrupt-once)")
        sys.stderr.write(
            "NOTE: reflection duties are still unmet; proceeding because this turn was "
            "already interrupted once.\n"
        )
        return 0
    label = "SUBAGENT STOP" if subagent else "STOP"
    return deny(
        "%s BLOCKED - unmet duties:\n%s\n%s\nThis interrupts once: if you deliberately "
        "choose to stop anyway, the next attempt proceeds." % (
            label, "\n".join("  - " + duty for duty in duties),
            reflection.receipt_instructions(),
        )
    )


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def declared_event() -> str:
    """Event name as declared by settings.json (`--event <Name>`).

    Authoritative when the payload is unparsable: the fail-closed decision must not
    depend on grepping a malformed blob for a substring.
    """
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "--event":
        return argv[1]
    return ""


def main() -> int:
    declared = declared_event()
    event, raw = read_event()
    if event is None:
        # Fail closed on the only surface where a forged/garbled payload could smuggle a
        # mutation past the gate. Stop/SubagentStop deliberately fail OPEN: with no
        # parsable session id no duty is provable, and a block we cannot justify would
        # strand the turn. Both directions are logged.
        hlog("ERROR", "unparsable %s payload (%d bytes)" % (declared or "hook", len(raw)))
        if declared == "PreToolUse":
            return deny(
                "BLOCKED: the reflection gate could not parse the tool payload and "
                "cannot prove no reflection checkpoint is pending."
            )
        return 0

    name = str(field(event, "hook_event_name", "hookEventName") or declared)
    session_id = str(field(event, "session_id", "sessionId") or "")
    if not reflection.valid_session(session_id):
        hlog("WARN", "event %s without a session id - no reflection state applied" % name)
        return 0

    if name == "SessionStart":
        return handle_session_start(event, session_id)
    if name == "PostToolUseFailure":
        return handle_failure(event, session_id)
    if name == "PostToolUse":
        return handle_post_tool_use(event, session_id)
    if name == "PreCompact":
        return handle_pre_compact(event, session_id)

    if not blocking_enabled():
        # See PROFILE CONVENTION in the header: blocking only, recording already ran.
        hlog("INFO", "ECC_HOOK_PROFILE=minimal - %s blocking suppressed" % name)
        return 0
    if name == "PreToolUse":
        return handle_pre_tool_use(event, session_id)
    if name in {"Stop", "SubagentStop"}:
        return handle_stop(event, session_id, subagent=(name == "SubagentStop"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

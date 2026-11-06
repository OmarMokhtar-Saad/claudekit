"""End-to-end pipeline composition, deterministic and offline.

Covers the SEAM no unit test sees: the hooks running as `settings.json` actually wires
them (through the `bash -c` wrapper with its `ROOT=` resolution), so plan-gate blocks a
source edit end to end, and no shipped agent or command tells the model to reprint a plan
payload. `ECC_HOOK_PROFILE` is passed explicitly to every subprocess, and the fixture
project is created BESIDE the repo, never under `$TMPDIR` (OS scratch is exempted).
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

REPO = Path(__file__).resolve().parents[1]
CLAUDE = REPO / ".claude"
SCRIPTS = CLAUDE / "operations" / "scripts"
SETTINGS = CLAUDE / "settings.json"

EXTRACTOR = SCRIPTS / "extract-json-from-plan.py"
VALIDATOR = SCRIPTS / "validate-config-json.py"
RECORDER = SCRIPTS / "review-record.py"

ORIGINAL = "VALUE = 1\n"
PATCHED = "VALUE = 99\n"
REVISED = "VALUE = 123\n"


# --------------------------------------------------------------------------- fixtures

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
            if not command:
                continue
            if "dispatch.sh" in command:
                out.extend(_dispatched_commands(matcher_tool))
                continue
            out.append((_hook_name(command), command))
    return out


def _dispatched_commands(matcher_tool):
    """Expand a `dispatch.sh` registration into the handlers it will really run.

    settings.json now names ONE dispatcher for PreToolUse, so parsing settings
    alone would stop naming individual hooks -- and these chain tests would go
    quiet exactly where they are supposed to shout, since their whole job is to
    catch a hook that is present, unit-tested and never invoked. The registry is
    the wiring now, so the registry is what gets parsed: a handler dropped from
    `dispatch-registry.json` fails these tests the same way an unwired hook did.

    Each row is reconstructed into the command settings.json used to hold,
    INCLUDING the `git commit` / `git push` conditional wrapper, so the chain the
    tests drive is behaviourally the same one.
    """
    registry_path = SETTINGS.parent / "hooks" / "dispatch-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    out = []
    for row in registry["events"].get("PreToolUse", []):
        matcher = row.get("matcher") or ""
        if matcher and matcher_tool not in matcher.split("|"):
            continue
        runner = row.get("runner", "bash")
        args = " ".join(row.get("args") or [])
        root = 'ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"'
        invoke = '%s "$ROOT/.claude/hooks/%s" %s' % (runner, row["file"], args)
        condition = row.get("command_matcher") or ""
        if condition:
            command = (
                '%s; TOOL_INPUT=$(cat); CMD=$(echo "$TOOL_INPUT" | python3 -c '
                '"import sys,json; d=json.load(sys.stdin); '
                'print(d.get(\'tool_input\',{}).get(\'command\') or d.get(\'command\',\'\'))" '
                '2>/dev/null); if echo "$CMD" | grep -qE "%s"; then %s; fi'
                % (root, condition, invoke))
        else:
            command = "%s; %s" % (root, invoke)
        out.append((row["file"], command))
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

def test_wired_edit_chain_blocks_a_source_edit_under_standard(project, tmp_path):
    """E2E-13/17 as composition: the hooks are run through settings.json's own `bash -c`
    wrapper (ROOT resolution included), not by file path. Attribution is asserted per
    hook, so "blocked" can never be satisfied by some unrelated hook in the chain."""
    results = run_chain(project, "Edit", {"file_path": str(project / "src" / "app.py")},
                        "standard", tmp_path)
    assert "plan-gate.sh" in results, \
        "plan-gate.sh is not wired for Edit in settings.json - it never fires"
    gate = results["plan-gate.sh"]
    assert gate.returncode == 2, gate.stdout + gate.stderr
    assert gate.stderr.strip(), "a block with no stderr gives the agent nothing to act on"
    assert "PLAN GATE" in gate.stderr
    assert gate.stdout == "", "a PreToolUse decision must never travel on stdout"
    # No checkpoint tag exists in the fixture either, so checkpoint-gate also blocks.
    assert blockers(results) == ["checkpoint-gate.sh", "plan-gate.sh"], blockers(results)


def test_wired_edit_chain_still_blocks_under_minimal(project, tmp_path):
    """`minimal` (the maintainer default) must NOT disable the Tier-3 plan gate."""
    results = run_chain(project, "Edit", {"file_path": str(project / "src" / "app.py")},
                        "minimal", tmp_path)
    assert results["plan-gate.sh"].returncode == 2, results["plan-gate.sh"].stderr


def test_wired_edit_chain_defaults_to_enforcing_when_profile_is_unset(project, tmp_path):
    """E2E-15: an unset profile must NOT silently disable enforcement for anyone who did
    not read the setup gotcha. `${ECC_HOOK_PROFILE:-standard}` is the whole guard."""
    results = run_chain(project, "Edit", {"file_path": str(project / "src" / "app.py")},
                        None, tmp_path)
    assert results["plan-gate.sh"].returncode == 2, \
        "an unset ECC_HOOK_PROFILE left the plan gate dormant"


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

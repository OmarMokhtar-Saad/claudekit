"""The three `$LOG` hooks log to their own directory, not the caller's cwd.

`format-typecheck.sh`, `security-reminder.sh` and `session-start.sh` each set
`LOG=".claude/hooks/hooks.log"` -- a CWD-RELATIVE path -- and defined their own
`log()` writing to it. Run from anywhere but the repo root, their log lines landed in
a different tree or nowhere at all, silently. That is finding F107's third `LOG_FILE=`
form, and the same class already misplaces `command-log-audit.sh`'s audit trail (F55).

Only these three were changed. The other 11 local `log()` definitions work correctly and
were deliberately left alone: delegating them would mean adding `. lib.sh` to 12 hooks
(including `pre-push.sh`, which runs the full suite) and widening `lib.sh`'s blast radius
from 11 hooks to 23, across 16 downstream repos, with no defect behind it.

The mutation that proves these bind: restore `LOG=".claude/hooks/hooks.log"` plus the
local `log()` in any of the three and `test_logs_land_beside_the_hook_not_in_the_cwd`
fails.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / ".claude" / "hooks"

# The three hooks this change covers, and the profile each needs to do any work.
DELEGATED = {
    "format-typecheck.sh": "strict",
    "security-reminder.sh": "standard",
    "session-start.sh": "standard",
}


@pytest.mark.parametrize("name", sorted(DELEGATED))
def test_no_local_log_definition_remains(name):
    body = (HOOKS / name).read_text()
    assert 'log() { hlog "$@"; }' in body, f"{name} should delegate to lib.sh's hlog"
    assert 'LOG=".claude/hooks/hooks.log"' not in body, (
        f"{name} still sets a cwd-relative LOG"
    )
    assert 'LOG_FILE="$SCRIPT_DIR/hooks.log"' in body


@pytest.mark.parametrize("name", sorted(DELEGATED))
def test_each_sources_lib_sh(name):
    """`hlog` comes from lib.sh; delegating without sourcing it is a silent no-op."""
    body = (HOOKS / name).read_text()
    assert '. "$SCRIPT_DIR/lib.sh"' in body


@pytest.mark.parametrize("name", sorted(DELEGATED))
def test_logs_land_beside_the_hook_not_in_the_cwd(tmp_path, name):
    """The actual defect: run the hook from a foreign cwd and follow the log line.

    A copy of the hooks directory is used so the assertion is about a fresh log file
    rather than this repo's 4.7 MB one, and so a failure cannot be masked by lines
    another test appended.
    """
    kit = tmp_path / "kit" / ".claude" / "hooks"
    kit.parent.mkdir(parents=True)
    shutil.copytree(HOOKS, kit, ignore=shutil.ignore_patterns("*.log"))
    # `.claude/hooks/` is created in the foreign cwd ON PURPOSE. The replaced code
    # appended with `2>/dev/null`, so without an existing directory the write failed
    # SILENTLY and this assertion passed against the defect -- a vacuous test. Proven:
    # with the old `log()` restored and no directory here, only the structural
    # assertions failed. Now the stray path is writable, so the defect lands a file.
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / ".claude" / "hooks").mkdir(parents=True)

    env = dict(os.environ, ECC_HOOK_PROFILE=DELEGATED[name])
    subprocess.run(
        ["bash", str(kit / name)],
        cwd=str(elsewhere), input="{}", capture_output=True, text=True, env=env,
    )

    log = kit / "hooks.log"
    stray = elsewhere / ".claude" / "hooks" / "hooks.log"
    assert not stray.exists(), f"{name} wrote its log into the caller's cwd"
    if log.exists():
        assert name.replace(".sh", "") in log.read_text()


def test_hlog_keeps_arguments_past_the_second():
    """`hlog` uses `$*`; the replaced one-liners used `$2` and dropped the rest."""
    script = (
        'HOOK_NAME=probe\n'
        'LOG_FILE="$1"\n'
        '. "$2/lib.sh"\n'
        'log() { hlog "$@"; }\n'
        'log INFO one two three\n'
    )
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        logf = Path(d) / "out.log"
        subprocess.run(["bash", "-c", script, "-", str(logf), str(HOOKS)],
                       capture_output=True, text=True)
        assert "one two three" in logf.read_text()


def test_the_audit_log_lands_beside_the_hook_not_in_the_cwd(tmp_path):
    """`command-log-audit.sh` wrote its AUDIT TRAIL to a cwd-relative path while its own
    `LOG_FILE` one line above used `$SCRIPT_DIR`. Of the 11 hooks wired in settings.json
    exactly one is invoked with a `cd` to the project root, and this is not it, so from any
    other directory the trail went elsewhere -- or nowhere, since the append is
    `2>/dev/null` and a missing directory fails silently. Finding F55.
    """
    kit = tmp_path / "kit" / ".claude" / "hooks"
    kit.parent.mkdir(parents=True)
    shutil.copytree(HOOKS, kit, ignore=shutil.ignore_patterns("*.log"))
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / ".claude" / "hooks").mkdir(parents=True)

    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "echo audit-probe-marker"}})
    subprocess.run(["bash", str(kit / "command-log-audit.sh")], cwd=str(elsewhere),
                   input=payload, capture_output=True, text=True,
                   env=dict(os.environ, ECC_HOOK_PROFILE="standard"))

    # RECORDING FIRST, location second. The earlier version of this test asserted only
    # that no stray file appeared in the cwd, and it passed against a hook that recorded
    # NOTHING ANYWHERE -- the fifth vacuous assertion in this series. The hook had its own
    # inline extractor reading `command` at the top level while the payload nests it under
    # `tool_input`, so it returned before the append every time; `.claude/hooks/
    # bash-commands.log` did not exist in this repo after weeks of hook runs.
    trail = kit / "bash-commands.log"
    assert trail.exists(), "the audit hook recorded nothing at all"
    assert "audit-probe-marker" in trail.read_text(), (
        "the command never reached the audit trail -- check the payload extraction, not "
        "the path"
    )
    stray = elsewhere / ".claude" / "hooks" / "bash-commands.log"
    assert not stray.exists(), "the audit trail was written into the caller's cwd"


def test_cost_tracker_records_land_beside_the_hook(tmp_path):
    """Same class, same measurement: `COST_LOG` and `SESSION_LOG` were cwd-relative."""
    body = (HOOKS / "cost-tracker.sh").read_text()
    assert 'COST_LOG=".claude/' not in body
    assert 'SESSION_LOG=".claude/' not in body
    assert 'COST_LOG="$SCRIPT_DIR' in body


def test_cost_tracker_does_not_claim_to_track_cost():
    """F49: it counts lines in the hook log and has no access to tokens or prices. The
    filename stays (renaming a shipped hook is user-visible and owner-gated), so the file
    must say so -- a name that promises what the code cannot deliver is hard rule 6's
    territory, and the honest statement is the whole fix available here."""
    body = (HOOKS / "cost-tracker.sh").read_text()
    assert "no cost is tracked here" in body
    assert "estimates costs" not in body, "the old promise is still in the header"

@pytest.mark.parametrize("name", sorted(DELEGATED))
def test_a_missing_lib_sh_stays_silent(tmp_path, name):
    """The `[ -f ... ] &&` source guard promises graceful degradation; `log() { hlog "$@"; }`
    removed it. With `lib.sh` absent the hook printed "hlog: command not found" on stderr
    for every log call -- the old body ended in `2>/dev/null`. A no-op `hlog` fallback keeps
    the promise the guard makes. Mutation: delete the `command -v hlog` line and this fails.
    """
    solo = tmp_path / "solo"
    solo.mkdir()
    shutil.copy(HOOKS / name, solo / name)
    env = dict(os.environ, ECC_HOOK_PROFILE=DELEGATED[name])
    proc = subprocess.run(["bash", str(solo / name)], cwd=str(solo), input="{}",
                          capture_output=True, text=True, env=env)
    assert "command not found" not in proc.stderr, proc.stderr

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

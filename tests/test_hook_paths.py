"""No hook assumes its working directory.

Measured 2026-08-25, as a PROPERTY rather than as the sites anyone happened to notice --
which is why the count kept growing. Finding F107 recorded "two forms", then three, then
four; a structural grep found **16 cwd-relative `.claude/` assignments across 8 hooks**,
while exactly **one** of the eleven hooks wired in `settings.json` is invoked with a `cd`
to the project root.

The consequences were not cosmetic. `command-log-audit.sh` never wrote its audit trail;
`format-typecheck.sh` looked for `edited-files.log` in a directory `post-tool-use.sh` had
not written it to; `session-start.sh` reported a phantom injection finding for any session
started below the repo root.

The rule this file enforces:

  * a file the HOOK owns (its log, its counter, its scratch report, its own config)
    resolves through `$SCRIPT_DIR`;
  * a file the PROJECT owns (checkpoints, locks, the session context, the project graph)
    resolves through `$CK_ROOT` -- `CLAUDE_PROJECT_DIR`, else the git toplevel, else cwd.

Neither may be spelled as a bare `.claude/...` string, because that silently means
"wherever this process happens to be standing".
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / ".claude" / "hooks"

# `PATH=` and friends are not filesystem paths into the kit; only `.claude/`-rooted
# literals are in scope.
# WIDENED. The first version matched only an unindented UPPERCASE scalar assignment with a
# quote, while the docstring claimed the property "no hook assumes its working directory".
# Live offenders it missed, both found by review: `pre-plan.sh` declared
# `local plan_dirs=(".claude/plans" ...)` -- a UserPromptSubmit hook whose duplicate
# detection then reports "no duplicates" from any subdirectory, a silent wrong answer --
# and `pre-commit.sh` passed `.claude/plans/` as a bare `find` argument.
_CWD_RELATIVE = re.compile(
    r'^\s*(?:local\s+|export\s+|declare\s+(?:-[a-zA-Z]+\s+)?)?'   # local/export/declare
    r'(\w+)=\(?["\']?\.claude/',                                    # scalar or array
    re.M)

# `.claude/...` as a bare word in a command position: `find .claude/plans`, `cd .claude`,
# `mkdir -p .claude/hooks`. Quoted or not.
_CWD_RELATIVE_ARG = re.compile(r'(?<![\w$/"\'])\.claude/[\w./*-]*', re.M)


def _shell_hooks():
    return sorted(p for p in HOOKS.glob("*.sh"))


def test_there_is_something_to_check():
    """A property test over an empty set is the vacuity this file exists to prevent."""
    assert len(_shell_hooks()) >= 15


@pytest.mark.parametrize("hook", _shell_hooks(), ids=lambda p: p.name)
def test_no_hook_assigns_a_cwd_relative_claude_path(hook):
    offenders = [m.group(1) for m in _CWD_RELATIVE.finditer(hook.read_text())]
    assert not offenders, (
        f"{hook.name} assigns {offenders} as a cwd-relative `.claude/` path. Use "
        f"$SCRIPT_DIR for a file the hook owns, or $CK_ROOT for a file the project owns; "
        f"a bare `.claude/...` means 'wherever this process is standing', and only one of "
        f"the eleven wired hooks is invoked with a cd to the project root."
    )


@pytest.mark.parametrize("hook,var", [
    ("auto-checkpoint.sh", "CHECKPOINT_DIR"),
    ("session-start.sh", "LOCKS_DIR"),
    ("session-start.sh", "GRAPH_FILE"),
    ("session-start.sh", "CONTEXT_FILE"),
])
def test_project_state_resolves_through_the_project_root(hook, var):
    """These name the repo being worked in, so `$SCRIPT_DIR` would be just as wrong as a
    bare relative path -- it would put a project's checkpoints inside the kit."""
    body = (HOOKS / hook).read_text()
    match = re.search(rf'^{var}="([^"]+)"', body, re.M)
    assert match, f"{var} not found in {hook}"
    assert "$CK_ROOT" in match.group(1), f"{hook}:{var} = {match.group(1)}"


@pytest.mark.parametrize("hook,var", [
    ("file-guard.sh", "LOG_FILE"),
    ("check-comment-replacement.sh", "LOG_FILE"),
    ("auto-checkpoint.sh", "LOG_FILE"),
    ("suggest-compact.sh", "COUNTER_FILE"),
    ("format-typecheck.sh", "EDITED_LOG"),
    ("command-log-audit.sh", "AUDIT_LOG"),
    ("cost-tracker.sh", "COST_LOG"),
])
def test_hook_owned_files_resolve_through_the_script_directory(hook, var):
    body = (HOOKS / hook).read_text()
    match = re.search(rf'^{var}="([^"]+)"', body, re.M)
    assert match, f"{var} not found in {hook}"
    assert "$SCRIPT_DIR" in match.group(1), f"{hook}:{var} = {match.group(1)}"


# `lib.sh` is SOURCED, not executed: it inherits `$SCRIPT_DIR` from whichever hook sources
# it, and defining its own would shadow the caller's. Exempt by nature, not by convenience.
SOURCED_LIBRARIES = {"lib.sh"}


def _code_only(body):
    """Comment lines dropped. Both of these checks first failed on PROSE -- the banner
    comment explaining the $SCRIPT_DIR/$CK_ROOT rule mentions both names, so a hook that
    merely documents the convention read as one that depends on it. A test that cannot
    tell code from a comment about code will report the comment."""
    return "\n".join(line for line in body.splitlines()
                      if not line.lstrip().startswith("#"))


def test_every_hook_that_uses_ck_root_defines_it():
    """`$CK_ROOT` unset resolves to `/.claude/...` -- an absolute path at the filesystem
    root. Louder than a cwd-relative path, but still wrong."""
    for hook in _shell_hooks():
        if hook.name in SOURCED_LIBRARIES:
            continue
        code = _code_only(hook.read_text())
        if "$CK_ROOT" in code:
            assert re.search(r'^CK_ROOT=', code, re.M), f"{hook.name} uses $CK_ROOT unset"


def test_every_hook_that_uses_script_dir_defines_it():
    for hook in _shell_hooks():
        if hook.name in SOURCED_LIBRARIES:
            continue
        code = _code_only(hook.read_text())
        if "$SCRIPT_DIR" in code:
            assert re.search(r'^SCRIPT_DIR=', code, re.M), f"{hook.name} uses $SCRIPT_DIR unset"


def test_the_sourced_library_exemption_is_still_accurate():
    """If `lib.sh` ever defines its own `SCRIPT_DIR`, the exemption above stops being a
    statement about how sourcing works and becomes a hole."""
    body = (HOOKS / "lib.sh").read_text()
    assert not re.search(r'^SCRIPT_DIR=', body, re.M), (
        "lib.sh now defines SCRIPT_DIR, which shadows its caller's -- remove it from "
        "SOURCED_LIBRARIES and fix the shadowing"
    )

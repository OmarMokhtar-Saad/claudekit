"""Behavioral tests for .claude/hooks/iron-law-gate.py.

Every test runs the real hook as a subprocess with a real JSON payload on stdin and
asserts the exit code and stderr - the only contract Claude Code honours (exit 2 +
stderr blocks; exit 1 / stdout does not). `ECC_HOOK_PROFILE` is forced explicitly so no
result depends on the developer's own session profile (this repo develops with
`minimal`, which the hook deliberately treats as "record but do not block").

The BLOCKED corpus is not decoration: every entry is a bypass that was actually
available to the interactive implementer before this hook existed, because a
frontmatter-declared `Bash(...)` specifier is not applied on that path.
`test_every_blocked_command_is_bound_to_the_guard` re-runs the whole corpus against a
copy of the hook whose decision function has been neutered, and requires that every
single case flips to exit 0 - so none of these assertions can pass for an unrelated
reason.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "iron-law-gate.py"
SETTINGS = REPO / ".claude" / "settings.json"

# --------------------------------------------------------------------------- corpora

# The implementer's sanctioned loop, taken verbatim from `.claude/agents/implementer.md`
# (Steps 1-4) and `.claude/commands/implement.md` (Phases 1-3). If any of these regress
# to a block, /implement can do nothing at all - the ops engine is reached THROUGH Bash.
SANCTIONED = [
    "python3 .claude/operations/scripts/validate-config-json.py p.ops.json --stamp-baseline",
    "python3 .claude/operations/scripts/execute-json-ops.py p.ops.json --dry-run",
    "python3 .claude/operations/scripts/execute-json-ops.py p.ops.json",
    "python3 -u .claude/operations/scripts/execute-json-ops.py p.ops.json",
    # The reflection escape hatch. reflection-gate.py can block the implementer on a
    # pending checkpoint and this CLI is the ONLY way out (the receipt inbox is a Write,
    # which the implementer does not hold). Two gates fighting over an escape hatch has
    # already happened in this repo once; this case is the regression test for it.
    "python3 .claude/hooks/reflection.py receipt --session-id s --session-token t",
    "python3 .claude/hooks/reflection.py status --session-id s",
    # Step 4 verification.
    "python3 -m pytest tests/ -q",
    "pytest -q",
    "ruff check src/ tests/ scripts/",
    "ruff format --check src/",
    "mypy",
    "shellcheck install.sh",
    "shellcheck install.sh .claude/hooks/*.sh",
    "ck doctor --strict",
    # Read-only inspection, per implementer.md ("cat, grep, ls, git status").
    "cat README.md",
    "head -n 40 pyproject.toml",
    "grep -rn TODO src",
    "ls -la .claude/plans",
    "find . -name '*.ops.json'",
    "find . -maxdepth 2 -type f -name '*.sh'",
    "wc -l install.sh",
    "git status",
    "git status --porcelain",
    "git diff --stat",
    "git log --oneline -5",
    "git show HEAD --stat",
    # `branch`/`remote` are mutating subcommands kept only in their pure listing forms.
    "git branch --show-current",
    "git branch --list",
    "git branch --list 'feat*'",
    "git remote -v",
    # CLAUDE.md's two remaining mandatory Definition-of-Done gates. Permitted ONLY with
    # --check; without it gen-docs.py rewrites the docs.
    "python3 scripts/gen-docs.py --check",
    "python3 scripts/gen-registry.py --check",
]

# CLAUDE.md's six mandatory Definition-of-Done commands, verbatim. Every SAFE list in the
# hook is derived from these plus the ops triple and the reflection escape hatch; if one
# of these regresses to a block, the implementer can never report a green DoD.
DOD_COMMANDS = [
    "python3 -m pytest tests/ -q",
    "ruff check src/ tests/ scripts/",
    "mypy",
    "python3 scripts/gen-docs.py --check",
    "python3 scripts/gen-registry.py --check",
    "shellcheck install.sh .claude/hooks/*.sh",
]

# Each entry is (command, short label). Labels keep pytest ids readable.
BLOCKED = [
    ("sed -i 's/a/b/' src/x.py", "sed-in-place"),
    ("sed -n '1,5w /tmp/out' src/x.py", "sed-w-command-writes-without-i"),
    ("cat > src/x.py", "cat-redirect"),
    ("cat >> src/x.py", "cat-append"),
    ("python3 -c \"open('src/x.py','w').write('x')\"", "python-c-write"),
    ("python -c 'import os; os.remove(\"x\")'", "python-c-remove"),
    ("tee src/x.py", "tee"),
    ("git apply patch.diff", "git-apply"),
    ("git checkout -- src/", "git-checkout"),
    ("git restore src/x.py", "git-restore"),
    ("git reset --hard origin/main", "git-reset"),
    ("git commit -m x", "git-commit"),
    ("git -c core.pager='!sh -c \"id\"' log", "git-dash-c-alias"),
    ("git -C /tmp status", "git-dash-C"),
    ("git diff --output=/tmp/out", "git-diff-output"),
    ("patch -p1 -i patch.diff", "patch"),
    ("perl -pi -e 's/a/b/' src/x.py", "perl-pi"),
    ("perl -i -e 1 src/x.py", "perl-i"),
    ("ed src/x.py", "ed"),
    ("sh -c 'echo x > src/y.py'", "sh-c"),
    ("bash -c 'rm -rf src'", "bash-c"),
    ("env FOO=1 rm src/x.py", "env-wrapper"),
    ("xargs rm", "xargs"),
    ("nohup rm src/x.py", "nohup"),
    ("eval rm", "eval"),
    ("PYTHONPATH=/tmp python3 .claude/operations/scripts/execute-json-ops.py p.ops.json",
     "leading-env-assignment"),
    ("cat <<EOF", "heredoc"),
    ("echo $(whoami)", "dollar-paren"),
    ("echo `whoami`", "backtick"),
    ("git status; rm src/x.py", "semicolon-chain"),
    ("git status && rm src/x.py", "and-chain"),
    ("git status || rm src/x.py", "or-chain"),
    ("cat f | tee src/x.py", "pipe-to-tee"),
    ("git status\nrm src/x.py", "newline-second-command"),
    ("rm -rf src", "rm"),
    ("mv src/a.py src/b.py", "mv"),
    ("cp /dev/null src/x.py", "cp"),
    ("truncate -s 0 src/x.py", "truncate"),
    ("install -m 644 /dev/null src/x.py", "install"),
    ("dd if=/dev/zero of=src/x.py", "dd"),
    ("ln -s /etc/passwd src/x.py", "ln"),
    ("touch src/x.py", "touch"),
    ("chmod +x src/x.py", "chmod"),
    ("sort -o src/x.py src/x.py", "sort-o-writes"),
    ("find . -name '*.py' -delete", "find-delete"),
    ("find . -name '*.py' -exec rm {} ;", "find-exec"),
    ("ruff check --fix src/", "ruff-fix"),
    ("ruff format src/", "ruff-format-writes"),
    ("mypy --html-report /tmp/r src", "mypy-report-writes"),
    ("pytest -p evilplugin tests/", "pytest-plugin-injection"),
    # MAJOR 1 (review): an arbitrary-write vector through an allowlisted verb. pytest's
    # own writer is pointed at a source file, which it creates and truncates - no
    # ops.json, no backup, no approval. Distinct from the conftest.py residual.
    ("pytest --log-file=src/claudekit/__init__.py --log-file-level=DEBUG tests/ -q",
     "pytest-log-file"),
    ("pytest --log-file src/x.py tests/", "pytest-log-file-detached"),
    ("pytest -o addopts=-pevil tests/", "pytest-ini-override"),
    ("pytest -c /tmp/evil.ini tests/", "pytest-alt-ini"),
    ("pytest --override-ini=addopts=-pevil tests/", "pytest-override-ini-long"),
    # MAJOR 2 (review): `branch` and `remote` are NOT read-only subcommands.
    ("git branch -D feature", "git-branch-delete"),
    ("git branch -m old new", "git-branch-move"),
    ("git remote add origin git@example.com:x/y.git", "git-remote-add"),
    ("git branch newfeature", "git-branch-create-positional"),
    ("git branch -D", "git-branch-delete-flagonly"),
    ("git remote set-url origin git@evil:x/y.git", "git-remote-set-url"),
    ("git remote prune origin", "git-remote-prune"),
    # Same bypass class as MAJOR 1, in the other linters.
    ("ruff check --output-file /tmp/out src/", "ruff-output-file"),
    ("ruff check --config /tmp/evil.toml src/", "ruff-config-injection"),
    ("mypy --config-file /tmp/evil.ini src", "mypy-config-plugin-injection"),
    # MAJOR 4 (review): permitted ONLY with --check, because without it gen-docs writes.
    ("python3 scripts/gen-docs.py", "gen-docs-without-check"),
    ("python3 scripts/gen-registry.py", "gen-registry-without-check"),
    ("python3 scripts/build.py --check", "other-repo-script-even-with-check"),
    # ROUND 3 findings - writers that a flag DENYLIST missed twice in a row.
    ("ruff check --add-noqa src/", "ruff-add-noqa-rewrites-sources"),
    ("pytest --debug=/tmp/out tests/", "pytest-debug-writes"),
    ("mypy --install-types src", "mypy-install-types-invokes-pip"),
    ("mypy --cache-dir /tmp/c src", "mypy-cache-dir"),
    ("mypy @/tmp/flags.txt src", "mypy-response-file"),
    ("ruff check @/tmp/flags.txt", "ruff-response-file"),
    ("pytest @/tmp/flags.txt", "pytest-response-file"),
    # ROUND 4: the property the inversion buys - a flag nobody has ever enumerated.
    ("ruff check --totally-new-writer=x src/", "invented-flag-refused-by-default"),
    ("pytest --some-future-writer=/tmp/x tests/", "invented-pytest-flag"),
    ("git status --some-future-writer", "invented-git-flag"),
    ("find . -somefutureaction /tmp/x", "invented-find-primary"),
    # `--` would add a second parsing mode; refused everywhere, by decision.
    ("git log -- src/x.py", "double-dash-separator"),
    # Verb matching must name a PROGRAM, not a word.
    ("/tmp/evil/cat README.md", "path-bearing-inert-verb"),
    ("./shellcheck install.sh", "relative-path-bearing-verb"),
    ("/tmp/evil/ruff check src/", "path-bearing-gated-verb"),
    # ROUND 5 MAJOR: the path check used to sit BELOW the interpreter dispatch, so the
    # python branch returned first and an arbitrary binary named `python3` ran with an
    # argv of the caller's choosing. Resolving the SCRIPT is not resolving the INTERPRETER.
    ("/tmp/evil/python3 .claude/operations/scripts/execute-json-ops.py p.ops.json",
     "path-bearing-interpreter-ops"),
    ("./python3 -m pytest tests/ -q", "relative-path-bearing-interpreter"),
    # Positionals may not escape the project root.
    ("cat ../../../etc/passwd", "positional-dotdot-escape"),
    ("cat /etc/passwd", "positional-absolute-outside-root"),
    # The ops engine's own authorization bypass flag needs a human, per implement.md.
    ("python3 .claude/operations/scripts/execute-json-ops.py p.ops.json --no-approval",
     "ops-no-approval-flag"),
    # Verbs deliberately removed from the inert class for smallest surface.
    ("file -C -m evil", "file-writes-mgc"),
    ("diff a b", "diff-removed-from-inert-class"),
    ("python3 .claude/hooks/reflection.py evil --x", "reflection-unknown-verb"),
    ("ck install", "ck-write-subcommand"),
    ("npm test", "unlisted-verb"),
]


# --------------------------------------------------------------------------- helpers

def payload(command, agent_type="implementer", tool_name="Bash", drop_command=False):
    event = {"hook_event_name": "PreToolUse", "session_id": "s-iron-0001",
             "cwd": str(REPO), "permission_mode": "default"}
    if tool_name is not None:
        event["tool_name"] = tool_name
    if agent_type is not None:
        event["agent_type"] = agent_type
    event["tool_input"] = {} if drop_command else {"command": command}
    return json.dumps(event)


def run(body, tmp_path, profile="standard", hook=None, **extra):
    env = dict(os.environ,
               CLAUDEKIT_HOOK_LOG=str(tmp_path / "hooks.log"),
               CLAUDE_PROJECT_DIR=str(REPO),
               ECC_HOOK_PROFILE=profile)
    env.pop("CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS", None)
    env.update(extra)
    return subprocess.run([sys.executable, str(hook or HOOK)], input=body,
                          capture_output=True, text=True, env=env, timeout=60)


# --------------------------------------------------------------- the hook must exist

def test_hook_exists_and_is_a_python_hook():
    assert HOOK.is_file(), "the Iron Law gate is not installed"
    first = HOOK.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("#!"), (
        "install.sh chmods +x by shebang, not by extension - without one the installed "
        "hook is not executable")


def test_hook_is_wired_on_pretooluse_bash():
    text = SETTINGS.read_text(encoding="utf-8")
    config = json.loads(text)
    entries = [e for e in config["hooks"]["PreToolUse"] if e.get("matcher") == "Bash"]
    wired = [h for e in entries for h in e.get("hooks", [])
             if "iron-law-gate.py" in h.get("command", "")]
    if not wired:
        # PreToolUse now routes through dispatch.sh, so "wired" means "in the
        # dispatch registry for this event, with a matcher that includes Bash".
        # The assertion is not weakened: a hook missing from BOTH places still
        # never fires, and that is still a failure.
        dispatched = [h for e in config["hooks"]["PreToolUse"] for h in e.get("hooks", [])
                      if "dispatch.sh" in h.get("command", "")]
        assert dispatched, (
            "iron-law-gate.py is not wired on PreToolUse/Bash and PreToolUse does "
            "not route through dispatch.sh either - it would never fire")
        registry = json.loads(
            (SETTINGS.parent / "hooks" / "dispatch-registry.json").read_text(encoding="utf-8"))
        wired = [row for row in registry["events"].get("PreToolUse", [])
                 if row["file"] == "iron-law-gate.py"
                 and "Bash" in (row.get("matcher") or "").split("|")]
    assert wired, "iron-law-gate.py is not wired on PreToolUse/Bash - it would never fire"


# ------------------------------------------------------- the sanctioned loop must run

@pytest.mark.parametrize("command", SANCTIONED)
def test_sanctioned_implementer_loop_is_never_blocked(command, tmp_path):
    """If this fails, /implement is dead: the ops engine is reached THROUGH Bash."""
    proc = run(payload(command), tmp_path)
    assert proc.returncode == 0, (
        "the implementer's own documented command was blocked, which leaves it with no "
        "possible action:\n%s\n%s" % (command, proc.stderr))


# -------------------------------------------------------------- write vectors blocked

@pytest.mark.parametrize("command,label", BLOCKED, ids=[b[1] for b in BLOCKED])
def test_write_vector_is_blocked(command, label, tmp_path):
    proc = run(payload(command), tmp_path)
    assert proc.returncode == 2, "not blocked: %s" % command
    assert "IRON LAW" in proc.stderr, "block gave no actionable reason: %r" % proc.stderr
    assert proc.stdout == "", "a PreToolUse decision must never travel on stdout"


def test_every_blocked_command_is_bound_to_the_guard(tmp_path):
    """Mutation check: neuter the decision and EVERY blocked case must flip to exit 0.

    Without this, a test could pass because of an unrelated early return. The mutant is a
    COPY in tmp_path - the real tree is never modified (same discipline as
    tests/test_install.py).
    """
    source = HOOK.read_text(encoding="utf-8")
    needle = '''def decide(command: str, root: Path) -> Tuple[bool, str]:'''
    assert source.count(needle) == 1, "decide() signature moved; update this mutant"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(source.replace(needle, needle + "\n    return True, ''  # MUTANT"),
                      encoding="utf-8")
    unbound = []
    for command, label in BLOCKED:
        proc = run(payload(command), tmp_path, hook=mutant)
        if proc.returncode != 0:
            unbound.append((label, proc.returncode))
    assert not unbound, (
        "these cases still blocked with the guard removed, so they do not test it: %s"
        % unbound)


# A surgical mutant per guard: (label_to_flip, source_find, source_replace, collateral).
#
# `collateral` is the set of OTHER blocked labels that this mutant legitimately also
# unblocks, because they share the guard being disabled. It is DECLARED, and the test
# asserts the flipped set is EXACTLY {target} | collateral - nothing more, nothing less.
#
# The earlier version asserted only that the target flipped, which does not establish
# "each mutant disables exactly one thing"; that claim was made and was false for the
# path-bearing mutant, which also unblocks three sibling cases. Declaring collateral is
# the honest form: it still pins each case to its own guard, and it makes the blast radius
# of every guard visible instead of asserted.
# The wholesale mutant below proves only that a case depends on `decide()` AT ALL - it
# cannot tell whether `git -C /tmp status` is caught by a `-C` rule or by the generic
# global-option branch. These pin each high-value case to THE SPECIFIC TABLE that is
# supposed to catch it, which is the only form that catches a vacuous assertion.
TARGETED_MUTANTS = [
    # (target_label, source_find, source_replace, collateral_labels)
    ("cat-redirect", "_METACHARACTERS = (",
     "_METACHARACTERS = ()\n_DISABLED_METACHARACTERS = (",
     ("cat-append", "heredoc", "and-chain", "or-chain", "pipe-to-tee",
      "newline-second-command")),
    ("pipe-to-tee", "_METACHARACTERS = (",
     "_METACHARACTERS = ()\n_DISABLED_METACHARACTERS = (",
     ("cat-redirect", "cat-append", "heredoc", "and-chain", "or-chain",
      "newline-second-command")),
    ("pytest-log-file", "_PYTEST_SAFE = frozenset({",
     '_PYTEST_SAFE = frozenset({"--log-file", "--log-file-level",',
     ("pytest-log-file-detached",)),
    # Flag-only form, so this pins _GIT_LIST_SAFE and nothing else. `git branch -D x` is
    # bound to TWO guards (the flag list AND the positional rule), which would make it a
    # poor surgical target - the positional mutant below covers that half.
    ("git-branch-delete-flagonly", "_GIT_LIST_SAFE = frozenset({",
     '_GIT_LIST_SAFE = frozenset({"-D",', ()),
    ("git-remote-add", '            if not token.startswith("-") and not listing:',
     "            if False:",
     ("git-branch-create-positional", "git-remote-set-url", "git-remote-prune")),
    ("find-delete", "_FIND_SAFE = frozenset({",
     '_FIND_SAFE = frozenset({"-delete",', ()),
    # D5f. Its blast radius covers the two INTERPRETER cases as well, which is the
    # round-5 MAJOR: the path check had to move ABOVE the _PYTHON_HEADS dispatch for
    # those two to be bound to it at all.
    ("path-bearing-inert-verb", 'if "/" in tokens[0] or "\\\\" in tokens[0]:',
     "if False:",
     ("relative-path-bearing-verb", "path-bearing-gated-verb",
      "path-bearing-interpreter-ops", "relative-path-bearing-interpreter")),
    # THE INVERSION ITSELF: turn default-deny back into allow-any-flag. Its blast radius
    # is deliberately wide - that width IS the value of the architecture, measured rather
    # than asserted. The cases it does NOT flip are held by the positional path rule.
    ("invented-flag-refused-by-default", "            if bare not in safe_flags:",
     "            if False:",
     ("git-diff-output", "find-delete", "ruff-fix", "pytest-plugin-injection",
      "pytest-log-file", "pytest-log-file-detached", "pytest-ini-override",
      "pytest-override-ini-long", "git-branch-delete-flagonly",
      "ruff-add-noqa-rewrites-sources", "pytest-debug-writes",
      "mypy-install-types-invokes-pip", "invented-pytest-flag", "invented-git-flag",
      "ops-no-approval-flag")),
]


@pytest.mark.parametrize("label,find,replace,collateral", TARGETED_MUTANTS,
                         ids=[m[0] for m in TARGETED_MUTANTS])
def test_blocked_case_is_bound_to_its_own_guard(label, find, replace, collateral, tmp_path):
    """Disable ONE guard; the set of cases that unblock must be EXACTLY the declared set.

    Both halves matter. "Target flips" proves the case tests that guard. "Nothing else
    flips beyond the declared collateral" proves the guard is scoped - and is the half
    the previous revision claimed without testing.
    """
    source = HOOK.read_text(encoding="utf-8")
    assert source.count(find) == 1, "mutant anchor %r moved" % find
    mutant = tmp_path / ("mutant_%s.py" % label.replace("-", "_"))
    mutant.write_text(source.replace(find, replace), encoding="utf-8")
    flipped = set()
    for command, other in BLOCKED:
        if run(payload(command), tmp_path, hook=mutant).returncode == 0:
            flipped.add(other)
    expected = {label} | set(collateral)
    assert label in flipped, (
        "%r still blocked with its own guard disabled, so the assertion does not test "
        "that guard" % label)
    assert flipped == expected, (
        "mutant blast radius is not what is declared.\n  unexpected: %s\n  missing: %s"
        % (sorted(flipped - expected), sorted(expected - flipped)))


@pytest.mark.parametrize("command", DOD_COMMANDS)
def test_dod_command_is_permitted(command, tmp_path):
    """All six of CLAUDE.md's mandatory gates must survive the default-deny inversion.

    Tightening flags is only safe if the commands the project actually REQUIRES still
    pass; otherwise the gate silently makes a green DoD unreachable.
    """
    proc = run(payload(command), tmp_path)
    assert proc.returncode == 0, "DoD gate blocked: %s\n%s" % (command, proc.stderr)


def test_invented_flag_is_refused_without_being_enumerated(tmp_path):
    """The property the inversion buys, and the one thing a denylist could never have.

    Nobody has enumerated `--totally-new-writer` anywhere in this repo. Under the old
    flag-denylist design it would have been ALLOWED, exactly as `--log-file` and
    `--add-noqa` were, in three consecutive review rounds.
    """
    source = HOOK.read_text(encoding="utf-8")
    assert "totally-new-writer" not in source, (
        "the invented flag leaked into the hook, which would make this test circular")
    proc = run(payload("ruff check --totally-new-writer=x src/"), tmp_path)
    assert proc.returncode == 2
    assert "DEFAULT-DENY" in proc.stderr, (
        "the refusal must say WHY, or the implementer will retry variations of it")


def test_no_flag_denylist_survives_in_the_hook(tmp_path):
    """Structural: the v1 denylists must be DELETED, not merely bypassed.

    Leaving them in place would falsely signal that the dangerous set is known - the
    exact claim three review rounds falsified.
    """
    source = HOOK.read_text(encoding="utf-8")
    for dead in ("_PYTEST_WRITE_FLAGS", "_RUFF_WRITE_FLAGS", "_MYPY_WRITE_FLAGS",
                 "_FIND_WRITE_FLAGS", "_GIT_OUTPUT_FLAGS", "_decide_flag_guard"):
        assert dead not in source, "%s is a v1 flag denylist and must be deleted" % dead


# ------------------------------------------------------------------ agent scoping

@pytest.mark.parametrize("agent_type", [None, "planner", "reviewer", "verifier",
                                        "explore", "gitOps", "general-purpose"])
def test_other_agents_and_the_main_agent_pass_through(agent_type, tmp_path):
    """The hook must be invisible to everyone but the implementer.

    `agent_type=None` is the MAIN agent: Claude Code 2.1.237 builds the payload with
    `agent_type: n?.agentType ?? Z$()`, and `Z$()` (mainThreadAgentType) is undefined
    unless the session was started with --agent, so the key is simply absent.
    """
    proc = run(payload("sed -i 's/a/b/' src/x.py", agent_type=agent_type), tmp_path)
    assert proc.returncode == 0, (
        "the hook blocked a non-implementer caller (%r) - out of remit and catastrophic "
        "for the main agent:\n%s" % (agent_type, proc.stderr))
    assert proc.stderr == ""


def test_agent_type_match_is_case_insensitive(tmp_path):
    proc = run(payload("rm -rf src", agent_type="Implementer"), tmp_path)
    assert proc.returncode == 2


def test_non_bash_tool_passes_through(tmp_path):
    proc = run(payload("rm -rf src", tool_name="Read"), tmp_path)
    assert proc.returncode == 0


# -------------------------------------------------------------- fail open / fail closed

def test_unparsable_payload_fails_open(tmp_path):
    """Deliberate: we cannot tell WHOSE command this is.

    Failing closed here would deny every Bash call the main agent makes. No coverage is
    lost - reflection-gate.py is wired on the same event with matcher "" and already
    fails CLOSED on an unparsable PreToolUse payload, so the chain still denies.
    """
    proc = run("{not json at all", tmp_path)
    assert proc.returncode == 0, proc.stderr
    log = (tmp_path / "hooks.log").read_text(encoding="utf-8")
    assert "unparsable" in log, "a fail-open decision must be logged, not silent"


def test_implementer_with_unreadable_command_fails_closed(tmp_path):
    """The opposite unknown: we KNOW it is the implementer and cannot see the command."""
    proc = run(payload(None, drop_command=True), tmp_path)
    assert proc.returncode == 2
    assert "IRON LAW" in proc.stderr


def test_non_dict_payload_fails_open(tmp_path):
    proc = run("[1, 2, 3]", tmp_path)
    assert proc.returncode == 0


# ------------------------------------------------------- the gate must not leak secrets

SECRET = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"


@pytest.mark.parametrize("profile", ["standard", "minimal"])
def test_blocked_secret_value_never_reaches_the_log(profile, tmp_path):
    """A gate that records the secrets it blocks is worse than the bypass it prevents.

    `emit()` writes on BOTH profiles, so both are checked. Only the variable NAME may
    survive; the value must not, in the log OR in the stderr shown to the model.
    """
    command = ("AWS_SECRET_ACCESS_KEY=%s python3 "
               ".claude/operations/scripts/execute-json-ops.py p.ops.json" % SECRET)
    proc = run(payload(command), tmp_path, profile=profile)
    log = (tmp_path / "hooks.log").read_text(encoding="utf-8")
    assert SECRET not in log, "the blocked secret VALUE was written to hooks.log"
    assert SECRET not in proc.stderr, "the blocked secret VALUE was echoed to stderr"
    assert "AWS_SECRET_ACCESS_KEY" in (log + proc.stderr), (
        "redaction went too far - the variable NAME is what makes the block actionable")


@pytest.mark.parametrize("command,leak", [
    ("deploytool --token=%s x" % SECRET, SECRET),
    ("deploytool --password %s x" % SECRET, SECRET),
    ("deploytool https://user:%s@host/x" % SECRET, SECRET),
])
def test_secret_shapes_are_redacted_from_stderr(command, leak, tmp_path):
    """`redact()` v1 only handled `NAME=value`, so these three survived into stderr - which
    is persisted in the transcript. `reflection.looks_like_credential()` already existed
    and was unused; it is now the detector for the bare/embedded shapes."""
    proc = run(payload(command), tmp_path)
    assert leak not in proc.stderr, "secret survived into the message shown to the model"
    assert leak not in (tmp_path / "hooks.log").read_text(encoding="utf-8")


def test_absolute_host_paths_are_digested_in_the_log(tmp_path):
    """The positional refusal is where a FULL path is the interpolated value.

    The previous case (`/Users/x/tooling/evilbin --go`) was near-vacuous: the only
    interpolation was `safe(head)`, and `head` is already the basename, so the absolute
    path could not have reached the log even with `safe()` deleted. Here `safe(token)`
    is genuinely load-bearing - `_mutant_without_safe` below proves it.
    """
    proc = run(payload("cat /Users/someone/private/secrets.txt"), tmp_path)
    assert proc.returncode == 2
    log = (tmp_path / "hooks.log").read_text(encoding="utf-8")
    assert "/Users/someone/private" not in log
    assert "digest-" in log, "the refused path must be digested, not merely truncated"


def test_absolute_path_digest_is_bound_to_safe(tmp_path):
    """Mutant: neuter safe() and the host path must reach the log."""
    source = HOOK.read_text(encoding="utf-8")
    needle = "def safe(value: str, fallback: str = \"unknown\") -> str:"
    assert source.count(needle) == 1, "safe() signature moved; update this mutant"
    mutant = tmp_path / "mutant_safe.py"
    mutant.write_text(source.replace(needle, needle + "\n    return str(value)  # MUTANT"),
                      encoding="utf-8")
    run(payload("cat /Users/someone/private/secrets.txt"), tmp_path, hook=mutant)
    log = (tmp_path / "hooks.log").read_text(encoding="utf-8")
    assert "/Users/someone/private" in log, (
        "the host path never reached the log even with safe() removed, so the assertion "
        "in the test above does not test safe()")


# ------------------------------------------------------------------------- profiles

def test_minimal_profile_suppresses_blocking(tmp_path):
    proc = run(payload("sed -i 's/a/b/' src/x.py"), tmp_path, profile="minimal")
    assert proc.returncode == 0
    assert proc.stderr == ""


def test_minimal_profile_still_records_the_decision(tmp_path):
    """DELIBERATE DIVERGENCE from ops-enforcement.sh's wholesale short-circuit.

    This repo develops with ECC_HOOK_PROFILE=minimal, so a wholesale `exit 0` would give
    ZERO dogfood signal about whether the allowlist is too tight - the problem Decision 21
    addressed. Recording under minimal is what makes that measurable.
    """
    run(payload("sed -i 's/a/b/' src/x.py"), tmp_path, profile="minimal")
    log = (tmp_path / "hooks.log").read_text(encoding="utf-8")
    assert "WOULD-BLOCK" in log
    assert "head=sed" in log


@pytest.mark.parametrize("profile", ["standard", "strict"])
def test_blocking_profiles_block(profile, tmp_path):
    proc = run(payload("rm -rf src"), tmp_path, profile=profile)
    assert proc.returncode == 2


# ------------------------------------------------------------------ extension point

def test_extra_verbs_env_widens_the_allowlist(tmp_path):
    blocked = run(payload("npm test"), tmp_path)
    assert blocked.returncode == 2
    allowed = run(payload("npm test"), tmp_path,
                  CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS="npm:go")
    assert allowed.returncode == 0


def test_extra_verbs_rejects_path_bearing_entries(tmp_path):
    proc = run(payload("/tmp/evil/npm test"), tmp_path,
               CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS="/tmp/evil/npm")
    assert proc.returncode == 2


def test_extra_verbs_get_no_safe_flags(tmp_path):
    """An env var must not be able to grant more than a built-in verb gets."""
    assert run(payload("npm test"), tmp_path,
               CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS="npm").returncode == 0
    assert run(payload("npm test --logfile=/tmp/x"), tmp_path,
               CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS="npm").returncode == 2


def test_allowlisted_verb_given_as_a_path_is_blocked(tmp_path):
    """`test_extra_verbs_rejects_path_bearing_entries` does NOT cover this: it exercises a
    non-allowlisted basename. This is an ALLOWLISTED basename at an attacker path."""
    for command in ("/tmp/evil/cat README.md", "./shellcheck install.sh",
                    "/tmp/evil/ruff check src/"):
        proc = run(payload(command), tmp_path)
        assert proc.returncode == 2, command


# ------------------------------------------------------------- anti-laundering checks

def test_symlinked_ops_script_is_not_laundered(tmp_path):
    """Resolving the FULL path would let a symlink named execute-json-ops.py stand in for
    an arbitrary script. Only the PARENT is resolved (same control as
    reflection-gate.is_receipt_inbox_write)."""
    fake = tmp_path / "execute-json-ops.py"
    fake.symlink_to(sys.executable)
    proc = run(payload("python3 %s x.ops.json" % fake), tmp_path)
    assert proc.returncode == 2


def test_ops_script_basename_outside_the_engine_directory_is_blocked(tmp_path):
    decoy = tmp_path / "execute-json-ops.py"
    decoy.write_text("import os\n", encoding="utf-8")
    proc = run(payload("python3 %s" % decoy), tmp_path)
    assert proc.returncode == 2, "matched on basename instead of resolved directory"


def test_prefix_match_does_not_satisfy_the_allowlist(tmp_path):
    """`git diff` must not be satisfied by `git diff --output=x`."""
    assert run(payload("git diff"), tmp_path).returncode == 0
    assert run(payload("git diff --output=/tmp/x"), tmp_path).returncode == 2

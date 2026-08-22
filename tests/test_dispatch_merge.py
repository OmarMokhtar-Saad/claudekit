"""Behavioural proofs for the hook dispatcher: precedence, fail-closed, advisory.

Every test here runs the SHIPPED `.claude/hooks/dispatch.sh` as a subprocess
against a temporary registry of real handler scripts, and asserts on the process
exit code — the only thing Claude Code actually observes. No structural
assertions: "the file contains the word DENY" would pass against every mutant
this file exists to catch.

Each of the three contract proofs is paired with a MUTANT test that copies the
shipped artifact, applies one targeted mutation, and asserts the outcome
CHANGES. A gate that passes against a mutant is worse than no gate — that has
shipped twice in this repo, caught only by executing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(REPO_ROOT, ".claude", "hooks")
DISPATCH = os.path.join(HOOKS_DIR, "dispatch.sh")
LIB = os.path.join(HOOKS_DIR, "lib.sh")
REGISTRY = os.path.join(HOOKS_DIR, "dispatch-registry.json")

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from claudekit.enforcement import decisions  # noqa: E402

PAYLOAD = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}})


# ---------------------------------------------------------------- helpers ----

def _handler(directory, name, exit_code, stderr="", stdout=""):
    """Write a real handler script that exits with `exit_code`."""
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env bash\ncat >/dev/null\n")
        if stdout:
            fh.write("printf '%%s\\n' %s\n" % json.dumps(stdout))
        if stderr:
            fh.write("printf '%%s\\n' %s >&2\n" % json.dumps(stderr))
        fh.write("exit %d\n" % exit_code)
    os.chmod(path, 0o755)
    return name


def _sandbox(tmp_path, dispatch_src=DISPATCH, lib_src=LIB):
    """A hooks dir holding the shipped dispatcher and lib (or a mutant of either).

    `dispatch_resolve.py` must come too. The dispatcher invokes it as
    `python3 "$SCRIPT_DIR/dispatch_resolve.py"`, so a sandbox without it resolves no
    handlers and every blocking event exits 2 — which is the correct fail-closed
    behaviour, and is exactly how 21 tests here failed when the resolver was first
    extracted from the heredoc. Whatever ships beside the dispatcher has to be
    sandboxed beside it.
    """
    directory = str(tmp_path)
    shutil.copy(dispatch_src, os.path.join(directory, "dispatch.sh"))
    shutil.copy(lib_src, os.path.join(directory, "lib.sh"))
    shutil.copy(os.path.join(HOOKS_DIR, "dispatch_resolve.py"),
                os.path.join(directory, "dispatch_resolve.py"))
    return directory


def _registry(directory, rows, event="PreToolUse"):
    """Write the registry the dispatcher will read. Called after the handlers exist."""
    doc = {"schema_version": 1, "blocking_events": ["PreToolUse"],
           "events": {event: rows}}
    with open(os.path.join(directory, "dispatch-registry.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def _run(directory, event="PreToolUse", payload=PAYLOAD, env=None, timeout=None,
         raw_argv=None):
    """`raw_argv` replaces the argv tail, so a probe can pass no event at all."""
    environ = dict(os.environ)
    environ["ECC_HOOK_PROFILE"] = "standard"
    environ["CLAUDEKIT_SESSION_ID"] = "pytest-dispatch"
    environ.setdefault("CLAUDE_PROJECT_DIR", REPO_ROOT)
    if env:
        environ.update(env)
    argv = ["bash", os.path.join(directory, "dispatch.sh")]
    argv.extend([event] if raw_argv is None else raw_argv)
    return subprocess.run(
        argv,
        input=payload, capture_output=True, text=True, env=environ, cwd=directory,
        timeout=timeout,
    )


def _row(hid, file, tier, matcher=""):
    return {"id": hid, "file": file, "runner": "bash", "tier": tier, "matcher": matcher}


# ------------------------------------------- PROOF 1: most restrictive wins --

@pytest.mark.parametrize("order", [("allower", "denier"), ("denier", "allower")])
def test_most_restrictive_wins_regardless_of_order(tmp_path, order):
    """Two blocking handlers disagree on one event -> DENY, in EITHER order.

    The parametrisation is the substance: if the outcome depended on
    registration order (the pre-dispatcher behaviour), exactly one of these two
    cases would return 0.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "allower.sh", 0)
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: denier says no")
    _registry(directory, [_row(name, name + ".sh", "blocking") for name in order])

    result = _run(directory)
    assert result.returncode == 2, (
        "most-restrictive-wins violated for order %r: rc=%s stderr=%s"
        % (order, result.returncode, result.stderr))
    assert "denier says no" in result.stderr


def test_reversed_precedence_mutant_stops_blocking(tmp_path):
    """MUTANT: flip the merge comparison in dispatch.sh; the block must vanish.

    This is what makes the test above non-vacuous. If this mutant still returned
    2, the assertion in test_most_restrictive_wins_regardless_of_order would be
    proving nothing.
    """
    source = open(DISPATCH, encoding="utf-8").read()
    mutated = source.replace(
        'if [ "$DECISION" -gt "$MERGED" ]; then MERGED="$DECISION"; fi',
        'if [ "$DECISION" -lt "$MERGED" ]; then MERGED="$DECISION"; fi')
    assert mutated != source, "mutation anchor not found -- update this test"
    mutant_path = os.path.join(str(tmp_path), "mutant-dispatch.sh")
    with open(mutant_path, "w", encoding="utf-8") as fh:
        fh.write(mutated)

    directory = _sandbox(tmp_path, dispatch_src=mutant_path)
    _handler(directory, "allower.sh", 0)
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: denier says no")
    _registry(directory, [_row("allower", "allower.sh", "blocking"),
                          _row("denier", "denier.sh", "blocking")])

    result = _run(directory)
    assert result.returncode == 0, (
        "the reversed-precedence mutant still blocked -- the precedence test is "
        "not actually binding on this code path")


# ------------------------------------------------- PROOF 2: fail closed ------

@pytest.mark.parametrize("exit_code", [1, 3, 42, 124, 127])
def test_crashing_handler_fails_closed(tmp_path, exit_code):
    """A blocking handler that exits anything but 0 or 2 BLOCKS, never passes.

    Re-measured baseline at 5f3e322, in a clean environment so the outer shell's
    interpreter lookup cannot be read as the hook's exit code::

        $ echo '' | env -i PATH=/nonexistent /bin/bash ops-enforcement.sh; echo $?
        0

    0 is ALLOW, so the guarded edit proceeded -- a stronger fact than the 127 an
    earlier measurement reported (that 127 was `bash` itself not being found, so
    the hook had never run). Under the dispatcher the same environment yields an
    OBSERVABLE 127, because the handler process cannot start, which is why 127 is
    in this parametrisation.

    These exit codes are PRE-COOKED by the handler: this test proves the codec,
    not a timeout. There is no per-handler timeout -- see dispatch.sh's own
    "WHAT THIS DOES NOT DO" note; 124 here is only a handler reporting one.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "crasher.sh", exit_code, stderr="boom")
    _registry(directory, [_row("crasher", "crasher.sh", "blocking")])
    result = _run(directory)
    assert result.returncode == 2, (
        "handler exiting %d failed OPEN (rc=%s)" % (exit_code, result.returncode))


def test_missing_handler_fails_closed(tmp_path):
    """A registered handler whose file is gone is an unknown verdict, not an allow."""
    directory = _sandbox(tmp_path)
    _registry(directory, [_row("ghost", "ghost.sh", "blocking")])
    result = _run(directory)
    assert result.returncode == 2
    assert "verdict is unknown" in result.stderr or "ghost" in result.stderr


def test_unreadable_registry_fails_closed(tmp_path):
    """No registry means we cannot know which guards should have run -> block."""
    directory = _sandbox(tmp_path)
    _registry(directory, [])
    os.remove(os.path.join(directory, "dispatch-registry.json"))
    result = _run(directory)
    assert result.returncode == 2
    assert "registry unreadable" in result.stderr


def test_fail_open_mutant_lets_the_crash_through(tmp_path):
    """MUTANT: make the codec's catch-all return ALLOW; the crash must pass."""
    source = open(LIB, encoding="utf-8").read()
    mutated = source.replace("        *) printf '2' ;;\n    esac\n}",
                             "        *) printf '0' ;;\n    esac\n}", 1)
    assert mutated != source, "mutation anchor not found -- update this test"
    mutant_lib = os.path.join(str(tmp_path), "mutant-lib.sh")
    with open(mutant_lib, "w", encoding="utf-8") as fh:
        fh.write(mutated)
    directory = _sandbox(tmp_path, lib_src=mutant_lib)
    _handler(directory, "crasher.sh", 127, stderr="boom")
    _registry(directory, [_row("crasher", "crasher.sh", "blocking")])
    result = _run(directory)
    assert result.returncode == 0, (
        "the fail-open mutant still blocked -- the fail-closed tests are not binding")


# ------------------------------------------ PROOF 3: advisory cannot block ---

def test_advisory_cannot_override_a_block(tmp_path):
    """An advisory handler exiting 0 next to a blocking handler exiting 2 -> DENY."""
    directory = _sandbox(tmp_path)
    _handler(directory, "chatty.sh", 0, stdout="looks fine to me")
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: real guard says no")
    _registry(directory, [_row("chatty", "chatty.sh", "advisory"),
                          _row("denier", "denier.sh", "blocking")])
    result = _run(directory)
    assert result.returncode == 2
    assert "real guard says no" in result.stderr
    assert "looks fine to me" in result.stdout, (
        "advisory output must still surface -- it is suppressed as a DECISION, "
        "not as information")


def test_advisory_cannot_create_a_block(tmp_path):
    """An advisory handler exiting 2, or crashing, is clamped to ADVISE.

    A flaky advisory hook must not be able to brick a session. This is the other
    half of the clamp, and the half that is easy to forget.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "shouty.sh", 2, stderr="I would like to block")
    _handler(directory, "broken.sh", 127, stderr="I crashed")
    _registry(directory, [_row("shouty", "shouty.sh", "advisory"),
                          _row("broken", "broken.sh", "advisory")])
    result = _run(directory)
    assert result.returncode == 0, (
        "an advisory handler created a block (rc=%s)" % result.returncode)


def test_unclamped_advisory_mutant_creates_a_block(tmp_path):
    """MUTANT: remove the clamp; the advisory handler must then block."""
    source = open(LIB, encoding="utf-8").read()
    mutated = source.replace(
        'if [ "$tier" = "advisory" ] && [ "$decision" -gt 1 ]; then',
        'if [ "$tier" = "never-matches" ] && [ "$decision" -gt 1 ]; then', 1)
    assert mutated != source, "mutation anchor not found -- update this test"
    mutant_lib = os.path.join(str(tmp_path), "mutant-lib.sh")
    with open(mutant_lib, "w", encoding="utf-8") as fh:
        fh.write(mutated)
    directory = _sandbox(tmp_path, lib_src=mutant_lib)
    _handler(directory, "shouty.sh", 2, stderr="I would like to block")
    _registry(directory, [_row("shouty", "shouty.sh", "advisory")])
    result = _run(directory)
    assert result.returncode == 2, (
        "the unclamped mutant did not block -- the clamp tests are not binding")


# ----------------------------------------- codec parity and registry honesty --

@pytest.mark.parametrize("code", [0, 1, 2, 3, 42, 124, 126, 127, 255])
def test_shell_and_python_codecs_agree(code):
    """The bash table in lib.sh and decisions.py must decode identically.

    Two implementations of one rule is a drift hazard; this is the gate that
    makes it a caught one.
    """
    shell = subprocess.run(
        ["bash", "-c", '. "$1"; ck_decision_from_exit "$2"', "_", LIB, str(code)],
        capture_output=True, text=True)
    assert shell.returncode == 0, shell.stderr
    assert int(shell.stdout.strip()) == int(decisions.from_exit_code(code)), (
        "codec drift on exit %d: shell=%r python=%r"
        % (code, shell.stdout, decisions.from_exit_code(code)))


@pytest.mark.parametrize("tier", ["blocking", "advisory", "on", "", "bogus"])
@pytest.mark.parametrize("value", [0, 1, 2, 3])
def test_shell_and_python_clamps_agree(tier, value):
    """The clamp must agree across BOTH implementations, on the REAL vocabulary.

    `dispatch-registry.json` writes `blocking` / `advisory`; `profile.json`
    writes `on` / `advisory`. An earlier draft parametrised only `["on",
    "advisory"]` and then mapped the tier through an identity function before
    handing it to the shell -- so `blocking`, the only value the shipped registry
    actually uses, was never tested on either side, and the Python clamp raising
    on it would not have been caught. `""` and `bogus` pin the fail-closed
    direction: an unrecognised tier does NOT clamp, because clamping is what
    disarms a guard.
    """
    shell = subprocess.run(
        ["bash", "-c", '. "$1"; ck_clamp_advisory "$2" "$3"', "_", LIB,
         str(value), tier],
        capture_output=True, text=True)
    assert shell.returncode == 0, shell.stderr
    assert int(shell.stdout.strip()) == int(decisions.clamp_advisory(value, tier)), (
        "clamp drift on tier=%r value=%r: shell=%r python=%r"
        % (tier, value, shell.stdout.strip(), decisions.clamp_advisory(value, tier)))


@pytest.mark.parametrize("tier", ["blocking", "on", "", "bogus"])
def test_only_the_word_advisory_disarms_a_handler(tmp_path, tier):
    """End-to-end: a DENY is only clamped away by the literal tier `advisory`.

    Drives the shipped dispatcher, so it binds the registry vocabulary to the
    live outcome rather than to the codec in isolation.

    This test is one half of the round-4 Critical. It already proved that `""`
    does NOT disarm a handler, while the registry invariant in the resolver was
    simultaneously ACCEPTING `{"tier": "", "command_matcher": ...}` as advisory
    -- so the two facts sat in the same suite, both green, and together they
    were a bypass. The connection is now asserted in one place:
    test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: guard says no")
    _registry(directory, [_row("denier", "denier.sh", tier)])
    assert _run(directory).returncode == 2, (
        "tier %r disarmed a blocking handler" % (tier,))


@pytest.mark.parametrize("value", [0, 1, 2, 3])
def test_shell_and_python_boundary_renderers_agree(value):
    """`ck_decision_exit` and `to_exit_code` must render identically.

    This only means anything because dispatch.sh CALLS `ck_decision_exit` at the
    render boundary; while the comparison was inlined there, this parity test was
    covering dead code.
    """
    shell = subprocess.run(
        ["bash", "-c", '. "$1"; ck_decision_exit "$2"', "_", LIB, str(value)],
        capture_output=True, text=True)
    assert shell.returncode == 0, shell.stderr
    assert int(shell.stdout.strip()) == decisions.to_exit_code(value)


def test_boundary_renderer_is_actually_called(tmp_path):
    """MUTANT: make `ck_decision_exit` always render 0; the block must vanish.

    If dispatch.sh went back to inlining `[ "$MERGED" -ge 2 ]`, this mutant would
    still block and the test would fail -- which is the point: it pins the CALL,
    not the function.
    """
    source = open(LIB, encoding="utf-8").read()
    mutated = source.replace(
        'ck_decision_exit() {\n    if [ "${1:-0}" -ge 2 ]; then printf \'2\'; else printf \'0\'; fi\n}',
        "ck_decision_exit() {\n    printf '0'\n}", 1)
    assert mutated != source, "mutation anchor not found -- update this test"
    mutant_lib = os.path.join(str(tmp_path), "mutant-lib.sh")
    with open(mutant_lib, "w", encoding="utf-8") as fh:
        fh.write(mutated)
    directory = _sandbox(tmp_path, lib_src=mutant_lib)
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: guard says no")
    _registry(directory, [_row("denier", "denier.sh", "blocking")])
    assert _run(directory).returncode == 0, (
        "dispatch.sh did not route its exit through ck_decision_exit -- the "
        "boundary parity test is covering dead code")


# --------------------------------- the dispatcher's OWN crash fails closed ---

def test_dispatcher_with_a_broken_path_fails_closed(tmp_path):
    """A broken PATH must make dispatch.sh exit 2, never pass the operation.

    This is THE headline defect, aimed at the dispatcher itself. Re-measured at
    5f3e322 against the guard this phase replaces, in a clean environment so the
    outer shell's interpreter lookup is not mistaken for the hook's exit code::

        $ echo '' | env -i PATH=/nonexistent /bin/bash ops-enforcement.sh; echo $?
        0

    0 is ALLOW, so Claude Code let the guarded edit through. (An earlier
    `PATH=/nonexistent bash ...` reading of 127 was `bash` not being found; the
    hook had not run.) A dispatcher that
    indicts other hooks for having no trap does not get to inherit the defect:
    with no external commands available, every path out of dispatch.sh -- the
    unreadable-lib.sh guard, an unset variable under `set -u`, the panic trap --
    must still render a block on a blocking event.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: guard says no")
    _registry(directory, [_row("denier", "denier.sh", "blocking")])
    environ = dict(os.environ)
    environ["PATH"] = "/nonexistent"
    environ["ECC_HOOK_PROFILE"] = "standard"
    # Resolve bash BEFORE breaking PATH -- otherwise subprocess cannot find the
    # interpreter either and we would be testing our own test harness.
    bash = shutil.which("bash") or "/bin/bash"
    result = subprocess.run(
        [bash, os.path.join(directory, "dispatch.sh"), "PreToolUse"],
        input=PAYLOAD, capture_output=True, text=True, env=environ, cwd=directory)
    assert result.returncode == 2, (
        "dispatch.sh failed OPEN with a broken PATH (rc=%s, stderr=%r)"
        % (result.returncode, result.stderr[-400:]))


def test_missing_lib_fails_closed(tmp_path):
    """lib.sh gone -> exit 2 on a blocking event, never a silent degrade.

    Sourcing lib.sh conditionally (`[ -f ... ] && . ...`) would make every `ck_*`
    call a command-not-found, the merge would degrade to ALLOW, and the
    dispatcher would become a fail-open no-op wearing a guard's name.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: guard says no")
    _registry(directory, [_row("denier", "denier.sh", "blocking")])
    os.remove(os.path.join(directory, "lib.sh"))
    result = _run(directory)
    assert result.returncode == 2, (
        "dispatch.sh ran without its decision codec and did not block (rc=%s)"
        % result.returncode)
    assert "lib.sh" in result.stderr


def test_panic_trap_blocks_on_an_abort(tmp_path):
    """An abort between entry and the render boundary must still exit 2.

    Injects a hard failure (an unset variable under `set -u`) after the trap is
    installed. Without the EXIT trap this returns 1, and 1 is not a block.
    """
    source = open(DISPATCH, encoding="utf-8").read()
    anchor = 'PAYLOAD=$(cat)'
    assert anchor in source, "injection anchor not found -- update this test"
    injected = source.replace(anchor, anchor + '\nprintf "%s" "$CK_DEFINITELY_UNSET"', 1)
    mutant_path = os.path.join(str(tmp_path), "aborting-dispatch.sh")
    with open(mutant_path, "w", encoding="utf-8") as fh:
        fh.write(injected)
    directory = _sandbox(tmp_path, dispatch_src=mutant_path)
    _registry(directory, [])
    result = _run(directory)
    assert result.returncode == 2, (
        "an aborted dispatch did not fail closed (rc=%s)" % result.returncode)
    assert result.returncode != 1, "exit 1 is not a block"


def test_panic_trap_does_not_block_a_non_blocking_event(tmp_path):
    """The same abort on `Stop` exits 0: fail-closed is scoped to guarded events."""
    source = open(DISPATCH, encoding="utf-8").read()
    injected = source.replace(
        'PAYLOAD=$(cat)', 'PAYLOAD=$(cat)\nprintf "%s" "$CK_DEFINITELY_UNSET"', 1)
    mutant_path = os.path.join(str(tmp_path), "aborting-dispatch.sh")
    with open(mutant_path, "w", encoding="utf-8") as fh:
        fh.write(injected)
    directory = _sandbox(tmp_path, dispatch_src=mutant_path)
    _registry(directory, [], event="Stop")
    assert _run(directory, event="Stop").returncode == 0


def test_registry_covers_every_settings_registration():
    """Every hook registered in settings.json appears in the dispatch registry.

    Without this, moving to a dispatcher could silently DROP a guard -- the
    quietest possible security regression.
    """
    settings = json.load(open(os.path.join(REPO_ROOT, ".claude", "settings.json")))
    registry = json.load(open(REGISTRY))
    for event, entries in settings.get("hooks", {}).items():
        if not isinstance(entries, list):
            continue          # a comment/annotation key, not an event
        registered = set()
        for entry in entries:
            for hook in entry.get("hooks", []):
                for name in re.findall(r"\.claude/hooks/([A-Za-z0-9._-]+)", hook["command"]):
                    registered.add(name)
        registered.discard("dispatch.sh")
        registered.discard("lib.sh")
        known = {row["file"] for row in registry["events"].get(event, [])}
        missing = registered - known
        assert not missing, "dispatch registry drops %s on %s" % (sorted(missing), event)

        # Once an event is routed THROUGH dispatch.sh, `registered` goes empty for
        # it and the check above becomes vacuous -- exactly when it matters most.
        # So for any event wired to the dispatcher, assert the registry is not
        # empty and every file it names is really on disk.
        routes_through_dispatch = any(
            "dispatch.sh" in hook["command"]
            for entry in entries for hook in entry.get("hooks", []))
        if routes_through_dispatch:
            rows = registry["events"].get(event, [])
            assert rows, "%s is routed through dispatch.sh with an EMPTY registry" % event
            for row in rows:
                assert os.path.exists(os.path.join(HOOKS_DIR, row["file"])), (
                    "%s on %s points at a handler that does not exist" % (row["file"], event))


def test_registry_handlers_all_exist():
    """No registry row may name a handler file that is not shipped."""
    registry = json.load(open(REGISTRY))
    for event, rows in registry["events"].items():
        for row in rows:
            assert os.path.exists(os.path.join(HOOKS_DIR, row["file"])), (
                "%s on %s is registered but not shipped" % (row["file"], event))


def test_registry_passes_reflection_gate_its_required_event_arg():
    """`reflection-gate.py` REQUIRES `--event`; a registry without args is unwirable.

    settings.json invokes it as `python3 reflection-gate.py --event <EventName>`
    on seven events. If the registry could not carry argv, routing those events
    through the dispatcher would call it with no `--event` -- so this pins the
    field against the shipped hook's own interface rather than against a table.
    """
    source = open(os.path.join(HOOKS_DIR, "reflection-gate.py"), encoding="utf-8").read()
    assert "--event" in source, "reflection-gate.py no longer takes --event; update the registry"
    registry = json.load(open(REGISTRY))
    for event, rows in registry["events"].items():
        for row in rows:
            if row["file"] != "reflection-gate.py":
                continue
            assert row.get("args") == ["--event", event], (
                "reflection-gate on %s is registered with args=%r" % (event, row.get("args")))


def test_registry_matches_the_command_conditions_settings_json_applies():
    """`pre-commit` / `pre-push` must keep their command guards through the rewire.

    settings.json runs them only when the Bash command matches `git commit` /
    `git push`. A dispatcher that dropped that condition would run a commit hook
    on every shell command -- a behaviour change smuggled in by a refactor.
    """
    registry = json.load(open(REGISTRY))
    rows = {row["id"]: row for row in registry["events"]["PreToolUse"]}
    assert rows["pre-commit"].get("command_matcher"), "pre-commit lost its command condition"
    assert rows["pre-push"].get("command_matcher"), "pre-push lost its command condition"
    for hid, sample_yes, sample_no in [
            ("pre-commit", "git commit -m x", "ls -la"),
            ("pre-push", "git push origin main", "ls -la")]:
        pattern = rows[hid]["command_matcher"]
        assert re.search(pattern, sample_yes), (hid, pattern, sample_yes)
        assert not re.search(pattern, sample_no), (hid, pattern, sample_no)


def test_handler_receives_its_registry_args(tmp_path):
    """argv from the registry reaches the handler process."""
    directory = _sandbox(tmp_path)
    path = os.path.join(directory, "argecho.sh")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('#!/usr/bin/env bash\ncat >/dev/null\nprintf "ARGS:%s\\n" "$*"\nexit 0\n')
    os.chmod(path, 0o755)
    row = _row("argecho", "argecho.sh", "advisory")
    row["args"] = ["--event", "PreToolUse"]
    _registry(directory, [row])
    result = _run(directory)
    assert "ARGS:--event PreToolUse" in result.stdout, result.stdout


def test_command_matcher_asymmetry_on_an_unreadable_payload(tmp_path):
    """No command_matcher -> RUNS on bad JSON. A command_matcher -> NOT APPLICABLE.

    The two rules are deliberately asymmetric, and both are fail-closed:

    * The tool-name matcher is a RELEVANCE FILTER. On an unreadable payload we
      cannot prove a guard irrelevant, so every guard without a precondition
      runs and decides for itself. That is why rc is still 2 below, and that
      direction is UNCHANGED.
    * A `command_matcher` is a PRECONDITION. With no command text it cannot be
      evaluated, and a precondition that cannot be evaluated is not satisfied,
      so the handler is NOT APPLICABLE and is skipped.

    Skipping it is not a bypass -- and that is ENFORCED, not argued. Only an
    `advisory` row may declare a command_matcher, so such a handler's verdict is
    clamped to ADVISE and could never have contributed a DENY; the resolver
    rejects any other row (see
    test_a_blocking_row_carrying_a_command_matcher_is_rejected_by_the_resolver).

    HISTORY, kept because this test used to assert the exact OPPOSITE and the
    opposite was wrong. Revision 2 shipped it as
    `test_command_matcher_filters_and_never_filters_on_a_broken_payload`, over a
    row that was tier `blocking` WITH a command_matcher, ending in
    `assert _run(payload="not json at all").returncode == 2, "a malformed payload
    filtered a guard OUT -- that is a bypass"`. Round-2 review executed that rule
    against the REAL registry and the dispatch never returned: `pre-push.sh:138`
    runs the full test suite and its precondition is "the user ran git push". So
    the old assertion defended a rule that ran a guard outside its contract and
    stalled the tool call -- a denial of service, not a guard. Round-3 review
    then found the inverted assertion still sitting in the tree, red
    (`assert 0 == 2`). It is reconciled here rather than deleted quietly: the
    bypass it was reaching for is real, and it is closed by the tier invariant
    instead of by running preconditions blind.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "precondition.sh", 0, stdout="PRECONDITION-GUARD-RAN")
    _handler(directory, "plain.sh", 0, stdout="PLAIN-GUARD-RAN")
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: unconditional guard says no")
    scoped = _row("precondition", "precondition.sh", "advisory", matcher="Bash")
    scoped["command_matcher"] = "^\\s*git\\s+commit"
    # NOTE: the two markers must not nest. An earlier draft used "CONDITIONAL RAN"
    # and "UNCONDITIONAL RAN"; the first is a SUBSTRING of the second, so the
    # skip assertion could never fail. Caught by executing, not by reading.
    _registry(directory, [
        scoped,
        _row("plain", "plain.sh", "advisory", matcher="Bash"),
        _row("denier", "denier.sh", "blocking", matcher="Bash"),
    ])

    matching = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
    other = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})

    # Readable and matching: the precondition holds, so the handler runs.
    hit = _run(directory, payload=matching)
    assert "PRECONDITION-GUARD-RAN" in hit.stdout, hit.stdout
    assert "PLAIN-GUARD-RAN" in hit.stdout, hit.stdout

    # Readable and not matching: the precondition is false, so it does not run.
    miss = _run(directory, payload=other)
    assert "PRECONDITION-GUARD-RAN" not in miss.stdout, miss.stdout
    assert "PLAIN-GUARD-RAN" in miss.stdout, miss.stdout

    # UNREADABLE: the asymmetry itself, which is what this test exists for.
    broken = _run(directory, payload="not json at all")
    assert "PRECONDITION-GUARD-RAN" not in broken.stdout, (
        "a handler whose precondition cannot be evaluated ran anyway -- that is "
        "the root cause of the round-2 hang, reintroduced")
    assert "PLAIN-GUARD-RAN" in broken.stdout, (
        "a malformed payload filtered OUT a guard that has NO precondition -- "
        "that IS a bypass, and this direction has not changed")
    assert broken.returncode == 2, (
        "fail-closed was lost on an unreadable payload: rc=%s stderr=%r"
        % (broken.returncode, broken.stderr))


def test_blocking_tier_is_honest():
    """A handler declared `blocking` must actually be able to reach exit 2.

    Derived from the shipped hook file, not asserted in a table, so a handler
    that loses its block does not keep a blocking label. `advisory` is not
    checked in this direction on purpose: a capable handler MAY be clamped down,
    and reflection-gate legitimately is on non-blocking events.

    The accepted evidence is deliberately narrow. An earlier draft also accepted
    a bare `"deny " in text`, which is worthless: `lib.sh` DEFINES `deny()`, so
    every shell hook that sources it matched, and so did a comment containing the
    word. What counts now is a literal `exit 2` / `exit(2)`, or a line whose
    first token is a `deny` CALL -- i.e. the hook can actually reach the only
    exit code Claude Code honours as a block.
    """
    registry = json.load(open(REGISTRY))
    for event, rows in registry["events"].items():
        for row in rows:
            if row["tier"] != "blocking":
                continue
            text = open(os.path.join(HOOKS_DIR, row["file"]), encoding="utf-8").read()
            capable = bool(
                ("exit 2" in text) or ("exit(2)" in text)
                or re.search(r"(?m)^\s*deny\s", text))
            assert capable, (
                "%s on %s is declared blocking but cannot reach exit 2"
                % (row["file"], event))


def test_minimal_profile_still_short_circuits(tmp_path):
    """ECC_HOOK_PROFILE=minimal must keep working through the dispatcher.

    This repo depends on it (see CONTRIBUTING.md) and every test forces it
    explicitly. The dispatcher does not read the profile itself -- the handlers
    do, exactly as before -- so this asserts the pass-through, not a new switch.
    """
    directory = _sandbox(tmp_path)
    path = _handler(directory, "profiled.sh", 0)
    with open(os.path.join(directory, path), "w", encoding="utf-8") as fh:
        fh.write('#!/usr/bin/env bash\ncat >/dev/null\n'
                 '[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0\n'
                 'echo "would block" >&2\nexit 2\n')
    _registry(directory, [_row("profiled", path, "blocking")])
    assert _run(directory, env={"ECC_HOOK_PROFILE": "minimal"}).returncode == 0
    assert _run(directory, env={"ECC_HOOK_PROFILE": "standard"}).returncode == 2


# ------------------ C1: the SHIPPED registry, on a malformed payload ---------
#
# Round-2 review executed this and the session HUNG:
#
#   $ echo 'not json' | ECC_HOOK_PROFILE=standard bash .claude/hooks/dispatch.sh PreToolUse
#   still running after 25s;  ps -> bash .../.claude/hooks/pre-push.sh
#
# pre-push.sh:138 runs the full test suite. Every sandboxed test above used a
# SYNTHETIC registry, so none of them could see it. These two drive the real one.

def _shipped_env():
    environ = dict(os.environ)
    environ["ECC_HOOK_PROFILE"] = "standard"
    environ["CLAUDEKIT_SESSION_ID"] = "pytest-dispatch"
    environ.setdefault("CLAUDE_PROJECT_DIR", REPO_ROOT)
    return environ


def test_the_shipped_registry_terminates_and_blocks_on_a_malformed_payload():
    """The REAL registry + `not json` must TERMINATE, and must block.

    Two distinct properties, both regressions from round 2:

    * TERMINATION -- a malformed PreToolUse payload must not stall the tool call.
      There is no per-handler timeout (by decision, see dispatch.sh), so the only
      thing standing between a malformed payload and a multi-minute stall is that
      a handler whose precondition cannot be evaluated does not run at all.
    * FAIL CLOSED -- rc 2 all the same, because `ops-enforcement.sh` itself exits
      2 on an unparseable payload. Skipping the two advisory command_matcher
      handlers cannot weaken that: advisory verdicts are clamped to ADVISE.
    """
    started = time.time()
    try:
        result = subprocess.run(
            ["bash", DISPATCH, "PreToolUse"], input="not json",
            capture_output=True, text=True, env=_shipped_env(), cwd=HOOKS_DIR,
            timeout=90)
    except subprocess.TimeoutExpired:
        pytest.fail(
            "dispatch.sh did not terminate on a malformed PreToolUse payload. A "
            "handler that declares a command_matcher ran out of precondition; "
            "pre-push.sh runs the full test suite. This is the round-2 hang.")
    elapsed = time.time() - started
    assert result.returncode == 2, (
        "the shipped registry failed OPEN on a malformed payload (rc=%s, stderr=%r)"
        % (result.returncode, result.stderr[-400:]))
    assert elapsed < 60, (
        "the shipped registry took %.1fs on a malformed payload -- a guard is "
        "running out of precondition" % elapsed)
    combined = result.stdout + result.stderr
    for hid in ("pre-push", "pre-commit"):
        assert hid not in combined, (
            "%s ran on a payload with no command text; its precondition is "
            "'the user ran git %s' and it cannot be evaluated here"
            % (hid, hid.split("-")[1]))


def _sleeper(directory, name, seconds):
    """A handler that stands in for pre-push.sh: slow, and precondition-scoped."""
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env bash\ncat >/dev/null\nsleep %d\nexit 0\n" % seconds)
    os.chmod(path, 0o755)
    return name


def _not_applicable_registry(tmp_path, dispatch_src=DISPATCH):
    directory = _sandbox(tmp_path, dispatch_src=dispatch_src)
    _sleeper(directory, "slow-precondition.sh", 30)
    _handler(directory, "denier.sh", 2, stderr="BLOCKED: guard says no")
    slow = _row("slow-precondition", "slow-precondition.sh", "advisory", matcher="Bash")
    slow["command_matcher"] = "^\\s*git\\s+push"
    # Slow handler FIRST on purpose: if it runs at all, nothing after it matters.
    _registry(directory, [slow, _row("denier", "denier.sh", "blocking")])
    return directory


def test_a_command_matcher_handler_is_not_applicable_on_an_unreadable_payload(tmp_path):
    """No command text -> a command_matcher handler is NOT APPLICABLE, so it is skipped.

    Deterministic and fast where the real-registry test above is broad: the
    stand-in sleeps 30s, so "did it run" is observable as a timeout rather than
    inferred from prose. The block still happens, from the handler that has no
    precondition to evaluate.
    """
    directory = _not_applicable_registry(tmp_path)
    try:
        result = _run(directory, payload="not json", timeout=25)
    except subprocess.TimeoutExpired:
        pytest.fail(
            "a handler declaring a command_matcher ran on an unreadable payload; "
            "the shipped equivalent (pre-push.sh) runs the full test suite")
    assert result.returncode == 2, (
        "fail-closed was lost: rc=%s stderr=%r" % (result.returncode, result.stderr))


def test_reverting_the_not_applicable_rule_reintroduces_the_hang(tmp_path):
    """MUTANT: restore `readable and cmd_matcher and ...` -> the slow guard runs.

    This is what makes the test above non-vacuous. With the mutant, a payload we
    cannot read runs a handler whose precondition we cannot evaluate, and the
    dispatch does not return -- exactly the round-2 hang, reproduced on demand.
    """
    # The rule now lives in dispatch_resolve.py, not in a heredoc inside
    # dispatch.sh, so the mutant is applied to the RESOLVER and the sandbox's copy
    # of it is overwritten. When the resolver was extracted this assertion fired
    # ("mutation anchor not found"), which is the intended behaviour of an anchored
    # mutant test: it fails loudly instead of silently proving nothing.
    resolver = os.path.join(HOOKS_DIR, "dispatch_resolve.py")
    source = open(resolver, encoding="utf-8").read()
    mutated = source.replace(
        "    if cmd_matcher and (not readable or not re.search(cmd_matcher, command)):",
        "    if readable and cmd_matcher and not re.search(cmd_matcher, command):")
    assert mutated != source, "mutation anchor not found -- update this test"
    directory = _not_applicable_registry(tmp_path)
    with open(os.path.join(directory, "dispatch_resolve.py"), "w",
              encoding="utf-8") as fh:
        fh.write(mutated)
    with pytest.raises(subprocess.TimeoutExpired):
        _run(directory, payload="not json", timeout=8)


def test_a_readable_payload_still_honours_the_command_matcher_both_ways(tmp_path):
    """The precondition rule did not become "always skip".

    A matching command still runs the handler; a non-matching one still does not.
    Uses a fast handler, since here the handler is EXPECTED to run.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "pusher.sh", 0, stdout="PUSH GUARD RAN")
    row = _row("pusher", "pusher.sh", "advisory", matcher="Bash")
    row["command_matcher"] = "^\\s*git\\s+push"
    _registry(directory, [row])
    yes = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
    no = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    assert "PUSH GUARD RAN" in _run(directory, payload=yes).stdout
    assert "PUSH GUARD RAN" not in _run(directory, payload=no).stdout


# ---- the invariant the skip rule depends on: enforced, not assumed (C1-R3) ---
#
# Round-3 review asked the adversarial question the skip rule invites: what stops
# a `command_matcher` from being added to a row that CAN block? At revision 3 the
# answer was NOTHING -- no schema for dispatch-registry.json, no registry
# validator, no gate, and no test. The reviewer added
# `"command_matcher": "^\\s*git\\s+commit"` to the shipped blocking
# `commit-quality` row and got 68 passed with all eight gates green. Such a row is
# skipped on an unreadable payload, so malformed input would silently remove a
# guard that can block: the fail-open class this whole phase exists to kill. The
# resolver now rejects it, and the rejection is proven by mutating the SHIPPED
# registry -- not a synthetic one, which is exactly how revision 2's test managed
# to miss a hang that was live in the real file.

#: The DISPATCHER's user-facing line: "the registry could not be resolved", for
#: ANY reason -- a parse error, a whitespace arg, an illegal row, or a crash in
#: the resolver itself. Necessary but NOT sufficient evidence that the invariant
#: fired, and round-4 review is the reason that distinction is now spelled out:
#: with `tier: null` the pre-fix resolver ACCEPTED the row and then died in
#: `"\t".join(None)`, which produces rc 1 -> this same line. A mutant test that
#: only asserted this string would have passed against the bug it exists to
#: catch -- a vacuous assertion of exactly the kind the round-4 AST audit swept
#: this file for.
RESOLVER_REJECTION = "could not resolve hook handlers"

#: The RESOLVER's own message, written by the heredoc, whose stderr is appended
#: to `hooks.log`. This is the specific evidence that the registry invariant --
#: and not some other failure -- rejected the row.
ILLEGAL_ROW = "illegal registry row"


def _read_log(directory):
    """The dispatcher's hooks.log, or "" if nothing was written."""
    path = os.path.join(directory, "hooks.log")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _truncate_log(directory):
    """Start a run from an empty log, so a later read cannot see an earlier run."""
    with open(os.path.join(directory, "hooks.log"), "w", encoding="utf-8"):
        pass


#: A row builder that can OMIT the tier key entirely -- `_row` cannot, and
#: "absent" is one of the three cases the normalization rule has to answer for.
_MISSING = object()


def _tier_row(hid, file, tier, **extra):
    row = {"id": hid, "file": file, "runner": "bash", "matcher": ""}
    if tier is not _MISSING:
        row["tier"] = tier
    row.update(extra)
    return row


def _shipped_hooks_copy(tmp_path):
    """A writable copy of the REAL .claude/hooks tree, shipped registry included."""
    directory = os.path.join(str(tmp_path), "hooks")
    shutil.copytree(HOOKS_DIR, directory,
                    ignore=shutil.ignore_patterns("hooks.log", "*.log", "__pycache__"))
    return directory


def test_the_shipped_registry_keeps_preconditions_on_advisory_rows_only():
    """Static companion: no shipped row mixes a blocking tier with a precondition.

    A cheap drift detector that names the offending row. The BEHAVIOURAL proof --
    that the resolver actually refuses such a row -- is the next test; this one
    would pass against a resolver with no check at all, and is not offered as
    the gate.

    TWO IMPLEMENTATIONS OF ONE INVARIANT, AND THE DIFFERENCE IS DELIBERATE.
    The resolver normalizes an ABSENT tier to "advisory" (`row.get("tier",
    "advisory")`), because that is also what it EMITS for an absent key, so such
    a row really is clamped. This test is STRICTER: it requires the key to be
    PRESENT and to be the literal string. The strictness runs one way only --
    every registry that passes here also passes the resolver -- so this test can
    never green a row the resolver would reject, and the shipped artifact never
    relies on the default. Round-4 review found the two normalizations had
    diverged in the OTHER direction (the resolver accepted `""`, this test did
    not), which is why the rule is now written down in both places and pinned by
    test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms.
    """
    registry = json.load(open(REGISTRY))
    for event, rows in registry["events"].items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not (row.get("command_matcher") or ""):
                continue
            assert "tier" in row, (
                "%s on %s declares a command_matcher with NO tier key. The "
                "resolver would default it to advisory, but a shipped row must "
                "say what it is rather than inherit it" % (row["id"], event))
            assert row.get("tier") == "advisory", (
                "%s on %s declares a command_matcher with tier=%r; a precondition "
                "on a row that can block is skipped on an unreadable payload, "
                "which is a bypass" % (row["id"], event, row.get("tier")))


#: The tier values a mutant may carry, and what each one proves.
#: - "blocking" is the realistic regression: a maintainer adds a precondition to
#:   a real guard (round-3 review did exactly this and the suite stayed green).
#: - "" and None are the round-4 CRITICAL. Revision 4 read the tier as
#:   `(_r.get("tier") or "advisory")`, which mapped BOTH onto "advisory" and
#:   therefore ACCEPTED them, while `ck_clamp_advisory` disarms ONLY the literal
#:   string "advisory" -- deliberately, because clamping is what removes a
#:   handler's teeth. So `{"tier": "", "command_matcher": ...}` was a row that
#:   could reach exit 2 AND was skipped on an unreadable payload: malformed
#:   input silently removed a live guard. `None` survived only by accident
#:   (`"\t".join(None)` raises, the resolver dies, the dispatcher fails closed);
#:   an accident is not a control, so it is pinned here too.
_ILLEGAL_MUTANT_TIERS = ["blocking", "", None]


@pytest.mark.parametrize("mutant_tier", _ILLEGAL_MUTANT_TIERS,
                         ids=["blocking", "empty-string", "null"])
def test_a_blocking_row_carrying_a_command_matcher_is_rejected_by_the_resolver(
        tmp_path, mutant_tier):
    """MUTATE THE SHIPPED REGISTRY: give a blocking-CAPABLE row a precondition.

    `commit-quality` is the mutant on purpose. It is tier `blocking` in the
    shipped registry AND `commit-quality.sh` really contains `exit 2` (asserted
    below), so the mutation creates a row that could block and would be skipped
    on an unreadable payload. `pre-push.sh` would be the WRONG mutant: it has no
    `exit 2`, so relabelling it trips test_blocking_tier_is_honest instead and
    proves nothing about this check.

    THE INVARIANT'S ACCEPTED SET MUST BE EXACTLY THE SET THE CLAMP DISARMS, and
    a divergence between them IS the vulnerability -- not a style difference.
    test_only_the_word_advisory_disarms_a_handler already proves, end to end,
    that `""` does NOT disarm a handler; before revision 5 this test did not
    cover `""` at all, so the two tests documented the hole without connecting
    it. They are connected now, here and in
    test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms.

    WHY THE LOG LINE IS THE EVIDENCE AND rc IS NOT. The specific assertion is
    the resolver's own `illegal registry row` message in `hooks.log`; the
    dispatcher's `could not resolve hook handlers` line and rc=2 are checked
    after it. rc alone is not evidence: on the shipped 26-row registry the
    sibling blocking guards fail closed on unparseable input all by themselves,
    so an accepted illegal row still shows rc=2 and the bypass is MASKED in the
    exit code (the M1 correction in the plan measures exactly this). And the
    generic stderr line is not evidence either: with `tier: null` the pre-fix
    resolver accepted the row and then crashed in `"\t".join(None)`, printing
    that same line for an entirely different reason. Assert the check that
    fired, not the fact that something went wrong.

    The rejection is OBSERVED, not string-matched into existence: control and
    mutant differ by one (for "blocking") or two (for ""/null) registry keys;
    the control resolves and runs handlers, the mutant runs NO handler at all
    because the resolver exits 3 before the loop; and the revert restores the
    control outcome exactly. `ECC_HOOK_PROFILE=minimal` is forced so the real
    handlers short-circuit -- the rejection fires before any handler runs, so
    the profile cannot mask it. The control's exit code is compared to the
    REVERTED run rather than pinned to a literal, because what the real guards
    decide about this payload is not this test's subject.
    """
    directory = _shipped_hooks_copy(tmp_path)
    registry_path = os.path.join(directory, "dispatch-registry.json")
    with open(registry_path, encoding="utf-8") as fh:
        pristine = fh.read()
    doc = json.loads(pristine)

    # CONTROL: the shipped registry is legal and is NOT rejected.
    control = _run(directory, payload=PAYLOAD, env={"ECC_HOOK_PROFILE": "minimal"})
    assert ILLEGAL_ROW not in _read_log(directory), (
        "the shipped registry is already rejected by its own resolver: %r"
        % _read_log(directory)[-400:])
    assert RESOLVER_REJECTION not in control.stderr, (
        "the shipped registry does not resolve: %r" % control.stderr[-400:])

    # MUTANT: a row that is blocking-CAPABLE and carries a precondition.
    rows = doc["events"]["PreToolUse"]
    target = [row for row in rows if row["id"] == "commit-quality"]
    assert len(target) == 1, "commit-quality is no longer registered -- pick another mutant"
    assert target[0]["tier"] == "blocking", target[0]
    hook_text = open(os.path.join(HOOKS_DIR, target[0]["file"]), encoding="utf-8").read()
    assert "exit 2" in hook_text, (
        "commit-quality.sh can no longer reach exit 2, so this mutant no longer "
        "demonstrates the hazard -- pick another blocking-CAPABLE handler")
    target[0]["command_matcher"] = "^\\s*git\\s+commit"
    target[0]["tier"] = mutant_tier
    mutated = json.dumps(doc, indent=2)
    assert mutated != pristine, "mutation anchor not found -- update this test"
    with open(registry_path, "w", encoding="utf-8") as fh:
        fh.write(mutated)

    _truncate_log(directory)
    result = _run(directory, payload=PAYLOAD, env={"ECC_HOOK_PROFILE": "minimal"})
    log = _read_log(directory)
    assert ILLEGAL_ROW in log, (
        "tier=%r with a command_matcher was ACCEPTED by the resolver -- the "
        "invariant's accepted set is wider than the set ck_clamp_advisory "
        "disarms, so this row can reach exit 2 AND is skipped on an unreadable "
        "payload. rc=%s (rc alone is masked by the sibling guards) log=%r"
        % (mutant_tier, result.returncode, log[-500:]))
    assert RESOLVER_REJECTION in result.stderr, (
        "the row was rejected in the log but the dispatcher did not render it as "
        "a block: rc=%s stderr=%r" % (result.returncode, result.stderr[-400:]))
    assert result.returncode == 2, (
        "rejected, but the boundary did not emit 2 -- rc=%s" % result.returncode)

    # REVERT: put the shipped bytes back; the rejection must disappear.
    with open(registry_path, "w", encoding="utf-8") as fh:
        fh.write(pristine)
    _truncate_log(directory)
    reverted = _run(directory, payload=PAYLOAD, env={"ECC_HOOK_PROFILE": "minimal"})
    assert ILLEGAL_ROW not in _read_log(directory), _read_log(directory)[-400:]
    assert RESOLVER_REJECTION not in reverted.stderr, reverted.stderr[-400:]
    assert reverted.returncode == control.returncode, (
        "reverting the mutated keys did not restore the control outcome "
        "(%s vs %s)" % (reverted.returncode, control.returncode))


def test_an_advisory_row_may_still_carry_a_command_matcher(tmp_path):
    """The check is not "reject every command_matcher".

    Without this, tightening the invariant to "no preconditions at all" would
    satisfy the test above while silently deleting the pre-commit / pre-push
    command conditions that settings.json enforces today.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "pusher.sh", 0, stdout="PUSH GUARD RAN")
    row = _row("pusher", "pusher.sh", "advisory", matcher="Bash")
    row["command_matcher"] = "^\\s*git\\s+push"
    _registry(directory, [row])
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
    result = _run(directory, payload=payload)
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert "PUSH GUARD RAN" in result.stdout, result.stdout


# ---- the reconciliation, as an executable property (round-4 Critical) --------

#: Every tier string the dispatcher can actually meet, plus "absent".
_TIER_VOCABULARY = ["advisory", "blocking", "on", "", "bogus", None, _MISSING]


@pytest.mark.parametrize("tier", _TIER_VOCABULARY,
                         ids=["advisory", "blocking", "on", "empty-string",
                              "bogus", "null", "absent"])
def test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms(
        tmp_path, tier):
    """THE invariant of the invariant: accepted set == disarmed set, per tier.

    The registry rule "a `command_matcher` may appear only on an advisory row"
    is safe **only** if the resolver's notion of "advisory" is the same as
    `ck_clamp_advisory`'s. If the resolver accepts a tier the clamp will not
    disarm, that row can reach exit 2 while being skipped on an unreadable
    payload -- malformed input silently removes a guard that can block. That is
    not a theoretical shape: it is the round-4 Critical, caused by the resolver
    reading `(tier or "advisory")` while the clamp matched only the literal
    string. Two implementations of one invariant, two normalizations, one hole.

    So the property is asserted directly, for every tier value in the
    vocabulary, by driving the shipped dispatcher twice:
      * ACCEPTED  -- a row with a `command_matcher` and this tier does not
                     produce the resolver's `illegal registry row`;
      * DISARMED  -- the same tier on a row whose handler exits 2 yields rc 0.
    They must be equal. Reverting the resolver to `(_r.get("tier") or
    "advisory")` fails this at ids `empty-string` and `null`.

    `absent` is included because the documented rule is asymmetric on purpose: a
    missing key normalizes to "advisory" on BOTH sides (the resolver defaults it
    and then EMITS "advisory", which the clamp really does disarm), so accepting
    it is consistent rather than lucky. `None` is rejected outright rather than
    being left to crash the resolver on `"\t".join(None)`: fail-closed by
    accident is not fail-closed by design.
    """
    accept_dir = os.path.join(str(tmp_path), "accept")
    os.makedirs(accept_dir)
    _sandbox(accept_dir)
    _handler(accept_dir, "quiet.sh", 0)
    _registry(accept_dir, [_tier_row("quiet", "quiet.sh", tier,
                                     command_matcher="^echo")])
    accept_run = _run(accept_dir, payload=PAYLOAD)
    accepted = ILLEGAL_ROW not in _read_log(accept_dir)

    clamp_dir = os.path.join(str(tmp_path), "clamp")
    os.makedirs(clamp_dir)
    _sandbox(clamp_dir)
    _handler(clamp_dir, "denier.sh", 2, stderr="BLOCKED: guard says no")
    _registry(clamp_dir, [_tier_row("denier", "denier.sh", tier)])
    disarmed = _run(clamp_dir, payload=PAYLOAD).returncode == 0

    assert accepted == disarmed, (
        "tier=%r: the invariant %s it, the clamp %s it. A tier the invariant "
        "ACCEPTS but the clamp does NOT disarm is a row that can block and is "
        "skipped on an unreadable payload -- the bypass. accept-run rc=%s log=%r"
        % (tier, "accepts" if accepted else "rejects",
           "disarms" if disarmed else "does not disarm",
           accept_run.returncode, _read_log(accept_dir)[-300:]))


# ---- the hook boundary emits 0 or 2, and nothing else (round-4 M2) ----------

@pytest.mark.parametrize("argv", [[], [""], ["Bogus"], ["pretooluse"],
                                  ["PreToolUse extra"]],
                         ids=["no-arg", "empty-arg", "unknown", "wrong-case",
                              "run-together"])
def test_the_boundary_emits_only_zero_or_two_for_a_missing_or_unknown_event(
        tmp_path, argv):
    """An escape probe. `exit 1` here is a fail-OPEN, so it may not exist.

    Round-4 review ran 21 escape probes against this dispatcher; 20 returned 0
    or 2 and exactly one returned 1 -- `dispatch.sh` with no event argument.
    CLAUDE.md hard rule 2 allows only 0 or 2 at a hook boundary, and the reason
    is not tidiness: Claude Code honours 2 as a block and treats every other
    non-zero code as NON-BLOCKING, so a dispatcher misregistered with a missing
    or misspelled event would have failed OPEN on PreToolUse while looking like
    a loud error. "Unreachable through the shipped wiring" is not a defence --
    it is the same reasoning that produced the round-4 Critical.

    Wrong case is included deliberately: `pretooluse` is not `PreToolUse`, and a
    dispatcher that guesses which one the operator meant is a dispatcher that
    can guess wrong about a guarded event.
    """
    directory = _sandbox(tmp_path)
    _handler(directory, "allower.sh", 0, stdout="HANDLER RAN")
    _registry(directory, [_row("allower", "allower.sh", "advisory")])
    result = _run(directory, raw_argv=argv, timeout=60)
    assert result.returncode in (0, 2), (
        "the hook boundary emitted rc=%s for argv=%r; only 0 and 2 are decisions "
        "Claude Code has, and anything else is read as non-blocking"
        % (result.returncode, argv))
    assert result.returncode == 2, (
        "an event this dispatcher cannot name must fail CLOSED: argv=%r rc=%s "
        "stderr=%r" % (argv, result.returncode, result.stderr[-300:]))
    assert "BLOCKED" in result.stderr, result.stderr[-300:]
    assert "HANDLER RAN" not in result.stdout, (
        "handlers ran for an event the dispatcher could not name: %r"
        % result.stdout[-300:])


def test_the_known_event_list_matches_the_registry():
    """The known-event list cannot drift from the registry it dispatches.

    Failing closed on an unknown event has a cost: an event that IS registered
    but missing from the case statement would block instead of running. This
    test is what makes that trade safe -- add an event to
    `dispatch-registry.json` without naming it in `dispatch.sh` and it fails
    here, loudly, at build time, instead of at a user's tool call.
    """
    source = open(DISPATCH, encoding="utf-8").read()
    block = re.search(r'case "\$EVENT" in\n(.*?)\nesac', source, re.S)
    assert block, "the EVENT case statement moved -- update this test"
    known = set()
    for pattern in re.findall(r'^\s*([A-Za-z][A-Za-z|]*)\)', block.group(1), re.M):
        known.update(pattern.split("|"))
    registered = set(json.load(open(REGISTRY))["events"])
    assert known == registered, (
        "dispatch.sh knows %s; dispatch-registry.json registers %s. An event in "
        "the registry but not in the case statement is dispatched as UNKNOWN and "
        "blocks; an event in the case statement but not in the registry is dead "
        "wiring" % (sorted(known), sorted(registered)))

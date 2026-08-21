"""Behavioural coverage for layered profiles (`ck profile`, `claudekit.profiles`).

Structural assertions do not count here, so the CLI tests drive the real
`python -m claudekit.cli.main` in a subprocess and read its exit code and streams,
and the hook-equivalence test executes real hooks under real `ECC_HOOK_PROFILE`
values rather than reasoning about their source.

Three properties are load-bearing and each is proved by MUTATING the shipped
artifact and reading the failure, not by asserting the happy path:

  (a) `minimal` behaves identically to today's `ECC_HOOK_PROFILE=minimal`;
  (b) a later layer overrides an earlier one BY ID, and an untouched row survives;
  (c) an unknown or malformed profile fails closed with a named cause.

`ECC_HOOK_PROFILE` is forced explicitly in every subprocess (project convention:
a hook result must never depend on the developer's own session profile).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from claudekit import profiles as prof  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"
SHIPPED = ("minimal", "python", "standard", "strict")
#: The three values `ECC_HOOK_PROFILE` actually takes. `python` is a stack
#: profile, selectable as a value too, but it is not a posture of its own.
ENV_VALUES = ("minimal", "standard", "strict")


def run_cli(*args, cwd=None, env=None):
    environ = dict(os.environ, ECC_HOOK_PROFILE="minimal",
                   PYTHONPATH=str(ROOT / "src"))
    environ.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "claudekit.cli.main", *args],
        cwd=str(cwd or ROOT), capture_output=True, text=True, env=environ)


def add_guard(hook, line):
    """Insert a guard line into a hook, and PROVE the insertion landed.

    `str.replace` on an absent anchor is a silent no-op, so a mutation test built
    on one asserts against an unmutated file and passes for the wrong reason. That
    is a `vacuous-check`, and it is exactly what happened on the first run of the
    three mutant tests below: the anchor was `set -uo pipefail`, which
    commit-quality.sh does not contain. The `!=` assertion here is the fix, and it
    belongs in the helper so no future mutant can reintroduce the same hole.
    """
    before = hook.read_text(encoding="utf-8")
    anchor = 'HOOK_NAME="commit-quality"'
    assert anchor in before, f"anchor {anchor!r} absent from {hook.name}"
    after = before.replace(anchor, anchor + "\n" + line, 1)
    assert after != before, "mutation did not change the file"
    hook.write_text(after, encoding="utf-8")


@pytest.fixture()
def tree(tmp_path):
    """A minimal installed tree: real hooks, real profiles, nothing else."""
    dest = tmp_path / "proj"
    (dest / ".claude").mkdir(parents=True)
    shutil.copytree(HOOKS, dest / ".claude" / "hooks")
    shutil.copytree(ROOT / ".claude" / "profiles", dest / ".claude" / "profiles")
    return dest


# --------------------------------------------------------------------------
# What ships
# --------------------------------------------------------------------------

def test_exactly_the_shipped_profiles_are_installed():
    """Four, and no more. A profile-per-stack explosion is the thing to prevent."""
    assert tuple(prof.list_profiles(ROOT)) == SHIPPED


def test_base_is_not_a_shipped_profile():
    """`base` is the built-in identity, not a directory anyone can select."""
    assert "base" not in prof.list_profiles(ROOT)
    assert set(prof.base_layer()["hooks"]) == set(prof.GUARDED_HOOKS)
    assert set(prof.base_layer()["hooks"].values()) == {"on"}


# --------------------------------------------------------------------------
# (a) equivalence with the hooks' own guards
# --------------------------------------------------------------------------

def test_every_declaration_matches_the_hooks_own_guards():
    """The declaration is bound to the shipped artifact, not to prose about it."""
    assert prof.check_declarations(ROOT) == []


def test_no_unlisted_hook_carries_a_profile_guard():
    """A NEW guard in an undeclared hook must red this, not pass silently."""
    listed = set(prof.GUARDED_HOOKS.values())
    stray = []
    for path in sorted(HOOKS.iterdir()):
        if path.name in listed or path.suffix not in (".sh", ".py"):
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if prof._SH_SIGIL_RE.search(stripped):
                stray.append(f"{path.name}:{lineno}")
    assert stray == [], (
        "these hooks guard on ECC_HOOK_PROFILE but are absent from "
        "profiles.GUARDED_HOOKS, so no profile declares them: " + ", ".join(stray))


@pytest.mark.parametrize("hook_id", sorted(prof.GUARDED_HOOKS))
def test_minimal_declaration_equals_the_minimal_guard(hook_id):
    modes, unknown = prof.scan_hook_guards(HOOKS / prof.GUARDED_HOOKS[hook_id], ENV_VALUES)
    assert unknown == []
    declared = prof.resolve(ROOT, "minimal", env={}).value("hooks", hook_id)
    assert declared == modes["minimal"]


def test_ops_enforcement_really_stands_down_under_minimal_and_blocks_otherwise():
    """The end-to-end anchor: run the real hook, compare to what minimal declares.

    A declaration proved only against a parser would be a mirror of a mirror. This
    executes the hook under both env values and reads the exit codes.
    """
    payload = json.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/claudekit/cli/main.py"},
    })
    results = {}
    for value in ("minimal", "standard"):
        proc = subprocess.run(
            ["bash", str(HOOKS / "ops-enforcement.sh")],
            input=payload, capture_output=True, text=True, cwd=str(ROOT),
            env=dict(os.environ, ECC_HOOK_PROFILE=value))
        results[value] = proc.returncode

    minimal_declared = prof.resolve(ROOT, "minimal", env={}).value("hooks", "ops-enforcement")
    standard_declared = prof.resolve(ROOT, "standard", env={}).value("hooks", "ops-enforcement")
    assert minimal_declared == "off" and results["minimal"] == 0, (
        f"minimal declares {minimal_declared!r} but the hook exited "
        f"{results['minimal']}")
    assert standard_declared == "on" and results["standard"] == 2, (
        f"standard declares {standard_declared!r} but the hook exited "
        f"{results['standard']} (a block is exit 2 + stderr)")


def test_a_drifted_declaration_is_reported(tree):
    """MUTANT: flip one declared row. check_declarations must name it.

    Without this the gate could report PASS against a wrong declaration, which is
    worse than no gate — this repo has shipped that failure twice.
    """
    path = tree / ".claude" / "profiles" / "minimal" / "profile.json"
    doc = json.loads(path.read_text())
    doc["hooks"]["ops-enforcement"] = "on"
    path.write_text(json.dumps(doc, indent=2))
    problems = prof.check_declarations(tree)
    assert any("ops-enforcement" in p and "minimal" in p for p in problems), problems


def test_an_unmodelled_guard_form_is_reported_not_ignored(tree):
    """MUTANT: ADD a guard in a shape the scanner does not model.

    The failure this closes is the one `.ai/REVIEW_GUIDE.md` records: a mirror that
    detects a CHANGED clause but not an ADDED one silently becomes wrong.
    """
    hook = tree / ".claude" / "hooks" / "commit-quality.sh"
    add_guard(hook, 'case "${ECC_HOOK_PROFILE:-standard}" in fancy) exit 0 ;; esac')
    _modes, unknown = prof.scan_hook_guards(hook, ENV_VALUES)
    assert unknown and "fancy" in unknown[0], unknown


def test_a_braceless_guard_is_reported_not_silently_skipped(tree):
    """MUTANT M7: `[ "$ECC_HOOK_PROFILE" = ... ]` — no braces, ordinary bash.

    This is the shape that escaped the first version of the scanner: the sigil was
    a substring test for `${ECC_HOOK_PROFILE`, so the brace-less form matched
    nothing and was skipped WITHOUT being recorded as unknown. Neither recognised
    nor reported is strictly worse than unrecognised, and it is the precise silent
    drift `unrecognised` exists to prevent. Regression test, not a hypothetical.
    """
    hook = tree / ".claude" / "hooks" / "commit-quality.sh"
    add_guard(hook, '[ "$ECC_HOOK_PROFILE" = "minimal" ] && exit 0')
    _modes, unknown = prof.scan_hook_guards(hook, ENV_VALUES)
    assert unknown and prof.PROFILE_ENV in unknown[0], unknown


def test_an_unquoted_alias_guard_is_reported(tree):
    """MUTANT M9: `[ $PROFILE = "minimal" ]` — the alias this module models, unquoted.

    Round 1 closed the brace-less `$ECC_HOOK_PROFILE` hole; round 2 found the same
    hole one alternative to the right, because the alias pattern demanded quotes.
    Two instances of one class in two review rounds is why the candidate test now
    matches the dereference and leaves recognition to the form regexes.
    """
    hook = tree / ".claude" / "hooks" / "command-guard.sh"
    hook.write_text(hook.read_text().replace(
        '[ "$PROFILE" = "minimal" ] && exit 0',
        '[ $PROFILE = "minimal" ] && exit 0', 1))
    _modes, unknown = prof.scan_hook_guards(hook, ENV_VALUES)
    assert unknown and "PROFILE" in unknown[0], unknown


def test_a_braced_guard_without_the_default_is_reported(tree):
    """`${ECC_HOOK_PROFILE}` with no `:-standard` has different semantics (unset
    becomes empty, not `standard`), so it must be reported rather than quietly
    treated as equivalent to the form the hooks actually use."""
    hook = tree / ".claude" / "hooks" / "commit-quality.sh"
    add_guard(hook, '[ "${ECC_HOOK_PROFILE}" = "minimal" ] && exit 0')
    _modes, unknown = prof.scan_hook_guards(hook, ENV_VALUES)
    assert unknown, "a guard missing the :-standard default must not pass silently"


def test_prose_that_merely_names_the_variable_is_not_a_guard():
    """command-guard.sh's help text names ECC_HOOK_PROFILE. That is not a form."""
    modes, unknown = prof.scan_hook_guards(HOOKS / "command-guard.sh", ENV_VALUES)
    assert unknown == []
    assert modes == {"minimal": "off", "standard": "on", "strict": "on"}


def test_reflection_gate_is_advisory_under_minimal_not_off():
    """Three modes exist because this hook still RUNS under minimal; it cannot block."""
    modes, unknown = prof.scan_hook_guards(HOOKS / "reflection-gate.py", ENV_VALUES)
    assert unknown == []
    assert modes["minimal"] == "advisory"
    assert prof.resolve(ROOT, "minimal", env={}).value("hooks", "reflection-gate") == "advisory"


# --------------------------------------------------------------------------
# (b) layer precedence, by id
# --------------------------------------------------------------------------

def test_profile_layer_overrides_base_and_leaves_other_rows_alone():
    resolved = prof.resolve(ROOT, "minimal", env={})
    overridden = resolved.rows[("hooks", "ops-enforcement")]
    assert (overridden.value, overridden.layer) == ("off", "profile")
    survivor = prof.resolve(ROOT, "strict", env={}).rows[("hooks", "ops-enforcement")]
    assert (survivor.value, survivor.layer) == ("on", "base"), (
        "strict declares no hook rows; the base value must survive and say so")


def test_extends_composes_parent_then_child():
    resolved = prof.resolve(ROOT, "python", env={})
    # from the parent (`standard`), by id
    assert resolved.value("hooks", "injection-scan-gate") == "off"
    # from base, untouched by either
    assert resolved.rows[("hooks", "ops-enforcement")].layer == "base"
    # the child's own rows
    assert resolved.value("stack", "test_cmd") == "python3 -m pytest -q"
    assert resolved.value("mcp", "max_tools") == 40


def test_project_local_layer_beats_the_profile(tree):
    (tree / ".claude" / "profiles" / "local.json").write_text(json.dumps({
        "schema_version": 1,
        "hooks": {"ops-enforcement": "advisory"},
    }))
    row = prof.resolve(tree, "minimal", env={}).rows[("hooks", "ops-enforcement")]
    assert (row.value, row.layer) == ("advisory", "project-local")
    # a row local.json does not mention still comes from the profile
    other = prof.resolve(tree, "minimal", env={}).rows[("hooks", "commit-quality")]
    assert (other.value, other.layer) == ("off", "profile")


def test_override_layer_beats_project_local(tree):
    (tree / ".claude" / "profiles" / "local.json").write_text(json.dumps({
        "schema_version": 1,
        "hooks": {"ops-enforcement": "advisory"},
    }))
    row = prof.resolve(tree, "minimal", env={},
                       overrides=["hooks.ops-enforcement=on"]).rows[("hooks", "ops-enforcement")]
    assert (row.value, row.layer) == ("on", "override")


def test_layer_order_constant_is_the_one_the_resolver_uses():
    assert prof.LAYERS == ("base", "profile", "project-local", "override")


# --------------------------------------------------------------------------
# (c) fail-closed, with a named cause
# --------------------------------------------------------------------------

def test_env_selects_the_profile_and_minimal_still_works():
    assert prof.select_name(ROOT, None, {"ECC_HOOK_PROFILE": "minimal"}) == "minimal"
    assert prof.select_name(ROOT, None, {}) == "standard"
    assert prof.resolve(ROOT, env={"ECC_HOOK_PROFILE": "minimal"}).name == "minimal"


@pytest.mark.parametrize("name,cause", [
    ("nope", "unknown profile"),
    ("Bad Name", "invalid profile name"),
    ("../etc", "invalid profile name"),
    ("", "invalid profile name"),
])
def test_bad_profile_names_fail_closed(name, cause):
    """Asserted against load_profile, which is where name validation lives.

    Routing the empty name through resolve() would prove nothing: `select_name`
    treats "" as "no explicit choice" and falls back to the default, so the
    original version of this case passed an empty string and never reached a
    validator at all — green for the wrong reason.
    """
    with pytest.raises(prof.ProfileError) as exc:
        prof.load_profile(ROOT, name)
    assert cause in str(exc.value)


def test_an_unknown_name_fails_closed_through_resolve_too():
    with pytest.raises(prof.ProfileError) as exc:
        prof.resolve(ROOT, "nope", env={})
    assert "unknown profile" in str(exc.value)


@pytest.mark.parametrize("doc,cause", [
    ({"name": "minimal"}, "missing 'schema_version'"),
    ({"schema_version": 2, "name": "minimal"}, "unsupported schema_version"),
    ({"schema_version": 1, "name": "minimal", "hooks": {"nope": "off"}}, "unknown hook id"),
    ({"schema_version": 1, "name": "minimal", "hooks": {"ops-enforcement": "maybe"}},
     "must be one of"),
    ({"schema_version": 1, "name": "minimal", "mcp": {"max_tools": -1}},
     "non-negative integer"),
    ({"schema_version": 1, "name": "minimal", "stack": {"nope": "x"}}, "unknown stack key"),
    ({"schema_version": 1, "name": "minimal", "wat": 1}, "unknown top-level key"),
    ({"schema_version": 1, "name": "other"}, "the two must agree"),
])
def test_a_malformed_profile_fails_closed_with_a_named_cause(tree, doc, cause):
    path = tree / ".claude" / "profiles" / "minimal" / "profile.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(prof.ProfileError) as exc:
        prof.resolve(tree, "minimal", env={})
    assert cause in str(exc.value)


def test_unparseable_profile_json_fails_closed(tree):
    (tree / ".claude" / "profiles" / "minimal" / "profile.json").write_text("{ nope")
    with pytest.raises(prof.ProfileError) as exc:
        prof.resolve(tree, "minimal", env={})
    assert "malformed JSON" in str(exc.value)


def test_extends_cycle_fails_closed(tree):
    for a, b in (("minimal", "standard"), ("standard", "minimal")):
        path = tree / ".claude" / "profiles" / a / "profile.json"
        doc = json.loads(path.read_text())
        doc["extends"] = b
        path.write_text(json.dumps(doc))
    with pytest.raises(prof.ProfileError) as exc:
        prof.resolve(tree, "minimal", env={})
    assert "cycle" in str(exc.value)


def test_project_local_may_not_extend(tree):
    (tree / ".claude" / "profiles" / "local.json").write_text(json.dumps({
        "schema_version": 1, "extends": "strict"}))
    with pytest.raises(prof.ProfileError) as exc:
        prof.resolve(tree, "minimal", env={})
    assert "'extends' is not allowed" in str(exc.value)


@pytest.mark.parametrize("item,cause", [
    ("hooks.ops-enforcement", "SECTION.ID=VALUE"),
    ("nosuch.thing=on", "unknown section"),
    ("hooks.ops-enforcement=sideways", "must be one of"),
])
def test_a_bad_override_fails_closed(item, cause):
    with pytest.raises(prof.ProfileError) as exc:
        prof.parse_overrides([item])
    assert cause in str(exc.value)


# --------------------------------------------------------------------------
# The CLI (driven for real)
# --------------------------------------------------------------------------

def test_cli_list_names_every_profile_and_marks_the_active_one():
    proc = run_cli("profile", "list", env={"ECC_HOOK_PROFILE": "minimal"})
    assert proc.returncode == 0, proc.stderr
    for name in SHIPPED:
        assert name in proc.stdout
    assert "(active)" in proc.stdout
    assert "Active selection: minimal" in proc.stdout


def test_cli_show_resolved_attributes_every_row_to_a_layer():
    proc = run_cli("profile", "show", "python", "--resolved")
    assert proc.returncode == 0, proc.stderr
    assert "base" in proc.stdout and "profile" in proc.stdout
    assert "max_tools" in proc.stdout and "test_cmd" in proc.stdout


def test_cli_show_json_is_machine_readable_and_attributed():
    proc = run_cli("profile", "show", "python", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["profile"] == "python"
    assert data["layers"] == list(prof.LAYERS)
    hooks = data["sections"]["hooks"]
    assert hooks["ops-enforcement"] == {"value": "on", "layer": "base"}
    assert hooks["injection-scan-gate"] == {"value": "off", "layer": "profile"}


def test_cli_show_accepts_an_override_and_attributes_it():
    proc = run_cli("profile", "show", "minimal", "--json",
                   "--set", "hooks.ops-enforcement=on")
    assert proc.returncode == 0, proc.stderr
    row = json.loads(proc.stdout)["sections"]["hooks"]["ops-enforcement"]
    assert row == {"value": "on", "layer": "override"}


def test_cli_show_without_resolved_prints_the_raw_document():
    proc = run_cli("profile", "show", "strict")
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["name"] == "strict" and doc["hooks"] == {}


@pytest.mark.parametrize("args,cause", [
    (["profile", "show", "nope"], "unknown profile"),
    (["profile", "show", "minimal", "--json", "--set", "hooks.x=on"], "unknown hook id"),
])
def test_cli_fails_closed_with_the_cause_on_stderr(args, cause):
    proc = run_cli(*args)
    assert proc.returncode == 1, proc.stdout
    assert cause in proc.stderr


def test_cli_reports_a_malformed_profile_rather_than_falling_back(tree):
    (tree / ".claude" / "profiles" / "minimal" / "profile.json").write_text("{ nope")
    proc = run_cli("profile", "show", "minimal", "--resolved", cwd=tree)
    assert proc.returncode == 1
    assert "malformed JSON" in proc.stderr


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def test_doctor_fails_when_a_profile_has_drifted_from_the_hooks(tree):
    """MUTATE the shipped artifact and read the failure — the gate must bind."""
    path = tree / ".claude" / "profiles" / "minimal" / "profile.json"
    doc = json.loads(path.read_text())
    doc["hooks"]["ops-enforcement"] = "on"
    path.write_text(json.dumps(doc, indent=2))
    proc = run_cli("doctor", cwd=tree)
    assert proc.returncode == 1, proc.stdout
    assert "ops-enforcement" in (proc.stdout + proc.stderr)


def test_doctor_passes_the_profile_check_on_the_real_tree():
    proc = run_cli("doctor")
    assert "Profile declarations match hook guards" in proc.stdout, proc.stdout

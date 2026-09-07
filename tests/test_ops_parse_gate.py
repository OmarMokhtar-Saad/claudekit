"""The parse gate refuses an ops.json whose result would not compile.

Behavioural, not structural: every test drives the real module over a real ops.json against
real files on disk and asserts the verdict. A mutation of ops_precompile.py turns one red.

The gate exists because approval, identity and drift all gate on INTENT, and none of them
gates on the RESULT -- a validator-clean, dry-run-clean, APPROVED ops.json once spliced a
malformed f-string into a source file and the SyntaxError surfaced only at runtime.

WHAT THIS GATE DOES NOT DO, and why several tests below assert a PASS on a broken plan: a
missing or ambiguous anchor is the executor's refusal, not this one. `execute_code_edit`
already fails closed on both and RESULT-JSON then names which operation failed. This module
withholds its parse verdict for such a file and says so, but does not refuse -- refusing first
would flatten that per-operation diagnostic into a generic parse-gate reason.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / ".claude" / "operations" / "scripts"
GATE = SCRIPTS / "ops_precompile.py"
EXECUTOR = SCRIPTS / "execute-json-ops.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("ops_precompile", str(GATE))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def gate():
    return load_gate()


def write_ops(tmp_path, operations):
    cfg = tmp_path / "ops.json"
    cfg.write_text(json.dumps({"plan_name": "t", "operations": operations}))
    return str(cfg)


def edit_ops(tmp_path, edits, path="target.py"):
    return write_ops(tmp_path, [{"type": "code_edit", "path": path, "edits": edits}])


@pytest.fixture()
def target(tmp_path, monkeypatch):
    src = tmp_path / "target.py"
    src.write_text('def greet(name):\n    msg = "hello " + name\n    return msg\n')
    monkeypatch.chdir(tmp_path)
    return src


FIND = '    msg = "hello " + name'
BREAKS = '    msg = f"hello {name"'


def test_gate_file_exists():
    assert GATE.is_file(), f"the parse gate is a required part of the engine: {GATE}"


# ---------------------------------------------------------------- the core claim

def test_clean_edit_passes(gate, tmp_path, target):
    ok, _ = gate.check(edit_ops(tmp_path, [{"find": FIND, "replace": '    msg = f"hello {name}"'}]))
    assert ok is True


def test_syntax_error_is_refused(gate, tmp_path, target):
    """The original incident: a replace block that splices an unbalanced f-string."""
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}]))
    assert ok is False
    assert any("BREAK" in line for line in lines)


def test_refusal_names_the_file_and_line(gate, tmp_path, target):
    _, lines = gate.check(edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}]))
    blob = "\n".join(lines)
    assert "target.py" in blob and "line 2" in blob


def test_later_edit_may_repair_an_earlier_break(gate, tmp_path, target):
    """Edits thread through one accumulator, so only the FINAL text is judged."""
    ok, _ = gate.check(edit_ops(tmp_path, [
        {"find": FIND, "replace": BREAKS},
        {"find": BREAKS, "replace": '    msg = f"hello {name}"'}]))
    assert ok is True


# ------------------------------------------------- every edit action, not just replace

@pytest.mark.parametrize("edit", [
    {"find": "def greet(name):", "add_after": "\n    y = (1\n"},
    {"find": "def greet(name):", "add_before": "x = (1\n"},
    {"find": "def greet(name):", "delete": True},  # leaves the body dedented
])
def test_each_edit_action_is_modelled(gate, tmp_path, target, edit):
    """add_after / add_before / delete must be modelled, not only `replace`."""
    ok, _ = gate.check(edit_ops(tmp_path, [edit]))
    assert ok is False, f"{edit} broke the file and the gate did not notice"


def test_action_precedence_matches_the_executor(gate, tmp_path, target):
    """REGRESSION. An edit may carry two action keys and the validator accepts it.

    `execute_code_edit` checks add_after BEFORE replace, so add_after is what gets written.
    A gate that preferred `replace` would apply a no-op, report OK, and let the executor
    write a file that does not parse -- modelling a result the executor never produces.
    """
    ok, _ = gate.check(edit_ops(tmp_path, [{
        "find": "def greet(name):",
        "add_after": "\n    y = (1\n",     # what the executor applies -> breaks
        "replace": "def greet(name):",      # a no-op the gate must NOT prefer
    }]))
    assert ok is False, "gate preferred `replace`; the executor prefers `add_after`"


# ------------------------------------------------------------------- file_create

def test_file_create_with_broken_python_is_refused(gate, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ok, _ = gate.check(write_ops(tmp_path, [
        {"type": "file_create", "path": "new.py", "content": "def f(:\n"}]))
    assert ok is False


def test_file_create_reports_the_file_as_new(gate, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(write_ops(tmp_path, [
        {"type": "file_create", "path": "new.py", "content": "x = 1\n"}]))
    assert ok is True
    assert any("is new and parses" in line for line in lines)


def test_file_create_without_content_is_reported(gate, tmp_path, monkeypatch):
    """`execute_file_create` indexes operation['content'], so an absent key KeyErrors
    there. Modelling it as an empty file would green-light a plan that cannot run."""
    monkeypatch.chdir(tmp_path)
    _, lines = gate.check(write_ops(tmp_path, [{"type": "file_create", "path": "n.py"}]))
    assert any("no content key" in line for line in lines)


def test_edit_after_delete_in_the_same_plan_is_reported(gate, tmp_path, target):
    """The file is still on disk, so a naive re-read models an edit the executor cannot do."""
    _, lines = gate.check(write_ops(tmp_path, [
        {"type": "file_delete", "path": "target.py", "reason": "x"},
        {"type": "code_edit", "path": "target.py", "edits": [{"find": FIND, "replace": "x = 1"}]}]))
    assert any("deletes it" in line for line in lines)


# --------------------------------------------------------------- shadow detection

def test_new_module_level_shadow_is_refused(gate, tmp_path, monkeypatch):
    """A name imported and then rebound at module level is the module's second refusal."""
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(write_ops(tmp_path, [{
        "type": "file_create", "path": "s.py",
        "content": "import html\n\nhtml = html.escape('x')\n"}]))
    assert ok is False
    assert any("SHADOW" in line for line in lines)


def test_global_rebind_counts_as_module_level(gate, tmp_path, monkeypatch):
    """A `global` assignment inside a function rebinds the module name too."""
    monkeypatch.chdir(tmp_path)
    ok, _ = gate.check(write_ops(tmp_path, [{
        "type": "file_create", "path": "g.py",
        "content": "import html\n\ndef f():\n    global html\n    html = 1\n"}]))
    assert ok is False


def test_local_assignment_is_not_a_shadow(gate, tmp_path, monkeypatch):
    """A function-local of the same name shadows nothing at module level."""
    monkeypatch.chdir(tmp_path)
    ok, _ = gate.check(write_ops(tmp_path, [{
        "type": "file_create", "path": "l.py",
        "content": "import html\n\ndef f():\n    html = 1\n    return html\n"}]))
    assert ok is True


def test_preexisting_shadow_is_not_newly_blamed(gate, tmp_path, monkeypatch):
    """Only shadows this edit INTRODUCES are refused; the gate is not a linter."""
    src = tmp_path / "p.py"
    src.write_text("import html\n\nhtml = 1\n\nz = 0\n")
    monkeypatch.chdir(tmp_path)
    ok, _ = gate.check(edit_ops(tmp_path, [{"find": "z = 0", "replace": "z = 2"}], path="p.py"))
    assert ok is True


# ------------------------------------------------------- anchors: report, do not refuse

def test_missing_anchor_withholds_the_verdict_without_refusing(gate, tmp_path, target):
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": "nowhere in the file", "replace": "x = 1"}]))
    blob = "\n".join(lines)
    assert "MISS" in blob
    assert "not checked" in blob, "the parse verdict must be withheld, not guessed"
    assert ok is True, "refusing here would flatten the executor's per-operation reporting"


def test_ambiguous_anchor_is_reported(gate, tmp_path, monkeypatch):
    src = tmp_path / "a.py"
    src.write_text("x = 1\nx = 1\n")
    monkeypatch.chdir(tmp_path)
    _, lines = gate.check(edit_ops(tmp_path, [{"find": "x = 1", "replace": "x = 2"}], path="a.py"))
    assert any("ambiguous" in line for line in lines)


def test_edit_without_find_is_reported(gate, tmp_path, target):
    _, lines = gate.check(edit_ops(tmp_path, [{"replace": "x = 1"}]))
    assert any("no find pattern" in line for line in lines)


# ------------------------------------------------------------------- other shapes

def test_legacy_files_schema_is_understood(gate, tmp_path, target):
    """LEGACY `files: [{path, edits}]` must be modelled, not silently skipped."""
    cfg = tmp_path / "ops.json"
    cfg.write_text(json.dumps({"plan_name": "t", "files": [
        {"path": "target.py", "edits": [{"find": FIND, "replace": BREAKS}]}]}))
    ok, _ = gate.check(str(cfg))
    assert ok is False


def test_bom_file_is_read_as_the_executor_reads_it(gate, tmp_path, monkeypatch):
    """The executor reads utf-8-sig. Reading plain utf-8 would blame the BOM as a
    non-printable character and refuse a perfectly good edit."""
    src = tmp_path / "b.py"
    src.write_text("﻿x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": "x = 1", "replace": "x = 2"}], path="b.py"))
    assert ok is True, "BOM falsely refused: " + "\n".join(lines)


@pytest.mark.parametrize("name,before,after", [
    # Content that is NOT valid Python, so the assertion can only pass because of the
    # .py/.pyi guard. The earlier version of this test used '# title' -> '# other', which
    # ast.parse accepts, so it held whether or not the guard existed.
    ("notes.yaml", "title:\n  - a\n", "title:\n  - b\n"),
    ("run.sh", "if [ -f x ]; then\n", "if [ -f y ]; then\n"),
])
def test_non_python_files_are_not_parsed(gate, tmp_path, monkeypatch, name, before, after):
    doc = tmp_path / name
    doc.write_text(before)
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": before, "replace": after}], path=name))
    assert ok is True, "a non-Python file was parsed as Python: " + "\n".join(lines)
    assert any("not Python" in line for line in lines)


def test_pyi_stubs_are_parsed(gate, tmp_path, monkeypatch):
    """.pyi is Python too — narrowing the guard to ('.py',) must not go unnoticed."""
    stub = tmp_path / "s.pyi"
    stub.write_text("def f() -> int: ...\n")
    monkeypatch.chdir(tmp_path)
    ok, _ = gate.check(edit_ops(tmp_path, [
        {"find": "def f() -> int: ...", "replace": "def f( -> int: ..."}], path="s.pyi"))
    assert ok is False


def test_gate_never_writes(gate, tmp_path, target):
    before = target.read_text()
    gate.check(edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}]))
    assert target.read_text() == before


# --------------------------------------------------- the wiring, through the executor

def _run_executor(tmp_path, cfg, *flags):
    return subprocess.run([sys.executable, str(EXECUTOR), cfg, *flags],
                          cwd=str(tmp_path), capture_output=True, text=True, timeout=120)


def test_executor_refuses_a_breaking_plan_and_writes_nothing(tmp_path, target):
    cfg = edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}])
    before = target.read_text()
    res = _run_executor(tmp_path, cfg, "--no-approval")
    assert res.returncode == 1
    assert "PARSE GATE" in res.stdout
    assert target.read_text() == before, "the tree was mutated despite the refusal"


def test_executor_runs_the_gate_in_dry_run_too(tmp_path, target):
    res = _run_executor(tmp_path, edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}]),
                        "--dry-run")
    assert res.returncode == 1
    assert "PARSE GATE" in res.stdout


def test_no_parse_check_bypasses_loudly(tmp_path, target):
    cfg = edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}])
    res = _run_executor(tmp_path, cfg, "--no-approval", "--no-parse-check")
    assert "BYPASSED" in res.stdout
    assert "PARSE GATE BYPASSED" in res.stderr, "a silent bypass is not a bypass"
    assert BREAKS in target.read_text(), "the bypass did not actually write"


def test_executor_fails_closed_when_the_gate_is_missing(tmp_path, target, monkeypatch):
    """A gate that cannot inspect the result must refuse, not wave it through."""
    engine = tmp_path / "engine.py"
    engine.write_text(EXECUTOR.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = edit_ops(tmp_path, [{"find": FIND, "replace": '    msg = f"hello {name}"'}])
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS))
    res = subprocess.run([sys.executable, str(engine), cfg, "--no-approval"],
                         cwd=str(tmp_path), capture_output=True, text=True, timeout=120, env=env)
    assert res.returncode == 1
    assert "parse checker is missing" in res.stdout
    assert target.read_text() == 'def greet(name):\n    msg = "hello " + name\n    return msg\n'


# --------------------------------------------- shadow detection: the unpinned branches

def test_shadow_bound_inside_a_block_is_found(gate, tmp_path, monkeypatch):
    """THE MOTIVATING CASE. The binding sits at module level but nested in an `if`, so it is
    only reachable through the recursive walk. Without the recursion this returns clean."""
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(write_ops(tmp_path, [{
        "type": "file_create", "path": "n.py",
        "content": "import html\n\nif 1:\n    html = html.escape('x')\n"}]))
    assert ok is False, "a nested module-level rebind was missed: " + "\n".join(lines)


@pytest.mark.parametrize("body", [
    "import html\n\nclass html:\n    pass\n",                    # ClassDef name
    "import html\n\ndef html():\n    pass\n",                    # FunctionDef name
    "import html\n\nfor html in []:\n    pass\n",                # For target
    "import html\n\nwith open('f') as html:\n    pass\n",        # withitem
    "import html\n\ntry:\n    pass\nexcept Exception as html:\n    pass\n",  # ExceptHandler
    "from x import html\n\nhtml = 1\n",                           # ImportFrom
    "import y as html\n\nhtml = 1\n",                             # asname
])
def test_every_binding_form_counts_as_a_shadow(gate, tmp_path, monkeypatch, body):
    monkeypatch.chdir(tmp_path)
    ok, _ = gate.check(write_ops(tmp_path, [
        {"type": "file_create", "path": "b.py", "content": body}]))
    assert ok is False, "this binding form did not register as a shadow:\n" + body


def test_global_without_assignment_is_not_a_shadow(gate, tmp_path, monkeypatch):
    """`global html` on its own rebinds nothing. If this filter regresses the gate starts
    REFUSING valid plans, which is how a noisy gate gets muted."""
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(write_ops(tmp_path, [{
        "type": "file_create", "path": "r.py",
        "content": "import html\n\ndef f():\n    global html\n    print(html)\n"}]))
    assert ok is True, "read-only `global` falsely refused: " + "\n".join(lines)


def test_legacy_schema_reads_a_bom_file_as_the_executor_does(gate, tmp_path, monkeypatch):
    src = tmp_path / "lb.py"
    src.write_text("\ufeffx = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "ops.json"
    cfg.write_text(json.dumps({"plan_name": "t", "files": [
        {"path": "lb.py", "edits": [{"find": "x = 1", "replace": "x = 2"}]}]}))
    ok, lines = gate.check(str(cfg))
    assert ok is True, "BOM falsely refused via the legacy schema: " + "\n".join(lines)


def test_shadow_baseline_reads_a_bom_file_as_the_executor_does(gate, tmp_path, monkeypatch):
    """_new_shadows re-reads the ORIGINAL file to diff against; that read needs the BOM
    stripped too, or the baseline parse fails and pre-existing shadows look new."""
    src = tmp_path / "sb.py"
    src.write_text("\ufeffimport html\n\nhtml = 1\n\nz = 0\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": "z = 0", "replace": "z = 2"}], path="sb.py"))
    assert ok is True, "a pre-existing shadow was blamed on this edit: " + "\n".join(lines)


# ---------------------------------------------------------------------------
# ORDERING: the ambiguity verdict outranks the parse verdict.
#
# Both directions, or neither test binds. Swapping the two checks back must turn one of
# these red: the first pins that a precise diagnosis is not replaced by a symptom, the
# second pins that the gate is still a real backstop for a unique match that breaks.
# ---------------------------------------------------------------------------

AMBIGUOUS_SRC = 'def f():\n    return 1\n\n\ndef g():\n    return 1\n'


def test_ambiguity_outranks_the_parse_gate_in_the_executor(tmp_path, monkeypatch):
    """MUTATION PROOF (ordering): refuse ambiguity in the gate and this goes red.

    The executor must report `ambiguous match` and name WHICH operation failed, not the
    generic `parse-gate: result does not parse`. If the gate is made to refuse a miss --
    i.e. the parse verdict is evaluated first -- stdout loses the precise sentence and
    RESULT-JSON flattens `operations` to [].
    """
    src = tmp_path / "target.py"
    src.write_text(AMBIGUOUS_SRC)
    monkeypatch.chdir(tmp_path)
    cfg = edit_ops(tmp_path, [{"find": "    return 1", "replace": "    return 2"}])
    res = _run_executor(tmp_path, cfg, "--no-approval")
    assert res.returncode == 1
    assert "ambiguous match" in res.stdout, res.stdout[-600:]
    assert "PARSE GATE: refusing" not in res.stdout, res.stdout[-600:]
    assert '"status": "ambiguous-pattern"' in res.stdout, res.stdout[-600:]
    assert src.read_text() == AMBIGUOUS_SRC, "the tree was mutated"


def test_the_parse_gate_still_fires_for_a_unique_match_that_breaks(tmp_path, target):
    """MUTATION PROOF (backstop): the other direction of the ordering invariant.

    Deferring to the ambiguity check must NOT have turned the gate into a no-op. A
    uniquely-matching edit that leaves unparseable text is still refused, by the gate,
    before any write.
    """
    before = target.read_text()
    cfg = edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}])
    res = _run_executor(tmp_path, cfg, "--no-approval")
    assert res.returncode == 1
    assert "PARSE GATE: refusing" in res.stdout, res.stdout[-600:]
    assert "ambiguous" not in res.stdout
    assert target.read_text() == before, "the tree was mutated despite the refusal"


def test_an_ambiguous_anchor_alone_does_not_fail_the_gate(gate, tmp_path, monkeypatch):
    """Unit-level half of the ordering invariant: ok is True, and the miss is still said."""
    (tmp_path / "target.py").write_text(AMBIGUOUS_SRC)
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": "    return 1",
                                                "replace": "    return 2"}]))
    report = "\n".join(lines)
    assert ok is True, report
    assert "ambiguous" in report, report
    assert "not checked" in report, report


# ---------------------------------------------------------------------------
# DIFFERENTIAL: the gate refuses NEW breakage, not pre-existing breakage.
#
# Both directions. Making the check absolute again (dropping `_parsed_before`) turns the
# first red; dropping the check entirely turns the second red.
# ---------------------------------------------------------------------------

PREBROKEN = 'ok = 1\n    bad_indent = 2\ntail = 3\n'


def test_a_preexisting_syntax_error_is_not_blamed_on_this_plan(gate, tmp_path, monkeypatch):
    """MUTATION PROOF (differential): make the parse check absolute and this goes red."""
    src = tmp_path / "pre.py"
    src.write_text(PREBROKEN)
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": "tail = 3", "replace": "tail = 4"}],
                                    path="pre.py"))
    report = "\n".join(lines)
    assert ok is True, report
    assert "PRE" in report, report
    assert "BREAK" not in report, report


def test_a_preexisting_break_is_still_reported_not_silently_passed(gate, tmp_path, monkeypatch):
    """A withheld refusal that printed nothing would be a silent pass. It must be said."""
    (tmp_path / "pre.py").write_text(PREBROKEN)
    monkeypatch.chdir(tmp_path)
    _ok, lines = gate.check(edit_ops(tmp_path, [{"find": "tail = 3", "replace": "tail = 4"}],
                                     path="pre.py"), quiet=True)
    report = "\n".join(lines)
    assert "already did not parse" in report.lower() or "PRE" in report, report


def test_a_plan_may_repair_an_already_broken_file(gate, tmp_path, monkeypatch):
    """The motivating consequence: the Iron Law path can be used to FIX a syntax error."""
    (tmp_path / "pre.py").write_text(PREBROKEN)
    monkeypatch.chdir(tmp_path)
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": "    bad_indent = 2",
                                                "replace": "bad_indent = 2"}], path="pre.py"))
    report = "\n".join(lines)
    assert ok is True, report
    assert "OK" in report, report


def test_a_created_file_has_no_baseline_and_is_judged_absolutely(gate, tmp_path, monkeypatch):
    """MUTATION PROOF: exempt created files too and this goes red."""
    monkeypatch.chdir(tmp_path)
    cfg = write_ops(tmp_path, [{"type": "file_create", "path": "fresh.py",
                                "content": 'x = f"{\n'}])
    ok, lines = gate.check(cfg)
    assert ok is False, "\n".join(lines)
    assert "BREAK" in "\n".join(lines)


def test_a_new_break_in_a_file_that_did_parse_is_still_refused(gate, tmp_path, target):
    """The differential exemption must be scoped to files that were ALREADY broken."""
    ok, lines = gate.check(edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}]))
    assert ok is False, "\n".join(lines)
    assert "BREAK" in "\n".join(lines)
    assert "PRE" not in "\n".join(lines)


# -------------------------------------------- a miss names its own file, structurally

def test_a_colon_in_one_path_does_not_hide_a_break_in_another(gate, tmp_path, monkeypatch):
    """MUTATION PROOF: rebuild `unresolved` as `{m.split(':', 1)[0] for m in misses}` and
    this goes green on a plan that breaks a file -- `ok` flips to True and the BREAK line
    vanishes, replaced by a "not checked" line about the wrong file.

    A colon is legal in a filename on macOS and on Linux. Split on its first colon,
    `mod.py:v1: anchor not found ...` yields the key `mod.py` -- a DIFFERENT file that this
    plan really does break.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mod.py:v1").write_text("x = 1\n")
    (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
    ok, lines = gate.check(write_ops(tmp_path, [
        {"type": "code_edit", "path": "mod.py:v1",
         "edits": [{"find": "nowhere", "replace": "y = 2"}]},
        {"type": "code_edit", "path": "mod.py",
         "edits": [{"find": "    return 1", "replace": "    return f'{'"}]}]))
    blob = "\n".join(lines)
    assert ok is False, blob
    assert "BREAK mod.py:" in blob, blob
    assert "mod.py not checked" not in blob, blob


def test_the_withheld_verdict_lands_on_the_path_that_missed(gate, tmp_path, monkeypatch):
    """The other direction. The colon-bearing file is the one withheld; its clean sibling
    is still checked.

    MUTATION PROOF: with the string-split version `a:b.py` is absent from `unresolved`
    (the key is `a`), so it is reported "OK ... still parses" -- a false claim about a file
    whose anchor never landed -- and the `not checked` assertion goes red.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a:b.py").write_text("x = 1\n")
    (tmp_path / "a.py").write_text("y = 1\n")
    ok, lines = gate.check(write_ops(tmp_path, [
        {"type": "code_edit", "path": "a:b.py",
         "edits": [{"find": "nowhere", "replace": "z = 2"}]},
        {"type": "code_edit", "path": "a.py",
         "edits": [{"find": "y = 1", "replace": "y = 2"}]}]))
    blob = "\n".join(lines)
    assert ok is True, blob
    assert "?     a:b.py not checked" in blob, blob
    assert "OK    a.py still parses" in blob, blob
    assert "OK    a:b.py" not in blob, blob


def test_the_miss_line_text_is_unchanged_by_the_structured_record(gate, tmp_path, target):
    """Carrying the pair must not change one byte of what is printed. Print the tuple
    (`'MISS  %s' % miss`), drop the ': ', or swap the two halves, and this goes red.
    """
    _, lines = gate.check(edit_ops(tmp_path, [{"find": "nowhere at all", "replace": "x = 1"}]))
    assert "MISS  target.py: anchor not found: 'nowhere at all'" in lines, lines


def test_a_reason_with_colons_of_its_own_still_names_the_right_path(gate, tmp_path,
                                                                    monkeypatch):
    """The ambiguity reason carries colons of its own. Under the old split those were
    harmless -- the FIRST colon was the path delimiter -- and that must stay true.

    MUTATION PROOF: append `(reason, path)` instead of `(path, reason)` and both
    assertions go red.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "amb.py").write_text("x = 1\nx = 1\n")
    _, lines = gate.check(edit_ops(tmp_path, [{"find": "x = 1", "replace": "x = 2"}],
                                   path="amb.py"))
    blob = "\n".join(lines)
    assert "MISS  amb.py: anchor is ambiguous" in blob, blob
    assert "?     amb.py not checked" in blob, blob


def test_simulate_carries_the_path_as_data_not_a_formatted_string(gate, tmp_path,
                                                                  monkeypatch):
    """`simulate`'s second value is the contract the withheld-verdict set is built from, so
    it is pinned directly: the path comes back as itself, colons and all.

    MUTATION PROOF: go back to appending `'%s: reason' % path` and the unpacking below
    raises ValueError, so this goes red on the contract as well as on the behaviour above.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "c:d.py").write_text("x = 1\n")
    cfg = write_ops(tmp_path, [{"type": "code_edit", "path": "c:d.py",
                                "edits": [{"find": "nowhere", "replace": "y = 2"}]}])
    with open(cfg, encoding="utf-8") as fh:
        _files, misses, _created, _deleted, _named = gate.simulate(json.load(fh))
    assert [p for p, _r in misses] == ["c:d.py"], misses


# ----------------------------------------- one path identity: the gate's key IS the executor's

def test_a_dot_slash_alias_is_one_file_to_the_gate_as_it_is_to_the_executor(gate, tmp_path,
                                                                            monkeypatch):
    """The reviewer's C1 reproduction. `x.py` then `./x.py`: the second edit's anchor exists
    only in the text the FIRST one writes, so keying on the raw path made the alias a second,
    freshly-read file -- MISS, verdict withheld, exit 0 -- while the executor threaded both
    edits and left `B = (` on disk.

    MUTATION PROOF: drop `_canon` from `simulate` (key on `op['path']`) and this goes red:
    `ok` becomes True and the report says `not checked` instead of BREAK.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("A = 1\n")
    cfg = write_ops(tmp_path, [
        {"type": "code_edit", "path": "x.py",
         "edits": [{"find": "A = 1", "replace": "A = 2\nB = 3"}]},
        {"type": "code_edit", "path": "./x.py", "edits": [{"find": "B = 3", "replace": "B = ("}]}])
    ok, lines = gate.check(cfg)
    blob = "\n".join(lines)
    assert ok is False, blob
    assert "BREAK x.py" in blob, blob
    assert "not checked" not in blob, blob


def test_the_dot_slash_alias_refusal_also_stops_the_real_executor(tmp_path, monkeypatch):
    """End to end, against the writer itself: the tree must be byte-identical afterwards.

    MUTATION PROOF: revert `_canon` AND remove the `_aliases` loop and this goes red -- the
    executor exits 0 and `x.py` holds unparseable text. Either mechanism alone refuses this
    plan (with `_canon` reverted the two spellings become an ALIAS group), which is why the
    gate-level test above asserts BREAK specifically: that one pins `_canon` on its own.
    """
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "x.py"
    src.write_text("A = 1\n")
    cfg = write_ops(tmp_path, [
        {"type": "code_edit", "path": "x.py",
         "edits": [{"find": "A = 1", "replace": "A = 2\nB = 3"}]},
        {"type": "code_edit", "path": "./x.py", "edits": [{"find": "B = 3", "replace": "B = ("}]}])
    res = _run_executor(tmp_path, cfg, "--no-approval")
    assert res.returncode == 1, res.stdout
    assert "PARSE GATE" in res.stdout, res.stdout
    assert src.read_text() == "A = 1\n", "the tree was mutated despite the refusal"


def test_the_canonical_key_is_the_executors_own_function(gate, tmp_path, monkeypatch):
    """Parity, not similarity: the key must BE `os.path.relpath`, which is what
    execute-json-ops.py:684 uses. A repo reached through a symlinked parent must not yield
    `../..` garbage -- relpath is lexical, so it cannot.

    MUTATION PROOF: key on `os.path.realpath` and the second assertion goes red under a
    symlinked parent; key on `normpath` alone and `nested/../x.py` still differs.
    """
    real = tmp_path / "real"
    (real / "pkg").mkdir(parents=True)
    (tmp_path / "link").symlink_to(real)
    monkeypatch.chdir(tmp_path / "link")
    for spelled in ("x.py", "./x.py", "pkg/../x.py"):
        assert gate._canon(spelled) == os.path.relpath(spelled) == "x.py", spelled
    assert gate._canon("pkg/m.py") == "pkg/m.py"


def test_a_miss_on_an_alias_names_the_spelling_the_author_wrote(gate, tmp_path, monkeypatch):
    """The key groups; the spelling has to reach the human. Both, not one.

    MUTATION PROOF: drop the `written in this config as` branch from `_apply._miss` and the
    second assertion goes red; render the miss under the spelling instead of the key and the
    first goes red.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("A = 1\n")
    _ok, lines = gate.check(write_ops(tmp_path, [
        {"type": "code_edit", "path": "./x.py", "edits": [{"find": "nowhere", "replace": "z = 1"}]}]))
    blob = "\n".join(lines)
    assert "MISS  x.py:" in blob, blob
    assert "./x.py" in blob, blob


def test_a_symlink_alias_is_refused_because_neither_side_models_it(gate, tmp_path, monkeypatch):
    """The reviewer's second C1 reproduction. One inode, two relpath keys: the gate reads the
    link before the executor's earlier write, and the executor's `os.replace` replaces the
    link rather than following it. Measured before this fix: gate exit 0, `sym.py`
    unparseable. Refused, not withheld -- withholding exits 0.

    MUTATION PROOF: remove the `_aliases` loop from `check` and this goes red (ok is True).
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("A = 1\n")
    (tmp_path / "sym.py").symlink_to(tmp_path / "pkg" / "m.py")
    ok, lines = gate.check(write_ops(tmp_path, [
        {"type": "code_edit", "path": "pkg/m.py",
         "edits": [{"find": "A = 1", "replace": "A = 2\nB = 3"}]},
        {"type": "code_edit", "path": "sym.py", "edits": [{"find": "B = 3", "replace": "B = ("}]}])
    )
    blob = "\n".join(lines)
    assert ok is False, blob
    assert "ALIAS" in blob, blob
    assert "pkg/m.py" in blob and "sym.py" in blob, blob


def test_the_symlink_refusal_also_stops_the_real_executor(tmp_path, monkeypatch):
    """MUTATION PROOF: remove the `_aliases` loop and this goes red -- the executor exits 0
    and leaves `sym.py` as a regular file holding unparseable text."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    m = tmp_path / "pkg" / "m.py"
    m.write_text("A = 1\n")
    (tmp_path / "sym.py").symlink_to(m)
    cfg = write_ops(tmp_path, [
        {"type": "code_edit", "path": "pkg/m.py",
         "edits": [{"find": "A = 1", "replace": "A = 2\nB = 3"}]},
        {"type": "code_edit", "path": "sym.py", "edits": [{"find": "B = 3", "replace": "B = ("}]}])
    res = _run_executor(tmp_path, cfg, "--no-approval")
    assert res.returncode == 1, res.stdout
    assert m.read_text() == "A = 1\n"
    assert (tmp_path / "sym.py").is_symlink(), "the link was replaced despite the refusal"


# ------------------------------------------- one normaliser: the schema the executor will run

def test_a_config_carrying_both_schema_keys_is_simulated_as_the_executor_runs_it(
        gate, tmp_path, monkeypatch):
    """The reviewer's C2 reproduction. `normalize_config` discards `files` whenever
    `operations` is present; this module used to apply both, so the modern anchor counted
    twice, the verdict was withheld and the gate exited 0 while the executor wrote
    unparseable text. Reachable on a default install: without `jsonschema` the validator
    reports APPROVED on this exact config.

    MUTATION PROOF: process `ops['files']` in addition to `operations` (the old behaviour)
    and this goes red -- the anchor becomes ambiguous, `ok` returns True and BREAK is absent.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "y.py").write_text("A = 1\nB = 1\n")
    cfg = tmp_path / "ops.json"
    cfg.write_text(json.dumps({
        "plan": "both",
        "files": [{"path": "y.py", "edits": [{"find": "B = 1", "replace": "A = 1"}]}],
        "operations": [{"type": "code_edit", "path": "y.py",
                        "edits": [{"find": "A = 1", "replace": "A = ("}]}]}))
    ok, lines = gate.check(str(cfg))
    blob = "\n".join(lines)
    assert ok is False, blob
    assert "BREAK y.py" in blob, blob
    assert "ambiguous" not in blob, blob


def test_the_both_keys_refusal_also_stops_the_real_executor(tmp_path, monkeypatch):
    """MUTATION PROOF: restore the legacy loop in `simulate` and this goes red -- the
    executor exits 0 and `y.py` is left as `A = (`."""
    monkeypatch.chdir(tmp_path)
    y = tmp_path / "y.py"
    y.write_text("A = 1\nB = 1\n")
    cfg = tmp_path / "ops.json"
    cfg.write_text(json.dumps({
        "plan": "both",
        "files": [{"path": "y.py", "edits": [{"find": "B = 1", "replace": "A = 1"}]}],
        "operations": [{"type": "code_edit", "path": "y.py",
                        "edits": [{"find": "A = 1", "replace": "A = ("}]}]}))
    res = _run_executor(tmp_path, str(cfg), "--no-approval")
    assert res.returncode == 1, res.stdout
    assert "PARSE GATE" in res.stdout, res.stdout
    assert y.read_text() == "A = 1\nB = 1\n"


def test_deleting_a_target_and_editing_its_link_is_refused(tmp_path, monkeypatch):
    """Round-2 MINOR. `_aliases` saw only `files`, so a file_delete of a symlink's target plus
    a code_edit of the link printed `OK sym.py still parses` and exited 0. The executor then
    aborts on the dangling link and rolls back -- fail-closed, but the gate pronounced on a
    plan it cannot model.

    Mutation that reds this: pass `files` alone to `_aliases` instead of the union with
    `deleted`.
    """
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'm.py').write_text('A = 1\n', encoding='utf-8')
    try:
        os.symlink(str(pkg / 'm.py'), str(tmp_path / 'sym.py'))
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip('this platform cannot create symlinks here')
    cfg = write_ops(tmp_path, [
        {'type': 'file_delete', 'path': 'pkg/m.py', 'reason': 'probe'},
        {'type': 'code_edit', 'path': 'sym.py',
         'edits': [{'find': 'A = 1', 'replace': 'A = 2'}]}])
    ok, lines = load_gate().check(cfg)
    body = '\n'.join(lines)
    assert ok is False, body
    assert 'ALIAS' in body, body


def test_the_gate_normaliser_agrees_with_the_executors(tmp_path):
    """One rule, two entry points. The CLI's `_normalize` must produce the same `operations`
    list the executor's `normalize_config` does, or the standalone verdict describes a
    different plan than the run.

    MUTATION PROOF: flip `_normalize`'s precedence (convert `files` even when `operations`
    is present) and the first case goes red.
    """
    gate = load_gate()
    spec = importlib.util.spec_from_file_location("ck_executor", str(EXECUTOR))
    assert spec is not None and spec.loader is not None
    ex = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))          # the executor imports its sibling `shared`
    try:
        spec.loader.exec_module(ex)
    finally:
        sys.path.remove(str(SCRIPTS))
    legacy = {"plan": "p", "files": [{"path": "a.py", "edits": [{"find": "x", "replace": "y"}]}]}
    both = dict(legacy, operations=[{"type": "code_edit", "path": "b.py", "edits": []}])
    modern = {"plan": "p", "operations": [{"type": "code_edit", "path": "b.py", "edits": []}]}
    for cfg in (legacy, both, modern):
        mine = gate._normalize(cfg)["operations"]
        theirs = (ex.normalize_config(cfg) or {}).get("operations")
        assert mine == theirs, (cfg, mine, theirs)


# -------------------------------------------------------------- the remaining review findings

def test_a_crashing_checker_fails_the_run_closed(tmp_path, target):
    """The vacuous branch. Inverting `check_parses`'s `except Exception ... return False` to
    `return True` left all 54 tests green, so the fail-closed claim was unproven.

    MUTATION PROOF: return True from that handler and this goes red -- the executor exits 0
    and writes the (perfectly valid) edit.
    """
    engine = tmp_path / "engine.py"
    engine.write_text(EXECUTOR.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "ops_precompile.py").write_text(
        'raise RuntimeError("the checker itself is broken")\n', encoding="utf-8")
    before = target.read_text()
    cfg = edit_ops(tmp_path, [{"find": FIND, "replace": '    msg = f"hello {name}"'}])
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS))
    res = subprocess.run([sys.executable, str(engine), cfg, "--no-approval"],
                         cwd=str(tmp_path), capture_output=True, text=True, timeout=120, env=env)
    assert res.returncode == 1, res.stdout
    assert "parse checker itself failed to run" in res.stdout, res.stdout
    assert "parse-gate" in res.stdout, res.stdout
    assert target.read_text() == before, "the tree was mutated by a run the gate could not check"


def test_the_break_line_names_the_grammar_it_judged_with(gate, tmp_path, target):
    """A verdict from the interpreter's grammar must say so: on the 3.9 floor a valid `match`
    statement is refused as invalid syntax, and the author is owed that context.

    MUTATION PROOF: drop the version from the BREAK line and this goes red.
    """
    _ok, lines = gate.check(edit_ops(tmp_path, [{"find": FIND, "replace": BREAKS}]))
    blob = "\n".join(lines)
    assert "BREAK" in blob and "CPython %d.%d" % sys.version_info[:2] in blob, blob


def test_the_pre_line_does_not_claim_the_edits_are_innocent(gate, tmp_path, monkeypatch):
    """It cannot know that: a plan may repair the old break and add a new one, and this gate
    parses only the final text.

    MUTATION PROOF: restore "The edits here are not the cause" and this goes red.
    """
    (tmp_path / "pre.py").write_text(PREBROKEN)
    monkeypatch.chdir(tmp_path)
    _ok, lines = gate.check(edit_ops(tmp_path, [{"find": "tail = 3", "replace": "tail = 4"}],
                                     path="pre.py"))
    blob = "\n".join(lines)
    assert "PRE" in blob, blob
    assert "not the cause" not in blob, blob
    assert "cannot be told apart" in blob, blob


def test_delete_is_modelled_only_on_a_literal_true(gate, tmp_path, target):
    """`execute_code_edit` requires `edit.get('delete') is True`; a truthy `"delete": "yes"`
    is no action there, so modelling it as a deletion describes a splice that never happens.

    MUTATION PROOF: go back to `edit.get('delete')` and this goes red -- the edit is modelled
    as a deletion, no miss is recorded, and `names no action` is absent.
    """
    _ok, lines = gate.check(edit_ops(tmp_path, [{"find": FIND, "delete": "yes"}]))
    assert any("names no action" in line for line in lines), lines
    ok, _ = gate.check(edit_ops(tmp_path, [{"find": FIND, "delete": True}]))
    assert ok is True


def test_run_command_writes_are_declared_unmodelled(gate, tmp_path, target):
    """A verdict that covered nothing about a command's writes must not read as if it covered
    everything.

    MUTATION PROOF: drop the note and this goes red.
    """
    cfg = write_ops(tmp_path, [
        {"type": "code_edit", "path": "target.py",
         "edits": [{"find": FIND, "replace": '    msg = f"hello {name}"'}]},
        {"type": "run_command", "command": ["python3", "-V"], "reason": "regenerate something"}])
    ok, lines = gate.check(cfg)
    blob = "\n".join(lines)
    assert ok is True, blob
    assert "run_command" in blob and "not modelled" in blob, blob


# --------------------------------------- fold invariance: ONE identity for every spelling
#
# THE INVARIANT IS WRITTEN BEFORE THE FIX, AND THAT ORDER IS THE POINT. Four example-shaped
# tests already stood here -- `./x.py`, a symlink, `X.py`, a hardlink -- and each pinned one
# SPELLING of one defect. Three consecutive review rounds then found the same class again,
# each time through a spelling nobody had enumerated, the last of them every not-yet-existing
# path. Examples cannot close a class. So these assert the PROPERTY: whatever spelling names
# a file, the gate's identity for it is one value.
#
# A FOLD THE FILESYSTEM DOES NOT PERFORM SKIPS WITH ITS REASON, IT DOES NOT PASS. On a
# case-sensitive filesystem `x.py` and `X.py` really are two files and collapsing them would
# be the bug. A row that went green on every filesystem would not be testing identity at all.


def _fold_tree(root):
    """Every alias shape in one tree: {fold: (spelling_a, spelling_b, skip_reason_or_None)}.

    The pairs cover BOTH sides of the round-3 hole: a path already on disk (an inode can be
    read) and a path this plan would create (none can), for every fold.
    """
    (root / "sub").mkdir()
    (root / "real").mkdir()
    (root / "pkg").mkdir()
    (root / "x.py").write_text("A = 1\n", encoding="utf-8")
    (root / "real" / "r.py").write_text("A = 1\n", encoding="utf-8")
    nfc = unicodedata.normalize("NFC", "café.py")
    nfd = unicodedata.normalize("NFD", "café.py")
    (root / nfc).write_text("A = 1\n", encoding="utf-8")
    new_nfc = unicodedata.normalize("NFC", "crème.py")
    new_nfd = unicodedata.normalize("NFD", "crème.py")

    case_skip = None if (root / "X.py").exists() else (
        "case-sensitive filesystem: x.py and X.py are genuinely two files")
    norm_skip = None if (root / nfd).exists() else (
        "this filesystem does not normalise unicode: NFC and NFD are genuinely two files")
    link_skip = None
    try:
        os.symlink(str(root / "x.py"), str(root / "sym.py"))
        os.symlink(str(root / "real"), str(root / "linkdir"))
        os.symlink(str(root / "pkg" / "m.py"), str(root / "dangling.py"))
    except (OSError, NotImplementedError, AttributeError):
        link_skip = "this platform cannot create symlinks here"
    hard_skip = None
    try:
        os.link(str(root / "x.py"), str(root / "hard.py"))
    except (OSError, AttributeError):
        hard_skip = "this filesystem does not support hardlinks"

    return {
        # case -- existing and not-yet-existing, in the leaf and in a directory component
        "case-existing-file": ("x.py", "X.py", case_skip),
        "case-existing-dir": ("real/r.py", "REAL/r.py", case_skip),
        "case-new-file": ("new.py", "New.py", case_skip),
        "case-new-dir": ("sub/n.py", "SUB/n.py", case_skip),
        # unicode normalisation, with a real accented name
        "nfc-nfd-existing": (nfc, nfd, norm_skip),
        "nfc-nfd-new": (new_nfc, new_nfd, norm_skip),
        # symlinks: a linked FILE, a linked DIRECTORY component, and a DANGLING link whose
        # target this same plan would create
        "symlink-file": ("x.py", "sym.py", link_skip),
        "symlink-dir-existing": ("real/r.py", "linkdir/r.py", link_skip),
        "symlink-dir-new": ("real/n.py", "linkdir/n.py", link_skip),
        "dangling-link-vs-target": ("dangling.py", "pkg/m.py", link_skip),
        "hardlink": ("x.py", "hard.py", hard_skip),
        # the lexical folds the earlier rounds already closed -- kept so a rewrite of the
        # identity cannot quietly drop them
        "lexical-dot-slash": ("x.py", "./x.py", None),
        "lexical-double-slash": ("x.py", ".//x.py", None),
        "lexical-dotdot": ("x.py", "sub/../x.py", None),
        "lexical-abs-vs-rel": ("x.py", str(root / "x.py"), None),
        "lexical-trailing-slash": ("real", "real/", None),
        "lexical-new-dot-slash": ("new.py", "./new.py", None),
    }


FOLDS = [
    "case-existing-file", "case-existing-dir", "case-new-file", "case-new-dir",
    "nfc-nfd-existing", "nfc-nfd-new",
    "symlink-file", "symlink-dir-existing", "symlink-dir-new", "dangling-link-vs-target",
    "hardlink",
    "lexical-dot-slash", "lexical-double-slash", "lexical-dotdot", "lexical-abs-vs-rel",
    "lexical-trailing-slash", "lexical-new-dot-slash",
]


#: Codepoints where FULL Unicode case folding and the simple lowercase mapping DISAGREE.
#: DERIVED FROM THE PROPERTY, NOT FROM A PAST BUG. The first version of this list filtered on
#: `casefold() != lower()` -- the signature of the defect being fixed at the time -- and a
#: review then showed that 98 codepoints the kernel folds above U+11000 (Warang Citi, Adlam,
#: Medefaidrin) could never reach the oracle at all, because they fold but their casefold and
#: lowercase agree. A mutation disabling folding above U+11000 survived the whole suite. That
#: is the same blind spot the round before had found in the twin derivation, one level up: a
#: check built from the last bug cannot see the next one.
#:
#: So the candidate is any codepoint that varies under ANY case or normalisation operation --
#: which is the property `_fold` claims to be invariant under -- across the whole assigned
#: plane. Unassigned, surrogate and private-use categories are excluded because a filesystem
#: has nothing to say about them. Built at import time, no I/O.
FOLD_DIVERGENT = [c for c in range(0x20, 0x110000)
                  if unicodedata.category(chr(c)) not in ('Cs', 'Cn', 'Co')
                  and chr(c).isprintable() and chr(c) not in ('/', '\x00', '.')
                  and (chr(c).upper() != chr(c) or chr(c).lower() != chr(c)
                       or chr(c).casefold() != chr(c)
                       or unicodedata.normalize('NFD', chr(c)) != chr(c))]


def test_the_identity_agrees_with_the_kernel_on_every_fold_it_performs(gate, tmp_path,
                                                                      monkeypatch):
    """THE MECHANICAL CHECK, and the reason it exists: five spellings escaped five
    hand-written fold lists. `relpath` missed `./x.py`; `realpath` missed the symlink;
    `(st_dev, st_ino)` missed not-yet-existing paths; those never reached the alias check at
    all; and `NFC+lower()` missed 101 codepoints the filesystem folds. Every one of those
    lists was written by enumerating what a person could think of, which is why the next
    spelling always walked through.

    So this does not enumerate spellings. It asks the KERNEL which pairs name one file --
    `st_ino`, the same question `_case_insensitive` asks -- and asserts `_identity` agrees on
    every pair the kernel folded. A sixth spelling in this dimension cannot pass.

    MUTATION: `_fold` back to `component.lower()` and this reds with a list of the codepoints
    the filesystem folds and the gate does not (101 of them on APFS). On a case-sensitive
    filesystem the kernel folds nothing, the oracle finds no pairs to check, and the test
    skips rather than passing for the wrong reason.
    """
    monkeypatch.chdir(tmp_path)
    probe = tmp_path / 'probe'
    probe.mkdir()
    folded_by_kernel = []
    for code in FOLD_DIVERGENT:
        base = chr(code)
        # EVERY spelling, not just `casefold`. The previous version derived twins from
        # `casefold()` alone and then skipped any whose fold was not one character -- which
        # discarded U+0390 and the ten like it, U+00DF, U+FB01 and U+1E9E: the entire
        # multi-character expansion branch, which is exactly where the bug was. The kernel
        # folds many-to-one over PAIRS, so the pairs must be formed the way a filename varies.
        twins = {base.upper(), base.lower(), base.casefold(), base.title(), base.swapcase(),
                 unicodedata.normalize('NFC', base), unicodedata.normalize('NFD', base)}
        first = probe / ('n%s.py' % base)
        try:
            first.write_text('A = 1\n', encoding='utf-8')
            own = os.stat(str(first))
        except (OSError, ValueError, UnicodeError):
            continue
        for other in twins:
            if not other or other == base:
                continue
            try:
                twin = os.stat(str(probe / ('n%s.py' % other)))
            except (OSError, ValueError, UnicodeError):
                continue
            # INODE EQUALITY, not `if twin.st_ino`. Any successful stat was scored as a fold,
            # so the assertion carrying the whole property did not assert it.
            if (twin.st_dev, twin.st_ino) == (own.st_dev, own.st_ino):
                folded_by_kernel.append((base, other))
        try:
            first.unlink()
        except OSError:  # silent-ok: tidying a probe file inside tmp_path, which pytest removes anyway; a failed unlink must not fail a test about fold identity
            pass
    if not folded_by_kernel:
        pytest.skip('this filesystem folds none of the divergent codepoints (case-sensitive)')
    disagreed = []
    for base, other in folded_by_kernel:
        a, b = 'new%s.py' % base, 'new%s.py' % other
        if gate._identity(a) != gate._identity(b):
            disagreed.append('U+%04X vs %r' % (ord(base), other))
    assert not disagreed, (
        'the filesystem folds these codepoints and the gate does not, so one file gets two '
        'identities: %s' % ', '.join(disagreed))


def test_dotdot_through_a_symlinked_directory_is_one_identity(gate, tmp_path, monkeypatch):
    """`abspath` runs `normpath` FIRST, so it collapses `..` before any symlink to its left is
    resolved: `deep/../x.py` with `deep -> a/b/c` resolved to the top level rather than to
    `a/b/`, and split identity from `a/b/x.py`.

    A review found the fix correct but UNPINNED -- reverting it left 111 tests green, the
    fourth fix in this series with no behavioural binding.

    MUTATION: restore `os.path.realpath(os.path.abspath(path))` and this reds.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'a' / 'b' / 'c').mkdir(parents=True)
    (tmp_path / 'a' / 'b' / 'x.py').write_text('A = 1\n', encoding='utf-8')
    (tmp_path / 'x.py').write_text('DECOY = 1\n', encoding='utf-8')
    try:
        os.symlink(str(tmp_path / 'a' / 'b' / 'c'), str(tmp_path / 'deep'))
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip('this platform cannot create symlinks here')
    assert gate._identity('deep/../x.py') == gate._identity('a/b/x.py'), (
        'deep/../x.py resolves into a/b/, so it and a/b/x.py are one file')
    assert gate._identity('deep/../x.py') != gate._identity('x.py'), (
        'the top-level decoy is a different file and must keep a different identity')


def test_creating_one_spelling_and_editing_another_is_refused(gate, tmp_path, monkeypatch):
    """The shape the fifth return value (`named`) exists for, pinned directly.

    A review found the parametrised test could not catch it: its helper picks `file_create`
    for any path not on disk, so when BOTH spellings are missing it emits two creates -- and
    `created` was already in the alias union. Dropping `named` from that union therefore left
    108 tests green while reopening the original break. The asymmetric shape is the one that
    matters: create under one spelling, EDIT under the other.

    MUTATION: remove `named` from the `_aliases(...)` union, or delete `named.add(path)`.
    Either reds this; before it existed, both left the suite green.
    """
    monkeypatch.chdir(tmp_path)
    if _fold_tree(tmp_path)['case-new-file'][2] is not None:
        pytest.skip('this filesystem does not fold case for new files')
    cfg = write_ops(tmp_path, [
        {'type': 'file_create', 'path': 'fresh.py', 'content': 'A = 1\n'},
        {'type': 'code_edit', 'path': 'FRESH.py',
         'edits': [{'find': 'A = 1', 'replace': 'A = ('}]}])
    ok, lines = load_gate().check(cfg)
    body = '\n'.join(lines)
    assert ok is False, body
    assert 'ALIAS' in body, body


def test_a_case_sensitive_device_keeps_the_two_spellings_apart(gate, tmp_path, monkeypatch):
    """The other direction, which no test covered: where the device does NOT fold case, two
    spellings really are two files and folding them would be a false refusal.

    Driven by injecting the probe's answer, because a case-sensitive mount is not available
    on the author's machine -- which is exactly why this branch had never executed.

    MUTATION: make `_fold` fold case unconditionally (ignore the probe) and this reds.
    """
    monkeypatch.chdir(tmp_path)
    gate_mod = load_gate()
    monkeypatch.setattr(gate_mod, '_case_insensitive', lambda existing, st: False)
    gate_mod._CASE_FOLD.clear()
    try:
        assert gate_mod._identity('newfile.py') != gate_mod._identity('NEWFILE.py'), (
            'on a case-sensitive device these are two files and must keep two identities')
    finally:
        gate_mod._CASE_FOLD.clear()


@pytest.mark.parametrize("fold", FOLDS)
def test_the_identity_is_invariant_under_every_alias_spelling(gate, tmp_path, monkeypatch,
                                                              fold):
    """One file, two spellings, ONE identity -- for every fold this filesystem performs.

    HEADLINE MUTATION: replace `_identity`'s body with the lexical fallback it replaced
    (`return ('path', os.path.realpath(p))`) and this reds for case-existing-file,
    case-existing-dir, case-new-file, case-new-dir, nfc-nfd-existing, nfc-nfd-new and
    hardlink -- seven rows, not one, which is the whole reason this is a property and not
    another example. Drop only the ancestor walk (stat-or-realpath, round 3's shape) and the
    four not-yet-existing case rows plus nfc-nfd-new red. Drop `unicodedata.normalize` and
    both nfc-nfd rows red. Drop `os.path.realpath` from the first line and
    symlink-dir-existing, symlink-dir-new and dangling-link-vs-target red.
    """
    monkeypatch.chdir(tmp_path)
    a, b, skip = _fold_tree(tmp_path)[fold]
    if skip:
        pytest.skip(skip)
    assert gate._identity(a) == gate._identity(b), (
        "%s: %r and %r name one file and got two identities (%r vs %r)"
        % (fold, a, b, gate._identity(a), gate._identity(b)))


def test_the_identity_keeps_genuinely_distinct_paths_distinct(gate, tmp_path, monkeypatch):
    """The failure direction that would block every future change. Two files that really are
    two files -- including two that do not exist yet, which is where an over-eager fold would
    do its damage -- must never share an identity.

    MUTATION: return a constant for any path that cannot be stat'd (round 3's shape, taken
    one step further) and the new-file rows red.
    """
    monkeypatch.chdir(tmp_path)
    _fold_tree(tmp_path)
    for a, b in [("x.py", "real/r.py"),          # two files on disk
                 ("n1.py", "n2.py"),             # two files this plan would create
                 ("sub/n.py", "real/n.py"),      # one new name under two real directories
                 ("x.py", "new.py")]:            # one on disk, one not
        assert gate._identity(a) != gate._identity(b), (a, b, gate._identity(a))


@pytest.mark.parametrize("fold", FOLDS)
def test_every_alias_spelling_is_refused_by_the_gate_not_half_checked(gate, tmp_path,
                                                                      monkeypatch, fold):
    """The invariant, carried through to the verdict the executor consumes.

    An identity that collapses is worth nothing if the refusal does not follow, and before
    this change the follow-through had its own hole: a `code_edit` of a not-yet-existing
    spelling was recorded as a MISS and `continue`d, so that path never reached the alias
    check at all. The set is now every path the config NAMES.

    MUTATION: pass `set(files) | deleted | created` to `_aliases` instead of `named` and the
    rows whose second spelling is a modelled-away miss red. Remove the `_aliases` loop from
    `check` and every row reds.
    """
    monkeypatch.chdir(tmp_path)
    a, b, skip = _fold_tree(tmp_path)[fold]
    if skip:
        pytest.skip(skip)
    if a.endswith("/") or os.path.isdir(a):
        pytest.skip("a directory is not an ops target; this fold is identity-level only")

    def op(path):
        # A path already on disk is edited; one that is not is created. Uniform across folds,
        # and it is the shape of the round-3 reproduction either way.
        if os.path.exists(path):
            return {"type": "code_edit", "path": path,
                    "edits": [{"find": "A = 1", "replace": "A = 2"}]}
        return {"type": "file_create", "path": path, "content": "A = 1\n"}

    ok, lines = gate.check(write_ops(tmp_path, [op(a), op(b)]))
    body = "\n".join(lines)
    if gate._canon(a) == gate._canon(b):
        # THE TWO KEYS, VISIBLE IN THE VERDICT. `_canon` -- the WRITER's key -- already
        # collapses this fold, so the plan is ONE file to the gate exactly as it is to the
        # executor and there is nothing left to refuse. The claim for these rows is that the
        # plan was modelled ONCE, not that it was rejected; a row that demanded a refusal
        # here would be demanding a false positive.
        assert "ALIAS" not in body, body
        named = [ln for ln in lines if ln.startswith(("OK", "BREAK", "?", "skip"))]
        assert len(named) == 1, body
        return
    assert ok is False, "%s: %s" % (fold, body)
    assert "ALIAS" in body, body
    # The message must name a path the reader can open, never a bare inode number.
    assert "names one file (" in body, body
    assert not re.search(r"names one file \(\d+\)", body), body


def test_the_gate_still_passes_a_plan_of_distinct_and_new_files(gate, tmp_path, monkeypatch):
    """Over-refusal, at the verdict. Two distinct files edited and two new files created --
    the everyday plan -- must still pass.

    This is the assertion the 601-config sweep of `.claude/plans/archive` generalises: zero
    of them is flagged by `_aliases`, before this change or after it.

    MUTATION: fold every not-yet-existing path to one key and the two file_creates become an
    ALIAS group, turning every ordinary two-file plan into a refusal.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "p.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "q.py").write_text("B = 1\n", encoding="utf-8")
    ok, lines = gate.check(write_ops(tmp_path, [
        {"type": "code_edit", "path": "p.py", "edits": [{"find": "A = 1", "replace": "A = 2"}]},
        {"type": "code_edit", "path": "q.py", "edits": [{"find": "B = 1", "replace": "B = 2"}]},
        {"type": "file_create", "path": "new1.py", "content": "C = 1\n"},
        {"type": "file_create", "path": "sub/new2.py", "content": "D = 1\n"}]))
    body = "\n".join(lines)
    assert ok is True, body
    assert "ALIAS" not in body, body


def test_the_case_probe_writes_nothing_into_the_tree(gate, tmp_path, monkeypatch):
    """A read-only gate that dropped a probe file into the author's checkout would be a worse
    defect than the one it closes -- the repo's own secret self-scan and its ops queue gate
    both read the working tree.

    MUTATION: probe with `tempfile.mkstemp(dir=...)` and this goes red if the unlink is ever
    skipped (an exception between create and unlink), which is the failure this shape cannot
    have.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("A = 1\n", encoding="utf-8")
    before = sorted(p.name for p in tmp_path.iterdir())
    gate._CASE_FOLD.clear()
    gate._identity("does/not/exist/yet.py")
    gate._identity("x.py")
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_the_case_probe_is_taken_once_per_device(gate, tmp_path, monkeypatch):
    """Per-`st_dev` cache, because the answer is a property of the MOUNT and without it the
    gate re-probes for every path in the plan. The cache key must be the device and not a
    single global boolean: one checkout can span a case-folding and a case-sensitive mount.

    MUTATION: drop the cache and the warm run costs the same as the cold one, so the
    strict-inequality assertion reds; make the cache a single boolean and the second
    assertion (one entry per device, keyed by st_dev) still holds but
    test_the_identity_is_invariant_under_every_alias_spelling is what would catch the
    cross-mount error, which is why this test claims only what it measures.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("A = 1\n", encoding="utf-8")
    real_stat = os.stat

    def counted(path, *a, **kw):
        counted.n += 1
        return real_stat(path, *a, **kw)

    gate._CASE_FOLD.clear()
    counted.n = 0
    monkeypatch.setattr(gate.os, "stat", counted)
    gate._identity("cold.py")
    cold = counted.n
    counted.n = 0
    gate._identity("warm.py")
    warm = counted.n
    monkeypatch.undo()
    assert warm < cold, "the probe was re-taken: cold=%d warm=%d" % (cold, warm)
    assert list(gate._CASE_FOLD) == [os.stat(str(tmp_path)).st_dev], gate._CASE_FOLD


def test_the_case_probe_refuses_to_answer_from_another_device(tmp_path, monkeypatch):
    """A probe performed on a DIFFERENT filesystem answers the wrong question.

    When the deepest existing path is itself a mount point, its own name lives in the parent
    mount, so a case-insensitive volume mounted inside a case-sensitive tree would be probed
    against the case-sensitive parent, cached as sensitive, and its aliases would then stay
    distinct -- the silent exit-0 hole. The guard stops the walk at a device boundary and
    leaves the answer at True (collapse), which is the loud direction.

    Driven directly rather than through a real mount: a fake stat result whose `st_dev`
    differs from the directory's own is the precise condition, and no test can mount a
    volume.

    Mutation that reds this: delete the `if cur_st.st_dev != st.st_dev: break` guard.
    """
    gate_mod = load_gate()
    monkeypatch.chdir(tmp_path)
    probe_dir = tmp_path / 'Vol'
    probe_dir.mkdir()
    own = os.stat(str(probe_dir))
    parent = str(tmp_path)
    real_stat = os.stat

    class _Foreign:
        """A parent that reports a different device, i.e. `probe_dir` is a mount point."""

        def __init__(self, src):
            self.st_dev = src.st_dev + 1000
            self.st_ino = src.st_ino

    swapped = os.path.join(parent, 'Vol'.swapcase())

    def fake_stat(path, *args, **kwargs):
        # The swapped name must MISS, the way it would on a case-sensitive parent. Without
        # this the probe resolves it to the same inode on APFS and answers True regardless of
        # the guard -- which is exactly how the first version of this test came out vacuous
        # under its own mutation.
        if os.path.abspath(str(path)) == os.path.abspath(swapped):
            raise OSError('probed on the parent device, which does not fold case')
        result = real_stat(path, *args, **kwargs)
        if os.path.abspath(str(path)) == os.path.abspath(parent):
            return _Foreign(result)
        return result

    monkeypatch.setattr(os, 'stat', fake_stat)
    gate_mod._CASE_FOLD.clear()
    try:
        answer = gate_mod._case_insensitive(str(probe_dir), own)
    finally:
        gate_mod._CASE_FOLD.clear()
    assert answer is True, (
        'a probe that can only be performed on another device must collapse, not split')
    # Control: with the parent on the SAME device, the identical foreign lookup is trusted and
    # the answer flips to False. Without this the test could pass because nothing was probed
    # at all, rather than because the guard fired.
    monkeypatch.setattr(os, 'stat', lambda p, *a, **k: (
        (_ for _ in ()).throw(OSError('absent'))
        if os.path.abspath(str(p)) == os.path.abspath(swapped)
        else real_stat(p, *a, **k)))
    gate_mod._CASE_FOLD.clear()
    try:
        same_device = gate_mod._case_insensitive(str(probe_dir), own)
    finally:
        gate_mod._CASE_FOLD.clear()
    assert same_device is False, (
        'with the parent on the same device the probe must be trusted, so this control '
        'proves the True above came from the guard and not from an unprobed path')


def test_the_two_keys_are_not_one_key(gate, tmp_path, monkeypatch):
    """The design in one assertion: `_canon` is the WRITER's key and `_identity` is the ALIAS
    key, and they must not be collapsed into one. `_canon` has to stay `os.path.relpath`
    because `execute_code_edit` keys its own accumulator and backup set on exactly that
    (execute-json-ops.py:684) -- pinned by
    test_the_canonical_key_is_the_executors_own_function above. `_identity` has to be
    filesystem truth, which relpath is not.

    MUTATION: make `_canon` return `_identity(path)` and the executor-parity test reds; make
    `_aliases` group on `_canon` and every fold row above reds.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("A = 1\n", encoding="utf-8")
    assert gate._canon("./x.py") == os.path.relpath("./x.py") == "x.py"
    assert isinstance(gate._identity("x.py"), tuple)
    assert gate._identity("x.py") != gate._canon("x.py")

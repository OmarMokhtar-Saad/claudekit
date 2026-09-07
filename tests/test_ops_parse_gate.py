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
import subprocess
import sys
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

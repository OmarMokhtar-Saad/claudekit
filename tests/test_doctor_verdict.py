"""`ck doctor` closes with a one-line verdict and the next step to take.

The detail still streams live and unchanged (same lines, streams, exit codes); the
verdict is appended as the last stdout line. The next step comes only from an explicit
`fix_cmd=` at a check site, never from hint prose -- the regression test below parses
main.py so a prose fix_cmd cannot be added unnoticed.
"""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "src" / "claudekit" / "cli" / "main.py"
sys.path.insert(0, str(ROOT / "src"))

from claudekit.cli.main import _SHELLCHECK_INSTALL, _doctor_verdict  # noqa: E402

VERDICT = re.compile(r"^(PASS|WARN|FAIL) .+ — next: .+$")
RUNNABLE = ("ck ", "bash ", "brew ", "apt-get ", "python3 ", "pip ", "chmod ", "git ")


def ck(*args, cwd):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), ECC_HOOK_PROFILE="minimal")
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main", *args],
                          capture_output=True, text=True, cwd=str(cwd), env=env,
                          timeout=300)


def test_an_uninstalled_project_ends_with_a_fail_verdict_naming_ck_init(tmp_path):
    result = ck("doctor", cwd=tmp_path)
    lines = result.stdout.splitlines()
    assert result.returncode == 1, result.stdout + result.stderr
    # Streaming is unchanged: the header still opens the output.
    assert "ClaudeKit Doctor v" in next(ln for ln in lines if ln.strip()), result.stdout
    assert VERDICT.match(lines[-1]), result.stdout
    assert lines[-1].startswith("FAIL "), lines[-1]
    assert lines[-1].endswith("next: run `ck init`"), lines[-1]


def test_a_floor_above_100_ends_with_fail_and_keeps_the_error_on_stderr(tmp_path):
    result = ck("doctor", "--min-score", "101", cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1].startswith("FAIL ")
    assert "Some checks failed" in result.stderr
    assert "Some checks failed" not in result.stdout


def _fix_cmd_values():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "check":
            for kw in node.keywords:
                if kw.arg == "fix_cmd":
                    yield node, kw.value


def test_every_fix_cmd_is_a_runnable_command_not_prose():
    found = list(_fix_cmd_values())
    assert len(found) >= 5, "fix_cmd sites disappeared -- wrong parse?"
    for _, value in found:
        if isinstance(value, ast.Constant):
            literal = value.value
        elif isinstance(value, ast.JoinedStr):
            literal = value.values[0].value
        elif (isinstance(value, ast.Call)
              and ast.unparse(value.func) == "_SHELLCHECK_INSTALL.get"):
            continue  # its values are checked below
        else:
            raise AssertionError(f"unrecognised fix_cmd form: {ast.dump(value)}")
        assert isinstance(literal, str) and literal.startswith(RUNNABLE), literal
    for cmd in _SHELLCHECK_INSTALL.values():
        assert cmd.startswith(RUNNABLE), cmd


def test_conditional_and_non_command_hints_declare_no_fix_cmd():
    names = {"Install version drift", "Agent memory"}
    for node in ast.walk(ast.parse(MAIN.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "check":
            label = ast.unparse(node.args[0]) if node.args else ""
            if any(n in label for n in names):
                assert all(kw.arg != "fix_cmd" for kw in node.keywords), label


def test_the_verdict_uses_the_first_failure_command_else_points_at_the_line():
    fail = {"applicable": 28, "failed": 2, "warned": 1, "passed": 25,
            "first_fail_cmd": "ck update", "first_warn_cmd": "brew install shellcheck"}
    assert _doctor_verdict(1, fail) == "FAIL 2/28 failed — next: run `ck update`"
    fail["first_fail_cmd"] = None
    assert _doctor_verdict(1, fail) == "FAIL 2/28 failed — next: fix the first [✗] line above"
    warn = {"applicable": 10, "failed": 0, "warned": 1, "passed": 9, "first_warn_cmd": None}
    assert _doctor_verdict(0, warn) == "WARN 1/10 warned — next: fix the first [!] line above"
    assert _doctor_verdict(1, warn).startswith("FAIL 1/10 warned")
    clean = {"applicable": 5, "failed": 0, "warned": 0, "passed": 5}
    assert _doctor_verdict(0, clean) == "PASS 5/5 passed — next: nothing"

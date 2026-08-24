"""Delivery guards: every hook wired by settings.json must actually ship.

Regression (workstream 9): commit 26b26da added .claude/hooks/reflection-gate.py
and wired it into settings.json on 7 lifecycle events, but install.sh copied
hooks by an extension allowlist (*.sh/*.json/*.md) and never shipped it.
`python3 <missing>` exits 2, and exit 2 on PreToolUse is a BLOCK -- so a fresh
install produced a project where every Edit, Write and Bash was blocked.

These tests are BEHAVIORAL: they run the real installer into a temp directory
and assert on the installed result, never on the text of install.sh. Nothing
here mutates the real tree -- the negative fixtures operate on a copytree.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO / "install.sh"
CLI_MAIN = REPO / "src" / "claudekit" / "cli" / "main.py"

# How settings.json refers to a hook script, regardless of interpreter.
HOOK_REF = re.compile(r"\.claude/hooks/([A-Za-z0-9._-]+)")

# Runtime state that lives in the source hooks dir but must never be installed.
RUNTIME_NAMES = {"compact-counter.txt", "settings.local.json"}
RUNTIME_SUFFIXES = (".log", ".pyc", ".orig", ".rej", ".swp", "~")


def _env():
    """Hook profile is forced explicitly -- never inherited from the dev shell."""
    env = os.environ.copy()
    env["ECC_HOOK_PROFILE"] = "minimal"
    return env


def _install(target, script=None, check=True):
    cmd = ["bash", str(script or INSTALL_SCRIPT), str(target), "--full", "--force", "--yes"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=_env())
    if check:
        assert result.returncode == 0, (
            f"install failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
        )
    return result


def _kit_copy(dest):
    """A throwaway copy of the kit source. The real tree is never modified."""
    shutil.copytree(
        REPO, dest, symlinks=True,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", "node_modules", ".venv", "backups",
            "*.log",
        ),
    )
    return dest


def _hooks_dir(target):
    return Path(target) / ".claude" / "hooks"


def _installed_names(target):
    return {p.name for p in _hooks_dir(target).iterdir() if p.is_file()}


def test_every_wired_hook_resolves_after_install():
    """THE guard. Would have caught the reflection-gate.py regression on day one."""
    with tempfile.TemporaryDirectory() as tmp:
        _install(tmp)
        text = (Path(tmp) / ".claude" / "settings.json").read_text(encoding="utf-8")
        wired = set(HOOK_REF.findall(text))
        assert wired, "settings.json wires no hooks -- this guard would be vacuous"
        missing = sorted(
            n for n in wired
            if not n.endswith(RUNTIME_SUFFIXES)
            and n not in RUNTIME_NAMES
            and not (_hooks_dir(tmp) / n).is_file()
        )
        assert not missing, (
            f"settings.json wires hooks that were not installed: {missing}. "
            "`python3 <missing>` exits 2, and exit 2 on PreToolUse blocks "
            "every Edit, Write and Bash in the installed project."
        )


def test_python_hooks_installed_and_executable():
    with tempfile.TemporaryDirectory() as tmp:
        _install(tmp)
        for name in ("reflection-gate.py", "reflection.py"):
            assert (_hooks_dir(tmp) / name).is_file(), f"{name} was not installed"
        assert os.access(_hooks_dir(tmp) / "reflection-gate.py", os.X_OK), (
            "wired Python hook is not executable"
        )


def test_all_source_hook_assets_installed():
    """Structural: catches the NEXT stale extension, not just this one."""
    src = REPO / ".claude" / "hooks"
    expected = {
        p.name for p in src.iterdir()
        if p.is_file()
        and p.name not in RUNTIME_NAMES
        and not p.name.endswith(RUNTIME_SUFFIXES)
    }
    assert expected, "source hooks dir is empty -- fixture precondition failed"
    with tempfile.TemporaryDirectory() as tmp:
        _install(tmp)
        missing = sorted(expected - _installed_names(tmp))
        assert not missing, f"hook assets in source but not installed: {missing}"


def test_no_runtime_state_installed():
    """The structural copy must still deny runtime state that lives in-tree."""
    with tempfile.TemporaryDirectory() as tmp:
        _install(tmp)
        names = _installed_names(tmp)
        assert not [n for n in names if n.endswith(".log")], f"logs installed: {names}"
        assert "compact-counter.txt" not in names


def test_installer_fails_closed_on_wired_but_missing_hook():
    """Runs against a COPY of the repo; the real tree is never modified."""
    with tempfile.TemporaryDirectory() as tmp:
        kit = _kit_copy(Path(tmp) / "kit")
        victim = kit / ".claude" / "hooks" / "reflection-gate.py"
        assert victim.is_file(), "fixture precondition: wired hook exists in the copy"
        victim.unlink()

        target = Path(tmp) / "proj"
        target.mkdir()
        result = _install(target, script=kit / "install.sh", check=False)

        assert result.returncode != 0, (
            "installer reported success despite a wired-but-missing hook; "
            "it must fail closed rather than ship a blocked project"
        )
        assert "reflection-gate.py" in (result.stdout + result.stderr), (
            "installer did not name the missing wired hook"
        )
        # `exit` does not fire the ERR trap, so cleanup must be explicit.
        leftovers = list(target.glob(".claude.staging.*"))
        assert not leftovers, f"staging dir left behind in the project: {leftovers}"


def test_log_and_unprovable_references_do_not_block_install():
    """The guard must not fail closed on a name it cannot prove is a script.

    A hook that merely LOGS to $ROOT/.claude/hooks/hooks.log (an idiom this repo
    already uses) must not make the installer refuse to install.
    """
    with tempfile.TemporaryDirectory() as tmp:
        kit = _kit_copy(Path(tmp) / "kit")
        settings = kit / ".claude" / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["_ws9_probe"] = [
            "bash -c 'echo x >> \"$ROOT/.claude/hooks/hooks.log\"'",
            "python3 \"$ROOT/.claude/hooks/hooks.log\"",
            "see $ROOT/.claude/hooks/mystery-token for details",
        ]
        settings.write_text(json.dumps(data, indent=2), encoding="utf-8")

        target = Path(tmp) / "proj"
        target.mkdir()
        result = _install(target, script=kit / "install.sh", check=False)

        assert result.returncode == 0, (
            "installer refused to install over a hooks.log / unprovable reference; "
            f"failing closed on an unprovable name blocks everyone:\n{result.stdout}\n"
            f"{result.stderr}"
        )
        assert not (_hooks_dir(target) / "hooks.log").exists(), "runtime log was installed"


def _doctor(cwd):
    return subprocess.run(
        [sys.executable, str(CLI_MAIN), "doctor"],
        cwd=str(cwd), capture_output=True, text=True, timeout=180, env=_env(),
    )


def _doctor_output(result):
    """cli.main.err() writes to stderr and ok()/warn() to stdout, so a check's
    text lands in a different stream depending on its verdict. Assert on both."""
    return result.stdout + result.stderr


def _fixture_tree(tmp, command):
    claude = Path(tmp) / ".claude"
    (claude / "hooks").mkdir(parents=True)
    (claude / "settings.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": command}]}
        ]}}),
        encoding="utf-8",
    )
    return claude


def test_doctor_flags_wired_but_missing_hook():
    with tempfile.TemporaryDirectory() as tmp:
        _fixture_tree(tmp, "python3 $CLAUDE_PROJECT_DIR/.claude/hooks/ghost-hook.py")
        result = _doctor(tmp)
        # THIS assertion is what binds the fix. The returncode below is NOT
        # binding: the minimal fixture already fails several pre-existing checks.
        output = _doctor_output(result)
        assert "ghost-hook.py" in output, (
            f"doctor did not report the unresolved wired hook:\n{output}"
        )
        assert result.returncode == 1, "doctor must fail on a wired-but-missing hook"


def test_doctor_flags_hook_that_is_a_directory():
    """Existence is not resolvability."""
    with tempfile.TemporaryDirectory() as tmp:
        claude = _fixture_tree(
            tmp, "python3 $CLAUDE_PROJECT_DIR/.claude/hooks/impostor.py"
        )
        (claude / "hooks" / "impostor.py").mkdir()
        result = _doctor(tmp)
        output = _doctor_output(result)
        assert "impostor.py" in output, (
            f"a directory passed as a runnable hook:\n{output}"
        )


def test_doctor_ignores_unprovable_reference():
    with tempfile.TemporaryDirectory() as tmp:
        _fixture_tree(tmp, "echo see .claude/hooks/mystery-token")
        result = _doctor(tmp)
        output = _doctor_output(result)
        assert "mystery-token" not in output, (
            f"doctor required a token it cannot prove is a script:\n{output}"
        )


def test_doctor_passes_wired_hook_check_on_clean_install():
    """Guards against a false positive that would break `ck doctor --strict`."""
    with tempfile.TemporaryDirectory() as tmp:
        _install(tmp)
        result = _doctor(tmp)
        output = _doctor_output(result)
        assert "Wired hooks resolve" in output, (
            f"doctor never ran the wired-hook check:\n{output}"
        )
        assert "references missing hooks" not in output, (
            f"doctor false-positived on a clean install:\n{output}"
        )


def test_setup_bundles_python_hooks():
    """The wheel/sdist path. tests/test_packaging.py only asserted `.sh`, so it
    was blind to this bug class; this closes that gap."""
    import importlib.util

    setuptools = pytest.importorskip("setuptools")
    spec = importlib.util.spec_from_file_location("_ck_setup_hookdelivery", REPO / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    orig = setuptools.setup
    setuptools.setup = lambda *a, **k: None
    cwd = os.getcwd()
    try:
        os.chdir(REPO)
        spec.loader.exec_module(mod)
        data = mod._asset_data_files()
    finally:
        os.chdir(cwd)
        setuptools.setup = orig

    flat = [f for _dest, files in data for f in files]
    assert any(f.endswith("reflection-gate.py") and "hooks" in f for f in flat), (
        "wheel/sdist asset bundle is missing the wired Python hook"
    )

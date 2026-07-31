"""Runs shellcheck over install.sh and .claude/hooks/*.sh when available; reports a
visible SKIP (not silence) when the tool is absent, so `pytest -v` output always states
whether this DoD gate ran."""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHELLCHECK = shutil.which("shellcheck")

pytestmark = pytest.mark.skipif(
    SHELLCHECK is None,
    reason="shellcheck not installed — CI (.github/workflows/ci.yml, security.yml) still "
           "gates this; install locally with `brew install shellcheck` / "
           "`apt-get install shellcheck` to run it here too",
)


def _shell_scripts():
    yield REPO_ROOT / "install.sh"
    yield from sorted((REPO_ROOT / ".claude" / "hooks").glob("*.sh"))


@pytest.mark.parametrize("script", list(_shell_scripts()), ids=lambda p: p.name)
def test_shellcheck_clean(script):
    result = subprocess.run([SHELLCHECK, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"shellcheck findings in {script.name}:\n{result.stdout}"

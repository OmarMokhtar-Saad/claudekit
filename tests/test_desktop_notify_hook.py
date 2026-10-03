"""Behavioral test for desktop-notify.sh (Stop hook): never blocks, notifies, logs."""

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def _run(tmp_path):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    script = hooks / "desktop-notify.sh"
    shutil.copy(HOOKS / "desktop-notify.sh", script)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.txt"
    for tool in ("osascript", "notify-send"):
        stub = bindir / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{calls}"\n')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "ECC_HOOK_PROFILE": "standard"}
    p = subprocess.run(
        ["bash", str(script)], input="{}", capture_output=True, text=True,
        cwd=str(tmp_path), env=env, timeout=30,
    )
    for _ in range(50):  # the notifier is backgrounded
        if calls.exists():
            break
        time.sleep(0.1)
    return p, calls, hooks / "hooks.log"


def test_stop_notifies_and_exits_zero(tmp_path):
    p, calls, log = _run(tmp_path)
    assert p.returncode == 0, p.stderr
    assert calls.exists(), "no notifier was invoked"
    assert "Session ended" in calls.read_text()
    assert "desktop-notify" in log.read_text()


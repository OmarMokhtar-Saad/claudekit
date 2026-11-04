"""Hook counting: the published hook count is true (python hooks included)."""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _gen_docs():
    spec = importlib.util.spec_from_file_location(
        "gen_docs_under_test", REPO / "scripts" / "gen-docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestHookCountIsTrue:
    def test_python_hooks_are_counted(self):
        g = _gen_docs()
        counted = {p.name for p in g._hook_files() if not g._is_helper_module(p, g._hook_files())}
        assert "reflection-gate.py" in counted, "python hooks must count"
        assert "plan-gate.sh" in counted
        assert g.count_hooks() == len(counted)

    def test_sourced_and_imported_helpers_are_not_hooks(self):
        g = _gen_docs()
        files = g._hook_files()
        by_name = {p.name: p for p in files}
        assert g._is_helper_module(by_name["lib.sh"], files), "lib.sh is sourced, not a hook"
        assert g._is_helper_module(by_name["reflection.py"], files), \
            "reflection.py is imported by reflection-gate.py, not wired as a hook"

    def test_every_wired_hook_is_counted(self):
        g = _gen_docs()
        settings = (REPO / ".claude" / "settings.json").read_text()
        wired = set(re.findall(r"([A-Za-z0-9_.-]+\.(?:sh|py))", settings))
        files = g._hook_files()
        counted = {p.name for p in files if not g._is_helper_module(p, files)}
        assert wired - counted == set(), f"wired but uncounted: {sorted(wired - counted)}"

    def test_docs_drift_gate_passes(self):
        proc = subprocess.run([sys.executable, str(REPO / "scripts" / "gen-docs.py"), "--check"],
                              cwd=str(REPO), capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr

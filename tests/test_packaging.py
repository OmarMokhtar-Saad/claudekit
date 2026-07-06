"""Regression guards for the packaging metadata (task 001).

These are fast, dependency-free invariants that would have caught the year-long
"package never installable" bug and the ``src``-as-package layout mistake.
The full end-to-end build is exercised by the CI ``package-smoke`` job.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = (REPO / "pyproject.toml").read_text(encoding="utf-8")


def _field(pattern):
    match = re.search(pattern, PYPROJECT, re.MULTILINE)
    assert match, f"pattern not found in pyproject.toml: {pattern}"
    return match.group(1)


def test_build_backend_is_real():
    # The old value "setuptools.backends._legacy:_Backend" does not exist in any release.
    assert _field(r'^build-backend\s*=\s*"([^"]+)"') == "setuptools.build_meta"


def test_no_setuptools_scm_in_build_requires():
    requires = _field(r'^requires\s*=\s*(\[[^\]]*\])')
    assert "setuptools-scm" not in requires


def test_src_layout_package_discovery():
    assert _field(r'where\s*=\s*\["([^"]+)"\]') == "src"


def test_entry_points_target_claudekit_package():
    assert "claudekit.cli.main:main" in PYPROJECT
    assert "src.cli.main:main" not in PYPROJECT


def test_source_tree_is_true_src_layout():
    assert (REPO / "src" / "claudekit" / "__init__.py").exists()
    assert (REPO / "src" / "claudekit" / "cli" / "main.py").exists()
    # ``src`` itself must NOT be an importable package.
    assert not (REPO / "src" / "__init__.py").exists()


def test_single_version_source_of_truth():
    version = _field(r'^version\s*=\s*"([^"]+)"')
    # No stale literal versions anywhere in the shipped Python package.
    for py in (REPO / "src").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert '"1.1.0"' not in text, f"stale version literal in {py}"
        assert '"3.1.0"' not in text, f"stale version literal in {py}"
    assert re.match(r"\d+\.\d+\.\d+", version)


def test_setup_bundles_runtime_assets():
    """setup.py must collect the asset tree so `pip install` is self-contained.

    Guards the wheel-bundling contract without a full build: the computed
    data_files must include .claude/agents, a hook, and install.sh, and must
    exclude local/runtime cruft.
    """
    import importlib.util
    import pytest
    # setup.py imports setuptools; Python 3.12+ venvs don't bundle it.
    setuptools = pytest.importorskip("setuptools")
    spec = importlib.util.spec_from_file_location("_ck_setup", REPO / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    # setup.py calls setup() at import; stub it so import is a no-op.
    orig = setuptools.setup
    setuptools.setup = lambda *a, **k: None
    try:
        import os
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            spec.loader.exec_module(mod)
            data = mod._asset_data_files()
        finally:
            os.chdir(cwd)
    finally:
        setuptools.setup = orig

    flat = [f for _dest, files in data for f in files]
    assert any(f.endswith("install.sh") for f in flat)
    assert any(os.path.join(".claude", "agents") in f for f in flat)
    assert any(f.endswith(".sh") and "hooks" in f for f in flat)
    # No local overrides / logs bundled.
    assert not any("settings.local.json" in f for f in flat)
    assert not any(f.endswith(".log") for f in flat)

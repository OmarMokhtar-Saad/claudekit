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
    # Every version literal in the shipped package must BE the current version.
    #
    # This listed two hardcoded strings to forbid ('"1.1.0"', '"3.1.0"'). Both
    # failure modes followed: it never contained "2.1.0", so `_resolve_version`'s
    # source-checkout fallback sat two releases stale through 3.0.0 with nothing
    # failing; and it pre-forbade "3.1.0", so the release that legitimately reached
    # that number tripped a guard meant for staleness. Deriving catches the first
    # and cannot cause the second.
    literal = re.compile(r'(?:__version__\s*=|return)\s+"(\d+\.\d+\.\d+)"')
    for py in (REPO / "src").rglob("*.py"):
        for found in literal.findall(py.read_text(encoding="utf-8")):
            assert found == version, (
                f"stale version literal {found!r} in {py}; pyproject says {version!r}")
    # install.sh too. Scanning only src/ is why `VERSION="2.1.0"` survived TWO releases
    # there unnoticed, stamping a stale version into every install manifest. Any literal
    # assignment is the defect regardless of spelling -- export/readonly/indented/
    # unquoted all count -- so the pattern is deliberately wider than the single
    # historical form. The value must be derived from pyproject.
    installer = (REPO / "install.sh").read_text(encoding="utf-8")
    hardcoded = re.findall(
        r"""^[ \t]*(?:export[ \t]+|readonly[ \t]+)?VERSION[ \t]*=[ \t]*["']?(\d+\.\d+\.\d+)["']?""",
        installer, re.M)
    assert not hardcoded, (
        f"install.sh hardcodes VERSION={hardcoded[0]!r}; derive it from pyproject.toml")
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

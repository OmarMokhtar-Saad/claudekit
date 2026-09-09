"""Version precedence: a source checkout reports its tree, a wheel reports metadata.

Every test here is a MUTATION PROOF of one half of the rule in
`src/claudekit/_version.py`, driven in a subprocess against a synthetic package
tree so no `pip` run is needed and the developer's own installed metadata is the
control:

* revert the precedence (metadata first) and
  `test_a_source_checkout_reports_the_source_version`,
  `test_the_cli_and_the_package_both_report_the_pyproject_version` and
  `test_the_installer_and_the_cli_cannot_disagree` fail;
* drop the `src`-layout guard and
  `test_a_wheel_style_layout_still_prefers_installed_metadata` fails;
* drop the `name = "claudekit-agents"` guard and
  `test_an_unrelated_neighbouring_pyproject_is_not_a_kit_source` fails;
* move the distribution name in ONE of `pyproject.toml`, `_version.DIST_NAME` or
  `cli/main.py`'s `metadata.version()` argument and
  `TestTheDistributionNameIsOneString` fails.

The defect being pinned, measured on this machine before the fix: source
pyproject 3.2.0, editable-install metadata 3.1.0, so `install.sh` stamped 3.2.0
into every manifest while the CLI reported 3.1.0 and `ck doctor` called a
freshly installed project DRIFTED (7 failures in tests/test_doctor_gate.py that
CI never saw, because CI installs fresh).
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "src" / "claudekit"
INSTALL = REPO / "install.sh"

# A version no environment will ever have installed, so equality with it can only
# come from the source tree.
SENTINEL = "42.0.1"

ENV = dict(os.environ, ECC_HOOK_PROFILE="minimal")

MAIN = PKG / "cli" / "main.py"


def _module_from_source(name, path):
    """Load one module FILE, without importing the `claudekit` package.

    `import claudekit._version` would resolve against whatever is on sys.path --
    including an editable install pointing at a DIFFERENT checkout -- so the
    constant under test would not be this tree's. Loading the file cannot.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Derived, never typed: every synthetic tree and metadata lookup below uses the
#: name the shipped module declares, so a rename cannot half-land in the tests.
DIST_NAME = _module_from_source("_ck_version_probe", PKG / "_version.py").DIST_NAME


def _project_field(text, key):
    """`[project]`-scoped read, mirroring install.sh's anchored sed."""
    pattern = re.compile(r'%s\s*=\s*"([^"]+)"' % re.escape(key))
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = pattern.match(stripped)
            if match:
                return match.group(1)
    return None


def _pyproject_version():
    return _project_field((REPO / "pyproject.toml").read_text(encoding="utf-8"), "version")


def _metadata_version():
    """The version installed metadata reports, or None when nothing is installed.

    Read in a subprocess with PYTHONPATH stripped so the repo's own source tree
    cannot influence the answer.
    """
    env = {k: v for k, v in ENV.items() if k != "PYTHONPATH"}
    code = ("from importlib import metadata\n"
            "try:\n"
            "    print(metadata.version(%r))\n"
            "except metadata.PackageNotFoundError:\n"
            "    print('')\n" % DIST_NAME)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(sys.prefix)), capture_output=True, text=True, timeout=60, env=env)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip() or None


def _synthetic_tree(root, layout, name, version, write_pyproject=True):
    """A copy of the real package under `<root>/<layout>/claudekit`, returning the
    directory to put on PYTHONPATH.

    `layout="src"` reproduces this repo's editable src-layout checkout;
    `layout="site-packages"` reproduces a wheel install, where the package has no
    `src` parent. The two modules are copied rather than stubbed, so the code under
    test is the shipped code.
    """
    pkgdir = Path(root) / layout / "claudekit"
    pkgdir.mkdir(parents=True)
    for rel in ("__init__.py", "_version.py"):
        shutil.copy(PKG / rel, pkgdir / rel)
    if write_pyproject:
        (Path(root) / "pyproject.toml").write_text(
            '[tool.poetry]\nversion = "0.0.9"\n\n'
            '[project]\nname = "%s"\nversion = "%s"\n' % (name, version),
            encoding="utf-8")
    return Path(root) / layout


def _reported(path_root):
    """What `claudekit.__version__` is when imported from `path_root`."""
    env = dict(ENV, PYTHONPATH=str(path_root))
    proc = subprocess.run(
        [sys.executable, "-c", "import claudekit; print(claudekit.__version__)"],
        cwd=str(Path(path_root).parent), capture_output=True, text=True, timeout=60,
        env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


class TestSourceCheckoutWins:
    def test_a_source_checkout_reports_the_source_version(self, tmp_path):
        """The inversion itself. An editable install's metadata is frozen at install
        time; the tree is not, so the tree wins."""
        root = _synthetic_tree(tmp_path, "src", DIST_NAME, SENTINEL)
        installed = _metadata_version()
        assert installed != SENTINEL, (
            "the sentinel collides with real installed metadata; this test would pass "
            "for the wrong reason")
        assert _reported(root) == SENTINEL

    def test_the_source_version_is_read_from_the_project_table_only(self, tmp_path):
        """A `[tool.*]` table above `[project]` also has a `version` key. The
        synthetic pyproject carries `[tool.poetry] version = "0.0.9"` for exactly
        this reason: an unanchored match returns it."""
        root = _synthetic_tree(tmp_path, "src", DIST_NAME, SENTINEL)
        assert _reported(root) != "0.0.9"

    def test_the_cli_and_the_package_both_report_the_pyproject_version(self):
        """Against the REAL checkout, both former literal sites now derive. This is the
        recurring release defect: `cli/main.py`'s fallback sat at 2.1.0 through 3.0.0."""
        expected = _pyproject_version()
        env = dict(ENV, PYTHONPATH=str(REPO / "src"))
        cli = subprocess.run([sys.executable, "-m", "claudekit.cli.main", "--version"],
                             cwd=str(REPO), capture_output=True, text=True, timeout=60,
                             env=env)
        assert cli.returncode == 0, cli.stdout + cli.stderr
        assert expected in cli.stdout, cli.stdout
        assert _reported(REPO / "src") == expected

    def test_no_hand_bumped_version_literal_remains(self):
        """The sites that used to need a manual bump must contain no semver literal at
        all, so there is nothing left to forget."""
        for rel in ("__init__.py", "_version.py", "cli/main.py"):
            text = (PKG / rel).read_text(encoding="utf-8")
            code = "\n".join(line for line in text.splitlines()
                             if not line.lstrip().startswith("#"))
            found = re.findall(r'(?:__version__\s*=|return)\s+"(\d+\.\d+\.\d+)"', code)
            assert not found, "%s still hardcodes %r" % (rel, found)


class TestInstalledPackageStillUsesMetadata:
    def test_a_wheel_style_layout_still_prefers_installed_metadata(self, tmp_path):
        """No source tree above the package, so metadata is the only truth -- even
        though a matching pyproject sits one directory up. Without the `src`-layout
        guard this returns 7.7.7."""
        installed = _metadata_version()
        if installed is None:
            pytest.skip("%s is not installed in this environment" % DIST_NAME)
        root = _synthetic_tree(tmp_path, "site-packages", DIST_NAME, "7.7.7")
        reported = _reported(root)
        assert reported != "7.7.7"
        assert reported == installed

    def test_an_unrelated_neighbouring_pyproject_is_not_a_kit_source(self, tmp_path):
        """A vendored copy under someone else's `src/`. Without the name guard this
        reports the HOST project's version as ClaudeKit's."""
        installed = _metadata_version()
        root = _synthetic_tree(tmp_path, "src", "someone-else", "6.6.6")
        reported = _reported(root)
        assert reported != "6.6.6"
        assert reported == (installed or "unknown")

    def test_a_src_layout_without_a_pyproject_falls_back_without_raising(self, tmp_path):
        """A tarball or a copied tree. The fallback must be a value, not a traceback."""
        installed = _metadata_version()
        root = _synthetic_tree(tmp_path, "src", DIST_NAME, SENTINEL,
                               write_pyproject=False)
        assert _reported(root) == (installed or "unknown")


class TestInstallerAndCliAgree:
    def test_the_installer_and_the_cli_cannot_disagree(self, tmp_path):
        """The measured defect, end to end: install.sh stamps the SOURCE version into
        the manifest, and `ck doctor`'s install-drift check compares that with the
        version the CLI reports. Before the fix those were 3.2.0 and 3.1.0 on an
        editable install, and a freshly installed project was reported DRIFTED."""
        target = tmp_path / "project"
        target.mkdir()
        proc = subprocess.run(["bash", str(INSTALL), str(target), "--minimal"],
                              capture_output=True, text=True, timeout=300,
                              stdin=subprocess.DEVNULL, env=ENV)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        manifest = json.loads(
            (target / ".claude" / ".claudekit-manifest.json").read_text(encoding="utf-8"))
        env = dict(ENV, PYTHONPATH=str(REPO / "src"))
        doctor = subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "doctor"],
            cwd=str(target), capture_output=True, text=True, timeout=300, env=env)
        combined = doctor.stdout + doctor.stderr
        assert manifest["version"] == _pyproject_version(), manifest["version"]
        assert "Install version drift" not in combined, combined
        assert "Install matches kit v%s" % _pyproject_version() in combined, combined


class TestTheDistributionNameIsOneString:
    """The rename coupling, pinned.

    `DIST_NAME` is used twice with DIFFERENT meanings -- the argument to
    `importlib.metadata.version()`, and the `[project] name` a neighbouring
    pyproject must declare for `source_version()` to accept the tree as a source
    checkout -- and `cli/main.py` repeats the literal a third time in the branch
    where `claudekit._version` is not importable and so cannot supply it. Move
    fewer than all three and a source checkout stops recognising itself and
    silently falls back to stale installed metadata: the PR #37 defect.
    """

    def test_pyproject_version_module_and_cli_name_one_distribution(self):
        """Mutation: change the name in ANY ONE of the three sites -> this fails."""
        pyproject_name = _project_field(
            (REPO / "pyproject.toml").read_text(encoding="utf-8"), "name")
        literals = re.findall(r'metadata\.version\(\s*"([^"]+)"\s*\)',
                              MAIN.read_text(encoding="utf-8"))
        assert literals, "cli/main.py names no distribution to look up any more"
        assert pyproject_name == DIST_NAME, (pyproject_name, DIST_NAME)
        assert set(literals) == {DIST_NAME}, (literals, DIST_NAME)

    def test_the_distribution_name_is_the_one_pypi_accepted(self):
        """Renaming all three at once is still a deliberate act that edits a test.

        `claude-kit` was REFUSED by PyPI as confusable with the unrelated
        `claudekit` project (PyPI ignores separators when comparing names), and
        nothing was ever published under it.

        Mutation: rename all three sites consistently -> this fails."""
        assert DIST_NAME == "claudekit-agents"

"""Bundle ClaudeKit's runtime asset tree into the wheel/sdist.

Project metadata lives in pyproject.toml. This shim exists only to attach the
non-Python asset tree (`.claude/`, `templates/`, `install.sh`, `config.schema.json`)
as ``data_files`` so a plain ``pip install claudekit-agents`` is self-contained and
``ck init`` works with no source checkout. The files land under
``<prefix>/share/claudekit/`` and are located at runtime by
``claudekit.cli.main.find_claudekit_root``.
"""

import os
import subprocess

from setuptools import setup

# Files/dirs never shipped: local overrides, runtime state, caches, VCS noise.
_EXCLUDE_NAMES = {
    "settings.local.json",
    ".claudekit-manifest.json",
    "compact-counter.txt",
    ".DS_Store",
}
_EXCLUDE_DIR_PARTS = {"__pycache__", "backups", ".managed", ".git", "node_modules"}
_EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log", ".lock")

_DEST_ROOT = "share/claudekit"


def _include(path):
    name = os.path.basename(path)
    if name in _EXCLUDE_NAMES or name.endswith(_EXCLUDE_SUFFIXES):
        return False
    parts = set(path.split(os.sep))
    return not (parts & _EXCLUDE_DIR_PARTS)


def _git_ignored():
    """(files, dirs) .gitignore marks as runtime state, when building from the kit's own
    checkout; the lists above are only the fallback for a source with no git (an sdist).
    A build from a used working tree otherwise bundled hooks/.state ledgers, research
    caches, reflection notes and worktrees. Only when the checkout root IS this
    directory: under an outer repo that ignores it, every asset would be dropped."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                             capture_output=True, text=True, check=True).stdout.strip()
        if os.path.realpath(top) != os.path.realpath(here):
            return set(), set()
        out = subprocess.run(["git", "ls-files", "-z", "--others", "--ignored",
                              "--exclude-standard", "--directory"], cwd=here,
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return set(), set()
    files, dirs = set(), set()
    for p in filter(None, out.split("\0")):
        (dirs if p.endswith("/") else files).add(os.path.normpath(p))
    return files, dirs


def _tree(root, ignored=None):
    """Yield (dest_dir, [files]) preserving directory structure under _DEST_ROOT."""
    entries = []
    if not os.path.isdir(root):
        return entries
    ign_files, ign_dirs = ignored or (set(), set())
    if os.path.normpath(root) in ign_dirs:
        return entries
    for dirpath, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIR_PARTS
                   and os.path.normpath(os.path.join(dirpath, d)) not in ign_dirs]
        files = [os.path.join(dirpath, f) for f in filenames
                 if _include(os.path.join(dirpath, f))
                 and os.path.normpath(os.path.join(dirpath, f)) not in ign_files]
        if files:
            entries.append((os.path.join(_DEST_ROOT, dirpath), files))
    return entries


def _asset_data_files():
    data = []
    ignored = _git_ignored()
    data += _tree(".claude", ignored)
    data += _tree("templates", ignored)
    root_files = [f for f in ("install.sh", "config.schema.json") if os.path.exists(f)]
    if root_files:
        data.append((_DEST_ROOT, root_files))
    return data


setup(data_files=_asset_data_files())

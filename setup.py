"""Bundle ClaudeKit's runtime asset tree into the wheel/sdist.

Project metadata lives in pyproject.toml. This shim exists only to attach the
non-Python asset tree (`.claude/`, `templates/`, `install.sh`, `config.schema.json`)
as ``data_files`` so a plain ``pip install claudekit`` is self-contained and
``ck init`` works with no source checkout. The files land under
``<prefix>/share/claudekit/`` and are located at runtime by
``claudekit.cli.main.find_claudekit_root``.
"""

import os

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


def _tree(root):
    """Yield (dest_dir, [files]) preserving directory structure under _DEST_ROOT."""
    entries = []
    if not os.path.isdir(root):
        return entries
    for dirpath, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIR_PARTS]
        files = [os.path.join(dirpath, f) for f in filenames
                 if _include(os.path.join(dirpath, f))]
        if files:
            entries.append((os.path.join(_DEST_ROOT, dirpath), files))
    return entries


def _asset_data_files():
    data = []
    data += _tree(".claude")
    data += _tree("templates")
    root_files = [f for f in ("install.sh", "config.schema.json") if os.path.exists(f)]
    if root_files:
        data.append((_DEST_ROOT, root_files))
    return data


setup(data_files=_asset_data_files())

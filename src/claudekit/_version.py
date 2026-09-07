"""Where the running version comes from, and in what order.

ONE precedence rule, in one place, because the alternative has already cost two
releases: `claudekit/__init__.py` and `claudekit/cli/main.py` each carried a
hand-bumped `"x.y.z"` literal as an offline fallback, and `cli/main.py`'s sat at
`2.1.0` through the whole of the 3.0.0 release with nothing failing.

The rule:

1. **A source checkout reports its own tree.** If this file sits at
   `<root>/src/claudekit/_version.py` and `<root>/pyproject.toml` declares
   `name = "claude-kit"`, that pyproject's version IS the version. This is the
   precedence inversion the module exists for: an EDITABLE install
   (`pip install -e .`) freezes `importlib.metadata` at install time, so with
   metadata first the CLI kept reporting the pre-bump version until somebody
   re-ran pip -- while `install.sh` stamped the SOURCE version into every
   project's `.claudekit-manifest.json`. `ck doctor`'s install-drift check
   compares those two, so a freshly installed project reported as DRIFTED. The
   installer reads the source; so does the CLI now; they cannot disagree.
2. **Otherwise, installed metadata.** A wheel install has no source tree above
   the package, so metadata is the only truth and behaviour is unchanged.
3. **Otherwise `"unknown"`.** Honest rather than invented, and the same word
   `install.sh` already records for an unpinnable value. `_parse_semver` maps it
   to None, which doctor renders as a skip -- never a false "matches".

Detector failure modes, stated rather than hoped for:

* **Wheel / site-packages install** -- the package is `site-packages/claudekit/`,
  so `parents[1].name` is not `src` and no `pyproject.toml` is consulted at all.
  Falls to metadata. Correct.
* **A site-packages copy that happens to sit near an unrelated pyproject.toml**
  -- rejected twice over: the `src` layout check fails, and the
  `name = "claude-kit"` check would fail too. Falls to metadata.
* **A vendored copy** at `<other-project>/src/claudekit/` -- the neighbouring
  pyproject describes the HOST project, so the name check rejects it. Falls to
  metadata.
* **A vendored copy of a claude-kit FORK** (its own pyproject, name kept) --
  reports the fork's pyproject version. That is the source `install.sh` would
  stamp from that same tree, so agreement is preserved, which is the property
  being defended.
* **Zipapp / frozen / any import without a real file** -- `__file__` missing or
  unresolvable, or `pyproject.toml` unreadable inside the archive: every access
  is guarded and returns None. Falls to metadata.
* **A malformed or version-less `[project]` table** -- no version parsed, so
  None. Falls to metadata. A partially-written pyproject can never make the CLI
  report garbage.

Stdlib only, Python 3.9 target: 3.9 has no `tomllib`, so the `[project]` table
is scanned line-wise with the same anchoring `install.sh` uses (an unanchored
`^version` match would take a `version =` key from any `[tool.*]` table sorted
above it -- the silent-wrong-value shape this module removes).
"""

import re
from importlib import metadata
from pathlib import Path
from typing import Optional

#: PyPI distribution name. The import package and console scripts are
#: `claudekit`/`ck`; the distribution is `claude-kit` (`claudekit` was taken).
DIST_NAME = "claude-kit"

#: Fallback when neither a source tree nor installed metadata can answer.
UNKNOWN = "unknown"


def _project_field(text: str, key: str) -> Optional[str]:
    """Read `key` from the `[project]` table only, or None.

    Table-scoped on purpose: a repo-root pyproject.toml also carries `[tool.ruff]`,
    `[tool.mypy]` and friends, and a global regex would happily return a `version`
    or `name` from any of them.
    """
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


def source_version() -> Optional[str]:
    """The version of the source checkout this module was imported from, or None.

    None means "this is not a claude-kit source tree" -- never a guess.
    """
    try:
        here = Path(__file__).resolve()
    except (NameError, OSError):  # no real file behind the module (zipapp, frozen)
        return None
    # <root>/src/claudekit/_version.py: parents[0]=claudekit, [1]=src, [2]=<root>.
    # The `src` check is what separates an editable src-layout checkout from an
    # installed `site-packages/claudekit/`, and it is the cheap half of the guard.
    if len(here.parents) < 3 or here.parents[1].name != "src":
        return None
    try:
        text = (here.parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return None
    # The expensive half: the neighbouring pyproject must describe THIS project.
    # Without it, a vendored copy under someone else's src/ would report their
    # version as ClaudeKit's.
    if _project_field(text, "name") != DIST_NAME:
        return None
    return _project_field(text, "version")


def resolve_version() -> str:
    """The version to report: source checkout first, then installed metadata."""
    from_source = source_version()
    if from_source:
        return from_source
    try:
        return metadata.version(DIST_NAME)
    except metadata.PackageNotFoundError:
        return UNKNOWN

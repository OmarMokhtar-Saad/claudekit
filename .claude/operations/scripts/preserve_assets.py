"""Carry a project's custom assets from a pre-update backup into the new tree.

Extracted from a 178-line heredoc inside install.sh (2026-08-29). In the heredoc this
logic was invisible to ruff and mypy -- which lint `.claude/operations/scripts/` -- and
it produced three defects in three review rounds: a `shutil.copy2` that dereferenced
symlinks and aborted the whole loop on the first dangling one (656 files lost from one
project), a directory-symlink class that `os.walk` never surfaces in `names`, and a
`_within` that resolved only one side (macOS /var -> /private/var read every legitimate
link as an escape). It also crossed the silent-failure scanner's MAX_JOIN_LINES, leaving
the rest of install.sh unscanned.

Everything here is import-safe and parameter-driven so it can be tested directly rather
than through a full install.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from typing import List, Optional, Sequence, Set, Tuple

# The legacy fallback, used ONLY when the backup carries no manifest. It was
# ("agents", "commands", "skills"), which silently dropped a project's custom hooks/ and
# operations/ on every pre-manifest update -- measured: rest-framework lost
# hooks/format-compile.sh and hooks/quick-verify.sh that way. Widened to the directories
# that hold AUTHORED content.
#
# `reports/` is deliberately NOT here: this repo treats reports as generated, not source
# ("re-derive, don't cite" -- CLAUDE.md), and the installer writes `.claude/reports/` into
# .gitignore. Resurrecting a scratch report a user had cleaned up, and relabelling it
# "custom" in `ck diff`, is not preservation.
ASSET_DIRS: Tuple[str, ...] = (
    "agents", "commands", "skills", "hooks", "operations", "modes",
    "local", "plans", "knowledge", "defects",
)

# Must stay in step with NEVER_MANAGED in install.sh's manifest block.
SKIP_NAMES = {"hooks.log", "settings.local.json", ".claudekit-manifest.json"}


class PreserveResult:
    """What the walk did. Kept separate from printing so tests can assert on it."""

    def __init__(self) -> None:
        self.restored: List[str] = []
        self.refused: List[Tuple[str, str]] = []
        self.failed: List[Tuple[str, str]] = []
        self.had_manifest: bool = False


def load_old_manifest(backup: str) -> Optional[Set[str]]:
    """The set of files the OLD kit owned, or None when the backup predates manifests."""
    mpath = os.path.join(backup, ".claudekit-manifest.json")
    if not os.path.exists(mpath):
        return None
    try:
        with open(mpath, encoding="utf-8") as fh:
            return set(json.load(fh).get("files", {}))
    except (ValueError, OSError):
        return None


def within(child: str, parent: str) -> bool:
    """Both sides through realpath, which is the whole trick.

    On macOS a temp dir is /var/folders/... -- itself a symlink to /private/var/...
    Resolving only the child made every legitimate link look like an escape, and the
    refusal policy silently ate three passing tests before this was normalised.
    """
    child = os.path.realpath(child)
    parent = os.path.realpath(parent)
    return child == parent or child.startswith(os.path.join(parent, ""))


def link_refusal(path: str, target: str, project_root: str) -> Optional[str]:
    """Why this symlink must NOT be recreated, or None to carry it over.

    This is the one place that would rebuild an arbitrary symlink target verbatim.
    `security/path_guard.py` rejects targets escaping the project root and
    `review-record.py:_safe_write` refuses to write THROUGH a link at any level;
    recreating whatever a backup happens to contain is the same class of trust, so it
    gets the same answer. A refusal is reported, never silent.
    """
    dest_of_link = os.path.join(os.path.dirname(path), os.readlink(path))
    resolved = os.path.realpath(dest_of_link)
    if not within(resolved, project_root):
        return "target escapes the project"
    # A DIRECTORY link whose target contains the link's own location is a cycle:
    # `plans/x/shadow/.claude -> <project>/.claude` resolves back to the tree it lives in.
    # This never descends it, but baking a self-reference into the installed tree hands
    # the next `find -L`, `du`, or followlinks=True walker an infinite descent.
    if os.path.isdir(dest_of_link) and within(os.path.realpath(target), resolved):
        return "self-referential directory link (target is an ancestor of it)"
    return None


def carry_over(path: str, target: str) -> None:
    """Copy one backup entry into the new tree. Symlinks stay symlinks.

    `shutil.copy2` DEREFERENCES: on a link it copies the target's bytes, silently turning
    the project's symlink into a regular file -- and on a DANGLING link it raises
    FileNotFoundError. Recreating from `os.readlink` preserves what the project actually
    had and cannot fail on a target that no longer exists.
    """
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.islink(path):
        os.symlink(os.readlink(path), target)
    else:
        shutil.copy2(path, target)


def preserve_entry(path: str, rel: str, dest: str, project_root: str,
                   result: PreserveResult) -> bool:
    """Apply the refusal policy, then carry the entry over. True if restored."""
    target = os.path.join(dest, rel)
    if os.path.islink(path):
        why = link_refusal(path, target, project_root)
        if why is not None:
            result.refused.append((rel, why))
            return False
    carry_over(path, target)
    return True


def _is_custom(rel: str, old_manifest: Optional[Set[str]]) -> bool:
    """Is this backup entry the PROJECT's rather than the old kit's?"""
    if old_manifest is not None:
        # Precise: old-kit files (removed/renamed since) are NOT resurrected.
        return rel not in old_manifest
    return rel.split(os.sep)[0] in ASSET_DIRS


def preserve_tree(backup: str, dest: str) -> PreserveResult:
    """Walk the backup and carry every custom entry the new tree lacks."""
    result = PreserveResult()
    old_manifest = load_old_manifest(backup)
    result.had_manifest = old_manifest is not None
    # realpath, not abspath: `within` normalises both sides itself, but leaving an
    # unresolved root here is a footgun for the next direct user of it.
    project_root = os.path.dirname(os.path.realpath(dest))

    for root, dirs, names in os.walk(backup):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        # A symlink to an EXISTING directory is classified as a directory, so it lands in
        # `dirs` and a loop over `names` alone can never carry it over -- measured: 36 of
        # them under one project's plans/, silently dropped on every update. (A DANGLING
        # dir-symlink is classified as a file and does reach `names`, which is why this
        # only shows up for links whose target still exists.) Removed from `dirs` so the
        # walk cannot descend through them into the live tree.
        for d in list(dirs):
            link_path = os.path.join(root, d)
            if not os.path.islink(link_path):
                continue
            dirs.remove(d)
            _consider(link_path, backup, dest, project_root, old_manifest, result)
        for n in names:
            if n in SKIP_NAMES or n.endswith(".pyc"):
                continue
            _consider(os.path.join(root, n), backup, dest, project_root,
                      old_manifest, result)
    return result


def _consider(path: str, backup: str, dest: str, project_root: str,
              old_manifest: Optional[Set[str]], result: PreserveResult) -> None:
    rel = os.path.relpath(path, backup)
    # lexists, not exists: a DANGLING symlink already in the new tree is present and must
    # be left alone, where `exists` would read it as absent.
    if os.path.lexists(os.path.join(dest, rel)):
        return
    if not _is_custom(rel, old_manifest):
        return
    # Per-entry, and this is the whole point. One unreadable entry used to abort the LOOP:
    # a single dangling symlink under plans/ cost qa-agents 656 custom files, because
    # everything the walk had not yet reached was abandoned under one yellow line saying
    # the files "remain in the backup". Isolating each entry makes the damage proportional
    # to the fault. Broad on purpose: nothing here may end the walk.
    try:
        if preserve_entry(path, rel, dest, project_root, result):
            result.restored.append(rel)
    except Exception as e:  # one bad entry must not end the walk -- see comment above
        result.failed.append((rel, e.__class__.__name__))


def format_report(result: PreserveResult) -> List[str]:
    """The operator-facing lines. Separate from the walk so tests can assert on both."""
    out: List[str] = []
    for rel in sorted(result.restored):
        out.append("    preserved: " + rel)
    if result.restored and not result.had_manifest:
        out.append("    (pre-manifest backup: preserved files may include assets from an")
        out.append("     older kit version -- run `ck diff` to review the custom list)")
    if result.refused:
        out.append("    %d symlink(s) NOT recreated (kept in the backup):"
                   % len(result.refused))
        for rel, why in sorted(result.refused)[:10]:
            out.append("      %s -- %s" % (rel, why))
        if len(result.refused) > 10:
            out.append("      ... and %d more" % (len(result.refused) - 10))
    if result.failed:
        # A count and names, not just "something failed". The old message gave no scale,
        # so losing one scratch file and losing 656 read identically.
        out.append("    WARNING: %d file(s) could NOT be preserved; they remain in the "
                   "backup:" % len(result.failed))
        for rel, kind in sorted(result.failed)[:10]:
            out.append("      %s (%s)" % (rel, kind))
        if len(result.failed) > 10:
            out.append("      ... and %d more" % (len(result.failed) - 10))
    return out


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: preserve_assets.py <backup_dir> <dest_dir>", file=sys.stderr)
        return 2
    result = preserve_tree(argv[0], argv[1])
    for line in format_report(result):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

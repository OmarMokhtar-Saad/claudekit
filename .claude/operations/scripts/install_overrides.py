#!/usr/bin/env python3
"""What a project overrides in a kit install, read from its own tree before the copy.

Two decisions install.sh used to make blindly (measured 2026-09-22 on qa-agents, where
`ck update` undid two committed changes on every run):

1. **Parked / removed assets.** The installer copied every agent, command, skill and hook,
   so an agent a project had moved to `agents-unused/` and a command it had deleted came
   back with each update. `skip_list` answers "which kit paths must NOT be installed here"
   from three signals, all read from the project (`.claude/`) before it is replaced:

   - explicit `parked` / `removed` lists in `.claudekit-manifest.json` (carried forward
     into the new manifest, so the decision survives the receipt being rewritten);
   - a receipted prompt asset (`agents/`, `commands/`, `skills/`) that is absent on disk:
     the project deleted it, and a deletion is a decision, not drift. Hooks are excluded
     from this inference on purpose -- settings.json wires hooks by path and a missing
     wired hook makes Claude Code block every tool call, so a hook comes back unless the
     manifest names it explicitly;
   - `<dir>-unused/<name>` beside `<dir>/` (the fleet's parking convention): the file is
     parked, and `<dir>/<name>` is skipped.

2. **settings.json.** The installer copied the kit's file over the project's, keeping only
   `settings.local.json`; a project's committed `autoCompactWindow`, `env` thresholds,
   `permissions.deny` and `skillOverrides` were lost on every update. `merge_settings`
   replaces the kit-managed key (`hooks`) and keeps every other key the project has; kit
   keys the project lacks are added so new defaults still reach it.

Stdlib only. Exercised by tests/test_install_overrides.py (direct) and by the installer
tests that run install.sh end to end.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Sequence, Set, Tuple

# Keys the kit owns outright: the project's copy is replaced, never merged. Hooks are
# wired by path to the scripts the same install ships, so a stale project copy would
# reference hooks that no longer exist (or miss ones that now do).
KIT_MANAGED_KEYS = ("hooks",)
# Per-entry decision lists: a project that declares one keeps it verbatim. Deep-merging
# the kit's entries in would re-hide a skill or re-deny a tool the project chose to keep.
PROJECT_OWNED_KEYS = ("skillOverrides", "permissions")

# Prompt-asset roots where "receipted but gone" means "the project removed it".
INFERRED_REMOVAL_ROOTS = ("agents/", "commands/", "skills/")

# Roots whose `<root>-unused/` sibling marks parked files.
PARKABLE_ROOTS = ("agents", "commands", "skills", "hooks")


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and v and not v.startswith("/")]


def skip_list(final_dest: str) -> Tuple[List[str], List[str]]:
    """Return (parked, removed): kit-relative paths install.sh must not write.

    ``final_dest`` is the project's existing ``.claude/`` (may not exist: fresh install).
    Both lists are sorted and disjoint; a path named in both is reported as parked.
    """
    manifest = _read_json(os.path.join(final_dest, ".claudekit-manifest.json"))
    if not isinstance(manifest, dict):
        manifest = {}
    parked: Set[str] = set(_str_list(manifest.get("parked")))
    removed: Set[str] = set(_str_list(manifest.get("removed")))

    files = manifest.get("files")
    if isinstance(files, dict):
        for rel in files:
            if not isinstance(rel, str) or not rel.startswith(INFERRED_REMOVAL_ROOTS):
                continue
            if not os.path.exists(os.path.join(final_dest, rel)):
                removed.add(rel)

    for root in PARKABLE_ROOTS:
        unused = os.path.join(final_dest, root + "-unused")
        if not os.path.isdir(unused):
            continue
        for name in os.listdir(unused):
            if name.startswith("."):
                continue
            parked.add(root + "/" + name)

    removed -= parked
    return sorted(parked), sorted(removed)


def write_skip_files(final_dest: str, flat_out: str, json_out: str) -> int:
    """Write the flat list bash greps (one path per line) and the JSON the manifest reads."""
    parked, removed = skip_list(final_dest)
    with open(flat_out, "w", encoding="utf-8") as fh:
        for rel in parked + removed:
            fh.write(rel + "\n")
    with open(json_out, "w", encoding="utf-8") as fh:
        json.dump({"parked": parked, "removed": removed}, fh, indent=2)
    return 0


def _deep_merge(kit: Any, project: Any) -> Any:
    """Project wins at every leaf; kit-only keys are added. Lists and scalars are leaves."""
    if isinstance(kit, dict) and isinstance(project, dict):
        merged: Dict[str, Any] = dict(kit)
        for key, value in project.items():
            merged[key] = _deep_merge(kit[key], value) if key in kit else value
        return merged
    return project


def merge_settings(kit: Dict[str, Any], project: Dict[str, Any]) -> Dict[str, Any]:
    """Kit-managed keys come from the kit; everything else the project has is kept."""
    merged = _deep_merge(kit, project)
    for key in PROJECT_OWNED_KEYS:
        if key in project:
            merged[key] = project[key]
    for key in KIT_MANAGED_KEYS:
        if key in kit:
            merged[key] = kit[key]
        else:
            merged.pop(key, None)
    return merged


def write_merged_settings(kit_path: str, project_path: str, out_path: str) -> int:
    kit = _read_json(kit_path)
    if not isinstance(kit, dict):
        sys.stderr.write(f"install_overrides: kit settings.json unreadable: {kit_path}\n")
        return 1
    project = _read_json(project_path)
    if not isinstance(project, dict):
        # Fail closed: overwriting an unparseable file would destroy whatever the project
        # meant by it. The backup keeps it, the message says what to fix.
        sys.stderr.write(
            f"install_overrides: project settings.json is not a JSON object: {project_path}\n"
            "  Fix or remove it, then re-run the install.\n")
        return 1
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(merge_settings(kit, project), fh, indent=2)
        fh.write("\n")
    return 0


def main(argv: Sequence[str]) -> int:
    if len(argv) == 4 and argv[0] == "skip-list":
        return write_skip_files(argv[1], argv[2], argv[3])
    if len(argv) == 4 and argv[0] == "settings":
        return write_merged_settings(argv[1], argv[2], argv[3])
    sys.stderr.write(
        "usage: install_overrides.py skip-list <final_dest> <flat_out> <json_out>\n"
        "       install_overrides.py settings <kit_settings> <project_settings> <out>\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

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

import ast
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
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

# Files the installer merges rather than copies; they are never "kept" wholesale.
MERGED_FILES = ("settings.json", "skills/skills-registry.json")
# Local-only by definition; never receipted, never compared.
NEVER_MANAGED = ("hooks.log", "settings.local.json", ".claudekit-manifest.json",
                 "session-footprint.md")
# Project state the kit tree may hold a copy of (the kit's own runtime, or a seed file):
# never receipted, compared, kept or merged, so an update never writes a .kit-new for it.
# agent-memory/README.md is the shipped entry-format contract and stays managed.
RUNTIME_STATE_DIRS = ("runtime/", "hooks/.state/", "agent-memory/")
RUNTIME_STATE_FILES = ("knowledge/rejections/INDEX.jsonl", "plans/archive/README.md")
MANIFEST = ".claudekit-manifest.json"


def is_unmanaged(rel: str) -> bool:
    """True for a path under .claude/ that is project data, never a kit asset.
    install.sh's manifest writer and scripts/gen-kit-history.py import this."""
    rel = rel.replace(os.sep, "/")
    name = rel.rsplit("/", 1)[-1]
    if name in NEVER_MANAGED or name.endswith((".pyc", ".kit-new")):
        return True
    if rel in RUNTIME_STATE_FILES or (rel.startswith("hooks/") and name.endswith(".log")):
        return True
    return rel.startswith(RUNTIME_STATE_DIRS) and rel != "agent-memory/README.md"


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
        # Project key order first so a committed file round-trips byte for byte;
        # kit-only keys are appended.
        merged: Dict[str, Any] = {}
        for key, value in project.items():
            merged[key] = _deep_merge(kit[key], value) if key in kit else value
        for key, value in kit.items():
            if key not in merged:
                merged[key] = value
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


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def modified_files(final_dest: str, staging: str) -> Dict[str, str]:
    """Managed files whose on-disk bytes differ from the hash the last install receipted.

    Returns ``{rel: kit_hash}`` where ``kit_hash`` is the sha256 of the copy the new
    install staged for that path. The manifest records that kit hash for a kept file, so
    the file stays "locally modified" and is kept again on the next update. Merged files,
    never-managed files, ``runtime/`` and paths the new kit does not ship are excluded;
    a shipped path on disk that the receipt never recorded is kept too. A file whose
    bytes already equal the kit's is never kept: the kit copy wins, mode included.
    """
    manifest = _read_json(os.path.join(final_dest, MANIFEST))
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        return {}
    out: Dict[str, str] = {}
    # Walk what the new kit ships, not the receipt: a shipped file present on disk that
    # the receipt never recorded has unknown provenance and is kept like a modified one.
    for root, dirs, names in os.walk(staging):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(root, name), staging)
            if rel in MERGED_FILES or is_unmanaged(rel):
                continue
            on_disk = os.path.join(final_dest, rel)
            if not os.path.isfile(on_disk):
                continue
            try:
                on_hash = _sha256(on_disk)
                if rel in files and on_hash == files[rel]:
                    continue
                kit_hash = _sha256(os.path.join(root, name))
                if on_hash == kit_hash:
                    # Same bytes: only the mode can differ, and the kit copy carries the
                    # right one. Keeping it (cp -p) would install the project's 644 and
                    # receipt a match, so the NEXT run flips it to 755 -- measured on the
                    # 2026-09-23 fleet run. Let the kit copy win on the first run.
                    continue
                out[rel] = kit_hash
            except OSError:
                continue
    return out


def write_keep_files(final_dest: str, staging: str, flat_out: str, json_out: str) -> int:
    """Flat list (one rel per line) for bash to copy back; JSON ``{rel: kit_hash}`` for the manifest."""
    kept = modified_files(final_dest, staging)
    with open(flat_out, "w", encoding="utf-8") as fh:
        for rel in kept:
            fh.write(rel + "\n")
    with open(json_out, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, indent=2)
    return 0


def _entry_key(item: Any) -> Any:
    if isinstance(item, dict):
        for key in ("id", "name"):
            if isinstance(item.get(key), str):
                return item[key]
    return None


def merge_registry(kit: Any, project: Any) -> Any:
    """Kit entries update shared ones; project-only entries and keys survive; kit-only are appended.

    Dicts recurse in project key order. Lists of keyed dicts (``id``/``name``) keep project
    order, take the kit's version of a shared entry, keep project-only entries and append
    kit-only ones. Lists of strings are project + kit-only. Scalars are the kit's, except
    ``lastUpdated`` which is the later of the two.
    """
    if isinstance(kit, dict) and isinstance(project, dict):
        merged: Dict[str, Any] = {}
        for key, value in project.items():
            if key not in kit:
                merged[key] = value
            elif key == "lastUpdated" and isinstance(value, str) and isinstance(kit[key], str):
                merged[key] = max(value, kit[key])
            else:
                merged[key] = merge_registry(kit[key], value)
        for key, value in kit.items():
            if key not in merged:
                merged[key] = value
        return merged
    if isinstance(kit, list) and isinstance(project, list):
        kit_keyed = {_entry_key(i): i for i in kit if _entry_key(i) is not None}
        if kit_keyed or any(_entry_key(i) is not None for i in project):
            out: List[Any] = []
            seen: Set[Any] = set()
            for item in project:
                key = _entry_key(item)
                if key is None:
                    out.append(item)
                    continue
                seen.add(key)
                out.append(kit_keyed.get(key, item))
            out.extend(i for i in kit if _entry_key(i) is not None and _entry_key(i) not in seen)
            return out
        if all(isinstance(i, str) for i in kit + project):
            return list(project) + [i for i in kit if i not in project]
        return kit
    return kit


def write_merged_registry(kit_path: str, project_path: str, out_path: str) -> int:
    kit = _read_json(kit_path)
    project = _read_json(project_path)
    if not isinstance(kit, dict) or not isinstance(project, dict):
        sys.stderr.write(
            f"install_overrides: skills-registry.json unreadable ({kit_path} / {project_path})\n")
        return 1
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(merge_registry(kit, project), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return 0


# ---- kit history: stale copy vs real edit, 3-way merge, scripts as one unit ------------
# `modified_files` keeps every managed file whose bytes differ from the receipt. Measured
# 2026-09-23 on qa-agents: 46 files kept, most of them byte-identical to an OLDER kit
# version -- stale copies, not edits -- so fixes never reached the project. The history
# (.claudekit-history.json, built at release by scripts/gen-kit-history.py) lists the
# sha256 of every version the kit ever shipped for a path; a file matching one is stale
# and is replaced. A file matching none is a project edit: it is 3-way merged (base = the
# shipped version the receipt names, fetched from the kit's git by blob id) and, on a
# conflict, kept with the new kit copy beside it as `<file>.kit-new`.
HISTORY = ".claudekit-history.json"
KIT_NEW = ".kit-new"
SCRIPTS_DIR = "operations/scripts/"


def load_history(path: str) -> Dict[str, Dict[str, List[str]]]:
    """``{rel: {sha256: [version, git_blob]}}``; empty when absent or malformed."""
    data = _read_json(path)
    files = data.get("files") if isinstance(data, dict) else None
    return files if isinstance(files, dict) else {}


def _git_blob(kit_git: str, blob: str) -> Any:
    """Bytes of ``blob`` in the kit's git, or None (no git, not a repo, unknown blob)."""
    if not kit_git or not blob:
        return None
    try:
        proc = subprocess.run(["git", "-C", kit_git, "cat-file", "blob", blob],
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _merge3(ours: str, base: bytes, theirs: str) -> Tuple[int, bytes]:
    """``git merge-file -p``: (0, merged) when clean, (>0, _) on conflict, (-1, _) unusable."""
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(base)
        base_path = fh.name
    try:
        proc = subprocess.run(["git", "merge-file", "-p", "-L", "project", "-L", "base",
                               "-L", "kit", ours, base_path, theirs],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return -1, b""
    finally:
        os.unlink(base_path)
    return (proc.returncode, proc.stdout) if proc.returncode >= 0 else (-1, b"")


def _diff_size(a: str, b: str) -> int:
    """Changed lines between two files (added + removed); -1 when not text."""
    try:
        with open(a, encoding="utf-8") as fa, open(b, encoding="utf-8") as fb:
            left, right = fa.readlines(), fb.readlines()
    except (OSError, UnicodeDecodeError):
        return -1
    return sum(1 for line in difflib.unified_diff(left, right, n=0)
               if line[:1] in "+-" and not line.startswith(("+++", "---")))


def _module_api(source: Any) -> Any:
    """Top-level names a Python module (bytes) defines, or None when it does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError):
        return None
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def _needs(path: str, siblings: Set[str]) -> Dict[str, Set[str]]:
    """``{sibling_module: names used}`` for the sibling scripts ``path`` imports."""
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return {}
    needs: Dict[str, Set[str]] = {}
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in siblings and not node.level:
            needs.setdefault(node.module, set()).update(
                a.name for a in node.names if a.name != "*")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in siblings:
                    aliases[alias.asname or alias.name] = alias.name
                    needs.setdefault(alias.name, set())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in aliases):
            needs[aliases[node.value.id]].add(node.attr)
    return needs


def _final_bytes(final_dest: str, rel: str, merged: Dict[str, bytes]) -> Any:
    """What a kept file will contain: its merge result, else the project's copy."""
    if rel in merged:
        return merged[rel]
    try:
        with open(os.path.join(final_dest, rel), "rb") as fh:
            return fh.read()
    except OSError:
        return None


def reconcile(final_dest: str, staging: str, history_path: str, kit_git: str,
              apply: bool = True) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """Decide every managed file the project changed; return (kept, report).

    ``kept`` is ``{rel: kit_hash}`` for files whose project copy stays (receipted with the
    kit hash, as ``modified_files`` does). ``report`` has one row per decision:
    ``status`` stale (replaced) | merged (clean 3-way merge applied) | edited (kept; the
    release did not change the file) | conflict (kept; ``<rel>.kit-new`` written) | held
    (kit copy of a script held back: it needs names a kept sibling lacks), plus
    ``release_changed`` and ``diff`` (changed lines, project vs kit). With ``apply`` the
    staging tree is updated; without it nothing is written (``ck update --show-kept``).
    """
    manifest = _read_json(os.path.join(final_dest, MANIFEST))
    receipt = manifest.get("files") if isinstance(manifest, dict) else None
    receipt = receipt if isinstance(receipt, dict) else {}
    history = load_history(history_path)
    kept: Dict[str, str] = {}
    merged_bytes: Dict[str, bytes] = {}  # the final content of a clean merge
    report: List[Dict[str, Any]] = []

    def row(rel: str, status: str, **extra: Any) -> None:
        entry: Dict[str, Any] = {"path": rel, "status": status}
        entry.update(extra)
        report.append(entry)

    for rel, kit_hash in modified_files(final_dest, staging).items():
        ours = os.path.join(final_dest, rel)
        theirs = os.path.join(staging, rel)
        on_hash = _sha256(ours)
        diff = _diff_size(ours, theirs)
        shipped = (history.get(rel) or {}).get(on_hash)
        if shipped:
            # A version the kit shipped, byte for byte: stale, not an edit. Kit copy wins.
            row(rel, "stale", was=shipped[0], release_changed=True, diff=diff)
            continue
        base_hash = receipt.get(rel)
        release_changed = base_hash != kit_hash
        if not release_changed:
            # The kit did not change this file since the receipt: nothing to merge.
            kept[rel] = kit_hash
            row(rel, "edited", release_changed=False, diff=diff)
            continue
        base_entry = (history.get(rel) or {}).get(base_hash) if base_hash else None
        base = _git_blob(kit_git, base_entry[1]) if base_entry else None
        code, merged = _merge3(ours, base, theirs) if base is not None else (-1, b"")
        if code == 0:
            merged_bytes[rel] = merged
            if apply:
                with open(theirs, "wb") as fh:
                    fh.write(merged)
            kept[rel] = kit_hash
            row(rel, "merged", release_changed=True, diff=diff)
            continue
        kept[rel] = kit_hash
        row(rel, "conflict", release_changed=True, diff=diff,
            reason="merge conflict" if code > 0 else "no base version to merge against")

    # operations/scripts/ is one unit: a refreshed script must not import a name a kept
    # sibling does not define. Such a script is held at the project's version too (its
    # kit copy goes to .kit-new); repeat until nothing more is held.
    scripts = os.path.join(staging, SCRIPTS_DIR)
    if os.path.isdir(scripts):
        modules = {n[:-3] for n in os.listdir(scripts) if n.endswith(".py")}
        changed = True
        while changed:
            changed = False
            kept_api = {m: _module_api(_final_bytes(final_dest, SCRIPTS_DIR + m + ".py",
                                                    merged_bytes))
                        for m in modules if SCRIPTS_DIR + m + ".py" in kept}
            for name in sorted(modules):
                rel = SCRIPTS_DIR + name + ".py"
                if rel in kept:
                    continue
                missing = sorted(
                    "%s.%s" % (mod, n)
                    for mod, used in _needs(os.path.join(scripts, name + ".py"),
                                            set(kept_api)).items()
                    for n in used if kept_api[mod] is not None and n not in kept_api[mod])
                ours = os.path.join(final_dest, rel)
                if not missing or not os.path.isfile(ours):
                    continue
                kept[rel] = _sha256(os.path.join(scripts, name + ".py"))
                report[:] = [r for r in report if r["path"] != rel]
                row(rel, "held", release_changed=True,
                    diff=_diff_size(ours, os.path.join(scripts, name + ".py")),
                    reason="needs %s from a kept sibling" % ", ".join(missing))
                changed = True

    if apply:
        for entry in report:
            rel = entry["path"]
            if entry["status"] in ("conflict", "held"):
                shutil.copy2(os.path.join(staging, rel), os.path.join(staging, rel + KIT_NEW))
            if entry["status"] in ("edited", "conflict", "held"):
                shutil.copy2(os.path.join(final_dest, rel), os.path.join(staging, rel))
    report.sort(key=lambda r: r["path"])
    return kept, report


def write_reconcile(final_dest: str, staging: str, history_path: str, kit_git: str,
                    json_out: str, report_out: str) -> int:
    """Apply ``reconcile`` to staging; JSON ``{rel: kit_hash}`` for the manifest, the report
    for the log (one line per decision on stdout, the rows as JSON in ``report_out``)."""
    kept, report = reconcile(final_dest, staging, history_path, kit_git)
    with open(json_out, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, indent=2)
    with open(report_out, "w", encoding="utf-8") as fh:
        json.dump({"rows": report}, fh, indent=2)
    for entry in report:
        print(format_row(entry))
    return 0


def format_row(entry: Dict[str, Any]) -> str:
    """One log line: what happened to a file the project changed."""
    rel, status = entry["path"], entry["status"]
    diff = entry.get("diff", -1)
    size = "binary" if diff < 0 else "%d line(s) differ" % diff
    changed = "release-changed %s" % ("yes" if entry.get("release_changed") else "no")
    if status == "stale":
        return "updated %s (was kit v%s)" % (rel, entry.get("was", "?"))
    if status == "merged":
        return "merged %s (project edits kept, kit changes applied)" % rel
    if status == "edited":
        return "Kept locally-modified %s (edited, %s, %s)" % (rel, changed, size)
    return "Kept locally-modified %s (%s, %s, %s; %s; kit copy in %s%s)" % (
        rel, status, changed, size, entry.get("reason", ""), rel, KIT_NEW)


def main(argv: Sequence[str]) -> int:
    if len(argv) == 4 and argv[0] == "skip-list":
        return write_skip_files(argv[1], argv[2], argv[3])
    if len(argv) == 4 and argv[0] == "settings":
        return write_merged_settings(argv[1], argv[2], argv[3])
    if len(argv) == 4 and argv[0] == "registry":
        return write_merged_registry(argv[1], argv[2], argv[3])
    if len(argv) == 5 and argv[0] == "keep-modified":
        return write_keep_files(argv[1], argv[2], argv[3], argv[4])
    if len(argv) == 7 and argv[0] == "reconcile":
        return write_reconcile(argv[1], argv[2], argv[3], argv[4], argv[5], argv[6])
    sys.stderr.write(
        "usage: install_overrides.py skip-list <final_dest> <flat_out> <json_out>\n"
        "       install_overrides.py settings <kit_settings> <project_settings> <out>\n"
        "       install_overrides.py registry <kit_registry> <project_registry> <out>\n"
        "       install_overrides.py keep-modified <final_dest> <staging> <flat_out> <json_out>\n"
        "       install_overrides.py reconcile <final_dest> <staging> <history> <kit_git> "
        "<json_out> <report_out>\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

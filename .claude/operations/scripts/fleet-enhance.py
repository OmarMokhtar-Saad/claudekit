#!/usr/bin/env python3
"""Bring every kitted fleet repo up to the current corpus WITHOUT reinstalling.

`install.sh --force` refreshes by moving `.claude/` aside and restoring what it can
guess. On a project with no `.claudekit-manifest.json` that guess is a directory
heuristic (`agents/`, `commands/`, `skills/` only), which silently strands plans,
rules and project-specific hooks in the backup. This does the opposite: it never
moves, never deletes, and never overwrites a file the project has edited.

Classification is exact where a manifest exists, because the manifest records
sha256 per installed file:

    MISSING    in the kit, absent downstream            -> ADD
    PRISTINE   present, hash == manifest                -> UPDATE to current
    MODIFIED   present, hash != manifest                -> SKIP and report
    LOCAL      present, absent from kit and manifest    -> LEAVE ALONE

Without a manifest the tool degrades honestly: it ADDs what is missing and refuses
to update anything, because it cannot tell a pristine kit file from a customised
one and guessing is what this tool exists to avoid.

Nothing is committed. Every repo is left dirty for the owner.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.expanduser("~/IdeaProjects")
KIT = os.path.join(ROOT, "claudekit", ".claude")
PROJECTS = ["ai-agent-system", "ApiForge", "AppiumLens", "AutomationApp", "Eatizaz",
            "Lean", "LeanApis", "MobileUIAutomator", "qa-agents", "qaforge-ai",
            "rest-framework", "SehhatyApp", "shsmartassistant-qa"]

# Directories the kit owns. `plans/`, `reports/`, `knowledge/`, `state/`, `locks/`
# are deliberately ABSENT: they are project working data, not corpus.
SYNC_DIRS = ("skills", "agents", "commands", "hooks", "modes")

# Never touched, at any classification. settings.local.json carries the local hook
# profile; hooks.log and runtime counters are state, not assets.
NEVER = {"hooks.log", "settings.local.json", ".claudekit-manifest.json",
         "compact-counter.txt", "cost-tracker.log", "skills-registry.json"}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def kit_files():
    """Relative paths of every corpus file the kit ships, under SYNC_DIRS."""
    out = []
    for sub in SYNC_DIRS:
        base = os.path.join(KIT, sub)
        if not os.path.isdir(base):
            continue
        for root, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for n in sorted(names):
                if n in NEVER or n.endswith(".pyc"):
                    continue
                out.append(os.path.relpath(os.path.join(root, n), KIT))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default=os.path.join(
        ROOT, "claudekit", ".claude", "reports", "fleet-enhance.md"))
    args = ap.parse_args()
    dry = args.dry_run
    files = kit_files()
    # str -> {added: [str], updated: [str], modified: [(str, str)],
    #         unchanged: int, manifest: bool}
    log: Dict[str, Dict[str, Any]] = {}

    for p in PROJECTS:
        dest = os.path.join(ROOT, p, ".claude")
        if not os.path.isdir(dest):
            continue
        mpath = os.path.join(dest, ".claudekit-manifest.json")
        manifest: Optional[Dict[str, str]] = None
        if os.path.isfile(mpath):
            try:
                with open(mpath) as fh:
                    manifest = json.load(fh).get("files", {})
            except (ValueError, OSError):
                manifest = None

        added: List[str] = []
        updated: List[str] = []
        modified: List[Tuple[str, str]] = []
        unchanged = 0
        for rel in files:
            src = os.path.join(KIT, rel)
            dst = os.path.join(dest, rel)
            if not os.path.exists(dst):
                added.append(rel)
                if not dry:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                continue
            if sha(src) == sha(dst):
                unchanged += 1
                continue
            if manifest is None:
                # Cannot distinguish stale-kit from customised. Refuse, do not guess.
                modified.append((rel, "no manifest — cannot prove it is unmodified"))
                continue
            recorded = manifest.get(rel)
            if recorded is None:
                modified.append((rel, "not in manifest — treated as project-local"))
            elif recorded == sha(dst):
                updated.append(rel)
                if not dry:
                    shutil.copy2(src, dst)
            else:
                modified.append((rel, "edited since install — customisation preserved"))

        # Keep the manifest truthful about what this run installed.
        if manifest is not None and (added or updated) and not dry:
            try:
                with open(mpath) as fh:
                    doc = json.load(fh)
                for rel in added + updated:
                    doc.setdefault("files", {})[rel] = sha(os.path.join(dest, rel))
                doc["last_enhanced"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                with open(mpath, "w") as fh:
                    json.dump(doc, fh, indent=2)
                    fh.write("\n")
            except (ValueError, OSError) as e:
                modified.append((".claudekit-manifest.json", f"not updated ({e})"))

        log[p] = {"added": added, "updated": updated, "modified": modified,
                  "unchanged": unchanged, "manifest": manifest is not None}

    lines = [
        "# Fleet enhancement — no reinstall, nothing moved aside",
        "",
        f"**Run:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"**Mode:** {'DRY RUN' if dry else 'EXECUTED'} · **Repos:** {len(log)}",
        "",
        "Additive and non-destructive by construction: **nothing is deleted, nothing is "
        "moved aside, and no file the project has edited is overwritten.** Every repo is "
        "left uncommitted.",
        "",
        "Classification is exact where a `.claudekit-manifest.json` exists, because it "
        "records sha256 per installed file. A file is UPDATED only when its current hash "
        "still matches what the kit installed — i.e. nobody has touched it. Anything else "
        "is reported, never written.",
        "",
        "| Project | Added | Updated | Preserved (edited) | Already current | Manifest |",
        "|---|---|---|---|---|---|",
    ]
    for p in PROJECTS:
        if p not in log:
            continue
        entry = log[p]
        lines.append(f"| {p} | {len(entry['added'])} | {len(entry['updated'])} | "
                     f"{len(entry['modified'])} | {entry['unchanged']} | "
                     f"{'yes' if entry['manifest'] else '**NO**'} |")
    lines += ["", "## Preserved files, per project", "",
              "These were **not** written. Each is either edited since install or "
              "unprovable as pristine.", ""]
    for p in PROJECTS:
        if p not in log or not log[p]["modified"]:
            continue
        entry = log[p]
        lines.append(f"### {p} ({len(entry['modified'])})")
        lines.append("")
        for rel, why in entry["modified"][:15]:
            lines.append(f"- `{rel}` — {why}")
        if len(entry["modified"]) > 15:
            lines.append(f"- … and {len(entry['modified']) - 15} more")
        lines.append("")

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    ta = sum(len(v["added"]) for v in log.values())
    tu = sum(len(v["updated"]) for v in log.values())
    tm = sum(len(v["modified"]) for v in log.values())
    print(f"[{'DRY RUN' if dry else 'EXECUTED'}] added={ta} updated={tu} preserved={tm}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

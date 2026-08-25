#!/usr/bin/env python3
"""Repoint downstream references from a superseded skill to its successor.

Phase B held three of the six approved deletions because 84 `## Skill Loading` directives
across 12 repos still name them, and the registry's `renamed` map is DIAGNOSTIC ONLY -- it
makes `ck doctor` warn, it does not resolve a skill at load time. So the references have to
move before the directories can go.

Two shapes, and conflating them is the trap: a file that already loads the successor must
have the old line REMOVED, not renamed, or it ends up loading the same skill twice.
"""
import argparse
import os
import re
import sys

ROOT = os.path.expanduser("~/IdeaProjects")
PROJECTS = ["ai-agent-system", "ApiForge", "AppiumLens", "AutomationApp", "Eatizaz", "Lean",
            "LeanApis", "MobileUIAutomator", "qa-agents", "qaforge-ai", "SehhatyApp",
            "shsmartassistant-qa"]
PAIRS = {"session-continuity": "context-keeper",
         "dependency-audit": "supply-chain-audit",
         "verification-loop": "verification-before-completion"}
SUBS = ("agents", "commands", "hooks", "modes")


def directive(line, sid):
    return re.match(r"^\s*-\s+\*\*%s\*\*" % re.escape(sid), line) is not None


def word(sid):
    return re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(sid))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = {"renamed": 0, "removed": 0, "prose": 0, "files": 0}
    per_project = {}

    for p in PROJECTS:
        base = os.path.join(ROOT, p, ".claude")
        log = []
        for sub in SUBS:
            d = os.path.join(base, sub)
            if not os.path.isdir(d):
                continue
            for root, _, files in os.walk(d):
                for f in sorted(files):
                    fp = os.path.join(root, f)
                    try:
                        lines = open(fp, encoding="utf-8").read().splitlines(keepends=True)
                    except Exception:
                        continue
                    changed = False
                    out = []
                    # one pass over lines, applying every pair
                    for line in lines:
                        drop = False
                        newline = line
                        for old, new in PAIRS.items():
                            if not word(old).search(newline):
                                continue
                            if directive(newline, old):
                                # does this file already carry a directive for the successor?
                                already = any(directive(x, new) for x in lines)
                                if already:
                                    drop = True
                                    stats["removed"] += 1
                                    log.append(f"{sub}/{f}: removed duplicate `{old}` "
                                               f"(file already loads `{new}`)")
                                else:
                                    newline = word(old).sub(new, newline)
                                    stats["renamed"] += 1
                                    log.append(f"{sub}/{f}: `{old}` -> `{new}`")
                            else:
                                newline = word(old).sub(new, newline)
                                stats["prose"] += 1
                        if drop:
                            changed = True
                            continue
                        if newline != line:
                            changed = True
                        out.append(newline)
                    if changed:
                        stats["files"] += 1
                        if not args.dry_run:
                            with open(fp, "w", encoding="utf-8") as fh:
                                fh.write("".join(out))
        if log:
            per_project[p] = log

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"[{mode}] files touched: {stats['files']}  "
          f"directives renamed: {stats['renamed']}  "
          f"duplicate directives removed: {stats['removed']}  "
          f"prose mentions repointed: {stats['prose']}")
    for p, log in sorted(per_project.items()):
        print(f"\n{p} ({len(log)} directive change(s))")
        for line in log[:4]:
            print("   ", line)
        if len(log) > 4:
            print(f"    ... and {len(log)-4} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())

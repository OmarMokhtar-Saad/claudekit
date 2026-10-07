#!/usr/bin/env python3
"""Repair skills-registry.json in the kitted repos after the fleet sync.

The sync overwrote .claude/skills/skills-registry.json with claudekit's copy.
That file lists only claudekit's own skills, so any repo carrying PROJECT-LOCAL
skills lost their registration -- they still exist on disk, but `ck doctor`
reports each as "exists on disk but is not registered". Measured: AppiumLens 15,
MobileUIAutomator 9, qa-agents 2, rest-framework 2.

This MERGES rather than reverts. Reverting would restore the local entries but
drop the kit entries the sync was for. So: keep the freshly-synced entries, and
re-add every skill that (a) has a directory on disk, (b) is absent from the
current registry, and (c) can be described -- from the newest .claude.bak-*
registry that knows it, else rebuilt from its own SKILL.md frontmatter.

Idempotent, and writes only when something is actually missing.
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
REPOS = """ai-agent-system AppiumLens AutomationApp Eatizaz Lean LeanApis
MobileUIAutomator qa-agents qaforge-ai rest-framework SehhatyApp
shsmartassistant-agent shsmartassistant-qa""".split()

REG = os.path.join(".claude", "skills", "skills-registry.json")


def frontmatter(path):
    """`name` and `description` from a SKILL.md, without a YAML dependency."""
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return out
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return out
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        if _ and k.strip() in ("name", "description"):
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def entry_for(skill_id, root, backups):
    """Prefer the real prior entry; fall back to rebuilding from frontmatter."""
    for b in backups:
        try:
            with open(b, encoding="utf-8") as fh:
                for e in json.load(fh).get("skills", []):
                    if e.get("id") == skill_id:
                        return e, os.path.basename(os.path.dirname(os.path.dirname(b)))
        except (OSError, ValueError):
            continue
    fm = frontmatter(os.path.join(root, ".claude", "skills", skill_id, "SKILL.md"))
    if not fm:
        return None, None
    return {
        "id": skill_id,
        "name": fm.get("name") or skill_id.replace("-", " ").title(),
        "path": "skills/%s/SKILL.md" % skill_id,
        "mandatory": False,
        "usedBy": [],
        "description": fm.get("description", ""),
    }, "SKILL.md"


def main():
    dry = os.environ.get("DRY_RUN") == "1"
    total = 0
    for repo in REPOS:
        root = os.path.join(HOME, "IdeaProjects", repo)
        reg_path = os.path.join(root, REG)
        skills_dir = os.path.join(root, ".claude", "skills")
        if not os.path.isfile(reg_path) or not os.path.isdir(skills_dir):
            continue
        with open(reg_path, encoding="utf-8") as fh:
            reg = json.load(fh)
        have = {e.get("id") for e in reg.get("skills", [])}
        on_disk = sorted(
            d for d in os.listdir(skills_dir)
            if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
        )
        missing = [d for d in on_disk if d not in have]
        if not missing:
            print("%-24s ok" % repo)
            continue
        backups = []
        for b in sorted(os.listdir(root), reverse=True):
            if b.startswith(".claude.bak-"):
                p = os.path.join(root, b, "skills", "skills-registry.json")
                if os.path.isfile(p):
                    backups.append(p)
        restored, sources = [], []
        for sid in missing:
            e, src = entry_for(sid, root, backups)
            if e:
                restored.append(e)
                sources.append(src)
        if not restored:
            print("%-24s %d missing, NONE recoverable" % (repo, len(missing)))
            continue
        reg["skills"] = sorted(reg.get("skills", []) + restored,
                               key=lambda e: e.get("id", ""))
        if not dry:
            with open(reg_path, "w", encoding="utf-8") as fh:
                json.dump(reg, fh, indent=2)
                fh.write("\n")
        total += len(restored)
        print("%-24s %s %d skill(s): %s" % (
            repo, "would restore" if dry else "restored",
            len(restored), ", ".join(s["id"] for s in restored)))
    print()
    print("%s %d entr(ies)." % ("Would restore" if dry else "Restored", total))
    return 0


if __name__ == "__main__":
    sys.exit(main())

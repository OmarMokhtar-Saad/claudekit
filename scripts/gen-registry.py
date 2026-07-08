#!/usr/bin/env python3
"""Regenerate skills-registry.json agentMapping from the agent files.

The agent .md "Skill Loading" sections are the single source of truth for what
an agent loads (mandatory + on-demand). This script derives agentMapping from
them so the registry can never silently drift again (the 2026-07 audit found
10 mapped agents with no skill section at all and two command names mapped as
agents).

Usage:
    python3 scripts/gen-registry.py            # rewrite agentMapping in place
    python3 scripts/gen-registry.py --check    # exit 1 if the registry drifted
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".claude", "agents")
REGISTRY = os.path.join(ROOT, ".claude", "skills", "skills-registry.json")

SECTION_RE = re.compile(
    r"## (?:Skill Loading|Mandatory Skill Loading)\n(.*?)(?=\n## |\n---)", re.S
)
SKILL_RE = re.compile(r"\*\*([a-z0-9][a-z0-9-]*)\*\*")


def derive_mapping():
    """agent -> sorted list of skills (mandatory + on-demand) from agent files."""
    mapping = {}
    for fname in sorted(os.listdir(AGENTS_DIR)):
        path = os.path.join(AGENTS_DIR, fname)
        if not fname.endswith(".md") or not os.path.isfile(path):
            continue
        text = open(path).read()
        if not text.startswith("---\n"):
            continue  # shared docs, not agents
        match = SECTION_RE.search(text)
        if not match:
            continue  # agent declares no skills — it gets no mapping entry
        skills = sorted(set(SKILL_RE.findall(match.group(1))))
        if skills:
            mapping[fname[:-3]] = skills
    return mapping


def main():
    check = "--check" in sys.argv
    with open(REGISTRY) as fh:
        registry = json.load(fh)
    derived = derive_mapping()

    known_ids = {s["id"] for s in registry.get("skills", [])}
    unknown = {a: [s for s in skills if s not in known_ids]
               for a, skills in derived.items()}
    unknown = {a: miss for a, miss in unknown.items() if miss}
    if unknown:
        for agent, miss in unknown.items():
            print(f"ERROR: {agent} loads skills missing from the registry: {miss}",
                  file=sys.stderr)
        return 1

    if registry.get("agentMapping") == derived:
        print(f"OK: agentMapping matches agent files ({len(derived)} agents).")
        return 0
    if check:
        current = registry.get("agentMapping", {})
        for key in sorted(set(current) | set(derived)):
            if current.get(key) != derived.get(key):
                print(f"DRIFT: {key}: registry={current.get(key)} "
                      f"agent-file={derived.get(key)}", file=sys.stderr)
        print("FAIL: skills-registry.json agentMapping drifted from agent files. "
              "Run: python3 scripts/gen-registry.py", file=sys.stderr)
        return 1

    registry["agentMapping"] = derived
    with open(REGISTRY, "w") as fh:
        json.dump(registry, fh, indent=2)
        fh.write("\n")
    print(f"Rewrote agentMapping from agent files ({len(derived)} agents).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

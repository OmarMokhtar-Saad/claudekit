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
SKILLS_DIR = os.path.join(ROOT, ".claude", "skills")

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


def derive_skill_ids():
    """Skill ids on disk. One directory with a SKILL.md is one skill.

    Until 2026-08 nothing in this script looked at the filesystem side of the
    skills corpus at all: it derived agentMapping from agent files and compared
    that to the registry. A skill created by hand -- never through a generator,
    never registered -- was therefore invisible to `--check`, which is the drift
    this function closes.
    """
    if not os.path.isdir(SKILLS_DIR):
        return []
    return sorted(
        name for name in os.listdir(SKILLS_DIR)
        if os.path.isfile(os.path.join(SKILLS_DIR, name, "SKILL.md"))
    )


def _frontmatter_field(text, field):
    match = re.search(
        r'(?m)^%s:[ \t]*["\']?(.*?)["\']?[ \t]*$' % re.escape(field), text)
    return match.group(1).strip() if match else ""


def skill_entry_from_disk(sid):
    """The registry entry a hand-created skill should have had."""
    path = os.path.join(SKILLS_DIR, sid, "SKILL.md")
    text = open(path).read()
    head = text.split("\n---", 2)[0] if text.startswith("---\n") else ""
    return {
        "id": sid,
        "name": " ".join(part.capitalize() for part in sid.split("-")),
        "path": "skills/%s/SKILL.md" % sid,
        "mandatory": False,
        "usedBy": [],
        "description": _frontmatter_field(head, "description"),
    }


def derive_agent_ids():
    """Agent ids on disk: a .md file with frontmatter. Shared docs are skipped."""
    ids = []
    for fname in sorted(os.listdir(AGENTS_DIR)):
        path = os.path.join(AGENTS_DIR, fname)
        if not fname.endswith(".md") or not os.path.isfile(path):
            continue
        if open(path).read().startswith("---\n"):
            ids.append(fname[:-3])
    return ids


def derive_used_by(registry, mapping):
    """skill -> usedBy: agents from the reverse mapping, plus any existing
    non-agent entries (e.g. command names). The literal "all" is fiction
    (honored nowhere) and is dropped."""
    agent_names = {os.path.splitext(f)[0]
                   for f in os.listdir(AGENTS_DIR) if f.endswith(".md")}
    reverse = {}
    for agent, skills in mapping.items():
        for skill in skills:
            reverse.setdefault(skill, set()).add(agent)
    result = {}
    for skill in registry.get("skills", []):
        sid = skill["id"]
        keep = {u for u in skill.get("usedBy", [])
                if u != "all" and u not in agent_names}
        result[sid] = sorted(reverse.get(sid, set()) | keep)
    return result


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

    used_by = derive_used_by(registry, derived)
    current_used_by = {s["id"]: s.get("usedBy", []) for s in registry.get("skills", [])}

    # Filesystem <-> registry reconciliation. Both directions, because they fail
    # differently: a skill on disk that nobody registered is silent drift, while a
    # registry row with no directory is a dangling reference the doctor already
    # trips over at runtime.
    fs_skills = set(derive_skill_ids())
    reg_skills = {s["id"] for s in registry.get("skills", [])}

    # The `renamed` alias map is how a REMOVED skill name stays resolvable for one
    # release, so the 16 downstream repos see a rename and not a deletion (a condition
    # of the task-008 sign-off). It is hand-maintained -- nothing on disk can derive it,
    # since the whole point is that the old name is gone -- so the generator's job is to
    # keep it HONEST rather than to write it. `ck doctor` is what READS it.
    #
    # Checked here, before the skills reconciliation below, so a broken alias is
    # reported by BOTH `--check` and the rewrite rather than only whichever runs first.
    _aliases = registry.get("renamed", {})
    if not isinstance(_aliases, dict):
        print("ERROR: renamed: expected an object mapping old id -> new id, got "
              f"{type(_aliases).__name__}", file=sys.stderr)
        return 1
    for _old, _new in sorted(_aliases.items()):
        if not _old or not isinstance(_new, str) or not _new:
            print(f"ERROR: renamed: {_old!r} -> {_new!r} is not a usable alias "
                  f"(an empty key matches every file)", file=sys.stderr)
            return 1
        if _old in fs_skills:
            print(f"ERROR: renamed: '{_old}' is aliased but still exists on disk",
                  file=sys.stderr)
            return 1
        if _new not in fs_skills:
            print(f"ERROR: renamed: '{_old}' -> '{_new}', which does not exist",
                  file=sys.stderr)
            return 1
    unregistered = sorted(fs_skills - reg_skills)
    orphaned = sorted(reg_skills - fs_skills)

    # An agent may legitimately load no skills -- but then it must SAY so. Listing
    # those agents explicitly is what makes a hand-created agent file fail --check:
    # under the old rule it simply matched no pattern and was skipped in silence.
    fs_agents = derive_agent_ids()
    unmapped = sorted(set(fs_agents) - set(derived))
    listed_unmapped = registry.get("agentsWithoutSkills")

    if orphaned:
        for sid in orphaned:
            print(f"ERROR: registry skill {sid!r} has no .claude/skills/{sid}/SKILL.md",
                  file=sys.stderr)
        print("FAIL: registry rows without a directory are never auto-removed -- "
              "deleting an asset is owner-gated. Restore the skill or remove the row "
              "by hand.", file=sys.stderr)
        return 1

    clean = (registry.get("agentMapping") == derived
             and current_used_by == used_by
             and not unregistered
             and listed_unmapped == unmapped)

    if clean:
        print(f"OK: registry matches the filesystem ({len(derived)} mapped agents, "
              f"{len(unmapped)} agents without skills, {len(fs_skills)} skills).")
        return 0
    if check:
        current = registry.get("agentMapping", {})
        for key in sorted(set(current) | set(derived)):
            if current.get(key) != derived.get(key):
                print(f"DRIFT agentMapping {key}: registry={current.get(key)} "
                      f"agent-file={derived.get(key)}", file=sys.stderr)
        for sid in sorted(current_used_by):
            if current_used_by[sid] != used_by.get(sid):
                print(f"DRIFT usedBy {sid}: registry={current_used_by[sid]} "
                      f"derived={used_by.get(sid)}", file=sys.stderr)
        for sid in unregistered:
            print(f"UNREGISTERED skill {sid!r}: .claude/skills/{sid}/SKILL.md exists but "
                  f"is not in skills-registry.json. Create skills with "
                  f"`ck skill new`, which registers as it creates.", file=sys.stderr)
        if listed_unmapped != unmapped:
            missing = sorted(set(unmapped) - set(listed_unmapped or []))
            stale = sorted(set(listed_unmapped or []) - set(unmapped))
            if missing:
                print(f"UNREGISTERED agent(s) {missing}: an agent file that declares no "
                      f"'## Skill Loading' section must be listed in "
                      f"agentsWithoutSkills, so that adding one by hand is visible.",
                      file=sys.stderr)
            if stale:
                print(f"STALE agentsWithoutSkills {stale}: listed but the agent file "
                      f"now declares skills (or is gone).", file=sys.stderr)
        print("FAIL: skills-registry.json drifted from the filesystem. "
              "Run: python3 scripts/gen-registry.py", file=sys.stderr)
        return 1

    registry["agentMapping"] = derived
    registry["agentsWithoutSkills"] = unmapped
    for sid in unregistered:
        registry.setdefault("skills", []).append(skill_entry_from_disk(sid))
    used_by = derive_used_by(registry, derived)
    for skill in registry.get("skills", []):
        skill["usedBy"] = used_by[skill["id"]]
    with open(REGISTRY, "w") as fh:
        json.dump(registry, fh, indent=2)
        fh.write("\n")
    print(f"Rewrote registry from the filesystem ({len(derived)} mapped agents, "
          f"{len(unmapped)} without skills, {len(unregistered)} newly registered skills).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""`ck skill new` — creating a skill and registering it are one act.

The drift this ends
-------------------
`writing-skills` explains how to author a skill. Nothing registered it, so
`.claude/skills/skills-registry.json` diverged from the filesystem silently: an
author who created a directory by hand got a skill that exists, that no
`agentMapping` can reference, and that `gen-registry.py --check` never looked
for. This module makes the two steps indivisible — the registry entry is
written in the same call, and if that write fails the scaffold is removed
again, so "a skill exists but is unregistered" is not a reachable state.

Fail-closed, with numbers
-------------------------
Every refusal names its cause and quotes the numbers behind it: an invalid
name, a name already taken on disk or in the registry, an unreadable registry,
and — the one that costs real money on every future session — a description
that would push the always-on context floor over budget
(:func:`claudekit.context_floor.check_new_skill`). Nothing is written before
every check has passed.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import context_floor

NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")

#: A description longer than this is a paragraph, not a trigger line. The
#: floor gate would eventually catch it in aggregate; this catches it at the
#: one skill responsible, which is the actionable place to catch it.
MAX_DESCRIPTION = 300


class SkillError(Exception):
    """A skill could not be created. The message names the cause."""


def skills_dir(root: Path) -> Path:
    return Path(root) / ".claude" / "skills"


def registry_path(root: Path) -> Path:
    return skills_dir(root) / "skills-registry.json"


def title_from_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def load_registry(root: Path) -> Dict[str, Any]:
    path = registry_path(root)
    if not path.is_file():
        raise SkillError(
            f"no skills registry at {path}; `ck skill new` registers as it creates and "
            f"will not create an unregistered skill. Run `claudekit update` first."
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SkillError(f"unreadable skills registry {path}: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("skills"), list):
        raise SkillError(f"{path}: expected an object with a 'skills' list")
    return doc


def registered_ids(doc: Dict[str, Any]) -> List[str]:
    return [s["id"] for s in doc.get("skills", []) if isinstance(s, dict) and "id" in s]


def render_skill(name: str, description: str, *, invisible: bool,
                 allowed_tools: str) -> str:
    """The scaffold. It must pass every gate the shipped corpus already passes:
    closed frontmatter, a `name`, a single-line quoted `description`, and a
    non-empty body with real headings."""
    lines = ["---", f"name: {name}", f'description: "{description}"']
    if invisible:
        lines.append("disable-model-invocation: true")
    lines.append(f"allowed-tools: {allowed_tools}")
    lines.append("---")
    title = title_from_name(name)
    lines += [
        "",
        f"# {title}",
        "",
        "## Core Principle",
        "",
        "**State the one rule this skill exists to enforce.** One sentence. If it takes",
        "a paragraph, this is two skills.",
        "",
        "---",
        "",
        "## When To Use",
        "",
        f"- <the concrete trigger that should load {name}>",
        "",
        "## When NOT To Use",
        "",
        "- <the neighbouring case that belongs to a different skill — name it>",
        "",
        "---",
        "",
        "## Process",
        "",
        "1. <first step>",
        "2. <second step>",
        "",
        "## Verification",
        "",
        "State how a reader proves this skill was followed — a command and its",
        "expected output, not an assertion that it was.",
        "",
    ]
    return "\n".join(lines)


def new_skill(root: Path, name: str, description: str, *,
              summary: Optional[str] = None,
              invisible: bool = False,
              mandatory: bool = False,
              allowed_tools: str = "Read, Grep, Glob"
              ) -> Tuple[Path, Dict[str, Any], Tuple[str, ...]]:
    """Create ``name`` and register it, or raise :class:`SkillError`.

    Returns ``(skill_md_path, registry_entry, floor_warnings)``. Every validation
    runs before the first byte is written; if the registry write fails afterwards
    the scaffold directory is removed, so the two artifacts cannot disagree.
    ``floor_warnings`` names context-floor categories that are over budget for
    reasons this skill did not cause -- they are reported, not enforced, because
    a skill charges only the skill-description category.
    """
    root = Path(root)
    if not NAME_RE.fullmatch(name or ""):
        raise SkillError(
            f"invalid skill name {name!r}: expected kebab-case (lowercase letters, "
            f"digits and hyphens, starting with a letter or digit)"
        )
    description = (description or "").strip()
    if not description:
        raise SkillError("a skill needs a description: it is the only text a model sees "
                         "when deciding whether to load the skill")
    if "\n" in description:
        raise SkillError("description must be a single line (it is inlined into "
                         "frontmatter as a quoted scalar)")
    if '"' in description:
        raise SkillError('description must not contain a double quote: it is written as '
                         'a double-quoted YAML scalar')
    if len(description) > MAX_DESCRIPTION:
        raise SkillError(
            f"description is {len(description)} chars; the limit is {MAX_DESCRIPTION}. "
            f"A description is a trigger line, not documentation — the body is free, "
            f"the description is charged to every session."
        )

    directory = skills_dir(root) / name
    if directory.exists():
        raise SkillError(f"{directory} already exists; refusing to overwrite an existing skill")

    doc = load_registry(root)
    if name in registered_ids(doc):
        raise SkillError(
            f"skill id {name!r} is already in {registry_path(root)} but has no directory; "
            f"that is registry drift — run `python3 scripts/gen-registry.py --check`"
        )

    refusal, floor_warnings = context_floor.check_new_skill(
        root, description, invisible=invisible)
    if refusal:
        raise SkillError(refusal)

    entry: Dict[str, Any] = {
        "id": name,
        "name": title_from_name(name),
        "path": f"skills/{name}/SKILL.md",
        "mandatory": bool(mandatory),
        # Always empty, never operator-supplied. `usedBy` is DERIVED by
        # scripts/gen-registry.py from each agent's `## Skill Loading` section,
        # so any value asserted here could only disagree with the derivation and
        # put `--check` red -- manufacturing the exact drift this phase abolishes.
        # A brand-new skill is loaded by no agent yet; adding it to an agent file
        # and re-running the generator is what fills this in.
        "usedBy": [],
        "description": (summary or description).strip(),
    }

    skill_md = directory / "SKILL.md"
    directory.mkdir(parents=True)
    try:
        skill_md.write_text(
            render_skill(name, description, invisible=invisible,
                         allowed_tools=allowed_tools),
            encoding="utf-8",
        )
        # Appended, never re-sorted: re-ordering the whole list would bury a
        # one-line addition in a 700-line diff and make review useless.
        doc["skills"] = list(doc.get("skills", [])) + [entry]
        doc["lastUpdated"] = date.today().isoformat()
        _write_json(registry_path(root), doc)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return skill_md, entry, floor_warnings


def _write_json(path: Path, doc: Dict[str, Any]) -> None:
    """Write JSON atomically: a half-written registry is worse than no write."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

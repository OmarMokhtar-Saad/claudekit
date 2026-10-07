"""`ck skill roles list|check|apply` -- bind generic agents' skill ROLES to this project.

Why roles
---------
Kit agents are generic and fleet-synced: the debugger that ships to a Java/Appium repo
is byte-identical to the one in a pytest repo. What should differ is which stack skills
it arrives knowing. So a kit agent declares ROLES (`ROLE_CATALOG`: the debugger has
`debugging-method`, `stack-debugging`, `project-gotchas`), and each project binds a role
to one of its installed skills in the `roles` map of `.claude/skills-profile.json`:

    "roles": {"stack-debugging": "pytest-debugging",
              "project-gotchas": ".claude/skills/house-gotchas/SKILL.md"}

The mechanism, and why this one
-------------------------------
`apply` resolves the bindings and writes the resolved skill ids into the documented
Claude Code sub-agent key `skills:` in each installed role agent's frontmatter. Claude
Code preloads the full content of those skills when it spawns the agent -- a real load,
not a sentence asking the model to load something (`tests/test_skill_loading_contract.py`:
prose in a prompt is not enforcement). There is no hook and no runtime prompt injection:
the output is a deterministic function of the profile and the installed skills, and
`check` (and `ck doctor`) re-derive it and report drift.

The generator OWNS the `skills:` key of the agents in `ROLE_CATALOG` and nothing else:
it never touches an agent body, so every mandatory and on-demand Skill Loading line
survives, and it never touches an agent outside the catalog. Kit role agents ship no
`skills:` key (a test pins that), so a present one was written here. With no bindings
the key is removed and the file is byte-identical to the kit's.

Install manifest: the agent file is kit-managed, so a changed hash would make `ck diff`
report it modified and `ck update` ask before overwriting. `apply` therefore re-stamps
the receipt -- but only when the file it found was the one the receipt describes (its
hash, or its hash with the generated key removed, matches). A file edited locally in any
other way keeps its old receipt, so the edit stays visible to `ck diff`.

Threat model
------------
A profile is repository content, so a pull request can edit it. A binding can therefore
only ADD a preload: it names an installed, model-visible skill under `.claude/skills/`,
by id or by exactly `.claude/skills/<id>/SKILL.md` -- no absolute path, no `..`, no
symlink resolving outside `.claude/skills/`. A skill the same profile disables is
refused (a hidden skill cannot be preloaded), and once written, a preloaded skill is
protected from `ck skill apply` by `skill_fit.protected_skills`. Every check runs before
the first write, so a refusal changes nothing. Honest limit (hard rule 6): the agent
file is still the user's to edit; this is convergence plus drift detection, not a lock.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import adapt, context_floor, skill_fit, skills

#: agent -> the roles it declares, in preload order. Start small: three agents.
ROLE_CATALOG: Dict[str, Tuple[str, ...]] = {
    "debugger": ("debugging-method", "stack-debugging", "project-gotchas"),
    "code-reviewer": ("review-checklist", "project-gotchas"),
    "tester": ("test-framework", "project-gotchas"),
}

ROLE_DESCRIPTIONS: Dict[str, str] = {
    "debugging-method": "How failures are investigated in this project",
    "stack-debugging": "Stack-specific debugging (pytest, JVM, Appium, ...)",
    "review-checklist": "The language or framework review checklist this project uses",
    "test-framework": "How tests are written and run here (pytest, JUnit, ...)",
    "project-gotchas": "Project pitfalls every role agent must know",
}

#: Preloads are FULL skill bodies charged to every spawn of the agent, so both are small.
MAX_SKILLS_PER_ROLE = 2
MAX_SKILLS_PER_AGENT = 4

MANIFEST_NAME = ".claudekit-manifest.json"
_SKILLS_LINE = re.compile(r"^skills:")
_BLOCK_ITEM = re.compile(r"^[ \t]+-")


class RolesError(skill_fit.SkillFitError):
    """A role binding could not be resolved or written. Nothing was changed."""


def catalog() -> Dict[str, Any]:
    """The role vocabulary and which agent declares which roles."""
    return {"roles": dict(ROLE_DESCRIPTIONS),
            "agents": {agent: list(roles) for agent, roles in ROLE_CATALOG.items()}}


def _skill_id(root: Path, role: str, raw: Any) -> str:
    """The installed, model-visible skill id a binding names, or RolesError."""
    if not isinstance(raw, str) or not raw:
        raise RolesError(f"role '{role}': a binding must be a non-empty string")
    if skills.NAME_RE.fullmatch(raw):
        name = raw
    else:
        candidate = Path(raw)
        parts = candidate.parts
        if (candidate.is_absolute() or len(parts) != 4
                or parts[:2] != (".claude", "skills") or parts[3] != "SKILL.md"
                or not skills.NAME_RE.fullmatch(parts[2])):
            raise RolesError(f"role '{role}': '{raw}' is neither a skill id nor a "
                             f".claude/skills/<id>/SKILL.md path")
        name = parts[2]
    skill_md = root / ".claude" / "skills" / name / "SKILL.md"
    if not skill_md.is_file():
        raise RolesError(f"role '{role}': skill '{name}' is not installed")
    base = (root / ".claude" / "skills").resolve()
    if base not in skill_md.resolve().parents:
        raise RolesError(f"role '{role}': skill '{name}' resolves outside .claude/skills/")
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RolesError(f"role '{role}': skill '{name}' is unreadable: {exc}") from exc
    if context_floor.model_invisible(context_floor.frontmatter(text)):
        raise RolesError(f"role '{role}': skill '{name}' sets disable-model-invocation, "
                         f"so it cannot be preloaded")
    return name


def resolve(root: Path) -> Tuple[Dict[str, List[str]], List[str]]:
    """(installed role agent -> skill ids to preload, warnings). RolesError on any bad
    binding. No profile, or no `roles`, resolves every installed role agent to []."""
    root = Path(root)
    profile = skill_fit.load_profile(root) or {}
    roles = profile.get("roles", {})
    known = {role for declared in ROLE_CATALOG.values() for role in declared}
    unknown = sorted(set(roles) - known)
    if unknown:
        raise RolesError(f"unknown role(s) {', '.join(unknown)}; known: "
                         f"{', '.join(sorted(known))}")
    disabled = set(profile.get("disabled", []))
    by_role: Dict[str, List[str]] = {}
    for role in sorted(roles):
        value = roles[role]
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list) or not items:
            raise RolesError(f"role '{role}' must be a skill id, a "
                             f".claude/skills/<id>/SKILL.md path, or a non-empty list")
        if len(items) > MAX_SKILLS_PER_ROLE:
            raise RolesError(f"role '{role}' binds {len(items)} skills; the limit is "
                             f"{MAX_SKILLS_PER_ROLE}")
        resolved: List[str] = []
        for raw in items:
            name = _skill_id(root, role, raw)
            if name in disabled:
                raise RolesError(f"role '{role}' binds '{name}', which the profile "
                                 f"disables; a hidden skill cannot be preloaded")
            if name not in resolved:
                resolved.append(name)
        by_role[role] = resolved
    bindings: Dict[str, List[str]] = {}
    warnings: List[str] = []
    for agent, declared in sorted(ROLE_CATALOG.items()):
        names: List[str] = []
        for role in declared:
            for name in by_role.get(role, []):
                if name not in names:
                    names.append(name)
        if len(names) > MAX_SKILLS_PER_AGENT:
            raise RolesError(f"agent '{agent}' would preload {len(names)} skills; the "
                             f"limit is {MAX_SKILLS_PER_AGENT}")
        if not (root / ".claude" / "agents" / f"{agent}.md").is_file():
            if names:
                warnings.append(f"agent '{agent}' is not installed; its role bindings "
                                f"apply to nothing")
            continue
        bindings[agent] = names
    return bindings, warnings


def with_skills(text: str, names: List[str]) -> str:
    """`text` with its frontmatter `skills:` key replaced by `names` (removed when
    empty). Every other byte is kept, so `with_skills(t, [])` of a kit agent is `t`."""
    if not text.startswith("---\n"):
        raise RolesError("agent file has no frontmatter")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise RolesError("agent file frontmatter is not closed")
    kept: List[str] = []
    dropping = False
    for line in text[4:end].split("\n"):
        if dropping and _BLOCK_ITEM.match(line):
            continue
        dropping = bool(_SKILLS_LINE.match(line))
        if not dropping:
            kept.append(line)
    if names:
        kept.append("skills: [" + ", ".join(names) + "]")
    return "---\n" + "\n".join(kept) + text[end:]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _agent_text(path: Path) -> str:
    if path.is_symlink():
        raise RolesError(f"{path} is a symlink; refusing to write through it")
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RolesError(f"unreadable {path}: {exc}") from exc


def _manifest(path: Path) -> Optional[Dict[str, Any]]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("files"), dict) else None


def apply(root: Path) -> Dict[str, Any]:
    """Converge the role agents' `skills:` frontmatter to the profile's bindings."""
    root = Path(root)
    claude = root / ".claude"
    if not claude.is_dir():
        raise RolesError(f"no {claude} directory; install ClaudeKit first")
    if (root / "scripts" / "gen-registry.py").is_file() and (root / "src" / "claudekit").is_dir():
        raise RolesError("this is the ClaudeKit source tree; role bindings are written "
                         "only into installed projects")
    bindings, warnings = resolve(root)
    planned = []
    for agent, names in sorted(bindings.items()):
        path = claude / "agents" / f"{agent}.md"
        text = _agent_text(path)
        planned.append((agent, path, text, with_skills(text, names), names))
    manifest_path = claude / MANIFEST_NAME
    manifest = _manifest(manifest_path)
    result: Dict[str, Any] = {"written": [], "unchanged": [], "restamped": [],
                              "not_restamped": [], "warnings": warnings,
                              "preloads": {}, "tokens": {}}
    stamped = False
    for agent, path, text, new, names in planned:
        result["preloads"][agent] = names
        result["tokens"][agent] = sum(
            skill_fit.tokens((claude / "skills" / n / "SKILL.md").read_text(encoding="utf-8"))
            for n in names)
        if new != text:
            adapt.write_atomic(path, new)
            result["written"].append(agent)
        else:
            result["unchanged"].append(agent)
        rel = f"agents/{agent}.md"
        if manifest is None or rel not in manifest["files"]:
            continue
        recorded = manifest["files"][rel]
        target = _sha(new.encode("utf-8"))
        if recorded == target:
            continue
        found = {_sha(text.encode("utf-8")), _sha(with_skills(text, []).encode("utf-8"))}
        if recorded in found:
            manifest["files"][rel] = target
            result["restamped"].append(agent)
            stamped = True
        else:
            result["not_restamped"].append(agent)
    if stamped and manifest is not None:
        adapt.write_atomic(manifest_path, json.dumps(manifest, indent=2))
    return result


def findings(root: Path) -> Tuple[List[str], List[str], int]:
    """(errors, warnings, bound skill count) for `check` and `ck doctor`."""
    root = Path(root)
    try:
        bindings, warnings = resolve(root)
    except skill_fit.SkillFitError as exc:
        return [str(exc)], [], 0
    warnings = list(warnings)
    for agent, names in sorted(bindings.items()):
        path = root / ".claude" / "agents" / f"{agent}.md"
        try:
            current = skill_fit.agent_preloaded_skills(_agent_text(path))
        except RolesError as exc:
            return [str(exc)], warnings, 0
        if current != names:
            warnings.append(f"{agent} preloads [{', '.join(current)}] but its roles resolve "
                            f"to [{', '.join(names)}]; run `ck skill roles apply`")
    return [], warnings, sum(len(v) for v in bindings.values())

"""`ck skill audit|profile|card|match` -- does each installed skill fit THIS project?

What this module is, and what it is not
---------------------------------------
Every installed skill charges its description to every session, and a Java project
pays for `python-review-checklist` as surely as a Python one does. This module
MEASURES that: it detects the project's stacks, estimates each skill's tokens, and
buckets every skill as relevant, irrelevant for the detected stacks, or broken. It
also lets a project record its decisions in one file it owns,
`.claude/skills-profile.json`, and lets projects share sanitized metadata cards so a
skill proven in one repo can be suggested to another.

It is READ-ONLY analysis. Nothing here edits a skill, installs a skill, or injects
anything into a prompt. `disabled` in the profile is a recorded decision that `audit`
and `ck doctor` read; no hook enforces it in this release (deferred, see
plan-skill-fit.md "Phase 2"). Saying otherwise would overstate the product
(CLAUDE.md hard rule 6).

Stack tags and the shared registry
----------------------------------
A card is only as findable as its tags. Explicit `stack_tags` frontmatter always wins;
a kit skill otherwise uses `KIT_STACK_TAGS`; a project's OWN skill otherwise gets tags
DERIVED deterministically -- a word-boundary scan of its name, description and body
against `STACK_VOCAB`, unioned with the project's detected stacks. Kit skills are never
derived: their bodies cite every language as examples, and a derived tag there would
make `profile init` disable stack-neutral capability.

Cards are shared through a USER-level directory, never a repository:
`~/.claudekit/registry/cards/<project>.json`, or `$CLAUDEKIT_REGISTRY` (absolute).
`card --publish` writes there atomically; `match` reads it by default, skips the
current project's own card, and scores by Jaccard overlap of tags.

Estimates, not measurements
---------------------------
Tokens are chars/4, rounded up. That is the same order-of-magnitude rule the context
floor uses; it is good for ranking and budgeting, not for billing.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from . import adapt, context_floor, memory, skills

SCHEMA_VERSION = 1
CARD_VERSION = 1

PROFILE_NAME = "skills-profile.json"
PROFILE_KEYS = ("schema", "packs", "disabled", "overlays", "roles")
REPORT_REL = (".claude", "reports", "skills", "audit.json")

#: Body budget. Measured 2026-09-13 on the kit's own 81 skills: a 150-line limit
#: flags 73 of them, which makes the flag noise; these defaults flag the genuinely
#: large bodies. Both are CLI-overridable.
DEFAULT_MAX_LINES = 300
DEFAULT_MAX_TOKENS = 2000
CHARS_PER_TOKEN = 4

#: A stack is claimed from source files only past this count -- the same >=20
#: tracked-file rule fleet-sync.py's STACKS table was measured with, so a stray
#: build script does not make a Java project "kotlin".
STACK_FILE_THRESHOLD = 20
MAX_SCAN_FILES = 20000
_EXT_STACK = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".rs": "rust",
    ".go": "go",
}
_SCAN_SKIP_DIRS = {"node_modules", "build", "dist", "target", "venv", "__pycache__"}

#: Kit skills that only earn their cost on one stack. Everything else in the kit is
#: stack-neutral. A project's own skill declares its stacks in frontmatter
#: (`stack_tags: [python, go]`), which wins over this table.
KIT_STACK_TAGS: Dict[str, Tuple[str, ...]] = {
    "python-review-checklist": ("python",),
    "typescript-review-checklist": ("typescript",),
    "java-review-checklist": ("java",),
    "kotlin-review-checklist": ("kotlin",),
}

#: Stack vocabulary for DERIVED tags (project-owned skills only). Each tag is claimed
#: by a case-insensitive word-boundary pattern; ordered by tag so output is stable.
#: Deliberately narrow where English collides: `spring` needs "spring boot"/framework,
#: `react` refuses "react to", `go` needs "golang"/"go.mod".
STACK_VOCAB: Tuple[Tuple[str, str], ...] = (
    ("android", r"\bandroid\b"),
    ("appium", r"\bappium\b"),
    ("go", r"\bgolang\b|\bgo\.mod\b"),
    ("gradle", r"\bgradle\b"),
    ("intellij-plugin", r"\bintellij\b"),
    ("ios", r"\bios\b|\bxcuitest\b|\bswiftui\b"),
    ("java", r"\bjava\b|\.java\b|\bjunit\b"),
    ("kotlin", r"\bkotlin\b|\.kts?\b"),
    ("maven", r"\bmaven\b|\bpom\.xml\b"),
    ("pytest", r"\bpytest\b"),
    ("python", r"\bpython3?\b|\.py\b|\bpytest\b"),
    ("react", r"\breact\b(?!\s+to\b)|\.jsx\b"),
    ("rust", r"\brust\b|\bcargo\.toml\b"),
    ("selenium", r"\bselenium\b|\bwebdriver\b"),
    ("spring", r"\bspring[ -]?boot\b|\bspring framework\b|\bspringframework\b"),
    ("typescript", r"\btypescript\b|\.tsx?\b"),
)
_VOCAB = tuple((tag, re.compile(pattern, re.IGNORECASE)) for tag, pattern in STACK_VOCAB)

REGISTRY_ENV = "CLAUDEKIT_REGISTRY"
#: Jaccard floor for a suggestion. Low on purpose: a project with many tags divides
#: every narrow card's score, and a floor tuned on two-tag projects would hide them.
DEFAULT_MIN_SCORE = 0.1
_PROJECT_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")

RELEVANT, IRRELEVANT, BROKEN = "relevant", "irrelevant", "broken"

_FRONTMATTER_BLOCK = re.compile(r"(?s)\A---\n.*?\n---\n")
_NAME = re.compile(r"(?m)^name:[ \t]*[\"']?(.*?)[\"']?[ \t]*$")
_STACK_TAGS = re.compile(r"(?m)^stack_tags:[ \t]*\[?([^\]\n]*)\]?[ \t]*$")
_TAG = re.compile(r"[a-z0-9][a-z0-9+#.-]*")
_LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
_INLINE_CODE = re.compile(r"`[^`]*`")


class SkillFitError(Exception):
    """A skill-fit verb could not complete. The message names the cause."""


def tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


# ------------------------------------------------------------------ stack detection

def detect_stacks(root: Path) -> Tuple[List[str], Dict[str, str]]:
    """The project's stacks and where each claim came from. Executes nothing.

    Two sources, unioned: `ck adapt`'s own manifest detection (reused, not copied, so
    the two verbs cannot disagree about a pyproject.toml project) and a bounded count
    of source files by extension, which is what catches Java and Kotlin -- adapt's
    marker table does not map pom.xml or build.gradle to a stack.
    """
    root = Path(root)
    found: Dict[str, str] = {}
    primary = adapt.detect(root).stack
    if primary:
        found[primary] = "ck adapt manifest detection"
    counts: Dict[str, int] = {}
    seen = 0
    for path in _walk_sources(root):
        seen += 1
        if seen > MAX_SCAN_FILES:
            break
        stack = _EXT_STACK.get(path.suffix)
        if stack:
            counts[stack] = counts.get(stack, 0) + 1
    for stack, count in sorted(counts.items()):
        if count >= STACK_FILE_THRESHOLD and stack not in found:
            found[stack] = f"{count} {stack} source files"
    return sorted(found), found


def _walk_sources(root: Path) -> Iterator[Path]:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name.startswith(".") or entry.name in _SCAN_SKIP_DIRS:
                    continue
                stack.append(entry)
            elif entry.is_file():
                yield entry


# ------------------------------------------------------------------------ ownership

def manifest_files(root: Path) -> Optional[Set[str]]:
    """Paths the install receipt says the kit owns, or None when there is no receipt."""
    path = Path(root) / ".claude" / ".claudekit-manifest.json"
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    files = doc.get("files") if isinstance(doc, dict) else None
    return set(files) if isinstance(files, dict) else None


# --------------------------------------------------------------------------- audit

def parse_stack_tags(fm: str) -> List[str]:
    return explicit_stack_tags(fm) or []


def explicit_stack_tags(fm: str) -> Optional[List[str]]:
    """Frontmatter `stack_tags`, or None when the key is absent. `stack_tags: []` is an
    explicit empty list -- an opt-out from derivation, not a request for it."""
    m = _STACK_TAGS.search(fm)
    if not m:
        return None
    out: List[str] = []
    for raw in m.group(1).split(","):
        tag = raw.strip().strip("\"'").lower()
        if _TAG.fullmatch(tag) and tag not in out:
            out.append(tag)
    return out


def derive_stack_tags(text: str) -> List[str]:
    """Stack tags a text names, by `STACK_VOCAB`. Deterministic; executes nothing."""
    return [tag for tag, pattern in _VOCAB if pattern.search(text)]


def missing_references(skill_dir: Path, text: str) -> List[str]:
    """Relative markdown links that resolve to nothing.

    Links inside code fences and inline code are examples, not references -- without
    that exclusion the kit's own corpus reports three false positives
    (`./objective-slug.md`, `./path/to/skill.md`, `URL`); with it, zero.
    """
    lines = text.splitlines()
    fenced = adapt.fenced_lines(lines)
    out: List[str] = []
    for index, line in enumerate(lines):
        if index in fenced:
            continue
        for target in _LINK.findall(_INLINE_CODE.sub("", line)):
            if "://" in target or target.startswith(("/", "mailto:")):
                continue
            if not (skill_dir / target).exists() and target not in out:
                out.append(target)
    return out


def inspect_skill(skill_dir: Path, stacks: List[str],
                  owned: Optional[Set[str]], disabled: Set[str],
                  max_lines: int, max_tokens: int) -> Dict[str, Any]:
    name = skill_dir.name
    record: Dict[str, Any] = {
        "name": name,
        "owner": ("unknown" if owned is None
                  else "kit" if f"skills/{name}/SKILL.md" in owned else "local"),
        "disabled": name in disabled,
        "stack_tags": [], "stack_tags_source": "none", "description": "",
        "description_tokens": 0, "always_on_tokens": 0,
        "body_lines": 0, "body_tokens": 0, "over_budget": False,
        "problems": [],
    }
    skill_md = skill_dir / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        record["problems"].append(f"SKILL.md unreadable: {exc.__class__.__name__}")
        record["status"] = BROKEN
        return record

    fm = context_floor.frontmatter(text)
    block = _FRONTMATTER_BLOCK.match(text)
    body = text[block.end():] if block else text
    description = context_floor.description_span(fm).strip() if fm else ""
    if not fm:
        record["problems"].append("no frontmatter block (--- ... ---)")
    else:
        name_match = _NAME.search(fm)
        if not name_match or not name_match.group(1).strip():
            record["problems"].append("frontmatter has no name")
        if not description:
            record["problems"].append("frontmatter has no description")
    for target in missing_references(skill_dir, text):
        record["problems"].append(f"missing referenced file: {target}")

    explicit = explicit_stack_tags(fm)
    if explicit is not None:
        tags, source = explicit, "frontmatter"
    elif name in KIT_STACK_TAGS:
        tags, source = list(KIT_STACK_TAGS[name]), "kit-table"
    elif record["owner"] == "local":
        # Union with the project's stacks, so a local skill always overlaps the stacks
        # it was written for and can never be bucketed irrelevant by its own derivation.
        tags = sorted(set(derive_stack_tags(f"{name}\n{description}\n{body}")) | set(stacks))
        source = "derived" if tags else "none"
    else:
        tags, source = [], "none"
    body_lines = body.count("\n")
    body_tokens = tokens(body)
    record.update({
        "stack_tags": tags,
        "stack_tags_source": source,
        "description": description,
        "description_tokens": tokens(description),
        "always_on_tokens": 0 if context_floor.model_invisible(fm) else tokens(description),
        "body_lines": body_lines,
        "body_tokens": body_tokens,
        "over_budget": body_lines > max_lines or body_tokens > max_tokens,
    })
    if record["problems"]:
        record["status"] = BROKEN
    elif tags and stacks and not set(tags) & set(stacks):
        # An UNDETECTED stack never makes a skill irrelevant: `profile init` disables
        # what this bucket names, and guessing there would disable real capability.
        record["status"] = IRRELEVANT
    else:
        record["status"] = RELEVANT
    return record


def audit(root: Path, *, max_lines: int = DEFAULT_MAX_LINES,
          max_tokens: int = DEFAULT_MAX_TOKENS) -> Dict[str, Any]:
    root = Path(root)
    directory = skills.skills_dir(root)
    if not directory.is_dir():
        raise SkillFitError(f"no skills directory at {directory}; nothing to audit")
    stacks, sources = detect_stacks(root)
    profile = load_profile(root) or {}
    disabled = set(profile.get("disabled", []))
    owned = manifest_files(root)
    records = [
        inspect_skill(d, stacks, owned, disabled, max_lines, max_tokens)
        for d in sorted(directory.iterdir())
        if d.is_dir() and not d.name.startswith((".", "__"))
    ]
    totals = {
        "skills": len(records),
        RELEVANT: sum(1 for r in records if r["status"] == RELEVANT),
        IRRELEVANT: sum(1 for r in records if r["status"] == IRRELEVANT),
        BROKEN: sum(1 for r in records if r["status"] == BROKEN),
        "over_budget": sum(1 for r in records if r["over_budget"]),
        "always_on_tokens": sum(r["always_on_tokens"] for r in records),
        "always_on_tokens_irrelevant": sum(
            r["always_on_tokens"] for r in records if r["status"] == IRRELEVANT),
        "body_tokens": sum(r["body_tokens"] for r in records),
    }
    return {
        "schema": SCHEMA_VERSION,
        "estimate": "tokens = chars/4, rounded up",
        "stacks": stacks,
        "stack_sources": sources,
        "budget": {"max_lines": max_lines, "max_tokens": max_tokens},
        "totals": totals,
        "skills": records,
    }


def report_path(root: Path) -> Path:
    return Path(root).joinpath(*REPORT_REL)


def save_audit(root: Path, report: Dict[str, Any]) -> Path:
    path = report_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    adapt.write_atomic(path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


# ------------------------------------------------------------------------- profile

def profile_path(root: Path) -> Path:
    return Path(root) / ".claude" / PROFILE_NAME


def load_profile(root: Path) -> Optional[Dict[str, Any]]:
    """The project's profile, None when absent, SkillFitError when malformed."""
    path = profile_path(root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SkillFitError(f"unreadable {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise SkillFitError(f"{path}: expected a JSON object")
    unknown = sorted(set(doc) - set(PROFILE_KEYS))
    if unknown:
        raise SkillFitError(f"{path}: unknown key(s) {', '.join(unknown)}; "
                            f"allowed: {', '.join(PROFILE_KEYS)}")
    for key in ("packs", "disabled"):
        value = doc.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SkillFitError(f"{path}: '{key}' must be a list of strings")
    overlays = doc.get("overlays", {})
    if not isinstance(overlays, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in overlays.items()):
        raise SkillFitError(f"{path}: 'overlays' must map skill name -> file path")
    if not isinstance(doc.get("roles", {}), dict):
        raise SkillFitError(f"{path}: 'roles' must be an object")
    return doc


def profile_findings(root: Path) -> Tuple[List[str], List[str]]:
    """(errors, warnings) for the profile. Both empty when there is no profile.

    Errors are things that cannot be right: a malformed file, an overlay path that is
    absolute or escapes the project. Warnings are references that went stale -- a kit
    update that removes a skill must not turn every downstream doctor red.
    """
    root = Path(root)
    try:
        doc = load_profile(root)
    except SkillFitError as exc:
        return [str(exc)], []
    if doc is None:
        return [], []
    errors: List[str] = []
    warnings: List[str] = []
    directory = skills.skills_dir(root)
    try:
        aliases = skills.renamed_map(skills.load_registry(root))
    except skills.SkillError:
        aliases = {}

    def dangling(kind: str, name: str) -> None:
        if (directory / name / "SKILL.md").is_file():
            return
        hint = f" (renamed to '{aliases[name]}')" if name in aliases else ""
        warnings.append(f"{kind} names skill '{name}', which is not installed{hint}")

    for name in doc.get("disabled", []):
        dangling("disabled", name)
    real_root = root.resolve()
    for name, rel in sorted(doc.get("overlays", {}).items()):
        dangling("overlays", name)
        candidate = Path(rel)
        if candidate.is_absolute():
            errors.append(f"overlay for '{name}' is an absolute path; use a "
                          f"project-relative one")
            continue
        target = (root / candidate).resolve()
        if target != real_root and real_root not in target.parents:
            errors.append(f"overlay for '{name}' escapes the project: {rel}")
        elif not target.is_file():
            warnings.append(f"overlay for '{name}' points at a missing file: {rel}")
    return errors, warnings


def init_profile(root: Path, report: Dict[str, Any]) -> Path:
    """Write a starting profile from an audit. Never overwrites: the file is the
    project's, and a regenerated one would silently discard its decisions."""
    path = profile_path(root)
    if not path.parent.is_dir():
        raise SkillFitError(f"no {path.parent} directory; install ClaudeKit first")
    doc = {
        "schema": SCHEMA_VERSION,
        "packs": [],
        "disabled": sorted(r["name"] for r in report["skills"]
                           if r["status"] == IRRELEVANT),
        "overlays": {},
        "roles": {},
    }
    try:
        with open(str(path), "x", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, indent=2) + "\n")
    except FileExistsError as exc:
        raise SkillFitError(f"{path} already exists and is never overwritten; "
                            f"edit it by hand") from exc
    return path


# --------------------------------------------------------------------------- cards

def _card_refusal(name: str, description: str) -> Optional[str]:
    """Why a card must not leave the project, or None. Reasons never quote content."""
    if not skills.NAME_RE.fullmatch(name):
        return "name is not a kebab-case skill id"
    if not description:
        return "no description"
    if len(description) > skills.MAX_DESCRIPTION:
        return f"description longer than {skills.MAX_DESCRIPTION} chars"
    if not description.isprintable():
        return "description contains control characters"
    if memory.rejections(name, description):
        return "description failed the sanitizer (secret-, credential- or private-path-shaped)"
    return None


def cards(root: Path) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Sanitized cards for this project's OWN skills, plus (name, reason) withheld.

    Only metadata leaves: name, stack tags, description, estimated tokens. Never a
    body, never a path. Ownership comes from the install receipt, so without one this
    refuses rather than guessing -- a guess would publish kit skills as the project's.
    """
    root = Path(root)
    owned = manifest_files(root)
    if owned is None:
        raise SkillFitError(
            "no readable .claude/.claudekit-manifest.json, so kit skills cannot be told "
            "apart from this project's own; refusing to emit cards")
    report = audit(root)
    out: List[Dict[str, Any]] = []
    withheld: List[Tuple[str, str]] = []
    for record in report["skills"]:
        if record["owner"] != "local":
            continue
        if record["status"] == BROKEN:
            withheld.append((record["name"], "skill is broken (see `ck skill audit`)"))
            continue
        why = _card_refusal(record["name"], record["description"])
        if why:
            withheld.append((record["name"], why))
            continue
        out.append({
            "card_version": CARD_VERSION,
            "name": record["name"],
            "stack_tags": record["stack_tags"],
            "description": record["description"],
            "tokens": record["description_tokens"] + record["body_tokens"],
        })
    return out, withheld


def load_cards(registry: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Cards from every *.json under ``registry``, and why any were skipped.

    Another project's card is untrusted input: every field is re-validated here and a
    card that fails is skipped, never repaired.
    """
    registry = Path(registry)
    if not registry.is_dir():
        raise SkillFitError(f"card registry {registry} is not a directory")
    loaded: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for path in sorted(registry.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            skipped.append(f"{path.name}: not readable JSON")
            continue
        items = doc.get("cards") if isinstance(doc, dict) and "cards" in doc else [doc]
        if not isinstance(items, list):
            skipped.append(f"{path.name}: 'cards' is not a list")
            continue
        for item in items:
            problem = _invalid_card(item)
            if problem:
                skipped.append(f"{path.name}: {problem}")
                continue
            loaded.append(dict(item, source=path.stem))
    return loaded, skipped


def _invalid_card(item: Any) -> Optional[str]:
    if not isinstance(item, dict):
        return "card is not an object"
    name, tags = item.get("name"), item.get("stack_tags")
    description, count = item.get("description"), item.get("tokens")
    if not isinstance(name, str) or not isinstance(description, str):
        return "card needs string name and description"
    if (not isinstance(tags, list)
            or not all(isinstance(t, str) and _TAG.fullmatch(t) for t in tags)):
        return f"card '{name[:40]}' has invalid stack_tags"
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return f"card '{name[:40]}' has invalid tokens"
    why = _card_refusal(name, description)
    return f"card refused: {why}" if why else None


def registry_dir() -> Path:
    """The user-level card registry: `$CLAUDEKIT_REGISTRY`, else ~/.claudekit/registry/cards.

    Never inside a repository. A relative override is refused: it would resolve
    against whatever directory `ck` runs in, which is a repository.
    """
    override = os.environ.get(REGISTRY_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise SkillFitError(f"{REGISTRY_ENV} must be an absolute path, got {override!r}")
        return path
    return Path.home() / ".claudekit" / "registry" / "cards"


def project_id(root: Path, explicit: Optional[str] = None) -> str:
    """The card file stem for a project: `--project`, else the directory name, lowercased."""
    raw = explicit if explicit is not None else Path(root).resolve().name
    ident = raw.strip().lower()
    if not _PROJECT_ID.fullmatch(ident):
        raise SkillFitError(f"project id {raw!r} is not [a-z0-9][a-z0-9._-]*; "
                            f"pass --project <id>")
    return ident


def publish_cards(root: Path, *, project: Optional[str] = None,
                  registry: Optional[Path] = None
                  ) -> Tuple[Path, List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Write this project's sanitized cards to the registry, atomically. Replaces the
    project's previous card file whole, so a removed skill stops being suggested."""
    found, withheld = cards(root)
    ident = project_id(root, project)
    directory = Path(registry) if registry is not None else registry_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ident}.json"
    doc = {"card_version": CARD_VERSION, "project": ident, "cards": found}
    adapt.write_atomic(path, json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return path, found, withheld


def match(root: Path, registry: Optional[Path] = None, *, project: Optional[str] = None,
          min_score: float = DEFAULT_MIN_SCORE) -> Dict[str, Any]:
    """Suggest cards whose tags overlap this project's tags. Installs nothing.

    The project's tags are its detected stacks plus the tags of its own skills, so two
    Appium projects whose source counts fall under the stack threshold still meet on
    the `appium`/`android` their skills name. Score is Jaccard: |card & project| /
    |card | project|. The project's own card file is skipped.
    """
    root = Path(root)
    default = registry is None
    directory = registry_dir() if registry is None else Path(registry)
    if not directory.is_dir():
        hint = (" -- publish one with `ck skill card --publish` in another project, or set "
                f"{REGISTRY_ENV} / pass --registry") if default else ""
        raise SkillFitError(f"no card registry at {directory}{hint}")
    try:
        report: Optional[Dict[str, Any]] = audit(root)
    except SkillFitError:
        report = None
    if report is not None:
        stacks = report["stacks"]
        installed = {r["name"] for r in report["skills"]}
        own_tags = {t for r in report["skills"] if r["owner"] == "local"
                    for t in r["stack_tags"]}
    else:
        stacks, _ = detect_stacks(root)
        installed, own_tags = set(), set()
    project_tags = set(stacks) | own_tags
    try:
        own = project_id(root, project)
    except SkillFitError:
        own = None
    loaded, skipped = load_cards(directory)
    suggestions: List[Dict[str, Any]] = []
    for card in loaded:
        if card["source"] == own or card["name"] in installed:
            continue
        tags = set(card["stack_tags"])
        overlap = sorted(tags & project_tags)
        if not overlap:
            continue
        score = round(len(overlap) / len(tags | project_tags), 3)
        if score < min_score:
            continue
        suggestions.append({
            "name": card["name"],
            "source": card["source"],
            "score": score,
            "matched_tags": overlap,
            "tokens": card["tokens"],
            "description": card["description"],
        })
    suggestions.sort(key=lambda s: (-s["score"], s["tokens"], s["name"], s["source"]))
    return {"stacks": stacks, "project_tags": sorted(project_tags),
            "registry": str(directory), "project": own, "min_score": min_score,
            "suggestions": suggestions, "skipped": skipped}

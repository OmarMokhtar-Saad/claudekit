"""Layered hook/asset profiles — the resolver behind `ck profile`.

Why this exists
---------------
Before this module a "profile" was one environment variable, ``ECC_HOOK_PROFILE``,
read independently by eleven hook scripts in four different guard forms. It has
three effective values (``minimal``, ``standard`` — the default — and ``strict``),
and there was no way to ask the installation which one was active or what that
implied. "Which profile is actually running" is the single most recurring session
gotcha in this repo's history.

What a profile is here — and what it is NOT
-------------------------------------------
A profile is a **declaration** that is mechanically bound to the hooks' own guards.
It does not yet *drive* them: the shell and Python hooks still read
``ECC_HOOK_PROFILE`` exactly as they did before, so this module cannot change hook
behaviour, and installing it cannot break an existing project. The binding is
:func:`scan_hook_guards`, which reads the shipped hook artifact and derives the
per-profile mode from its actual guard lines; a declaration that disagrees with the
artifact is a failure, in the test suite and in ``ck doctor``. Calling this a
control would be an overstatement — it is an inspectable, drift-gated description.

Layer order (documented in `.ai/PROFILES.md`, proved in tests/test_profiles.py)
-------------------------------------------------------------------------------
``base -> profile -> project-local -> override``. Each layer replaces rows **by
id**; a row an outer layer does not mention survives from the layer beneath.

Fail-closed
-----------
Every load path raises :class:`ProfileError` with a named cause. There is no
permissive fallback: an unknown profile name, an unreadable file, an unknown
schema version, an unknown section, an unknown row id and an out-of-range value
all raise. A resolver that guessed would put the answer to "what is active" back
in the state this module exists to end.
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 1

#: Composition order, outermost last. Exposed so docs and tests cite one list.
LAYERS: Tuple[str, ...] = ("base", "profile", "project-local", "override")

#: A hook either runs and may block (``on``), runs but cannot block
#: (``advisory`` — reflection-gate under ``minimal``), or short-circuits (``off``).
HOOK_MODES: Tuple[str, ...] = ("on", "advisory", "off")
TOGGLE_MODES: Tuple[str, ...] = ("on", "off")

#: The eleven hooks that carry an ``ECC_HOOK_PROFILE`` guard, and their file names.
#: A hook NOT listed here is profile-independent; tests assert that no unlisted
#: hook grows a guard without this table being updated.
GUARDED_HOOKS: Dict[str, str] = {
    "block-no-verify": "block-no-verify.sh",
    "command-guard": "command-guard.sh",
    "commit-quality": "commit-quality.sh",
    "config-protection": "config-protection.sh",
    "file-guard-gate": "file-guard-gate.sh",
    "format-typecheck": "format-typecheck.sh",
    "injection-scan-gate": "injection-scan-gate.sh",
    "iron-law-gate": "iron-law-gate.py",
    "ops-enforcement": "ops-enforcement.sh",
    "reflection-gate": "reflection-gate.py",
    "security-reminder": "security-reminder.sh",
}

#: Sections a profile document may declare, and the value domain of each.
SECTIONS: Tuple[str, ...] = ("hooks", "agents", "commands", "mcp", "stack")

MCP_KEYS: Tuple[str, ...] = ("max_servers", "max_tools")
STACK_KEYS: Tuple[str, ...] = ("build_cmd", "test_cmd", "lint_cmd", "coverage_cmd")

#: The default env value every hook falls back to (`${ECC_HOOK_PROFILE:-standard}`).
DEFAULT_PROFILE = "standard"
PROFILE_ENV = "ECC_HOOK_PROFILE"


class ProfileError(Exception):
    """A profile could not be loaded or composed. The message names the cause."""


class Row:
    """One resolved (section, id) pair, plus the layer that last set it."""

    __slots__ = ("section", "id", "value", "layer")

    def __init__(self, section: str, id: str, value: Any, layer: str) -> None:
        self.section = section
        self.id = id
        self.value = value
        self.layer = layer

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Row({self.section}.{self.id}={self.value!r} <- {self.layer})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Row):
            return NotImplemented
        return (self.section, self.id, self.value, self.layer) == (
            other.section, other.id, other.value, other.layer)


class Resolved:
    """The composed result: rows keyed by (section, id), each attributed."""

    def __init__(self, name: str, rows: Dict[Tuple[str, str], Row]) -> None:
        self.name = name
        self.rows = rows

    def section(self, section: str) -> Dict[str, Row]:
        return {rid: row for (sec, rid), row in self.rows.items() if sec == section}

    def value(self, section: str, row_id: str) -> Any:
        """Value for a row, falling back to the section's ``*`` default if present."""
        row = self.rows.get((section, row_id))
        if row is not None:
            return row.value
        star = self.rows.get((section, "*"))
        if star is not None:
            return star.value
        raise ProfileError(f"no row and no '*' default for {section}.{row_id}")

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"profile": self.name, "layers": list(LAYERS), "sections": {}}
        for section in SECTIONS:
            out["sections"][section] = {
                rid: {"value": row.value, "layer": row.layer}
                for rid, row in sorted(self.section(section).items())
            }
        return out


def base_layer() -> Dict[str, Dict[str, Any]]:
    """The built-in bottom layer: everything on, no budget, no stack facts.

    ``base`` is deliberately NOT a shipped profile directory. It is the identity
    every profile is a diff against, so `ck profile list` shows only real,
    selectable profiles and `.claude/profiles/` never grows a pseudo-entry.
    """
    return {
        "hooks": {hid: "on" for hid in sorted(GUARDED_HOOKS)},
        "agents": {"*": "on"},
        "commands": {"*": "on"},
        "mcp": {key: None for key in MCP_KEYS},
        "stack": {key: None for key in STACK_KEYS},
    }


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------

def profiles_dir(root: Path) -> Path:
    return Path(root) / ".claude" / "profiles"


def list_profiles(root: Path) -> List[str]:
    """Names of installed profiles (directories containing ``profile.json``)."""
    directory = profiles_dir(root)
    if not directory.is_dir():
        return []
    names = []
    for child in sorted(directory.iterdir()):
        if child.is_dir() and (child / "profile.json").is_file():
            names.append(child.name)
    return names


def _read_doc(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"unreadable profile file {path}: {exc}") from exc
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ProfileError(f"malformed JSON in {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ProfileError(f"{path}: top level must be an object, got {type(doc).__name__}")
    return doc


def _check_value(section: str, row_id: str, value: Any, where: str) -> None:
    if section == "hooks":
        if row_id not in GUARDED_HOOKS:
            raise ProfileError(
                f"{where}: unknown hook id {row_id!r} "
                f"(known: {', '.join(sorted(GUARDED_HOOKS))})")
        if value not in HOOK_MODES:
            raise ProfileError(
                f"{where}: hooks.{row_id} must be one of {', '.join(HOOK_MODES)}, "
                f"got {value!r}")
    elif section in ("agents", "commands"):
        if value not in TOGGLE_MODES:
            raise ProfileError(
                f"{where}: {section}.{row_id} must be one of "
                f"{', '.join(TOGGLE_MODES)}, got {value!r}")
    elif section == "mcp":
        if row_id not in MCP_KEYS:
            raise ProfileError(
                f"{where}: unknown mcp key {row_id!r} (known: {', '.join(MCP_KEYS)})")
        if value is not None and not (isinstance(value, int) and not isinstance(value, bool)
                                      and value >= 0):
            raise ProfileError(
                f"{where}: mcp.{row_id} must be a non-negative integer or null, got {value!r}")
    elif section == "stack":
        if row_id not in STACK_KEYS:
            raise ProfileError(
                f"{where}: unknown stack key {row_id!r} (known: {', '.join(STACK_KEYS)})")
        if value is not None and not isinstance(value, str):
            raise ProfileError(f"{where}: stack.{row_id} must be a string or null, got {value!r}")


def validate_doc(doc: Dict[str, Any], where: str, *, require_name: bool = True) -> None:
    """Raise ProfileError unless ``doc`` is a well-formed profile document."""
    version = doc.get("schema_version")
    if version is None:
        raise ProfileError(f"{where}: missing 'schema_version' (expected {SCHEMA_VERSION})")
    if version != SCHEMA_VERSION:
        raise ProfileError(
            f"{where}: unsupported schema_version {version!r}; this ClaudeKit "
            f"understands {SCHEMA_VERSION} only")
    allowed = {"schema_version", "name", "description", "extends"} | set(SECTIONS)
    unknown = sorted(set(doc) - allowed)
    if unknown:
        raise ProfileError(
            f"{where}: unknown top-level key(s) {', '.join(unknown)} "
            f"(allowed: {', '.join(sorted(allowed))})")
    if require_name and not isinstance(doc.get("name"), str):
        raise ProfileError(f"{where}: 'name' must be a string")
    extends = doc.get("extends")
    if extends is not None and not isinstance(extends, str):
        raise ProfileError(f"{where}: 'extends' must be a string or null, got {extends!r}")
    for section in SECTIONS:
        rows = doc.get(section)
        if rows is None:
            continue
        if not isinstance(rows, dict):
            raise ProfileError(f"{where}: section {section!r} must be an object")
        for row_id, value in rows.items():
            if not isinstance(row_id, str) or not row_id:
                raise ProfileError(f"{where}: {section} has a non-string row id {row_id!r}")
            _check_value(section, row_id, value, where)


def load_profile(root: Path, name: str) -> Dict[str, Any]:
    """Load one profile document (without resolving ``extends``)."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name or ""):
        raise ProfileError(f"invalid profile name {name!r} (expected kebab-case)")
    path = profiles_dir(root) / name / "profile.json"
    if not path.is_file():
        known = list_profiles(root)
        hint = ", ".join(known) if known else "none installed"
        raise ProfileError(f"unknown profile {name!r} (installed: {hint})")
    doc = _read_doc(path)
    validate_doc(doc, f"{name}/profile.json")
    if doc.get("name") != name:
        raise ProfileError(
            f"{name}/profile.json: 'name' is {doc.get('name')!r} but the directory "
            f"is {name!r}; the two must agree or `ck profile show` would lie")
    return doc


def _profile_chain(root: Path, name: str) -> List[Dict[str, Any]]:
    """``extends`` chain, base-most first. Cycles and unknown parents raise."""
    chain: List[Dict[str, Any]] = []
    seen: List[str] = []
    current: Optional[str] = name
    while current is not None:
        if current in seen:
            raise ProfileError(
                "profile 'extends' cycle: " + " -> ".join(seen + [current]))
        seen.append(current)
        doc = load_profile(root, current)
        chain.append(doc)
        parent = doc.get("extends")
        current = parent if isinstance(parent, str) else None
    chain.reverse()
    return chain


def parse_overrides(items: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """``["hooks.ops-enforcement=off"]`` -> ``{"hooks": {"ops-enforcement": "off"}}``.

    Values are read as JSON when they parse as JSON (so ``mcp.max_tools=0`` and
    ``stack.build_cmd=null`` work), else as the literal string.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if "=" not in item:
            raise ProfileError(f"override {item!r} is not SECTION.ID=VALUE")
        key, raw = item.split("=", 1)
        if "." not in key:
            raise ProfileError(f"override {item!r} is not SECTION.ID=VALUE")
        section, row_id = key.split(".", 1)
        if section not in SECTIONS:
            raise ProfileError(
                f"override {item!r}: unknown section {section!r} "
                f"(known: {', '.join(SECTIONS)})")
        try:
            value: Any = json.loads(raw)
        except ValueError:
            value = raw
        _check_value(section, row_id, value, f"override {item!r}")
        out.setdefault(section, {})[row_id] = value
    return out


def select_name(root: Path, name: Optional[str] = None,
                env: Optional[Dict[str, str]] = None) -> str:
    """Which profile is active: explicit argument, then env, then the default."""
    if name:
        return name
    environ = os.environ if env is None else env
    return environ.get(PROFILE_ENV) or DEFAULT_PROFILE


def resolve(root: Path, name: Optional[str] = None, *,
            env: Optional[Dict[str, str]] = None,
            overrides: Optional[Sequence[str]] = None) -> Resolved:
    """Compose ``base -> profile -> project-local -> override`` and attribute rows."""
    root = Path(root)
    selected = select_name(root, name, env)
    rows: Dict[Tuple[str, str], Row] = {}

    def apply(sections: Dict[str, Dict[str, Any]], layer: str) -> None:
        for section, entries in sections.items():
            for row_id, value in entries.items():
                rows[(section, row_id)] = Row(section, row_id, value, layer)

    apply(base_layer(), "base")

    for doc in _profile_chain(root, selected):
        apply({s: dict(doc[s]) for s in SECTIONS if isinstance(doc.get(s), dict)}, "profile")

    local_path = profiles_dir(root) / "local.json"
    if local_path.is_file():
        local = _read_doc(local_path)
        validate_doc(local, "profiles/local.json", require_name=False)
        if local.get("extends") is not None:
            raise ProfileError(
                "profiles/local.json: 'extends' is not allowed in the project-local "
                "layer; it overlays whatever profile is selected")
        apply({s: dict(local[s]) for s in SECTIONS if isinstance(local.get(s), dict)},
              "project-local")

    if overrides:
        apply(parse_overrides(overrides), "override")

    return Resolved(selected, rows)


# --------------------------------------------------------------------------
# The binding: derive each hook's real per-profile mode from its own guards
# --------------------------------------------------------------------------

#: A line can only be a guard if it DEREFERENCES the variable. Prose that merely
#: NAMES it (`set ECC_HOOK_PROFILE=strict to block instead`) is not a candidate,
#: and must not be, or every help string would read as an unknown form.
#:
#: This is a regex and not a substring test on purpose. `${ECC_HOOK_PROFILE` misses
#: `$ECC_HOOK_PROFILE` — the brace-less form is ordinary bash, and a substring test
#: skipped it WITHOUT recording it as unknown: neither recognised nor reported,
#: which is the exact silent-drift failure this scanner exists to make impossible.
#: Caught in review of this module rather than by a hook someday written that way.
#:
#: Neither alternative requires QUOTES, for the same reason. Round 2 of review found
#: that `"$PROFILE"` — quoted — left `[ $PROFILE = "minimal" ]` in the identical
#: hole: unquoted is valid shell, and the alias is one this module already models.
#: Two instances of one class in two rounds is the argument for matching the
#: dereference itself and letting the FORM regexes below decide what is recognised.
_SH_SIGIL_RE = re.compile(r'\$\{?' + PROFILE_ENV + r'\b|\$PROFILE\b')

_SH_ENV_GUARD = re.compile(
    r'^\[\s*"\$\{' + PROFILE_ENV + r':-standard\}"\s*(=|!=)\s*"([a-z]+)"\s*\]'
    r'\s*&&\s*exit\s+0\s*$')
_SH_VAR_GUARD = re.compile(
    r'^\[\s*"\$PROFILE"\s*(=|!=)\s*"([a-z]+)"\s*\]\s*&&\s*exit\s+0\s*$')
_SH_ASSIGN = re.compile(r'^PROFILE="\$\{' + PROFILE_ENV + r':-standard\}"\s*$')
#: A profile-conditional that makes an ALREADY-RUNNING hook stricter rather than
#: turning it off: `[ "$PROFILE" = "strict" ] && deny "..."` in command-guard.sh,
#: which blocks instead of warning when the validator is missing. Recognised on
#: purpose and narrowly — the consequent must be `deny`, so an `exit 0` written in
#: this shape still reads as an enablement guard and still has to be declared.
_SH_STRICTEN = re.compile(
    r'^\[\s*"\$(?:PROFILE|\{' + PROFILE_ENV + r':-standard\})"\s*(?:=|!=)\s*"[a-z]+"\s*\]'
    r'\s*&&\s*deny\s')


def _apply_guard(modes: Dict[str, str], op: str, target: str, mode: str) -> None:
    if op == "=":
        modes[target] = mode
    else:
        for key in modes:
            if key != target:
                modes[key] = mode


def _scan_shell(text: str, known: Iterable[str]) -> Tuple[Dict[str, str], List[str]]:
    modes = {name: "on" for name in known}
    unknown: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("#") or not _SH_SIGIL_RE.search(line):
            continue
        if _SH_ASSIGN.match(line):
            continue
        if _SH_STRICTEN.match(line):
            continue
        match = _SH_ENV_GUARD.match(line) or _SH_VAR_GUARD.match(line)
        if match:
            _apply_guard(modes, match.group(1), match.group(2), "off")
            continue
        unknown.append(f"line {lineno}: {line}")
    return modes, unknown


def _scan_python(text: str, known: Iterable[str], where: str) -> Tuple[Dict[str, str], List[str]]:
    modes = {name: "on" for name in known}
    unknown: List[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ProfileError(f"{where}: cannot parse hook: {exc}") from exc

    enclosing: Dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    enclosing.setdefault(child.lineno, node.name)

    consumed = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        call = node.left
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "get" and call.args
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == PROFILE_ENV):
            continue
        right = node.comparators[0]
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            continue
        op, target = node.ops[0], right.value
        func = enclosing.get(node.lineno, "")
        if func == "blocking_enabled" and isinstance(op, ast.NotEq):
            # "blocking is enabled unless X" -> under X the hook still runs, but
            # cannot block. That is `advisory`, not `off`, and the distinction is
            # the whole reason HOOK_MODES has three values.
            _apply_guard(modes, "=", target, "advisory")
        elif isinstance(op, ast.Eq):
            _apply_guard(modes, "=", target, "off")
        else:
            unknown.append(f"line {node.lineno}: unrecognised {PROFILE_ENV} comparison")
            continue
        consumed.add(call.args[0].lineno)

    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and node.value == PROFILE_ENV
                and node.lineno not in consumed):
            unknown.append(
                f"line {node.lineno}: {PROFILE_ENV} referenced outside a recognised guard")
    return modes, unknown


def scan_hook_guards(path: Path, known: Optional[Iterable[str]] = None
                     ) -> Tuple[Dict[str, str], List[str]]:
    """Derive ``profile -> mode`` from a hook's OWN guard lines.

    Returns ``(modes, unrecognised)``. ``unrecognised`` is the load-bearing half:
    a guard written in a form this function does not model is reported rather than
    silently ignored, so a new guard shape reddens the gate instead of leaving the
    declaration quietly wrong. That failure mode — a mirror that only detects
    CHANGED clauses, never ADDED ones — is a recurrence class this repo has already
    paid for once (`.ai/REVIEW_GUIDE.md`).
    """
    path = Path(path)
    names = list(known) if known is not None else ["minimal", "standard", "strict"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"unreadable hook {path}: {exc}") from exc
    if path.suffix == ".py":
        return _scan_python(text, names, str(path))
    return _scan_shell(text, names)


def guard_modes_for(hooks_dir: Path, profile_names: Sequence[str]
                    ) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    """Scan every guarded hook. Returns ``(hook -> profile -> mode, problems)``."""
    hooks_dir = Path(hooks_dir)
    table: Dict[str, Dict[str, str]] = {}
    problems: List[str] = []
    for hook_id, filename in sorted(GUARDED_HOOKS.items()):
        path = hooks_dir / filename
        if not path.is_file():
            problems.append(f"{hook_id}: missing hook file {filename}")
            continue
        modes, unknown = scan_hook_guards(path, profile_names)
        table[hook_id] = modes
        problems.extend(f"{hook_id}: {u}" for u in unknown)
    return table, problems


def check_declarations(root: Path) -> List[str]:
    """Every installed profile's ``hooks`` rows vs. the hooks' real guards.

    Returns a list of human-readable disagreements; empty means the declaration
    matches the shipped artifact. This is what `ck doctor` runs, so a profile that
    has drifted from the hooks is a health failure and not merely a red test.
    """
    root = Path(root)
    names = list_profiles(root)
    if not names:
        return []
    hooks_dir = root / ".claude" / "hooks"
    if not hooks_dir.is_dir():
        # A `--minimal` install ships no hooks at all. There is nothing to
        # disagree with, and reporting eleven "missing hook file" problems would
        # turn a designed absence into a health failure.
        return []
    table, problems = guard_modes_for(hooks_dir, names)
    for name in names:
        try:
            resolved = resolve(root, name, env={})
        except ProfileError as exc:
            problems.append(f"{name}: {exc}")
            continue
        for hook_id in sorted(GUARDED_HOOKS):
            if hook_id not in table:
                continue
            declared = resolved.value("hooks", hook_id)
            actual = table[hook_id].get(name)
            if actual is None:
                continue
            if declared != actual:
                problems.append(
                    f"{name}: hooks.{hook_id} declares {declared!r} but "
                    f"{GUARDED_HOOKS[hook_id]} behaves {actual!r}")
    return problems

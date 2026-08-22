"""`ck mcp add` — an MCP server is a standing context cost, so it has a budget.

Why a budget at all
-------------------
An MCP server's tool schemas are injected into **every** session that has the
server configured, whether or not a single tool is called. That makes "add an
MCP server" one of the few decisions in this repo that raises the always-on
floor for all future work, and it was until now the only such decision with no
gate on it. `.claude/profiles/<name>/profile.json` already declares
``mcp.max_servers`` and ``mcp.max_tools``; this module is what makes those two
numbers mean something at the moment a server is added.

What this is NOT
----------------
This is not a runtime, a client, or a supervisor, and it executes nothing. It
reads two JSON files, decides, and writes two JSON files. The tool count is
supplied by the operator (``--tools N``); ClaudeKit never spawns the server to
find out. Measuring it automatically would mean downloading and running
third-party code from a `ck` verb, and ClaudeKit's command denylist allowlists
`npx`, `node` and `docker` -- it would not stop that, and it is a speed bump,
not a sandbox. See `.claude/plans/ops-mcp-probe.json` for an opt-in probe,
queued separately and owner-gated.

Adoption
--------
A server already in `.mcp.json` with no ledger row (Claude Code wrote it, or a
human did) is *adopted* by `ck mcp add <name> --tools N`: the count is recorded,
no configuration is touched, and the budget cannot refuse a cost already being
paid. Without that, the fail-closed "projected total is unknown" refusal had no
reachable remedy.

Declared tool counts
--------------------
`.mcp.json` is Claude Code's file and carries no room for our bookkeeping, so
the per-server tool count lives beside it in `.claude/state/mcp-servers.json`.
The count is **required** (``--tools N``, from the server's documentation).
There is no default, because a default of zero would make the ``max_tools``
budget pass by pretending every server is free.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import profiles

NAME_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")


class MCPError(Exception):
    """A server could not be added. The message names the cause and the numbers."""


def config_path(root: Path) -> Path:
    """Claude Code's project-scope MCP config."""
    return Path(root) / ".mcp.json"


def ledger_path(root: Path) -> Path:
    """Our bookkeeping: declared tool counts and how each count was obtained."""
    return Path(root) / ".claude" / "state" / "mcp-servers.json"


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file():
        return dict(default)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MCPError(f"unreadable {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise MCPError(f"{path}: top level must be an object")
    return doc


def load_config(root: Path) -> Dict[str, Any]:
    doc = _read_json(config_path(root), {"mcpServers": {}})
    doc.setdefault("mcpServers", {})
    if not isinstance(doc["mcpServers"], dict):
        raise MCPError(f"{config_path(root)}: 'mcpServers' must be an object")
    return doc


def load_ledger(root: Path) -> Dict[str, Any]:
    doc = _read_json(ledger_path(root), {"schema_version": 1, "servers": {}})
    doc.setdefault("schema_version", 1)
    doc.setdefault("servers", {})
    if not isinstance(doc["servers"], dict):
        raise MCPError(f"{ledger_path(root)}: 'servers' must be an object")
    return doc


def declared_tools(ledger: Dict[str, Any]) -> int:
    total = 0
    for name, row in ledger.get("servers", {}).items():
        count = row.get("tools") if isinstance(row, dict) else None
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise MCPError(
                f"{name}: tool count in the ledger is {count!r}, not a non-negative "
                f"integer; the max_tools budget cannot be evaluated against it"
            )
        total += count
    return total


def budget(root: Path, profile: Optional[str] = None) -> Tuple[str, Optional[int], Optional[int]]:
    """``(profile_name, max_servers, max_tools)``; ``None`` means unlimited."""
    try:
        resolved = profiles.resolve(Path(root), profile)
        # value() is inside the try on purpose: a raw ProfileError escaping here
        # would surface as a traceback through cmd_mcp's `except mcp.MCPError`.
        return (resolved.name,
                resolved.value("mcp", "max_servers"),
                resolved.value("mcp", "max_tools"))
    except profiles.ProfileError as exc:
        raise MCPError(f"cannot resolve the MCP budget: {exc}") from exc


def check_budget(root: Path, name: str, tools: int, *,
                 profile: Optional[str] = None,
                 adopting: bool = False) -> Optional[str]:
    """The named refusal for adding ``name``, or None. Numbers always quoted.

    ``adopting=True`` means ``name`` is already in `.mcp.json` and this call only
    records the tool count it is already contributing. That adds no server and
    no schema, so it is not charged +1 server and its own missing count is not
    the "unknown" that blocks evaluation -- and the string returned in that mode
    is a **warning**, not a refusal (see :func:`add_server`): refusing to record
    a cost already being paid is what made this state inescapable.
    """
    profile_name, max_servers, max_tools = budget(root, profile)
    ledger = load_ledger(root)
    config = load_config(root)
    # Count the UNION. `.mcp.json` is Claude Code's file and users edit it by
    # hand; counting only our ledger would let three hand-added servers count as
    # zero and admit three more -- a budget that fails OPEN, which is the exact
    # silent pass this phase exists to remove.
    registered = set(ledger.get("servers", {})) | set(config.get("mcpServers", {}))
    current_servers = len(registered)
    projected_servers = current_servers if adopting else current_servers + 1
    unbudgeted = sorted(
        set(config.get("mcpServers", {})) - set(ledger.get("servers", {})) - {name})
    current_tools = declared_tools(ledger)

    if max_servers is not None and projected_servers > max_servers:
        if adopting:
            return (
                f"MCP budget already exceeded: {current_servers} servers are "
                f"configured in {config_path(root)} and profile {profile_name!r} "
                f"allows max_servers={max_servers}. Adopting {name!r} records a cost "
                f"you are already paying, so it is allowed; remove a server from "
                f"{config_path(root)} to get back under budget."
            )
        return (
            f"MCP budget exceeded: adding {name!r} would be server "
            f"{projected_servers}, and profile {profile_name!r} allows "
            f"max_servers={max_servers} (current {current_servers}). "
            f"Remove a server, raise the budget in "
            f".claude/profiles/{profile_name}/profile.json, or — often the right "
            f"answer — write a project-local CLI instead (see .ai/RESEARCH.md)."
        )
    if max_tools is not None and unbudgeted:
        # Their schemas are in every session, but we do not know how many tools
        # they carry, so the projected total is unknown. Refuse with the cause
        # named rather than treating unknown as zero -- and name a remedy that
        # actually works: `ck mcp add <that name> --tools N` ADOPTS a server
        # already in `.mcp.json` instead of trying to add a second copy.
        return (
            f"MCP budget cannot be evaluated: {', '.join(repr(n) for n in unbudgeted)} "
            f"{'is' if len(unbudgeted) == 1 else 'are'} in {config_path(root)} with no "
            f"tool count in {ledger_path(root)}, so the projected total against "
            f"max_tools={max_tools} is unknown. Record the count with "
            f"`ck mcp add <that server> --tools N` — for a server already in "
            f"{config_path(root)} that adopts the existing entry and changes no "
            f"configuration — or delete the server from {config_path(root)}."
        )
    if max_tools is not None and current_tools + tools > max_tools:
        if adopting:
            return (
                f"MCP budget already exceeded: adopting {name!r} records the {tools} "
                f"tools it already contributes, taking the total to "
                f"{current_tools + tools} against profile {profile_name!r}'s "
                f"max_tools={max_tools} — {current_tools + tools - max_tools} over. "
                f"Recorded anyway, because those schemas are already in every "
                f"session; remove a server from {config_path(root)} to get back under "
                f"budget. The next server you try to add will be refused."
            )
        return (
            f"MCP budget exceeded: {name!r} advertises {tools} tools, current total is "
            f"{current_tools}, projected {current_tools + tools}, and profile "
            f"{profile_name!r} allows max_tools={max_tools} — "
            f"{current_tools + tools - max_tools} over. Every tool schema is injected "
            f"into every session, so this is an always-on cost, not a per-use one."
        )
    return None


def add_server(root: Path, name: str, command: Sequence[str], *,
               tools: Optional[int] = None,
               profile: Optional[str] = None) -> Dict[str, Any]:
    """Register ``name`` against the active profile's MCP budget, or raise.

    Order is load-bearing: validate, resolve the tool count, check the budget,
    and only then write. Nothing is written by a call that refuses.

    Adoption -- why this verb has two modes
    ---------------------------------------
    `.mcp.json` is Claude Code's own file and `claude mcp add` is its primary
    writer, so a configured server with no ledger row is a normal state, not an
    error. Under a profile that declares ``max_tools`` that state refuses every
    subsequent `ck mcp add` (the projected total is genuinely unknown, and
    failing closed there is correct). The first draft then refused the very
    remedy it printed -- "already registered" -- which left hand-editing the
    ledger as the only exit: exactly the drift this phase abolishes.

    So a call naming a server that is in `.mcp.json` but not in the ledger
    **adopts** it: it writes the ledger row and touches no configuration. That
    adds no server and no tool schema -- it records a cost already being paid --
    so the budget cannot refuse it; an over-budget result is reported as a
    warning carrying the numbers, and the next genuine addition is refused
    normally. No new verb, so the public surface does not grow.
    """
    root = Path(root)
    if not NAME_RE.fullmatch(name or ""):
        raise MCPError(f"invalid server name {name!r}: expected [A-Za-z0-9][A-Za-z0-9_-]*")

    config = load_config(root)
    ledger = load_ledger(root)
    if name in ledger["servers"]:
        raise MCPError(
            f"server {name!r} is already registered in {ledger_path(root)} with a "
            f"recorded tool count; there is nothing to add. Correct the count there, "
            f"or remove the server from {config_path(root)} and that row together."
        )
    adopting = name in config["mcpServers"]

    argv = list(command)
    if adopting:
        existing = config["mcpServers"][name]
        # Typed explicitly and coerced with str(): `.get()` on a hand-written
        # `.mcp.json` is Any, and mypy (py3.9 target) rejected the untyped form as
        # `Union[list[Optional[Any]], list[str]]` assigned into `list[str]` below.
        config_argv: List[str] = ([str(existing.get("command"))]
                                  + [str(a) for a in (existing.get("args") or [])]
                                  if isinstance(existing, dict) and existing.get("command")
                                  else [])
        if argv and config_argv and argv != config_argv:
            raise MCPError(
                f"server {name!r} is already in {config_path(root)} as "
                f"{config_argv!r}; adopting it records the tool count and changes no "
                f"configuration. Re-run without a `--` command, or fix the entry in "
                f"{config_path(root)} first."
            )
        argv = config_argv or argv
    elif not argv:
        raise MCPError("a server needs a command to run")

    if tools is None:
        raise MCPError(
            "tool count is required: pass --tools N, taken from the server's "
            "documentation. There is no default, because assuming zero would make "
            "the max_tools budget pass for free."
        )
    if tools < 0:
        raise MCPError(f"--tools must be non-negative, got {tools}")

    verdict = check_budget(root, name, tools, profile=profile, adopting=adopting)
    if verdict and not adopting:
        raise MCPError(verdict)

    source = "adopted" if adopting else "declared"
    ledger["servers"][name] = {
        "tools": tools,
        "source": source,
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "command": argv,
    }
    ledger_path(root).parent.mkdir(parents=True, exist_ok=True)
    if adopting:
        # Ledger only. The config entry is Claude Code's and is already correct;
        # rewriting it would be this tool editing a file it does not own.
        _write_json(ledger_path(root), ledger)
        return {"name": name, "tools": tools, "source": source,
                "entry": config["mcpServers"][name], "warning": verdict}

    entry = {"command": argv[0], "args": argv[1:]}
    config["mcpServers"][name] = entry
    # Two files, no transaction across them. The ledger is written first, so a
    # hard kill in between leaves a ledger row with no `.mcp.json` entry: the
    # budget then OVER-counts (refuses one server too early) and `ck mcp list`
    # shows the row. That direction is safe; the reverse would fail open. Not
    # atomic -- disclosed, not claimed away.
    _write_json(ledger_path(root), ledger)
    try:
        _write_json(config_path(root), config)
    except Exception:
        del ledger["servers"][name]
        _write_json(ledger_path(root), ledger)
        raise
    return {"name": name, "tools": tools, "source": source, "entry": entry,
            "warning": None}


def list_servers(root: Path, profile: Optional[str] = None) -> Dict[str, Any]:
    """Servers as the *enforcer* sees them: the union of the ledger and `.mcp.json`.

    Listing only our ledger hid config-only servers that :func:`check_budget`
    counts, so the user's view disagreed with the enforcer and its refusals
    looked arbitrary. Config-only rows are shown with an unknown tool count,
    which is precisely why ``max_tools`` cannot be evaluated while they exist.

    Note what the returned numbers can say, honestly: this budget binds on
    **deltas only**. `.mcp.json` is Claude Code's file and adoption records a
    cost already being paid, so ``len(servers)`` may legitimately exceed
    ``max_servers`` and ``total_tools`` exceed ``max_tools`` with nothing
    refusing anything -- only the next *addition* is refused. `cmd_mcp`'s list
    branch says so out loud rather than printing the numbers and leaving the
    reader to assume a standing overage is impossible.
    """
    profile_name, max_servers, max_tools = budget(root, profile)
    ledger = load_ledger(root)
    config = load_config(root)
    rows: Dict[str, Any] = {}
    for server, row in ledger.get("servers", {}).items():
        rows[server] = {"tools": row.get("tools") if isinstance(row, dict) else None,
                        "source": (row.get("source", "declared")
                                   if isinstance(row, dict) else "declared")}
    for server in config.get("mcpServers", {}):
        rows.setdefault(server, {"tools": None, "source": "config-only"})
    return {
        "profile": profile_name,
        "max_servers": max_servers,
        "max_tools": max_tools,
        "servers": rows,
        "total_tools": declared_tools(ledger),
        "unknown": sorted(s for s, row in rows.items() if row["tools"] is None),
    }


def _write_json(path: Path, doc: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

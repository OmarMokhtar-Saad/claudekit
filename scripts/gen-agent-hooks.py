#!/usr/bin/env python3
"""Generate Codex and Cursor hook configs from .claude/hooks/dispatch-registry.json.

The registry is the single source of truth for which hook runs on which event. This
script derives the other two tools' configs from it, so they cannot drift from it by hand:

    codex   -> hooks.json   {"hooks": {Event: [{"matcher", "hooks": [{"type": "command", ...}]}]}}
    cursor  -> hooks.json   {"version": 1, "hooks": {cursorEvent: [{"command": ...}]}}

Usage:
    python3 scripts/gen-agent-hooks.py                     # both configs on stdout, as one JSON object
    python3 scripts/gen-agent-hooks.py --target codex      # one config on stdout
    python3 scripts/gen-agent-hooks.py --out DIR           # write DIR/.codex/hooks.json, DIR/.cursor/hooks.json
    python3 scripts/gen-agent-hooks.py --check DIR         # exit 1 when those files differ from the registry
    python3 scripts/gen-agent-hooks.py --skipped           # list rows a target cannot express, with the reason

Nothing is written unless --out is given, and the repo does not commit the outputs: a
committed `.codex/` or `.cursor/` would switch hooks on for every contributor's tool. Each
hook command resolves the project root with git, then runs the same file the registry names,
so the hook scripts are shared, not copied.

Mapping limits (honest, not hidden; see --skipped):
  * Codex has no PreCompact, SubagentStop or PostToolUseFailure event: those rows are skipped.
  * Cursor has only beforeShellExecution (Bash), beforeReadFile (Read), afterFileEdit
    (Edit/Write/MultiEdit/NotebookEdit), beforeSubmitPrompt and stop. A row maps to every one
    of those whose tool names its matcher matches; everything else is skipped.
  * Hook payloads differ between hosts; hooks that read `tool_input` see what the host sends.
    Registry tiers (blocking/advisory) are not expressed: each host decides on exit codes.
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / ".claude" / "hooks" / "dispatch-registry.json"

CODEX_EVENTS = ("PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit", "Stop")

# (registry event, cursor event, tool names the cursor event covers; None = no tool)
CURSOR_EVENTS = (
    ("PreToolUse", "beforeShellExecution", ("Bash",)),
    ("PreToolUse", "beforeReadFile", ("Read",)),
    ("PostToolUse", "afterFileEdit", ("Edit", "Write", "MultiEdit", "NotebookEdit")),
    ("UserPromptSubmit", "beforeSubmitPrompt", None),
    ("Stop", "stop", None),
)

OUT_FILES = {"codex": Path(".codex") / "hooks.json", "cursor": Path(".cursor") / "hooks.json"}


def load_registry(path: Path = REGISTRY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def command(row: dict) -> str:
    """One shell command: resolve the project root with git, run the registry's file."""
    parts = [row["runner"], '"$ROOT/.claude/hooks/%s"' % row["file"]]
    parts += [shlex.quote(a) for a in row.get("args") or []]
    inner = 'ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"; ' + " ".join(parts)
    return "bash -c " + shlex.quote(inner)


def _matches(pattern: str, name: str) -> bool:
    return not pattern or re.fullmatch(pattern, name) is not None


def codex_config(registry: dict) -> dict:
    hooks: dict = {}
    for event in CODEX_EVENTS:
        for row in registry["events"].get(event, []):
            hooks.setdefault(event, []).append({
                "matcher": row.get("matcher", ""),
                "hooks": [{"type": "command", "command": command(row)}],
            })
    return {"hooks": hooks}


def cursor_config(registry: dict) -> dict:
    hooks: dict = {}
    for reg_event, cursor_event, tools in CURSOR_EVENTS:
        for row in registry["events"].get(reg_event, []):
            pattern = row.get("matcher", "")
            if tools is None or any(_matches(pattern, t) for t in tools):
                hooks.setdefault(cursor_event, []).append({"command": command(row)})
    return {"version": 1, "hooks": hooks}


def skipped(registry: dict) -> dict:
    """{target: [(event, hook id, reason)]} for rows a target cannot express."""
    out = {"codex": [], "cursor": []}
    for event, rows in registry["events"].items():
        for row in rows:
            if event not in CODEX_EVENTS:
                out["codex"].append((event, row["id"], "Codex has no %s event" % event))
            covered = [(re_, ce, tools) for re_, ce, tools in CURSOR_EVENTS if re_ == event]
            if not covered:
                out["cursor"].append((event, row["id"], "Cursor has no %s event" % event))
                continue
            pattern = row.get("matcher", "")
            if not any(tools is None or any(_matches(pattern, t) for t in tools)
                       for _, _, tools in covered):
                out["cursor"].append((event, row["id"],
                                      "matcher %r covers no tool Cursor exposes on this event" % pattern))
    return out


def render(registry: dict, target: str) -> str:
    return json.dumps(codex_config(registry) if target == "codex" else cursor_config(registry), indent=2) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", choices=("codex", "cursor", "all"), default="all")
    ap.add_argument("--registry", default=str(REGISTRY))
    ap.add_argument("--out", help="write the config files under this directory")
    ap.add_argument("--check", metavar="DIR", help="exit 1 when files under DIR differ from the registry")
    ap.add_argument("--skipped", action="store_true", help="list rows each target cannot express")
    args = ap.parse_args(argv)
    try:
        registry = load_registry(Path(args.registry))
        registry["events"].items()
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        sys.stderr.write("FAIL: cannot read dispatch registry (%s)\n" % exc)
        return 1
    targets = ("codex", "cursor") if args.target == "all" else (args.target,)

    if args.skipped:
        info = skipped(registry)
        for t in targets:
            for event, hid, why in info[t]:
                sys.stdout.write("%s: skip %s/%s: %s\n" % (t, event, hid, why))
        return 0
    if args.check:
        bad = 0
        for t in targets:
            path = Path(args.check) / OUT_FILES[t]
            try:
                current = path.read_text(encoding="utf-8")
            except OSError:
                current = None
            if current != render(registry, t):
                sys.stdout.write("DRIFT: %s is %s; run --out\n" % (path, "missing" if current is None else "stale"))
                bad = 1
        if not bad:
            sys.stdout.write("OK: generated hook configs match the registry\n")
        return bad
    if args.out:
        for t in targets:
            path = Path(args.out) / OUT_FILES[t]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(registry, t), encoding="utf-8")
            sys.stdout.write("wrote %s\n" % path)
        return 0
    if len(targets) == 1:
        sys.stdout.write(render(registry, targets[0]))
    else:
        sys.stdout.write(json.dumps({t: json.loads(render(registry, t)) for t in targets}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""session-model.py - SessionStart (ledger): record which model this session runs on.

delegate-nudge.py enforces delegation only on the top two capability tiers, so it has to know
the session model before the transcript does. Claude Code's SessionStart payload carries no
model, and a headless session writes no assistant line until its first tool call is under
way (both probed on 2.1.280). So the model is resolved here, in order:

  1. `--model X` / `--model=X` on the claude process (`CLAUDE_PID`, read with `ps`);
  2. ANTHROPIC_MODEL;
  3. `"model"` in .claude/settings.local.json, .claude/settings.json, ~/.claude/settings.json.

and written to .claude/runtime/session-model/<session>.json as {"model", "source"}. No
answer writes {"model": null}: the nudge then stays advisory. A later /model switch is
picked up by the nudge from the transcript itself.

Ledger tier: exit 0 always, nothing on stdout or stderr. stdlib only, py3.9.
"""

import json
import os
import subprocess
import sys


def _from_argv(pid):
    if not str(pid or "").isdigit():
        return None
    try:
        args = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True,
                              text=True, timeout=5).stdout.split()
    except Exception:
        return None
    for i, arg in enumerate(args):
        if arg == "--model" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--model="):
            return arg.split("=", 1)[1] or None
    return None


def _from_settings(root):
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    for path in (os.path.join(root, ".claude", "settings.local.json"),
                 os.path.join(root, ".claude", "settings.json"),
                 os.path.join(home, "settings.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                model = json.load(fh).get("model")
        except Exception:
            continue
        if isinstance(model, str) and model:
            return model
    return None


def resolve(root):
    model = _from_argv(os.environ.get("CLAUDE_PID"))
    if model:
        return model, "argv"
    if os.environ.get("ANTHROPIC_MODEL"):
        return os.environ["ANTHROPIC_MODEL"], "env"
    model = _from_settings(root)
    return (model, "settings") if model else (None, "unknown")


def ledger_path(root, session_id):
    safe = "".join(ch for ch in str(session_id or "") if ch.isalnum() or ch in "-_")[:64]
    return os.path.join(root, ".claude", "runtime", "session-model", (safe or "unknown") + ".json")


def main():
    try:
        payload = json.load(sys.stdin)
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        model, source = resolve(root)
        path = ledger_path(root, payload.get("session_id"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"model": model, "source": source}, fh)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

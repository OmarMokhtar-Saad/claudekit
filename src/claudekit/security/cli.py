"""Command-line entry points for the security validators.

Exposed two ways:
  * ``claudekit check-command "<cmd>"`` / ``claudekit check-path <path>``
    (via ``claudekit.cli.main``), and
  * ``python3 -m claudekit.security check-command "<cmd>"`` (via ``__main__``),
    which the ``command-guard`` hook uses when the ``claudekit`` console script
    is not on PATH.

Exit codes: 0 = allowed, 2 = blocked (reason written to stderr).
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from .command_validator import CommandValidator
from .path_guard import PathGuard


def _project_config() -> Optional[Path]:
    """Locate the project's ``.claude/hooks/config.json``.

    Claude Code runs hooks with cwd = the session's cwd, which is the directory
    the session was STARTED in, not the repo root. A cwd-relative lookup made
    the guard silently ignore the project's policy for any session opened in a
    subdirectory: measured 2026-09-19, one session lost 5 of 17 Bash turns to
    ``cd``/``sort``/``sed`` refusals that the project's own config allowed.
    Prefer the harness's ``CLAUDE_PROJECT_DIR``, then walk up from cwd.
    """
    roots = []
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        roots.append(Path(env_root))
    cwd = Path.cwd()
    roots.extend([cwd, *cwd.parents])
    for root in roots:
        cfg = root / ".claude" / "hooks" / "config.json"
        if cfg.is_file():
            return cfg
    return None


def _validator_from_project() -> CommandValidator:
    """Build a validator, honoring a project's config.json security section."""
    cfg = _project_config()
    if cfg is not None:
        try:
            return CommandValidator.from_config(json.loads(cfg.read_text()))
        except (json.JSONDecodeError, OSError):
            pass  # fall back to defaults rather than crash the guard
    return CommandValidator(safe_mode=False)


def check_command(command: str) -> int:
    ok, reason = _validator_from_project().validate(command)
    if ok:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


def check_path(path: str) -> int:
    ok, reason = PathGuard().validate_path(path)
    if ok:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write("usage: check-command <cmd> | check-path <path>\n")
        return 2
    sub, rest = argv[0], argv[1:]
    if sub == "check-command":
        return check_command(rest[0] if rest else "")
    if sub == "check-path":
        return check_path(rest[0] if rest else "")
    sys.stderr.write(f"unknown subcommand: {sub}\n")
    return 2

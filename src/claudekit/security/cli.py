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
import sys
from pathlib import Path

from .command_validator import CommandValidator
from .path_guard import PathGuard


def _validator_from_project() -> CommandValidator:
    """Build a validator, honoring a project's config.json security section."""
    cfg = Path(".claude/hooks/config.json")
    if cfg.exists():
        try:
            return CommandValidator.from_config(json.loads(cfg.read_text()))
        except (json.JSONDecodeError, OSError):
            pass  # fall back to defaults rather than crash the guard
    return CommandValidator()


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

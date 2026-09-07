"""ClaudeKit — production-grade multi-agent orchestration for Claude Code."""

from ._version import resolve_version

# One precedence rule, in one place (_version.py): on a source checkout the tree's
# pyproject.toml wins, everywhere else installed metadata does. The literal that used
# to sit here was a hand-bumped version site and there is nothing left to bump.
__version__ = resolve_version()

__all__ = ["__version__"]

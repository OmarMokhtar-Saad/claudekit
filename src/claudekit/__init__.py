"""ClaudeKit — production-grade multi-agent orchestration for Claude Code."""

from importlib import metadata

try:
    __version__ = metadata.version("claude-kit")  # PyPI distribution name
except metadata.PackageNotFoundError:  # running from a source checkout, not installed
    __version__ = "2.1.0"

__all__ = ["__version__"]

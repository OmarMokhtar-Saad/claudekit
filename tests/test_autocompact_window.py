"""`.claude/settings.json` ships `autoCompactWindow: 200000`.

WHY: on a 1M-window model Claude Code's own auto-compact does not fire until ~1M tokens, and
every API turn re-sends the whole context. Measured over 227 qa-agents sessions (16,770 unique
requests, deduplicated by requestId): 85% of the 5.24B billed tokens were spent by turns whose
context was already above 200K, with 16 compactions in total. This one setting caps the context
a session reaches before Claude Code compacts it; `/autocompact` still overrides it per session,
which is why it is the SETTING and not `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (the env var takes
precedence over `/autocompact` and cannot be changed without unsetting it).

Claude Code 2.1.278 accepts 'auto' or 100k-1M tokens; the setting is stored as an integer.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _settings():
    return json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))


def test_auto_compact_window_is_shipped_at_two_hundred_k():
    value = _settings().get("autoCompactWindow")
    assert isinstance(value, int) and not isinstance(value, bool), (
        "autoCompactWindow must be an integer token count (Claude Code stores the parsed value)")
    assert 100_000 <= value <= 200_000, (
        "below 100K Claude Code refuses the value; above 200K the session pays the 1M-window "
        "rate on every turn - 85% of measured spend happened there")


def test_the_env_override_is_not_used():
    env = _settings().get("env") or {}
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in env, (
        "the env var takes precedence over /autocompact, so a tester could not raise the window "
        "for one long session; the setting keeps that door open")

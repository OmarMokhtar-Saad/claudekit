"""Coverage gate: every registered hook has at least one behavioral test.

A hook is *registered* when ``.claude/hooks/dispatch-registry.json`` lists it or a
``.claude/settings*.json`` / ``templates/**`` settings file points a command at it.
It is *covered* when a test module that executes processes (``subprocess`` or the
shared ``run_hook`` helper) names the hook's file. The check is a name-presence
heuristic on purpose: it catches a hook added with no test at all, not a weak test.

``UNCOVERED_BASELINE`` is a shrink-only ratchet: a hook listed there may be
uncovered, an unlisted uncovered hook fails by name, and a listed hook that is
now covered fails until it is removed from the baseline.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".claude" / "hooks"
TESTS = REPO / "tests"
HOOK_REF = re.compile(r"\.claude/hooks/([A-Za-z0-9_.-]+\.(?:sh|py))")

# Shrink-only. Empty: every registered hook is covered today.
UNCOVERED_BASELINE: set = set()


def registered_hooks():
    """Return {hook file name: where it is registered}."""
    found = {}
    registry = json.loads((HOOKS / "dispatch-registry.json").read_text())
    for event, handlers in registry["events"].items():
        for h in handlers:
            found.setdefault(h["file"], f"dispatch-registry.json:{event}:{h['id']}")
    settings = [REPO / ".claude" / "settings.json", *sorted((REPO / "templates").rglob("settings*.json"))]
    for path in settings:
        if path.is_file():
            for name in HOOK_REF.findall(path.read_text()):
                found.setdefault(name, str(path.relative_to(REPO)))
    return found


def behavioral_test_text():
    chunks = []
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(errors="replace")
        if "subprocess" in text or "run_hook" in text:
            chunks.append(text)
    return "\n".join(chunks)


def uncovered_hooks(registered=None):
    corpus = behavioral_test_text()
    return {name for name in (registered or registered_hooks()) if name not in corpus}


def test_registered_hook_files_exist():
    missing = sorted(n for n in registered_hooks() if not (HOOKS / n).is_file())
    assert not missing, f"registered hooks with no file in .claude/hooks/: {missing}"


def test_every_registered_hook_has_a_behavioral_test():
    where = registered_hooks()
    new = sorted(uncovered_hooks(where) - UNCOVERED_BASELINE)
    assert not new, "hooks with no behavioral payload test: " + ", ".join(f"{n} ({where[n]})" for n in new)


def test_baseline_only_shrinks():
    stale = sorted(UNCOVERED_BASELINE - uncovered_hooks())
    assert not stale, f"now covered, remove from UNCOVERED_BASELINE: {stale}"


def test_gate_detects_an_uncovered_hook():
    fake = {**registered_hooks(), "no-such-hook-xyz.sh": "fake"}
    assert "no-such-hook-xyz.sh" in uncovered_hooks(fake)

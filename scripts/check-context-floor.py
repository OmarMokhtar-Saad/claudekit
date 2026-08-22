#!/usr/bin/env python3
"""Always-on context floor gate.

Measures the text that is injected into EVERY session's context window before
any work happens: agent frontmatter descriptions, skill descriptions, command
descriptions, and CLAUDE.md. Exits 1 whenever the floor exceeds budget, on ANY
invocation — same drift-gate pattern as gen-docs.py --check, except that this
gate's exit code never depended on being asked nicely.

Usage:
    python3 scripts/check-context-floor.py            # table; exit 1 if over budget
    python3 scripts/check-context-floor.py --check    # accepted for gate symmetry; ignored
    python3 scripts/check-context-floor.py --json     # JSON instead of the table

Budgets are chars (tokens ~ chars/4). Raise a budget only with owner sign-off —
the point of this gate is that the floor never silently grows back.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_HERE = Path(__file__).resolve().parent

# ONE measurement, two callers. `ck skill new` refuses a skill that would breach
# this floor, and it has to refuse on the same number CI gates on -- so the
# measurement moved into src/claudekit/context_floor.py and this script became a
# CLI over it. A second copy here would drift from that one the first time
# either changed, and a floor gate that disagrees with the generator enforcing
# it is worse than either alone.


def _load_context_floor():
    """Import the one measurement, deterministically and from THIS tree only.

    Two candidates, in order: the package source under this checkout, then a
    copy sitting beside this script (that is how tests/test_context_floor.py
    plants the gate in an isolated temp tree). We deliberately never fall
    through to `import claudekit`: under CI's editable install that would
    silently resolve a temp-tree copy back to the real repo, destroying the
    isolation those tests exist for -- invisibly, with everything still green.
    Missing module is a named, fail-closed error, not a fallback.
    """
    for candidate in (ROOT / "src" / "claudekit" / "context_floor.py",
                      _HERE / "context_floor.py"):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("_ck_context_floor", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    sys.exit(
        "FAIL: cannot locate context_floor.py (looked in src/claudekit/ and beside "
        "this script). The floor gate refuses to guess."
    )


_cf = _load_context_floor()

# Re-exported because callers load THIS file as a module by path and use them
# (tests/test_skill_loading_contract.py calls module.frontmatter /
# module.model_invisible / module.measure).
BUDGETS = _cf.BUDGETS
CLAUDE_MD_MULTIPLIER = _cf.CLAUDE_MD_MULTIPLIER
PIPELINE_AGENTS = _cf.PIPELINE_AGENTS
frontmatter = _cf.frontmatter
model_invisible = _cf.model_invisible
description_span = _cf.description_span


def measure() -> "dict[str, int]":
    """The floor under this checkout. Kept zero-arg: callers import this module
    by path and call `measure()` with no arguments."""
    return _cf.measure(ROOT)


def main() -> int:
    args = sys.argv[1:]
    # `--check` is accepted for symmetry with the other generator gates and is
    # otherwise IGNORED. It used to gate the exit code -- `return 1 if check else 0`
    # -- so the bare invocation printed `FAIL: context floor over budget` and then
    # exited 0. CLAUDE.md's command block prescribes the bare form, so the
    # documented way to run this gate was the one way it could not fail. A gate
    # that reports failure and returns success is the class this repo ratchets
    # against, so the exit code now follows the measurement, never the flag.
    sizes = measure()
    total = sum(sizes.values())
    budget_total = sum(BUDGETS.values())

    if "--json" in args:
        ok = all(size <= BUDGETS[name] for name, size in sizes.items())
        payload = {"sizes": sizes, "budgets": BUDGETS, "total": total, "ok": ok}
        print(json.dumps(payload, indent=2))
        return 0 if ok else 1

    print("Always-on context floor (chars; tokens ~ chars/4)")
    print(f"{'source':<24}{'chars':>8}{'budget':>8}  status")
    failures = []
    for name, size in sizes.items():
        budget = BUDGETS[name]
        ok = size <= budget
        if not ok:
            failures.append(name)
        print(f"{name:<24}{size:>8}{budget:>8}  {'OK' if ok else 'OVER'}")
    print(f"{'TOTAL':<24}{total:>8}{budget_total:>8}  (~{total // 4} tokens)")

    if failures:
        print(
            f"\nFAIL: context floor over budget: {', '.join(failures)}.\n"
            "Trim descriptions (no <example> blocks in frontmatter) or get owner\n"
            "sign-off to raise the budget in scripts/check-context-floor.py.",
            file=sys.stderr,
        )
        return 1
    print("\nOK: context floor within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

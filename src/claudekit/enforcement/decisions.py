"""Hook decision codec and the most-restrictive-wins merge rule.

The gap this closes
-------------------
``.claude/settings.json`` registers 26 hook entries across 8 events. On the
``PreToolUse``/``Bash`` matcher alone, six hooks fire on one event, and nothing
anywhere defined what happens when two of them decide differently. The answer was
"whatever registration order happens to be", which is not a decision anybody made.

Worse, the exit-code contract was partial. Claude Code honours ``exit 2`` + stderr
as a block and treats every other non-zero exit as a *non-blocking error*. So a
hook that crashes fails **open**. Re-measured at ``5f3e322`` in a clean
environment, so the shell's interpreter lookup cannot be mistaken for the hook::

    $ echo '' | env -i PATH=/nonexistent /bin/bash .claude/hooks/ops-enforcement.sh; echo $?
    0

**0** — and 0 is ALLOW. Every helper the guard needs (``dirname``, ``cat``, even
``deny`` from ``lib.sh``) is command-not-found, so it emits nothing and exits
successfully. That is the exact opposite of the "fail closed" rule in CLAUDE.md
hard rule 2, and it is *worse* than the 127 an earlier measurement reported: that
127 was the interpreter lookup failing, i.e. the hook had not run at all.

The limit of this codec, stated rather than glossed: it maps an **observed** exit
code, so it cannot rescue a handler that degrades to **0** on its own. What it
does fix is every failure the dispatcher can see — a handler that cannot start
(``bash``/``python3`` unresolvable -> 127), crashes, or is killed by a signal. The
hook-level "degrades to 0" shape is filed in ``.ai/BACKLOG.md``, not papered over
here.

The rule, stated once
---------------------
Four decisions, totally ordered by restrictiveness::

    ALLOW (0)  <  ADVISE (1)  <  ERROR (2)  <  DENY (3)

* ``from_exit_code`` maps 0 -> ALLOW, 2 -> DENY, **everything else -> ERROR**.
* ``ERROR`` is *not* a third outcome at the boundary: ``to_exit_code`` renders it
  as 2. A handler that crashed is a handler whose verdict is unknown, and an
  unknown verdict on a guarded event is a block. The distinction is preserved
  inside the event log (so "blocked you" and "broke, so blocked you" are
  diagnosable) and collapsed at the process boundary.
* ``merge`` returns the **maximum** severity. Order-independent by construction:
  ``max`` is commutative and associative, so no registration order can change it.
* ``clamp_advisory`` caps a handler declared ``advisory`` at ``ADVISE`` — applied
  **before** merge. Two consequences, both intended: advisory output can never
  override a block, and a flaky advisory handler can never *create* one.

The shell mirror
----------------
``.claude/hooks/lib.sh`` carries the same table in bash-3.2 arithmetic, because
the dispatcher must merge without depending on a Python import succeeding.
``tests/test_dispatch_merge.py`` drives both and asserts they agree on every
input; a table that drifts fails the suite, the same drift-gate pattern
``profiles.scan_hook_guards`` already uses.
"""
from __future__ import annotations

from typing import Iterable, Tuple

__all__ = [
    "Decision", "DecisionError", "ALLOW", "ADVISE", "ERROR", "DENY",
    "from_exit_code", "to_exit_code", "merge", "clamp_advisory", "name_of",
]


class DecisionError(Exception):
    """A decision could not be decoded. The message names the cause."""


class Decision(int):
    """A hook verdict, ordered by restrictiveness. ``int`` so ``max`` just works."""

    __slots__ = ()

    @property
    def label(self) -> str:
        return _LABELS[int(self)]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "Decision.%s" % self.label


ALLOW = Decision(0)
ADVISE = Decision(1)
ERROR = Decision(2)
DENY = Decision(3)

_LABELS = {0: "ALLOW", 1: "ADVISE", 2: "ERROR", 3: "DENY"}

#: Severity order, least to most restrictive. Exposed so tests and docs cite one list.
ORDER: Tuple[Decision, ...] = (ALLOW, ADVISE, ERROR, DENY)

#: Exit codes the boundary may emit. ERROR and DENY both render as 2 (fail closed).
_EXIT_OF = {0: 0, 1: 0, 2: 2, 3: 2}


def name_of(decision: int) -> str:
    """Label for a decision value, for logs and assertion messages."""
    try:
        return _LABELS[int(decision)]
    except KeyError:
        raise DecisionError("not a decision value: %r" % (decision,)) from None


def from_exit_code(code: int) -> Decision:
    """Decode a handler's process exit code.

    0 -> ALLOW, 2 -> DENY, anything else -> ERROR. There is no permissive branch:
    an exit code we do not recognise is a handler we cannot trust, and an
    untrusted handler does not get to say "allow". This is the whole fix for the
    exit-127-fails-open defect.
    """
    if not isinstance(code, int) or isinstance(code, bool):
        raise DecisionError("exit code must be an int, got %r" % (code,))
    if code == 0:
        return ALLOW
    if code == 2:
        return DENY
    return ERROR


def to_exit_code(decision: int) -> int:
    """Render a decision at the process boundary. ERROR and DENY both give 2."""
    try:
        return _EXIT_OF[int(decision)]
    except KeyError:
        raise DecisionError("not a decision value: %r" % (decision,)) from None


def clamp_advisory(decision: int, tier: str) -> Decision:
    """Cap an ``advisory``-tier handler's verdict at ADVISE.

    Exactly one tier string clamps: ``"advisory"``. **Every other value —
    ``"blocking"`` (what dispatch-registry.json actually writes), ``"on"`` (what
    ``profile.json`` writes), the empty string, and a typo — passes through
    unclamped.** That asymmetry is the fail-closed direction and is deliberate:
    clamping means "this handler may not block", so treating an unrecognised tier
    as advisory would silently *disarm* a guard whose tier was misspelled. An
    unrecognised tier instead keeps the handler's verdict, and
    ``test_blocking_tier_is_honest`` plus the registry schema catch the typo.

    This mirrors ``ck_clamp_advisory`` in ``.claude/hooks/lib.sh`` exactly — the
    shell is the implementation that actually runs, so the Python side matches it
    rather than the other way round. An earlier draft raised on any tier outside
    ``("on", "advisory")``, which would have raised on ``"blocking"``, the only
    value the shipped registry uses; the parity test's tier parametrisation now
    covers ``blocking``/``advisory``/``""``/``bogus`` so that divergence cannot
    return.
    """
    value = Decision(int(decision))
    if int(value) not in _LABELS:
        raise DecisionError("not a decision value: %r" % (decision,))
    if tier == "advisory" and value > ADVISE:
        return ADVISE
    return value


def merge(decisions: Iterable[int]) -> Decision:
    """Most restrictive wins. Empty input is ALLOW (no handler objected)."""
    worst = ALLOW
    for item in decisions:
        value = Decision(int(item))
        if int(value) not in _LABELS:
            raise DecisionError("not a decision value: %r" % (item,))
        if value > worst:
            worst = value
    return worst

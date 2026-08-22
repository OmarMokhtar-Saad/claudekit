"""Enforcement runtime — the layer that *decides*, as opposed to the layer that advises.

Three concerns live here, deliberately separated so a future policy change edits
policy and not measurement:

``decisions``
    The exit-code <-> decision codec and the **most-restrictive-wins** merge rule.
    Before this module, ~20 hooks fired on shared events with no defined resolution
    when two of them decided differently: the outcome depended on a registration
    order nobody chose, and a hook that *broke* failed **open**. Re-measured at
    ``5f3e322`` in a clean environment, so the shell's own interpreter lookup
    cannot be mistaken for the hook's exit code::

        $ echo '' | env -i PATH=/nonexistent /bin/bash .claude/hooks/ops-enforcement.sh
        .claude/hooks/ops-enforcement.sh: line 20: deny: command not found
        $ echo $?
        0

    **0**, not a crash code: with no ``dirname``, no ``cat`` and no ``lib.sh``
    helpers, every statement fails and the script still ends successfully, so the
    guard returns the one code Claude Code reads as "allow". An earlier
    ``PATH=/nonexistent bash ...`` measurement reported 127 — that was the
    *interpreter* not being found, and the hook never ran at all.

``eventlog``
    A durable, typed, append-only JSONL stream. Invariant: **model-visible means
    logged** — anything that reaches a model request must be reconstructable from
    the stream. ``.claude/hooks/hooks.log`` (prose, ~2.5 MB) keeps working
    untouched; this is a second, structured stream, not a migration.

``spill``
    Oversized output persists to a session-scoped file and is replaced inline by a
    bounded preview plus a retrieval locator, and a **model-free** pruner drops
    stale records *before* any paid summarization.

What this is NOT
----------------
Not a harness. No model client, no agent loop, no session runtime, no sandbox.
Nothing here calls a model; ``prune`` is deterministic arithmetic by construction.

One re-export is deliberately absent
------------------------------------
The ``spill`` *function* is not re-exported from this package. Re-exporting it
would shadow the ``claudekit.enforcement.spill`` *module* for anyone writing
``from claudekit.enforcement import spill`` — a silent footgun that cost a whole
test file's worth of confusing ``AttributeError``s the first time it was written.
Import it explicitly: ``from claudekit.enforcement.spill import spill``.
"""
from __future__ import annotations

from .decisions import (
    ADVISE,
    ALLOW,
    DENY,
    ERROR,
    Decision,
    DecisionError,
    clamp_advisory,
    from_exit_code,
    merge,
    to_exit_code,
)
from .eventlog import (
    SCHEMA_VERSION,
    EventLogError,
    append,
    assert_model_visible_logged,
    read,
    replay,
    required_fields,
)
from .spill import (
    SpillError,
    prune,
    retrieve,
)

__all__ = [
    "ALLOW", "ADVISE", "DENY", "ERROR", "Decision", "DecisionError",
    "from_exit_code", "to_exit_code", "merge", "clamp_advisory",
    "SCHEMA_VERSION", "EventLogError", "append", "read", "replay",
    "required_fields", "assert_model_visible_logged",
    "SpillError", "retrieve", "prune",
]

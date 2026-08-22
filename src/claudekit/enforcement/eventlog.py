"""Durable typed event log — "model-visible means logged".

The invariant
-------------
Anything that reaches a model request must be reconstructable from a structured,
append-only stream. Not *summarizable* — reconstructable, field by field.

Why prose is not enough. ``.claude/hooks/hooks.log`` is ~2.5 MB of
``[ts] [name] [LEVEL] message``. You cannot diff a run against a golden record
when the record is prose, which is precisely what the eval framework (task 010)
needs and why it is blocked on this file. That log is **not** migrated or
truncated here: existing debugging workflows (``.ai/DEBUGGING_GUIDE.md`` starts at
``hooks.log``) keep working unchanged. This is a second, structured stream.

Shape
-----
One JSON object per line, UTF-8, ``\\n``-terminated, opened ``O_APPEND`` so
concurrent hook processes interleave whole lines rather than corrupting each
other. Every record carries ``schema_version``, ``ts``, ``session_id``, ``kind``,
plus the fields required for its kind.

Two kinds ship in v1, matching the two things that currently reach a model
without a record: hook decisions and ops.json execution.

The runtime assertion
---------------------
:func:`assert_model_visible_logged` is the invariant as executable code: given a
payload that is about to become model-visible, it fails unless a matching event
exists carrying every required field. ``tests/test_event_log.py`` proves it binds
by deleting a field from a record the shipped emitter produced and reading the
failure — a schema that accepts a mutant is worse than no schema.

Failure policy
--------------
Writing is best-effort at the *call site* (a full disk must not brick a session)
but never silently lossy at the *contract*: :func:`append` raises
:class:`EventLogError` on a malformed record, and the dispatcher's shell shim
decides separately whether to swallow an I/O failure. Validation and durability
are different questions and are answered in different places on purpose.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

__all__ = [
    "SCHEMA_VERSION", "KINDS", "EventLogError", "required_fields",
    "new_event", "append", "read", "replay", "assert_model_visible_logged",
    "default_log_path",
]

SCHEMA_VERSION = 1

#: Fields every record carries, regardless of kind.
COMMON_FIELDS: Tuple[str, ...] = ("schema_version", "ts", "session_id", "kind")

#: Per-kind required fields. Adding a kind means adding a row here; a record whose
#: kind is not in this table is rejected, so the log cannot grow untyped rows.
KIND_FIELDS: Dict[str, Tuple[str, ...]] = {
    # One handler's verdict on one event, plus the merged outcome of the dispatch.
    "hook_decision": (
        "event", "handler", "tier", "exit_code", "decision", "merged_decision",
        "tool_name", "duration_ms", "stderr_preview",
    ),
    # One ops.json execution, as the operations engine applied it.
    "ops_execution": (
        "plan", "config_path", "operation_index", "operation_type", "target_path",
        "status", "duration_ms", "detail_preview",
    ),
}

KINDS: Tuple[str, ...] = tuple(sorted(KIND_FIELDS))


class EventLogError(Exception):
    """A record was malformed, or the invariant was violated. Message names which."""


def required_fields(kind: str) -> Tuple[str, ...]:
    """Full required field tuple for ``kind`` (common fields first)."""
    try:
        specific = KIND_FIELDS[kind]
    except KeyError:
        raise EventLogError(
            "unknown event kind %r (known: %s)" % (kind, ", ".join(KINDS))) from None
    return COMMON_FIELDS + specific


def default_log_path(root: str, session_id: str) -> str:
    """Session-scoped stream under ``.claude/runtime/events/``.

    Session-scoped rather than one global file so replay has a natural unit and a
    long-lived project does not accumulate one unbounded record. ``.claude/runtime/``
    is gitignored: it is runtime state, and per CLAUDE.md's evidence-precedence rule
    runtime state is never a source artifact.
    """
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in str(session_id))
    if not safe:
        safe = "unknown"
    return os.path.join(root, ".claude", "runtime", "events", safe + ".jsonl")


def new_event(kind: str, session_id: str, **fields: Any) -> Dict[str, Any]:
    """Build a validated record. Raises rather than emitting an incomplete one."""
    record: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ts": fields.pop("ts", None) or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_id": str(session_id),
        "kind": kind,
    }
    record.update(fields)
    _validate(record)
    return record


def _validate(record: Any) -> None:
    if not isinstance(record, dict):
        raise EventLogError("record must be an object, got %s" % type(record).__name__)
    kind = record.get("kind")
    if not isinstance(kind, str):
        raise EventLogError("record has no string 'kind'")
    missing = [f for f in required_fields(kind) if f not in record]
    if missing:
        raise EventLogError(
            "kind %r is missing required field(s): %s" % (kind, ", ".join(sorted(missing))))
    version = record.get("schema_version")
    if version != SCHEMA_VERSION:
        raise EventLogError(
            "schema_version %r is not the supported version %d" % (version, SCHEMA_VERSION))


def append(path: str, record: Dict[str, Any]) -> None:
    """Validate and append one record as a single ``O_APPEND`` line write.

    Raises :class:`EventLogError` for a malformed record and :class:`OSError` for
    an I/O failure — two different problems, so two different exceptions.
    """
    _validate(record)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def read(path: str, strict: bool = True) -> List[Dict[str, Any]]:
    """Read every record. ``strict`` rejects a malformed line instead of skipping it.

    Skipping silently is how a log stops being evidence, so it is not the default.
    """
    out: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                _validate(record)
            except (ValueError, EventLogError) as exc:
                if strict:
                    raise EventLogError("%s:%d: %s" % (path, number, exc)) from None
                continue
            out.append(record)
    return out


def replay(path: str, kinds: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Deterministic projection over the stream — the golden-record primitive.

    Pure: same file, same dict, no clock and no environment reads. Counts by kind,
    the blocked/errored dispatches, and the handlers that produced them.
    """
    wanted = set(kinds) if kinds is not None else None
    records = read(path)
    projection: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "count": 0,
        "by_kind": {},
        "blocked": [],
        "errored": [],
    }
    for record in records:
        kind = record["kind"]
        if wanted is not None and kind not in wanted:
            continue
        projection["count"] += 1
        projection["by_kind"][kind] = projection["by_kind"].get(kind, 0) + 1
        if kind == "hook_decision":
            if record.get("merged_decision") == "DENY":
                projection["blocked"].append(
                    {"event": record["event"], "handler": record["handler"],
                     "ts": record["ts"]})
            if record.get("decision") == "ERROR":
                projection["errored"].append(
                    {"event": record["event"], "handler": record["handler"],
                     "exit_code": record["exit_code"], "ts": record["ts"]})
    return projection


def iter_records(path: str) -> Iterator[Dict[str, Any]]:
    """Streaming variant of :func:`read`, for logs too large to hold in memory."""
    for record in read(path):
        yield record


def assert_model_visible_logged(
    payload: Dict[str, Any],
    path: str,
    kind: str = "hook_decision",
    match_on: Iterable[str] = ("event", "handler"),
) -> Dict[str, Any]:
    """The invariant as executable code.

    ``payload`` describes something that is about to become model-visible. This
    fails unless the stream at ``path`` holds a record of ``kind`` that matches on
    ``match_on`` **and** carries every field :func:`required_fields` demands. Both
    halves matter: a matching record missing a field is exactly the mutant the
    schema exists to catch, and it must not pass.
    """
    keys = tuple(match_on)
    missing_in_payload = [k for k in keys if k not in payload]
    if missing_in_payload:
        raise EventLogError(
            "payload cannot be matched: missing %s" % ", ".join(missing_in_payload))
    needed = required_fields(kind)
    candidates = []
    for record in read(path, strict=False):
        if record.get("kind") != kind:
            continue
        if all(record.get(k) == payload[k] for k in keys):
            candidates.append(record)
    if not candidates:
        raise EventLogError(
            "model-visible but not logged: no %r record matching %s in %s"
            % (kind, {k: payload[k] for k in keys}, path))
    for record in candidates:
        absent = [f for f in needed if f not in record]
        if absent:
            raise EventLogError(
                "model-visible but under-logged: %r record matching %s is missing %s"
                % (kind, {k: payload[k] for k in keys}, ", ".join(sorted(absent))))
    return candidates[-1]

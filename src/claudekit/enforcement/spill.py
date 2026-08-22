"""Spill oversized output, and prune stale records without a model.

Three stages, in this order, and the order is the point
-------------------------------------------------------
1. **Spill** — output over a byte threshold is written to a session-scoped file
   and replaced inline by a bounded preview plus a retrieval locator.
2. **Model-free prune** — a deterministic pruner drops stale records.
3. **Model summarization** — only whatever survives 1 and 2 is worth paying for.

Doing 3 before 1 and 2 is how a context budget gets spent summarizing text that
was about to be discarded anyway. The ``token-optimization`` skill already
*describes* spilling; a description is prompt advice that a model may or may not
follow. This is the same idea in the layer that enforces.

Measurement is not policy
-------------------------
:func:`size_of` measures. :data:`DEFAULT_THRESHOLD_BYTES`, :data:`PREVIEW_BYTES`
and the :func:`prune` budget are policy, passed in. They are separated so that
changing a budget never edits the counter — otherwise every future policy change
lands as a diff on the measurement code and the two stop being independently
reviewable.

Not a harness
-------------
:func:`prune` performs arithmetic on a list of dicts. It imports nothing that can
make a network call, and ``tests/test_spill.py`` pins that by asserting the module
imports only from the stdlib set named there.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "SpillError", "DEFAULT_THRESHOLD_BYTES", "PREVIEW_BYTES", "LOCATOR_SCHEME",
    "size_of", "spill", "retrieve", "prune", "default_spill_dir",
]

LOCATOR_SCHEME = "ck-spill"

#: Policy defaults. Callers override; nothing here reads them from the environment.
DEFAULT_THRESHOLD_BYTES = 8192
PREVIEW_BYTES = 1024

#: A locator is exactly ``ck-spill://<session>/<64 hex>``. Anything else is refused
#: before it touches the filesystem: the locator is attacker-influenced input the
#: moment it round-trips through a model, so it is parsed, never interpolated.
_LOCATOR_RE = re.compile(
    r"\A" + re.escape(LOCATOR_SCHEME) + r"://(?P<session>[A-Za-z0-9_-]{1,128})/"
    r"(?P<digest>[0-9a-f]{64})\Z")


class SpillError(Exception):
    """A spill could not be written, or a locator could not be resolved."""


def default_spill_dir(root: str) -> str:
    """``.claude/runtime/spill/`` — gitignored runtime state, alongside the event log."""
    return os.path.join(root, ".claude", "runtime", "spill")


def size_of(text: str) -> int:
    """Bytes the text occupies as UTF-8. Measurement only — no policy here."""
    return len(text.encode("utf-8"))


def _safe_session(session_id: str) -> str:
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in str(session_id))
    return (safe or "unknown")[:128]


def spill(
    text: str,
    spill_dir: str,
    session_id: str,
    threshold: int = DEFAULT_THRESHOLD_BYTES,
    preview_bytes: int = PREVIEW_BYTES,
) -> Dict[str, Any]:
    """Persist ``text`` if it exceeds ``threshold``; return preview + locator.

    Under threshold the text is returned whole with ``spilled: False`` and no file
    is written — spilling short output would trade a cheap inline string for a
    file read.

    Over threshold the full text is written under ``spill_dir`` keyed by its
    SHA-256, and the returned ``preview`` is truncated on a **character** boundary
    (never mid-codepoint) and annotated with the byte count withheld and the
    locator that retrieves it. The preview always states that content was
    withheld: a silent truncation is a lie to the model about what it has read.

    The spill file is created **0600, regardless of umask**. Spilled text is the
    oversized tool output that could not stay inline, which is exactly where a
    secret ends up; a world-readable copy of it on disk would be a disclosure
    created by an optimisation.
    """
    if threshold < 0 or preview_bytes < 0:
        raise SpillError("threshold and preview_bytes must be non-negative")
    total = size_of(text)
    if total <= threshold:
        return {
            "spilled": False, "preview": text, "locator": None,
            "bytes": total, "withheld_bytes": 0, "sha256": None, "path": None,
        }
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    session = _safe_session(session_id)
    directory = os.path.join(spill_dir, session)
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        path = os.path.join(directory, digest + ".txt")
        if not os.path.exists(path):
            # 0600 ALWAYS -- not "whatever the umask happens to be". `open()`
            # (what this used) takes the process umask, so on a normal 022 box
            # every spill file was 0644: a world-readable copy of tool output,
            # created by an optimisation, while eventlog.append already did the
            # right thing with os.open(..., 0o600). Round-4 review found the
            # asymmetry.
            #
            # `tempfile.mkstemp` is the fix rather than
            # `os.open(..., O_EXCL, 0o600)` on a fixed name: mkstemp also creates
            # with O_EXCL and 0600 (so a symlink planted at the temp name cannot
            # redirect this write), but its name is unique, so a crash cannot
            # leave a stale temp behind that makes every later spill of the same
            # digest fail permanently -- which a pid-suffixed O_EXCL name can.
            # `os.replace` preserves the mode, so the published file is 0600 too.
            fd, tmp = tempfile.mkstemp(dir=directory, prefix=digest + ".",
                                       suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(text)
                os.replace(tmp, path)
            finally:
                # After a successful replace the temp name is gone, so this is a
                # no-op on the happy path and a cleanup on every failing one.
                if os.path.exists(tmp):
                    os.unlink(tmp)
    except OSError as exc:
        raise SpillError("could not write spill file: %s" % exc) from exc

    head = text.encode("utf-8")[:preview_bytes].decode("utf-8", errors="ignore")
    locator = "%s://%s/%s" % (LOCATOR_SCHEME, session, digest)
    preview = (
        "%s\n[... %d of %d bytes withheld; retrieve with %s ...]"
        % (head, total - size_of(head), total, locator)
    )
    return {
        "spilled": True, "preview": preview, "locator": locator,
        "bytes": total, "withheld_bytes": total - size_of(head),
        "sha256": digest, "path": path,
    }


def retrieve(locator: str, spill_dir: str) -> str:
    """Resolve a locator back to the full text, or raise.

    The locator is parsed against :data:`_LOCATOR_RE` and the resolved path is
    re-checked to be inside ``spill_dir`` after ``realpath``, so a symlink planted
    in the spill directory cannot turn a retrieval into an arbitrary file read.
    The digest is re-verified against the content: a spill file edited on disk is
    a corrupted record, not a cheaper answer.
    """
    if not isinstance(locator, str):
        raise SpillError("locator must be a string, got %s" % type(locator).__name__)
    match = _LOCATOR_RE.match(locator)
    if not match:
        raise SpillError("malformed locator: %r" % (locator,))
    path = os.path.join(spill_dir, match.group("session"), match.group("digest") + ".txt")
    real = os.path.realpath(path)
    base = os.path.realpath(spill_dir)
    if not (real == base or real.startswith(base + os.sep)):
        raise SpillError("locator resolves outside the spill directory: %r" % (locator,))
    try:
        with open(real, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise SpillError("spill file unavailable for %r: %s" % (locator, exc)) from exc
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != match.group("digest"):
        raise SpillError("spill file for %r does not match its digest" % (locator,))
    return text


def prune(
    records: Sequence[Dict[str, Any]],
    budget_bytes: int,
    protect: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Model-free, deterministic pruning. Returns ``(kept, dropped)``.

    Each record needs ``id`` (str), ``bytes`` (int) and ``last_used`` (comparable,
    higher = more recent). Records whose ``id`` is in ``protect``, or that carry
    ``pinned: True``, are never dropped and are charged against the budget first —
    so a caller can see that the protected set alone busts the budget rather than
    having the pruner quietly drop something it promised to keep.

    Eviction order: **stalest first**, ties broken by larger ``bytes``, then by
    ``id`` ascending. The final tie-break on ``id`` is what makes the function a
    pure function of its input — with only (last_used, bytes) two equal records
    would evict in list order, and the result would depend on how the caller
    happened to build the list.

    No model is consulted, no clock is read, and nothing is summarized. That is
    the whole contract: this runs *before* anything is paid for.
    """
    if budget_bytes < 0:
        raise SpillError("budget_bytes must be non-negative")
    protected = set(protect or ())
    for record in records:
        for field in ("id", "bytes", "last_used"):
            if field not in record:
                raise SpillError("record %r is missing %r" % (record, field))
        if not isinstance(record["bytes"], int) or record["bytes"] < 0:
            raise SpillError("record %r has a non-negative-int 'bytes'" % (record,))

    keep_always = [r for r in records if r["id"] in protected or r.get("pinned")]
    candidates = [r for r in records if not (r["id"] in protected or r.get("pinned"))]
    # Freshest first, so we keep from the front while budget remains.
    candidates.sort(key=lambda r: (r["last_used"], -int(r["bytes"]), r["id"]), reverse=True)

    used = sum(int(r["bytes"]) for r in keep_always)
    kept: List[Dict[str, Any]] = list(keep_always)
    dropped: List[Dict[str, Any]] = []
    for record in candidates:
        size = int(record["bytes"])
        if used + size <= budget_bytes:
            kept.append(record)
            used += size
        else:
            dropped.append(record)
    kept.sort(key=lambda r: r["id"])
    dropped.sort(key=lambda r: r["id"])
    return kept, dropped

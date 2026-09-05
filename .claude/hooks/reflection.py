#!/usr/bin/env python3
"""reflection.py - session-scoped failure ledger, fingerprinting and reflection receipts.

WHY THIS EXISTS (gaps G3/G4/G7)
-------------------------------
Before this module the kit had no durable memory of *failure*. `PostToolUseFailure`
printed a line and forgot it; `Stop` and `SubagentStop` were decorative; a compaction
erased every unmet duty. "After three failed fixes, widen the premise" was advice an
agent could only give itself. This module makes the loop *detectable* by machine.

DESIGN PROPERTIES (each one is load-bearing; do not "simplify" them away)
------------------------------------------------------------------------
1. LOW-CARDINALITY FINGERPRINT. A failure is identified by sha256 over exactly six
   bounded fields - phase, target, failureClass, platform, invariant, head - never over
   raw error text. Two attempts at the same thing collide by construction, which is what
   makes "you already tried this" computable.
2. PRIVACY BY CONSTRUCTION. Every field passes `bounded_token`, which replaces any value
   matching an absolute-path or credential regex with `digest-<sha256[:16]>`. Free-text
   receipt fields go through `_safe_text`, which *rejects* rather than digests. Raw host
   paths and secret-shaped strings therefore never reach the ledger. This is a privacy
   requirement, not a nicety - the ledger outlives the transcript.
3. EXTERNAL, APPEND-ONLY LEDGER. JSONL under the OS temp dir, keyed by sha256(session_id),
   never inside the repo and never inside the transcript - so it survives `/compact`,
   survives context loss, and can never be committed. The fallback root is discriminated
   by uid AND by a hash of the project root, and every component we create is 0o700 and
   re-verified with `os.lstat` on use. A single shared `$TMPDIR/claudekit-reflection` was
   both a correctness bug (two checkouts sharing one ledger under colliding session ids)
   and, where `$TMPDIR` is world-writable `/tmp`, a pre-creation/symlink target: a co-user
   could plant the directory or a `<key>.jsonl` symlink and turn every append into a write
   into a file of their choosing, or pre-create `<key>.token` so `O_EXCL` lost and their
   key was adopted. Honest sizing (hard rule 6): on a single-user macOS host `$TMPDIR` is
   already a private per-user `/var/folders/.../T`, so that was never reachable there; the
   exposure was real on shared Linux build hosts and CI runners.
4. RECEIPTS ARE AN INTEGRITY SPEED BUMP, NOT AN ADVERSARIAL CONTROL. A receipt is
   HMAC-SHA256'd with a per-session token created `O_EXCL` at mode 0o600, and is bound to
   `checkpointDigest` - a digest of the *exact* active failure set it discharges. That
   defeats ACCIDENTAL and LAZY discharge: a hand-written plausible receipt appended to the
   ledger clears nothing, and a valid receipt replayed against a later active set clears
   nothing either. It does NOT defeat an adversarial model: the agent holds Bash and Read
   and runs under the SAME uid as the 0o600 token, so it can read the token and mint a
   valid HMAC over any receipt it likes. Claim only what is true (project hard rule 6) -
   this is the same honest framing as "denylist speed bump, not a sandbox". The value is
   that discharging a checkpoint requires a deliberate, auditable act naming the exact
   duty owed, not that it is cryptographically impossible.
5. `non-attempt` DISPOSITION. setup-error / syntax-error / capability-probe failures are
   retracted from the active set, so a broken harness does not burn the failure counter.

Python 3.9, stdlib only (project hard rule 8). No `datetime.UTC`, no PEP-604 unions.
"""

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

#: Semantic reasons a reflection checkpoint may be raised. `second-failure` and
#: `repeated-fingerprint` are derived by `pending_checkpoint`; the rest are explicit.
TRIGGERS = frozenset({
    "second-failure",
    "repeated-fingerprint",
    "third-fix",
    "review-repeat",
    "user-correction",
    "guard-repeat",
    "scope-expansion",
    "premise-invalidated",
    # Raised by the Stop learning-loop duty, not by a failure count: the session changed
    # the world and owes a routed learning decision.
    "learning-loop",
})

#: Where a reflection may land. `nothing-durable` is a VALID outcome - the gate exists to
#: force the *decision*, not to force a write.
DISPOSITIONS = frozenset({
    "guidance-fixed",
    "issue-filed",
    "knowledge-recorded",
    "nothing-durable",
    "degraded",
})

NON_ATTEMPT_REASONS = frozenset({"setup-error", "syntax-error", "capability-probe"})

# The receipt's field set and text budget, hoisted so the DEMAND and the VALIDATOR read
# from one table. Filing a receipt against the 2026-09-05 self-describing demand still
# cost three refusal rounds -- unknown field, 240-char cap, credential shape -- because
# each of those rules lived only in the validator. A demand that names the closed field
# set and the text budget costs one round instead.
RECEIPT_FIELDS = frozenset({
    "schemaVersion", "taskId", "trigger", "failureFingerprints", "failedAssumption",
    "approachesCompared", "chosenExperiment", "changedApproach", "proofCommandOrCheck",
    "proofOutcome", "durableDisposition", "issue",
})
RECEIPT_OPTIONAL_FIELDS = frozenset({"changedApproach", "issue"})

_SAFE_TEXT_MAX = 240
_SAFE_TEXT = re.compile(r"^[^\r\n\x00]{1,%d}$" % _SAFE_TEXT_MAX)
# Absolute POSIX/UNC/Windows paths and home-shaped prefixes.
_ABSOLUTE_PATH = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+|(?:^|\s)/(?!/)|~/|"
    r"(?:home|users?|workspace|private|var)[\\/:][^\s]+)"
)
_SECRET = re.compile(
    r"(?i)(?:password|passwd|secret|access[_-]?token|token|bearer|credential|"
    r"api[_-]?key|authorization|private[_-]?key|aws_[a-z_]*key)"
)

_ENV_DIR = "CLAUDEKIT_REFLECTION_DIR"
_ENV_INBOX = "CLAUDEKIT_REFLECTION_INBOX"

#: Basename of the temp-dir fallback root. The uid and project segments appended to it
#: in `ledger_dir()` are what stop two users, or two checkouts, from sharing a ledger.
_TMP_ROOT_NAME = "claudekit-reflection"
#: Per-process memo for `_project_key()`: ((CLAUDE_PROJECT_DIR, cwd), digest).
_PROJECT_KEY_CACHE = None  # type: Optional[Tuple[Tuple[str, str], str]]
#: One-shot latch so a degraded host says so ONCE per process instead of silently.
_WARNED_UNTRUSTED = False

# --- high-entropy secret shapes (keyword-free credentials) -------------------
# A keyword list alone is not a control: a bare 40-char hex token, an opaque key with no
# vendor prefix, or a JWT with no adjacent keyword matches no keyword at all and would
# otherwise survive `re.sub` verbatim into a file that outlives the transcript. These
# shape/entropy rules close that path.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}")
_HEX_TOKEN = re.compile(r"^[0-9a-fA-F]{20,}$")
_B64URL_TOKEN = re.compile(r"^[A-Za-z0-9_+/=-]{20,}$")
_TOKEN_CHUNK = re.compile(r"[^A-Za-z0-9_+/=]+")
# Values this module produced itself are already sanitized digests; re-digesting them
# would only make the ledger unreadable. Explicit allowlist, never a heuristic.
_INTERNAL_SHAPE = re.compile(r"^(?:digest|command|file|logical)-[0-9a-f]{16,24}$")
_MIN_TOKEN_LEN = 20
_MIN_SINGLE_CASE_LEN = 32
_MIN_ENTROPY_BITS = 3.5


def shannon_bits_per_char(text: str) -> float:
    """Shannon entropy per character. Random credentials sit near 4-6; English prose and
    identifiers sit well below 3.5."""
    if not text:
        return 0.0
    counts: Dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = float(len(text))
    bits = 0.0
    for count in counts.values():
        share = count / total
        bits -= share * math.log(share, 2)
    return bits


def looks_like_credential(raw: str) -> bool:
    """True when the RAW value carries a keyword-free, credential-shaped token.

    Rules, all requiring >= 3.5 bits/char of Shannon entropy:
      * a JWT header (`eyJ...`);
      * an all-hex run of >= 20 chars;
      * a >= 20-char base64url run mixing upper case, lower case and digits;
      * a >= 32-char single-case base64url run containing no `_`.
    Runs on the value BEFORE casefolding, because casefolding destroys the case mix that
    identifies base64url secrets.

    HONEST LIMIT (hard rule 6): this is a shape heuristic, not a proof of secret-freeness.
    The residual blind spot is a single-case, non-hex token of 20-31 chars, or one
    carrying an underscore - both concessions to keeping snake_case identifiers like
    `test_reflection_ledger_py` readable in the ledger. Combined with the keyword list and
    the absolute-path rule this closes the realistic leak paths and nothing more.
    """
    if _JWT.search(raw):
        return True
    if _INTERNAL_SHAPE.match(raw.strip()):
        return False
    for chunk in _TOKEN_CHUNK.split(raw):
        if len(chunk) < _MIN_TOKEN_LEN or _INTERNAL_SHAPE.match(chunk):
            continue
        if _HEX_TOKEN.match(chunk):
            return True
        if not _B64URL_TOKEN.match(chunk):
            continue
        if shannon_bits_per_char(chunk) < _MIN_ENTROPY_BITS:
            continue
        mixed_case = (any(c.islower() for c in chunk) and any(c.isupper() for c in chunk)
                      and any(c.isdigit() for c in chunk))
        if mixed_case:
            return True
        # Single-case residual: `_TOKEN_CHUNK` keeps `_` inside a chunk, which is what
        # makes snake_case identifiers look base64url-ish and forced the mixed-case rule
        # above. So for single-case runs demand a longer, underscore-free chunk - real
        # identifiers of that length almost always carry a separator, opaque secrets do
        # not.
        if len(chunk) >= _MIN_SINGLE_CASE_LEN and "_" not in chunk:
            return True
    return False


# --------------------------------------------------------------------------- paths


def _current_uid() -> int:
    """Our own uid, or -1 where the platform has none.

    Indirected through a function on purpose: it is the only way a test can simulate a
    directory owned by SOMEONE ELSE without being root to chown one.
    """
    getter = getattr(os, "getuid", None)
    return getter() if getter is not None else -1


def _project_key() -> str:
    """Low-cardinality discriminator for the project this session belongs to.

    Two checkouts on one machine must never share a ledger directory even if their
    session ids collide. Hashed rather than spelled out, so the path itself records no
    host path (design property 2). Memoised per process: `project_root()` may shell out
    to `git rev-parse`, and `ledger_dir()` is called on every ledger operation. The memo
    key includes the inputs, so a project change inside one process invalidates it.
    """
    global _PROJECT_KEY_CACHE
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = ""
    cache_key = (os.environ.get("CLAUDE_PROJECT_DIR") or "", cwd)
    cached = _PROJECT_KEY_CACHE
    if cached is not None and cached[0] == cache_key:
        return cached[1]
    root = os.path.realpath(str(project_root()))
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]
    _PROJECT_KEY_CACHE = (cache_key, digest)
    return digest


def ledger_root_is_explicit() -> bool:
    """True when the operator named the ledger root themselves."""
    override = os.environ.get(_ENV_DIR)
    return bool(override and os.path.isabs(override))


def ledger_dir() -> Path:
    """External ledger root.

    `CLAUDEKIT_REFLECTION_DIR` (tests, and projects that want an explicit location) wins,
    and is honoured VERBATIM - no uid or project segment is appended to it.

    Otherwise the OS temp dir - deliberately OUTSIDE the repository so the ledger cannot
    be committed, cannot be read back into the transcript wholesale, and survives
    compaction of the session that produced it - narrowed to `<tmp>/claudekit-reflection-
    u<uid>/<project-key>`. The uid segment keeps two users on one host apart; the project
    segment keeps two checkouts apart. Neither may depend on anything per-INVOCATION: the
    ledger is written by one hook process and read by later ones in the same session, and
    a pid- or time-derived path would silently break every checkpoint.
    """
    override = os.environ.get(_ENV_DIR)
    if override and os.path.isabs(override):
        return Path(override)
    base = os.environ.get("TMPDIR") or os.environ.get("TEMP") or os.environ.get("TMP")
    if not base or not os.path.isabs(base):
        base = tempfile.gettempdir()
    return Path(base, "%s-u%d" % (_TMP_ROOT_NAME, _current_uid()), _project_key())


def _is_private_dir(path: Path) -> bool:
    """True only for a REAL directory owned by us with no group or other access.

    `os.lstat`, never `stat`: a symlink planted at this path must FAIL the check, not be
    followed to its target's metadata. `Path.mkdir(exist_ok=True)` does follow it - it
    swallows `FileExistsError` whenever `is_dir()` is true - which is exactly how a
    predictable name in a world-writable temp dir becomes an arbitrary-write primitive.
    """
    try:
        info = os.lstat(str(path))
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode):
        return False
    uid = _current_uid()
    if uid >= 0 and info.st_uid != uid:
        return False
    return not (stat.S_IMODE(info.st_mode) & 0o077)


def _warn_untrusted_root() -> None:
    """Say so, ONCE per process, on stderr.

    A degraded host must not be silent: reflection would then be off-and-quiet, which is
    precisely the failure mode that disqualifies "refuse unless configured" as a design.
    stderr, not stdout, and never with a non-zero exit - this is advisory, never a block.
    """
    global _WARNED_UNTRUSTED
    if _WARNED_UNTRUSTED:
        return
    _WARNED_UNTRUSTED = True
    try:
        sys.stderr.write(
            "reflection: ledger root is not private to this user (wrong owner, "
            "group/other access, or a symlink) - reflection is degraded. Set "
            "CLAUDEKIT_REFLECTION_DIR to a directory you own.\n")
    except (OSError, ValueError):
        pass


def ledger_dir_trusted() -> bool:
    """Read-side predicate. Creates NOTHING: `reflection-gate.py` calls into the read
    paths from a blocking PreToolUse hook, which must have no filesystem side effects.

    Audits the LEAF only, while `ensure_ledger_dir()` audits `(parent, leaf)`. That is
    sufficient here and must stay this way: a private leaf cannot be reached, replaced or
    have files planted in it by another uid regardless of who owns the parent, because
    directory entries can only be created inside a directory, and `_is_private_dir`
    rejects a symlink outright rather than following it. The write path audits both
    because it CREATES the parent and must not create it inside someone else's symlink.
    Do not "simplify" either side into the other.
    """
    if ledger_root_is_explicit():
        return True
    if _is_private_dir(ledger_dir()):
        return True
    _warn_untrusted_root()
    return False


def ensure_ledger_dir() -> Optional[Path]:
    """Create the ledger root if needed and return it, or None if it cannot be trusted.

    Every component WE own is created 0o700 and re-validated on each use, so a co-user
    can neither pre-create it nor plant symlinked ledger files inside it. Refusing is the
    right failure: callers degrade (`False` / `None` / `[]`) and the user's tool call is
    never crashed.

    An explicit `CLAUDEKIT_REFLECTION_DIR` is created but NOT audited - the operator
    chose that location and owns its permissions. Auditing it would also break every
    caller that points the kit at a shared or group-readable directory on purpose.
    """
    path = ledger_dir()
    if ledger_root_is_explicit():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        return path
    # The system temp dir is not ours to audit, but it may legitimately be missing
    # (a pruned `$TMPDIR`); create it with the platform default before the audited
    # components, so a missing base degrades reflection to nothing.
    try:
        os.makedirs(str(path.parent.parent), exist_ok=True)
    except OSError:
        return None
    for candidate in (path.parent, path):
        try:
            os.mkdir(str(candidate), 0o700)
        except FileExistsError:
            pass
        except OSError:
            return None
        if not _is_private_dir(candidate):
            _warn_untrusted_root()
            return None
    return path


def _session_key(session_id: str) -> str:
    return hashlib.sha256(session_id.strip().encode("utf-8")).hexdigest()[:32]


def ledger_path(session_id: str) -> Path:
    return ledger_dir() / ("%s.jsonl" % _session_key(session_id))


def token_path(session_id: str) -> Path:
    return ledger_dir() / ("%s.token" % _session_key(session_id))


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def inbox_path(session_id: str) -> Path:
    """Project-local drop box for a receipt payload.

    WHY THIS EXISTS: the only other channel for a receipt is a shell command line, and
    that string is also scanned by `command-guard.sh` -> `command_validator.py`, which
    denies on literal substrings like `subprocess.run`, `os.system(` and `__import__(`.
    A receipt whose `failedAssumption` legitimately names one of those - entirely
    plausible in a Python debugging session, which is exactly when a checkpoint fires -
    would be refused by an unrelated hook while the checkpoint stayed pending. Writing
    the payload with the Write tool and passing `--inbox` removes that coupling: the
    command line then carries flags only, never free text.

    Lives under `.claude/reflection/` (Write-allowed by ops-enforcement, gitignored).
    """
    override = os.environ.get(_ENV_INBOX)
    base = Path(override) if override and os.path.isabs(override) else (
        project_root() / ".claude" / "reflection")
    return base / ("inbox-%s.json" % _session_key(session_id))


def carryover_path(session_id: str) -> Path:
    """Duty summary re-injected at SessionStart after a compaction (gap G7)."""
    return ledger_dir() / ("%s.carryover" % _session_key(session_id))


def valid_session(session_id: Any) -> bool:
    return isinstance(session_id, str) and bool(session_id.strip())


# --------------------------------------------------------------------------- storage


def append_entry(session_id: str, entry: Dict[str, Any]) -> bool:
    """Append one JSON object as a line. Returns False instead of raising: a hook that
    cannot write its ledger must degrade, never crash the user's tool call."""
    if not valid_session(session_id):
        return False
    if ensure_ledger_dir() is None:
        # Untrusted root (wrong owner, group/other access, or a planted symlink). Losing
        # a ledger entry is strictly better than appending through someone else's link.
        return False
    path = ledger_path(session_id)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError):
        return False
    return True


def entries(session_id: str) -> List[Dict[str, Any]]:
    """Read the ledger. A truncated or corrupt final line is skipped, never fatal."""
    if not valid_session(session_id):
        return []
    if not ledger_dir_trusted():
        # Entries from a root another uid can write are attacker-supplied, not history.
        return []
    path = ledger_path(session_id)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            found.append(item)
    return found


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- token


def _new_token() -> str:
    """A session token that cannot be mistaken for a command-line flag.

    `secrets.token_urlsafe` draws from the base64url alphabet, which contains `-`,
    so ~1.5% of tokens begin with one (measured: 306 of 20000). Every caller passes
    the token as `--session-token <value>`, and argparse reads a leading-dash value
    as the next OPTION -- producing `argument --session-token: expected one
    argument` and an exit 2. That was the "UNEXPLAINED intermittent" in
    `.ai/BACKLOG.md`, unreproducible for weeks because it depends on a coin flip
    inside the secret itself.

    The token is also PRINTED to the user at session start and pasted onto command
    lines by agents, so hardening one caller would not have been enough; the fix
    belongs here, where every consumer inherits it.

    Redraws rather than strips: dropping the leading character would shorten the
    secret, and replacing it would bias the first character. Entropy per token is
    unchanged.
    """
    for _ in range(64):
        token = secrets.token_urlsafe(24)
        if not token.startswith("-"):
            return token
    # Unreachable in practice (p ≈ 2**-380); prefixing keeps it flag-safe and is
    # better than returning something argparse will reject.
    return "s" + secrets.token_urlsafe(24)


def read_session_token(session_id: str) -> Optional[str]:
    if not valid_session(session_id):
        return None
    if not ledger_dir_trusted():
        # `O_EXCL` stops the token being OVERWRITTEN, not PRE-CREATED: without this the
        # loser of that race adopts a key the attacker already knows, and every receipt
        # HMAC becomes forgeable by them.
        return None
    try:
        token = token_path(session_id).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return token if len(token) >= 24 else None


def ensure_session_token(session_id: str) -> Optional[str]:
    """Create the per-session HMAC key exactly once.

    `O_EXCL` + 0o600: the token is the capability that lets the owner of this session -
    and nobody else on a shared host - write a receipt. A race loses harmlessly (the
    loser re-reads the winner's token).
    """
    if not valid_session(session_id):
        return None
    existing = read_session_token(session_id)
    if existing:
        return existing
    if ensure_ledger_dir() is None:
        return None
    path = token_path(session_id)
    token = _new_token()
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(token)
    except FileExistsError:
        return read_session_token(session_id)
    except OSError:
        return None
    return token


# --------------------------------------------------------------------------- sanitize


def bounded_token(value: Any, fallback: str = "unknown") -> str:
    """Collapse an arbitrary value to a low-cardinality, privacy-safe token.

    Anything that looks like an absolute path or a credential is replaced by a digest, so
    the ledger records *that two failures were the same* without recording *what they
    were about* in host terms.
    """
    original = str(value if value is not None else "")
    raw = original.casefold()
    if not raw:
        return fallback
    # Entropy/shape check runs on the ORIGINAL text; keyword and path checks on the
    # casefolded text. Any hit is digested rather than rendered.
    if looks_like_credential(original) or _ABSOLUTE_PATH.search(raw) or _SECRET.search(raw):
        return "digest-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    rendered = re.sub(r"[^a-z0-9_.:-]+", "-", raw).strip("-")
    return rendered[:80] or fallback


def _safe_text(name: str, value: Any, required: bool = True) -> str:
    """Validate a free-text receipt field. Rejects (does not digest) unsafe text - a
    human-authored sentence has no business containing a host path or a token."""
    rendered = str(value if value is not None else "").strip()
    if not rendered and not required:
        return ""
    if not _SAFE_TEXT.match(rendered):
        raise ValueError("%s must be 1-%d characters on a single line"
                         % (name, _SAFE_TEXT_MAX))
    if (_ABSOLUTE_PATH.search(rendered) or _SECRET.search(rendered)
            or looks_like_credential(rendered)):
        raise ValueError("%s contains path-shaped or credential-shaped text" % name)
    return rendered


# Vendor-shaped credential markers, and a THIRD disposition for the same knowledge.
# _safe_text REJECTS a whole string; bounded_token DIGESTS one; a transcript slice needs
# text that stays READABLE while carrying no secret. All three live here so this repo has
# exactly ONE place that says what a secret looks like -- a second copy inside
# transcript-miner.py would be two definitions that must stay in sync, which is the
# failure mode this codebase has already paid for. Existing callers are untouched: every
# name below is new.
_VENDOR_SECRET = re.compile(
    r"(?:sk-(?:ant-)?[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}"
    r"|github_pat_[A-Za-z0-9_]{8,}|AKIA[0-9A-Z]{8,}|xox[abprs]-[A-Za-z0-9-]{8,})"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_KEYED_VALUE = re.compile(
    r"(?i)([\x22\x27]?[A-Za-z0-9_.-]*"
    r"(?:token|secret|key|password|passwd|credential)[\x22\x27]?\s*[:=]\s*)"
    r"([\x22\x27]?)([^\s\x22\x27,;]{4,})"
)
REDACTED = "<redacted>"


def redact_secrets(text):
    """Replace credential-shaped substrings in free text with <redacted>.

    For output that must stay human-readable -- a transcript slice quoted into a TRACKED
    retro report -- where rejecting or digesting the whole string would destroy the
    evidence it exists to carry.

    HONEST LIMIT (hard rule 6): shape heuristics, not proof of secret-freeness. A novel
    token format with low entropy and no keyword still passes. A speed bump on the
    highest-risk channel, not a sandbox.
    """
    if not text:
        return text
    text = _PEM.sub(REDACTED, text)
    text = _VENDOR_SECRET.sub(REDACTED, text)
    text = _BEARER.sub("Bearer " + REDACTED, text)
    text = _KEYED_VALUE.sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)
    # Entropy pass: looks_like_credential unchanged, applied piece by piece so the
    # surrounding prose survives.
    return "".join(
        REDACTED if piece and looks_like_credential(piece) else piece
        for piece in re.split(r"(\s+)", text)
    )


def fingerprint_fields(
    phase: Any,
    target: Any,
    failure_class: Any,
    platform: Any = "unknown",
    invariant: Any = "command-outcome",
    head: Any = "unknown",
) -> Dict[str, str]:
    return {
        "phase": bounded_token(phase, "unknown-phase"),
        "target": bounded_token(target, "unknown-target"),
        "failureClass": bounded_token(failure_class, "unknown-class"),
        "platform": bounded_token(platform, "unknown-platform"),
        "invariant": bounded_token(invariant, "command-outcome"),
        "head": bounded_token(head, "unknown"),
    }


def compute_fingerprint(fields: Dict[str, str]) -> str:
    blob = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


# --------------------------------------------------------------------------- recording


def record_session_start(session_id: str) -> Optional[str]:
    token = ensure_session_token(session_id)
    if token is None:
        return None
    if not any(item.get("kind") == "session-start" for item in entries(session_id)):
        append_entry(session_id, {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "session-start",
            "observedAt": now_iso(),
        })
    return token


SESSION_POINTERS = "session-pointers.jsonl"
#: What a transcript-filename-shaped session id looks like. THE definition, enforced at
#: WRITE time -- review-record.py reads these rows with the identical pattern, and if the
#: two ever drift the reader POISONS (returns "unknown") rather than skipping the odd row
#: and resolving to an older one, so drift degrades to no answer instead of a wrong one.
SESSION_ID_SHAPE = re.compile(r"^[0-9a-fA-F-]{8,64}$")
#: Only the nearest few ancestors are recorded and matched. Everything shares launchd and
#: a terminal, so an unbounded chain makes ANY two processes on the host "related": a
#: manual invocation in the same terminal as a live session would resolve to that
#: session's id. A real caller is 1-3 hops away (review-record <- bash <- claude), so a
#: bound of 4 keeps every legitimate case and refuses the coincidental ones.
_POINTER_MAX_DEPTH = 4
#: A pointer older than this is ignored. Bounds the one residual risk of matching by pid:
#: pid reuse. A stale entry that is both within 24h AND shares a live ancestor with the
#: reader is possible in principle; it is far likelier to produce a SECOND match (which
#: resolves to "unknown") than a wrong one.
POINTER_TTL_SECONDS = 24 * 60 * 60
_POINTER_MAX_ROWS = 64


def _pointer_path() -> Optional[Path]:
    root = ensure_ledger_dir()
    return None if root is None else root / SESSION_POINTERS


def _ancestor_pids() -> List[int]:
    """This process's ancestor pids, innermost first.

    `ps -o ppid=` because the stdlib has no portable parent-of-parent. Bounded at 12 hops
    with a short timeout and a total guard: this runs on hook and approval paths, where a
    helper may degrade to [] but may never raise or hang.
    """
    out: List[int] = []
    current = os.getpid()
    for _ in range(12):
        try:
            res = subprocess.run(["ps", "-o", "ppid=", "-p", str(current)],
                                 capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            break
        value = res.stdout.strip()
        if res.returncode != 0 or not value.isdigit():
            break
        current = int(value)
        if current <= 1:
            break
        out.append(current)
    return out


def record_session_pointer(session_id: Any, transcript_path: Any = None) -> bool:
    """Record (session id, this process's ancestor pids) so a later tool in the SAME
    process tree can PROVE which session it belongs to.

    WHY THIS EXISTS: a session id reaches nothing in this repo except a hook payload --
    no env var carries it, and a slash command's bash fence has no channel to it. So the
    rejection briefs recorded `session: unknown` and root-cause mining silently degraded
    to brief-only. Ancestry rather than recency: "the newest transcript" was MEASURED
    wrong here (the newest belonged to a subagent, and concurrent sessions were writing),
    and a wrong session id is worse than none because nothing downstream can detect it.

    The raw id is a transcript filename, not a credential -- and it stays in the external
    ledger root, which is outside the repository by construction, so it can never be
    committed. Best-effort throughout: False, never an exception.
    """
    # valid_session() alone is NOT enough here: it accepts any non-empty string, while
    # the reader requires a transcript filename. A pointer the reader cannot use is worse
    # than none -- it was demonstrated to make resolution fall through to an older, stale
    # pointer sharing ancestry and return a WRONG id silently. Same shape, both sides.
    if not valid_session(session_id) or not SESSION_ID_SHAPE.match(str(session_id).strip()):
        return False
    path = _pointer_path()
    if path is None or path.is_symlink():
        return False
    row = {
        "schemaVersion": SCHEMA_VERSION,
        "session_id": str(session_id).strip(),
        "pids": _ancestor_pids()[:_POINTER_MAX_DEPTH],
        # Basename only: the directory is the host's, and this row is read by tools whose
        # output lands in committed files.
        "transcript": os.path.basename(str(transcript_path or "")),
        "observedAt": now_iso(),
        "epoch": int(datetime.now(timezone.utc).timestamp()),
    }
    rows = [r for r in session_pointers() if r.get("session_id") != row["session_id"]]
    rows.append(row)
    rows = rows[-_POINTER_MAX_ROWS:]
    try:
        with open(str(path), "w", encoding="utf-8") as handle:
            for item in rows:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        os.chmod(str(path), 0o600)
    except OSError:
        return False
    return True


def session_pointers() -> List[Dict[str, Any]]:
    """Live, non-expired session pointers. Never raises: every caller is on a hot path."""
    path = _pointer_path()
    if path is None or path.is_symlink() or not path.is_file():
        return []
    cutoff = int(datetime.now(timezone.utc).timestamp()) - POINTER_TTL_SECONDS
    rows: List[Dict[str, Any]] = []
    try:
        with open(str(path), "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not valid_session(row.get("session_id")):
            continue
        try:
            epoch = int(row.get("epoch") or 0)
        except (TypeError, ValueError):
            # A hand-edited or truncated pointer must not raise out of a function whose
            # docstring promises it never does -- and whose callers sit on hot paths.
            continue
        if epoch < cutoff:
            continue
        rows.append(row)
    return rows


def record_failure(
    session_id: str,
    phase: Any,
    target: Any,
    failure_class: Any,
    platform: Any = "unknown",
    invariant: Any = "command-outcome",
    head: Any = "unknown",
    attempted: bool = True,
    observation_id: Any = None,
) -> Optional[Dict[str, Any]]:
    """Append one sanitized failure. Idempotent per `observation_id` (tool_use_id), so a
    retried hook delivery cannot inflate the failure count."""
    if not valid_session(session_id):
        return None
    ensure_session_token(session_id)
    observation = None
    if observation_id:
        observation = hashlib.sha256(str(observation_id).encode("utf-8")).hexdigest()[:24]
        for item in entries(session_id):
            if item.get("kind") == "task-failure" and item.get("observationId") == observation:
                return item
    fields = fingerprint_fields(phase, target, failure_class, platform, invariant, head)
    entry: Dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "task-failure",
        "failureId": "failure-" + (observation or secrets.token_hex(12)),
        "fingerprint": compute_fingerprint(fields),
        "attempted": bool(attempted),
        "observedAt": now_iso(),
    }
    entry.update(fields)
    if observation:
        # Recorded so a redelivered hook event dedupes instead of inflating the counter.
        entry["observationId"] = observation
    return entry if append_entry(session_id, entry) else None


def record_trigger(session_id: str, trigger: str, fingerprint: str = "manual") -> bool:
    if trigger not in TRIGGERS or trigger == "learning-loop":
        raise ValueError("trigger is not an actionable checkpoint enum value")
    return append_entry(session_id, {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "reflection-trigger",
        "trigger": trigger,
        "fingerprint": bounded_token(fingerprint, "manual"),
        "observedAt": now_iso(),
    })


def mark_non_attempt(session_id: str, failure_id: str, reason: str) -> bool:
    """Retract one failure from the active set (broken harness, not a real attempt)."""
    if reason not in NON_ATTEMPT_REASONS:
        raise ValueError("reason is not a supported non-attempt enum value")
    known = [item for item in entries(session_id) if item.get("kind") == "task-failure"]
    if failure_id not in {item.get("failureId") for item in known}:
        raise ValueError("failureId does not exist in this session")
    for item in entries(session_id):
        if item.get("kind") == "failure-disposition" and item.get("failureId") == failure_id:
            return True
    return append_entry(session_id, {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "failure-disposition",
        "failureId": failure_id,
        "disposition": "non-attempt",
        "reason": reason,
        "observedAt": now_iso(),
    })


def record_activity(session_id: str, activity: str) -> bool:
    """Note that this session mutated or delivered something. Drives the learning-loop
    duty at Stop: a session that changed the world owes a routed learning decision."""
    return append_entry(session_id, {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "task-activity",
        "activity": bounded_token(activity, "activity"),
        "observedAt": now_iso(),
    })


# --------------------------------------------------------------------------- receipts


def _session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.strip().encode("utf-8")).hexdigest()[:24]


def checkpoint_digest(active: List[Dict[str, Any]]) -> str:
    """Digest of the EXACT active set a receipt must discharge.

    Binding receipts to this is what stops a model from clearing a checkpoint it does not
    owe: a receipt minted against an older/smaller active set no longer matches.
    """
    bindings = [
        {
            "kind": item.get("kind"),
            "failureId": item.get("failureId"),
            "fingerprint": item.get("fingerprint"),
            "trigger": item.get("trigger"),
        }
        for item in active
    ]
    blob = json.dumps(bindings, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


def _receipt_hash(session_id: str, entry: Dict[str, Any]) -> Optional[str]:
    token = read_session_token(session_id)
    if token is None:
        return None
    payload = {k: v for k, v in entry.items() if k != "receiptHash"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(token.encode("utf-8"), blob, hashlib.sha256).hexdigest()


def receipt_clears(session_id: str, entry: Dict[str, Any], active: List[Dict[str, Any]]) -> bool:
    """A receipt clears the active set only if all three bindings hold: correct HMAC,
    correct session, and the digest of the exact active set it claims to discharge."""
    supplied = entry.get("receiptHash")
    expected = _receipt_hash(session_id, entry)
    if not isinstance(supplied, str) or expected is None:
        return False
    return (
        hmac.compare_digest(supplied, expected)
        and entry.get("sessionHash") == _session_hash(session_id)
        and entry.get("checkpointDigest") == checkpoint_digest(active)
    )


# --------------------------------------------------------------------------- reduction


def active_entries(session_id: str) -> List[Dict[str, Any]]:
    """Pure reduction: attempted failures and explicit triggers since the last VALID
    receipt, minus anything retracted as a non-attempt."""
    active: List[Dict[str, Any]] = []
    for item in entries(session_id):
        kind = item.get("kind")
        if kind == "reflection-receipt":
            if receipt_clears(session_id, item, active):
                active = []
        elif kind == "task-failure" and item.get("attempted") is not False:
            active.append(item)
        elif kind == "reflection-trigger":
            active.append(item)
        elif kind == "failure-disposition" and item.get("disposition") == "non-attempt":
            active = [c for c in active if c.get("failureId") != item.get("failureId")]
    return active


def pending_checkpoint(session_id: str) -> Optional[Dict[str, Any]]:
    """The checkpoint currently owed, or None.

    Rule: an explicit trigger always wins and is `deep`. Otherwise >=2 active failures
    raise a checkpoint - `deep`/`repeated-fingerprint` when every fingerprint is
    identical (the same wrong idea, twice), else `task`/`second-failure`.
    """
    active = active_entries(session_id)
    explicit = None
    for item in reversed(active):
        if item.get("kind") == "reflection-trigger":
            explicit = item
            break
    fingerprints = [str(item.get("fingerprint", "manual")) for item in active]
    if explicit is not None:
        return {
            "depth": "deep",
            "trigger": explicit["trigger"],
            "failureFingerprints": sorted(set(fingerprints)),
            "attemptCount": len(active),
        }
    if len(active) < 2:
        return None
    same = len(set(fingerprints)) == 1
    return {
        "depth": "deep" if same else "task",
        "trigger": "repeated-fingerprint" if same else "second-failure",
        "failureFingerprints": sorted(set(fingerprints)),
        "attemptCount": len(active),
    }


def learning_loop_pending(session_id: str) -> bool:
    """True when this session mutated or delivered something and routed no learning.

    `nothing-durable` is a valid routing - it just has to be *stated* in a receipt.
    """
    recorded = entries(session_id)
    mutated = any(
        item.get("kind") == "task-activity" and item.get("activity") == "mutation-or-delivery"
        for item in recorded
    )
    if not mutated:
        return False
    routed = any(
        item.get("kind") == "reflection-receipt"
        and item.get("durableDisposition") in DISPOSITIONS
        for item in recorded
    )
    return not routed


def _validate_receipt_shape(receipt: Dict[str, Any]) -> None:
    unknown = set(receipt) - RECEIPT_FIELDS
    if unknown:
        raise ValueError("receipt contains unknown fields: " + ", ".join(sorted(unknown)))
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("schemaVersion must be %d" % SCHEMA_VERSION)


def record_receipt(
    session_id: str, receipt: Dict[str, Any], session_token: str
) -> Dict[str, Any]:
    """Validate and append a reflection receipt. Raises ValueError on every refusal."""
    expected_token = read_session_token(session_id)
    if expected_token is None or not hmac.compare_digest(expected_token, str(session_token)):
        raise ValueError("session token is missing or invalid")
    _validate_receipt_shape(receipt)
    checkpoint = pending_checkpoint(session_id)
    trigger = str(receipt.get("trigger", ""))
    if trigger not in TRIGGERS:
        raise ValueError("trigger %r is not one of: %s" % (trigger, ", ".join(sorted(TRIGGERS))))
    if checkpoint is None:
        if not learning_loop_pending(session_id):
            raise ValueError("no reflection checkpoint or learning-loop duty is pending")
        if trigger != "learning-loop":
            raise ValueError("a learning-loop duty must be discharged with trigger "
                             "'learning-loop'")
    elif trigger != checkpoint["trigger"]:
        raise ValueError("trigger %r does not match the pending checkpoint, which requires %r"
                         % (trigger, checkpoint["trigger"]))
    disposition = str(receipt.get("durableDisposition", ""))
    if disposition not in DISPOSITIONS:
        raise ValueError("durableDisposition %r is not one of: %s"
                         % (disposition, ", ".join(sorted(DISPOSITIONS))))
    compared = receipt.get("approachesCompared")
    if not isinstance(compared, list) or len(compared) < 2:
        raise ValueError("approachesCompared must contain at least two approaches")
    expected_fps = [] if checkpoint is None else checkpoint["failureFingerprints"]
    supplied_fps = receipt.get("failureFingerprints", expected_fps)
    if not isinstance(supplied_fps, list) or sorted(supplied_fps) != sorted(expected_fps):
        raise ValueError("failureFingerprints must equal %s exactly (got %s)"
                         % (json.dumps(sorted(expected_fps)), json.dumps(supplied_fps)))
    active = active_entries(session_id)
    entry: Dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "reflection-receipt",
        "sessionHash": _session_hash(session_id),
        "checkpointDigest": checkpoint_digest(active),
        "taskId": _safe_text("taskId", receipt.get("taskId")),
        "trigger": trigger,
        "failureFingerprints": sorted(supplied_fps),
        "failedAssumption": _safe_text("failedAssumption", receipt.get("failedAssumption")),
        "approachesCompared": [_safe_text("approachesCompared", i) for i in compared],
        "chosenExperiment": _safe_text("chosenExperiment", receipt.get("chosenExperiment")),
        "proofCommandOrCheck": _safe_text(
            "proofCommandOrCheck", receipt.get("proofCommandOrCheck")
        ),
        "proofOutcome": _safe_text("proofOutcome", receipt.get("proofOutcome")),
        "durableDisposition": disposition,
        "observedAt": now_iso(),
    }
    changed = _safe_text("changedApproach", receipt.get("changedApproach"), required=False)
    if changed:
        entry["changedApproach"] = changed
    if entry["proofOutcome"].casefold() in {"pending", "unknown", "not run", "tbd", "n/a"}:
        raise ValueError("proofOutcome must describe a completed proof")
    if receipt.get("issue"):
        issue = str(receipt["issue"]).strip()
        if not re.match(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/\d+$", issue):
            raise ValueError("issue must be a GitHub issue URL")
        entry["issue"] = issue
    entry["receiptHash"] = _receipt_hash(session_id, entry)
    if not append_entry(session_id, entry):
        raise OSError("could not append reflection receipt")
    return entry


# --------------------------------------------------------------------------- duties


def duty_summary(session_id: str) -> Tuple[List[str], Dict[str, Any]]:
    """Human-readable unmet duties plus the machine state behind them."""
    checkpoint = pending_checkpoint(session_id)
    duties: List[str] = []
    if checkpoint is not None:
        duties.append(
            "REFLECTION (%s / %s): %d active failure(s), fingerprints %s. "
            "Diagnose, compare >=2 approaches, then append a receipt." % (
                checkpoint["depth"], checkpoint["trigger"], checkpoint["attemptCount"],
                ",".join(checkpoint["failureFingerprints"]),
            )
        )
    if learning_loop_pending(session_id):
        duties.append(
            "LEARNING LOOP: this session mutated or delivered and routed no learning. "
            "'nothing-durable' is a valid answer - record it in a receipt."
        )
    return duties, {"checkpoint": checkpoint}


_TEXT_RULES = (
    "Every text field is ONE line of at most %d characters of plain prose: absolute\n"
    "paths, hex digests and long underscore-free identifiers are refused as path- or\n"
    "credential-shaped, so describe them in words instead of pasting them.\n"
    % _SAFE_TEXT_MAX
)


def receipt_instructions(session_id: Optional[str] = None) -> str:
    """The demand, SELF-DESCRIBING when the session is known.

    Without the session it can only say `inbox-<session-key>.json`; a 2026-09-05 session
    read that as the raw session id, then hit three trigger refusals in a row, each one a
    Write+run cycle -- because the key is a hash, the required trigger is whatever the
    pending checkpoint says, and the fingerprint list must match exactly, and none of
    that was written down where the writer could see it. With the session id every one
    of those values is printed verbatim, so a correct receipt takes one attempt.
    """
    steps = (
        "Clear it in two steps (this route keeps receipt free text OUT of any shell\n"
        "command line, so command-guard.sh cannot refuse a receipt that legitimately\n"
        "mentions subprocess.run, os.system( or __import__():\n"
    )
    if session_id and valid_session(session_id):
        checkpoint = pending_checkpoint(session_id)
        trigger = checkpoint["trigger"] if checkpoint else "learning-loop"
        fps = checkpoint["failureFingerprints"] if checkpoint else []
        try:
            path = str(inbox_path(session_id))
        except Exception:  # noqa: BLE001 - the demand must never itself fail
            path = ".claude/reflection/inbox-<session-key>.json"
        return (
            steps
            + "  1. Write the JSON payload to EXACTLY this path with the Write tool\n"
            + "     (it stays writable while a checkpoint is pending):\n"
            + "     %s\n" % path
            + "  2. python3 .claude/hooks/reflection.py receipt --session-id %s "
              "--session-token <token> --inbox\n" % session_id
            + "Required fields and the values THIS checkpoint requires:\n"
            + "  schemaVersion: %d\n" % SCHEMA_VERSION
            + "  trigger: %r  (the only value accepted right now)\n" % trigger
            + "  failureFingerprints: %s  (must match exactly)\n" % json.dumps(fps)
            + "  durableDisposition: one of %s\n" % ", ".join(sorted(DISPOSITIONS))
            + "  plus taskId, failedAssumption, approachesCompared (>=2), "
              "chosenExperiment, proofCommandOrCheck, proofOutcome.\n"
            + "  optional: %s. Any OTHER field is refused.\n"
              % ", ".join(sorted(RECEIPT_OPTIONAL_FIELDS))
            + _TEXT_RULES
            + "If a /goal is set and the remaining step is human-only, run /goal clear: "
              "the goal loop cannot be satisfied by waiting."
        )
    return (
        steps
        + "  1. Write the JSON payload to .claude/reflection/inbox-<session-key>.json\n"
        "     using the Write tool (this exact path stays writable while a checkpoint\n"
        "     is pending).\n"
        "  2. python3 .claude/hooks/reflection.py receipt --session-id <id> "
        "--session-token <token> --inbox\n"
        "Required receipt fields: schemaVersion, taskId, trigger, failureFingerprints, "
        "failedAssumption, approachesCompared (>=2), chosenExperiment, "
        "proofCommandOrCheck, proofOutcome, durableDisposition. "
        "'nothing-durable' is a valid durableDisposition. "
        "Optional: " + ", ".join(sorted(RECEIPT_OPTIONAL_FIELDS))
        + ". Any OTHER field is refused.\n"
        + _TEXT_RULES.rstrip("\n")
    )


# --------------------------------------------------------------------------- CLI


def _emit(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ClaudeKit reflection ledger")
    sub = parser.add_subparsers(dest="operation")

    trig = sub.add_parser("trigger", help="record an explicit reflection trigger")
    trig.add_argument("--session-id", required=True)
    trig.add_argument("--trigger", required=True,
                      choices=sorted(TRIGGERS - {"learning-loop"}))
    trig.add_argument("--fingerprint", default="manual")

    rec = sub.add_parser("receipt", help="append a validated reflection receipt")
    rec.add_argument("--session-id", required=True)
    rec.add_argument("--session-token", required=True)
    group = rec.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", dest="receipt_json")
    group.add_argument("--file", type=Path)
    group.add_argument(
        "--inbox", action="store_true",
        help="read the payload from .claude/reflection/inbox-<session>.json (written "
             "with the Write tool) so no receipt free text ever enters a shell command",
    )
    group.add_argument(
        "--json-stdin", action="store_true", dest="json_stdin",
        help="read the payload from stdin. For direct/programmatic use only: a Bash call "
             "made through the PreToolUse gate cannot reach it, because is_receipt_cli() "
             "refuses '<' and so a heredoc never parses. Use --inbox from an agent.",
    )

    non = sub.add_parser("non-attempt", help="retract a setup/probe failure")
    non.add_argument("--session-id", required=True)
    non.add_argument("--failure-id", required=True)
    non.add_argument("--reason", required=True, choices=sorted(NON_ATTEMPT_REASONS))

    # Not named `stat`: that would shadow the `stat` module imported above.
    stat_p = sub.add_parser("status", help="print pending duties for a session")
    stat_p.add_argument("--session-id", required=True)

    args = parser.parse_args(argv)
    if not args.operation:
        parser.print_help(sys.stderr)
        return 2

    if args.operation == "status":
        duties, state = duty_summary(args.session_id)
        return _emit({"duties": duties, "checkpoint": state["checkpoint"]})

    if args.operation == "trigger":
        try:
            ok = record_trigger(args.session_id, args.trigger, args.fingerprint)
        except ValueError as err:
            print("reflection: %s" % err, file=sys.stderr)
            return 2
        return _emit({"recorded": ok, "trigger": args.trigger})

    if args.operation == "non-attempt":
        try:
            ok = mark_non_attempt(args.session_id, args.failure_id, args.reason)
        except ValueError as err:
            print("reflection: %s" % err, file=sys.stderr)
            return 2
        return _emit({"recorded": ok, "failureId": args.failure_id})

    inbox = inbox_path(args.session_id)
    try:
        # The CLI - never the PreToolUse gate - owns creating this directory. A blocking
        # gate must have no filesystem side effects, especially on the deny path.
        inbox.parent.mkdir(parents=True, exist_ok=True)
        if args.receipt_json is not None:
            rendered = args.receipt_json
        elif args.json_stdin:
            rendered = sys.stdin.read()
        elif args.inbox:
            rendered = inbox.read_text(encoding="utf-8")
        else:
            rendered = args.file.read_text(encoding="utf-8")
        payload = json.loads(rendered)
        if not isinstance(payload, dict):
            raise ValueError("receipt payload must be a JSON object")
        entry = record_receipt(args.session_id, payload, args.session_token)
    except (OSError, TypeError, ValueError) as err:
        print("reflection: receipt refused - %s" % err, file=sys.stderr)
        return 2
    if args.inbox:
        # Consume the drop box so a stale payload can never be replayed by accident.
        try:
            inbox.unlink()
        except OSError:
            pass
    return _emit(entry)


if __name__ == "__main__":
    raise SystemExit(main())

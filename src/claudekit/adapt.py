"""`ck adapt` — configure ClaudeKit for the project it is pointed at.

This module is COMPOSITION. Profile resolution lives in :mod:`claudekit.profiles`,
the MCP budget in :mod:`claudekit.mcp`, evidence hashing in :mod:`claudekit.memory`,
the installer in ``install.sh``, and the ownership receipt in
``cli/main.py._classify_manifest``. Nothing here reimplements any of them; where a
rule already exists this file calls it and states which one.

Two ownership classes, because one rule cannot serve both
--------------------------------------------------------
An earlier design applied a single receipt rule to every file it writes. It refused
on every already-adopted project and no-op'd on every fresh one. The boundary is not
the file's NAME, it is whether the kit owns the file WHOLE or in PART:

* **Class 1 — whole-file kit-owned.** Every key in the receipt's ``files`` map minus
  the Class 2 members that are receipted. A COMPLEMENT, never an enumeration: the
  receipt walk (``install.sh``) records everything under ``.claude/`` except
  ``NEVER_MANAGED`` and ``.pyc``, so any hand-written membership list drifts out of
  step with it the moment that walk changes. Drawing it as ``MANAGED_DIRS`` minus
  ``DIFF_IGNORED`` left ``settings.json``, ``local/CONSTITUTION.md``, ``profiles/**``
  and ``knowledge/issues/README.md`` receipted but in NEITHER class.
* **Class 2 — partially kit-owned.** Two receipted members
  (``local/CLAUDE.project.md``, ``hooks/config.json``) and two unreceipted artifacts
  (``.mcp.json``, the memory store). Each has a bounded mechanism: a marked region,
  a key subtree, and two APIs that already refuse before writing.

The ownership class lives HERE, in code, never in the receipt. A ``"partial": true``
flag beside the hash fails three ways: it breaks ``_classify_manifest``'s string
compare so every Class 2 file reads ``modified`` forever; ``ck uninstall --force``
ignores per-entry skips because ``removable`` is every listed path that exists; and
the installer rebuilds ``files`` from a bare walk, so any update silently discards
the flag and regains delete rights.

Fail-closed, everywhere
-----------------------
No usable receipt is a REFUSAL, not a licence. ``_load_manifest`` returns ``None`` for
an absent receipt and an unparseable one alike, so without that rule the Class 1
complement is the EMPTY set and adapt would write into a tree of entirely unknown
provenance — refusing nowhere precisely where provenance is least known.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

#: Class 2 members that carry a receipt. Kept beside the ownership constants in
#: cli/main.py (PARTIAL_OWNED) and duplicated nowhere else.
#:
#: `local/CONSTITUTION.md` is the odd one: `ck adapt` writes into NEITHER a marked region
#: nor a key of it, so "partial" understates the kit's distance from it -- the installer
#: seeds it once and every line after that is the project's. It is listed here anyway
#: because this set is what the deletion paths consult: `cmd_uninstall` builds `removable`
#: from `unchanged`, and a preserved-but-never-edited CONSTITUTION.md hashes as `unchanged`
#: against the manifest written just after it was preserved. Without this entry the
#: installer would stop overwriting a project's constitution while `ck uninstall` went on
#: silently deleting it, under a prompt that never says the file was customized.
PARTIAL_OWNED_RELS = ("local/CLAUDE.project.md", "local/CONSTITUTION.md",
                      "hooks/config.json")

#: The region `ck adapt` owns inside .claude/local/CLAUDE.project.md.
REGION_ID = "PROJECT-ADAPT"
REGION_VERSION = 1

_MARKER_OPEN = "<!-- CLAUDEKIT:"
_START_SUFFIX = "START -->"
_END_SUFFIX = "END -->"
#: A fence OPENER: at most three leading spaces (four makes it literal text in
#: CommonMark, not a fence), then three or more backticks or tildes.
_FENCE_OPEN = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: The four keys adapt owns inside hooks/config.json's `project` subtree, and
#: nothing else. Mirrors install.sh's own setdefault-then-assign shape.
COMMAND_KEYS = ("build_cmd", "test_cmd", "lint_cmd", "coverage_cmd")


class AdaptError(Exception):
    """A refusal. The message names the file and the cause."""


# --------------------------------------------------------------------------- markers

class Region:
    """A parsed marked region: the line span it occupies and its declared version."""

    __slots__ = ("start", "end", "version")

    def __init__(self, start: int, end: int, version: Optional[int]):
        self.start, self.end, self.version = start, end, version


def _marker_id_and_version(line: str, suffix: str) -> Optional[Tuple[str, Optional[int]]]:
    """Tokenize one marker line, or None if it is not one.

    Line-STRUCTURED, not a regex over the user's prose. "Exact literal" cannot be
    taken literally because the version lives inside the marker, and a stale version
    has to be detectable before it is known. So: require the open and the suffix,
    then read an id and an OPTIONAL `vN` from between them.

    The version is optional on BOTH markers, symmetrically. Requiring it on START had
    a bug in it: a legacy region written without one would not be recognised as a
    region at all, and would collect a SECOND appended region on every run — the
    exact idempotence failure the concession exists to prevent.
    """
    stripped = line.strip()
    if not stripped.startswith(_MARKER_OPEN) or not stripped.endswith(suffix):
        return None
    inner = stripped[len(_MARKER_OPEN):-len(suffix)].strip()
    if not inner:
        return None
    parts = inner.split()
    ident = parts[0]
    version: Optional[int] = None
    if len(parts) == 2 and re.fullmatch(r"v\d+", parts[1]):
        version = int(parts[1][1:])
    elif len(parts) != 1:
        return None
    return ident, version


def fenced_lines(lines: Sequence[str]) -> FrozenSet[int]:
    """0-based indices of every line inside a CLOSED fenced code block.

    A bare ``in_fence = not in_fence`` toggle was wrong in two ways and both were
    measured through the CLI. One unmatched ``` desynchronises it for the rest of
    the file, so every marker below reads "fenced" — INCLUDING the region adapt
    itself had just written, so adapt appended a NEW region on every run
    (1 -> 2 -> 3 regions across three runs). And a four-space-indented ``` is
    literal text in CommonMark, yet a naive toggle flips on it too.

    So an opener needs at most three leading spaces, and its closer must use the
    SAME character, be at least as long, carry no info string, and also be indented
    at most three. An UNTERMINATED fence is NOT a fence: swallowing the rest of the
    file is precisely the failure above, so scanning resumes on the line after the
    false opener and a balanced pair further down is still recognised.
    """
    fenced: List[int] = []
    index, total = 0, len(lines)
    while index < total:
        opener = _FENCE_OPEN.match(lines[index].rstrip("\r\n"))
        if opener is None:
            index += 1
            continue
        fence = opener.group("fence")
        char, length = fence[0], len(fence)
        if char == "`" and "`" in opener.group("info"):
            # A backtick info string may not contain a backtick, so this is not an
            # opener at all — it is a longer run of backticks read wrongly.
            index += 1
            continue
        close = None
        for probe in range(index + 1, total):
            candidate = _FENCE_OPEN.match(lines[probe].rstrip("\r\n"))
            if (candidate is not None
                    and candidate.group("fence")[0] == char
                    and len(candidate.group("fence")) >= length
                    and not candidate.group("info").strip()):
                close = probe
                break
        if close is None:
            index += 1
            continue
        fenced.extend(range(index, close + 1))
        index = close + 1
    return frozenset(fenced)


def find_region(text: str, region_id: str = REGION_ID) -> Tuple[Optional[Region], List[int]]:
    """Locate `region_id`'s region. Returns (region_or_None, fenced_line_numbers).

    Raises AdaptError on a malformed shape — unterminated, an END before its START,
    or a second START — because a parser that does its best on a malformed region is
    how a user's prose gets eaten.

    Markers inside a fenced code block are SKIPPED, not refused. This repo's own docs
    quote these markers verbatim, and refusing on a fenced START carrying adapt's own
    id would brick the verb permanently for that project with no recovery path the
    user could discover. Their line numbers are returned so the report can say they
    were recognised and deliberately ignored.

    Every other `CLAUDEKIT:`-prefixed comment is ignored outright. All eleven
    `templates/*/CLAUDE.md` carry a different dialect
    (`<!-- CLAUDEKIT:PARALLEL-AGENTS-POLICY v1 -->` … `<!-- /CLAUDEKIT:… -->`) and
    those templates are what the installer renders into a target, so a parser that
    claimed every such comment would refuse on every fresh install.
    """
    region: Optional[Region] = None
    start_idx: Optional[int] = None
    start_version: Optional[int] = None
    fenced: List[int] = []
    lines = text.splitlines()
    inside = fenced_lines(lines)

    for idx, line in enumerate(lines):
        opened = _marker_id_and_version(line, _START_SUFFIX)
        closed = _marker_id_and_version(line, _END_SUFFIX)
        marker = opened if opened is not None else closed
        if marker is None:
            continue
        if marker[0] != region_id:
            continue
        if idx in inside:
            fenced.append(idx + 1)
            continue
        if opened is not None:
            if start_idx is not None:
                raise AdaptError(
                    f"region {region_id!r}: a second START at line {idx + 1} while the "
                    f"one at line {start_idx + 1} is still open")
            if region is not None:
                raise AdaptError(
                    f"region {region_id!r}: more than one region in the file "
                    f"(second START at line {idx + 1})")
            start_idx, start_version = idx, opened[1]
        else:
            if start_idx is None:
                raise AdaptError(
                    f"region {region_id!r}: END at line {idx + 1} with no START before it")
            region = Region(start_idx, idx, start_version if start_version is not None
                            else marker[1])
            start_idx, start_version = None, None

    if start_idx is not None:
        raise AdaptError(
            f"region {region_id!r}: START at line {start_idx + 1} is never closed")
    return region, fenced


def dominant_newline(text: str) -> str:
    """The file's prevailing line ending, so a CRLF file does not acquire mixed ones.

    A `\\r` before `-->` breaks a literal-anchor match, so a Windows checkout would
    collect a second appended region on every run. Tokenization strips it on read;
    this is the other half — the writer re-emits what the file already used.
    """
    crlf = text.count("\r\n")
    return "\r\n" if crlf and crlf >= (text.count("\n") - crlf) else "\n"


def render_region(body: str, region_id: str = REGION_ID,
                  version: int = REGION_VERSION) -> List[str]:
    """The marker block as lines. The writer always emits a version."""
    return ([f"{_MARKER_OPEN}{region_id} v{version} {_START_SUFFIX}"]
            + body.splitlines()
            + [f"{_MARKER_OPEN}{region_id} v{version} {_END_SUFFIX}"])


def apply_region(text: str, body: str, region_id: str = REGION_ID,
                 version: int = REGION_VERSION) -> Tuple[str, str, Optional[int]]:
    """Return (new_text, action, previous_version). Never rewrites outside the region.

    `action` is "replaced" or "appended". A file with no region gets one APPENDED —
    the bytes before it are preserved exactly, with no trailing-newline tidying,
    because those bytes are the user's.

    SPLICED, with ``keepends``, not decomposed and re-joined. The earlier revision
    did ``splitlines()`` then ``newline.join(...)``, which rewrote EVERY
    non-conforming line in a mixed-ending file — on the append path as well as the
    replace path — in a file whose stated contract is that outside the region is the
    user's and is never touched. Each untouched line now carries its own original
    terminator through verbatim; only the region's own slice is replaced.
    """
    region, _fenced = find_region(text, region_id)
    newline = dominant_newline(text)
    block = [line + newline for line in render_region(body, region_id, version)]
    lines = text.splitlines(keepends=True)

    if region is None:
        prefix = list(lines)
        if prefix:
            if not prefix[-1].endswith(("\n", "\r")):
                prefix[-1] = prefix[-1] + newline
            if prefix[-1].strip():
                prefix.append(newline)
        return "".join(prefix + block), "appended", None

    previous = region.version
    lines[region.start:region.end + 1] = block
    return "".join(lines), "replaced", previous


def write_atomic(path: Path, text: str) -> None:
    """Write via a same-directory temp file and os.replace.

    Non-negotiable: this writes into other people's repositories, so an interrupted
    or concurrent run must not be able to leave a half-written file. The temp file is
    removed if the replace fails, so no `.tmp` residue survives a failure either.
    """
    path = Path(path)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=str(path.parent),
        prefix=path.name + ".", suffix=".tmp", delete=False)
    tmp = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        # `tempfile` creates at 0600. Replacing a 0644 file with it would silently
        # narrow the target's mode, so carry the existing mode across; a file that
        # does not exist yet keeps the umask default.
        try:
            existing = os.stat(str(path)).st_mode
        except OSError:
            existing = None
        if existing is not None:
            os.chmod(str(tmp), existing & 0o7777)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def read_text_strict(path: Path) -> str:
    """Read with an explicit encoding, and fail closed on prose we cannot decode.

    Locale-dependent decoding is what made a hook crash on one invalid byte earlier
    in this repo's history; an undecodable target here is a refusal, never a partial
    write.

    BYTES, then decode. `Path.read_text` opens in text mode, so universal-newline
    translation turned every `\r\n` into `\n` before the writer ever saw it -- which
    defeated the keepends splice in `apply_region` entirely and rewrote the endings of
    lines outside the region, the exact contract violation that splice exists to
    prevent. A CRLF-only file merely looked correct because it was normalised
    consistently; a MIXED file exposed it.
    """
    try:
        return Path(path).read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdaptError(f"{path}: not valid UTF-8 ({exc}); refusing to write") from exc


# ------------------------------------------------------------------------- detection

#: Where a command may be discovered, in CI-first order: what CI actually runs beats
#: what a Makefile claims, which beats what docs claim. Mirrors the ordering the
#: project-adaptation skill already prescribes, so the verb and the prompt agree.
DETECT_ORDER = (
    ".github/workflows",
    "Makefile",
    "package.json",
    "pyproject.toml",
    "tox.ini",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Gemfile",
)

#: How a discovered command line is assigned to one of the four keys. ORDER IS
#: LOAD-BEARING and each entry is here because a shorter list got it wrong: a
#: coverage command almost always contains "test", and a lint command frequently
#: does too ("npm run lint:test"), so the narrower kinds must win before "test".
_CMD_HINTS = (
    ("coverage_cmd", ("--cov", "coverage", "nyc ", "jacoco", "-cover")),
    ("lint_cmd", ("lint", "ruff", "flake8", "eslint", "clippy", "go vet", "gofmt",
                  "checkstyle", "--check", "mypy", "tsc --noemit")),
    ("test_cmd", ("pytest", "go test", "cargo test", "jest", "vitest", "rspec",
                  "tox", "test")),
    ("build_cmd", ("compileall", "cargo build", "go build", "tsc", "webpack",
                   "gradle build", "package", "compile", "build")),
)

#: A `run:` scalar on one line, and the block-scalar header that opens a multi-line
#: one. Text scanning, not YAML parsing: stdlib only, and a partial read of a
#: workflow is exactly as much as detection is allowed to conclude from.
_RUN_INLINE = re.compile(r"^\s*(?:-\s+)?run:\s*(?![|>])(?P<cmd>\S.*?)\s*$")
_RUN_BLOCK = re.compile(r"^(?P<indent>\s*)(?:-\s+)?run:\s*[|>][-+0-9]*\s*$")

#: Provisioning, not the thing being provisioned. Every entry here was measured:
#: against this repo's own workflows the unfiltered scan returned
#: `pip install --require-hashes -r tests/requirements.txt` as the TEST command
#: (it contains "test") and `pip install ruff mypy` as the LINT command. A
#: dependency install is setup; it is never the project's build, test or lint.
_INSTALL_NOISE = (
    "pip install", "pipx ", "poetry install", "npm ci", "npm install", "yarn install",
    "pnpm install", "bundle install", "apt-get", "apt ", "brew ", "cargo install",
    "go install", "uv pip", "uv sync", "gem install", "curl ", "wget ",
    "actions/", "python -m build", "-m pip",
)

#: Stripped from the FRONT before classification, never used to reject: `cd web &&
#: npm test` is a real test command and rejecting the whole line on its `cd` would
#: lose it. Prefix removal and rejection are different jobs.
_PREFIX_NOISE = re.compile(r"^(?:set\s+-[a-z]+\s*;?\s*|cd\s+[^;&|]+(?:&&|;)\s*)+")

#: A DERIVED command carrying any of these is refused rather than written. Adapt
#: writes into `hooks/config.json`, and pre-commit / pre-push / post-implement
#: EXECUTE what is in there -- so a `run:` string in the target repository is
#: attacker-controlled input to a shell that fires on the user's next push. Measured:
#: `run: pytest ; touch /tmp/PWNED_BY_ADAPT` was derived and written verbatim.
#: Detection still executed nothing (the sentinel was never created), and the report
#: still named the command, but a report is read once and a hook runs every time.
#:
#: EVERY value adapt writes is screened for shell COMPOSITION, whatever its source.
#: Stated narrowly on purpose (hard rule 6): this is not a sandbox and it does not
#: make a hostile command safe. `build_cmd = "python3 .evil.py"` carries no
#: metacharacter, passes, and a hook will run it -- an adversarial reviewer measured
#: exactly that. What the screen buys is that a command cannot smuggle a SECOND
#: action past the one the report shows the user, which is the difference between a
#: value they can audit and one they cannot. Screening writes through
#: `CommandValidator` is filed as a follow-up, not claimed here. An earlier revision
#: exempted profile values on the premise that "a profile ships with the kit and is
#: not attacker-controlled". **That premise was false and an adversarial reviewer
#: proved it end to end.** `profiles.profiles_dir` resolves
#: `<TARGET>/.claude/profiles`, so a profile is a file in the repository being
#: adapted, and a NEW one is unreceipted -- `_classify_manifest` reports only
#: MODIFIED receipted files, so the Class 1 pre-flight cannot see it and refuses
#: nothing. Measured: a `typescript/profile.json` carrying
#: `npm run build; python3 -c "open('/tmp/PWNED_PROFILE','w').write('x')"` reached
#: `hooks/config.json`, and `post-implement.sh` ran it. The exemption also had a
#: GREEN TEST asserting it, which is worse than no test.
#:
#: The cost is nil: every shipped profile value is metacharacter-free. A profile that
#: genuinely needs composition (`cd web && npm test`) is refused BY NAME rather than
#: silently rewritten, and the user can set the key directly in `hooks/config.json`,
#: which adapt now preserves.
_SHELL_METACHARS = (";", "|", "&", "`", "$(", ">", "<", "\n", "\r")

#: How far into a command line an install marker still means "this is provisioning".
#: `python -m pip install --upgrade build` puts it at column 10, so a window keyed to
#: the marker's own length missed it and shipped a pip invocation as `build_cmd`.
_NOISE_WINDOW = 40

#: A Makefile target, ignoring pattern rules and variable assignments.
_MAKE_TARGET = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)")

_STACK_BY_MARKER = (
    ("pyproject.toml", "python"),
    ("tox.ini", "python"),
    ("package.json", "typescript"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
)


def unsafe_to_write(command: str) -> Optional[str]:
    """The metacharacter that makes `command` unfit to write, or None.

    Named rather than boolean so the report can say WHICH character stopped it: a
    refusal a user cannot act on is barely better than a silent write.
    """
    for char in _SHELL_METACHARS:
        if char in command:
            return char
    return None


def classify_command(line: str) -> Optional[str]:
    """Which of the four keys a discovered command line belongs to, or None."""
    lowered = " " + line.strip().lower() + " "
    for key, hints in _CMD_HINTS:
        for hint in hints:
            if hint in lowered:
                return key
    return None


def _workflow_commands(path: Path) -> Dict[str, str]:
    """Commands CI actually runs, read out of one workflow file. Executes nothing."""
    found: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return found
    index = 0
    while index < len(lines):
        block = _RUN_BLOCK.match(lines[index])
        if block is not None:
            depth = len(block.group("indent"))
            index += 1
            pending = ""
            while index < len(lines):
                body = lines[index]
                if body.strip() and (len(body) - len(body.lstrip())) <= depth:
                    break
                stripped = body.strip()
                # A shell line continued with a trailing backslash is ONE command.
                # Split, `--cov=src/... \` was read as a whole coverage command and
                # the pytest invocation it belongs to was never seen.
                if stripped.endswith("\\"):
                    pending += stripped[:-1].rstrip() + " "
                    index += 1
                    continue
                _record(found, pending + stripped)
                pending = ""
                index += 1
            if pending:
                _record(found, pending)
            continue
        inline = _RUN_INLINE.match(lines[index])
        if inline is not None:
            _record(found, inline.group("cmd"))
        index += 1
    return found


def _record(found: Dict[str, str], raw: str) -> None:
    """Assign one command line to its key, first writer wins."""
    command = raw.strip().strip("'\"")
    if not command or command.startswith("#") or command.startswith("-"):
        return
    command = _PREFIX_NOISE.sub("", command).strip()
    if not command:
        return
    lowered = command.lower()
    if any(marker in lowered[:_NOISE_WINDOW] for marker in _INSTALL_NOISE):
        return
    key = classify_command(command)
    if key is not None and key not in found:
        found[key] = command


def _commands_from(target: Path, rel: str) -> Dict[str, str]:
    """Every command derivable from ONE evidence source. Reads; never executes."""
    path = target / rel
    found: Dict[str, str] = {}
    if rel == ".github/workflows":
        for child in sorted(list(path.glob("*.yml")) + list(path.glob("*.yaml"))):
            for key, value in _workflow_commands(child).items():
                found.setdefault(key, value)
        return found
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found
    if rel == "Makefile":
        targets = {m.group("name") for m in
                   (_MAKE_TARGET.match(line) for line in text.splitlines())
                   if m is not None}
        for key in COMMAND_KEYS:
            name = key[:-4]
            if name in targets:
                found[key] = "make " + name
    elif rel == "package.json":
        try:
            scripts = json.loads(text).get("scripts")
        except (ValueError, AttributeError):
            scripts = None
        if isinstance(scripts, dict):
            for key in COMMAND_KEYS:
                name = key[:-4]
                if name in scripts:
                    found[key] = "npm test" if name == "test" else "npm run " + name
    elif rel == "pyproject.toml":
        # Evidence-driven, never a guess: a tool is claimed only where the project
        # configures it. Shipping ClaudeKit's own pytest/ruff invocation into a
        # stranger's push hook is the failure install.sh:542-563 exists to avoid.
        if "[tool.pytest" in text:
            found["test_cmd"] = "python3 -m pytest -q"
        if "[tool.ruff" in text:
            found["lint_cmd"] = "ruff check ."
        if "[tool.coverage" in text:
            found["coverage_cmd"] = "python3 -m pytest -q --cov"
    elif rel == "tox.ini":
        found["test_cmd"] = "tox"
    elif rel == "Cargo.toml":
        found.update(build_cmd="cargo build", test_cmd="cargo test",
                     lint_cmd="cargo clippy")
    elif rel == "go.mod":
        found.update(build_cmd="go build ./...", test_cmd="go test ./...",
                     lint_cmd="go vet ./...")
    elif rel == "pom.xml":
        found.update(build_cmd="mvn -q -DskipTests package", test_cmd="mvn -q test")
    elif rel == "build.gradle":
        found.update(build_cmd="gradle build", test_cmd="gradle test")
    return found


class Detection:
    """What was found, and where from. Never what was RUN."""

    __slots__ = ("stack", "sources", "has_git", "dirty", "commands", "command_sources",
                 "refused")

    def __init__(self, stack: Optional[str], sources: Dict[str, str],
                 has_git: bool, dirty: Optional[bool],
                 commands: Optional[Dict[str, str]] = None,
                 command_sources: Optional[Dict[str, str]] = None,
                 refused: Optional[Dict[str, str]] = None):
        self.stack, self.sources = stack, sources
        self.has_git, self.dirty = has_git, dirty
        #: key -> command line, and key -> the evidence source it came from. Two
        #: maps rather than one of pairs, so `region_body` and `apply_commands` can
        #: take the plain command map every other caller already expects.
        self.commands = dict(commands or {})
        self.command_sources = dict(command_sources or {})
        #: key -> the reason a derived command was NOT written. Carried so the report
        #: names it: a command dropped without a reason reads as "none was found",
        #: which is a different fact.
        self.refused = dict(refused or {})


def vcs_dirty(target: Path) -> Optional[bool]:
    """Whether the checkout has uncommitted changes; None when that is unknowable.

    Deliberately NOT inside :func:`detect`. Detection's contract is that it executes
    NOTHING, and this runs `git`. It is a fixed VCS query rather than a command
    discovered in the target — it can create no file and run no stranger's script —
    but it is still an execution, so it sits on the far side of that line where a
    reader can see which one it is.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(target), "status", "--porcelain"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return bool(proc.stdout.strip())


def detect(target: Path) -> Detection:
    """Read-only inspection of files on disk. Executes NOTHING.

    A discovered command is reported with its provenance so a wrong guess is visible
    rather than run. This is the whole reason detection is separate from application:
    running a stranger's `Makefile` target to find out what it does is not detection.
    """
    target = Path(target)
    sources: Dict[str, str] = {}
    for rel in DETECT_ORDER:
        path = target / rel
        if path.is_dir():
            if any(path.glob("*.yml")) or any(path.glob("*.yaml")):
                sources[rel] = "present"
        elif path.is_file():
            sources[rel] = "present"

    stack: Optional[str] = None
    for marker, name in _STACK_BY_MARKER:
        if marker in sources:
            stack = name
            break

    # CI-first, and the ORDER of DETECT_ORDER is the whole rule: what CI actually
    # runs beats what a Makefile claims, which beats what a manifest claims. First
    # writer wins, per key, so a Makefile can still supply a key CI never mentions.
    commands: Dict[str, str] = {}
    command_sources: Dict[str, str] = {}
    refused: Dict[str, str] = {}
    for rel in DETECT_ORDER:
        if rel not in sources:
            continue
        for key, value in _commands_from(target, rel).items():
            if key in commands or key in refused:
                continue
            char = unsafe_to_write(value)
            if char is not None:
                refused[key] = (
                    "%s in %s contains %r, so it is shell composition rather than a "
                    "single command; refusing to write it into a file the hooks "
                    "execute" % (key, rel, char))
                continue
            commands[key] = value
            command_sources[key] = rel

    return Detection(stack=stack, sources=sources,
                     has_git=(target / ".git").exists(),
                     dirty=None, commands=commands,
                     command_sources=command_sources, refused=refused)


# ------------------------------------------------------------------------- ownership

class Ownership:
    """The receipt, split into the two classes, or the reason there is no split."""

    __slots__ = ("class1", "class2_receipted", "manifest")

    def __init__(self, class1: Sequence[str], class2_receipted: Sequence[str],
                 manifest: Dict[str, Any]):
        self.class1 = tuple(class1)
        self.class2_receipted = tuple(class2_receipted)
        self.manifest = manifest


def classify_ownership(manifest: Optional[Dict[str, Any]]) -> Ownership:
    """Split the receipt's `files` map into Class 1 and Class 2.

    Class 1 is the COMPLEMENT — every receipted key except the Class 2 members that
    carry a receipt. Stated as a complement because the receipt walk records
    everything under `.claude/` bar a small exclusion list, so any enumerated
    membership list drifts out of step with it the moment that walk changes.

    Manifest keys are relative to `.claude/`, so `.mcp.json` (project root) and the
    memory store are not in the key set at all and cannot be subtracted from it —
    Class 2 is two receipted members plus two unreceipted artifacts, not "three
    members".
    """
    if manifest is None:
        raise AdaptError(
            "no usable install receipt (.claudekit-manifest.json is absent or "
            "unparseable), so nothing here has known provenance")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise AdaptError(
            "the install receipt has no usable 'files' map, so nothing here has "
            "known provenance")
    partial = set(PARTIAL_OWNED_RELS)
    return Ownership(class1=sorted(set(files) - partial),
                     class2_receipted=sorted(set(files) & partial),
                     manifest=manifest)


def refuse_on_modified(modified: Sequence[str],
                       intended: Sequence[str]) -> Optional[str]:
    """The Class 1 pre-flight: a modified whole-file kit asset refuses the RUN.

    Not "skip that file". Mixed ownership means the tree's provenance is unknown, and
    a partial adapt over project-specific content is exactly what the fleet rule
    exists to prevent across the downstream repositories.
    """
    hit = sorted(set(modified) & set(intended))
    if not hit:
        return None
    return ("refusing: these kit-owned files differ from the install receipt, so "
            "this tree's provenance is unknown — " + ", ".join(hit))


# --------------------------------------------------------------- hooks/config.json

def apply_commands(text: str, commands: Dict[str, str]) -> Tuple[str, List[str]]:
    """Set adapt's four keys under `project`. Returns (new_text, keys_left_alone).

    The JSON analogue of a marked region, and the shape `install.sh` already uses:
    setdefault the subtree, assign the owned keys, re-emit everything else in value.
    Unknown keys are preserved rather than dropped, because they are the user's.
    Invalid JSON is a refusal, never a rewrite.

    A key adapt CANNOT evidence keeps whatever is already there. The earlier
    revision blanked it, and that was wrong twice over. `install.sh:495-497` writes
    all four keys EMPTY -- it never ships ClaudeKit's own `pytest`/`ruff` -- so on an
    adopted tree a non-empty value is the USER's, and blanking it destroyed their
    configuration on every run. Worse, `project-adaptation` Phase 2 explicitly tells
    the user to set the keys adapt could not derive, so the verb and the skill
    contradicted each other: the documented workflow was undone by the next run.
    Only an evidenced value overwrites; the rest are named in the report as kept.
    """
    try:
        config = json.loads(text) if text.strip() else {}
    except ValueError as exc:
        raise AdaptError(
            f"hooks/config.json is not valid JSON ({exc}); refusing to write") from exc
    if not isinstance(config, dict):
        raise AdaptError("hooks/config.json is not a JSON object; refusing to write")

    project = config.setdefault("project", {})
    if not isinstance(project, dict):
        raise AdaptError(
            "hooks/config.json 'project' is not an object; refusing to write")
    kept: List[str] = []
    for key in COMMAND_KEYS:
        value = commands.get(key)
        if value:
            project[key] = value
        elif project.get(key):
            kept.append(key)
        else:
            project[key] = ""
    return json.dumps(config, indent=2) + "\n", kept


# ----------------------------------------------------------------- report + orchestrate

#: A step's outcome. `skipped` is not a failure — it exits 0 with the reason named.
#: `failed` exits non-zero. The distinction is the whole honesty contract: a run that
#: could not wire MCP but did everything else must never read as "adapt complete".
DONE, SKIPPED, FAILED = "done", "skipped", "failed"


class Report:
    """What was detected, chosen, written, and skipped — and why, for each."""

    def __init__(self, target: Path, branch: str):
        self.target = Path(target)
        self.branch = branch
        self.steps: List[Tuple[str, str, str]] = []
        self.notes: List[str] = []

    def step(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append((name, status, detail))

    def note(self, text: str) -> None:
        self.notes.append(text)

    @property
    def failed(self) -> bool:
        return any(status == FAILED for _n, status, _d in self.steps)

    def render(self) -> str:
        width = max([len(n) for n, _s, _d in self.steps] + [4])
        lines = [f"ck adapt — {self.target} ({self.branch} tree)", ""]
        for name, status, detail in self.steps:
            suffix = f" — {detail}" if detail else ""
            lines.append(f"  {name.ljust(width)}  {status}{suffix}")
        if self.notes:
            lines.append("")
            lines.extend(f"  note: {n}" for n in self.notes)
        lines.append("")
        lines.append("FAILED — see the steps above" if self.failed
                     else "OK — every step either completed or is reported as skipped")
        return "\n".join(lines)


def is_fresh(target: Path) -> bool:
    """"Fresh" means `.claude/` does not exist. It NEVER means "no manifest".

    This distinction is load-bearing. A tree with a hand-made `.claude/agents/` and no
    receipt, routed to the installer on the strength of the missing manifest, is moved
    aside into `.claude.bak-*` with only a heuristic subset copied back — the worst
    outcome this design exists to prevent, reached through the branch that looks safe.
    Receipt-less trees WITH a `.claude/` are a refusal, not a fresh install.
    """
    return not (Path(target) / ".claude").exists()


def project_doc(target: Path) -> Path:
    """The one CLAUDE.md adapt owns: the kit-rendered, receipted project doc.

    Never the root `CLAUDE.md`. That is the project's front door, unreceipted by
    definition, and writing into it across the downstream repositories is precisely
    the risk the fleet rule exists to prevent.
    """
    return Path(target) / ".claude" / "local" / "CLAUDE.project.md"


def region_body(detection: Detection, profile_name: Optional[str],
                commands: Dict[str, str], *,
                stack_profile: Optional[str] = None,
                sources: Optional[Dict[str, str]] = None,
                mcp_budget: Optional[str] = None) -> str:
    """The prose adapt owns. Facts only — judgement belongs to the skill, not here.

    Every command carries the evidence it came from, because a wrong guess must be
    visible rather than run. `profile_name` is the POSTURE profile (hook enablement)
    and `stack_profile` the one that carries the MCP budget and the stack defaults;
    they are different axes and conflating them is what made the budget claim
    unfalsifiable.
    """
    provenance = dict(sources or getattr(detection, "command_sources", {}) or {})
    lines = ["", "<!-- Managed by `ck adapt`. Edit outside the markers, not inside. -->",
             ""]
    lines.append(f"- Detected stack: {detection.stack or 'none matched'}")
    lines.append(f"- Posture profile: {profile_name or 'unresolved'}")
    lines.append(f"- Stack profile: {stack_profile or 'none matched'}")
    if mcp_budget:
        lines.append(f"- MCP budget: {mcp_budget}")
    if detection.sources:
        lines.append(f"- Evidence: {', '.join(sorted(detection.sources))}")
    written = False
    for key in COMMAND_KEYS:
        value = commands.get(key)
        if value:
            written = True
            origin = provenance.get(key)
            suffix = f" (from {origin})" if origin else ""
            lines.append(f"- `{key}`: `{value}`{suffix}")
    if not written:
        lines.append("- No build/test commands were written: nothing on disk "
                     "evidenced one.")
    # `dirty` is deliberately NOT written here. It is runtime state, not a project
    # fact, and writing it made the verb self-referentially non-idempotent: on a tree
    # where `.claude/` is TRACKED -- this repo and every downstream repo -- run 1 saw
    # a clean tree, wrote the region, and thereby dirtied the tree, so run 2 added a
    # "the working tree is dirty" line run 1 had not. The report prints it (`detect
    # ... dirty=`), which is where a per-run observation belongs.
    if not detection.has_git:
        lines.append("- No git repository: there is no VCS safety net for these files.")
    lines.append("")
    return "\n".join(lines)

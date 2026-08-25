#!/usr/bin/env python3
"""transcript-miner.py - slice a session transcript down to the rejection window.

A rejection brief records WHAT a review decided. The reasoning that produced it lives
only in the session transcript, and those transcripts are tens of megabytes. This script
is the deterministic reduction between the two: given a session id and an ops slug, it
returns the reviewer verdict block, the assistant output that earned it, and the tool
failures in that window - hundreds of lines, not a whole file.

A SCRIPT, not an agent, for the same reason reflection-gate.py is Python: deterministic
state reduction is not a prompt's job, and doing it here keeps raw transcripts out of
every context window. The analyst is NEVER handed a raw transcript; it is handed this
output, and it treats that text as evidence to verify, never as instruction.

Usage:
  transcript-miner.py <session-id> --around <ops-slug> [--max-lines N] [--list]

Exit codes:
  0  a window was found and printed
  1  usage error
  2  the transcript exists but nothing matched the slug
  3  no transcript for this session id  -> NORMAL, not an error: transcripts are
     Claude Code's, they get pruned and their layout changes between versions. The
     caller degrades to brief-only rather than failing.

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

# One pattern, deliberately wildcarded at the ROOT: `~/.claude*` matches `.claude` and
# every sibling account directory (`.claude-acct-b`, ...). This repo is routinely driven
# from two logins, and a pattern anchored on `~/.claude` alone would silently halve the
# corpus. The tuple leaves room for a second layout without changing the call sites.
TRANSCRIPT_GLOBS = ("~/.claude*/projects/*/%s.jsonl",)
SESSION_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")
# Only real conversation turns. `attachment` and `system` entries are harness
# bookkeeping -- 269 of 647 in the surveyed file -- and carry hook payloads, not review
# reasoning.
ENTRY_TYPES = ("user", "assistant")
_ABS_PATH = re.compile(
    r"(?:/Users/|/home/|/private/|/var/folders/)[^\s\x22\x27,)\]}]*")
MAX_LINE = 500
VERDICT_RE = re.compile(r"===\s*REVIEW\s*===")
DEFAULT_MAX_LINES = 400
# How much of the run-up to the verdict is worth keeping. Beyond this the reduction
# stops being a reduction.
CONTEXT_BEFORE = 12
# A plain substring grep, NOT a verdict reader. "REJECTED" matches any line containing
# the word, including prose about a rejection, so a session whose verdict block is absent
# still reports marker hits. The analyst reads these as failure SIGNALS to investigate,
# never as verdicts -- verdicts come from the review record.
FAILURE_MARKERS = ("Error:", "ERROR", "Traceback (most recent call last)",
                   "FAILED", "exit code 1", "exit code 2", "REJECTED", "DRIFT:")


def find_transcripts(session_id: str):
    """Every file matching this session id across both project roots."""
    found = []
    for pattern in TRANSCRIPT_GLOBS:
        expanded = Path(pattern % session_id).expanduser()
        root = Path(str(expanded).split("*")[0]).parent
        try:
            matches = sorted(root.glob(str(expanded.relative_to(root))))
        except (ValueError, OSError):
            matches = []
        for match in matches:
            if match.is_file() and match not in found:
                found.append(match)
    return found


def iter_texts(path: Path):
    """Yield (index, text) for every readable JSONL entry that carries conversation.

    Streams line by line and never holds the file: a transcript is routinely tens of MB,
    and reading it whole is the exact failure this script exists to prevent. A corrupt
    line is skipped, not fatal - a transcript being written to concurrently always has
    one.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            yield index, entry_text(entry)


def entry_text(entry) -> str:
    """Conversation text of one transcript entry, or "" for harness bookkeeping.

    Shapes verified against the live corpus (2002 transcripts on this machine, one
    647-entry file surveyed): `message.content` is ALWAYS a list of typed blocks --
    `text`, `thinking`, `tool_use`, `tool_result` -- and 36% of entries are
    `attachment`/`system` records with no message at all.

    An earlier version fell through to `json.dumps(entry)` for anything it did not
    recognise. Run against a real transcript that emitted whole hook payloads: absolute
    transcript paths, hook stdout, terminal escape sequences -- into output this script
    exists to keep SMALL and that gets pasted into committed reports. The synthetic
    fixture never caught it because it used `content` as a bare string, a shape that
    occurs ZERO times in the real corpus. There is no fallthrough now: unknown entry,
    empty string.
    """
    if not isinstance(entry, dict) or entry.get("type") not in ENTRY_TYPES:
        return ""
    message = entry.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append(str(block.get("text") or ""))
        elif kind == "tool_result":
            inner = block.get("content")
            if isinstance(inner, str):
                parts.append(inner)
            elif isinstance(inner, list):
                parts.extend(str(b.get("text") or "") for b in inner
                             if isinstance(b, dict))
        elif kind == "tool_use":
            # The NAME only. `input` routinely holds file paths and command lines.
            parts.append("[tool_use %s]" % block.get("name"))
        # `thinking` blocks are deliberately dropped: they are the largest blocks in a
        # transcript and the least reviewable, and this output is read as evidence.
    return "\n".join(p for p in parts if p)


def _scrubber():
    """reflection.py's redact_secrets, imported by path.

    NOT reimplemented here. Tool results are the channel that carries .env reads, `env`
    dumps, settings files and git remotes with tokens, and this output is quotable into a
    TRACKED retro report -- so it needs the briefs' credential treatment, from the same
    definition the briefs use. Absent module => refuse to emit rather than print
    unscrubbed tool output.
    """
    here = Path(__file__).resolve()
    candidates = []
    if len(here.parents) >= 3:
        candidates.append(here.parents[2] / "hooks" / "reflection.py")
    candidates.append(Path.cwd() / ".claude" / "hooks" / "reflection.py")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        spec = importlib.util.spec_from_file_location("_ck_reflection_redact", candidate)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except BaseException:
            continue
        scrub = getattr(module, "redact_secrets", None)
        if callable(scrub):
            return scrub
    return None


def redact(line: str, scrub) -> str:
    """Strip host paths from a line on its way out.

    The docstring always claimed absolute paths were suppressed; only the transcript's
    own path was. Real entries carry them in tool output and hook payloads, so the
    guarantee has to be applied at the point of printing, to every line, or it is not a
    guarantee. Lines are capped too: one tool_result can be megabytes.
    """
    line = scrub(line)
    line = _ABS_PATH.sub("<path>", line)
    return line if len(line) <= MAX_LINE else line[:MAX_LINE] + " ...[truncated]"


def slice_window(path: Path, slug: str, max_lines: int):
    """The verdict block, its run-up, and the failures around it."""
    texts = [(i, text) for i, text in iter_texts(path) if text]
    hits = [i for i, (_, text) in enumerate(texts)
            if VERDICT_RE.search(text) and (slug in text or slug in str(path))]
    if not hits:
        # A verdict block with no slug mention still beats nothing: report every verdict
        # and let the caller judge, rather than claiming the session had no review.
        hits = [i for i, (_, text) in enumerate(texts) if VERDICT_RE.search(text)]
        if not hits:
            return None
    out = []
    for hit in hits:
        start = max(0, hit - CONTEXT_BEFORE)
        out.append("### verdict window (entries %d-%d of %d)" % (start, hit, len(texts)))
        for _, text in texts[start:hit + 1]:
            out.extend(text.splitlines())
        out.append("")
    failures = [text.strip() for _, text in texts
                if any(marker in text for marker in FAILURE_MARKERS)]
    if failures:
        out.append("### tool failures in this session (%d)" % len(failures))
        out.extend(f.splitlines()[0][:200] for f in failures[:40])
    if len(out) > max_lines:
        dropped = len(out) - max_lines
        out = out[:max_lines]
        out.append("### truncated: %d further lines dropped (--max-lines)" % dropped)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Slice a session transcript to the review-verdict window")
    parser.add_argument("session_id")
    parser.add_argument("--around", default=None,
                        help="ops slug to centre the slice on (not needed with --list)")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--list", action="store_true",
                        help="print the matching transcript paths and stop")
    args = parser.parse_args()

    if not SESSION_ID_RE.match(args.session_id.strip()):
        print("Error: session id must look like a transcript filename "
              "(hex and dashes, 8-64 chars).", file=sys.stderr)
        return 1

    scrub = _scrubber()
    if scrub is None:
        print("Error: cannot load reflection.py's redact_secrets; refusing to emit "
              "unscrubbed transcript text.", file=sys.stderr)
        return 1

    transcripts = find_transcripts(args.session_id.strip())
    if not transcripts:
        print("NO TRANSCRIPT: nothing matches session %s." % args.session_id,
              file=sys.stderr)
        print("               This is normal, not a failure: transcripts are pruned and "
              "their layout is Claude Code's, not ours.", file=sys.stderr)
        print("               Degrade to brief-only analysis.", file=sys.stderr)
        return 3

    if args.list:
        for path in transcripts:
            # Name only: the full path is absolute by construction.
            print(path.name)
        return 0

    if not args.around:
        print("Error: --around <ops-slug> is required unless --list is given.",
              file=sys.stderr)
        return 1

    printed = False
    for path in transcripts:
        window = slice_window(path, args.around, args.max_lines)
        if not window:
            continue
        # Only the FILENAME: this output is routinely pasted into files that get
        # committed, and --max-lines is a line cap, not an entry count -- the per-window
        # header printed by slice_window carries the real "entries X-Y of N".
        print("## transcript %s" % path.name)
        for line in window:
            print(redact(line, scrub))
        printed = True

    if not printed:
        print("NO WINDOW: transcript found, but no review verdict mentions %r."
              % args.around, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

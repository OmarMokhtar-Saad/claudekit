#!/usr/bin/env python3
"""Park fetched web content on disk and refuse to re-bill a repeat fetch.

Measured on session hermes-agent-20260920-2108: 10 WebFetch + 6 WebSearch, and
one GitHub raw URL accounted for 4 of the 10 fetches. Every fetch lands a full
page in the conversation, and the conversation is re-sent with every later
request -- so fetching one page four times bills it far more than four times.
The content was not gone when it was re-fetched; it had merely scrolled out of
the model's attention, which a file fixes and a re-fetch does not.

PostToolUse on WebFetch|WebSearch:

  first time   the result is left completely untouched -- the model asked for
               it and needs it -- but a copy is written to the research dir and
               the path is appended so it can be re-read cheaply later.
  repeat       same URL + question (or same query) already fetched in this session: the
               result is replaced by a pointer to the parked file. Nothing is
               lost; the text is on disk, and grep -n / sed -n reads the part
               that is actually needed instead of the whole page.

Replacement goes through hookSpecificOutput.updatedToolOutput and preserves the
response's original shape. If the host does not honour that for these tools the
hook simply parks the file and changes nothing -- it must never cost a fetch.

Pure stdlib, no kit imports, runs from a user-level hooks dir in any folder.
"""

import hashlib
import json
import os
import re
import sys
import time

LEDGER_NAME = "web-park.jsonl"
MAX_PARK_BYTES = 400_000
KEEP_ROWS = 600
TEXT_KEYS = ("result", "content", "text", "output", "response", "body")


def base_dir():
    d = os.environ.get("CK_RESEARCH_DIR")
    if d:
        return d
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "research")


def slug(value):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return (s[:60] or "item")


def key_of(tool, tool_input):
    if tool == "WebFetch":
        # WebFetch returns a summary written for its prompt, not the page itself, so the same
        # URL asked a different question is a different result and must not hit the cache.
        url = (tool_input.get("url") or "").strip()
        prompt = " ".join((tool_input.get("prompt") or "").split())
        if not url or not prompt:
            return url
        return "%s #q-%s" % (url, hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8])
    return " ".join((tool_input.get("query") or "").split()).lower()


def extract_text(resp):
    """Return (text, container_key). container_key is None for a bare string."""
    if isinstance(resp, str):
        return resp, None
    if isinstance(resp, dict):
        for k in TEXT_KEYS:
            v = resp.get(k)
            if isinstance(v, str) and v:
                return v, k
        return json.dumps(resp, indent=2)[:MAX_PARK_BYTES], None
    return "", None


def read_ledger(path, session):
    seen = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("session") == session and row.get("key"):
                    seen[row["key"]] = row
    except OSError:
        pass
    return seen


def append_ledger(path, row):
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        if len(lines) > KEEP_ROWS * 2:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(lines[-KEEP_ROWS:])
    except OSError:
        pass


def park(directory, tool, key, text):
    name = "%s-%s.md" % (hashlib.sha1(key.encode("utf-8")).hexdigest()[:10], slug(key))
    path = os.path.join(directory, name)
    header = "<!-- %s | %s | %s -->\n\n" % (
        tool,
        key,
        time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    try:
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header + text[:MAX_PARK_BYTES])
    except OSError:
        return None
    return path


def emit(resp, container_key, new_text):
    if container_key is None:
        if not isinstance(resp, str):
            return  # unknown shape: leave it alone
        updated = new_text
    else:
        updated = dict(resp)
        updated[container_key] = new_text
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": updated,
            }
        },
        sys.stdout,
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name") or ""
    if tool not in ("WebFetch", "WebSearch"):
        return 0
    if os.environ.get("CK_RAW_WEB") == "1":
        return 0

    tool_input = payload.get("tool_input") or {}
    resp = payload.get("tool_response")
    key = key_of(tool, tool_input)
    if not key:
        return 0

    text, container_key = extract_text(resp)
    if not text:
        return 0

    directory = base_dir()
    ledger = os.path.join(directory, LEDGER_NAME)
    session = payload.get("session_id") or "unknown"
    seen = read_ledger(ledger, session)

    prior = seen.get(key)
    if prior and prior.get("path") and os.path.exists(prior["path"]):
        emit(
            resp,
            container_key,
            "[ck web-park] Already fetched in this session at %s (%d chars). The "
            "full text is parked at:\n  %s\nRe-fetching re-bills the whole page in "
            "every later request. Read the part you need from that file instead "
            "(grep -n '<term>' <path>, or sed -n 'a,bp' <path>). If the page really "
            "may have changed, re-run the fetch with CK_RAW_WEB=1."
            % (prior.get("when", "?"), prior.get("chars", 0), prior["path"]),
        )
        return 0

    path = park(directory, tool, key, text)
    if not path:
        return 0

    append_ledger(
        ledger,
        {
            "session": session,
            "key": key,
            "tool": tool,
            "path": path,
            "chars": len(text),
            "when": time.strftime("%H:%M:%S"),
            "ts": int(time.time()),
        },
    )

    emit(
        resp,
        container_key,
        text
        + "\n\n[ck web-park] Parked at %s -- re-read from there instead of "
        "fetching this again." % path,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

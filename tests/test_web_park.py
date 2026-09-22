"""Behavioural tests for the web-park hook (.claude/hooks).

Every test drives the real script as a subprocess with a real PostToolUse payload on stdin
and asserts on what the process writes -- never on its internals. The mutation that turns
each test red is named in its docstring, because a passing check that was never shown
capable of failing measures nothing.

The contract under test is narrow on purpose: the FIRST fetch of a URL must survive
completely intact, because the model asked for it and is about to use it. Only a REPEAT is
replaced. A hook that trims a first fetch would cost the session the work it was doing.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".claude" / "hooks" / "web-park.py"

URL = "https://example.com/docs/hooks.md"
OTHER_URL = "https://example.com/docs/settings.md"
BODY = "# Hooks\n\n" + ("the quick brown fox jumps over the lazy dog. " * 40)
SESSION = "sess-A"


def run(payload, research_dir, **env):
    environ = dict(os.environ)
    environ["CK_RESEARCH_DIR"] = str(research_dir)
    environ.pop("CK_RAW_WEB", None)
    environ.update({k: str(v) for k, v in env.items()})
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env=environ,
        timeout=30,
    )
    return proc


def updated(proc):
    """The replacement output the hook asked the host to substitute, or None."""
    if not proc.stdout.strip():
        return None
    body = json.loads(proc.stdout)
    out = body["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    return out["updatedToolOutput"]


def fetch(url=URL, session=SESSION, response=None, prompt="summarise"):
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "WebFetch",
        "session_id": session,
        "tool_input": {"url": url, "prompt": prompt},
        "tool_response": BODY if response is None else response,
    }


def search(query, session=SESSION):
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "WebSearch",
        "session_id": session,
        "tool_input": {"query": query},
        "tool_response": BODY,
    }


def text_of(out):
    return out if isinstance(out, str) else out["result"]


# --- first fetch: untouched, but parked -----------------------------------------------

def test_the_first_fetch_keeps_every_byte(tmp_path):
    """Red if the hook ever trimmed a first fetch. The model requested this page and is
    about to reason over it; replacing it with a pointer would destroy the current step."""
    out = text_of(updated(run(fetch(), tmp_path)))

    assert BODY in out, "the whole fetched body must survive the first fetch"
    assert "[ck web-park] Parked at" in out


def test_the_first_fetch_lands_on_disk_with_its_url(tmp_path):
    """Red if parking were skipped -- the pointer a later repeat emits would then aim at
    nothing, and the repeat would have destroyed content with no copy behind it."""
    run(fetch(), tmp_path)

    parked = [p for p in Path(tmp_path).glob("*.md")]
    assert len(parked) == 1, "exactly one file per fetched URL"
    body = parked[0].read_text()
    assert body.startswith("<!-- WebFetch | %s #q-" % URL), (
        "the header must name the tool, the URL and the question tag, or the file cannot be traced back")
    assert BODY in body


# --- repeat fetch: the measured waste -------------------------------------------------

def test_a_repeat_of_the_same_url_returns_a_pointer_not_the_page(tmp_path):
    """Red if repeats were let through. This is the measured failure: on session
    hermes-agent-20260920-2108 one URL accounted for 4 of 10 WebFetch calls, and every
    copy was re-billed in every later request until the next compaction."""
    run(fetch(), tmp_path)
    out = text_of(updated(run(fetch(), tmp_path)))

    assert BODY not in out, "the page body must not be re-billed"
    assert "Already fetched in this session" in out
    assert str(tmp_path) in out, "the pointer must name the parked path"
    assert "CK_RAW_WEB=1" in out, "the escape hatch must be discoverable at the moment of need"


def test_a_different_url_is_not_a_repeat(tmp_path):
    """Red if the ledger key were dropped or coarsened -- every fetch after the first
    would come back as a pointer to the wrong page."""
    run(fetch(), tmp_path)
    out = text_of(updated(run(fetch(url=OTHER_URL), tmp_path)))

    assert BODY in out
    assert "Already fetched" not in out


def test_the_same_url_with_a_different_question_is_not_a_repeat(tmp_path):
    """Red if the key were the URL alone. WebFetch returns a summary written for its
    prompt, not the page, so the second question would get a pointer to an answer to the
    first one (the Q5 miss: same doc, different question, wrong cached summary)."""
    run(fetch(prompt="list the hook event names"), tmp_path)
    out = text_of(updated(run(fetch(prompt="what does exit 2 mean"), tmp_path)))

    assert BODY in out
    assert "Already fetched" not in out


def test_the_same_url_and_question_is_a_repeat_whatever_the_whitespace(tmp_path):
    """Red if the prompt were compared raw -- the model rarely retypes it byte-for-byte."""
    run(fetch(prompt="list  the hook\nevent names"), tmp_path)
    out = text_of(updated(run(fetch(prompt="list the hook event names"), tmp_path)))

    assert BODY not in out
    assert "Already fetched in this session" in out


def test_another_session_starts_clean(tmp_path):
    """Red if the session filter were dropped. A page fetched yesterday is not in today's
    context, so pointing a new session at a file it has never read loses the content."""
    run(fetch(), tmp_path)
    out = text_of(updated(run(fetch(session="sess-B"), tmp_path)))

    assert BODY in out


def test_a_websearch_repeat_is_keyed_by_the_normalised_query(tmp_path):
    """Red if query normalisation were dropped -- 'Claude Code hooks' and 'claude code
    hooks' are the same search and re-running one bills the same results twice."""
    run(search("Claude Code   hooks"), tmp_path)
    out = text_of(updated(run(search("claude code hooks"), tmp_path)))

    assert "Already fetched in this session" in out


# --- shape preservation ---------------------------------------------------------------

def test_a_dict_response_keeps_its_other_fields(tmp_path):
    """Red if the hook replaced the whole response object. The host reads siblings such as
    durationMs and code off that dict; flattening it to a string breaks the tool result."""
    resp = {"result": BODY, "durationMs": 812, "url": URL}
    run(fetch(response=resp), tmp_path)
    out = updated(run(fetch(response=resp), tmp_path))

    assert isinstance(out, dict)
    assert out["durationMs"] == 812
    assert out["url"] == URL
    assert BODY not in out["result"]


def test_an_unrecognised_shape_is_left_alone(tmp_path):
    """Red if the hook guessed at shapes it does not understand. A wrong guess costs the
    fetch outright; staying silent costs only the parking."""
    proc = run(fetch(response=["chunk one", "chunk two"]), tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == ""


# --- escape hatches and scope ---------------------------------------------------------

def test_ck_raw_web_disables_the_hook(tmp_path):
    """Red if the escape hatch stopped working -- a page that genuinely changed between
    fetches could then never be re-read in the same session."""
    run(fetch(), tmp_path)
    proc = run(fetch(), tmp_path, CK_RAW_WEB=1)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_other_tools_are_untouched(tmp_path):
    """Red if the tool filter were dropped: this hook would then rewrite Bash and Read
    results, which have no URL to key on and must never be replaced."""
    proc = run({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": SESSION,
        "tool_input": {"command": "ls"},
        "tool_response": {"stdout": BODY, "stderr": ""},
    }, tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_a_fetch_with_no_url_is_ignored(tmp_path):
    """Red if an empty key were parked -- every keyless call would collide on one file and
    the second one would come back as a pointer to the first one's content."""
    proc = run(fetch(url=""), tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_garbage_stdin_fails_open(tmp_path):
    """Red if the hook raised on malformed input. A PostToolUse hook that dies noisily
    turns a successful fetch into a visible error for no benefit."""
    proc = run("not json at all", tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == ""


# --- wiring ---------------------------------------------------------------------------

def test_the_hook_is_wired_for_both_web_tools():
    """Red if the hook shipped inert or covered only one tool -- the measured session made
    10 WebFetch and 6 WebSearch calls, and both re-billed their results."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    matchers = [
        entry.get("matcher", "")
        for entry in settings["hooks"].get("PostToolUse", [])
        for hook in entry["hooks"]
        if "web-park.py" in hook["command"]
    ]
    assert matchers, "web-park.py is not wired on PostToolUse"
    joined = "|".join(matchers)
    assert "WebFetch" in joined and "WebSearch" in joined


def test_the_hook_is_wired_directly_not_through_the_dispatcher():
    """Red if the hook were routed through dispatch.sh, which prefixes advisory stdout
    with `[<id>] ` -- that prefix would make this hook's JSON unparseable and every
    replacement would be silently dropped."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    for entry in settings["hooks"].get("PostToolUse", []):
        for hook in entry["hooks"]:
            if "web-park.py" in hook["command"]:
                assert "dispatch.sh" not in hook["command"]

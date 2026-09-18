"""Behavioural coverage for .claude/hooks/context-budget-gate.py.

Every case runs the hook as a REAL subprocess with a synthetic PreToolUse payload on stdin and
a synthetic transcript in tmp_path, and asserts the exit code the dispatcher would see. Nothing
is imported from the hook, so the shipped artifact is what is measured.

Mutants these tests must catch (apply them, do not assume them):
  * DEFAULT_BLOCK = 400000 -> 4000000        => test_blocks_at_the_block_threshold RED
  * replace the seek + bounded read with
    `blob = handle.read()` (whole file)      => test_only_the_tail_is_read RED on read_bytes
                                                (~40 MB instead of 64 KB) and on wall time.
                                                The VERDICT is identical either way - the last
                                                usage record is the same - so bytes read, not
                                                the exit code, is the observable that pins this
                                                property, and CK_CONTEXT_TRACE=1 is what makes
                                                it observable.
  * delete only `handle.seek(size - TAIL_BYTES)`
    (read the FIRST 64 KB)                   => test_only_the_tail_is_read RED on the exit
                                                code: the over-BLOCK record planted on line 2
                                                is inside that window, so the mutant BLOCKS
                                                where the shipped hook allows.
  * delete `lines = lines[1:]` (the
    leading-fragment drop)                   => test_the_leading_fragment_is_never_parsed RED -
                                                the window opens on a fragment that IS valid
                                                JSON and an over-BLOCK usage record.
  * delete the `_is_subagent` branch          => test_a_subagent_over_the_block_line_is_advised
                                                RED (a subagent would be hard-blocked)
  * drop "NotebookEdit" from GUARDED_TOOLS    => test_notebook_edit_is_guarded RED
  * make `_state_dir` fall back to cwd
    unconditionally                          => test_the_warn_counter_writes_no_state_outside
                                                _the_project RED
  * delete the UNBOUNDED_AGENT branch in
    `_spawns_unbounded_agent`                => test_blocks_a_general_purpose_spawn RED and
                                                test_dispatch_blocks_a_general_purpose_spawn RED

ENV DISCIPLINE: CK_RAW_CONTEXT, CK_ALLOW_GENERAL_PURPOSE, CK_CONTEXT_WARN, CK_CONTEXT_BLOCK and
CK_CONTEXT_TRACE are POPPED from the inherited environment. A developer with a hatch exported
would otherwise turn every block assertion silently green - the same class of mistake recorded
in .claude/knowledge/issues ("assumed subprocess.run inherited the parent env").

CLAUDE_PROJECT_DIR points at tmp_path for the direct-subprocess cases, so the hook's warn
counter under .claude/hooks/.state/ is written inside the temp tree and never into the repo.
The two dispatch.sh cases need the real project root; their state lands in the repo's
.claude/hooks/.state/, which .gitignore covers.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "context-budget-gate.py"
DISPATCH = ROOT / ".claude" / "hooks" / "dispatch.sh"
REGISTRY = ROOT / ".claude" / "hooks" / "dispatch-registry.json"

HATCHES = ("CK_RAW_CONTEXT", "CK_ALLOW_GENERAL_PURPOSE", "CK_CONTEXT_WARN", "CK_CONTEXT_BLOCK",
           "CK_CONTEXT_TRACE")

# Mirrors the hook's TAIL_BYTES. Deliberately re-declared rather than imported: these tests
# measure the shipped artifact from outside, and a constant read out of the module under test
# cannot contradict it.
TAIL_BYTES = 65536

_UNSET = object()


def usage_line(total):
    """One assistant transcript line whose three usage counters sum to `total`."""
    return json.dumps({
        "type": "assistant",
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": total - 2,
                "cache_read_input_tokens": 1,
                "cache_creation_input_tokens": 1,
            },
        },
    })


def filler_line(index, width=1024):
    """A user line with no usage record, wide enough to push the tail window along."""
    return json.dumps({"type": "user", "message": {"role": "user", "content": "x" * width},
                       "i": index})


def padded_line(length):
    """A usage-free user line of EXACTLY `length` characters (no trailing newline)."""
    empty = json.dumps({"type": "user", "message": {"role": "user", "content": ""}})
    pad = length - len(empty)
    assert pad >= 0, "padded_line needs at least %d characters" % len(empty)
    return json.dumps({"type": "user", "message": {"role": "user", "content": "x" * pad}})


def transcript(tmp_path, *lines, **kwargs):
    target = tmp_path / kwargs.get("name", "session.jsonl")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def huge_transcript(tmp_path, planted, tail_usage, target_bytes=40 * 1024 * 1024):
    """A ~40 MB transcript: the over-BLOCK record on LINE 2, an under-WARN record last.

    The placement is the whole point. On line 1 the leading-fragment drop discards the record
    for a whole-file reader too, so the mutant behaves identically to the shipped hook - that
    is exactly how the first version of this test passed against the mutant it was named for.
    On line 2 the record survives every reader:
      * shipped (seek to the last 64 KB) -> sees only `tail_usage` -> allow, 64 KB read
      * seek deleted (first 64 KB)       -> sees the planted record -> rc 2
      * whole file read                  -> `tail_usage` again (last record wins) -> allow,
                                            but read_bytes goes from 64 KB to ~40 MB
    """
    path = tmp_path / "huge.jsonl"
    chunk = "".join(filler_line(i) + "\n" for i in range(1000))
    written = 0
    with path.open("w", encoding="utf-8") as handle:
        written += handle.write(filler_line(0) + "\n")
        written += handle.write(usage_line(planted) + "\n")
        while written < target_bytes:
            written += handle.write(chunk)
        handle.write(usage_line(tail_usage) + "\n")
    return path


def fragment_transcript(tmp_path, planted=900000):
    """A transcript whose 64 KB window OPENS mid-line, on a fragment that is valid JSON.

    The byte layout is exact: everything after the start of `record` is exactly TAIL_BYTES, so
    the window begins precisely at that offset and lines[0] IS `record` - a complete assistant
    usage record over the block line, cut out of the middle of a much longer physical line.
    Shipped behaviour drops it unparsed; a hook that parses the fragment blocks on half a line.
    """
    record = usage_line(planted)
    trailer_len = TAIL_BYTES - len(record) - 2  # the two newlines: after record, after trailer
    assert trailer_len > 0
    trailer = padded_line(trailer_len)
    head = "".join(filler_line(i) + "\n" for i in range(16))
    path = tmp_path / "fragment.jsonl"
    path.write_text(head + "P" * 4096 + record + "\n" + trailer + "\n", encoding="utf-8")
    assert path.stat().st_size > TAIL_BYTES
    return path


def run_hook(tmp_path, transcript_path=None, tool_name="Write", tool_input=None,
             session_id="pytest-context-budget", extra_env=None, project_dir=_UNSET, cwd=None):
    payload = {
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": tool_input if tool_input is not None else {"file_path": "x.py"},
    }
    if transcript_path is not None:
        payload["transcript_path"] = str(transcript_path)

    env = dict(os.environ)
    for key in HATCHES:
        env.pop(key, None)
    if project_dir is _UNSET:
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    elif project_dir is None:
        env.pop("CLAUDE_PROJECT_DIR", None)
    else:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd or tmp_path),
    )


def test_hook_ships():
    assert HOOK.is_file(), "the gate must exist on disk for the registry row to resolve"


# ------------------------------------------------------------------ context budget ----

def test_below_the_warn_threshold_is_silent(tmp_path):
    path = transcript(tmp_path, usage_line(50000))
    result = run_hook(tmp_path, path)
    assert result.returncode == 0
    assert result.stderr == "", "a session well under budget must not be nagged"


def test_warns_once_at_the_warn_threshold(tmp_path):
    path = transcript(tmp_path, usage_line(250000))
    result = run_hook(tmp_path, path)
    assert result.returncode == 0, "the warn band allows the call"
    assert "/compact" in result.stderr
    assert "250K" in result.stderr


def test_the_warning_is_suppressed_on_the_next_call(tmp_path):
    path = transcript(tmp_path, usage_line(250000))
    first = run_hook(tmp_path, path)
    second = run_hook(tmp_path, path)
    assert first.stderr != ""
    assert second.returncode == 0
    assert second.stderr == "", (
        "the advisory must repeat at most once per 20 calls; the state file under "
        ".claude/hooks/.state/ is what makes that true"
    )


def test_the_warn_counter_writes_no_state_outside_the_project(tmp_path):
    """With CLAUDE_PROJECT_DIR unset and an unrelated cwd, no .claude/ tree may appear.

    The counter is advisory state; creating `.claude/hooks/.state/` under whatever directory
    the hook was invoked from is a worse failure than warning twice, so the hook degrades to
    warning on every call instead.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    path = transcript(tmp_path, usage_line(250000))

    first = run_hook(tmp_path, path, project_dir=None, cwd=elsewhere)
    second = run_hook(tmp_path, path, project_dir=None, cwd=elsewhere)

    assert first.returncode == 0 and second.returncode == 0
    assert not (elsewhere / ".claude").exists(), (
        "the hook created state under an arbitrary cwd: %s"
        % sorted(p.name for p in elsewhere.iterdir())
    )
    assert "/compact" in first.stderr and "/compact" in second.stderr, (
        "with nowhere to keep the counter the advisory must repeat, never go silent"
    )


def test_blocks_at_the_block_threshold(tmp_path):
    path = transcript(tmp_path, usage_line(450000))
    result = run_hook(tmp_path, path)
    assert result.returncode == 2, (
        "a 450K session must be refused (rc=%s, stderr=%r)" % (result.returncode, result.stderr)
    )
    assert "/compact" in result.stderr
    assert "CK_RAW_CONTEXT=1" in result.stderr
    assert result.stdout == "", "a block is stderr-only; stdout is never a decision"


def test_a_subagent_over_the_block_line_is_advised_not_blocked(tmp_path):
    """Both branches in one case: the same 450K transcript, two paths, two verdicts.

    A subagent can run neither /compact nor /save-session, and cannot put CK_RAW_CONTEXT into
    the hook process's environment, so a block would leave it with no route out. It gets the
    one move it can actually make instead: stop and hand back.
    """
    body = usage_line(450000) + "\n"
    session_dir = tmp_path / "sess-A"
    (session_dir / "subagents").mkdir(parents=True)
    sub = session_dir / "subagents" / "agent-explore.jsonl"
    sub.write_text(body, encoding="utf-8")
    main = session_dir / "session.jsonl"
    main.write_text(body, encoding="utf-8")

    sub_result = run_hook(tmp_path, sub, session_id="pytest-subagent")
    assert sub_result.returncode == 0, (
        "a subagent must not be hard-blocked - it has no /compact (rc=%s, stderr=%r)"
        % (sub_result.returncode, sub_result.stderr)
    )
    assert "BLOCKED" not in sub_result.stderr
    assert "subagent" in sub_result.stderr and "hand it back" in sub_result.stderr, (
        "the subagent advisory must name the one move it can make (stderr=%r)"
        % sub_result.stderr
    )

    main_result = run_hook(tmp_path, main, session_id="pytest-main-session")
    assert main_result.returncode == 2, (
        "a MAIN session at 450K is still refused (rc=%s, stderr=%r)"
        % (main_result.returncode, main_result.stderr)
    )
    assert "BLOCKED" in main_result.stderr


def test_raw_context_hatch_allows_an_oversize_session(tmp_path):
    path = transcript(tmp_path, usage_line(450000))
    result = run_hook(tmp_path, path, extra_env={"CK_RAW_CONTEXT": "1"})
    assert result.returncode == 0
    assert result.stderr == ""


def test_thresholds_come_from_the_environment(tmp_path):
    path = transcript(tmp_path, usage_line(250000))
    result = run_hook(tmp_path, path, extra_env={"CK_CONTEXT_BLOCK": "200000"})
    assert result.returncode == 2, "CK_CONTEXT_BLOCK must move the block line"


def test_a_missing_transcript_allows(tmp_path):
    result = run_hook(tmp_path, tmp_path / "does-not-exist.jsonl")
    assert result.returncode == 0


def test_a_malformed_transcript_allows(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text("not json\n{\"usage\": truncated...\n", encoding="utf-8")
    result = run_hook(tmp_path, path)
    assert result.returncode == 0, "garbage in the transcript must never block a tool call"


def test_the_last_usage_record_wins_not_the_largest(tmp_path):
    path = transcript(tmp_path, usage_line(900000), usage_line(50000))
    result = run_hook(tmp_path, path)
    assert result.returncode == 0, (
        "context is the CURRENT window, so the last record decides, not the largest"
    )


def test_only_the_tail_is_read(tmp_path):
    """A ~40 MB transcript, read for 64 KB: asserted on BYTES READ, not only on the verdict.

    Two mutants die here. Deleting the seek (reading the FIRST 64 KB) flips the exit code,
    because the over-BLOCK record sits on line 2. Reading the whole file leaves the exit code
    alone - the last usage record is the same - and is caught only by read_bytes and wall
    time, which is why the hook carries the CK_CONTEXT_TRACE knob at all.
    """
    path = huge_transcript(tmp_path, planted=900000, tail_usage=50000)
    assert path.stat().st_size > 40 * 1024 * 1024

    started = time.time()
    result = run_hook(tmp_path, path, extra_env={"CK_CONTEXT_TRACE": "1"})
    elapsed = time.time() - started

    assert result.returncode == 0, (
        "only the last 64 KB may decide: the 900K record on line 2 is outside that window "
        "(rc=%s, stderr=%r)" % (result.returncode, result.stderr)
    )
    match = re.search(r"read_bytes=(\d+)", result.stderr)
    assert match, "CK_CONTEXT_TRACE=1 must report bytes read (stderr=%r)" % result.stderr
    read_bytes = int(match.group(1))
    assert read_bytes <= TAIL_BYTES + 4096, (
        "the gate read %d bytes of a %d-byte transcript; it must read one 64 KB window per "
        "guarded tool call" % (read_bytes, path.stat().st_size)
    )
    assert elapsed < 1.0, (
        "a PreToolUse gate that walks whole transcripts taxes every call (%.2fs)" % elapsed
    )


def test_the_leading_fragment_is_never_parsed(tmp_path):
    """The window opens mid-line on a fragment that WOULD parse as a 900K usage record.

    Dropping `lines[0]` is the one line that keeps half a record out of the verdict. The
    positive control below proves the record itself is block-worthy, so a green first
    assertion cannot be an artifact of a malformed payload.
    """
    path = fragment_transcript(tmp_path)
    result = run_hook(tmp_path, path)
    assert result.returncode == 0, (
        "a record cut in half by the window boundary must not decide a block (rc=%s, "
        "stderr=%r)" % (result.returncode, result.stderr)
    )

    control = transcript(tmp_path, filler_line(0), usage_line(900000), name="control.jsonl")
    control_result = run_hook(tmp_path, control, session_id="pytest-fragment-control")
    assert control_result.returncode == 2, (
        "positive control: the same record on a whole line DOES block, so the case above "
        "measures the fragment drop and nothing else (rc=%s)" % control_result.returncode
    )


def test_unguarded_tools_are_ignored(tmp_path):
    path = transcript(tmp_path, usage_line(450000))
    result = run_hook(tmp_path, path, tool_name="Read", tool_input={"file_path": "x.py"})
    assert result.returncode == 0


def test_notebook_edit_is_guarded(tmp_path):
    """The registry matcher is an unanchored re.search, so the dispatcher already routes
    NotebookEdit to this handler; a tool that reaches the handler and falls through the
    guarded set is a hole a 500K session can write through."""
    path = transcript(tmp_path, usage_line(450000))
    result = run_hook(tmp_path, path, tool_name="NotebookEdit",
                      tool_input={"notebook_path": "x.ipynb", "new_source": "print(1)"})
    assert result.returncode == 2, (
        "NotebookEdit writes files and must be inside the budget (rc=%s, stderr=%r)"
        % (result.returncode, result.stderr)
    )


def test_allows_on_unparseable_payload(tmp_path):
    env = dict(os.environ)
    for key in HATCHES:
        env.pop(key, None)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json at all",
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0


# --------------------------------------------------------------------- spawn guard ----

def test_blocks_a_general_purpose_spawn(tmp_path):
    path = transcript(tmp_path, usage_line(1000))
    result = run_hook(tmp_path, path, tool_name="Agent",
                      tool_input={"subagent_type": "general-purpose", "prompt": "redesign it"})
    assert result.returncode == 2, (
        "general-purpose is the one agent our frontmatter cannot bound (rc=%s, stderr=%r)"
        % (result.returncode, result.stderr)
    )
    assert "planner" in result.stderr
    assert "CK_ALLOW_GENERAL_PURPOSE=1" in result.stderr


def test_blocks_a_spawn_that_names_no_agent(tmp_path):
    path = transcript(tmp_path, usage_line(1000))
    result = run_hook(tmp_path, path, tool_name="Agent", tool_input={"prompt": "do the thing"})
    assert result.returncode == 2


def test_allows_a_scoped_agent(tmp_path):
    path = transcript(tmp_path, usage_line(1000))
    result = run_hook(tmp_path, path, tool_name="Agent",
                      tool_input={"subagent_type": "planner", "prompt": "plan it"})
    assert result.returncode == 0
    assert result.stderr == ""


def test_allow_general_purpose_hatch(tmp_path):
    path = transcript(tmp_path, usage_line(1000))
    result = run_hook(tmp_path, path, tool_name="Agent",
                      tool_input={"subagent_type": "general-purpose", "prompt": "x"},
                      extra_env={"CK_ALLOW_GENERAL_PURPOSE": "1"})
    assert result.returncode == 0


# ------------------------------------------------- the gate, through dispatch.sh ----
# Every test above spawns the hook directly. That proves the SCRIPT works and proves nothing
# about whether Claude Code ever runs it: the shipped control is the registry row, which
# settings.json reaches only via `dispatch.sh PreToolUse`. These three drive the real path.


def run_dispatch(tmp_path, subagent_type=None, context_tokens=1000):
    path = transcript(tmp_path, usage_line(context_tokens))
    tool_input = {"prompt": "work", "description": "work"}
    if subagent_type is not None:
        tool_input["subagent_type"] = subagent_type
    payload = json.dumps({
        "session_id": "pytest-context-budget-dispatch",
        "transcript_path": str(path),
        "tool_name": "Agent",
        "tool_input": tool_input,
    })

    env = dict(os.environ)
    for key in HATCHES:
        env.pop(key, None)
    env["ECC_HOOK_PROFILE"] = "standard"
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    env["CLAUDEKIT_SESSION_ID"] = "pytest-context-budget-gate"

    return subprocess.run(
        ["bash", str(DISPATCH), "PreToolUse"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )


def test_registry_registers_the_gate_as_blocking():
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))["events"]["PreToolUse"]
    matches = [row for row in rows if row.get("id") == "context-budget-gate"]
    assert matches, "the gate is not registered for PreToolUse; the script is inert"
    row = matches[0]
    assert row["file"] == "context-budget-gate.py"
    assert row["tier"] == "blocking", (
        "an advisory row cannot deny a tool call; the gate would be observable but powerless"
    )
    for tool in ("Write", "Edit", "NotebookEdit", "Bash", "Agent", "Task"):
        assert tool in row["matcher"], (
            "%s is unguarded, so the budget never applies to it" % tool
        )


def test_dispatch_blocks_a_general_purpose_spawn(tmp_path):
    """End to end, exactly as settings.json invokes it: payload -> dispatch.sh -> exit 2."""
    result = run_dispatch(tmp_path, subagent_type="general-purpose")
    assert result.returncode == 2, (
        "dispatch.sh did not block a general-purpose spawn (rc=%s, stderr=%r)"
        % (result.returncode, result.stderr)
    )


def test_dispatch_allows_a_scoped_spawn(tmp_path):
    result = run_dispatch(tmp_path, subagent_type="planner")
    assert result.returncode == 0, result.stderr

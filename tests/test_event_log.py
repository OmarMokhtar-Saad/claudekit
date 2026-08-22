"""Proof 4: "model-visible means logged", and the assertion that enforces it.

The interesting test in this file is not that a well-formed record round-trips.
It is that a record with ONE FIELD REMOVED fails -- because that is the only
version of this gate that catches the realistic regression, which is an emitter
quietly dropping a field, not an emitter vanishing.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(REPO_ROOT, ".claude", "hooks")

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from claudekit.enforcement import eventlog  # noqa: E402

#: Pinned literal, deliberately duplicated from the module. If someone narrows
#: KIND_FIELDS to make a failing assertion pass, this fails instead -- the schema
#: is a contract, and a contract you can edit to match your bug is not one.
EXPECTED_HOOK_DECISION_FIELDS = (
    "schema_version", "ts", "session_id", "kind",
    "event", "handler", "tier", "exit_code", "decision", "merged_decision",
    "tool_name", "duration_ms", "stderr_preview",
)


def _record(**overrides):
    fields = {
        "event": "PreToolUse", "handler": "ops-enforcement", "tier": "blocking",
        "exit_code": 2, "decision": "DENY", "merged_decision": "DENY",
        "tool_name": "Write", "duration_ms": 12, "stderr_preview": "BLOCKED: nope",
    }
    fields.update(overrides)
    return eventlog.new_event("hook_decision", "sess-1", **fields)


def test_required_fields_match_the_pinned_contract():
    assert eventlog.required_fields("hook_decision") == EXPECTED_HOOK_DECISION_FIELDS


def test_unknown_kind_is_rejected():
    with pytest.raises(eventlog.EventLogError) as excinfo:
        eventlog.required_fields("whatever")
    assert "unknown event kind" in str(excinfo.value)


def test_append_and_read_round_trip(tmp_path):
    path = os.path.join(str(tmp_path), "events.jsonl")
    eventlog.append(path, _record())
    eventlog.append(path, _record(handler="command-guard", exit_code=0,
                                  decision="ALLOW", merged_decision="DENY"))
    records = eventlog.read(path)
    assert [r["handler"] for r in records] == ["ops-enforcement", "command-guard"]
    assert all(r["schema_version"] == eventlog.SCHEMA_VERSION for r in records)


def test_append_refuses_an_incomplete_record(tmp_path):
    """An under-specified record is not written at all -- no partial evidence."""
    path = os.path.join(str(tmp_path), "events.jsonl")
    incomplete = _record()
    del incomplete["decision"]
    with pytest.raises(eventlog.EventLogError) as excinfo:
        eventlog.append(path, incomplete)
    assert "decision" in str(excinfo.value)
    assert not os.path.exists(path)


@pytest.mark.parametrize("field", [
    f for f in EXPECTED_HOOK_DECISION_FIELDS if f not in ("schema_version", "kind")
])
def test_deleting_any_logged_field_breaks_the_invariant(tmp_path, field):
    """PROOF 4, mutated per field: drop one field, the assertion must fail.

    The record is written past `append` deliberately (raw line write), because
    the regression being modelled is a *log file* that lost a field, not a caller
    that called the API wrongly.
    """
    path = os.path.join(str(tmp_path), "events.jsonl")
    mutant = _record()
    del mutant[field]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(mutant) + "\n")

    with pytest.raises(eventlog.EventLogError):
        eventlog.assert_model_visible_logged(
            {"event": "PreToolUse", "handler": "ops-enforcement"}, path)


def test_intact_record_satisfies_the_invariant(tmp_path):
    """The other half: a complete record must PASS, or the test above is trivial."""
    path = os.path.join(str(tmp_path), "events.jsonl")
    eventlog.append(path, _record())
    found = eventlog.assert_model_visible_logged(
        {"event": "PreToolUse", "handler": "ops-enforcement"}, path)
    assert found["decision"] == "DENY"


def test_nothing_logged_at_all_fails(tmp_path):
    path = os.path.join(str(tmp_path), "events.jsonl")
    with pytest.raises(eventlog.EventLogError) as excinfo:
        eventlog.assert_model_visible_logged(
            {"event": "PreToolUse", "handler": "ops-enforcement"}, path)
    assert "not logged" in str(excinfo.value)


def test_replay_is_a_pure_projection(tmp_path):
    """Same file, same projection -- the golden-record property task 010 needs."""
    path = os.path.join(str(tmp_path), "events.jsonl")
    eventlog.append(path, _record())
    eventlog.append(path, _record(handler="command-guard", exit_code=127,
                                  decision="ERROR", merged_decision="DENY"))
    first = eventlog.replay(path)
    second = eventlog.replay(path)
    assert first == second
    assert first["count"] == 2
    assert first["by_kind"] == {"hook_decision": 2}
    assert [b["handler"] for b in first["blocked"]] == ["ops-enforcement", "command-guard"]
    assert [e["handler"] for e in first["errored"]] == ["command-guard"]


def test_ops_execution_kind_is_typed_too():
    record = eventlog.new_event(
        "ops_execution", "sess-1", plan="demo", config_path="a.ops.json",
        operation_index=0, operation_type="code_edit", target_path="src/x.py",
        status="applied", duration_ms=3, detail_preview="1 edit")
    assert set(eventlog.required_fields("ops_execution")) <= set(record)


def test_dispatcher_actually_emits_a_conforming_record(tmp_path):
    """End-to-end: drive the SHIPPED dispatcher, then assert the invariant holds.

    A schema nothing writes to is documentation. This is the test that makes it
    a runtime property: the record must come out of dispatch.sh, not a fixture.
    """
    directory = str(tmp_path)
    shutil.copy(os.path.join(HOOKS_DIR, "dispatch.sh"),
                os.path.join(directory, "dispatch.sh"))
    shutil.copy(os.path.join(HOOKS_DIR, "lib.sh"), os.path.join(directory, "lib.sh"))
    # The dispatcher invokes `python3 "$SCRIPT_DIR/dispatch_resolve.py"`, so a
    # sandbox without it resolves no handlers, emits no decision record, and this
    # test fails with "model-visible but not logged" — which is the fail-closed path
    # working, not a logging bug. Whatever ships beside the dispatcher has to be
    # sandboxed beside it.
    shutil.copy(os.path.join(HOOKS_DIR, "dispatch_resolve.py"),
                os.path.join(directory, "dispatch_resolve.py"))
    handler = os.path.join(directory, "denier.sh")
    with open(handler, "w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env bash\ncat >/dev/null\necho 'BLOCKED: nope' >&2\nexit 2\n")
    os.chmod(handler, 0o755)
    with open(os.path.join(directory, "dispatch-registry.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 1, "blocking_events": ["PreToolUse"],
                   "events": {"PreToolUse": [{"id": "denier", "file": "denier.sh",
                                              "runner": "bash", "tier": "blocking",
                                              "matcher": ""}]}}, fh)

    project = os.path.join(directory, "project")
    os.makedirs(project)
    environ = dict(os.environ)
    environ.update({"ECC_HOOK_PROFILE": "standard",
                    "CLAUDEKIT_SESSION_ID": "pytest-eventlog",
                    "PYTHONPATH": os.path.join(REPO_ROOT, "src")})
    result = subprocess.run(
        ["bash", os.path.join(directory, "dispatch.sh"), "PreToolUse"],
        input=json.dumps({"tool_name": "Write"}), capture_output=True, text=True,
        env=environ, cwd=directory)
    assert result.returncode == 2, result.stderr

    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=directory,
                          capture_output=True, text=True).stdout.strip() or directory
    log = eventlog.default_log_path(root, "pytest-eventlog")
    try:
        eventlog.assert_model_visible_logged(
            {"event": "PreToolUse", "handler": "denier"}, log)
    finally:
        if os.path.exists(log):
            os.remove(log)


def test_prose_log_is_not_disturbed():
    """`.claude/hooks/hooks.log` keeps its prose shape.

    `.ai/DEBUGGING_GUIDE.md` starts every investigation there. The typed stream is
    additive; a silent migration would break a workflow the docs still describe.
    """
    path = os.path.join(HOOKS_DIR, "hooks.log")
    if not os.path.exists(path):
        pytest.skip("hooks.log absent in this checkout")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        head = [next(fh, "") for _ in range(5)]
    non_empty = [line for line in head if line.strip()]
    assert non_empty, "hooks.log is empty"
    assert not any(line.lstrip().startswith("{") for line in non_empty), (
        "hooks.log has been turned into JSONL -- that is a separate, "
        "owner-approved migration, not a side effect of this phase")


def test_the_event_log_file_is_readable_only_by_its_owner(tmp_path):
    """0600 on the log too -- correct in the code, asserted nowhere until now.

    `append` already opens with `os.open(..., 0o600)`, and that was the CORRECT
    side of the asymmetry round-4 review found in `spill.py`. It was also
    untested, which means the correct mode was one refactor away from being lost
    silently. The event log records every hook decision plus a stderr preview of
    what produced it, so the disclosure argument is the same as for spill files.

    Umask forced to 0o022, for the same reason as the spill test: under a
    permissive developer umask a regression to plain `open()` would still yield
    0600 here and this test would pass against it.
    """
    path = os.path.join(str(tmp_path), "nested", "events.jsonl")
    old = os.umask(0o022)
    try:
        eventlog.append(path, _record())
    finally:
        os.umask(old)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, (
        "event log %s is mode %o, not 0600" % (path, mode))

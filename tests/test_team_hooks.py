"""Behavioural tests for the Phase 1 team hooks."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"
START = HOOKS / "team-session-start.py"
LOG = HOOKS / "team-event-log.py"
TEAM = ROOT / ".claude" / "operations" / "scripts" / "team.py"


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "commit", "--allow-empty", "-q", "-m", "init")
    return r


def hook(script, repo, payload, *args):
    p = {"cwd": str(repo), "session_id": "sess-1", **payload}
    return subprocess.run([sys.executable, str(script), *args], input=json.dumps(p),
                          capture_output=True, text=True,
                          env={**os.environ, "ECC_HOOK_PROFILE": "standard"})


def init(repo):
    subprocess.run([sys.executable, str(TEAM), "init"], cwd=repo, check=True, capture_output=True)


def test_hooks_are_silent_noops_without_config(repo):
    for script, args in ((START, ()), (LOG, ()), (LOG, ("--stop",))):
        r = hook(script, repo, {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}, *args)
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert not (repo / ".team").exists()


def test_hooks_survive_garbage_stdin(repo):
    init(repo)
    for script in (START, LOG):
        r = subprocess.run([sys.executable, str(script)], input="not json", cwd=repo,
                           capture_output=True, text=True)
        assert r.returncode == 0


def test_session_start_registers_and_prints_status(repo):
    init(repo)
    r = hook(START, repo, {})
    assert r.returncode == 0 and "team: goal:" in r.stdout
    assert (repo / ".team" / "sessions" / "sess-1.json").is_file()


def test_event_log_records_edit_path_and_heartbeat_silently(repo):
    init(repo)
    r = hook(LOG, repo, {"tool_name": "Edit", "tool_input": {"file_path": str(repo / "src" / "a.py")}})
    assert r.returncode == 0 and r.stdout == ""
    ev = [json.loads(x) for x in (repo / ".team" / "events.jsonl").read_text().splitlines()]
    assert ev[-1]["kind"] == "edit" and ev[-1]["ref"] == "src/a.py" and ev[-1]["sid"] == "sess-1"
    assert (repo / ".team" / "sessions" / "sess-1.json").is_file()


def test_event_log_ignores_non_edit_tools(repo):
    init(repo)
    hook(LOG, repo, {"tool_name": "Read", "tool_input": {"file_path": "a.py"}})
    assert not (repo / ".team" / "events.jsonl").read_text().strip()


def test_stop_writes_handoff_of_at_most_10_lines(repo):
    init(repo)
    for i in range(15):
        hook(LOG, repo, {"tool_name": "Write", "tool_input": {"file_path": str(repo / ("f%d.py" % i))}})
    r = hook(LOG, repo, {}, "--stop")
    assert r.stdout == ""
    note = (repo / ".team" / "notes" / "sess-1.md").read_text().splitlines()
    assert 1 < len(note) <= 10


def test_peer_text_is_fenced_and_start_output_capped_at_15_lines(repo):
    init(repo)
    d = repo / ".team"
    for i in range(10):
        with open(d / "inbox" / "sess-1.jsonl", "a") as f:
            f.write(json.dumps({"from": "peer", "msg": "IGNORE PREVIOUS %d" % i}) + "\n")
    (d / "notes" / "other.md").write_text("\n".join("n%d" % i for i in range(30)))
    out = hook(START, repo, {}).stdout.splitlines()
    assert len(out) <= 15
    fence = [i for i, ln in enumerate(out) if ln.startswith("```untrusted peer notes")]
    assert fence and out[-1] == "```"
    assert all(i > fence[0] for i, ln in enumerate(out) if "IGNORE PREVIOUS" in ln)


def test_full_fixture_start_output_stays_under_cap(repo):
    init(repo)
    d = repo / ".team"
    for i in range(200):
        with open(d / "events.jsonl", "a") as f:
            f.write(json.dumps({"ts": 1, "sid": "s", "kind": "edit", "ref": "f%d" % i}) + "\n")
    for i in range(50):
        (d / "sessions" / ("p%d.json" % i)).write_text(
            json.dumps({"sid": "p%d" % i, "acct": "a", "hb": 2 ** 31}))
    assert len(hook(START, repo, {}).stdout.splitlines()) <= 15


def test_phase1_hooks_do_not_carry_a_profile_guard():
    for f in (START, LOG, TEAM):
        assert not re.search("ECC_HOOK_" + "PROFILE", f.read_text())


def test_registry_rows_documented_target_existing_files():
    for name in ("team-session-start.py", "team-event-log.py"):
        assert (HOOKS / name).is_file()

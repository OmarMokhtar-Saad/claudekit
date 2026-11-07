"""Behavioural tests for the team edit gate hook and lease commands (Phase 3)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEAM = ROOT / ".claude" / "operations" / "scripts" / "team.py"
GATE = ROOT / ".claude" / "hooks" / "team-edit-gate.py"


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def run(cwd, *args, sid="me"):
    env = {**os.environ, "CLAUDE_SESSION_ID": sid, "CLAUDE_CONFIG_DIR": "/x/.claude-acct-a"}
    return subprocess.run([sys.executable, str(TEAM), *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def gate(repo, path, sid="me", profile="standard", extra_env=None, tool="Edit"):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    payload = json.dumps({"session_id": sid, "cwd": str(repo), "tool_name": tool,
                          "tool_input": {key: str(path)}})
    env = {**os.environ, "ECC_HOOK_PROFILE": profile, "LOG_FILE": str(repo / "hooks.log"),
           **(extra_env or {})}
    return subprocess.run([sys.executable, str(GATE)], input=payload, cwd=repo, env=env,
                          capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "commit", "--allow-empty", "-q", "-m", "init")
    assert run(r, "init").returncode == 0
    run(r, "status", sid="me")
    run(r, "status", sid="peer")
    return r


def new_task(repo, title, files, sid):
    run(repo, "task", "new", title, "--files", files, sid=sid)
    tid = json.loads((repo / ".team" / "tasks.jsonl").read_text().splitlines()[-1])["id"]
    assert run(repo, "claim", tid, sid=sid).returncode == 0
    return tid


def test_no_config_is_silent_allow(tmp_path):
    r = tmp_path / "plain"
    r.mkdir()
    git(r, "init", "-q")
    res = gate(r, r / "a.py")
    assert res.returncode == 0 and res.stderr == ""


def test_no_claimed_task_allows_with_note(repo):
    res = gate(repo, repo / "a.py")
    assert res.returncode == 0 and "no claimed task" in res.stderr


def test_peer_claimed_file_blocks_me(repo):
    new_task(repo, "peer work", "a.py", "peer")
    res = gate(repo, repo / "a.py")
    assert res.returncode == 2 and "a.py" in res.stderr
    assert len(res.stderr.strip().splitlines()) <= 3


def test_my_task_file_allowed_and_auto_leased(repo):
    new_task(repo, "mine", "b.py", "me")
    assert gate(repo, repo / "b.py").returncode == 0
    assert any((repo / ".team" / "leases").glob("*.json"))
    assert run(repo, "who", "b.py", sid="peer").stdout.startswith("held by me")


def test_path_outside_my_task_blocks(repo):
    tid = new_task(repo, "mine", "b.py", "me")
    res = gate(repo, repo / "c.py")
    assert res.returncode == 2 and "team plan" in res.stderr
    assert run(repo, "plan", tid, "--add-file", "c.py").returncode == 0
    assert gate(repo, repo / "c.py").returncode == 0


def test_hotspot_needs_lease(repo):
    res = gate(repo, repo / "pyproject.toml")
    assert res.returncode == 2 and "hotspot" in res.stderr
    assert run(repo, "lease", "pyproject.toml").returncode == 0
    assert gate(repo, repo / "pyproject.toml").returncode == 0


def test_lease_conflict_exit_4_and_unlease(repo):
    assert run(repo, "lease", "x.py", sid="peer").returncode == 0
    assert run(repo, "lease", "x.py").returncode == 4
    assert gate(repo, repo / "x.py").returncode == 2
    assert run(repo, "unlease", "x.py", sid="peer").returncode == 0
    assert run(repo, "lease", "x.py").returncode == 0


def test_dead_peer_lease_is_free(repo):
    assert run(repo, "lease", "x.py", sid="peer").returncode == 0
    sf = repo / ".team" / "sessions" / "peer.json"
    rec = json.loads(sf.read_text())
    rec["hb"] = 1
    sf.write_text(json.dumps(rec))
    assert gate(repo, repo / "x.py").returncode == 0
    assert "leases_freed=" in run(repo, "gc").stdout


def test_gc_orphans_dead_owners_task(repo):
    tid = new_task(repo, "peer work", "a.py", "peer")
    sf = repo / ".team" / "sessions" / "peer.json"
    rec = json.loads(sf.read_text())
    rec["hb"] = 1
    sf.write_text(json.dumps(rec))
    out = run(repo, "gc").stdout
    assert "orphaned=1" in out
    row = [json.loads(x) for x in (repo / ".team" / "tasks.jsonl").read_text().splitlines()
           if json.loads(x)["id"] == tid][0]
    assert row["state"] == "orphaned" and row["owner"] == ""


def test_team_dir_always_blocked_even_gate_off(repo):
    (repo / ".team" / "gate.off").write_text("")
    res = gate(repo, repo / ".team" / "tasks.jsonl")
    assert res.returncode == 2
    new_task(repo, "peer", "a.py", "peer")
    assert gate(repo, repo / "a.py").returncode == 0  # gate.off lets the rest through
    assert "GATE OFF" in run(repo, "status").stdout


def test_notebook_path_is_gated(repo):
    new_task(repo, "peer", "n.ipynb", "peer")
    assert gate(repo, repo / "n.ipynb", tool="NotebookEdit").returncode == 2


def test_corrupt_state_blocks_and_names_doctor(repo):
    (repo / ".team" / "tasks.jsonl").write_text("{not json\n")
    res = gate(repo, repo / "a.py")
    assert res.returncode == 2 and "team doctor" in res.stderr


def test_lock_held_blocks_busy(repo):
    import fcntl
    fh = open(repo / ".team" / ".lock", "a+")
    fcntl.flock(fh, fcntl.LOCK_EX)
    try:
        res = gate(repo, repo / "a.py")
    finally:
        fh.close()
    assert res.returncode == 2 and "busy" in res.stderr


def test_unexpected_exception_fails_closed(repo, tmp_path):
    # a sitecustomize that makes gate_decision explode
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "sitecustomize.py").write_text(
        "import sys\nsys.path.insert(0, %r)\nimport team\n"
        "def boom(*a, **k):\n    raise RuntimeError('x')\nteam.gate_decision = boom\n"
        % str(TEAM.parent))
    res = gate(repo, repo / "a.py", extra_env={"PYTHONPATH": str(sc)})
    assert res.returncode == 2 and "RuntimeError" in res.stderr


def test_minimal_profile_never_blocks_but_logs(repo):
    new_task(repo, "peer", "a.py", "peer")
    res = gate(repo, repo / "a.py", profile="minimal")
    assert res.returncode == 0
    assert "WOULD-BLOCK" in (repo / "hooks.log").read_text()


def test_mutation_always_allow_would_fail_blocking_tests(repo, tmp_path):
    """Prove the blocking tests bind: with gate_decision patched to allow, a peer's file passes."""
    new_task(repo, "peer", "a.py", "peer")
    assert gate(repo, repo / "a.py").returncode == 2
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "sitecustomize.py").write_text(
        "import sys\nsys.path.insert(0, %r)\nimport team\n"
        "team.gate_decision = lambda *a, **k: (None, '')\n" % str(TEAM.parent))
    assert gate(repo, repo / "a.py", extra_env={"PYTHONPATH": str(sc)}).returncode == 0


def test_registry_rows_resolve_to_hook_files():
    reg = json.loads((ROOT / ".claude" / "hooks" / "dispatch-registry.json").read_text())
    rows = [r for ev in reg.values() if isinstance(ev, list) for r in ev if isinstance(r, dict)
            and str(r.get("id", "")).startswith("team-")]
    for r in rows:
        assert (ROOT / ".claude" / "hooks" / r["file"]).is_file(), r

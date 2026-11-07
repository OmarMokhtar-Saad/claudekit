"""Behavioural tests for opt-in task stages (Phase 4)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEAM = ROOT / ".claude" / "operations" / "scripts" / "team.py"
GATE = ROOT / ".claude" / "hooks" / "team-edit-gate.py"
ENV_GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **ENV_GIT}).stdout.strip()


def run(cwd, *args, sid="me"):
    env = {**os.environ, "CLAUDE_SESSION_ID": sid, "CLAUDE_CONFIG_DIR": "/x/.claude-acct-a"}
    return subprocess.run([sys.executable, str(TEAM), *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def gate(cwd, path, sid="me", extra_env=None):
    payload = json.dumps({"session_id": sid, "cwd": str(cwd), "tool_name": "Edit",
                          "tool_input": {"file_path": str(path)}})
    env = {**os.environ, "ECC_HOOK_PROFILE": "standard", "LOG_FILE": str(cwd / "hooks.log"),
           **(extra_env or {})}
    return subprocess.run([sys.executable, str(GATE)], input=payload, cwd=cwd, env=env,
                          capture_output=True, text=True)


def set_cfg(main, **kw):
    f = main / ".team" / "config.json"
    cfg = json.loads(f.read_text())
    cfg.update(kw)
    f.write_text(json.dumps(cfg))


def row(main, tid):
    rows = [json.loads(x) for x in (main / ".team" / "tasks.jsonl").read_text().splitlines()]
    return [r for r in rows if r["id"] == tid][0]


@pytest.fixture()
def env(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    (main / "a.txt").write_text("a\n")
    git(main, "add", ".")
    git(main, "commit", "-q", "-m", "init")
    (main / ".git" / "info" / "exclude").write_text(".team/\n")
    assert run(main, "init").returncode == 0
    set_cfg(main, stages=True, land="local", test_cmd="true", fmt_cmd="true", base="main")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "feat", str(wt))
    run(wt, "status")
    run(wt, "status", sid="peer")
    run(wt, "task", "new", "work", "--files", "a.txt")
    tid = json.loads((main / ".team" / "tasks.jsonl").read_text().splitlines()[-1])["id"]
    assert run(wt, "claim", tid).returncode == 0
    return main, wt, tid


def to_planned(wt, tid):
    assert run(wt, "debug", tid, "--repro", "fails").returncode == 0
    assert run(wt, "plan", tid, "--files", "a.txt").returncode == 0


def to_implementing(wt, tid):
    to_planned(wt, tid)
    assert run(wt, "review", tid, "--approve", sid="peer").returncode == 0
    assert run(wt, "start", tid).returncode == 0


def test_gate_blocks_planned_task_file(env):
    main, wt, tid = env
    to_planned(wt, tid)
    res = gate(wt, wt / "a.txt")
    assert res.returncode == 2 and "planned" in res.stderr and "implementing" in res.stderr


def test_gate_mutation_always_allow_would_pass(env, tmp_path):
    # proves the block above comes from team.gate_decision, not something else
    main, wt, tid = env
    to_planned(wt, tid)
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "sitecustomize.py").write_text(
        "import sys\nsys.path.insert(0, %r)\nimport team\n"
        "team.gate_decision = lambda *a, **k: (None, '')\n"
        % str(TEAM.parent))
    res = gate(wt, wt / "a.txt", extra_env={"PYTHONPATH": str(sc)})
    assert res.returncode == 0


def test_gate_allows_at_implementing(env):
    main, wt, tid = env
    to_implementing(wt, tid)
    assert gate(wt, wt / "a.txt").returncode == 0


def test_gate_blocks_session_without_task(env):
    main, wt, tid = env
    res = gate(wt, wt / "b.txt", sid="peer")
    assert res.returncode == 2 and "quick" in res.stderr


def test_full_flow_to_land(env):
    main, wt, tid = env
    to_implementing(wt, tid)
    (wt / "a.txt").write_text("changed\n")
    git(wt, "commit", "-qam", "work")
    assert run(wt, "verify", tid).returncode == 0
    assert row(main, tid)["state"] == "verifying"
    r = run(wt, "land", tid)
    assert r.returncode == 0, r.stderr
    assert git(main, "show", "main:a.txt") == "changed"


def test_land_requires_verifying(env):
    main, wt, tid = env
    to_implementing(wt, tid)
    r = run(wt, "land", tid)
    assert r.returncode == 4 and "team verify" in r.stderr


def test_self_approve_exits_4(env):
    main, wt, tid = env
    to_planned(wt, tid)
    assert run(wt, "review", tid, "--approve").returncode == 4
    assert row(main, tid)["state"] == "planned"


def test_review_non_planned_exits_4(env):
    main, wt, tid = env
    assert run(wt, "review", tid, "--approve", sid="peer").returncode == 4


def test_reject_keeps_planned(env):
    main, wt, tid = env
    to_planned(wt, tid)
    assert run(wt, "review", tid, "--reject", "too wide", sid="peer").returncode == 0
    assert row(main, tid)["state"] == "planned"


def test_plan_without_repro_exits_4(env):
    main, wt, tid = env
    assert run(wt, "debug", tid).returncode == 0
    assert run(wt, "plan", tid, "--files", "a.txt").returncode == 4


def test_plan_from_claimed_exits_4(env):
    main, wt, tid = env
    r = run(wt, "plan", tid, "--files", "a.txt")
    assert r.returncode == 4 and "debug" in r.stderr


def test_start_stale_base_exits_4(env):
    main, wt, tid = env
    to_planned(wt, tid)
    assert run(wt, "review", tid, "--approve", sid="peer").returncode == 0
    (main / "z.txt").write_text("z\n")
    git(main, "add", "z.txt")
    git(main, "commit", "-qm", "z")
    r = run(wt, "start", tid)
    assert r.returncode == 4 and "rebase" in r.stderr
    assert row(main, tid)["state"] == "reviewed"


def test_verify_failing_tests_exits_7(env):
    main, wt, tid = env
    to_implementing(wt, tid)
    set_cfg(main, test_cmd="false")
    assert run(wt, "verify", tid).returncode == 7
    assert row(main, tid)["state"] == "implementing"


def test_verify_unset_test_cmd_exits_3(env):
    main, wt, tid = env
    to_implementing(wt, tid)
    set_cfg(main, test_cmd="")
    assert run(wt, "verify", tid).returncode == 3


def test_unblock_peer_holds_exits_4_force_ok(env):
    main, wt, tid = env
    to_planned(wt, tid)
    f = main / ".team" / "tasks.jsonl"
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    for r in rows:
        if r["id"] == tid:
            r["state"] = "blocked"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    q = run(wt, "quick", "peer edit", "--file", "a.txt", sid="peer")
    assert q.returncode == 0, q.stderr
    assert run(wt, "unblock", tid).returncode == 4
    assert run(wt, "unblock", tid, "--force").returncode == 0
    assert row(main, tid)["state"] == "planned"


def test_quick_hotspot_exits_4(env):
    main, wt, tid = env
    assert run(wt, "quick", "lock", "--file", "uv.lock", sid="peer").returncode == 4


def test_quick_goes_to_implementing(env):
    main, wt, tid = env
    r = run(wt, "quick", "tiny", "--file", "b.txt", sid="peer")
    assert r.returncode == 0
    assert row(main, r.stdout.strip())["state"] == "implementing"


def test_stages_off_rollback(env):
    main, wt, tid = env
    to_implementing(wt, tid)
    set_cfg(main, stages=False)
    assert gate(wt, wt / "a.txt").returncode == 0
    (wt / "a.txt").write_text("changed\n")
    git(wt, "commit", "-qam", "work")
    r = run(wt, "land", tid)
    assert r.returncode == 0, r.stderr
    assert run(wt, "debug", tid).returncode == 3

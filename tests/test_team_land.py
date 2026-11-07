"""Behavioural tests for `team land` (Phase 3), using a real repo with a linked worktree."""
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEAM = ROOT / ".claude" / "operations" / "scripts" / "team.py"
ENV_GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **ENV_GIT}).stdout.strip()


def run(cwd, *args, sid="me"):
    env = {**os.environ, **ENV_GIT, "CLAUDE_SESSION_ID": sid,
           "CLAUDE_CONFIG_DIR": "/x/.claude-acct-a"}
    return subprocess.run([sys.executable, str(TEAM), *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def set_cfg(main, **kw):
    f = main / ".team" / "config.json"
    cfg = json.loads(f.read_text())
    cfg.update(kw)
    f.write_text(json.dumps(cfg))


@pytest.fixture()
def env(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    (main / "base.txt").write_text("base\n")
    (main / "a.txt").write_text("a\n")
    git(main, "add", ".")
    git(main, "commit", "-q", "-m", "init")
    (main / ".git" / "info" / "exclude").write_text(".team/\n")
    assert run(main, "init").returncode == 0
    set_cfg(main, land="local", test_cmd="true", fmt_cmd="true", base="main")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "feat", str(wt))
    run(wt, "status")
    run(wt, "task", "new", "work", "--files", "a.txt")
    tid = json.loads((main / ".team" / "tasks.jsonl").read_text().splitlines()[-1])["id"]
    assert run(wt, "claim", tid).returncode == 0
    return main, wt, tid


def commit(wt, name, text="x\n", msg="work"):
    (wt / name).write_text(text)
    git(wt, "add", name)
    git(wt, "commit", "-q", "-m", msg)


def state(main, tid):
    rows = [json.loads(x) for x in (main / ".team" / "tasks.jsonl").read_text().splitlines()]
    return [r for r in rows if r["id"] == tid][0]["state"]


def test_land_unset_exits_3(env):
    main, wt, tid = env
    set_cfg(main, land="")
    assert run(wt, "land", tid).returncode == 3


def test_test_cmd_unset_exits_3(env):
    main, wt, tid = env
    set_cfg(main, test_cmd="")
    assert run(wt, "land", tid).returncode == 3


def test_land_ff_merges_and_compacts_task(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    r = run(wt, "land", tid)
    assert r.returncode == 0, r.stderr
    assert (main / "a.txt").read_text() == "changed\n"
    assert state(main, tid) == "landed"
    assert git(main, "rev-parse", "main") == git(wt, "rev-parse", "HEAD")


def test_extra_changed_path_exits_6(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    commit(wt, "other.txt")
    before = git(main, "rev-parse", "main")
    r = run(wt, "land", tid)
    assert r.returncode == 6 and "other.txt" in r.stderr
    assert git(main, "rev-parse", "main") == before


def test_rebase_conflict_exits_5_clean_tree_base_unchanged(env):
    main, wt, tid = env
    commit(wt, "a.txt", "mine\n")
    (main / "a.txt").write_text("theirs\n")
    git(main, "commit", "-qam", "theirs")
    before = git(main, "rev-parse", "main")
    r = run(wt, "land", tid)
    assert r.returncode == 5 and "a.txt" in r.stderr
    assert git(wt, "status", "--porcelain") == ""
    assert git(main, "rev-parse", "main") == before
    assert state(main, tid) == "claimed"


def test_second_land_while_queue_busy_exits_4(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    fh = open(main / ".team" / "land.lock", "a+")
    fcntl.flock(fh, fcntl.LOCK_EX)
    try:
        r = run(wt, "land", tid)
    finally:
        fh.close()
    assert r.returncode == 4 and "queue busy" in r.stderr


def test_base_moved_during_land_exits_4(env, tmp_path):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    # test_cmd advances main while tests run: base moved after the rebase
    script = tmp_path / "move.sh"
    script.write_text("#!/bin/sh\ncd %s && echo z > z.txt && git add z.txt && "
                      "git -c user.name=t -c user.email=t@t commit -qm z\n" % main)
    script.chmod(0o755)
    set_cfg(main, test_cmd=str(script))
    r = run(wt, "land", tid)
    assert r.returncode == 4 and "moved" in r.stderr
    assert state(main, tid) == "claimed"


def test_resume_is_idempotent(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    assert run(wt, "land", tid).returncode == 0
    r1 = run(wt, "land", tid, "--resume")
    r2 = run(wt, "land", tid, "--resume")
    assert r1.returncode == 0 and r2.returncode == 0 and "already landed" in r2.stdout


def test_resume_refuses_when_not_merged(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    assert run(wt, "land", tid, "--resume").returncode == 4


def test_dirty_main_checkout_exits_8(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    (main / "base.txt").write_text("dirty\n")
    r = run(wt, "land", tid)
    assert r.returncode == 8 and "dirty" in r.stderr


def test_main_checkout_off_base_exits_8(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    git(main, "checkout", "-q", "-b", "side")
    r = run(wt, "land", tid)
    assert r.returncode == 8 and "not on main" in r.stderr


def test_live_peer_in_main_checkout_exits_8(env):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    assert run(main, "lease", "zzz.txt", sid="peer").returncode == 0
    r = run(wt, "land", tid)
    assert r.returncode == 8 and "main checkout" in r.stderr


def test_gatekeeper_mode_leaves_base_and_prints_steps(env):
    main, wt, tid = env
    set_cfg(main, land="gatekeeper")
    commit(wt, "a.txt", "changed\n")
    before = git(main, "rev-parse", "main")
    r = run(wt, "land", tid)
    assert r.returncode == 0 and "gatekeeper" in r.stdout and "untouched" in r.stdout
    assert git(main, "rev-parse", "main") == before


def test_bookkeeping_failure_prints_undo_does_not_run_it(env, tmp_path):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    pre = git(main, "rev-parse", "main")
    code = ("import sys\nsys.path.insert(0, %r)\nimport team\n"
            "def boom(*a, **k):\n    raise OSError('disk')\n"
            "team.finish_land = boom\nsys.exit(team.main(['land', %r]))\n"
            % (str(TEAM.parent), tid))
    env_ = {**os.environ, "CLAUDE_SESSION_ID": "me", "CLAUDE_CONFIG_DIR": "/x/.claude-acct-a"}
    r = subprocess.run([sys.executable, "-c", code], cwd=wt, env=env_,
                       capture_output=True, text=True)
    assert r.returncode == 1 and "reset --hard %s" % pre in r.stderr
    assert git(main, "rev-parse", "main") != pre  # merge stayed; undo only printed


def test_fmt_touches_only_task_files(env, tmp_path):
    main, wt, tid = env
    commit(wt, "a.txt", "changed\n")
    (wt / "stray.txt").write_text("untracked\n")
    fmt = tmp_path / "fmt.sh"
    fmt.write_text("#!/bin/sh\nfor f in \"$@\"; do echo fmt >> \"$f\"; done\n")
    fmt.chmod(0o755)
    set_cfg(main, fmt_cmd="%s {files}" % fmt)
    r = run(wt, "land", tid, "--fmt")
    assert r.returncode == 0, r.stderr
    assert (main / "a.txt").read_text().endswith("fmt\n")
    assert not (main / "stray.txt").exists()

"""Race tests for `team claim` (Phase 2): exactly one of N processes wins."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAM = ROOT / ".claude" / "operations" / "scripts" / "team.py"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def spawn(cwd, sid, *args):
    env = {**os.environ, **GIT_ENV, "CLAUDE_SESSION_ID": sid,
           "CLAUDE_CONFIG_DIR": "/x/.claude-acct-" + sid}
    return subprocess.Popen([sys.executable, str(TEAM), *args], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_eight_processes_race_one_claim_exactly_one_wins(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (["init", "-q"], ["commit", "--allow-empty", "-q", "-m", "i"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True,
                       env={**os.environ, **GIT_ENV})
    assert spawn(repo, "s0", "init").wait() == 0
    assert spawn(repo, "s0", "task", "new", "contested").wait() == 0
    procs = [spawn(repo, "racer%d" % i, "claim", "T1") for i in range(8)]
    codes = [p.wait() for p in procs]
    assert codes.count(0) == 1, codes
    assert codes.count(4) == 7, codes
    tasks = (repo / ".team" / "tasks.jsonl").read_text().strip().splitlines()
    assert len(tasks) == 1 and '"state":"claimed"' in tasks[0]

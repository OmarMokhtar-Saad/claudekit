"""A rollback leaves a DURABLE record of what it deleted.

OperationTransaction.rollback() os.unlink()s every file the run created and
reported it on stdout only. Inside a subagent that stdout dies with the agent's
transcript, so a created file could vanish with nothing surviving the session
to say so. The audit line lives beside the backups, with the other durable
record of what a run did.

Method: force a REAL rollback -- op 1 creates a file, op 2 fails on an anchor
that does not exist -- then assert the created file is gone AND that
backups/<run>/rollback.log names it.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / ".claude" / "operations" / "scripts"
EXE = SCRIPTS / "execute-json-ops.py"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=True)


@pytest.fixture()
def repo(tmp_path):
    p = tmp_path / "repo"
    p.mkdir()
    git(p, "init", "-q", "-b", "main")
    git(p, "config", "user.email", "t@example.com")
    git(p, "config", "user.name", "t")
    (p / "victim.txt").write_text("ORIGINAL\n", encoding="utf-8")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "init")
    return p


def failing_config(repo: Path) -> Path:
    cfg = repo / "ops.json"
    cfg.write_text(json.dumps({
        "plan": "rollback-audit-fixture",
        "operations": [
            {"type": "file_create", "path": "created.txt", "content": "NEW\n"},
            {"type": "code_edit", "path": "victim.txt",
             "edits": [{"find": "ORIGINAL", "replace": "EDITED"}]},
        ],
    }, indent=2), encoding="utf-8")
    return cfg


def run_exe(cfg: Path, repo: Path, exe: Path = EXE, *extra):
    return subprocess.run(
        [sys.executable, str(exe), str(cfg), "--no-approval", "--skip-validation", *extra],
        cwd=str(repo), capture_output=True, text=True)


def force_rollback(repo: Path, exe: Path = EXE):
    """Make op 2 fail AFTER op 1 has written, by moving the anchor out from
    under it once the config has already been validated."""
    cfg = failing_config(repo)
    (repo / "victim.txt").write_text("SOMETHING ELSE\n", encoding="utf-8")
    return run_exe(cfg, repo, exe)


class TestRollbackAudit:
    def test_rollback_records_what_it_removed(self, repo):
        proc = force_rollback(repo)
        assert proc.returncode != 0, proc.stdout
        assert not (repo / "created.txt").exists()
        logs = list((repo / "backups").glob("*/rollback.log"))
        assert logs, f"no rollback.log under backups/: {proc.stdout}"
        lines = [json.loads(line) for line in
                 logs[0].read_text(encoding="utf-8").splitlines() if line.strip()]
        actions = {entry["action"] for entry in lines}
        assert "rollback_start" in actions and "rollback_complete" in actions
        removed = [entry for entry in lines if entry["action"] == "removed"]
        assert removed, lines
        assert removed[0]["path"].endswith("created.txt")
        # The tree is named, because the incident this exists for was a file
        # created in the WRONG tree and then removed.
        assert removed[0]["tree"]
        assert removed[0]["pid"]

    def test_audit_failure_cannot_break_rollback(self, repo, monkeypatch):
        """A rollback whose audit cannot be written must still roll back."""
        (repo / "backups").write_text("not a directory\n", encoding="utf-8")
        proc = force_rollback(repo)
        assert proc.returncode != 0
        assert not (repo / "created.txt").exists()

    def test_mutation_control_audit_is_a_noop(self, repo, tmp_path):
        src = EXE.read_text(encoding="utf-8")
        anchor = '                    self._audit("removed", fp)'
        assert src.count(anchor) == 1
        mutated = SCRIPTS / "_mutant_noaudit_execute.py"
        mutated.write_text(src.replace(anchor, "                    pass"),
                           encoding="utf-8")
        try:
            proc = force_rollback(repo, exe=mutated)
            assert proc.returncode != 0
            logs = list((repo / "backups").glob("*/rollback.log"))
            text = logs[0].read_text(encoding="utf-8") if logs else ""
            assert '"action": "removed"' not in text, (
                "the removal line survived the mutation: the assertion above "
                "is not caused by _audit")
        finally:
            mutated.unlink(missing_ok=True)

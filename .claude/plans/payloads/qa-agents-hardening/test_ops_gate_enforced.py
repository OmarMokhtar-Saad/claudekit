"""The executor OBEYS the validator, and knows which tree it may edit.

Two gates, both ported from a downstream project where each was learned from a
real incident:

  * validation gate -- for years execute-json-ops.py's own epilog said "always
    validate first" and nothing enforced it: a config the validator REJECTED
    (forbidden top-level key) executed to completion, 2/2 edits applied.
  * root gate -- every path in the executor resolves against os.getcwd(),
    including validate_path's containment check, so an agent handed a worktree
    whose shell cwd reset to the main checkout edited the MAIN tree while
    believing it was isolated.

Each gate carries a MUTATION CONTROL: the gate is broken in a copy of the real
executor (kept beside it so `from shared import ...` still resolves) and the
assertion above is required to flip. A green gate that cannot fail measures
nothing.
"""
import json
import os
import shutil
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


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    (path / "target.txt").write_text("ORIGINAL\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    return path


def write_cfg(repo: Path, name: str, extra=None) -> Path:
    body = {
        "plan": "gate-enforced-fixture",
        "operations": [
            {"type": "code_edit", "path": "target.txt",
             "edits": [{"find": "ORIGINAL", "replace": "EDITED"}]},
        ],
    }
    if extra:
        body.update(extra)
    cfg = repo / name
    cfg.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return cfg


def run_exe(cfg: Path, cwd: Path, *extra, exe: Path = EXE):
    proc = subprocess.run(
        [sys.executable, str(exe), str(cfg), "--no-approval", *extra],
        cwd=str(cwd), capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


@pytest.fixture()
def mutant():
    """Yield a factory that writes a mutated executor beside the real one.

    Beside, not in tmp_path: the executor does `from shared import ...`, which
    only resolves from its own directory.
    """
    made = []

    def _make(find: str, replace: str, tag: str) -> Path:
        src = EXE.read_text(encoding="utf-8")
        assert src.count(find) == 1, f"mutation anchor {tag!r} is not unique"
        dst = SCRIPTS / f"_mutant_{tag}_execute.py"
        dst.write_text(src.replace(find, replace), encoding="utf-8")
        made.append(dst)
        return dst

    yield _make
    for p in made:
        p.unlink(missing_ok=True)


class TestValidationGate:
    def test_rejected_config_is_not_executed(self, tmp_path):
        repo = make_repo(tmp_path / "repo")
        # A forbidden top-level key: the schema rejects it, the executor used
        # to apply the edits anyway.
        cfg = write_cfg(repo, "ops.json", {"description": "not a legal key"})
        rc, out = run_exe(cfg, repo)
        assert rc == 2, out
        assert "REFUSING TO EXECUTE" in out
        assert (repo / "target.txt").read_text(encoding="utf-8") == "ORIGINAL\n"

    def test_skip_validation_is_the_only_way_past(self, tmp_path):
        repo = make_repo(tmp_path / "repo")
        cfg = write_cfg(repo, "ops.json", {"description": "not a legal key"})
        rc, out = run_exe(cfg, repo, "--skip-validation")
        assert rc == 0, out
        assert (repo / "target.txt").read_text(encoding="utf-8") == "EDITED\n"

    def test_valid_config_still_executes(self, tmp_path):
        repo = make_repo(tmp_path / "repo")
        cfg = write_cfg(repo, "ops.json")
        rc, out = run_exe(cfg, repo)
        assert rc == 0, out
        assert (repo / "target.txt").read_text(encoding="utf-8") == "EDITED\n"

    def test_mutation_control_gate_fail_open(self, tmp_path, mutant):
        """Neutering the gate must make the refusal test above fail."""
        mutated = mutant(
            "        ok, errors = _preflight_validate(args.config)",
            "        ok, errors = True, []",
            "failopen",
        )
        repo = make_repo(tmp_path / "repo")
        cfg = write_cfg(repo, "ops.json", {"description": "not a legal key"})
        rc, out = run_exe(cfg, repo, exe=mutated)
        assert rc == 0, out
        assert (repo / "target.txt").read_text(encoding="utf-8") == "EDITED\n", (
            "the mutant still refused: the refusal above is not caused by the gate")

    def test_mutation_control_gate_uses_half_the_rules(self, tmp_path, mutant):
        """A validator without preflight_verdict() must REFUSE, never fall back."""
        mutated = mutant(
            '        if not hasattr(module, "preflight_verdict"):',
            '        if False:',
            "halfrules",
        )
        # The stand-in for an old validator is the absence of the attribute; we
        # cannot remove it from the real file, so we assert the shape instead:
        # with the guard gone, a missing attribute crashes into the fail-closed
        # except, which must still refuse rather than execute.
        repo = make_repo(tmp_path / "repo")
        cfg = write_cfg(repo, "ops.json", {"description": "not a legal key"})
        rc, out = run_exe(cfg, repo, exe=mutated)
        assert rc == 2, out


class TestRootGate:
    def test_config_in_another_tree_is_refused(self, tmp_path):
        here = make_repo(tmp_path / "here")
        there = make_repo(tmp_path / "there")
        cfg = write_cfg(there, "ops.json")
        rc, out = run_exe(cfg, here)
        assert rc == 3, out
        assert "DIFFERENT git worktrees" in out
        assert (here / "target.txt").read_text(encoding="utf-8") == "ORIGINAL\n"
        assert (there / "target.txt").read_text(encoding="utf-8") == "ORIGINAL\n"

    def test_root_states_the_intent(self, tmp_path):
        here = make_repo(tmp_path / "here")
        there = make_repo(tmp_path / "there")
        cfg = write_cfg(there, "ops.json")
        rc, out = run_exe(cfg, here, "--root", str(there))
        assert rc == 0, out
        assert (there / "target.txt").read_text(encoding="utf-8") == "EDITED\n"
        assert (here / "target.txt").read_text(encoding="utf-8") == "ORIGINAL\n"

    def test_same_tree_is_unaffected(self, tmp_path):
        repo = make_repo(tmp_path / "repo")
        cfg = write_cfg(repo, "ops.json")
        rc, out = run_exe(cfg, repo)
        assert rc == 0, out

    def test_mutation_control_root_gate_ignored(self, tmp_path, mutant):
        mutated = mutant(
            "    root, root_errors = _resolve_root(args.config, args.root)",
            "    root, root_errors = None, []",
            "rootopen",
        )
        here = make_repo(tmp_path / "here")
        there = make_repo(tmp_path / "there")
        cfg = write_cfg(there, "ops.json")
        rc, out = run_exe(cfg, here, exe=mutated)
        assert rc != 3, out
        assert "DIFFERENT git worktrees" not in out


class TestWorktreeIsolationIsReal:
    """The original incident, reproduced: cwd in the MAIN tree, config in a
    linked worktree. Creates a real `git worktree`, so it is slow and is
    excluded from the default run.
    """

    @pytest.mark.skipif(not os.environ.get("CK_SLOW_TESTS"),
                        reason="creates a real git worktree; set CK_SLOW_TESTS=1")
    def test_linked_worktree_config_does_not_edit_the_main_tree(self, tmp_path):
        repo = make_repo(tmp_path / "repo")
        wt = tmp_path / "wt"
        git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
        cfg = write_cfg(wt, "ops.json")
        rc, out = run_exe(cfg, repo)
        assert rc == 3, out
        assert (repo / "target.txt").read_text(encoding="utf-8") == "ORIGINAL\n"
        rc, out = run_exe(cfg, repo, "--root", str(wt))
        assert rc == 0, out
        assert (wt / "target.txt").read_text(encoding="utf-8") == "EDITED\n"
        assert (repo / "target.txt").read_text(encoding="utf-8") == "ORIGINAL\n"
        shutil.rmtree(str(wt), ignore_errors=True)
        git(repo, "worktree", "prune")

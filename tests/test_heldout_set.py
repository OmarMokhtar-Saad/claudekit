"""Behavioural tests for the frozen held-out review set.

The script is executed; nothing here imports it or asserts on its structure. Each test
names the weaker version it replaces, because "asserted structurally, not executed" is a
recorded defect of this repo's own review history.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ["ECC_HOOK_PROFILE"] = "minimal"

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "heldout-check.py"
MANIFEST = REPO / ".claude" / "knowledge" / "heldout" / "MANIFEST.json"


def run(*argv, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT)] + list(argv),
                          cwd=str(cwd or REPO), capture_output=True, text=True, timeout=120)


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def mirror(tmp_path):
    """A real project root holding only what the manifest points at."""
    data = manifest()
    for fixture in data["fixtures"]:
        for key in ("plan", "snapshot", "record"):
            src = REPO / fixture[key]
            dst = tmp_path / fixture[key]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
    dst = tmp_path / ".claude" / "knowledge" / "heldout" / "MANIFEST.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(MANIFEST), str(dst))
    return tmp_path


class TestTheSetIsActuallyFrozen:
    def test_every_pinned_hash_is_true_right_now(self):
        """The recorded defect this replaces: a claim assessed structurally rather than
        executed. A transcribed-but-stale hash passes any test that only reads the
        manifest; this one runs the checker over the real tree."""
        out = run("--verify")
        assert out.returncode == 0, out.stdout + out.stderr
        assert out.stdout.count("OK ") == 2 * len(manifest()["fixtures"])

    def test_a_mutated_fixture_is_reported_DRIFTED(self, tmp_path):
        """A verifier that passed on any tree would freeze nothing at all. The mutation
        is one byte appended to a real fixture in a real mirror."""
        root = mirror(tmp_path)
        target = root / manifest()["fixtures"][0]["plan"]
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        out = run("--verify", "--root", str(root))
        assert out.returncode == 4, out.stdout
        assert "DRIFTED" in out.stdout

    def test_a_missing_fixture_is_not_a_silent_skip(self, tmp_path):
        root = mirror(tmp_path)
        (root / manifest()["fixtures"][0]["snapshot"]).unlink()
        out = run("--verify", "--root", str(root))
        assert out.returncode == 4 and "MISSING" in out.stdout


class TestScoringAReplay:
    def _results(self, tmp_path, overrides=None, drop=()):
        data = manifest()
        verdicts = {}
        for fixture in data["fixtures"]:
            if fixture["id"] in drop:
                continue
            verdicts[fixture["id"]] = {"score": fixture["score"],
                                       "decision": fixture["decision"]}
        for fid, value in (overrides or {}).items():
            verdicts[fid] = value
        path = tmp_path / "results.json"
        path.write_text(json.dumps({"prompt_version": "test", "verdicts": verdicts}),
                        encoding="utf-8")
        return path

    def test_an_unchanged_replay_passes(self, tmp_path):
        out = run("--results", str(self._results(tmp_path)))
        assert out.returncode == 0, out.stdout + out.stderr
        assert "did not become HARSHER" in out.stdout

    def test_a_decision_flip_fails_with_a_nonzero_exit(self, tmp_path):
        """The exit code IS the gate. A harness that printed REGRESSION and exited 0
        would let the edit ship, and every reader would believe it had been checked."""
        fid = manifest()["fixtures"][0]["id"]
        path = self._results(tmp_path, overrides={fid: {"score": 70, "decision": "REVISE"}})
        out = run("--results", str(path))
        assert out.returncode == 5, out.stdout
        assert "REGRESSION" in out.stderr

    def test_a_score_wobble_alone_does_not_fail(self, tmp_path):
        """Gating on +-2 would make the harness a coin toss: the same plan scores 92 or
        94 across runs. The delta is reported and not gated, and that is asserted."""
        fid = manifest()["fixtures"][0]["id"]
        base = manifest()["fixtures"][0]["score"]
        path = self._results(tmp_path,
                             overrides={fid: {"score": base - 2, "decision": "APPROVED"}})
        out = run("--results", str(path))
        assert out.returncode == 0, out.stdout + out.stderr
        assert "mean score delta" in out.stdout

    def test_a_missing_verdict_is_a_failure_not_a_skip(self, tmp_path):
        """Otherwise "no regression" is reachable by simply not replaying the fixtures
        that would have regressed."""
        fid = manifest()["fixtures"][0]["id"]
        out = run("--results", str(self._results(tmp_path, drop=(fid,))))
        assert out.returncode == 5 and "MISSING" in out.stderr

    def test_scoring_refuses_over_a_drifted_set(self, tmp_path):
        """A clean score over artifacts that moved is worse than no score."""
        root = mirror(tmp_path)
        target = root / manifest()["fixtures"][0]["plan"]
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        out = run("--results", str(self._results(tmp_path)), "--root", str(root))
        assert out.returncode == 4, out.stdout


class TestTheLimitationIsStatedWhereItIsRead:
    def test_the_readme_and_the_manifest_both_say_it_is_one_directional(self):
        readme = (REPO / ".claude" / "knowledge" / "heldout" / "README.md").read_text(
            encoding="utf-8")
        assert "cannot catch" in readme.casefold()
        assert "laxer" in manifest()["limitation"]

    def test_the_analyst_prompt_points_at_the_real_path(self):
        body = (REPO / ".claude" / "agents" / "flow-analyst.md").read_text(encoding="utf-8")
        assert ".claude/knowledge/heldout/" in body
        assert "heldout-check.py" in body

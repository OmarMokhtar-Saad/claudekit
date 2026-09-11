"""Behavioral contract of the approval gate in execute-json-ops.py.

The reviewer verdict recorded by review-record.py is only a gate if the executor
refuses to mutate anything without it. These tests run the real executor against
a throwaway project tree (never the repo) and assert on the working tree after the
run: refused runs must leave the target byte-identical.

Matrix: no record / drift / CONDITIONAL / REJECTED / APPROVED / --no-approval /
--dry-run / config outside a plans dir / renamed config with a live record.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXECUTOR = REPO / ".claude" / "operations" / "scripts" / "execute-json-ops.py"
RECORDER = REPO / ".claude" / "operations" / "scripts" / "review-record.py"

ORIGINAL = "VALUE = 1\n"
PATCHED = "VALUE = 99\n"


def _env(**extra):
    env = dict(os.environ)
    env["ECC_HOOK_PROFILE"] = "minimal"
    env.pop("ECC_OPS_GATE_ALL", None)
    env.update(extra)
    return env


def result_json(output: str) -> dict:
    """The executor's machine-readable verdict — the only thing that tells a
    refused run apart from a failed one (both exit 1)."""
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT-JSON:")]
    assert lines, f"no RESULT-JSON line in output:\n{output}"
    return json.loads(lines[-1][len("RESULT-JSON:"):])


def _ops_payload(plan="demo", target="src/app.py"):
    return {
        "plan": plan,
        "operations": [
            {
                "type": "code_edit",
                "path": target,
                "edits": [{"find": "VALUE = 1", "replace": "VALUE = 99"}],
            }
        ],
    }


def _write_ops(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def project(tmp_path):
    """A minimal ClaudeKit-shaped project: .claude/, a plans dir, one target file."""
    root = tmp_path / "proj"
    (root / ".claude" / "plans").mkdir(parents=True)
    (root / ".claude" / "reports" / "reviews").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(ORIGINAL, encoding="utf-8")
    return root


def run_executor(project: Path, config: Path, *extra, **envvars):
    return subprocess.run(
        [sys.executable, str(EXECUTOR), str(config), *extra],
        capture_output=True, text=True, cwd=str(project), timeout=120,
        env=_env(**envvars),
    )


def record(project: Path, slug: str, config: Path, score: int, decision: str):
    proc = subprocess.run(
        [sys.executable, str(RECORDER), "write", f".claude/plans/plan-{slug}.md",
         str(config), "--score", str(score), "--decision", decision],
        capture_output=True, text=True, cwd=str(project), timeout=60, env=_env(),
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return proc


def target_text(project: Path) -> str:
    return (project / "src" / "app.py").read_text(encoding="utf-8")


class TestApprovalGateRefuses:
    def test_no_record_refuses_and_leaves_tree_untouched(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        proc = run_executor(project, config)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "APPROVAL GATE" in proc.stdout + proc.stderr
        assert target_text(project) == ORIGINAL
        # A refusal must be distinguishable from "operations failed": same exit
        # code, so the RESULT-JSON reason is the whole contract.
        verdict = result_json(proc.stdout)
        assert verdict["status"] == "failed", verdict
        assert str(verdict.get("reason", "")).startswith("approval-gate:"), verdict
        assert verdict["operations"] == [], verdict

    def test_drifted_ops_json_refuses(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, 95, "APPROVED")
        payload = _ops_payload()
        payload["operations"][0]["edits"][0]["replace"] = "VALUE = 1234"
        _write_ops(config, payload)

        proc = run_executor(project, config)
        assert proc.returncode != 0
        assert "DRIFT" in proc.stdout + proc.stderr
        assert target_text(project) == ORIGINAL

    @pytest.mark.parametrize("score,decision", [(95, "CONDITIONAL"), (95, "REJECTED"),
                                                (95, "REVISE"), (50, "APPROVED")])
    def test_non_authorising_verdict_refuses(self, project, score, decision):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, score, decision)

        proc = run_executor(project, config)
        assert proc.returncode != 0
        assert target_text(project) == ORIGINAL

    def test_config_outside_plans_dir_with_sibling_plan_md_is_gated(self, project):
        """Writing the config outside plans/ must not shed the gate while the plan
        document it implements still exists."""
        (project / ".claude" / "plans" / "plan-demo.md").write_text("# plan\n",
                                                                   encoding="utf-8")
        config = project / "elsewhere.json"
        _write_ops(config, _ops_payload(plan="demo"))
        proc = run_executor(project, config)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert result_json(proc.stdout)["reason"].startswith("approval-gate:")
        assert target_text(project) == ORIGINAL

    def test_gate_all_env_gates_every_config(self, project):
        """ECC_OPS_GATE_ALL=1 is the fail-closed-everywhere switch: no plans dir,
        no record, no plan.md, still refused."""
        config = project / "ops.json"
        _write_ops(config, _ops_payload(plan="ad-hoc-fixup"))
        proc = run_executor(project, config, ECC_OPS_GATE_ALL="1")
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert result_json(proc.stdout)["reason"].startswith("approval-gate:")
        assert target_text(project) == ORIGINAL

    def test_renamed_config_with_live_record_still_gated(self, project):
        """Moving the file out of plans/ must not detach it from its verdict:
        the config's own "plan" field still resolves the record."""
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, 95, "APPROVED")

        moved = project / "elsewhere.json"
        payload = _ops_payload()
        payload["operations"][0]["edits"][0]["replace"] = "VALUE = 1234"
        _write_ops(moved, payload)

        proc = run_executor(project, moved)
        assert proc.returncode != 0
        assert target_text(project) == ORIGINAL


class TestApprovalGateAllows:
    def test_approved_and_unchanged_executes(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, 95, "APPROVED")

        proc = run_executor(project, config)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert target_text(project) == PATCHED
        assert "RESULT-JSON:" in proc.stdout

    def test_dry_run_needs_no_record(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        proc = run_executor(project, config, "--dry-run")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert target_text(project) == ORIGINAL

    def test_no_approval_escape_hatch_executes_and_is_loud(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        proc = run_executor(project, config, "--no-approval")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert target_text(project) == PATCHED
        assert "BYPASSED" in proc.stdout + proc.stderr

    def test_config_outside_plans_dir_without_record_is_not_gated(self, project):
        """Ad-hoc configs (tooling, worktrees, tests) keep working: the gate binds
        pipeline artifacts and anything with a live record, not every ops.json."""
        config = project / "ops.json"
        _write_ops(config, _ops_payload(plan="ad-hoc-fixup"))
        proc = run_executor(project, config)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert target_text(project) == PATCHED


class TestRefusalCauseIsSpecific:
    """'No record at all' and 'a verdict exists but does not authorise this file' are
    different failures with different remedies (run /review vs re-run /review on the
    delta). review-record.py already separates them -- exit 3 vs 2 vs 4, with distinct
    stderr -- but execute-json-ops.py collapsed all three into the single machine-readable
    reason "approval-gate: review-record check exit N". A consumer parsing RESULT-JSON
    saw one undifferentiated failure. Collapsing the mapping back to one string flips
    test_refusal_causes_are_distinguishable.
    """

    SENTINEL = " [review-record exit"

    def _reason(self, proc):
        return str(result_json(proc.stdout).get("reason", ""))

    def _cause(self, proc):
        """The cause phrase alone, with the exit code / slug / why suffix stripped.

        Comparing whole reasons pins nothing: the exit code is IN the string, so three
        reasons stay distinct even if every cause phrase collapses to one constant --
        and the pre-fix message ("review-record check exit N (slug ...; why)") is three
        distinct strings too, with an IDENTICAL `why` ("config lives in a plans/
        directory") measured across all three cases. Asserting the sentinel is present
        is what makes this test fail against the unfixed executor rather than pass on it.
        """
        reason = self._reason(proc)
        assert self.SENTINEL in reason, f"cause/detail format missing: {reason}"
        return reason.split(self.SENTINEL)[0]

    def test_missing_record_names_the_missing_record(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        proc = run_executor(project, config)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "no review record" in self._reason(proc).lower()
        assert target_text(project) == ORIGINAL

    def test_drift_names_drift_not_absence(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, 95, "APPROVED")
        payload = _ops_payload()
        payload["operations"][0]["edits"][0]["replace"] = "VALUE = 1234"
        _write_ops(config, payload)
        proc = run_executor(project, config)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        reason = self._reason(proc).lower()
        assert "changed after it was reviewed" in reason
        assert "no review record" not in reason
        assert target_text(project) == ORIGINAL

    def test_unauthorised_verdict_names_the_verdict(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, 40, "REJECTED")
        proc = run_executor(project, config)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        reason = self._reason(proc).lower()
        assert "does not authorise execution" in reason
        assert "no review record" not in reason
        # The exit-2 phrase also contains "does not authorise execution", so that
        # substring alone does not discriminate code 4 from code 2. Pin the difference.
        assert "drift" not in reason
        assert target_text(project) == ORIGINAL

    def test_refusal_causes_are_distinguishable(self, project, tmp_path):
        """The paired assertion: the three CAUSE phrases must all differ.

        Flips to len == 1 under the collapse mutant (one constant `cause`), and flips
        via _cause's format assertion against the unfixed executor. Verified against
        all three worlds before this test was written.
        """
        reasons = set()

        cfg_a = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(cfg_a, _ops_payload())
        reasons.add(self._cause(run_executor(project, cfg_a)))

        record(project, "demo", cfg_a, 95, "APPROVED")
        drifted = _ops_payload()
        drifted["operations"][0]["edits"][0]["replace"] = "VALUE = 4321"
        _write_ops(cfg_a, drifted)
        reasons.add(self._cause(run_executor(project, cfg_a)))

        record(project, "demo", cfg_a, 40, "REJECTED")
        reasons.add(self._cause(run_executor(project, cfg_a)))

        assert len(reasons) == 3, reasons


class TestApprovalThresholdBoundary:
    """E2E-09: the threshold boundary was correct but unpinned by any test.

    Measured on the current tree: APPROVED 88 -> check exit 4, 89 -> 4, 90 -> 0, 91 -> 0.
    Moving APPROVAL_THRESHOLD to 89 flips test_score_below_threshold_refuses; relaxing
    `<` to `<=` flips test_score_at_threshold_executes (under `<=`, 89 still refuses).
    """

    def test_score_below_threshold_refuses(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, 89, "APPROVED")
        proc = run_executor(project, config)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert result_json(proc.stdout)["status"] == "failed"
        assert target_text(project) == ORIGINAL

    def test_score_at_threshold_executes(self, project):
        config = project / ".claude" / "plans" / "plan-demo.ops.json"
        _write_ops(config, _ops_payload())
        record(project, "demo", config, 90, "APPROVED")
        proc = run_executor(project, config)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert target_text(project) == PATCHED


class TestOperationsDirectoryLayout:
    """Configs stored as operations/<slug>/ops.json, a layout some downstream CLAUDE.md
    files mandate. Keyed by filename, every such config shared the record 'ops'."""

    @staticmethod
    def _dir_config(project: Path, slug: str) -> Path:
        (project / ".claude" / "plans" / f"plan-{slug}.md").write_text(
            "# plan\n", encoding="utf-8")
        config = project / "operations" / slug / "ops.json"
        _write_ops(config, _ops_payload(plan=slug))
        return config

    def test_approved_directory_config_executes(self, project):
        config = self._dir_config(project, "lens")
        record(project, "lens", config, 95, "APPROVED")
        proc = run_executor(project, config)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert target_text(project) == PATCHED

    def test_drifted_directory_config_refuses(self, project):
        config = self._dir_config(project, "lens")
        record(project, "lens", config, 95, "APPROVED")
        payload = _ops_payload(plan="lens")
        payload["operations"][0]["edits"][0]["replace"] = "VALUE = 1234"
        _write_ops(config, payload)
        proc = run_executor(project, config)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "DRIFT" in proc.stdout + proc.stderr
        assert target_text(project) == ORIGINAL

    def test_a_sibling_plans_record_is_not_this_configs_record(self, project):
        """Before the fix plan beta resolved plan alpha's record (both keyed 'ops') and
        was refused as DRIFT against alpha's hash, not as unreviewed."""
        record(project, "alpha", self._dir_config(project, "alpha"), 95, "APPROVED")
        unreviewed = self._dir_config(project, "beta")
        proc = run_executor(project, unreviewed)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        reason = result_json(proc.stdout)["reason"]
        assert "no review record exists" in reason, reason
        assert "slug 'beta'" in reason, reason
        assert target_text(project) == ORIGINAL

    def test_approving_a_prefixed_sibling_leaves_this_approval_valid(self, project):
        """operations/alpha and operations/ops-alpha are two configs. Under a prefix strip
        the second approval overwrote the first and alpha was refused as DRIFT."""
        alpha = self._dir_config(project, "alpha")
        record(project, "alpha", alpha, 95, "APPROVED")
        sibling = self._dir_config(project, "ops-alpha")
        record(project, "ops-alpha", sibling, 95, "APPROVED")
        proc = run_executor(project, alpha)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert target_text(project) == PATCHED

    def test_a_plan_field_naming_an_approved_sibling_does_not_authorise(self, project):
        """The executor also tries the config's stripped "plan" field. A sibling declaring
        "plan": "alpha" reaches alpha's record, and the sha256 binding refuses it."""
        record(project, "alpha", self._dir_config(project, "alpha"), 95, "APPROVED")
        sibling = project / "operations" / "ops-alpha" / "ops.json"
        payload = _ops_payload(plan="alpha")
        payload["operations"][0]["edits"][0]["replace"] = "VALUE = 7"
        _write_ops(sibling, payload)
        proc = run_executor(project, sibling)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "DRIFT" in result_json(proc.stdout)["reason"]
        assert target_text(project) == ORIGINAL

    def test_recorder_and_executor_derive_the_same_key(self, tmp_path, monkeypatch):
        """The two sides must agree for every form; this pins it on the real modules."""
        import importlib.util

        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, str(path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        monkeypatch.syspath_prepend(str(EXECUTOR.parent))  # executor imports `shared`
        recorder = load("_rr_key_parity", RECORDER)
        executor = load("_ex_key_parity", EXECUTOR)
        cases = {
            ".claude/plans/plan-x.ops.json": "x", ".claude/plans/ops-x.json": "x",
            ".claude/plans/x.ops.json": "x", ".claude/plans/x.json": "x",
            # a directory name is VERBATIM: stripping it collapsed distinct configs
            "operations/x/ops.json": "x", "operations/ops-x/ops.json": "ops-x",
            "operations/plan-x/ops.json": "plan-x", "operations/ops-/ops.json": "ops-",
            "operations/plan-/ops.json": "plan-", "operations/.x/ops.json": ".x",
        }
        for rel, expected in cases.items():
            path = tmp_path / rel
            assert recorder.ops_slug(path) == expected, rel
            assert executor._approval_slugs(str(path), "")[0] == expected, rel
        nested = tmp_path / "operations" / "y"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        assert recorder.ops_slug("ops.json") == "y"
        assert executor._approval_slugs("ops.json", "")[0] == "y"

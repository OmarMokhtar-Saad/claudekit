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

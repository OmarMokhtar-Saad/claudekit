"""Offline tests for the eval harness (task 010). The evals themselves cost
API money and run via `ck eval` / scripts/run-evals.py — pytest only covers
the framework: definition validity, workspace building, and check logic."""
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
RUNNER = os.path.join(ROOT, "scripts", "run-evals.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_evals", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_all_definitions_load_and_reference_real_assets():
    mod = _load_runner()
    defs = mod.load_definitions()
    assert len(defs) >= 4
    ids = {d["id"] for d in defs}
    # The four pipeline-stage evals derived from the 2026-07-08 E2E run.
    for expected in ("planner-delivers-artifacts", "reviewer-refutes-and-formats",
                     "implementer-no-fabrication", "verifier-ground-truth"):
        assert expected in ids


def test_dry_run_builds_all_workspaces():
    r = subprocess.run([sys.executable, RUNNER, "--dry-run"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "No agents were run" in r.stdout
    assert "FAIL" not in r.stdout


def test_workspace_isolates_fixture_with_kit_assets(tmp_path):
    mod = _load_runner()
    d = next(x for x in mod.load_definitions()
             if x["id"] == "implementer-no-fabrication")
    ws = mod.build_workspace(d)
    try:
        assert os.path.isfile(os.path.join(ws, "src", "calc", "basic.py"))
        assert os.path.isfile(os.path.join(ws, ".claude", "agents", "implementer.md"))
        assert os.path.isfile(os.path.join(
            ws, ".claude", "operations", "scripts", "execute-json-ops.py"))
        # setup_files landed and parse
        ops = os.path.join(ws, ".claude", "plans", "ops-negate.json")
        assert json.load(open(ops))["plan"] == "add-negate"
        # no hooks/settings — evals judge prompts, not hooks
        assert not os.path.exists(os.path.join(ws, ".claude", "settings.json"))
    finally:
        import shutil
        shutil.rmtree(ws, ignore_errors=True)


def test_check_engine_logic(tmp_path):
    mod = _load_runner()
    definition = {"checks": [
        {"type": "regex_present", "pattern": "SCORE: \\d+", "why": "score"},
        {"type": "regex_absent", "pattern": "fabricated", "why": "honesty"},
        {"type": "workspace_file_contains", "path": "x.py",
         "pattern": "def negate", "why": "applied"},
    ]}
    (tmp_path / "x.py").write_text("def negate(a):\n    return -a\n")
    ok = mod.apply_checks(definition, "SCORE: 93 all good", str(tmp_path))
    assert ok == []
    bad = mod.apply_checks(definition, "fabricated numbers, no score", str(tmp_path))
    assert len(bad) == 2  # missing score + fabricated present


def test_cli_eval_subcommand_lists():
    cli = os.path.join(ROOT, "src", "claudekit", "cli", "main.py")
    r = subprocess.run([sys.executable, cli, "eval", "--list"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "planner-delivers-artifacts" in r.stdout

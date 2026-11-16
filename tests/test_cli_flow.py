"""Behavioral tests for ``ck flow``: a fake ``claude`` on PATH plays every agent role, the
real operations scripts run against a throwaway project, and the assertions are on the
artifacts the chain must leave behind (plan, review, review record, usage table).
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = str(ROOT / "src" / "claudekit" / "cli" / "main.py")

FAKE_CLAUDE = '''#!{python}
import json, os, sys
prompt = sys.stdin.read()
role = sys.argv[sys.argv.index("--agent") + 1]
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as f:
    f.write("=== " + role + " " + " ".join(sys.argv[1:]) + "\\n" + prompt + "\\n")
if role == "planner":
    result = ("# Plan: greet\\n\\nTier: 3\\n\\nFiles: `src/hello.txt`\\n\\n"
              "## Steps\\n\\n1. Change the greeting.\\n")
    turns, cost = 3, 0.12
else:
    result = ("Looks fine.\\n\\nSCORE: " + os.environ.get("FAKE_SCORE", "95") + "\\nDECISION: "
              + os.environ.get("FAKE_DECISION", "APPROVED") + "\\n")
    turns, cost = 2, 0.03
json.dump({{"type": "result", "subtype": "success", "is_error": False, "num_turns": turns,
           "total_cost_usd": cost, "result": result,
           "usage": {{"input_tokens": 100 * turns, "cache_creation_input_tokens": 1000,
                     "cache_read_input_tokens": 20000 * turns, "output_tokens": 500}}}}, sys.stdout)
'''


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ck-flow-"))
        self.project = self.tmp / "project"
        (self.project / ".claude" / "plans").mkdir(parents=True)
        (self.project / "src").mkdir()
        (self.project / "src" / "hello.txt").write_text("hello\n")
        shutil.copytree(ROOT / ".claude" / "operations" / "scripts",
                        self.project / ".claude" / "operations" / "scripts")
        subprocess.run(["git", "init", "-q"], cwd=str(self.project), check=True)
        bindir = self.tmp / "bin"
        bindir.mkdir()
        self.fake = bindir / "claude"
        self.fake.write_text(FAKE_CLAUDE.format(python=sys.executable))
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)
        self.log = self.tmp / "claude.log"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_flow(self, *extra, **env_extra):
        env = dict(os.environ, ECC_HOOK_PROFILE="minimal", FAKE_CLAUDE_LOG=str(self.log))
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, CLI_PATH, "flow", "greet", "--slug", "greet",
             "--python", sys.executable, "--claude", str(self.fake)] + list(extra),
            capture_output=True, text=True, cwd=str(self.project), env=env, timeout=300)

    def test_chain_stops_at_an_approved_recorded_plan(self):
        proc = self.run_flow()
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        plans = self.project / ".claude" / "plans"
        self.assertTrue((plans / "plan-greet.md").exists(), out)
        self.assertIn("DECISION: APPROVED", (plans / "plan-greet.review.md").read_text())
        self.assertTrue(list((self.project / ".claude" / "reports" / "reviews").glob("*")), out)
        # the flow never edits: the main session does that after approval
        self.assertEqual((self.project / "src" / "hello.txt").read_text(), "hello\n")
        self.assertRegex(out, r"planner\s+3\s+\S+\s+61,300\s+\$0\.12")
        self.assertRegex(out, r"reviewer\s+2\s+")
        self.assertNotIn("implementer", out)
        self.assertNotIn("verifier", out)
        log = self.log.read_text()
        self.assertNotIn("=== verifier", log)
        self.assertIn("--agent reviewer --model sonnet --allowedTools Read,Grep,Glob "
                      "--output-format json", log)
        self.assertIn("--agent planner --model opus --allowedTools Read,Grep,Glob,Write", log)
        # advisory critic panel: path-only prompt, merged, exit code unchanged
        for critic in ("plan-design-critic", "plan-readiness-critic"):
            self.assertIn(f"--agent {critic} --model sonnet --allowedTools Read,Grep ", log)
            self.assertTrue((plans / f"plan-greet.panel-{critic}.md").exists(), out)
        self.assertRegex(log, r"\nPlan: /\S+/plan-greet\.md\. Review it\.\n")
        self.assertIn("=== PANEL ===", out)

    def test_panel_off_runs_no_critic(self):
        proc = self.run_flow(CK_REVIEW_PANEL="off")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("critic", self.log.read_text())
        self.assertNotIn("=== PANEL ===", proc.stdout)

    def test_python_default_names_its_source(self):
        env = dict(os.environ, ECC_HOOK_PROFILE="minimal", FAKE_CLAUDE_LOG=str(self.log))

        def flow(slug):
            return subprocess.run(
                [sys.executable, CLI_PATH, "flow", "greet", "--slug", slug,
                 "--claude", str(self.fake)],
                capture_output=True, text=True, cwd=str(self.project), env=env,
                timeout=300).stdout

        self.assertIn("(no .venv found; the interpreter running ck)", flow("greet"))
        project = self.project.resolve()  # git reports /private/var, not /var
        venv_python = project / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.symlink_to(sys.executable)
        self.assertIn(f"python {venv_python} ({project}/.venv)", flow("greet2"))

    def test_rejecting_reviewer_is_exit_2_and_leaves_the_tree_alone(self):
        proc = self.run_flow(FAKE_SCORE="40", FAKE_DECISION="REJECTED")
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2, out)
        self.assertEqual((self.project / "src" / "hello.txt").read_text(), "hello\n")
        self.assertIn("did not approve", out)
        self.assertRegex(out, r"reviewer\s+2\s+")

    def test_model_override_and_bad_role(self):
        proc = self.run_flow("--model", "reviewer=haiku")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("--agent reviewer --model haiku", self.log.read_text())
        for role in ("cook", "implementer"):
            proc = self.run_flow("--model", f"{role}=haiku")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("ROLE=MODEL", proc.stderr)


class UsageMathTest(unittest.TestCase):
    def test_usage_of_sums_rebilled_and_tolerates_missing_fields(self):
        sys.path.insert(0, str(ROOT / "src"))
        from claudekit.cli import flow
        u = flow.usage_of({"num_turns": 4, "total_cost_usd": 1.5,
                           "usage": {"input_tokens": 10, "cache_read_input_tokens": 90,
                                     "cache_creation_input_tokens": 100}})
        self.assertEqual(u, {"turns": 4, "rebilled": 200, "avg_ctx": 50, "cost": 1.5})
        self.assertEqual(flow.usage_of({})["avg_ctx"], 0)
        self.assertEqual(flow.parse_result_json('noise\n{"num_turns": 2}\n')["num_turns"], 2)
        self.assertEqual(flow.parse_result_json("garbage"), {})


if __name__ == "__main__":
    unittest.main()

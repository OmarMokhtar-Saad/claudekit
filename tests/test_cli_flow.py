"""Behavioral tests for ``ck flow``: a fake ``claude`` on PATH plays every agent role, the
real operations scripts run against a throwaway project, and the assertions are on the
artifacts the chain must leave behind (plan, ops, review record, edited file, usage table).
"""

import json
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
    ops = {{"plan": "plan-greet", "operations": [{{"type": "code_edit", "path": "src/hello.txt",
           "edits": [{{"find": "hello\\n", "replace": "hello, flow\\n"}}]}}]}}
    result = ("# Plan: greet\\n\\n## Validation commands\\n\\n```bash\\n{python} --version\\n```\\n\\n"
              "## Operations\\n\\n```json\\n" + json.dumps(ops, indent=2) + "\\n```\\n")
    plan = os.environ.get("FAKE_PLAN")
    if plan == "create":
        ops = {{"plan": "plan-greet", "operations": [{{"type": "file_create",
               "path": "src/new.txt", "content": "new\\n"}}]}}
        checks = ("{python} .claude/operations/scripts/validate-config-json.py "
                  ".claude/plans/plan-greet.ops.json\\ntest -f src/new.txt && echo shell-ok\\n"
                  "{python} -c print(4242)")
    elif plan == "missing":
        checks = "ck-flow-no-such-binary --version"
    else:
        checks = None
    if checks is not None:
        result = ("# Plan: greet\\n\\n## Validation commands\\n\\n```bash\\n" + checks
                  + "\\n```\\n\\n## Operations\\n\\n```json\\n" + json.dumps(ops, indent=2)
                  + "\\n```\\n")
    turns, cost = 3, 0.12
elif role == "reviewer":
    result = ("Looks fine.\\n\\nSCORE: " + os.environ.get("FAKE_SCORE", "95") + "\\nDECISION: "
              + os.environ.get("FAKE_DECISION", "APPROVED") + "\\n")
    turns, cost = 2, 0.03
else:
    result = "VERIFIED from the captured output: PASS 90/100\\n"
    turns, cost = 1, 0.01
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
        env.pop("ECC_OPS_GATE_ALL", None)
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, CLI_PATH, "flow", "greet", "--slug", "greet",
             "--python", sys.executable, "--claude", str(self.fake)] + list(extra),
            capture_output=True, text=True, cwd=str(self.project), env=env, timeout=300)

    def test_full_chain_leaves_every_artifact_and_a_usage_table(self):
        proc = self.run_flow()
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        plans = self.project / ".claude" / "plans"
        self.assertTrue((plans / "plan-greet.md").exists(), out)
        ops = json.loads((plans / "plan-greet.ops.json").read_text())
        self.assertEqual(ops["operations"][0]["path"], "src/hello.txt")
        self.assertIn("DECISION: APPROVED", (plans / "plan-greet.review.md").read_text())
        self.assertIn("PASS", (plans / "plan-greet.verify.md").read_text())
        self.assertTrue(list((self.project / ".claude" / "reports" / "reviews").glob("*")), out)
        # the gate was ON (no --no-approval) and the record authorised the edit
        self.assertEqual((self.project / "src" / "hello.txt").read_text(), "hello, flow\n")
        # per-phase usage from --output-format json: 3 planner turns, 20k cache-read each
        self.assertRegex(out, r"planner\s+3\s+\S+\s+61,300\s+\$0\.12")
        self.assertRegex(out, r"implementer\s+-\s+-\s+-\s+-\s+0")
        self.assertRegex(out, r"total\s+6\s+")
        log = self.log.read_text()
        # the verifier got the implementer's captured output (executor + the plan's checks)
        verifier_prompt = log.split("=== verifier")[1]
        self.assertIn("--version", verifier_prompt)
        self.assertIn("RESULT-JSON", verifier_prompt)
        self.assertIn("Python 3", verifier_prompt)
        # scoped tools per role
        self.assertIn("--agent reviewer --model sonnet --allowedTools Read,Grep,Glob "
                      "--output-format json", log)
        self.assertIn("--agent planner --model opus --allowedTools Read,Grep,Glob,Write", log)

    def test_file_create_plan_validates_its_config_before_executing(self):
        proc = self.run_flow(FAKE_PLAN="create")
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual((self.project / "src" / "new.txt").read_text(), "new\n")
        self.assertNotIn("already exists", out)
        verifier_prompt = self.log.read_text().split("=== verifier")[1]
        # the config check ran first, the executor next, the plain check after it
        self.assertLess(verifier_prompt.index("validate-config-json.py"),
                        verifier_prompt.index("RESULT-JSON"))
        self.assertLess(verifier_prompt.index("RESULT-JSON"),
                        verifier_prompt.index("4242\n(exit 0)"))
        # the shell line is not run, and says so as its own row
        self.assertIn("echo shell-ok\n(skipped: needs a shell)", verifier_prompt)
        self.assertRegex(out, r"check: test -f src/new.txt.*skipped: needs shell")

    def test_missing_validation_binary_is_exit_127_not_a_traceback(self):
        proc = self.run_flow(FAKE_PLAN="missing")
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("implementer exited 127", out)

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

    def test_rejecting_reviewer_stops_before_the_implementer(self):
        proc = self.run_flow(FAKE_SCORE="40", FAKE_DECISION="REJECTED")
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2, out)
        self.assertEqual((self.project / "src" / "hello.txt").read_text(), "hello\n")
        self.assertIn("did not authorise", out)
        self.assertNotIn("=== verifier", self.log.read_text())
        self.assertRegex(out, r"reviewer\s+2\s+")

    def test_model_override_and_bad_role(self):
        proc = self.run_flow("--model", "reviewer=haiku")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("--agent reviewer --model haiku", self.log.read_text())
        proc = self.run_flow("--model", "cook=haiku")
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

"""Keyless behavioural tests for the eval replay engine (wave-2 phase 2.1).

The point of the engine is that an eval suite can run in CI without an API key
and without paying per run. These tests therefore exercise the real replay path
end to end -- write a cassette, serve it, apply the suite's own checks -- and
never call a model. Nothing here mocks the code under test.

The property that matters most is INVALIDATION, not caching. A cassette that
outlives the prompt it recorded answers a question nobody asked, and a green CI
run off a superseded recording is worse than no CI run at all. Most of the file
is therefore about staleness.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(ROOT, "scripts", "run-evals.py")


def load_runner():
    spec = importlib.util.spec_from_file_location("run_evals", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RE = load_runner()

# A response shaped like a real `claude -p --output-format json` payload, whose
# text satisfies the planner eval's checks.
def good_planner_payload(definition):
    return {
        "result": (
            "## Plan: add a subtract function\n\n"
            "### Problem\nThe calculator has no subtraction.\n\n"
            "### Operations\n\n```json\n"
            + json.dumps({"plan": "add-subtract", "operations": [
                {"type": "code_edit", "path": "src/calc/basic.py",
                 "edits": [{"find": "def add(a: float, b: float) -> float:",
                            "replace": "def add(a: float, b: float) -> float:"}]}]},
                indent=2)
            + "\n```\n\n### Rollback\n`git revert` the commit.\n"),
        "total_cost_usd": 0.11,
    }


class CassetteDir:
    """Redirect the engine at a temp cassette directory for the duration."""

    def __init__(self, testcase):
        self.dir = tempfile.mkdtemp(prefix="ck-cassettes-")
        self.previous = RE.CASSETTES_DIR
        RE.CASSETTES_DIR = self.dir
        testcase.addCleanup(self.restore)

    def restore(self):
        RE.CASSETTES_DIR = self.previous
        shutil.rmtree(self.dir, ignore_errors=True)


def definition(eval_id):
    for d in RE.load_definitions():
        if d["id"] == eval_id:
            return d
    raise AssertionError(f"no eval definition {eval_id!r}")


class DefinitionsNameTiersNotModels(unittest.TestCase):
    def test_every_definition_declares_a_tier(self):
        for d in RE.load_definitions():
            self.assertIn(d["tier"], ("most-capable", "balanced", "fast"))

    def test_a_definition_naming_a_vendor_model_is_rejected(self):
        """The regression: eval definitions were a vendor-name surface the
        model-policy audit did not cover, and two of them ran agents on models
        those agents do not ship on."""
        d = dict(definition("planner-delivers-artifacts"))
        d["model"] = "opus"
        tmp = tempfile.mkdtemp(prefix="ck-defs-")
        self.addCleanup(shutil.rmtree, tmp, True)
        previous = RE.DEFS_DIR
        RE.DEFS_DIR = tmp
        self.addCleanup(setattr, RE, "DEFS_DIR", previous)
        with open(os.path.join(tmp, "bad.json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        with self.assertRaises(ValueError) as ctx:
            RE.load_definitions()
        self.assertIn("never a vendor", str(ctx.exception))

    def test_tier_resolves_through_the_model_policy_table(self):
        d = definition("planner-delivers-artifacts")
        with open(os.path.join(ROOT, ".claude", "model-policy.json"), encoding="utf-8") as fh:
            policy = json.load(fh)
        self.assertEqual(RE.resolve_model(d),
                         policy["capability_tiers"][d["tier"]]["model"])

    def test_each_definition_exercises_the_agent_as_shipped(self):
        """An eval that runs an agent on a model the agent does not use is not
        testing the shipped system."""
        with open(os.path.join(ROOT, ".claude", "model-policy.json"), encoding="utf-8") as fh:
            policy = json.load(fh)
        for d in RE.load_definitions():
            self.assertEqual(d["tier"], policy["roles"][d["agent"]]["tier"],
                             "%s runs %s off its own tier" % (d["id"], d["agent"]))


class ReplayServesWhatWasRecorded(unittest.TestCase):
    def setUp(self):
        CassetteDir(self)
        self.definition = definition("planner-delivers-artifacts")

    def test_round_trip_replays_without_calling_a_model(self):
        payload = good_planner_payload(self.definition)
        RE.write_cassette(self.definition, payload)
        served, err = RE.load_cassette(self.definition)
        self.assertIsNone(err)
        self.assertEqual(served, payload)

    def test_a_replayed_response_still_goes_through_the_real_checks(self):
        RE.write_cassette(self.definition, good_planner_payload(self.definition))
        served, err = RE.load_cassette(self.definition)
        self.assertIsNone(err)
        workspace = RE.build_workspace(self.definition)
        self.addCleanup(shutil.rmtree, workspace, True)
        failures = RE.apply_checks(self.definition, served["result"], workspace)
        self.assertEqual(failures, [], "a good recorded response must pass the checks")

    def test_a_missing_cassette_is_an_error_not_a_pass(self):
        served, err = RE.load_cassette(self.definition)
        self.assertIsNone(served)
        self.assertIn("no cassette", err)
        self.assertIn("--record", err)

    def test_an_unreadable_cassette_is_an_error_not_a_pass(self):
        RE.write_cassette(self.definition, good_planner_payload(self.definition))
        with open(RE.cassette_path(self.definition), "w", encoding="utf-8") as fh:
            fh.write("{ truncated")
        served, err = RE.load_cassette(self.definition)
        self.assertIsNone(served)
        self.assertIn("unreadable", err)


class StaleCassettesFailClosed(unittest.TestCase):
    """The property the whole design exists for.

    Each test edits one input the model actually sees, then asserts replay
    refuses AND names what moved. A cassette that survives a corpus edit would
    let CI go green against a prompt that no longer exists.
    """

    def setUp(self):
        CassetteDir(self)
        self.definition = definition("planner-delivers-artifacts")
        RE.write_cassette(self.definition, good_planner_payload(self.definition))
        _served, err = RE.load_cassette(self.definition)
        self.assertIsNone(err, "cassette must be fresh before the mutation")

    def assert_stale(self, needle):
        served, err = RE.load_cassette(self.definition)
        self.assertIsNone(served)
        self.assertIn("STALE", err)
        self.assertIn(needle, err)
        self.assertIn("--record", err, "a refusal must say how to fix itself")

    def _edit(self, path, suffix="\n<!-- eval staleness probe -->\n"):
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        self.addCleanup(lambda: open(path, "w", encoding="utf-8").write(original))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(original + suffix)

    def test_editing_the_agent_prompt_invalidates_it(self):
        self._edit(os.path.join(ROOT, ".claude", "agents",
                                self.definition["agent"] + ".md"))
        self.assert_stale("agent_prompt")

    def test_editing_a_skill_the_agent_loads_invalidates_it(self):
        surface = RE.prompt_surface(self.definition)
        skill = sorted(surface["skills"])[0]
        self._edit(os.path.join(ROOT, ".claude", "skills", skill, "SKILL.md"))
        self.assert_stale("skills(%s)" % skill)

    def test_changing_the_prompt_invalidates_it(self):
        self.definition["prompt"] += "\n\nAlso rename the module."
        self.assert_stale("prompt")

    def test_changing_the_tool_grant_invalidates_it(self):
        self.definition["allowed_tools"] += ",Bash"
        self.assert_stale("allowed_tools")

    def test_changing_setup_files_invalidates_it(self):
        self.definition.setdefault("setup_files", {})["NOTES.md"] = "hello"
        self.assert_stale("setup_files")

    def test_editing_an_operations_script_the_agent_can_run_invalidates_it(self):
        """The gap the first review round found.

        `planner-delivers-artifacts` grants
        `Bash(python3 .claude/operations/scripts/validate-config-json.py *)` and
        tells the agent to self-validate, so that script's output is read by the
        model before it answers. Excluding it from the fingerprint left a live
        false-PASS path: change the validator, and replay keeps serving a
        recording made against the old behaviour.
        """
        self._edit(os.path.join(ROOT, ".claude", "operations", "scripts",
                                "validate-config-json.py"),
                   suffix="\n# eval staleness probe\n")
        self.assert_stale("operations_scripts")

    def test_retargeting_the_tier_invalidates_it(self):
        self.definition["tier"] = "fast"
        self.assert_stale("model")

    def test_changing_something_the_model_never_sees_does_NOT_invalidate_it(self):
        """Re-recording costs real money, so the fingerprint must not be
        hair-triggered: budgets and check definitions are ours, not the
        model's, and may change freely."""
        self.definition["max_cost_usd"] = 99.0
        self.definition["description"] = "rewritten description"
        self.definition["checks"] = []
        _served, err = RE.load_cassette(self.definition)
        self.assertIsNone(err, "a cassette must survive edits the model cannot see")


class InjectedFaultsAreRejected(unittest.TestCase):
    """Mutation testing for the eval suite itself.

    If an eval's checks pass against a deliberately broken model response, the
    checks are decorative. Cheap to state, and it has teeth: a suite of
    `regex_absent` checks alone would sail through every one of these.
    """

    @classmethod
    def setUpClass(cls):
        cls.definition = definition("planner-delivers-artifacts")
        cls.workspace = RE.build_workspace(cls.definition)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workspace, ignore_errors=True)

    def _failures_for(self, fault):
        payload, err = RE.inject_fault(fault, self.definition)
        if err:
            return ["agent run failed: " + err]
        return RE.apply_checks(self.definition, payload.get("result") or "",
                               self.workspace)

    def test_timeout_is_reported_as_a_failure(self):
        self.assertTrue(self._failures_for("timeout"))

    def test_truncation_is_rejected(self):
        self.assertTrue(self._failures_for("truncation"),
                        "output that merely STARTS correctly must not pass")

    def test_malformed_tool_call_is_rejected(self):
        self.assertTrue(self._failures_for("malformed_tool_call"))

    def test_refusal_is_rejected(self):
        self.assertTrue(self._failures_for("refusal"))

    def test_an_unknown_fault_is_refused_rather_than_ignored(self):
        with self.assertRaises(ValueError):
            RE.inject_fault("gremlins", self.definition)


class InjectModeExitCodeIsInverted(unittest.TestCase):
    """`--inject` is green only when every eval REJECTED the broken response."""

    def _run(self, *args, cassettes=None):
        env = dict(os.environ)
        if cassettes:
            env["CK_EVAL_CASSETTES"] = cassettes
        return subprocess.run([sys.executable, RUNNER, *args], env=env,
                              capture_output=True, text=True, cwd=ROOT, timeout=300)

    def test_refusal_injection_reports_every_eval_rejecting_it(self):
        result = self._run("--inject", "refusal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rejected the injected refusal", result.stdout)
        self.assertNotIn("PASSED DESPITE FAULT", result.stdout)

    def test_zero_matching_definitions_is_an_error_not_a_pass(self):
        """`0/0 passed` is not a pass.

        With an empty definition set the result loop never runs, so the failure
        count is zero and the old aggregation returned success -- a green run
        that verified nothing.
        """
        empty = tempfile.mkdtemp(prefix="ck-empty-defs-")
        self.addCleanup(shutil.rmtree, empty, True)
        env = dict(os.environ, CK_EVAL_DEFS=empty)
        result = subprocess.run([sys.executable, RUNNER, "--replay"], env=env,
                                capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("vacuous", result.stderr)

    def test_an_unknown_fault_name_is_a_usage_error(self):
        result = self._run("--inject", "gremlins")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown fault", result.stderr)

    def test_replay_and_record_are_mutually_exclusive(self):
        result = self._run("--replay", "--record")
        self.assertEqual(result.returncode, 2)
        self.assertIn("mutually exclusive", result.stderr)

    def test_replay_with_no_cassettes_fails_rather_than_passing_vacuously(self):
        """An empty cassette store must not read as "nothing broken"."""
        empty = tempfile.mkdtemp(prefix="ck-empty-cassettes-")
        self.addCleanup(shutil.rmtree, empty, True)
        result = self._run("--replay", "--only", "planner-delivers-artifacts",
                           cassettes=empty)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no cassette", result.stdout)


if __name__ == "__main__":
    unittest.main()

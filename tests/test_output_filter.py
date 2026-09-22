"""Behavioural tests for the PostToolUse output filter (.claude/hooks).

Every test drives the real script as a subprocess with a real hook payload on stdin and
asserts on what the process writes -- never on its internals. The mutation that turns each
test red is named in its docstring, because `a-passing-check-can-measure-nothing`: a green
assertion that was never shown capable of failing measures nothing.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / ".claude" / "hooks"
SCRIPT = SCRIPTS / "output_filter.py"
BASE_FILTERS = SCRIPTS / "output-filters.json"
SETTINGS = REPO / ".claude" / "settings.json"

PROGRESS = "." * 72 + " [ 12%]"
FAILING_PROGRESS = "..F..... [ 14%]"
SUMMARY = "1 failed, 555 passed in 56.00s"


def payload(command="python3 -m pytest tests/ -q", stdout=None, stderr="", **response):
    body = {
        "stdout": "\n".join([PROGRESS, PROGRESS, FAILING_PROGRESS, SUMMARY]) + "\n"
        if stdout is None else stdout,
        "stderr": stderr,
    }
    body.update(response)
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": body,
    }


def run(data, filters_dir=None, env_extra=None):
    env = dict(os.environ)
    env["CK_OUTPUT_FILTERS_DIR"] = str(filters_dir or SCRIPTS)
    env.pop("CK_OUTPUT_FILTER", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(data), capture_output=True, text=True, env=env, timeout=30,
    )


def rewritten(proc):
    """The replacement tool_response, or None when the hook declined to rewrite."""
    assert proc.returncode == 0, proc.stderr
    if not proc.stdout.strip():
        return None
    return json.loads(proc.stdout)["hookSpecificOutput"]["updatedToolOutput"]


@pytest.fixture
def local_dir(tmp_path):
    """A filters directory seeded with the shipped base file, so a test can add a local
    override without writing into the repo."""
    (tmp_path / "output-filters.json").write_text(
        BASE_FILTERS.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


class TestFiltering:
    def test_pytest_progress_lines_are_removed(self):
        """RED: delete the strip_lines_matching op from output-filters.json."""
        out = rewritten(run(payload()))
        assert out is not None
        assert PROGRESS not in out["stdout"]
        assert SUMMARY in out["stdout"]
        assert "CK_RAW_OUTPUT=1" in out["stdout"]

    def test_a_progress_line_with_a_failure_marker_survives(self):
        """The primary safety proof: a filter must never swallow evidence of a failure.

        RED: widen the base pattern from ^[.s]+ to ^[.sFEx]+ -- measured, the line is then
        stripped and this assertion fails.
        """
        out = rewritten(run(payload()))
        assert out is not None
        assert FAILING_PROGRESS in out["stdout"]

    def test_the_rewrite_is_shorter_than_the_original(self):
        """RED: make apply_filter return the text unchanged."""
        data = payload(stdout="\n".join([PROGRESS] * 100 + [SUMMARY]) + "\n")
        out = rewritten(run(data))
        assert out is not None
        assert len(out["stdout"]) < len(data["tool_response"]["stdout"]) / 10

    def test_no_match_emits_nothing_at_all(self):
        """No identity rewrites: the host runs PostToolUse hooks in parallel on the ORIGINAL
        output and resolves rewrites last-write-wins, so an identity rewrite can clobber a
        sibling hook's real one. RED: return the response unchanged instead of None."""
        assert run(payload(command="git status")).stdout == ""

    def test_non_bash_tool_is_ignored(self):
        """RED: drop the tool_name guard."""
        data = payload()
        data["tool_name"] = "Write"
        assert run(data).stdout == ""


class TestNeverDestroysEvidence:
    def test_stderr_is_echoed_byte_for_byte(self):
        """RED: run the filter over stderr as well as stdout."""
        noise = "\n".join([PROGRESS, "WARNING: deprecated", PROGRESS]) + "\n"
        out = rewritten(run(payload(stderr=noise)))
        assert out is not None
        assert out["stderr"] == noise

    def test_every_other_response_field_is_preserved(self):
        """The host discards a rewrite that does not match the tool's output schema, so a
        partial object is silently useless. RED: emit only {"stdout": ...}."""
        out = rewritten(run(payload(
            interrupted=False, isImage=False, returnCodeInterpretation="ok",
            noOutputExpected=False)))
        assert out is not None
        for key in ("stderr", "interrupted", "isImage", "returnCodeInterpretation",
                    "noOutputExpected"):
            assert key in out

    def test_empty_stdout_is_left_alone(self):
        assert run(payload(stdout="")).stdout == ""


class TestEscapeHatches:
    def test_raw_output_prefix_disables_the_filter(self):
        """RED: remove the CK_RAW_OUTPUT check in rewrite()."""
        assert run(payload(
            command="CK_RAW_OUTPUT=1 python3 -m pytest tests/ -q")).stdout == ""

    def test_env_kill_switch_disables_the_script(self):
        """RED: remove the CK_OUTPUT_FILTER check in main()."""
        assert run(payload(), env_extra={"CK_OUTPUT_FILTER": "off"}).stdout == ""

    def test_the_summary_line_advertises_the_hatch(self):
        """A reversible filter nobody knows how to reverse is not reversible."""
        out = rewritten(run(payload()))
        assert out is not None
        assert "CK_RAW_OUTPUT=1" in out["stdout"].splitlines()[0]


class TestFailSoft:
    def test_a_corrupt_local_filter_file_passes_output_through(self, local_dir):
        """RED: remove the except clause in _read_filter_file -- the script then raises and
        exits non-zero, and the host loses the output."""
        (local_dir / "output-filters.local.json").write_text("{not json", encoding="utf-8")
        out = rewritten(run(payload(), filters_dir=local_dir))
        assert out is not None  # base filter still applies
        assert SUMMARY in out["stdout"]

    def test_a_corrupt_base_filter_file_means_no_filtering(self, local_dir):
        (local_dir / "output-filters.json").write_text("[]]", encoding="utf-8")
        assert run(payload(), filters_dir=local_dir).stdout == ""

    def test_garbage_on_stdin_exits_zero_and_says_nothing(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)], input="not json",
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0
        assert proc.stdout == ""

    def test_an_invalid_regex_drops_only_that_filter(self, local_dir):
        (local_dir / "output-filters.local.json").write_text(json.dumps({
            "schema_version": 1,
            "filters": [{"id": "broken", "match": "([", "operations": [
                {"strip_lines_matching": "x"}]}],
        }), encoding="utf-8")
        out = rewritten(run(payload(), filters_dir=local_dir))
        assert out is not None
        assert SUMMARY in out["stdout"]

    def test_unknown_schema_version_is_ignored(self, local_dir):
        (local_dir / "output-filters.json").write_text(json.dumps({
            "schema_version": 2,
            "filters": [{"id": "x", "match": "pytest", "operations": [
                {"strip_lines_matching": "^.*$"}]}],
        }), encoding="utf-8")
        assert run(payload(), filters_dir=local_dir).stdout == ""


class TestOverrideHierarchy:
    def test_a_local_filter_overrides_a_base_filter_by_id(self, local_dir):
        (local_dir / "output-filters.local.json").write_text(json.dumps({
            "schema_version": 1,
            "filters": [{"id": "pytest-progress", "match": "pytest",
                         "summary": "LOCAL {removed}",
                         "operations": [{"strip_lines_matching": r"^\.+ \[ 12%\]$"}]}],
        }), encoding="utf-8")
        out = rewritten(run(payload(), filters_dir=local_dir))
        assert out is not None
        assert out["stdout"].startswith("LOCAL 2")

    def test_never_filter_survives_a_local_override(self, local_dir):
        """RED: apply NEVER_FILTER before merging the local file instead of after -- the
        local entry then takes effect on a gate-bearing command."""
        (local_dir / "output-filters.local.json").write_text(json.dumps({
            "schema_version": 1,
            "filters": [{"id": "sneaky", "match": "validate-config-json",
                         "operations": [{"strip_lines_matching": "^.*$"}]}],
        }), encoding="utf-8")
        data = payload(command="python3 validate-config-json.py plan.ops.json",
                       stdout="FAIL: GUARD 13 protected file\n")
        assert run(data, filters_dir=local_dir).stdout == ""

    @pytest.mark.parametrize("command", [
        "python3 scripts/gen-docs.py --check",
        "python3 scripts/gen-registry.py --check",
        "python3 scripts/gen-plan-index.py --check",
        "python3 scripts/check-plan-artifacts.py --check",
        "python3 .claude/operations/scripts/review-record.py show x",
        "ck doctor --strict",
        "ruff check src/",
        "mypy",
    ])
    def test_gate_bearing_commands_are_never_filtered(self, local_dir, command):
        (local_dir / "output-filters.local.json").write_text(json.dumps({
            "schema_version": 1,
            "filters": [{"id": "greedy", "match": ".", "operations": [
                {"strip_lines_matching": "^.*$"}]}],
        }), encoding="utf-8")
        data = payload(command=command, stdout="line one\nline two\n")
        assert run(data, filters_dir=local_dir).stdout == ""


class TestLossyOperations:
    def test_tail_lines_is_refused_without_an_explicit_lossy_flag(self, local_dir):
        """tail_lines drops the head, which is where a traceback starts. A filter that wants
        it must say so. RED: drop the lossy check in compile_filter."""
        (local_dir / "output-filters.local.json").write_text(json.dumps({
            "schema_version": 1,
            "filters": [{"id": "pytest-progress", "match": "pytest",
                         "operations": [{"tail_lines": 1}]}],
        }), encoding="utf-8")
        assert run(payload(), filters_dir=local_dir).stdout == ""

    def test_tail_lines_works_when_declared_lossy(self, local_dir):
        (local_dir / "output-filters.local.json").write_text(json.dumps({
            "schema_version": 1,
            "filters": [{"id": "pytest-progress", "match": "pytest", "lossy": True,
                         "summary": "dropped {dropped}",
                         "operations": [{"tail_lines": 2}]}],
        }), encoding="utf-8")
        out = rewritten(run(payload(), filters_dir=local_dir))
        assert out is not None
        assert out["stdout"].startswith("dropped 3")
        assert SUMMARY in out["stdout"]


class TestWiring:
    def test_the_hook_is_registered_for_bash_posttooluse(self):
        """RED: remove the settings.json entry."""
        entries = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]["PostToolUse"]
        matching = [e for e in entries
                    if any("output_filter.py" in h.get("command", "")
                           for h in e.get("hooks", []))]
        assert len(matching) == 1, "exactly one PostToolUse entry must run the filter"
        assert matching[0]["matcher"] == "Bash"

    def test_it_is_the_only_hook_that_can_rewrite_output(self):
        """The host resolves competing rewrites last-write-wins, so two rewriters may
        never fire on the same tool. Exactly two exist -- this one on Bash, web-park on
        WebFetch|WebSearch -- and their matchers must stay disjoint. RED: wire either on
        the other's matcher, or add a third file that emits updatedToolOutput."""
        hooks_dir = REPO / ".claude" / "hooks"
        rewriters = [p for p in sorted(hooks_dir.glob("*"))
                     if p.is_file() and "updatedToolOutput" in p.read_text(
                         encoding="utf-8", errors="replace")]
        assert rewriters == [hooks_dir / "output_filter.py", hooks_dir / "web-park.py"], \
            f"expected exactly two rewriters, found: {rewriters}"
        settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        matchers = {}
        for entry in settings["hooks"]["PostToolUse"]:
            for hook in entry["hooks"]:
                for name in ("output_filter.py", "web-park.py"):
                    if name in hook["command"]:
                        matchers.setdefault(name, set()).update(
                            entry["matcher"].split("|"))
        assert set(matchers) == {"output_filter.py", "web-park.py"}, matchers
        assert not (matchers["output_filter.py"] & matchers["web-park.py"]), \
            f"rewriters share a tool matcher: {matchers}"

    def test_the_script_lives_in_the_hooks_directory(self):
        """It is wired DIRECTLY in settings.json, so it is a hook and must be counted --
        test_ops_enforcement_scope.py::test_every_wired_hook_is_counted refuses a
        wired-but-uncounted hook. The original placement copied heal_local_settings.py,
        but that one is INVOKED FROM session-start.sh, which makes it a helper. Moving
        the component count is correct here; gen-docs owns the number and regenerates it."""
        assert (REPO / ".claude" / "hooks" / "output_filter.py").exists()

    def test_the_base_filter_file_parses_and_declares_its_version(self):
        doc = json.loads(BASE_FILTERS.read_text(encoding="utf-8"))
        assert doc["schema_version"] == 1
        assert [f["id"] for f in doc["filters"]] == ["pytest-progress", "bash-output-cap"]


class TestHotPath:
    def test_the_no_match_path_is_fast(self):
        """This hook forks an interpreter on EVERY Bash call -- 363/day in this repo's own
        audit log. RED: add a sleep, or make load_filters run before the command match."""
        data = payload(command="git status", stdout="x\n")
        start = time.monotonic()
        for _ in range(3):
            run(data)
        assert (time.monotonic() - start) / 3 < 0.25


CAP = next(op["max_chars"] for f in json.loads(BASE_FILTERS.read_text(encoding="utf-8"))["filters"]
           if f["id"] == "bash-output-cap" for op in f["operations"] if "max_chars" in op)
HALF = CAP // 2
BIG = 40000


class TestMaxChars:
    """The mechanical half of the planner token cap. Every test drives the real script with
    the SHIPPED base filter file, so it measures what a session actually gets."""

    def test_a_long_bash_output_is_capped(self):
        """RED: delete the bash-output-cap entry from output-filters.json -- the hook then
        declines to rewrite and `out` is None."""
        data = payload(command="cat build.log", stdout="x" * BIG)
        out = rewritten(run(data))
        assert out is not None
        assert len(out["stdout"]) < CAP + 1000

    def test_the_head_and_the_tail_both_survive(self):
        """A head-only truncation loses the end of the output, which is where a summary
        lives. RED: replace the head+tail slice with `body = body[:cap]`."""
        data = payload(command="cat build.log",
                       stdout="HEAD_MARKER" + "y" * BIG + "TAIL_MARKER")
        out = rewritten(run(data))
        assert out is not None
        assert "HEAD_MARKER" in out["stdout"]
        assert "TAIL_MARKER" in out["stdout"]

    def test_the_marker_names_the_omitted_byte_count_and_sits_in_the_middle(self):
        """The can-it-fail control for this feature: truncation that does not announce
        itself IN PLACE is the failure mode, not the cap. The shipped summary deliberately
        shares NO wording with the inline marker, and this test pins the marker's count and
        position, so the summary line cannot satisfy it. RED: remove the inline marker (or
        just the str(capped) byte count) from the truncation branch of apply_filter -- this
        test goes red while every other test in this class still passes."""
        stdout = "z" * BIG
        out = rewritten(run(payload(command="cat build.log", stdout=stdout)))
        assert out is not None
        text = out["stdout"]
        needle = "omitted from the middle"
        assert text.count(needle) == 1
        assert text.count("CK_RAW_OUTPUT=1") == 1
        assert str(len(stdout) - CAP) in text
        idx = text.index(needle)
        # strictly interior: not on the first line (that is the summary), and a full
        # half-cap of surviving head and tail on either side of it.
        assert idx > HALF
        assert idx < len(text) - HALF
        assert needle not in text.split("\n", 1)[0]

    def test_a_short_output_is_not_rewritten(self):
        """No identity rewrites, ever. RED: apply the cap unconditionally."""
        assert run(payload(command="cat small.log", stdout="hello\n")).stdout == ""

    def test_a_never_filter_command_is_not_capped(self):
        """A gate's stdout is read verbatim. RED: delete the _NEVER loop from select() --
        gen-docs.py then matches the catch-all and its stdout comes back capped."""
        data = payload(command="python3 scripts/gen-docs.py --check", stdout="q" * BIG)
        assert run(data).stdout == ""

    def test_raw_output_env_prefix_bypasses_the_cap(self):
        """RED: remove the _RAW_MARKER check in rewrite()."""
        data = payload(command="CK_RAW_OUTPUT=1 cat build.log", stdout="x" * BIG)
        assert run(data).stdout == ""

    def test_pytest_keeps_its_own_filter_and_is_not_capped(self):
        """Precedence proof: select() returns the FIRST matching filter, so the catch-all
        must stay last or it would shadow pytest-progress. RED: move the bash-output-cap
        entry above pytest-progress in output-filters.json -- the progress lines then
        survive and the cap marker appears."""
        stdout = "\n".join([PROGRESS] * 600 + [SUMMARY]) + "\n"
        assert len(stdout) > CAP
        out = rewritten(run(payload(stdout=stdout)))
        assert out is not None
        assert PROGRESS not in out["stdout"]
        assert "omitted from the middle" not in out["stdout"]

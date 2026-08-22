"""The bash oracle must fire on a validator that lets a blocklisted command through.

This is the gate for `validator-executor-divergence` - the class every fail-open in the
2026-08-21 batch belonged to, and the one the differential gate structurally cannot see,
because it compares the validator against itself at another commit. Here the second opinion is
bash. These tests point the oracle at a mutant that allows everything and assert it reports the
markers; a gate that has only ever reported clean is not evidence.
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-validator-vs-bash.py"
MODULE = REPO_ROOT / "src" / "claudekit" / "security" / "command_validator.py"

# One shell process per ALLOWED payload, so this is far slower than the differential gate.
FAST = 2

pytestmark = pytest.mark.skipif(shutil.which("bash") is None,
                                reason="the oracle needs a real bash to be an oracle")


def _load():
    spec = importlib.util.spec_from_file_location("check_validator_vs_bash", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_validator_vs_bash"] = module
    spec.loader.exec_module(module)
    return module


oracle = _load()


class TestTheOracleBinds:
    def test_a_validator_with_no_blocklist_is_caught_by_bash(self, tmp_path):
        """The mutant allows what the blocklist exists to stop; bash reaches `rm` and `sudo`
        and the oracle must say so, naming the payload."""
        source = MODULE.read_text()
        start = source.index("BLOCKLIST = {")
        end = source.index("}", start) + 1
        holed = tmp_path / "no_blocklist.py"
        holed.write_text(source[:start] + "BLOCKLIST = set()" + source[end:])

        report = oracle.run(FAST, REPO_ROOT, 5.0, module_path=holed)
        assert report["status"] == "fail", report
        reached = {name for item in report["findings"] for name in item["reached"]}
        assert "rm" in reached, report["findings"][:3]

    def test_the_shipped_validator_allows_nothing_bash_can_use(self):
        """The state this repo intends to be in. If this fails, a real bypass exists."""
        report = oracle.run(FAST, REPO_ROOT, 5.0)
        assert report["status"] == "pass", report["findings"][:5]

    def test_probes_come_from_the_shipped_module_not_the_one_under_test(self, tmp_path):
        """A mutant that empties BLOCKLIST must not also shrink the corpus meant to catch it."""
        source = MODULE.read_text()
        start = source.index("BLOCKLIST = {")
        end = source.index("}", start) + 1
        holed = tmp_path / "no_blocklist.py"
        holed.write_text(source[:start] + "BLOCKLIST = set()" + source[end:])
        shipped_report = oracle.run(FAST, REPO_ROOT, 5.0)
        mutant_report = oracle.run(FAST, REPO_ROOT, 5.0, module_path=holed)
        assert mutant_report["payloads"] == shipped_report["payloads"]


    def test_a_validator_that_always_raises_is_not_a_clean_run(self, tmp_path):
        """Review found this reported findings=0, unverified=0, status=pass - identical to a
        thorough clean run, from a gate that asked bash nothing. Exceptions are counted now,
        and executed==0 is a FAIL in the report itself, not only in the CLI."""
        source = MODULE.read_text()
        holed = tmp_path / "always_raises.py"
        holed.write_text(source.replace(
            "    def validate(self, command: str)",
            '    def validate(self, command: str):\n        raise RuntimeError("boom")\n\n'
            "    def _unused(self, command: str)", 1))

        report = oracle.run(FAST, REPO_ROOT, 5.0, module_path=holed)
        assert report["status"] == "fail", report
        assert report["executed"] == 0
        assert report["errored"] > 0

    def test_a_starved_run_is_not_a_clean_run(self, monkeypatch):
        """Liveness is part of the verdict. A refusal rule that grows over-broad would keep
        reporting `pass` on a run that verified almost nothing - the same fake-green shape as
        an empty corpus, which is why `unverified > executed` fails."""
        monkeypatch.setattr(oracle, "refused", lambda payload: payload != "echo hi")
        report = oracle.run(FAST, REPO_ROOT, 5.0)
        assert report["status"] == "fail", report
        assert report["unverified"] > report["executed"]

    def test_a_clean_run_actually_executed_something(self):
        """`pass` must mean bash ran payloads, not that everything was refused."""
        report = oracle.run(FAST, REPO_ROOT, 5.0)
        assert report["executed"] > 0, report


class TestContainment:
    def test_an_absolute_redirect_target_is_refused(self):
        """THE containment finding. Empty PATH and shadow functions contain external COMMANDS;
        redirection is bash's own parser. `echo x > /etc/hosts` is in this very corpus as a
        dangerous-pattern probe, so the moment a validator under test allowed it - which is the
        scenario the oracle exists for - it would have written to the real path, as root on a CI
        runner. Refused before bash sees it, at the cost of not observing redirect divergence."""
        for payload in ("echo x > /etc/hosts", "cat x > /dev/sda", "echo x >| /usr/bin/ls",
                        "echo x > ~/.bashrc", "cat < /etc/shadow",
                        # Round 2: the first refusal was a denylist on `>` followed by `/`,
                        # and every one of these reaches an absolute path around it.
                        'echo x > "/etc/hosts"', "exec 3>/etc/x", "cat <<EOF > /etc/x",
                        "echo x >> /etc/x", "echo x > $HOME/../../etc/x",
                        "echo x > ${x}/etc/x", "echo x >\t/etc/x"):
            assert oracle.refused(payload), payload

    def test_a_relative_redirect_still_runs(self):
        """The refusal is about escaping the sandbox, not about redirects - and the oracle must
        keep its teeth on the payload shapes that actually mattered."""
        assert not oracle.refused("echo hi > out.txt")
        assert not oracle.refused("echo hi >> log.txt")
        assert not oracle.refused("ls\nrm -rf /")

    def test_the_redirect_target_rule_is_an_allowlist(self):
        """Polarity, pinned: a denylist of dangerous targets is what round 1 shipped and round 2
        broke with quotes and expansions. Only a plain relative name may be a target."""
        assert oracle._SAFE_TARGET.match("out.txt")
        for target in ("/etc/x", "~/x", "$HOME/x", "${x}/y", '"/etc/x"', "../x"):
            assert not oracle._SAFE_TARGET.match(target), target

    def test_the_dangerous_pattern_probes_are_all_refused_or_rejected(self):
        """Every absolute-path probe in the shared corpus must be unreachable by execution -
        either refused here, or rejected by the validator so it is never offered to bash."""
        differential_spec = importlib.util.spec_from_file_location(
            "cvd", REPO_ROOT / "scripts" / "check-validator-differential.py")
        differential = importlib.util.module_from_spec(differential_spec)
        differential_spec.loader.exec_module(differential)
        for probe in differential.PATTERN_PROBES:
            if ">" in probe and "/" in probe.split(">")[-1]:
                assert oracle.refused(probe), probe

    def test_the_caller_process_limit_is_never_touched(self):
        """`ulimit -u` in the probe would apply to the whole USER on macOS, not the child: an
        early draft set it and broke the harness's own shell before it broke any payload."""
        assert "ulimit -u" not in oracle._probe_script()

    def test_changing_directory_is_refused(self):
        """Review round 4, and the finding that ended the regex-patching. `cd /etc && echo x >
        passwd` has a target of `passwd` - safe in isolation. The escape is the reference frame,
        not the string, and `cd` is a builtin so an empty PATH does not touch it."""
        for payload in ("cd /etc && echo x > passwd", "CDPATH=/ cd etc && echo x > passwd",
                        "pushd /etc", "popd", "exec 3>/etc/x", ". /etc/x", "source /etc/x"):
            assert oracle.refused(payload), payload

    def test_the_teeth_survive_the_refusals(self):
        """Five rounds of refusals must not have refused the thing the oracle is for. Each of
        these is a real bypass this release closed, and bash reaches `rm` in every one."""
        for payload in ("ls\nrm -rf /", "``rm -rf /", "2>err.log rm -rf /",
                        "echo # don\\'t\nrm -rf /"):
            assert not oracle.refused(payload), payload

    def test_an_absolute_redirect_costs_coverage_and_that_is_recorded(self):
        """`2>/dev/null rm -rf /` - the exact shape of the fd-prefix bypass - IS refused,
        because /dev/null is an absolute target. The oracle sees that class only through a
        relative-target variant. Asserted so the cost is visible rather than assumed away."""
        assert oracle.refused("2>/dev/null rm -rf /")
        assert not oracle.refused("2>err.log rm -rf /")

    def test_fork_bomb_shapes_are_refused_before_execution(self):
        for payload in (":(){ :|:& };:", "x & ", "while true; do x; done", "((i=0;i<9;i++))"):
            assert oracle.refused(payload), payload

    def test_reassigning_path_is_refused(self):
        """Review round 5: the empty-PATH premise holds only at lookup time, and the payload is
        arbitrary bash. `PATH=/usr/bin python3 -c ...` restores every external binary on the
        machine - not the shadowed ten, which bash resolves as functions first, but everything
        else. Same class as `cd`: it changes what a command name means."""
        for payload in ("PATH=/usr/bin python3 -c 'x'", "export PATH=/usr/bin; id",
                        "PATH=$PATH:/bin ls"):
            assert oracle.refused(payload), payload

    def test_process_isolation_does_not_claim_a_filesystem_boundary(self):
        """An earlier version wrapped the child in `unshare --mount --map-root-user` and called
        it a jail. Review refuted it: an unshared mount table that nothing mounts into still
        resolves /etc to the same inode. The flags are PID-only now, and the docstring says so -
        a containment claim that does not hold is worse than none, because the CI decision
        rested on it."""
        assert "--mount" not in oracle.process_isolation()
        assert "--map-root-user" not in oracle.process_isolation()
        assert "filesystem boundary" in oracle.process_isolation.__doc__

    def test_a_refused_payload_is_counted_not_silently_passed(self, tmp_path):
        assert oracle.markers(":(){ :|:& };:", tmp_path, 5.0) is None

    def test_the_probe_empties_path_and_shadows_the_blocklisted_commands(self):
        script = oracle._probe_script()
        assert 'export PATH=""' in script
        for name in ("rm", "sudo", "chmod", "curl", "dd"):
            assert f'{name}() {{ echo "MARKER:{name}"; }}' in script

    def test_the_sandbox_is_removed(self):
        before = set(Path(tempfile.gettempdir()).glob("validator-oracle-*"))
        oracle.run(FAST, REPO_ROOT, 5.0)
        after = set(Path(tempfile.gettempdir()).glob("validator-oracle-*"))
        assert after == before


class TestTheScriptRuns:
    def test_the_cli_refuses_to_execute_without_opt_in(self):
        """It executes fuzzed shell. Running that by default on a developer machine, where
        containment is lexical, is not a decision this script gets to make."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--max-len", str(FAST)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0
        assert "SKIP" in result.stdout and "--allow-execution" in result.stdout

    def test_cli_exits_zero_on_the_shipped_validator(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--max-len", str(FAST), "--json",
             "--allow-execution"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert '"status": "pass"' in result.stdout

    def test_a_short_corpus_is_refused(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--max-len", "1", "--allow-execution"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 1
        assert "proves nothing" in result.stdout

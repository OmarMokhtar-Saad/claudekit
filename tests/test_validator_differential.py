"""The differential gate must FAIL on a holed validator, or it is decoration.

`scripts/check-validator-differential.py` exists because three consecutive review rounds each
found a fail-open in `command_validator.py` that reading the diff had missed, and because two
of those fail-opens were introduced by the fix for the previous one. A gate for that class is
worthless unless it has been shown to fire, so these tests build deliberately holed modules and
assert the gate reports them - the same discipline the validator's own matrix is held to.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-validator-differential.py"
MODULE = REPO_ROOT / "src" / "claudekit" / "security" / "command_validator.py"

# Corpus size for the tests. This was 2 (441 payloads) until the gate's own mutation test
# refuted the comment above it: the newline bypass needs THREE tokens to express
# (`ls ` + `\n` + `rm -rf /`), so a length-2 corpus reported the reintroduced bypass as PASS.
# The gate caught the defect in its own test harness on the first run, which is the argument
# for having it. 9,702 payloads, still under a second per comparison.
FAST = 3


def _load_script():
    spec = importlib.util.spec_from_file_location("check_validator_differential", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_validator_differential"] = module
    spec.loader.exec_module(module)
    return module


check = _load_script()


def _holed(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of the real validator with one substitution - a mutant, not a hand-written stub,
    so what the gate is measured against is the shipped parser."""
    source = MODULE.read_text()
    assert source.count(old) == 1, f"anchor {old!r} is not unique; update this test"
    holed = tmp_path / "holed_validator.py"
    holed.write_text(source.replace(old, new))
    return holed


class TestTheGateBinds:
    def test_a_removed_blocklist_entry_is_reported(self, tmp_path):
        """The simplest possible protection loss: `rm` stops being blocklisted."""
        holed = _holed(tmp_path, '"rm", ', "")
        report = check.compare(MODULE, holed, FAST)
        assert report["status"] == "fail", report
        assert report["regression_count"] > 0
        payloads = {item["payload"] for item in report["regressions"]}
        assert any("rm" in payload for payload in payloads), sorted(payloads)[:5]
        # Unsafe mode is where this module's bypasses were actually exploitable, and it is the
        # only mode a removed blocklist entry regresses in: safe mode still rejects `rm` as
        # unallowlisted. Asserting False is present keeps a refactor that stops sweeping
        # safe_mode=False from leaving this green.
        assert False in {item["safe_mode"] for item in report["regressions"]}

    def test_the_newline_bypass_is_reported_if_reintroduced(self, tmp_path):
        """The defect this module was built around: if the per-line split is removed, every
        `first\\nblocked` payload flips back to ALLOW and the gate must say so."""
        holed = _holed(
            tmp_path,
            "        for line in _split_unquoted_newlines(command):",
            "        for line in [command]:",
        )
        report = check.compare(MODULE, holed, FAST)
        assert report["status"] == "fail", report

    def test_an_identical_module_passes(self, tmp_path):
        """No change, no regressions - the gate must not cry wolf on a no-op diff."""
        same = tmp_path / "same.py"
        same.write_text(MODULE.read_text())
        report = check.compare(MODULE, same, FAST)
        assert report["status"] == "pass", report["regressions"][:3]
        assert report["regression_count"] == 0


class TestTheCorpusReachesTheProtections:
    """Review measured the combinatorial corpus reaching 3 of 27 blocklisted commands and 1 of
    17 dangerous patterns: replacing the whole blocklist with two entries, and emptying
    DANGEROUS_PATTERNS outright, were both reported as a clean PASS. Combinatorics over an
    alphabet do not produce `/etc/`, `dd`, or a fork bomb. The corpus is now seeded, and these
    tests are what stop the seed falling behind the module."""

    def _module(self):
        spec = importlib.util.spec_from_file_location("cv_for_probe_check", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_dangerous_pattern_has_a_probe(self):
        """Adding a DANGEROUS_PATTERNS entry without a probe means the gate cannot see it
        deleted again. Fails on the new pattern, by name."""
        module = self._module()
        validator = module.CommandValidator(safe_mode=False)
        reached = set()
        for probe in check.PATTERN_PROBES:
            ok, reason = validator.validate(probe)
            if not ok and reason.startswith("Dangerous pattern ("):
                reached.add(reason[len("Dangerous pattern ("):-1])
        labels = {label for _, label in module.DANGEROUS_PATTERNS}
        assert labels - reached == set(), sorted(labels - reached)

    def test_a_baseline_without_a_blocklist_is_refused_not_silently_narrowed(self):
        """Probing only the 17 pattern triggers because the attribute was renamed is the C1
        blind spot again. It must be loud."""
        class NoBlocklist:
            pass

        with pytest.raises(RuntimeError, match="no BLOCKLIST"):
            check.protection_probes(NoBlocklist())

    def test_every_blocklisted_command_is_probed(self):
        module = self._module()
        probes = set(check.protection_probes(module))
        missing = [command for command in module.BLOCKLIST if f"{command} x" not in probes]
        assert not missing, sorted(missing)

    def test_gutting_the_blocklist_is_reported(self, tmp_path):
        module = self._module()
        source = MODULE.read_text()
        start = source.index("BLOCKLIST = {")
        end = source.index("}", start) + 1
        holed = tmp_path / "gutted.py"
        holed.write_text(source[:start] + 'BLOCKLIST = {"rm", "sudo"}' + source[end:])
        report = check.compare(MODULE, holed, FAST)
        assert report["status"] == "fail", report
        assert len(module.BLOCKLIST) > 20  # the mutant deletes most of it

    def test_emptying_the_dangerous_patterns_is_reported(self, tmp_path):
        source = MODULE.read_text()
        start = source.index("DANGEROUS_PATTERNS = [")
        end = source.index("\n]", start) + 2
        holed = tmp_path / "nopatterns.py"
        holed.write_text(source[:start] + "DANGEROUS_PATTERNS = []" + source[end:])
        report = check.compare(MODULE, holed, FAST)
        assert report["status"] == "fail", report


class TestDisclosedWidenings:
    def test_an_entry_only_absorbs_its_own_baseline_reason(self):
        """`baseline_reason` is what stops a broad payload pattern from swallowing unrelated
        regressions: every entry must carry one."""
        for entry in check.DISCLOSED_WIDENINGS:
            assert entry.get("baseline_reason"), entry
            assert entry.get("why"), entry

    def test_no_entry_keys_on_the_shared_dangerous_pattern_prefix(self):
        """Review round 1 of this gate: keying the eval/exec entry on `Dangerous pattern (`
        absorbed EVERY dangerous-pattern category - IFS evasion, interpreter smuggling, fork
        bombs - for any payload containing the word `eval`, and the corpus contains `eval `.
        An entry must name the exact pattern label."""
        for entry in check.DISCLOSED_WIDENINGS:
            reason = entry["baseline_reason"]
            assert reason != "Dangerous pattern (", entry
            if reason.startswith("Dangerous pattern ("):
                assert reason.endswith(")"), entry

    def test_no_entry_absorbs_a_large_share_of_the_corpus(self):
        """A suppression wide enough to cover a tenth of the corpus is a hole waiting for a
        reason-string rename. Measured at the time of writing: the widest is ~13%."""
        import re as _re

        corpus = check.payloads(FAST)
        for entry in check.DISCLOSED_WIDENINGS:
            matcher = _re.compile(entry["payload"])
            share = sum(1 for payload in corpus if matcher.search(payload)) / len(corpus)
            assert share < 0.15, (entry["payload"], round(share, 3))

    def test_a_disclosed_widening_does_not_hide_a_different_defect(self, tmp_path):
        """The `#` entry is disclosed only for baseline `Empty command after parsing`. A hole
        in comment handling that produces a DIFFERENT baseline verdict must still be reported:
        here `rm` is un-blocklisted, so `#\\nrm -rf /` regresses with a baseline reason the
        entry does not cover."""
        holed = _holed(tmp_path, '"rm", ', "")
        report = check.compare(MODULE, holed, FAST)
        blocked = [item for item in report["regressions"]
                   if item["baseline_reason"].startswith("Blocked command")]
        assert blocked, report["regressions"][:5]


class TestBaselineResolution:
    def test_a_push_to_main_falls_back_to_the_parent(self, monkeypatch):
        """On a push, the checked-out commit is one origin/main ALREADY points at, so the merge
        base is HEAD. Review found the first version of this guard turned that into a permanent
        red build on every push to main - a false FAIL, which is how a gate gets deleted."""
        calls = {"rev-parse HEAD": "aaa", "merge-base origin/main HEAD": "aaa",
                 "rev-parse HEAD~1": "bbb"}

        def fake_git(_repo, *args):
            return calls.get(" ".join(args))

        monkeypatch.setattr(check, "_git", fake_git)
        ref, how = check.resolve_baseline("auto", REPO_ROOT)
        assert ref == "bbb", (ref, how)
        assert "push, not PR" in how

    def test_a_pull_request_uses_the_merge_base(self, monkeypatch):
        calls = {"rev-parse HEAD": "aaa", "merge-base origin/main HEAD": "ccc"}

        def fake_git(_repo, *args):
            return calls.get(" ".join(args))

        monkeypatch.setattr(check, "_git", fake_git)
        ref, how = check.resolve_baseline("auto", REPO_ROOT)
        assert (ref, how) == ("ccc", "merge-base with origin/main")

    def test_an_unloadable_baseline_skips_with_the_cause(self, monkeypatch):
        """A baseline that cannot be imported or constructed - a syntax error at that commit, a
        changed __init__ signature - is not a finding about the current tree. A raw traceback
        naming neither side reads as flakiness."""
        monkeypatch.setattr(check, "_baseline_source", lambda ref, root: "def broken(:\n")
        report = check.run("HEAD~1", FAST, REPO_ROOT)
        assert report["status"] == "skipped", report
        assert "not loadable" in report["reason"]


    def test_explicit_ref_is_passed_through(self):
        ref, how = check.resolve_baseline("HEAD", REPO_ROOT)
        assert (ref, how) == ("HEAD", "explicit")

    def test_auto_resolves_to_a_real_commit(self):
        ref, how = check.resolve_baseline("auto", REPO_ROOT)
        assert how != "explicit"
        resolved = subprocess.run(["git", "cat-file", "-t", ref],
                                  capture_output=True, text=True, cwd=REPO_ROOT)
        assert resolved.stdout.strip() == "commit", (ref, how, resolved.stderr)

    def test_a_baseline_that_is_head_is_flagged(self):
        """The false-PASS route review round 1 found: on a push to main, `origin/main` already
        points at the commit being tested, so the merge base IS HEAD and the gate would diff
        the tree against a copy of itself and pass forever. The label alone did not reveal it -
        `how` said "merge-base with origin/main" - so the check is on the resolved SHA."""
        report = check.run("HEAD", FAST, REPO_ROOT)
        assert report["baseline_is_head"] is True, report
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--baseline", "HEAD", "--max-len", str(FAST),
             "--require-baseline"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 1, result.stdout
        assert "compare the tree against a copy of itself" in result.stdout

    def test_a_short_corpus_is_refused(self):
        """`--max-len 1` is a corpus of single tokens; passing it proves nothing."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--max-len", "1"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 1, result.stdout
        assert "proves nothing" in result.stdout

    def test_a_missing_baseline_skips_rather_than_passes(self):
        """A baseline that does not exist must not be reported as a clean run."""
        report = check.run("0000000000000000000000000000000000000000", FAST, REPO_ROOT)
        assert report["status"] == "skipped", report


class TestVerdictIsFailClosed:
    def test_an_exploding_validator_counts_as_reject(self):
        """An exception is not an ALLOW. It will fail the suite on its own; it must not be
        laundered into a widening here."""
        class Boom:
            def validate(self, command):
                raise RuntimeError("boom")

        assert check.verdict(Boom(), "ls") is False


class TestTheScriptRuns:
    def test_cli_exits_zero_against_its_own_head(self):
        """End to end, as CI invokes it."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--baseline", "HEAD", "--max-len", str(FAST),
             "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert '"status"' in result.stdout


if __name__ == "__main__":
    pytest.main([__file__])

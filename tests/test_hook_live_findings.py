"""The live hook findings from `review/code-review.md`, fixed 2026-08-24.

Confirmed live by `plan-backlog-triage-pass.md`, fixed by `plan-hook-live-findings.md`.

The checkpoint tests EXTRACT the pruner out of the shipped hook and run it, rather
than restating its logic here -- a test that reimplements the code it checks proves
only that two copies agree. The extraction is asserted first, because the first
attempt at this pulled the WRONG `python3 -c` block out of the same file (a
three-line counter) and produced confident numbers about code that was never under
test.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"
AUTO_CHECKPOINT = HOOKS / "auto-checkpoint.sh"


def _pruner_source():
    """The pruner's Python body, taken from the shipped hook."""
    text = AUTO_CHECKPOINT.read_text(encoding="utf-8")
    body = text.split("prune_old_checkpoints()", 1)[1]
    m = re.search(r'python3 -c "\n(.*?)\n" "\$REGISTRY_FILE"', body, re.S)
    assert m, "could not find the pruner block in auto-checkpoint.sh"
    src = m.group(1)
    # Guard against extracting some OTHER python3 -c block: the pruner is the one
    # that reads max_cp and prints the refs it dropped.
    assert "max_cp" in src and "checkpoints" in src, src[:200]
    return src


class TestThePrunerIsExtractedNotReimplemented:
    def test_the_extracted_block_is_the_pruner(self):
        src = _pruner_source()
        assert "sys.argv[2]" in src, "the pruner takes MAX_CHECKPOINTS as argv[2]"
        assert "print(ref)" in src, "the pruner prints the stash refs it dropped"


class TestTheCheckpointCapHolds:
    """`<= max_cp` in the pruner disagreed with `-lt MAX_CHECKPOINTS` in the shell.

    At exactly count == max the shell decided to prune and the pruner decided not
    to, so the append took the registry to max + 1 and the next run pruned it back:
    an oscillation that exceeded the configured cap on every other checkpoint, each
    overshoot a retained git stash.
    """

    def _run_cycle(self, tmp_path, start, max_cp, rounds=5):
        """One full checkpoint cycle per round: shell guard, prune, append."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        registry = tmp_path / "checkpoints.json"
        registry.write_text(json.dumps({"checkpoints": [
            {"timestamp": f"t{i:02d}", "stash_ref": f"sha{i}"} for i in range(start)
        ]}), encoding="utf-8")
        src = _pruner_source()
        sizes = []
        for _ in range(rounds):
            data = json.loads(registry.read_text(encoding="utf-8"))
            # The shell guard, verbatim from auto-checkpoint.sh:
            #     [ "$count" -lt "$MAX_CHECKPOINTS" ] && return 0
            if len(data["checkpoints"]) >= max_cp:
                subprocess.run([sys.executable, "-c", src, str(registry), str(max_cp)],
                               capture_output=True, text=True, timeout=30)
            data = json.loads(registry.read_text(encoding="utf-8"))
            data["checkpoints"].append({"timestamp": "tZ", "stash_ref": "shaZ"})
            registry.write_text(json.dumps(data), encoding="utf-8")
            sizes.append(len(data["checkpoints"]))
        return sizes

    def test_the_registry_never_exceeds_the_configured_maximum(self, tmp_path):
        for start in (2, 3, 4, 5):
            sizes = self._run_cycle(tmp_path / f"s{start}", start, 3)
            assert max(sizes) <= 3, (
                f"starting at {start}, the registry reached {max(sizes)} with "
                f"MAX_CHECKPOINTS=3: {sizes}")

    def test_it_settles_at_the_maximum_rather_than_below_it(self, tmp_path):
        """A cap that prunes too eagerly loses checkpoints the user was promised."""
        sizes = self._run_cycle(tmp_path / "settle", 4, 3)
        assert sizes[-1] == 3, sizes

    def test_the_shell_guard_and_the_pruner_agree(self):
        """The defect was two guards, not one wrong number -- so pin both."""
        text = AUTO_CHECKPOINT.read_text(encoding="utf-8")
        assert '[ "$count" -lt "$MAX_CHECKPOINTS" ]' in text, (
            "shell guard changed; the pruner's `< max_cp` is paired with it")
        assert "if len(checkpoints) < max_cp:" in _pruner_source(), (
            "the pruner must skip only BELOW the cap, or the two guards disagree "
            "at count == max again")


class TestTheRegistryIsLocked:
    def test_a_mutex_wraps_both_read_modify_writes(self):
        text = AUTO_CHECKPOINT.read_text(encoding="utf-8")
        assert text.count("registry_lock") >= 3, "prune and append must both lock"
        assert text.count("registry_unlock") >= 3
        assert "mkdir \"$REGISTRY_LOCK\"" in text, (
            "mkdir is the portable atomic lock; flock is Linux-only")

    def test_contention_never_drops_a_checkpoint(self):
        """The deliberate difference from suggest-compact.sh, pinned.

        That hook SKIPS its work when the lock is held, because a lost counter
        increment costs nothing. A skipped checkpoint costs the user's uncommitted
        work, so this one proceeds with a WARN instead of returning early.
        """
        text = AUTO_CHECKPOINT.read_text(encoding="utf-8")
        lock_fn = text.split("registry_lock() {", 1)[1].split("\n}", 1)[0]
        assert "proceeding unlocked" in lock_fn, lock_fn
        assert "exit 0" not in lock_fn, (
            "the lock must never exit the hook -- that would drop the checkpoint "
            "it exists to protect")

    def test_the_stale_lock_is_recoverable(self):
        lock_fn = AUTO_CHECKPOINT.read_text(encoding="utf-8")
        assert "-mmin +1" in lock_fn, (
            "a lock left by a died process must expire; `find -mmin` is the "
            "portable check (date -r/stat differ across platforms)")


class TestNoDeadPackageManagerVariables:
    def test_pm_install_and_pm_run_are_gone(self):
        text = (HOOKS / "session-start.sh").read_text(encoding="utf-8")
        # Assignments and expansions, not the bare name: the comment recording WHY
        # they were removed names them, and a test that forbids that is a test that
        # forbids the explanation.
        for var in ("PM_INSTALL", "PM_RUN"):
            assert not re.search(rf'^\s*{var}=', text, re.M), (
                f"{var} is assigned again; it was assigned eight times and read "
                "never (SC2034)")
            assert f"${var}" not in text and f"${{{var}}}" not in text

    def test_package_manager_detection_still_works(self, tmp_path):
        """The variable removal must not touch what the summary actually prints."""
        (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        proc = subprocess.run(["bash", str(HOOKS / "session-start.sh")],
                              cwd=str(tmp_path), capture_output=True, text=True,
                              timeout=60, input="")
        assert "cargo" in proc.stdout, proc.stdout + proc.stderr


class TestFailureOutputIsNotTruncatedPastTheCause:
    """`tail -20` of a test summary is the summary, not the first error."""

    def _tail_sites(self, name):
        """Every `tail -N` of a captured run, tagged failure or success.

        Classified by the marker the hook prints immediately above it -- the same
        signal the hook uses -- because the number alone cannot tell a coverage
        SUMMARY (short on purpose) from a truncated failure.
        """
        lines = (HOOKS / name).read_text(encoding="utf-8").splitlines()
        sites = []
        for i, line in enumerate(lines):
            m = re.search(r'echo "\$output" \| tail -(\d+)', line)
            if not m:
                continue
            context = "\n".join(lines[max(0, i - 4):i])
            failing = "FAILED" in context or "ERROR" in context
            sites.append((i + 1, int(m.group(1)), failing))
        return sites

    def test_every_failure_path_shows_more_than_twenty_lines(self):
        checked = 0
        for name in ("post-implement.sh", "pre-push.sh"):
            for lineno, n, failing in self._tail_sites(name):
                if not failing:
                    continue
                checked += 1
                assert n >= 60, (
                    f"{name}:{lineno}: `tail -{n}` on a failure path truncates "
                    "past the root cause")
        assert checked >= 5, (
            f"only {checked} failure paths found; this property is what caught "
            "the sites the review never listed, so it must not silently match none")

    def test_success_summaries_are_left_short(self):
        """The fix must not turn every summary into a wall of output."""
        short = [(n, ln) for name in ("post-implement.sh", "pre-push.sh")
                 for ln, n, failing in self._tail_sites(name) if not failing]
        assert short, "the success branches still print a short tail"
        assert all(n <= 20 for n, _ in short), short

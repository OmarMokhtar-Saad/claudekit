#!/usr/bin/env python3
"""Differential fuzz gate for CommandValidator: no change may turn REJECT into ALLOW.

Why this exists. `command_validator.py` is the module where three consecutive review rounds
each found a fail-open, and where a *fix for a finding* twice opened a hole bigger than the
one it closed. Reading the diff did not catch any of them; executing payloads did, in
seconds. `.ai/REVIEW_GUIDE.md` records `validator-executor-divergence` and
`fix-introduces-larger-hole` as classes with nothing mechanical behind them. This is the
mechanical check.

What it does: builds the validator from a git baseline and from the working tree, runs the
same generated payload corpus through both in BOTH safeMode states, and fails if any payload
moved REJECT -> ALLOW. A widening is not forbidden - it must be DISCLOSED, by adding an entry
to DISCLOSED_WIDENINGS below, which is reviewed like any other code.

What the comparison window is: `auto` resolves to the merge base with main, so a long-unrebased
branch is compared against its own old fork point rather than against main's tip. That is
correct per-PR semantics - a regression that predates the fork point belonged to whichever PR
introduced it - but it means the window can be wider than a reader assumes, so the baseline SHA
and how it was chosen are always printed. Rebase to tighten it.

What it is not: a proof. It fuzzes an alphabet of shell metacharacters and two blocklisted
commands; it does not model bash. A clean run means "no payload in this corpus regressed",
never "the validator is sound".

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import importlib.util
import itertools
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MODULE_PATH = "src/claudekit/security/command_validator.py"

# Shell metacharacters plus a benign command, a blocklisted one, and a builtin. Short
# products of these reproduce every defect this module has actually shipped: the bare
# newline, the comment/quote disagreements, the fd prefix and the empty expansions.
ALPHABET = [
    "`", "$", "(", ")", "#", "'", '"', "\\", "\n", ";", "|", "&&", ">", "2>",
    "ls ", "rm -rf /", "sudo -s", "eval ", "x", " ", "echo ",
]

# Widenings that are ALLOWED, each with the reason it was accepted. An entry here is a
# decision on the record, not a suppression: adding one takes the same review as changing the
# validator, and each must also be disclosed in CHANGELOG.md. `baseline_reason` narrows an
# entry to the verdict the OLD validator gave, so a broad payload pattern cannot silently
# absorb an unrelated regression.
DISCLOSED_WIDENINGS: List[Dict[str, str]] = [
    {
        "payload": r"(?:^|\s)\d+[<>]",
        "baseline_reason": "Command not in allowlist: ",
        "why": "A file-descriptor digit adjacent to a redirect is no longer read as the base "
               "command, so `2> log echo hi` validates `echo` instead of failing as 'not in "
               "allowlist: 2'. The blocklist still sees the real command.",
    },
    {
        "payload": r"\beval\b",
        "baseline_reason": "Dangerous pattern (eval)",
        "why": "eval/exec are matched in command position per segment instead of as bare "
               "words anywhere, which is what rejected `bundle exec rspec`. Command-position "
               "eval/exec is still refused in both modes; only argument position widened. "
               "The baseline reason is the EXACT pattern label, not the shared "
               "'Dangerous pattern (' prefix: review found that prefix absorbed every other "
               "dangerous-pattern category - IFS evasion, interpreter smuggling, fork bombs - "
               "for any payload that merely contained the word `eval`.",
    },
    {
        "payload": r"\bexec\b",
        "baseline_reason": "Dangerous pattern (exec)",
        "why": "The `exec` half of the same disclosed change; same exact-label narrowing.",
    },
    {
        "payload": r"#\s*$",
        "baseline_reason": "Empty command after parsing",
        "why": "Same disclosed change, comment at the END of a line that has no command word "
               "of its own (`> echo #`): the old validator discarded the comment and saw an "
               "empty command, the new one tokenizes it. bash runs nothing here either - it "
               "creates the redirect target and executes no command.",
    },
    {
        "payload": r"(?m)^[\s;&|>\\]*#",
        "baseline_reason": "Empty command after parsing",
        "why": "shlex used to DISCARD `#` comments, so a comment-only line tokenized to "
               "nothing and was rejected as empty. Comment stripping is now disabled (it was "
               "a fail-open: see the splitter docstring), so the line has tokens. A line that "
               "is only a comment runs nothing in bash either, so ALLOW is what the shell "
               "does - there is no execution behind this one. Anchored to a comment that opens "
               "a line, optionally after separators: review found the bare `#` was one "
               "reason-string rename away from being the widest suppression in this file.",
    },
]


def _repo_root() -> Path:
    """The repo this script lives in - resolved via git so it works from any cwd, with the
    script's own location as the fallback for a tarball checkout with no .git."""
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parent)
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo_root: Path, *args: str) -> Optional[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=repo_root)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def resolve_baseline(ref: str, repo_root: Path) -> Tuple[str, str]:
    """`auto` picks the merge base with the default branch, falling back to HEAD~1.

    Returns (ref, how) so the output can say which one it used - a gate whose baseline is
    ambiguous is a gate nobody can act on.
    """
    if ref != "auto":
        return ref, "explicit"
    head = _git(repo_root, "rev-parse", "HEAD")
    for remote_main in ("origin/main", "main"):
        base = _git(repo_root, "merge-base", remote_main, "HEAD")
        if not base:
            continue
        if base == head:
            # A push to main checks out a commit origin/main ALREADY points at, so the merge
            # base is HEAD and comparing against it is comparing the tree with itself. The
            # right baseline there is the commit that was just merged onto.
            parent = _git(repo_root, "rev-parse", "HEAD~1")
            if parent:
                return parent, f"HEAD~1 ({remote_main} is at HEAD - push, not PR)"
            continue
        return base, f"merge-base with {remote_main}"
    parent = _git(repo_root, "rev-parse", "HEAD~1")
    if parent:
        return parent, "HEAD~1 (no main branch reachable)"
    return "HEAD", "HEAD (single-commit repository)"


def _is_head(ref: str, repo_root: Path) -> bool:
    """Does this baseline resolve to the commit we are testing?

    It is not enough to check the fallback label. On a push to main the workflow checks out a
    commit that origin/main ALREADY points at, so `merge-base(origin/main, HEAD)` is HEAD
    itself: a real-looking baseline that diffs the tree against itself and passes forever.
    """
    head = _git(repo_root, "rev-parse", "HEAD")
    resolved = _git(repo_root, "rev-parse", ref)
    return bool(head and resolved and head == resolved)


def _baseline_source(ref: str, repo_root: Path) -> Optional[str]:
    result = subprocess.run(["git", "show", f"{ref}:{MODULE_PATH}"],
                            capture_output=True, text=True, cwd=repo_root)
    if result.returncode != 0:
        return None
    return result.stdout


# One trigger per DANGEROUS_PATTERNS label. Combinatorics over ALPHABET reach exactly ONE of
# the seventeen, so without these a change deleting sixteen dangerous patterns passed the gate -
# measured in review, not hypothesised. `test_every_dangerous_pattern_has_a_probe` fails when a
# pattern is added here without one, so the corpus cannot silently fall behind the module.
PATTERN_PROBES = [
    "cat x > /dev/sda",
    "echo x > /etc/hosts",
    "echo x > /usr/bin/ls",
    "echo x > /sys/kernel/x",
    "echo x > /proc/self/mem",
    "IFS=$'\\n' ls",
    "cat${IFS}/etc/passwd",
    "find . -delete",
    "find . -exec rm {} ;",
    "python3 -c 'import os; os.system(\"x\")'",
    "python3 -c 'import subprocess; subprocess.run(\"x\")'",
    "python3 -c '__import__(\"os\")'",
    ":(){ :|:& };:",
    "git reset --hard",
    "git clean -f",
    "git checkout -- .",
    "git checkout .",
    "git stash drop",
]


def protection_probes(baseline) -> List[str]:
    """Every blocklisted command, in the three positions this module has actually been bypassed
    in: alone, after a newline, and after a separator.

    Derived from the BASELINE's own blocklist rather than hardcoded, so deleting an entry shows
    up as a regression on the payload that entry used to reject. Review measured the
    combinatorial corpus reaching 3 of 27 blocklisted commands: replacing the whole blocklist
    with two entries was reported as a clean PASS.
    """
    blocklist = getattr(baseline, "BLOCKLIST", None)
    if not blocklist:
        # Silently probing only the 17 pattern triggers would be the C1 blind spot again, one
        # attribute rename away. A baseline with no blocklist cannot be compared for blocklist
        # protections at all, so say so: run() turns this into a SKIP naming the cause, and
        # --require-baseline decides whether a skip is acceptable.
        raise RuntimeError("baseline module exposes no BLOCKLIST - nothing to probe it with")
    probes: List[str] = list(PATTERN_PROBES)
    for command in sorted(blocklist):
        probes.append(f"{command} x")
        probes.append(f"ls\n{command} x")
        probes.append(f"echo hi; {command} x")
    return probes


def payloads(max_len: int, extra: Optional[List[str]] = None) -> List[str]:
    out = set(extra or [])
    for n in range(2, max_len + 1):
        for combo in itertools.product(ALPHABET, repeat=n):
            out.add("".join(combo))
    return sorted(out)


def verdict(validator, command: str) -> bool:
    """True == ALLOW. Any exception counts as REJECT: an exploding validator is not a pass,
    but it is also not a widening, and it will fail the test suite on its own."""
    try:
        return bool(validator.validate(command)[0])
    except Exception as exc:  # noqa: BLE001 - deliberately total; see docstring
        # Reported, not swallowed: a FAIL caused by a crash looks identical to a FAIL caused
        # by a real regression unless the cause is on stderr.
        print(f"  (validator raised on {command!r}: {exc!r})", file=sys.stderr)
        return False


def compare(baseline_path: Path, current_path: Path, max_len: int) -> Dict[str, object]:
    """The whole check, over two module FILES - no git, so it is directly testable.

    A test can hand this a deliberately holed module and assert the gate fails; a gate that
    has never been shown to fail is not evidence of anything, which is the lesson this
    module's own review history keeps re-teaching.
    """
    baseline = _load("cv_baseline", baseline_path)
    current = _load("cv_current", current_path)

    corpus = payloads(max_len, protection_probes(baseline))
    disclosed = [(re.compile(entry["payload"]), entry.get("baseline_reason", ""))
                 for entry in DISCLOSED_WIDENINGS]
    regressions: List[Dict[str, object]] = []
    widened = 0
    for safe_mode in (True, False):
        old_validator = baseline.CommandValidator(safe_mode=safe_mode)
        new_validator = current.CommandValidator(safe_mode=safe_mode)
        for command in corpus:
            if verdict(old_validator, command) or not verdict(new_validator, command):
                continue
            baseline_reason = old_validator.validate(command)[1]
            if any(rx.search(command) and baseline_reason.startswith(prefix)
                   for rx, prefix in disclosed):
                widened += 1
                continue
            regressions.append({
                "safe_mode": safe_mode,
                "payload": command,
                "baseline_reason": baseline_reason,
            })

    return {"status": "fail" if regressions else "pass",
            "payloads": len(corpus),
            "regressions": regressions[:50],
            "regression_count": len(regressions),
            "disclosed_widenings": widened}


def run(baseline_ref: str, max_len: int, repo_root: Path) -> Dict[str, object]:
    baseline_ref, how = resolve_baseline(baseline_ref, repo_root)
    source = _baseline_source(baseline_ref, repo_root)
    if source is None:
        return {"status": "skipped", "baseline": baseline_ref, "baseline_how": how,
                "reason": f"no {MODULE_PATH} at {baseline_ref} - nothing to compare against"}

    with tempfile.TemporaryDirectory() as tmp:
        baseline_path = Path(tmp) / "cv_baseline.py"
        baseline_path.write_text(source)
        try:
            report = compare(baseline_path, repo_root / MODULE_PATH, max_len)
        except Exception as exc:  # noqa: BLE001 - the baseline is the untrusted side here
            # A baseline that cannot be imported or constructed (syntax error at that commit, a
            # changed __init__ signature) is not a finding about the current tree, and a raw
            # traceback naming neither side reads as "the gate is flaky" - which is how a gate
            # gets deleted. Report it as a SKIP with the cause, and let --require-baseline
            # decide whether that is acceptable.
            return {"status": "skipped", "baseline": baseline_ref, "baseline_how": how,
                    "baseline_is_head": _is_head(baseline_ref, repo_root),
                    "reason": f"baseline at {baseline_ref[:12]} is not loadable: {exc!r}"}
    report["baseline"] = baseline_ref
    report["baseline_how"] = how
    report["baseline_is_head"] = _is_head(baseline_ref, repo_root)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", default="auto",
                        help="git ref to compare against; 'auto' (default) uses the merge base "
                             "with main, falling back to HEAD~1")
    parser.add_argument("--max-len", type=int, default=3,
                        help="longest alphabet product to generate (default: 3)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--require-baseline", action="store_true",
                        help="fail instead of skipping when no usable baseline exists. CI "
                             "passes this: a shallow clone with no reachable main would "
                             "otherwise compare HEAD against itself and report a vacuous pass, "
                             "which is the fake-green failure this gate exists to prevent.")
    args = parser.parse_args()

    repo_root = _repo_root()
    if args.max_len < 2:
        print("FAIL: --max-len must be at least 2; a corpus of single tokens proves nothing.")
        return 1

    report = run(args.baseline, args.max_len, repo_root)

    if args.require_baseline and (report["status"] == "skipped"
                                  or report.get("baseline_is_head")):
        print(f"FAIL: --require-baseline was given and there is no usable baseline "
              f"({report.get('baseline_how') or report.get('reason')}). The baseline resolves "
              "to HEAD itself, so this run would compare the tree against a copy of itself. "
              "Fetch enough history for a real merge base with main.")
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    elif report["status"] == "skipped":
        print(f"SKIP: {report['reason']}")
    elif report["status"] == "pass":
        print(f"OK: {report['payloads']} payloads, both modes, vs {report['baseline'][:12]} "
              f"({report['baseline_how']}) - "
              f"no undisclosed REJECT -> ALLOW "
              f"({report['disclosed_widenings']} disclosed widenings matched).")
    else:
        print(f"FAIL: {report['regression_count']} payload(s) moved REJECT -> ALLOW vs "
              f"{report['baseline'][:12]} ({report['baseline_how']}). "
              "Each one is a protection this change removed.")
        for item in report["regressions"]:
            print(f"  safe_mode={item['safe_mode']}  {item['payload']!r}")
            print(f"      baseline rejected it: {item['baseline_reason']}")
        print("\nIf a widening is intended, add it to DISCLOSED_WIDENINGS in this script "
              "with the reason - and disclose it in CHANGELOG.md too.")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())

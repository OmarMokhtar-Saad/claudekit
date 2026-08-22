#!/usr/bin/env python3
"""Executable oracle for `validator-executor-divergence`: does bash run what the validator let through?

`scripts/check-validator-differential.py` compares the validator against ITSELF at another
commit. That catches a protection being REMOVED; it cannot catch one that was never there,
because a payload both versions wrongly allow looks identical in both. Every fail-open found in
the 2026-08-21 batch was that second shape - the validator and bash disagreeing about what the
input is - and the only thing that ever found them was running the payload under bash with the
dangerous commands shadowed. This script is that, automated.

For every payload the validator ALLOWS, bash runs it in a sandbox where `rm`, `sudo`, `chmod`,
`curl`, `dd` and friends are shell functions that print a marker and do nothing. A marker on an
ALLOWED payload is a divergence: the guard said yes and the shell reached a command the
blocklist exists to stop.

Containment, and its limits, stated plainly because this script executes fuzzed shell input:
  * `PATH` is emptied, so nothing outside the shadow functions and bash builtins can run -
    and a payload that reassigns `PATH` is refused, because that premise only holds at lookup
    time and arbitrary bash can rewrite it;
  * cwd and `HOME` are a throwaway temp directory, removed afterwards;
  * `ulimit -t` (CPU) and `-f` (file size) are set INSIDE the child - never the caller;
  * `ulimit -u` is deliberately NOT set: on macOS the process cap is per-USER, so a small value
    breaks unrelated processes and every payload fails to fork. Measured, not assumed;
  * fork-bomb and loop shapes are refused structurally BEFORE they reach bash, and counted as
    unverified rather than silently passed;
  * every run has a wall-clock timeout.
Known blind spots, none of them a claim of coverage:
  * an empty `PATH` means a wrapper like `xargs` is absent, so wrapper-argument divergence is
    not observable;
  * `command rm -rf /` and `\rm -rf /` bypass function lookup by design, so they reach neither
    the shadow function nor a real binary and the oracle stays SILENT on them - a false
    negative under this containment, not a live escape;
  * every refused shape above is unobserved by construction, which is why the refusal ratio is
    part of the verdict rather than a footnote.

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

MODULE_PATH = "src/claudekit/security/command_validator.py"
SIBLING = "check-validator-differential.py"

# Shapes refused before execution. A refusal is REPORTED, never silently treated as clean.
#
# The second alternative is the one that matters, and review caught its absence: an empty PATH
# and shadow functions contain EXTERNAL COMMANDS ONLY. Redirection is bash's own parser, so
# `echo x > /etc/hosts` - which is in this very corpus, as a dangerous-pattern probe - would
# have written to the real path the moment a validator under test allowed it. On a root CI
# runner that is host damage, on exactly the payload class this oracle exists to exercise.
# Any redirect whose target starts with `/` or `~` is refused before bash sees it, which means
# redirect divergence is NOT something this gate can observe. That is a stated blind spot, not
# a silent one.
REFUSED_SHAPES = re.compile(
    r"\(\s*\)\s*\{"              # function definition: fork bombs
    r"|&\s*$|&\s*[;\n]"            # backgrounding: outlives the run
    r"|\bwhile\b|\bfor\b|\buntil\b|\(\("   # loops, including C-style
    # Anything that moves the frame of reference a "safe relative target" is relative TO.
    # Review round 4: `cd /etc && echo x > passwd` has a target of `passwd`, which is safe in
    # isolation - the escape is the cwd, not the string. `cd` is a builtin, so an empty PATH
    # does not touch it. CDPATH reaches the same place without an absolute argument.
    r"|\bcd\b|\bpushd\b|\bpopd\b|\bchdir\b|\bCDPATH\b"
    # exec replaces the shell (including its ulimits and shadow functions); source/. run a file
    # as script in this shell.
    r"|\bexec\b|\bsource\b|(?:^|[\s;&|])\.\s"
    # The empty-PATH premise is a property of PATH's value AT LOOKUP TIME, and the payload is
    # arbitrary bash. `PATH=/usr/bin python3 -c ...` restores every external binary on the
    # machine - not the shadowed ten (bash checks functions first, so those stay shadowed) but
    # python3, perl, find, nc, tar, awk and whatever else the runner has. Review round 5, and
    # the same class as `cd`: it changes what a command name means.
    r"|\bPATH\s*=|\bexport\b"
)

# Redirect targets are ALLOWLISTED, not denylisted, and the polarity is the point: a denylist
# of dangerous targets is what review round 1 rejected here. `>[|]?\s*[/~]` refused
# `> /etc/hosts` but not `> "/etc/hosts"`, `> $HOME/../../etc/x` or `> ${x}/etc/x`, each of
# which reaches a real absolute path just as well. A target may only be a plain relative name -
# word characters, dots and dashes - which cannot leave the sandbox cwd.
_REDIRECT = re.compile(r"(?:\d*)(?:>>|>\||>&|>|<<<|<<|<)\s*([^\s;|&\n]*)")
_SAFE_TARGET = re.compile(r"[\w.-]+\Z")


def refused(payload: str) -> bool:
    """Would executing this risk the machine rather than the sandbox?"""
    if REFUSED_SHAPES.search(payload):
        return True
    for target in _REDIRECT.findall(payload):
        if target and not _SAFE_TARGET.match(target):
            return True
        if not target:
            # A redirect with no target on this line - the next word could be anything, and a
            # heredoc body is not a filename. Fail closed rather than model it.
            return True
    return False


SHADOWED = ["rm", "sudo", "chmod", "chown", "curl", "wget", "dd", "mkfs", "shutdown", "reboot"]

PROBE = """\
ulimit -t 2  2>/dev/null || true
ulimit -f 64 2>/dev/null || true
ulimit -v 262144 2>/dev/null || true
set -o noclobber 2>/dev/null || true
export PATH=""
export HOME="$PWD"
%s
eval "$1"
"""


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _probe_script() -> str:
    functions = "\n".join(f'{name}() {{ echo "MARKER:{name}"; }}' for name in SHADOWED)
    return PROBE % functions


def markers(payload: str, sandbox: Path, timeout: float) -> Optional[List[str]]:
    """Marker names bash reached, or None if the payload was refused or timed out."""
    if refused(payload):
        return None
    try:
        result = subprocess.run(
            [*process_isolation(), "bash", "--noprofile", "--norc", "probe.sh", payload],
            capture_output=True, text=True, timeout=timeout, cwd=sandbox,
        )
    except subprocess.TimeoutExpired:
        return None
    return [line[len("MARKER:"):] for line in result.stdout.splitlines()
            if line.startswith("MARKER:")]


def process_isolation() -> List[str]:
    """PID/process isolation where the platform offers it - NOT a filesystem boundary.

    An earlier version of this function claimed to contain absolute-path writes, and review
    refuted it: `unshare --mount` gives the child its own mount TABLE, initialised as a copy of
    the parent's, and this script never mounts anything inside it - so `/etc/hosts` still
    resolves to the same inode and a write goes through to the real file. `--map-root-user`
    makes the process look like UID 0 to itself; it does not grant writes the invoking user
    could not already perform. Real containment would need `pivot_root` or tmpfs over the paths
    that matter, which is more machinery than this gate is worth.

    So the honest account of why executing here is acceptable has three parts, and the
    namespace is the smallest of them: payload shapes that can escape are refused before bash
    sees them; CI runs on an ephemeral runner that is discarded; and a developer machine does
    not run this at all without --allow-execution. What is left below is process containment
    for runaway children, which is real but narrow.
    """
    if sys.platform.startswith("linux") and shutil.which("unshare"):
        return ["unshare", "--pid", "--fork"]
    return []


def run(max_len: int, repo_root: Path, timeout: float,
        module_path: Optional[Path] = None) -> Dict[str, object]:
    """`module_path` overrides which validator is asked - the tests point it at a mutant, so
    the oracle itself is shown to fire rather than only ever reporting clean."""
    shipped = _load("cv_shipped", repo_root / MODULE_PATH)
    validator_module = (_load("cv_under_test", module_path) if module_path else shipped)
    differential = _load("cv_differential", repo_root / "scripts" / SIBLING)
    # Probes come from the SHIPPED module, never from the one under test: a mutant that
    # empties BLOCKLIST would otherwise shrink the corpus that is supposed to catch it.
    corpus = differential.payloads(max_len, differential.protection_probes(shipped))

    sandbox = Path(tempfile.mkdtemp(prefix="validator-oracle-"))
    findings: List[Dict[str, object]] = []
    unverified = 0
    errored = 0
    executed = 0
    try:
        (sandbox / "probe.sh").write_text(_probe_script())
        for safe_mode in (True, False):
            validator = validator_module.CommandValidator(safe_mode=safe_mode)
            for payload in corpus:
                try:
                    allowed = bool(validator.validate(payload)[0])
                except Exception:  # noqa: BLE001 - a crash is not an ALLOW
                    # Counted, not skipped: review found that a validator raising on EVERY
                    # payload produced findings=0, unverified=0, status=pass - indistinguishable
                    # from a thorough clean run. A gate that reports clean because it asked
                    # nothing is the failure mode this whole file exists to avoid.
                    errored += 1
                    continue
                if not allowed:
                    continue
                reached = markers(payload, sandbox, timeout)
                if reached is None:
                    unverified += 1
                    continue
                executed += 1
                if reached:
                    findings.append({"safe_mode": safe_mode, "payload": payload,
                                     "reached": sorted(set(reached))})
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    # Liveness is part of the verdict, not a number to read afterwards. `executed == 0` is the
    # floor; `unverified > executed` is the slope review asked about - a refusal rule that grows
    # over-broad would otherwise keep reporting `pass` on a run that verified almost nothing,
    # which is the same fake-green shape as an empty corpus.
    offered = executed + unverified
    refusal_ratio = round(unverified / offered, 3) if offered else 1.0
    starved = not executed or refusal_ratio > 0.5
    return {"status": "fail" if (findings or starved) else "pass",
            "refusal_ratio": refusal_ratio,
            "payloads": len(corpus),
            "findings": findings[:50],
            "finding_count": len(findings),
            "executed": executed,
            "unverified": unverified,
            "errored": errored}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-len", type=int, default=2,
                        help="longest alphabet product to generate (default: 2 - this one "
                             "SPAWNS A SHELL per allowed payload, so it is far slower than the "
                             "differential gate)")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds per payload")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--allow-execution", action="store_true",
                        help="required to run: this gate EXECUTES fuzzed shell payloads. CI "
                             "passes it: the runner is ephemeral and is discarded afterwards. "
                             "That, plus refusing escape-shaped payloads before bash sees them, "
                             "is the containment - there is no filesystem jail. Five review "
                             "rounds each found a shell feature the lexical rules did not "
                             "model, so a developer machine does not run this by default.")
    args = parser.parse_args()

    if args.max_len < 2:
        print("FAIL: --max-len must be at least 2; a corpus of single tokens proves nothing.")
        return 1
    if not args.allow_execution:
        print("SKIP: this gate executes fuzzed shell payloads. Pass --allow-execution to run "
              "it (CI does). Refusing by default is the point: on a machine without a "
              "namespace jail, containment here is lexical.")
        return 0
    if shutil.which("bash") is None:
        print("SKIP: no bash on PATH - this gate needs a real shell to be an oracle.")
        return 0

    repo_root = Path(__file__).resolve().parent.parent
    report = run(args.max_len, repo_root, args.timeout)

    if args.json:
        print(json.dumps(report, indent=2))
    elif report["status"] == "pass":
        print(f"OK: {report['payloads']} payloads, both modes - bash actually ran "
              f"{report['executed']} of the ones the validator allowed and reached no shadowed "
              f"command ({report['unverified']} refused or timed out, "
              f"{report['errored']} raised).")
    elif not report["finding_count"]:
        print(f"FAIL: bash ran only {report['executed']} of the allowed payloads while "
              f"{report['unverified']} were refused or timed out and {report['errored']} made "
              "the validator raise. A clean report from a gate that asked almost nothing is "
              "not a clean report.")
    else:
        print(f"FAIL: {report['finding_count']} payload(s) the validator ALLOWED reached a "
              "command the blocklist exists to stop:")
        for item in report["findings"]:
            print(f"  safe_mode={item['safe_mode']}  {item['payload']!r}")
            print(f"      bash reached: {', '.join(item['reached'])}")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())

"""command-guard.sh tells a CRASHED validator apart from a VERDICT.

Both directions, because only one of them was ever tested downstream:

  * a validator that dies on ImportError is UNAVAILABLE, not a refusal. A
    console script whose package is gone exits 1 with a traceback; that fell
    through to the deny branch and blocked EVERY Bash command for 17 minutes
    while printing a Python traceback dressed as a policy decision.
  * a genuine refusal whose TEXT contains a crash token must still block. A
    refusal echoes the command it refused, so `ImportError=1 rm -rf /tmp/zzz`
    put the token inside the verdict and was waved through. The exit code, not
    the text, decides.

The hook is driven with a fake `claudekit` on PATH, so nothing real is broken
and no installed package is touched.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / ".claude" / "hooks"
HOOK = HOOKS / "command-guard.sh"

CRASHING = """#!/bin/sh
echo 'Traceback (most recent call last):' >&2
echo '  File "/x/bin/claudekit", line 3, in <module>' >&2
echo "    from claudekit.cli.main import main" >&2
echo "ModuleNotFoundError: No module named 'claudekit'" >&2
exit 1
"""

# A REAL refusal (rc 2) whose message echoes the attacker-supplied token.
ECHOING_REFUSAL = """#!/bin/sh
echo "BLOCKED: Dangerous pattern (environment override: ImportError)"
exit 2
"""

# The SAME refusal, written to STDERR. Some validators report their reason
# there; that is the channel the crash discriminator reads, so this is the shape
# the rc-2 exclusion -- and nothing else -- has to block.
STDERR_REFUSAL = """#!/bin/sh
echo "ImportError: environment override is a blocked pattern" >&2
exit 2
"""

# rc 1 (not a verdict code) with an anchored crash token on STDOUT. Only the
# channel split keeps this from reading as a crash.
RC1_STDOUT_CRASH_TOKEN = """#!/bin/sh
echo "ImportError: blocked pattern in your command"
exit 1
"""

PLAIN_REFUSAL = """#!/bin/sh
echo "BLOCKED: Blocked command: rm"
exit 2
"""

ALLOWING = """#!/bin/sh
exit 0
"""


def fake_bin(tmp_path: Path, script: str) -> Path:
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    shim = d / "claudekit"
    shim.write_text(script, encoding="utf-8")
    shim.chmod(0o755)
    return d


def run_hook(tmp_path: Path, script: str, command: str, profile="standard",
             hook: Path = HOOK):
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin(tmp_path, script)}{os.pathsep}{env['PATH']}"
    env["ECC_HOOK_PROFILE"] = profile
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": command}})
    proc = subprocess.run(["bash", str(hook)], input=payload, env=env,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


class TestCrashIsNotAVerdict:
    def test_crashing_validator_is_permissive_under_standard(self, tmp_path):
        rc, out = run_hook(tmp_path, CRASHING, "git status")
        assert rc == 0, out
        assert "NOT checked" in out

    def test_crashing_validator_still_blocks_under_strict(self, tmp_path):
        rc, out = run_hook(tmp_path, CRASHING, "git status", profile="strict")
        assert rc == 2, out

    def test_allowed_command_passes(self, tmp_path):
        rc, out = run_hook(tmp_path, ALLOWING, "ls -la")
        assert rc == 0, out


class TestVerdictWins:
    def test_plain_refusal_blocks(self, tmp_path):
        rc, out = run_hook(tmp_path, PLAIN_REFUSAL, "rm -rf /tmp/zzz")
        assert rc == 2, out

    def test_stderr_refusal_carrying_a_crash_token_still_blocks(self, tmp_path):
        """The exit code decides even when the token lands on the channel the
        discriminator reads."""
        rc, out = run_hook(tmp_path, STDERR_REFUSAL, "ImportError=1 rm -rf /tmp/zzz")
        assert rc == 2, out
        assert "NOT checked" not in out

    def test_rc1_refusal_with_a_crash_token_on_stdout_still_blocks(self, tmp_path):
        """The split: a verdict on stdout is never searched for crash tokens."""
        rc, out = run_hook(tmp_path, RC1_STDOUT_CRASH_TOKEN, "rm -rf /tmp/zzz")
        assert rc == 2, out

    def test_refusal_echoing_a_crash_token_still_blocks(self, tmp_path):
        """THE bypass: eleven inert characters put `ImportError` in the verdict."""
        rc, out = run_hook(tmp_path, ECHOING_REFUSAL, "ImportError=1 rm -rf /tmp/zzz")
        assert rc == 2, out
        assert "NOT checked" not in out


@pytest.fixture()
def guard_mutant():
    made = []

    def _make(find: str, replace: str, tag: str) -> Path:
        src = HOOK.read_text(encoding="utf-8")
        assert src.count(find) == 1, f"mutation anchor {tag!r} is not unique"
        dst = HOOKS / f"_mutant_{tag}_command-guard.sh"
        dst.write_text(src.replace(find, replace), encoding="utf-8")
        made.append(dst)
        return dst

    yield _make
    for p in made:
        p.unlink(missing_ok=True)


class TestMutationControls:
    def test_dropping_the_exit_code_condition_reopens_the_bypass(
            self, tmp_path, guard_mutant):
        """The rc-2 exclusion is load-bearing for a validator that reports its
        refusal on STDERR -- the channel the discriminator reads. Measured: with
        the refusal on stdout the split alone already closes it, so this control
        has to use the stderr shim or it proves nothing."""
        mutated = guard_mutant(
            'if [ "$RC" -ne 0 ] && [ "$RC" -ne 2 ] && [ "$RC" -ne 127 ] \\',
            'if [ "$RC" -ne 0 ] && [ "$RC" -ne 127 ] \\',
            "verdictignored",
        )
        rc, out = run_hook(tmp_path, STDERR_REFUSAL, "ImportError=1 rm -rf /tmp/zzz",
                           hook=mutated)
        assert rc == 0, (
            "the mutant still blocked: the stderr-refusal test is not caused by "
            "the exit-code condition")

    def test_searching_the_verdict_channel_reopens_the_bypass(self, tmp_path, guard_mutant):
        """THE historical defect: the first version grepped the MERGED output, so
        a refusal that echoes the command carried the crash token into the
        channel being searched. Search $OUT as well and it reopens."""
        mutated = guard_mutant(
            'printf \'%s\\n\' "$ERR" | grep -qE \\',
            'printf \'%s\\n\' "$OUT$ERR" | grep -qE \\',
            "merged",
        )
        rc, out = run_hook(tmp_path, RC1_STDOUT_CRASH_TOKEN, "rm -rf /tmp/zzz",
                           hook=mutated)
        assert rc == 0, "the channel split is not load-bearing"

    def test_widening_the_pattern_reopens_the_bypass(self, tmp_path, guard_mutant):
        mutated = guard_mutant(
            "'^(Traceback \\(most recent call last\\):|[A-Za-z_.]*(ModuleNotFoundError|ImportError): )'; then",
            "''; then",
            "toowide",
        )
        # rc 1 with arbitrary stderr now reads as a crash.
        noisy = "#!/bin/sh\necho 'BLOCKED: Blocked command: rm' >&2\nexit 1\n"
        rc, out = run_hook(tmp_path, noisy, "rm -rf /tmp/zzz", hook=mutated)
        assert rc == 0, "pattern anchoring is not load-bearing"
        rc, out = run_hook(tmp_path, noisy, "rm -rf /tmp/zzz")
        assert rc == 2, "the real hook must still block an rc-1 refusal"

    def test_removing_crash_detection_restores_the_outage(self, tmp_path, guard_mutant):
        mutated = guard_mutant(
            'if [ "$RC" -ne 0 ] && [ "$RC" -ne 2 ] && [ "$RC" -ne 127 ] \\',
            "if false \\",
            "nocrash",
        )
        rc, out = run_hook(tmp_path, CRASHING, "git status", hook=mutated)
        assert rc == 2, "crash detection is not load-bearing"

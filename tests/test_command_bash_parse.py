"""Command-prompt bash cannot be syntactically broken without CI saying so.

`.claude/commands/*.md` ships 682 lines of bash inside ```bash fences (27 files,
measured 2026-08-24) and nothing linted it. CI's `shellcheck` step covers `install.sh`
and `.claude/hooks/*.sh`; the command corpus was outside it. Six parse errors of one
shape -- `<TASK>`, `<N>` and friends left inside `[ ]` -- were fixed by
`plan-command-bash-placeholders.md`, and nothing kept them fixed.

That is not a hypothetical: a comment written *during* those fixes put markdown
backticks inside a `python3 -c "..."` shell string, where a backtick is command
substitution. The class reopens silently without a gate.

Scope, deliberately narrow: PARSE ERRORS ONLY (SC1072/SC1073/SC1009). Style findings
are out of scope so the gate is satisfiable the day it lands -- `ops-dispatcher-payload`'s
H1 recorded what happens otherwise ("a gate that cries wolf gets routed around"). Parse
errors are the class currently at zero, so this lands green and stays meaningful.

Fences are concatenated PER FILE rather than linted individually: they share state, and
per-fence linting produces SC2154 noise that would have to be suppressed. Suppressions
are where gates go to die.

`shellcheck` is not import-skipped. It is already a DoD gate, and a skip here would
restore exactly the silent pass this file exists to remove.

What this does NOT catch: bash that parses and is wrong. Do not read a green run as
"command bash is linted".
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMMANDS = REPO / ".claude" / "commands"

PARSE_CODES = {"SC1072", "SC1073", "SC1009"}


def _bash_blocks(path):
    """(first_body_line_1indexed, [lines]) for every ```bash fence in a markdown file."""
    lines = path.read_text().splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```bash"):
            start = i + 2
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            if body:
                out.append((start, body))
        i += 1
    return out


def parse_errors(path):
    """Parse-error findings for one command file, reported at MARKDOWN line numbers."""
    parts = []
    linemap = {}
    n = 1
    for start, body in _bash_blocks(path):
        for offset, line in enumerate(body):
            linemap[n] = start + offset
            parts.append(line)
            n += 1
        # A blank separator between fences, mapped to nothing: a finding on the
        # separator is a bug in this mapping, and `None` makes that visible as `?`
        # instead of silently blaming the previous line.
        linemap[n] = None
        parts.append("\n")
        n += 1
    if not parts:
        return []

    script = "#!/usr/bin/env bash\n" + "".join(parts)
    proc = subprocess.run(
        ["shellcheck", "-s", "bash", "-f", "gcc", "-"],
        input=script, capture_output=True, text=True,
    )
    found = []
    for line in proc.stdout.splitlines():
        m = re.match(r"-:(\d+):\d+: \w+: (.*) \[(SC\d+)\]", line)
        if not m or m.group(3) not in PARSE_CODES:
            continue
        # shellcheck line 1 is the synthetic shebang, so concat line N is script N+1.
        md_line = linemap.get(int(m.group(1)) - 1)
        found.append(
            f"{path.name}:{md_line if md_line else '?'}: {m.group(3)} {m.group(2)}"
        )
    return found


def test_shellcheck_is_available():
    """No skip: shellcheck is a DoD gate, and skipping restores the silent pass."""
    assert shutil.which("shellcheck"), (
        "shellcheck is required -- it is already in the DoD command list. "
        "Install it (brew install shellcheck) rather than skipping this file."
    )


def test_no_command_bash_has_a_parse_error():
    findings = [f for path in sorted(COMMANDS.glob("*.md")) for f in parse_errors(path)]
    assert not findings, "Parse errors in command bash:\n" + "\n".join(findings)


def test_the_gate_catches_a_reintroduced_placeholder(tmp_path):
    """Mutation proof, in the suite: the gate must FAIL on the original defect shape.

    The first hand-run of this proof targeted `ship.md` and reported GREEN. `ship.md`
    has ZERO ```bash fences, so nothing was inserted into a linted region -- a `grep`
    for the mutation caught it, not the gate. This test builds its own fixture so the
    mutation cannot fail to land.
    """
    victim = tmp_path / "mutant.md"
    victim.write_text(
        "# Mutant\n\n```bash\nif [ <N> -gt 3 ]; then echo hi\n```\n"
    )
    findings = parse_errors(victim)
    assert findings, "the gate did not flag a reintroduced <N> placeholder"
    codes = {f.split()[1] for f in findings}
    assert codes & PARSE_CODES
    # The line mapping is the half most likely to be silently useless.
    assert any(f.startswith("mutant.md:4:") for f in findings), findings


def test_a_clean_fence_is_not_flagged(tmp_path):
    """The other direction: valid bash must pass, or the gate is unsatisfiable."""
    ok = tmp_path / "clean.md"
    ok.write_text("# Clean\n\n```bash\nif [ 4 -gt 3 ]; then echo hi; fi\n```\n")
    assert parse_errors(ok) == []


@pytest.mark.parametrize("stem", ["adapt", "audit", "build-fix"])
def test_the_corpus_actually_has_fences_to_check(stem):
    """Coverage floor: a gate over an empty extraction is a gate over nothing."""
    path = COMMANDS / f"{stem}.md"
    assert _bash_blocks(path), f"{path.name} has no ```bash fences to lint"

"""Behavioral tests for scripts/check-silent-failure.py.

Every assertion is on an EXIT CODE, never on summary text.

Fixtures live in a gitignored directory INSIDE the repo. They must not go under $TMPDIR:
`.claude/hooks/ops-enforcement.sh:43` exempts `/private/tmp/claude-*`, `/tmp/claude-*` and
`/var/folders/*` (macOS $TMPDIR), so a fixture placed there makes that hook exit 0 and any
assertion about it passes vacuously.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCANNER = REPO / "scripts" / "check-silent-failure.py"
FIXTURE_ROOT = REPO / ".tmp-test-fixtures"

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_UNUSABLE = 2
EXIT_INCOMPLETE = 3

# Read from the scanner instead of hardcoded: these tests exist to prove the cap TRIPS,
# so a fixture sized by a literal silently stops proving it the moment the cap moves.
# Raising MAX_JOIN_LINES 80 -> 250 turned both of them green against an uncapped scan.
MAX_JOIN_LINES = int(
    re.search(r"^MAX_JOIN_LINES = (\d+)", SCANNER.read_text(encoding="utf-8"),
              re.M).group(1))
OVER_CAP = MAX_JOIN_LINES + 40

# Known, accepted residue. These paths are owned by other workstreams; see the plan's
# "Gate decision". The set pins PATHS, not counts or line numbers, so edits inside these
# files cannot flip it spuriously.
ACCEPTED_RESIDUE = {
    "install.sh",
    "src/claudekit/cli/main.py",
    ".claude/operations/scripts/execute-json-ops.py",
    ".claude/hooks/iron-law-gate.py",
    ".claude/hooks/reflection-gate.py",
    ".claude/hooks/reflection.py",
}


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCANNER), *args], capture_output=True, text=True
    )


@pytest.fixture()
def sandbox():
    FIXTURE_ROOT.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=str(FIXTURE_ROOT), prefix="sft-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write(sandbox: Path, name: str, body: str) -> Path:
    target = sandbox / name
    target.write_text(body, encoding="utf-8")
    return target


def test_scanner_ships_with_the_plan():
    assert SCANNER.is_file()


# --- shell rule -----------------------------------------------------------
def test_planted_silent_failure_is_caught(sandbox):
    script = write(sandbox, "planted.sh",
                   '#!/usr/bin/env bash\ngit stash apply 2>/dev/null || true\n')
    assert run(str(script)).returncode == EXIT_FINDINGS


def test_planted_compound_python_write_is_caught(sandbox):
    """The install.sh shape: the write and the swallowed failure are lines apart, so a
    line-at-a-time scanner misses it. This test pins logical_lines()."""
    body = (
        '#!/usr/bin/env bash\n'
        'python3 -c "\n'
        'import json\n'
        "open('/tmp/x.json', 'w').write(json.dumps({}))\n"
        '" 2>/dev/null && print_ok "configured" || print_warn "could not configure"\n'
    )
    assert run(str(write(sandbox, "compound.sh", body))).returncode == EXIT_FINDINGS


def test_readonly_probes_are_not_flagged(sandbox):
    """192 `2>/dev/null` sites are legitimate probes. Flagging them gets the lint disabled."""
    body = (
        '#!/usr/bin/env bash\n'
        'command -v jq >/dev/null 2>&1 || echo "no jq"\n'
        'root=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")\n'
        'grep -q needle haystack 2>/dev/null || true\n'
        'branch=$(git branch --show-current 2>/dev/null || echo detached)\n'
        'git stash list 2>/dev/null || true\n'
    )
    assert run(str(write(sandbox, "probes.sh", body))).returncode == EXIT_CLEAN


def test_sed_inplace_is_caught(sandbox):
    """Recall guard: `sed -i` is a mutator that the first draft missed entirely."""
    body = '#!/usr/bin/env bash\nsed -i.bak "s/a/b/" "$FILE" 2>/dev/null || true\n'
    assert run(str(write(sandbox, "sed.sh", body))).returncode == EXIT_FINDINGS


def test_odd_quote_in_a_comment_does_not_swallow_following_lines(sandbox):
    """M1 regression. A comment containing one `"` used to break quote parity, collapsing
    every following line into one block -- wrong line numbers, and one pragma anywhere in
    the runaway block would exempt all of it. The clean `|| true` below is on a read-only
    command, so the correct verdict is exit 0."""
    body = (
        '#!/usr/bin/env bash\n'
        '# the previous inline ["\\x27] was NOT decoded by grep -E\n'
        'grep -q needle haystack 2>/dev/null || true\n'
        'echo done\n'
    )
    assert run(str(write(sandbox, "oddquote.sh", body))).returncode == EXIT_CLEAN


def test_pragma_in_a_later_block_does_not_exempt_an_earlier_finding(sandbox):
    """Companion to the above: proves blocks are not being merged. The pragma sits on a
    different command than the finding, so it must NOT suppress it."""
    body = (
        '#!/usr/bin/env bash\n'
        '# a comment with one " quote\n'
        'rm -rf "$STAGING" 2>/dev/null || true\n'
        '# silent-ok: this pragma belongs to the copy below, not the rm above\n'
        'cp "$A" "$B" 2>/dev/null || true\n'
    )
    assert run(str(write(sandbox, "scoped.sh", body))).returncode == EXIT_FINDINGS


def test_heredoc_body_is_not_scanned_as_shell(sandbox):
    body = (
        '#!/usr/bin/env bash\n'
        "cat <<'DOC' > /dev/null\n"
        'rm -rf "$HOME" 2>/dev/null || true\n'
        'DOC\n'
        'echo done\n'
    )
    assert run(str(write(sandbox, "heredoc.sh", body))).returncode == EXIT_CLEAN


def test_shebang_file_without_sh_suffix_is_scanned(sandbox):
    script = write(sandbox, "hookfile",
                   '#!/bin/bash\ngit stash apply 2>/dev/null || true\n')
    assert run(str(script)).returncode == EXIT_FINDINGS


# --- pragma ---------------------------------------------------------------
def test_pragma_exempts_an_intentional_site(sandbox):
    body = ('#!/usr/bin/env bash\n'
            '# silent-ok: optional asset dir; absence is not an error\n'
            'cp "$SRC"/*.md "$DEST/" 2>/dev/null || true\n')
    assert run(str(write(sandbox, "pragma.sh", body))).returncode == EXIT_CLEAN


def test_pragma_without_a_substantive_reason_does_not_exempt(sandbox):
    body = ('#!/usr/bin/env bash\n'
            '# silent-ok: eh\n'
            'cp "$SRC"/*.md "$DEST/" 2>/dev/null || true\n')
    assert run(str(write(sandbox, "weak.sh", body))).returncode == EXIT_FINDINGS


# --- python rule ----------------------------------------------------------
def test_python_swallowed_mutation_is_caught(sandbox):
    """The src/claudekit/cli/main.py:726 shape: mutation swallowed, caller reports success."""
    body = (
        "import os\n"
        "def uninstall(base):\n"
        "    for root, _d, _f in os.walk(base, topdown=False):\n"
        "        try:\n"
        "            os.rmdir(root)\n"
        "        except OSError:\n"
        "            pass\n"
        "    print('Removed everything')\n"
        "    return 0\n"
    )
    assert run(str(write(sandbox, "uninstall.py", body))).returncode == EXIT_FINDINGS


def test_python_cleanup_that_reraises_is_not_flagged(sandbox):
    """execute-json-ops.py:145 shape -- the failure IS propagated, one frame out."""
    body = (
        "import os\n"
        "def atomic(tmp):\n"
        "    try:\n"
        "        os.replace(tmp, 'dest')\n"
        "    except BaseException:\n"
        "        try:\n"
        "            os.unlink(tmp)\n"
        "        except OSError:\n"
        "            pass\n"
        "        raise\n"
    )
    assert run(str(write(sandbox, "atomic.py", body))).returncode == EXIT_CLEAN


def test_python_teardown_is_not_flagged(sandbox):
    """execute-json-ops.py:185 shape -- best-effort release is the documented contract."""
    body = (
        "import os\n"
        "class Lock:\n"
        "    def release(self):\n"
        "        try:\n"
        "            os.unlink(self.path)\n"
        "        except OSError:\n"
        "            pass\n"
    )
    assert run(str(write(sandbox, "lock.py", body))).returncode == EXIT_CLEAN


def test_python_readonly_probe_is_not_flagged(sandbox):
    body = (
        "import subprocess\n"
        "def root():\n"
        "    try:\n"
        "        return subprocess.run(['git', 'rev-parse'], capture_output=True).stdout\n"
        "    except Exception:\n"
        "        pass\n"
        "    return None\n"
    )
    assert run(str(write(sandbox, "probe.py", body))).returncode == EXIT_CLEAN


def test_python_pragma_exempts(sandbox):
    body = (
        "import os\n"
        "def f(p):\n"
        "    try:\n"
        "        os.rmdir(p)\n"
        "    # silent-ok: leftover dir is cosmetic; removal is opportunistic\n"
        "    except OSError:\n"
        "        pass\n"
        "    print('done')\n"
    )
    assert run(str(write(sandbox, "prag.py", body))).returncode == EXIT_CLEAN


# --- the lint must not itself fail silently -------------------------------
def test_missing_path_fails_loudly(sandbox):
    assert run(str(sandbox / "no-such-dir")).returncode == EXIT_UNUSABLE


def test_scanning_zero_files_is_distinguishable_from_zero_findings(sandbox):
    empty = sandbox / "empty"
    empty.mkdir()
    scanned_nothing = run(str(empty)).returncode
    clean = write(sandbox, "clean.sh", '#!/usr/bin/env bash\necho hello\n')
    scanned_something = run(str(clean)).returncode
    assert scanned_nothing == EXIT_UNUSABLE
    assert scanned_something == EXIT_CLEAN
    assert scanned_nothing != scanned_something


# --- the worked example and the ratchet -----------------------------------
def test_f57_site_is_fixed():
    """Fails against unfixed code: this is the test that pins the F57 patch."""
    target = REPO / ".claude" / "hooks" / "auto-checkpoint.sh"
    assert run(str(target)).returncode == EXIT_CLEAN


def test_repo_residue_is_confined_to_known_paths():
    """The interim ratchet. Any NEW silent-failure site outside the accepted residue fails.

    The exit-code assertion is load-bearing: without it, a scanner that exits 2 (renamed,
    moved, unreadable, zero files scanned) produces no matching stderr lines, `offenders`
    is empty, and the subset check passes vacuously -- exactly the `vacuous-check` class
    this plan's REVIEW_GUIDE edit flags as the next ratchet owing a verdict.
    """
    result = run(str(REPO))
    assert result.returncode in (EXIT_CLEAN, EXIT_FINDINGS), (
        "scanner did not run usefully (exit %d):\n%s" % (result.returncode, result.stderr)
    )
    offenders = set()
    for line in result.stderr.splitlines():
        if "silent failure:" not in line:
            continue
        raw = line.split(":", 1)[0]
        try:
            offenders.add(Path(raw).resolve().relative_to(REPO).as_posix())
        except ValueError:
            offenders.add(raw)
    assert offenders <= ACCEPTED_RESIDUE, (
        "new silent-failure site outside the accepted residue: %s"
        % sorted(offenders - ACCEPTED_RESIDUE)
    )


# --- the scan must never report clean when it could not read its input ----
def test_unparseable_python_is_not_reported_clean(sandbox):
    """A SyntaxError used to emit a Diagnostic and then fall through to exit 0 -- the linted
    class, inside the linter."""
    write(sandbox, "broken.py", "def f(:\n    pass\n")
    assert run(str(sandbox)).returncode == EXIT_INCOMPLETE


def test_join_cap_is_not_reported_clean(sandbox):
    """Tripping MAX_JOIN_LINES means part of the file was never parsed. Reviewer's mutant:
    setting MAX_JOIN_LINES=3 previously flipped ZERO tests."""
    body = ('#!/usr/bin/env bash\nfoo="'
            + "\n".join("line %d" % i for i in range(OVER_CAP)) + "\n")
    write(sandbox, "runaway.sh", body)
    assert run(str(sandbox)).returncode == EXIT_INCOMPLETE


def test_unterminated_heredoc_is_not_reported_clean(sandbox):
    """An unbounded heredoc skip would swallow every following line -- including a real
    finding -- and report success."""
    body = ('#!/usr/bin/env bash\n'
            'cat <<NOPE\n'
            + "\n".join("filler %d" % i for i in range(OVER_CAP)) + "\n"
            'git stash apply 2>/dev/null || true\n')
    write(sandbox, "heredoc-runaway.sh", body)
    assert run(str(sandbox)).returncode == EXIT_INCOMPLETE


def test_false_heredoc_that_terminates_far_away_is_not_reported_clean(sandbox):
    """The heredoc skip must be capped, not just diagnosed at EOF. `<< MARKER` here is an
    arithmetic shift, so the following lines are real code; if a bogus heredoc swallows them
    and then finds a line equal to the delimiter, no EOF diagnostic ever fires. Uncapped, the
    real finding below vanishes and the scanner reports OK -- verified by mutation."""
    body = ["#!/usr/bin/env bash", "x=$(( 1 << MARKER ))"]
    body += ["echo filler %d" % i for i in range(OVER_CAP)]
    body += ["git stash apply 2>/dev/null || true", "MARKER", "echo tail"]
    script = write(sandbox, "shift.sh", "\n".join(body) + "\n")
    assert run(str(script)).returncode == EXIT_INCOMPLETE


def test_incomplete_outranks_findings(sandbox):
    """An incomplete scan cannot support a complete verdict, so exit 3 beats exit 1."""
    write(sandbox, "real.sh", '#!/usr/bin/env bash\ngit stash apply 2>/dev/null || true\n')
    write(sandbox, "broken.py", "def f(:\n    pass\n")
    assert run(str(sandbox)).returncode == EXIT_INCOMPLETE


def test_large_inline_python_block_is_still_caught(sandbox):
    """Pins MAX_JOIN_LINES against regression to a corpus-unsafe value. The real
    auto-checkpoint.sh has inline `python3 -c` blocks of 26 and 45 lines; at cap=25 the join
    truncated and mis-reported F57's sibling at :101 instead of :109."""
    filler = "\n".join("x = %d" % i for i in range(40))
    body = ('#!/usr/bin/env bash\n'
            'python3 -c "\n'
            'import json\n' + filler + '\n'
            "open('/tmp/x.json', 'w').write(json.dumps({}))\n"
            '" 2>/dev/null && print_ok "ok" || print_warn "failed"\n')
    script = write(sandbox, "bigblock.sh", body)
    assert run(str(script)).returncode == EXIT_FINDINGS


# --- the fixture sandbox must not pollute the repo scan -------------------
def test_planted_fixture_is_excluded_from_a_whole_repo_scan(sandbox):
    """FIXTURE_ROOT lives inside the scan root. rmtree(ignore_errors=True) means an
    interrupted run leaves planted findings on disk; gitignoring hides them from git, not
    from rglob. Without the EXCLUDED_PARTS entry this reds the residue ratchet, the
    documented validation command, and the proposed CI line."""
    write(sandbox, "planted.sh", '#!/usr/bin/env bash\ngit stash apply 2>/dev/null || true\n')
    result = run(str(REPO))
    assert result.returncode in (EXIT_CLEAN, EXIT_FINDINGS), result.stderr
    assert str(FIXTURE_ROOT.name) not in result.stderr


# --- python rule: the two clauses added after the third review ------------
def test_python_sibling_handler_that_propagates_exempts(sandbox):
    """reflection.py:351 shape -- `except FileExistsError: pass` beside
    `except OSError: return None` is the idiomatic exist_ok emulation, not a swallow."""
    body = ("import os\n"
            "def ensure(p):\n"
            "    try:\n"
            "        os.mkdir(p, 0o700)\n"
            "    except FileExistsError:\n"
            "        pass\n"
            "    except OSError:\n"
            "        return None\n"
            "    return p\n")
    assert run(str(write(sandbox, "sibling.py", body))).returncode == EXIT_CLEAN


def test_python_unrelated_sibling_does_not_exempt(sandbox):
    """Pins the WIDTH of the sibling clause, not just its existence (M17 only removes it).

    An `except ValueError: return None` beside an `except OSError: pass` proves nothing
    about the OSError swallow -- the two catch disjoint types. Exempting on any propagating
    sibling regardless of type was a latent recall hole.
    """
    body = ("import pathlib\n"
            "def save(p, x):\n"
            "    try:\n"
            "        pathlib.Path(p).write_text(x)\n"
            "    except OSError:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        return None\n"
            "    return p\n")
    assert run(str(write(sandbox, "unrelated.py", body))).returncode == EXIT_FINDINGS


def test_python_bare_except_sibling_exempts(sandbox):
    """The other end of the same clause: a bare `except:` sibling really does catch a
    superset, so it legitimately exempts."""
    body = ("import pathlib\n"
            "def save(p, x):\n"
            "    try:\n"
            "        pathlib.Path(p).write_text(x)\n"
            "    except OSError:\n"
            "        pass\n"
            "    except:\n"
            "        raise\n"
            "    return p\n")
    assert run(str(write(sandbox, "bare.py", body))).returncode == EXIT_CLEAN


def test_here_string_is_not_mistaken_for_a_heredoc(sandbox):
    """MINOR 2. `HEREDOC` used `.search()`, so `foo <<<WORD` matched from the second `<`,
    set the delimiter to WORD, skipped 80 lines and produced a DIAGNOSTIC/exit 3 -- while
    both the docstring and the REVIEW_GUIDE claimed here-strings 'degrade to a silent skip'.
    The real finding below must still be reported, and no diagnostic may fire."""
    body = ('#!/usr/bin/env bash\n'
            'grep -q needle <<<WORD\n'
            'echo ok\n'
            'git stash apply 2>/dev/null || true\n')
    result = run(str(write(sandbox, "herestring.sh", body)))
    assert result.returncode == EXIT_FINDINGS, result.stderr
    assert "DIAGNOSTIC" not in result.stderr


def test_python_stderr_write_is_not_a_mutation(sandbox):
    """reflection.py:298 shape -- writing a diagnostic to a stream is not persistent state."""
    body = ("import sys\n"
            "def warn():\n"
            "    try:\n"
            "        sys.stderr.write('degraded\\n')\n"
            "    except (OSError, ValueError):\n"
            "        pass\n")
    assert run(str(write(sandbox, "warn.py", body))).returncode == EXIT_CLEAN

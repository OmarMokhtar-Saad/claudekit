"""Behavioral tests for the two day-one blockers, plus the newline bypass found while
fixing them.

  BUG 1  templates/python/config.env shipped BUILD_CMD="pip install -e ." - not in
         CommandValidator's allowlist - and pre-commit.sh EXECUTES build_cmd, so the
         blocking hook returned 1 on any staged src/*.py.
  BUG 2  check_secrets() stored its private-key patterns as bare literals, so
         .claude/hooks/pre-commit.sh (which the installer places in the user's repo,
         and which users do commit) matched itself, with no sanctioned way forward.
Scope: this module covers the two SHIPPED-CONFIG blockers only. The CommandValidator
parsing work (allowlist additions, eval/exec, env prefixes, newline segmentation) is a
separate project - .claude/plans/plan-validator-segmentation.md - and nothing here
depends on it landing.

Every assertion is an EXIT CODE, a validator return value, or a hook log line.

Fixtures use tempfile.mkdtemp(dir=REPO.parent), never $TMPDIR: ops-enforcement.sh:43
exempts /private/tmp/claude-*, /tmp/claude-* and /var/folders/* (what macOS $TMPDIR
resolves to), and a fixture placed there makes hooks exit 0 and assertions pass silently.

This module must not TRIP the live scanner either - a source line that merely looks like
an assignment is enough, since the control matches patterns, not secrets. Planted values
are assembled so that no `name = "` adjacency survives into the source text, and
TestSelfScanIsClean scans `tests/` with all 13 live patterns to keep that true.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
TEMPLATES = REPO / "templates"
PRE_COMMIT = REPO / ".claude" / "hooks" / "pre-commit.sh"

ENV = dict(
    os.environ,
    ECC_HOOK_PROFILE="minimal",
    PYTHONPATH=str(REPO / "src")
    + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
)

_ASSIGN_RE = re.compile(r'^(BUILD_CMD|TEST_CMD|LINT_CMD|COVERAGE_CMD)="(.*)"$')


def _template_commands():
    out = []
    for cfg in sorted(TEMPLATES.glob("*/config.env")):
        for line in cfg.read_text().splitlines():
            match = _ASSIGN_RE.match(line.strip())
            if match and match.group(2):
                out.append((cfg.parent.name, match.group(1),
                            match.group(2).replace('\\"', '"')))
    return out


TEMPLATE_COMMANDS = _template_commands()


def _check_command(command):
    return subprocess.run(
        [sys.executable, "-m", "claudekit.security", "check-command", command],
        cwd=str(REPO), capture_output=True, text=True, env=ENV, timeout=60,
    )


def _git(project, *args):
    return subprocess.run(["git", *args], cwd=str(project), capture_output=True,
                          text=True, env=ENV, timeout=60)


# The 18 commands still rejected by CommandValidator after this plan. Each needs a
# validator change (allowlist entries for the build tools; `bundle exec` matching the
# shell-builtin `exec` regex; `XDEBUG_MODE=coverage` parsed as a base command), which is
# scoped separately in .claude/plans/plan-validator-segmentation.md. They are xfail
# (strict=True), NOT skipped: when Plan B lands, each flips to XPASS and fails the suite,
# which is the signal to delete it from this set. A rejected command means
# pre-commit/pre-push/post-implement refuse to run that language's configured gate.
#
# _BASELINE_BLOCKED is the measured audit result and never changes. STILL_BLOCKED may only
# ever be a SUBSET of it, which makes this a membership ratchet rather than a headcount:
# a cardinality check (`len(...) <= 18`) would happily let a NEWLY blocked command take the
# place of one Plan B unblocks, which is the failure mode this guard exists to prevent.
_BASELINE_BLOCKED = frozenset({
    ("go", "LINT_CMD"),
    ("java", "BUILD_CMD"), ("java", "TEST_CMD"),
    ("java", "LINT_CMD"), ("java", "COVERAGE_CMD"),
    ("kotlin", "BUILD_CMD"), ("kotlin", "TEST_CMD"),
    ("kotlin", "LINT_CMD"), ("kotlin", "COVERAGE_CMD"),
    ("php", "LINT_CMD"), ("php", "COVERAGE_CMD"),
    ("ruby", "TEST_CMD"), ("ruby", "LINT_CMD"), ("ruby", "COVERAGE_CMD"),
    ("swift", "BUILD_CMD"), ("swift", "TEST_CMD"),
    ("swift", "LINT_CMD"), ("swift", "COVERAGE_CMD"),
})

# Entries leave this as Plan B lands. Nothing may ever join it. Plan B
# (plan-validator-segmentation.md) landed and unblocked all 18, re-measured by the
# 40-command audit below rather than assumed: the set is now empty, and
# test_the_blocked_set_is_not_silently_growing keeps it a subset of the baseline
# forever, so a future regression cannot re-enter it under an xfail marker.
STILL_BLOCKED = frozenset()


def _screen_params():
    params = []
    for lang, key, command in TEMPLATE_COMMANDS:
        marks = [pytest.mark.xfail(strict=True, reason=(
            f"{lang}/{key} needs a CommandValidator change - see "
            "plan-validator-segmentation.md. strict=True so landing that plan forces "
            "this entry out of STILL_BLOCKED rather than leaving a stale xfail."))
        ] if (lang, key) in STILL_BLOCKED else []
        params.append(pytest.param(lang, key, command, marks=marks,
                                   id=f"{lang}-{key}"))
    return params


class TestTemplateCommandsSurviveTheScreen:
    """pre-commit/pre-push/post-implement all refuse to run a command CommandValidator
    rejects, so a rejected template command is a dead gate at best and a blocked commit
    at worst. Binds the TEMPLATES, where commands actually ship - test_doctor_gate.py
    bound only this repo's own config.json, which install.sh overwrites."""

    def test_every_template_command_is_discovered(self):
        """Exactly 40 - the count in the plan-day-one-blockers.md audit table (10 templates
        x 4 keys, minus the 4 deliberately empty `generic` values). `>=` would let a parser
        regression silently drop commands, and a dropped command is an UNSCREENED command:
        narrowing _ASSIGN_RE to omit COVERAGE_CMD takes this from 40 to 31, which a `>= 30`
        bound accepts while ten coverage commands quietly stop being checked."""
        assert len(TEMPLATE_COMMANDS) == 40, (
            "expected the 40 non-empty commands in the plan-day-one-blockers.md audit "
            "table; got %d: %s" % (len(TEMPLATE_COMMANDS), TEMPLATE_COMMANDS))

    def test_the_blocked_set_is_not_silently_growing(self):
        """STILL_BLOCKED must stay a subset of the measured _BASELINE_BLOCKED audit result:
        entries may leave it as Plan B lands, and nothing may ever join it.

        A cardinality cap (`len(STILL_BLOCKED) <= 18`) does NOT express that. It accepts
        swapping ("go", "LINT_CMD") out for ("rust", "LINT_CMD") - same size, still a real
        template command - laundering a newly regressed command into the accepted-failure
        set, which is the exact move this guard exists to stop."""
        assert STILL_BLOCKED <= _BASELINE_BLOCKED, sorted(STILL_BLOCKED - _BASELINE_BLOCKED)
        # Independent staleness check: a baseline entry naming a command that no longer
        # exists (renamed key, deleted template) is stale and must be pruned.
        known = {(lang, key) for lang, key, _ in TEMPLATE_COMMANDS}
        assert _BASELINE_BLOCKED <= known, sorted(_BASELINE_BLOCKED - known)

    @pytest.mark.parametrize("language,key,command", _screen_params())
    def test_command_passes_the_validator(self, language, key, command):
        proc = _check_command(command)
        assert proc.returncode == 0, (
            f"{language}/{key}={command!r} rejected: {proc.stdout}{proc.stderr}")


class TestCheckCommandCliContract:
    """The hooks shell out to this entry point, so its exit code is its own contract."""

    def test_rejected_command_exits_nonzero(self):
        assert _check_command("rm -rf /").returncode != 0

    def test_accepted_command_exits_zero(self):
        proc = _check_command("python3 -m pytest tests/ -v")
        assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# BUG 1 end to end
# ---------------------------------------------------------------------------

CLAUDEKIT_SHIM = """\
#!/bin/sh
# pre-commit.sh:45 prefers a `claudekit` console script on PATH over the PYTHONPATH
# branch, so on a machine with claudekit pip-installed the hook would screen the
# INSTALLED validator instead of the source under test. This shim pins the branch to
# the working tree and records that it ran.
echo "shim" >> "$CK_SHIM_MARKER"
PYTHONPATH="$CK_SRC${PYTHONPATH:+:$PYTHONPATH}" exec "$CK_PYTHON" -m claudekit.security "$@"
"""


@pytest.fixture(scope="module")
def installed_project():
    """A real `install.sh --full` into a fresh git repo, outside $TMPDIR.

    pyproject.toml is written BEFORE install and --language python is passed: install.sh
    detect_language() (:141-165) returns `generic` without a Python marker, and the
    generic template ships EMPTY commands, so run_build() would return 0 at
    pre-commit.sh:203-206 before any screening - making every assertion below vacuous.
    """
    root = tempfile.mkdtemp(dir=str(REPO.parent), prefix="ck-dayone-")
    project = Path(root) / "project"
    project.mkdir()
    bin_dir = Path(root) / "bin"
    bin_dir.mkdir()
    marker = Path(root) / "shim-ran"
    shim = bin_dir / "claudekit"
    shim.write_text(CLAUDEKIT_SHIM)
    shim.chmod(0o755)

    env = dict(ENV, PATH=f"{bin_dir}{os.pathsep}{ENV['PATH']}",
               CK_SHIM_MARKER=str(marker), CK_SRC=str(REPO / "src"),
               CK_PYTHON=sys.executable)
    try:
        (project / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "0.0.1"\n')
        result = subprocess.run(
            ["bash", str(INSTALL), str(project), "--full", "--language", "python", "--yes"],
            capture_output=True, text=True, env=env, timeout=900,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (project / ".claude" / "hooks" / "pre-commit.sh").is_file()

        assert _git(project, "init").returncode == 0
        _git(project, "config", "user.email", "test@example.invalid")
        _git(project, "config", "user.name", "ClaudeKit Test")
        yield project, env, marker
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _run_pre_commit(installed):
    project, env, _ = installed
    return subprocess.run(
        ["bash", str(Path(project) / ".claude" / "hooks" / "pre-commit.sh")],
        cwd=str(project), capture_output=True, text=True, env=env, timeout=300,
    )


def _reset_index(installed):
    _git(installed[0], "reset")


def _installed_build_cmd(installed):
    config = json.loads(
        (Path(installed[0]) / ".claude" / "hooks" / "config.json").read_text())
    return config.get("project", {}).get("build_cmd", "")


def _hooks_log(installed):
    log = Path(installed[0]) / ".claude" / "hooks" / "hooks.log"
    return log.read_text() if log.is_file() else ""


class TestFreshInstallFirstCommit:
    @pytest.fixture(autouse=True)
    def _staged_source(self, installed_project):
        _reset_index(installed_project)
        source = Path(installed_project[0]) / "src" / "app.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("def main():\n    return 0\n")
        assert _git(installed_project[0], "add", "src/app.py").returncode == 0

    def test_installed_build_cmd_is_the_python_template_command(self, installed_project):
        """Anti-vacuity guard: an empty build_cmd would make the next tests pass for free.

        Asserts the SHAPE, not byte equality with templates/python/config.env: exact
        rendered escaping is install.sh's business and install.sh is owned by a parallel
        workstream. `compileall` still fails this the moment `pip install -e .` returns."""
        build = _installed_build_cmd(installed_project)
        assert build, "installed build_cmd is empty: every assertion here would be vacuous"
        assert "compileall" in build, build
        assert "pip install" not in build, build

    def test_source_commit_is_not_blocked(self, installed_project):
        proc = _run_pre_commit(installed_project)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_build_cmd_screen_actually_ran_against_the_source_under_test(
            self, installed_project):
        """Three-part, because each part alone is weak: the log must show the build ran,
        must NOT show the unscreened fallback (rc=127, which would execute build_cmd
        without screening), and the shim marker must exist, proving the validator that
        screened was this working tree rather than an installed wheel."""
        _run_pre_commit(installed_project)
        log = _hooks_log(installed_project)
        assert "running build:" in log, log[-2000:]
        assert "unscreened" not in log, log[-2000:]
        assert installed_project[2].is_file(), "claudekit shim never ran: wrong branch"

    def test_shipped_build_cmd_catches_a_syntax_error_in_a_flat_layout(
            self, installed_project):
        """The gate must be a gate. `compileall -q src` EXITS 0 on a project with no src/
        ("Can't list 'src'"), compiling nothing and reporting success - the silent-pass
        class this batch exists to remove."""
        build = _installed_build_cmd(installed_project)
        flat = tempfile.mkdtemp(dir=str(REPO.parent), prefix="ck-flat-")
        try:
            (Path(flat) / "pkg").mkdir()
            (Path(flat) / "pkg" / "bad.py").write_text("def f(:\n")
            proc = subprocess.run(build, shell=True, cwd=flat, capture_output=True,
                                  text=True, env=ENV, timeout=300)
            assert proc.returncode != 0, (
                f"{build!r} reported success on a syntax error: {proc.stdout}{proc.stderr}")
        finally:
            shutil.rmtree(flat, ignore_errors=True)



# ---------------------------------------------------------------------------
# FINDING 1: the value-bearing patterns could not fire
# ---------------------------------------------------------------------------

# `pre-commit.sh` never sources lib.sh (verified: no `source`/`.` line), so
# ERE_QUOTE_CLASS / ERE_NOT_QUOTE_CLASS are ALWAYS unset there and the `:-` defaults always
# apply - and those defaults were syntactically broken. `local q="${ERE_QUOTE_CLASS:-[\"']}"`
# puts a `'` inside a double-quoted ${:-} default, which opens a single-quote context; bash
# reports `bad substitution` and the two statements merge, leaving `nq` EMPTY. The shipped
# hook therefore ran `grep -iE 'api_key\s*[:=]\s*["']{8}'` - EIGHT CONSECUTIVE QUOTES -
# which no real credential matches. Measured against the unfixed hook: 0 of 7 planted
# secrets detected.
#
# These tests assert on the BUILT PATTERN STRING, not only on behaviour, because pattern
# construction is what broke. Behaviour tests alone would not say why.

VALUE_BEARING = ("api_key", "apikey", "api_secret", "password", "passwd",
                 "secret_key", "access_token")

# One entry since 2026-08-21, when `.codex/` was removed (DECISIONS.md 22).
# RENAMED from HOOK_MIRRORS deliberately: a one-element tuple still called
# "mirrors" would assert a mirror relationship that no longer exists, and the
# name shows up in every parametrisation id this class emits.
SECRET_PATTERN_HOOKS = (".claude/hooks/pre-commit.sh",)


def _built_patterns(hook_path):
    """Run the hook's own pattern-construction block and return (patterns, stderr).

    Extracted and executed rather than re-implemented: a copy of the construction logic
    would have been just as broken as the original and just as green."""
    text = pathlib.Path(hook_path).read_text()
    start = text.index('local q="${ERE_QUOTE_CLASS')
    end = text.index("\n    )\n", start) + len("\n    )\n")
    block = text[start:end].replace("local ", "")
    proc = subprocess.run(
        ["bash", "-c", block + '\nprintf "%s\\n" "${patterns[@]}"\n'],
        capture_output=True, text=True, timeout=30)
    return proc.stdout.splitlines(), proc.stderr


class TestSecretPatternConstruction:
    @pytest.mark.parametrize("hook", SECRET_PATTERN_HOOKS)
    def test_building_the_patterns_emits_no_shell_error(self, hook):
        """The shipped hook printed `bad substitution: no closing '}'` here. A blocking
        security hook must not build its ruleset out of a shell parse error."""
        _, stderr = _built_patterns(REPO / hook)
        assert stderr.strip() == "", stderr

    @pytest.mark.parametrize("hook", SECRET_PATTERN_HOOKS)
    @pytest.mark.parametrize("name", VALUE_BEARING)
    def test_value_pattern_requires_a_quote_then_non_quote_run(self, hook, name):
        """Each value-bearing pattern must be `<name> <sep> <quote> <non-quotes>{n}`. The
        defect collapsed it to `<name> <sep> {n}`, i.e. n consecutive quote characters."""
        patterns, _ = _built_patterns(REPO / hook)
        matching = [p for p in patterns if p.startswith(name + "\\s")]
        assert len(matching) == 1, f"{name}: expected one pattern, got {matching}"
        pattern = matching[0]
        assert "[^\"']" in pattern, (
            f"{hook} {name}: negated quote class missing, pattern cannot match a real "
            f"credential: {pattern!r}")
        assert "{" in pattern.split("[^\"']")[-1], f"{name}: no repetition count: {pattern!r}"

    @pytest.mark.parametrize("hook", SECRET_PATTERN_HOOKS)
    def test_private_key_pattern_still_requires_a_quote(self, hook):
        """The same defect left `private_key\\s*[:=]\\s*` with NO quote class - not dead
        but over-broad, firing on any `private_key =` line. Detection and precision are both
        part of the contract."""
        patterns, _ = _built_patterns(REPO / hook)
        matching = [p for p in patterns if p.startswith("private_key")]
        assert len(matching) == 1, matching
        assert matching[0].rstrip().endswith("[\"']"), matching[0]

# ---------------------------------------------------------------------------
# BUG 2
# ---------------------------------------------------------------------------

# The roots this suite is responsible for: everything install.sh ships, the .agents
# mirror, the code and plan artifacts, and - since 2026-08-21 - the committed review
# records and the user docs. `.codex` was a root here until it was removed the same
# day (DECISIONS.md 22); note that its removal alone would NOT have reddened this
# suite, because a root with no tracked files yields no files to scan. There is no
# missing-root guard, and adding one is a separate change - recorded in
# plan-remove-codex-mirror.md rather than left as a silent property.
#
# `review` could join once the three lines that matched the live api-key pattern were
# retyped: review/code-review.md:219, review/security-review.md:90, and
# review/tasks/003-fix-hook-bugs-and-fail-closed.md:49. Each was documentation quoting an
# example assignment, not a secret, so each was fixed by breaking the name/separator/quote
# adjacency the pattern needs - three adjacent markdown inline-code spans - leaving the
# finding text, severity and line references untouched. `docs` joined for FREE: it had
# zero matches against all 13 live patterns before this change and nothing in it was
# edited. Enumerated, not assumed: git ls-files over both roots x every expanded pattern.
#
# `.claude/plans` is deliberately included: plans and their ops configs ARE committed (18
# under .claude/plans/archive/), so an ops config whose `find` anchor carried a bare
# pattern literal would block the archiving commit with no sanctioned exit. The anchors in
# plan-day-one-blockers.ops.json are chosen to avoid that; this root is what enforces it.
SCAN_ROOTS = (".claude", "templates", ".agents", "tests", "scripts", "src",
              "review", "docs")


def _scanner_patterns():
    """Every live pattern, read out of the shipped hook rather than copied, so a newly
    added bare literal is caught instead of being invisible to this test."""
    text = PRE_COMMIT.read_text()
    block = re.search(r"local patterns=\((.*?)\n    \)", text, re.S)
    assert block, "pattern array not found in pre-commit.sh"
    out = []
    for line in block.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pattern = stripped.strip("'\"")
        # The hook builds quote classes from lib.sh at runtime; substitute them here.
        pattern = pattern.replace("${q}", "[\"']").replace("${nq}", "[^\"']")
        pattern = pattern.replace("\\\\s", "\\s")
        out.append(pattern)
    assert len(out) >= 13, out
    return out


# Mirrors pre-commit.sh:167-172 exactly. Derived from the hook rather than hand-copied so
# the test cannot become STRICTER than the control it mirrors - an independently written
# list would red on a binary extension the hook would never have flagged.
_SKIP_SUFFIX_RE = re.compile(
    r"\.(lock|png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|pdf)$|"
    r"(config\.json|config\.template|\.example)$")


def _committed_files(root, roots=SCAN_ROOTS):
    """Paths tracked in git, filtered to the roots this plan owns and to the files the
    hook itself would actually scan."""
    existing = [r for r in roots if (pathlib.Path(root) / r).exists()]
    if not existing:
        return []
    proc = subprocess.run(["git", "ls-files", "-z", "--", *existing],
                          cwd=str(root), capture_output=True, text=True, timeout=120)
    return [p for p in proc.stdout.split("\0") if p and not _hook_skips(p)]


def _hook_skips(path):
    return bool(_SKIP_SUFFIX_RE.search(path))


def _check_secrets_block():
    """The BODY of check_secrets(), so its skip clauses can be COUNTED and not merely
    matched. Fails loudly if the function is renamed rather than returning an empty
    string that would trivially count zero clauses."""
    text = PRE_COMMIT.read_text()
    block = re.search(r"^check_secrets\(\) \{\n(.*?)\n\}$", text, re.S | re.M)
    assert block, "check_secrets() not found in pre-commit.sh; update this mirror"
    return block.group(1)


def test_skip_mirror_matches_the_hook():
    """If the hook's skip list changes, this test must be updated with it.

    Two literal tokens catch a CHANGED clause but not an ADDED one: a third
    continue-guarded clause in check_secrets leaves both tokens present while making
    _SKIP_SUFFIX_RE STRICTER than the control it mirrors. That surfaces as a spurious red
    in test_no_committed_file_matches_a_live_pattern - a file the hook now skips is still
    scanned here - instead of failing where the fix belongs. So the clause COUNT is
    asserted too."""
    text = PRE_COMMIT.read_text()
    for token in ("lock|png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|pdf",
                  "config\\.json|config\\.template|\\.example"):
        assert token in text, f"pre-commit.sh skip list changed; update _SKIP_SUFFIX_RE ({token})"
    clauses = re.findall(r'\[\[ "\$file" =~', _check_secrets_block())
    assert len(clauses) == 2, (
        f"check_secrets() has {len(clauses)} skip clauses but _SKIP_SUFFIX_RE mirrors 2; "
        "add the new clause to _SKIP_SUFFIX_RE, or remove it from pre-commit.sh")


class TestSelfScanIsClean:
    SHIPPED = (
        ".claude/hooks/pre-commit.sh",
        ".claude/agents/opensource-sanitizer.md",
        ".claude/skills/insecure-defaults/SKILL.md",
    )

    def test_staging_shipped_claude_files_does_not_block(self, installed_project):
        _reset_index(installed_project)
        for rel in self.SHIPPED:
            assert (Path(installed_project[0]) / rel).is_file(), rel
            assert _git(installed_project[0], "add", "-f", rel).returncode == 0, rel
        proc = _run_pre_commit(installed_project)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    @pytest.mark.parametrize("pattern", _scanner_patterns())
    def test_no_committed_file_matches_a_live_pattern(self, pattern):
        """All 13 patterns, not just the private-key ones: an earlier revision's test
        module itself matched the api_key pattern and nothing caught it.

        Enumerates the INDEX (`git ls-files`), not the filesystem, which is what this
        test's name has always claimed. Walking the tree made it fail on
        `.claude/hooks/hooks.log` - untracked and gitignored - which had recorded an
        earlier run's own scanner test. Any log that records command text will match a
        secret pattern the moment someone tests the scanner, so a filesystem walk
        self-poisons indefinitely."""
        files = _committed_files(REPO)
        assert files, "git ls-files returned nothing: this scan would pass vacuously"
        hits = []
        for chunk in (files[i:i + 400] for i in range(0, len(files), 400)):
            proc = subprocess.run(["grep", "-ilE", pattern, "--", *chunk],
                                  cwd=str(REPO), capture_output=True, text=True, timeout=120)
            hits.extend(line for line in proc.stdout.splitlines() if line.strip())
        assert not hits, f"{pattern!r} matches committed files: {hits}"

    def test_gitignored_file_cannot_poison_the_scan(self):
        """Regression for the above: a gitignored file holding a pattern must be invisible
        to the enumeration. Runs against a purpose-built repo rather than mutating this
        one, and outside $TMPDIR like every other fixture here."""
        root = tempfile.mkdtemp(dir=str(REPO.parent), prefix="ck-ignored-")
        try:
            repo = pathlib.Path(root)
            subprocess.run(["git", "init", "-q", "."], cwd=root, check=True, timeout=60)
            (repo / ".gitignore").write_text("poison.log\n")
            (repo / "tracked.md").write_text("nothing to see\n")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True, timeout=60)
            (repo / "poison.log").write_text(
                "-----BEGIN " + "RSA PRIVATE" + " KEY-----\n")
            assert subprocess.run(["git", "check-ignore", "-q", "poison.log"],
                                  cwd=root, timeout=60).returncode == 0

            listed = _committed_files(repo, roots=(".",))
            assert "poison.log" not in listed, listed
            assert any(f.endswith("tracked.md") for f in listed), listed
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestRealSecretIsStillCaught:
    """The test that matters. An exclusion-based fix for BUG 2 (skip pre-commit.sh, skip a
    marked region, skip markdown) would leave TestSelfScanIsClean green while creating a
    named hiding place. The first two cases fail against every such fix.

    Scope, stated rather than implied: this does NOT prove the scanner has no hiding
    places. pre-commit.sh:167-172 already skips *.lock, images/fonts/pdf and any path
    ending config.json / config.template / .example. That predates this plan and is
    unchanged by it; the xfail below binds it so it stays visible.

    Each case restores the file it edited: the fixture is module-scoped, so an unrestored
    planted secret would make TestSelfScanIsClean pass or fail on class ordering."""

    def _plant(self, installed, rel, addition):
        target = Path(installed[0]) / rel
        original = target.read_text()
        try:
            target.write_text(original + addition)
            _reset_index(installed)
            assert _git(installed[0], "add", "-f", rel).returncode == 0
            return _run_pre_commit(installed)
        finally:
            target.write_text(original)
            _reset_index(installed)

    def test_real_private_key_in_the_hook_itself_is_caught(self, installed_project):
        header = "-----BEGIN " + "RSA PRIVATE" + " KEY-----"
        proc = self._plant(installed_project, ".claude/hooks/pre-commit.sh",
                           "\n# " + header + "\n# MIIEowIBAAKCAQEAxxxxx\n")
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 1, combined
        assert "pre-commit.sh" in combined, combined

    # Three of the seven value-bearing patterns, so the CLASS is covered rather than one
    # instance. All seven were dead in the shipped hook (measured: 0 of 7 planted secrets
    # detected); `api_key` and `access_token` carry the {8} run, `password` the {4} run, so
    # both repetition variants are exercised. Names and values are assembled at runtime so
    # no `name = "value"` adjacency appears in THIS file's source - the scanner matches
    # patterns, not secrets, and tests/ is itself scanned above.
    @pytest.mark.parametrize("name,value", [
        ("api_key", "sk-live-0123456789abcdef"),
        ("password", "hunter2xyz"),
        ("access_token", "ghp_abcdefghijklmnop"),
    ])
    def test_real_credential_in_a_shipped_markdown_file_is_caught(
            self, installed_project, name, value):
        literal = name + " = " + chr(34) + value + chr(34)
        proc = self._plant(installed_project,
                           ".claude/skills/insecure-defaults/SKILL.md",
                           "\n" + literal + "\n")
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 1, (
            f"{name} credential was NOT detected - the value-bearing patterns are dead "
            f"again: {combined}")
        assert "SKILL.md" in combined, combined

    @pytest.mark.xfail(strict=True, reason=(
        "KNOWN HOLE, pre-existing and deliberately not fixed here: pre-commit.sh:170 "
        "skips any path ending config.json, so a real key committed to "
        ".claude/hooks/config.json ships silently. Bound as xfail(strict=True) so it "
        "cannot be quietly closed or quietly forgotten - closing it flips this to XPASS "
        "and fails the suite, which is the signal to delete this marker."))
    def test_real_private_key_in_config_json_is_caught(self, installed_project):
        header = "-----BEGIN " + "RSA PRIVATE" + " KEY-----"
        proc = self._plant(installed_project, ".claude/hooks/config.json",
                           "\n# " + header + "\n")
        assert proc.returncode == 1, proc.stdout + proc.stderr

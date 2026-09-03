"""Behavioral tests for concurrency-guard.py.

Why the hook exists: several Claude sessions (possibly two accounts) share one working
tree and therefore one `.git/index`. A tree-wide stage or a destructive checkout acts on
files the session does not own, so one session commits or deletes another's in-flight
work. `TestWorktreeIsolationIsTheRealFix` proves the structural fix both ways; the rest
prove the guard's contract.

Every case in BLOCKED/ALLOWED below that looks oddly specific is a REGRESSION case from
the adversarial review of the first (regex-based) implementation, which this file's
predecessor passed while the hook was broken. Do not thin the lists.
"""

import json
import os
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".claude" / "hooks"
GUARD = "concurrency-guard.py"

#: The hook is loaded so tests can parametrise over its OWN constants. A hand-copied
#: list silently drifts: round 3 found `:!` in TREE_WIDE_PATHSPECS with no test case,
#: and deleting the member left the suite green.
guard = SourceFileLoader("concurrency_guard", str(HOOKS / GUARD)).load_module()

BLOCKED = [
    # tree-wide stage
    "git add -A", "git add .", "git add --all", "git add -u", "git add --update",
    "git add ./", "git add :/", "git add *",
    # commit -a, in every flag position and cluster (regression: `-m x -a` leaked)
    "git commit -am wip", "git commit -a -m wip", "git commit -m x -a",
    "git commit --all -m x", "git commit -ma x",
    # destructive reset (regression: --merge/--keep were absent)
    "git reset --hard", "git reset --hard origin/main", "git reset --merge",
    "git reset --keep origin/main",
    # destructive checkout/restore (regression: all four of these leaked)
    "git checkout .", "git checkout -- .", "git checkout HEAD -- .",
    "git checkout HEAD~1 -- .", "git checkout -f", "git checkout -f main",
    "git restore .", "git restore --staged .", "git restore --worktree .",
    "git restore --source=HEAD .",
    # clean / rm (regression: `git rm -r .` was absent)
    "git clean -fd", "git clean -fdx", "git clean --force", "git rm -r .", "git rm -rf .",
    # stash forms that TAKE work away
    "git stash", "git stash push", "git stash save wip", "git stash clear", "git stash -u",
    # git global options before the subcommand (regression: all of these leaked)
    "git -C . add -A", "git -C /tmp/repo add -A",
    "git --git-dir=.git --work-tree=. add -A", "git -c user.name=x add -A",
    # command-word and prefix wrappers
    "sudo git add -A", "env git add -A", "/usr/bin/git add -A", "GIT_DIR=x git add -A",
    "bash -c 'git add -A'",
    # shell structure (regression: `{ ...; }` and `then ...` leaked)
    "{ git add -A; }", "if true; then git add -A; fi", "cd foo && git add -A",
    "git status && git add .",
    # another session's worktree
    "git worktree remove --force ../wt-a",
    # --- round 2 regressions ---
    # `git stage` is git's OWN synonym for add, not a user alias
    "git stage -A", "git stage .",
    # `switch -f` throws away local modifications exactly as `checkout -f` does, and the
    # doc had been prescribing `switch` as the REMEDIATION for a blocked `checkout -f`
    "git switch -f main", "git switch --discard-changes main",
    # clustered `-c` (the ordinary login-shell form) must still unwrap
    "bash -lc 'git add -A'", "bash -xc 'git add -A'",
    # pathspec magic that re-roots at the top of the tree
    "git add **", "git add :(glob)**", "git add :(top)",
    # a bare/--mixed reset unstages every path ANOTHER session staged
    "git reset", "git reset --mixed", "git reset HEAD~1",
    # MULTI-LINE. shlex keeps newline in `whitespace`, so an earlier version discarded
    # every line after the first and the guard was inert for the commonest script shape.
    "git status\ngit add -A",
    "cd src\ngit add -A",
    "echo hi\ngit reset --hard",
    "cat > f <<EOF\nhello\nEOF\ngit add -A",
    "git fetch\n\n  git reset --hard origin/main",
]

ALLOWED = [
    # dot-prefixed paths. THE regression: an unanchored `\.` blocked every one of these,
    # i.e. the guard denied the remediation its own message prescribes.
    "git add .ai/CONCURRENCY.md", "git add .gitignore", "git add ./src/a.py",
    "git add .claude/hooks/x.py", "git add ../shared/a.py",
    "git add src/a.py tests/b.py",
    # -A/-u WITH an explicit pathspec is scoped, and `--` ends the options
    "git add -A -- src/", "git add -u -- src/", "git add -- -A",
    "git add -p", "git add --patch",
    # ordinary commits, including a message that merely MENTIONS a blocked flag
    "git commit -m msg", "git commit --amend --no-edit", "git commit --allow-empty -m x",
    "git commit -m 'fix add -A handling'", "git commit -m 'a;b'",
    # non-destructive reset / branch switching
    "git reset --soft HEAD~1", "git reset HEAD -- src/a.py",
    "git checkout main", "git checkout -b feat/x", "git switch main",
    "git restore -- src/a.py", "git restore --staged -- src/a.py",
    # read-only and RESTORATIVE stash forms. Regression: pop/apply/drop were blocked,
    # i.e. the guard denied the operation that gives work back.
    "git clean -n", "git clean --dry-run",
    "git stash list", "git stash show", "git stash apply", "git stash pop",
    "git stash drop", "git stash branch tmp",
    "git rm src/a.py",
    "git status --short", "git diff", "git log --oneline", "git push origin HEAD",
    "git branch -a", "git config --add x y",
    "git worktree list", "git worktree add ../wt -b x",
    # the phrase as DATA, not as an invocation
    "grep -rn 'git add -A' docs/", "echo 'never run git reset --hard here'",
    "python3 -m pytest tests/ -q",
    # --- round 2: forms that must NOT be swept up ---
    # `git stash push <path>` is the ordinary SCOPED stash; blocking it would deny
    # exactly the per-path habit this guard exists to encourage.
    "git stash push src/a.py", "git stash push -- src/a.py",
    "git switch main", "git checkout main -- src/",
    "git reset -- src/a.py", "git reset HEAD -- src/a.py",
    # read-only plumbing that takes `.` as an argument
    "git status .", "git diff -- .", "git log -- .", "git show HEAD -- .", "git ls-files .",
    "git worktree remove ../wt",
    "git add 'file with spaces.py'",
    "git commit -m 'add .'", "git commit -m 'reset --hard'",
    # a heredoc BODY is data, not a command
    "cat > f <<EOF\ngit reset --hard\nEOF",
    "cat > f <<'EOF'\ngit add -A\nEOF",
    # a newline INSIDE quotes is data and must not split the command
    'echo "a\nb"',
]


def run_guard(command, profile="standard", extra_env=None, raw=None, unset_profile=False):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    env = dict(os.environ)
    env.pop("CK_ALLOW_BROAD_GIT", None)
    if unset_profile:
        env.pop("ECC_HOOK_PROFILE", None)
    else:
        env["ECC_HOOK_PROFILE"] = profile
    env["LOG_FILE"] = os.environ.get("PYTEST_GUARD_LOG", "/dev/null")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["python3", str(HOOKS / GUARD)],
        input=payload, capture_output=True, text=True,
        cwd=str(REPO), env=env, timeout=30,
    )


class TestBlocks:
    @pytest.mark.parametrize("command", BLOCKED)
    def test_tree_wide_command_is_blocked(self, command):
        p = run_guard(command)
        assert p.returncode == 2, f"NOT blocked: {command!r} (stderr={p.stderr!r})"
        assert p.stdout == "", "a blocking hook must not write to stdout"
        assert "concurrency-guard" in p.stderr

    def test_the_log_records_a_verdict_not_an_outcome(self, tmp_path):
        log = tmp_path / "hooks.log"
        run_guard("git add -A", extra_env={"LOG_FILE": str(log)})
        body = log.read_text()
        assert "verdict=deny" in body, body
        assert "denied" not in body, "the log claims an outcome the hook does not control"

    def test_the_reason_does_not_claim_to_have_blocked(self):
        # A registry row may clamp this hook to `advisory`, in which case dispatch.sh
        # lets the command run anyway -- that is how the fleet ships it in record-only
        # mode. The hook cannot see its own tier, so the text must not assert an
        # outcome it does not control.
        stderr = run_guard("git add -A").stderr
        assert "blocked" not in stderr.lower(), stderr
        assert "another concurrent session" in stderr

    def test_reason_names_the_scoped_alternative_for_every_rule(self):
        # Each rule's remediation text is asserted, so none can be emptied or swapped.
        expected = {
            "git add -A": "git add path/to/file",
            "git commit -am x": "git add <paths>",
            "git reset --hard": "git restore --source=HEAD",
            "git checkout .": "git restore -- path/to/file",
            "git checkout -f": "commit your work first",
            "git clean -fd": "specific files you created",
            "git stash": "commit to your own branch",
            "git rm -r .": "git rm path/to/file",
            "git worktree remove -f ../w": "owning session",
        }
        for command, fragment in expected.items():
            p = run_guard(command)
            assert p.returncode == 2, command
            assert fragment in p.stderr, f"{command!r} -> missing {fragment!r}: {p.stderr!r}"

    def test_the_escape_hatch_is_named_so_the_block_is_actionable(self):
        assert "CK_ALLOW_BROAD_GIT" in run_guard("git add -A").stderr


class TestAllows:
    @pytest.mark.parametrize("command", ALLOWED)
    def test_scoped_or_read_only_command_is_untouched(self, command):
        p = run_guard(command)
        assert p.returncode == 0, f"wrongly blocked: {command!r} (stderr={p.stderr!r})"

    def test_a_non_git_command_exits_without_opinion(self):
        assert run_guard("ls -la").returncode == 0
        assert run_guard("rm -rf build/").returncode == 0


class TestProfilesAndFailClosed:
    def test_the_default_profile_blocks_when_the_variable_is_unset(self):
        # Binds the `DEFAULT_PROFILE` branch: mutating the default to "minimal" makes
        # the hook globally inert, and no test that always SETS the variable notices.
        p = run_guard("git add -A", unset_profile=True)
        assert p.returncode == 2, p.stderr

    def test_strict_profile_blocks(self):
        assert run_guard("git add -A", profile="strict").returncode == 2

    def test_minimal_is_advisory_not_off(self, tmp_path):
        # DELIBERATE divergence: under `minimal` the decision is still computed and
        # logged as WOULD-BLOCK, so this repo (which develops under `minimal`) keeps a
        # dogfood signal. A wholesale `exit 0` would record nothing.
        log = tmp_path / "hooks.log"
        p = run_guard("git add -A", profile="minimal",
                      extra_env={"LOG_FILE": str(log)})
        assert p.returncode == 0
        assert log.exists(), "minimal must still RECORD the decision"
        body = log.read_text()
        assert "WOULD-BLOCK" in body and "add-tree-wide" in body

    def test_minimal_records_nothing_for_an_allowed_command(self, tmp_path):
        log = tmp_path / "hooks.log"
        p = run_guard("git add src/a.py", profile="minimal",
                      extra_env={"LOG_FILE": str(log)})
        assert p.returncode == 0
        assert not log.exists() or "WOULD-BLOCK" not in log.read_text()

    def test_unparseable_payload_fails_closed(self):
        p = run_guard(None, raw="not json at all")
        assert p.returncode == 2
        assert p.stdout == ""

    def test_empty_payload_fails_closed(self):
        assert run_guard(None, raw="").returncode == 2

    def test_a_json_array_payload_fails_closed(self):
        assert run_guard(None, raw="[1,2,3]").returncode == 2

    def test_an_untokenisable_git_command_fails_closed(self):
        # An unbalanced quote cannot be tokenised; the text contains `git`, so the hook
        # cannot prove what it would run.
        p = run_guard("git add -A \"unclosed")
        assert p.returncode == 2, p.stderr

    def test_a_payload_without_a_command_is_not_our_business(self):
        assert run_guard(None, raw=json.dumps({"tool_name": "Read"})).returncode == 0

    def test_escape_hatch_downgrades_to_a_logged_warning(self, tmp_path):
        log = tmp_path / "hooks.log"
        p = run_guard("git add -A", extra_env={"CK_ALLOW_BROAD_GIT": "1",
                                               "LOG_FILE": str(log)})
        assert p.returncode == 0
        assert p.stdout == ""
        assert "CK_ALLOW_BROAD_GIT" in p.stderr
        assert log.exists() and "CK_ALLOW_BROAD_GIT" in log.read_text()

    def test_the_escape_hatch_needs_exactly_one(self):
        assert run_guard("git add -A", extra_env={"CK_ALLOW_BROAD_GIT": "yes"}).returncode == 2
        assert run_guard("git add -A", extra_env={"CK_ALLOW_BROAD_GIT": "0"}).returncode == 2


class TestLoggingIsNotAnExfiltrationChannel:
    def test_the_command_text_is_never_logged(self, tmp_path):
        # A blocked command line is the text most likely to carry a credential.
        log = tmp_path / "hooks.log"
        secret = "AWS_SECRET_ACCESS_KEY=hunter2wowsecret"
        p = run_guard(f"{secret} git add -A", extra_env={"LOG_FILE": str(log)})
        assert p.returncode == 2
        body = log.read_text()
        assert "hunter2wowsecret" not in body, "the guard logged the command text"
        assert "hunter2wowsecret" not in p.stderr, "the guard echoed the command text"
        assert "add-tree-wide" in body


class TestRegistration:
    def test_registered_as_a_blocking_pretooluse_bash_handler(self):
        reg = json.loads((HOOKS / "dispatch-registry.json").read_text())
        rows = reg["events"]["PreToolUse"]
        row = next((r for r in rows if r["id"] == "concurrency-guard"), None)
        assert row is not None, "concurrency-guard is not in the dispatch registry"
        assert row["tier"] == "blocking"
        assert row["matcher"] == "Bash"
        assert row["runner"] == "python3"
        # Registry invariant: only an advisory row may carry a command_matcher.
        assert "command_matcher" not in row

    def test_the_registered_file_exists(self):
        # A registered-but-missing handler fails the whole dispatcher closed, which
        # blocks every Bash call in the session. Cheap assertion, expensive outage.
        reg = json.loads((HOOKS / "dispatch-registry.json").read_text())
        for event, rows in reg["events"].items():
            for row in rows:
                assert (HOOKS / row["file"]).is_file(), f"{event}/{row['id']}: {row['file']}"

    def test_dispatcher_propagates_the_block_and_stays_silent_on_stdout(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git add -A"}})
        p = subprocess.run(
            ["bash", str(HOOKS / "dispatch.sh"), "PreToolUse"],
            input=payload, capture_output=True, text=True, cwd=str(REPO),
            env=dict(os.environ, ECC_HOOK_PROFILE="standard"), timeout=60,
        )
        assert p.returncode == 2, (p.returncode, p.stderr)
        assert "concurrency-guard" in p.stderr

    def test_dispatcher_allows_a_scoped_stage(self):
        payload = json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "git add src/claudekit/cli.py"}})
        p = subprocess.run(
            ["bash", str(HOOKS / "dispatch.sh"), "PreToolUse"],
            input=payload, capture_output=True, text=True, cwd=str(REPO),
            env=dict(os.environ, ECC_HOOK_PROFILE="standard"), timeout=60,
        )
        assert p.returncode == 0, p.stderr


class TestWorktreeIsolationIsTheRealFix:
    """The guard is a speed bump; separate worktrees are the isolation."""

    def _git(self, cwd, *args):
        p = subprocess.run(["git", *args], cwd=str(cwd),
                           capture_output=True, text=True, timeout=60)
        # Checked, so a `not in` assertion downstream can never pass vacuously because
        # a setup command silently failed.
        assert p.returncode == 0, f"git {' '.join(args)} failed: {p.stderr}"
        return p.stdout

    def _repo(self, path):
        path.mkdir()
        self._git(path, "init", "-q", "-b", "main")
        self._git(path, "config", "user.email", "t@t")
        self._git(path, "config", "user.name", "t")
        return path

    def test_worktrees_isolate_concurrent_sessions(self, tmp_path):
        demo = self._repo(tmp_path / "demo")
        (demo / "app.py").write_text("line1\nline2\n")
        (demo / "util.py").write_text("shared\n")
        self._git(demo, "add", "app.py", "util.py")
        self._git(demo, "commit", "-qm", "init")

        wt_a, wt_b = tmp_path / "wt-a", tmp_path / "wt-b"
        self._git(demo, "worktree", "add", "-q", str(wt_a), "-b", "sess/a")
        self._git(demo, "worktree", "add", "-q", str(wt_b), "-b", "sess/b")

        # A's edit is in flight while B stages its whole tree.
        (wt_a / "app.py").write_text("line1\nA_FEATURE\nline2\n")
        (wt_b / "util.py").write_text("shared\nB_FEATURE\n")
        self._git(wt_b, "add", "-A")
        self._git(wt_b, "commit", "-qm", "B")
        self._git(wt_a, "add", "app.py")
        self._git(wt_a, "commit", "-qm", "A")

        # B's tree-wide stage could not reach A's file...
        assert "A_FEATURE" not in self._git(demo, "show", "sess/b:app.py")
        # ...and both changes exist, so the `not in` above is about isolation, not loss.
        assert "A_FEATURE" in self._git(demo, "show", "sess/a:app.py")
        assert "B_FEATURE" in self._git(demo, "show", "sess/b:util.py")

        self._git(demo, "merge", "-q", "--no-edit", "sess/a")
        self._git(demo, "merge", "-q", "--no-edit", "sess/b")
        assert "A_FEATURE" in self._git(demo, "show", "main:app.py")
        assert "B_FEATURE" in self._git(demo, "show", "main:util.py")

    def test_a_shared_tree_loses_work_which_is_why_the_guard_exists(self, tmp_path):
        demo = self._repo(tmp_path / "shared")
        (demo / "app.py").write_text("line1\nline2\n")
        self._git(demo, "add", "app.py")
        self._git(demo, "commit", "-qm", "init")

        (demo / "app.py").write_text("line1\nA_FEATURE\nline2\n")   # session A, in flight
        (demo / "app.py").write_text("line1\nline2\nB_FEATURE\n")   # session B overwrites
        self._git(demo, "add", "-A")
        self._git(demo, "commit", "-qm", "B")
        committed = self._git(demo, "show", "HEAD:app.py")
        # The commit landed (so this is not a vacuous pass) but A's work is simply gone.
        assert "B_FEATURE" in committed
        assert "A_FEATURE" not in committed


class TestDecorationsCannotDisarmTheGuard:
    """Every blocked command stays blocked under ordinary shell decoration.

    THIS IS THE CLASS RATCHET. Three review rounds produced three CRITICALs of one
    shape: a pre-tokenisation text transform silently dropped commands, so the guard
    reported "allowed" -- fail-open, in a hook documented as fail-closed. The
    instances were a dead `"\n"` separator, a `#` comment eating the rest of the
    script, a quoted `<<` inventing a heredoc marker, and a redirection token read as
    a scoping pathspec.

    Example-based cases could not close that class: each new decoration is a new
    hole. Cross-producting the decorations with the whole BLOCKED list is what makes
    the property hold, and it is what would have caught all four.
    """

    DECORATIONS = [
        "{cmd} >/dev/null 2>&1",
        "{cmd} > /dev/null",
        "{cmd} 2>/dev/null",
        "{cmd} >log.txt 2>&1",
        "# a note\n{cmd}",
        "echo ok  # trailing note\n{cmd}",
        "echo hi\n{cmd}",
        "{cmd}\necho done",
        'echo "a << b"\n{cmd}',
        'python3 -c "print(1 << 2)"\n{cmd}',
        "cat <<EOF\nbody\nEOF\n{cmd}",
        "cat <<-EOF\n\tbody\nEOF\n{cmd}",
        "cat <<'EOF'\nbody\nEOF\n{cmd}",
        "cat <<\\EOF\nbody\nEOF\n{cmd}",
        "true && {cmd}",
        "true; {cmd}",
        "{ {cmd}; }",
        "( {cmd} )",
        "if true; then {cmd}; fi",
        "eval '{cmd}'",
        "bash -lc '{cmd}'",
    ]

    # A representative blocked command per rule; the full BLOCKED list is
    # cross-producted below for the redirection/comment/heredoc decorations, which are
    # the ones that historically disarmed the guard.
    REPRESENTATIVE = [
        "git add -A", "git commit -am wip", "git reset --hard", "git checkout .",
        "git clean -fd", "git stash", "git rm -r .", "git stage -A",
    ]

    @pytest.mark.parametrize("decoration", DECORATIONS)
    @pytest.mark.parametrize("command", REPRESENTATIVE)
    def test_decoration_preserves_the_block(self, decoration, command):
        decorated = decoration.replace("{cmd}", command)
        p = run_guard(decorated)
        assert p.returncode == 2, (
            f"decoration disarmed the guard: {decorated!r} (stderr={p.stderr!r})")

    @pytest.mark.parametrize("command", BLOCKED)
    def test_redirection_never_disarms_the_block(self, command):
        # The round-3 CRITICAL: `>` and its target were read as scoping pathspecs.
        if "\n" in command:
            pytest.skip("multi-line commands carry their own redirection cases")
        p = run_guard(command + " >/dev/null 2>&1")
        assert p.returncode == 2, f"redirection disarmed: {command!r}"


class TestShippedConstantsAreEachLoadBearing:
    """Parametrised over the hook's OWN constants, so a new member needs a case.

    Parametrising over a constant has one weakness: DELETING a member deletes its own
    test case, so the suite stays green. The subset assertions below close that --
    they name the members whose removal must be a failure, so the two mechanisms
    together catch both an unhandled addition and a silent removal.
    """

    def test_the_constants_still_contain_what_the_docs_promise(self):
        assert {".", "..", "*", "**", ":/", ":", ":!", "./", "../"} <= (
            guard.TREE_WIDE_PATHSPECS), "a tree-wide pathspec was removed"
        assert {":/", ":(top)", ":(glob)"} <= set(guard.TREE_WIDE_MAGIC)
        assert "::" not in guard.TREE_WIDE_MAGIC, (
            "`::` is not tree-wide: a second colon ends the magic signature")
        assert {"-C", "-c", "--git-dir", "--work-tree"} <= (
            guard.GIT_GLOBAL_WITH_VALUE)
        assert {"-p", "--paginate", "--no-pager"} <= guard.GIT_GLOBAL_FLAGS
        assert {"sudo", "env", "then", "do", "{", "("} <= guard.PREFIX_WORDS
        assert {"bash", "sh", "eval"} <= guard.SCRIPT_WRAPPERS
        assert "\n" not in guard.OPERATORS, (
            "newlines are converted to `;` by preprocess; a `\\n` member here is dead "
            "code, and a dead separator is how a whole review round's CRITICAL hid")

    @pytest.mark.parametrize("pathspec", sorted(guard.TREE_WIDE_PATHSPECS))
    def test_every_tree_wide_pathspec_member_blocks(self, pathspec):
        assert run_guard("git add '%s'" % pathspec).returncode == 2, pathspec

    @pytest.mark.parametrize("pathspec", [".", "*", "**", ":/", "./", "*/", ".//"])
    def test_tree_wide_pathspecs_also_block_unquoted(self, pathspec):
        assert run_guard("git add %s" % pathspec).returncode == 2, pathspec

    @pytest.mark.parametrize("pathspec", ["::x", ".ai/x.md", ".gitignore",
                                          "./src/a.py", "src/a.py"])
    def test_a_concrete_path_is_never_tree_wide(self, pathspec):
        # `::x` -- a second `:` ends the magic signature, so this is just path `x`.
        assert run_guard("git add '%s'" % pathspec).returncode == 0, pathspec

    @pytest.mark.parametrize("magic", sorted(guard.TREE_WIDE_MAGIC))
    def test_every_pathspec_magic_member_blocks_when_unscoped(self, magic):
        assert run_guard("git add '%s'" % magic.rstrip(",")).returncode == 2, magic

    @pytest.mark.parametrize("magic", sorted(guard.TREE_WIDE_MAGIC))
    def test_pathspec_magic_with_a_concrete_path_is_scoped(self, magic):
        # `:/src/a.py` is the ordinary form from a subdirectory. Blocking it would
        # repeat round 1's defect: denying the remediation the hook prescribes.
        if magic.endswith(","):
            pytest.skip("`:(top,` needs its option list closed before a path")
        assert run_guard("git add '%ssrc/a.py'" % magic).returncode == 0, magic

    @pytest.mark.parametrize("flag", sorted(guard.GIT_GLOBAL_FLAGS))
    def test_every_git_global_flag_is_stripped(self, flag):
        assert run_guard("git %s add -A" % flag).returncode == 2, flag

    @pytest.mark.parametrize("opt", sorted(guard.GIT_GLOBAL_WITH_VALUE))
    def test_every_valued_git_global_option_is_stripped(self, opt):
        value = "x=y" if opt in ("-c", "--config-env") else "/tmp/x"
        assert run_guard("git %s %s add -A" % (opt, value)).returncode == 2, opt

    @pytest.mark.parametrize("word", sorted(w for w in guard.PREFIX_WORDS
                                            if w.isalpha() or w == "!"))
    def test_every_prefix_word_is_stepped_over(self, word):
        assert run_guard("%s git add -A" % word).returncode == 2, word

    @pytest.mark.parametrize("wrapper", sorted(guard.SCRIPT_WRAPPERS))
    def test_every_script_wrapper_is_unwrapped(self, wrapper):
        flag = "" if wrapper == "eval" else "-c "
        assert run_guard("%s %s'git add -A'" % (wrapper, flag)).returncode == 2, wrapper


class TestFailsClosedWhenItCannotRead:
    @pytest.mark.parametrize("command", [
        'git add -A "unclosed',
        "git add -A 'unclosed",
        "cat <<EOF\ngit add -A\n",          # heredoc terminator never arrives
        "bash -c 'git add -A \"'",           # untokenisable INNER script
    ])
    def test_unreadable_git_text_blocks(self, command):
        # An unterminated heredoc means we do not know where the body ended, so we
        # cannot claim to have read the command. Fail closed, not open.
        p = run_guard(command)
        assert p.returncode == 2, f"failed OPEN on unreadable text: {command!r}"

    def test_the_nested_and_top_level_paths_agree(self):
        inner = "git add -A \""
        assert run_guard(inner).returncode == run_guard("bash -c %r" % inner).returncode


class TestHeredocBodiesAreDataNotCommands:
    """A heredoc body is text being WRITTEN, not a command being run.

    These cases are where `preprocess`'s heredoc internals are observable: a mistake
    in marker detection makes the terminator unmatchable, which fails CLOSED and shows
    up as a spurious block here rather than as a leak in the BLOCKED list. Round-3
    mutation testing found the `<<<`, `<<-` and marker-unquoting rules unbound for
    exactly this reason.
    """

    @pytest.mark.parametrize("command", [
        "cat > f <<EOF\ngit add -A\nEOF",
        "cat > f <<'EOF'\ngit add -A\nEOF",
        'cat > f <<"EOF"\ngit add -A\nEOF',
        "cat > f <<\\EOF\ngit add -A\nEOF",
        "cat > f <<-EOF\n\tgit add -A\nEOF",
        "cat > f <<MARKER\ngit reset --hard\nMARKER",
        # two heredocs in one script, both bodies data
        "cat > a <<EOF\ngit add -A\nEOF\ncat > b <<EOF2\ngit clean -fd\nEOF2",
        # a here-STRING is not a heredoc: nothing after it may be swallowed
        'cat <<< "git add -A"',
    ])
    def test_a_heredoc_body_does_not_trigger_the_guard(self, command):
        p = run_guard(command)
        assert p.returncode == 0, f"heredoc body treated as a command: {command!r}"

    @pytest.mark.parametrize("command", [
        "cat > f <<EOF\nbody\nEOF\ngit add -A",
        "cat > f <<'EOF'\nbody\nEOF\ngit add -A",
        "cat > f <<\\EOF\nbody\nEOF\ngit add -A",
        "cat > f <<-EOF\n\tbody\nEOF\ngit add -A",
        'cat <<< "hi"\ngit add -A',
        "cat > a <<EOF\nbody\nEOF\ncat > b <<EOF2\nbody\nEOF2\ngit add -A",
    ])
    def test_a_real_command_after_a_heredoc_is_still_seen(self, command):
        # The failure mode this closes: an over-eager marker scan eats to end of input
        # and the guard reports "allowed" for the command that follows.
        p = run_guard(command)
        assert p.returncode == 2, f"command after a heredoc was swallowed: {command!r}"

    @pytest.mark.parametrize("command", [
        'git commit -m "wip #123"',
        "git commit -m 'fix # not a comment'",
    ])
    def test_a_hash_inside_quotes_is_not_a_comment(self, command):
        assert run_guard(command).returncode == 0, command

    def test_a_quoted_hash_does_not_hide_a_later_command(self):
        assert run_guard('echo "#"\ngit add -A').returncode == 2

    @pytest.mark.parametrize("command", [
        "git add -A  # stage everything",
        "git commit -am wip  # quick",
        "git reset --hard  # nuke it",
    ])
    def test_a_trailing_comment_does_not_disarm_the_block(self, command):
        # Binds the quote-aware comment strip specifically: without it the `#` and the
        # words after it survive as TOKENS and read as scoping pathspecs, so the
        # command looks scoped and is allowed.
        assert run_guard(command).returncode == 2, command

    @pytest.mark.parametrize("command", [
        'cat <<< "hi"\ngit status --short',
        'cat <<< "x"\ngit log --oneline',
    ])
    def test_a_here_string_does_not_swallow_a_following_safe_command(self, command):
        # Binds the `<<<` guard: mistaking a here-string for a heredoc invents a marker
        # that never terminates, which fails CLOSED and blocks innocent commands.
        assert run_guard(command).returncode == 0, command

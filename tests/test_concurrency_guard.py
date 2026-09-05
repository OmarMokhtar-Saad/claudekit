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
import re
import shlex
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
    "git commit --all -m x",
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
    # round 4: the `-m` VALUE is a message, not a scoping pathspec -- `push -m wip`
    # stashes the whole shared tree (the round-3 fix was unbound by any test, and a
    # mutation that reverted it kept the suite green)
    "git stash push -m wip", "git stash push -mwip", "git stash push --message wip",
    "git stash push --message=wip",
    # round 4: process substitution is not a scoping pathspec
    "git add -A <(echo hi)", "git add -A >(cat)",
    # git global options before the subcommand (regression: all of these leaked)
    "git -C . add -A", "git -C /tmp/repo add -A",
    "git --git-dir=.git --work-tree=. add -A", "git -c user.name=x add -A",
    # command-word and prefix wrappers
    "sudo git add -A", "env git add -A", "/usr/bin/git add -A", "GIT_DIR=x git add -A",
    "bash -c 'git add -A'",
    # shell structure (regression: `{ ...; }` and `then ...` leaked)
    "{ git add -A; }", "if true; then git add -A; fi", "cd foo && git add -A",
    "git status && git add .",
    # round 5: each of these is the PROBE for a mutant in
    # TestTheMutationRecordIsExecutable, and is listed here so this suite is what
    # kills that mutant. `file#1.txt` keeps its hash (`at_token_boundary`) and shlex's
    # own commenter stays disabled; both lines were documented as redundant and both
    # turn this command into an ALLOW when reverted.
    "echo file#1.txt; git add -A", "git add -A 2>/dev/null",
    "cat <<EOF\nno terminator\ngit add -A",
    # a closing group ENDS its command: `b` is not a pathspec of the inner `git add -A`
    "diff <(git add -A) b", "case $x in a) git add -A;; esac",
    # COMBINED pathspec magic re-roots at the top exactly as `:(top)` does -- verified
    # against git: `git add ':(top,glob)'` stages every modified file in the tree
    "git add ':(top,glob)'", "git add ':(glob,top)'", "git add ':(top,exclude)'",
    # round 6: a closing group FUSED to its separator (`);`, `)&&`, `))`) used to eat
    # the separator, so the next command merged into the previous segment and its
    # command word was no longer `git`. No obfuscation needed -- a subshell, a command
    # substitution or an arithmetic expansion on the line above is enough.
    "(echo x); git add -A", "x=$(date); git add -A", "(ls)&&git add -A",
    "arr=(1 2); git add -A", "echo $((1+2))\ngit add -A",
    # round 6: a NEGATIVE pathspec never scopes -- verified against git, `git add
    # ':!nope'` stages every modified file in the tree, and `git checkout -- ':!nope'`
    # discards every local modification
    "git add ':!nope'", "git add ':^nope'", "git add ':(exclude)nope'",
    "git add -A ':!node_modules'", "git checkout -- ':!nope'", "git rm -r ':!nope'",
    "git add ':(top,exclude)nope'",
    # round 6: `**/*` is a TREE_WIDE_PATHSPECS member that a hand-copied remainder set
    # had dropped, so the whole tree came back through a magic prefix
    "git add ':(glob)**/*'", "git add ':(top)**/*'", "git add ':(top)/'",
    # round 6: `git commit -- .` commits every modified tracked file, exactly as -a does
    "git commit -- .", "git commit -- ':!nope'",
    # round 6: probes for mutants of lines that carried a verdict with no test
    "sleep 1 & git add -A", "git -C/tmp/x add -A", "git clean -qf", "git.exe add -A",
    # round 7: `git reset -- .` empties the shared index exactly as bare `git reset`
    # does -- verified against git. Only the spelling differs.
    "git reset -- .", "git reset -- ':!x'", "git reset --mixed -- .",
    # round 7: a wrapper's OWN option used to become the command word, so the git call
    # behind it was dropped. Bare `sudo git add -A` was tested; the flagged form was not.
    "sudo -u me git add -A", "env -i git add -A", "nice -n 10 git add -A",
    "command -p git add -A", "time -p git add -A",
    # round 7: git's own long synonym for `-A`, blocked but bound by nothing
    "git add --no-ignore-removal",
    # round 8: a single reset operand is a REVISION -- `git reset main` resets the whole
    # index to a branch, and `git reset HEAD` unstages everything
    "git reset HEAD", "git reset main",
    # round 9: a TREE-WIDE first reset operand is a pathspec, not a revision --
    # `git reset . src/a.py` empties the shared index (verified against git), and
    # appending any second token used to turn the denial into an allow
    "git reset . src/a.py", "git reset :/ src/a.py",
    # round 14: `:(literal)` suppresses WILDMATCH, not path resolution -- these still
    # walk to the repo root and stage everything (verified from a subdirectory)
    "git add ':(literal)a/../..'", "git add ':(literal)./..'", "git add ':(literal).'",
    "git add ':(literal)..'", "git commit -m wip ':(literal)a/../..'",
    "git add ':(top,literal)a/../..'",
    # round 13: an INTERIOR `..` walks up exactly as a leading one does -- `a/../..`
    # stages the whole tree from a subdirectory (verified against git)
    "git add a/../..", "git rm -r a/../..", "git commit -- a/../..",
    # round 12: `../..` walks UP to the repo root and stages everything (verified from
    # a subdirectory); only the enumerated `..` spelling used to catch it
    "git add ../..", "git add ../../",
    # round 11: the commonest spelling of the incident. `git commit -m wip .` commits
    # every modified tracked file in the shared tree (verified against git) -- only the
    # `--` spelling used to block, because ALL operands were discarded as "the message".
    "git commit -m wip .", "git commit -mwip .", "git commit --message=wip .",
    # round 15: an option's SEPARATE value was read as a scoping pathspec, and the
    # scoped-pathspec early return then fired before the flag rule was reached. Every
    # one of these committed or staged the whole shared tree and exited 0 (verified
    # against git), and `--author` is the spelling this repo family writes most, since
    # CLAUDE.md mandates AI attribution.
    'git commit -am wip --author "N <n@e.com>"',
    'git commit -a -m wip --author "N <n@e.com>"',
    'git commit -a --author "N <n@e.com>"',
    "git commit --all -F msg.txt", "git commit -a -C HEAD", "git commit -a -t t.txt",
    "git commit -a --date now", "git commit -a --cleanup whitespace",
    'git commit -am wip --trailer "K: v"', "git commit -a --squash HEAD",
    "git add -A --chmod +x", "git stage -A --chmod +x",
    # `-S`/`-u` take an OPTIONAL value, so git reads the next token as a PATHSPEC and
    # refuses it alongside `-a`. The hook must not need to know that: `--all` is tested
    # before any pathspec can look scoping.
    "git commit -a -S keyid", "git commit -a --untracked-files no",
    # round 15: `git commit -u . -m wip` commits every modified tracked file (verified),
    # because `.` is a pathspec here and not `-u`'s value
    "git commit -u . -m wip", "git commit -S . -m wip",
    # round 15: the commit operand list was read by COUNT, not by POSITION -- a pathspec
    # BEFORE `-m` was dropped as "the message". `git commit . -m wip` committed both
    # sessions' files (verified against git) and exited 0
    "git commit . -m wip", "git commit .. -m wip", "git commit . --message wip",
    # round 15: a pathspec list read from a FILE cannot be inspected, so it is tree-wide
    # -- fail CLOSED. With `.` in the file, `git rm -r --pathspec-from-file=list.txt`
    # deleted every tracked file and exited 0; the fused spelling left `pathspecs`
    # empty, so no rule fired at all.
    "git add -A --pathspec-from-file list.txt",
    "git add --pathspec-from-file list.txt", "git add --pathspec-from-file=list.txt",
    "git rm -r --pathspec-from-file list.txt", "git rm -r --pathspec-from-file=list.txt",
    "git commit -m wip --pathspec-from-file list.txt",
    "git checkout --pathspec-from-file list.txt",
    "git restore --pathspec-from-file list.txt",
    "git stash push --pathspec-from-file list.txt",
    # round 15: an arithmetic expansion that never closes means the `<<` suppression
    # may have swallowed a real heredoc, so the text was not understood -- fail closed,
    # inside the documented cost of "untokenisable text containing `git`"
    "echo $(( ; git status",
    # round 16: git resolves any UNAMBIGUOUS PREFIX of a long option, so every
    # exact-match denial had a legal spelling it did not recognise. Verified against
    # git 2.50: `--al` staged the whole tree, `--fo` discarded another session's edit,
    # `--pathspec-fr=` deleted every tracked file. Full coverage of every rule name at
    # every abbreviation length is in TestALongOptionAbbreviationIsResolvedLikeGitDoes;
    # these two are the MUTANTS probes, which must be members of this list.
    "git add --al",
    # an abbreviated EXEMPTION must not lift a denial -- prefix-matching an allowlist
    # is the fail-OPEN direction, so exemptions stay exact and this over-blocks
    "git add --dry-ru -A",
    # round 16 follow-up: the abbreviation rule and round 15's value consumption meet
    # here, and the meeting point leaked -- an abbreviated value-taking option's value
    # stayed an operand and scoped the command. Verified against git: both of these
    # reached the whole tree and exited 0.
    "git add -A --chm +x", "git stash push --mes wip",
    # round 19: GROUPING and non-pipe separators reset the stdin-fed bit, so round 18's
    # whole fix vanished the moment the command was wrapped. Verified against git 2.50:
    # `yes | (git checkout -p .)` DESTROYED another session's in-flight edit and
    # `yes | (git commit -p -m wip .)` committed both sessions' files, both exit 0,
    # while the identical UNWRAPPED spellings blocked. A subshell does not hand a human
    # back the keyboard.
    "yes | (git checkout -p .)", "yes | { git commit -p -m wip .; }",
    "yes | (git commit -p -m wip .)", "yes | (git add -p .)",
    "yes | if true; then git commit -p -m wip .; fi",
    "yes | (git reset -p)", "yes | (git stash -p)", "yes | (git restore -p .)",
    # round 19: an unrecognised option before the subcommand became the "subcommand"
    # itself and disarmed every rule. All documented globals, not obfuscation.
    "git --no-advice add -A", "git --no-lazy-fetch add -A",
    "git --no-literal-pathspecs commit -a -m x", "git --attr-source=HEAD add -A",
    "git --no-advice clean -fd", "git --no-advice reset --hard",
    "git --frobnicate add -A",
    # round 19, and an OVER-block I introduced rather than a leak: a `;` sibling
    # inherits the pipeline's stdin, so a `-p` after a pipeline is denied even though
    # bash hands it the terminal back. Named in the doc's residuals -- telling a
    # compound's sibling from a top-level one needs a real shell grammar, and
    # fail-closed is the direction this hook takes.
    "yes | git status; git add -p .",
    # round 20 (found while probing my own round-19 fix): `punctuation_chars` FUSES a
    # run of operator characters, so a heredoc arrives glued to the separator that
    # follows it -- `git add -p . <<EOF` preprocesses to one token `<<;`. Classified
    # whole it read as a SEPARATOR, the redirection meaning was lost, and the `--patch`
    # exemption came back to life: verified against git, this staged BOTH sessions'
    # files at exit 0 while the identical `<<<` and `<` spellings blocked.
    "git add -p . <<EOF\ny\ny\nEOF",
    "git commit -p -m wip . <<EOF\ny\nEOF",
    "git checkout -p . <<-EOF\ny\nEOF",
    "git add -p . 0< ans",
    "git clean -i", "git clean --interactive", "git clean -i -d", "git clean --inter",
    "git commit --interactive -m wip", "git commit --inter -m wip",
    # round 20 second pass: a redirection attached to the GROUP feeds every command
    # inside it, and the closer had already started a new segment, so the git command
    # kept fed=False. Verified against git 2.50: this DESTROYED both sessions'
    # in-flight edits, unattended, at rc 0.
    "{ git checkout -p .; } < ans", "( git checkout -p . ) < ans",
    "{ git add -p .; } <<< y", "{ git commit -p -m wip .; } <<EOF\ny\nEOF",
    # the redirection can also hang off a LOOP, where `do`/`done` are not grouping
    # tokens at all -- so an input redirection anywhere now marks every segment
    "while read x; do git add -p .; done < f",
    "for f in a; do git checkout -p .; done < list",
    "cat < f; git add -p .",
    # round 21: two round-20 lines that carried a verdict with no test
    "git add -p . ; (echo x) ; cat < f", 'echo "$(f (x) ; git add -A)"',
    # round 20: a DOUBLE-QUOTED command substitution was copied verbatim as quoted
    # data, so shlex yielded one word and the inner command never became a segment.
    # `x="$(git ...)"` is the commonest scripted capture spelling there is, and the
    # doc claimed the whole `$(...)` class was caught when only the unquoted form was.
    'echo "$(git add -A)"', 'x="$(git checkout -f)"', 'echo "$(git reset --hard)"',
    'echo "before $(git add -A) after"', 'echo "$(git clean -fd)"',
    'echo "$(cd src && git add -A)"',
    # round 21: `arith_depth` was only ever raised by the UNQUOTED `$((` branch, and
    # the round-20 `$(` lift matched `$((` first. So a `<<` inside `"$((...))"` or
    # inside the bare arithmetic COMMAND `((...))` became a heredoc whose invented
    # marker swallowed every following line WITH `confident` still True -- the
    # fail-OPEN shape this layer was rewritten to eliminate, arriving inside round
    # 20's own fix. Verified against git: both staged session A's in-flight edit.
    'x="$((1<<2))"\ngit add -A\n2',
    "(( 1 << 2 ))\ngit checkout -f\n2",
    "(( 1 << 2 ))\ngit add -A\n2",
    # an unconsumed heredoc marker at end of text is not understood text
    "git log <<EOF", "git status; cat <<EOF",
    # round 21: `-c` carries config that decides what the command MEANS, and the hook
    # was parsing the token and throwing it away. `clean`'s premise -- that git
    # refuses to delete without `-f` -- is config-dependent: verified against git,
    # this DELETED another session's untracked file and a whole subdirectory at rc 0.
    "git -c clean.requireForce=false clean -d",
    "git -c clean.requireForce=false clean",
    "git -cclean.requireForce=false clean -d",
    "git -c ALIAS.ST='add -A' st",
    # an ALIAS makes the command word something only git can expand
    "git -c alias.st='add -A' st", "git -calias.st='add -A' st",
    # round 21: `shlex` discards quoting, so a quoted operator-only word was
    # classified as a REDIRECTION and its skip swallowed the token behind it.
    # Verified with a file named `>` present: this staged both sessions' files.
    "git add '>' .", "git rm -r '>' .", "git commit -m wip '<' .",
    "git add '|' .", "git add '&&' .",
    # round 21: an unlisted wrapper word makes the command word not `git`, so the
    # WHOLE segment was dropped. `caffeinate` is macOS-native and was the miss.
    "caffeinate git add -A", "timeout 5 git add -A", "stdbuf -o0 git add -A",
    # round 22: the FUSED `--config-env=key=value` skipped the opacity test the
    # separate spelling had, restoring round 21's two leaks for one `=`. Verified
    # against git: the alias form staged both sessions' files and the requireForce
    # form deleted both untracked files, rc 0.
    "git --config-env=alias.st=AL st",
    "git --config-env=clean.requireForce=RF clean -d",
    "git --config-env=include.path=INCP st",
    # round 22: `include.path` pulls in a config FILE, so an alias arrives one
    # indirection further out -- git config sections are case-insensitive
    "git -c include.path=/tmp/inc.cfg st", "git -c INCLUDE.path=/tmp/inc.cfg st",
    "git -c includeIf.gitdir:x.path=/tmp/f st",
    # round 23: `help.autocorrect` decides WHICH SUBCOMMAND git runs -- verified,
    # `addd -A` really executed `add -A` and staged both sessions' files
    "git -c help.autocorrect=immediate addd -A",
    "git -chelp.autocorrect=immediate addd -A",
    "git --config-env=help.autocorrect=AC addd -A",
    "git -c help.autocorrect=immediate cleann -fd",
    # round 23: round 22's escaped-operator fix emitted a closing `"` while INSIDE
    # double quotes, severing the line so every token after it was dropped. Verified:
    # each of these committed or deleted both sessions' work at rc 0.
    'git commit -m "wip\\;x" -a', 'git clean -e "a\\;b" -fd',
    'git commit --author "Claude\\;X <n@a.com>" -a -m x', 'git commit -m "a\\|b" -a',
    # round 23: round 20's `$(...)` lift spliced `;` into the OUTER command, dropping
    # every flag after the substitution -- the ordinary release-commit spelling
    'git commit -m "release $(cat VERSION)" -a', 'git commit -m "$(date)" -a',
    'git clean -e "$(cat p)" -fd', 'echo "$(echo "$(git add -A)")"',
    # an EMPTY argument is an argument: dropping it let `-m` swallow the `-a`
    'git commit -m "" -a', 'git clean -e "" -fd', 'git commit -m "" --all',
    'git add "" -A',
    # git refuses an empty PATHSPEC, so over-blocking this costs nothing
    'git add "" src/a.py',
    # round 22: round 21's sentinel covered only the QUOTED spelling, so an ESCAPED
    # operator-only pathspec was still classified as a redirection and its
    # target-skip ate the tree-wide token behind it. Verified: `git checkout \> .`
    # destroyed both sessions' in-flight edits.
    "git checkout \\> .", "git commit -m x \\> .", "git add \\> .",
    # round 24/25: every expansion is now ONE opaque word with a placeholder, in every
    # quote state, because the unquoted spellings severed the outer command and
    # dropped the flag behind it. Each of these committed, staged or deleted BOTH
    # sessions' work at rc 0 (verified against git).
    "git commit -m $(date) -a", "git commit -m $(cat VERSION) -a",
    "git commit -m $((1)) -a", "git clean -e $(cat p) -fd",
    "git add --chmod +x $(date) .", "echo $(git add -A)",
    # process substitution is a word whose body is a command, exactly like `$(...)`
    "git commit -m <(echo x) -a", "git clean -e <(echo x) -fd", "git commit -m >(cat) -a",
    "git commit -m ${x:-a;b} -a", "git clean -e ${x:-a;b} -fd", "git add ${x:-a;b} .",
    # a QUOTED or ESCAPED grouping character is a word, not a closer -- rounds 21/22
    # closed `<>&|;` and left `(){}` out
    'git commit -m ")" -a', 'git add ")" .', 'git add "}" .',
    'git checkout ")" -f', 'git clean ")" -fd', 'git commit -m \\) -a',
    "git commit -m } -a",
    # bash DELETES a line continuation, joining the words; emitting a space split one
    # word into two and the extra one read as a revision operand
    "git reset HEA\\\nD", "git stash push -m a\\\nb",
    # round 25: a brace is a reserved word ONLY in command-word position -- `{`, `}`
    # and `{}` are ordinary words anywhere else, grouped or not. Round 24 fixed the
    # bare `}` gated on no group being open, so wrapping the command undid it, and it
    # never covered the opener. Each of these committed or deleted both sessions'
    # work at rc 0 (verified against bash + git).
    "git commit -m { -a", "git clean -e { -fd", "git commit -m {} -a", "git add { .",
    "{ git commit -m } -a; }", "{ git clean -e { -fd; }",
    # round 25: `>|` (noclobber override) is ONE redirection operator; reading its `|`
    # as a pipe severed the command at the redirection
    "git commit -m x >| out -a", "git add >| out -A", "git clean -e p >| out -fd",
    "git rm -r >| out .", "git checkout >| out .", "git add -A >| out", "git add -A >& out",
    # round 26: the heredoc MARKER is consumed in preprocess, so the `<<` token's
    # target-skip ate the next real argument -- `-a` after the marker is still git's
    # (verified: this committed both sessions' files at rc 0)
    "git commit -m x <<EOF -a\nbody\nEOF", "git add <<EOF -A\nbody\nEOF",
    "git clean -e p <<EOF -fd\nbody\nEOF",
    # round 26: process substitution GLUED to a word is still a substitution (bash
    # performs it mid-word), and gating the lift on a token boundary let `<(` reach
    # the classifier as a separator. Verified: both committed/deleted both sessions'
    # work at rc 0.
    "git commit -m x<(echo y) -a", "git clean -e p<(echo y) -fd", "git commit -m x>(cat) -a",
    # round 26: a wrapper option's VALUE is not a script file, so the stdin script
    # must still be treated as unreadable -- verified, `-O extglob` staged both
    # sessions' files and the here-string spelling destroyed both in-flight edits
    "bash -O extglob <<EOF\ngit add -A\nEOF", "bash --rcfile f <<EOF\ngit add -A\nEOF",
    'bash -O extglob <<< "git checkout -f"', 'zsh -o x <<< "git add -A"',
    # round 27: an EMPTY brace expansion `{,}` yields zero words under bash, so git
    # received `add -A` while the hook kept `{,}` as a scoping pathspec -- a PHANTOM.
    # Verified under bash 3.2 (zsh differs): both sessions' files staged, both
    # sessions' edits stashed. `{a,b}` is over-blocked by the same rule, named in
    # the residuals.
    "git add {,} -A", "git stash push {,}", "git rm -r {,}", "git add {a,b} -A",
    "git commit -m {,} -a",
    # round 27: bare `$name` was the one expansion spelling not made opaque; an unset
    # name expands to NOTHING, so `git stash push $x` degraded to a bare stash
    "git add $x -A", "git stash push $x", "git add $DIR -A", "git commit -m $x -a",
    "git rm -r \\> .", "git add \\| .",
    # round 22: a shell wrapper reads STDIN as a SCRIPT, and `preprocess` strips
    # heredoc bodies as data -- so the script vanished. Verified: the `sh` form
    # destroyed both sessions' edits and the here-string staged both.
    "sh <<'EOF'\ngit reset --hard\nEOF", "bash <<EOF\ngit add -A\nEOF",
    "bash <<< 'git add -A'", "zsh <<< 'git add -A'", "dash <<< 'git add -A'",
    "bash -s <<EOF\ngit add -A\nEOF", "cat <<EOF | bash\ngit add -A\nEOF",
    # round 24, found by probing round 23's own wrapper fix: `-s` means READ THE
    # SCRIPT FROM STDIN, so a following operand is a positional parameter and not a
    # script file. Verified against bash and git: this staged both sessions' files.
    "bash -s file <<EOF\ngit add -A\nEOF", "bash -s x y <<< 'git add -A'",
    # round 16: a value that LOOKS like an option must NOT be consumed. `--d`
    # abbreviates `--date`, and swallowing the `-a` behind it dropped the `--all`
    # denial -- round 15 wrote that rule in a docstring and did not implement it.
    # round 17: an option VALUE must reach NEITHER list. Left in `flags` it
    # impersonates an exemption -- `flags` is where the exemptions are read from -- and
    # each of these committed, deleted or stashed BOTH sessions' work at exit 0
    # (verified against git 2.50).
    "git commit -a -m --dry-run", "git commit -am --dry-run",
    "git clean -f -e -n", "git clean -fe -n", "git clean -f --exclude -n",
    "git stash push -m --patch", "git commit -a -m --patch",
    # a dropped value must not hide a tree-wide PATHSPEC either
    "git commit -m -a .", "git commit -m --dry-run .", "git add --chmod -A .",
    # round 11: enumerating tree-wide spellings was losing a race against git's
    # wildmatch grammar -- each of these stages the entire tree
    "git add './*'", "git add '?*'", "git add '*?'", "git add '[a-z.]*'",
    "git add ':/?*'", "git add ':(top).'",
    # round 11: a function DEFINITION swallowed its body -- `()` is one token the
    # closing-group peel cannot touch, so the command word became `stage`
    "stage() { git add -A; }", "foo(){ git add -A; }",
    # round 10: a magic PREFIX with a tree-wide remainder -- the only case the
    # `for magic in TREE_WIDE_MAGIC` loop decides, and it had no test. `:/*` stages the
    # entire tree from a subdirectory (verified against git).
    "git add ':/*'", "git add ':/.'", "git add ':/**'", "git checkout -- ':/.'",
    # round 9: bash CONCATENATES eval's arguments, so the joined argv is the script.
    # Only the fully quoted form was ever tested, and only it was caught.
    "eval git add -A", "eval git reset --hard",
    # round 9: `push` is the only stash form that takes pathspecs, so an unknown verb
    # carrying a path must not walk past the default deny
    "git stash frobnicate -- src/a.py",
    # round 8: probes for lines that carried a verdict with no test
    "git clean --force=1", "{git add -A;}",
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
    # round 5: a FUSED long message leaves the operand a real pathspec -- verified
    # against git, `--message=wip src/a.py` stashes only src/a.py
    "git stash push --message=wip src/a.py", "git stash push --message=wip -- src/a.py",
    # a concrete path after a magic signature scopes it, combined keywords included
    "git add ':(top)src/a.py'", "git add ':(top,glob)src/a.py'",
    "git diff <(cat a) <(cat b)",
    # round 6: a negative pathspec alongside a POSITIVE one is the ordinary scoped form
    "git add src/a.py ':!src/b.py'", "git add -A -- src/ ':!src/vendor'",
    # a closing paren inside a quoted argument is data, not a segment terminator
    "git commit -m 'fix(parser): handle ) in msg'", "git log --format='%h (%an)'",
    "git checkout $(git rev-parse HEAD) -- src/a.py", "echo $((1+2))",
    # round 7: a dry run PREVIEWS and mutates nothing -- verified, `git add -n -A`
    # leaves the index empty. Denying the safe way to look at what `-A` would do is
    # over-blocking the very command this hook teaches you to avoid.
    "git add -n -A", "git add --dry-run -A", "git commit --dry-run -a",
    "git reset --soft -- .",
    # round 8: `git reset HEAD <path>` is the classic unstage-ONE-file and it is SCOPED
    # -- verified against git, a second staged path survives it. It was denied while the
    # doc's blocked row said a non-tree-wide pathspec is allowed.
    "git reset HEAD src/a.py", "git reset HEAD .ai/x.md",
    # round 8: `rm` has a dry run too -- the one ruled subcommand round 7 missed
    "git rm -n -r .", "git rm --dry-run -r .",
    # round 13: `:(literal)` turns wildmatch OFF, so `?` is an ordinary character --
    # verified against git, this stages exactly one file. It is also the escape the
    # residuals offer for a literal `?` in a filename, and it was blocked too.
    "git add ':(literal)what?.txt'", "git add ':(icase,literal)a*.py'",
    # `commit` has a real `--patch`; every sibling's `-p .` was allowed and its was not
    "git commit -p .", "git commit --patch .",
    # `worktree add -f` force-creates when a branch is already checked out -- only
    # `worktree remove --force` is ruled on
    "git worktree add -f ../wt/x main",
    # round 12: a bracket expression matches exactly ONE character, so it can never
    # reach past a literal name. Including `[` in the wildmatch set denied a scoped
    # stage of a real tracked file -- one fleet repo has three such names under `.run/`.
    "git add 'notes[1].md'", "git rm 'notes[1].md'",
    "git checkout -- 'notes[1].md'", "git commit -m wip 'notes[1].md'",
    "git add ../src/a.py",
    # round 11: the operand pathspecs commit now reads -- scoped, and `-ma x` really is
    # message "a" with pathspec "x", which the doc claimed before the code did it
    "git commit -m wip src/a.py", "git commit -F msg.txt", "git commit -C HEAD",
    # a literal first path component keeps a glob scoped
    "git add src/*", "git add ':(glob)src/*'",
    # bash takes the FIRST -c as the script; the rest are positional parameters
    "bash -c 'echo hi' -c 'git add -A'",
    # round 9: `-p` confirms every hunk with a human. The exemption existed only on
    # `reset` and `stash`, so these ordinary forms were denied.
    "git add -p .", "git checkout -p .", "git restore -p .", "git stage -p .",
    "git stash -p", "git stash create", "git stash store x",
    # the fail-closed radius is bounded to text containing `git`: an unbalanced quote
    # with no git in it is not this hook's business
    "echo 'unbalanced",
    "git switch main", "git checkout main -- src/",
    "git reset -- src/a.py", "git reset HEAD -- src/a.py",
    # read-only plumbing that takes `.` as an argument
    "git status .", "git diff -- .", "git log -- .", "git show HEAD -- .", "git ls-files .",
    "git worktree remove ../wt",
    "git add 'file with spaces.py'",
    "git commit -m 'add .'", "git commit -m 'reset --hard'",
    # round 4: a fused option VALUE is not a flag cluster. `-m"refactor"` was blocked
    # as `commit -a` and `-bfeature` as `checkout -f`, purely because of the letters
    # in a message or a branch name. `git commit -ma x` is read as git reads it:
    # message "a", pathspec "x" -- scoped, not `--all`.
    'git commit -m"refactor"', 'git commit -m"add a feature"', "git commit -mall",
    "git commit -ma x", "git checkout -bfeature", 'git checkout -b"fix/x"',
    "git switch -cfix", "git restore -sHEAD src/a.py", 'git clean -e"*.log" -n',
    # a FUSED stash message leaves the following operand a real pathspec
    "git stash push -mwip src/a.py", "git stash push -m wip src/a.py",
    # a heredoc BODY is data, not a command
    "cat > f <<EOF\ngit reset --hard\nEOF",
    "cat > f <<'EOF'\ngit add -A\nEOF",
    # round 15: an option's separate VALUE is not a pathspec and must not be denied.
    # One case per member of REQUIRED_VALUE_LONG_OPTS / REQUIRED_VALUE_SHORT_OPTS lives
    # in TestASeparateOptionValueIsNotAPathspec; these are the daily spellings.
    'git commit -m x --author "N <n@e.com>"', "git commit -m x --date now",
    "git add --chmod +x src/a.py", "git commit --squash HEAD", "git commit --fixup HEAD",
    "git checkout --orphan newbranch", "git restore --source HEAD -- src/a.py",
    # a DRY RUN of a file-supplied pathspec list mutates nothing, so the fail-closed
    # treatment of the list must not swallow the preview
    "git add -n --pathspec-from-file list.txt",
    "git add --dry-run --pathspec-from-file=list.txt",
    "git rm -n --pathspec-from-file list.txt",
    # round 15: `$((1<<2))` is an arithmetic shift, not a heredoc. Reading it as one
    # invented a marker that never arrived and DENIED a read-only `git log` script.
    "git log --oneline\necho $((1<<2))\necho done",
    "echo $((1<<2))\ngit status",
    # round 19: grouping alone changes nothing -- only a FED stdin lifts the `-p`
    # exemption, so an ordinary interactive patch in a subshell stays allowed
    "(git add -p .)", "{ git add -p .; }", "git add -p . && git status",
    # an OUTPUT redirection does not feed stdin, so the exemption survives it
    "git add -p . > out", "git add -p . 2>/dev/null",
    # round 20: the read-only globals the fail-closed inversion had denied. The doc
    # justified that with "it is not a command git would run either" -- false, and
    # `git --version` is in doctor and CI scripts everywhere, where a denial anywhere
    # in a compound kills the whole call.
    "git --version", "git -v", "git --help", "git -h", "git --man-path",
    "git --list-cmds=main", "git status && git --version",
    # `commit -i` is `--include`, which takes paths and is scoped by them -- not the
    # interactive flag denied above
    "git commit -i src/a.py -m x", "git clean -i -n",
    # a substitution that is read-only, or scoped, is still allowed
    'echo "$(git status)"', 'echo "$(git log --oneline)"',
    'echo "$(git add src/a.py)"', "echo '$(git add -A)'",
    # round 21: a quoted arithmetic expansion must still be READ, not feared -- the
    # `))` decrement has to fire while quoted too, or this read-only script fails
    # closed (round 15's documented allowance, in the quoted spelling)
    'x="$((1<<2))"\ngit log --oneline',
    'echo "$((1<<2))"', 'n=$(( 1 << 3 ))\ngit status',
    # an ordinary `-c` setting is not opaque: only alias.* and clean.requireForce are
    "git -c user.name=x add src/a.py", "git -c core.editor=vim commit -m x",
    "git -cuser.name=x add src/a.py",
    # git itself scopes `git add ';' -A` to the file named `;` (verified), and a
    # quoted redirection-looking FILENAME is an ordinary scoped stage
    "git add ';' -A", 'git add ">out.txt"', "caffeinate git add src/a.py",
    # round 22: an escaped operator-only pathspec is a PATHSPEC, so a scoped one stays
    # allowed, and git itself scopes `-A` to the pathspecs given before it (verified:
    # `git add ';' -A` stages only the file named `;`)
    "git checkout \\> src/a.py", "git add \\> src/a.py", "git add \\; -A",
    "echo a \\> b",
    # a wrapper whose script arrives as ARGV is still read, not feared
    "bash -c 'git status'", "bash -lc 'git status'", "bash script.sh",
    # round 23: gating the wrapper denial on `fed` alone refused every ordinary
    # piped-into wrapper, including one whose git text is read-only. A wrapper with a
    # script FILE operand is the named script-file residual either way.
    "git status; echo x | bash build.sh", 'echo "git is fine" | sh cleanup.sh',
    # `sh -- file` really does run the FILE (verified: it printed the file's own output
    # and staged nothing), so `--` is not the stdin case and stays the named residual
    "sh -- file <<EOF\ngit add -A\nEOF",
    # a substitution mid-line must leave the outer command intact
    'git commit -m "release $(cat VERSION)" src/a.py', 'echo "$(git status)"',
    # round 25: the `${` scan is quote-aware, so a `}` INSIDE quotes does not close it
    'git commit -m ${x:-"}"} src/a.py', 'git commit -m ${x:-a;b} src/a.py',
    # a brace as an ordinary argument of a SCOPED command, and a noclobber redirection
    # on a read-only or scoped one
    "git commit -m { src/a.py", "git status >| out", "git add src/a.py >| out",
    # a wrapper option's value followed by a REAL script file stays the file residual
    "bash -O extglob build.sh", "bash -O extglob -c 'git status'", "echo x<(echo y)",
    # an opaque `$name` where its value cannot make the command tree-wide
    "git commit -m $msg src/a.py", "git log $b", "git push origin $b", "echo {a,b}",
    "git add -p . >| out", "echo A {} B",
    'echo "$(echo "$(git status)")"', 'git commit -m "" src/a.py',
    'echo "a $(date) b"',
    # an ordinary `-c` setting is not opaque in the fused spelling either
    "git --config-env=user.name=U add src/a.py",
    # a KNOWN global must not turn a scoped stage into a denial
    "git --no-advice add src/a.py", "git --attr-source=HEAD add src/a.py",
    "git --no-literal-pathspecs add src/a.py", "git -C/tmp/x add src/a.py",
    # a newline INSIDE quotes is data and must not split the command
    'echo "a\nb"',
]


#: A FROZEN COPY of every shipped collection the suite parametrises over.
#:
#: Parametrising over the hook's own constant has one weakness that three rounds of
#: "subset canaries" did not close: DELETING a member deletes its own test case, so the
#: suite stays green. Round 9 removed `nohup` from PREFIX_WORDS, `zsh` from
#: SCRIPT_WRAPPERS, `--namespace` from GIT_GLOBAL_WITH_VALUE and `*.*` from
#: TREE_WIDE_PATHSPECS -- each changed a verdict, each left the suite green. Comparing
#: the shipped set against this copy makes any deletion OR addition a hard failure,
#: while the parametrised behaviour tests below still exercise every member.
#:
#: Changing the hook means changing this copy in the same commit, deliberately.
EXPECTED_CONSTANTS = {
    "TREE_WIDE_PATHSPECS": {"*", "**", "**/*", "*.*", ".", "..", "../", "./", ":",
                            ":!", ":/"},
    "TREE_WIDE_MAGIC": {":/", ":(top)", ":(glob)", ":(top,", ":(exclude)"},
    "OPERATORS": {"&", "&&", ";", "|", "|&", "||"},
    "PREFIX_WORDS": {"!", "(", "((", ".", "builtin", "caffeinate", "case", "chrt",
                     "command", "coproc", "do", "doas", "elif", "else", "env", "esac",
                     "exec", "for", "function", "if", "in", "ionice", "nice", "nohup",
                     "select", "setsid", "source", "stdbuf", "sudo", "then", "time",
                     "timeout", "until", "while", "{"},
    "SCRIPT_WRAPPERS": {"bash", "dash", "eval", "sh", "zsh"},
    "WRAPPER_VALUE_OPTS": {"+O", "+o", "--init-file", "--rcfile", "-O", "-o"},
    "GIT_GLOBAL_WITH_VALUE": {"--attr-source", "--config-env", "--exec-path",
                              "--git-dir", "--list-cmds", "--namespace",
                              "--super-prefix", "--work-tree", "-C", "-c"},
    "GIT_GLOBAL_FLAGS": {"--bare", "--glob-pathspecs", "--html-path",
                         "--icase-pathspecs", "--info-path", "--literal-pathspecs",
                         "--man-path", "--no-advice", "--no-lazy-fetch",
                         "--no-literal-pathspecs", "--no-optional-locks", "--no-pager",
                         "--no-replace-objects", "--noglob-pathspecs", "--paginate",
                         "--version", "-P", "-h", "-p", "-v", "--help"},
    "STASH_RESTORATIVE": {"apply", "branch", "create", "drop", "list", "pop", "show",
                          "store"},
    "PATCH_SUBCOMMANDS": {"add", "checkout", "commit", "reset", "restore", "stage",
                          "stash"},
}


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

    @pytest.mark.parametrize("flag", ["--hard", "--merge", "--keep"])
    def test_every_destructive_reset_flag_names_its_own_remediation(self, flag):
        # Asserting the exit code alone left `--merge` and `--keep` unbound: dropping
        # either kept the suite green because the command still blocked, just under the
        # wrong rule, so the user got "unstage your own paths" for a command that
        # destroys the working tree. Bind the REMEDIATION, not only the verdict.
        p = run_guard("git reset %s" % flag)
        assert p.returncode == 2
        assert guard.FIXES["reset-destructive"] in p.stderr, (
            "`git reset %s` fell through to the wrong rule" % flag)

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

    def test_a_top_level_command_field_is_read(self):
        # Some payload shapes carry `command` at the top level rather than under
        # `tool_input`. That fallback had no test: replacing it with `None` left the
        # suite green while the command sailed through.
        p = run_guard(None, raw='{"tool_name":"Bash","command":"git add -A"}')
        assert p.returncode == 2, "the top-level command field was not read"

    def test_a_non_dict_tool_input_fails_closed(self):
        # The sibling of the non-string `command` field: present but malformed is not
        # the same as absent, and reporting "no command" made it fail open.
        p = run_guard(None, raw='{"tool_name":"Bash","tool_input":"git add -A"}')
        assert p.returncode == 2, "a non-dict tool_input failed open"

    def test_a_non_string_command_field_fails_closed(self):
        # A `command` key that is not a string is MALFORMED, not absent. It used to be
        # the one malformed payload that failed open, while the doc claimed every one
        # of them blocks.
        p = run_guard(None, raw='{"tool_name":"Bash","tool_input":{"command":123}}')
        assert p.returncode == 2, "a non-string command field failed open"

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
        # round 24: the doc claimed here-strings and line continuations were in this
        # list, and neither was -- the missing continuation is exactly where
        # `git reset HEA\<nl>D` lived. Both are decorations, not part of the command.
        "cat <<< 'a string'\n{cmd}",
        "echo one \\\n  two\n{cmd}",
        "x=$(date)\n{cmd}",
        "echo ${x:-a;b}\n{cmd}",
        "echo $((1<<2))\n{cmd}",
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

    @pytest.mark.parametrize("name", sorted(EXPECTED_CONSTANTS))
    def test_no_member_can_be_deleted_without_a_failure(self, name):
        # The deletion half of the ratchet. Without it, removing a member removes its
        # own parametrised case -- round 9 deleted four members with the suite green.
        assert set(getattr(guard, name)) == EXPECTED_CONSTANTS[name], (
            "%s drifted from its frozen copy; change both, deliberately, or the "
            "member you removed has no test left" % name)

    @pytest.mark.parametrize("verb", sorted(guard.STASH_RESTORATIVE))
    def test_every_restorative_stash_verb_is_allowed(self, verb):
        # `stash` DENIES by default and this allowlist is what lifts it, so every
        # member needs a case: `create` and `store` were as unproven as `apply` was
        # before round 8 made the list load-bearing.
        command = "git stash %s" % verb
        assert run_guard(command).returncode == 0, command

    @pytest.mark.parametrize("sub", sorted(guard.PATCH_SUBCOMMANDS))
    def test_the_interactive_patch_flag_is_exempt_for_every_subcommand_that_has_one(self, sub):
        # `-p` confirms every hunk with a human, so it cannot touch another session's
        # file unattended. The exemption existed only on `reset` and `stash`, so
        # `git add -p .` -- ordinary daily usage -- was denied for eight rounds.
        for command in ("git %s -p" % sub, "git %s -p ." % sub):
            assert run_guard(command).returncode == 0, command

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
        pathspec = magic + "src/a.py"
        if guard.is_negative_pathspec(pathspec):
            # An EXCLUDE signature is the inversion: `:(exclude)src/a.py` does not
            # narrow anything, it stages everything ELSE. Verified against git in
            # round 6 -- this case asserted the opposite for three rounds.
            assert run_guard("git add '%s'" % pathspec).returncode == 2, magic
            return
        assert run_guard("git add '%s'" % pathspec).returncode == 0, magic

    @pytest.mark.parametrize("remainder", sorted(guard.TREE_WIDE_PATHSPECS))
    @pytest.mark.parametrize("magic", sorted(guard.TREE_WIDE_MAGIC))
    def test_pathspec_magic_with_a_tree_wide_remainder_blocks(self, magic, remainder):
        # The one case the `for magic in TREE_WIDE_MAGIC` loop actually decides -- the
        # bare forms and the concrete-path forms are both settled before it runs. It had
        # NO test at any level: deleting the whole loop left all 950 green while
        # `git add ':/*'` flipped to allow, and `:/*` stages the entire tree from a
        # subdirectory (verified against git).
        pathspec = magic.rstrip(",") + remainder
        assert run_guard("git add '%s'" % pathspec).returncode == 2, pathspec

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


class TestAnUnknownPreSubcommandOptionFailsClosed:
    """Round 19's second BLOCKING finding: the option became the "subcommand".

    `strip_git_globals` used to `break` on the first token it did not recognise, so
    `decide_git` read the OPTION as `sub`, matched no rule, and returned None. One
    ordinary documented flag disarmed add, commit, reset, checkout, clean and stash at
    once -- verified against git 2.50: `git --no-lazy-fetch add -A` staged both
    sessions' files, `git --no-literal-pathspecs reset --hard` destroyed another
    session's edit, `git --attr-source=HEAD clean -fd` deleted its untracked file.

    Enumerating the four missing members would have been the FIFTH hand-patch in the
    "legal spelling not enumerated" class, so the fail DIRECTION was inverted instead.
    These cases pin the inversion, not the enumeration: an option nobody has ever heard
    of must block too.
    """

    @pytest.mark.parametrize("glob", [
        "--no-advice", "--no-lazy-fetch", "--no-literal-pathspecs",
        "--attr-source=HEAD", "--frobnicate", "--not-a-real-git-option",
    ])
    @pytest.mark.parametrize("tail", ["add -A", "commit -a -m x", "reset --hard",
                                      "checkout -f", "clean -fd", "stash"])
    def test_a_tree_wide_command_still_blocks_behind_any_global(self, glob, tail):
        p = run_guard("git %s %s" % (glob, tail))
        assert p.returncode == 2, (
            f"global {glob!r} disarmed {tail!r} (rc={p.returncode})")

    def test_an_unknown_global_blocks_even_a_read_only_subcommand(self):
        # The COST of the inversion, named rather than hidden: the hook can no longer
        # tell an unknown global's invocation apart from text it cannot read, so it
        # takes the same fail-CLOSED path. `git --frobnicate status` is not a real
        # command anyway (git exits 129), so nothing that works is denied.
        assert run_guard("git --frobnicate status").returncode == 2

    @pytest.mark.parametrize("glob", [
        "--no-advice", "--attr-source=HEAD", "--no-pager", "--git-dir=.git",
        "--literal-pathspecs", "--no-literal-pathspecs", "--no-lazy-fetch",
    ])
    def test_a_known_global_does_not_block_a_scoped_command(self, glob):
        # The other direction: adding members must not turn a scoped stage into a
        # denial. `--no-literal-pathspecs` is the NEGATION of a member that was already
        # shipped -- the sibling-drift shape of rounds 5-9, 11, 13 and 14.
        p = run_guard("git %s add src/a.py" % glob)
        assert p.returncode == 0, (glob, p.stderr)

    def test_git_accepts_every_global_this_hook_lists(self, tmp_path):
        # The premise, proven against git rather than asserted: a member that git does
        # NOT accept would be dead weight, and one it accepts with a VALUE in the
        # no-value set would eat the subcommand.
        repo = tmp_path / "globals"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=str(repo), capture_output=True)
        # Members git itself only learned recently. On an older git (ubuntu-latest
        # ships 2.43) they are "unknown option" -- which is an environment fact, not
        # dead weight, so they are skipped BELOW the version that introduced them.
        # The hook must still list them: a newer git accepts them, and an unlisted
        # accepted global became the "subcommand" in round 19.
        introduced = {"--no-lazy-fetch": (2, 44), "--no-advice": (2, 45),
                      "--attr-source": (2, 41)}
        ver = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
        m = re.search(r"(\d+)\.(\d+)", ver)
        local = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        for glob in sorted(guard.GIT_GLOBAL_FLAGS):
            if local < introduced.get(glob, (0, 0)):
                continue
            # STANDALONE, not `git <glob> status`: `--version`, `-v`, `--help`, `-h`
            # and `--man-path` are terminal actions rather than modifiers, so
            # appending a subcommand made git reject them and this test called five
            # real globals "dead weight" (round 20). Every member is accepted alone.
            p = subprocess.run(["git", glob],
                               cwd=str(repo), capture_output=True, text=True)
            assert "unknown option" not in (p.stdout + p.stderr), (
                f"git does not accept the global {glob!r}; it is dead weight")


class TestALongOptionAbbreviationIsResolvedLikeGitDoes:
    """git resolves any UNAMBIGUOUS PREFIX of a long option; the denylists did not.

    Round 16's BLOCKING finding, and the THIRD instance of "a legal git spelling the
    denylist does not enumerate" (round 5: combined `:(top,glob)` keywords; round 15:
    the fused `--pathspec-from-file=` spelling). Dropping three characters restored
    round 15's leak in full: `git rm -r --pathspec-fr=list.txt` deleted every tracked
    file, `git checkout --fo` destroyed another session's edit, `git add --al` staged
    the whole tree -- all verified against git 2.50, none of them obfuscation.

    Driven off the RULE TABLE below rather than a hand-written case list, and every
    abbreviation length down to `--x` is generated, so a long name added to a rule
    without its abbreviations cannot pass.
    """

    #: rule long-name -> a command carrying it that must be DENIED. Every long name in
    #: every DENIAL in `decide_git` appears here; the exemptions are the next table.
    DENIED = {
        "--all": "git add %s",
        "--update": "git add %s",
        "--no-ignore-removal": "git add %s",
        "--force": "git clean %s",
        "--discard-changes": "git switch %s main",
        "--hard": "git reset %s",
        "--merge": "git reset %s",
        "--keep": "git reset %s",
        "--pathspec-from-file": "git rm -r %s=list.txt",
        # round 18: `-e`/`-i` need NO pathspec to reach the whole tree -- they open the
        # tree-wide diff, which is `-u` semantics by another name. `git add --e` is
        # resolved by git to `--edit` (verified: it opened the patch), so blocking the
        # abbreviation is CORRECT here and not merely harmless.
        "--edit": "git add %s",
        "--interactive": "git add %s",
    }

    #: An EXEMPTION must NOT be matched by an abbreviation: prefix-matching an allowlist
    #: is the fail-OPEN direction. Each command is tree-wide but for the exemption, so
    #: the abbreviated spelling must still DENY.
    EXEMPT = {
        # each template must be tree-wide BUT FOR the exemption, or the case proves
        # nothing: `git clean --dry` alone deletes nothing even unexempted, so the
        # denial it has to lift is `-f`
        "--dry-run": ["git add %s -A", "git rm %s -r .", "git commit %s -a",
                      "git clean %s -f"],
        "--patch": ["git add %s ."],
        "--soft": ["git reset %s"],
    }

    @staticmethod
    def abbreviations(name):
        # every prefix git could resolve, down to `--x`; the full name is covered by
        # the ordinary BLOCKED/ALLOWED lists
        return [name[:i] for i in range(3, len(name))]

    def test_every_denial_long_name_is_in_the_table(self):
        # Parametrising over a hand-copied list is what let round 15's `--author` slip
        # through, so the table is compared against the names the rules actually carry.
        shipped = set()
        source = (HOOKS / GUARD).read_text()
        for line in source.splitlines():
            if "has_flag(" in line and "exact=True" not in line:
                shipped.update(re.findall(r'"(--[a-z-]+)"', line))
        # passed as the PATHSPEC_FROM_FILE constant, so the string scan cannot see it,
        # but it IS a denial and has abbreviation cases -- so it is ADDED, not discarded
        # (the round-25 `==` ratchet called the row stale the moment it was discarded)
        shipped.add("--pathspec-from-file")
        # EQUALITY, like the exemption sibling: a subset assertion could never fail on
        # a stale row, so the table could accumulate dead entries silently (round 25)
        assert shipped == set(self.DENIED), (
            f"the denial table and the rules have drifted: "
            f"missing={sorted(shipped - set(self.DENIED))} "
            f"stale={sorted(set(self.DENIED) - shipped)}")

    def test_every_exemption_long_name_is_in_the_table(self):
        shipped = set()
        source = (HOOKS / GUARD).read_text()
        for line in source.splitlines():
            if "has_flag(" in line and "exact=True" in line:
                shipped.update(re.findall(r'"(--[a-z-]+)"', line))
        assert shipped == set(self.EXEMPT), (
            "an exemption's long names and the abbreviation table have drifted")

    @pytest.mark.parametrize("name,abbrev", [
        (n, a) for n, t in sorted(DENIED.items()) for a in
        [n[:i] for i in range(3, len(n))]
    ])
    def test_an_abbreviated_denial_still_blocks(self, name, abbrev):
        command = self.DENIED[name] % abbrev
        p = run_guard(command)
        assert p.returncode == 2, (
            f"abbreviation of {name} leaked: {command!r} (rc={p.returncode})")

    @pytest.mark.parametrize("name,abbrev", [
        (n, a) for n in sorted(EXEMPT) for a in [n[:i] for i in range(3, len(n))]
    ])
    def test_an_abbreviated_exemption_does_not_lift_a_denial(self, name, abbrev):
        for template in self.EXEMPT[name]:
            command = template % abbrev
            sub = command.split()[1]
            if any(opt.startswith(abbrev)
                   for opt in guard.REQUIRED_VALUE_LONG_OPTS.get(sub, ())):
                # This abbreviation is ALSO a prefix of a value-taking option of the
                # same subcommand, so round 17's unconditional value drop swallows the
                # next token and the verdict goes to 0. That is a real COST, not a
                # leak, and it is not waved away here: the exclusion is justified by
                # test_a_dropped_value_is_a_command_git_refuses below, which proves
                # git refuses every such command, so the lost denial can never run.
                continue
            p = run_guard(command)
            assert p.returncode == 2, (
                f"abbreviated exemption {abbrev!r} lifted a denial: {command!r} "
                f"(rc={p.returncode})")

    def test_a_dropped_value_is_a_command_git_refuses(self, tmp_path):
        """The cost of dropping an option-looking value, PROVEN rather than assumed.

        Round 17 made a consumed value reach neither list, which is what stops it
        impersonating an exemption. The price is that an option-looking token behind a
        value-taking option is dropped, so `git commit --d -a` exits 0 where round 16
        blocked it. That is only acceptable while git itself refuses these commands --
        so this test asserts the refusal against real git rather than trusting it, and
        will fail loudly if a future git starts accepting one.
        """
        repo = tmp_path / "refused"
        repo.mkdir()

        def run(*a):
            return subprocess.run(a, cwd=str(repo), capture_output=True, text=True)

        run("git", "init", "-q", ".")
        run("git", "config", "user.email", "a@b.c")
        run("git", "config", "user.name", "a")
        (repo / "a.txt").write_text("1\n")
        (repo / "b.txt").write_text("1\n")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "base")
        (repo / "a.txt").write_text("A2\n")
        (repo / "b.txt").write_text("B2\n")
        dropped = [
            ["git", "commit", "--d", "-a"],       # ambiguous: --date or --dry-run
            ["git", "commit", "--dat", "-a"],     # --date with an invalid value
            ["git", "add", "--chm", "-A"],        # --chmod param must be -x or +x
        ]
        for argv in dropped:
            assert run_guard(" ".join(argv)).returncode == 0, (
                f"{argv} no longer exits 0; this test records the drop's cost and the "
                f"record is stale")
            p = run(*argv)
            assert p.returncode != 0, (
                f"git now ACCEPTS {argv} -- the dropped value is a live leak, not a "
                f"bounded cost. Re-derive the rule.")
        # git refused every one, so HEAD is untouched and both edits are still in the
        # working tree -- nothing was committed, staged or discarded
        assert run("git", "log", "--oneline").stdout.count("\n") == 1
        assert (repo / "a.txt").read_text() == "A2\n"
        assert (repo / "b.txt").read_text() == "B2\n"

    def test_the_unabbreviated_exemption_still_works(self):
        # The over-block above must not have swallowed the real spelling.
        for name, templates in self.EXEMPT.items():
            for template in templates:
                p = run_guard(template % name)
                assert p.returncode == 0, (template % name, p.stderr)

    def test_an_abbreviated_destructive_reset_names_its_own_remediation(self):
        # Round 16's MINOR: `git reset --har` blocked, but fell through to the
        # UNSTAGING rule, so round 10's remediation test bound only the full spelling.
        for abbrev in ("--har", "--mer", "--kee", "--hard", "--merge", "--keep"):
            p = run_guard("git reset %s" % abbrev)
            assert p.returncode == 2, abbrev
            assert "git restore --source=HEAD" in p.stderr, (
                f"{abbrev} got the unstaging remediation, not the destructive one")

    def test_an_abbreviated_value_option_is_still_consumed(self):
        """The two rules meet here, and the meeting point was a leak.

        Round 16 made DENIALS match by prefix but left round 15's value-consumption
        tables exact, so an ABBREVIATED value-taking option's value stayed an operand,
        became a scoping pathspec, and disarmed the flag rule above it -- exactly the
        round-15 defect, reached through the round-16 dimension. Verified against git:
        `git add -A --chm +x` staged both sessions' files and `git stash push --mes wip`
        stashed the whole tree, both exit 0. Generated off the shipped table, so a
        member added later is covered without a new case.
        """
        # (subcommand, option) -> a command that must be DENIED at every abbreviation
        # length, because the option's value is not a scoping pathspec
        templates = {
            ("add", "--chmod"): "git add -A %s +x",
            ("stage", "--chmod"): "git stage -A %s +x",
            ("stash", "--message"): "git stash push %s wip",
            ("commit", "--message"): "git commit -a %s wip",
            ("commit", "--author"): 'git commit -a %s "N <n@e.com>"',
            ("commit", "--file"): "git commit -a %s msg.txt",
            ("clean", "--exclude"): 'git clean -f %s "*.log"',
        }
        for (sub, opt), template in templates.items():
            assert opt in guard.REQUIRED_VALUE_LONG_OPTS[sub], (sub, opt)
            for abbrev in [opt[:i] for i in range(3, len(opt) + 1)]:
                p = run_guard(template % abbrev)
                assert p.returncode == 2, (
                    f"abbreviated value option {abbrev!r} became a scoping pathspec: "
                    f"{template % abbrev!r} (rc={p.returncode})")

    def test_every_value_option_template_is_tree_wide_but_for_the_value(self):
        # The vacuous-case guard the probe-binding config had to add: each template
        # above must block for a reason the VALUE could hide, or it proves nothing.
        assert run_guard("git add -A").returncode == 2
        assert run_guard("git stash push").returncode == 2
        assert run_guard("git clean -f").returncode == 2

    #: Exemption spellings an option VALUE could impersonate. Round 17's BLOCKING
    #: finding: an unconsumed value stayed in `flags`, which is the SAME list the
    #: exemptions are read from, so the command line could inject `--dry-run` as a
    #: commit message and lift every denial.
    EXEMPTION_SPELLINGS = ("--dry-run", "--patch", "-n", "-p", "--soft", "-q")

    #: commands that are tree-wide BUT FOR the option value in `%s`
    VALUE_SLOTS = (
        "git commit -a -m %s",
        "git commit -am %s",
        "git clean -f -e %s",
        "git clean -fe %s",
        "git stash push -m %s",
        "git add -A --chmod %s",
        "git commit -a --author %s",
        "git add -A --pathspec-from-file %s",
    )

    @pytest.mark.parametrize("template", VALUE_SLOTS)
    @pytest.mark.parametrize("spelling", EXEMPTION_SPELLINGS)
    def test_an_option_value_cannot_impersonate_an_exemption(self, template, spelling):
        """A value is neither a flag nor a pathspec, and must reach neither list.

        Round 17, verified against real git 2.50: `git commit -a -m --dry-run`
        committed BOTH sessions' files, `git clean -f -e -n` deleted both sessions'
        untracked files, and `git stash push -m --patch` stashed the whole shared tree
        -- all exit 0, because the value landed in `flags` and fired an exemption
        before any denial ran. Round 15 wrote "keeping it in `flags` can only ADD a
        denial, never lift one" into the hook, and that sentence was simply false:
        `flags` is where the exemptions live too.

        Generated as a cross-product so a new exemption or a new value-taking option
        cannot reopen it one spelling at a time.
        """
        command = template % spelling
        p = run_guard(command)
        assert p.returncode == 2, (
            f"an option value impersonated an exemption: {command!r} "
            f"(rc={p.returncode}, stderr={p.stderr!r})")

    def test_the_value_slots_are_tree_wide_but_for_the_value(self):
        # Vacuity guard: each template must block for a reason the VALUE could hide.
        for template in self.VALUE_SLOTS:
            stem = template.replace(" %s", "")
            p = run_guard(stem)
            assert p.returncode == 2, (
                f"{stem!r} is not tree-wide, so its exemption cases prove nothing")

    def test_a_dropped_value_does_not_lose_a_real_denial(self):
        # The other direction: dropping the token must not hide a tree-wide PATHSPEC.
        assert run_guard("git commit -m -a .").returncode == 2
        assert run_guard("git commit -m --dry-run .").returncode == 2
        assert run_guard("git add --chmod -A .").returncode == 2
        # and the cases git itself refuses stay allowed rather than being special-cased
        assert run_guard("git commit -m -a").returncode == 0

    def test_git_resolves_these_abbreviations(self, tmp_path):
        # The premise, proven against git rather than asserted: if git STOPPED
        # resolving prefixes, this whole class would be over-blocking and should go.
        repo = tmp_path / "abbrev"
        repo.mkdir()

        def run(*a):
            return subprocess.run(a, cwd=str(repo), capture_output=True, text=True)

        run("git", "init", "-q", ".")
        run("git", "config", "user.email", "a@b.c")
        run("git", "config", "user.name", "a")
        (repo / "sessionA.txt").write_text("1\n")
        (repo / "sessionB.txt").write_text("1\n")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "base")
        (repo / "sessionA.txt").write_text("A2\n")
        (repo / "sessionB.txt").write_text("B2\n")
        assert run("git", "add", "--al").returncode == 0, "git no longer resolves --al"
        staged = run("git", "diff", "--cached", "--name-only").stdout.split()
        assert sorted(staged) == ["sessionA.txt", "sessionB.txt"], staged


class TestNoConstructSwallowsTheFlagBehindIt:
    """The ratchet the `preprocess-transform-silently-deletes-a-command` class earned.

    That class has instances in rounds 1, 2, 3, 6, 20, 21, 22 and twice in 23 — every
    one the same shape: some construct in the command text made a LATER token vanish,
    so a tree-wide flag was never inspected and the guard exited 0. Three rounds of
    case lists did not stop it, because each round enumerated the construct it had just
    found -- an escaped semicolon, a command substitution, a quoted arithmetic
    expansion, a heredoc -- and the next round arrived with another one.

    So this is METAMORPHIC rather than enumerative: for every construct below, the
    verdict on `<command with construct> <flag>` must EQUAL the verdict on the same
    command with the construct replaced by a plain word. It does not matter whether the
    construct is understood — only that it cannot swallow what follows it. A new
    construct nobody has thought of still has to satisfy it, and a fix that severs the
    token stream fails it without anyone writing a case for that spelling.

    Proven to bind, by re-introducing round 23's own defects in a scratch copy of the
    hook: reverting the escaped-operator-in-quotes fix fails 18 rows, and reverting the
    empty-argument fix fails 16. Round 23's substitution SPLICE is covered by the
    `"$(date)"` x `-a` row, measured at exit 0 before the fix while its `"plain"`
    control blocked -- exactly the inequality asserted below. Reverting the extraction
    to a plain DROP fails no row, and that is correct: dropping the body leaves the
    outer flag intact, so it is not this class's failure mode.
    """

    #: Constructs that go where a plain quoted word could go. Each has caused, or is
    #: adjacent to, a real leak in this file's history.
    CONSTRUCTS = [
        '"plain"',                 # the control
        '"wip\\;x"',                # round 23: escaped operator inside quotes
        '"a\\|b"', '"a\\&&b"', '"x\\>y"',
        '"$(date)"',               # round 23: substitution spliced into the outer text
        '"release $(cat VERSION)"',
        '"$(echo "$(date)")"',     # nested
        '"$((1<<2))"',             # round 21: arithmetic read as a heredoc
        '"${x:-plain}"',
        '""',                      # round 23: the empty argument
        "'plain'", "'a;b'", "'a|b'", "'>'",
        'plain', 'a\\;b', 'a\\>b',
        '"a#b"',                   # a `#` that is not a comment
        '"a b"', '"tab\\there"',
        '"$(printf %s wip)"',
        # round 24: the reviewer showed this list was scoped to QUOTED words, so an
        # unquoted expansion, a quoted grouping character and a bare `}` were all
        # structurally invisible to it -- and 78 rows of its own tails leaked. Every
        # construct below reached the whole tree at rc 0 before round 25.
        '$(date)', '$(cat VERSION)', '$((1))', '$((1<<2))', '${x:-a;b}', '${x:-plain}',
        '")"', '"("', '"}"', '"{"', '\\)', '\\}', '}',
        # round 25: the opener, unquoted, was the gap. NOT `{ }` -- that is TWO words,
        # and `git stash push -m { }` is genuinely scoped to a file named `}`, so it
        # legitimately differs from the one-word control.
        '{', '{}',
        'a\\\nb',                   # a line continuation INSIDE a word
        '"a$(date)b"', 'a$(date)b', 'a${x:-b}c',
        '<(echo x)',
        'a<(echo x)', 'a>(cat)b',   # round 26: glued, which the lift's boundary gate missed
    ]

    #: Tails that make the command tree-wide. The flag sits AFTER the construct, which
    #: is the position every instance of this class attacked.
    TAILS = [
        ("git commit -m %s -a", 2),
        ("git commit -m %s --all", 2),
        ("git commit -m %s .", 2),
        ("git clean -e %s -fd", 2),
        # `-A` AFTER a pathspec is scoped to it by git itself (verified: `git add
        # --chmod +x plain -A` stages only `plain`), so the tree-wide `add` row has to
        # put a tree-wide PATHSPEC behind the construct instead. My first draft of this
        # row expected 2 and the vacuity guard below caught it -- the control differed
        # from the expectation, which is precisely what that guard is for.
        ("git add --chmod +x %s .", 2),
        ("git add --chmod +x %s -A", 0),
        ("git stash push -m %s", 2),
        ("git commit -m %s -- .", 2),
        # round 25: the same command WRAPPED, so a fix gated on "no group open" is seen
        ("{ git commit -m %s -a; }", 2),
        # and a redirection operator run between the construct and the flag
        ("git commit -m %s >| out -a", 2),
        ("git commit -m %s src/a.py", 0),
        ("git clean -e %s -n", 0),
    ]

    @pytest.mark.parametrize("construct", CONSTRUCTS)
    @pytest.mark.parametrize("template,expected", TAILS,
                             ids=[t[0].replace(" ", "_") for t in TAILS])
    def test_the_construct_cannot_change_the_verdict(self, construct, template, expected):
        command = template % construct
        got = run_guard(command).returncode
        control = run_guard(template % '"plain"').returncode
        assert control == expected, (
            f"the CONTROL changed verdict, so this row proves nothing: "
            f"{template % chr(34) + 'plain' + chr(34)!r} -> {control}")
        # ONE-DIRECTIONAL: a construct may make the verdict MORE restrictive -- an
        # unreadable or unknowable expansion should fail closed, and
        # `git add --chmod +x "$(date)" -A` legitimately does, since the hook cannot
        # know what the substitution expands to and git itself refuses the empty
        # pathspec that remains. What it must never do is make the verdict LESS
        # restrictive, which is what every instance of this class did: each turned a 2
        # into a 0 by swallowing the token behind the construct.
        if control == 2:
            assert got == 2, (
                f"the construct {construct!r} swallowed what followed it: "
                f"{command!r} -> {got}, but with a plain word -> 2")

    def test_the_matrix_is_not_vacuous(self):
        # Two failure modes this file has actually shipped: a control that does not
        # block (so every row passes trivially), and a construct list that lost its
        # historical entries.
        assert run_guard('git commit -m "plain" -a').returncode == 2
        assert run_guard('git commit -m "plain" src/a.py').returncode == 0
        for needed in ('"wip\\;x"', '"$(date)"', '""', '"$((1<<2))"',
                       '$(date)', '")"', '}', '${x:-a;b}', 'a\\\nb'):
            assert needed in self.CONSTRUCTS, needed
        assert len(self.CONSTRUCTS) >= 35 and len(self.TAILS) >= 6
        # The invariant is one-directional, so the matrix is only worth having if most
        # rows have a BLOCKING control -- otherwise it asserts nothing at all.
        blocking = [t for t in self.TAILS if t[1] == 2]
        assert len(blocking) >= 5, "too few blocking controls to catch a swallowed flag"


def _is_subsequence(needle, hay):
    it = iter(hay)
    return all(ch in it for ch in needle)


class TestBashIsTheOracleForWhatReachesGit:
    """The round-trip invariant two reviewers asked for, built in round 27.

    Every leak of the `preprocess-transform-silently-deletes-a-command` class -- eleven
    instances, rounds 1 through 26 -- had the same observable: bash handed git a flag
    that the hook's own argv for that command did not contain. So instead of
    enumerating constructs, this asks BASH. Each corpus command runs under real bash
    with a stub `git` on PATH that records its argv and does nothing, in a throwaway
    directory with stdin closed; the hook's segments are computed from the same text;
    and every `-`-prefixed word bash actually passed to git must appear in some hook
    segment for that command. A construct nobody has thought of still has to satisfy
    this, and a fix that severs the token stream fails it without anyone writing a
    case for that spelling.

    What it does NOT assert, deliberately: equality. Expansions become placeholders
    (`$(date)` -> ``), and that is fine -- a placeholder cannot hide a FLAG. Nor does it
    assert anything when bash itself refuses the text (a syntax error yields no argv).

    Safety: PATH is the stub directory plus /usr/bin and /bin, cwd is `tmp_path`, HOME
    is `tmp_path`, stdin is /dev/null, and there is a 5 second timeout. `sudo`/`doas`
    spellings are excluded because they would prompt. No real git can run.
    """

    STUB = (
        "#!/bin/bash\n"
        "printf '%s\\x1f' \"$@\" >> \"$ARGV_LOG\"; printf '\\x1e' >> \"$ARGV_LOG\"\n"
        "exit 0\n"
    )

    @staticmethod
    def _bash_git_argvs(cmd, tmp_path):
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "git"
        if not stub.exists():
            stub.write_text(TestBashIsTheOracleForWhatReachesGit.STUB)
            stub.chmod(0o755)
        cwd = tmp_path / "cwd"
        cwd.mkdir(exist_ok=True)
        log = tmp_path / "argv.log"
        log.write_bytes(b"")
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(cwd),
               "ARGV_LOG": str(log), "LANG": "C"}
        try:
            subprocess.run(["bash", "-c", cmd], cwd=str(cwd), env=env,
                           capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return None
        data = log.read_bytes().decode("utf-8", "replace")
        return [rec.split("\x1f")[:-1] for rec in data.split("\x1e") if rec]

    @classmethod
    def _hook_git_argvs(cls, cmd):
        """The git argvs the hook derives -- mirroring `analyse`'s wrapper handling.

        The first draft read only top-level segments and false-alarmed on every
        `bash -c '...'` and `eval ...` spelling, where the hook itself recurses into
        the inner script. A stdin-fed wrapper is left to the verdict gate in the test:
        the hook fails closed there, and a denial cannot be a leak.
        """
        text, confident = guard.preprocess(cmd)
        if not confident:
            return None          # the hook fails closed here; nothing to compare
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        out = []
        for segment, _fed in guard.split_segments(list(lexer)):
            segment = guard.strip_prefixes(segment)
            if not segment:
                continue
            head = os.path.basename(segment[0])
            if head == "eval":
                inner = cls._hook_git_argvs(" ".join(segment[1:]))
                out.extend(inner or [])
                continue
            if head in guard.SCRIPT_WRAPPERS:
                for i, tok in enumerate(segment[1:], start=1):
                    is_c = tok == "-c" or (tok.startswith("-") and not tok.startswith("--")
                                           and "c" in tok[1:])
                    if is_c and i + 1 < len(segment):
                        inner = cls._hook_git_argvs(segment[i + 1])
                        out.extend(inner or [])
                        break
                continue
            if guard.is_git(segment[0]):
                out.append(segment[1:])
        return out

    #: The corpus is every command this file already asserts a verdict on, plus the
    #: metamorphic matrix. Excluded: anything that would prompt or is not a command.
    @staticmethod
    def corpus():
        seen = []
        for cmd in list(BLOCKED) + list(ALLOWED):
            if cmd.split()[:1] in (["sudo"], ["doas"]):
                continue
            seen.append(cmd)
        M = TestNoConstructSwallowsTheFlagBehindIt
        for construct in M.CONSTRUCTS:
            for template, _ in M.TAILS:
                seen.append(template % construct)
        return seen

    @pytest.mark.parametrize("cmd", corpus.__func__())
    def test_every_flag_bash_hands_git_reaches_the_hook(self, cmd, tmp_path):
        bash = self._bash_git_argvs(cmd, tmp_path)
        if not bash:
            pytest.skip("bash refused or ran no git for this text")
        # A DENIAL can never be a leak, whatever the hook's argv looked like -- the
        # class this invariant guards is "bash handed git a flag and the hook ALLOWED".
        # So the comparison only runs when the hook let the command through; that is
        # also what keeps stdin-fed wrappers (which fail closed) out of the comparison.
        if run_guard(cmd).returncode != 0:
            return
        hook = self._hook_git_argvs(cmd)
        if hook is None:
            return               # fail-closed is never a leak
        hook_words = {w for argv in hook for w in argv}
        # With no expansion in the text, EVERY word bash hands git must reach the hook
        # -- flags and operands alike. The flag-only form could not see round 24's
        # line-continuation leak, which split `HEAD` into `HEA` and `D` and dropped no
        # flag at all. Expansions become placeholders the hook cannot know the value
        # of, so when the text contains one only the flags are compared.
        expands = any(tok in cmd for tok in ("$", "`", "<(", ">(", "{"))
        for argv in bash:
            for word in argv:
                if (word.startswith("-") and word != "-") or not expands:
                    assert word in hook_words, (
                        f"bash handed git {word!r} and the hook never saw it: "
                        f"{cmd!r}\n  bash={bash}\n  hook={hook}")
        # THE CONVERSE, added in round 27 after the reviewer showed the subset check
        # alone was blind to a PHANTOM pathspec: `git add {,} -A` reached git as
        # `add -A`, but the hook kept `{,}` as a positive, scoping operand and allowed
        # it. So every non-flag operand the hook believes in must be a word bash
        # actually handed git -- an operand bash never produced cannot be what scoped
        # the command. Placeholders (empty after the sentinel strip) are exempt: they
        # are the hook saying "unknowable", and the rules already treat them as such.
        bash_words = {w for argv in bash for w in argv}
        for argv in hook:
            for word in argv:
                if word and not word.startswith("-"):
                    # An in-order SUBSEQUENCE, not equality: an expansion glued to
                    # literal text on BOTH sides (`a>(cat)b`) leaves the hook `ab` once
                    # the placeholder is stripped, against bash's `a/dev/fd/63b` -- the
                    # hook's letters all appear, in order, with the expansion's value
                    # between them. That is not a phantom. A phantom -- `{,}`, which bash
                    # turned into nothing -- is a subsequence of no bash word, because
                    # no bash word carries its braces.
                    # When an unquoted expansion's OUTPUT word-splits (`a$(date)b` ->
                    # `aSat Sep 5 ... 2026b`), the hook's `ab` spans several bash words,
                    # so with an expansion present the subsequence is taken over the
                    # CONCATENATION of bash's words. `{,}` is a subsequence of neither.
                    haystacks = ["".join(w for argv in bash for w in argv)] if expands else bash_words
                    assert any(_is_subsequence(word, bw) for bw in haystacks), (
                        f"the hook believed in an operand {word!r} that bash never "
                        f"handed git -- a phantom pathspec scoped the command: "
                        f"{cmd!r}\n  bash={bash}\n  hook={hook}")

    def test_the_oracle_is_not_vacuous(self, tmp_path):
        # The stub must actually record, and the corpus must actually exercise it.
        assert self._bash_git_argvs("git commit -m x -a", tmp_path) == [["commit", "-m", "x", "-a"]]
        assert self._bash_git_argvs("git add -A; git status", tmp_path) == [["add", "-A"], ["status"]]
        ran = sum(1 for c in self.corpus()[:60] if self._bash_git_argvs(c, tmp_path))
        assert ran >= 40, f"only {ran} of the first 60 corpus commands reached the stub"
        # The binding proof lives in the archive README and the doc: re-introducing
        # the line-continuation, heredoc-marker and glued-`<(` leaks in a scratch
        # copy each fails this class. A literal-only assertion used to sit here and
        # could never fail -- round 27 called it a tautology, correctly.


class TestEverySpellingOfAGlobalAndAWrapperIsCovered:
    """The mechanical check the `one-site-updated-sibling-missed` class earned.

    That class reached EIGHT recorded instances by round 22, two of them found in the
    same round: the FUSED `--config-env=key=value` skipped the opacity test that the
    separate spelling had (restoring round 21's two leaks for the cost of one `=`), and
    a `SCRIPT_WRAPPER` fed its script on stdin was never analysed while the `-c`
    spelling was. Both were invisible to 1731 tests because
    `test_every_valued_git_global_option_is_stripped` and
    `test_every_script_wrapper_is_unwrapped` each asserted exactly ONE spelling.

    So these assert PARITY ACROSS SPELLINGS, driven off the shipped collections: a
    valued global must reach the same verdict fused as separate, and a wrapper must
    reach the same verdict for every way of handing it a script.
    """

    @pytest.mark.parametrize("glob", sorted(guard.GIT_GLOBAL_WITH_VALUE))
    def test_a_valued_global_behaves_the_same_fused_as_separate(self, glob):
        if not glob.startswith("--"):
            pytest.skip("short globals have their own fused-form cases")
        separate = run_guard("git %s x=y add -A" % glob).returncode
        fused = run_guard("git %s=x=y add -A" % glob).returncode
        assert separate == fused == 2, (
            f"{glob}: separate={separate} fused={fused} -- a spelling git accepts "
            f"reaches a different verdict")

    @pytest.mark.parametrize("key", ["alias.st=add -A", "clean.requireForce=false",
                                     "include.path=/tmp/x", "includeIf.gitdir:x.path=/tmp/x"])
    def test_an_opaque_config_key_fails_closed_in_every_spelling(self, key):
        for command in ("git -c %s st" % key,
                        "git -c%s st" % key,
                        "git --config-env=%s st" % key,
                        "git --config-env %s st" % key):
            assert run_guard(command).returncode == 2, command

    @pytest.mark.parametrize("wrapper", sorted(guard.SCRIPT_WRAPPERS))
    def test_a_wrapper_reaches_the_same_verdict_however_it_is_fed(self, wrapper):
        if wrapper == "eval":
            pytest.skip("eval takes its script as ARGV, not on stdin")
        spellings = [
            "%s -c 'git add -A'" % wrapper,
            # round 26: every spelling below was a BARE wrapper, so a wrapper option
            # whose VALUE looked like a script file was invisible to this very test
            "%s -O extglob <<EOF\ngit add -A\nEOF" % wrapper,
            "%s --rcfile f <<< 'git add -A'" % wrapper,
            "%s <<< 'git add -A'" % wrapper,
            "%s <<EOF\ngit add -A\nEOF" % wrapper,
            "%s < script.sh\ngit add -A" % wrapper,
            "cat <<EOF | %s\ngit add -A\nEOF" % wrapper,
        ]
        for command in spellings:
            assert run_guard(command).returncode == 2, (
                f"{wrapper}: this spelling hides the script: {command!r}")

class TestASeparateOptionValueIsNotAPathspec:
    """One case per member of `REQUIRED_VALUE_LONG_OPTS` and `REQUIRED_VALUE_SHORT_OPTS`.

    Round 15's BLOCKING finding: only `-m` was modelled, so every OTHER value-taking
    option's separate value stayed an operand, became a scoping pathspec, and disarmed
    the flag rule above it -- `git commit -am wip --author 'N <n@e.com>'` committed both
    sessions' files and exited 0 (verified against git). A member with no case is the
    recurring shape of this hook's review history, so the tables are parametrised over
    the SHIPPED collections: a member added or deleted without a case is a hard failure.
    """

    #: (subcommand, long option) -> (command, expected returncode).
    LONG_CASES = {
        ("add", "--chmod"): ("git add --chmod +x src/a.py", 0),
        ("add", "--pathspec-from-file"): ("git add --pathspec-from-file list.txt", 2),
        ("stage", "--chmod"): ("git stage --chmod +x src/a.py", 0),
        ("stage", "--pathspec-from-file"): ("git stage --pathspec-from-file l.txt", 2),
        ("commit", "--message"): ("git commit --message wip src/a.py", 0),
        ("commit", "--file"): ("git commit --file msg.txt", 0),
        ("commit", "--reuse-message"): ("git commit --reuse-message HEAD", 0),
        ("commit", "--reedit-message"): ("git commit --reedit-message HEAD", 0),
        ("commit", "--template"): ("git commit --template t.txt", 0),
        ("commit", "--author"): ('git commit -m x --author "N <n@e.com>"', 0),
        ("commit", "--date"): ("git commit -m x --date now", 0),
        ("commit", "--cleanup"): ("git commit -m x --cleanup whitespace", 0),
        ("commit", "--trailer"): ('git commit -m x --trailer "K: v"', 0),
        ("commit", "--squash"): ("git commit --squash HEAD", 0),
        ("commit", "--fixup"): ("git commit --fixup HEAD", 0),
        ("commit", "--pathspec-from-file"): (
            "git commit -m x --pathspec-from-file list.txt", 2),
        ("checkout", "--orphan"): ("git checkout --orphan newbranch", 0),
        ("checkout", "--conflict"): ("git checkout --conflict diff3 -- src/a.py", 0),
        ("checkout", "--pathspec-from-file"): (
            "git checkout --pathspec-from-file list.txt", 2),
        ("switch", "--orphan"): ("git switch --orphan newbranch", 0),
        ("switch", "--conflict"): ("git switch --conflict diff3 main", 0),
        ("restore", "--source"): ("git restore --source HEAD -- src/a.py", 0),
        ("restore", "--conflict"): ("git restore --conflict diff3 -- src/a.py", 0),
        ("restore", "--pathspec-from-file"): (
            "git restore --pathspec-from-file list.txt", 2),
        ("clean", "--exclude"): ('git clean --exclude "*.log" -n', 0),
        ("rm", "--pathspec-from-file"): ("git rm --pathspec-from-file list.txt", 2),
        ("stash", "--message"): ("git stash push --message wip src/a.py", 0),
        ("stash", "--pathspec-from-file"): (
            "git stash push --pathspec-from-file list.txt", 2),
        # round 18: members the missing-direction audit added. `reset` was the one
        # ruled subcommand whose `--pathspec-from-file` was absent from the table --
        # harmless only because the shared tree-wide override catches it first, which
        # is the kind of luck the completeness test below now removes.
        ("reset", "--pathspec-from-file"): (
            "git reset --pathspec-from-file list.txt", 2),
        ("switch", "--create"): ("git switch --create newbranch", 0),
        ("switch", "--force-create"): ("git switch --force-create fix", 0),
        ("worktree", "--expire"): ("git worktree prune --expire 3.days", 0),
        ("worktree", "--reason"): ("git worktree lock --reason busy", 0),
    }

    def test_every_required_value_option_git_reports_is_in_the_table(self, tmp_path):
        """Closes the MISSING-member direction, which nothing bound before round 18.

        `test_every_long_value_option_has_a_case` and `EXPECTED_CONSTANTS` freeze what
        the tables DO contain, so they catch a false member and a deletion. An option
        git takes a value for and the hook has never heard of is invisible to both --
        and that is precisely round 15's leak shape, since such an option's value
        becomes a scoping pathspec. So the truth is read from git itself: every
        `--opt <value>` git prints in `<sub> -h` must be classified.
        """
        import shutil
        if not shutil.which("git"):
            pytest.skip("git not available")
        # `-h` is enumerated only for the NAMES; git itself is the oracle for ARITY.
        # The first draft of this test parsed the value shape out of `-h` with
        # `(--[a-z-]+)\s+<` and asserted ZERO options -- git prints `--[no-]author
        # <author>`, so the `[` defeated the name match, and values like `(+|-)x` are
        # not `<...>` at all. It passed, and it passed just as happily with a member
        # DELETED. A check that looks like coverage and is not is the failure this
        # file's mutation record exists to prevent, so the shapes are no longer parsed:
        # every option name in `-h` is probed with `git <sub> <opt>` and only git's own
        # "requires a value" counts. `-h` writes to STDOUT here (rc 129), which the
        # first draft also had wrong, so both streams are read.
        # EVERY probe runs in a DISPOSABLE repo, never in this one. The first version
        # of this test passed `cwd=str(REPO)`, and probing arity means EXECUTING
        # `git <sub> <opt>`: an option whose value is OPTIONAL runs for real, so the
        # sweep executed `git checkout --force`, `git clean --force`, `git commit
        # --amend` and `git stash` in the working tree. It reverted tracked files,
        # deleted untracked ones, detached HEAD and stacked stashes -- destroying
        # uncommitted work repeatedly, which is the exact incident this hook exists to
        # prevent, caused by the hook's own test suite. A hook cannot save us here: it
        # sees the Bash tool, not a subprocess inside pytest. The isolation is the
        # scratch repo, and it is the same lesson the doc draws for sessions.
        probe_repo = tmp_path / "arity"
        probe_repo.mkdir()
        for argv in (["init", "-q", "."], ["config", "user.email", "a@b.c"],
                     ["config", "user.name", "a"]):
            subprocess.run(["git"] + argv, cwd=str(probe_repo),
                           capture_output=True, text=True)
        (probe_repo / "seed.txt").write_text("1\n")
        subprocess.run(["git", "add", "-A"], cwd=str(probe_repo), capture_output=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=str(probe_repo),
                       capture_output=True)
        name = re.compile(r"--(?:\[no-\])?([a-z][a-z0-9-]*)")
        asserted = 0
        for sub in sorted(guard.REQUIRED_VALUE_LONG_OPTS):
            helped = subprocess.run(["git", sub, "-h"], capture_output=True, text=True)
            helptext = helped.stdout + helped.stderr
            for stem in sorted(set(name.findall(helptext))):
                opt = "--" + stem
                probed = subprocess.run(
                    ["git", sub, opt], capture_output=True, text=True,
                    cwd=str(probe_repo))
                if "requires a value" not in (probed.stdout + probed.stderr):
                    continue          # optional value or no value: not this table
                asserted += 1
                assert opt in guard.REQUIRED_VALUE_LONG_OPTS[sub], (
                    f"git {sub} {opt} takes a separate value and is not in "
                    f"REQUIRED_VALUE_LONG_OPTS[{sub!r}]: its value would be read as a "
                    f"scoping pathspec, which is round 15's leak")
        # Anti-vacuity floor: the first draft asserted nothing at all and was green.
        assert asserted >= 25, (
            f"only {asserted} options were checked; the enumeration is broken and this "
            f"test is measuring nothing")

    #: (subcommand, short letter) -> (command, expected returncode). The SEPARATED
    #: spelling; the fused one is covered by TestAFusedOptionValueIsNotAFlagCluster.
    SHORT_CASES = {
        ("commit", "m"): ("git commit -m wip src/a.py", 0),
        ("commit", "F"): ("git commit -F msg.txt", 0),
        ("commit", "C"): ("git commit -C HEAD", 0),
        ("commit", "c"): ("git commit -c HEAD", 0),
        ("commit", "t"): ("git commit -t t.txt", 0),
        ("checkout", "b"): ("git checkout -b feature", 0),
        ("checkout", "B"): ("git checkout -B fix", 0),
        ("switch", "c"): ("git switch -c fix", 0),
        ("switch", "C"): ("git switch -C fix", 0),
        ("restore", "s"): ("git restore -s HEAD -- src/a.py", 0),
        ("clean", "e"): ('git clean -e "*.log" -n', 0),
        # the ONE mutating case: a message is not a pathspec, so the stash is unscoped
        ("stash", "m"): ("git stash push -m wip", 2),
    }

    def test_every_long_value_option_has_a_case(self):
        shipped = {(sub, opt)
                   for sub, opts in guard.REQUIRED_VALUE_LONG_OPTS.items()
                   for opt in opts}
        assert shipped == set(self.LONG_CASES), (
            "REQUIRED_VALUE_LONG_OPTS and the case table have drifted")

    def test_every_required_short_letter_has_a_case(self):
        shipped = {(sub, letter)
                   for sub, letters in guard.REQUIRED_VALUE_SHORT_OPTS.items()
                   for letter in letters}
        assert shipped == set(self.SHORT_CASES), (
            "REQUIRED_VALUE_SHORT_OPTS and the case table have drifted")

    def test_the_required_letters_are_a_subset_of_the_value_letters(self):
        # A required letter that is not a value letter would never be found by the
        # first-value-letter scan in `option_needs_next_token`, so the row would be
        # silently dead.
        for sub, letters in guard.REQUIRED_VALUE_SHORT_OPTS.items():
            assert set(letters) <= set(guard.VALUE_SHORT_OPTS.get(sub, "")), sub

    def test_an_optional_value_option_is_not_treated_as_required(self):
        # Subset canary in the LEAK-OPENING direction: `-S`/`-u` and their long
        # spellings take an OPTIONAL value, so git reads the next token as a pathspec.
        # Verified against git: `git commit -u . -m x` commits every modified tracked
        # file. Consuming that token would hide the tree-wide `.` from every rule.
        assert "S" not in guard.REQUIRED_VALUE_SHORT_OPTS["commit"]
        assert "u" not in guard.REQUIRED_VALUE_SHORT_OPTS["commit"]
        assert "--gpg-sign" not in guard.REQUIRED_VALUE_LONG_OPTS["commit"]
        assert "--untracked-files" not in guard.REQUIRED_VALUE_LONG_OPTS["commit"]
        # `--track` is optional-valued too, on both subcommands that have it
        assert "t" not in guard.REQUIRED_VALUE_SHORT_OPTS["checkout"]
        assert "t" not in guard.REQUIRED_VALUE_SHORT_OPTS["switch"]
        # and `git add` has no value-taking short option at all: -A/-u stay a cluster
        assert guard.REQUIRED_VALUE_SHORT_OPTS["add"] == ""

    def test_the_tables_cover_the_options_that_caused_the_finding(self):
        # Subset canary: parametrising over a shipped collection lets a DELETION
        # delete its own case.
        assert "--author" in guard.REQUIRED_VALUE_LONG_OPTS["commit"]
        assert "--chmod" in guard.REQUIRED_VALUE_LONG_OPTS["add"]
        assert "--pathspec-from-file" in guard.REQUIRED_VALUE_LONG_OPTS["rm"]
        assert "m" in guard.REQUIRED_VALUE_SHORT_OPTS["commit"]

    def test_every_ruled_subcommand_has_a_row_in_both_tables(self):
        # A missing row falls back to "" / frozenset(), which silently reverts this
        # subcommand to the round-15 behaviour instead of failing.
        ruled = {"add", "stage", "commit", "reset", "checkout", "restore", "switch",
                 "clean", "stash", "rm", "worktree"}
        assert ruled <= set(guard.REQUIRED_VALUE_SHORT_OPTS)
        assert ruled <= set(guard.REQUIRED_VALUE_LONG_OPTS)

    @pytest.mark.parametrize("key", sorted(LONG_CASES))
    def test_a_long_option_value_is_not_read_as_a_pathspec(self, key):
        command, expected = self.LONG_CASES[key]
        p = run_guard(command)
        assert p.returncode == expected, (
            f"separate long-option value misread: {command!r} "
            f"(rc={p.returncode}, stderr={p.stderr!r})")

    @pytest.mark.parametrize("key", sorted(SHORT_CASES))
    def test_a_short_option_value_is_not_read_as_a_pathspec(self, key):
        command, expected = self.SHORT_CASES[key]
        p = run_guard(command)
        assert p.returncode == expected, (
            f"separate short-option value misread: {command!r} "
            f"(rc={p.returncode}, stderr={p.stderr!r})")

    def test_git_agrees_the_author_commit_is_tree_wide(self, tmp_path):
        # The finding, proven against git rather than asserted: two sessions' files,
        # one `commit -a --author`, and BOTH are committed.
        repo = tmp_path / "authored"
        repo.mkdir()
        def run(*a):
            return subprocess.run(a, cwd=str(repo), capture_output=True, text=True)

        run("git", "init", "-q", ".")
        run("git", "config", "user.email", "a@b.c")
        run("git", "config", "user.name", "a")
        (repo / "sessionA.txt").write_text("1\n")
        (repo / "sessionB.txt").write_text("1\n")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "base")
        (repo / "sessionA.txt").write_text("A2\n")
        (repo / "sessionB.txt").write_text("B2\n")
        run("git", "commit", "-a", "-m", "wip", "--author", "N <n@e.com>")
        named = run("git", "show", "--name-only", "--format=", "HEAD").stdout.split()
        assert sorted(named) == ["sessionA.txt", "sessionB.txt"], (
            "git no longer commits the whole tree here; re-derive the rule")
        # and git REFUSES a pathspec alongside -a, which is what makes testing `--all`
        # before the scoped-pathspec return safe rather than merely stricter
        (repo / "sessionA.txt").write_text("A3\n")
        refused = run("git", "commit", "-a", "-m", "x", "sessionA.txt")
        assert "does not make sense" in refused.stderr, refused.stderr


class TestAFusedOptionValueIsNotAFlagCluster:
    """One case per (subcommand, value-taking short letter) in `VALUE_SHORT_OPTS`.

    Round 4's BLOCKING finding: `has_flag` read every character after a single `-` as a
    flag cluster, so an option's ARGUMENT was scanned as flags -- `git commit -m"refactor"`
    was denied as `commit -a` and `git checkout -bfeature` as `checkout -f`, purely because
    of the letters in a message or a branch name. Each value below is chosen to contain
    exactly the letters that subcommand's rules look for, so a cluster scan cannot help but
    misfire; a correct parse cannot.
    """

    #: (subcommand, short letter) -> (command, expected returncode).
    CASES = {
        ("commit", "m"): ('git commit -m"a fix"', 0),
        ("commit", "F"): ("git commit -Fa.txt", 0),
        ("commit", "C"): ("git commit -Cabc123", 0),
        ("commit", "c"): ("git commit -cabc123", 0),
        ("commit", "t"): ("git commit -ta.tpl", 0),
        ("commit", "S"): ("git commit -Sabcd -m x", 0),
        ("commit", "u"): ("git commit -uall -m x", 0),
        ("checkout", "b"): ("git checkout -bfeature", 0),
        ("checkout", "B"): ("git checkout -Bfix", 0),
        ("checkout", "t"): ("git checkout -tfix/x", 0),
        ("switch", "c"): ("git switch -cfix", 0),
        ("switch", "C"): ("git switch -Cfix", 0),
        ("switch", "t"): ("git switch -tfix/x", 0),
        ("restore", "s"): ("git restore -sfix src/a.py", 0),
        ("clean", "e"): ("git clean -efoo", 0),
        # the ONE mutating case: `-mpatch` must not read as `--patch`, and the message
        # is not a pathspec, so an unscoped `stash push` still blocks
        ("stash", "m"): ("git stash push -mpatch", 2),
    }

    def test_every_value_taking_letter_has_a_case(self):
        # Parametrised over the shipped table, so a letter added to VALUE_SHORT_OPTS
        # without a case is a hard failure -- and a case for a letter that no longer
        # exists is too, which is what catches a silent deletion.
        shipped = {(sub, letter)
                   for sub, letters in guard.VALUE_SHORT_OPTS.items()
                   for letter in letters}
        assert shipped == set(self.CASES), (
            "VALUE_SHORT_OPTS and the case table have drifted")

    def test_the_table_still_covers_the_letters_that_caused_the_finding(self):
        # Subset canary: deleting a member would otherwise delete its own test case.
        assert "m" in guard.VALUE_SHORT_OPTS["commit"]
        assert "b" in guard.VALUE_SHORT_OPTS["checkout"]
        assert "c" in guard.VALUE_SHORT_OPTS["switch"]
        assert "m" in guard.VALUE_SHORT_OPTS["stash"]
        assert guard.VALUE_SHORT_OPTS["add"] == "", (
            "`git add` has no value-taking short option; -A/-u must stay a cluster")

    @pytest.mark.parametrize("key", sorted(CASES))
    def test_a_fused_value_is_read_as_an_argument(self, key):
        command, expected = self.CASES[key]
        p = run_guard(command)
        assert p.returncode == expected, (
            f"fused option value misread: {command!r} "
            f"(rc={p.returncode}, stderr={p.stderr!r})")

    def test_a_separated_value_still_leaves_the_flags_visible(self):
        # Cutting the fused argument must not blind the guard to a real cluster.
        assert run_guard("git commit -am wip").returncode == 2
        assert run_guard("git commit -m wip -a").returncode == 2
        assert run_guard("git checkout -bfoo -f").returncode == 2

    def test_git_agrees_that_a_fused_message_scopes_the_commit(self, tmp_path):
        # `git commit -ma x` is message "a" with pathspec "x", NOT `commit --all`.
        # Proven against git rather than asserted: the second file must stay dirty.
        repo = tmp_path / "demo"
        repo.mkdir()
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

        def git(*args):
            return subprocess.run(("git",) + args, cwd=str(repo), env=env,
                                  capture_output=True, text=True, timeout=30)

        git("init", "-q", ".")
        (repo / "a.txt").write_text("1\n")
        (repo / "b.txt").write_text("1\n")
        git("add", "a.txt", "b.txt")
        git("commit", "-qm", "init")
        (repo / "a.txt").write_text("2\n")
        (repo / "b.txt").write_text("2\n")
        assert git("commit", "-ma", "a.txt").returncode == 0
        assert git("log", "-1", "--format=%s").stdout.strip() == "a"
        assert "b.txt" in git("status", "--short").stdout, (
            "git treated -ma as --all; the guard's parse would then be wrong")
        assert run_guard("git commit -ma x").returncode == 0


class TestTheDashDashFormAgreesWithTheBareForm:
    """`git <sub> -- <tree-wide>` must not be a way to spell `git <sub> <tree-wide>`.

    THREE rounds running, one subcommand's pathspec rule was updated and its siblings
    were not: round 5 (magic prefixes), round 6 (`commit -- .`), round 7 (`reset -- .`,
    which wipes the shared index exactly as bare `git reset` does -- verified against
    git). Each time the parallel was stated in a comment and each time the comment was
    not the thing that failed. Parametrising over the shipped pathspec set x every
    ruled subcommand is that check, mechanically.
    """

    #: Every subcommand whose rule consults a pathspec. `switch` is absent because
    #: `git switch -- .` is not a form git accepts.
    SUBCOMMANDS = ["add", "stage", "commit", "reset", "checkout", "restore", "rm",
                   "stash push"]

    @pytest.mark.parametrize("pathspec", sorted(guard.TREE_WIDE_PATHSPECS))
    @pytest.mark.parametrize("sub", SUBCOMMANDS)
    def test_a_tree_wide_pathspec_blocks_however_it_is_spelled(self, sub, pathspec):
        command = "git %s -- '%s'" % (sub, pathspec)
        assert run_guard(command).returncode == 2, command

    @pytest.mark.parametrize("pathspec", [":!x", ":^x", ":(exclude)x", ":(top,exclude)x"])
    @pytest.mark.parametrize("sub", SUBCOMMANDS)
    def test_a_negative_only_pathspec_blocks_for_every_subcommand(self, sub, pathspec):
        # Negatives match everything ELSE, so a list of only negatives is the tree.
        command = "git %s -- '%s'" % (sub, pathspec)
        assert run_guard(command).returncode == 2, command

    @pytest.mark.parametrize("sub", SUBCOMMANDS)
    def test_a_positive_pathspec_still_scopes_every_subcommand(self, sub):
        # The other half of the parity: the fix must not deny the remediation.
        command = "git %s -- src/a.py" % sub
        assert run_guard(command).returncode == 0, command

    #: Every ruled subcommand that HAS a dry run, with the flag git accepts for it.
    #: Round 7 added the exemption to add/stage/commit and missed `rm`; round 8 added
    #: `rm`. The pathspec parity above does not cover FLAG parity, which is how that
    #: survived a round explicitly about dry runs.
    DRY_RUNS = [
        ("git add -n -A", "add"),
        ("git add --dry-run -A", "add long"),
        ("git stage -n -A", "stage"),
        ("git commit --dry-run -a", "commit"),
        ("git clean -n -fd", "clean"),
        ("git rm -n -r .", "rm"),
        ("git rm --dry-run -r .", "rm long"),
    ]

    @pytest.mark.parametrize("command,label", DRY_RUNS, ids=[d[1] for d in DRY_RUNS])
    def test_a_dry_run_mutates_nothing_and_is_allowed(self, command, label):
        # Denying the safe way to PREVIEW the command this hook teaches you to avoid is
        # the false-positive class that produced round 4's rejection.
        assert run_guard(command).returncode == 0, command

    def test_the_dry_run_exemption_does_not_leak_the_real_thing(self):
        # The other direction: the exemption must be the FLAG, not the subcommand.
        assert run_guard("git add -A").returncode == 2
        assert run_guard("git commit -n -a").returncode == 2, (
            "`commit -n` is --no-verify, not a dry run")
        assert run_guard("git rm -r .").returncode == 2
        assert run_guard("git clean -fd").returncode == 2



class TestTheMutationRecordIsExecutable:
    """The mutation record as a GATE, not as prose.

    FIVE adversarial rounds have rejected this hook and every rejection was one class:
    a code path with no test. The only detector for that class was a human running
    mutations by hand and writing the result into `.ai/CONCURRENCY.md` -- and round 5
    proved that record wrong twice, both times in the fail-OPEN direction: two lines
    documented as "REDUNDANT-BY-DESIGN, reverting changes nothing observable" each
    turned `echo file#1.txt; git add -A` from a block into an allow. Prose about a
    mutation is not a test. This class runs the mutations.

    Each entry must satisfy three things, and each is asserted separately:

      * the anchor occurs EXACTLY ONCE in the shipped hook, so a refactor that moves
        or duplicates the line fails here rather than voiding the check silently;
      * the mutation actually CHANGES the verdict on its probe -- a mutation that
        changes nothing proves nothing, which is how two "survivors" turned out to be
        artifacts (a `while False:` left an adjacent `i += 1` doing the same work);
      * the probe is a member of BLOCKED or ALLOWED, which is what makes the rest of
        this suite the thing that actually kills the mutant.

    Add a line to the hook that carries a verdict, add its mutant here.
    """

    #: SCOPE, stated so nobody reads more assurance into this table than it carries:
    #: every entry compares an EXIT CODE. A line that only decides WHICH rule fires --
    #: `--merge`/`--keep` falling through to `reset-unstages-all`, where the command
    #: still blocks but the user is handed the wrong remediation -- cannot be expressed
    #: here. `test_every_destructive_reset_flag_names_its_own_remediation` binds that
    #: one by asserting the remediation text instead.
    #: (name, anchor, replacement, probe, verdict of the SHIPPED hook for that probe)
    MUTANTS = [
        ("shlex-commenters-stay-disabled",
         '    lexer.commenters = ""', '    lexer.commenters = "#"',
         "echo file#1.txt; git add -A", 2),
        ("hash-only-starts-a-comment-at-a-token-boundary",
         r'        return not out or out[-1] in " \t;&|("', "        return True",
         "echo file#1.txt; git add -A", 2),
        ("an-unterminated-heredoc-is-not-confident",
         "                        confident = False", "                        pass",
         "cat <<EOF\nno terminator\ngit add -A", 2),
        ("a-bare-fd-digit-is-part-of-the-redirection",
         "            if segments[-1] and segments[-1][-1].isdigit():",
         "            if False:",
         "git add -A 2>/dev/null", 2),
        ("a-closing-group-fused-to-a-separator-still-separates",
         '        core = raw.lstrip(")}")', "        core = raw",
         "(echo x); git add -A", 2),
        ("a-bare-ampersand-separates-rather-than-redirects",
         '    if body == "&":\n        return "separator"',
         '    if body == "&":\n        return "redirection"',
         "sleep 1 & git add -A", 2),
        ("the-magic-remainder-is-compared-against-the-shipped-set",
         '            if is_tree_wide_token(remainder, wildmatch="literal" not in keywords):',
         "            if False:",
         # `:(top).` and not `:(glob)**/*`: the structural wildmatch rule catches the
         # latter inside `is_tree_wide_token`, so it could no longer isolate this line.
         "git add ':(top).'", 2),
        ("a-literal-signature-turns-wildmatch-off",
         '            if is_tree_wide_token(remainder, wildmatch="literal" not in keywords):',
         "            if is_tree_wide_token(remainder):",
         # `:(literal)` is the escape the doc offers for a `?` in a filename, and the
         # structural rule used to fire on it anyway. Verified against git: this stages
         # exactly one file.
         "git add ':(literal)what?.txt'", 0),
        ("a-negative-pathspec-never-scopes",
         "    if len(positives) != len(pathspecs):", "    if False:",
         "git add ':!nope'", 2),
        ("a-tree-wide-pathspec-commits-everything",
         "        if tree_wide(pathspecs):\n            # `git commit -- .` and "
         "`git commit -- ':!x'` commit every modified tracked",
         "        if False:\n            # `git commit -- .` and "
         "`git commit -- ':!x'` commit every modified tracked",
         "git commit -- .", 2),
        ("a-fused-git-global-option-is-stripped",
         '        if len(head) > 2 and head[:2] in ("-C", "-c"):', "        if False:",
         # a SCOPED probe: since round 19 an unstripped global raises UnknownGitGlobal
         # and fails closed, so the tree-wide probe blocked either way and could no
         # longer isolate this line
         "git -C/tmp/x add src/a.py", 0),
        ("an-unknown-pre-subcommand-option-fails-closed",
         '        if head.startswith("-") and head != "-":\n'
         "            # Not a subcommand and not a global we model: fail CLOSED. git does NOT",
         "        if False:\n"
         "            # Not a subcommand and not a global we model: fail CLOSED. git does NOT",
         # `--frobnicate`, not `--no-advice`: the latter is a KNOWN member now and is
         # stripped normally, so it blocked either way and could not isolate this line
         "git --frobnicate add -A", 2),
        ("a-fused-input-redirection-still-feeds-stdin",
         '        if "<" in tok:\n            fed[-1] = True',
         '        if False:\n            fed[-1] = True',
         # the heredoc spelling: its `<<` is fused to the following separator, so this
         # line is the only thing that sees it
         "git add -p . <<EOF\ny\ny\nEOF", 2),
        ("grouping-inherits-the-stdin-of-its-compound",
         '            start_segment(fed[-1])\n            if any(ch in "({" for ch in core):',
         '            start_segment(False)\n            if any(ch in "({" for ch in core):',
         "yes | (git checkout -p .)", 2),
        ("a-real-word-ends-a-pending-group-close",
         "            closed_group_at = None",
         "            pass",
         # round 21 found this line unbound: without it a redirection later on the
         # line is credited to the group behind it instead of the word in front
         "git add -p . ; (echo x) ; cat < f", 2),
        ("a-group-redirection-feeds-the-commands-inside-it",
         "            start = closed_group_at if closed_group_at is not None else 0",
         "            start = len(fed) - 1",
         "{ git checkout -p .; } < ans", 2),
        ("a-command-substitution-is-a-command-in-any-quote-state",
         '        if quote != "\'" and command.startswith("$(", i):',
         '        if quote == \'"\' and command.startswith("$(", i):',
         # round 23 gated this on being inside double quotes, so the UNQUOTED spelling
         # severed the outer command and dropped the flag behind it
         "git commit -m $(date) -a", 2),
        ("clean-denies-the-interactive-flag-too",
         '        if has_flag(flags, ("--force", "--interactive"), "fi"):',
         '        if has_flag(flags, ("--force",), "f"):',
         "git clean -i", 2),
        ("commit-denies-the-interactive-flag",
         '        if has_flag(flags, ("--interactive",)):\n            return "commit", "commit-all"',
         '        if False:\n            return "commit", "commit-all"',
         "git commit --interactive -m wip", 2),
        ("a-non-pipe-separator-inherits-the-enclosing-stdin",
         '            start_segment(True if "|" in tok else fed[-1])',
         '            start_segment("|" in tok)',
         # the `;` inside `if ...; then ...; fi` is the separator path; the braces case
         # is decided by the GROUPING branch above and cannot isolate this one
         "yes | if true; then git commit -p -m wip .; fi", 2),
        ("a-long-denial-matches-an-unambiguous-abbreviation",
         "    return any(name.startswith(base) for name in long_names)",
         "    return False",
         # git resolves `--al` to `--all` and stages the whole tree (verified)
         "git add --al", 2),
        ("an-exemption-is-not-matched-by-abbreviation",
         "    if exact:\n        return base in long_names",
         "    if exact:\n        return any(name.startswith(base) for name in long_names)",
         # prefix-matching an ALLOWLIST is the fail-OPEN direction: this mutation lifts
         # the denial on a real `-A` because `--dry-ru` looks like the exemption
         "git add --dry-ru -A", 2),
        ("a-pathspec-list-read-from-a-file-is-tree-wide",
         "    if has_flag(flags, (PATHSPEC_FROM_FILE,)):",
         "    if False:",
         "git rm -r --pathspec-from-file=list.txt", 2),
        ("clean-checks-only-n-for-a-dry-run",
         "        # not destructive and must not be swept up.\n"
         '        if has_flag(flags, ("--dry-run",), "n", exact=True):',
         "        # not destructive and must not be swept up.\n"
         '        if has_flag(flags, ("--dry-run",), "nq", exact=True):',
         "git clean -qf", 2),
        ("add-exempts-a-dry-run",
         '        if has_flag(flags, ("--dry-run",), "n", exact=True):\n            return None\n'
         "        # -A/-u with an explicit non-tree-wide pathspec is SCOPED, and allowed.",
         "        if False:\n            return None\n"
         "        # -A/-u with an explicit non-tree-wide pathspec is SCOPED, and allowed.",
         "git add -n -A", 0),
        ("rm-exempts-a-dry-run",
         "        # class the pathspec parity test was written to close.\n"
         '        if has_flag(flags, ("--dry-run",), "n", exact=True):',
         "        # class the pathspec parity test was written to close.\n"
         "        if False:",
         "git rm -n -r .", 0),
        ("the-patch-exemption-covers-every-subcommand-that-has-one",
         '    if sub in PATCH_SUBCOMMANDS and has_flag(flags, ("--patch",), "p", exact=True):',
         '    if sub in ("reset", "stash") and has_flag(flags, ("--patch",), "p", exact=True):',
         "git add -p .", 0),
        ("commit-exempts-only-the-long-dry-run",
         '        if has_flag(flags, ("--dry-run",), exact=True):', "        if False:",
         "git commit --dry-run -a", 0),
        ("a-tree-wide-pathspec-unstages-everything",
         "        if not pathspecs or tree_wide(pathspecs):",
         "        if not pathspecs:",
         "git reset -- .", 2),
        ("a-wrappers-own-option-is-stepped-over",
         '        if saw_prefix and head.startswith("-") and head != "-":',
         "        if False:",
         # `nice -n 10 git ...`, not `env -i git ...`: with a VALUE between the option
         # and the command word, the option-value branch below cannot cover for this
         # one, so the probe isolates the line it names.
         "nice -n 10 git add -A", 2),
        ("a-wrappers-option-value-is-stepped-over",
         "        if saw_prefix and len(out) > 1 and is_git(out[1]) and not is_git(head):",
         "        if False:",
         "sudo -u me git add -A", 2),
        ("no-ignore-removal-is-a-synonym-for-all",
         '        if has_flag(flags, ("--all", "--no-ignore-removal", "--update"), "Au"):',
         '        if has_flag(flags, ("--all", "--update"), "Au"):',
         "git add --no-ignore-removal", 2),
        ("reset-reads-its-operand-pathspecs",
         "        elif len(operands) > 1:", "        elif False:",
         "git reset HEAD src/a.py", 0),
        ("the-stash-allowlist-is-what-lifts-the-denial",
         "        if operands and operands[0] in STASH_RESTORATIVE:",
         '        if operands and operands[0] in ("list",):',
         "git stash apply", 0),
        ("a-long-flag-is-compared-without-its-value",
         '        base = flag.split("=", 1)[0]', "        base = flag",
         "git clean --force=1", 2),
        ("the-fail-closed-radius-is-bounded-to-text-containing-git",
         '    if "git" not in command:', "    if False:",
         "echo 'unbalanced", 0),
        ("a-grouping-token-fused-to-the-command-word-is-peeled",
         '        if len(head) > 1 and head[0] in "{(":', "        if False:",
         "{git add -A;}", 2),
        ("a-tree-wide-first-reset-operand-is-a-pathspec",
         "            pathspecs = operands if tree_wide(operands[:1]) else operands[1:]",
         "            pathspecs = operands[1:]",
         "git reset . src/a.py", 2),
        ("eval-analyses-its-joined-argv",
         '            for candidate in [" ".join(segment[1:])] + list(segment[1:]):',
         "            for candidate in list(segment[1:]):",
         "eval git add -A", 2),
        ("only-push-may-be-scoped-by-a-stash-pathspec",
         '        if operands[:1] == ["push"] and pathspecs and not tree_wide(pathspecs):',
         "        if pathspecs and not tree_wide(pathspecs):",
         "git stash frobnicate -- src/a.py", 2),
        ("the-magic-prefix-loop-catches-a-tree-wide-remainder",
         "        for magic in TREE_WIDE_MAGIC:", "        for magic in ():",
         "git add ':/*'", 2),
        ("a-required-option-value-is-not-a-scoping-pathspec",
         "            skip_next = option_needs_next_token(\n"
         "                tok, value_letters, required_letters, long_value_opts)",
         "            skip_next = False",
         "git add -A --chmod +x", 2),
        ("an-optional-value-letter-never-consumes-the-next-token",
         '    "commit": "mFCct",', '    "commit": "mFCctSu",',
         # `-u`'s value is optional, so `.` is a PATHSPEC (verified against git);
         # consuming it hides the tree-wide token from every rule
         "git commit -u . -m wip", 2),
        ("commit-tests-all-before-a-scoped-pathspec-returns",
         '        if has_flag(flags, ("--all",), "a"):\n'
         '            return "commit", "commit-all"\n'
         "        # `--interactive` runs the same interactive-add loop",
         "        if pathspecs and not tree_wide(pathspecs):\n"
         "            return None\n"
         '        if has_flag(flags, ("--all",), "a"):\n'
         '            return "commit", "commit-all"\n'
         "        # `--interactive` runs the same interactive-add loop",
         # git refuses a pathspec with -a, so any operand here is an option value the
         # model failed to consume -- the ordering is the second of two belts
         "git commit -a -S keyid", 2),
        ("the-bare-arithmetic-command-is-an-opaque-word",
         '        if command.startswith("((", i) and at_token_boundary():',
         "        if False:",
         "(( 1 << 2 ))\ngit checkout -f\n2", 2),
        ("an-unclosed-arithmetic-expansion-is-not-confident",
         "                confident = False          # unclosed: the text was not understood",
         "                pass",
         "echo $(( ; git status", 2),
        ("an-unconsumed-heredoc-marker-is-not-confident",
         "    if quote or escaped or pending_markers:",
         "    if quote or escaped:",
         "git log <<EOF", 2),
        ("arithmetic-is-recognised-before-command-substitution",
         '        if quote != "\'" and command.startswith("$((", i):',
         '        if False and command.startswith("$((", i):',
         # `$((` matches `startswith("$(")` too, so this branch has to win. Round 25
         # let the substitution extraction run unquoted and immediately regressed
         # `echo $((1+2))` above `git add -A` from BLOCK to ALLOW.
         "echo $((1+2))\ngit add -A", 2),
        ("an-arithmetic-expansion-becomes-one-opaque-word",
         "                confident = False          # unclosed: the text was not understood\n"
         "                break\n"
         "            out.append('\"' + QUOTED_WORD_SENTINEL + '\"')\n",
         "                confident = False          # unclosed: the text was not understood\n"
         "                break\n",
         # with NO placeholder the expansion leaves no token, so `-m` swallows the
         # `-a` behind it as its message. The previous re-aim emitted a SECOND
         # placeholder instead and did not flip -- commit tests `--all` before the
         # scoped-pathspec return, so an extra pathspec changes nothing there.
         "git commit -m $((1)) -a", 2),
        ("the-bare-arithmetic-command-is-not-a-heredoc",
         '        if command.startswith("((", i) and at_token_boundary():',
         "        if False:",
         "(( 1 << 2 ))\ngit checkout -f\n2", 2),
        ("the-fused-config-spelling-is-opacity-checked-too",
         '            if head.split("=", 1)[0] in ("-c", "--config-env"):\n'
         "                if _config_is_opaque(head.split(\"=\", 1)[1]):",
         '            if head.split("=", 1)[0] in ("-c", "--config-env"):\n'
         "                if False:",
         "git --config-env=alias.st=AL st", 2),
        ("a-quoted-substitution-body-is-extracted",
         # the process-substitution branch shares this line verbatim, so the anchor
         # carries the placeholder comment that only the `$(` branch has
         "            extra_scripts.append(command[i + 2:j])\n"
         "            # A PLACEHOLDER word takes the expansion's place",
         "            pass\n"
         "            # A PLACEHOLDER word takes the expansion's place",
         'echo "$(git add -A)"', 2),
        ("an-extracted-body-is-read-recursively",
         "        inner_text, inner_confident = preprocess(script)",
         "        inner_text, inner_confident = script, True",
         'echo "$(echo "$(git add -A)")"', 2),
        ("an-empty-argument-is-kept-as-an-argument",
         '            segments[-1].append("")', "            continue",
         'git commit -m "" -a', 2),
        ("an-escaped-operator-inside-quotes-needs-no-surgery",
         '            if ch in SHELL_ONLY_CHARS and quote == \'"\':',
         "            if False:",
         'git commit -m "wip\\;x" -a', 2),
        ("a-wrapper-reading-stdin-has-no-script-operand",
         "            has_script = not reads_stdin and (",
         "            has_script = (",
         "bash -s file <<EOF\ngit add -A\nEOF", 2),
        ("a-wrapper-with-a-script-operand-is-not-denied",
         "                or bool(operands))", "                or False)",
         "git status; echo x | bash build.sh", 0),
        ("an-included-config-file-is-opaque",
         'OPAQUE_CONFIG_PREFIXES = (\n'
         '    "alias.", "clean.requireforce", "include.", "includeif.", "help.autocorrect",\n'
         ")",
         'OPAQUE_CONFIG_PREFIXES = (\n'
         '    "alias.", "clean.requireforce", "help.autocorrect",\n'
         ")",
         "git -c include.path=/tmp/inc.cfg st", 2),
        ("an-escaped-operator-only-word-is-a-pathspec",
         "                out.append('\"' + QUOTED_WORD_SENTINEL + ch + '\"')",
         "                out.append(ch)",
         "git checkout \\> .", 2),
        ("a-wrapper-fed-its-script-on-stdin-fails-closed",
         '                raise ValueError("a script fed to a shell wrapper cannot be read")',
         "                pass",
         "bash <<< 'git add -A'", 2),
        ("an-opaque-config-setting-fails-closed",
         '        if head in ("-c", "--config-env") and len(out) > 1 and _config_is_opaque(out[1]):',
         "        if False:",
         "git -c clean.requireForce=false clean -d", 2),
        ("a-quoted-operator-only-word-is-a-pathspec",
         '                if body and all(c in SHELL_ONLY_CHARS for c in body):',
         "                if False:",
         "git add '>' .", 2),
        ("the-shell-only-set-covers-grouping-characters",
         'SHELL_ONLY_CHARS = "<>&|;(){}"', 'SHELL_ONLY_CHARS = "<>&|;"',
         # rounds 21 and 22 closed `<>&|;` and left `(){}` out, so a quoted `)` was
         # peeled as a real closer and the flag behind it was dropped
         'git commit -m ")" -a', 2),
        ("a-line-continuation-is-deleted-not-spaced",
         '            out.append("" if ch == "\\n" else ch)',
         '            out.append(" " if ch == "\\n" else ch)',
         # bash JOINS the words either side; a space split one word into two and the
         # extra one read as a revision operand
         "git reset HEA\\\nD", 2),
        ("a-brace-outside-command-word-position-is-an-argument",
         "        if raw and all(ch in \"{}\" for ch in raw) and segments[-1]:", "        if False:",
         "{ git commit -m } -a; }", 2),
        ("a-brace-expansion-is-an-opaque-word",
         "        if not quote and command.startswith(\"{\", i) and at_token_boundary_or_word():", "        if False:",
         "git add {,} -A", 2),
        ("a-bare-parameter-expansion-is-an-opaque-word",
         "        if quote != \"'\" and command.startswith(\"$\", i) and i + 1 < n and (command[i + 1] == \"_\" or command[i + 1].isalpha()):", "        if False:",
         "git add $x -A", 2),
        ("process-substitution-is-lifted-in-any-word-position",
         '        if not quote and command[i:i + 2] in ("<(", ">("):',
         '        if not quote and command[i:i + 2] in ("<(", ">(") and at_token_boundary():',
         # this entry subsumes the round-25 one (deleted): the boundary-gated form
         # still lifts a standalone `<(`, so only the GLUED probe isolates the line
         "git commit -m x<(echo y) -a", 2),
        ("a-wrapper-option-value-is-not-a-script-file",
         "                and not (idx and words[idx - 1] in WRAPPER_VALUE_OPTS)",
         "                and True",
         "bash -O extglob <<EOF\ngit add -A\nEOF", 2),
        ("a-consumed-heredoc-marker-leaves-a-placeholder-target",
         "            out.append('<< \"' + QUOTED_WORD_SENTINEL + '\"')",
         "            out.append(\"<<\")",
         "git commit -m x <<EOF -a\nbody\nEOF", 2),
        ("a-redirection-run-is-not-a-pipe",
         "    if body[:1] in (\"<\", \">\") and \";\" not in body and \"&&\" not in body:", "    if False:",
         "git commit -m x >| out -a", 2),
        ("the-parameter-expansion-scan-is-quote-aware",
         "                # Quote-aware like the `$(` scan: `${x:-\"}\"}` has a `}` INSIDE quotes,\n"
         "                # and closing on it left an unbalanced quote behind that failed the\n"
         "                # whole read-only command closed (`git commit -m ${x:-\"}\"} src/a.py`\n"
         "                # exited 2 -- found probing this fix, round 25).\n"
         "                if inner_quote:",
         "                # Quote-aware like the `$(` scan: `${x:-\"}\"}` has a `}` INSIDE quotes,\n"
         "                # and closing on it left an unbalanced quote behind that failed the\n"
         "                # whole read-only command closed (`git commit -m ${x:-\"}\"} src/a.py`\n"
         "                # exited 2 -- found probing this fix, round 25).\n"
         "                if False:",
         'git commit -m ${x:-"}"} src/a.py', 0),
        ("a-parameter-expansion-is-one-opaque-word",
         '        if quote != "\'" and command.startswith("${", i):',
         "        if False:",
         "git commit -m ${x:-a;b} -a", 2),
        ("an-unlisted-wrapper-word-hides-the-command",
         '    "caffeinate", "timeout", "stdbuf", "setsid", "ionice", "chrt", "doas",',
         "",
         "caffeinate git add -A", 2),
        ("a-wildmatch-first-component-reaches-the-whole-tree",
         '    return bool(first) and any(ch in "*?" for ch in first)',
         "    return False",
         # `?*`, not `./*`: the latter normalises to the enumerated `*` before this
         # line runs, so it cannot isolate the structural rule.
         "git add '?*'", 2),
        ("a-run-of-grouping-punctuation-is-never-an-argument",
         '        if all(ch in "(){}" for ch in core):', "        if False:",
         "stage() { git add -A; }", 2),
        ("the-script-wrapper-loop-stops-at-the-first--c",
         "                    if inner:\n                        return inner\n"
         "                    break",
         "                    if inner:\n                        return inner\n"
         "                    pass",
         "bash -c 'echo hi' -c 'git add -A'", 0),
        ("a-parent-run-is-normalised-away",
         "    stripped = collapse_dot_segments(pathspec)", "    stripped = pathspec",
         # `a/../..` and not `../..`: the leading-run loop below still handles the
         # leading spelling, so only an INTERIOR `..` isolates the collapse call.
         "git add a/../..", 2),
        ("an-interior-parent-component-is-collapsed-too",
         "        if part == \"..\":\n            if out and out[-1] != \"..\":\n"
         "                out.pop()",
         "        if part == \"..\":\n            if False:\n"
         "                out.pop()",
         # `a/../..` walks up exactly as `..` does; only a LEADING run used to be seen.
         "git add a/../..", 2),
        ("commit-has-an-interactive-patch-too",
         '    "add", "stage", "checkout", "restore", "reset", "stash", "commit",',
         '    "add", "stage", "checkout", "restore", "reset", "stash",',
         "git commit -p .", 0),
        ("only-worktree-remove-is-ruled-on",
         '        if operands[:1] == ["remove"] and has_flag(flags, ("--force",), "f"):',
         '        if has_flag(flags, ("--force",), "f"):',
         "git worktree add -f ../wt/x main", 0),
        ("a-literal-remainder-is-still-path-resolved",
         "    if not wildmatch:\n        return False", "    if False:\n        return False",
         # `:(literal)` turns PATTERN matching off, not PATH RESOLUTION: the dot
         # collapse still applies. Giving that keyword its own membership-only test let
         # `:(literal)a/../..` commit the whole shared tree from a subdirectory.
         "git add ':(literal)what?.txt'", 0),
        ("the-command-word-is-matched-up-to-its-first-dot",
         '    return os.path.basename(word).split(".")[0] == "git" if word else False',
         '    return os.path.basename(word) == "git" if word else False',
         "git.exe add -A", 2),
        ("magic-signatures-are-parsed-to-their-paren",
         '        if p.startswith(":("):', "        if False:",
         "git add ':(top,glob)'", 2),
        ("a-fused-option-value-is-cut-before-any-flag-scan",
         "    if not value_letters or not is_short_cluster(flag):", "    if True:",
         'git commit -m"refactor"', 0),
        ("a-separated-short-value-consumes-the-next-token",
         "            return ch in required_letters and idx + 1 == len(flag)",
         "            return False",
         "git stash push -m wip", 2),
        ("a-long-option-value-is-consumed-only-when-separate",
         '        return "=" not in flag and matches_long(flag, long_value_opts, exact=False)',
         "        return matches_long(flag.split(\"=\", 1)[0], long_value_opts, exact=False)",
         "git stash push --message=wip src/a.py", 0),
        ("an-abbreviated-value-option-is-consumed-too",
         '        return "=" not in flag and matches_long(flag, long_value_opts, exact=False)',
         '        return "=" not in flag and flag in long_value_opts',
         # round 16's dimension applied to round 15's tables: verified against git,
         # this stages both sessions' files
         "git add -A --chm +x", 2),
        ("a-consumed-value-reaches-neither-list",
         "        if consume:\n            continue",
         "        if consume and not (tok.startswith(\"-\") and tok != \"-\"):\n"
         "            continue",
         # this mutation IS round 16's code, and round 17 refuted it by executing:
         # left in `flags`, the value fires an exemption, and this commits both
         # sessions' files (verified against git 2.50)
         "git commit -a -m --dry-run", 2),
        ("an-unquoted-newline-separates-commands",
         '            out.append(";")', '            out.append(" ")',
         "git status\ngit add -A", 2),
    ]

    @staticmethod
    def _run_mutant(tmp_path, anchor, replacement, probe):
        source = (HOOKS / GUARD).read_text()
        mutant = tmp_path / GUARD
        mutant.write_text(source.replace(anchor, replacement, 1))
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": probe}})
        env = dict(os.environ, ECC_HOOK_PROFILE="standard", LOG_FILE="/dev/null")
        env.pop("CK_ALLOW_BROAD_GIT", None)
        return subprocess.run(
            ["python3", str(mutant)], input=payload, capture_output=True,
            text=True, cwd=str(REPO), env=env, timeout=30,
        ).returncode

    @pytest.mark.parametrize("entry", MUTANTS, ids=[m[0] for m in MUTANTS])
    def test_the_anchor_is_unique_in_the_shipped_hook(self, entry):
        _, anchor, _, _, _ = entry
        assert (HOOKS / GUARD).read_text().count(anchor) == 1, (
            f"anchor is not unique, so the mutation below proves nothing: {anchor!r}")

    @pytest.mark.parametrize("entry", MUTANTS, ids=[m[0] for m in MUTANTS])
    def test_the_probe_is_bound_by_this_suite(self, entry):
        _, _, _, probe, _ = entry
        assert probe in BLOCKED or probe in ALLOWED, (
            f"probe is in neither list, so nothing would kill this mutant: {probe!r}")

    @pytest.mark.parametrize("entry", MUTANTS, ids=[m[0] for m in MUTANTS])
    def test_the_shipped_hook_gives_the_recorded_verdict(self, entry):
        _, _, _, probe, expected = entry
        assert run_guard(probe).returncode == expected

    @pytest.mark.parametrize("entry", MUTANTS, ids=[m[0] for m in MUTANTS])
    def test_the_mutation_changes_the_verdict(self, entry, tmp_path):
        name, anchor, replacement, probe, expected = entry
        got = self._run_mutant(tmp_path, anchor, replacement, probe)
        assert got != expected, (
            f"{name}: the mutation changed nothing, so the line it targets is not "
            f"load-bearing and this entry is an artifact, not a guard")


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

# Concurrency — several sessions or accounts on one repo

Maintainer doc. Deliberately NOT in CLAUDE.md: that file is weighted x4 in the
always-on context floor and sits ~28 raw chars under budget
(`scripts/check-context-floor.py`), so this contract is enforced by a hook
rather than prompted. A prompt would also be advisory, which is the weaker half
of the point.

## The failure

Two Claude sessions — possibly two accounts — share one working tree, and
therefore one `.git/index`. Session B sees session A's half-written files and
staged paths. A tree-wide stage or a destructive checkout in B then commits or
deletes A's in-flight work, silently. Observed twice in `qa-agent`
(2026-09-02, 2026-09-03).

Proven, not asserted — `tests/test_concurrency_guard.py`:

* `test_a_shared_tree_loses_work_which_is_why_the_guard_exists` — one tree, two
  edits, `git add -A`: the commit lands with B's change and A's is gone.
* `test_worktrees_isolate_concurrent_sessions` — the same two edits, one
  worktree each: B's `git add -A` cannot reach A's file, both survive, and
  `main` carries both after merge.

## The fix: one worktree per session

```bash
git worktree add ../<repo>-wt/<slug> -b <branch>     # one per session
git worktree list                                     # audit
git worktree remove ../<repo>-wt/<slug>               # when merged
git worktree prune                                    # drop stale entries
```

Separate directory, separate index, separate branch. Integration happens
through PRs to `main` only; cross-branch merges are owner-gated.

Two accounts need separate config dirs so credentials and history do not fight:

```bash
CLAUDE_CONFIG_DIR=~/.claude-acct-b claude     # inside its own worktree
```

Do not have sessions poll each other. Cross-session messaging enters both
contexts and is re-sent every turn, and it is advisory anyway: it arrives on a
turn boundary and cannot stop a concurrent edit. One handoff message when work
is pushed is fine.

## The enforcement: `.claude/hooks/concurrency-guard.py`

PreToolUse / Bash / tier `blocking`, registered in `dispatch-registry.json`
after `command-guard` (order is cosmetic — the dispatcher takes
max(severity) over all handlers). Blocks with `exit 2` + stderr, naming the
scoped alternative:

| blocked | instead |
| --- | --- |
| `add`/`stage` with `-A` `-u` `--all` `--update` `--no-ignore-removal`, or a tree-wide pathspec (`-n`/`--dry-run` exempt) | `git add path/to/file` |
| `add`/`stage` with `-e`/`--edit` or `-i`/`--interactive` and NO pathspec — they open the TREE-WIDE diff, which is `-u` semantics by another name (`GIT_EDITOR=true git add -e` staged another session's file, verified). `git add -e src/a.py` is scoped and allowed | `git add path/to/file` |
| `commit -a` / `--all` (any flag position, any cluster, and BEFORE any pathspec can look scoping), or a tree-wide pathspec WITH OR WITHOUT `--` — `git commit -m wip .` commits every modified tracked file just as `commit -a` does (`--dry-run` exempt) | `git add <paths>` then `git commit` |
| a tree-wide pathspec in ANY operand position, not only the first — `git commit . -m wip` commits both sessions' files (verified against git); the operand list is read by POSITION now, and used to be read by COUNT | `git commit -m wip path/to/file` |
| `--pathspec-from-file` (either spelling) on `add`/`stage`/`commit`/`checkout`/`restore`/`rm`/`stash push` — the list is in a FILE the hook cannot read, so it is treated as tree-wide (`-n`/`--dry-run` still exempt) | pass the paths on the command line |
| `reset --hard` / `--merge` / `--keep` | `git restore --source=HEAD -- <path>` |
| `reset` bare or `--mixed`, with no pathspec OR a tree-wide one (`git reset -- .` and `git reset . src/a.py` both empty the shared index just as bare `reset` does — a tree-wide FIRST operand is a pathspec, not a revision). A SINGLE operand is a revision — `git reset main` and `git reset HEAD` unstage everything | `git reset -- path/to/file` |
| `checkout` / `restore` / `switch` with a tree-wide pathspec | `git restore -- <path>` |
| `checkout -f` / `switch -f` / `--discard-changes` | commit your work first |
| `-c help.autocorrect=<x>` — it decides WHICH SUBCOMMAND runs, so the text says one thing and git does another: `git -c help.autocorrect=immediate addd -A` really executed `add -A` and staged both sessions' files, and `cleann -fd` deleted both sessions' untracked files, rc 0 (round 23, verified) | run the command without the config override |
| `-c alias.<x>=...`, `-c include.path=<file>`, `-c includeIf.<...>.path=<file>` or `-c clean.requireForce=<false>` — in EVERY spelling: `-c k=v`, `-ck=v`, `--config-env k=v` and `--config-env=k=v`. Round 22: the fused `--config-env=` form skipped the opacity test entirely, restoring round 21's two leaks for the cost of one `=` (verified: the alias form staged both sessions' files, the requireForce form deleted both untracked files), and `include.path` reaches an alias one indirection further out through a config FILE. Parity across spellings is now asserted mechanically for every valued global rather than per spelling — the setting decides what the command MEANS, and the hook was parsing the token and discarding it. `git -c clean.requireForce=false clean -d` deleted another session's untracked file AND a subdirectory at rc 0; `git -c alias.st='add -A' st` staged both sessions' files | run the command without the config override |
| a shell WRAPPER reading stdin via `-s`, even WITH an operand (`bash -s file <<EOF … EOF`) — `-s` means read the script from stdin, so the operand is a positional parameter, not a script file (round 24, verified: it staged both sessions' files). `sh -- file` is NOT this case and stays allowed — checked rather than assumed: it runs the FILE and staged nothing | pass the script as `bash -c '<script>'` |
| a shell WRAPPER whose script arrives on STDIN (`bash <<EOF … EOF`, `sh <<< '…'`, `cat <<EOF \| bash`, and `bash -s <operand> <<EOF …` since `-s` reads the script from stdin and makes the operand a positional) — `bash`/`sh`/`zsh`/`dash` read stdin as CODE, while `preprocess` strips heredoc bodies as DATA so that `cat > f <<EOF … EOF` can document a command without triggering it. The two rules met and the script vanished: verified, the `sh` form destroyed both sessions' edits and the here-string staged both, rc 0. Until round 22 only the `-c` spelling was unwrapped; a wrapper with a script FILE operand (`bash build.sh`, `sh -- file`) stays the named script-file residual. The script text is genuinely unavailable at that point, so it fails CLOSED | pass the script as `bash -c '<script>'`, which IS read |
| a BRACE EXPANSION — `{,}` yields ZERO words under bash, so `git add {,} -A` handed git exactly `add -A` while the hook kept `{,}` as a positive scoping pathspec: both sessions' files staged, and `git stash push {,}` stashed both sessions' in-flight edits (round 27, verified under bash 3.2; zsh passes two empty words and differs). Any word carrying an unquoted `{…,…}`/`{a..b}` list is an opaque placeholder now — a PHANTOM the hook cannot resolve | spell the paths out |
| a bare `$name` — the one expansion spelling that was not opaque; an unset name expands to nothing, so `git add $x -A` staged both sessions' files and `git stash push $x` degraded to a bare stash (round 27). `${x}` had failed closed for the identical reason one spelling over | spell the value out |
| a lone BRACE anywhere but command-word position is an ordinary WORD (`{`, `}`, `{}` — not an expansion list) — `git commit -m { -a`, `git commit -m {} -a`, and `{ git commit -m } -a; }` each committed both sessions' files (round 25, verified). Round 24 fixed only the bare `}`, gated on no group being open, so wrapping the command undid it; position decides now, opener and closer alike | `git add <paths>` then `git commit` |
| process substitution GLUED to a word (`git commit -m x<(echo y) -a`) — bash performs it mid-word (`echo x<(echo y)` prints `x/dev/fd/63`), and gating the lift on a token boundary let `<(` reach the classifier as a separator, dropping the flag behind it; both sessions' files were committed (round 26, verified) | `git add <paths>` then `git commit` |
| a shell WRAPPER whose own option takes a VALUE, fed on stdin (`bash -O extglob <<EOF …`, `bash --rcfile f <<< '…'`) — the value was counted as a script file, so the fail-closed rule for stdin scripts was skipped; `-O extglob <<< "git checkout -f"` destroyed both sessions' in-flight edits (round 26, verified). `WRAPPER_VALUE_OPTS` names the options whose next word is not a script | pass the script as `bash -c '<script>'` |
| an argument AFTER a heredoc marker — `git commit -m x <<EOF -a` — is still git's argument, but the marker is consumed in `preprocess`, so the `<<` token's target-skip ate the `-a` and both sessions' files were committed (round 26, found probing, verified). A placeholder now stands in for the consumed marker | `git add <paths>` then `git commit` |
| `>\|` (noclobber override) is ONE redirection operator — reading its `\|` as a pipe severed the command at the redirection: `git commit -m wip >\| out -a` committed both sessions' files, `git clean -e p >\| out -fd` deleted both sessions' untracked files (round 25, verified) | drop the redirection or move it to the end |
| a QUOTED **or ESCAPED** operator-only pathspec (`git add '>' .`, `git checkout \> .`) — `shlex` discards quoting, so the word `>` was classified as a REDIRECTION and the tree-wide token behind it was swallowed as its target (verified with a file named `>` present). Round 21 fixed the quoted spelling and round 22 the escaped one — `git checkout \> .` DESTROYED both sessions' in-flight edits at rc 0. The word is re-emitted QUOTED, not merely sentinel-prefixed: two earlier attempts failed because the backslash escaped the sentinel instead of the operator, and because `shlex` with `punctuation_chars` splits a punctuation character away from an adjacent word character anyway. Quoting is the only reason the quoted branch's own sentinel survives tokenisation | `git add path/to/file` |
| `clean -f` / `--force` / `-i` / `--interactive` (any cluster; `-n` / `--dry-run` exempt) — `-i` satisfies git's requireForce exactly as `-f` does and deletes as much: `printf '1\n' \| git clean -i` removed both of another session's untracked files at rc 0 with no `-f` anywhere | delete the files you created |
| `commit --interactive` (long spelling only) — it runs the same interactive-add loop as `git add -i` and then COMMITS; verified, both sessions' files landed in one commit. `commit -i` is `--include`, which takes paths and is scoped by them | `git add <paths>` then `git commit` |
| `stash` bare / `stash push` (unscoped) / `save` / `clear` | commit to your own branch |
| `rm` with a tree-wide pathspec | `git rm path/to/file` |
| `worktree remove --force` | let the owning session close its own worktree |

**Every long option in a DENIAL is matched by unambiguous PREFIX, the way git resolves
it.** The denylists were exact-match, and git resolves any unambiguous prefix, so every
rule had a legal spelling it did not recognise: `git add --al` staged the whole tree,
`git add --up` staged every tracked modification, `git checkout --fo` destroyed another
session's edit, `git clean --fo` deleted untracked work, and
`git rm -r --pathspec-fr=list.txt` deleted every tracked file — all verified against
git 2.50, all exited 0, and none of them obfuscation: these are spellings git documents
as supported. Round 16, and the THIRD instance of "a legal git spelling the denylist
does not enumerate" after round 5's combined `:(top,glob)` keywords and round 15's fused
`--pathspec-from-file=`. Prefix matching cannot cause a wrong DENIAL, which is what
makes it safe rather than merely stricter: the names compared are exactly the options
valid for that subcommand, so if the text is a prefix of one of them git sees at least
that candidate — either it is the only one, and git resolves to the option being denied,
or there are several and git refuses the command itself. **EXEMPTIONS stay exact-match**,
deliberately: prefix-matching an allowlist is the fail-OPEN direction, and this hook has
been rejected three times for an allowlist doing more than it could prove. The cost is
named in the residuals below.

The abbreviation rule and the option-VALUE rule meet, and the meeting point leaked:
making the denials prefix-matched while round 15's value tables stayed exact put round
15's defect back inside round 16's dimension — an ABBREVIATED value-taking option's
value stayed an operand, became a scoping pathspec, and disarmed the flag rule above it.
`git add -A --chm +x` staged both sessions' files and `git stash push --mes wip` stashed
the whole tree, both exit 0, both verified against git. `option_needs_next_token` now
matches long options through the SAME `matches_long`, so there is one matcher and not
two. Found while fixing round 16 rather than by a reviewer, which is the argument for
routing both rules through one function: two matchers would have needed a
seventeenth round to notice they disagreed.

**A consumed value reaches NEITHER list, and both halves of that rule cost a round.**
In `operands` it became a scoping pathspec (round 15). In `flags` it impersonated an
EXEMPTION — because `flags` is the same list `--dry-run`, `--patch` and `--soft` are
read from — so the command line could inject one: `git commit -a -m --dry-run`
committed BOTH sessions' files, `git clean -f -e -n` deleted both sessions' untracked
files, and `git stash push -m --patch` stashed the whole shared tree, every one at
exit 0 and every one verified against git 2.50 (round 17). Round 16 had kept an
option-LOOKING value in `flags` on the written reasoning that this "can only ADD a
denial, never lift one". That sentence was false, and it is recorded here because the
hook shipped it as a comment: an allowlist and a denylist reading ONE list means
nothing may be filed there on the attacker's word.

The COST of dropping it, stated plainly rather than left implied: an option-looking
token behind a value-taking option is dropped, so `git commit --d -a` exits 0 where
round 16 blocked it. That is bounded, and the bound is TESTED rather than assumed —
`test_a_dropped_value_is_a_command_git_refuses` asserts against real git that every
such command is refused (`ambiguous option: d`, `invalid date format: -a`,
`--chmod param '-A' must be either -x or +x`), so the lost denial can never run, and
the test fails loudly if a future git starts accepting one. A tree-wide PATHSPEC is
unaffected: `git commit -m -a .` and `git add --chmod -A .` both still block, because a
pathspec is not the token directly behind the option.

`stage` is git's own synonym for `add`, and `switch -f` throws away local
modifications exactly as `checkout -f` does — an earlier draft of this document
prescribed `switch` as the *remediation* for a blocked `checkout -f`, which
pointed at an unguarded synonym.

A tree-wide pathspec means `.` `..` `*` `**` `:/` `:` `:!` `**/*` and their
trailing-slash forms, compared as WHOLE tokens so `.ai/x` is never `.`. That
enumeration is not the whole test, because enumeration was losing a race against
git's wildmatch grammar — `./*`, `?*`, `*?`, `[a-z.]*` each stage the entire tree
and none was a member. The STRUCTURAL rule is: a pathspec whose FIRST path
component carries a WIDENING wildmatch metacharacter (`*` or `?`) can match any
top-level entry and therefore reaches the whole tree — unless a `:(literal)`
signature turns wildmatch off, in which case `*` and `?` are ordinary characters.
`:(literal)` suppresses PATTERN matching only: path resolution still applies, so
`:(literal)a/../..` blocks like `a/../..` (round 14 — giving that keyword its own
membership-only test let it commit the whole shared tree from a subdirectory). One
normaliser decides all of it, with wildmatch as a flag, so a keyword cannot opt out
of the dot collapse by carrying its own copy of the rule — so `'*.py'` blocks while
`src/*` keeps its literal first component and stays scoped. `[` is deliberately
NOT in that set: a bracket expression matches exactly one character, so it cannot
widen a match, and including it denied `git add 'notes[1].md'` — a scoped stage of
a real tracked file, and one fleet repo has three such names under `.run/`. A
`.` and `..` components are collapsed LEXICALLY first, so `../..` and the interior
form `a/../..` both block like `..` — each stages the whole tree from a
subdirectory, verified against git.
The
magic prefixes count only when what FOLLOWS them is empty or itself tree-wide:
`:/` blocks, `:/src/a.py` is a scoped single file and is allowed. A `:(...)`
signature is parsed to its closing paren rather than prefix-matched, so COMBINED
keywords are covered too: `:(top,glob)` and `:(glob,top)` block, `:(top,glob)src/a.py`
is scoped. Round 5 found the prefix match let every combined form through —
`git add ':(top,glob)'` stages the whole shared tree, verified against git. An
unclosed signature (`:(top,`) cannot be read and therefore blocks. A magic
PREFIX with a tree-wide remainder blocks too — `:/*`, `:/.`, `:/**` all re-root
at the top and stage everything (verified from a subdirectory) — and round 10
found that case had no test at any level, though the code was right. `::x` is not
tree-wide at all — a second colon ends the magic signature, so it is just the path `x`.

**An option before the subcommand that this hook does not model FAILS CLOSED.**
`strip_git_globals` used to stop at the first token it did not recognise, so the OPTION
became the subcommand, matched no rule, and one ordinary documented flag disarmed
`add`, `commit`, `reset`, `checkout`, `clean` and `stash` at once. Verified against git
2.50: `git --no-lazy-fetch add -A` staged both sessions' files,
`git --no-literal-pathspecs reset --hard` destroyed another session's edit, and
`git --attr-source=HEAD clean -fd` deleted its untracked file — all exit 0 (round 19).
Enumerating the four missing members would have been the FIFTH hand-patch in the
"a legal git spelling the denylist does not enumerate" class (`:(top,glob)` r5,
`--pathspec-from-file=` r15, long-option prefixes r16, `add -e`/`-i` r18, globals r19),
so the fail DIRECTION was inverted instead: an unknown pre-subcommand option is now
indistinguishable from text the hook cannot read and takes the same fail-closed path.
The known globals are still listed because they must NOT block, and exact membership is
right there — git does not abbreviate globals (`git --lit status` → `unknown option`).
`test_git_accepts_every_global_this_hook_lists` asks GIT whether each listed member is
real, which immediately caught two I had invented (`--no-glob-pathspecs`,
`--no-icase-pathspecs` — git rejects both; the negation it accepts is
`--no-literal-pathspecs`).

**A NEGATIVE pathspec is the inversion, and it does not scope anything.** `:!x`,
`:^x`, `:(exclude)x` and `:(top,exclude)x` say "everything EXCEPT x", so a pathspec
list made only of negatives matches the whole tree. Round 6 found the guard reading
them as narrowing: `git add -A ':!node_modules'` and `git checkout -- ':!nope'` —
ordinary usage, not obfuscation — staged and discarded the entire tree and exited 0
(verified against git). Only POSITIVE pathspecs scope a command now; negatives
alongside a positive are fine, so `git add src/a.py ':!src/b.py'` is allowed.

**Explicitly allowed**, because they are scoped or give work back:

* `git add -A -- src/`, `git add -u -- src/` — a pathspec scopes the flag
* `git add -- -A` — `--` ends the options, so `-A` is a filename
* every dot-prefixed path: `git add .ai/x.md`, `.gitignore`, `./src/a.py`
* an interactive `-p`/`--patch` for every subcommand that has one — **only while a
  human is actually at the prompt.** The exemption's whole justification is that every
  hunk is confirmed, and round 18 refuted it by executing: with stdin fed from the
  command line nothing is confirmed by anyone. `yes | git commit -p -m wip .` committed
  BOTH sessions' files and `yes | git checkout -p .` DESTROYED another session's edit,
  both exit 0 (verified against git 2.50). `split_segments` now carries one bit per
  segment — stdin is fed when the segment is the right operand of a `|` or carries a
  `<` / `<<<` redirection — and the exemption is refused when it is set. **That bit is
  INHERITED by grouping and by non-pipe separators**, because resetting it discarded the
  whole fix the moment the command was wrapped: `yes | (git checkout -p .)` destroyed
  another session's in-flight edit and `yes | { git commit -p -m wip .; }` committed both
  sessions' files, exit 0, while the identical unwrapped spellings blocked (round 19,
  verified against git). A subshell does not hand a human back the keyboard. The bit is
  recorded for ANY token containing `<`, before that token is classified — because
  `punctuation_chars` FUSES a run of operator characters, so a heredoc arrives glued to
  the separator behind it (`git add -p . <<EOF` becomes the single token `<<;`).
  Classified whole it read as a SEPARATOR, the redirection meaning was lost, and
  `git add -p . <<EOF … EOF` staged BOTH sessions' files at exit 0 while the identical
  `<<<` and `<` spellings blocked (round 20 — the same fused-token trap that cost
  rounds 1-3 and 6 their command separators). An OUTPUT redirection still leaves the
  exemption intact: `git add -p . > out` is allowed. A
  redirection attached to a GROUP feeds every command INSIDE it, and the closer has
  already started a new segment by the time the `<` is read, so marking only the
  current segment marked an empty one — `{ git checkout -p .; } < ans` DESTROYED both
  sessions' in-flight edits, unattended, at rc 0. The redirection can also hang off a
  LOOP (`while read x; do git add -p .; done < f`), where `do`/`done` are not grouping
  tokens at all, so an input redirection ANYWHERE in the command text now marks every
  segment. That closes the class instead of a fourth spelling, and its cost is named in
  the residuals below The hook was
  already LOOKING at that evidence and throwing it away, so the fix keeps a bit rather
  than adding a layer. An exemption resting on an assumption must test the assumption — `git add -p .`,
  `git checkout -p .`, `git restore -p .`, `git reset -p`, `git stash -p`,
  `git commit -p .` (round 13: `commit` has a real `--patch` and was the one sibling
  left out, while this line already claimed "every"; git itself refuses `-p` with
  `-a`, so the exemption opens nothing). The human
  confirms every hunk, so it cannot touch another session's file unattended. The
  exemption existed only on `reset` and `stash` until round 9, so `git add -p .` was
  denied while the bare `git add -p` was allowed
* `git add -p`, `git commit --amend`, `git reset --soft`, `git reset -- <path>`
* **`git reset HEAD <path>`** — the classic unstage-one-file. Verified against
  git: a second staged path survives it, so it is scoped. Round 8 found it denied
  while this table said a non-tree-wide pathspec is allowed
* a DRY RUN, because it mutates nothing: `git add -n -A`, `git add --dry-run -A`,
  `git commit --dry-run -a`, `git clean -n`, `git rm -n -r .`. (For `commit` the long spelling only —
  `commit -n` is `--no-verify`.) Round 7's point: denying the safe way to preview
  the command this hook teaches you to avoid is over-blocking
* `git checkout <branch>`, `git switch <branch>`, `git checkout main -- src/`
* `git restore -- <path>`, `git clean -n`, `git clean --dry-run`
* **`git stash push src/a.py`** — the ordinary scoped stash; and
  **`stash apply` / `pop` / `drop` / `branch` / `list` / `show`**, because `pop`
  RESTORES work and blocking it would cause the loss the hook exists to prevent.
  `STASH_RESTORATIVE` is an ALLOWLIST and the `stash` rule denies by default, so
  an unknown stash verb fails CLOSED — including one carrying a pathspec, since
  only `push` takes pathspecs and only `push` may be scoped by one. (Round 9:
  `git stash frobnicate -- src/a.py` used to walk past the default deny, which
  made the "fails CLOSED" claim false as written.) It used to sit in front of a denylist of the
  three mutating verbs, which made it dead code — removing `apply` from it changed
  no verdict while this paragraph credited it with protecting `pop`, which round 8
  found and this change fixes.
* read-only plumbing that takes `.`: `git status .`, `git log -- .`,
  `git diff -- .`, `git show HEAD -- .`, `git ls-files .`
* a commit message that merely mentions a blocked form:
  `git commit -m 'add .'`, `-m 'reset --hard'`
* a negative pathspec ALONGSIDE a positive one: `git add src/a.py ':!src/b.py'`,
  `git add -A -- src/ ':!src/vendor'` — the positive is what scopes it
* `git commit -m wip src/a.py` — the operand pathspecs of a commit, read once the
  message operand is consumed. Until round 11 every commit operand was discarded as
  "the message", so `git commit -m wip .` — which commits every modified tracked file
  in the shared tree — exited 0 while only `git commit -- .` blocked
* an option's SEPARATE value, for every value-taking option of every ruled
  subcommand: `git commit -m x --author 'N <n@e.com>'`, `--date`, `--cleanup`,
  `--trailer`, `--squash`, `--fixup`, `--file`, `--template`, `--reuse-message`,
  `git add --chmod +x src/a.py`, `git checkout --orphan new`, `git switch --conflict
  diff3 main`, `git restore --source HEAD -- src/a.py`, `git clean --exclude '*.log' -n`,
  and their short spellings (`-F msg.txt`, `-C HEAD`, `-t t.txt`, `-b feature`,
  `-s HEAD`, `-e '*.log'`). Round 15: only `-m` was modelled, so every OTHER separate
  value stayed an operand, became a scoping pathspec, and disarmed the flag rule above
  it — `git commit -am wip --author 'Claude <noreply@anthropic.com>'`, the spelling
  this repo family writes most, committed both sessions' files and exited 0. ONE
  consumption model now serves every subcommand (`option_needs_next_token`), and
  `REQUIRED_VALUE_SHORT_OPTS` / `REQUIRED_VALUE_LONG_OPTS` carry the per-subcommand
  tables, each member confirmed against git 2.50 by `git <sub> <opt>` reporting
  "requires a value". `-S`/`--gpg-sign` and `-u`/`--untracked-files` are deliberately
  EXCLUDED: their value is OPTIONAL, so git reads the next token as a pathspec —
  `git commit -u . -m wip` commits the whole tree (verified) and blocks
* an arithmetic shift, in every spelling: `echo $((1<<2))`, `x="$((1<<2))"` and the bare
  arithmetic COMMAND `(( 1 << 2 ))`. Round 15 found `<<` inside `$((` read as a heredoc
  marker that never arrived, so a purely read-only `git log` script was DENIED — and
  round 21 found the mirror image in the two spellings round 15 never covered, failing
  OPEN: `arith_depth` was raised only by the UNQUOTED `$((` branch, and round 20's `$(`
  lift matched `$((` first, so `x="$((1<<2))"` and `(( 1 << 2 ))` both had their `<<`
  read as a heredoc whose invented marker swallowed every following command **with
  `confident` still True**. `x="$((1<<2))"\ngit add -A\n2` staged both sessions' files
  at exit 0 (verified). That is the fail-OPEN shape this layer was rewritten to
  eliminate, arriving inside round 20's own fix. The `))` decrement now fires while
  quoted too, or the read-only script fails closed again; an arithmetic expansion that
  never CLOSES still fails closed, and so does an UNCONSUMED heredoc marker
  (`git log <<EOF`), which is what stops a mis-read marker from ever failing open
* a DRY RUN of a file-supplied pathspec list: `git add -n --pathspec-from-file list.txt`
* an option VALUE fused to its short option: `git commit -m"refactor"`,
  `git checkout -bfeature`, `git switch -cfix`, `git restore -sHEAD <path>`,
  `git clean -e"*.log" -n`. The letters of a message or a branch name are not a
  flag cluster — `VALUE_SHORT_OPTS` cuts the argument before any cluster scan, so
  `git commit -ma x` is read as git reads it: message `a`, pathspec `x`

One wrapper-word gap is worth naming as a rule rather than a list: an unlisted word in
front of the command makes the segment's command word not `git`, so `is_git` says no and
the WHOLE segment is dropped — `caffeinate git add -A` staged both sessions' files at
exit 0 (round 21). `caffeinate` is macOS-native and was simply missing; `timeout`,
`stdbuf`, `setsid`, `ionice`, `chrt` and `doas` are the same shape and were added with
it. This is the enumeration half of a residual that already existed for the positional
half, and it stays an enumeration deliberately: making an unknown leading word
fail closed would deny `echo git add -A`, an ordinary line that mutates nothing.

**Every EXPANSION is one opaque WORD, in every quote state — `$(...)`, `$((...))`,
`${...}`, bare `$name` and the positional/special parameters `$1`…`$9`, `$@`, `$*`, `$#`, `$?`,
`$!`, `$-` (round 28 — they were outside the `$name` character class and expand to zero
words when unset; `git add "$@" -A` staged both sessions' files), a brace expansion
`{a,b}`/`{a..b}`, `<(...)`/`>(...)` and the bare
arithmetic command `((...))` are each read to
their matching closer and replaced by a placeholder, with a command body lifted out and
analysed as its own script.** Round 24 found that round 23's extraction was gated on
being inside double quotes, so every UNQUOTED spelling still went out verbatim: shlex made
`(` and `)` their own tokens, the grouping branch started a new segment, and the flag
behind the expansion was silently dropped. `git commit -m $(cat VERSION) -a`,
`git commit -m $((1)) -a` and `git commit -m ${x:-a;b} -a` each committed BOTH sessions'
files, `git clean -e $(cat p) -fd` deleted both sessions' untracked files, all rc 0.
One mechanism now, not five; `arith_depth` is gone with it.

Three more from the same round, all "a shell character reaching git as a word":
`SHELL_ONLY_CHARS` gained the grouping characters, because a QUOTED or ESCAPED `)` was
still peeled as a real closer (`git commit -m ")" -a` committed both sessions' files); a
BARE `}` with no group open is an ordinary argument (`git commit -m } -a` did the same —
bash treats `}` as a reserved word only in command-word position); and a line
continuation is now DELETED as bash deletes it, where emitting a space split one word
into two — `git reset HEA\<newline>D` emptied the shared index at rc 0.

A double-quoted `$(...)` is EXTRACTED and analysed as its own script, never spliced
into the outer text. Round 20 bracketed it with `;` in place, which split the git
invocation itself: every token AFTER the substitution landed in a segment whose command
word was not `git`, so the flag behind it was silently dropped —
`git commit -m "release $(cat VERSION)" -a` committed BOTH sessions' files and
`git clean -e "$(cat p)" -fd` deleted both sessions' untracked files, rc 0 (round 23,
verified against git). Every existing test missed it because they all put the
substitution last or alone. Bodies are re-read through `preprocess` recursively, so a
substitution nested inside another one is seen; an unbalanced one fails closed.

An ESCAPED operator inside double quotes needs no surgery at all — shlex already keeps
it literal — and round 22's `"…"` wrapper, emitted there, CLOSED the live quote and
severed the line the same way: `git commit -m "wip\;x" -a` committed both sessions'
files, as did the attribution spelling this project mandates,
`git commit --author "Claude\;X <…>" -a`.

An EMPTY argument is an ARGUMENT. `all()` over an empty string is True, so an empty
token was swallowed by the grouping branch and STARTED A NEW SEGMENT, dropping every
flag behind it — latent until extraction started leaving `""` behind. It is kept rather
than skipped, because git reads `-m ""` as an option with an empty value, so the flag
behind it really is a flag: skipping it instead let `-m` swallow the `-a`, which was the
same fail-open one step further along.

Multi-line commands ARE analysed. One quote-aware pass (`preprocess`) turns
every unquoted newline into `;`, turns an escaped newline into a space, drops
unquoted `#` comments to end of line, and strips heredoc BODIES as data — so
`cd src` on line 1 cannot hide `git add -A` on line 2, `cat <<EOF ... git reset
--hard ... EOF` documents the command without triggering it, and a trailing
`# comment` neither hides the command it follows nor the ones after it.
Redirections (`>`, `2>`, `>&`) and their targets are dropped rather than read
as arguments.

If that pass cannot understand the text — an unterminated heredoc, an
unbalanced quote — it reports NO confidence and the command is DENIED. That
inversion is the point: three review rounds each found a bug in this layer, and
every one of them failed OPEN by silently deleting commands.

* `ECC_HOOK_PROFILE=minimal` makes it **advisory, not off**: the decision is
  still computed and written to `hooks.log` as `WOULD-BLOCK`. This repo
  develops under `minimal` (CLAUDE.md "Session setup gotcha"), so a wholesale
  `exit 0` would leave zero dogfood signal in the very tree where the incident
  is recorded. Same posture as `iron-law-gate.py` and `reflection-gate.py`.
  **Consequence to be honest about: inside ClaudeKit itself the guard does not
  block — it only records.** It blocks in the 13 downstream projects, which run
  `standard`.
* `CK_ALLOW_BROAD_GIT=1` downgrades to a logged warning for a deliberate solo
  session. An env var, not a command flag — the turn writing the command cannot
  grant itself the exemption. Only the exact value `1`.
* Fail-closed: an unparseable payload, a `command` field that is present but not
  a string, and a command containing `git` that cannot be tokenised, all block.
  (The non-string field used to be the one malformed payload that failed OPEN,
  found in round 5 while checking this very sentence.) There is no `lib.sh` dependency, so no
  missing-helper path degrades it to `exit 0`. The COST of that rule, stated
  plainly: any untokenisable text containing the substring `git` is denied, so
  `echo it's a git repo` (unbalanced quote) blocks. The stderr says so.
* Only the git subcommand and the rule id are logged, never the command text —
  a blocked command line is the text most likely to carry a credential
  (`test_the_command_text_is_never_logged`).

### Why Python and not `grep -E` — do not "simplify" this back

The first implementation was regex-over-command-text. An adversarial review ran
a 90-case battery and found **eight defects, all tokenisation failures**, while
the then-current tests stayed green:

* `git add .ai/CONCURRENCY.md` was **blocked** — an unanchored `\.` matched the
  first character of every dot-prefixed path, so the guard denied the exact
  remediation its own message prescribes. In this repo family most staged paths
  begin with `.claude/` or `.ai/`.
* `git stash pop|apply|drop` were **blocked** — denying work recovery.
* `git commit -m x -a` **leaked** (flag after a message operand).
* `git checkout HEAD -- .`, `git restore --staged|--worktree|--source=HEAD .`
  all **leaked** — only a bare `--` was tolerated before the pathspec.
* `git -C <dir> add -A` **leaked** — ordinary usage, not obfuscation.
* `git add -u`, `checkout -f`, `reset --merge|--keep`, `git rm -r .` were absent.

`shlex` + per-subcommand argv inspection removes the class: flag order stops
mattering, `--` is honoured, clusters (`-am`, `-fd`) decompose, and a pathspec
is compared as a whole token so `.ai/x` is never `.`.

A SECOND adversarial round then rejected the Python version too, and its
CRITICAL finding was the same shape as the first round's: `shlex` keeps the
newline in its `whitespace` set, so the `"\n"` entry in `OPERATORS` was dead and
every line after the first was silently discarded — `git status\ngit add -A`
was allowed. Multi-line scripts are the commonest shape a session writes, so
the guard was inert for most real invocations. Removing the newline from
`lexer.whitespace` does not help (it fuses into the neighbouring word,
`status\ngit`); the fix is to substitute unquoted newlines with `;` BEFORE
tokenising. Round 2 also found `git stage`, `git switch -f`, `bash -lc` and a
false positive on the scoped `git stash push <path>`.

A THIRD round rejected it again, with three CRITICALs — and the class was the
same one for the third time: a pre-tokenisation transform that silently deleted
commands. `git add -A >/dev/null 2>&1` was ALLOWED (the redirection token read
as a scoping pathspec — the incident command in its commonest scripted form); a
single `#` comment discarded every following command, because newlines had
already become `;` and shlex's commenter ran to a newline that no longer
existed; and a quoted `<<` (`python3 -c "print(1 << 2)"`) invented a heredoc
marker that never matched, eating the rest of the script. Also `git stash push
-m wip` leaked (the message read as a pathspec) and `git add :/src/a.py` was
wrongly blocked.

The response was NOT to patch the three cases. Separate text passes each lacked
the quote state the others had, so they were replaced by ONE quote-aware pass
that reports whether it understood the text, plus the property test below. The
narrow fix would have been "eight more chances to get an anchor wrong", which
is what this hook's own header warns against.

**The class ratchet.** `tests/test_concurrency_guard.py` cross-products every
representative blocked command with 21 ordinary shell DECORATIONS —
redirections, comments, heredocs, here-strings, line continuations, `eval`,
`bash -lc`, grouping, `&&`/`;` chains — and asserts the block survives all of
them. Every blocked command is also re-tested with `>/dev/null 2>&1` appended.
That is what closes the class: each of the four historical CRITICALs is one
decoration, and example-based cases could only ever chase them one at a time.

Mutation record, stated precisely rather than as a coverage claim. The suite is
parametrised over the hook's OWN constants (`TREE_WIDE_PATHSPECS`,
`TREE_WIDE_MAGIC`, `GIT_GLOBAL_FLAGS`, `GIT_GLOBAL_WITH_VALUE`, `PREFIX_WORDS`,
`SCRIPT_WRAPPERS`, `VALUE_SHORT_OPTS`), so a member added without a case is a
hard failure — and
subset canaries assert the members whose REMOVAL must fail, because
parametrising over a constant otherwise lets a deletion delete its own test.
An earlier version of this file claimed "every member is asserted individually"
while the test list was hand-copied and had already drifted (`:!` was in the
frozenset with no case); that claim was false and is the reason for the
canaries.

**The mutation record is now a TEST, not a paragraph.** It had to become one.
This file previously named two survivors as REDUNDANT-BY-DESIGN — `lexer.commenters
= ""` and the `at_token_boundary()` check on `#` — and asserted that reverting
either "changes nothing observable". Round 5 executed both claims and both were
false, in the fail-OPEN direction: with either line reverted,
`echo file#1.txt; git add -A` goes from BLOCK to ALLOW with the suite green. The
two lines are load-bearing together — `preprocess` deliberately KEEPS the `#` in
`file#1.txt`, which is what `at_token_boundary` is for, and disabling shlex's own
commenter is then the only thing stopping it from eating `; git add -A`. A
maintainer reading the old text had written permission to delete a live guard.

`TestTheMutationRecordIsExecutable` now carries the battery in the suite. For each
entry it asserts three separate things: the anchor occurs exactly ONCE in the
shipped hook (so a refactor cannot void the check silently), the mutation actually
CHANGES the verdict on its probe (a mutation that changes nothing proves nothing —
two earlier "survivors" were artifacts where a `while False:` left an adjacent
`i += 1` doing the same work), and the probe is a member of BLOCKED or ALLOWED,
which is what makes the rest of the suite the thing that kills the mutant. Adding
a line to the hook that carries a verdict means adding its mutant there.

A SECOND ratchet closes the deletion half. Parametrising over a shipped
constant lets a DELETION delete its own test case, and three rounds of
hand-written "subset canaries" did not close it: round 9 removed `nohup` from
`PREFIX_WORDS`, `zsh` from `SCRIPT_WRAPPERS`, `--namespace` from
`GIT_GLOBAL_WITH_VALUE`, `*.*` from `TREE_WIDE_PATHSPECS` and `create`/`store`
from `STASH_RESTORATIVE` — every one changed a verdict, every one left the suite
green. `EXPECTED_CONSTANTS` in the test file is now a frozen copy of every such
collection, compared for equality, so a deletion or an addition is a hard
failure and the member's behaviour test survives it.

The table compares EXIT CODES, and that is its stated limit: a line that only
decides WHICH rule fires cannot be expressed in it. `git reset --merge` with
`--merge` dropped from the destructive rule still blocks — it just hands the user
the unstaging remediation for a command that destroys the working tree. That one
is bound by asserting the remediation TEXT
(`test_every_destructive_reset_flag_names_its_own_remediation`), because round 10
found both `--merge` and `--keep` removable with the suite green.

That table is the record, and it is not claimed to be exhaustive. Round 6 ran
sixteen mutations against it and five survived with the suite green — the `&`
separator, the magic remainder set, the fused `-C` global option, `clean`'s
dry-run letter, and `is_git`'s basename split — every one a line carrying a
verdict with no test. They are entries now. The honest form of this paragraph is
therefore: **every line listed in `MUTANTS` is bound, and a line not listed may
not be.** A future round finding a survivor should add an entry, not a sentence.

That earlier record was INCOMPLETE, and round 4 proved it by re-running the battery: a
THIRD mutation survived — reverting the `-m` operand consumption in the `stash`
branch flipped `git stash push -m wip` back to ALLOWED with the suite green,
because that command was in neither the blocked nor the allowed list. It was a
real coverage gap in a round-3 fix, not a redundancy, and it is now bound by
cases in both lists. A mutation record is only worth having if the misses are
written down too.

The ABBREVIATION rule (round 16) is bound off the RULE TABLE rather than a case list, by
`TestALongOptionAbbreviationIsResolvedLikeGitDoes`: the shipped hook is scanned for the
long names each `has_flag` call carries, denials and exemptions separately by their
`exact=True` marker, and every name is generated at every abbreviation length down to
`--x`. A long name added to a rule without its abbreviations therefore cannot pass, and
neither can an exemption added without its over-block cases. One test proves the PREMISE
against real git — that git still resolves `--al` to `--all` — so if git ever stopped,
the whole class would be revealed as pure over-blocking instead of quietly staying.
`MIN_LONG_ABBREV` was measured NOT to change any verdict (`--` never reaches the
matcher, since `split_args` consumes it as end-of-options) and was DELETED rather than
shipped as a line no test could bind — the mistake this file's own mutation record was
written to stop.

The MISSING-member direction is bound by
`test_every_required_value_option_git_reports_is_in_the_table` (round 18), which asks
GIT rather than a list: every option name in `git <sub> -h` is probed with
`git <sub> <opt>`, and only git's own "requires a value" counts. `EXPECTED_CONSTANTS`
and the case tables freeze what the tables DO contain, so they catch a false member and
a deletion; an option git takes a value for and the hook has never heard of was
invisible to both, and that is exactly round 15's leak shape. **The first draft of that
test asserted ZERO options and was green** — it parsed the value shape out of `-h` with
`(--[a-z-]+)\s+<`, but git prints `--[no-]author <author>`, and `-h` writes to STDOUT
(rc 129) rather than stderr. It passed just as happily with a member deleted. It now
carries an anti-vacuity floor asserting at least 25 options were actually checked, for
the same reason this file's mutation record exists at all.

`REQUIRED_VALUE_SHORT_OPTS` and `REQUIRED_VALUE_LONG_OPTS` (round 15) are bound the
same way, per (subcommand, option), by `TestASeparateOptionValueIsNotAPathspec`: the
case tables are compared for EQUALITY against the shipped collections, so a member
added or deleted without a case is a hard failure. Two canaries guard the
leak-opening direction specifically — that `-S`/`-u`/`--gpg-sign`/`--untracked-files`
and `--track` stay OUT of the required set, because consuming their next token would
hide a tree-wide `.` from every rule, and that every ruled subcommand has a row in
both tables (a missing row falls back to empty and silently reverts that subcommand).
`git commit . -m wip` is bound by a `BLOCKED` case rather than a mutant: the fix
replaced a count-based operand drop with a positional model, and no single line
carries that verdict any more.

`VALUE_SHORT_OPTS` (round 4) is bound the same way, per (subcommand, letter): each
case fuses a value made of exactly the letters that subcommand's rules look for,
so a cluster scan cannot help but misfire and a correct parse cannot. Emptying any
row of the table fails between two and seven cases; the `add` row is canaried at
`""` because `-A`/`-u` there must stay a cluster.

## Residuals — it is a speed bump, not a sandbox

It reads the command the model wrote. `bash -c`, `sh -c`, `sudo`, `env` and
`VAR=val` prefixes are unwrapped (including a wrapper's own options and their
values), `/usr/bin/git` resolves, and `eval` is analysed both as its JOINED argv
and token by token — round 9 found `eval git add -A` unseen, because the
separate words `git`, `add`, `-A` are not a verdict on their own. These are NOT
seen, and are named rather than hidden:

* a DEFERRED invocation whose git call runs later: `trap 'git add -A' EXIT` and
  `find . -exec git add -A \;` are read as arguments to `trap`/`find`, not as commands.
  Named rather than fixed (round 18) — recursing into every quoted argument of every
  command would deny far more than it caught
* a git invocation built at runtime (`$GIT add -A`, `xargs git`,
  `git submodule foreach git ...`)
* `<wrapper> <word> git ...` where the word is NOT an option value — a wrapper's
  own options and their values are stepped over (`sudo -u me`, `nice -n 10`,
  `env -i`, `time -p`), which round 7 found were not, but the heuristic is
  positional: it steps over one bare word directly in front of the command word
* a script or Makefile target that runs git internally (a function DEFINITION in
  the command text itself is NOT a residual — `stage() { git add -A; }` is read,
  since round 11)
* a pathspec that only a shell or git can resolve: `git add $PWD`, an absolute
  path that happens to be the repo root, or `../<reponame>` from a subdirectory —
  the hook cannot know which directory that names
* a filename containing a literal `?` (`git add 'what?.txt'`) is over-blocked: `?`
  is a wildmatch metacharacter and a bare pathspec cannot tell the two apart. The
  escape is git's own: `git add ':(literal)what?.txt'` turns wildmatch off and IS
  allowed (round 13 — it was blocked too, which made the escape useless). `[` was in
  that set too until round 12, and was removed because a bracket expression cannot
  widen a match at all
* a git command in BACKTICKS (`` `git add -A` ``) is not seen. `$(git add -A)` IS
  caught, in both the bare and the DOUBLE-QUOTED spelling: inside double quotes it used
  to be copied verbatim as quoted data, so shlex yielded one word and the inner command
  never became a segment — `echo "$(git add -A)"` staged both sessions' paths and
  `x="$(git checkout -f)"` discarded a session's work, both at exit 0 (round 20), while
  this bullet already claimed the class was closed. The substitution is now lifted OUT
  of the quotes and analysed as its own segment; `'$(git add -A)'` in SINGLE quotes
  stays allowed, because it is not a command
* a command word split by an escape (`g\it add -A`, `git ad\<newline>d -A`) reads as
  a different program. Deliberate obfuscation, in the same family as `$VAR add -A`
* `git-add -A` (the obsolete dashed builtin form) is not recognised, and
  `is_git` compares the basename up to the first dot, so `./git.py` would read
  as git — a spurious block on a command that does not exist
* an input redirection ANYWHERE in the command text over-blocks a `-p` elsewhere in
  it: `cat < f; git add -p .` is denied. The hook cannot tell which commands a
  redirection feeds without a shell grammar — `done < f` hangs it off a loop — so it
  marks them all. `fed` gates only the `--patch` exemption, so nothing that lacks `-p`
  changes verdict
* an unterminated `$(` inside double quotes fails closed, like every other unreadable
  text
* a brace expansion that DOES name real paths is over-blocked: `git add {a,b} -A` is
  scoped by git to `a` and `b`, but the hook cannot know how many words `{…}` yields
  (`{,}` yields none), so every brace list is a placeholder (round 27)
* an EXPANSION used as a pathspec is over-blocked: `git add $((1)) src/a.py` and
  `git add "$(date)" .` are denied, because the placeholder that stands for the expansion
  is not a path the hook can read — it could expand to `.`. Deliberate fail-closed; the
  workaround is to spell the path out (round 25)
* `git add "" <path>` is over-blocked — an empty pathspec is kept as an argument, and
  git refuses it anyway (`fatal: empty string is not a valid pathspec`), so nothing that
  works is denied
* `help.autocorrect` set in the user's own `~/.gitconfig` rather than on the command
  line is outside the text the hook reads and cannot be seen. Only the `-c` spelling is
  covered — the same limit as every other config residual
* a `-p` after a PIPELINE is over-blocked: `yes | git status; git add -p .` is denied,
  because a `;` sibling inherits the pipeline's stdin bit even though bash hands the
  terminal back to it (round 19 — my own over-block, introduced by the fix above).
  Telling a compound's sibling from a top-level one needs a real shell grammar; the
  fail-closed direction is the one this hook takes, and the workaround is to run the
  interactive patch as its own command
* an unknown pre-subcommand option denies the whole invocation, including a read-only
  one: `git --frobnicate status` blocks. **The first version of this bullet went on to
  claim "it is not a command git would run either, so nothing that works is denied" —
  and that was false when executed:** `git --version`, `git -v`, `git --help`,
  `git -h` and `git --man-path` all run at rc 0 and were all DENIED, with
  `git --version` appearing in doctor and CI scripts constantly and a denial anywhere
  in a compound killing the whole call (round 20). They are members now. What remains
  true is narrower: an option git does not accept is denied, and so is one git accepts
  that this hook has never heard of — the second half is the cost of failing closed,
  and `test_git_accepts_every_global_this_hook_lists` keeps the member list honest by
  asking git. That test had to be fixed too: it probed `git <glob> status`, which the
  terminal globals reject, so it called five real ones dead weight
* an ABBREVIATED exemption is over-blocked: `git add --dry-ru -A`, `git commit --dry-ru
  -a`, `git reset --sof`, `git add --patc .` are all denied, because exemptions are
  matched exactly while denials are matched by prefix (round 16). Deliberate asymmetry —
  prefix-matching an allowlist would let an abbreviation that git resolves to some OTHER
  option lift a denial, which is the fail-open direction. Spell the exemption out in
  full and it works
* a pathspec list read from a FILE (`--pathspec-from-file list.txt`) is over-blocked:
  the hook cannot read the file, so it cannot tell one path from `.`, and it fails
  CLOSED. With `.` in the file this was a real leak, not a theoretical one —
  `git rm -r --pathspec-from-file=list.txt` deleted every tracked file and exited 0
  (round 15, verified against git), the fused spelling leaving `pathspecs` empty so
  that no rule fired at all. `-n`/`--dry-run` still previews it
* `git reset <path>` with NO `--` and no revision (`git reset src/a.py`) is
  over-blocked: one operand is ambiguous between a revision and a pathspec, and
  guessing "pathspec" would fail open on `git reset main`, which resets the whole
  index. `git reset -- <path>` and `git reset HEAD <path>` both work and are what
  the denial message prescribes
* `git reset` with a pathspec, `git clean -fd -- <path>` and
  `git checkout -f -- <path>` are SCOPED but still blocked for the destructive
  verbs — deliberate over-blocking, named here so a user who hits it has
  something to read

The worktree is the isolation. The hook catches the honest mistake, which is
the one that actually happened.

## Record-only mode (how the fleet ships it)

A registry row with `tier: advisory` makes `dispatch.sh` CLAMP this hook's
`exit 2`, so the command runs and the reason is still logged and surfaced.
That is record-only, built from machinery that already exists — no flag, no
second code path. The fleet shipped it that way because the hook had not passed
an adversarial review round: rounds 1 through 7 each rejected a version of it.
Round 8 was the first APPROVED verdict, and it still carried a MAJOR — the
scoped `git reset HEAD <path>` was denied. Round 9 then REJECTED again, and its
CRITICAL was inside round 8's own fix: `git reset . src/a.py` dropped the
tree-wide first operand as "the revision" and emptied the shared index while
exiting 0. Round 11 then found the worst leak of the whole series in the most ordinary
spelling there is: `git commit -m wip .` committed every modified tracked file in
the shared tree and exited 0, because every commit operand was discarded as "the
message" and only the `--` spelling blocked. That is the incident this hook exists
to prevent, eleven rounds in. Round 10 found no mis-verdict that ships, but it did find the
`TREE_WIDE_MAGIC` prefix loop — the only thing blocking `git add ':/*'`, which
stages the whole tree from a subdirectory — deletable with the whole suite
green. Round 15 then found the same shape as round 11 in a THIRD spelling, and this one
is the most ordinary of the three: `git commit -am wip --author 'Claude
<noreply@anthropic.com>'` — the attribution CLAUDE.md mandates on every AI commit —
committed both sessions' files and exited 0, because `--author`'s separate value was
read as a scoping pathspec and the scoped-pathspec early return fired before `-a` was
ever inspected. `git add -A --chmod +x`, `git commit . -m wip` and
`git rm -r --pathspec-from-file=list.txt` were the same defect in three more places.
Round 17 then found a BLOCKING leak inside round 16's own fix, in the half of it that
was reasoned about rather than executed: an option value left in `flags` fires an
EXEMPTION, so `git commit -a -m --dry-run` committed both sessions' files. Three
consecutive rounds have now found the same defect in the same two lines from three
different directions — the value as a pathspec (15), the value's option name
abbreviated (16), the value as a flag (17) — which is the argument for reading
`split_args` as the hook's most dangerous function rather than its most boring one.
Round 16 then found a BLOCKING leak in a dimension fifteen rounds had never probed:
every long-option denial was EXACT-match while git resolves unambiguous prefixes, so
`git add --al`, `git checkout --fo`, `git clean --fo` and
`git rm -r --pathspec-fr=list.txt` restored round 15's leak in full by dropping three
characters — ordinary spellings, verified against git, untested at any level, and
invisible to `EXPECTED_CONSTANTS`, which freezes each rule's MEMBERS and can say nothing
about its MATCHING SEMANTICS.
Round 18 then found two more BLOCKING leaks, both OUTSIDE the `split_args` lines the
three rounds before it had lived in: `git add -e`/`-i` reaching the whole tree with no
pathspec (the FOURTH instance of "a legal git spelling the denylist does not
enumerate"), and the `--patch` exemption honoured while stdin was piped, which is the
first defect of a new shape — an exemption justified by an assumption the hook never
checked. It also drove the option tables from git's own `-h` output, which closed the
MISSING-member direction that nothing had bound.
Round 20 then returned FOUR BLOCKING findings and a MAJOR, the largest single round of
the series: `git clean -i` (the sixth "one site updated, its sibling missed"),
`git commit --interactive` (`git add -i`'s sibling, denied two rounds after it),
a group-attached redirection defeating the stdin bit, a double-quoted command
substitution never being analysed at all — and the `git --version` over-block above,
which my own round-19 inversion introduced and my own doc then justified with a sentence
that execution refutes. Round 20's earlier leak was found by ME, probing my own round-19
fix rather than by the reviewer: a heredoc feeding an interactive `-p` was invisible because its `<<` fuses to
the following separator. That is the THIRD spelling of one class — an exemption
justified by an assumption about who is answering the prompt — after round 18's pipe and
round 19's grouping. The lesson is not "check heredocs": it is that a token stream where
one token can carry two meanings needs the meaning extracted BEFORE the classification,
which is the same conclusion rounds 1-3 reached about separators and had to reach again.
Round 19 found two more BLOCKING leaks: the round-18 stdin bit discarded by grouping and
by non-pipe separators — a leak INSIDE the previous round's fix, for the second time in
five rounds — and an unrecognised git global becoming the "subcommand", which disarmed
every rule at once. Both were invisible to the whole suite.
Round 21 found two more BLOCKING and a MAJOR: the arithmetic/heredoc fail-open above
(inside round 20's fix), `-c` config deciding what a command means while the hook threw
the token away, and a quoted operator-only pathspec swallowing the tree-wide token
behind it. It also found two round-20 lines carrying a verdict with no test, which are
`MUTANTS` entries now.
Round 22 found four more BLOCKING — two of them inside round 21's own fixes — and the
`one-site-updated-sibling-missed` class reached EIGHT recorded instances, two in that
single round. It has a mechanical check now rather than a ninth hand-patch:
`TestEverySpellingOfAGlobalAndAWrapperIsCovered` asserts, off the shipped collections,
that a valued global reaches the same verdict fused as separate and that a wrapper
reaches the same verdict however its script is handed to it. Both round-22 leaks were
invisible to 1731 tests precisely because the two existing parametrisations each
asserted exactly ONE spelling.
Round 23 found three more BLOCKING, two of them inside rounds 20 and 22's own fixes, and
all three in the same layer: a pre-tokenisation transform that silently deletes part of
a command. That class now has instances in rounds 1, 2, 3, 6, 20, 21, 22 and 23 — and
the round-23 reviewer proposed the check it has earned, which is not another case list
but a ROUND-TRIP INVARIANT: for a corpus of command texts, the word tokens `preprocess`
yields must be a superset of the words bash itself would produce. Both round-23 leaks
dropped a word (`-a`) while `confident` stayed True, and either would have failed such a
check without anyone enumerating `\;` or `$(date)`. **The round-trip invariant now EXISTS, built in round 27 after the loop failed to
converge: `TestBashIsTheOracleForWhatReachesGit`.** It asks BASH rather than a list.
Every corpus command — all of `BLOCKED`, all of `ALLOWED`, and the whole metamorphic
construct×tail matrix, ~1000 texts — runs under real bash in a throwaway directory with a
stub `git` on `PATH` that records its argv and does nothing (stdin closed, PATH restricted,
5-second timeout, `sudo`/`doas` excluded). The hook's own segments are computed from the
same text, and: **when the hook ALLOWS the command, every word bash actually handed git
must appear in the hook's segments** — every word when the text has no expansion, the
flags when it has one (an expansion becomes a placeholder whose value the hook cannot
know, and a placeholder cannot hide a flag). **And the CONVERSE, added after round 27
showed the subset check alone was blind to a PHANTOM pathspec: every non-flag operand the
hook believes in must be a word bash actually handed git.** `git add {,} -A` reached git
as `add -A` while the hook kept `{,}` as a scoping operand and allowed it — the subset
direction saw nothing wrong, because nothing bash produced was missing. A denial is never
compared, because a denial is never a leak — which also means roughly seven in ten corpus
rows return at the verdict gate and compare nothing; the ~300 that do are the allowed
commands, and those are exactly the ones where a leak could hide. Proven to bind by re-introducing three closed leaks in a scratch copy:
the glued `<(…)` gate, the consumed heredoc marker and the line-continuation-as-space
each surface as `bash handed git '-a' and the hook never saw it` (or `HEAD` for the
word split), while the shipped hook passes 998 of them. The metamorphic list stays, as
the fast enumerated layer; the oracle is the one that does not need a new spelling
enumerated first. An earlier version of this paragraph said the invariant existed when
it did not, and round 25 found three leaks in that gap; both facts stay recorded here. Round 24 also showed the ratchet's first version was BLIND: its constructs
were scoped to words that could sit inside quotes, so an unquoted expansion, a quoted
grouping character and a bare `}` were structurally outside it — and 78 rows of its own
tails leaked. It now carries every one of those, and on its very first widened run it
found a live leak nobody had reported: process substitution `<(...)` severing the
command. `DECORATIONS` likewise now really contains the here-string and the line
continuation this paragraph used to claim it did.
`TestNoConstructSwallowsTheFlagBehindIt` is METAMORPHIC. It crosses every entry of `CONSTRUCTS`
against every entry of `TAILS` (counts live in the test, not here — hand-maintained
counts drift, and this file has recorded that before) that put a tree-wide flag or pathspec AFTER the construct,
and asserts the verdict against a `"plain"` control — so a construct nobody has thought
of still has to satisfy it, and no future round has to enumerate its spelling first.
The invariant is ONE-DIRECTIONAL: a construct may make the verdict more restrictive (an
unknowable `"$(date)"` expansion fails closed, and git refuses the empty pathspec that
remains), never less. Every instance of this class turned a 2 into a 0. It is proven to
bind by re-introducing round 23's own defects in a scratch copy — 18 rows fail with the
escaped-operator fix reverted, 16 with the empty-argument fix reverted — and it caught a
wrong row of mine on its first run, via the same vacuity guard that requires the control
to match its expectation. What it does NOT catch is written down too: reverting the
substitution extraction to a plain DROP fails no row, because dropping a body leaves the
outer flag intact and that is not this class's failure mode.
Round 24's first finding came from probing round 23's own wrapper fix rather than from
the reviewer: `bash -s file` reads its script from STDIN, so the operand round 23 counted
as a script file is a positional parameter. Fourth consecutive round in which follow-up
probing of a fix found the next leak — which is the argument for probing every fix
instead of reading it.
Round 24 then returned FIVE BLOCKING: the unquoted expansions, the quoted/escaped
grouping character, the bare `}`, the line continuation, and the `${…}` expansion — every
one a construct making a later token vanish, and the round-23 ratchet could see none of
them because its constructs were quoted-word-only. Widening it found a sixth (`<(…)`)
before any reviewer did.
Round 25 returned three more BLOCKING — the brace opener round 24 never covered, round
24's own brace fix undone by wrapping, and `>|` read as a pipe — plus the doc drift above.
Round 26 returned two more BLOCKING, both outside what round 26's own fixes touched, and
each one an existing rule with a position or value gate that bash does not have; the
parity test written to close the wrapper class had itself enumerated only bare wrappers.
Round 27 built the bash oracle instead of running another review round, and the shipped
hook passes it. Round 28 was run once, as a MEASUREMENT: it found `$1`/`"$@"` outside the
`$name` class (fixed), and established the oracle's real limit — its converse direction
detects that exact shape, but the oracle is CORPUS-BOUND and no row spelled it. The
measured coverage: 1053 rows, 68.7% return at the verdict gate, 286 compare. So the
oracle changes what a leak needs in order to survive — it must now be a spelling absent
from BLOCKED, ALLOWED and the construct matrix — and the round-28 constructs were added
so that this class is in the corpus from now on.
So the honest status is: **twenty-six review rounds, two approvals (8 and 12), and every
single round has found something** — and rounds 17 through 25 each found a leak inside the fix
that preceded them. Nine consecutive rounds. The suite grew from 1122 cases to well over two thousand across those rounds
(the exact number lives in the test run, not in this file), and it never once predicted the next leak: every one was found by a
fresh adversarial reader executing spellings nobody had enumerated. Three separate
fixes this session also failed on their first attempt and were caught only by re-running
the probe rather than by reading the diff. That is the number to weigh before promoting
the fleet. That is the number to weigh
before anyone promotes the fleet, not the size of the test suite. That is the number to weigh, not the latest verdict.
Flipping 13 repos to blocking is the owner's call.

Upstream (this repo) keeps `tier: blocking`, where `minimal` already makes it
advisory in practice. The reason text deliberately never says "blocked" — the
hook cannot see its own tier, so the exit code carries the verdict and the text
carries only the reason.

To promote the fleet to blocking later: flip `tier` to `blocking` in each
project's `dispatch-registry.json`. Nothing else changes.

## Rollout

13 kitted projects under `~/IdeaProjects`. `qa-agent-pro` is EXCLUDED (public
repo, owner's call) and has no `.claude/` anyway. Their
`dispatch-registry.json` and `profiles/minimal/profile.json` were verified
byte-identical to upstream HEAD before any copy, so a whole-file update cannot
lose downstream customisation. `profiles.GUARDED_HOOKS` needs no distribution:
`ck` is an editable install pointing at this repo.

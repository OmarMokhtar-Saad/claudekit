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
| `add`/`stage` with `-A` `-u` `--all` `--update`, or a tree-wide pathspec | `git add path/to/file` |
| `commit -a` / `--all` (any flag position, any cluster) | `git add <paths>` then `git commit` |
| `reset --hard` / `--merge` / `--keep` | `git restore --source=HEAD -- <path>` |
| `reset` bare or `--mixed` with no pathspec | `git reset -- path/to/file` |
| `checkout` / `restore` / `switch` with a tree-wide pathspec | `git restore -- <path>` |
| `checkout -f` / `switch -f` / `--discard-changes` | commit your work first |
| `clean -f` / `-d` / `-x` (unless `-n` / `--dry-run`) | delete the files you created |
| `stash` bare / `stash push` (unscoped) / `save` / `clear` | commit to your own branch |
| `rm` with a tree-wide pathspec | `git rm path/to/file` |
| `worktree remove --force` | let the owning session close its own worktree |

`stage` is git's own synonym for `add`, and `switch -f` throws away local
modifications exactly as `checkout -f` does — an earlier draft of this document
prescribed `switch` as the *remediation* for a blocked `checkout -f`, which
pointed at an unguarded synonym.

A tree-wide pathspec means `.` `..` `*` `**` `:/` `:` `:!` and their
trailing-slash forms, compared as WHOLE tokens so `.ai/x` is never `.`. The
magic prefixes `:/` `:(top)` `:(glob)` `:(exclude)` count only when what
FOLLOWS them is empty or itself tree-wide: `:/` blocks, `:/src/a.py` is a
scoped single file and is allowed. `::x` is not tree-wide at all — a second
colon ends the magic signature, so it is just the path `x`.

**Explicitly allowed**, because they are scoped or give work back:

* `git add -A -- src/`, `git add -u -- src/` — a pathspec scopes the flag
* `git add -- -A` — `--` ends the options, so `-A` is a filename
* every dot-prefixed path: `git add .ai/x.md`, `.gitignore`, `./src/a.py`
* `git add -p`, `git commit --amend`, `git reset --soft`, `git reset -- <path>`
* `git checkout <branch>`, `git switch <branch>`, `git checkout main -- src/`
* `git restore -- <path>`, `git clean -n`, `git clean --dry-run`
* **`git stash push src/a.py`** — the ordinary scoped stash; and
  **`stash apply` / `pop` / `drop` / `branch` / `list` / `show`**, because `pop`
  RESTORES work and blocking it would cause the loss the hook exists to prevent
* read-only plumbing that takes `.`: `git status .`, `git log -- .`,
  `git diff -- .`, `git show HEAD -- .`, `git ls-files .`
* a commit message that merely mentions a blocked form:
  `git commit -m 'add .'`, `-m 'reset --hard'`

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
* Fail-closed: an unparseable payload, and a command containing `git` that
  cannot be tokenised, both block. There is no `lib.sh` dependency, so no
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
`SCRIPT_WRAPPERS`), so a member added without a case is a hard failure — and
subset canaries assert the members whose REMOVAL must fail, because
parametrising over a constant otherwise lets a deletion delete its own test.
An earlier version of this file claimed "every member is asserted individually"
while the test list was hand-copied and had already drifted (`:!` was in the
frozenset with no case); that claim was false and is the reason for the
canaries.

Of the mutations tried against the current hook, two survive, and both are
REDUNDANT-BY-DESIGN rather than gaps — named here so nobody deletes them
because "tests still pass":

* `lexer.commenters = ""` — `preprocess` already removed every comment, so
  reverting this line changes nothing observable. It stays as a second barrier
  against the exact interaction that produced a CRITICAL.
* the `at_token_boundary()` check on `#` — every realistic case is either
  quoted or stays non-tree-wide either way.

The rest are caught, including all four historical CRITICALs. Two earlier
"survivors" turned out to be MUTATION ARTIFACTS, not coverage gaps: a `while
False:` left an adjacent `i += 1` doing the same work by accident. A mutation
that does not change behaviour proves nothing about the test.

## Residuals — it is a speed bump, not a sandbox

It reads the command the model wrote. `bash -c`, `sh -c`, `sudo`, `env` and
`VAR=val` prefixes are unwrapped, and `/usr/bin/git` resolves. These are NOT
seen, and are named rather than hidden:

* a git invocation built at runtime (`$GIT add -A`, `xargs git`,
  `git submodule foreach git ...`)
* a script or Makefile target that runs git internally
* a pathspec that only a shell or git can resolve: `git add $PWD`, or an
  absolute path that happens to be the repo root
* `git-add -A` (the obsolete dashed builtin form) is not recognised, and
  `is_git` compares the basename up to the first dot, so `./git.py` would read
  as git — a spurious block on a command that does not exist
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
second code path. The fleet ships it that way because the hook has not passed
an adversarial review round: three rounds each rejected a version of it, and
the round-3 fixes are unreviewed. Blocking on 13 repos on the strength of an
unreviewed guard would be exactly the false assurance this doc warns about.

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

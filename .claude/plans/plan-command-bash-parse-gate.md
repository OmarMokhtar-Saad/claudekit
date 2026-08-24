# Implementation Plan: a parse-error gate for command bash

**Status:** **EXECUTED 2026-08-24** — owner approved "land it". Enabling a new CI gate is
owner-gated and the pytest suite is CI, so this needed the answer it got. Proven both ways
before and after landing; see Artifacts.

Job 5 of handoff 9. `.claude/commands/*.md` ships bash that nothing lints.

## The measurement, re-derived

    $ 27 command files, 682 lines of bash inside ```bash fences

682, not the handoff's 688 — re-derive it rather than quoting either number. `shellcheck` in
CI covers `install.sh` and `.claude/hooks/*.sh`; the command corpus is outside it. Six parse
errors of one shape (`<TASK>`, `<N>` and friends inside `[ ]`) were fixed by
`plan-command-bash-placeholders.md`, and **nothing keeps them fixed.**

## The argument, which is the whole reason to land this

Without the gate the class reopens silently, and that is not a prediction — **it happened
during the fixes themselves.** A comment written while repairing those six errors put markdown
backticks inside a `python3 -c "..."` shell string, where a backtick is command substitution.
The corpus can go red again on the next prompt edit and no gate anywhere would say so.

This is the handoff's lesson 1 in its constructive form: a class that was fixed without a gate
is a class that is scheduled to return.

## Design — settled, and deliberately narrow

- Extract every ```bash fence per command file, concatenate with a synthetic shebang.
- `shellcheck -s bash -f gcc -` over the concatenation.
- **Fail on parse errors only:** `SC1072`, `SC1073`, `SC1009`. Style findings are out of scope.
- Map shellcheck's line numbers back through a per-line index so a failure names
  `<file>.md:<line-in-the-markdown>`.

**Why parse errors only.** A gate must be satisfiable the day it lands or it gets routed
around — this repo has already recorded that lesson (`ops-dispatcher-payload.json`'s H1: an
over-tightened gate "would have reddened CI on correct plans; a gate that cries wolf gets routed
around"). Parse errors are the class that is currently at zero, so the gate lands green and
stays meaningful. Style rules would land red on 682 lines of prose-adjacent bash.

**Why concatenate per file rather than per fence.** Fences share state — a variable set in one
block is used in the next. Linting each fence alone produces SC2154 noise the gate would then
have to suppress, and suppressions are where gates go to die.

## Proof it binds — run, not asserted

Prototype at `scratchpad/parse_gate.py`. Clean corpus:

    $ python3 parse_gate.py .claude/commands
    0 parse error(s)
    rc=0

Reintroduce the exact placeholder shape that produced the original six, into a **copy** of the
corpus, and verify the mutation landed before reading the result:

    $ grep -n '<N> -gt 3' cmdmut/adapt.md
    38:if [ <N> -gt 3 ]; then echo hi

    $ python3 parse_gate.py cmdmut
    cmdmut/adapt.md:38: SC1009 The mentioned syntax error was in this if expression.
    cmdmut/adapt.md:38: SC1073 Couldn't parse this test expression. Fix to allow more checks.
    cmdmut/adapt.md:38: SC1072  Fix any mentioned problems and try again.

    3 parse error(s)
    rc=1

**Both directions, and the line number is exact** — inserted at markdown line 38, reported at
markdown line 38. The line-mapping half is the part most likely to be wrong and silently
useless, so it is the part the proof pins.

**A near-miss worth recording.** My first mutation targeted `ship.md` and the gate stayed green.
`ship.md` has **zero** ```bash fences — `grep -c '```bash' ship.md` → 0 — so nothing was
inserted into a linted region. `grep` for the mutation returned nothing and *that* is what
caught it, not the gate's output. Handoff lesson 2, met on the first attempt: a GREEN from a
mutation that never landed is worse than no test, because it certifies the gate works.

## What landing it means

- A new test in `tests/`, so it runs in CI. **That is the owner-gated part.**
- Currently green, so it lands without a red CI.
- The permanent cost: any future command edit that breaks bash parsing fails the suite with a
  `file.md:LINE` pointer. That is the intent.

## Explicitly NOT in scope

- No style rules, ever, in this gate. A second gate can argue for those on its own merits.
- No changes to the 682 lines themselves — the corpus is clean today.
- No extension to `.claude/agents/*.md` or skills, which also contain bash. Same shape, separate
  decision, separate measurement.

## Ops shape, if approved

One config: the gate module plus its test, and a `tests/` entry that runs it over
`.claude/commands`. Mutation evidence re-run at execution time and pasted into the archive row —
the proof above was taken against a scratch copy, and a proof from a scratch tree is a proof
about a scratch tree.


## Artifacts — EXECUTED 2026-08-24, owner-approved "land it"

| Path | Config |
| --- | --- |
| `tests/test_command_bash_parse.py` | `ops-command-bash-parse-gate.json` |

Seven tests. The corpus is clean, and the mutation proof is **inside the suite** rather than
only in this document: `test_the_gate_catches_a_reintroduced_placeholder` builds its own fixture
so the mutation cannot fail to land — which is precisely how the first hand-run went wrong
(`ship.md` has zero ```bash fences, so nothing was inserted and the gate reported GREEN).

Re-proven against the **shipped** corpus at execution time: inserting `if [ <N> -gt 3 ]; then`
into `.claude/commands/adapt.md` at markdown line 38 fails
`test_no_command_bash_has_a_parse_error` with `adapt.md:38: SC1009/SC1073/SC1072`; restoring the
file returns 7 passed. The mutation was confirmed present with `grep` before the result was read.

**No independent review** — same as the sibling plans this period.

## The honest caveat

This gate catches **parse** errors. It does not catch a command whose bash parses and is wrong,
and it does not catch the backtick-in-a-python-string defect that motivated it *unless* that
defect breaks parsing — in the recorded case it did, but a backtick inside a double-quoted
string that happens to parse would sail through. Do not describe this as "command bash is now
linted". It is "command bash can no longer be syntactically broken without CI saying so."

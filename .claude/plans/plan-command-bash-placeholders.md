# Implementation Plan: shell placeholders in command bash blocks

**Status:** EXECUTED 2026-08-24. 2 ops configs, 8 edits across 6 command files.
**The gate that would keep this closed is NOT landed — it is owner-gated. See below.**

## How this started, and why the assigned job could not be done as written

Handoff job 5 asked for the command diet, whose "genuinely valuable slice" was named as:
`refine.md` holds ~196 lines of fenced content, 89 of them bash, none of it linted —
so extract that script to `.claude/operations/scripts/` and it comes under `shellcheck`.

**Two corrections, both measured.**

1. **The numbers moved.** `refine.md` is now **464 lines with 181 fenced, of which 84 are
   bash**. The 196/89 figures predate the 468 → 464 trim in `ops-refine-trim`.
2. **There is no script to extract.** The bash blocks are *fragments* of a loop —
   `<TASK>`, `<N>`, `<MAX_ITER>`, `$iteration` assigned somewhere in prose, no loop
   wrapper. `tests/test_delivery_contract_smoke.py`'s own module docstring already says
   this: "`/refine`'s scripted mode is pseudocode fragments across several markdown
   sections with `<N>`/`<MAX_ITER>`/`$last_score` placeholders that aren't a standalone
   runnable script". Extracting would mean **writing a new script** and changing behaviour
   on a CI-facing path, not moving an existing one.

So the goal was pursued by the other route — put the bash under `shellcheck` where it
lives — and that immediately paid.

## What the measurement found

`.claude/commands/*.md` holds **688 lines of bash across 25 files, and none of it was ever
linted**: `shellcheck` in CI covers `install.sh` and `.claude/hooks/*.sh` only. Extracting
each file's `bash` blocks and running `shellcheck -S warning` found findings in 12 files —
and **6 of them were parse errors of one identical shape**:

| Site | As written | What bash actually does |
| --- | --- | --- |
| `worktree.md:57` | `git branch -D agent/<slug>` | deletes branch `agent/`, stdin redirected from a file named `slug` |
| `prp-commit.md:51` | `git add <specific matched files>` | `git add` with no paths |
| `prp-implement.md:78` | `python3 -m py_compile <file>` | compiles nothing |
| `gan-build.md:154` | `python3 -m py_compile <generated files>` | same, inside a real `&&` chain |
| `refine.md:203` | `... --from-review <saved-output-file>` | flag with no value |
| `review.md:115` | `... --from-review <saved-output-file>` | the same line, second copy |

**An angle-bracket placeholder in a shell command position is not a placeholder — it is an
input redirection.** These files are prompts an agent copy-pastes from, so the failure is
real even though nothing in CI executes them. `refine.md:203` and `review.md:115` are the
same command written two ways, and the *correct* form already exists 82 lines below
`refine.md:203` (`--from-review -` with a pipe) — the third
`claim-not-corrected-everywhere-it-was-made` shape in a month.

## What shipped

- **Config 01** quotes the placeholder at all six sites. Quoted, the line parses, still
  reads as a placeholder, and **fails loudly instead of strangely** if pasted verbatim.
- **Config 02** re-fences two blocks as `text` rather than `bash`, because they are usage
  synopses and never were scripts: `prp-implement.md`'s "Run commands from plan" block
  (whose entire body is `<commands from plan>`) and `worktree.md`'s four-line
  `worktree-manager.py` interface listing (six competing redirections, SC2261).

**Fixing the first parse error in `prp-implement.md` exposed a second at `:91`** — shellcheck
stops at the first one, so the count of parse errors is never trustworthy until the file
parses. Worth remembering: this class hides behind itself.

Result: **0 parse errors across all 25 command files**, down from 6 files.

## What is deliberately NOT fixed

Seven files still carry style/info findings — `SC2034` unused variable
(`build-fix`, `code-review`, `santa`), `SC2046` unquoted expansion (`build-fix`), `SC2010`
`ls | grep` (`blueprint`), `SC2011` (`eval`), `SC1081` (`opensource`), `SC2154` `iteration`
referenced but not assigned (`refine`). Most are artifacts of the fragments-not-scripts
reality rather than defects, and each needs a judgement call. Filed, not swept.

## THE GATE IS NOT LANDED, and that matters

A fix with no gate reopens silently, which is the failure this repo keeps rediscovering.
The gate here is small and currently green: extract each command's `bash` blocks, run
`shellcheck` over the concatenation, and fail on **parse errors only** (`SC1072`/`SC1073`/
`SC1009`), leaving the style findings above out of scope so the gate is satisfiable on the
day it lands. The extractor already exists as throwaway script in this session's scratchpad
and maps shellcheck's line numbers back to the markdown line, so a failure names
`file.md:LINE` directly.

It is not landed because **enabling a new CI gate is owner-gated** and the pytest suite is
CI. This is the one piece of this plan awaiting a decision; everything above ships without
it.

## Definition of Done

Documentation-only edits: the full `CLAUDE.md` gate list, plus `ck lint` (the command-budget
ratchet — config 02 removes 6 bash lines and adds none, so the ratchet tightens).

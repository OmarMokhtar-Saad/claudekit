# Implementation Plan: Declarative output filter for noisy Bash (adoption item B1)

**Verdict: ADOPT, at 1/64th of the source's scope.** The design transfers. The corpus does
not. Measurement (below) says **one** filter captures 97% of the strippable bytes in this
repo, and two of the three commands named in the task brief do not survive measurement.

## Overview

Add a stdlib-Python `PostToolUse` hook that rewrites the `stdout` of matched Bash commands
using declarative JSON filter definitions, with a two-level override hierarchy (kit base +
project local). Ship exactly **one** base filter — pytest progress lines — because that is
the only candidate the measurement justifies. No Rust, no TOML, no new dependency, no new
file in `.claude/hooks/`.

## Phase 0 — Design precheck

**Ownership/data model.** The value of this change sits in exactly two files:
`.claude/operations/scripts/output_filter.py` (the mechanism) and
`.claude/operations/scripts/output-filters.json` (the one filter that pays for it). A third
file, `output-filters.local.json`, is *never written by this plan* — it is created per
project downstream. `.claude/settings.json` carries the registration. Everything else is
documentation. The model this assumes: **a filter owns `stdout` and nothing else**; `stderr`,
the exit status, and every other field of the Bash `tool_response` are outside the filter's
ownership and are echoed back byte-for-byte.

**Rejection-brief search** (mandatory, run 2026-09-16):

```
$ python3 .claude/operations/scripts/review-record.py rejections search "output filter PostToolUse hook token bash"
REJECTIONS: 10 match(es) ...   (exit 0)
```

Two hits are validated against the current tree and bind this plan:

1. `agent-memory-learning` (round 2, REVISE 81), CRITICAL: *"HOOK_GLOBS includes `*.py` so
   the hook count …"*. Verified still live — `scripts/gen-docs.py:75` reads
   `HOOK_GLOBS = ("*.sh", "*.py")` and `_hook_files()` globs `.claude/hooks/`. **What this
   plan does differently:** it puts no file in `.claude/hooks/` at all. The hook script goes
   to `.claude/operations/scripts/`, the precedent `heal_local_settings.py` set.
2. `agent-memory-learning`, MAJOR: *"Two contradictory measured totals … Fix: one number,
   labelled."* **What this plan does differently:** every number below is stated once, with
   the command that produced it and whether it is measured or extrapolated.

`python3 .claude/operations/scripts/project-graph.py hubs` → exit 1, no graph in this tree;
blast radius is argued from `install.sh` and `preserve_assets.py` directly instead (see
Risk Assessment).

---

## The mechanism actually exists (verified, not assumed)

This is the step that killed adoption item A1, so it is done first here. Claude Code
**2.1.273** (`claude --version`), binary at
`/Users/omarmokhtar/.local/share/claude/versions/2.1.273`:

| Fact | Evidence (string-extracted from the binary) |
|---|---|
| PostToolUse may replace tool output | `updatedToolOutput: … .describe("Replaces the tool output before it is sent to the model")` |
| It works for all tools, not just MCP | `updatedMCPToolOutput … "Prefer updatedToolOutput, which works for all tools"` |
| A bad-shaped rewrite is discarded, not applied | `"PostToolUse hook returned updatedToolOutput that does not match <tool>'s output shape … using original output."` guarded by `e.outputSchema?.safeParse(ts)` |
| `PostToolUseFailure` has **no** rewrite field | `hookEventName:R("PostToolUseFailure"),additionalContext:o().optional()` — that is the whole schema |
| Hooks run in parallel on the ORIGINAL output; rewrites are last-write-wins | `"hooks run in parallel on the ORIGINAL output, so an identity rewrite competes last-write-wins with sibling rewrites and can clobber a real redaction"` |
| Bash `tool_response` shape | `{stdout, stderr, interrupted, isImage, returnCodeInterpretation, noOutputExpected, backgroundTaskId, …}` — note there is **no exit-code field** |
| Successful Bash output is already capped | `bashOutputMaxChars … "(default 30000, values clamp to 4000-128000). Output past this is saved to a file and Claude receives a short preview plus the path."` |
| That preview is **head**-biased | `"Output too large (N). Full output saved to: <path>" + "Preview (first N):"` |

**Empirical check of the failure path** (2026-09-16, this session): a deliberate
`false; exit 3` Bash call produced **no** `[post-tool-use]` line in
`.claude/hooks/hooks.log`, while the successful calls immediately before and after it did.
PostToolUse does not fire for a Bash call that exits non-zero.

---

## Measurement — and what it kills

**Corpus:** `.claude/hooks/hooks.log`, the repo's own PostToolUse audit trail.
4,355 Bash tool calls over 12 active days (2026-09-04 → 2026-09-16), extracted with
`grep -h "Tool: Bash | Target: "`.

**Per-call output sizes, measured 2026-09-16 by running each command and counting bytes:**

| Command | bytes/call | lines | calls/12d |
|---|---:|---:|---:|
| `python3 -m pytest tests/ -q` (full suite, green) | **12,940** (extrapolated, method below) | ~157 | 34 |
| `git status` | 1,075 | 23 | 71 |
| `ck doctor --strict` | 1,546 | 40 | ~5 |
| `python3 scripts/gen-plan-index.py --check` | 863 | 12 | 30 |
| `python3 scripts/gen-docs.py --check` | 77 | 1 | 6 |
| `ruff check src/ tests/ scripts/ .claude/operations/scripts/` | 18 | 0 | 33 |

**The pytest extrapolation, stated once.** `pytest tests/ -q --collect-only` reports
**11,282 tests collected**. A measured 556-test run emitted 8 progress lines / 640 bytes for
558 marks = **1.147 bytes per test mark** (progress lines are 72 marks + ` [ NN%]` = 79 bytes
+ newline). 11,282 × 1.147 = **12,940 bytes** of progress lines in a full green run ≈ 3,235
tokens. A 34-test run measured 100 bytes total, consistent. This is the only number quoted
for pytest anywhere in this plan.

**Strippable bytes — the number that decides scope:**

| Command | total bytes/12d | *strippable* | share of strippable |
|---|---:|---:|---:|
| pytest full suite (unpiped) | 440,000 | **440,000** | **97.0%** |
| `git status` | 76,325 | 12,780 (boilerplate hints only, 180 B/call) | 2.8% |
| `gen-plan-index.py --check` | 25,890 | ~950 | 0.2% |
| `ck doctor --strict` | 7,730 | ~0 | 0% |

**Two of the three hypotheses in the brief did not survive measurement:**

- *"`gen-plan-index.py` prints 11 identical `WARNING: … is DRIFTED` lines … pure repeated
  noise."* They are **not** identical: each names a different plan file. Collapsing them to a
  count destroys the only information they carry. Rejected — and the whole command is 863
  bytes, 0.2% of the strippable total.
- *"`git status` lists ~28 untracked files of accumulated cruft."* Measured 19 untracked
  files, 1,075 bytes. The filenames are the payload; only the two parenthetical
  `(use "git add <file>…")` hints are removable — 180 bytes per call, 2.8% of the total.
  Not worth a filter's risk surface.

**Therefore: one filter.** `python3 -m pytest … -q` progress lines, which are 97% of the
measurable waste and carry, provably, zero information when every mark is a pass or a skip.

### The finding that matters more than the tokens

Of the 59 full-suite `pytest tests/ -q` invocations in the corpus, **25 (42%) were already
piped to `tail`/`head`, and 0 of those used `pipefail`**:

```
$ grep -cE 'pytest tests/? -q' cmds.txt                      # 59
$ grep -E 'pytest tests/? -q' cmds.txt | grep -cE '\| *(tail|head)'   # 25
$ grep pytest cmds.txt | grep -c pipefail                    # 0
```

In bash, `pytest … | tail -3` exits with **tail's** status. Those are 25 recorded occasions
on which the DoD gate "full suite — zero failures tolerated" was evaluated against an exit
code that could not express failure. That is precisely the pattern memory
`a-passing-check-can-measure-nothing` records. The output filter removes the *incentive* for
that pipe while preserving the exit code, because it rewrites text and never touches status.
**The correctness win is the primary justification; the ~110,000 tokens per 12 days is
secondary.**

### Alternatives considered and rejected

1. **Change the canonical command in CLAUDE.md to `… | tail -30`.** Zero code — and
   actively harmful: it institutionalises the exit-code-destroying pipe above.
2. **Lower `bashOutputMaxChars` to its 4,000 floor.** One settings line, no code. Rejected:
   the over-cap preview is **head**-biased (`"Preview (first N)"`), so for pytest it would
   keep the dots and discard the summary — the exact inversion of what is wanted — and it
   would apply to every command, not the one that needs it.
3. **Port rtk's 64 filters / three-level hierarchy / 6 operations.** Rejected as unmeasured.
   This plan ships 1 filter, 2 levels, 2 operations.

---

## Scope

- **In scope:** one `PostToolUse` hook script, one base filter file with one filter, its
  registration in `.claude/settings.json`, a behavioural test module, and documentation of
  the escape hatch. Repo-local to claudekit.
- **Out of scope:** the fleet rollout to the other ~13 repos (each has its own
  `settings.json`; a surgical insert via `fleet-sync.py` is a separate, owner-gated plan);
  a user-global `~/.config` hierarchy level; filters for `git status`, `gen-plan-index.py`,
  `ck doctor`; grouping/dedup/`on_empty`/`keep_lines_matching`/`head_lines`/`strip_ansi`
  operations; the `CHANGELOG.md` entry (protected file — see Prerequisites).

## Prerequisites

- `.claude/settings.local.json` present with `ECC_HOOK_PROFILE=minimal` (CLAUDE.md session
  setup gotcha), else ops execution is blocked.
- `CHANGELOG.md` is in `shared.protected_patterns()`, so it **cannot** be an ops operation
  (GUARD 13). The `[Unreleased]` entry is a manual owner step after execution. Verified:
  `is_protected_file('CHANGELOG.md') → True`, `is_protected_file('.claude/settings.json') →
  False`.

---

## Implementation Steps

### Step 1: The filter engine

- **File:** `.claude/operations/scripts/output_filter.py`
- **Action:** Create
- **Description:** stdlib-only PostToolUse hook. Reads the hook payload on stdin; if the
  Bash command matches a filter, prints
  `{"hookSpecificOutput":{"hookEventName":"PostToolUse","updatedToolOutput":{…}}}` and
  exits 0. Otherwise prints nothing and exits 0.
- **Why not `.claude/hooks/`:** `scripts/gen-docs.py:75` counts `*.sh` and `*.py` there;
  a file there moves the hook count and reddens the docs-drift gate (validated rejection
  brief, Phase 0). `heal_local_settings.py` is the precedent.
- **Why this directory reaches the fleet for free:** `install.sh:222-223` copies
  `.claude/operations/scripts/*.py` **and** `*.json`. No installer change is needed, and no
  new top-level `.claude/` directory has to be added to the `mkdir -p` list at
  `install.sh:204`.
- **Details — the four safety properties, each with its test:**
  1. **Never touches a failed command.** Structural: the host does not run PostToolUse for a
     non-zero Bash exit (verified above), and `PostToolUseFailure` has no rewrite field.
  2. **Never touches stderr.** The script rewrites `tool_response["stdout"]` only and echoes
     every other key unchanged. This also makes the rewrite schema-valid by construction.
  3. **Fail-soft, twice.** Every path is wrapped; any exception exits 0 printing nothing, so
     the original output stands. Independently, the host discards a shape-mismatched rewrite
     and logs "using original output".
  4. **`NEVER_FILTER` denylist**, applied *after* the local-override merge so a downstream
     `output-filters.local.json` cannot re-enable it: `gen-docs.py`, `gen-registry.py`,
     `gen-model-policy.py`, `gen-plan-index.py`, `check-context-floor.py`,
     `check-plan-artifacts.py`, `validate-config-json.py`, `execute-json-ops.py`,
     `review-record.py`, `ck doctor`, `claudekit doctor`, `shellcheck`, `mypy`, `ruff`.
     These are the machine-parsed / gate-bearing outputs.
- **Escape hatch, stated exactly:** prefix the command with `CK_RAW_OUTPUT=1`, e.g.
  `CK_RAW_OUTPUT=1 python3 -m pytest tests/ -q`. The script matches that token in
  `tool_input.command` and returns without rewriting. Every summary line it emits names the
  hatch, so it is discoverable from the filtered output itself. `CK_OUTPUT_FILTER=off` in
  the hook's environment disables the script wholesale.
- **Test-only seam:** `CK_OUTPUT_FILTERS_DIR` relocates the two filter files so tests can
  exercise the override hierarchy without writing into the repo.

### Step 2: The base filter set (one filter)

- **File:** `.claude/operations/scripts/output-filters.json`
- **Action:** Create
- **Description:** `{"schema_version": 1, "filters": [ … ]}`. One filter, `pytest-progress`.
- **Details:** it strips lines matching `^[.s]+ +\[ *\d{1,3}%\]$` — a progress line whose
  marks are **only** `.` (passed) and `s` (skipped). A line containing `F`, `E`, `x`, `X` or
  `u` does **not** match and survives untouched. That regex is the entire safety argument for
  this filter: a removed line provably carried no failure. The summary line replaces them:
  `[ck output-filter: pytest-progress] {removed} all-passing progress line(s) removed
  ({marks} pass/skip markers). Prefix the command with CK_RAW_OUTPUT=1 for raw output.`

### Step 3: Register the hook

- **File:** `.claude/settings.json`
- **Action:** Modify
- **Description:** append a fifth `PostToolUse` entry with `"matcher": "Bash"`, invoking
  `python3 "$ROOT/.claude/operations/scripts/output_filter.py"` through the same
  `bash -c 'ROOT=…'` preamble the other four use.
- **Details:** it must be the **only** PostToolUse hook that ever returns
  `updatedToolOutput`. The host runs PostToolUse hooks in parallel against the original
  output and resolves rewrites last-write-wins; the other four (`reflection-gate.py`,
  `post-tool-use.sh`, `command-log-audit.sh`, `suggest-compact.sh`) return none today, and
  none of them may start returning an identity rewrite.

### Step 4: Behavioural tests

- **File:** `tests/test_output_filter.py`
- **Action:** Create
- **Description:** subprocess-driven; every test feeds a real hook payload on stdin and
  asserts on the process's stdout. See Testing Strategy for the red-proof of each.

### Step 5: Document it for users

- **File:** `docs/HOOKS.md`
- **Action:** Modify
- **Description:** add a section documenting the filter, the `CK_RAW_OUTPUT=1` escape hatch,
  the `output-filters.local.json` override file, and the four safety properties. Adds no
  row to a generator-owned count table.

### Step 6: Document it for maintainers

- **File:** `.ai/HOOKS.md`
- **Action:** Modify
- **Description:** record under "PostToolUse / telemetry (never block)" that one PostToolUse
  hook now *rewrites* rather than only observing, and that the single-rewriter invariant is
  load-bearing.

---

## Testing Strategy

Every test below is paired with the mutation that makes it go **red against unmodified
code** — per `a-passing-check-can-measure-nothing`, the implementer must run each mutation,
record the failure, and revert before claiming the test passes.

| # | Test | Mutation that turns it red |
|---|---|---|
| 1 | `test_pytest_progress_lines_are_removed` | Delete the `strip_lines_matching` op from `output-filters.json` → no rewrite is emitted. |
| 2 | `test_a_progress_line_with_a_failure_marker_survives` | Widen the base regex from `^[.s]+` to `^[.sFEx]+` → the `..F..... [ 12%]` line is stripped and the assertion fails. **This is the primary safety proof.** |
| 3 | `test_stderr_is_echoed_byte_for_byte` | Make the script also run the filter over `stderr` → the assertion on the exact stderr string fails. |
| 4 | `test_every_other_response_field_is_preserved` | Emit `{"stdout": …}` instead of the full response object → `interrupted` / `returnCodeInterpretation` vanish. |
| 5 | `test_raw_output_escape_hatch_disables_the_filter` | Remove the `CK_RAW_OUTPUT=1` check → a rewrite is emitted and stdout is non-empty. |
| 6 | `test_a_corrupt_filter_file_passes_output_through` | Remove the `except Exception` → the script tracebacks and exits non-zero. |
| 7 | `test_never_filter_survives_a_local_override` | Apply `NEVER_FILTER` *before* merging the local file instead of after → a local filter for `validate-config-json.py` takes effect. |
| 8 | `test_unknown_schema_version_is_ignored` | Drop the `schema_version` check → a v2 file is applied. |
| 9 | `test_non_bash_tool_is_ignored` | Drop the `tool_name` guard. |
| 10 | `test_no_match_emits_nothing` | Make the default branch emit an identity rewrite → violates the host's explicit "do NOT return an identity rewrite" warning and the test fails. |
| 11 | `test_fast_path_latency_under_250ms` | The hook runs on every Bash call; a regression here taxes every tool use. Measured budget, not a guess. |
| 12 | `test_output_filter_hook_is_registered` | Remove the `settings.json` entry. |

**End-to-end verification (manual, once, by the implementer):** run
`python3 -m pytest tests/ -q` in a live session and confirm the received output is the
summary plus the `[ck output-filter: …]` line; then run
`CK_RAW_OUTPUT=1 python3 -m pytest tests/test_output_filter.py -q` and confirm the raw dots
come back. A green unit suite alone does **not** prove the host honours the rewrite.

**Gates to run after execution:** `python3 -m pytest tests/ -q`, `ruff check src/ tests/
scripts/ .claude/operations/scripts/`, `mypy`, `python3 scripts/gen-docs.py --check`
(must stay green — this is the count the rejection brief warns about),
`python3 scripts/gen-registry.py --check`, `python3 scripts/check-context-floor.py --check`,
`python3 scripts/check-plan-artifacts.py --check`, `ck doctor --strict`.

---

## Evidence recorded at planning time

The engine, the filter file and the test module in `plan-output-filters.ops.json` were built
and executed in a scratch tree before this plan was written, so none of the claims above is a
forecast.

- **Suite:** 33 tests, `33 passed in 1.27s` against a fake repo laid out exactly as the ops
  config writes it (`.claude/operations/scripts/`, `tests/`, patched `.claude/settings.json`).
- **Mutation battery — every mutant was caught, by the intended test:**

  | Mutant applied to the scratch tree | Result |
  |---|---|
  | widen `^[.s]+` to `^[.sFEx]+` in `output-filters.json` | `FAILED … test_a_progress_line_with_a_failure_marker_survives` (1 failed, 32 passed) |
  | delete the `CK_RAW_OUTPUT=1` check | `FAILED … test_raw_output_prefix_disables_the_filter` (1 failed, 32 passed) |
  | emit `{"stdout": …}` instead of the whole response | `FAILED … test_stderr_is_echoed_byte_for_byte`, `… test_every_other_response_field_is_preserved` (2 failed, 31 passed) |
  | remove the `NEVER_FILTER` denylist | 9 failed, 24 passed (incl. `test_gate_bearing_commands_are_never_filtered[ruff check src/]`, `[mypy]`) |

- **Lint/types:** `ruff check --line-length 100 --select E,F,W,I --target-version py39` →
  `All checks passed!`; `mypy --python-version 3.9 --check-untyped-defs` →
  `Success: no issues found in 1 source file`.
- **Ops config:** `python3 .claude/operations/scripts/validate-config-json.py
  .claude/plans/plan-output-filters.ops.json` → `-> APPROVED` (exit 0), with one benign
  warning about the duplicate filename `HOOKS.md` across `docs/` and `.ai/`.
- **Artifact gate, shown capable of failing on *this* plan:** renaming `.ai/HOOKS.md` in the
  plan body produced `PLAN/CONFIG DRIFT — .claude/plans/plan-output-filters.md: does not name
  .ai/HOOKS.md`; restored, `check-plan-artifacts: OK (514 config(s), 747 path(s) verified)`.
- **Post-state parse check:** the `.claude/settings.json` edit was applied in memory and
  re-parsed with `json.loads` before being written into the ops config — the validator does
  not compile a post-state (memory `ops-add-after-is-literal-concat`), so this was done here.

## Rollback Plan

1. Remove the fifth `PostToolUse` entry from `.claude/settings.json` — that alone fully
   disables the feature; the two scripts become inert files.
2. `git rm .claude/operations/scripts/output_filter.py
   .claude/operations/scripts/output-filters.json tests/test_output_filter.py`.
3. Revert the `docs/HOOKS.md` and `.ai/HOOKS.md` sections.
4. No migration, no state, no generated artifact to unwind. An in-session kill switch exists
   without any rollback at all: `CK_OUTPUT_FILTER=off` in `.claude/settings.local.json`.

## Risk Assessment

**Low**

- *Hiding an error.* Structurally prevented three ways: the host never runs PostToolUse on a
  non-zero exit; the script never touches `stderr`; the shipped regex only matches lines
  whose every mark is a pass or a skip. Tests 2 and 3 pin the last two.
- *Breaking a machine-parsed output.* The engine is opt-in per command pattern and ships one
  filter. `NEVER_FILTER` is a post-merge backstop (test 7). Exit codes are never touched.
- *Filter bug corrupting output.* Fail-soft in the script, plus host-side schema validation
  that falls back to the original output.

**Medium**

- *Per-call latency.* The hook forks a Python interpreter on **every** Bash tool call —
  363/day in this corpus. Budgeted and pinned by test 11 at <250 ms; the no-match path reads
  stdin, matches a handful of compiled regexes, and exits.
- *`.claude/settings.json` blast radius.* It is not on the protected list, and this plan adds
  one array element without touching any existing entry. But it is the file the whole hook
  system hangs off; a malformed edit disables every hook. `find` is anchored on the
  `suggest-compact.sh` block, verified unique by `grep -cF` → 1.
- *Parallel-rewrite invariant.* The host warns that rewrites are last-write-wins across
  hooks. Today exactly one hook rewrites. This is an invariant maintained by prose in
  `.ai/HOOKS.md`, not by a gate — stated honestly rather than overclaimed.

**High**

- *Fleet rollout.* Deliberately **out of scope**. `install.sh:222-223` copies the two new
  files to every kitted project automatically, but they are inert until that project's own
  `settings.json` registers the hook. `output-filters.local.json` is never shipped, so it is
  absent from `.claudekit-manifest.json`, which is exactly what makes `preserve_assets.py`
  classify it as custom and preserve it across upgrades (`preserve_assets.py:186`
  `_is_custom`) — satisfying `fleet-sync-preserve-local` with no new machinery. The
  registration step across ~13 repos needs its own owner-gated plan and its own measurement;
  the filter set is stack-specific and a Node or Go repo gets nothing from a pytest filter.

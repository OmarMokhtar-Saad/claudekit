# Implementation Plan: Enforcement runtime — typed event log, one dispatcher per event, spill

**Lane:** Agent A, Phase 0 (0.1 event log, 0.2 dispatcher + most-restrictive merge, 0.3 spill +
model-free pruning, 0.4 advisory tier). **Tier:** 3 (security-relevant: hook decision logic).
**Branch:** `perf/token-efficiency`. Plan only — **nothing has been executed against the
repository.** Revision 4's measurements were taken in throwaway `git worktree` trees at `5f3e322`,
outside the session scratchpad; the repo itself is untouched.

**Two configs, one owner decision:**

| Config | Ops | State | Applies |
|---|---|---|---|
| `.claude/plans/plan-enforcement-runtime.ops.json` | **18** | validates against HEAD | the runtime, its tests, its docs — **zero hook behaviour change** |
| `.claude/plans/pending/plan-enforcement-runtime-wiring.ops.json` | **7** | validates against HEAD **+ core applied** | routes `PreToolUse` through the dispatcher and **appends** the "wiring landed" changelog entry |

**Round-5 verdict: APPROVED — 92.9/100** (Plan Quality 92 / Architecture 94 / Security 93), **zero
blocking findings**. The re-review the owner required has happened.

The second config is **APPROVED WITH TWO CONDITIONS** (it was SUSPENDED through round 4). The
round-5 reviewer recommends it as **safe to run**, subject to exactly these two and nothing else:

1. **Land the core config first, and archive its spent config per runbook step 5, BEFORE the
   addendum runs.** The addendum's anchors are text the core creates, and a spent core config left
   in `.claude/plans/` fails `test_queued_ops_configs_validate_against_head` by name.
2. **[L3-R5] Addendum op 2 must be an append, not a `replace`, on `CHANGELOG.md`** — done in this
   revision (see [L3-R5] below). Both configs now carry **zero `replace` on a contended file**.

The first config is still written to be true whether or not the second ever runs.

**Revision 6 (four mechanical corrections on an APPROVED plan).** Review history: 79.4 (rejected)
-> 76 (rejected) -> 81 (rejected) -> **75 (rejected: Plan Quality 33/40, Architecture 25/30,
Security 17/30)** -> revision 5 -> **round 5: APPROVED 92.9/100 (PQ 92 / Arch 94 / Sec 93), zero
blocking findings**. Revision 6 changes **nothing** that round 5 settled: it converts addendum op 2
to an append (**[L3-R5]**, a condition of running the addendum), corrects the wrong vacuity
rationale to what the reviewer actually measured (**[L1-R5]**, prose only), adds the missing spill
**directory**-mode assertion to the `test_spill.py` payload (**[L2-R5]**), and refreshes two stale
test counts to the round-5 figures (**[L4-R5]**: 71 -> **86**, 104 -> **121**). No Critical or High
from rounds 1-5 is reopened. Revision 6 executed no test either — its Bash was scoped to
`validate-config-json.py` — so every figure it adds is labelled as the **round-5 reviewer's**
measurement, never as its own. Round 4 executed
**21 escape probes** and an **AST-level audit of every `in`/`not in` literal assertion** across all
three test files, and narrowed the objection to **one Critical plus three lesser findings**. It
also confirmed, by execution, everything revision 4 claimed about C1-R3 (the reconciled asymmetry
test fails under mutation; the non-nesting markers hold; no other vacuous assertion exists; exit 3
never escapes; the heredoc is 58 lines and `check-silent-failure.py` is untouched; the runbook, the
anchor counts and the +1 hook delta are right) — **none of that is re-litigated here.**

**[C1-R4] CRITICAL — `tier: ""` evaded the registry invariant.** The invariant read a row's tier as
`(_r.get("tier") or "advisory")`, which maps `""`, `None` and an absent key **all** onto
`"advisory"` and therefore **accepts** them — while `ck_clamp_advisory` deliberately disarms only
the literal string `"advisory"`, and says so in its own comment. So a row with `"tier": ""` **and**
a `command_matcher` was (a) accepted by the invariant, (b) not clamped and therefore
blocking-capable, and (c) skipped when the payload could not be parsed: malformed input silently
removed a live guard. Aggravating, and the reason it is Critical rather than Medium: the plan's own
static companion test used the **correct** strict form (`row.get("tier") == "advisory"`), so one
invariant shipped with two normalizations — and `install.sh` copies `.claude/hooks/` into user
projects, where **the resolver is the only enforcement** because the pytest companion does not ship
as a gate. Fixed, reconciled and pinned per tier value in [C1-R4] below.

**Round 4's three lesser findings, all taken:** **[M2]** the one non-`{0,2}` exit at the hook
boundary (`exit 1` on a missing event name) is now `exit 2`, with a known-event list and an escape
probe; **[L1]** spill files were created with the default umask while the event log correctly used
`0o600` — now `0600` unconditionally, asserted on both; **[M1]** the headline counter-mutation
figure did not reproduce on the shipped 26-row registry, so the prose is corrected to say what was
actually measured. Details in their own sections below.

**Revision 4 (history).** Review history at that point: 79.4 (rejected) -> 76 (rejected) -> **81 (rejected)** -> that revision.
Rounds 2 and 3 executed everything; all eight round-1 findings and all six round-2 mutation proofs
are closed and binding against the shipped artifact, and none of that is touched here. Round 3
raised **one Critical**, and the owner authorised this fourth round past the normal 3-round ceiling
**for that finding only**:

**[C1-R3]** revision 3 closed C1 by inverting a rule that the plan's own shipped test declared a
bypass — and left that test in the tree, **failing** (`assert 0 == 2` at
`tests/test_dispatch_merge.py:553`). Three defects in one artifact: the suite was red on this
lane's own file; the test was the plan's own written refutation of its own fix; and the invariant
the fix depends on — *a handler with a precondition cannot block* — was **enforced nowhere**. The
reviewer proved that last point by adding `command_matcher` to the shipped **blocking**
`commit-quality` row and getting a fully green suite and eight green gates. Closed here in both
halves: the test is **reconciled** (it now asserts the asymmetry the code implements, and carries
its own history), and the invariant is **enforced in the resolver and proven by mutating the
shipped registry**. Round 3's three non-blocking findings (H1-R3 archive step, M1-R3 scope wording,
L1-R3 changelog REPLACE) are folded in as disclosure improvements, not redesigns.

**Every number below is labelled, and neither revision 5 nor revision 6 could execute.** The revision-5 author is a
planning role with Bash scoped to `validate-config-json.py`; it ran no test, no gate and no
dispatcher. Every figure therefore carries one of five labels, and there are no unlabelled numbers:

| Label | Means |
|---|---|
| **re-measured by round-4 review** | The reviewer executed it, on a materialized core tree at `5f3e322`. Their measurement, not this plan's. |
| **re-measured (rev 4)** | Executed by the revision-4 author in a throwaway `git worktree` at `5f3e322`. |
| **re-measured at `5f3e322`** | HEAD, no config applied. |
| **prior-round evidence, not re-run** | Stated because it was measured once; not confirmed against the current artifact. |
| **not yet executed** | Nobody has run it. Revision 5's own changes are all in this class, except the four static checks named below. |

**What revision 5 did verify itself** (static, in a throwaway `git archive HEAD` copy under
`/tmp`, using its own applier — **not** the operations engine, which it is barred from running):
the core config validates `APPROVED` against HEAD; all **11** core `code_edit` anchors match
exactly once; all **8** addendum anchors match exactly once against HEAD+core (and the addendum is
still `REJECTED` against HEAD alone, by design); every `file_create` payload parses
(`py_compile` / `json.load` / `bash -n` all clean); `ruff check --line-length 100` is clean on the
three Python payloads; and the resolver heredoc is still **58 lines**, so
`check-silent-failure.py`'s `MAX_JOIN_LINES = 80` cap is untouched. Everything else in this
revision — the new tests, the boundary change, the `0600` spill mode — is **not yet executed**.

---

## Overview

Build the enforcement runtime that `caa96f7` documented but never implemented: a durable typed
JSONL event log, a single dispatcher per hook event with an explicit **most-restrictive-wins**
merge rule and a shared exit-code codec that **fails closed**, a spill + model-free pruning layer,
and a named **advisory** tier that can neither override a block nor create one.

## Verified ground truth (commands and real output)

```
$ git show --stat --format="" caa96f7
 .ai/REVIEW_GUIDE.md | 33 +++++++++++++++++++++
 CHANGELOG.md        | 85 +++++++++++++++++++++++++++++++++++++++++++++++++++++
```
`caa96f7` is **docs-only**. No dispatcher, event log, spill or merge rule exists anywhere in
`src/`, `.claude/hooks/`, `.claude/operations/` or `tests/`.

**Hook counts (correcting the brief).** `gen-docs.py --check` reports `hooks=21`.
Blocking-capable is **7**, not 6 (`iron-law-gate.py` and `reflection-gate.py` block too).
`file-guard-gate.sh`, `injection-scan-gate.sh` and `security-reminder.sh` contain neither `exit 2`
nor a `deny` call, so despite their `-gate` names they cannot block. That finding is now **filed
in `.ai/BACKLOG.md` (op 13)**, not left inside a plan document.

**The ordering gap is real.** Re-measured at `5f3e322` — `.claude/settings.json` registers
**26 hook entries across 8 events**, not the 24 the previous revision claimed (11 PreToolUse, 4
PostToolUse, 2 UserPromptSubmit, 2 SessionStart, 1 PreCompact, 4 Stop, 1 SubagentStop, 1
PostToolUseFailure). `PreToolUse` alone carries 11, six on the `Bash` matcher. Nothing defines the
outcome when two decide differently. The shipped `dispatch-registry.json` in op 5 already carries
**26** rows, so the fidelity was right and only the prose was wrong; a test asserts registry ==
settings, so the two cannot drift.

**The fail-open defect is real — and the previously cited number was wrong (H2).** Re-measured at
`5f3e322`:
```
$ echo 'not json' | ECC_HOOK_PROFILE=standard /bin/bash .claude/hooks/ops-enforcement.sh; echo $?
BLOCKED: could not parse the tool payload; refusing an unverified edit.
2                                              <- fails closed on a bad payload, correct

$ echo '' | env -i PATH=/nonexistent /bin/bash .claude/hooks/ops-enforcement.sh; echo $?
.claude/hooks/ops-enforcement.sh: line 8: dirname: command not found
.claude/hooks/ops-enforcement.sh: line 15: resolve_root: command not found
.claude/hooks/ops-enforcement.sh: line 16: cat: command not found
.claude/hooks/ops-enforcement.sh: line 19: extract_json_field: command not found
.claude/hooks/ops-enforcement.sh: line 20: deny: command not found
.claude/hooks/ops-enforcement.sh: line 21: extract_json_field: command not found
0                                              <- FAIL OPEN. 0 is ALLOW.
```
The previous revision printed `PATH=/nonexistent bash ... -> 127` and called it the measured
defect. That 127 was **zsh failing to find `bash`** (`(eval):1: command not found: bash`) — the
hook never executed. Run through `env -i` with an absolute interpreter, the hook *does* run and
exits **0**: every helper is command-not-found, `deny` included, so it emits nothing and ends
successfully. **0, not a crash code, is what makes it fail open**, and that is a stronger and more
alarming fact than the one claimed. Two consequences, both now written into the artifacts:
- The dispatcher still fixes this class, because under it the *handler process itself* cannot
  start — `bash`/`python3` unresolvable -> 127 -> `ERROR` -> exit 2. That is an **observed** code.
- No exit-code codec can fix a hook that degrades to 0 on its own. Filed in `.ai/BACKLOG.md`
  (op 13) rather than glossed; the fix belongs in the hooks (`set -e` + an `EXIT` trap + a
  positive "I ran" assertion), not in the merge rule.

No hook sets a `trap`; four set `set -e`. `.claude/hooks/hooks.log` is a **live, growing**
figure, not a fixed property: 2,615,783 bytes when revision 3 measured it and ~2,651,919 bytes
when round 3 re-read it a day later, because every session appends to it. Treat any byte count
for this file as a timestamped sample (~2.5-2.7 MB at the time of writing), not a constant.
The growth itself is not a defect and is not fixed here (open decision 4).

---

## Scope

**In scope (core config)**
- `src/claudekit/enforcement/` — `decisions.py` (codec + merge + advisory clamp), `eventlog.py`
  (typed JSONL, replay, runtime assertion), `spill.py` (spill + locator + model-free pruner).
- `.claude/hooks/dispatch.sh` — one dispatcher per event, with its own panic trap.
- `.claude/hooks/dispatch-registry.json` — event → ordered handler list with tier, tool matcher,
  **command matcher** and **argv**.
- `.claude/hooks/lib.sh` — the shell half of the codec plus the event-log emitter shim (append
  only; no existing line touched).
- Three behavioural test files carrying the five required mutation proofs, plus proofs 6 and 7
  (the boundary renderer; the precondition rule and the malformed-payload hang).
- The `gen-docs.py` count regeneration (21 → 22) and the prose rewording it forces.

**Out of scope**
- Rewiring `.claude/settings.json` — the separate addendum config, owner-gated.
- Stop-hook DoD gate, failure-fingerprint breaker (next phase, per the brief's scope guards).
- Migrating `hooks.log` to JSONL. It keeps its prose shape; a test pins that.
- **Agent B's lane, and the newly-assigned files: `scripts/check-context-floor.py`,
  `tests/test_context_floor.py`, `.github/workflows/ci.yml`.** Not touched. No ci.yml change is
  required by either config.
- No model client, agent loop, session runtime, sandbox or plugin system.

## Prerequisites

None for the core config. The addendum requires the core config to have been applied.

---

## Implementation Steps — 1:1 with the 18 core ops

| Op | File | Action | What and why |
|---|---|---|---|
| 1 | `src/claudekit/enforcement/__init__.py` | Create | Package docstring + re-exports. The `spill` *function* is deliberately not re-exported — it shadows the `spill` *module* (found by execution; it broke 13 tests). |
| 2 | `src/claudekit/enforcement/decisions.py` | Create | `ALLOW(0) < ADVISE(1) < ERROR(2) < DENY(3)`. `from_exit_code`: `0→ALLOW`, `2→DENY`, **everything else→ERROR**, no permissive branch. `to_exit_code`: ERROR and DENY both render 2. `merge` = `max` (commutative, so no order can change the outcome). `clamp_advisory` caps an `advisory` handler at ADVISE, before merge. |
| 3 | `src/claudekit/enforcement/eventlog.py` | Create | `SCHEMA_VERSION = 1`, two kinds (`hook_decision`, `ops_execution`) with required-field tuples; unknown kind rejected. `append` is one `O_APPEND` line write. `replay` is a pure projection (no clock) — the golden-record primitive task 010 needs. `assert_model_visible_logged` is the invariant as code. |
| 4 | `src/claudekit/enforcement/spill.py` | Create | Under threshold: text returned unchanged, no file. Over: persisted by SHA-256, codepoint-safe preview + bytes-withheld + `ck-spill://<session>/<digest>` locator. `retrieve()` re-checks realpath containment and re-verifies the digest. `prune()` is deterministic and model-free. Measurement (`size_of`) is separate from policy (thresholds are arguments, never env-read module state). **L1-R4:** the spill file is created **`0600` regardless of umask** via `tempfile.mkstemp` + `os.replace` (mkstemp gives `O_EXCL` + `0600` and a unique name, so a crash cannot leave a stale temp that permanently breaks later spills of the same digest); the session directory is created `0700`. Spilled text is the oversized tool output that could not stay inline — precisely where a secret lands — and `open()` took the process umask, so on a normal `022` box every spill file was `0644`. |
| 5 | `.claude/hooks/dispatch-registry.json` | Create | **C1-R3:** its `_doc` now states the enforced invariant (a `command_matcher` only on an `advisory` row) instead of leaving it as an unwritten assumption. All **26** registrations across 8 events (the content already had 26; only the prose said 24), each `{id, file, runner, tier, matcher, command_matcher?, args?}`. `args` exists because `reflection-gate.py` **requires** `--event`; `command_matcher` exists because settings.json runs `pre-commit`/`pre-push` only on `git commit`/`git push`. Without both, no faithful rewire is possible. |
| 6 | `.claude/hooks/dispatch.sh` | Create | **C1-R4 here (the ship-blocker):** the invariant reads the tier as `_r.get("tier", "advisory")`, not `(_r.get("tier") or "advisory")` — one word, and it closes `""` and `null` while keeping an *absent* key consistent with the default the resolver already **emits**. The one normalization rule is now written down in this file, in `lib.sh` beside the clamp, and in the static companion test. **M2-R4 here too:** a missing or unknown event name fails closed at **`exit 2`** (it was `exit 1`, which Claude Code reads as NON-blocking, so a misregistered dispatcher failed OPEN on `PreToolUse`); the eight known event names are pinned against the registry by a drift test. The change is two lines in and two lines out of the heredoc, so its body is still **58 lines**. **C1-R3 half two:** the resolver **rejects** any row with `tier != "advisory"` **and** a non-empty `command_matcher` (resolver `exit 3` -> the dispatcher's registry-resolution branch -> `exit 2` on a blocking event). All events are scanned, not just the dispatched one. The resolver's rationale comments now live in shell comments **above** the heredoc, because the repo's own silent-failure linter caps a heredoc skip at 80 lines and the inline form made its scan of this file INCOMPLETE (measured: 103-line body, two `test_silent_failure_lint.py` failures; now 58 lines, green). Also **C1 fix:** a handler declaring a `command_matcher` is NOT APPLICABLE on an unreadable payload (see below); and the `timeout` claim is deleted, not faked (H1). One dispatcher. Merge is **bash-3.2 arithmetic**, so the rule survives a failed Python import. Fails closed on unreadable registry, unresolvable handler list, missing handler file, **missing `lib.sh`**, and on any abort via an **EXIT/INT/TERM panic trap**. Renders through `ck_decision_exit`. Only `PreToolUse` may emit 2. |
| 7 | `.claude/hooks/lib.sh` | Modify (append) | `ck_decision_from_exit`, `ck_clamp_advisory`, `ck_decision_label`, `ck_decision_exit`, `ck_mktemp`, `ck_now_ms`, `ck_emit_hook_decision`. Appended after `ERE_NOT_QUOTE_CLASS`; no existing line touched, so every hook sourcing `lib.sh` is unaffected. It stays a helper, so `gen-docs.py` still excludes it from the count. |
| 8 | `tests/test_dispatch_merge.py` | Create | **C1-R4:** the invariant's mutation proof is now **parametrized over `["blocking", "", None]`** and asserts on the resolver's **own** `illegal registry row` message in `hooks.log` rather than on rc or on the dispatcher's generic line — because rc is masked by the sibling guards (M1) and the generic line is *also* what `"\t".join(None)` crashing produces, so asserting it would have been vacuous for the `null` case. Plus `test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms`, which asserts the reconciliation as an executable property over the whole tier vocabulary including *absent*. **M2-R4:** `test_the_boundary_emits_only_zero_or_two_for_a_missing_or_unknown_event` (5 argv shapes) and `test_the_known_event_list_matches_the_registry`. **C1-R3 half one:** the self-refuting test is rewritten as `test_command_matcher_asymmetry_on_an_unreadable_payload`, asserting the asymmetry the code implements and carrying the history of why its predecessor asserted the opposite; plus proof 8, the invariant's mutation proof. Proofs 1–3 + parity + registry-honesty + the dispatcher's own fail-closed paths, **plus proof 7 (C1): four new tests that drive the REAL `dispatch-registry.json`, not a synthetic one** — the gap that let the hang through. |
| 9 | `tests/test_event_log.py` | Create | Proof 4, plus **L1-R4** `test_the_event_log_file_is_readable_only_by_its_owner` — `append` was already correct (`os.open(..., 0o600)`) and asserted **nowhere**, so the correct mode was one refactor from silent loss. |
| 10 | `tests/test_spill.py` | Create | Proof 5, plus **L1-R4** `test_a_spill_file_is_readable_only_by_its_owner`. The umask is **forced to `0o022`** inside both mode tests: under a developer umask of `0o077` the old `open()` form also yields `0600`, so without forcing it the test would pass against the very defect it exists to catch. `tempfile` is added to the module's model-free import allowlist. **L2-R5:** the same umask-forced test also asserts the **session directory** is `0o700` (`stat.S_IMODE(os.stat(os.path.dirname(result["path"])).st_mode)`), the mode that was correct in `spill.py` but asserted nowhere; `stat` was already imported and the allowlist governs `spill.py`'s imports, not the test's. |
| 11 | `README.md` | Modify | The `gen-docs.py` count update (21→22) **plus** rewording line 264 so a hook that is PRESENT is not called WIRED. |
| 12 | `docs/HOOKS.md` | Modify | Same: "ships 22 … 21 of them are wired", plus a note that `dispatch.sh` ships unwired and what it does. |
| 13 | `.ai/BACKLOG.md` | Modify (append) | Files the "three `-gate`-named hooks cannot block" security finding, at the end of the P1 section. |
| 14 | `.gitignore` | Modify | Ignore `.claude/runtime/` — runtime state, never a source artifact. |
| 15 | `CHANGELOG.md` | Modify (append) | Two bullets: what landed, **and** that the fail-open hole is still open in the live path — corrected to `exits **0**` (H2), with the reason 0 is worse than a crash code, plus the absent timeout. |
| 16 | `.ai/SESSION_STATE.md` | Modify (prepend) | Session state, newest-first. |
| 17 | `.ai/CHANGELOG_AI.md` | Modify (prepend) | Session log, newest-first. Includes the round-2 findings and the re-measurement lesson. |
| 18 | `.claude/plans/archive/README.md` | Modify (append) | **M1 fix: the archive step the plan was missing.** Appends the archive row for the spent core config as the last table row. The **file move itself is a `git mv` in the same commit** — the ops schema has no `move` type and `git` is not on the `run_command` allowlist, so this op records the move and the operator performs it: `git mv .claude/plans/plan-enforcement-runtime.ops.json .claude/plans/archive/ops-enforcement-runtime.json`. Without it `test_queued_ops_configs_validate_against_head` fails the moment the config is applied, because a spent config self-invalidates (its `find` strings no longer exist) — which is exactly the +1 failure round 2 measured. |

### Contended-file anchor discipline (correcting the previous revision)

The previous plan claimed all contended-file ops anchor on the *last* line of their section. That
was false for two of them, and the correction is to state the rule accurately rather than to
force a shape the files do not have:

- **Append-at-end-of-section** (`COORDINATION.md` default): op 13 `.ai/BACKLOG.md` (end of P1),
  op 15 `CHANGELOG.md` (end of the `[Unreleased]` bullet list), op 14 `.gitignore`.
- **Prepend, by explicit exception:** op 16 `.ai/SESSION_STATE.md` and op 17
  `.ai/CHANGELOG_AI.md` are **reverse-chronological by construction** — CHANGELOG_AI's own header
  says "Reverse-chronological log … Append an entry per significant session", and appending a
  2026-08-21 entry below 2026-07 ones would corrupt the ordering the file is built on. So both
  insert at the top. Op 16 anchors on `## Previous session — 2026-08-19 …` (a dated heading,
  which Agent B has no reason to touch); op 17 anchors on the file's descriptive header line,
  which **is** the highest-collision anchor in the repo, and that is accepted with eyes open: if
  Agent B lands a CHANGELOG_AI entry first, this op's `find` still matches (the header is never
  removed) and the rebase rule applies — **keep both entries, never resolve by deletion**
  (`COORDINATION.md`). The cost of a collision here is a rebase hunk; the cost of appending at
  the bottom is a permanently mis-ordered log.

---

## Mutation proofs — each fails against a mutant, executed, not asserted

All drive the shipped artifact as a subprocess or an import. Each contract proof is paired with a
**mutant test** that copies the shipped file, applies one targeted mutation, and asserts the
outcome *changes*; every mutant carries `assert mutated != source` so a stale anchor fails loudly
instead of silently proving nothing.

| # | Contract | Positive | Mutant that must break it |
|---|---|---|---|
| 1 | Most restrictive wins | `test_most_restrictive_wins_regardless_of_order` runs ALLOW+DENY in **both** orders; both exit 2. | `test_reversed_precedence_mutant_stops_blocking` flips `-gt`→`-lt`; asserts **0**. |
| 2 | Errors fail closed | `test_crashing_handler_fails_closed` over exit `1,3,42,124,127` — all **pre-cooked by the handler**, so this proves the codec and *not* a timeout (H1); plus missing handler, unreadable registry. | `test_fail_open_mutant_lets_the_crash_through` makes the codec catch-all ALLOW; asserts **0**. |
| 3 | Advisory cannot override a block | `test_advisory_cannot_override_a_block` (+ its text still reaches stdout) and `test_advisory_cannot_create_a_block`. | `test_unclamped_advisory_mutant_creates_a_block` disables the clamp; asserts **2**. |
| 4 | Model-visible means logged | `test_deleting_any_logged_field_breaks_the_invariant` parametrised over **every** required field; paired with an intact-record test and with `test_dispatcher_actually_emits_a_conforming_record`, which drives the real `dispatch.sh`. | `test_required_fields_match_the_pinned_contract` duplicates the field tuple as a literal, so narrowing `KIND_FIELDS` to silence a failure fails here instead. |
| 5 | Spill preview + working locator | Preview bounded in **bytes**, states bytes withheld, `retrieve()` returns the original byte-for-byte; codepoint safety, path-escape and missing-file refusal. | `test_tampered_spill_file_is_refused` mutates the spill file and requires a digest failure. |
| **7 (C1, round 2)** | A guard never runs outside its precondition, and a malformed payload cannot stall a tool call | `test_the_shipped_registry_terminates_and_blocks_on_a_malformed_payload` drives the **real** `.claude/hooks/dispatch-registry.json` with `not json` under a 90 s subprocess timeout, requires rc **2**, requires elapsed < 60 s, and requires `pre-push`/`pre-commit` not to appear in the output. `test_a_command_matcher_handler_is_not_applicable_on_an_unreadable_payload` is the fast deterministic form: a 30-second stand-in for `pre-push.sh` registered *first*, so "did it run" is observed as a timeout rather than inferred. `test_a_readable_payload_still_honours_the_command_matcher_both_ways` proves the rule did not become "always skip". | `test_reverting_the_not_applicable_rule_reintroduces_the_hang` restores `if readable and cmd_matcher and ...` and requires `subprocess.TimeoutExpired` — the round-2 hang, reproduced on demand. |
| **8 (new, C1-R3)** | An invariant the code depends on is enforced, not assumed: a `command_matcher` may appear only on an `advisory` row | `test_a_blocking_row_carrying_a_command_matcher_is_rejected_by_the_resolver` copies the whole **shipped** `.claude/hooks` tree, adds `command_matcher` to the shipped **blocking** `commit-quality` row (asserting first that `commit-quality.sh` really contains `exit 2`, so the mutant is blocking-*capable*), and requires rc **2** with the resolver's rejection — then **reverts** and requires the control outcome back. `test_an_advisory_row_may_still_carry_a_command_matcher` stops the check degenerating into "reject every precondition". `test_the_shipped_registry_keeps_preconditions_on_advisory_rows_only` is the cheap static drift detector, offered as a companion and **not** as the gate. | Removing the invariant block from `dispatch.sh` makes the first test fail — **re-measured (rev 4)**; note the *measured rc* correction under M1-R4 below. Revision 5 widens the same test to `tier=""` and `tier=null` and moves the assertion onto the resolver's own log line, so the mutant cannot be satisfied by a sibling guard's block or by a resolver crash. **Not yet executed.** |
| **9 (new, C1-R4)** | The invariant ACCEPTS exactly the tiers the clamp DISARMS | `test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms`, parametrized over `advisory / blocking / on / "" / bogus / null / absent`, drives the shipped dispatcher twice per tier — once for "is a row with a `command_matcher` accepted" (the resolver's own log line), once for "does this tier disarm a DENY" (rc 0) — and requires the two to be **equal**. | Reverting the resolver to `(_r.get("tier") or "advisory")` fails it at ids `empty-string` and `null`. The parametrized `test_a_blocking_row_carrying_a_command_matcher_is_rejected_by_the_resolver["", None]` fails against the same revert. **Not yet executed.** |
| **10 (new, M2-R4)** | The hook boundary emits only 0 or 2 | `test_the_boundary_emits_only_zero_or_two_for_a_missing_or_unknown_event` over `[] / [""] / ["Bogus"] / ["pretooluse"] / ["PreToolUse extra"]`: rc must be in `{0,2}`, must be **2**, `BLOCKED` on stderr, and no handler may have run. | Restoring `exit 1` on the missing-event path fails it at `no-arg`. `test_the_known_event_list_matches_the_registry` fails if an event is registered but unknown to `dispatch.sh` (which would block it) or known but unregistered (dead wiring). **Not yet executed.** |
| **11 (new, L1-R4)** | Spilled output is not world-readable | `test_a_spill_file_is_readable_only_by_its_owner` and `test_the_event_log_file_is_readable_only_by_its_owner` assert `stat.S_IMODE == 0o600` **with the umask forced to `0o022`**. | Reverting `spill()` to `open(tmp, "w")` fails the first under the forced umask — and would NOT fail it without the forcing, which is why the forcing is part of the proof. **L2-R5:** the same test now also asserts the session directory is `0o700`, so **dropping `mode=0o700` from `os.makedirs` must fail a test** — the round-5 reviewer's mutant dropped both modes and only the file assertion flipped. **Not yet executed.** |
| **6** | The boundary renderer is really called | `test_shell_and_python_boundary_renderers_agree` over all four decisions. | `test_boundary_renderer_is_actually_called` makes `ck_decision_exit` always print `0`; asserts the block **vanishes**. If `dispatch.sh` re-inlines `[ "$MERGED" -ge 2 ]`, this fails. |

**Fixes from this revision, each bound by a test that fails without it:**

- **M2 — the dispatcher's own trap.** `test_panic_trap_blocks_on_an_abort` injects an unset
  variable under `set -u` after the trap is installed and requires **2**, plus
  `test_panic_trap_does_not_block_a_non_blocking_event` (same abort on `Stop` → 0), plus
  `test_dispatcher_with_a_broken_path_fails_closed` (`PATH=/nonexistent`).
- **N2 — `lib.sh` is required.** `test_missing_lib_fails_closed`: delete `lib.sh`, blocking event
  must still exit 2 and name the file.
- **M3 — the tier vocabulary that actually ships.** Parity is now over
  `["blocking","advisory","on","","bogus"]` with **no identity mapping**, plus an end-to-end
  `test_only_the_word_advisory_disarms_a_handler`.
- **M1 — `test_blocking_tier_is_honest` is no longer near-vacuous** (evidence below).
- **New registry fidelity:** `test_registry_passes_reflection_gate_its_required_event_arg`,
  `test_registry_matches_the_command_conditions_settings_json_applies`,
  `test_handler_receives_its_registry_args`,
  `test_command_matcher_asymmetry_on_an_unreadable_payload` (renamed and reconciled, C1-R3),
  `test_a_blocking_row_carrying_a_command_matcher_is_rejected_by_the_resolver`,
  `test_an_advisory_row_may_still_carry_a_command_matcher`,
  `test_the_shipped_registry_keeps_preconditions_on_advisory_rows_only`,
  `test_registry_handlers_all_exist`.

---

## Evidence — and what the previous revision's evidence was actually worth (M1)

**The measurement method was wrong, so the headline conclusion was wrong.** Revision 2 baselined in
a `git archive HEAD` tree, which has **no `.git`**, so 34 `git`-dependent tests failed in *both*
trees and "identical set (34 == 34)" read as clean. Round 2 re-ran it in a `git worktree`, where
baseline is **one** failure — and the core config adds exactly **one**:
```
FAILED tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head
  plan-enforcement-runtime.ops.json: -> REJECTED
```
So the true delta was **+1, not 0**. The cause is benign and mechanical: **a spent config
self-invalidates** — once its edits are applied, its `find` strings no longer exist, and the repo's
own gate requires every `.json` directly in `.claude/plans/` to validate against the current tree.
The cure is the archive step the 17-op table did not have (`grep -i archive` over the previous
revision found two incidental hits and no step). **Op 18 adds it**, and the plan-step table stays
1:1 with the ops.

**Baselining rules, now explicit, so this cannot recur:**
- Re-baseline with **`git worktree`, never `git archive`** — a tree with no `.git` hides `git`-
  dependent failures in the noise and makes a real +1 look identical.
- Place the worktree **outside** the session scratchpad. A full-suite run in a worktree rooted at a
  scratchpad path **deletes its own CWD mid-run** (a test `rmtree`s scratchpad paths); the symptom
  is a cascade of `getcwd`/`FileNotFoundError` that looks like a test-ordering bug. Filed in
  `.ai/BACKLOG.md` (op 13).
- Compare failure **sets**, not counts, and state the baseline command used.

**Re-measured in revision 4, and the delta is now 0.** The core config was materialised into a
`git worktree` at `5f3e322`, **outside the session scratchpad** (both rules this plan wrote after
round 2), and run there:

```
baseline  (5f3e322, nothing applied):   1 failed, 1766 passed, 1 xfailed in 317.45s
HEAD + core config applied:             1 failed, 1871 passed, 1 xfailed in 447.32s
```

The failure **set** is identical — the single pre-existing memory-lane self-scan — so the core
config's delta is **+0 failures and +105 passing tests**. Revision 3's "+1" is superseded: it was
`test_queued_ops_configs_validate_against_head` catching a spent config self-invalidating, which
op 18 + the operator `git mv` cure. **Disclosed:** the plan configs are untracked, so a `git
worktree` tree does not contain them and *cannot* exercise that test. Its absence from this run is
a limit of the measurement, **not** evidence that op 18 is unnecessary — op 18 is still required,
and it is step 5 of the runbook below.

Eight gates with the core config applied — **re-measured (rev 4)**, in the same worktree:

```
ruff check src/ tests/ scripts/          All checks passed!
mypy                                    Success: no issues found in 24 source files
python3 scripts/gen-docs.py --check      Counts: agents=29 commands=42 skills=76 hooks=22
                                         OK: docs counts are current.
python3 scripts/gen-registry.py --check  OK: agentMapping + usedBy match agent files (18 agents).
python3 scripts/gen-model-policy.py --check   Model policy in sync: 29 agent roles.
python3 scripts/check-context-floor.py   OK: context floor within budget.
shellcheck install.sh .claude/hooks/*.sh (silent; rc=0)
python3 -m pytest tests/ -q              1 failed, 1871 passed  (== baseline set)
```

`hooks=22` is the C2 claim discharged by execution rather than by promise: ops 11-12 carry the
generator's own bytes and the drift gate reports `OK` with them applied.

**Status of every other figure in this document.** Marked, not assumed:
- **Re-measured by round-5 review** — the three new test files at revision 5:
  **`121 passed`** for `test_dispatch_merge.py` + `test_event_log.py` + `test_spill.py`, of which
  `test_dispatch_merge.py` is **`86 passed`**. These *supersede* the rev-4 figures (`104` and
  `71`), which were measured before revision 5 widened the parametrization; the rev-4 numbers are
  no longer stated anywhere as current.
- **Re-measured (rev 4)** — the worktree runs above; the C1-R3 counter-mutation (`rc=0` -> `rc=2`,
  and `1 failed, 70 passed` -> `71 passed`) against the **pre-revision-5** file — the mutant pair
  was **not re-run at revision 5**, so its *direction* carries forward but its counts do not; the
  silent-failure-linter heredoc finding (103 -> 58
  lines, two lint tests red -> green); the addendum validating **APPROVED** against HEAD+core with
  8/8 anchors at count 1, and **REJECTED — 5 patterns not found** against HEAD alone (by design);
  the core config validating **APPROVED** against HEAD with **11 anchors across 9 `code_edit` ops**
  (9 `file_create`, 9 `code_edit`, 18 total), each anchor at count 1.
- **Re-measured at `5f3e322`** (HEAD, no config applied): the fail-open exit code (**0**),
  `settings.json` = **26** registrations across 8 events, blocking-capable hooks = **7**.
- **Live figure, not a constant:** `hooks.log` size (~2.5-2.7 MB and growing every session).
- **Prior-round evidence, not re-run in revision 4:** the round-2 hang timing (>45 s pre-fix,
  2.12 s rc=2 post-fix), the M1/M2/M4/N2 counter-mutations, and the six round-2 mutation proofs
  verified as binding. They were verified against the shipped artifact in rounds 2-3 and this
  revision did not change the code they bind on.
- **Not yet executed:** the suite and gate sweep **with the addendum applied** (the addendum is
  suspended, see below), and op 18's archive row in a tree that actually contains the plan
  configs.

**One gate is red at HEAD, and it is another lane's file — now separately approved for repair.**
Disclosed so it is not misattributed. The suite is **green once the separately-approved memory-lane
fix lands**; until then the DoD sweep must expect exactly this one failure at baseline, and the
core config adds none:
```
FAILED tests/test_day_one_blockers.py::TestSelfScanIsClean::
       test_no_committed_file_matches_a_live_pattern[api_key...]  -> tests/test_memory.py
```
`tests/test_memory.py` (lines 240/257/438) was committed in HEAD `5f3e322` by the **memory lane**,
which owns it. **Pre-existing, another lane's file, not fixed here.** The owner has since approved
fixing it **outside this plan**, in the memory lane — so it is deliberately absent from these ops,
and this plan makes no claim that the suite is unfixable. Re-measured (rev 4): it is the *only*
failure at baseline (`1 failed, 1766 passed`) and the only failure with the core config applied
(`1 failed, 1871 passed`). The executing session must expect it and must not "fix" it inside this
commit.

**C2 — the gen-docs gate is closed by ops, not by a promise.** `gen-docs.py` is not on the
`run_command` allowlist (`pip-compile, black, isort, ruff, prettier, gofmt, goimports, rustfmt`)
and `CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW` is unset, so a `run_command` op **cannot validate**. Ops
11–12 instead carry the generator's own output, byte-for-byte. It was produced by running the
generator, not typed by hand (hard rule 8):
```
$ python3 scripts/gen-docs.py --check           # with dispatch.sh present, BEFORE op 11/12
ERROR: README generated inventory block is out of date.
ERROR: stale component counts in docs:
  README.md:264: says 21, should be 22 -> 21 hooks are wired through `.claude/settings.json` ...
  README.md:343: says 21, should be 22 -> │   ├── hooks/    # 21 workflow hooks + lib.sh
  docs/HOOKS.md:3: says 21, should be 22 -> ClaudeKit ships 21 hook scripts (plus `lib.sh` ...
rc=1
$ python3 scripts/gen-docs.py                   # its diff is what ops 11-12 encode
Updated README generated inventory block. Updated stale counts in README.md, docs/HOOKS.md.
```
The generator would have written *"22 hooks are wired through `.claude/settings.json`"*, which is
**false** — 22 exist, 21 are wired. So ops 11–12 keep the generator-owned number in the
noun-adjacent position the drift regex rewrites, and reword around it:
`"22 hooks ship in .claude/hooks/. 21 of them are registered in .claude/settings.json …"`. The
regex (`(\d+)\s+(?:[\w-]+\s+)?(hooks?)`) does not match `21 of them`, so the gate stays green —
verified above, after the ops: `OK: docs counts are current.`

**M1 was a real hole, not a style nit.** The old predicate accepted a shipped hook that cannot
reach `exit 2`:
```
$ python3 - <<'EOF'   # both predicates over every shipped hook
hook            old    new
reflection.py   True   False   <-- old predicate accepted a hook that cannot reach exit 2
EOF
```

**M2/M4/N2 counter-mutation** — reverting `dispatch.sh` to the reviewed draft's shape (trap
removed, `lib.sh` sourced conditionally, boundary comparison re-inlined):
```
FAILED test_boundary_renderer_is_actually_called
FAILED test_missing_lib_fails_closed
FAILED test_panic_trap_blocks_on_an_abort
FAILED test_panic_trap_does_not_block_a_non_blocking_event
4 failed, 55 passed
```

**The headline defect, aimed at the dispatcher itself — measured with the wrong command, so
restated rather than repeated.** The revision-2 line
`PATH=/nonexistent bash dispatch.sh PreToolUse -> 127 / 2` was taken through the outer shell, where
`bash` itself is unresolvable, so it measured the interpreter lookup exactly as H2 describes. The
claim it supported is still the right one, but it must be re-measured with an absolute interpreter
before anyone relies on the number:
```
$ echo '' | env -i PATH=/nonexistent /bin/bash .claude/hooks/dispatch.sh PreToolUse; echo $?
.claude/hooks/dispatch.sh: line 137: cat: command not found
.../lib.sh: line 36: date: command not found
BLOCKED: could not resolve hook handlers for PreToolUse; failing closed.
2                                    <- fails CLOSED, and says why
$ echo '' | env -i PATH=/nonexistent /bin/bash .claude/hooks/dispatch.sh Stop; echo $?
0                                    <- same abort, non-blocking event: no fake block
```
**Re-measured (rev 4)** in the materialised worktree, with an absolute interpreter, so the outer
shell's own lookup cannot be mistaken for the hook's exit code (the H2 lesson). This is the
contrast that matters: the same broken environment makes `ops-enforcement.sh` exit **0** (ALLOW)
today, and makes the dispatcher exit **2** with a reason. `test_dispatcher_with_a_broken_path_fails_closed`
resolves `bash` BEFORE breaking PATH, so the shipped test does not have the defect the plan prose
once had.

**Three bugs were found by executing, not by reasoning** (all fixed in the ops content, each with
the test that caught it named in a code comment):
1. `clamp_advisory` in Python **raised** on `tier="blocking"` — the only value the shipped
   registry uses. The old parity test hid it behind an identity mapping. Python now mirrors the
   shell: only the literal `"advisory"` clamps; every other value passes through **unclamped**,
   which is the fail-closed direction (clamping is what *disarms* a guard).
2. `ck_clamp_advisory` used `${2:-advisory}`, so an **empty** tier clamped — i.e. a guard whose
   tier went missing silently lost its ability to block. Now `${2:-}`.
3. **A malformed payload filtered every matcher-scoped guard out** and the dispatch returned 0 —
   the same fail-open class, reintroduced one layer up. The revision-2 fix — "an unreadable payload
   disables *all* matcher filtering, so every guard runs" — was **half right, and the wrong half
   was critical (C1).**

   *Round 2 executed it:* `echo 'not json' | ECC_HOOK_PROFILE=standard bash dispatch.sh PreToolUse`
   was **still running after 25 s**, with `ps` showing `.claude/hooks/pre-push.sh` — and
   `pre-push.sh:138` runs the **full test suite**. At HEAD that is impossible: `settings.json`
   extracts `CMD` and `grep -qE "^\s*git\s+push"` cannot match a malformed payload, so the hook
   never starts. "Run everything to be safe" **inverted** that protection, in two distinct ways:
   an unbounded stall on any malformed `PreToolUse` payload, and — worse in kind — a guard whose
   precondition is *"the user ran `git push`"* executing on an arbitrary tool call. That is the
   dispatcher running guards outside their contract, the exact risk this plan's own Risk Assessment
   names.

   **The rule now, and why it is still fail-closed:** the **tool-name** matcher stays disabled on
   an unreadable payload (a guard we cannot prove irrelevant runs). A **`command_matcher`** is a
   *precondition*, not a convenience filter: with no command text it cannot be evaluated, so the
   handler is **NOT APPLICABLE** and is skipped. Nothing is weakened — both `command_matcher`
   handlers (`pre-commit`, `pre-push`) are tier `advisory`, so their verdicts are clamped to
   `ADVISE` and they could never have contributed a block; and `ops-enforcement.sh` still exits 2
   on unparseable input, so the end-to-end block is unchanged (asserted: rc **2**).

   *Why the revision-2 test missed it:* `test_command_matcher_filters_and_never_filters_on_a_broken_payload`
   used a **synthetic sandbox registry**, never the shipped one, and its handler was instant. A
   test that never touches the shipped registry cannot see a shipped registry's behaviour. Proof 7
   drives the real file and pins termination, not just the exit code.

---

## [C1-R3] — closed in both halves, and the reasoning is the point

**What round 3 found.** Revision 3 fixed the round-2 hang by making a `command_matcher` handler
NOT APPLICABLE on an unreadable payload. That is the right rule. But the test that revision 2 had
shipped —
`test_command_matcher_filters_and_never_filters_on_a_broken_payload` — asserted the **opposite**,
over a row that was tier `blocking` **with** a `command_matcher`, and its own message called the
skip *"a bypass"*. Revision 3 inverted the rule and left the test in the tree, red:

```
E  assert 0 == 2   ->  returncode=0
tests/test_dispatch_merge.py:553: AssertionError
1 failed, 67 passed
```

Three defects in one artifact, and the third is the serious one:
1. the suite was **red on this lane's own file**, and the DoD tolerates zero failures;
2. the failing test was the plan's **own written refutation of its own fix**;
3. it was the answer to the adversarial question — *what stops a row that CAN block from carrying
   a precondition?* — and at revision 3 the answer was **nothing**. No schema for
   `dispatch-registry.json`, no registry validator, no gate, no test. The reviewer added
   `"command_matcher": "^\s*git\s+commit"` to the shipped **blocking** `commit-quality` row and
   got 68 passed with all eight gates green. Such a row is skipped on a malformed payload, so
   malformed input would silently remove a guard that can block: the exact fail-open class this
   plan exists to kill. The addendum would make it live rather than latent, because it routes all
   11 `PreToolUse` registrations — the only blocking event — through the skip rule.

**Half one — the test is reconciled, not deleted.** It is now
`test_command_matcher_asymmetry_on_an_unreadable_payload`, and it asserts the asymmetry the code
actually implements, in three payload states over three handlers:

| Payload | handler with NO `command_matcher` | handler WITH a `command_matcher` |
|---|---|---|
| readable, command matches | runs | runs |
| readable, command does not match | runs | skipped (precondition false) |
| **unreadable** | **runs** (unchanged — fail closed) | **skipped** (precondition unevaluable) |

and still requires rc **2** on the unreadable payload, so the end-to-end block is pinned. Its
docstring states plainly why the skip is not a bypass — a `command_matcher` is a **precondition**,
and a precondition that cannot be evaluated is not satisfied — and it **keeps the history**: the
old name, the old assertion quoted verbatim, the fact that round 2 executed that rule against the
real registry and the dispatch never returned (`pre-push.sh:138` runs the full test suite), and the
fact that round 3 found the inverted assertion still red in the tree. That history is the round-2
evidence trail and it is preserved deliberately rather than tidied away.

*One defect in this rewrite was found by executing it, not by reading it:* the first draft used the
markers `"CONDITIONAL RAN"` and `"UNCONDITIONAL RAN"` — the first is a **substring** of the second,
so the skip assertion could never have failed. It was a vacuous test that passed. Caught by running
it (`1 failed, 70 passed`), fixed to non-nesting markers, and the reason is now a comment in the
test so it cannot be reintroduced.

**Half two — the invariant is enforced, in the resolver and by a mutation proof.**

> **Rule:** a `dispatch-registry.json` row may declare a `command_matcher` **only** if its tier is
> `advisory`. Any other row is **rejected**.

*Where.* In the `dispatch.sh` resolver, before the handler loop, over **every** event rather than
only the one being dispatched — an illegal row must not be able to hide on an event that happens
not to be firing.

*Exit code, and why.* The resolver exits **3**. That is the code it already uses for *"the registry
cannot be trusted"* (a JSON parse failure, and an `args` entry containing whitespace), so the codec
gains no new vocabulary. **3 never reaches Claude Code:** any non-zero resolver rc lands in
`dispatch.sh`'s registry-resolution branch, which prints `BLOCKED:` to stderr and exits **2** on a
blocking event and 0 elsewhere. So the hook boundary still only ever emits 0 or 2 (hard rule 2:
blocking is `exit 2` + stderr, fail closed), and an illegal registry fails **closed** rather than
silently allowing. The resolver's own message names the offending row and event and goes to
`hooks.log`.

*Why this is the fail-closed direction.* The alternative — accept the row and run it anyway — is
what caused the round-2 hang. Rejecting the registry blocks; accepting a row we cannot reason about
runs a guard outside its contract. The invariant also keeps half one honest: the skip is safe
**because** such a handler is clamped to ADVISE, and that is now a checked property rather than a
sentence in a plan. Per this plan's own thesis: an invariant the code depends on and does not
enforce **is** the defect.

*Proven by mutating the shipped artifact — and the previous revision's headline figure was wrong.
Corrected here (M1-R4).*

**What revision 4 printed** was `rc=0 <- BYPASS` for the counter-mutant, labelled "same registry,
same payload". **That does not reproduce on the shipped artifact.** Round-4 review re-ran it against
the real 26-row registry with the illegal row on `commit-quality` and the invariant block deleted —
**re-measured by round-4 review:**

```
prof=minimal   NOCHECK rc=2 | WITHCHECK rc=2
prof=standard  NOCHECK rc=2 | WITHCHECK rc=2
prof=strict    NOCHECK rc=2 | WITHCHECK rc=2
```

`rc=0` appears **only when the registry is reduced to that single row**, which is the setup
revision 4 actually used and did not say so. On the shipped registry the sibling blocking guards
(`reflection-gate`, `command-guard`, `ops-enforcement`, `config-protection`) each fail closed on
unparseable input **independently**, so defence-in-depth **masks** the bypass in the exit code.

The honest conclusion is unchanged, and is worse than the number suggested: **the hole is real, and
the layered guards are luck, not design.** Nothing in the architecture says four sibling guards
must keep failing closed on malformed input; the moment one of them is fixed, relaxed, or the only
guard on an event, the masking disappears. And the isolated measurement is not a contrivance — it
is what an installed user project looks like when it has one or two hooks.

*Correctly labelled figures, single-row isolation, on `block-no-verify.sh` (a handler that really
reaches `exit 2`) — **re-measured by round-4 review**, materialized core tree:*

```
tier=""         READABLE   rc=2   [block-no-verify] BLOCKED: The --no-verify flag ...
tier=""         MALFORMED  rc=0   <- silent ALLOW. The guard was removed by malformed input.
tier="blocking" MALFORMED  rc=2   BLOCKED: could not resolve hook handlers for PreToolUse
```

*What binds regardless of the masking.* The **test** mutation proof was sound even while the prose
was wrong: it uses a readable `echo hi` payload, so both mutants bind. Revision 5 makes it
independent of the exit code altogether — the assertion is now the resolver's own
`illegal registry row` line in `hooks.log`, which no sibling guard can produce. **This is the third
time an unreproduced headline number has appeared in this plan** (H1 and H2 in rounds 1–2); the
correction here is to state the setup, not to restate the number.

and the test binds on the same mutation:

```
$ python3 -m pytest tests/test_dispatch_merge.py -q          # invariant block removed
E  AssertionError: a blocking row with a command_matcher was ACCEPTED ... rc=0
FAILED tests/test_dispatch_merge.py::
       test_a_blocking_row_carrying_a_command_matcher_is_rejected_by_the_resolver
1 failed, 70 passed     # rev-4 transcript, pre-revision-5 file; NOT re-run at revision 5
$ python3 -m pytest tests/test_dispatch_merge.py -q          # shipped dispatcher restored
86 passed               # re-measured by round-5 review at revision 5 (was 71 passed at rev 4)
```

The mutated run's `1 failed, 70 passed` is the rev-4 transcript and is left as measured; only the
control count was re-run at revision 5, and it is labelled as the round-5 reviewer's measurement.

`commit-quality` is the mutant on purpose: it is tier `blocking` in the shipped registry **and**
`commit-quality.sh` really contains `exit 2`, which the test asserts before mutating. `pre-push.sh`
would be the wrong mutant — it has no `exit 2`, so relabelling it trips `test_blocking_tier_is_honest`
instead and proves nothing about this check.

**A third defect this revision found by executing, in the repo's own linter.** Adding the invariant
pushed the resolver heredoc to **103 lines**; `scripts/check-silent-failure.py` caps a heredoc skip
at `MAX_JOIN_LINES = 80`, then abandons the skip and reports the scan **INCOMPLETE** — reding
`test_repo_residue_is_confined_to_known_paths` and
`test_planted_fixture_is_excluded_from_a_whole_repo_scan`. Revision 3's body was 71 lines, one
nudge from the cliff. The fix is not to relax the linter on a security-relevant file: the resolver's
rationale comments were **relocated verbatim** into shell comments immediately above the
invocation, no sentence rewritten or dropped, and the body is now **58 lines** with margin. Both
lint tests are green (re-measured, rev 4). Recorded because it is exactly the failure mode this
plan keeps punishing: a gate that goes quiet is worse than a gate that fails.

---

## [C1-R4] The Critical — `tier: ""` evaded the invariant. One word, and the fix.

**The defect.** `.claude/hooks/dispatch.sh`, the registry invariant, as revision 4 shipped it:

```python
        if isinstance(_r, dict) and (_r.get("command_matcher") or "") and \
                (_r.get("tier") or "advisory") != "advisory":     # <-- WRONG
```

`(_r.get("tier") or "advisory")` maps `""`, `None` **and** an absent key all onto `"advisory"`, so
all three are **accepted**. But `lib.sh`'s `ck_clamp_advisory` disarms **only** the literal string
`"advisory"`, and its own comment explains why that is deliberate: *"`${2:-}`, not
`${2:-advisory}`: an omitted or empty tier must NOT clamp, because clamping is what DISARMS a
handler."* Both sides were defensible in isolation. Together they were a bypass.

**The exact diff.** Two lines in, two lines out — the heredoc body stays at 58 lines, so
`check-silent-failure.py`'s `MAX_JOIN_LINES = 80` cap is untouched (verified statically, rev 5):

```diff
         if isinstance(_r, dict) and (_r.get("command_matcher") or "") and \
-                (_r.get("tier") or "advisory") != "advisory":
+                _r.get("tier", "advisory") != "advisory":
```

**The evasion matrix — re-measured by round-4 review** (materialized core tree, single-row registry
on `block-no-verify.sh`, a handler that really reaches `exit 2`):

| `tier` | Pre-fix invariant | Clamp disarms it? | Consequence |
|---|---|---|---|
| `"advisory"` | accepted | yes | correct, and intended |
| `""` | **accepted** | **no** | **exploitable.** Readable payload -> rc 2 (it really blocks); malformed payload -> **rc 0, silent ALLOW**. Malformed input removed a live guard. |
| `null` | accepted | no | fail-closed **by accident only**: `"\t".join(None)` raises, the resolver dies rc 1, the dispatcher blocks. An accident is not a control. |
| absent | accepted | yes | safe, and *consistently* so: the resolver **emits** `"advisory"` for an absent key, so the row really is clamped. |
| `"blocking"`, `"on"`, `"bogus"` | rejected | no | correct |

**Why Critical rather than Medium.** Two implementations of one invariant, with two different
normalizations: the resolver used the `or` form while the plan's own static companion test at
`tests/test_dispatch_merge.py` used the **correct** strict form
(`assert row.get("tier") == "advisory"`). And `install.sh:276-283` copies every file in
`.claude/hooks/` into user projects, so **in an installed tree the resolver is the only
enforcement** — the pytest companion is a repo gate and does not ship. A divergence between the two
is therefore not a lint nit; it is the whole control, failing on one side only.

### The reconciliation — one normalization rule, written down in three places

> **Rule.** A row's **effective tier** is `row.get("tier", "advisory")`. An **absent** key means
> advisory. An explicitly **empty or null** tier does **not**. The set of tiers the invariant
> ACCEPTS must be exactly the set `ck_clamp_advisory` DISARMS; a divergence between those two sets
> is not a style difference, it **is** the bypass.

Why *this* normalization and not the strict one (`row.get("tier") == "advisory"`) in the resolver:
the resolver **already** emits the tier downstream as `row.get("tier", "advisory")` (the same line
that builds the handler's tab-separated record). Reading it any other way would mean the invariant
judged a row by a different tier than the one the clamp is handed. The fix makes the invariant read
the tier *exactly as the emitter writes it* — one expression, used twice in the same resolver.

Where the rule is now recorded, and how a future one-sided edit is caught:

| Place | What it says |
|---|---|
| `dispatch.sh`, the "THE RULE, ONCE" header block | The rule, plus the sentence that revision 4's `or` form accepted `""` while the clamp refused to disarm it. |
| `lib.sh`, above `ck_clamp_advisory` | "THE RESOLVER MUST ACCEPT EXACTLY WHAT THIS FUNCTION DISARMS" — with the resolver's expression quoted, and a pointer to the test. |
| `test_the_shipped_registry_keeps_preconditions_on_advisory_rows_only` | Why the **static companion is deliberately STRICTER** (it also requires the key to be *present*), and that the strictness runs one way only: every registry that passes it also passes the resolver, so it can never green a row the resolver would reject. |
| `test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms` | The rule as an **executable property**, per tier value, driving the shipped dispatcher. This is what fails when someone edits one side and not the other. |

### Proven by mutation — and the mutant assertion itself had to be fixed

`test_a_blocking_row_carrying_a_command_matcher_is_rejected_by_the_resolver` is now
`@pytest.mark.parametrize`d over `["blocking", "", None]` (ids `blocking`, `empty-string`, `null`).
Reverting the resolver to the `or` form must fail the two new ids.

**A weak-assertion trap — and the revision-5 rationale for it was WRONG. Corrected here from the
round-5 reviewer's execution.** The existing mutant test asserted
`RESOLVER_REJECTION in result.stderr`, where
`RESOLVER_REJECTION = "could not resolve hook handlers"` — the **dispatcher's** generic line, which
it prints for *any* non-zero resolver rc. Revision 5 claimed that with `tier: null` the pre-fix
resolver accepted the row, crashed in `"\t".join(None)`, produced rc 1 and therefore that same
line, so the `null` mutant "would have passed against the bug it exists to catch". **The round-5
reviewer executed it and that is false.** The mutated row carries
`command_matcher = "^\s*git\s+commit"` and the test's payload is `{"command": "echo hi"}`, so the
row is skipped by the **precondition** before the join is ever reached — no crash, no generic line.
**Re-measured by round-5 review** (pre-fix resolver):

```
pre-fix, payload {"command": "echo hi"}   tier=None  rc=0   OLD assertion -> False
pre-fix, payload {"command": "echo hi"}   tier=""    rc=0   OLD assertion -> False
pre-fix, payload {"command": "git commit ..."}  tier=None  rc=2   OLD assertion -> True
pre-fix, payload {"command": "git commit ..."}  tier=""    rc=0   OLD assertion -> False
```

So for **this test's own payload** the old assertion was **weak but NOT vacuous** — it would have
failed, i.e. it *would* have caught the bug. The vacuity is real only under a **matching** command
payload, where the `null` mutant reaches the join, exits 2, and satisfies the generic line. The
dependence is on the payload, and revision 5 asserted the vacuous case unconditionally without
running it. **This is the fourth unreproduced claim in this document** (H1, H2, M1, and this one)
and it is the only defect class that has recurred across four rounds — see the guard recorded
below. **The remedy stands, and stands on the reviewer's own measurement, not on the wrong
rationale:** the round-5 reviewer independently verified that asserting the resolver's own
`illegal registry row` message in `hooks.log` is strictly stronger evidence than the generic line,
and that it binds. Fixed by asserting the resolver's **own** message,
`illegal registry row`, which the heredoc writes to `hooks.log` (its stderr is appended there) and
which no other failure path produces:

- `ILLEGAL_ROW in hooks.log` — the specific evidence that *this* check fired. Asserted **first**.
- `RESOLVER_REJECTION in stderr` and `rc == 2` — asserted after, as the rendering, not as the proof.
  Per M1-R4, rc alone is masked by the sibling guards on the shipped registry.
- `hooks.log` is truncated before the mutant and the revert runs, so a later read cannot see an
  earlier run's line.

**Guard for the recurring class (round-5 reviewer's proposal, recorded because it cannot be
mechanised — you cannot lint English for reproducibility).** No revision of this plan ships an
evidence block whose figures were not produced by a command *in that same revision*, and every
"would have passed / would have failed" claim about a mutant must cite the run that produced it.

**Still not yet executed.** No test in this revision has been run: the revision-5 author's Bash is
scoped to `validate-config-json.py`. The reviewer's sequence (below) is the one that closes this.

---

## [M2-R4] `exit 1` escaped the hook boundary. Taken.

Round-4 review's 21 escape probes found exactly one non-`{0,2}` exit code in the whole dispatcher —
**re-measured by round-4 review:**

```
=== no event arg   rc=1   ***ESCAPE***
```

Hard rule 2 permits only 0 or 2 at a hook boundary, and the reason is behavioural, not cosmetic:
Claude Code honours **2** as a block and treats every other non-zero code as **NON-BLOCKING**. So a
dispatcher registered with a missing, misspelled or wrong-case event name **failed open** on
`PreToolUse` while looking like a loud error. It is unreachable through the shipped wiring today
(addendum op 1 does pass `PreToolUse` — prior-round evidence, not re-run) — and "unreachable today"
is precisely the argument that produced C1-R4, so it is not accepted as a defence.

**The fix.** The blocking-event `case` now also sets `EVENT_KNOWN`, and an unknown or missing name
fails closed:

- `PreToolUse` -> `EVENT_BLOCKING=1, EVENT_KNOWN=1`.
- The other **seven** registry events -> `EVENT_BLOCKING=0, EVENT_KNOWN=1`.
- Anything else, including empty -> `EVENT_BLOCKING=1, EVENT_KNOWN=0` -> `BLOCKED:` on stderr,
  **`exit 2`**.

Case sensitivity is deliberate and matches the invariant's (round 4 confirmed the invariant
correctly rejects `Advisory`, `ADVISORY`, `" advisory"`, `"advisory "`): `pretooluse` is not
`PreToolUse`, and a dispatcher that guesses which one the operator meant can guess wrong about a
guarded event.

**The cost of failing closed here, stated.** An event that *is* registered but missing from the
`case` list would now **block** instead of running. That is the safe direction, but it is not free,
so it is bounded by `test_the_known_event_list_matches_the_registry`, which fails at build time if
the two sets ever differ — and the blast radius today is one event, because only `PreToolUse` is
wired (and only by the suspended addendum). Both are **not yet executed**.

---

## [L1-R4] Spill files took the umask while the event log did not. Taken.

`eventlog.append` opens with `os.open(path, O_WRONLY|O_CREAT|O_APPEND, 0o600)`. `spill()` used a
plain `open(tmp, "w")`, which takes the **process umask** — so on an ordinary `022` box every spill
file was `0644`. Spilled text is the oversized tool output that could not stay inline, which is
exactly where a secret ends up; that is the entire point of spilling. A world-readable copy of it
on disk is a **new disclosure created by an optimisation**.

**The fix,** in `spill()`: the session directory is created `0700`, and the file is written through
`tempfile.mkstemp(dir=directory, ...)` + `os.replace`. `mkstemp` was chosen over
`os.open(fixed_name, O_WRONLY|O_CREAT|O_EXCL, 0o600)` deliberately: it gives the same `O_EXCL`
(so a symlink planted at the temp name cannot redirect the write) and the same `0600`
**irrespective of umask**, but its name is unique — a fixed `pid`-suffixed name plus `O_EXCL` would
leave a stale temp behind after a crash and make every later spill of that digest fail
**permanently**. `os.replace` preserves the mode, so the published file is `0600` too. A `finally`
unlinks the temp on any failing path (it is already gone on the happy one). `tempfile` is added to
`test_spill.py`'s model-free import allowlist.

**Both mode tests force `umask` to `0o022` and restore it.** Without that, a developer running
`umask 077` would get `0600` from the *old* `open()` form as well, and the test would pass against
the defect it exists to catch — a vacuous security test. `eventlog`'s `0600` was **correct and
asserted nowhere**; it is asserted now, so the correct side of the asymmetry is no longer one
refactor from silent loss. **Not yet executed.**

**[L2-R5] The spill DIRECTORY mode was correct and asserted nowhere — the same class, missed by the
sweep that caught it for `eventlog`.** `spill.py` creates the session directory with
`os.makedirs(directory, mode=0o700, exist_ok=True)`. The **round-5 reviewer's mutant dropped both**
that `mode=0o700` **and** the file mode, and **only the file assertion flipped** — so under umask
`022` the spill directory would silently become `0o755` with nothing catching it. Impact is small
(the files inside stay `0600` and their names are sha256 digests, so the directory leaks
traversability rather than content), but "correct but asserted nowhere" is exactly the class this
plan claims to have swept. Fixed inside the existing umask-forced block of
`test_a_spill_file_is_readable_only_by_its_owner`:

```python
spill_directory = os.path.dirname(result["path"])
dir_mode = stat.S_IMODE(os.stat(spill_directory).st_mode)
assert dir_mode == 0o700, (...)
```

`stat` was **already imported** by that test payload, and the model-free import allowlist inside
`test_spill.py` constrains **`spill.py`'s** imports, not the test's, so neither needed an edit.
Two details make the assertion non-vacuous, and both are written into the test as comments: it
asserts on `os.path.dirname(result["path"])`, the `<spill_dir>/<session>` directory that `spill()`
creates **itself** (asserting on `tmp_path` would be vacuous, because `makedirs(exist_ok=True)`
leaves an existing directory's mode alone), and the umask is already forced to `0o022`, so
`0o700 & ~umask == 0o700` while the default `0o777 & ~umask == 0o755`. **Prove-by-mutation intent:
deleting `mode=0o700` must now fail this test.** Prose and test payload only — no product file and
no resolver logic changed. **Not yet executed** (the revision-6 author's Bash is scoped to
`validate-config-json.py`); the mutation run belongs to the reviewer's sequence.

---

## Testing Strategy

Behavioural only: the dispatcher is driven as a subprocess and asserted on its exit code — the
only thing Claude Code observes. `ECC_HOOK_PROFILE` is forced explicitly in every test, and
`test_minimal_profile_still_short_circuits` proves `minimal` still works through the dispatcher
(handlers read the env var exactly as before; the dispatcher adds no new switch).

**H1 — the timeout claim is deleted, not implemented. Choice: (b).** The shipped comment said
`ANY other exit (crash, timeout, 127) -> ERROR`; `grep -n 'timeout\|TIMEOUT' dispatch.sh` returned
only that comment, and `test_crashing_handler_fails_closed[124]` feeds a **pre-cooked** 124 — it
proves the codec, not a bound. So the word is gone from `dispatch.sh`, from `lib.sh`'s comment, and
from this plan; `dispatch.sh` now carries an explicit **"WHAT THIS DOES *NOT* DO: THERE IS NO
PER-HANDLER TIMEOUT"** block, and the gap is filed in `.ai/BACKLOG.md` with the shape a real fix
would need. Why (b) and not (a): macOS has no `timeout(1)`; a bash-3.2 background+poll+kill wrapper
cannot reliably kill a handler's **descendants** without a process group, so it would bound the
dispatcher while leaving the child tree running — a control that looks like enforcement and is not;
`pre-commit`/`pre-push` legitimately run for minutes, so any bound short enough to help would break
them, which means (a) really requires a per-handler `timeout_s` with an unbounded opt-out; and
revision 3 could not execute, so shipping new unbounded-wait shell with an *asserted* mutation
proof would have been the very sin H2 punished — and revision 4 does not reopen a settled decision
merely because it *can* execute. Hard rule 6 decides it: do not document a control that does not
exist. The one **measured** stall is fixed at its cause (C1), not masked by a timer.

---

## Execution runbook — numbered, and step 5 is an OPERATOR action

[H1-R3] Round 3 noted that op 18 records the archive row but the **file move itself** is a
`git mv`, outside the ops engine — so the DoD is not reachable by `execute-json-ops.py` alone. That
is accepted (it is not an Iron Law violation: the implementer still never gets Edit/Write, and a
`git mv` is an operator action), but it must not be *skippable*. It is promoted here to an explicit
numbered step. **No `move` op type is invented in this revision** — that is a schema change and a
separate, owner-gated decision.

Run in order. Do not skip 5.

1. **Baseline, in a `git worktree` outside the session scratchpad.** Record the failure **set**,
   not the count. Expect exactly one failure at `5f3e322`
   (`test_day_one_blockers.py::TestSelfScanIsClean` -> `tests/test_memory.py`) unless the
   separately-approved memory-lane fix has already landed, in which case expect zero.
2. **Validate the core config:** `python3 .claude/operations/scripts/validate-config-json.py
   .claude/plans/plan-enforcement-runtime.ops.json` -> must print `APPROVED`.
3. **Execute the core config** through `execute-json-ops.py`. 18 ops, no `run_command`, no
   `file_delete`.
4. **Re-run the suite and the eight gates.** Expect the same failure set as step 1, plus ~105 new
   passing tests. Expect `gen-docs.py --check` to report `hooks=22` and `OK`.
5. **OPERATOR STEP — perform the archive move by hand, in the same commit:**
   ```
   git mv .claude/plans/plan-enforcement-runtime.ops.json \
          .claude/plans/archive/ops-enforcement-runtime.json
   ```
   Op 18 has already appended the matching README row; this step moves the file the row describes.
   **If you skip it, `test_queued_ops_configs_validate_against_head` fails by name** — a spent
   config self-invalidates, because its `find` strings no longer exist once applied. That failure is
   the gate doing its job, and it is the *only* symptom, so it is recoverable rather than dangerous.
   Note that a `git worktree` measurement cannot see this test at all (the plan configs are
   untracked), which is exactly why the step is written down instead of inferred from a green run.
6. **Commit one concern**, conventional commit, `Co-Authored-By:` line. Append-only entries in
   `CHANGELOG.md`, `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md` are already carried by ops 15-17;
   `git pull --rebase` first, and on a conflict in a contended file **keep both entries**.
7. **STOP and check the two conditions before the addendum.** Round 5 approved the addendum
   **with two conditions**: step 5's archive move must already be done (condition 1), and op 2 must
   be an append rather than a `replace` on `CHANGELOG.md` (condition 2, satisfied in this
   revision). It also still needs the open-decision-2 ack for the two test files outside both
   lanes. Do not move it out of `.claude/plans/pending/` before then.
8. The verifier agent does **not** auto-run. Ask first.

---

## Asset-count delta

| Asset | Before | After | Why |
|---|---|---|---|
| Hooks | 21 | **22** | `dispatch.sh` is a new counted hook. `dispatch-registry.json` is not counted (`HOOK_GLOBS = ("*.sh","*.py")`); `lib.sh` stays a helper. |
| Agents / commands / skills | 29 / 42 / 76 | unchanged | Not this lane. |
| `settings.json` registrations | **26** across 8 events (re-measured) | 26 (core) → **16** (with addendum: the 11 `PreToolUse` entries become 1) | |
| Context floor | unchanged | unchanged | No agent/skill/command description touched. |

Net **+1 hook** (21 → 22), and **no other asset count moves**: `dispatch-registry.json` is not
counted (`HOOK_GLOBS = ("*.sh","*.py")`), `lib.sh` stays a helper, and the three test files, the
`src/claudekit/enforcement/` modules and the doc/backlog/archive edits are not counted assets.
Revision 6 adds **zero** new assets and moves no count either: its whole diff is one appended
CHANGELOG bullet in the addendum (replacing a `replace`), one assertion plus comments in the
`test_spill.py` payload, and plan prose. **Net asset delta is unchanged at +1 hook (21 -> 22).**
Revision 5 adds **zero** new assets and moves no count: its whole diff is one expression and one
comment block in `dispatch.sh`'s invariant, the `EVENT_KNOWN` arm and the boundary exit code in the
same file, a comment beside `ck_clamp_advisory` in `lib.sh`, the `mkstemp` write in `spill.py`, four
new/parametrized tests plus one import and one allowlist entry across the three test files, one
archive-README sentence, and plan prose. **No new file, no new hook, no new module.** Revision 4
likewise added **zero** new assets, exactly as revision 3 did: its changes are one resolver
check plus a comment relocation inside `dispatch.sh`, one rewritten and three new tests inside an
existing test file, `_doc` text in the registry, doc wording, and plan prose. **Net asset-count
delta for the whole plan is unchanged: +1 hook (21 -> 22), nothing else moves** — re-measured
(rev 4): `gen-docs.py --check` reports `agents=29 commands=42 skills=76 hooks=22` and `OK` with the
core config applied. Handler *merging* (task 008) is not attempted here and
remains open; this phase adds the substrate that makes it possible without pretending to have done
it.

## Rollback

Every op is reversible without a migration: `git revert` the single commit, or delete
`src/claudekit/enforcement/`, `dispatch.sh`, `dispatch-registry.json` and the three test files,
drop the appended `lib.sh` block (a contiguous trailing region below `ERE_NOT_QUOTE_CLASS`), and
re-run `python3 scripts/gen-docs.py` to take the counts back to 21. `.claude/runtime/` is
gitignored and can be removed at any time. The archive step (op 18 + the `git mv`) reverts with the
same `git revert`; if the config is applied but *not* archived, the only symptom is
`test_queued_ops_configs_validate_against_head` failing by name, which is the gate doing its job. **No hook behaviour changes under the core config**,
which is exactly why rollback here is cheap. The addendum is reverted by restoring the
`PreToolUse` block in `settings.json` — kept verbatim in that config's `find` string.

## Risk Assessment

**High**
- *The addendum's `settings.json` rewire.* Routing 11 live registrations through one new
  dispatcher is the change that can silently drop a guard. Mitigated and **measured**: with the
  addendum applied, the full suite's failure set is still byte-identical to baseline, and the
  repo's own pre-existing wiring detectors (`test_iron_law_hook`, the `test_pipeline_e2e` chain
  tests) were **updated to resolve wiring through the registry rather than weakened** — they now
  fail if a handler is dropped from `dispatch-registry.json`, which is strictly more coverage than
  before. Held to its own config on purpose.

**Medium**
- *A registry invariant is now load-bearing (C1-R3).* The not-applicable skip rule is safe only
  while a `command_matcher` row cannot block, and that is enforced in one place — the resolver. It
  is proven by mutating the shipped registry, and a second test stops the check degenerating into
  "reject every precondition". The residual risk is that the invariant lives in the resolver rather
  than in a schema for `dispatch-registry.json`; a schema is the more complete answer and is **not**
  attempted here (it is a new artifact and a wider decision). What is closed is the fail-open path.
- *The resolver heredoc sits under a linter cap.* `scripts/check-silent-failure.py` abandons a
  heredoc skip past `MAX_JOIN_LINES = 80` and then reports the file's scan INCOMPLETE — a gate going
  *quiet*, not loud. The body is 58 lines now, but anyone adding to that heredoc must keep it under
  the cap or move the addition into shell comments. Measured, red, and fixed in this revision.
- *No per-handler timeout (H1, accepted and documented).* A handler that blocks forever stalls the
  tool call, and the dispatcher cannot see it. The dispatcher does **not** make this worse than
  HEAD once C1 is fixed — it now runs the same handlers under the same preconditions
  `settings.json` enforced — but it does not improve it either. Filed; the shape of a real fix is
  recorded with it.
- *A guard running outside its precondition (C1's class) is a dispatcher-shaped risk, not a
  one-off.* Any future registry field that gates a handler must answer "what does this mean when
  the payload is unreadable?" — and the answer for a *precondition* is "not applicable", while for
  a *relevance filter* it is "run anyway". Both directions now exist in the code with the reasoning
  attached, and proof 7 pins the one that stalls.
- *The addendum's single REPLACE on a contended file (L1).* Addendum op 2 rewrites the
  `CHANGELOG.md` bullet that this plan's **own** core op 15 authored, so COORDINATION.md's "never
  rewrite another agent's rows" is not violated — but if Agent B appends to `[Unreleased]` between
  the two configs it conflicts hard. Recorded in that op's `description` as a precondition: keep
  **both** entries on rebase and re-apply the swap by hand. The **core** config still has zero
  REPLACE on a contended file.
- *Two implementations of one table* (bash + Python). Mitigated by parity tests over every input
  and every tier string; drift is a suite failure.
- *Two implementations of one **invariant** — the residual C1-R4 risk.* The registry invariant lives
  in the resolver; a stricter static form of it lives in `test_dispatch_merge.py`. That duplication
  is now **documented on both sides with the normalization rule spelled out**, and the equivalence
  between "what the invariant accepts" and "what the clamp disarms" is asserted as an executable
  property per tier value. What is *not* eliminated is the duplication itself: a schema for
  `dispatch-registry.json` is the more complete answer and remains out of scope (a new artifact, a
  wider decision). The mitigation is that a one-sided edit now fails a test rather than shipping.
- *Failing closed on an unknown event name (M2-R4) is not free.* An event registered in
  `dispatch-registry.json` but absent from `dispatch.sh`'s `case` list now **blocks** rather than
  runs. Bounded by `test_the_known_event_list_matches_the_registry` (build-time, loud) and by the
  fact that only `PreToolUse` is wired at all, and only by the suspended addendum. The alternative —
  treating an unknown name as advisory — is a silent fail-open, which is the defect class this
  phase exists to remove.
- *`0700` on the spill session directory (L1-R4) is `exist_ok=True`,* so a directory that already
  exists keeps its current mode. The file mode is the load-bearing control; the directory mode is
  an adjunct. Stated rather than implied.
- *`lib.sh` is sourced by every shell hook.* Pure append of `ck_`-prefixed names; verified by
  running the existing hooks against the appended library.
- *Event-log write per handler invocation.* Best-effort at the call site (a full disk must not
  brick a session), strict at the schema. Cost is one short `python3` process per handler —
  **measure before the addendum rather than assuming it is free**; with 11 PreToolUse handlers
  that is up to 11 extra interpreter starts per tool call.

**Low**
- New stdlib-only package, py3.9 clean. `.claude/runtime/` gitignored and session-scoped.

---

## Open decisions — owner only

0. **THE WIRING ADDENDUM IS APPROVED WITH TWO CONDITIONS** (it was SUSPENDED through round 4).
   The owner suspended `.claude/plans/pending/plan-enforcement-runtime-wiring.ops.json` on the
   round-3 reviewer's recommendation: it must not run until the outstanding Critical is fixed
   **and re-reviewed**. Revision 4 fixed C1-R3 and round 4 confirmed that by execution — then
   found **C1-R4** in the same check. Revision 5 fixes C1-R4, and **round 5 re-reviewed it and
   recommends the addendum as safe to run**, subject to exactly two conditions: **(1)** land the
   core config first and archive its spent config per runbook step 5, before the addendum;
   **(2)** convert addendum op 2 from `replace` to an append on `CHANGELOG.md` — done in this
   revision ([L3-R5]). Lifting the suspension is still the **owner's** call, and the
   open-decision-2 ack below is still outstanding. It stays in `pending/` until then. The original
   reason was specific rather than procedural: the addendum
   routes all 11 `PreToolUse` registrations through `dispatch.sh`, `PreToolUse` is the only blocking
   event, so the not-applicable skip rule becomes the **sole live guard path** — which is precisely
   why the invariant behind that rule had to be enforced before the rewire could be trusted.
1. **Run the wiring addendum, or leave the dispatcher dark?** *Not decided here, on purpose.*
   Both branches are ready and both are honest about themselves. Arguments each way: an unwired
   dispatcher is exactly the "written up but never built" shape this lane exists to fix (it is
   proven by execution, but not load-bearing) — against which, the rewire is the one change in
   this phase that can silently drop a guard, and `settings.json` is shared with Agent B.
   The addendum's scope is deliberately **`PreToolUse` only**: it is the only event where
   Claude Code honours `exit 2`, and four hooks on the other events are backgrounded with `&`,
   which the dispatcher does not model yet.
2. **Two files outside both lanes.** The addendum edits `tests/test_pipeline_e2e.py` and
   `tests/test_iron_law_hook.py`, which `COORDINATION.md` assigns to **neither** agent. They are
   pre-existing wiring detectors that correctly fire on the rewire, so the addendum cannot be
   correct without them. **This needs an explicit ack (owner or Agent B) before the addendum
   runs.** The core config touches neither.
3. **The addendum lives in `.claude/plans/pending/`, not `.claude/plans/`.** Not evasion — a
   deliberate consequence of the repo's own gate: `test_queued_ops_configs_validate_against_head`
   requires every `.json` directly in `.claude/plans/` to validate against the *current* tree, and
   a successor config whose anchors the predecessor creates cannot. Move it up one directory at
   the moment the core commit lands; it validates there (proven below).
4. **`hooks.log` (~2.5 MB of prose, re-measured)** is left alone and its shape pinned by a test. Migrating or
   rotating it is a separate, owner-approved change.
5. **Spill thresholds** (`8192` bytes, `1024`-byte preview) are first guesses, not measurements.
6. **The three `-gate` hooks that cannot block** are now filed in `.ai/BACKLOG.md` (op 13). If any
   was meant to block, that is a live gap; promoting one is an owner call, not a refactor.
7. **Verifier does not auto-run.** Per CLAUDE.md, ask first.
8. **No per-handler timeout (H1, choice (b)).** Documented as absent rather than implemented, for
   the reasons in Testing Strategy. If the owner wants a bound, it is a separate change: a
   per-handler `timeout_s` in the registry with an explicit unbounded opt-out for
   `pre-commit`/`pre-push`, background+poll+kill (no `timeout(1)` on macOS), an honest note that
   descendants may outlive the kill, and a mutation proof that a sleeping handler yields exit 2 on
   a blocking event.
9. **A pre-existing gate failure at HEAD belongs to the memory lane.**
   `test_day_one_blockers.py::TestSelfScanIsClean::test_no_committed_file_matches_a_live_pattern[api_key...]`
   fails against `tests/test_memory.py` (240/257/438), committed in `5f3e322`. Not Agent A's file
   and not fixed here. Whoever runs the DoD sweep must expect it at baseline.

---

## The wiring addendum — `.claude/plans/pending/plan-enforcement-runtime-wiring.ops.json`

7 ops, all `code_edit`: (1) `settings.json` — the 11 `PreToolUse` entries become one `dispatch.sh`
entry (the old block is the `find` string, so the revert is verbatim); (2) `CHANGELOG.md` —
replaces the "still open" bullet with a "fixed on `PreToolUse`" bullet that is explicit about the
seven events it does *not* cover, about the `exit 0` shape no codec can fix, and about the absent
timeout. **Its `find` string is a verbatim copy of core op 15's payload and was regenerated from it
in this revision** — if core op 15 is edited again, this anchor must be regenerated with it. Its
`description` now records both preconditions: core-applied, and the contended-file conflict risk
(L1); (3) `README.md` and (4) `docs/HOOKS.md` — "all wired";
(5) `.ai/CHANGELOG_AI.md` — records that Phase 0b ran, as its own line; (6–7) the two
wiring-detector test files (decision 2 above).

**[M1-R3] "One dispatcher per event" describes the design, not today's coverage — and the docs
now say so.** The addendum routes **only** `PreToolUse` through `dispatch.sh`; the other **15
registrations across 7 events still invoke their hooks directly**, so the merge rule and the
event-log emission do **not** apply to them. That is defensible — `exit 2` is only honoured on
`PreToolUse`, and four of the other hooks are backgrounded with `&`, which the dispatcher does not
model — and `dispatch-registry.json`'s `_doc` already explains it. But deliverable 0.2 is *titled*
"one dispatcher per event", so the user-facing prose must not be readable as "all eight events are
covered". Corrected in this revision, precisely: core op 12 (`docs/HOOKS.md`) no longer calls it
"the one-dispatcher-per-event front end" but "the per-event dispatcher front end … for the event it
is wired on", and states that the rewire covers **`PreToolUse` only** and that "one dispatcher per
event" is the design realised for a single event today; addendum op 4 says **"that event only"** and
"**one of the eight events** is routed through it, and the merge rule and the event-log records
apply to that event alone"; addendum op 3 (`README.md`) says "`PreToolUse` handlers — and, of the
eight events, only those". Addendum op 4's second `find` string was **regenerated** from the revised
core op 12 payload and re-validated (count 1).

**[L3-R5] Addendum op 2's `REPLACE` on `CHANGELOG.md` is CONVERTED to an append. Taken.** Rounds 3
and 4 accepted it as-is on the grounds that the engine fails closed on a missing pattern, so the
failure mode is a rejected validate rather than a corrupted file, and that the replaced text was
this plan's own bullet (core op 15) rather than Agent B's row. Both remain true — the residual risk
was a **rebase conflict**, not data loss — but `COORDINATION.md` mandates append-only on
`CHANGELOG.md` without a "your own row" exception, and the **round-5 reviewer made this conversion
a condition of running the addendum**. It is done:

| | Before | After |
|---|---|---|
| Edit form | `replace` (1389-char bullet swapped out) | `add_after` |
| Anchor | the whole "Still open: a hook that breaks still fails open" bullet | its last line, `worse than one that says it is open.` (count **1** against HEAD+core) |
| Effect | rewrote the core's "landed, and deliberately NOT yet wired" bullet | **appends a third bullet** recording that the wiring subsequently landed |

Reading order after both configs run, verified by applying both to a HEAD tree: (1) "Enforcement
runtime … landed, and deliberately NOT yet wired", (2) "Still open: a hook that breaks still fails
open in the live path", (3) "**Update, superseding the two entries above: `PreToolUse` is now wired
onto the dispatcher.**" The third states in plain language that it supersedes the first two, so the
reader is not left holding two contradictory statements; the still-open residue (a hook that
degrades to `exit 0`, and the absent per-handler timeout) is restated in the third bullet rather
than left implied by the second. The addendum's anchor count is unchanged at **8/8, count 1 each**,
and no other op depended on the text this op used to replace. **Both** configs now have **zero**
`replace` on a contended file (core: 5 contended edits, all `add_after`/`add_before`; addendum: 2,
both appends).

**Validation, re-run in revision 4.** Against HEAD alone it is **REJECTED — 5 patterns not
found**, which is *by design* (open decision 3): its anchors are text the core config creates.
Against a HEAD tree with the core config's `code_edit`s applied to the four files it shares, it is
**APPROVED — all find patterns exist**, and every anchor matches exactly once (8/8 anchors, count
1 each, including the regenerated `CHANGELOG.md` one). The suite/gate sweep on top of the addendum
is **revision-2 evidence and was not re-run** — and its "34 failed (== baseline), identical set"
line is invalid for the M1 reason above; it must be re-measured in a `git worktree` before the
addendum is considered proven.
One bug in the addendum was caught by executing it: a `_PreToolUse_note` comment key placed
*inside* the `hooks` object crashed everything iterating that map (Claude Code reads every key
there as an event name). Removed; the explanation lives in `dispatch-registry.json` and
`docs/HOOKS.md` instead, and the core test now skips non-list values defensively.

**Round 4 narrowed the objection to exactly one Critical — and re-ran the addendum sweep that
revision 4 declined to run.** **Re-measured by round-4 review**, with the addendum applied on top of
the core config: `1 failed / 1871 passed`, an **identical failure set** to baseline; **8/8 gates
green**; `settings.json` valid; registrations **26 -> 16** and `PreToolUse` **11 -> 1**; live wired
probes benign -> `0`, malformed -> `2`, `--no-verify` -> `2`. That is the reviewer's measurement,
recorded as theirs — this plan did not run it, and the revision-2 sweep it replaces remains invalid
for the M1 reason above.

**Round 5's measured evidence, recorded as the reviewer's, not as this plan's.** All of it
**re-measured by round-5 review** in a real `git worktree` with the configs applied:

- the **14-value** tier evasion matrix, with set equality between what the resolver accepts and
  what the clamp disarms **holding**; the `or`-form mutant fails **exactly the 4 predicted ids**;
- **22/22** escape probes return `0` or `2` — nothing else escapes the hook boundary;
- spill: file **`0o600`** and directory **`0o700`** under umask `0022` / `0077` / `0000`; the
  failure path leaves **no leftovers**; `os.replace` is atomic;
- suite: baseline **9 failed / 1758 passed** vs core **8 failed / 1881 passed** vs core+addendum
  **8 failed / 1881 passed** — core's failure set a **strict subset** of baseline's, **zero new
  failures**, **+123 passing**;
- **7/7** non-pytest gates pass on core and on core+addendum;
- registrations **26 -> 16**, `PreToolUse` **11 -> 1**; `minimal` still short-circuits with `rc 0`.

**Caveat, not laundered:** the reviewer's 8-9 shared failures are **environmental** — their sandbox
lacked the editable install (`ModuleNotFoundError: No module named 'claudekit'`) — and are present
**identically at baseline**. Only the **set comparison** between baseline and applied is meaningful
there; the absolute failure counts are not this repo's green-suite figures and are not restated as
such. Note also that these counts differ from the rev-4 figures (`1 failed / 1871 passed`) because
they were taken in a different environment; neither supersedes the other as a suite baseline.

**The reviewer's stated sequence, and this plan does not get to reorder it:**

1. Land the **resolver fix** (C1-R4) and the **`""` / `null` mutants**.
2. Re-run `tests/test_dispatch_merge.py` **and the eight gates**.
3. **Only then** run the addendum.

That re-review has now happened: **round 5 = APPROVED 92.9/100, zero blocking findings**, and the
addendum is **recommended safe to run** under the two conditions in open decision 0. It still stays
in `.claude/plans/pending/` until the **owner** lifts the suspension and open decision 2 is acked.

**Not applied. Nothing has run against the repository.** The core config is queued and validates
`APPROVED` against HEAD; the addendum validates `APPROVED` against HEAD+core (**8/8** anchors at
count 1) and `REJECTED — 5 patterns not found` against HEAD alone, by design, and is
**APPROVED-WITH-TWO-CONDITIONS** in `pending/`. All
revision-4 execution happened in throwaway `git worktree` trees at `5f3e322` outside the session
scratchpad, which were used for measurement only and are not part of the deliverable.

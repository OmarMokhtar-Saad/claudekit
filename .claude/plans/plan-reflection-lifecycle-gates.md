# Implementation Plan: Reflection Lifecycle Gates (G3 / G4 / G7)

**Workstream:** 2 of 6 (`perf/token-efficiency`)
**Ops config:** `.claude/plans/plan-reflection-lifecycle-gates.ops.json` (6 operations, validator **APPROVED**, dry-run clean)
**Revision 3** — round 2 (88/100) fixed MAJOR 1 sanitizer entropy guard, MAJOR 2 honest framing (hard rule 6), MAJOR 3 receipt-inbox decoupling. Round 3 (87/100) found that **the MAJOR-3 fix itself opened a worse hole** — a symlinked inbox laundered the allowance into an arbitrary source write that cleared BOTH this gate and `ops-enforcement.sh`, breaching hard rule 1. Revision 3 closes it with three independent controls plus four bound tests, and lands three further MINORs.

> **Process lesson recorded (this pattern has now occurred twice across two workstreams):**
> a fix for a real finding introduced a worse hole than the original. Round 1's escape
> hatch was merely awkward; round 2's was *exploitable*. **Rule for the rest of this
> effort: when a fix adds an exception to a blocking gate, the exception IS the new attack
> surface — attack it yourself, with a constructed working bypass, before reporting.**
> `is_receipt_inbox_write()` now carries an in-code banner saying exactly that.
**Complexity:** Complex · **Risk:** Medium-High (security/architecture surface) · **Tier:** 3

---

## Overview

Give the kit a durable, privacy-safe memory of *failure*, and make the lifecycle events
that are currently decorative actually enforce a duty. One new stdlib-only library
(`reflection.py`) plus one hook entrypoint (`reflection-gate.py`) close three gaps:
`Stop`/`SubagentStop` can now interrupt a turn that owes something (G3), a tool failure
now leaves fingerprinted state so a loop is *detectable by machine* rather than by
self-advice (G4), and unmet duties now survive `/compact` (G7).

## Scope

**In scope**
- `.claude/hooks/reflection.py` — external append-only JSONL ledger, low-cardinality
  failure fingerprint, sanitizer, per-session HMAC token, receipt validation, the
  checkpoint reduction, and a CLI (`trigger` / `receipt` / `non-attempt` / `status`).
- `.claude/hooks/reflection-gate.py` — one hook entrypoint dispatching on
  `hook_event_name` (with an authoritative `--event <Name>` argv fallback).
- `.claude/settings.json` — register the gate on `PreToolUse`, `PostToolUse`,
  `SessionStart`, `PreCompact`; replace the decorative `Stop` (first entry),
  `SubagentStop`, and `PostToolUseFailure` entries.
- `.gitignore` — defensive rule for an in-tree ledger.
- `tests/test_reflection_ledger.py`, `tests/test_reflection_gate.py` — 61 behavioral tests.

**Out of scope (owned by other workstreams — see Risks)**
- `knowledge-ledger.py`, `execute-json-ops.py`, `review-record.py`
- any agent `.md`, any skill, `CLAUDE.md`, `CHANGELOG.md`, `docs/`, `.ai/`
- `loop-operator` agent wiring; installer/`ck doctor` awareness of `.py` hooks

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (repo runs its
  own hooks on itself; see CLAUDE.md "Session setup gotcha").
- Nothing else. Python stdlib only, no new dependencies (hard rule 8).

---

## Architecture

```
tool fails ──► PostToolUseFailure ──► reflection.record_failure()
                                        │  sanitize → 6 low-cardinality fields
                                        │  sha256 → fingerprint
                                        ▼
                       $TMPDIR/claudekit-reflection/<sha256(session)[:32]>.jsonl
                       (EXTERNAL to repo AND to transcript → survives /compact)
                                        │
                          pending_checkpoint() = pure reduction
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
   PreToolUse gate              PreCompact carry-over            Stop / SubagentStop
   block mutation +             persist duty text; never         block ONCE on an unmet
   unchanged reruns             blocks compaction                duty; honour
   (exit 2 + stderr)            (replayed at SessionStart)       stop_hook_active
        │
        └── ALWAYS ALLOWED: Read/Grep/Glob/Task, non-mutating Bash, planning,
            and `reflection.py receipt|trigger|non-attempt` (the way out)
                                        │
                                        ▼
                     receipt: HMAC(session_token) + checkpointDigest
                     → clears ONLY the exact active set it owes
```

### Load-bearing design decisions

| Decision | Why it must stay |
|---|---|
| Fingerprint = sha256 over **six bounded fields** (phase, target, failureClass, platform, invariant, head) | Low cardinality is what makes "you already tried this" *collide*. Hashing raw error text would make every failure unique and the counter useless. |
| Every field through `bounded_token()`; path/secret-shaped values → `digest-<sha256[:16]>` | Privacy requirement, not a nicety: the ledger outlives the transcript and lives on a possibly shared host. Free-text receipt fields go through `_safe_text()`, which **rejects** rather than digests — a human sentence has no business containing a host path or a token. |
| `looks_like_credential()` shape/entropy guard **in addition to** the keyword list (MAJOR 1) | A keyword list is not a control. A bare 40-char hex token, an opaque key with no vendor prefix, or a JWT with no adjacent keyword matches no keyword and no path rule, and would fall through `re.sub(r"[^a-z0-9_.:-]+", "-", raw)` **verbatim** into a file that outlives the transcript and sits outside the repo. That is the one genuinely durable leak path. Guard: digest any ≥20-char run that is all-hex, or is base64url with mixed case + a digit and ≥3.5 bits/char Shannon entropy, or matches `\beyJ[A-Za-z0-9_-]{10,}`. Runs on the **raw** value before casefolding (casefolding destroys the case mix that identifies base64url secrets). Internal shapes (`command-<sha>`, `digest-<sha>`) are allowlisted so the ledger stays readable. |
| Ledger is **external** (OS temp dir), append-only JSONL, keyed by `sha256(session_id)` | Survives compaction and context loss; can never be committed; is never slurped back into context. |
| Session token: `secrets.token_urlsafe(24)`, `O_EXCL`, mode `0o600` | `O_EXCL` makes creation race-safe; `0o600` keeps it off a shared host's *other accounts*. It does **not** keep it from the agent — see the row below. |
| Receipt = HMAC over the entry **plus** `checkpointDigest` of the exact active set — **an integrity speed bump, not an adversarial control** (MAJOR 2, hard rule 6) | What this defeats: *accidental and lazy* discharge. A hand-written plausible receipt appended to the ledger clears nothing, and a valid receipt replayed against a newer active set clears nothing either — you must discharge the checkpoint you actually owe. What it does **not** defeat: an adversarial model. The agent holds Bash and Read and runs under the **same uid** as the `0o600` token, so it can read `token_path` and mint a valid HMAC over any receipt it likes. The honest claim is the same shape as CLAUDE.md's "denylist speed bump, not a sandbox": clearing a checkpoint requires a deliberate, auditable act naming the exact duty owed. The implementation is unchanged — only the claim is. |
| The inbox allowance is defended by **three independent controls** (round-3 MAJOR) | The round-2 version compared `os.path.realpath()` on **both** sides, resolving symlinks on both. Constructed working bypass: `ln -s ../../src/claudekit/x.py .claude/reflection/inbox-<key>.json` (`ln` was not in `_MUTATING_SHELL`, so the gate permitted it), then `Write` that path — realpaths compared equal, the gate allowed, and `ops-enforcement.sh:47` allowed too because the `file_path` it saw was under `.claude/`. Arbitrary content in a source file having cleared **both** guards: a straight breach of hard rule 1. Controls, none droppable: **(1)** refuse if `os.path.islink()` on the candidate **or** the expected path — never follow, never resolve; **(2)** realpath the **parent only** and compare `realpath(parent) + basename` — realpathing the full path is exactly what launders the link; **(3)** `\bln\b` added to `_MUTATING_SHELL`, so step one of the bypass is itself blocked. Scope narrowed from `MUTATING_TOOLS` to `{"Write"}` only. The function is side-effect free — it no longer `mkdir`s the inbox directory (the receipt CLI owns that), so a blocking gate touches nothing on the deny path. |
| Receipt payload travels through a **write-once inbox**, not a shell command line (MAJOR 3) | Two hooks previously fought over the only escape hatch. `is_receipt_cli()` refuses `< > \| & ; $(` (so no heredoc) and writing a payload file needed Write, which the pending gate blocked — leaving the command line as the sole channel. That string is then scanned by `command-guard.sh:74` → `command_validator.py:58-60`, which denies on the literal substrings `subprocess.run`/`Popen`/`call`, `os.system(`, `__import__(`. A receipt whose `failedAssumption` legitimately names one of those — entirely plausible in a Python debugging session, which is exactly when a checkpoint fires — got refused by an unrelated hook while the checkpoint stayed pending. Fix: `reflection.py receipt --inbox` reads `.claude/reflection/inbox-<session-key>.json`, and the gate allows a Write to **that one exact resolved path** for **that one session**. The argv then carries flags only, never prose. `--json-stdin` is also available. The inbox is consumed on success so a stale payload can never be replayed. This removes the coupling rather than documenting it. |
| `non-attempt` disposition (setup-error / syntax-error / capability-probe) | A broken harness must not burn the failure counter and manufacture a checkpoint out of noise. |
| While pending: diagnosis / planning / receipt creation stay **available** | A gate that blocks the way out gets uninstalled within a day. Only implementation mutation and unchanged reruns are paused — the two actions that *cannot* be correct before the reflection happens. |
| Stop `stop_hook_active` honoured | One forced pause, never a trap. Interrupt-once, not block-forever. |
| Blocks are `exit 2` + **stderr** everywhere | Project hard rule 2. Never exit 1, never stdout-as-decision. |

### Decisions taken from evidence (documented so review can contest them)

1. **Python hooks, not shell.** The state being reduced (JSONL, HMAC, sha256 sanitizer)
   is not safely expressible in bash 3.2. Side benefit measured, not assumed:
   `scripts/gen-docs.py:55` counts hooks as `.claude/hooks/*.sh`, so two `.py` hooks add
   **zero** docs-drift and `tests/test_shell_lint.py` (which globs `*.sh`) is unaffected.
   The documented "19 hooks" count therefore stays truthful for shell hooks — see Risks
   for the follow-up.
2. **Which duties block at Stop.** Evidence: the old `Stop` entry checked two things —
   uncommitted work and ops.json validity — and blocked on **neither** (`exit 0`).
   - *Blocking:* unmet reflection checkpoint; unrouted learning loop.
   - *Warning only:* uncommitted changes, invalid ops.json (both preserved verbatim
     from the entry being replaced, now on stderr **and** hooks.log).
   Rationale: stopping mid-change is normal and legitimate. Blocking on a dirty tree
   would train the operator to hit the second attempt reflexively, hollowing out the
   duties that *do* block. Both advisory checks are covered by tests.
3. **`ECC_HOOK_PROFILE=minimal` suppresses blocking only, not recording.** Every other
   hook short-circuits wholesale at line 1. This one keeps recording so a developer who
   flips profiles mid-session does not end up with a ledger full of holes that later
   mis-reduce (a missing failure silently lowers the active count below the threshold).
   Deliberate divergence, flagged in the hook header under a
   `***DELIBERATE DIVERGENCE - DO NOT "FIX" THIS BACK***` banner naming the two tests
   (`test_minimal_profile_suppresses_blocking`, `test_minimal_profile_still_records`)
   that will tell the next maintainer why, and covered by both.
4. **Fail-closed asymmetry.** `PreToolUse` with an unparsable payload → **block** (it is
   the only surface where a garbled payload could smuggle a mutation past the gate, and
   it matches `ops-enforcement.sh`). `Stop` with an unparsable payload → **allow**, logged:
   with no parsable session id no duty is *provable*, and an unjustifiable block strands
   the turn. The event name comes from `--event <Name>` in settings.json, so the
   fail-closed decision never depends on grepping a malformed blob.

---

## Implementation Steps

### Phase 1 — The ledger library

**Step 1. Create `.claude/hooks/reflection.py`** (op 1, `file_create`)
Public surface: `ledger_path` / `token_path` / `carryover_path`, `append_entry`,
`entries`, `ensure_session_token` / `read_session_token`, `bounded_token`,
`fingerprint_fields` / `compute_fingerprint`, `record_session_start`, `record_failure`,
`record_trigger`, `mark_non_attempt`, `record_activity`, `checkpoint_digest`,
`receipt_clears`, `active_entries`, `pending_checkpoint`, `learning_loop_pending`,
`record_receipt`, `duty_summary`, `receipt_instructions`, `main`.

- Enums: `TRIGGERS` (incl. the derived-only `learning-loop`, which `record_trigger`
  refuses so it cannot be forged), `DISPOSITIONS` (incl. `nothing-durable` as a **valid**
  result), `NON_ATTEMPT_REASONS`.
- Reduction: `pending_checkpoint` → explicit trigger wins and is `deep`; else ≥2 active
  failures → `deep`/`repeated-fingerprint` when all fingerprints are identical, else
  `task`/`second-failure`.
- Required receipt fields enforced: `trigger`, `failureFingerprints`, `failedAssumption`,
  `approachesCompared` (≥2), `chosenExperiment`, `proofCommandOrCheck`, `proofOutcome`
  (rejects `pending`/`unknown`/`not run`/`tbd`/`n/a`), `durableDisposition`.
  Unknown fields are rejected outright.
- Ledger location override: `CLAUDEKIT_REFLECTION_DIR` (absolute paths only) — tests and
  projects that want an explicit location.
- Python 3.9: `typing.Optional/List/Dict/Tuple`, `datetime.now(timezone.utc)`.
  **No** `datetime.UTC`, **no** PEP-604 unions (the reference uses both).
- **Verification:** `python3 .claude/hooks/reflection.py status --session-id x` exits 0
  and prints `{"checkpoint":null,"duties":[]}`.

### Phase 2 — The hook entrypoint and ignore rule

**Step 2. Create `.claude/hooks/reflection-gate.py`** (op 2, `file_create`)
Dispatch table:

| Event | Behaviour | Exit |
|---|---|---|
| `SessionStart` | mint/read token, emit it + replay & consume carry-over on **stdout** (SessionStart stdout is injected into context) | 0 |
| `PostToolUseFailure` | `record_failure()`; announce a newly-raised checkpoint on stdout | 0 |
| `PostToolUse` | `record_activity("mutation-or-delivery")` on a mutating tool/command | 0 |
| `PreToolUse` | block mutation or unchanged rerun while a checkpoint is pending | **2** + stderr |
| `PreCompact` | persist duty text to `<key>.carryover`, log, **never** block | 0 |
| `Stop` / `SubagentStop` | advisory warnings, then block once on an unmet duty | **2** + stderr |

- Mutation set: `Write|Edit|MultiEdit|NotebookEdit|apply_patch|write_file|
  str_replace_based_edit_tool`, plus shell `rm|mv|cp|touch|truncate|install|sed -i|tee`,
  `git add|commit|push|merge|rebase|reset|revert|checkout|switch|clean|stash`, and
  `execute-json-ops.py`. `validate-config-json.py` is deliberately **not** mutation —
  planning is the way out.
- Escape hatch `is_receipt_cli()` resolves the script token to an **absolute path** and
  compares it to this file's sibling `reflection.py`, and refuses any command containing
  `; & | > < ` $(` — so it is not reachable by naming an unrelated file `reflection.py`
  or by appending a second command.
- Escape hatch `is_receipt_inbox_write()` allows a **`Write` only** (not `Edit`/
  `MultiEdit`/`NotebookEdit`/`apply_patch`/`write_file`/`str_replace_based_edit_tool`) to
  **one exact path per session** — symlinks refused on both sides, parent-only realpath,
  exact basename match, no filesystem side effects. A sibling file in the same directory,
  another session's inbox, a symlinked inbox, a symlinked parent, and every non-`Write`
  tool are all blocked, each by a bound test.
- `--json-stdin` exists for direct/programmatic use only and is **deliberately not** part
  of the agent-facing route: `is_receipt_cli()` refuses `<`, so a heredoc never parses and
  no other stdin channel exists for a gated Bash call. `receipt_instructions()` teaches
  the inbox route exclusively; the flag's `--help` text states the limitation.
- `CLAUDEKIT_HOOK_LOG` overrides the log destination so tests never append to the
  developer's real `hooks.log`.
- **Verification:** `echo '{}' | python3 .claude/hooks/reflection-gate.py --event Stop`
  exits 0; the same with `--event PreToolUse` and a malformed body exits 2.

**Step 3. Add the defensive ignore rule to `.gitignore`** (op 3, `code_edit`)
Inserted after the `.claude/locks/` block: `.claude/reflection/`, with a comment stating
the ledger normally lives outside the repo entirely.

### Phase 3 — Wiring

**Step 4. Edit `.claude/settings.json`** (op 4, `code_edit`, 7 edits — simulated and
verified to produce parseable JSON with the expected shape)

| # | Edit | Result |
|---|---|---|
| 1 | `add_after "PreToolUse": [` | new first entry, matcher `""` |
| 2 | `add_after "PostToolUse": [` | new first entry, matcher `""` |
| 3 | `add_after "SessionStart": [` | new first entry (existing `session-start.sh` untouched) |
| 4 | `add_before "Stop": [` | brand-new `PreCompact` section |
| 5 | `replace` the decorative Stop command line | the blocking gate |
| 6 | `replace` the `SubagentStop` echo line | the blocking gate |
| 7 | `replace` the `PostToolUseFailure` log line | the recorder |

Every command uses the repo's existing ROOT idiom:
`bash -c 'ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"; python3 "$ROOT/.claude/hooks/reflection-gate.py" --event <Name>'`

Post-edit counts (verified by simulation): PreToolUse 10, PostToolUse 4, SessionStart 2,
PreCompact 1, Stop 4, SubagentStop 1, PostToolUseFailure 1. **The three backgrounded
cosmetic Stop hooks (`cost-tracker.sh`, `desktop-notify.sh`, `format-typecheck.sh`) are
untouched and keep working.**

### Phase 4 — Tests

**Step 5. Create `tests/test_reflection_ledger.py`** (op 5) — 42 property tests.
**Step 6. Create `tests/test_reflection_gate.py`** (op 6) — 37 behavioral tests, each
running the real hook as a subprocess with real JSON on stdin.

---

## Testing Strategy

All 79 tests were written and **executed green against the exact file contents in
ops.json** in an isolated mirror tree (`79 passed`); `ruff check --select E,F,W,I
--line-length 100 --target-version py39` passes on both hooks and both test files.

Explicitly required properties, each with a named test:

| Property | Test |
|---|---|
| Absolute path never reaches the ledger | `test_absolute_path_never_reaches_the_ledger` |
| **Keyword-free high-entropy token never reaches the ledger** (BOUND: deleting the guard fails it — verified by deleting it) | `test_bare_high_entropy_token_never_reaches_the_ledger` (parametrized: bare hex, base64url, JWT) |
| Guard is not over-eager (ledger stays readable) | `test_ordinary_prose_and_identifiers_are_not_digested`, `test_internally_produced_digests_are_not_re_digested` |
| Receipt inbox keeps free text out of argv | `test_receipt_via_inbox_keeps_free_text_out_of_the_command_line`, `test_receipt_via_json_stdin_clears_the_checkpoint` |
| Inbox allowance is one exact path, not a directory (BOUND) | `test_the_inbox_allowance_is_one_exact_path_not_a_directory`, `test_another_sessions_inbox_is_blocked` |
| **Symlinked inbox cannot launder a source write** (BOUND — Iron Law) | `test_a_symlinked_inbox_cannot_launder_a_source_write` (asserts exit 2 **and** that the victim file is byte-identical) |
| Symlinked parent directory blocked (BOUND) | `test_a_path_whose_parent_is_symlinked_to_the_inbox_dir_is_blocked` |
| Creating the symlink is itself blocked (BOUND) | `test_creating_the_symlink_is_itself_blocked` |
| Allowance admits `Write` only (BOUND) | `test_the_inbox_allowance_admits_write_only` (6 other tools) |
| Gate has no filesystem side effects on the deny path | `test_the_gate_creates_no_directories_even_when_it_denies` |
| Single-case ≥32-char secret is digested | `test_bare_high_entropy_token_never_reaches_the_ledger[BARE_SINGLECASE]` |
| Inbox write does not arm the duty it discharges | `test_inbox_write_does_not_arm_the_learning_loop_duty` |
| `minimal` profile still records | `test_minimal_profile_still_records` |
| Secret-shaped string never reaches the ledger | `test_secret_shaped_string_never_reaches_the_ledger` |
| Same via the **hook** path, not just the library | `test_hook_path_does_not_leak_absolute_paths_or_secrets` |
| Free text rejects rather than digests | `test_free_text_receipt_fields_reject_rather_than_digest` |
| Ledger is outside the repo | `test_ledger_lives_outside_the_repository` |
| Token is `0o600` | `test_session_token_is_owner_only` |
| **Forged receipt does not clear** | `test_forged_receipt_line_does_not_clear_the_checkpoint` |
| **Stale/replayed valid receipt does not clear** | `test_receipt_bound_to_a_stale_active_set_does_not_clear` |
| Wrong session token refused | `test_wrong_session_token_is_refused` |
| **Interrupt-once (`stop_hook_active`)** | `test_interrupt_once_stop_hook_active_is_honoured` |
| Checkpoint reduction (0/1/2-distinct/2-identical/explicit) | 5 tests in `TestCheckpointReduction` |
| `non_attempt` does not burn the counter | `test_non_attempt_does_not_burn_the_counter` |
| Diagnosis/planning stay available | `test_read_only_diagnosis_stays_available`, `test_plan_writing_stays_available` |
| Receipt CLI never blocked, and cannot be forged | `test_receipt_cli_is_never_blocked`, `..._cannot_be_forged_by_a_compound_command` |
| PreToolUse fails closed on bad JSON | `test_unparsable_pretooluse_payload_fails_closed` |
| Stop fails open on bad JSON | `test_unparsable_stop_payload_fails_open` |
| `ECC_HOOK_PROFILE=minimal` forced explicitly | `test_minimal_profile_suppresses_blocking`, `..._the_stop_block` |
| Duty survives compaction | `TestPreCompact` (5 tests) |
| Uncommitted work warns, never blocks | `test_uncommitted_work_warns_but_never_blocks` |

Hermetic by construction: every test redirects `CLAUDEKIT_REFLECTION_DIR`,
`CLAUDEKIT_HOOK_LOG` and `CLAUDE_PROJECT_DIR` into `tmp_path`, and forces
`ECC_HOOK_PROFILE` explicitly. No test touches real session state.

**Post-execution DoD commands:** `python3 -m pytest tests/ -q` ·
`ruff check src/ tests/ scripts/` · `mypy` · `python3 scripts/gen-docs.py --check` ·
`python3 scripts/gen-registry.py --check` · `shellcheck install.sh .claude/hooks/*.sh` ·
`ck doctor --strict`.

## Rollback Plan

1. The executor backs up both `code_edit` targets (`.gitignore`, `.claude/settings.json`)
   under `backups/<timestamp>/`; `python3 .claude/operations/scripts/restore-backup.py`
   restores them. The four `file_create` targets are new files and are removed by
   transaction rollback.
2. Manual: `git checkout -- .claude/settings.json .gitignore` and
   `rm .claude/hooks/reflection.py .claude/hooks/reflection-gate.py
   tests/test_reflection_ledger.py tests/test_reflection_gate.py`.
3. **Disable without reverting:** `ECC_HOOK_PROFILE=minimal` in
   `.claude/settings.local.json` suppresses every block while leaving recording intact.
4. No migration, no schema, no state to clean: the ledger lives in the OS temp dir and
   is disposable.

## Risk Assessment

**High**
- *A blocking `Stop` is the single highest-blast-radius change in the kit.* Mitigations:
  `stop_hook_active` interrupt-once (tested), `minimal`-profile kill switch (tested),
  fail-open on unparsable Stop payloads (tested), and only two duties block.
- *The learning-loop duty fires after ANY mutation*, so most working sessions will hit
  one interruption at Stop until a receipt is written. This is the intended behaviour
  (that is the gap), but it is the item most likely to need tuning after a week of use.
  Tunable without a code change by not registering the `PostToolUse` entry.

**Medium**
- *`PostToolUseFailure` is a non-standard event name.* It is already registered in this
  repo's `settings.json`, so the recorder inherits exactly the existing delivery
  behaviour — no worse than today. `PostToolUse` with a failed `tool_response` is a
  possible future fallback; deliberately not added to keep the diff honest.
- *Python hooks are new to this repo* (all 19 existing hooks are shell). `install.sh`,
  `ck doctor --strict` and `scripts/gen-docs.py:55` all glob `*.sh`. Confirmed
  side-effect-free for the drift gates; **but** `install.sh` copies `.claude/` wholesale,
  so distribution is fine while *inventory* under-reports. See Dependencies.
- *Escape-hatch surface.* There are now two allow-paths through a blocking gate:
  `is_receipt_cli()` (absolute-path resolution, metacharacter refusal, subcommand
  allowlist) and `is_receipt_inbox_write()` (one exact resolved path per session). Both
  are narrowed deliberately and both narrowings are bound by tests. Framing per hard
  rule 6: these are speed bumps against accidental and lazy discharge — an agent holding
  Bash and Read under the same uid as the token can always mint a valid receipt, so do
  not describe the gate as unforgeable.

**Low**
- Ledger unwritable (read-only `TMPDIR`): every write returns `False` and the hook
  degrades to no-op rather than crashing a tool call.
- Ledger growth: one JSONL line per failure per session in the OS temp dir; the OS
  reclaims it.

## Cross-Workstream Dependencies (NOT mine to edit — raise with the owners)

1. **`knowledge-ledger.py` — recommend YES, move the `record` gate.** Evidence:
   `knowledge-ledger.py:271` refuses to write unless `--verified` asserts a Verifier PASS,
   while `CLAUDE.md` (Token & Model Policy) states *"the verifier agent NEVER auto-runs"*.
   In the common path nothing ever calls `record` and the learning store stays empty by
   construction. Recommendation for that workstream's owner: replace the Verifier-PASS
   assertion with the Stop learning-loop duty — accept a `record` when a reflection
   receipt with `durableDisposition == "knowledge-recorded"` exists for the session, and
   let `nothing-durable` be the explicit alternative. `reflection.learning_loop_pending()`
   and `reflection.entries()` are the public helpers to call. **No edit to
   `knowledge-ledger.py` is included in this plan.**
2. **Docs/CHANGELOG (docs/, `CLAUDE.md`, `CHANGELOG.md` owners):** the component
   inventory says "19 hooks", counted as `.claude/hooks/*.sh`. Two `.py` hooks now exist
   and are not counted, which moves "19 hooks" from stale to **wrong**. Two acceptable
   resolutions, both applied **via the generator, never by hand** (hard rule 8):
   (a) extend `scripts/gen-docs.py:55-58` to glob `*.sh` **and** `*.py` and let the gate
   bump the count; or (b) qualify the scope as **"19 shell hooks"** in the generator's
   template. Recommendation: (a), with (b) as the minimum honest interim. The reviewer
   owns this at integration; it is raised here, not hidden.
3. **Agent prompts (agent `.md` owners):** the `loop-operator` agent and the
   `systematic-debugging` / `continuous-learning` skills should learn that
   `python3 .claude/hooks/reflection.py status|receipt|trigger|non-attempt` exists and is
   the sanctioned way out of a checkpoint. Without that, agents will discover it from the
   stderr block text (which does print the exact command) rather than from their prompt.
4. **`install.sh` / `ck doctor` owner:** confirm `.py` files under `.claude/hooks/` are
   copied and health-checked; verified as copied (wholesale `.claude/` copy), not
   verified as *checked*.

---

## Verification Evidence

```
$ python3 .claude/operations/scripts/validate-config-json.py \
    .claude/plans/plan-reflection-lifecycle-gates.ops.json
  JSON syntax valid / All required fields present / All file paths valid
  All find patterns exist in files
-> APPROVED

$ python3 .claude/operations/scripts/execute-json-ops.py <ops.json> --dry-run
DRY RUN COMPLETE  Operations: 6 total  (file_create: 4, code_edit: 2, run_command: 0)
status: success

$ python3 -m pytest tests/ -q      # isolated mirror tree, exact ops.json contents
79 passed

$ # Round-2 MAJOR-1 bound proof: neutralise looks_like_credential()
$ python3 -m pytest tests/test_reflection_ledger.py -k bare_high_entropy -q
4 failed                          # guard restored -> 79 passed

$ # Round-3 MAJOR bound proofs, one control neutralised at a time:
$ #   islink refusal -> False
1 failed  test_a_symlinked_inbox_cannot_launder_a_source_write
$ #   islink -> False AND parent-realpath reverted to full-path realpath (the round-2 bug)
1 failed  test_a_symlinked_inbox_cannot_launder_a_source_write   # exploit reproduces
$ #   `ln` removed from _MUTATING_SHELL
1 failed  test_creating_the_symlink_is_itself_blocked
$ #   scope widened back to MUTATING_TOOLS
1 failed  test_the_inbox_allowance_admits_write_only
$ # all controls restored -> 79 passed, ruff clean

$ ruff check --select E,F,W,I --line-length 100 --target-version py39 <all 4 files>
All checks passed!

$ python3 -c 'json.loads(<simulated settings.json>)'   # 7 edits applied in order
JSON OK; PreToolUse 10, PostToolUse 4, SessionStart 2, PreCompact 1,
Stop 4 (3 cosmetic backgrounded hooks intact), SubagentStop 1, PostToolUseFailure 1
```

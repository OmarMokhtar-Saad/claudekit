# Plan: Ops-Engine Hardening + Implementer Reactive-Read Contract

**Status:** REVISION 6 — after reviews #1 (81), #2 (87), #3 (89), #4 (91), #5 (90), all
CONDITIONAL; awaiting re-review
**Ops config:** `.claude/plans/ops-hardening-implementer-contract.json`
(12 operations · 72 `code_edit` edits · 1 `file_create` — validated, dry-run clean, and
**applied to throwaway copies with all 15 new tests passing**, §10)
**Date:** 2026-07-30
**Owner approval required:** yes (Golden Rule; changes a managed agent contract + engine semantics)

---

## 1. Context & Problem

A downstream session measured ~50k tokens per implementer run, ~65k of which was the agent
reading ops.json + target source files upfront to "verify anchors" — work the engine is
supposed to enforce. Auditing that claim against this master repo found the safety story is
weaker than assumed. Review #1 then found a fifth, worse defect. All five are reproduced
below; **gap 0 is a live data-loss bug in the shipped engine, independent of this plan.**

| # | Gap | Evidence (pre-change) |
|---|-----|----------|
| **0** | **Rollback restores mutated content; backups are clobbered** | `execute_code_edit` re-copies the target over its backup on *every* operation (`execute-json-ops.py:374-385`). Two ops on one file → op 2's backup captures op 1's mutation → `txn.rollback()` restores the intermediate. **Reproduced**, §10. |
| 1 | Implementer spec skips the mandatory validator | `.claude/commands/implement.md:34-38` mandates `validate-config-json.py`; `.claude/agents/implementer.md` workflow starts at dry-run — the pipeline's only uniqueness guard is optional in the agent's own contract |
| 2 | Executor is fail-soft on anchors at apply time | `:406-408` skip-and-continue on missing pattern; `:424-434` `str.replace(find, r, 1)` silently edits the **first** occurrence of an ambiguous anchor — no count check |
| 3 | Validator checks pristine state, not cumulative | `validate-config-json.py:159-210` `_validate_edits` receives static `file_content`; an edit that makes a later edit's anchor ambiguous (or creates it) is mis-validated |
| 4 | Dry-run diverges from real execution for multiple ops on one file | each `code_edit` re-reads from disk (`:388`); dry-run writes nothing, so op N's preview sees pristine content while real execution sees op N−1's mutations |

Consequence: the "reactive reads" token optimization is *directionally* right, but adopting
it without hardening the engine would remove the one redundant layer papering over gaps 0–4.
This plan does both, engine first.

## 2. Approach mapping

- **Approach B — engine hardening** → Phase 1 (ops 1–3). Makes upfront reads *genuinely*
  redundant.
- **Approach A — spec fix** → Phase 2 (ops 4–9), including the Codex mirror corpus.
- **Approach C — evidence contract** → folded into both: the executor emits the evidence
  (diff + `RESULT-JSON`), the implementer relays it. This is what makes C viable at all —
  the headless implementer's tool grant is `Bash(python3 .claude/operations/scripts/*)`
  only (`_shared/INVOCATION.md:75`), so it could never run `git diff` itself.

## 3. Phase 1 — Engine hardening (ops 1–3)

### Op 1: `execute-json-ops.py` (32 edits)

1. **First-write-wins backups** (fixes gap 0, CRITICAL). Both `execute_code_edit` and
   `execute_file_delete` skip the copy when the file was already captured **this run**,
   preserving pre-run content. Membership lives in a run-scoped `backed_up` set threaded
   from `_execute_operations` — *not* a `backup_path.exists()` probe, which review #2
   showed would collide with the engine's own `manifest.json` and silently leave a
   project-root `manifest.json` unbacked. That name is now refused outright
   (`manifest-name-collision`) rather than corrupting the file `restore-backup.py:60`
   depends on — and refused in **both** modes in both executors, so dry-run can never report
   a plan clean that execution would then reject. Comments explain both, so neither is
   "optimized" back.
2. **Crash and signal safety** (gap 5, from review #2). `_execute_operations` gains
   `except Exception: ...; _emit_result(status='crashed'); raise`, so an unexpected error can
   no longer leave partial writes on disk unreported, and `_signal_handler` emits
   `status='interrupted'` (with the backup dir) after its rollback.
   Rollback after the batch commits is prevented on **both** paths, which took two reviews
   to get right:
   - *Exception path*: the `except Exception` handler guards its rollback with a
     `loop_completed` flag (review #4) — without it, a `BrokenPipeError` from the summary
     `print` under `… | head` would revert a fully successful run.
   - *Signal path*: `_active_txn` is retired **immediately after the loop, before the summary
     prints** (review #5). `_signal_handler` rolls back whatever `_active_txn` points at and
     is module-level, so it cannot see `loop_completed`; without the early clear, a SIGINT
     during the summary would revert a finished run — and `_result_emitted` would then
     suppress the `interrupted` verdict, leaving a success payload over a reverted tree.
   Both are proven by fault injection and pinned by tests, §10.
3. **Fail-closed edit loop** (gap 2) — missing anchor → abort `pattern-not-found`;
   ambiguous (`count > 1` against *current mutated content*) → `ambiguous-pattern`; empty
   `find` → `missing-find-pattern`; no action key → `no-action-specified`. Aborts happen
   **before** any write; `_execute_operations` rolls the batch back on op failure
   (`:585-591`). Dead partial-edit paths removed; `logger` repurposed to record abort
   reasons (so it does not become unused).
4. **Dry-run state threading** (gap 4) — `sim_state: Dict[str, Optional[str]]` per run,
   passed to all three executors. `code_edit` reads/writes it, `file_create` seeds it,
   `file_delete` marks `None`. Every access is gated on `dry_run`, so real execution is
   byte-identical to today.
5. **Evidence emission** — `show_diff` now also prints after a real write; a new
   `_emit_result()` helper prints `RESULT-JSON: {...}` on config errors, normalize failure,
   lock contention, manifest failure, operation failure, crashes and signals. Absence means
   the process **never reached a reported exit path** — killed outright (SIGKILL/OOM), or
   failed before execution began (bad CLI args). All seven artifacts (module docstring,
   `_emit_result` docstring, `implementer.md`, both `execute-operations-config` SKILL.md
   copies, the Codex toml, the CHANGELOG, and `docs/ARCHITECTURE.md`) describe emission
   consistently — reviews #3/#4/#5 caught four of them over-claiming "every exit path" or
   defining the guarantee circularly. The Codex toml states only the negative case (what an
   absent line means), which is the part its reader acts on.
   Emission is **idempotent** (`_result_emitted` flag): review #3 showed that a `RuntimeError`
   escaping the operation loop would emit `crashed` and then be re-caught by the pre-existing
   `except RuntimeError` around the lock, emitting a second, wrong `lock-contention` verdict.
   First verdict wins, so the "exactly one payload" invariant the tests assert always holds.
   Review #6 suggested also resetting `_result_emitted` in the `finally` block for in-process
   reuse; **that suggestion was tried and rejected** — it lets the outer `except RuntimeError`
   in `execute_json_config` emit a second, less specific verdict over the `crashed` one, and
   `test_crash_after_loop_keeps_applied_changes` failed immediately. The flag stays latched
   for the life of the process, with a comment saying why.
6. Module docstring updated to describe the new behavior.

### Op 2: `validate-config-json.py` (7 edits)

`_validate_edits` simulates each cleanly-matching edit on `sim` and checks GUARDs 10/11
against it — the content as it will exist at apply time — returning the post-edit content.
`validate_modern_format` threads `sim_files[relpath]` across operations on the same file.
`validate_legacy_format` threads `legacy_sim` the same way: review #5 noted that nothing
forbids two `files[]` entries for one path, so the earlier "legacy needs no threading"
assumption was unenforced — such a config validated APPROVED and then aborted at apply time
under the new fail-closed executor.

### Op 3: `tests/test_ops_hardening.py` (new, 15 tests)

Subprocess-runs the real scripts in a pytest `tmp_path` project dir. Covers: ambiguous-anchor
abort without write; missing-anchor abort with rollback of a prior op; **same-file rollback
restores pristine content (gap 0 regression)**; **backup file itself holds pre-run content**;
**`file_delete` after `code_edit` keeps the pristine backup**; **project-root `manifest.json`
refused rather than silently unbacked**; dry-run threading across ops on one file; diff +
`RESULT-JSON` on success; `RESULT-JSON` on failure with exact status; `RESULT-JSON` on
engine-level abort; **a post-loop crash leaving applied changes intact**; **the transaction
being retired before the summary prints**; and three validator cumulative-simulation cases.
`_result_json()` asserts exactly one payload line rather than raising `StopIteration`.
The last two copy the engine into `tmp_path` and inject a fault at the loop boundary — review
#5 correctly pointed out this needs no engine change and is ~15 lines, so the earlier §7
deferral was dropped.

## 4. Phase 2 — Contract rewrite (ops 4–10)

### Op 4: `.claude/agents/implementer.md` (9 edits)
Workflow renumbered bottom-up (4→5, 3→4, 2→3), then **Step 1: Validate (MANDATORY)**
inserted — closes gap 1. Safety Rules invert to reactive reads. Execute step documents the
diff (and its 50-line-per-file truncation), `RESULT-JSON` as the complete record, and what an
absent `RESULT-JSON` means. Anti-patterns updated. The `file_create`-then-`code_edit`
asymmetry (§7) is stated inline so the contract's claim is not absolute.
Preserved for `tests/test_behavior_spec.py`: "plan.md", "verification pending", and the
absence of "from ops.json validation section".

### Op 10: `.claude/commands/implement.md` (2 edits)
**The command file is the prompt that actually drives `/implement`**, so leaving it stale
would have silently defeated the whole change — review #5 caught this. Its Phase 1 said
"Parse ops.json and validate all operations" (impossible without reading ops.json into
context) and Phase 2 drove a per-operation loop with per-op announce/verify/rollback
(impossible against a batch engine, and outside the implementer's `Bash(python3
.claude/operations/scripts/*)` grant). Both are rewritten to the batch contract.

### Ops 5, 7: `execute-operations-config` SKILL.md (`.claude/skills/` + `.agents/` mirror)
`[STEP 0] Validate` added to the process diagram; new "Read Policy (token discipline)"
section; evidence/truncation wording. Both copies get all three edits — review #2 caught the
mirror receiving only two.

### Op 6: `.codex/agents/implementer.toml` (9 edits)
Mirrors the validator step, read-policy inversion, anti-pattern, **the full Step 2→3/3→4/4→5
renumbering** (without which the file would carry two "Step 2" headings), and **the evidence
paragraph** — so the Codex implementer does not lose its read-before-edit net without gaining
the compensating diff/`RESULT-JSON` contract. Review #3 also caught the two PRE-FLIGHT
CHECKLIST lines that op 4 rewrites in the Claude copy; those are now mirrored too, so the
file cannot simultaneously say "backups are automatic" and "create backup of files that will
be modified". Inserted commands use that file's own `.Codex/operations/scripts/...`
path convention.

### Ops 8, 9: `validate-operations-config` SKILL.md (`.claude/skills/` + `.agents/` mirror)
Removes the stale claim that a multi-match anchor is a *warning* — GUARD 11 is a hard FAIL,
now cumulative. Applied to both corpora.

**Deliberately NOT changed**, two read-first directives that live outside the implementer's
prompt:
- `.claude/agents/_shared/AGENT_TEMPLATE.md:74` ("ALWAYS read a file before editing it").
  Review #1 flagged it, but that template serves agents that genuinely hold Edit/Write
  (documenter, tester, devops), where read-before-edit is correct. Only the ops-driven
  implementer — which has no Edit/Write at all — is exempt.
- `.claude/agents/_shared/CONTEXT_CLEANUP_PROTOCOL.md:115-118` ("ALWAYS read a file at the
  start of your task"), raised by review #5. It is reference documentation, not `@`-injected
  into `implementer.md`, so it does not reach the agent's context — but it is named here so
  the omission is a decision rather than an oversight.

## 5. Phase 3 — Docs (ops 11–12 + manual)

- **Op 11:** `docs/ARCHITECTURE.md` — the "Execution Safety" guarantee list gains
  first-write-wins backups, fail-closed anchor matching, and the RESULT-JSON evidence
  contract; the pipeline diagram's "Implementer reads ops.json + plan.md" is corrected to
  match the new contract. Review #4 caught this as an unacknowledged DoD ("docs updated") gap.
- **Op 12:** CHANGELOG — entries merged *into* the existing `### Changed` block under
  `[Unreleased]` (anchored on the model-routing bullet) rather than opening a third
  duplicate heading. Leads with the rollback data-loss fix.
- **Manual, post-implementation:** `.ai/SESSION_STATE.md` + `.ai/CHANGELOG_AI.md`.
- **Test-count drift (pre-existing, surfaced here):** CLAUDE.md documents "516 tests"; the
  suite measured **576 passing** today, before any change here. This plan takes it to 591.
  The stale figure appears in ~17 places (CLAUDE.md, AGENTS.md, README.md, and eight `.ai/*`
  files per review #2), so this is a **multi-file docs sweep, not a one-line fix** — deferred
  to its own follow-up rather than smuggled in here. It is not gen-docs-gated
  (`scripts/gen-docs.py` counts only agents/commands/skills/hooks), so CI passes either way.

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| **Behavior change is breaking by design**: configs relying on skip-and-continue now abort | Intended (fail-closed). CHANGELOG documents it; the validator catches such configs with a precise error before execution |
| First-write-wins changes recovery semantics | Strictly safer: backup now always holds pre-run content, which is what `restore-backup.py` and `/rollback` already assume. Two new tests pin it |
| Op 1 edits the executor **while running it** | Python holds the old code in memory; `atomic_write` uses `os.replace`; remaining ops run on old semantics; rollback restores on failure. Dry-run clean |
| Ordering inside multi-edit operations | Renames applied bottom-up so every `find` stays unique at its application point; all 72 edits bound in dry-run (§10) |
| Codex/Claude corpora drift again | This plan syncs both; a CI parity gate remains absent — logged as follow-up, not silently assumed fixed |
| Existing tests assert old behavior | Repo-wide grep found none; the three `test_behavior_spec.py` couplings are preserved verbatim |
| `ruff`/`mypy` | Ops scripts are outside both (`pyproject.toml`: mypy `files=["src/claudekit"]`, ruff `extend-exclude=[".claude"]`). The new test file *is* in ruff scope and is clean |

Security: strictly tightening — fail-closed replaces fail-soft first-occurrence writes, and
backup integrity is restored. No new dependencies, no path-validation changes, no hook
exit-code changes, protected-file and MAX_DELETIONS guards untouched.

## 7. Out of scope (explicit)

- TOCTOU freshness pinning (content hash between validate and execute).
- `file_create`-then-`code_edit` on the same new file: dry-run now simulates it, but the
  validator's GUARD 6 disk-existence check still rejects it. Documented in the implementer
  contract as "split into a second ops.json"; unifying the two is a follow-up.
- A CI parity gate for `.codex`/`.agents` mirrors.
- (Previously deferred, now done: the post-loop crash path IS unit-tested — review #5 showed
  copy-and-inject needs no engine change.)
- CLAUDE.md template slimming for subagent injection — task 009 (context budget).

## 8. Validation commands (run after execution)

```bash
python3 -m pytest tests/test_ops_hardening.py -q          # 15 new tests
python3 -m pytest tests/ -q                               # expect 591 passing
ruff check src/ tests/ scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
shellcheck install.sh .claude/hooks/*.sh
```

Additionally, re-run the gap-0 reproduction (§10) and confirm it now ends with `alpha`.

## 9. Rollback

Engine auto-backup (`backups/ops-hardening-implementer-contract-<ts>/` + manifest) →
`restore-backup.py <backup-name>` or `/rollback latest`. Git is the second net (tree clean at
plan time). Note the irony: gap 0 means the *current* engine's rollback is unreliable for
multi-op-per-file runs — this ops.json touches each file in exactly one operation, so it is
unaffected, and it fixes the flaw for future runs.

## 10. Evidence (measured, not estimated)

**Gap 0 reproduction** — current engine, `file.txt` = `alpha`, op 1 edits it, op 2 fails on
the same file:
```
exit=1
--- file.txt after rollback ---   beta      <-- mutated intermediate, original lost
--- backup contents ---           beta      <-- pristine copy was overwritten
```

**Revision 3 ops.json:**
- `validate-config-json.py` → **APPROVED**, exit 0 (benign warnings only: duplicate
  `SKILL.md` basenames across different directories).
- `execute-json-ops.py --dry-run` → exit 0, **12/12 operations, 72/72 edits bound,
  0 failures**, `DRY RUN COMPLETE`.
- Counts verified programmatically from the config: op1=32, op2=7, op3=file_create(15 tests),
  op4=9, op5=3, op6=9, op7=3, op8=2, op9=2, op10=2, op11=2, op12=1 = **72 edits / 12 ops**.
- Baseline suite: **576 passed** (measured today; CLAUDE.md's "516" is stale — see §5).

**End-to-end rehearsal.** Exact layout, so it is reproducible: a temp dir mirroring the repo
shape — `<tmp>/.claude/operations/scripts/` (copies of `*.py` + `operations-schema.json`) and
`<tmp>/tests/` (op 3's new test file, plus a copy of `tests/test_validator.py`). Ops 1–2 were
extracted from this config and applied there by the **current, unpatched** engine; the patched
copies were then compiled and exercised. `SCRIPTS_DIR` in the test file resolves to
`tests/../.claude/operations/scripts`, which under this layout is the patched copy.
```
apply exit=0        EXECUTION COMPLETE   Successful: 2   Errors: 0
PY_COMPILE: OK      (both patched scripts)
pytest tests/      ->  34 passed   (15 new + 19 existing validator tests)
ruff check tests/test_ops_hardening.py  ->  All checks passed!
```
Behavioral probes against the patched engine:
```
gap-0 repro:                 file=alpha  backup=alpha  RESULT-JSON lines=1
unknown op type:             exit=1      RESULT-JSON lines=1   status="failed"
dry-run delete manifest.json exit=1      collision refused in dry-run too
```

**Fault injection at the loop boundary** — both post-commit rollback paths, each measured
against a counterfactual build with the fix removed:
```
exception path (review #4)   WITH loop_completed guard:  exit=1  f.txt=beta   <-- preserved
                             WITHOUT it:                 exit=1  f.txt=alpha  <-- reverted
signal path    (review #5)   WITH early _active_txn=None: assert passes, exit=0
                             WITHOUT it:                  assert fires — txn still live
                                                          during the summary window
```
Both are now pinned by tests (`TestPostLoopFailureDoesNotRevert`), not just by this rehearsal.
Note on measurement: two earlier attempts using a real `BrokenPipeError` (`… | head`) were
inconclusive — with small output no error fires at all, and with 400 operations the pipe
breaks *inside* the loop, where rollback is correct. Only fault injection isolates the
post-commit window.

**Legacy-format duplicate-path threading** (review #5 MINOR): a legacy config with two
`files[]` entries for one path, the second anchored on the first's output, now validates
`APPROVED` (exit 0) instead of failing "pattern not found".

**Gap 0 re-run against the patched engine** — same repro as above:
```
file.txt after rollback:  alpha    <-- was 'beta' before the fix
backup holds:             alpha    <-- pristine copy preserved
RESULT-JSON: {"plan": "backup-repro", "mode": "execute", "status": "failed", ...}
```

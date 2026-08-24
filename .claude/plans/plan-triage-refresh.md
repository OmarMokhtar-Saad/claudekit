# Implementation Plan: refresh the code-review triage, and close the false-drift hole

**Status:** PLANNED 2026-08-24. Tier 2 (docs across `review/` and `.ai/`, plus one
tooling correctness fix in `.claude/operations/scripts/review-record.py`).
**Owner decision already taken:** option **A** — `review/code-review-triage.md` is the single
record; the `.ai/BACKLOG.md` entry becomes a pointer.

## What this plan is, and the premise it corrects

The handoff that commissioned this work said 45 of `review/code-review.md`'s findings were
"unchecked, not probably fine", and asked where new verdicts should live. Both halves were
wrong, and the correction is the reason this plan exists rather than the one that was asked for.

`review/code-review-triage.md` already existed, committed at `8f54f55`
(`docs(review): triage all 108 findings in review/code-review.md`), an ancestor of `HEAD`.
It carries all 108 findings as `F1`–`F108`, each with a status and a `file:line`. Its header
table reads **53 LIVE · 49 FIXED · 5 OBSOLETE · 1 UNVERIFIABLE**. Nothing was unverified.

The "45" came from a *second*, incompatible enumeration in `.ai/BACKLOG.md` — 75 P2/P3
findings, 30 verified — of the same source review. Two triages of one file, different totals,
different IDs, neither pointing at the other. That is the actual defect, and it is the
`duplicate-asset` class the corpus is already consolidating under task 008.

What *is* stale is the triage's evidence: it was taken at `c167298` on branch
`perf/token-efficiency`, and `git rev-list --count 8f54f55..HEAD` = **78**. The three working
periods since then closed a batch of its LIVE rows without ever amending it.

## Phase 1 — re-verify all 53 LIVE rows against `HEAD`

Done before this plan was written; every verdict below was produced by opening the file or
running the code, per the triage's own method. **13 of the 53 are now FIXED**, one is
half-fixed, and three sections' paths moved wholesale.

### FIXED since the triage (13)

| ID | Triage claim | Evidence at `HEAD` |
| --- | --- | --- |
| F37 | `tail -20` hides the root cause; full output written nowhere | `post-implement.sh:101,136,170` and `pre-push.sh:153,188,223` are all `tail -60`, with the reasoning in a comment at `:98-100`; `log "ERROR" "Build failed: $output"` (`:96`) writes the **full** output to `hooks.log`. Both halves of the finding are answered. Residual, not a defect: the stdout cap is 60 lines. `tail -5` at `:128` is a *success* branch |
| F47 | suggestion echoed from a backgrounded subshell after exit | `.claude/settings.json:47` runs `suggest-compact.sh` synchronously — no trailing `&`. The premise is gone |
| F57 | `git stash apply 2>/dev/null \|\| true` logs success on a failed restore | `auto-checkpoint.sh:226` is `if ! git stash apply 2>"$stash_err"; then`, and `:229,:231` name the recovery command **and** the stash SHA on both the log and stderr paths |
| F59 | prune off-by-one + unlocked registry read/modify/write | Lock half: `registry_lock()` at `:77-90` uses the portable `mkdir` idiom (flock is Linux-only) and logs rather than silently dropping a checkpoint. Off-by-one half: the `+1` at `:138-139` is now **deliberate and documented** at `:125-127` — it reserves room for the append that follows. Two guards no longer disagree; one guard explains itself |
| F68 (half) | `ExecutionLock` is not a lock, and `release()` unlinks another holder's lock | Locking half FIXED: `:164-165` takes `fcntl.flock(LOCK_EX\|LOCK_NB)` when available and the docstring at `:151-155` is honest about the Windows fallback. **Unlink half is still LIVE** — see below |
| F70 | `normalize_config` annotated `-> dict`, returns `None` | `:272` is `def normalize_config(config: dict) -> Optional[dict]:` |
| F80 | `PROTECTED_PATTERNS` includes `*.md`, so `file_delete` can never remove markdown | `shared.py:10-22`: the `*.md` glob is gone and the removal is documented with its measurement (97 archived configs, zero `file_delete` ops; task 008 stalled 16-of-19 REJECTED on this pattern) |
| F91 | unguarded `json.loads` in `cmd_config` | `main.py:1886-1892` catches `JSONDecodeError` and `OSError` and calls `err()` |
| F92 | doctor's magic thresholds `>= 9` / `>= 8` / `>= 27` | `main.py:38-40` `EXPECTED_AGENTS/COMMANDS/SKILLS`, **written by `scripts/gen-docs.py:181-183`** — so hard rule 8 now owns them and `gen-docs --check` catches drift. The strongest of the thirteen: a magic number became a gated one |
| F93 | `subprocess.run` with no `timeout=` | `main.py:363,385` `timeout=PROBE_TIMEOUT`, with the measured limit of `subprocess.run(timeout=)` recorded at `:72` |
| F95 | identical `elif args.list` / `else` in `cmd_rollback` | `main.py:769-770`, single branch, with a comment naming the dead one |
| F98 | ANSI colours emitted unconditionally | `main.py:51-59`: `NO_COLOR` (any value, per no-color.org) beats an `isatty()` check |
| F99 | the shipped default config violates the shipped schema | `ck doctor --strict` → `[✓] Hooks config.json matches config.schema.json` |
| F100 | nothing validates against `config.schema.json` | `_check_config_schema` in the CLI, gated by `tests/test_config_schema.py` and `tests/test_gate_scope.py:178-185` (Gate 3) |

### Path drift: §6 no longer exists as written

The triage's §6 is titled ``templates/hooks/`` and its eight LIVE rows cite
`templates/hooks/auto-checkpoint.sh`, `templates/hooks/file-guard.sh` and siblings.
**`templates/hooks/` is not a directory in this tree** (`ls` → No such file or directory); the
hooks were *promoted* into `.claude/hooks/`. Every §6 citation needs repointing, and the
"template-only, unwired, so contained" mitigations attached to F61, F63 and F65 no longer
hold — those patterns now run against real input via `file-guard-gate.sh` and
`injection-scan-gate.sh`. This is a **priority increase**, not bookkeeping.

### Still LIVE at `HEAD` (40, one reduced in scope)

Re-confirmed by execution, grouped by what would fix them.

| ID | Site at `HEAD` | Note |
| --- | --- | --- |
| F15 | `install.sh:186` | `ls -1 … \| grep -v -E … \| wc -l`. ShellCheck 0.11 does not flag this variant, so `shellcheck install.sh` stays clean — the lint gate will never catch it |
| F16 | `install.sh:170` before `:174` | cosmetic banner order |
| F17 | `install.sh:146` | every Kotlin-DSL file contains the string `kotlin` |
| F27 | `config-protection.sh:19` | `'checkstyle' 'spotbugs' 'detekt'` bare substrings beside anchored siblings |
| F35 | `pre-commit.sh:188` | per-pattern loop inside a per-file loop |
| F38 | `.claude/hooks/` | **11** of the directory's scripts source `lib.sh`; **14** still define their own `log()`. Sharper than the triage's "9 of 19" |
| F39 | `post-implement.sh:3` | `set -e` against a run-all-three-steps design |
| F40 | `pre-plan.sh:69` | one `python3` per existing plan file, on a UserPromptSubmit hook |
| F41 | `pre-plan.sh:88+` | warns, returns 0 unconditionally — `vacuous-check` |
| F44 | `session-start.sh:136` | `head -20 "$CONTEXT_FILE" \| sed 's/^/  /'` — unsanitised file into the transcript. The only LIVE finding with a security shape |
| F49 | `cost-tracker.sh:26-33` | counts hook-log lines; prints "Session Summary" while the file is still named `cost-tracker.sh` |
| F51 | `format-typecheck.sh:49` | unquoted command substitution into an array; correct only because `IFS=$'\n'` |
| F52 | `format-typecheck.sh:92-93` | `grep -c "error TS"` over a report containing formatter output; `"?"` flows into `fail:${TSC_ERRORS}_errors` |
| F53 | `format-typecheck.sh:34` | `sleep 1` as synchronisation |
| F54 | `security-reminder.sh:55,81` | 3000-char silent truncation **and** unanchored `\bMD5\b\|\bSHA1\b\|\bRC4\b` |
| F55 | `command-log-audit.sh:10` | `AUDIT_LOG=".claude/hooks/bash-commands.log"` is cwd-relative while `:9` uses `$SCRIPT_DIR` |
| F60 | `auto-checkpoint.sh:200` | `awk '{print $2}'` on `--porcelain`; display-only |
| F61 | `.claude/hooks/file-guard.sh:94-96` | `cert\|crt\|pem\|key\|p12\|pfx` with no allowlist; `:125` `*"customer"*"data"*`. **Job 4** |
| F62/F101 | `config.schema.json:75,81` | "195+ patterns" for a ~60-pattern script. Two sites, not the `:58,64` the triage recorded. **Job 4** |
| F63 | `prompt-injection-scanner.sh:34,42,50` | `"you are now"`, `"developer mode"`, `"act as if"` unanchored — now reachable |
| F65 | `check-comment-replacement.sh:39` | `raise NotImplementedError` in the exit-1 set |
| F66 | `check-comment-replacement.sh:98` | `echo -e "$violations"` |
| F68 | `execute-json-ops.py:183-186` | `release()` still `os.unlink(self.lock_path)` unconditionally. **Job 4**, reduced: with `flock` held the window is narrower than the triage described |
| F69/F103 | `execute-json-ops.py:703-730` | per-edit anchor checks, no single-action enforcement; `add_after` precedence over `replace` unwarned |
| F71 | `execute-json-ops.py:1091` | `operation.get('path', 'unknown')` — a sentinel in a path slot |
| F72 | `execute-json-ops.py` | 119 `print(` vs 4 `logger.` — `--verbose` changes almost nothing |
| F74 | `validate-config-json.py` | 31 distinct `GUARD n` tokens and a docstring saying 31 (count half fixed), but **15, 27 and 28 are absent** from the run |
| F75 | `validate-config-json.py:504,664,788` | `file_op['path']` unguarded → `KeyError` traceback |
| F76 | `validate-config-json.py:107,145` | null-byte checks duplicated across paths |
| F77 | `restore-backup.py:31` | `sys.path.insert(0, dirname(__file__))`. Sharper than the triage: **one** script, not "all three" |
| F78 | `restore-backup.py` | 12 `restored_files` occurrences |
| F79 | `restore-backup.py:307` | `sorted(backups, reverse=True)` sorts by name; the timestamp coupling is uncommented |
| F96 | `main.py:341,347` | `if condition is True` / `elif == "warn"` — a check returning `1` counts as a *failure* |
| F97 | `main.py:799` | `line.startswith("name:")` as a frontmatter parser |
| F104 | `.claude/hooks/` | `2>/dev/null` counts: `auto-checkpoint.sh` **14**, `session-start.sh` 10, `pre-commit.sh` 10, `format-typecheck.sh` 8. The triage's own scoping — "none on a call whose failure changes the verdict" — is the version worth acting on |
| F105 | `command-guard.sh` 3, `ops-enforcement.sh` 7 | ten `python3` startups per guarded tool call |
| F106 | `.claude/hooks/` | same as F38; **job 6** |
| F107 | `.claude/hooks/` | **three** `LOG_FILE=` forms, not the two the triage recorded: `"$SCRIPT_DIR/hooks.log"`, `"${LOG_FILE:-$ROOT/…}"`, and a bare cwd-relative `".claude/hooks/hooks.log"` |

Also unchanged: F64 stays UNVERIFIABLE (latent by construction), F102 stays OBSOLETE.

## Phase 2 — write the refresh into the record (ops 1–4)

**Shape: append, do not rewrite.** The triage treats `review/code-review.md` as an untouched
historical record and layers verdicts on top; this refresh does the same to the triage. Editing
53 rows in place would destroy the 2026-08-20 evidence and cost ~40 anchored edits, each a
chance to hit the `add_before`/`add_after` newline trap.

1. `review/code-review-triage.md` — insert a dated **"Re-verification 2026-08-24 at `HEAD`"**
   section directly after "State in ten seconds", carrying Phase 1's three tables verbatim, the
   78-commit staleness measurement, and the §6 path-drift warning. New counts stated as a
   delta (**53 LIVE → 40 LIVE, 13 newly FIXED**), never by overwriting the original table.
2. `review/code-review-triage.md` — add one line under the header naming this file as the
   single record and the BACKLOG entry as a pointer, so a reader who arrives from either
   direction cannot mistake which is authoritative.
3. `.ai/BACKLOG.md` — replace the 75-finding entry's body with a pointer to
   `review/code-review-triage.md`, keeping the entry's two hard-won lessons (that its count was
   wrong twice, and that a count of `P2|P3` *mentions* is not a count of findings) because those
   are about method, not state.
4. `.ai/SESSION_STATE.md` + `.ai/CHANGELOG_AI.md` — record the period.

No `CHANGELOG.md` entry: nothing here is user-visible.

## Phase 3 — the false-drift hole (ops 5, and the only code in this plan)

Job 2 asked whether three `drifted` plans were executed, superseded, or abandoned. **All three
were executed** — `.claude/plans/archive/README.md` rows 55, 90 and 121 record each one with its
op count and score. But diagnosing *why* they read `drifted` found a gate defect, and it is the
handoff's lesson 1 again: a check reporting something it did not measure.

    $ python3 .claude/operations/scripts/review-record.py check \
        .claude/plans/plan-dispatcher-payload.md \
        .claude/plans/archive/ops-dispatcher-payload-docs.json
    NOTE: no record under ops key 'dispatcher-payload-docs'; using the legacy plan-slug record 'dispatcher-payload'.
    DRIFT: ops.json changed after it was reviewed.

The addendum config has **no record of its own**, so the fallback compares its bytes against a
*different file's* approved hash and reports DRIFT. `.claude/plans/archive/README.md:57` says
`ops-dispatcher-payload-docs.json` was executed with `--no-approval` as Tier 1 docs — it never
had a verdict, so there is no verdict for it to have drifted from. `ops-enforcement-runtime-wiring.json`
is the same shape. Meanwhile each plan's *primary* config is clean:

| Config | `review-record.py check` |
| --- | --- |
| `ops-dispatcher-payload.json` | `OK: … (APPROVED 94)` |
| `ops-enforcement-runtime.json` | `OK: … (APPROVED 93)` |
| `plan-capability-tiers-audit.ops.json` | `OK: … (APPROVED 93)` |
| `plan-capability-tiers-followup.ops.json` | `OK: … (APPROVED 95)` |
| `plan-capability-tiers.ops.json` | **DRIFT — genuine** |

`gen-plan-index.py`'s `PRECEDENCE` puts `drifted` first, so one falsely-drifted addendum
condemns the whole plan. **Two of the three warnings are manufactured by the tool.**

- **Op 5:** `review-record.py` — when no record exists under the ops key, report *absence*
  (the existing `planned` rc=3) instead of hashing against the legacy plan-slug record. An
  unreviewed config is unreviewed; it is not a drifted one. The legacy fallback stays for the
  case it was written for — an ops file whose key *is* the plan slug.
- **Mutation proof, both directions:** re-run the `-docs` and `-wiring` checks (rc 2 → 3) and
  the four primary configs (rc 0, unchanged); then hand-edit one byte of
  `ops-dispatcher-payload.json` and confirm rc 2 still fires for a *real* drift.
- **`plan-capability-tiers`'s drift is real and stays visible.** No approval will be
  re-recorded for it. `archive/README.md:90` documents it as executed 8/8 with APPROVED 95, and
  `review-record.py`'s own output names the likely cause — `--stamp-baseline` run after the
  verdict, which rewrites the config's bytes. That is a plausible, documented, *benign* cause and
  it is still not a verdict, so the plan is archived with a README row saying exactly that:
  executed, record no longer binds, cause probable-not-proven.
- **Op 6:** move the three spent plan documents to `.claude/plans/archive/` beside their configs,
  with README rows. `classify()` then reports `legacy` with a `record says …` note — honest, and
  it stops two false `drifted` warnings from being the first thing every CI run prints.

## Phase 4 — the command diet, and what it is not (ops 7)

Re-measured rather than inherited:

    $ wc -l .claude/commands/*.md | sort -rn | head -6
    7318 total
     464 refine.md   228 ship.md   227 gan-build.md   222 opensource.md   220 loop-start.md

    $ python3 scripts/check-context-floor.py
    command descriptions        4753    6000  OK

**Command bodies are not in the always-on context floor** — only descriptions, at 4753/6000
chars. So a diet buys readability and per-invocation cost, and calling it a context win would be
the kind of overstatement hard rule 6 exists to stop. The handoff's own figure (~4,730) is now
4753; re-derive it, do not quote it.

**`refine.md` cannot be split the obvious way.** Its bash blocks are fragments carrying
`<TASK>`, `<N>` and `$iteration` with no loop wrapper — `tests/test_delivery_contract_smoke.py`'s
module docstring states this. Extracting "the script" would mean *writing* a new script on a
CI-facing path, which is a feature wearing a refactor's clothes. Not attempted.

What op 7 does instead, and nothing more: record the five over-200 commands in
`.ai/TECH_DEBT.md` with the measurement above, the floor fact, and the `refine.md` trap, so the
next reader does not re-derive it a third time. **Any actual cut to a shipped command is
user-visible and stays owner-gated.**

## Out of scope — owner-gated, presented separately

Jobs 4 (enforcement trio: F68 unlink, F61 file-guard allowlist, F62/F101 schema overpromise),
5 (command-bash parse-error gate) and 6 (14-hook `log()` dedup). Each gets its own plan and its
own approval. Note for job 4: **F68 is smaller than the backlog claims** — the `fcntl.flock`
half already landed; only the unconditional `os.unlink` in `release()` remains.

## What I got wrong

- **I accepted the handoff's framing before measuring it.** My first action should have been
  `ls review/`, which would have shown `code-review-triage.md` immediately. Instead I read the
  handoff's ground-truth block first and started reconciling a "45 unverified" set that did not
  exist. The handoff even warned "re-verify, do not trust this" about its own numbers, and the
  one number it was wrong about was the one I did not check first.
- **I nearly reported F37 as LIVE.** `grep 'tail -20'` returns nothing, so the finding looked
  fixed; `grep 'tail -[0-9]'` returns eight sites. Both greps are true and only the second is
  informative. The finding's *number* was fixed (20 → 60) and its *class* was answered by the
  full output going to `hooks.log` — but reading only the first grep would have called it fixed
  for the wrong reason, and reading only the second would have called it live. Lesson 3, met
  from an angle I did not expect: asserting the property meant checking what the failure branch
  *does with* the output, not how many lines it prints.
- **F59's "off-by-one" is not one.** The `+1` survives, so a shape-only read says LIVE. The
  comment three lines above says the `+1` reserves room for the append that follows, which is
  the *caller* interpreting the guard — exactly the near-miss the handoff's lesson 4 recorded
  about this same finding. I read the comment because the handoff told me to; without it I would
  have filed a defect against working code.

## Definition of Done

Every gate in the handoff's DoD block, with the suite's whole output written to a file and
summarised from the file — never piped through `tail`. Plus: `Plan-Id: triage-refresh` trailer,
`gen-plan-index.py --check` regenerated after committing (committing flips this plan to
`executed` and drifts `INDEX.md`), and each spent config archived with a README row.

# Implementation Plan: Discharge the `silent-failure` ratchet

> **Revision 4** (post-approval, applying the two pre-execution conditions). MAJOR 1 fixed by
> option **(a)** — the sibling clause now requires a provable subset relation, resolved against
> the builtin exception hierarchy — plus the width-pinning test the reviewer asked for either
> way. MINOR 2 fixed in the code so the documented degradation becomes true. Test count
> 29 -> 32; mutants 19 -> 22. Corpus numbers unchanged: 16 findings post-fix, 0 diagnostics.
>
> **Revision 3** (round 3 of 3). C1 recurred and was found again — Rev 1's measuring
> instrument was missing a **verb** (`rmdir`), Rev 2's was missing a **root**
> (`.claude/hooks/`). The true corpus is **23 pass-only handlers, not 13**. Every published
> number below has been re-derived, and the scanner now carries an explicit
> "WHAT THIS SCANNER CANNOT SEE" section so the next blind spot is disclosed rather than
> discovered.

## Overview

`silent-failure` is the largest recurrence class in `review/code-review-triage.md` and has
crossed the three-entry ratchet in `.ai/REVIEW_GUIDE.md`. **This plan discharges it with a
mechanical check covering both shell and Python** (`scripts/check-silent-failure.py`), closes
F57 as a worked example, and records the residue honestly.

## Scope

- **In Scope:** `scripts/check-silent-failure.py` (new); F57 fix + banner gating + one pragma in
  `templates/hooks/auto-checkpoint.sh`; `tests/test_silent_failure_lint.py` (new); one
  `.gitignore` line; ratchet rows + verdict section in `.ai/REVIEW_GUIDE.md`.
- **Out of Scope (ownership):** `install.sh`, `pyproject.toml`, `config.schema.json`,
  `templates/*/config.env`, `.claude/hooks/*`, `src/claudekit/cli/main.py`, `.ai/BACKLOG.md`,
  `CHANGELOG.md` (text supplied as a follow-up note).
- **Out of Scope (deliberate):** wiring `.github/workflows/ci.yml`; annotating the 16 residual
  findings, all in files this workstream does not own.

---

## C1 (third pass) — the corrected Python corpus

**The reviewer was right again, and the failure mode was identical in shape to Rev 1's.**
Rev 2 published "fires on 2 of 13". The real denominator is **23**:

| Root | Pass-only `except` handlers |
|---|---:|
| `src/` | 4 |
| `.claude/operations/scripts/` | 9 |
| **`.claude/hooks/`** | **10 — never scanned** |
| `scripts/` | 0 |
| **TOTAL** | **23** |

**Root cause — an undisclosed asymmetry.** The shell half scanned every `.sh` file with no root
filter; the Python half was restricted by `PY_ROOTS = ("src/", ".claude/operations/scripts/")`.
Ten sites in `.claude/hooks/` were structurally invisible. **`PY_ROOTS` is deleted.** Both halves
now scan everything under the given paths, and `collect()` carries a comment saying why.

### The full 23-site table (mechanically generated, not hand-transcribed)

| Site | Mutators | Enclosing fn | Verdict |
|---|---|---|---|
| `.claude/hooks/iron-law-gate.py:274` | `write` | `hlog` | **FIRES** |
| `.claude/hooks/iron-law-gate.py:292` | — | `safe` | spared: no mutator |
| `.claude/hooks/iron-law-gate.py:368` | — | `project_root` | spared: no mutator |
| `.claude/hooks/reflection-gate.py:92` | `write` | `hlog` | **FIRES** |
| `.claude/hooks/reflection-gate.py:319` | `unlink` | `handle_session_start` | **FIRES** |
| `.claude/hooks/reflection-gate.py:494` | — | `project_root` | spared: no mutator |
| `.claude/hooks/reflection.py:298` | — | `_warn_untrusted_root` | spared: stderr write is not persistent state |
| `.claude/hooks/reflection.py:351` | `mkdir` | `ensure_ledger_dir` | spared: sibling handler propagates |
| `.claude/hooks/reflection.py:384` | — | `project_root` | spared: no mutator |
| `.claude/hooks/reflection.py:1006` | `unlink` | `main` | **FIRES** |
| `.claude/operations/scripts/execute-json-ops.py:132` | `chmod` | `atomic_write` | **FIRES** |
| `.claude/operations/scripts/execute-json-ops.py:140` | — | `atomic_write` | spared: no mutator |
| `.claude/operations/scripts/execute-json-ops.py:145` | `unlink` | `atomic_write` | spared: ancestor re-raises |
| `.claude/operations/scripts/execute-json-ops.py:180` | — | `release` | spared: no mutator |
| `.claude/operations/scripts/execute-json-ops.py:185` | `unlink` | `release` | spared: teardown |
| `.claude/operations/scripts/knowledge-ledger.py:60` | — | `project_root` | spared: no mutator |
| `.claude/operations/scripts/project-graph.py:71` | — | `project_root` | spared: no mutator |
| `.claude/operations/scripts/validate-config-json.py:379` | — | `validate_against_schema` | spared: no mutator |
| `.claude/operations/scripts/worktree-manager.py:144` | `unlink` | `save_registry` | spared: ancestor re-raises |
| `src/claudekit/cli/main.py:507` | — | `cmd_agents` | spared: no mutator |
| `src/claudekit/cli/main.py:726` | `rmdir` | `cmd_uninstall` | **FIRES** |
| `src/claudekit/security/cli.py:27` | — | `_validator_from_project` | spared: no mutator |
| `src/claudekit/security/path_guard.py:110` | — | `validate_directory` | spared: no mutator |

**Fires on 6 of 23.** Verdicts on the six:

| Site | Verdict |
|---|---|
| `src/claudekit/cli/main.py:726` | **TP** — `os.rmdir` swallowed, then `ok(...)` and `return 0` |
| `.claude/hooks/reflection-gate.py:319` | **TP** — a failed `carry.unlink()` replays stale carry-over into model context next session |
| `.claude/hooks/reflection.py:1006` | **TP** — a failed `inbox.unlink()` defeats the stated intent "so a stale payload can never be replayed" |
| `.claude/hooks/iron-law-gate.py:274`, `reflection-gate.py:92` | Arguable — best-effort `hlog`, but CLAUDE.md makes `hooks.log` the first debug step, so silent log loss has a real cost. Wants a pragma |
| `.claude/operations/scripts/execute-json-ops.py:132` | Documented `chmod` fallback. Wants a pragma |

**Measured precision: 3 clear TPs / 6 fires (50%); 6/6 actionable** — the other three each need
an explicit pragma decision rather than a code change.

### Two rule clauses added because the new sites earned them

Widening the roots exposed two shapes that were genuine rule weaknesses, not defects:

- **Sibling-handler clause.** `reflection.py:351` is `except FileExistsError: pass` sitting
  beside `except OSError: return None` — the idiomatic `exist_ok` emulation. A `pass` handler
  whose sibling propagates is a deliberate narrow carve-out. Pinned by mutant M17.
- **Stream-write clause.** `reflection.py:298` writes to `sys.stderr`. A diagnostic write is not
  persistent state. Pinned by mutant M18.

Also applied: minor (6) the re-raise test now requires a **top-level** `raise` in the ancestor
handler's body, not a `raise` anywhere in its subtree; minor (7) `close` and `flock` were
**removed** from `PY_MUTATORS` — neither mutates persistent state by the script's own
definition, and they were latent false positives masked only by the teardown/re-raise
exclusions (visible in the table: `:140` and `:180` now read "no mutator").

---

## Shell rule (unchanged, re-measured)

| Candidate | Hits | Sampled | TP est. | Verdict |
|---|---:|---|---|---|
| any `2>/dev/null` | 217 | — | ~1% | Reject — disabled within a week |
| any `\|\| true` family | 55 | — | low | Reject — misses install.sh |
| suppression AND ignored-failure | 32 | — | mixed | Reject |
| suppression AND mutating | 88 | — | low | Reject |
| supp AND ignored AND mutating (naive verbs) | 16 | 16/16 | 11 | 5 FPs |
| **(ignored OR `&&...\|\|`) AND mutating, refined + logical-line joining** | **12** | **12/12** | **12** | **CHOSEN** |

`install.sh:496` — the multi-line `python3 -c` config rewrite, historical silent failure #1 — is
found only because the joiner spans the 17 lines between the write and the swallow.

---

## MAJOR 2 — the linter no longer reports clean when it could not read its input

A `SyntaxError` and a tripped join cap both emitted a Diagnostic and then fell through to
`return 0` / "OK". That is the linted class, inside the linter, and the proposed CI line would
have rested on it. **New exit code 3 = INCOMPLETE, and it outranks exit 1** — an incomplete scan
cannot support a clean *or* a complete verdict. Pinned by M12, M14, and three new tests.

## MAJOR 3 — the fixture sandbox no longer pollutes the repo scan

`.tmp-test-fixtures` is in `EXCLUDED_PARTS`. Gitignoring hid leftover fixtures from git, not from
`rglob`, so an interrupted run would have redded the residue ratchet, the documented validation
command, and the proposed CI line.

Implementing this surfaced a second bug in my own fix: excluding the directory also made fixtures
**unscannable when named explicitly**, which broke 23 of 28 tests. `collect()` now (a) lets an
explicitly named file override the exclusion list, as other linters do, and (b) matches exclusion
parts **relative to the scan root** — which also fixes minor (8), where absolute-path matching
made behaviour depend on where the repo was checked out.

## MAJOR 4 — the heredoc skip is bounded and diagnosed

Capped at `MAX_JOIN_LINES` with a diagnostic, plus a diagnostic if the file ends inside a heredoc.

**The first version of this fix did not work and mutation testing caught it.** With only the
EOF diagnostic, mutant M13 (remove the cap) still passed all 28 tests, because the EOF diagnostic
masked it. The discriminating case is a *false* heredoc that terminates far away:
`x=$(( 1 << MARKER ))` is an arithmetic shift, so the following lines are real code; if the skip
runs to a later line that happens to equal `MARKER`, no EOF diagnostic ever fires. Verified by
execution — uncapped, a real finding 120 lines later **vanishes and the scanner reports OK**;
capped, it is reported and diagnosed (exit 3). Now pinned by
`test_false_heredoc_that_terminates_far_away_is_not_reported_clean`.

---

## MAJOR 1 — the sibling clause, narrowed to a provable subset relation

Rev 3's clause exempted a `pass` handler whenever ANY sibling had a top-level `raise`/`return`,
with no relationship between exception types — so `except OSError: pass` beside
`except ValueError: return None` was spared, though the OSError swallow is exactly the linted
class. Corpus impact was nil (`reflection.py:351` was the only spared site), so this was a
latent recall hole rather than a wrong published number.

**Fixed by option (a).** `_catches_superset_of()` resolves handler type names against the real
builtin exception hierarchy with `issubclass`, so `FileExistsError -> OSError` is recognised
**without a hand-maintained map** (a hardcoded map would itself be a `hardcoded-count`-shaped
liability in a repo whose ratchet already tracks that class). A bare `except:` sibling
legitimately catches everything and still exempts. An unresolvable name — a project-defined
exception class — returns False, so the site is **reported rather than skipped**: the
recall-safe direction for a lint.

Verified by execution: the subset pair exits 0, the unrelated pair exits 1, and the corpus is
unchanged at 6 Python findings with `reflection.py:351` still spared.

**The reviewer's observation that nothing constrained the clause's WIDTH is addressed:** M17
only removed the clause, so a widened clause passed. New mutant **M19** (drop the subset
requirement, keeping the clause) flips `test_python_unrelated_sibling_does_not_exempt`.

The residual hole is now disclosed in the docstring's "WHAT THIS SCANNER CANNOT SEE" section
and in the guide's "What this check cannot see" paragraph — this was the one blind spot missing
from the section built to prevent exactly that.

## MINOR 2 — the documented degradation is now true

Both durable texts claimed `<<<WORD` here-strings "degrade to a silent skip". They did not:
`HEREDOC` used `.search()`, so `foo <<<WORD` matched from the second `<`, set a bogus delimiter,
skipped 80 lines and emitted a DIAGNOSTIC with exit 3.

Fixed in the code rather than the prose, so the check gains a capability instead of an excuse.
**The first fix was wrong and mutation caught it:** `<<(?!<)` alone still matches — the engine
simply starts at the second `<` of `<<<`. The shipped pattern is `(?<!<)<<(?!<)`, verified
against `<<<WORD`, `<<EOF`, `<<-EOF`, `<<'EOF'`, `<<"EOF"` and the arithmetic `1 << MARKER`.
Mutants **M20** (lookbehind removed) and **M20b** (the lookahead-only version that shipped
wrong for one iteration) both flip `test_here_string_is_not_mistaken_for_a_heredoc`.

Note this test was itself wrong on the first attempt — it used a *quoted* `<<<"$HAY"`, which
never matched under either pattern, so it passed against the bug. Corrected to the reviewer's
stated unquoted form before being trusted.

## Disclosed unpinned surface — answering the reviewer's closing challenge

Rev 2 had four pieces of unpinned surface (`MAX_JOIN_LINES`, the DIAGNOSTIC path,
`scan_python`'s `SyntaxError` handling, `PY_ROOTS`). **All four are now pinned** by M11, M12,
M14 and M15 respectively. What remains deliberately unpinned, stated rather than implied — this
list is also in the script docstring and the guide:

- **Verb allowlists.** Unlisted shell mutators (`curl -o`, `rsync`, `python3 script.py`, project
  functions) and unlisted `PY_MUTATORS` are silent misses. `git` is the one denylist, so unknown
  git subcommands fail loud.
- **Shell syntax not modelled:** `$'...'` ANSI-C quoting, backticks, `<<<WORD` here-strings.
  These degrade to a silent skip, not a diagnostic.
- **Dataflow:** "the failure sets a flag nothing reads" is undetectable here.
- **Conditional raise:** a `raise` nested inside an `if` in an ancestor handler does not exempt.
- **`MAX_JOIN_LINES = 80` is corpus-tuned.** Pinned against regression by
  `test_large_inline_python_block_is_still_caught` (a ~45-line inline block that must still be
  caught) — at 25, the cap tripped 8 times and mis-reported F57's sibling at :101 instead of :109.

---

## Implementation Steps

### Step 1 — `scripts/check-silent-failure.py` (Create)
Shell rule + the 4-clause Python AST rule; quote/comment state machine; bounded, diagnosed
joins and heredoc skips; `# silent-ok:` pragma (length floor documented as a typo filter, not
enforcement); exit codes 0/1/2/3; and the "WHAT THIS SCANNER CANNOT SEE" docstring section.

### Step 2 — `templates/hooks/auto-checkpoint.sh` (Modify, 3 edits)
- **F57 at :165.** Verified by execution: a conflicting `git stash apply` exits 1 and the stash
  survives — a silent **SUCCESS**, not data loss. Does not `return 1` (the checkpoint succeeded);
  logs an ERROR and prints the `git stash apply <sha>` recovery command.
  **Minor (5) applied:** git's stderr goes to a temp file, then is replayed **both** to the
  terminal and into `hooks.log` (CLAUDE.md's first debug step). Not a command substitution —
  verified in Rev 2 that `$(git stash apply 2>&1 >/dev/null)` captures nothing and prints
  nothing, so stdout passthrough is preserved by not capturing stdout at all.
- **Banner gating.** The failure branch sets `restore_note`; the `Checkpoint saved:` echo appends
  it, so no bare success banner follows "working tree NOT restored".
- **The `:109` pragma**, demonstrating the exemption mechanism on a benign site.

### Step 3 — `tests/test_silent_failure_lint.py` (Create) — **32 tests, exit codes only**
Fixtures in `<repo>/.tmp-test-fixtures/` (gitignored **and** excluded from scanning), never
`$TMPDIR`: `.claude/hooks/ops-enforcement.sh:43` exempts `/private/tmp/claude-*`, `/tmp/claude-*`
and `/var/folders/*`, so a fixture there makes that hook exit 0 and the assertion pass vacuously.

### Step 4 — `.gitignore` (Modify) — one line.

### Step 5 — `.ai/REVIEW_GUIDE.md` (Modify, 3 edits)
Updated `silent-failure` row; `vacuous-check` row flagged as also-crossed and still owing; new
`## Verdicts on the silent-failure ratchet` section anchored `add_before` `## Review philosophy`.

---

## Testing Strategy — 22 mutants, all EXECUTED, all killed

| Mutant | Tests that flipped |
|---|---|
| **M0 baseline** | none — **32 passed** |
| M1 revert the F57 fix | `test_f57_site_is_fixed`, residue |
| M2 drop mutating-command requirement | 4 incl. `test_readonly_probes_are_not_flagged` |
| M3 `MIN_REASON = 0` | `test_pragma_without_a_substantive_reason_does_not_exempt` |
| M4 zero-files returns 0 | `test_scanning_zero_files_is_distinguishable_from_zero_findings` |
| M5 never exit non-zero on findings | 8 |
| M6 remove quote joining | 3 incl. `test_join_cap_is_not_reported_clean` |
| M7 drop python re-raise exclusion | `test_python_cleanup_that_reraises_is_not_flagged`, residue |
| M8 drop python teardown exclusion | `test_python_teardown_is_not_flagged` |
| M9 comments affect quote parity | 4 |
| **M10 delete the scanner** | **31 of 32, incl. the residue ratchet** |
| **M11 `MAX_JOIN_LINES = 3`** (reviewer's mutant) | **5** |
| **M12 diagnostics do not affect exit code** | **4** |
| **M13 unbounded heredoc skip** | **1** (`..._terminates_far_away_...`) |
| **M14 SyntaxError silently skipped** | **2** |
| **M15 re-introduce `PY_ROOTS`** (the C1 regression) | **9** |
| **M16 fixture dir not excluded** | **1** |
| **M17 sibling-handler clause dropped** | **1** |
| **M18 stderr writes count as mutations** | **1** |
| **M19 sibling clause widened back** (MAJOR 1) | **1** — `test_python_unrelated_sibling_does_not_exempt` |
| **M20 heredoc lookbehind removed** (MINOR 2) | **1** — `test_here_string_is_not_mistaken_for_a_heredoc` |
| **M20b lookahead-only heredoc regex** | **1** — same test; pins the fix that was wrong once |

**Tests that pass against unfixed code:** the 30 lint-behavior tests. Only
`test_f57_site_is_fixed` and `test_repo_residue_is_confined_to_known_paths` pin the F57 patch,
confirmed by M1.

**Pre-flight evidence (staged copy; tree restored and restoration asserted):** `pytest`
**32 passed** · `ruff` clean · `mypy` **Success, 18 source files** · `bash -n` OK · scanner over
repo -> **exit 1, 16 findings, 0 diagnostics, 118 files (45 shell, 73 python)** · scanner over
patched `auto-checkpoint.sh` -> exit 0.

## Validation commands

```bash
python3 scripts/check-silent-failure.py .    # expect exit 1, 16 findings, 0 DIAGNOSTIC
python3 scripts/check-silent-failure.py templates/hooks/auto-checkpoint.sh   # expect exit 0
python3 -m pytest tests/test_silent_failure_lint.py -q                       # expect 32 passed
python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ && mypy
bash -n templates/hooks/auto-checkpoint.sh
```

## Rollback Plan

`git rm scripts/check-silent-failure.py tests/test_silent_failure_lint.py` and
`git checkout -- templates/hooks/auto-checkpoint.sh .ai/REVIEW_GUIDE.md .gitignore`. No CI,
packaging, installer or runtime surface is touched; `scripts/` is not packaged into the wheel and
`auto-checkpoint.sh` remains template-only (not wired into `settings.json`, per F62).

## Gate decision

**Ship the script; do NOT wire CI here.** Precision is not the blocker — all 16 residual findings
are real instances of the shape. Ownership is: they live in `install.sh` (10),
`.claude/hooks/` (4), `src/claudekit/cli/main.py` (1) and
`.claude/operations/scripts/execute-json-ops.py` (1), none owned by this workstream. The script
exits non-zero on findings; it is simply not yet called by CI. The interim ratchet is
`test_repo_residue_is_confined_to_known_paths`, which asserts the exit code first and therefore
fails when the scanner is deleted, broken, or scans nothing (M10, M16).

## Risk Assessment

- **Low:** scanner unreferenced by CI; `.ai/` edits maintainer-facing; `:109` pragma is
  comment-only; `.gitignore` line additive.
- **Low:** `templates/hooks/*.sh` is outside CI's shellcheck scope, so shellcheck will not gate
  the F57 edit — hence `bash -n` in the validation list.
- **Medium:** the F57 edit changes failure-path behavior and now writes a temp file via `mktemp`.
  Success-path stdout is byte-identical (verified); success-path **stderr is no longer
  suppressed**, which is stated rather than hidden.
- **Medium:** `test_repo_residue_is_confined_to_known_paths` reads the live tree, so a sibling
  workstream adding a silent-failure site fails it. Intended ratchet, but cross-workstream
  coupling worth flagging at merge. It pins PATHS only, so in-flight edits inside those six files
  cannot flip it spuriously.
- **Medium (pre-existing, NOT fixed):** SC2155 at `auto-checkpoint.sh:143`.
- **Blast radius:** no hub file touched.

---

## Follow-up notes for the owner (NOT applied here)

**1. CHANGELOG** — text only, to avoid an anchor collision with two in-flight plans:

```
### Added
- `scripts/check-silent-failure.py`: flags compound silent failures — a mutating operation
  whose failure is swallowed while the caller reports success — in shell scripts and Python.
  Read-only probes are not flagged; intentional sites take an inline `# silent-ok: <reason>`
  pragma. Exits 1 on findings, 2 when it scans zero files, and 3 when the scan was incomplete.

### Fixed
- `templates/hooks/auto-checkpoint.sh`: a failed `git stash apply` after a checkpoint no longer
  reports success. The hook now logs an error to hooks.log, prints the exact
  `git stash apply <sha>` recovery command, and annotates the "Checkpoint saved" banner. Work
  was never lost — the stash survives — but the failure was previously invisible. (F57)
```

**2. Wire the gate** once the 16 residual findings are annotated or fixed:

```yaml
      - name: No compound silent failures
        run: python3 scripts/check-silent-failure.py .
```

**3. Three genuine Python defects to triage** (owner-gated, none in my scope):
`src/claudekit/cli/main.py:726`, `.claude/hooks/reflection-gate.py:319`,
`.claude/hooks/reflection.py:1006`. **Remedy direction: log-and-degrade, not raise.** The two
hook sites run inside code that must never crash a tool call, so the fix is to record the
failure (hooks.log) and continue, not to propagate.

**3b. MINOR 3 (deferred by reviewer's call).** In the F57 hunk,
`stash_err="$(mktemp ...)"` is unguarded; under `set -e` a mktemp failure would abort after
`git stash push` and before the apply. One-line guard: `|| stash_err=""`, with the redirect
falling back to `/dev/null`. Not applied now to keep the approved hunk byte-stable.

**3c. MINOR 5 (accepted as-is).** The `.gitignore` anchor ends at the file's final line, so a
missing trailing newline makes the edit fail loudly at validation rather than silently — the
correct failure direction, left alone deliberately.

**4. SC2155** at `auto-checkpoint.sh:143`; add `templates/hooks/*.sh` to shellcheck's CI scope.

**5. Remaining ratchet debt:** `vacuous-check` (3), `unanchored-pattern` (6),
`duplicate-asset` (5), `unwired-artifact` (4), `type-contract-drift` (3), `hardcoded-count` (3).

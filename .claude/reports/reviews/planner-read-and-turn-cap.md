# Code review — planner-read-and-turn-cap (executing review, ROUND 2)

Target: `.claude/plans/plan-planner-read-and-turn-cap.md` + `.claude/plans/ops-planner-read-and-turn-cap.json` (8 ops)
Reviewer: code-reviewer (executing; ops applied in a throwaway copy, real working tree untouched)
Revision: 069d823 + uncommitted working tree (both artifacts revised in place since round 1)
Round: 2 of 3 — scope limited to the revised guard payload, test payload, and Testing Strategy.

SUMMARY — Critical: 0 | High: 0 | Medium: 0 | Low: 2

VERDICT: APPROVE WITH SUGGESTIONS

## Execution evidence

`execute-json-ops.py ... --no-approval` → 8/8 ops succeeded, 0 errors.

### Unmutated
```
17 passed in 1.60s
```
(round 1 had 13; the four added cases are `test_blocks_a_same_length_file_outside_the_allowlist`,
`test_registry_registers_the_guard_as_blocking`, `test_dispatch_blocks_an_unwindowed_read`,
`test_dispatch_allows_a_windowed_read`.)

### Mutant 1 — `THRESHOLD = 200` → `20000`
```
FAILED tests/test_read_window_guard.py::test_blocks_unwindowed_read_of_a_long_file
FAILED tests/test_read_window_guard.py::test_blocks_a_same_length_file_outside_the_allowlist
FAILED tests/test_read_window_guard.py::test_dispatch_blocks_an_unwindowed_read
3 failed, 14 passed in 1.60s
```
The allowlist tests and the 200-line allow test stayed GREEN, as the plan predicts.

### Mutant 2 — delete `if _allowlisted(path): return 0`
```
FAILED tests/test_read_window_guard.py::test_allows_an_allowlisted_path - Ass...
1 failed, 16 passed in 1.43s
```
**Round-1 [H1] discharged.** The test now builds a 250-line `.claude/plans/plan-x.md` under a fake
`CLAUDE_PROJECT_DIR`, so the allowlist is the only branch that can allow it; the negative twin
(`docs/notes-x.md`, identical length → exit 2) stayed GREEN, so a widened allowlist cannot pass both.

### Mutant 3 — registry row `tier: blocking` → `advisory`
```
FAILED tests/test_read_window_guard.py::test_registry_registers_the_guard_as_blocking
FAILED tests/test_read_window_guard.py::test_dispatch_blocks_an_unwindowed_read
2 failed, 15 passed in 1.52s
```
**Round-1 [H2] discharged.** `test_dispatch_blocks_an_unwindowed_read` drives the real
`bash dispatch.sh PreToolUse` path with `ECC_HOOK_PROFILE=standard`, so the wiring — not just the
script — is now measured. Reverting all three mutants returns `17 passed in 1.45s`.

### Gates
`ruff check` clean · `pytest tests/test_agent_prompt_size.py tests/test_dispatch_merge.py -q` →
111 passed · `gen-model-policy.py --check` OK (22 roles) · `gen-docs.py` then `--check` → OK.

## INHERITED FINDINGS (round 1)

| id | title | status | evidence |
|---|---|---|---|
| H1 | allowlist branch untested — own mutant survived | **discharged** | mutant 2 now turns `test_allows_an_allowlisted_path` RED (1 failed, 16 passed); negative twin added |
| H2 | guard's dispatcher wiring untested | **discharged** | mutant 3 turns the registry assertion **and** the end-to-end dispatch test RED (2 failed, 15 passed) |
| M1 | ALLOWLIST named nonexistent `.claude/project-index.md` | **discharged** | `grep project-index .claude/hooks/read-window-guard.py` → absent |
| M2 | allowlist resolved against `CLAUDE_PROJECT_DIR`, stat against cwd | **discharged** | `read-window-guard.py:111-112` — `if not os.path.isabs(path): path = os.path.join(root, path)` before the stat |
| L2 | redundant `.ai/*/*.md` pattern | **discharged** | ALLOWLIST is now 5 entries; only `.ai/*.md` remains |
| L1 | `limit > 200` blocks a genuinely windowed Read | **open (accepted)** | `read-window-guard.py:117` still `0 < limit <= THRESHOLD`; documented, and the stderr names the fix |

## LOW (non-blocking, do not re-review)

- **[L1]** `limit=500` on a long file is still blocked (`read-window-guard.py:117`). Deliberate and
  documented; it will read as a false positive the first time an agent hits it. Consider widening the
  message to say "a limit above 200 is not accepted" rather than "declares no usable limit".
- **[L3]** Plan Testing Strategy item 1 names only `test_blocks_unwindowed_read_of_a_long_file` as
  going RED; the measured run turns **three** tests RED (also the negative twin and the dispatch
  block test). Understating a mutant's blast radius is harmless here, but the plan is now the
  record — list all three.

## Positive observations

- The fix addressed the *mechanism*, not the symptom: the allowlist test was rebuilt around a fake
  project root so its length no longer depends on whatever `CLAUDE.md` happens to be that week — the
  exact failure mode that made round 1's version inert.
- The negative twin plus the tier assertion close the two directions an allowlist test can lie in.
- Mutant 3 killing the dispatch test (not just the registry assertion) is the strongest single piece
  of evidence in this change: the row is genuinely read and its tier genuinely decides the outcome.

=== REVIEW ===
SCORE: 92
DECISION: APPROVED
- [MINOR] read-window-guard.py:117 blocks a Read with limit>200 though it is windowed; accepted design, message could say so explicitly
- [MINOR] plan Testing Strategy mutant 1 names one RED test; the measured run produces three
=== END REVIEW ===

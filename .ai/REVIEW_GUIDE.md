# Review Guide

## Two review systems — don't conflate

| | Plan review | Code review |
|---|------------|-------------|
| Agent | `reviewer` (opus, read-only) | `code-reviewer` (opus, read-only) |
| Command | `/review` | `/code-review` |
| Object | `plan-*.md` + ops.json | diffs, files, PRs |
| Gate | ≥90/100: Plan Quality 40% + Architecture 30% + Security 30% | findings ranked by severity; APPROVE/REQUEST_CHANGES/BLOCK |
| Auto-reject | plan without ops.json → score 0 | — |

High-stakes escalation: `/santa` (dual independent reviewers, both must approve). Language-specific: python-reviewer / typescript-reviewer (merge candidates into code-reviewer, task 008).

## Reviewing changes to ClaudeKit itself (maintainer checklist)

**Any PR:**
- [ ] Full DoD gate green (pytest 516, ruff, mypy, gen-docs --check, shellcheck).
- [ ] CHANGELOG `[Unreleased]` entry for user-visible changes.
- [ ] No hardcoded counts introduced; no new near-duplicate assets.
- [ ] Conventional commit format; co-author line for AI commits.

**Prompt changes (agents/commands/skills):**
- [ ] Registry, coordinator routing, QUICK_START, INVOCATION rows updated for renames/merges.
- [ ] No schema/rule duplication — reference the single source (generate-operations-config, INVOCATION.md).
- [ ] Frontmatter examples intact; tools list still minimal.
- [ ] Every review finding carries a `Class` (see the recurrence table below).
- [ ] Doesn't contradict HANDOFF_PROTOCOL / VERIFICATION_PROTOCOL / the Iron Law.

**Hook changes:**
- [ ] Blocking = exit 2 + stderr, fail closed; profile-gated correctly.
- [ ] bash-3.2/macOS-safe; shellcheck clean; behavioral test proves block AND allow paths.
- [ ] settings.json registration matches (dangling-hooks CI).
- [ ] Fixture location checked against the hook's exemption prefixes. A gate test that passes by ALLOWING is unverified until you know where its fixture lives (`tests/test_ops_enforcement_scope.py:42` places fixtures beside the repo for exactly this reason).

**Security-layer changes:**
- [ ] Bypass corpus extended for the new surface; coverage ≥85% holds.
- [ ] No allowlist additions of shell interpreters/launchers (bash/sh/env/xargs stay off).
- [ ] SECURITY.md still honest ("speed bump" framing).

**Installer changes:**
- [ ] Staging/backup/atomic-swap preserved; mid-failure test passes; manifest correctness; `settings.local.json` survival.

## Finding format and the recurrence ratchet

Every review finding — plan review, code review, or a maintainer reviewing ClaudeKit itself —
is one block. A finding that cannot fill `Scenario` and `Evidence` is not confirmed and is not
written.

```
F<n>      <one-line claim>
Verdict:  confirmed | refuted | unproven      (refuted is dropped, not softened)
Blocking: yes | no                            (yes = wrong behavior ships)
Where:    <path>:<line>                       repository-relative
Scenario: <the concrete sequence that produces the wrong result>
Evidence: <what was run or read, and what it returned>
Class:    <recurrence class from the table below, or "new: <name>">
Fix:      patch | ticket | decision_needed | dismiss
```

`Class` is the load-bearing field and the reason the block exists. **When a class reaches three
entries it earns a mechanical check, or an explicit written "cannot be mechanised, and here is
why."** Extend the table; never invent a synonym for a row that already exists. This ratchet is
what task 010 (eval framework) consumes — findings that live only in a transcript die with the
session, and the same class gets re-found instead of accumulating into a check.

| Class | Shape | What catches it now |
|---|---|---|
| `unconfirmed-revision` | a conclusion drawn from a tree never pinned to the reviewed ref | nothing yet — code-reviewer Phase 0 is prose, not a check |
| `vacuous-check` | a test or gate that cannot fail (mock-only, no-throw, or the fixture re-declares what the shipped artifact owns) | `verification-gap-lens` (prose); no mechanical check. **THRESHOLD CROSSED and still owing** — 3 LIVE instances F41/F47/F100 (`review/code-review-triage.md:533`); owes a check or a written "cannot be mechanised", exactly as `silent-failure` did. Two live examples from building that check: a residue test that built its offender set from stderr without asserting the exit code stayed green when the scanner was deleted; and the scanner itself emitted a diagnostic then returned 0, so a file it could not parse was reported clean |
| `hardcoded-count` | a component count typed by hand instead of generated | `scripts/gen-docs.py --check` |
| `registry-drift` | an agent loads a skill the registry does not list | `scripts/gen-registry.py --check` |
| `dangling-hook` | `settings.json` references a hook file that does not exist | dangling-hooks CI check |
| `context-floor-creep` | always-on prompt text grows and nothing fails | `scripts/check-context-floor.py --check` |
| `prose-verified-claim` | a claim resting on reading prose instead of executing something | `_shared/VERIFICATION_PROTOCOL.md` refutation pass (prose) |
| `duplicate-asset` | a new near-duplicate agent/skill instead of extending the existing one | nothing yet — task 008 is manual |
| `fix-introduces-larger-hole` | the fix for a finding opens a worse one than it closed | **partly mechanical for one seam.** `scripts/check-validator-differential.py` fails any change to `CommandValidator` that moves a payload REJECT → ALLOW, which is the shape this class takes there — it caught nothing retroactively (it did not exist during the 2026-08-21 batch), it makes repeating that sweep free. Its own review produced the FOURTH instance of this class: the guard added to close a false PASS created a permanent false FAIL on every push to main. Everywhere else, a FRESH reviewer told to attack the fix remains the only thing that has ever worked. |
| `guard-cannot-express-guarded-case` | a rule is added in one place while the artifact the model actually fills cannot express it | nothing yet — candidate check: assert every verdict/status token a prompt instructs also appears in that prompt's output template |
| `count-asserted-not-derived` | a total is restated in prose/metadata instead of re-derived from the thing it counts | `gen-docs.py --check` covers component counts only; in-document totals are ungated |
| `denylist-inside-an-allowlist` | the outer set is allowlisted but an inner dimension (flags, subcommands, arguments) is denylisted, so the security property collapses to "we thought of the bad ones" | nothing yet — the tell is a review round that finds new members of a class a previous round claimed to have swept |
| `silent-failure` | an error is swallowed (`\|\| true`, bare `except`, `2>/dev/null`) and the caller reports success | **`scripts/check-silent-failure.py`** — shell AND python, 16 residual findings (as of 2026-08-20; re-derive with the script, never by hand). NOT yet CI-wired (ownership, not precision); interim ratchet is `tests/test_silent_failure_lint.py`. See "Verdicts on the `silent-failure` ratchet" below |
| `unanchored-pattern` | a pattern matched without anchoring, so it fires on substrings | nothing yet — 6 LIVE |
| `unwired-artifact` | a file ships that nothing executable references | nothing yet — 4 LIVE; `config.schema.json` went 46 days unapplied |
| `type-contract-drift` | an annotation disagrees with what the function returns | `mypy` — but `pyproject.toml:57` scopes it to `src/claudekit`, so the operations engine is unchecked |
| `validator-executor-divergence` | the validator and the thing it gates disagree about what is valid | **`scripts/check-validator-vs-bash.py`** for the `command_validator.py` seam: every payload the validator ALLOWS is executed under `bash` with `rm`/`sudo`/`chmod`/`curl`/`dd` shadowed by marker functions, and a marker is a divergence. This is the oracle that found all five fail-opens in the 2026-08-21 batch by hand. Blind spots, stated: `PATH` is emptied for containment, so wrapper-argument divergence (`xargs eval ...`) is NOT observable, and fork-bomb/loop shapes are refused rather than run. The other 2 seams — unknown edit fields (validator rejects, executor ignores) and sequential-edit anchors (validator checks the original file, executor applies in order) — still have nothing. |

### What the 2026-08-19/20 batch actually proved about this table

Four classes above crossed the threshold inside a single batch, which is worth reading as a
result rather than a coincidence.

**`fix-introduces-larger-hole` is the one to design around.** Four instances in two days: a
reviewer that went from refusing every review to reporting clean while blind to new files; a
hook-conflict fix that opened an arbitrary source write through a symlinked inbox; an installer
fail-closed check that would have blocked every installation; and a `PreToolUse` control
bypassed by dispatch order. Every one was caught by a FRESH reviewer instance told to attack the
fix. A reviewer asked "did they address the finding? yes" passes all four. That is the delta-review
contract, and it is worth more than any check we could write.

**Writing a mutant finds defects before the mutant runs.** Three times in this batch, the act of
trying to disable a rule exposed that the rule did not live where the table implied: `X = () or
(...)` neutered nothing (it evaluates to the non-empty tuple), `_GIT_OUTPUT_FLAGS` could not be
disabled because the attached `--output=` form was hardcoded at the call site, and `git remote
add` turned out to mutate through positionals that no flag rule touched. Heuristic:
**a guard you cannot disable in one place is a guard whose enforcement you do not understand.**

**Mutants must assert the exact flipped set.** An earlier revision claimed each of eight mutants
flipped only its own case; the test asserted only that the target flipped, and the claim was false
for one of them. Declare the collateral per mutant and assert set equality.

**An exempted prefix disables enforcement for everything under it — including a whole clone.**
The standing warning was narrow: don't put hook fixtures under `$TMPDIR`. The rule is wider.
`.claude/hooks/ops-enforcement.sh:43` exempts `/private/tmp/claude-*`, `/tmp/claude-*` and
`/{private/,}var/folders/*`, and the exemption tests the *target path*, so any tree placed there
loses enforcement wholesale. Hit from the other direction on 2026-08-20: a fresh clone made inside
the session scratchpad (under `/private/tmp/claude-*`) produced 15 failures in
`tests/test_ops_enforcement_scope.py`, because its fixtures live in `REPO.parent`, which for that
clone was the exempt prefix. Re-cloning to a non-exempt parent: 1227 passed, 0 failed. There was no
regression and no CI gap (CI clones to `/home/runner/work/...`). **Diagnostic signature: assertions
expecting exit 2 receive exit 0** — a `vacuous-check` produced by location, not by code. So verify
where the clone and the fixtures sit before trusting ANY ops-enforcement result, and treat a gate
test that passes by allowing as suspect until its location is checked.

One caveat on everything above: the `reviewer` agent holds Read, Grep and Glob and cannot execute,
so it cannot write a mutant, apply an ops.json, or run the DoD commands. Until that is resolved
(BACKLOG P0.75) the mutation discipline in this section is the ORCHESTRATOR's to run, and a plan
review should be read as a static read-through, not as evidence that anything was executed.

## Verdicts on the `silent-failure` ratchet

`silent-failure` was discharged on 2026-08-20 with a **mechanical check covering both shell and
Python**: `scripts/check-silent-failure.py`. Candidate rules were measured against the corpus and
the hits sampled individually before anything was chosen.

### Read this first: the measuring instrument was wrong twice

Two successive revisions of this check published a **wrong corpus count**, and neither error was
in the rule — both were in the thing doing the measuring.

| Revision | Published | Actual | Blind spot |
|---|---:|---:|---|
| 1 | 6 pass-only handlers | 13 | a missing VERB: the mutator set had `remove` and `rmtree` but not `rmdir` — which silently excluded the strongest true positive, `src/claudekit/cli/main.py:726` |
| 2 | 13 | **23** | a missing ROOT: `PY_ROOTS` never looked at `.claude/hooks/`, hiding 10 sites. The shell half had no root filter; the asymmetry was undisclosed |

Revision 1 concluded from its 6 that the Python half "cannot be mechanised". That verdict was
**wrong and is withdrawn.** It is recorded here because a wrong "cannot be mechanised" closes a
ratchet permanently on a false premise — a worse failure than a noisy lint.

**The lesson, generalised: when a check reports a count, enumerate what it CANNOT see before
publishing what it did see.** The script now carries a
"WHAT THIS SCANNER CANNOT SEE" section for exactly this reason, and `PY_ROOTS` no longer exists.

### Shell

Report only when a failure path is ignored (`|| true`, `|| :`, `|| echo`, `|| print_warn`, or
`cmd && ok || fallback`) AND the command mutates state. The corpus has 192 `2>/dev/null` and
14 `|| true`; flagging those was rejected outright, because a rule with 217 hits gets disabled
within a week — strictly worse than no lint.

| Candidate | Hits | True positives (sampled) |
|---|---:|---|
| any `2>/dev/null` | 217 | ~1% — rejected |
| any `\|\| true` family | 55 | low, and misses the `install.sh` shape |
| suppression AND ignored-failure | 32 | mixed — rejected |
| suppression AND ignored AND mutating (naive verbs) | 16 | 11/16 |
| **(ignored OR `&&...\|\|`) AND mutating, refined + logical-line joining** | **12** | **12/12 — chosen** |

Logical-line joining is load-bearing: `install.sh:496` opens a `python3 -c "` block and swallows
the failure 17 lines later, so a line-at-a-time scanner misses the historical bug entirely.

### Python

Four clauses, all `ast.walk`-checkable: the `try` body mutates PERSISTENT state (a
`sys.stderr.write` is a diagnostic, not a mutation); no ancestor handler has a top-level `raise`;
no SIBLING handler on the same `try` has a top-level `raise`/`return` (the
`except FileExistsError: pass` / `except OSError: return None` pair is idiomatic `exist_ok`
emulation); and the handler is not in a teardown method.

**Fires on 6 of 23. Three are clear true positives** — `main.py:726` (`os.rmdir` swallowed, then
`ok("Removed N files")` and `return 0`; the swallow is benign in isolation, and a defect *there*
because the caller reports the uninstall complete while an empty managed tree survives), `reflection-gate.py:319` (a failed `carry.unlink()` replays stale
carry-over into model context), `reflection.py:1006` (a failed `inbox.unlink()` defeats the
stated "so a stale payload can never be replayed"). The other three — two best-effort `hlog`
writers and a documented `chmod` fallback — need an explicit pragma rather than a code change.

### Exemption is by pragma, not by path

An intentional site carries `# silent-ok: <reason>` on the line or the line above. A path
skip-list was rejected because it goes stale silently — the very class being linted. **The
10-character reason floor is a typo filter, not enforcement**: `# silent-ok: aaaaaaaaaa` passes.
Substance is a review obligation, not a machine check.

### The check must not itself fail silently

Exit codes are `0` clean, `1` findings, `2` unusable (bad path, or **zero files scanned**), and
`3` INCOMPLETE — a file would not parse, or a join/heredoc cap tripped. **Exit 3 outranks 1:** an
incomplete scan cannot support a clean or a complete verdict. An earlier draft emitted a
diagnostic and then returned 0, which put the linted class inside the linter.

### What this check cannot see

Stated so the next blind spot is disclosed rather than discovered. `git` uses a denylist of
read-only subcommands, so unknown git subcommands fail loud; **every other verb is an allowlist**,
so unlisted mutators (`curl -o`, `rsync`, `python3 script.py`, project shell functions) are
silent misses. `$'...'` quoting, backticks and `<<<WORD` here-strings are not modelled and
degrade to a silent skip. Dataflow ("the flag set on failure is never read") is out of reach. A
`raise` nested inside an `if` in an ancestor handler does not exempt. A sibling handler exempts
only when it provably catches a SUPERSET of the `pass` handler's types, resolved against the
builtin exception hierarchy — a subset relation expressed with project-defined exception
classes cannot be resolved and is reported rather than skipped. Read a clean run as
"no *known* shape present", never as "no silent failures present".

### Gate status — stated honestly

The script exits non-zero on findings but is **not** wired into `.github/workflows/ci.yml`.
Precision is not the blocker; ownership is: the 16 residual findings (as of 2026-08-20; the live
number is whatever `python3 scripts/check-silent-failure.py .` reports) live in `install.sh` (10),
`.claude/hooks/` (4), `src/claudekit/cli/main.py` (1) and `execute-json-ops.py` (1). Until they
are annotated or fixed, the ratchet is
`tests/test_silent_failure_lint.py::test_repo_residue_is_confined_to_known_paths`, which pins
PATHS (not counts or line numbers) and asserts the exit code first, so deleting or breaking the
scanner fails the suite rather than silently passing.

**Next classes owing a verdict:** `vacuous-check` (3 LIVE: F41, F47, F100 —
`review/code-review-triage.md:533`), `unanchored-pattern` (6), `duplicate-asset` (5),
`unwired-artifact` (4), `type-contract-drift` (3), `hardcoded-count` (3).

## Review philosophy

Findings need file:line and a suggested fix; severity-ranked; verify claims by running code, not by trusting prose (this repo's history is the cautionary tale — reviews once scored a product whose hooks had never fired). Push back with evidence; accept pushback with evidence. When reviewing consolidation PRs (task 008), demand the migration table: old asset → new home → registry/routing updates → user-facing note.

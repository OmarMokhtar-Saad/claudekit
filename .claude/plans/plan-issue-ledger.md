# Implementation Plan: Per-Issue Knowledge Ledger

**Goal:** stop Claude from re-diagnosing bugs this project already diagnosed, fixed, and verified.
**Approach:** a project-local markdown ledger (`.claude/knowledge/issues/<slug>.md`) written by one stdlib-only script, gated on the Verifier PASS checkpoint + the *existing* continuous-learning rubric, and read by a new debugger Phase 0 keyword grep.
**Riskiest step:** wiring the write into the Verifier — it is a read-only agent by contract, so the ledger write must be the single, narrowly-scoped, PASS-only exception (Op 7) or the agent's read-only guarantee erodes.

**Revision:** round 3 — one MINOR review finding addressed (installer coverage for the ledger README; see *Revision notes* at the end). Scope, architecture, and design are unchanged.

---

## Overview

Three moving parts, one new script:

1. **Storage** — `.claude/knowledge/issues/<slug>.md`, frontmatter `signature / root_cause / fix / files / date / verified`. Plain markdown; no index, no vector DB, no new runtime dependency (repo is stdlib-only, zero-dep).
2. **Write** — fires at the Verifier PASS checkpoint of Implementer → Verifier → GitOps, gated by the reusability+novelty rubric already defined in `continuous-learning/SKILL.md` (combined ≥ 10, threshold read from `.claude/hooks/config.json`). Not on Implementer edit, not only at session-end Stop.
3. **Read** — debugger Phase 0 greps the ledger before any fresh diagnosis; on a validated match it reports the known root cause/fix instead of re-deriving it. Pull-only — never auto-injected into context or CLAUDE.md.

## Scope

- **In scope:** ledger directory + entry contract; `knowledge-ledger.py` (`search`/`record`/`list`/`prune`); Verifier write step; debugger Phase 0; `continuous-learning` skill gains the second trigger (same rubric) **in both the Claude and the Codex corpus**; prune folded into the existing periodic sweep; CHANGELOG + BACKLOG; behavioral tests.
- **Out of scope (explicit):** cross-project promotion to `~/.claude/skills/learned/` (future phase, filed in BACKLOG Icebox); any embedding/vector retrieval; any new blocking hook; any auto-injection of ledger content into context; **Codex *agent* wiring** (`.codex/agents/debugger.toml`, `verifier.toml`) — see the mirror row below.

## Context summary (what exploration established)

| Finding | Consequence for this plan |
|---|---|
| `gen-docs.py:count_hooks()` counts `.claude/hooks/*.sh`; docs-drift is CI-gated | Ship the trigger as an **ops script**, not a new `.sh` hook — hook count stays 19, no docs-count churn. |
| `install.sh:203-204` copies `operations/scripts/*.py` and `*.json` wholesale | The new script ships to consumer projects with no installer change. |
| `verifier.md` Decision Logic: `Score >= 80: PASS → hand off to GitOps` | Exactly one natural checkpoint; Phase 6 slots in before the handoff. |
| `continuous-learning/SKILL.md` Step 2 already defines reusability/novelty ≥ 10 | Reuse verbatim. The script reads that one threshold from config (default 10) — no new scheme. |
| `.claude/hooks/config.json` has **no** `continuous_learning` key today | The script's config read falls back to 10, so behavior is identical to a hardcoded constant until someone opts in. No config edit is needed in this plan. |
| `.agents/skills/` is a **git-tracked Codex mirror** of `.claude/skills/` (74 `SKILL.md` pairs; 43 byte-identical, 31 differ only by name substitution `Claude→Codex`, `CLAUDE.md→AGENTS.md`, `.claude/→.Codex/`) | Substantive skill edits land in **both** copies — Step 5. |
| Prior approved plan `plan-ops-hardening-implementer-contract.md` ("Ops 5, 7" / "Ops 8, 9") edits `.claude/skills/X/SKILL.md` and `.agents/skills/X/SKILL.md` in one ops.json, and its review round caught "the mirror receiving only two [of three] edits" | The mirror is a maintained invariant, not dead weight — omitting it would repeat a defect this repo has already reviewed for. |
| The mirror uses its own `.Codex/operations/scripts/...` path convention and already references paths that exist only in an installed Codex tree (`.codex/` has `agents/` + `hooks/`, no `operations/`) | The Codex copy gets the same content with `.Codex/` paths — matching, not diverging from, the established convention. |
| `.agents/` and `.codex/` are **not** shipped by `install.sh`, not packaged, and not covered by any test or drift gate | Sync is convention-enforced only. Step 3 adds the first mechanical assert so this mirror cannot silently rot. |
| `.ai/BACKLOG.md` P3 already holds a periodic sweep item | Ledger pruning attaches there; no new hygiene mechanism. |
| `shared.py PROTECTED_PATTERNS` protects `*.md` from ops-engine deletion | Pruning must move files itself (`prune --apply` → `issues/archive/`), which it does. |
| Verifier is read-only; hooks fail closed on `exit 2` | The ledger write is one script call writing only under `.claude/knowledge/issues/`, guarded by an anti-pattern rule. |

### Why the Codex *agent* files stay out of scope

`.codex/agents/debugger.toml` and `verifier.toml` exist and carry the same phase structure, so
wiring them is feasible — but it is agent-behavior work, not the skill-corpus sync the mirror
invariant covers, and `.codex/` has no `operations/` tree of its own. Ledger v1 wires the read
and write paths on the Claude side only; the Codex skill documents the same contract so the two
corpora do not diverge in *content*. Codex agent wiring is listed under Follow-ups.

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (repo runs its own hooks on itself).
- Ops engine available; changes applied via `execute-json-ops.py` only (Iron Law) — no manual edits.

---

## Implementation Steps

### Step 1: Ledger CLI script
- **File:** `.claude/operations/scripts/knowledge-ledger.py` — **Create** (ops id `ledger-script`)
- Subcommands and exit-code contract:
  - `search <query…>` → `0` match printed, `3` no match (caller diagnoses fresh), `2` bad usage.
  - `record …` → `0` written, `1` refused by gate, `2` invalid input.
  - `list` → `0`. `prune [--apply]` → `0` clean/archived, `1` stale found without `--apply`.
- Write gate: `--verified` required (asserts Verifier PASS) **and** `reusability + novelty >= threshold` **and** signature not already recorded (`--force` to override) **and** slug matches `^[a-z0-9][a-z0-9._-]{0,63}$` (traversal defense).
- **Threshold is configuration, not a constant.** `min_combined_score()` reads
  `continuous_learning.issue_ledger.min_combined_score` from `.claude/hooks/config.json` — the
  exact block documented in `continuous-learning/SKILL.md` — and falls back to
  `DEFAULT_MIN_COMBINED_SCORE = 10` when the file is missing, the JSON is malformed, the key is
  absent, or the value is not an int (bools excluded). Config can never break the gate open by
  crashing it.
- **`--files` is validated on write.** `parse_files()` rejects (exit 2) any token containing
  `[`, `]`, `,`, a quote or a newline, because `prune` reads the `files: [a, b]` line back with
  `split_files()` (strip one bracket pair, split on commas). A misparsed list could make `prune`
  archive an entry whose files all still exist, so the input is refused rather than mangled.
- Retrieval: token + phrase scoring over entry text, signature hits weighted ×2, exact-signature phrase +5; top `--limit` (default 5).
- Env overrides `CLAUDEKIT_LEDGER_DIR` / `CLAUDEKIT_PROJECT_ROOT` exist so tests are hermetic.
- Python 3.9, stdlib only (`json` added), ruff line-length 100.

### Step 2: Ledger directory + entry contract
- **File:** `.claude/knowledge/issues/README.md` — **Create** (ops id `ledger-readme`)
- Documents the frontmatter schema, the write gate (threshold ≥ 10 *by default*, overridable via `.claude/hooks/config.json`), the read command, the prune cadence, and the project-local-only scope. Its presence also materializes the directory.

### Step 3: Behavioral tests
- **File:** `tests/test_knowledge_ledger.py` — **Create** (ops id `ledger-tests`)
- Subprocess-driven, against a `tmp_path` ledger: unverified refused; below-threshold refused; verified+scored writes valid frontmatter; duplicate signature refused then `--force`-able; traversal slug rejected with nothing written outside; search match → rc 0 with root cause printed; no match → rc 3; empty ledger → rc 3; signature hit outranks incidental body hit; live entry never pruned; stale entry reported (rc 1, file untouched) then archived by `--apply`; entry with empty `files:` never pruned.
- **New — `TestThresholdComesFromConfig`:** a temp project root carrying `.claude/hooks/config.json` proves config *raises* the bar (15 refused at 20), *lowers* it (5 accepted at 4), and that a missing key, malformed JSON, and a non-integer value each fall back to 10.
- **New — `TestFilesRoundTrip`:** bracket / quote / newline-injection tokens each rejected with rc 2 and nothing written; a clean two-file list serializes to exactly `files: [src/a.py, src/b.py]`.
- Four wiring asserts: debugger Phase 0, verifier `--verified`, the Claude skill references the ledger path, **and the Codex mirror does too** (`.Codex/knowledge/issues/` + `knowledge-ledger.py` in `.agents/skills/continuous-learning/SKILL.md`) — the first mechanical guard on the mirror.

### Step 4: Reuse the rubric at a second trigger
- **File:** `.claude/skills/continuous-learning/SKILL.md` — **Modify** (ops id `skill-continuous-learning`, 3 edits)
- Trigger section becomes **A. per-issue at Verifier PASS** / **B. per-session at Stop** (existing text preserved as B).
- New *Per-Issue Knowledge Ledger* section before `## Learning Categories`: comparison table, explicit "same gate — there is no second rubric", a sentence stating the threshold is *read from* the Configuration block below (not hardcoded twice), the `--files` character restriction, the three commands, and the pull-only / project-local / prune-don't-delete rules.
- Configuration block gains an `issue_ledger` key (`trigger: verifier-pass`, `storage_path`, `min_combined_score: 10`) — now a **live** key the script actually reads.

### Step 5: Mirror the skill edit into the Codex corpus
- **File:** `.agents/skills/continuous-learning/SKILL.md` — **Modify** (ops id `skill-continuous-learning-codex-mirror`, 3 edits)
- The same three edits as Step 4, translated to that corpus's own conventions: `.Codex/knowledge/issues/`, `~/.Codex/skills/learned/`, `.Codex/operations/scripts/knowledge-ledger.py`, `AGENTS.md` instead of `CLAUDE.md`. Content stays identical modulo those substitutions, which is exactly the mirror's observed invariant.

### Step 6: Debugger Phase 0 (read path)
- **File:** `.claude/agents/debugger.md` — **Modify** (ops id `agent-debugger`, 2 edits)
- New `### Phase 0: Check the Issue Ledger` before Phase 1: build query → `knowledge-ledger.py search` → **validate the match against current code** → report as `KNOWN ISSUE (ledger)` and skip Phases 2-3, or declare the entry stale and diagnose fresh. Explicit: "ledger silence is NOT evidence".
- Two anti-patterns added: never diagnose without the Phase 0 search; never report a ledger entry as diagnosis without re-validating it.

### Step 7: Verifier Phase 6 (write path) — riskiest
- **File:** `.claude/agents/verifier.md` — **Modify** (ops id `agent-verifier`, 3 edits)
- New `## Phase 6: Record the Issue in the Knowledge Ledger (PASS only)` before `## Anti-Pattern Penalties`: score with the skill's rubric, then the exact `record` invocation; exit 1 is a normal outcome reported in one line.
- Decision-Logic PASS branch points at Phase 6. Read-only boundary restated: this one invocation writes only under `.claude/knowledge/issues/`.
- Two anti-patterns added: never pass `--verified` on RETRY/FAIL; never record for a change that fixed no diagnosed bug.

### Step 8: CHANGELOG
- **File:** `CHANGELOG.md` — **Modify** (ops id `changelog`) — one entry under `[Unreleased] → Added` covering storage, gate, read path, hygiene, and the out-of-scope note.

### Step 9: Installer ships the ledger contract doc
- **File:** `install.sh` — **Modify** (ops id `install-ledger-readme`, 1 edit)
- Full mode already copies `.claude/skills/*/` and `operations/scripts/*.py|*.json`, but nothing copies `.claude/knowledge/issues/README.md`, so a fresh full install shipped the ledger script and the SKILL.md doc without the entry-format contract.
- Adds a guarded copy immediately after the `print_ok "$SKILL_COUNT skills installed"` line, using the same idiom as the neighbouring skills-registry copy (`if [[ -f ... ]]` → `mkdir -p "$DEST/knowledge/issues"` → `cp` → `print_ok`). Bash 3.2/macOS-safe, no new dependency, no behavior change when the source file is absent.

### Step 10: Backlog
- **File:** `.ai/BACKLOG.md` — **Modify** (ops id `backlog`, 2 edits) — P3 gains "Issue-ledger hygiene" on the existing sweep cadence; Icebox gains cross-project promotion (with its redaction/provenance preconditions).

---

## Ops config

`.claude/plans/ops-issue-ledger.json` — **10 operations** (3 `file_create`, 7 `code_edit`, 0 `file_delete`).
Validator verdict: **APPROVED**, two informational warnings, both expected:
- parent dir `.claude/knowledge/issues` does not exist yet — the executor creates it (`execute-json-ops.py:353`);
- duplicate filename `SKILL.md` across two paths — that *is* the Claude/Codex mirror pair, deliberate.

Dry run: `Operations: 10 total` — all ten `"success": true`.

---

## Testing / verification strategy

```bash
python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-issue-ledger.json
python3 .claude/operations/scripts/execute-json-ops.py .claude/plans/ops-issue-ledger.json --dry-run
python3 -m pytest tests/test_knowledge_ledger.py -q     # new behavioral suite
python3 -m pytest tests/ -q                             # full suite, no regressions
ruff check src/ tests/ scripts/
mypy
python3 scripts/gen-docs.py --check                     # expect no count drift (no new .sh hook)
python3 scripts/gen-registry.py --check
shellcheck install.sh .claude/hooks/*.sh                # unchanged; shellcheck may be absent locally
ck doctor --strict
```

End-to-end smoke (executed against a scratchpad copy of the script — every exit code below was observed, not assumed):

| Command | Observed |
|---|---|
| `record …` without `--verified` | rc 1, "written only at the Verifier PASS checkpoint" |
| `record … --reusability 3 --novelty 2 --verified` | rc 1, "5 < 10 (continuous-learning rubric: skip)" |
| `record … --reusability 7 --novelty 8 --verified` | rc 0, entry written with all six frontmatter keys |
| duplicate signature, different slug | rc 1, "already recorded in null-deref.md" |
| `--slug ../../escaped` | rc 2, nothing written |
| config `min_combined_score: 20`, score 15 | rc 1, "15 < 20" |
| config `min_combined_score: 4`, score 5 | rc 0, recorded |
| malformed `config.json`, score 15 | rc 0 (fallback 10, no crash) |
| no `config.json` at all, score 9 | rc 1, "9 < 10" |
| `--files 'src/a[0].py'` / `'src/we"ird.py'` / newline-injected | rc 2 each, nothing written |
| `--files 'src/a.py, src/b.py'` | rc 0, line is exactly `files: [src/a.py, src/b.py]`; `prune` reports stale when both are gone and clean when both exist |
| `search AttributeError NoneType items` | rc 0, score 9, root cause printed |
| `search kubernetes ingress certificates` | rc 3, "no match - diagnose from scratch" |
| `prune` with live file / with dead file / `--apply` | rc 0 clean / rc 1 report (file untouched) / rc 0 archived |

## Rollback plan

- Ops engine writes timestamped backups; `python3 .claude/operations/scripts/restore-backup.py` reverts the seven edited files (including `install.sh`).
- The three created files (`knowledge-ledger.py`, ledger `README.md`, `tests/test_knowledge_ledger.py`) are new and unreferenced elsewhere — `git checkout -- .` / deleting them fully reverts.
- No data migration, no schema, no dependency: rollback is total and leaves no residue beyond an empty `.claude/knowledge/` directory.

## Risk assessment

**Low**
- New script is additive; nothing imports it, so no blast radius on the ops engine.
- No new `.sh` hook → hook count stays 19 → docs-drift gate untouched.
- `install.sh` already globs `operations/scripts/*.py`; packaging tests assert existence, not an exhaustive list. The added ledger-README copy is guarded by `[[ -f ... ]]`, so it is a no-op when the file is absent and cannot break an install.
- Config read is fail-safe: every failure mode falls back to 10, and no `continuous_learning` key exists today, so day-one behavior is byte-identical to the previously reviewed constant.
- Codex mirror edit touches a tree that is not shipped, not packaged, and not imported — worst case it is stale prose, and Step 3 now asserts against that.

**Medium**
- *Prompt-enforced write.* The Verifier "remembering" Phase 6 is not mechanical. Mitigation: the gate lives in the script (refuses unverified/low-score/duplicate), so a missed write costs a lost lesson, never a wrong one; wiring tests pin the instructions in both agent files.
- *Stale entries mislead.* Mitigation: debugger Phase 0 step 3 mandates re-validation before reporting, "ledger silence is not evidence", and `prune` archives entries whose files are all gone.
- *Ledger noise.* Mitigation: rubric ≥ 10 plus duplicate-signature refusal.
- *Threshold now user-tunable.* Someone could set it to 0 and flood the ledger. Accepted: it is opt-in configuration in a file the project owns, the duplicate-signature and `--verified` gates still apply, and the alternative (a constant contradicting its own documentation) is the defect being fixed.

**High**
- *Erosion of the Verifier's read-only contract* (Step 7). Mitigation: the write is a single script invocation confined to `.claude/knowledge/issues/`, conditioned on PASS, restated in the agent's anti-pattern list, and enforced script-side by `--verified`. If review judges this unacceptable, the fallback is to move the `record` call into GitOps' pre-commit step (same checkpoint, one hop later) — noted here rather than chosen unilaterally.

## Follow-ups (not in this plan)

- Cross-project promotion to `~/.claude/skills/learned/` (Icebox; needs redaction + provenance).
- Codex **agent** wiring: `.codex/agents/debugger.toml` Phase 0 + `verifier.toml` Phase 6, once a `.codex/operations/` tree exists to host the script.
- `/learn --ledger` surface for manual inspection.
- Making the Verifier write mechanical once task 010's eval framework lands.

---

## Revision notes

### Round 3 (this revision) — 1 MINOR finding from the 95/100 APPROVED review

1. **The installer never shipped the ledger README.** `install.sh` copies skills
   (`.claude/skills/*/`) and ops scripts (`operations/scripts/*.py|*.json`), so a fresh
   full-mode install got `knowledge-ledger.py` and the updated `continuous-learning/SKILL.md`
   but not `.claude/knowledge/issues/README.md` — the entry-format contract created by op
   `ledger-readme`. Cosmetic (the directory and entries self-materialize on first `record`),
   but fixed properly: new op **`install-ledger-readme`** adds a guarded copy in the full-mode
   block, immediately after `print_ok "$SKILL_COUNT skills installed"`, mirroring the existing
   skills-registry idiom (`if [[ -f ... ]]` / `mkdir -p` / `cp` / `print_ok`). Bash 3.2 and
   macOS safe, no new dependency, no-op when the source file is missing.
   *(Ops count 9 → 10. Nothing else changed; Round 2 notes below stand as approved.)*

### Round 2 — 3 MINOR findings from the 93/100 APPROVED review

1. **`min_combined_score` was illustrative-only.** The skill documented the key while the script
   hardcoded `MIN_COMBINED_SCORE = 10`, so the two could drift. Fixed by making it a real config
   read (`min_combined_score()` → `.claude/hooks/config.json`, fallback 10 on missing file /
   bad JSON / missing key / non-int), threading the value through `render_entry()`, updating the
   skill + ledger README wording, and adding five behavioral tests. No comment-only patch.
   *(Ops: `ledger-script`, `ledger-readme`, `ledger-tests`, `skill-continuous-learning`.)*
2. **The `.agents/` Codex mirror was unacknowledged.** Verified from repo evidence — it is
   git-tracked, 75-for-75 with `.claude/skills/`, differs only by name substitution, and prior
   approved plans edit both copies in one ops.json (a past review round explicitly caught a
   half-applied mirror). So it is **synced**, not scoped out: new op
   `skill-continuous-learning-codex-mirror` applies the same three edits with `.Codex/` paths,
   plus a test that pins the mirror. Codex *agent* wiring is explicitly scoped out with its
   reasoning, in Context and Follow-ups.
3. **`--files` could corrupt the frontmatter that `prune` parses back.** Fixed on write:
   `parse_files()` rejects tokens containing `[`, `]`, `,`, quotes or newlines with exit 2, so
   `split_files()` can never misparse a `files:` line into archiving a live entry. Four tests
   cover bracket, quote, newline-injection, and exact round-trip serialization.
   *(Ops: `ledger-script`, `ledger-tests`, both skill copies.)*

Ops count 8 → 9 (round 2), 9 → 10 (round 3). Scope, architecture, and the approved design are otherwise unchanged.

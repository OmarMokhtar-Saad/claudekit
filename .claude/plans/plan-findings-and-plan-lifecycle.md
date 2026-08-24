# Implementation Plan: Findings Lifecycle + Derived Plan Index

**Goal:** one place to answer *what is broken, is it fixed, and which plan closes it* — and, for the 79 plans in `.claude/plans/`, *which are done, in flight, or never started* — without inventing a second tracker beside the machinery this repo already ships.

**Approach:** two lanes, both additive.
- **Lane A** — teach the *existing* `knowledge-ledger.py` an **open** state, so a finding can land at discovery time instead of only at the Verifier PASS checkpoint. Storage, retrieval, prune and the debugger Phase 0 pull are unchanged.
- **Lane B** — a new `scripts/gen-plan-index.py` that **derives** each plan's lifecycle state from evidence already on disk (ops.json presence, review records, git trailers) and writes a generated `.claude/plans/INDEX.md`, gated by `--check` like the repo's three other generators.

**Riskiest step:** Lane A Op 3 — `record` must keep its write gate. The whole value of the ledger is that `fixed` means *verified*. Adding `open` must not become a back door that lets an unverified entry be written as fixed.

---

## Why this shape (what exploration established)

| Finding | Consequence for this plan |
|---|---|
| `knowledge-ledger.py` already implements storage, keyword search, a write gate, `list` and `prune` over `.claude/knowledge/issues/<slug>.md` | Do **not** build a findings tracker. Extend this one. |
| The ledger is **empty** (only `README.md`) despite shipping | Its sole writer is `record`, gated on `--verified` at the Verifier PASS checkpoint — and CLAUDE.md's Token & Model Policy says the verifier **never auto-runs**. The gate is not wrong; it just has no upstream. `open` supplies one. |
| `record` refuses without `--verified` (rc 1) and below the combined rubric score (rc 1) | Both gates stay exactly as they are. `open` is a *different subcommand* with its own contract, not a flag that relaxes `record`. |
| `parse_entry()` ignores unknown frontmatter keys and never raises | New keys (`status`, `origin`, `plan`) are backward compatible by construction: old entries parse fine and default to `fixed`. |
| `prune` archives an entry only when **every** referenced file is gone, and never on absent data | An `open` finding whose files all vanished is a real signal, not garbage — prune must report it, not silently archive an unfixed bug. |
| `reflection.py`'s ledger is session-scoped, privacy-digested, and deliberately stored **outside the repo** under `$TMPDIR`, "never inside the repo and never inside the transcript" | Findings must **not** go there. That ledger is ephemeral failure fingerprinting by design; durable project findings belong in `.claude/knowledge/issues/`. Do not couple the two. |
| `execute-json-ops.py` writes backups to `backups/<plan>-<timestamp>/manifest.json`, which is **gitignored** | Backup manifests are a *local* execution hint, never durable proof. Lane B must not treat their absence as "not executed". |
| `review-record.py check` already returns a 4-way typed verdict (0 approved+matching, 2 drift, 3 no record, 4 not authorising) | Lane B calls it rather than re-deriving approval — one source of truth for verdicts. |
| `.ai/TECH_DEBT.md` (19 rows) and `.ai/AGENTS_KNOWN_ISSUES.md` (15+ numbered items) are hand-maintained prose | Both stay. Lane A gives them a mechanical destination; migration is a **follow-up**, not this plan. |
| `gen-docs.py --check` / `gen-registry.py --check` / `gen-model-policy.py --check` are the established gate shape | `gen-plan-index.py` copies it exactly, including the drift-report format and exit 1. |
| `install.sh` copies `operations/scripts/*.py` wholesale | Lane A ships to consumer projects with no installer change. Lane B is a repo-dev generator under `scripts/`, which is **not** installed — correct, it is maintainer tooling. |
| `.agents/skills/continuous-learning/SKILL.md` is a git-tracked Codex mirror of the Claude copy | Any substantive skill edit lands in **both** copies (the mirror-rot defect this repo has already reviewed for). |

---

## Scope

**In scope**
- Lane A: `status` / `origin` / `plan` frontmatter; `open` subcommand; `record` transitions `open → fixed`; `list` filters; `search` and `prune` surface status; behavioral tests.
- Lane B: `scripts/gen-plan-index.py` with `--check`; generated `.claude/plans/INDEX.md`; a `Plan-Id:` commit trailer convention; behavioral tests.
- Docs: `.claude/knowledge/issues/README.md` entry contract, `continuous-learning/SKILL.md` (**both** corpora), `debugger.md` Phase 0 note that a match may be `open`, CHANGELOG `[Unreleased]`, `.ai/CHANGELOG_AI.md`, `.ai/SESSION_STATE.md`.

**Out of scope (explicit)**
- Migrating TECH_DEBT / KNOWN_ISSUES rows into the ledger — follow-up, owner-gated (it is a user-visible content move).
- Emitting findings events into `.claude/runtime/events/` — that is the enforcement-runtime lane BACKLOG P0.7 already owns. Do not fork it.
- Any new blocking hook, any auto-injection of ledger content into context, any cross-project promotion to `~/.claude/skills/learned/`.
- Backfilling `Plan-Id:` trailers across 79 legacy plans — they resolve as `legacy`, see Lane B.
- Codex *agent* wiring (`.codex/agents/*.toml`), consistent with the ledger v1 plan.

---

## Lane A — the ledger learns `open`

### Entry contract (additive)

```markdown
---
signature: "reviewer agent has no Bash, so a verdict cannot gate execution"
root_cause: "..."          # required for fixed; "" while open
fix: "..."                 # required for fixed; "" while open
files: [.claude/agents/reviewer.md]
date: 2026-08-24
status: open               # open | fixed | wontfix | regressed
origin: workflow           # code | workflow | project
plan: plan-agent-tool-grants   # optional; the plan that closes this
verified: false
---
```

- `status` absent → **`fixed`** (every existing entry carries `verified: true`; this is the only reading that keeps history honest).
- `verified: true` is written **only** by `record`. `open` always writes `verified: false`.
- `origin: workflow` is the lane the repo has nowhere to put today — bad agent routing, hook misfires, phantom agents.

### Operations

| # | Op | File | What |
|---|---|---|---|
| 1 | edit | `knowledge-ledger.py` | `render_entry()` → `render_open()` + `render_fixed()`; both emit the full key set. `scalar()` applies to every free-text value, unchanged. |
| 2 | edit | `knowledge-ledger.py` | New `cmd_open`: requires `--slug`, `--signature`, `--origin`; optional `--plan`, `--severity`, `--files`, `--date`. **No** `--verified`, **no** rubric score. Reuses `SLUG_RE`, `parse_files()` and the duplicate-signature refusal verbatim. Refuses (rc 1) if the slug exists with `status: fixed` — reopening is `--reopen`, which writes `status: regressed`. |
| 3 | edit | `knowledge-ledger.py` | `cmd_record` keeps **both** gates (`--verified` required, combined ≥ threshold) and additionally: if the target exists with `status: open`, overwrite it in place carrying `origin`/`plan` forward, and log `open → fixed`. Existing `--force` semantics untouched. This is the riskiest op — the two refusals must survive intact. |
| 4 | edit | `knowledge-ledger.py` | New `cmd_close --status wontfix --reason ...` for a finding deliberately not fixed. Requires `--reason`; never sets `verified: true`. |
| 5 | edit | `knowledge-ledger.py` | `cmd_list` gains `--status` / `--origin` filters and prints a status column; `cmd_search` prints status per hit so the debugger's Phase 0 can tell "known and fixed" from "known and still open" — a different conclusion for the caller. |
| 6 | edit | `knowledge-ledger.py` | `cmd_prune`: entries with `status: open` are **excluded** from the archive set and listed under a separate `STALE-OPEN` heading. Rationale: archiving an unfixed finding because its files moved is exactly the silent-failure shape this repo audits for. Exit code stays 1 when anything needs attention. |
| 7 | edit | `.claude/knowledge/issues/README.md` | Document the new keys, the state machine, and the `open`-vs-`record` gate split. |
| 8 | edit | `.claude/skills/continuous-learning/SKILL.md` **and** `.agents/skills/continuous-learning/SKILL.md` | Third trigger: open a finding at discovery. Same rubric — the rubric gates `fixed`, never `open`. |
| 9 | edit | `.claude/agents/debugger.md` | Phase 0: a match with `status: open` means *known, unfixed* — report the finding and its `plan:`, do not re-diagnose. |

### State machine

```
        open ──record(--verified, score≥T)──> fixed
         │                                      │
         └──close --status wontfix──> wontfix    └──open --reopen──> regressed ──record──> fixed
```

Nothing reaches `fixed` except through `record`. That invariant is the plan.

---

## Lane B — derived plan index

### Derivation (evidence, in precedence order)

| State | Mechanical evidence |
|---|---|
| `not_started` | `plan-<slug>.md` exists; no ops.json anywhere |
| `planned` | ops.json exists (`ops-<slug>*.json` or `ops-<slug>/`, incl. `archive/`); `review-record.py check` → rc 3 |
| `revise` | `check` → rc 4 (record exists, verdict does not authorise) |
| `approved` | `check` → rc 0 |
| `drifted` | `check` → rc 2 — **loud**: ops.json changed after approval |
| `executed` | a commit exists whose message carries `Plan-Id: <slug>` |
| `legacy` | in `archive/` with no `Plan-Id:` commit — pre-convention, state unknowable |

- Ordering matters: `drifted` and `revise` must never be reported as `approved`.
- `backups/` manifests are read as an **advisory** local hint only, printed as `(local run detected)`, never as `executed`. They are gitignored; treating them as proof would make the index lie on a fresh clone.
- `legacy` is deliberate. Inventing a state for the 79 existing plans would be exactly the "generated index outranks current files" inversion CLAUDE.md forbids.

### Operations

| # | Op | File | What |
|---|---|---|---|
| 10 | create | `scripts/gen-plan-index.py` | Stdlib-only, py3.9. Derives the table above; `--check` exits 1 on drift with a per-row report; default run rewrites `INDEX.md`. Shells out to `review-record.py check` and `git log --format=%B` (one call, parsed in-process — not one git call per plan). |
| 11 | create | `.claude/plans/INDEX.md` | Generated. Carries the same "generator-owned, never hand-edit" header the other generated artifacts use. |
| 12 | edit | `CLAUDE.md` | Commit convention gains `Plan-Id: <slug>` beside the existing `Co-Authored-By:` line, and the Commands block gains `gen-plan-index.py --check`. |
| 13 | edit | `.github/workflows/*` | Add `gen-plan-index.py --check` to the same job as the other three `--check` gates. |

---

## Tests (behavioral, per CLAUDE.md)

`tests/test_knowledge_ledger.py` (extend) — every one asserts an outcome, not a structure:
1. `open` writes `status: open`, `verified: false`, and **no** score fields.
2. `record` on that slug flips it to `fixed`, `verified: true`, preserving `origin` and `plan`.
3. **`record` without `--verified` still exits 1 after Lane A** — the gate did not erode.
4. **`record` below the rubric threshold still exits 1** — same.
5. An entry with **no** `status` key reads as `fixed` (backward compat over the real corpus shape).
6. `search` on an open finding exits 0 and its output names the status.
7. `prune --apply` with an `open` entry whose files are all gone **does not** archive it, exits 1, names it under `STALE-OPEN`.
8. `open` on a slug already `fixed` exits 1; `--reopen` yields `regressed`.
9. `close --status wontfix` never yields `verified: true`.
10. Duplicate-signature refusal still fires across `open` and `record`.

`tests/test_plan_index.py` (new):
11. A fixture plan with no ops.json → `not_started`.
12. ops.json + an APPROVED record → `approved`; mutate ops.json after → `drifted` (mutation proof, per the verification-gap lens).
13. A `Plan-Id:` commit in a throwaway git repo → `executed`.
14. `--check` exits **1** when `INDEX.md` is stale and **0** right after a regen.
15. A gitignored `backups/` manifest alone never produces `executed`.

Plus the full suite green: `pytest -q`, `ruff`, `mypy`, all four `--check` gates, `shellcheck`, `ck doctor --strict`.

---

## Risks

| Risk | Mitigation |
|---|---|
| **The `fixed` gate erodes** — `open` becomes the easy path and everything sits unverified | Tests 3 and 4 pin both refusals; `verified: true` has exactly one writer. Accept that `open` entries accumulate — an honest open list beats an empty ledger. |
| `INDEX.md` is treated as authoritative and rots | Generator-owned header + `--check` in CI; CLAUDE.md's evidence-precedence rule already ranks generated indexes below current files. |
| `Plan-Id:` trailer is forgotten | Mechanically visible: the plan shows `approved`, never `executed`. That asymmetry is the reminder. Optional follow-up: a `Stop`-hook nudge. |
| Third tracker beside TECH_DEBT / KNOWN_ISSUES | Consciously accepted for one cycle; migration is the named follow-up, and a TECH_DEBT row records the deferral with its exit condition (that register's own rule). |
| Scope creep into the enforcement-runtime lane | Events are explicitly out of scope. |

## Follow-ups (not this plan)

- Migrate TECH_DEBT + KNOWN_ISSUES rows into the ledger as `open` findings — owner sign-off, user-visible.
- Emit `finding_opened` / `plan_executed` into `.claude/runtime/events/` once the enforcement-runtime lane lands its dispatcher; unblocks BACKLOG P0.7 mechanical DoD.
- `ck findings` / `ck plans` CLI surface once the frontmatter contract has settled.
- Codex agent wiring.

## Sequencing

Lane A and Lane B touch **disjoint files** — `knowledge-ledger.py` + skills/agents vs `scripts/` + `INDEX.md` + CI. They can be two PRs in parallel, or A first if you want the findings home before the plan index. One ops.json each; per the blast-radius tiering both are **Tier 2** (multi-file, no security/schema surface), so planner + ops.json, and each gets one adversarial `code-reviewer` diff review before merge.

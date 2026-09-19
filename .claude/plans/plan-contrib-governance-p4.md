# Plan: contrib-governance P4 — repo-scoped files, and skill-gap intake (C4 + C5)

Phase 4 of [plan-contrib-governance.md](plan-contrib-governance.md). Ops config:
`.claude/plans/ops-contrib-governance-p4.json` (5 operations, 0 deletions). Run after
Phase 3 — the second hard rule added here names the gate Phase 3 creates.

## C4 — repo-scoped files are not user assets

The upstream CONTRIBUTING forbids telling users to copy the repository's own
`CLAUDE.md`/`AGENTS.md` into their projects; only `skills/` is reusable. This repo states
the same thing in one clause of CLAUDE.md's header, which is easy to miss and easy to
regress — and the stakes are higher here, because `ck fleet update` physically copies
assets into 14+ downstream projects. A maintainer file that leaks downstream carries hard
rules about *our* hooks, *our* gates and *our* release process into a codebase where they
are simply false.

**Decision: maintainer-only, promoted to a numbered hard rule in `.ai/KNOWLEDGE_BASE.md`,
and deliberately not shipped.** Shipping a rule about *this repository's own files* into
user projects would be the exact category error the rule forbids. The enforcement that
already exists is structural: fleet sync only carries what lives under `.claude/`, and
`CLAUDE.md`/`.ai/` do not.

The same operation adds the C3 rule as hard rule 12, so the list matches the gates.

## C5 — structured skill-gap intake

Upstream's issue form asks four things: the affected skill, the offending excerpt, the
project context, and what the user did instead. This repo already has the receipt path:
`.claude/knowledge/issues/` written by `knowledge-ledger.py open`. It has no `skill-gap`
origin and no form, so a skill that misfires is reported as prose in a session and
forgotten.

**Small by design: one new `ORIGINS` value plus one template. No new subsystem**, no new
command, no second store (task 008).

The template lives at `.claude/knowledge/TEMPLATE-skill-gap.md`, one level *above*
`issues/`, so the ledger's own scans can never mistake the form for an entry.

## Tasks

### T1 — two hard rules

- **File:** `.ai/KNOWLEDGE_BASE.md`
- **Action:** `code_edit` (`add_after` item 10 of "Things future models must NEVER
  change", payload carries its own leading newline)
- **Details:** rule 11 (repo-scoped files are not user assets, with the fleet-sync
  reason) and rule 12 (write the procedure, not the workaround, naming
  `scripts/check-prompt-model-names.py`).
- **Done when:** both appear in the numbered list and name their enforcement.

### T2 — a `skill-gap` origin

- **File:** `.claude/operations/scripts/knowledge-ledger.py`
- **Action:** `code_edit`, one edit to the `ORIGINS` tuple
- **Details:** `("code", "workflow", "project")` → `(..., "skill-gap")`. `DEFAULT_ORIGIN`
  is untouched; an unknown origin is still refused by argparse, which one test asserts.
- **Done when:** `knowledge-ledger.py open --origin skill-gap ...` is accepted and
  `--origin nonsense` is still refused.

### T3 — the four-field form

- **File:** `.claude/knowledge/TEMPLATE-skill-gap.md` (new)
- **Action:** `file_create`
- **Details:** the four fields, the exact `knowledge-ledger.py open --origin skill-gap`
  invocation, and the rule that the excerpt is quoted verbatim — a paraphrase of a prompt
  line cannot be grepped back to the file that produced it. Ships to the fleet
  (it is under `.claude/`), which is intended: a skill gap is reported by whoever hits
  it, downstream included.
- **Done when:** the file names all four fields and the command.

### T4 — tests

- **File:** `tests/test_skill_gap_intake.py` (new)
- **Action:** `file_create`
- **Details:** subprocess, temp tree. Covers: a `skill-gap` receipt is written and
  records that origin; an unknown origin is still refused (the negative control — a
  widened enum that accepts anything is not a widened enum, it is a removed check); the
  template names its four fields and the exact command; and the template is not visible
  to the ledger as an entry.
- **Done when:** `python3 -m pytest tests/test_skill_gap_intake.py -q` passes.

### T5 — CHANGELOG

- **File:** `CHANGELOG.md`
- **Action:** `code_edit` (`add_after` `## [Unreleased]`, leading newline in payload).
  C5 only — C4 is maintainer-only and not user-visible.

## Files touched

- `.ai/KNOWLEDGE_BASE.md`
- `.claude/operations/scripts/knowledge-ledger.py`
- `.claude/knowledge/TEMPLATE-skill-gap.md`
- `tests/test_skill_gap_intake.py`
- `CHANGELOG.md`

## Acceptance criteria

1. `python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-contrib-governance-p4.json` → PASS.
2. `python3 -m pytest tests/ -q` → zero failures. **Watch for an existing test that
   asserts `ORIGINS` has exactly three members** — if one exists, update it in the same
   commit; it is a real assertion about the enum, not a nuisance.
3. `python3 scripts/gen-docs.py --check` and `python3 scripts/gen-registry.py --check`
   clean. A new file under `.claude/knowledge/` should not move any component count; if
   it does, run the generator — never hand-edit.
4. `ruff check .claude/operations/scripts/ tests/` and `mypy` clean.
5. Proven able to fail: `knowledge-ledger.py open --origin skill-gap` must exit non-zero
   if the `ORIGINS` edit is reverted. Check by hand once and record it in the commit body.

## Owner-run step (not part of this plan's execution)

After all four phases are committed and green, the owner may distribute the shipped half
(C1's machinery and store README, C2's skill prose, C5's template and origin) with
`ck fleet update --yes` followed by `ck fleet verify`, **excluding `qa-agents`** — that
project carries six hardened scripts a fleet update overwrites. C2's CI half, C3 and C4
are maintainer-only and must not be pushed downstream.

## Rollback

`git revert` the phase commit. Any `skill-gap` receipt already written stays on disk and
becomes an entry with an origin the enum no longer lists; the ledger reads it fine, and
`--origin` only gates writes.

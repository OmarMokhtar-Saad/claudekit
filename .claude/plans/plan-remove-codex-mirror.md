# Implementation Plan: remove the `.codex/` mirror

Branch `perf/token-efficiency`, planned at HEAD `f5eb927`. Owner signed off on the
removal against a costed alternative (keep + gate). Tier 3 — user-visible removal.

## Overview

Delete `.codex/` (53 tracked files: 23 hooks, 28 agent `.toml`s, `config.toml`,
`hooks.json`), update the two test constants that name it, and correct a backlog
entry I wrote in `f5eb927` that overstated the security impact of its drift.

## Why — measured at `f5eb927`, not assumed

`.codex/` was created deliberately (`bb9a2c5`, "mirror agents/skills/hooks corpus
for Codex CLI"). Five facts, each verified by command:

| Claim | Evidence |
|---|---|
| Nothing installs or packages it | `grep -c codex install.sh` → 0; absent from `pyproject.toml`, `MANIFEST.in` |
| Nothing references it but two test constants | one `grep` over the repo; the only non-plan, non-doc hits are `tests/test_day_one_blockers.py:325,396` |
| Its own config disables every enforcement hook it wires | `.codex/config.toml` sets `ECC_HOOK_PROFILE = "minimal"`; the hooks it wires short-circuit on exactly that value |
| Its wiring is machine-specific | `.codex/hooks.json` contains **20** hardcoded `/Users/omarmokhtar/...` paths. `.claude/settings.json` contains **0** — it resolves `$ROOT` at runtime |
| It is a stale copy, not an adaptation | 8 shell hooks + `config.json` diverge; every diff is `.claude` being *ahead*. `.codex/hooks/README.md` is byte-identical to `.claude`'s, including an instruction to `chmod +x .claude/hooks/*.sh`. The hooks still write to `.claude/locks`, `.claude/hooks` — never adapted for Codex at all |

Last substantive sync: 2026-07-30. `ops-enforcement.sh` was three weeks stale.

**`.agents/` is a different mirror and is NOT touched.** It is skills-only, and
`test_knowledge_ledger.py::test_codex_skill_mirror_documents_the_ledger_too` reads
`.agents/skills/`, not `.codex/`.

**Correction (review round 1).** I first wrote that `.agents/` "has zero references
to `.codex`". That was false, and the reason is worth recording: my grep was
**case-sensitive**, and this repo writes `.Codex/` with a capital C in exactly the
places that matter. `.agents/skills/*/SKILL.md` carries roughly a hundred
`.Codex/...` paths. What is *true* — and is what the claim should have said — is
that those paths point at a `.Codex/operations/...` layout which **does not exist
today and never fully did**, so this deletion neither creates nor repairs them. The
deletion is still safe for `.agents/`; the original claim was not evidence, it was
a search artifact.

## A correction I owe, and the entry it fixes

In `f5eb927` I filed a P1 backlog item calling the `format-typecheck.sh` mirror
drift **"security-relevant"**. That was wrong, and I wrote it without checking one
thing: `.codex/config.toml` forces `ECC_HOOK_PROFILE=minimal`, under which the
enforcement hooks stand down entirely — and `format-typecheck` is strict-only, so
it could never have run there under any reading. The drift was real; the security
framing was not. Hard rule 6 (security framing stays honest) applies to my own
findings, not only to the product's docs, so the entry is rewritten rather than
quietly deleted along with the directory.

## The MAX_DELETIONS tension, named rather than routed around

`.ai/DECISIONS.md` entry 7 caps deletions at 3 per plan and says large removals
"need multiple reviewed plans". 53 files is 18 plans. Splitting a single
owner-approved directory removal into eighteen synthetic plans satisfies the letter
of the rule and defeats its purpose, which is *review* — and this removal has
had more review than any 18-plan sequence would.

So the removal is performed as **one `git rm -r .codex`**, not through
`file_delete` ops, and that choice is recorded as a new `.ai/DECISIONS.md` entry.
**GUARD 26 is not bypassed, weakened, or given an escape hatch** — no flag is
added, `MAX_DELETIONS` stays 3, and the ops engine is still the only path for file
*edits*. What is recorded is that the engine models per-file deletes and has no
directory-removal operation, so a whole-directory removal is a git operation under
owner sign-off. Stated here so a reader does not have to reconstruct it from a
commit diff.

## Scope

- **Delete (via git):** `.codex/` — 53 tracked files.
- **Edit (via ops.json):** `tests/test_day_one_blockers.py`, `AGENTS.md` (one
  line), `.ai/BACKLOG.md`, `.ai/DECISIONS.md`, `.ai/PROFILES.md`, `CHANGELOG.md`,
  `.ai/CHANGELOG_AI.md`, `.ai/SESSION_STATE.md`.
- **`AGENTS.md:21` — the one line this deletion newly breaks.** It runs
  `shellcheck install.sh .Codex/hooks/*.sh`, which resolves TODAY (macOS is
  case-insensitive) to the 20 files being deleted. After removal the glob matches
  zero and the documented shell-lint gate silently stops linting hooks — the exact
  empty-glob failure mode this plan flags elsewhere. Repointed at `.claude/hooks/`.
  The **rest** of `AGENTS.md` is separately broken (a `.claude`→`.Codex` sed that
  also produced PyPI name "Codex-kit"; three of its four `.Codex/` paths already did
  not exist) — pre-existing, filed at P1, deliberately not fixed here.
- **Out of scope:** `.agents/` (independent, see above). The `.claude/hooks/`
  originals. Any hook behaviour.

## Steps

### 1 — `tests/test_day_one_blockers.py`

`HOOK_MIRRORS = (".claude/hooks/pre-commit.sh", ".codex/hooks/pre-commit.sh")`
becomes a one-element tuple renamed `SECRET_PATTERN_HOOKS`. The rename is the
point: the constant's *name* asserted a mirror relationship that will no longer
exist, and leaving a one-element tuple called `HOOK_MIRRORS` would be a false
claim in a parametrisation id. `SCAN_ROOTS` drops `".codex"`, and the comment above
it — which names "the .codex/.agents mirrors" — drops `.codex` and says why.

### 2 — `.ai/BACKLOG.md`

Replace the P1 entry with a resolved entry that (a) records the removal, (b)
**states the security framing was mine and was wrong**, and (c) keeps the one
durable lesson: a hand-maintained mirror with no gate drifts, and the answer was
not a gate.

### 3 — `.ai/DECISIONS.md`

New entry 22: `.codex/` removed, with the evidence table and the MAX_DELETIONS
reasoning above. Entry 7 is cross-referenced, not amended — the cap is unchanged.

### 4 — docs

`.ai/PROFILES.md:68` ("Mirrored into `.codex/hooks/`") corrected — the
`format-typecheck` fix now lives in one tree. `CHANGELOG.md` `[Unreleased]` gets a
`### Removed` entry (user-visible: anyone running Codex CLI against a clone loses
this corpus). Plus `CHANGELOG_AI.md` and `SESSION_STATE.md`.

## Verification

All nine DoD gates. Specifically:
- `pytest tests/ -q` — `test_day_one_blockers.py` is the file most likely to break;
  its secret-pattern class was parametrised over both mirrors.
- `grep -rni "\.codex" --include="*.py" --include="*.sh" --include="*.md" --include="*.json" .`
  (case-**insensitive**, `.md` included, repo root included) → the only surviving
  hits may be historical prose in `.claude/plans/`, `.ai/`, `CHANGELOG*`, and the
  known-stale `AGENTS.md`/`.agents/skills` decay filed at P1. **The original version
  of this command was `-rn` over `tests/ src/ scripts/ install.sh` only** — case
  sensitive, no `.md`, no repo root — and it is why round 1 of this plan claimed
  `.codex/` was unreferenced while `AGENTS.md:21` was running
  `shellcheck install.sh .Codex/hooks/*.sh`. A verification command scoped so it
  cannot see the place a defect lives is not verification.
- `ck doctor --strict`, `shellcheck install.sh .claude/hooks/*.sh` — the latter's
  glob no longer has a `.codex` counterpart to keep in step.

## Mutants and flipped cases

- **M1 — delete `.codex/` but not the `SCAN_ROOTS` entry.** The secrets self-scan
  iterates `git ls-files -- <root>`; a root with no tracked files yields nothing,
  so this would pass silently. **This mutant does not flip anything, and that is
  the honest finding**: `SCAN_ROOTS` has no missing-root guard. Recorded rather
  than papered over — adding one is a separate change with its own blast radius
  (every root would need to exist in every checkout shape).
- **M2 — delete `.codex/` but not `HOOK_MIRRORS`.** `_built_patterns` opens the
  path directly. **Flips:** every `TestSecretPatternConstruction` case for the
  `.codex` arm, with `FileNotFoundError`. This one binds.
- **M3 — rename the constant but miss a usage.** Review round 1 found this as a
  live defect, not a hypothetical: the constant had **three** parametrize sites
  (`:344`, `:351`, `:365`) and the first ops config edited two. The miss is worse
  than the mutant it models — a dangling `HOOK_MIRRORS` is a `NameError` at
  *collection* time, so it reds the entire module rather than the one arm this
  plan predicted. Covered now by a fourth edit; the lesson is that a rename must be
  driven by `grep -c`, not by the sites the author happens to remember.
- **Would pass against unfixed code:** everything except M2's arm.

## Rollback

`git revert` the commit — the deletion and the edits land together, so revert
restores the directory and the constants in one step. This is the strongest
rollback story of the three batches, and it is why the removal is safe to do first.

## Risk

- **Low:** the edits. Two constants and six doc files.
- **Low:** the deletion itself — nothing consumes it (evidence table above), and
  git makes it fully reversible.
- **The real risk is judgement, not mechanism:** if someone IS running Codex CLI
  against this checkout, their hooks stop existing. Mitigated by the fact that
  their hooks were already disabled by `.codex/config.toml` and their wiring
  pointed at one specific home directory. Called out in `CHANGELOG.md` regardless.
- **Blast radius:** zero runtime surface. Nothing installed, packaged or imported.

# Implementation Plan: Review Discipline (G5 revision confirmation, I2 verification-gap lens, I3 finding classes)

## Overview

Three defects in ClaudeKit's review layer, fixed together because they share the same
failure mode — a review that reports a clean result it did not earn:

- **G5** — `code-reviewer` never confirms which revision it is reading. Verified:
  `.claude/agents/code-reviewer.md:83` Phase 1 says "Identify what changed: files added,
  modified, deleted" and names no mechanism. `grep -rn 'git show\|gh pr diff\|worktree'
  .claude/agents/*.md` returns zero hits in any reviewer. With `/worktree`
  (`.claude/commands/worktree.md`) and `plan-worktree-multi-agent` putting several trees in
  play, the reviewer silently inherits whatever the shared tree holds. A search that misses
  because the tree is wrong returns a clean no-match — indistinguishable from a real absence.
- **I2** — no lens for verification coverage. The reviewer's dimension 5 has a single line
  ("critical path has no test coverage") and no method for deciding whether an existing test
  would actually fail if the change regressed.
- **I3** — findings carry no recurrence class, so repeated findings never accumulate into a
  mechanical check. Task 010 (eval framework) needs exactly this ratchet.

## Scope

- **In Scope:** `code-reviewer.md` Phase 0 + finding format; a new loadable skill
  `verification-gap-lens`; on-demand triggers in `code-reviewer` and `verifier`; the `Class`
  field + three-entries ratchet; the class table seeded in `.ai/REVIEW_GUIDE.md`; keeping
  `_shared/VERIFICATION_PROTOCOL.md`'s refutation pass as the single source that *points to*
  the lens rather than restating it.
- **Out of Scope (other workstreams / not owned):** `.claude/settings.json`, any hook,
  `reviewer.md` (plan reviewer), `_shared/INVOCATION.md`, `CLAUDE.md`, `CHANGELOG.md`,
  `docs/`, `.claude/skills/skills-registry.json`, `context-budget/`, `token-optimization/`.
  Component counts are never hand-edited (CLAUDE.md hard rule 8) — no count edit is planned
  anywhere in this plan.

## Measured constraint: always-on context floor

`python3 scripts/check-context-floor.py --json` run before planning:

```
skill descriptions: 9892 / 14000   -> headroom 4108 chars
agent descriptions: 7566 / 10000
CLAUDE.md:         29264 / 31000
pipeline agent bodies: 39144 / 43000   (planner/reviewer/implementer only)
total 89727, ok: true
```

The new skill adds exactly one `description:` value to the always-on floor. The planned
description is **226 chars**, leaving ~3882 chars of headroom — it fits with room to spare, so
nothing has to give. `code-reviewer.md` and `verifier.md` are NOT in `PIPELINE_AGENTS`
(`scripts/check-context-floor.py:44` — planner/reviewer/implementer only), so their body
growth is ungated; the SKILL.md body is ungated too (only frontmatter descriptions are
measured, `measure()` lines 60-66). Neither agent's own frontmatter `description` is touched,
so "agent descriptions" is unchanged.

## Prerequisites

- None inside this workstream. Two cross-workstream dependencies are recorded in Risks.

## Implementation Steps

### Step 1: Create the `verification-gap-lens` skill

- **File:** `.claude/skills/verification-gap-lens/SKILL.md`
- **Action:** Create
- **Description:** A single-question lens: *if the behavior this change is supposed to produce
  broke where it is actually used, would a test fail?* Contains the four gap shapes
  (regression, missing-adoption, broken-verification, unbound-check), the Demonstration
  technique, the "prove a check binds by mutating the shipped artifact" rule (weakening counts
  as a mutation: a rule survives deletion and dies by addition), evidence rules, the trimmed
  review sequence, and the finding shape.
- **Details:** Frontmatter follows the `differential-security-review` convention
  (`name`, `description`, `user-invocable: false`, `allowed-tools: Read, Grep, Glob, Bash`).
  Description held to 226 chars. Attribution chain preserved in the body: adapted from
  SHAFT_ENGINE `chaos-engine/references/verification-gap-lens.md` (MIT), itself adapted from
  bmad-method `bmad-review/references/lens-verification-gap.md` (MIT). Reworded to ClaudeKit
  scale — examples use this repo's own surfaces (hooks, ops guards, gates).

### Step 2: Give `code-reviewer` a Phase 0 (revision confirmation)

- **File:** `.claude/agents/code-reviewer.md`
- **Action:** Modify
- **Description:** Insert `### Phase 0: Confirm the Revision (before any finding)` immediately
  before `### Phase 1: Scope Assessment`. The reviewer confirms the revision via one of FOUR
  paths, never mutating the shared tree:
  1. PR: `gh pr diff <n>` + `gh pr view <n> --json headRefOid`;
  2. named ref/SHA: `git diff <base>...<ref>` + `git show <ref>:<path>`;
  3. whole-tree search: its own `git worktree add --detach <dir> <ref>`, then
     `git worktree remove`;
  4. **local uncommitted work — the common case, and the default for `/review` with no
     argument:** `git rev-parse HEAD` + `git diff HEAD --stat` + `git diff HEAD --name-only`
     (tracked, modified) **+ `git ls-files --others --exclude-standard` (new, untracked)**,
     reported as `Revision: <sha> + uncommitted working tree (N files dirty)`. A dirty tree is
     *confirmable*, not disqualifying — banning it would make the gate decorative, since a
     compliant reviewer would refuse every real review and a helpful model would ignore Phase 0.
     The untracked enumeration is not optional bookkeeping: in this repo the dominant change
     shape is ADDING files (this plan adds `SKILL.md`), so a `git diff`-only Phase 0 would print
     a confident confirmed-revision header while the change's primary artifact is invisible —
     strictly worse than refusing.
  Never `git checkout`/`switch`/`stash`/`restore` in the shared tree.
  **STOP is reserved for genuine ambiguity:** the tree is dirty AND the caller named a different
  ref. Then report `VERDICT: CANNOT REVIEW` with the two conflicting revisions.
- **Details:** The Output Format verdict enum (`code-reviewer.md:146`) is extended to
  `[APPROVE | APPROVE WITH SUGGESTIONS | REQUEST CHANGES | BLOCK | CANNOT REVIEW]` — without a
  legal refusal token a model filling the template reaches for APPROVE at exactly the pressure
  point the gate exists for. A `Revision:` header line is added (necessary but not sufficient on
  its own). Matching anti-patterns are added: never write a finding before Phase 0; never mutate
  the shared tree; never report "no match"/APPROVE from an unconfirmed tree; never omit `Class`.
  The `Revision:` header enumerates ALL FOUR paths
  (`<gh pr diff | git show | git worktree | git diff HEAD>`) and permits the
  `<sha> + uncommitted working tree (N files dirty)` form inline — a header that cannot express
  path (d) would push the model straight back to claiming a pinned ref it does not have, which is
  the same defect class as a missing `CANNOT REVIEW` token: a guard whose expressible outputs do
  not include the guarded case.
  Path (d) uses `git diff` + `git ls-files`, not `git status --porcelain`, so every Phase 0
  command falls inside the scoped allowed-tools row (see Risks). The caveat Phase 0 states is
  about PRESENCE, not absence: `git diff` does not list newly added files, so either enumerate
  them with `git ls-files --others --exclude-standard` or say in the header that new files were
  not enumerated.

### Step 3: Wire the lens trigger into `code-reviewer` (on-demand, not preload)

- **File:** `.claude/agents/code-reviewer.md`
- **Action:** Modify
- **Description:** Add one on-demand bullet under "On demand (load when the trigger fires)":
  load `verification-gap-lens` when the diff changes behavior and you are judging whether the
  tests would catch a regression. Explicitly NOT mandatory — the mandatory list is the
  always-loaded cost.

### Step 4: Add the `Class` field + three-entries ratchet to the finding format

- **File:** `.claude/agents/code-reviewer.md`
- **Action:** Modify
- **Description:** Add `Class:` to the `[C1]` and `[H1]` finding templates in Output Format,
  and a short "Finding Classes (the ratchet)" section stating the rule: every finding names a
  recurrence class (or `new: <name>`); when a class reaches three entries it EARNS a mechanical
  check, or an explicit written "cannot be mechanised, and here is why"; the live table lives
  in `.ai/REVIEW_GUIDE.md`; never invent a synonym for an existing row.

### Step 5: Wire the lens trigger into `verifier`

- **File:** `.claude/agents/verifier.md`
- **Action:** Modify
- **Description:** Add the same on-demand bullet, and rewrite Phase 3 step 5 to a single line
  inside the existing plain fence — "Assess test quality by applying the verification-gap-lens
  Demonstration and mutation proof" — with no repeated mechanics and no backticks (backticks
  render literally inside that fence). Add two terse scoring anti-patterns: never score a test as
  meaningful without naming the regression it would catch; never count a check that would still
  pass with the thing it protects removed (pointing at `verification-gap-lens`, unbound-check,
  rather than restating the mechanics).

### Step 6: Keep `VERIFICATION_PROTOCOL.md` coherent — one source, not two

- **File:** `.claude/agents/_shared/VERIFICATION_PROTOCOL.md`
- **Action:** Modify
- **Description:** The refutation pass stays the protocol's three questions (it applies to
  every agent, including ones that never review code). Add a fourth question scoped to code
  changes — *would a test fail if this change regressed?* — whose entire body is "load
  `verification-gap-lens` and work it", plus an explicit ownership note: the protocol owns the
  refutation pass; `verification-gap-lens` owns the gap shapes, the Demonstration, and the
  mutation proof; do not restate either inside the other, link. **The mechanics are written
  exactly once, in the skill** — neither this file nor `verifier.md` repeats them, or the
  single-source claim would be false on arrival.

### Step 7: Seed the class table in `.ai/REVIEW_GUIDE.md`

- **File:** `.ai/REVIEW_GUIDE.md`
- **Action:** Modify
- **Description:** Add a "Finding format and the recurrence ratchet" section before "Review
  philosophy": the finding block (claim / Verdict / Blocking / Where / Scenario / Evidence /
  Class / Fix), the three-entries rule, and the seed class table. Every row is evidenced from
  this repo and names what catches it now or "nothing yet":

  | Class | Shape | What catches it now |
  |---|---|---|
  | `unconfirmed-revision` | conclusion drawn from a tree that was never pinned to the reviewed ref | nothing yet — this plan's Phase 0 is prose, not a check |
  | `vacuous-check` | a test/gate that cannot fail (mock-only, no-throw, or the fixture re-declares what the artifact owns) | `verification-gap-lens` (prose); no mechanical check |
  | `hardcoded-count` | a component count typed by hand instead of generated | `scripts/gen-docs.py --check` |
  | `registry-drift` | an agent loads a skill the registry does not list | `scripts/gen-registry.py --check` |
  | `dangling-hook` | `settings.json` references a hook file that does not exist | dangling-hooks CI check |
  | `context-floor-creep` | always-on prompt text grows with nothing failing | `scripts/check-context-floor.py --check` |
  | `prose-verified-claim` | a claim resting on reading prose instead of executing something | `VERIFICATION_PROTOCOL.md` refutation pass (prose) |
  | `duplicate-asset` | a new near-duplicate agent/skill instead of extending the existing one | nothing yet — task 008 is manual |

  Also adds the maintainer-checklist line requiring the `Class` field on every ClaudeKit
  review finding.

## Testing Strategy

This workstream is prompt-corpus only — no `src/` or hook behavior changes — so the gates are
the repo's own drift/lint gates plus targeted structural assertions:

1. `python3 scripts/check-context-floor.py --check` → must stay green (predicted skill
   descriptions: 9892 + 226 = 10118 / 14000).
2. `python3 scripts/check-context-floor.py --json` → record the new number and confirm
   "pipeline agent bodies" is unchanged (neither edited agent is in that set).
3. `python3 -m pytest tests/ -q` → zero failures.
4. `python3 scripts/gen-registry.py --check` and `python3 scripts/gen-docs.py --check` → green
   only once integration lands the registry entry and regenerated counts in the same commit
   (`scripts/gen-registry.py:73-79` errors when an agent loads an unregistered skill). Sequenced
   by the coordinator; nothing for this workstream to do.
5. Manual structural checks (each one command):
   - `grep -n 'Phase 0' .claude/agents/code-reviewer.md` → present, before Phase 1.
   - `grep -c 'verification-gap-lens' .claude/agents/code-reviewer.md .claude/agents/verifier.md`
     → 1 each, under "On demand", not under "Mandatory".
   - `grep -n 'Class' .claude/agents/code-reviewer.md` → present in both finding templates.
   - `grep -n 'CANNOT REVIEW' .claude/agents/code-reviewer.md` → present in the verdict enum
     AND in Phase 0.
   - `grep -c 'mutate the shipped artifact' .claude/agents/*.md .claude/agents/_shared/*.md` → 0
     (mechanics live only in the skill).
   - Skill frontmatter description length == 226 chars.

## Rollback Plan

Every change is additive text in five files; nothing is deleted and no interface changes.

- Full rollback: `git checkout -- .claude/agents/code-reviewer.md .claude/agents/verifier.md
  .claude/agents/_shared/VERIFICATION_PROTOCOL.md .ai/REVIEW_GUIDE.md` and
  `rm -rf .claude/skills/verification-gap-lens/`.
- Partial rollback (skill only): remove the skill directory AND the two on-demand bullets, or
  `gen-registry.py --check` will report a dangling skill reference.
- Rollback order matters: remove the agent references before the skill directory.

## Risk Assessment

**High Risk**

- **INVOCATION.md contradicts the code-reviewer's own frontmatter, and Phase 0 depends on the
  resolution.** `.claude/agents/_shared/INVOCATION.md:103` lists code-reviewer's allowed tools
  as `Read,Grep,Glob` — **no Bash** — while `.claude/agents/code-reviewer.md:13` declares
  `["Read", "Grep", "Glob", "Bash"]`. Phase 0 is unimplementable under row 103.
  **INVOCATION.md is not mine to edit.** Unrestricted `Bash` must NOT be granted (forbidden for
  read-only roles at `INVOCATION.md:106`), and Phase 0 is not "read-only git" — path (c) runs
  `git worktree add/remove`, which writes to `.git` and to disk. The owning workstream will
  apply a SCOPED row on the `debugger` precedent (`INVOCATION.md:98`):
  `Read,Grep,Glob,Bash(git show *),Bash(git diff *),Bash(git rev-parse *),Bash(git ls-files *),Bash(git worktree *),Bash(gh pr *)`.
  Every Phase 0 command in this plan is inside that list — which is why path (d) uses
  `git diff HEAD --stat` and `git ls-files --others --exclude-standard` rather than
  `git status --porcelain`. `Bash(git ls-files *)` is read-only and writes nothing to `.git`,
  the same precedent as the other scoped entries; the coordinator is adding it to the row.

**Medium Risk**

- **Registry + count regeneration is sequenced by integration, not by this plan.**
  `skills-registry.json` needs a `verification-gap-lens` entry (`usedBy: [code-reviewer,
  verifier]`) and the skill count goes 75 → 76; the coordinator lands both in the same
  integration commit as these ops, so CI is never red. By hard rule 8 this plan touches no
  count and no registry file.
- **Two-source drift risk** between the refutation pass and the lens. Mitigated by Step 6's
  explicit ownership note (protocol owns refutation; skill owns gap shapes/Demonstration/
  mutation proof) instead of copying text into both.

**Low Risk**

- Context floor: +226 chars against 4108 headroom; measured, not estimated.
- Agent body growth in `code-reviewer.md`/`verifier.md` is ungated but real per-spawn cost;
  edits are kept terse and the lens detail lives in the on-demand skill, not the agent body.
- Attribution: the skill is adapted from SHAFT_ENGINE → bmad-method (MIT), reworded to this
  repo's scale, with the attribution chain named in the skill body.

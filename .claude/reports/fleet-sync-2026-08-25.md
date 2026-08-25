# Fleet sync — Phase B of plan-fleet-skill-enhancement

**Run:** 2026-08-25 10:39 UTC · **Mode:** EXECUTED
**Projects:** 12 kitted repos. `rest-framework` is excluded (Phase C1, deferred by the owner to its own session); `qa-agent-pro` is excluded (Phase C2, skipped by the owner).

**Every downstream repo is left UNCOMMITTED.** Nothing here is pushed, committed, or merged back. To undo any project entirely: `git -C <project> checkout -- .claude/` plus `git clean -fd .claude/skills/` for the newly added directories (they are untracked until you add them).

> Note: every one of these repos already carried uncommitted changes before this run, from earlier fleet syncs. The counts below are what THIS run did, not the repo's total dirt.

## The dedupe is complete — and the cheap option did not work

All six superseded skills are deleted in all 12 repos, references repointed, zero dangling names. Three of them were HELD for a while, because the diff-guard the plan specified asks whether a local copy was *customised* and never asks whether anything still **loads** it — 84 `## Skill Loading` directives did.

**The registry `renamed` alias map was investigated as the cheap fix and rejected on evidence.** It is diagnostic only: its sole consumer is `ck doctor` (`src/claudekit/cli/main.py` via `skills.renamed_map`), which prints "which was renamed to X — update the reference". Nothing resolves a skill by alias at load time, so shipping the map would have produced a fleet that reports its own breakage politely.

So the references moved first, and the two shapes needed different handling — conflating them is the trap:

| Shape | Count | Action |
|---|---|---|
| File loads only the old skill | 72 | rename the directive |
| File already loads the successor | 12 | **remove** the old line — renaming would load one skill twice |
| Prose mentions outside a directive | 24 | repointed for consistency |

Verified on a scratch copy first: zero duplicate load directives, zero old names left. Tool: `.claude/operations/scripts/fleet-repoint.py`, idempotent.

## Corrections to the plan's matrix (measured, not assumed)

The plan's §2.1 stack table was wrong in three places. Counts are tracked files with `.claude/` excluded:

| Project | Plan said | Measured | Action |
|---|---|---|---|
| AppiumLens | Kotlin/Gradle | **2054 `.java`**, 2 `.kts` (build scripts), 29 `.py` | java + python, NOT kotlin |
| qaforge-ai | Python | 83 `.py`, **34 `.java`** | python + java |
| ApiForge | "src is Java" | 27 `.java`, 0 `.py` | java (confirmed) |

The recurring "~34 `.py`" that made every Java project look dual-stack is ClaudeKit's own `.claude/operations/scripts/` plus `.claude.bak-*` copies — kit tooling, not project source.

## Per project

### ApiForge  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current

### AppiumLens  ·  stack: java, python

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current

### AutomationApp  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current

### Eatizaz  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current

### Lean  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current

### LeanApis  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current

### MobileUIAutomator  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current

### SehhatyApp  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current

### ai-agent-system  ·  stack: python

**Skipped:**
- verification-gap-lens: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current

### qa-agents  ·  stack: python

**Skipped:**
- verification-gap-lens: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current

### qaforge-ai  ·  stack: java, python

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current

### shsmartassistant-qa  ·  stack: kotlin

**Skipped:**
- verification-gap-lens: already present and identical
- kotlin-review-checklist: already present and identical
- code-reviewer.md: routing already current

## Totals

- Skills added: **0**
- Files edited: **0**
- Superseded skills deleted: **0**
- Skipped (logged, never forced): **38**

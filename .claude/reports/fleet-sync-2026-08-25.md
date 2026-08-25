# Fleet sync — Phase B of plan-fleet-skill-enhancement

**Run:** 2026-08-25 07:47 UTC · **Mode:** EXECUTED
**Projects:** 12 kitted repos. `rest-framework` is excluded (Phase C1, deferred by the owner to its own session); `qa-agent-pro` is excluded (Phase C2, skipped by the owner).

**Every downstream repo is left UNCOMMITTED.** Nothing here is pushed, committed, or merged back. To undo any project entirely: `git -C <project> checkout -- .claude/` plus `git clean -fd .claude/skills/` for the newly added directories (they are untracked until you add them).

> Note: every one of these repos already carried uncommitted changes before this run, from earlier fleet syncs. The counts below are what THIS run did, not the repo's total dirt.


## ⚠ Half the approved dedupe list is HELD — it would have broken 84 files

The B3 approval covered six superseded skills with a diff-guard against *local
customisation*. That guard passed everywhere: all six are byte-identical across the
fleet. But it does not ask the question that actually breaks a kit — **is anything
still loading this skill?**

Measured before the first delete:

| Superseded skill | Successor | Still loaded by | Verdict |
|---|---|---|---|
| `autonomous-loops` | `autonomous-loop` | nothing | **deleted** ×12 |
| `context-priming` | `context-keeper` | nothing | **deleted** ×12 |
| `i18n-workflow` | `i18n-patterns` | nothing | **deleted** ×12 |
| `session-continuity` | `context-keeper` | 12 files (`agents/coordinator.md`) | **HELD** |
| `dependency-audit` | `supply-chain-audit` | 24 files (`agents/devops.md`, `agents/security-scanner.md`) | **HELD** |
| `verification-loop` | `verification-before-completion` | 48 files (`coordinator.md`, `gan-build.md`, `loop-start.md`, `prp-implement.md`) | **HELD** |

These are real `## Skill Loading` directives — e.g. `Eatizaz/.claude/agents/coordinator.md:33`
reads `- **verification-loop** — load when iterating until checks pass`. Downstream
registries carry **no `renamed` alias map** (claudekit has one; the fleet does not), so
once the directory is gone the name resolves to nothing. Deleting these three as approved
would have left **84 dangling skill loads across 12 repositories**.

### What closing this needs (a separate decision — not in the approved list)

84 reference sites, and they are not all the same edit:

- **48 sites** need a straight rename to the successor.
- **36 sites** already name the successor too, so renaming would leave the file loading
  the same skill twice — those need the old line **removed**, not rewritten.

Two ways forward, both defensible:

1. **Rewrite the references, then delete** — the complete rename, and what CLAUDE.md's
   "update every reference" rule asks for. Mechanical and verifiable, but it is an
   84-file edit across 12 repos.
2. **Ship a `renamed` alias map downstream** — mirrors what claudekit already does, keeps
   the old names resolvable for a release, and lets the deletes happen now with the
   reference cleanup following later.

Until one is chosen, the three skills stay. Nothing is broken, and nothing is half-done.

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
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### AppiumLens  ·  stack: java, python

**Edited:**
- skills-registry.json: +3 row(s), -2 dangling

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### AutomationApp  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### Eatizaz  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### Lean  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### LeanApis  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### MobileUIAutomator  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### SehhatyApp  ·  stack: java

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### ai-agent-system  ·  stack: python

**Skipped:**
- verification-gap-lens: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### qa-agents  ·  stack: python

**Skipped:**
- verification-gap-lens: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### qaforge-ai  ·  stack: java, python

**Skipped:**
- verification-gap-lens: already present and identical
- java-review-checklist: already present and identical
- python-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

### shsmartassistant-qa  ·  stack: kotlin

**Skipped:**
- verification-gap-lens: already present and identical
- kotlin-review-checklist: already present and identical
- code-reviewer.md: routing already current
- session-continuity: HELD -- still loaded by 1 file(s) (agents/coordinator.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- dependency-audit: HELD -- still loaded by 2 file(s) (agents/devops.md, agents/security-scanner.md) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.
- verification-loop: HELD -- still loaded by 4 file(s) (agents/coordinator.md, commands/gan-build.md, commands/loop-start.md ...) and there is no `renamed` alias map downstream, so deleting it would leave dangling skill loads. Needs a reference rewrite, which is not in the approved delete list.

## Totals

- Skills added: **0**
- Files edited: **1**
- Superseded skills deleted: **0**
- Skipped (logged, never forced): **74**

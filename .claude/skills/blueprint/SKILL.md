---
name: blueprint
description: "Use when an objective requires multiple PRs or sessions — turns a one-line goal into a sequenced, agent-ready construction plan with dependency graph"
disable-model-invocation: true
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Blueprint

## Purpose

Turn a high-level objective into a multi-session, multi-agent construction plan. Each step in the plan is self-contained — a fresh agent can execute any step without prior context.

**Use when:**
- Work requires 3+ PRs or multiple sessions
- Objective has clear dependency ordering (step B requires step A)
- Multiple teams or parallel workstreams are involved
- You need an adversarially reviewed plan before any code changes

**Do NOT use for:**
- Single-PR tasks (use `/plan` instead)
- Fewer than 3 distinct steps
- Tasks you can execute immediately

---

## 5-Phase Pipeline

```
[Phase 1: Research]
      ↓
[Phase 2: Design]
      ↓
[Phase 3: Draft Plan]
      ↓
[Phase 4: Adversarial Review]
      ↓
[Phase 5: Register & Present]
```

---

## Phase 1: Research

Pre-flight checks and context gathering:

```bash
# Verify git state
git status
git remote -v
git log --oneline -5

# Read project structure
find . -maxdepth 2 -not -path "*/node_modules/*" -not -path "*/.git/*" | head -40

# Check for existing plans
ls .claude/plans/ 2>/dev/null || echo "No plans directory"

# Check CLAUDE.md for project conventions
cat CLAUDE.md 2>/dev/null | head -50
```

Gather: current tech stack, existing architecture decisions, team conventions, and any related plans or issues.

---

## Phase 2: Design

Break the objective into **one-PR-sized steps** (typically 3-12):

For each step, determine:
1. **What it does** (one sentence)
2. **Dependencies** (which prior steps must complete first)
3. **Parallelizable?** (can it run simultaneously with another step?)
4. **Model tier** (complex architecture → Sonnet/Opus; simple edits → Haiku)
5. **Rollback strategy** (how to undo if this step fails)
6. **Verification commands** (what must pass before calling it done)

**Dependency graph:**
```
Step 1 ──→ Step 3 ──→ Step 5 (sequential)
           ↓
Step 2 ──→ Step 4 ──→ Step 5 (can parallel with Step 3)
```

---

## Phase 3: Draft Plan

Write the plan to `plans/<objective-slug>.md`. Each step MUST be self-contained — a fresh agent with NO prior context must be able to execute it:

```markdown
# Blueprint: [Objective Title]

**Objective:** [One sentence description]
**Created:** [ISO date]
**Status:** DRAFT → REVIEWED → IN_PROGRESS → COMPLETE

## Steps

### Step 1: [Title]
**Depends on:** None (start here)
**Can parallel with:** Step 2

**Context brief:**
[Everything a fresh agent needs to know — no assumptions about conversation history]

**Task list:**
- [ ] [specific action]
- [ ] [specific action]

**Files to create/modify:**
- `path/to/file.ts` — [what changes]

**Verification:**
```bash
npm test -- --grep "Step 1"
npm run build
```

**Exit criteria:**
- All tests pass
- Build succeeds
- [specific measurable outcome]

**Rollback:**
```bash
git revert HEAD
```

---

### Step 2: [Title]
**Depends on:** None
**Can parallel with:** Step 1
...
```

---

## Phase 4: Adversarial Review

Delegate review to a stronger model as a subagent with this prompt:

```
Review this plan against the following anti-pattern checklist.
For each issue found, rate CRITICAL (must fix) or MINOR (should fix).
Plan location: plans/<name>.md

Anti-pattern checklist:
- [ ] Steps that are too large (should be split into smaller PRs)
- [ ] Steps with hidden dependencies not captured in the graph
- [ ] Missing verification commands (how will we know it's done?)
- [ ] Missing rollback strategy for any step
- [ ] Steps that assume context a fresh agent wouldn't have
- [ ] Circular dependencies in the step graph
- [ ] Steps that mix concerns (e.g., infrastructure + feature in one PR)
- [ ] Missing migration / backward compatibility considerations
- [ ] No mention of how to test the full flow end-to-end
- [ ] Unrealistic parallel steps (resource contention, file conflicts)
```

Fix ALL critical findings before proceeding to Phase 5.

---

## Phase 5: Register & Present

1. Save the reviewed plan to `plans/`
2. Update `.claude/plans/INDEX.md`:

```markdown
## Active Plans
- [objective-slug.md](./objective-slug.md) — [description] — [date] — IN_PROGRESS
```

3. Present to user:

```
## Blueprint: [Objective Title]

Steps: N total (M parallel groups)
Estimated PRs: N

Execution order:
  ▶ Group 1 (parallel): Step 1, Step 2
  ▶ Group 2 (sequential): Step 3
  ▶ Group 3 (parallel): Step 4, Step 5
  ▶ Group 4 (sequential): Step 6

Next action:
  Run: /implement plans/<name>.md --step 1
  Or: /plan "Step 1: [title]" for detailed planning
```

---

## Plan Mutation Protocol

When the plan needs to change mid-execution:

| Action | When | How |
|--------|------|-----|
| **Split** | Step is too large | Add step N.1, N.2; update dependencies |
| **Insert** | New requirement discovered | Add step, update dependency graph |
| **Skip** | Step no longer needed | Mark SKIPPED with reason |
| **Reorder** | Dependencies changed | Update graph, verify no circular deps |
| **Abandon** | Objective changed | Mark ABANDONED with reason, archive file |

Always log mutations with: timestamp, reason, who decided, impact on other steps.

---

## Cold-Start Execution Guarantee

Every step must pass this test before the plan is finalized:

> "Can a fresh Claude Code agent, reading only this step's content, execute it correctly?"

If the answer is NO for any step, the step needs more context in its "Context brief" section.

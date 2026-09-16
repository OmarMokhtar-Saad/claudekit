---
name: continuous-learning
description: "Use when operating this project's learning loop — reflection receipts open ledger findings, and repeated findings become skill PROPOSALS a human promotes"
disable-model-invocation: true
---

# Continuous Learning

## Core Principle

**Every session is a learning opportunity.** When you solve a problem in a novel way, debug an unusual issue, or discover a project-specific pattern — that knowledge should persist beyond the current conversation.

This skill governs how Claude turns a session into ledger entries, memory candidates and skill proposals — and where each one stops until a human promotes it.

---

## When Pattern Extraction Triggers

Extraction has FOUR triggers, and all four exist in the tree:

**A. Per-issue, at the Verifier PASS checkpoint (project-local ledger).** When a diagnosed bug
is fixed and the Verifier returns PASS, score that one issue with the rubric below and — if it
clears — write it to `.Codex/knowledge/issues/` (see *Per-Issue Knowledge Ledger*). Immediate
and per-issue; it does not wait for session end.

**B. Per-session, at the Stop gate (memory candidates).** When a session recorded
mutation-or-delivery activity, `reflection-gate.py` blocks the first Stop with a LEARNING
LOOP duty. Draft candidates from the open ledger entries:

```bash
python3 .Codex/operations/scripts/knowledge-ledger.py distill --agent <agent> --inbox
```

Each group becomes one file in `.Codex/agent-memory/<agent>/_inbox/`. Those files are a
second duty: Stop keeps demanding a decision until every one is accepted
(`inbox --accept <name>`, which moves it into agent memory and appends its `MEMORY.md`
index line) or rejected (`inbox --reject <name>`). `/learn` is the same thing with a
human reading each one first. There is no auto-writer, and no Stop-hook skill extractor -
a skill only ever comes from trigger D plus a human.

**C. At discovery, when a finding is NOT yet fixed (open a ledger entry).** A review finding, a
workflow defect (bad agent routing, a hook misfire) or a known bug you are deferring is
recorded immediately as `status: open`, with **no** rubric score and `verified: false`:

```bash
python3 .Codex/operations/scripts/knowledge-ledger.py open --slug <slug> \
  --signature "<symptom>" --origin workflow --plan <plan-slug> --severity medium
```

**The rubric gates `fixed`, never `open`.** Scoring answers "is this worth keeping once
solved" — it cannot answer that about a bug nobody has solved yet. Only
`record --verified` with a clearing combined score moves an entry to `fixed`;
`close --status wontfix --reason "..."` retires one unfixed. `open` is a separate
subcommand precisely so trigger A's write gate has no bypass.

---

## What to Extract

### Extractable Patterns

| Pattern Type | Example | Store As |
|-------------|---------|----------|
| Project-specific idiom | "This codebase uses X pattern for Y" | agent memory entry (`inbox --accept`) |
| Effective debugging technique | "When Foo fails, check Bar first" | agent memory entry for `debugger` |
| Error resolution recipe | "Error X is caused by Y, fix with Z" | `.Codex/knowledge/issues/<slug>.md` |
| Repeated class of finding | three open findings share tokens | skill proposal, promoted by a human |
| A gap in an existing skill | "this skill never says to check Z" | `propose --patch <skill> --section Pitfalls` |

**D. When a cluster repeats (skill proposals).** `propose` writes a candidate *skill* to
`.Codex/knowledge/proposals/`; `propose --patch <skill> --section Pitfalls|Verification
--text "..."` writes a candidate *patch* to an existing skill. Both are proposals only.
`/learn --promote` applies a patch through an ops.json after the user confirms in chat -
nothing ever writes into `.Codex/skills/` on a machine's own initiative (hard rule 5).

### NOT Extractable

- Information already in AGENTS.md files (read the file, don't duplicate)
- Generic programming knowledge (belongs in a skill, not a learned pattern)
- Temporary workarounds flagged as "don't do this permanently"
- User-specific preferences (store in user memory, not learned skills)

---

## Extraction Workflow

### Step 1: Session Review

At the Stop gate, before deciding each `_inbox/` candidate, review the transcript:

```
Questions to ask:
1. What problem was solved that wasn't obvious at the start?
2. What did I learn about THIS codebase specifically?
3. What workflow worked well that I'd want to repeat?
4. What error was diagnosed — and how?
5. Did I discover a pattern that would help a new developer here?
```

### Step 2: Pattern Assessment

Score each potential pattern:

```
Reusability Score:
- Applies to only this file/function: 1 (don't extract)
- Applies to this module: 3 (consider)
- Applies to this project: 7 (extract)
- Applies across projects: 9 (extract as general skill)

Novelty Score:
- Already documented in AGENTS.md: 0 (skip)
- Common knowledge: 2 (skip)
- Project-specific discovery: 8 (extract)
- Surprising behavior worth remembering: 9 (extract)

Combined score >= 10: Extract
Combined score < 10: Skip
```

### Step 3: Write the Learned Skill

Write the candidate body that `distill --inbox` will hold (or hand-write one there):

```markdown
---
name: <descriptive-name>
description: "<one-line summary of what this teaches>"
type: learned
source: <project-name>
date: <YYYY-MM-DD>
confidence: [high|medium|low]
---

# <Title>

## Context
[When does this apply? What project/situation?]

## Pattern
[What to do or know]

## Evidence
[Why this is true — what confirmed it]

## Example
[Concrete example of applying this]

## Caveats
[Any exceptions or conditions where this doesn't apply]
```

### Step 4: Register in Skill Registry

`inbox --accept` appends the candidate's `index:` line to the agent's `MEMORY.md`:

```markdown
- [Pattern Name](./path/to/skill.md) — one-line description — project: <name>
```

---

## Per-Issue Knowledge Ledger (project-local)

Session-end extraction is too coarse for bugs: by the time Stop fires, the exact error
signature and the verified root cause are buried in the transcript. So each *issue* is recorded
at the moment it is proven fixed.

| | Memory candidates (Stop gate) | Issue ledger (Verifier PASS) |
|---|---|---|
| Trigger | Stop, after mutation activity | Verifier DECISION = PASS on a bug fix |
| Unit | pattern / workflow | one issue |
| Storage | `.Codex/agent-memory/<agent>/` | `.Codex/knowledge/issues/<slug>.md` |
| Scope | one agent's prompt | this project only |
| Retrieval | auto-injected into that agent | debugger Phase 0 keyword grep |

**Same gate — there is no second rubric.** Reuse the Step 2 Pattern Assessment scores
unchanged: combined `reusability + novelty >= 10` extracts, `< 10` skips. The ledger script
enforces that threshold *and* the verified-PASS precondition, and refuses anything else. The
threshold is not hardcoded twice: the script reads
`continuous_learning.issue_ledger.min_combined_score` from the Configuration block below and
falls back to 10 when the key is absent.

```bash
# write (Verifier, on PASS only)
python3 .Codex/operations/scripts/knowledge-ledger.py record --slug <slug> \
  --signature "<error signature>" --root-cause "<why>" --fix "<what>" \
  --files "<a.py,b.py>" --reusability <N> --novelty <N> --verified

# read (debugger, before diagnosing)
python3 .Codex/operations/scripts/knowledge-ledger.py search "<signature or keywords>"

# hygiene (rides the periodic sweep — see .ai/BACKLOG.md)
python3 .Codex/operations/scripts/knowledge-ledger.py prune [--apply]
```

Entry frontmatter: `signature`, `root_cause`, `fix`, `files`, `date`, `status`
(`open`/`fixed`/`wontfix`/`regressed`; absent reads as `fixed`), `origin`
(`code`/`workflow`/`project`), optional `plan` and `severity`, and `verified`
(true only via `record`). File paths
passed to `--files` may not contain `[`, `]`, `,`, quotes or newlines — the script rejects
them so the `files:` line always parses back cleanly during pruning.

Rules:
- Retrieval is **pull-only**. The debugger greps the ledger on demand; NEVER auto-inject
  entries into context or append them to a AGENTS.md — that reintroduces exactly the context
  cost the ledger exists to avoid.
- Storage is plain markdown searched by keyword. No index, no vector store, no new runtime
  dependency.
- Scope is **project-local**. Promoting an entry into agent memory or a skill is a
  human step (`/learn --promote`) — never ad hoc, and never automatic.
- Stale entries (every referenced file gone) are archived by `prune`, never hand-deleted.

## Learning Categories

### Error Resolutions

When a specific error was diagnosed:

```markdown
## Error: <ExactErrorMessage>

**Root Cause:** <why it happens>
**Fix:** <what to do>
**Verification:** <how to confirm it's fixed>
**Recurrence Prevention:** <how to avoid in future>
```

### Project Patterns

When a codebase-specific pattern is discovered:

```markdown
## Pattern: <Name>

**Applies to:** <project or module>
**Discovery:** <how this was found>
**Rule:** <the pattern in one sentence>
**Example:** [code or command]
**Rationale:** <why this codebase does it this way>
```

### Workflow Discoveries

When an effective workflow is used:

```markdown
## Workflow: <Name>

**Use when:** <trigger condition>
**Steps:**
1. [step]
2. [step]
...
**Outcome:** <what this achieves>
**Validated:** YES — used successfully on [date]
```

---

## Anti-Patterns to Avoid

- **Over-extraction:** Don't save every session's details. Quality > quantity.
- **Stale patterns:** Mark patterns with dates; re-validate after major refactors.
- **Circular learning:** Don't extract something that contradicts a AGENTS.md rule.
- **False confidence:** Mark uncertain patterns as `confidence: low` and validate.

---

## Configuration

Control extraction sensitivity in `.Codex/hooks/config.json`:

```json
{
  "continuous_learning": {
    "enabled": true,
    "min_session_messages": 10,
    "auto_approve": false,
    "storage_path": ".claude/agent-memory/",
    "categories": ["error-resolution", "project-patterns", "debugging", "workflow"],
    "issue_ledger": {
      "enabled": true,
      "trigger": "verifier-pass",
      "storage_path": ".claude/knowledge/issues/",
      "min_combined_score": 10
    }
  }
}
```

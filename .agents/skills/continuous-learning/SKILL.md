---
name: continuous-learning
description: "Use when setting up automatic pattern extraction from sessions — Stop hook that learns reusable patterns and saves them as skills"
disable-model-invocation: true
---

# Continuous Learning

## Core Principle

**Every session is a learning opportunity.** When you solve a problem in a novel way, debug an unusual issue, or discover a project-specific pattern — that knowledge should persist beyond the current conversation.

This skill governs how Codex extracts reusable patterns at session end and saves them as skills for future sessions.

---

## When Pattern Extraction Triggers

Extraction has TWO triggers:

**A. Per-issue, at the Verifier PASS checkpoint (project-local ledger).** When a diagnosed bug
is fixed and the Verifier returns PASS, score that one issue with the rubric below and — if it
clears — write it to `.Codex/knowledge/issues/` (see *Per-Issue Knowledge Ledger*). Immediate
and per-issue; it does not wait for session end.

**B. Per-session, at the Stop hook (learned skills).** The Stop hook evaluates the session
when:

1. The session had **10 or more meaningful exchanges** (not just clarifications)
2. At least one of these occurred:
   - A non-trivial bug was diagnosed and fixed
   - A project-specific pattern was discovered
   - An effective workflow was used that could generalize
   - An error recovery strategy succeeded

If the session was primarily reading/exploring with no novel problem-solving, skip extraction.

---

## What to Extract

### Extractable Patterns

| Pattern Type | Example | Store As |
|-------------|---------|----------|
| Project-specific idiom | "This codebase uses X pattern for Y" | `~/.Codex/skills/learned/<project>/patterns.md` |
| Effective debugging technique | "When Foo fails, check Bar first" | `~/.Codex/skills/learned/debugging/<topic>.md` |
| Error resolution recipe | "Error X is caused by Y, fix with Z" | `~/.Codex/skills/learned/errors/<error-code>.md` |
| Build/tool configuration | "This project needs FLAG=1 to build" | `~/.Codex/skills/learned/<project>/setup.md` |
| Workflow that worked well | "For this repo, always X before Y" | `~/.Codex/skills/learned/<project>/workflow.md` |

### NOT Extractable

- Information already in AGENTS.md files (read the file, don't duplicate)
- Generic programming knowledge (belongs in a skill, not a learned pattern)
- Temporary workarounds flagged as "don't do this permanently"
- User-specific preferences (store in user memory, not learned skills)

---

## Extraction Workflow

### Step 1: Session Review

At session end (Stop hook), review the transcript:

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

Create a new file in `~/.Codex/skills/learned/`:

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

Add to `~/.Codex/skills/learned/INDEX.md`:

```markdown
- [Pattern Name](./path/to/skill.md) — one-line description — project: <name>
```

---

## Per-Issue Knowledge Ledger (project-local)

Session-end extraction is too coarse for bugs: by the time Stop fires, the exact error
signature and the verified root cause are buried in the transcript. So each *issue* is recorded
at the moment it is proven fixed.

| | Learned skills (Stop hook) | Issue ledger (Verifier PASS) |
|---|---|---|
| Trigger | session end | Verifier DECISION = PASS on a bug fix |
| Unit | pattern / workflow | one issue |
| Storage | `~/.Codex/skills/learned/` | `.Codex/knowledge/issues/<slug>.md` |
| Scope | cross-project | this project only |
| Retrieval | skill loading | debugger Phase 0 keyword grep |

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

Entry frontmatter: `signature`, `root_cause`, `fix`, `files`, `date`, `verified`. File paths
passed to `--files` may not contain `[`, `]`, `,`, quotes or newlines — the script rejects
them so the `files:` line always parses back cleanly during pruning.

Rules:
- Retrieval is **pull-only**. The debugger greps the ledger on demand; NEVER auto-inject
  entries into context or append them to an AGENTS.md — that reintroduces exactly the context
  cost the ledger exists to avoid.
- Storage is plain markdown searched by keyword. No index, no vector store, no new runtime
  dependency.
- Scope is **project-local**. Promoting an entry to the cross-project
  `~/.Codex/skills/learned/` tier is a deliberate future phase — never ad hoc.
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
    "storage_path": "~/.Codex/skills/learned/",
    "categories": ["error-resolution", "project-patterns", "debugging", "workflow"],
    "issue_ledger": {
      "enabled": true,
      "trigger": "verifier-pass",
      "storage_path": ".Codex/knowledge/issues/",
      "min_combined_score": 10
    }
  }
}
```

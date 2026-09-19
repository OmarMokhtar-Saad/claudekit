# Hermes Agent Self-Improvement & Learning Mechanics (2026-09)

**Date**: 2026-09-16  
**Topic**: Memory persistence, skill creation, reflection loop, quality gates

---

## 1. Memory Persistence

**File Layout**: Two files in `~/.hermes/memories/`:
- `MEMORY.md` (~2,200 chars): Agent's learned facts, environment conventions
- `USER.md` (~1,375 chars): User profile, preferences, communication style

**Writer**: The agent via the `memory` tool (three operations: add, replace, remove). Writes are automatic unless gated via `write_approval: true`.

**Injection Mechanism**: Both files are frozen snapshots injected into system prompt at **session start**. Changes within a session don't appear until next session (preserves prefix cache).

**Size Limits**: Character-based with section-sign delimiters (`§`). When capacity exceeded, tool returns error; agent must consolidate/remove entries before retry.

**No separate project vs. user distinction documented** — single shared MEMORY.md/USER.md per agent instance.

---

## 2. Skill Creation

**Trigger**: Autonomous creation after:
- Complex tasks (implicit threshold)
- Recovery from errors
- Receiving user corrections
- ~3–4 successful runs of similar work

**File Format**: `SKILL.md` with YAML frontmatter (name, description, version, platform restrictions). Sections: "When to Use," "Procedure," "Pitfalls," "Verification." Optional subdirs: `references/`, `templates/`, `scripts/`, `examples/`, `assets/`.

**Storage**: `~/.hermes/skills/` (hub-installed and agent-created coexist).

**Standard**: agentskills.io open standard (portable across compatible runtimes).

**Retrieval/Matching**: Progressive disclosure — lightweight skill list (~3k tokens) first, full content on-demand. Automatic discovery via slash commands (`/skill-name`); can stack multiple skills.

---

## 3. Reflection & Learning Loop

**Post-Task Reflection**: Runs after each turn to distill completed work into reusable skills.

**Skill Self-Improvement**: "Skills self-improve during use" — closed loop where repeated application refines existing skills (not one-time generation).

**No Separate "Lessons" Store**: Reflection outputs directly feed skill creation/evolution. No distinct lessons/insights file documented; learning is embodied in SKILL.md updates.

**Persistence Mechanism**: File modifications to SKILL.md via `skill_manage` tool with patch/edit actions.

---

## 4. Quality Gates & Evaluation

**Security Scanning**: Hub-installed skills checked for data exfiltration, prompt injection, destructive commands, supply-chain signals.

**Advisory Linting**: `skill_manage` runs linter on creation and `references/` writes; returns findings to agent.

**Write Approval Gating**: Optional `skills.write_approval: true` requires human review before agent-created skills commit.

**Origin-Hash Baselines**: Bundled skills tracked to detect user modifications and prevent unwanted overwrites.

**NOT DOCUMENTED**:
- Formal testing framework
- Explicit versioning beyond YAML `version` field
- Skill scoring/ranking mechanism
- Decay/deprecation policies
- Automated pruning

---

## Summary Table

| Feature | Implementation | File/Module |
|---------|---|---|
| Memory persistence | MEMORY.md + USER.md in `~/.hermes/memories/` | `hermes_state_*.py` |
| Memory injection | Session-start snapshot | System prompt (frozen until next session) |
| Memory writer | Agent via `memory` tool | Tool-gated, optional write_approval |
| Skill storage | `~/.hermes/skills/` SKILL.md files | agentskills.io format |
| Skill trigger | Post-task, ~3–4 runs, error recovery | `skill_manage` tool, advisory linter |
| Reflection | Post-turn distillation loop | Feeds skill updates (no separate store) |
| Quality gates | Security scan, linting, write_approval | `skill_manage` advisory linter + hub scanner |
| Decay/Version | UNVERIFIED | YAML `version` field only |

---

## Sources

- [Persistent Memory - Hermes Agent Docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- [Skills System - Hermes Agent Docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
- [GitHub: NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent)
- [Skills Documentation (GitHub source)](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)

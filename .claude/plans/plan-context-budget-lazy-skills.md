# Plan: Context budget — lazy skill loading + registry truth (task 009 core)

## Measured problem

Agents preload 16,120 lines of skills across 18 agents before any work; coordinator alone
preloads 12 skills (2,397 lines ≈ 27k tokens). skills-registry.json agentMapping (30 keys)
disagrees with agent files: 10 mapped agents have NO skill section; 2 keys are commands
(loop-start, opensource); usedBy:["all"] on 10 skills is honored nowhere.

## Design

1. **≤3 mandatory skills per agent** (using-superpowers + up to 2 role-core). Everything
   else moves to an explicit "on demand" list with a one-line trigger. Effort is preserved:
   behavioral rules live in _shared docs (always present via agent file references); skill
   bodies are depth, loaded exactly when their trigger fires.
2. **Agent .md files are the single source of truth.** scripts/gen-registry.py parses the
   Skill Loading sections and regenerates agentMapping (mandatory ∪ on-demand); --check mode
   gates drift (wired into tests like gen-docs). Ghost keys (sectionless agents, commands)
   are dropped from agentMapping.
3. AGENT_TEMPLATE.md Skill Loading Protocol updated to define mandatory vs on-demand
   semantics ("preloading burns context; the trigger loads the skill").
4. Budget gate test: no agent may declare >3 mandatory skills; registry --check must pass.

## Expected effect

Mandatory preload 16,120 → ~5,000 lines total (coordinator 2,397 → ~350).
Rolled to all 6 projects via ck update after DoD.

## Not in scope (recorded follow-ups)

- Splitting large SKILL.md bodies into core + references/ (74 skills — separate pass).
- usedBy field semantics cleanup beyond removing what agentMapping regeneration fixes.
- Command-file Mandatory Skills trimming (8 commands have 4; marginal).

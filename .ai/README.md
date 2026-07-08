# .ai/ — The ClaudeKit AI Operating System

This folder is the **model-independent knowledge transfer layer** for ClaudeKit. It exists so that any AI model (Claude, GPT, Gemini, Qwen, DeepSeek, …) — or any human — can clone this repository with **zero prior conversation history** and continue development at the same quality level.

Everything here was generated from a full-repository analysis on **2026-07-08** (v2.1.0, post Phase-1 "Fix What's Broken"). The filesystem is the source of truth; when a count or claim here disagrees with the tree, trust the tree and run `python3 scripts/gen-docs.py --check`.

## Read in this order

| # | Document | Why |
|---|----------|-----|
| 1 | [MODEL_ONBOARDING.md](MODEL_ONBOARDING.md) | Your first hour. Mandatory reading order, rules, mistakes to avoid. |
| 2 | [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | What ClaudeKit is, in plain language, plus the repo map. |
| 3 | [CONTEXT.md](CONTEXT.md) | Non-obvious project context: identity, distribution, versioning, session gotchas. |
| 4 | [ARCHITECTURE.md](ARCHITECTURE.md) | The full technical architecture with diagrams. |
| 5 | [STATUS.md](STATUS.md) + [SESSION_STATE.md](SESSION_STATE.md) | Where the project is right now and what to do next. |
| 6 | [AI_PROJECT_HANDOVER.md](AI_PROJECT_HANDOVER.md) | The handover narrative — what was done, what's open, what's user-gated. |

## Reference catalogs (consult as needed)

| Document | Contents |
|----------|----------|
| [AGENTS.md](AGENTS.md) | All 28 agents, shared protocols, interaction diagrams |
| [COMMANDS.md](COMMANDS.md) | All 40 slash commands + 13 template commands + 7 modes |
| [SKILLS.md](SKILLS.md) | All 74 skills, the registry, the operations pipeline |
| [HOOKS.md](HOOKS.md) | All 19 hooks, settings.json wiring, lifecycle, profiles |
| [PROMPTS.md](PROMPTS.md) | Prompt architecture, conventions, lifecycle |
| [DOMAIN.md](DOMAIN.md) | Domain model and business rules |
| [GLOSSARY.md](GLOSSARY.md) | Every ClaudeKit-specific term |
| [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md) | Mermaid graph of how everything relates |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Runtime/dev/CI/external dependencies |

## How-to guides

| Document | Contents |
|----------|----------|
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | Environment setup, ECC_HOOK_PROFILE, adding assets |
| [WORKFLOW.md](WORKFLOW.md) | All pipelines: standard, PRP, Santa, GAN, open-source, loops |
| [REVIEW_GUIDE.md](REVIEW_GUIDE.md) | Plan review vs code review, thresholds, checklists |
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | Python, Bash, and Markdown-asset standards |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Test suite map, philosophy, coverage gates |
| [SECURITY_GUIDE.md](SECURITY_GUIDE.md) | Threat model, security layer internals, rules |
| [PERFORMANCE_GUIDE.md](PERFORMANCE_GUIDE.md) | Token economy, hook latency, context budgets |
| [DEBUGGING_GUIDE.md](DEBUGGING_GUIDE.md) | How to debug hooks, installer, CLI, tests |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Symptom → cause → fix tables |
| [PLAYBOOK.md](PLAYBOOK.md) | Step-by-step recipes (release, feature, bugfix, consolidation) |
| [CHECKLISTS.md](CHECKLISTS.md) | Definition of Done, PR, release, new-asset checklists |
| [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) | v2.0 → v2.1 breaking changes and upgrade path |

## Memory & planning

| Document | Contents |
|----------|----------|
| [MEMORY.md](MEMORY.md) | Durable facts and invariants an AI must retain |
| [DECISIONS.md](DECISIONS.md) | Decision log with context, alternatives, consequences |
| [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md) | Philosophies, patterns, anti-patterns, lessons learned |
| [ROADMAP.md](ROADMAP.md) | v2.1 ship steps → v3.0 → 12–24 month vision |
| [BACKLOG.md](BACKLOG.md) | Prioritized open work items |
| [TECH_DEBT.md](TECH_DEBT.md) | Debt register with severity and file references |
| [CHANGELOG_AI.md](CHANGELOG_AI.md) | Log of AI working sessions on this repo |
| [FAQ.md](FAQ.md) | Questions a new maintainer will ask |

## Relationship to other documentation

- **`README.md` (root)** — user-facing marketing + quick start. Do not duplicate it here.
- **`docs/`** — user-facing deep dives (ARCHITECTURE, AGENTS, SKILLS, HOOKS, cli, CUSTOMIZATION, CONSTITUTION-GUIDE). Audience: people *using* ClaudeKit in their projects.
- **`.ai/`** (this folder) — maintainer/AI-facing. Audience: whoever *develops ClaudeKit itself*.
- **`review/`** — the frozen 2026-07-05 engineering audit (11 reviews, 14 tasks, roadmap). Historical record; superseded status lives in [STATUS.md](STATUS.md).
- **`CLAUDE.md` (root)** — operating instructions for an AI working in this repo. The short version of this folder.

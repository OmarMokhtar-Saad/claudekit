# Skills Catalog

74 skills in `.claude/skills/<id>/SKILL.md`, indexed by `.claude/skills/skills-registry.json` (schema: `version`, `lastUpdated`, `skills[]` with `id`, `name`, `path`, `mandatory`, `usedBy[]`, `description`). A skill is a reusable procedure module an agent loads on demand; `usedBy` maps skills to agents ("all" = every agent). CI's `validate-registry` job fails on dangling paths (a `documenter → i18n-workflow` dangling ref was a real caught bug). User-facing doc: `docs/SKILLS.md`. 14 additional template skills live in `templates/skills/` (overlapping set — deletion candidates, task 008).

**Mandatory for all agents:** `using-superpowers` (skill-discovery protocol — load first, always) and `golden-rule` (no code changes without explicit approval).

## By category

### Planning & process
`writing-plans` (plan structure + ops.json), `executing-plans` (batch execution with checkpoints), `brainstorming`, `context-first-workflow` (explore before modifying), `spec-driven-development`, `prp-plan` (deep-recon PRP phase 1), `blueprint` (EPIC → multi-PR construction plans), `clarify` (reverse-question protocol), `search-first` (check npm/PyPI/MCP/GitHub before writing custom code), `refactoring-patterns`.

### Operations pipeline (the safety-critical trio)
- `generate-operations-config` — **the canonical ops.json schema source** (planner must reference it, never embed a copy).
- `validate-operations-config` — reviewer-side validation against the 29 guards.
- `execute-operations-config` — implementer-side; **script-only** execution through `execute-json-ops.py` (rewritten in v2.1; previously instructed manual Edit usage that the Iron Law forbids).

Python backend in `.claude/operations/scripts/`:
| Script | Role |
|--------|------|
| `validate-config-json.py` | 29 guards: JSON syntax + schema (`operations-schema.json`, types `file_create`/`file_delete`/`code_edit`, `additionalProperties: false`), file existence, protected-file refusal, deletion reason ≥10 chars, unique/unambiguous `find` matches, null-byte checks, MAX_DELETIONS=3/plan (GUARD 26), parent-dir checks, overwrite protection. |
| `execute-json-ops.py` | Applies operations: per-file backup first, atomic writes, transactional rollback on failure, signal handling. |
| `restore-backup.py` | Manual/`ck rollback` restore from the backup set. |
| `shared.py` | PROTECTED_PATTERNS, path normalization, version constant (bump with releases!). |

Safety model in five bullets: (1) plans are data, not actions; (2) validation is deterministic and fail-closed; (3) every execution is preceded by backups and is atomic; (4) protected files can never be deleted; (5) rollback is always available (`/rollback`, `ck rollback`).

### Verification & testing
`verification-before-completion` (evidence before claims), `verification-loop` (6-phase QA: build/types/lint/tests/security/diff), `test-driven-development`, `property-based-testing`, `eval-harness`, `requesting-code-review` / `receiving-code-review`.

### Security
`security-checklist` (OWASP Top 10), `differential-security-review` (diff-focused), `insecure-defaults`, `supply-chain-audit` (typosquatting, CVE cross-ref), `dependency-audit`, `prompt-injection-defense` (27+ patterns), `safe-command-approval` (allowlist/blocklist + AST analysis), `static-analysis-integration` (semgrep/bandit/eslint-security, SARIF).

### Architecture & domain
`clean-architecture`, `api-design-patterns`, `database-migration-patterns` (expand-contract, zero-downtime), `error-handling`, `performance-guidelines`, `accessibility-standards` (WCAG 2.1 AA), `i18n-patterns`, `containerization-patterns`, `ci-cd-pipeline`, `monitoring-observability`, `incident-response`.

### Context & token management
`context-budget`, `token-optimization` (3 compression levels), `token-budget-advisor` (user-selectable 25/50/75/100% depth), `context-priming`, `context-keeper` (structured save/resume), `session-continuity` (freshness: <4h trust, 4–24h verify, >72h stale), `codebase-mapping`, `codebase-onboarding` (4-phase → guide + starter CLAUDE.md), `project-adaptation` (adapt the kit itself to any project/language: detect install state → learn project → configure config.json/CLAUDE.md/CONSTITUTION/hooks → verify with evidence → enhance via /hookify + /learn; backs `/adapt`), `usage-monitoring`, `hook-profiling`.

### Multi-agent & orchestration
`multi-agent-coordination`, `dispatching-parallel-agents`, `subagent-driven-development` (fresh subagent per task), `autonomous-loop` **and** `autonomous-loops` (near-duplicates — merge, task 008), `gan-harness` (generate → fresh evaluator → iterate, anti-anchoring), `santa-method` (dual Opus+Sonnet independent review, both must approve), `council` (Architect/Skeptic/Pragmatist/Critic parallel debate), `deep-research`, `mcp-integration` (Context7/Sequential-Thinking/Playwright/Memory/Filesystem guidance).

### Git & delivery
`git-workflow`, `using-git-worktrees`, `finishing-a-development-branch`, `opensource-pipeline` (3-stage hard-gated).

### Meta & governance
`golden-rule`, `using-superpowers`, `constitution` (project governance creation), `writing-skills` (TDD approach to authoring skills), `continuous-learning` (extract session patterns → new skills, backs `/learn`), `hookify` (behavior description → prevention hook), `command-flags` (universal `--mode/--depth/--format/--persona` system), `documentation-standards`, `systematic-debugging` (4-phase RCA), `code-explanation` (analogy-first), `debugging` support via `incident-response`.

## Authoring conventions

SKILL.md structure: frontmatter (name/description with when-to-use triggers) + purpose, inputs, execution flow, outputs, best practices, common mistakes. Keep descriptions trigger-rich (they drive discovery via `using-superpowers`). Register in skills-registry.json with accurate `usedBy` — CI validates paths. Prefer editing an existing skill over adding a near-duplicate (see task 008 merge list in [BACKLOG.md](BACKLOG.md)).

## Known issues

- Near-duplicates queued for merge (008): `autonomous-loop`/`autonomous-loops`, `verification-before-completion`/`verification-loop`, token/context trio, `codebase-mapping`/`codebase-onboarding`, `dependency-audit`/`supply-chain-audit`.
- `templates/skills/` duplicates 14 shipped skills; two have already diverged — delete after consolidation sign-off.
- Registry `mandatory` flags (2) understate practice — coordinator's prompt loads ~12 skills; roadmap §2.4 caps mandatory loads at ≤2 with inline digests.

# Glossary

| Term | Definition |
|------|-----------|
| **Agent** | A single-responsibility role prompt in `.claude/agents/` with model + tools frontmatter. 28 shipped. |
| **Anti-anchoring** | Preventing bias from a first opinion by spawning evaluators with fresh, unshared context (Santa, GAN, council). |
| **Auto-checkpoint** | Template hook stashing periodic checkpoints (stable stash SHAs). |
| **AUTO-REJECT** | Reviewer verdict scoring a plan 0 for a hard violation (e.g., missing ops.json). |
| **Blueprint** | Multi-session construction plan for EPIC-scope (3+ PR) objectives (`/blueprint`). |
| **ck** | Short CLI alias for `claudekit`. |
| **Command** | Slash-command workflow entry point in `.claude/commands/`. 40 shipped. |
| **Command-guard** | PreToolUse hook running Bash commands through CommandValidator (strict=block/standard=warn/minimal=off). |
| **CommandValidator** | Python denylist validator: segments chained commands, inspects substitutions, blocks dangerous patterns. |
| **Constitution** | Per-project governance doc (8 articles) that agents enforce; generated from `CONSTITUTION.template.md`. |
| **Context budget** | Token-consumption accounting across agents/skills/hooks/MCP (`/context-budget`, skill). |
| **Coordinator** | Routing agent: classifies tasks, selects pipelines, manages handoffs. |
| **Docs-drift** | CI job failing when any doc hard-codes a count that disagrees with the filesystem (`gen-docs.py --check`). |
| **ECC_HOOK_PROFILE** | Enforcement level env var: `minimal` / `standard` (default) / `strict`. |
| **Fail closed** | Blocking hook behavior on parse failure: block, don't allow. |
| **File-based handoff** | Agents exchange artifacts (plan.md, ops.json), not conversation context. |
| **GAN build** | Generator → fresh Evaluator → Adjudicator iteration loop (`/gan-build`, gan-harness skill). |
| **Golden Rule** | No code changes without explicit user approval. Mandatory skill for all agents. |
| **Guard** | One of 29 numbered validation rules in `validate-config-json.py`. |
| **Handoff Protocol** | The exact block format for agent-to-agent transitions (`HANDOFF_PROTOCOL.md`). |
| **Iron Law** | Implementer executes only via ops.json/engine; no ops.json → STOP. |
| **Manifest** | `.claude/.claudekit-manifest.json` — installed files + sha256, powering diff/update/uninstall/doctor. |
| **MAX_DELETIONS** | GUARD 26: ≤3 file deletions per plan. |
| **Mode** | Behavioral overlay (default/brainstorm/token-efficient/deep-research/implementation/review/orchestration). |
| **Model routing** | Scoring a task (reasoning depth, output complexity, error cost, novelty) → haiku/sonnet/opus (`/model-route`). |
| **Operations engine** | validate → execute (backup/atomic/rollback) → restore Python trio in `.claude/operations/scripts/`. |
| **ops.json** | Declarative operations config (`file_create`/`file_delete`/`code_edit`) accompanying every plan. Names: `*.ops.json` or `ops-*.json`. |
| **PathGuard** | Python path validator: protected patterns per component, symlink resolution, depth limit. |
| **Phase 1** | The v2.1 "Fix What's Broken" remediation (audit tasks 001–006, 011), completed 2026-07-06. |
| **Pipeline** | Ordered agent sequence chosen by task classification. |
| **Plan** | `plan-*.md` + ops.json pair in `.claude/plans/`. |
| **PRP** | Product Requirements Process — 4-phase deep-context workflow (`/prp-plan → /prp-implement → /prp-commit → /prp-pr`). |
| **Protected files** | Patterns that ops can never delete (canonical set: `shared.py` PROTECTED_PATTERNS / PathGuard). |
| **Quality gates** | Plan ≥90/100 (40/30/30); verification ≥80/100 (30/40/30). |
| **Santa method** | Dual independent review — Opus Skeptic + Sonnet Pragmatist, no shared context, both must approve (`/santa`). |
| **Skill** | Loadable procedure module in `.claude/skills/`; 74 shipped; mapped via skills-registry.json. |
| **Speed bump, not a sandbox** | The mandated honest framing of the security layer. |
| **Trusted Publishing** | Tokenless PyPI publishing from GitHub Actions (release.yml). |
| **using-superpowers** | Mandatory first skill: how agents discover and load other skills. |

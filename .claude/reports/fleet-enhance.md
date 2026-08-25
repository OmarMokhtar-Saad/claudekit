# Fleet enhancement — no reinstall, nothing moved aside

**Run:** 2026-08-25 10:50 UTC · **Mode:** EXECUTED · **Repos:** 13

Additive and non-destructive by construction: **nothing is deleted, nothing is moved aside, and no file the project has edited is overwritten.** Every repo is left uncommitted.

Classification is exact where a `.claudekit-manifest.json` exists, because it records sha256 per installed file. A file is UPDATED only when its current hash still matches what the kit installed — i.e. nobody has touched it. Anything else is reported, never written.

| Project | Added | Updated | Preserved (edited) | Already current | Manifest |
|---|---|---|---|---|---|
| ai-agent-system | 17 | 68 | 11 | 111 | yes |
| ApiForge | 17 | 68 | 11 | 111 | yes |
| AppiumLens | 15 | 66 | 14 | 112 | yes |
| AutomationApp | 17 | 68 | 11 | 111 | yes |
| Eatizaz | 17 | 68 | 11 | 111 | yes |
| Lean | 17 | 68 | 11 | 111 | yes |
| LeanApis | 16 | 68 | 12 | 111 | yes |
| MobileUIAutomator | 17 | 68 | 11 | 111 | yes |
| qa-agents | 16 | 65 | 16 | 110 | yes |
| qaforge-ai | 16 | 68 | 11 | 112 | yes |
| rest-framework | 110 | 0 | 66 | 31 | **NO** |
| SehhatyApp | 17 | 68 | 11 | 111 | yes |
| shsmartassistant-qa | 11 | 59 | 6 | 131 | yes |

## Preserved files, per project

These were **not** written. Each is either edited since install or unprovable as pristine.

### ai-agent-system (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### ApiForge (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### AppiumLens (14)

- `skills/generate-operations-config/SKILL.md` — edited since install — customisation preserved
- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved
- `hooks/config.json` — edited since install — customisation preserved
- `hooks/edited-files.log` — not in manifest — treated as project-local

### AutomationApp (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### Eatizaz (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### Lean (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### LeanApis (12)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved
- `hooks/edited-files.log` — not in manifest — treated as project-local

### MobileUIAutomator (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### qa-agents (16)

- `skills/generate-operations-config/SKILL.md` — edited since install — customisation preserved
- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved
- `hooks/command-guard.sh` — edited since install — customisation preserved
- `hooks/config.json` — edited since install — customisation preserved
- `hooks/edited-files.log` — not in manifest — treated as project-local
- … and 1 more

### qaforge-ai (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### rest-framework (66)

- `skills/execute-operations-config/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/using-git-worktrees/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/test-driven-development/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/systematic-debugging/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/security-checklist/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/using-superpowers/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/dispatching-parallel-agents/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/git-workflow/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/validate-operations-config/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/finishing-a-development-branch/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/multi-agent-coordination/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/brainstorming/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/autonomous-loop/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/continuous-learning/SKILL.md` — no manifest — cannot prove it is unmodified
- `skills/writing-plans/SKILL.md` — no manifest — cannot prove it is unmodified
- … and 51 more

### SehhatyApp (11)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `agents/debugger.md` — edited since install — customisation preserved
- `agents/implementer.md` — edited since install — customisation preserved
- `agents/opensource-sanitizer.md` — edited since install — customisation preserved
- `agents/planner.md` — edited since install — customisation preserved
- `agents/refactor-cleaner.md` — edited since install — customisation preserved
- `agents/reviewer.md` — edited since install — customisation preserved
- `agents/verifier.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved

### shsmartassistant-qa (6)

- `agents/code-reviewer.md` — edited since install — customisation preserved
- `agents/coordinator.md` — edited since install — customisation preserved
- `commands/gan-build.md` — edited since install — customisation preserved
- `commands/prp-implement.md` — edited since install — customisation preserved
- `hooks/config.json` — edited since install — customisation preserved
- `hooks/edited-files.log` — not in manifest — treated as project-local


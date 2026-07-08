---
name: project-adaptation
description: "Use when ClaudeKit has just been added to a project (any language, any stack) or is misconfigured for it — teaches the AI what to change, how to verify the kit works, and how to enhance it to fit the project"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash
---

# Project Adaptation

## Purpose

ClaudeKit is language-agnostic by design: agents, commands, skills, and the operations engine work on any codebase. What is **project-specific** is a small configuration surface. This skill teaches you to (1) detect what state the installation is in, (2) learn the project, (3) configure that surface correctly, (4) verify the kit actually works here, and (5) keep enhancing the fit over time.

**Trigger when:** `.claude/` was just copied or installed into a project · `CLAUDE.md` is missing or still contains `{{PLACEHOLDERS}}` · hooks skip steps because commands are unconfigured · the stack has no dedicated template (any language beyond the 11 shipped ones) · user says "set up ClaudeKit for this project" / "make this kit fit my repo".

**Golden Rule applies:** propose every file change and get user approval before writing. Configuration is still a change.

---

## Phase 0: Installation State Detection

```bash
# How did the kit get here, and how complete is it?
ls .claude/.claudekit-manifest.json 2>/dev/null        # present = installer/ck init; absent = manual copy
ls CLAUDE.md CONSTITUTION.md 2>/dev/null               # standing context present?
grep -l '{{' CLAUDE.md CONSTITUTION.md 2>/dev/null     # unrendered placeholders?
python3 -c "import json;c=json.load(open('.claude/hooks/config.json'));print(c.get('project',{}))"
ls .claude/settings.json && ls .claude/hooks/*.sh | head -3
command -v ck >/dev/null && ck doctor 2>&1 | tail -5   # CLI available?
git rev-parse --show-toplevel 2>/dev/null              # hooks assume a git repo
```

Classify: **A** fresh manual copy (no manifest, no CLAUDE.md) · **B** installer run but unconfigured (placeholders or empty `project.*` commands) · **C** configured but drifted (stack changed, commands wrong). All three follow the same phases; A additionally needs `chmod +x .claude/hooks/*.sh` and a git-repo check.

## Phase 1: Learn the Project

Load **codebase-onboarding** and run its reconnaissance (manifests, framework fingerprints, entry points, test layout, CI files). You need five answers:

1. **Language(s) + build system** — including languages with no ClaudeKit template (Elixir, Haskell, Zig, …): the kit still works; only the four commands below and CLAUDE.md content differ.
2. **The four commands**: build, test, lint, coverage — from the project's own CI/Makefile/scripts if they exist (`.github/workflows`, `Makefile`, `package.json` scripts, `tox.ini`…). Prefer what CI runs over what docs claim.
3. **Architecture + layout** — for CLAUDE.md and for the reviewer's architecture scoring to make sense.
4. **Conventions** — commit style, naming, test naming (feeds CONSTITUTION articles).
5. **Danger zones** — generated dirs, vendored code, secrets locations (feeds `.agentignore` and protected patterns).

## Phase 2: Configure the Kit (the entire project-specific surface)

| # | What | How |
|---|------|-----|
| 1 | `.claude/hooks/config.json` → `project.build_cmd/test_cmd/lint_cmd/coverage_cmd` | Set from Phase 1. Empty string `""` = hooks silently skip that step — valid for languages without, e.g., a lint step. **This single file drives pre-commit, pre-push, post-implement, format-typecheck.** |
| 2 | `CLAUDE.md` (project root) | Missing → render from `.claude/local/CLAUDE.template.md` (replace every `{{PLACEHOLDER}}`; closest `templates/<lang>/CLAUDE.md` is a reference for idioms; no template → use `templates/generic/`). Exists → **enhance, never replace**. |
| 3 | `CONSTITUTION.md` | Render from `.claude/local/CONSTITUTION.template.md`; tune articles to reality: review thresholds (90/80 defaults), coverage targets the project can actually meet, protected files beyond the defaults (e.g., `migrations/`, `*.lock`). |
| 4 | Hook profile | Recommend `ECC_HOOK_PROFILE`: `standard` for teams starting out, `strict` once commands are trusted, via `.claude/settings.local.json` (gitignored). Verify hooks are executable and `settings.json` paths resolve. |
| 5 | `.agentignore` | Copy `templates/.agentignore`; add project's generated/vendored dirs so explore/planner skip them. |
| 6 | Reviewer routing | Python/TypeScript → note in CLAUDE.md that `/code-review` may use python-reviewer / typescript-reviewer; every other language → generic `code-reviewer` (works for all). |
| 7 | Optional | MCP servers (`templates/mcp/`) only if the project benefits; a mode default (e.g., token-efficient for huge monorepos). |

## Phase 3: Verify It Works Here (evidence, not assumptions)

```bash
bash -n .claude/hooks/*.sh                                   # syntax on this machine's bash
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m x"}}' \
  | ECC_HOOK_PROFILE=standard bash .claude/hooks/block-no-verify.sh; echo "exit=$? (want 2)"
# The four commands actually run:
<build_cmd> && <test_cmd> && <lint_cmd>                       # each as configured
# Ops engine round-trip on a scratch file:
python3 .claude/operations/scripts/validate-config-json.py <a-minimal-test-ops.json>
command -v ck >/dev/null && ck doctor --strict                # when CLI installed
```

Then run one real mini-pipeline: `/plan <tiny task>` → confirm plan + ops.json land in `.claude/plans/` → `/review` scores it. If any step fails, fix configuration — do not weaken hooks or guards.

## Phase 4: Enhance the Fit Over Time

- After recurring feedback or a recurring mistake → `/hookify` it into a prevention hook; after a useful session pattern → `/learn` it into a project skill.
- Record every adaptation decision in CLAUDE.md ("why coverage_cmd is empty", "why strict profile") — the next AI must not re-derive them.
- Revisit this skill when the stack changes (new language in the monorepo, CI migration): rerun Phases 1–3.
- Do **not** delete shipped agents/skills to "slim down" — they cost nothing until loaded; pruning is an upstream (ClaudeKit) decision.

## Common Mistakes

- Configuring commands from README claims instead of what CI actually runs.
- Replacing an existing CLAUDE.md instead of enhancing it.
- Setting `strict` before the four commands are proven green — every commit then blocks.
- Forgetting `chmod +x` on hooks after a manual copy, or adapting a non-git directory (hooks degrade).
- Claiming "adapted" without Phase 3 evidence.

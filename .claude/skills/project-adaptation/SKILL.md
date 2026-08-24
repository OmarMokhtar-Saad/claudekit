---
name: project-adaptation
description: "Use when ClaudeKit has just been added to a project (any language, any stack) or is misconfigured for it — teaches the AI to run `ck adapt` for the mechanical surface and to judge everything the verb cannot"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash
---

# Project Adaptation

## Purpose

ClaudeKit is language-agnostic by design: agents, commands, skills, and the operations engine work on any codebase. What is **project-specific** is a small configuration surface, and that surface has two halves with two different owners.

**The mechanical half belongs to `ck adapt`, not to you.** The verb detects the installation state against the install receipt, derives the four commands CI-first, writes them into `.claude/hooks/config.json` (owning exactly `project.build_cmd|test_cmd|lint_cmd|coverage_cmd` and preserving every other key), maintains a marked region in `.claude/local/CLAUDE.project.md`, reports the MCP budget, records the decision in the memory store, and re-stamps the receipt. It is idempotent, it refuses on a tree whose provenance it cannot establish, and it executes nothing it discovers. Reproducing that as instructions is how three adaptation surfaces come to exist instead of one — run the verb and read its report.

**The judgement half is yours:** learning the project, the root `CLAUDE.md`, `CONSTITUTION.md`, the hook profile, `.agentignore`, reviewer routing, whether the verb's derived commands are actually right, and proving the whole thing works here.

**Trigger when:** `.claude/` was just installed into a project · `CLAUDE.md` is missing or still contains `{{PLACEHOLDERS}}` · hooks skip steps because commands are unconfigured · the stack has no dedicated template · user says "set up ClaudeKit for this project".

**Golden Rule applies:** propose every file change and get user approval before writing. Configuration is still a change.

---

## Phase 0: Run the verb, then read its report

```bash
ck adapt            # or: python3 -m claudekit.cli.main adapt .
```

Each step prints `done`, `skipped (reason)` or `failed (reason)`; a failed step exits non-zero, a skip exits 0. That report replaces the state-detection shell block this skill used to carry — the verb classifies against the receipt, which no `ls` can do.

What each outcome asks of **you**:

| The verb says | What it means | Your move |
|---|---|---|
| `install done` | `.claude/` was absent, so the verb installed FULL mode itself | nothing; carry on reading the report |
| `install failed` | the installer exited non-zero and may have left a PARTIAL tree | inspect `.claude/` before re-running — a partial tree is no longer "fresh", so the next run takes the adopted branch |
| `ownership failed` | no usable receipt: absent or unparseable | `ck diff`, or re-run `ck init`. Never hand-edit past it |
| `pre-flight failed` | a whole-file kit asset differs from the receipt | resolve the difference or `ck update`. The refusal wrote nothing |
| `commands skipped` | nothing on disk evidenced a command | supply the real ones from Phase 1 |
| a command `(from profile:<stack>)` | a stack DEFAULT, not this project's evidence | confirm it or replace it. A wrong command in a push hook is worse than an empty one |
| `refusing to write it into a file the hooks execute` | a command was shell composition (`;`, `\|`, `&&`, a redirect, a substitution) — from CI **or from a profile**, both of which live in this repository | set the command deliberately in `hooks/config.json`, which adapt preserves. The verb will not put repo-controlled shell into a file the hooks run |
| `kept the existing value of <key>` | nothing evidenced that key, so YOUR value stands | nothing. This is the workflow in row 6 working |
| `mcp skipped` | budget unbounded, or already breached | a user decision, not a default to fill in |
| `memory skipped — already recorded` | the store is append-only | nothing; this is idempotence, not an omission |

A manual copy with no receipt is a **refusal**, not a fresh install. `chmod +x .claude/hooks/*.sh` and the git-repo check still apply to that case, and the verb prints the no-VCS warning itself.

## Phase 1: Learn the Project

Load **codebase-onboarding** and run its reconnaissance (manifests, framework fingerprints, entry points, test layout, CI files). The verb reads files; it does not understand the codebase. You need five answers:

1. **Language(s) + build system** — including languages with no ClaudeKit template (Elixir, Haskell, Zig, …): the kit still works; only the commands and CLAUDE.md content differ.
2. **The four commands — as a CHECK on the verb.** It already derived them CI-first and printed the provenance of each. Your job is to confirm what it found, and to supply what it could not: prefer what CI runs over what docs claim, exactly as the verb does.
3. **Architecture + layout** — for CLAUDE.md and for the reviewer's architecture scoring to make sense.
4. **Conventions** — commit style, naming, test naming (feeds CONSTITUTION articles).
5. **Danger zones** — generated dirs, vendored code, secrets locations (feeds `.agentignore` and protected patterns).

## Phase 2: Configure what the verb does not own

`hooks/config.json`'s four commands and the `CLAUDE.project.md` region are **the verb's**. Everything below is yours, applied through the operations engine after approval.

| # | What | How |
|---|------|-----|
| 1 | `CLAUDE.md` (project root) | Missing → render from `.claude/local/CLAUDE.template.md` (replace every `{{PLACEHOLDER}}`; closest `templates/<lang>/CLAUDE.md` is a reference for idioms; no template → use `templates/generic/`). Exists → **enhance, never replace**. The verb never touches this file: it is the project's front door and is unreceipted by definition. |
| 2 | `CONSTITUTION.md` | Render from `.claude/local/CONSTITUTION.template.md`; tune articles to reality: review thresholds (90/80 defaults), coverage targets the project can actually meet, protected files beyond the defaults (e.g., `migrations/`, `*.lock`). |
| 3 | Hook profile | Recommend `ECC_HOOK_PROFILE`: `standard` for teams starting out, `strict` once commands are trusted, via `.claude/settings.local.json` (gitignored). Verify hooks are executable and `settings.json` paths resolve. |
| 4 | `.agentignore` | Copy `templates/.agentignore`; add project's generated/vendored dirs so explore/planner skip them. |
| 5 | Reviewer routing | One reviewer for every language: `code-reviewer` loads `python-review-checklist` or `typescript-review-checklist` itself when the diff contains those extensions, so no per-language routing note is needed in CLAUDE.md. |
| 6 | The four commands, IF the verb could not derive them | Set them yourself from Phase 1. **A value you set survives the next `ck adapt`:** the verb overwrites only a key it can evidence, and reports the ones it kept. Empty string `""` = hooks silently skip that step — valid for a language with no lint step, and better than a guess. **This one file drives pre-commit, pre-push, post-implement, format-typecheck.** |
| 7 | Optional | MCP servers (`templates/mcp/`) only if the project benefits, and only within the budget the verb reported; a mode default (e.g., token-efficient for huge monorepos). |

## Phase 3: Verify It Works Here (evidence, not assumptions)

```bash
bash -n .claude/hooks/*.sh                                   # syntax on this machine's bash
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m x"}}' \
  | ECC_HOOK_PROFILE=standard bash .claude/hooks/block-no-verify.sh; echo "exit=$? (want 2)"
# The four commands actually run — the verb never executes what it discovers:
<build_cmd> && <test_cmd> && <lint_cmd>                       # each as configured
# Ops engine round-trip on a scratch file:
python3 .claude/operations/scripts/validate-config-json.py <a-minimal-test-ops.json>
command -v ck >/dev/null && ck doctor --strict                # when CLI installed
ck adapt                                                      # second run: must change nothing
```

Then run one real mini-pipeline: `/plan <tiny task>` → confirm plan + ops.json land in `.claude/plans/` → `/review` scores it. If any step fails, fix configuration — do not weaken hooks or guards.

## Phase 4: Enhance the Fit Over Time

- After recurring feedback or a recurring mistake → `/hookify` it into a prevention hook; after a useful session pattern → `/learn` it into a project skill.
- Record judgement decisions in CLAUDE.md ("why coverage_cmd is empty", "why strict profile"). The verb records its own decision in the memory store; do not duplicate that there.
- When the stack changes (new language in the monorepo, CI migration): re-run `ck adapt`, then re-judge Phases 1–3.
- Do **not** delete shipped agents/skills to "slim down" — they cost nothing until loaded; pruning is an upstream (ClaudeKit) decision.

## Common Mistakes

- **Re-implementing the verb in prose.** Detection, the four commands and the region are `ck adapt`'s. Duplicating them is the task-008 anti-pattern.
- Accepting a `(from profile:<stack>)` command as this project's evidence — it is a stack default.
- Hand-editing past an `ownership failed` or `pre-flight failed` refusal.
- Configuring commands from README claims instead of what CI actually runs.
- Replacing an existing CLAUDE.md instead of enhancing it, or writing into it from the verb's half.
- Setting `strict` before the four commands are proven green — every commit then blocks.
- Claiming "adapted" without Phase 3 evidence, or restating the verb's report as your own work.

---
description: "Adapt ClaudeKit to the current project — any language, any stack: run `ck adapt` for the mechanical surface, then judge the rest with evidence"
argument-hint: "[--verify-only|--reconfigure]"
model: sonnet
---

# Adapt Command

Fit ClaudeKit to this project. Works for any language — including stacks with no dedicated template (the kit is language-agnostic; only a small configuration surface is project-specific).

**Two halves, one owner each.** The mechanical half — detect the stack, derive the four commands CI-first, write them into `hooks/config.json`, maintain the marked region in `.claude/local/CLAUDE.project.md`, report the MCP budget, record the decision — belongs to the **`ck adapt` verb**. Do not reproduce it here in prose: it is deterministic, receipt-guarded, idempotent, and it refuses on a tree whose provenance it cannot establish. The **judgement** half — the root `CLAUDE.md`, `CONSTITUTION.md`, the hook profile, `.agentignore`, reviewer routing, and whether the verb's guesses are right — is what this command and the `project-adaptation` skill are for.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **golden-rule** - Propose changes, get approval before writing
- **project-adaptation** - The judgement half of the methodology

**On demand:** load **codebase-onboarding** when project-adaptation directs reconnaissance (it loads this itself).

## Task

Adapt ClaudeKit to this project: $ARGUMENTS

## Modes

| Flag | Behavior |
|------|----------|
| (default) | `ck adapt`, then Phases 1–3 of project-adaptation for everything the verb does not own |
| `--verify-only` | Phase 3 only — prove the current configuration works (hook block test, four commands, ops round-trip, doctor) |
| `--reconfigure` | Re-run `ck adapt` (it rewrites its own region in place) and re-judge Phase 2's remaining rows |

## Execution

1. **Run the verb** and read its report:

   ```bash
   ck adapt            # or: python3 -m claudekit.cli.main adapt .
   ```

   Every step prints `done`, `skipped (reason)` or `failed (reason)`, and a failed step exits non-zero. The report is evidence — quote it rather than restating it.
2. **Act on what the verb reported, and only that.**
   - `ownership failed` / `pre-flight failed` — a kit asset differs from the receipt. Run `ck diff`, resolve it, or run `ck update`. Do **not** hand-edit around a refusal; it means this tree's provenance is unknown.
   - `install done` — the tree had no `.claude/`, so the verb installed FULL mode itself. `install failed` — the installer exited non-zero and the tree may be partial; inspect it before re-running.
   - `commands skipped`, or a command whose provenance reads `profile:<stack>` — nothing on disk evidenced it. Supply the real command from Phase 1 and set it yourself; a wrong command in a push hook is worse than an empty one, and a value you set survives the next run (the verb reports it as `kept the existing value of …`).
   - `refusing to write it into a file the hooks execute` — a derived command was shell composition, not a single invocation. The verb will not put repo-controlled shell into a file the hooks run; set that command deliberately.
   - `mcp skipped` — the budget is unbounded or already breached. That is a decision for the user, not a default to fill in.
3. **Learn the project** via codebase-onboarding reconnaissance (skill Phase 1) — the verb reads files, it does not understand the codebase.
4. **Propose the judgement rows** the verb does not own: root `CLAUDE.md` (render-or-enhance), `CONSTITUTION.md` tuning, hook profile, `.agentignore`, reviewer routing, optional MCP servers. Wait for approval.
5. **Apply approved changes** — through the operations engine, never by hand.
6. **Verify** with evidence (skill Phase 3) — paste command output; no unverified "it works".
7. **Report**: the verb's report, then what you changed on top of it, what you skipped and why, and the recommended profile.

## Usage Examples

- `/adapt` — first session after `ck init` in any project
- `/adapt --verify-only` — health-check an existing configuration
- `/adapt --reconfigure` — stack changed (e.g., migrated Jest→Vitest); re-run the verb and re-judge the rest

## Related

`ck adapt` is the verb; `/adapt` is the judgement wrapper around it; `/onboard` learns the codebase and writes CLAUDE.md content. Run `/adapt` first in a fresh install; it delegates recon to the same skill `/onboard` uses.

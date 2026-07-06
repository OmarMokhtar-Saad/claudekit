# Task 007 — Claude Code Plugin & Marketplace Packaging

## Problem
ClaudeKit's contents — agents, commands, skills, hooks, MCP config — are exactly what Claude Code's plugin system (GA since Oct 2025) packages, distributes, updates, and surfaces in marketplaces. There are zero hits for `plugin.json` or `marketplace` anywhere in the repo (missing-features #1). Shipping only a copy-in `install.sh` means: no discovery channel, no central updates (the problem task 005 solves by hand), no version pinning for consumers, and manual drift for every installed project. This is the single biggest strategic omission — distribution through the native channel dwarfs every other growth lever (oss-excellence rank 6, "Very High" impact).

## Root Cause
The kit predates (or ignored) the plugin GA; distribution energy went into install.sh and a pip wrapper that never worked (task 001). The `.claude/` layout is already plugin-shaped, so this is a manifest-and-metadata task, not a rearchitecture.

## Files
- New: `.claude-plugin/plugin.json` (name, version, description, author)
- New: `.claude-plugin/marketplace.json` (repo doubles as a single-plugin marketplace)
- New (if hooks require it): plugin `hooks/hooks.json` mapping from `.claude/settings.json`
- `templates/mcp/mcp-settings.json` → plugin `.mcp.json` (pin versions first — task 014)
- `.github/workflows/ci.yml` (plugin-validation job)
- `README.md` (document `/plugin install` as the primary path)
- `claudekit.manifest.json` (from task 005 — plugin version must derive from the same single source)

## Priority
**P0** (strategic; missing-features gap matrix #1). Sequenced after v2.1's correctness fixes — do not distribute broken hooks through a shiny new channel.

## Estimated Time
3–5 days for the fat plugin + validation; +2–3 days if splitting sub-plugins.

## Risk
Low–Medium. Plugin-format specifics (hook wiring shape, MCP embedding) must be validated against the current Claude Code release — build against the official schema, not memory. Name collision: `claudekit` is a known npm-ecosystem Claude Code toolkit (carlrannaberg/claudekit); marketplace naming needs the same disambiguation decision as PyPI (task 001). Dual-channel maintenance (plugin + install.sh) is a drift risk — mitigate by generating both from `claudekit.manifest.json`.

## Step-by-step Implementation
1. Verify current plugin/marketplace schema against Claude Code docs; capture in `docs/reference/plugin.md`.
2. Author `.claude-plugin/plugin.json`: name (pending disambiguation decision), version **read from the single version source** (release CI templates it), description, author, component paths pointing at the existing `.claude/` tree.
3. Map hooks: translate `.claude/settings.json` hook entries into the plugin hook format; ensure the exit-2 semantics from task 003 are in place first (a marketplace plugin with fail-open guards would scale the false-guarantee problem).
4. Embed MCP config from `templates/mcp/mcp-settings.json` with pinned versions (task 014 prerequisite) — or omit MCP from the base plugin and ship it as an optional sub-plugin.
5. Author `.claude-plugin/marketplace.json` so `claude /plugin marketplace add <slug>` works directly against the repo.
6. **Split decision:** ship one fat `claudekit` plugin first; evaluate `claudekit-security`, `claudekit-prp`, `claudekit-opensource` sub-plugins in a follow-up (the command namespaces already cluster this way). Don't block v3.0 on the split.
7. CI job: validate plugin.json against the official schema; cross-check every referenced agent/command/skill exists on disk; version matches pyproject.
8. Docs: README install section becomes two tabs — `/plugin install` (primary) and `install.sh` (self-contained copy-in for the zero-lock-in audience); document the trade-offs (plugin = auto-update; copy-in = fork-and-own).
9. Release flow: tagging a release updates plugin.json version + marketplace metadata via the release workflow.

## Acceptance Criteria
- From a clean machine: `claude /plugin marketplace add <slug>` then plugin install yields working `/plan`, `/review`, `/implement` and firing hooks in a fixture project.
- Plugin update path demonstrated: install vN, tag vN+1, plugin updates, new asset visible.
- CI plugin-validation job green; fails when a command referenced in plugin metadata is deleted.
- README documents both channels with the plugin first.
- Plugin version == pyproject version == git tag (extends task 006's CI gate).

## Testing Strategy
- CI schema validation + referential-integrity job (step 7).
- Manual end-to-end on macOS + Linux against the current Claude Code release, scripted into a `tests/plugin-smoke.sh` where headless verification is possible.
- Eval framework (task 010) runs its fixture pipeline against a plugin-installed environment, not just a copy-in install — proving channel parity.

## Rollback Plan
The plugin is additive — `.claude-plugin/` files can be deleted or the marketplace listing pulled without affecting install.sh users. If a broken plugin version ships, publish a patch tag (plugin channel makes the fix propagate automatically — the exact property this task exists to gain).

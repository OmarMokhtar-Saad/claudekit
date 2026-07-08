# Plan: Legacy-install lifecycle support (ck diff fallback + custom-asset preservation)

## Problem

All real-world ClaudeKit installs surveyed (LeanApis, ai-agent-system, qaforge-ai,
AppiumLens, MobileUIAutomator, qa-agents) predate the install manifest. For them:

- `ck diff` errors out ("No .claudekit-manifest.json") — zero drift visibility.
- `ck update` errors out — no upgrade path except `ck init --force`.
- `ck init --force` swaps `.claude/` wholesale: project-custom assets (e.g.
  AppiumLens' 15 project skills, LeanApis' installed optional templates) are
  stranded in the backup dir, silently dropped from the live tree.

## Changes (all stdlib-only, bash-3.2-safe)

### 1. `ck diff` source fallback (src/claudekit/cli/main.py)

When no manifest exists, fall back to comparing the project's `.claude/` managed
asset dirs (`agents/ commands/ skills/ hooks/ operations/scripts/ settings.json`)
against the kit source tree (`find_claudekit_root()`), classifying:
`identical` / `differs` / `custom` (project-only) / `not-installed` (kit-only).
Clearly label output as source-comparison (provenance unknown). Exit 0.

When a manifest exists AND kit source is findable, refine `modified` into:
- `locally modified` (kit source hash == manifest hash, file changed locally)
- `kit updated` (file matches manifest, but kit source moved on) — NEW bucket
- `both changed` (all three differ)
Also list `custom` files (present under managed dirs, absent from manifest).

### 2. Custom-asset preservation on reinstall (install.sh)

After the atomic swap + new-manifest write, restore from the backup any file that
(a) existed in the old tree, (b) does not exist in the new tree, and
(c) old manifest present ? not listed in old manifest : lives under
    agents/ commands/ skills/ (legacy heuristic).
Print each restored path; restored files are NOT added to the manifest (they are
custom, `ck diff` will report them as such). Everything remains in the backup
regardless — fully reversible.

### 3. `ck update` legacy support (src/claudekit/cli/main.py)

No manifest → warn "pre-manifest install", show what will happen, require
confirmation (or `--yes`), then run installer `--force --yes` in full mode.
Preservation in install.sh (change 2) carries the project's extra assets across.

## Tests (behavioral)

- test_cli.py: diff fallback classifies identical/differs/custom/not-installed;
  diff three-way buckets with manifest + source; update on manifest-less tree
  proceeds with yes=True (monkeypatched installer).
- test_install.py: real reinstall preserves a custom skill (manifest case and
  legacy case); obsolete-kit file NOT resurrected when old manifest lists it.

## Not in scope

- Promoting optional templates (13 commands, i18n-workflow) into core — they stay
  opt-in templates (consolidation, task 008).
- Domain QA pack — separate decision after asset review completes.

## DoD

pytest 516+ green · ruff · mypy · gen-docs --check · shellcheck install.sh ·
CHANGELOG [Unreleased] · conventional commit.

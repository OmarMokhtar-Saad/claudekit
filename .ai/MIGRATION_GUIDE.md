# Migration Guide

## For user projects: v2.0.x → v2.1.0

v2.1 is a repair release — the biggest "breaking" change is that **enforcement now actually works**.

1. **Update the install:** `pip install -U claude-kit && ck update <project>` (or re-run `install.sh`). The installer backs up first; `ck diff` shows which managed files you modified locally (re-apply after).
2. **Hooks go live.** Old installs never had `settings.json` copied, so hooks were inert. After update: blocking hooks really block (exit 2). If workflows suddenly stop, that's enforcement working — see the profile note below.
3. **Set your profile.** `ECC_HOOK_PROFILE`: `standard` (default; command-guard warns), `strict` (blocks), `minimal` (off). Local override in `.claude/settings.local.json` (never overwritten by updates).
4. **Ops filename tolerance:** both `*.ops.json` and `ops-*.json` now match everywhere. Plans live in `.claude/plans/` (old `operations/` search paths are gone).
5. **Agent invocation changed:** any custom prompts that used `--dangerously-skip-permissions` must switch to scoped `--allowedTools` (see `.claude/agents/_shared/INVOCATION.md`).
6. **Version sanity:** `ck doctor --strict` after updating; it validates 19 checks including hook registration and manifest integrity.
7. **Manifest introduced:** `.claude/.claudekit-manifest.json` now tracks managed files (enables `ck diff/update/uninstall`). Don't edit or delete it.
8. **Secret scanning got stricter:** single-quoted secrets are now caught; commits with staged secrets block.

Pure-pip note: v2.1 wheels bundle the asset tree, so `pip install claude-kit && ck init` works without a git checkout; `CLAUDEKIT_HOME` still overrides asset resolution.

## For maintainers: repo-layout changes in v2.1

Top-level `src` package → true src-layout `src/claudekit/` (git-renamed); version single-sourced via importlib.metadata (fallbacks in `__init__.py` + `shared.py`); CHANGELOG renumbered (1.3.0→2.1.0); canonical slug `OmarMokhtar-Saad/claudekit`; hooks refactored onto `lib.sh`; CI rewritten (11 honest jobs). If you're rebasing pre-July-2026 branches, expect conflicts in all of the above.

## Future migrations (planned, not yet applicable)

- **Task 008 consolidation** will merge ~10 agents and ~13 skills — a migration table (old → new asset) must ship with it; users referencing merged agents by name will need renames.
- **Task 007 plugin packaging** may change the primary install channel to `/plugin install`; install.sh becomes legacy.
- **Managed/user disk split** (`.claude/claudekit/` vs `.claude/local/`) will relocate managed files; `ck update` will handle it, manual installs won't.

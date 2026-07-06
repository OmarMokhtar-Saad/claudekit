# Task 005 — Installer Safety, Install Manifest & `ck update`

## Problem
The installer can destroy user data and there is no upgrade path:
1. **Destructive ERR trap.** `install.sh:94-101` sets `trap '_cleanup_on_failure' ERR` → `rm -rf "$DEST"` where `DEST="$TARGET_DIR/.claude"`. The trap is installed *before* the overwrite prompt and doesn't distinguish "directory I created" from "directory that already existed." A reinstall over a customized `.claude/` that fails mid-way (missing template, sed error on a `|` in a command — install.sh:306-337, permission problem) permanently deletes the user's CLAUDE.project.md, CONSTITUTION.md, and custom skills.
2. **No update channel.** The only "upgrade" is `--force` blind overwrite; `docs/CUSTOMIZATION.md:179-187` literally tells users to back up first. No installed-version manifest, no uninstall, no diff. Every installation forks permanently at install time (architecture-review F-21, missing-features #2).
3. **curl|bash guaranteed disaster.** When piped, `BASH_SOURCE[0]` is empty → `SCRIPT_DIR` = cwd → the `cp "$CLAUDE_SRC"/agents/*.md` at line 160 fails → the ERR trap `rm -rf`s the user's `.claude`. Interactive `read` prompts (lines 82, 107) also consume the piped script as stdin.
4. **Not idempotent; lying output.** `--force` copies over without clearing (stale hooks from old versions keep firing); the epilogue (install.sh:399-413) prints hardcoded counts/lists ("37 commands", a 28-agent name list, "15 hooks") while ignoring the computed `AGENT_COUNT`/`CMD_COUNT`/etc. variables; actual post-install command count is 52 (39 core + 13 templates).
5. **Misc:** interactive prompts break CI (no `--yes`); `TARGET_DIR` falls back to the raw string if `cd` fails (line 85); kotlin misdetection (any `build.gradle.kts` mentioning "kotlin" — line 120); `package.json` alone ⇒ "typescript"; `CLAUDEKIT_HOME` advertised in CLI error (`src/cli/main.py:53`) but never read (`find_claudekit_root`, lines 31-41).

## Root Cause
install.sh is 470 lines of imperative copy logic with no record of what it installed (no manifest), so safe cleanup, idempotency, upgrade, and honest reporting are all impossible by construction (F-17). The trap was written for the "fresh install" case only.

## Files
- `install.sh:85, 94-101, 104-112, 115-139 (detection), 158-160, 306-337 (sed), 363-384 (.gitignore), 399-426 (epilogue)`
- `src/cli/main.py:31-53` (`find_claudekit_root`, CLAUDEKIT_HOME), new `cmd_update`, `cmd_uninstall`
- New: `.claude/.claudekit-manifest.json` (written at install), `claudekit.manifest.json` (repo component manifest, arch F-17)
- `docs/CUSTOMIZATION.md:179-187` (update the destructive-reinstall guidance)
- **Also fixes F-6 here:** install.sh must copy/merge `.claude/settings.json` (currently never installed — hooks dead on arrival)

## Priority
**P0** for the data-loss trap + settings.json; **P0–P1** for manifest + `ck update`.

## Estimated Time
1 week (trap/staging/settings.json: 1 day; manifest + update command: 3–4 days).

## Risk
Medium. `ck update`'s three-way logic must never misclassify a user-modified file as pristine — hash comparison against the recorded manifest makes this deterministic. Staging-swap changes install semantics subtly (partial installs no longer exist — good, but scripts that watched `.claude` appear incrementally would change behavior; none known).

## Step-by-step Implementation
1. **Safe install transaction:** install into `.claude.staging.$$/`; on success, `mv` existing `.claude` → `.claude.bak-<ts>` and atomically swap staging in; on failure, remove only the staging dir. Print the backup path; offer cleanup.
2. **Copy settings.json** (merge non-destructively if the target has one — prefer writing ClaudeKit hooks into `settings.local.json` or merging keys via the python helper already used at line 348). `--minimal` emits a reduced hook map.
3. **curl|bash guard:** at top, `[[ -d "$CLAUDE_SRC" ]] || { print_err "Clone the repo and run ./install.sh"; exit 1; }`; before any `read`, check `[[ -t 0 ]]` or `--yes`.
4. **`--yes` / `--non-interactive`** flag; prompts fail loudly (not hang) when stdin isn't a TTY.
5. **Manifest at install time:** write `.claude/.claudekit-manifest.json` — `{version, timestamp, mode, language, files: {relpath: sha256}}`.
6. **Repo component manifest** (`claudekit.manifest.json`): components → src dir, profile (minimal/full/opt), post-steps. install.sh's copy phase becomes a loop over it (kills the per-directory special cases that caused settings.json to be forgotten).
7. **`ck update`:** read installed manifest → fetch/locate target version → per file: hash matches manifest (user didn't touch) → replace; hash differs → keep user file, write `.new` alongside, report; upstream-removed → prompt. Run applicable migrations (task 006/roadmap). Write the new manifest. `ck diff` previews. Reuse `restore-backup.py` machinery for downgrade.
8. **`ck uninstall`:** remove manifest-listed files only, revert the `.gitignore` entries install.sh appended (lines 363-384), keep `.claude/local/` unless `--purge`.
9. **Honest epilogue:** print only computed counts; add "Step 0: run `claudekit doctor`" to next steps (DX-13).
10. **Detection fixes:** JS-vs-TS via tsconfig presence; `find -maxdepth 3` for csproj/sln; kotlin only when kotlin sources exist; confirmation prompt ("Detected python — continue? [Y/n]", skipped with `--yes`).
11. **sed hardening:** escape `&`, `|`, `\` in replacement values (or use the python templating already invoked at line 348).
12. **CLI:** honor `CLAUDEKIT_HOME` in `find_claudekit_root()`; `doctor` reads the install manifest for expected counts and verifies every settings.json hook command points at an existing executable file (DX-14/15).

## Acceptance Criteria
- Simulated mid-install failure (unreadable source file) against a pre-existing customized `.claude/` leaves the original **byte-identical** and prints the staging-cleanup message. (testing-review missing test 13)
- Post-install, `.claude/settings.json` exists and is valid JSON; `doctor` reports zero hook-wiring warnings.
- `ck update` from a fixture v2.1 install to v2.2: pristine files replaced, a hand-edited agent preserved with `.new` sibling, report lists all three classes.
- `bash -c "curl ... | bash"` simulation exits 1 with the clone message; nothing deleted.
- `./install.sh target --full --yes` runs with stdin closed.
- Epilogue counts equal `find`-computed reality.

## Testing Strategy
- Extend `tests/test_install.py`: `--full` mode (only `--minimal` is currently tested), `--force` over existing, ERR-trap simulation, settings.json presence, `--with-mcp/--with-i18n`, language-detection matrix (go.mod, Cargo.toml, Package.swift, *.csproj, Gemfile, composer.json, build.gradle.kts), config.env injection resistance (`EVIL=$(touch /tmp/pwned)` ignored).
- New `tests/test_update.py`: three-way classification matrix; uninstall reverts .gitignore.
- CI integration job: install → doctor --strict → update → doctor --strict (task 011).

## Rollback Plan
The staging-swap design is itself the rollback mechanism (`.claude.bak-<ts>` always exists after an overwrite). `ck update` failures restore from the same backup + manifest. If the manifest-driven copy loop regresses, install.sh's previous copy blocks are one revert away; ship v2.1 with the old path behind `--legacy-install` for one release as a safety valve.

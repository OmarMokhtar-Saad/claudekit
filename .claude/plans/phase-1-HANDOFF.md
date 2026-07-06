# Phase 1 — Handoff to Next Agent

> **STATUS: PHASE 1 COMPLETE (2026-07-06).** All four waves (A–D) landed on branch
> `phase-1-fix-whats-broken`. **506 tests passing**; ruff + mypy clean; docs-drift clean.
> Commits: `987192a` (Waves A/B + enhancement suite), `66d5af5` (002 security wiring),
> `00a86f3` (006 docs + 011 CI), `fed37e9` (dormant-hook wiring + CLAUDEKIT_HOME),
> `969b242` (ck-init end-to-end fixes), `4ef8d38` (commit-quality block test).
> Not yet: merge to `main`, tag `v2.1.0`, PyPI publish (all **user-gated** — see Open decisions).
> Exit criteria met: `ck init && ck doctor` clean 19/19; every enforcement hook has a
> demonstrable-block test; no doc/version disagrees with the tree (CI-enforced); the CI
> `test` job runs the whole suite (can't pass with a failing test). The only residual on
> criterion 1 is a *pure-PyPI* standalone `pip install claudekit && ck init` — needs assets
> bundled into the wheel (Phase-2 packaging) + the name decision. `ck init` works today from
> a checkout or with `CLAUDEKIT_HOME`.

**Repo:** claudekit · **Branch:** `phase-1-fix-whats-broken` (6 commits; not yet merged to main)
**Plan of record:** `.claude/plans/phase-1-fix-whats-broken.md`
**Source audit/tasks:** `review/roadmap.md §1`, `review/tasks/00{1..6}.md`, `review/tasks/011-*.md`
**Test command:** `python3 -m pytest tests/ -q` → **506 passing, 0 failing**

Phase 1 = v2.1 "Fix What's Broken". Every item is a defect in something already advertised.
Exit criteria: `pip install claudekit && ck init && ck doctor` works clean; every enforcement
hook demonstrably blocks; no version/doc disagrees with the tree; CI can't pass with a failing test.

---

## ⚠️ READ FIRST — session gotchas

1. **`ECC_HOOK_PROFILE=minimal` is active** via `.claude/settings.local.json` (gitignored). This
   disables the kit's own enforcement hooks so you can Edit/Write source files normally. If it is
   NOT set in your session, `ops-enforcement.sh` will **block Edit/Write** to any file outside
   `.claude/` and docs (it now genuinely exits 2). Either keep the local override or write source
   via Bash heredocs. See CONTRIBUTING.md "Working on ClaudeKit itself".
2. **Hooks now really enforce.** The blocking hooks were fixed to `exit 2` + stderr this phase, so
   they are live. Tests that assert blocking force `ECC_HOOK_PROFILE=standard` per-subprocess.
3. **Nothing is committed.** The user deferred committing. When you commit, branch off main first.
   End commit messages with the Co-Authored-By line for Claude Opus 4.8 (1M context).
4. **Two open decisions (need the user):**
   - **PyPI name**: `claudekit` collides with an npm package in the same niche. Decide before publish.
   - Canonical GitHub slug is **`OmarMokhtar-Saad/claudekit`** (already applied where touched;
     README/badges still need the full sweep in task 006).

---

## DONE this phase (working tree, tested)

### Wave A
- **001 Packaging** — `pyproject.toml` build-backend → `setuptools.build_meta`; true src-layout
  `src/claudekit/{cli,security}` (git-renamed); single version via `importlib.metadata` (fallback
  2.1.0); entry points `claudekit.cli.main:main`; `requires-python>=3.9`, PEP 639 license, py3.13.
  `tests/test_packaging.py` guards it. Wheel builds & installs; `claudekit`/`ck` report 2.1.0.
- **011 CI (day-one slice)** — removed both `|| true`; matrix `3.9/3.10/3.12/3.13`; added
  `package-smoke` + `permission-gate` jobs.
- **§1.6 prompt-layer** — planner.md Phase 3 now references `generate-operations-config` (was an
  embedded schema that failed the kit's own validator); `execute-operations-config` skill rewritten
  to run everything through `execute-json-ops.py` (no manual Edit); `MAX_DELETIONS=3` guard
  (GUARD 26) added to `validate-config-json.py`.
- **006 P0 subset** — SECURITY.md supported versions → 2.x + disclosures; CHANGELOG renumbered
  (1.3.0→2.1.0, correction note, `[Unreleased]`, phantom agents removed); `shared.py` 3.1.0→2.1.0.

### Wave B
- **004 Skip-permissions** — removed all 5 `--dangerously-skip-permissions` (plan/review/refine),
  replaced with scoped `--allowedTools`; `_shared/INVOCATION.md` is the single source of truth;
  CI `permission-gate` blocks reintroduction; SECURITY.md discloses history.
- **003 Hooks** — `.claude/hooks/lib.sh` (resolve_root, hlog logging parse failures, `deny` =
  stderr+exit 2, OPS_FIND_EXPR/OPS_REGEX matching BOTH `*.ops.json` and `ops-*.json`, quote
  classes). All 4 blocking hooks (block-no-verify, ops-enforcement, config-protection,
  commit-quality) now **exit 2 + stderr + fail closed**. Telemetry fixed: post-tool-use.sh reads
  stdin JSON (env vars were never set); settings.json PostToolUse/PostToolUseFailure/Stop fixed;
  cost-tracker now counts. Detection fixes: `\x27` secret regex, bash-3.2 `${VAR,,}`→`tr`,
  `--no-verify` substring→git-scoped+quote-stripped, new-pyproject allowance. Removed the two
  bypass hints. `tests/test_hooks_behavioral.py` (14 tests) proves it.
- **005 Installer** — staging + backup + atomic swap (kills `rm -rf $DEST` data-loss trap);
  **settings.json now installed** (was omitted → dead hooks); `.claudekit-manifest.json` (version +
  per-file sha256); curl|bash guard; `--yes`/`--non-interactive`; honest computed epilogue; cd
  fallback fix. `tests/test_install.py` +5 safety tests (incl. byte-identical mid-failure proof).

---

## DONE — Wave C & D (this phase, tested)

### Wave C
- **002 Security** — fixed `from_config` (`hooks`→`security`), chained-command + `$(...)`/backtick
  segment validation, removed bash/sh/env/xargs from the allowlist, added find -delete/-exec, IFS
  evasion, python interpreter-smuggling detection; `path_guard` relative-symlink + component-level
  `.env` matching + named `MAX_DIRECTORY_DEPTH`. Wired: `claudekit check-command`/`check-path`,
  `python3 -m claudekit.security`, and the fail-closed `command-guard.sh` PreToolUse hook
  (strict=block, standard=warn, minimal=off). ARCHITECTURE.md/SECURITY.md rewritten as "speed
  bump, not a sandbox." Ops-script `validate_path` cross-references the canonical module (kept
  dependency-free for standalone runs). +bypass-corpus + CLI tests.
- **§1.6 Prompt-layer** — already landed in Wave A.

### Wave D
- **006** — `scripts/gen-docs.py` (filesystem = source of truth; `--check` = docs-drift gate);
  corrected all counts to **28 agents / 39 commands / 73 skills / 19 hooks**; canonical slug
  `OmarMokhtar-Saad/claudekit` everywhere (incl. i18n); rewrote `docs/HOOKS.md` around
  settings.json + `ECC_HOOK_PROFILE`; linked `docs/cli.md`; fixed CUSTOMIZATION "back up" text.
- **011** — CI `test` runs the whole `tests/` on ubuntu+macos × py3.9/3.10/3.12/3.13; new jobs:
  coverage (security ≥85%), lint (ruff+mypy), docs-drift, dangling-hooks, install-integration
  (install.sh→doctor); SHA-pinned actions + `.github/dependabot.yml`; `doctor --strict`.
- **Deferred fixes swept**: wired dormant `file-guard`/`prompt-injection-scanner` as advisory
  strict-only wrappers; `CLAUDEKIT_HOME` honored; `find_claudekit_root` src-layout depth bug fixed;
  `ck init --full/--minimal/--yes`; `skills-registry.json` dangling ref (`i18n-workflow`→
  `i18n-patterns`); `MANIFEST.in`; new `test_registry.py`.

---

## GENUINELY REMAINING (Phase 2 / user-gated — NOT Phase-1 blockers)

- **Publish (user-gated):** merge `phase-1-fix-whats-broken`→`main`; tag `v2.1.0`; exercise
  `release.yml`; PyPI publish. **Blocked on the PyPI-name decision.**
- **Wheel-bundled assets (Phase-2 packaging):** to make a *pure* `pip install claudekit && ck init`
  work with no checkout, bundle `.claude/`/`templates/`/`install.sh` into the wheel (they only reach
  the sdist today via `MANIFEST.in`). Until then `ck init` needs a checkout or `CLAUDEKIT_HOME`.
- **New CLI features (Phase 2 — the "no new features" thesis excludes these from Phase 1):**
  `ck update` three-way merge (manifest foundation exists), `ck uninstall`, `ck diff`,
  settings.json merge-on-existing.
- **Installer detection refinements:** JS-vs-TS via tsconfig, csproj maxdepth, sed hardening for
  `& | \``.
- **003 P2 rot (low):** auto-checkpoint stash-SHA fix; suggest-compact stale-lock + BSD date;
  format-typecheck data-source rewrite.
- **004 (low):** doc sweep of every wrapper command + `HANDOFF_PROTOCOL.md` to cite INVOCATION.md.

---

## Suggested next step
Get the user's PyPI-name decision, then merge to `main` and tag `v2.1.0`. After that, the top
Phase-2 item is wheel-bundled assets (unblocks standalone `pip install`), then `ck update`.

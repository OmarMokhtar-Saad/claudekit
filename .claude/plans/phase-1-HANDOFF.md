# Phase 1 — Handoff to Next Agent

**Repo:** claudekit · **Branch:** main (nothing committed yet — all work is in the working tree)
**Plan of record:** `.claude/plans/phase-1-fix-whats-broken.md`
**Source audit/tasks:** `review/roadmap.md §1`, `review/tasks/00{1..6}.md`, `review/tasks/011-*.md`
**Test command:** `python3 -m pytest tests/ -q` → currently **459 passing, 0 failing**

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

## REMAINING in Phase 1

### Wave C — 002 Security (full wiring) — P1, ~3–5d
Fix `src/claudekit/security/{command_validator,path_guard}.py` bypasses, then WIRE them:
- `command_validator.py`: reads `config.get("hooks")` but schema puts safeMode/allow/block under
  **`security`**; `bash -c`/`&&`-chaining/`xargs`/`find -delete` all pass (only argv[0] checked);
  `\$\(` over-bans. `path_guard.py`: relative-symlink resolved against cwd not link dir; `.env`
  substring match. Then: expose `claudekit check-command`/`check-path`, wire a **fail-closed**
  PreToolUse Bash guard under `ECC_HOOK_PROFILE=strict`, dedupe the 3 parallel impls, fix the
  ARCHITECTURE.md claim. `tests/test_security.py` exists (imports already fixed to
  `claudekit.security.*`). See `review/tasks/002-wire-security-layer.md`.

### Wave D
- **006 full** — `scripts/gen-docs.py` + docs-drift CI job; regenerate counts (README says
  13/17/45; reality ~28 agents / 52 commands / 73 skills); one canonical slug everywhere; rewrite
  `docs/HOOKS.md` around settings.json + `ECC_HOOK_PROFILE`; link `docs/cli.md`. Also update the
  now-obsolete `docs/CUSTOMIZATION.md:179` "back up first" text (installer auto-backs-up now).
  See `review/tasks/006-*.md`.
- **011 full** — run entire `tests/` in one job; add macOS matrix; install→`doctor --strict`
  integration job; coverage gate; ruff/mypy; manifest-derived count checks; dangling-hook-path
  check; SHA-pin actions + dependabot. See `review/tasks/011-*.md`.

### Deferred inside completed tasks (pick up opportunistically)
- **001**: tag `v2.1.0`, exercise `release.yml`, PyPI publish (blocked on name decision); ship
  `.claude/` assets in the wheel (`MANIFEST.in`) OR honor `CLAUDEKIT_HOME` in `find_claudekit_root`.
- **005**: `ck update` three-way merge (manifest foundation is in place), `ck uninstall`, `ck diff`,
  settings.json merge-on-existing, detection refinements (JS-vs-TS via tsconfig, csproj maxdepth),
  sed hardening for `& | \`.
- **003 (P2 rot)**: wire dormant `templates/hooks/file-guard.sh` + `prompt-injection-scanner.sh`
  into settings.json (anchor patterns first); auto-checkpoint stash-SHA fix; suggest-compact
  stale-lock + BSD date; format-typecheck data-source rewrite.
- **004**: full doc sweep of every wrapper command + `HANDOFF_PROTOCOL.md` to cite INVOCATION.md.

---

## Suggested next step
Commit the Phase 1 work on a branch (it's a large, tested, coherent changeset), THEN start
**002 (security wiring)** — it's the last substantive P1 and completes the security story that
004+003 began. Confirm the PyPI-name decision with the user before any publish/tag work.

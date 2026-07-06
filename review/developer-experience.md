# ClaudeKit — Developer Experience Review

**Reviewer role:** DX Engineer
**Date:** 2026-07-05
**Scope:** Full new-user journey: discovery → README → install → first init → first command → customization
**Version under review:** pyproject `2.0.0` / CLI `1.1.0` / installer banner `2.0.0` (see finding DX-3)

**Overall DX score: 54/100**

---

## 1. The New-User Journey, Walked End-to-End

### 1.1 Discovery → README (first 60 seconds)

**What works:** The README opens with a strong value proposition ("Structured planning. Review gates. Safe execution."), a pipeline diagram, and a Quick Start within the first screen. Badges convey version/license/language at a glance.

**Friction:**

| # | Friction | Evidence | Fix |
|---|----------|----------|-----|
| DX-1 | Two different install paths (bash and pip) exist but the README shows **only** the bash path. `pip install -e .` and the `ck` alias are documented only in `docs/cli.md`, which is not linked from the README's Documentation table. | `README.md:41-76` vs `docs/cli.md:5-9`; `pyproject.toml:29-31` defines `claudekit` and `ck` entry points | Add an "Install via pip" tab to Quick Start; link `docs/cli.md` from the Documentation table; mention `ck` in the first code block a user sees. |
| DX-2 | Clone URL in README (`github.com/omarmokhtar/claudekit`) disagrees with pyproject (`github.com/OmarMokhtar-Saad/claudekit`). One of them 404s for a real user; the CI badge points at the first. | `README.md:6,46`; `pyproject.toml:34` | Pick the canonical repo slug and grep-replace across README, CONTRIBUTING, badges, schema `$id`. Add a CI check that greps for the wrong slug. |

### 1.2 Install path A: `install.sh` (traced)

`bash -n install.sh` passes (syntax OK). Flow, as executed:

1. Parse args (`--full|--minimal|--language|--with-mcp|--with-i18n|--force|--help`).
2. **Interactive prompt** if no target dir given (`install.sh:80-83`) — blocks CI/scripted use.
3. Resolve target; hard-fail if dir doesn't exist (no offer to create it).
4. Set `trap '_cleanup_on_failure' ERR` which does **`rm -rf "$DEST"`** (`install.sh:94-101`).
5. Existing-install check → `Overwrite? (y/N)` prompt (`install.sh:104-112`).
6. Language auto-detect (11 languages) — **printed before the banner**, so the first line of output is a raw `[*] Auto-detected language:` line, then the banner appears (`install.sh:141-151`, cosmetic but sloppy).
7. Copy agents / commands / operations scripts / (full mode) skills + hooks / modes / `.agentignore` / optional MCP + i18n.
8. Parse `templates/<lang>/config.env` via a safe key=value allowlist (good — no `source`).
9. `sed`-generate `CLAUDE.project.md` and `CONSTITUTION.md`.
10. Patch `.claude/hooks/config.json` with build/test/lint/coverage commands via inline python3.
11. Append ClaudeKit entries to `.gitignore`.
12. Print summary + next steps.

**What works:** color-coded steps, language auto-detection, safe env parsing, `.gitignore` hygiene, cleanup trap concept, next-steps epilogue. This is a genuinely decent installer skeleton.

**Friction:**

| # | Friction | Evidence | Fix |
|---|----------|----------|-----|
| DX-3 | **Version chaos.** installer says `2.0.0`, pyproject says `2.0.0`, CLI says `1.1.0` (`src/cli/main.py:13`), and `tests/test_cli.py` asserts `"1.1.0" in result.stdout` — the test suite codifies the drift. Latest CHANGELOG entry is `1.3.0`. | `install.sh:7`, `pyproject.toml:7`, `src/cli/main.py:13`, `tests/test_cli.py:31` | Single source of truth: a `VERSION` file read by install.sh and `importlib.metadata` in the CLI; test asserts against pyproject, not a literal. |
| DX-4 | **Destructive failure/upgrade semantics.** The ERR trap runs `rm -rf "$DEST"` unconditionally. If a user re-runs the installer over an existing, customized `.claude/` and *anything* fails mid-way (missing template file, read-only FS), their entire existing `.claude/` — including hand-edited `CONSTITUTION.md` — is deleted. | `install.sh:94-101` | Before touching an existing `$DEST`, `mv "$DEST" "$DEST.bak.$(date +%s)"`; on failure restore the backup; on success offer to delete it. Never `rm -rf` a directory the installer didn't create in this run. |
| DX-5 | **Re-run = data loss by design.** `--force`/overwrite regenerates `CLAUDE.project.md` and `CONSTITUTION.md` from templates. `docs/CUSTOMIZATION.md:186` literally tells users to "back them up first." There is no upgrade mode, no uninstall, no installed-version manifest. | `install.sh:104-112, 304-338`; `docs/CUSTOMIZATION.md:179-187` | Add `--upgrade` (replace framework dirs `agents/ commands/ skills/ hooks/ operations/`, never `local/`), `--uninstall` (remove `.claude/`, revert `.gitignore` entries), and write `.claude/.claudekit-version` so `doctor` can detect stale installs. |
| DX-6 | **The summary lies.** Counts and lists in the epilogue are hardcoded: "37 commands" (actual after install: **52** — 39 core + 13 from `templates/commands/`), a hardcoded 28-agent name list, "15 hooks", "7 behavioral modes", "5 MCP server configurations". The script *computes* `AGENT_COUNT`, `CMD_COUNT`, `SKILL_COUNT`, `HOOK_COUNT`, `MODE_COUNT` earlier and then ignores several of them. | `install.sh:399-413` vs computed vars at 158, 170, 204, 216, 224 | Print only computed counts. Delete every hardcoded list/number from the epilogue. |
| DX-7 | Interactive prompts (`read -r TARGET_DIR`, overwrite y/N) break unattended/CI installs; no `--yes`/`--non-interactive`. | `install.sh:80-83, 104-112` | Add `--yes`; when stdin is not a TTY, fail with a clear message instead of hanging. |
| DX-8 | `--with-mcp` and `--with-i18n` appear in `usage()` but not in the README's "Install Options" section, so they're effectively undiscoverable. | `install.sh:48-49` vs `README.md:62-76` | Document all flags in README; better, make `usage()` the generated source of that section. |
| DX-9 | Detection edge cases: `package.json` alone ⇒ "typescript" (wrong for plain JS); `*.csproj` only detected at repo root (nested `src/App/App.csproj` ⇒ "generic"); no confirmation step ("Detected python — continue? [Y/n]"). | `install.sh:115-139` | Add a JS-vs-TS check (tsconfig presence), use `find -maxdepth 3` for csproj/sln, confirm detection interactively. |

### 1.3 Install path B: pip / CLI — **broken**

```
$ python3 -c "import setuptools.backends"
ModuleNotFoundError: No module named 'setuptools.backends'
```

| # | Friction | Evidence | Fix |
|---|----------|----------|-----|
| DX-10 | **`pip install -e .` cannot work.** `build-backend = "setuptools.backends._legacy:_Backend"` is not a real module; the documented pip path (`docs/cli.md:5-9`) fails at build time for every user. | `pyproject.toml:3`, verified import failure | Set `build-backend = "setuptools.build_meta"`. Add a CI job that actually runs `pip install .` and `claudekit --version`. |
| DX-11 | **Package layout pollutes site-packages.** `include = ["src*"]` installs a top-level package literally named `src`, and entry points are `src.cli.main:main`. This collides with any other project that does the same and is un-importable by name. | `pyproject.toml:29-31, 39-41` | Rename to a real package (`claudekit/cli/`, `claudekit/security/`) or use proper src-layout (`package-dir = {"" = "src"}` with `src/claudekit/...`). |
| DX-12 | **Even if pip worked, `claudekit init` couldn't.** The wheel ships only `src*` — no `.claude/` assets, no `install.sh`. `find_claudekit_root()` looks at `__file__/../../..` (site-packages) and `~/claudekit`, `~/.claudekit`. The error message says "Set CLAUDEKIT_HOME or run from the repo" — but **the code never reads `CLAUDEKIT_HOME`**. | `src/cli/main.py:31-41, 53` | (a) Ship `.claude/`, `templates/`, `install.sh` as package data; (b) actually honor `os.environ.get("CLAUDEKIT_HOME")`; (c) fallback: `claudekit init --from-git` clones a pinned tag into `~/.claudekit`. |

### 1.4 First project init & first command

Assuming the bash path, the epilogue's next steps are good (`/plan Add a new feature`). But:

| # | Friction | Evidence | Fix |
|---|----------|----------|-----|
| DX-13 | Nothing tells the user to run `claudekit doctor` (the best onboarding validator in the repo) — it isn't in the epilogue, README, or CUSTOMIZATION next-steps. | `install.sh:414-426`, README | Add "Run `claudekit doctor` (or `python3 -m src.cli.main doctor`) to verify the install" as step 0 of next steps. |
| DX-14 | `doctor` thresholds are stale: expects ≥9 agents, ≥8 commands, ≥27 skills while a full install has 28/52/73 — a half-broken install still "passes". | `src/cli/main.py:124-138` | Compare against a manifest written at install time (see DX-5's `.claudekit-version` manifest with counts), not magic numbers. |
| DX-15 | `doctor` checks 5 legacy hooks by name (`pre-commit.sh`…`post-tool-use.sh`) but the shipped hook set is 19 scripts driven by `settings.json`; it never validates that `settings.json` hook commands point at existing files. | `src/cli/main.py:167-189`; `.claude/hooks/` listing | Iterate `settings.json` hook entries, verify each referenced script exists and is executable. |

### 1.5 Customize

`docs/CUSTOMIZATION.md` is one of the better docs (concrete diffs for models, thresholds, protected files). Friction: the update story it documents is the destructive `--force` (DX-5), and `config.schema.json` is invisible (next section).

---

## 2. CLI UX Review (`src/cli/main.py`)

**Command names:** `init`, `doctor`, `validate`, `execute`, `rollback`, `agents`, `config` — clear, verb-first, memorable. Good.

**Help text:** argparse defaults only; no examples, no epilog. `claudekit init --mode` has no help string at all (`main.py:344`). *Fix:* add `epilog` with 3 copy-paste examples per subcommand; help strings for every flag.

**Error messages:** Mostly excellent pattern — every failure suggests the fix (`"Validator not found. Run: claudekit init"`). Two defects:
- `init` failure suggests `CLAUDEKIT_HOME` which is never read (DX-12) — a false promise.
- `config` docstring says "Show or **edit** configuration" but there is no set/edit capability (`main.py:310-330`). *Fix:* add `claudekit config set project.test_cmd "pytest -q"` or reword to "show/query".

**Colors:** ANSI codes emitted unconditionally — no `NO_COLOR`, no `isatty()` check, so piped output and CI logs contain escape garbage (`main.py:16-28`). *Fix:* `if not sys.stdout.isatty() or os.environ.get("NO_COLOR"): disable`.

**Exit codes:** Consistent 0/1; subprocess return codes propagated correctly for validate/execute/rollback. `doctor` returns 0-with-warnings — acceptable, but add `--strict` to turn warnings into exit 2 for CI.

**`ck` alias discoverability:** defined in pyproject, mentioned once in `docs/cli.md`. Since the pip path is broken (DX-10), no user has ever had `ck`. Once pip works, print "`ck` is a shorthand for `claudekit`" in `--help` epilog and README.

**Dead weight:** `import time` is unused (`main.py:10`). `src/security/` (`command_validator.py`, `path_guard.py`) is packaged but never imported by the CLI — dead code shipping in the wheel, plus committed `__pycache__/*.pyc` in the working tree. *Fix:* wire the validators into `execute`/hooks or remove; ensure `.pyc` never lands in the sdist.

**Missing commands users will reach for:** `claudekit update`, `claudekit uninstall`, `claudekit skills [list]`, `claudekit hooks [list|enable|disable]`, `claudekit version` (rich: CLI + installed-project versions), `claudekit doctor --fix` (chmod hooks, add missing gitignore entries).

---

## 3. Configuration UX (`config.schema.json`)

- **Not discoverable, not used.** No file in the repo references `config.schema.json`: the generated `.claude/hooks/config.json` carries no `$schema` key, `doctor` doesn't validate against it, and no doc mentions it. It's a schema for a config that nothing checks.
- **Schema drift:** it models per-hook `command/enabled/timeout/blocking` blocks — the pre-1.1.0 custom hook style — while the live mechanism is Claude Code's official `settings.json` (7 event types) plus a slimmer `config.json` used mainly for `project.*` commands. `additionalProperties: false` means several currently-shipped hooks (e.g. `commit-quality`, `session-start`, `format-typecheck`) aren't representable.
- **Fixes:**
  1. Installer writes `"$schema": "./config.schema.json"` (and copies the schema) into generated config.json — instant IDE autocomplete.
  2. `doctor` validates config.json against the schema (`jsonschema` optional dependency, or a 30-line hand-rolled checker).
  3. Regenerate the schema from the actually-shipped hook set; drop `additionalProperties: false` for `hooks` or enumerate all 19.
  4. Document the config.json ↔ settings.json split (who reads what) in docs/HOOKS.md — today it is genuinely ambiguous.

---

## 4. Template Bootstrap Experience (per language)

- Detection covers 11 ecosystems; `config.env` provides sane build/test/lint/coverage defaults (checked python: `ruff + mypy`, `pytest --cov`). Good baseline.
- **Gaps:** (a) `FRAMEWORK="FastAPI/Flask/Django"` — a slash-list placeholder gets sed'd verbatim into CLAUDE.project.md; user reads "Framework: FastAPI/Flask/Django". Detect or ask. (b) No per-language post-install smoke test ("run `pytest --version`… not found — install or edit config.json"). (c) `--with-i18n` copies *ClaudeKit's own translated READMEs* into the user's project `i18n/` directory — that's ClaudeKit marketing material injected into a customer repo. Remove the flag or make it copy the `i18n-patterns` skill only. (d) `.agentignore` is dropped into the project root silently and undocumented in README.

---

## 5. Error-Message Quality — Summary Table

| Location | Message | Verdict |
|----------|---------|---------|
| CLI validate/execute/rollback missing script | "…not found. Run: claudekit init" | Good — actionable |
| CLI init, no source | "Set CLAUDEKIT_HOME or run from the repo" | **Broken promise** (env var unimplemented) |
| install.sh unknown flag | prints usage | Good |
| install.sh missing dir | "Directory does not exist" | Add "create it? (y/N)" or `--create` |
| install.sh hook config failure | "update .claude/hooks/config.json manually" | Good |
| doctor failures | fix-hint per check | Good pattern; hints stale (DX-14) |

---

## 6. Steps-Eliminated Analysis

**Today (bash path, happy case):**

1. Find correct repo URL (README's is wrong — DX-2)
2. `git clone …`
3. `./claudekit/install.sh /path/to/project --full`
4. Answer overwrite prompt (re-runs)
5. Manually verify install (no doctor pointer)
6. Edit `.claude/local/CLAUDE.project.md`
7. Edit `.claude/local/CONSTITUTION.md`
8. Edit `.claude/hooks/config.json`
9. Open Claude Code, run `/plan …`

**= 8–9 user actions.** Pip path: ∞ (broken at step 1).

**Proposed:**

1. `pipx install claudekit` *(or `curl -fsSL https://…/install.sh | bash -s -- .`)*
2. `ck init` → detects language, confirms, installs, writes version manifest, **runs doctor automatically**, and opens an interactive 3-question wizard that fills CLAUDE.project.md/CONSTITUTION.md/config.json (project description, coverage target, framework)
3. `/plan …` in Claude Code

**= 3 actions. Eliminated: 5–6 steps**, plus eliminates the "which files do I edit now?" cognitive step by folding customization into the init wizard (with `--no-wizard` for scripted installs).

---

## 7. Ideal CLI Proposal (command tree)

```
ck (alias: claudekit)
├── init [DIR]            # detect → confirm → install → doctor → wizard
│     --minimal --language L --force --yes --no-wizard --from-git TAG
├── update                # upgrade framework dirs, preserve local/, show diff summary
├── uninstall             # remove .claude/, revert .gitignore, keep backups
├── doctor                # manifest-driven checks; --fix; --strict (warnings→exit 2)
├── ops
│   ├── validate <ops.json> [-v]
│   ├── execute  <ops.json> [--dry-run] [-v]
│   └── rollback [--list | --backup DIR] [--dry-run] [--force]
├── list
│   ├── agents            # today's `agents`
│   ├── skills
│   ├── commands
│   └── hooks
├── config
│   ├── get [key]         # today's `config [key]`
│   ├── set <key> <value>
│   └── validate          # against config.schema.json
└── version               # CLI version + installed-project manifest version
```

Keep `validate/execute/rollback` as top-level aliases for one deprecation cycle. Every subcommand: `--json` output for scripting, `NO_COLOR` respected, examples in `--help`.

---

## 8. Prioritized Fix List

| Priority | Items |
|----------|-------|
| P0 (broken) | DX-10 build backend; DX-12 CLAUDEKIT_HOME + package data; DX-4 `rm -rf` trap; DX-3 version drift |
| P1 (trust) | DX-6 lying summary; DX-2 repo slug; DX-5 upgrade/uninstall; DX-14/15 doctor accuracy; config.schema wiring (§3) |
| P2 (polish) | DX-1 pip docs in README; DX-7 `--yes`; NO_COLOR; `config set`; DX-9 detection; i18n flag rework; init wizard |

**Score rationale (54/100):** The bash installer, doctor concept, and error-message discipline are above average for a young project (+). But the second documented install path is entirely broken, the upgrade path destroys user data on failure, three version numbers disagree, and the installer's own success summary reports numbers that are false — each of these erodes exactly the trust a "safety-first" toolkit sells.

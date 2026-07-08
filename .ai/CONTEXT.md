# Context — Non-Obvious Facts You Must Know

Everything here is easy to get wrong without conversation history. Read before making any change.

## Identity & distribution

- **PyPI name is `claude-kit`** (the name `claudekit` was taken); the CLI commands remain `claudekit` and `ck`, and the import package is `claudekit`. Never "fix" this mismatch — it is deliberate (commit `a3ddc09`).
- **Canonical GitHub slug: `OmarMokhtar-Saad/claudekit`.** An older `omarmokhtar/claudekit` slug 404s; it was swept from docs in task 006. Don't reintroduce it.
- License MIT. Author Omar Mokhtar. Repo language: prompts (Markdown) + Bash + Python.

## Versioning

- Current version: **2.1.0**, still `[Unreleased]` in CHANGELOG.md. Tagging + PyPI publish are **user-gated** decisions.
- Version history had a correction: an entry published as `1.3.0` (2026-04-11) actually shipped *after* `2.0.0` and was renumbered `2.1.0`. Two agents listed under it (`dead-code-hunter`, `open-source-forker`) never shipped and were removed from history.
- Single source of truth is `pyproject.toml` via `importlib.metadata`, with hardcoded fallbacks in `src/claudekit/__init__.py` and `.claude/operations/scripts/shared.py` that must be bumped in lockstep (tests enforce).
- `release.yml` publishes to PyPI via **Trusted Publishing** on tag push (wired in `db45db8`, never yet exercised with a real tag).

## The repo runs its own enforcement on itself

- `.claude/settings.json` wires 19 hooks that apply to any Claude Code session **in this repo**. `ops-enforcement.sh` blocks Edit/Write to source files outside `.claude/`+docs unless an approved ops.json exists; blocking hooks exit 2 with stderr and fail closed.
- Escape hatch: `.claude/settings.local.json` (gitignored, survives reinstall since `719ea2c`) sets `ECC_HOOK_PROFILE=minimal`. `standard` is the shipped default (command-guard warns instead of blocks); `strict` blocks everything.
- If you are an agent working here through Claude Code and your edits are blocked, that local override is missing — do not try to bypass hooks; restore the override per CONTRIBUTING.md.

## History in one paragraph

v1.0.0 and v1.1.0 shipped 2026-03-16, v2.0.0 on 2026-03-17 — a rapid, ambitious build-out whose delivery shell was broken: the wheel never built (wrong build backend), install.sh never copied `settings.json` (all hooks dead on arrival), blocking hooks used the wrong exit code (never blocked anything), the security module was dead code, CI ran `|| true`. An 11-review external audit (2026-07-05, `review/`) scored the repo **49/100** — "conceptually top-decile, executionally bottom-decile" — and produced a 14-task remediation roadmap. Phase 1 ("v2.1 Fix What's Broken", tasks 001–006 + 011) was executed 2026-07-05/06 on branch `phase-1-fix-whats-broken` (14 commits), merged to main in PR #1, followed by one CI fix (`0c9223b`, setuptools missing on py3.12+). 516 tests pass; ruff/mypy/shellcheck/docs-drift clean.

## Session gotchas (from the Phase-1 handoff)

- Commit messages end with a `Co-Authored-By:` line crediting the AI model used (repo convention).
- `find_claudekit_root()` in the CLI walks up looking for `.claude/agents` — it broke once by resolving to `src/`; there's a regression test.
- `CLAUDEKIT_HOME` env var is honored for locating the asset tree (works from wheel installs via `<prefix>/share/claudekit`, bundled by `setup.py`).
- Ops filenames: **both** `*.ops.json` and `ops-*.json` are valid; `lib.sh` defines `OPS_FIND_EXPR`/`OPS_REGEX` as the single matching pattern. Never match only one form (the historic split-brain meant pre-commit validated zero files, ever).
- The secret-scan regex historically failed on single-quoted secrets (`\x27` bug) — fixed; there's a test proving staged secrets block commits (`4ef8d38`).
- macOS compatibility is a hard requirement: bash 3.2 (no `${VAR,,}`), BSD date (no `date -r` GNU semantics). CI runs a macOS matrix.

## Audience split (do not blur it)

- `docs/` + root README → **users** installing ClaudeKit into their projects.
- `.ai/` + root CLAUDE.md + CONTRIBUTING.md → **maintainers/AIs** developing ClaudeKit itself.
- `.claude/local/*.template.md` + `templates/*/CLAUDE.md` → **generated artifacts** for users' projects; placeholders like `{{PROJECT_NAME}}` are rendered by the installer (sed with escaping — values containing `&`/`|`/`\` are handled; don't regress `dca9a19`).

## Open decisions (user-gated — do not decide unilaterally)

1. Tag `v2.1.0` and publish to PyPI (mechanics ready; needs owner go-ahead).
2. Claude Code **plugin packaging** (`.claude-plugin/plugin.json`) as primary distribution (task 007) — strategic bet, owner call.
3. Corpus consolidation scope (task 008: 28 agents → ~20, 73 skills → ~60) — deletions are user-visible; get sign-off on the merge list first.

# Coding Standards

## Python (`src/claudekit/`, `scripts/`, `.claude/operations/scripts/`, `tests/`)

- Target py3.9+ (mypy `python_version = 3.9`); test matrix 3.9/3.10/3.12/3.13.
- ruff: line-length 100, rules E/F/W/I (E501 ignored); `.claude`, `templates`, `examples`, `i18n` excluded.
- mypy on `src/claudekit` with `ignore_missing_imports`.
- **Zero runtime dependencies** — stdlib only in `src/` and operations scripts (jsonschema is an optional extra used when present). This is a product feature.
- Style observed in the codebase: small module-level helper functions (`info/ok/warn/err` with ANSI colors and `NO_COLOR` respect), `cmd_<verb>` functions per CLI subcommand, tuples `(bool, str)` for validate-style returns, explicit exit codes, no cleverness in safety paths.
- Operations scripts stay standalone-runnable (no imports from the installed package — they ship into user projects).

## Bash (`install.sh`, `.claude/hooks/*.sh`, `templates/hooks/`)

- **bash 3.2 compatible** (stock macOS): no `${VAR,,}` (use `tr`), no associative arrays, no GNU-only `date` flags; BSD/GNU-neutral sed/find.
- shellcheck clean (`.shellcheckrc` holds accepted exceptions); `set -euo pipefail` where safe (careful with hooks — a spurious failure must not become an accidental block/allow).
- Hooks: source `lib.sh`; parse stdin JSON via `python3 -c` (no jq dependency); blocking = `deny` (stderr + exit 2); everything logged via `hlog`; profile checks first.
- Never use trap-based cleanup that removes user data (the historic `rm -rf $DEST` lesson); staging + atomic move instead.
- Quote everything; assume paths contain spaces.

## Markdown assets (agents/commands/skills — the product)

- Kebab-case filenames (legacy exception: `gitOps.md` — do not "fix" casually; handoff targets reference the name).
- Frontmatter per asset class (see [PROMPTS.md](PROMPTS.md)); two `<example>` blocks per agent.
- Reference shared docs instead of duplicating rules; keep commands ≤~40 lines.
- No `--dangerously-skip-permissions`, no unpinned `npx -y @latest` in examples.

## JSON

- 2-space indent; schemas use `additionalProperties: false`; registry entries complete (`id/name/path/mandatory/usedBy/description`).

## Naming conventions

`cmd_*` CLI handlers · `test_*.py` mirrors the surface it tests (`test_hooks_behavioral`, `test_packaging`) · hooks named for what they guard (`block-no-verify`, `config-protection`) · plans `plan-<slug>.md` + `<slug>.ops.json` (or `ops-*.json`) · guards numbered (GUARD 1–29) with comments at use sites.

## Documentation

CommonMark; blank line before lists and after headers; counts only via gen-docs; audience separation (docs/ = users, .ai/ = maintainers); every doc cross-links its siblings; British/American spelling not enforced — clarity is.

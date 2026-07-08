# Development Guide (for ClaudeKit itself)

User-facing customization lives in `docs/CUSTOMIZATION.md`; this guide is for developing the kit.

## Environment setup

```bash
git clone https://github.com/OmarMokhtar-Saad/claudekit.git && cd claudekit
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"           # pytest, pytest-timeout, pytest-cov, coverage, ruff, mypy, jsonschema
mkdir -p .claude && cat > .claude/settings.local.json <<'EOF'
{ "env": { "ECC_HOOK_PROFILE": "minimal" } }
EOF
```

The local settings file (gitignored, preserved across reinstalls) disables the kit's own enforcement hooks so you can edit source normally. Without it, `ops-enforcement.sh` blocks Edit/Write outside `.claude/`+docs. See CONTRIBUTING.md "Working on ClaudeKit itself".

## Daily commands

```bash
python3 -m pytest tests/ -q                      # full suite (516)
python3 -m pytest tests/test_hooks_behavioral.py -q   # enforcement truth suite
ruff check src/ tests/ scripts/ && mypy          # lint + types
python3 scripts/gen-docs.py --check              # docs-drift gate
shellcheck install.sh .claude/hooks/*.sh         # shell lint (.shellcheckrc has the config)
ck doctor --strict                               # installed-tree health (19 checks)
```

## Adding assets

**New agent** — copy `_shared/AGENT_TEMPLATE.md` → `.claude/agents/<kebab-name>.md`; frontmatter needs name, description with two `<example>` blocks, model, tools (minimum necessary — omit Write/Edit for read-only roles), color; add mandatory-skill section, output contract, handoff formats; add coordinator routing row + QUICK_START row + INVOCATION.md `--allowedTools` row; run `gen-docs.py --check`; consider whether an existing agent should be extended instead (we are consolidating, not growing — task 008).

**New skill** — `.claude/skills/<id>/SKILL.md` (see `writing-skills` skill); register in `skills-registry.json` with accurate `usedBy` (CI validates paths); check the near-duplicate list first.

**New command** — `.claude/commands/<name>.md`; keep ≤~40 lines; frontmatter `description`; dispatch per INVOCATION.md; document in README commands table (then `gen-docs.py --check`).

**New hook** — script in `.claude/hooks/` sourcing `lib.sh`; register in `.claude/settings.json` (correct event + matcher); blocking = `deny` helper (exit 2 + stderr) and fail closed; bash-3.2-safe; add a behavioral test in `tests/test_hooks_behavioral.py` proving both block and allow paths; CI `dangling-hooks` checks registration ↔ file existence.

**New language template** — `templates/<lang>/CLAUDE.md` + `config.env`; add detection logic in `install.sh`; add tests in `test_install.py`.

## Editing safety-critical code

`src/claudekit/security/` — coverage gate ≥85%; add bypass-corpus cases to `test_security.py` for any validator change. `.claude/operations/scripts/` — never weaken a guard without an explicit decision-log entry; `operations-schema.json` and `generate-operations-config` skill must change together. `install.sh` — preserve staging/backup/atomic-swap; test with `tests/test_install.py` including the mid-failure byte-identical assertion.

## Version bump procedure

Bump `pyproject.toml` + fallback in `src/claudekit/__init__.py` + `.claude/operations/scripts/shared.py`; move CHANGELOG `[Unreleased]` → dated section; `pytest tests/test_packaging.py -q`. Release: [PLAYBOOK.md](PLAYBOOK.md).

## Commit & PR

Conventional commits (`feat|fix|docs|test|ci|build|refactor(scope): subject`), Co-Authored-By line for AI work, PR template in `.github/`. The repo's own commit-quality hook enforces format when hooks are active. Definition of Done: [CHECKLISTS.md](CHECKLISTS.md).

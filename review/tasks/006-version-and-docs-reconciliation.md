# Task 006 — Version & Documentation Reconciliation

## Problem
For a tool whose pitch is auditability, nothing about its own identity is auditable:
- **Five version strings, four values:** pyproject.toml:7 = 2.0.0, `src/cli/main.py:13` = 1.1.0, CHANGELOG latest = **1.3.0 dated 2026-04-11, a month *after* 2.0.0 (2026-03-17)**, `operations/scripts/shared.py:3` = 3.1.0, skills-registry.json = "2.0". `tests/test_cli.py:31` asserts the wrong version, codifying the drift. Zero git tags.
- **CHANGELOG phantom features:** 1.3.0 lists agents `dead-code-hunter` and `open-source-forker` that don't exist in `.claude/agents/` (CHANGELOG.md:19-20), while 9 shipped agents appear in no entry. No `[Unreleased]` section, no compare links.
- **Counts wrong everywhere:** README says 13 agents (:304), 17 commands (:317), ~45 skills (:234); reality: 28 agents, 39+13=52 installed commands, 73 skills. README self-contradicts on guards (29 at :35/:422 vs 26 at :215). docs/AGENTS.md documents 13 of 28; docs/ARCHITECTURE.md says 44 skills (a third distinct count); docs/SKILLS.md catalogs ~45 of 73.
- **Dead/wrong links:** README clone URL + CI badge use `omarmokhtar/claudekit`; pyproject Homepage + schema `$id` use `OmarMokhtar-Saad/claudekit` — one 404s, and the unclaimed slug is a supply-chain squat risk (security §5.3). `docs/cli.md` is orphaned (not in README's docs table).
- **SECURITY.md** supports only "1.x" — the current 2.0.0 release is formally unsupported by its own policy; no threat-model note about prompt-injection or the (former) skip-permissions default.
- **docs/HOOKS.md** documents the pre-1.1 config.json hook mechanism; settings.json, the 14 newer hooks, and `ECC_HOOK_PROFILE` are absent. `.claude/hooks/README.md` duplicates ~70% of it, also stale.

## Root Cause
All counts, versions, and tables are hand-written in multiple places with no generation and no drift CI. The CHANGELOG was maintained on a branch mental-model ("1.3.0" work continuing after a "2.0.0" rebrand) without renumbering.

## Files
- `pyproject.toml:7`, `src/cli/main.py:13`, `.claude/operations/scripts/shared.py:3`, `skills-registry.json`, `install.sh:7`, `tests/test_cli.py:31`
- `CHANGELOG.md:8,19-20,62,64`
- `README.md:2,6,35,44-48,133-174,215,234,252-260,299-349,422`
- `docs/AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/SKILLS.md`, `docs/HOOKS.md`, `docs/cli.md`, `.claude/hooks/README.md`
- `SECURITY.md`, `CONTRIBUTING.md:9,25` (slug)
- `config.schema.json` (`$id` slug)
- New: `scripts/gen-docs.py`, `.github/workflows/ci.yml` docs-drift job

## Priority
**P1** (P0 subset: repo slug, SECURITY.md versions, CHANGELOG renumbering — each ≤1 hour).

## Estimated Time
3–4 days (generation script is the bulk; the corrections themselves are mechanical).

## Risk
Low. Documentation-only plus one script. Renumbering the CHANGELOG rewrites public history — mitigate with an explicit corrective note at the top explaining the renumbering rather than silently editing dates.

## Step-by-step Implementation
1. **Pick the canonical slug** (whichever GitHub account is real/primary), grep-replace across README (badges, clone URL), CONTRIBUTING, pyproject URLs, `config.schema.json` `$id`; claim/redirect the alternate account name if possible. Add a CI grep that fails on the wrong slug.
2. **Version unification** (with task 001): pyproject is truth; CLI via `importlib.metadata`; `shared.py.__version__` set to the release version by the release workflow (or dropped); registry `"version"` generated; install.sh VERSION templated at release. Fix `tests/test_cli.py:31`.
3. **CHANGELOG:** insert a "Versioning correction" note; renumber the 1.3.0 (2026-04-11) entry to **2.1.0-dev / merged into the v2.1.0 entry**; delete phantom agents (or move to "planned"); add entries for the 9 undocumented agents; add `[Unreleased]` + compare-link footer. CI gate: top CHANGELOG version == pyproject version at tag time.
4. **`scripts/gen-docs.py`:** emits (a) README count line ("28 agents · 52 commands · 73 skills · 19 hooks · 11 languages") from the tree/manifest, (b) `docs/reference/agents.md` from agent frontmatter (name/model/color/description), (c) `docs/reference/commands.md` (all 52), (d) `docs/reference/skills.md` from skills-registry.json, (e) the README project-structure tree. Counts must be computed, never written (arch F-14).
5. **docs-drift CI job:** run gen-docs.py, `git diff --exit-code` — fails on drift.
6. **Guard count:** derive from a constant in `validate-config-json.py`, cite one number in README (also fix the script's own docstring 26-vs-29 fiction — code-review §7).
7. **SECURITY.md:** supported versions `2.x`; add disclosures: prompt-assets-are-prompts threat model, hooks-are-advisory statement, MCP `npx` note, clone-trust guidance (security §7).
8. **Rewrite docs/HOOKS.md** around settings.json events + all 19 hooks + `ECC_HOOK_PROFILE`; reduce `.claude/hooks/README.md` to a pointer.
9. **Link `docs/cli.md`** from the README docs table; add a language bar linking i18n READMEs + "last synced" headers (docs §6); add per-example README.md files or relabel examples as "example configurations."
10. Net-new pages from docs-review §5: migration guide (feeds roadmap §5), ops-config reference (from operations-schema.json), modes guide, troubleshooting.

## Acceptance Criteria
- `grep -rn "omarmokhtar/claudekit\|OmarMokhtar-Saad/claudekit"` returns only the canonical slug.
- One version value repo-wide; CI fails on mismatch; a git tag exists matching it.
- README/docs contain zero hand-written asset counts (all generated); docs-drift job green and demonstrably red when an agent is added without regeneration.
- CHANGELOG monotonic; every agent named in it exists on disk (add the doc-drift test from docs-review D-12).
- SECURITY.md covers 2.x.
- docs/HOOKS.md describes settings.json wiring; no doc describes config.json as the hook mechanism.

## Testing Strategy
- `tests/test_docs_drift.py`: gen-docs output matches committed docs; changelog-mentioned agents exist; README guard count equals the validator constant; slug grep.
- Link checker over docs (relative links already clean per docs-review §8 — keep it that way in CI).

## Rollback Plan
Docs-only: revert commits. The drift CI job can be marked non-required for one release if generation produces churn, then promoted to required.

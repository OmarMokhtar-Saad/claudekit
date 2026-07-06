# Task 013 — OSS Community Health & Presentation

## Problem
The repo is content-rich but release-poor and community-bare (oss-excellence verdict): asset depth is top-decile for the category, while the GitHub community profile and presentation are bottom-decile. Missing: CODEOWNERS, CODE_OF_CONDUCT.md, SUPPORT.md, FUNDING.yml, labels strategy (`good first issue`/`help wanted` — critical for a prompt-asset repo where contributions are cheap), Discussions, logo/social preview, demo GIF (for a *workflow* product, a 30s recording of `/plan → /review → /implement → /verify` is the highest conversion-per-hour asset), docs site, and releases (zero tags, nothing on PyPI). Present but weak: legacy `.md` issue templates (no YAML forms, no `config.yml`), thin 1.6 KB CONTRIBUTING.md (no guidance for the most likely contributions — commands/hooks/language templates/translations; no shellcheck step; no release process), examples that are two config files oversold as "complete example projects," i18n READMEs (a genuine standout — 6 languages) that are stale, abridged, and unlinked from the English README. Repo hygiene: committed `hooks.log` (159 KB, containing usernames and paths), `cost-tracker.log`, `compact-counter.txt`, `.pytest_cache/`, committed `__pycache__/*.pyc`, a stray nested `.claude/operations/scripts/.claude/hooks/` directory, and 20+ dogfooding plan artifacts in `.claude/plans/`.

## Root Cause
All energy went into the asset corpus; the "boring" repo-shell work (community files, releases, presentation) was never scheduled. Runtime artifacts were committed because .gitignore coverage lagged the hooks that generate them.

## Files
- New: `.github/CODEOWNERS`, `CODE_OF_CONDUCT.md` (Contributor Covenant), `SUPPORT.md`, `.github/FUNDING.yml`, `.github/labels.yml` (+ labeler or sync action), `.github/ISSUE_TEMPLATE/*.yml` (forms) + `config.yml` (blank_issues_disabled, contact links → Discussions/security advisory)
- `CONTRIBUTING.md` (expand: per-contribution-type sections, shellcheck invocation, release process, CoC link)
- `README.md` (hero: logo, language bar for i18n, demo GIF, badges — fix per task 006; slim toward the 400-line outline in docs-review §10)
- `examples/python-fastapi/README.md`, `examples/typescript-nextjs/README.md` (+ runnable app or honest relabel; checked-in workflow transcript)
- `i18n/*.md` (sync-date headers; trim to translated overview linking English reference docs — docs-review recommendation)
- Delete/ignore: `.claude/hooks/hooks.log`, `cost-tracker.log`, `compact-counter.txt`, `.pytest_cache/`, `**/__pycache__/`, stray `.claude/operations/scripts/.claude/`, `.claude/plans/plan-2026*` debris; `.gitignore` additions (`.claude/plans/`, `.claude/session-*.{md,json}`, `.claude/hooks/*.txt`)
- New: `mkdocs.yml` + `docs-site` deploy workflow (MkDocs Material over existing docs/)
- New: `.github/release-please.yml` or semantic-release config (commits already Conventional)
- Demo recording assets: `docs/assets/demo.gif` (asciinema/VHS source checked in)

## Priority
**P1–P2** (oss-excellence ranks 5, 7, 8, 9, 10, 11). The hygiene purge and community-file sweep are day-one items; GIF/site/examples are the 30–60 day window.

## Estimated Time
Community sweep + hygiene purge: 1 day. GIF: half a day (after v2.1 makes the pipeline actually demoable). Examples rebuild: 2–3 days. MkDocs site: 1 day. release-please: half a day.

## Risk
Low. Everything is additive or cosmetic. Only care point: history rewrite is NOT required for the committed logs (they contain usernames/paths, not secrets — security §5.1 rates it Med); `git rm --cached` + scrub-before-next-release is sufficient, but check log contents once more before deciding against a filter-repo pass.

## Step-by-step Implementation
1. **Hygiene purge:** `git rm --cached` all logs/counters/caches/pyc; delete the stray nested `.claude` dir (and add the regression test for the hook-CWD bug that created it — oss-excellence #9); move the one intentional plan (`blueprint-professional-upgrade.md`) to docs/; extend .gitignore.
2. **Community sweep (one afternoon):** CODE_OF_CONDUCT (Contributor Covenant 2.1), SUPPORT.md, FUNDING.yml, CODEOWNERS (repo owner + path-scoped once maintainers exist), YAML issue forms (bug form asks for `claudekit --version` output *and* installer banner — the version-confusion lesson from DX-3), `config.yml`, enable Discussions, seed labels (`good first issue`, `help wanted`, `skill`, `agent`, `command`, `hook`, `template`, `i18n`, `docs`).
3. **CONTRIBUTING expansion:** sections for adding an agent/command/skill/hook/language/translation with exact files to touch (mirror docs/AGENTS.md's "Adding a Custom Agent"); `shellcheck install.sh .claude/hooks/*.sh` in the checklist; release/tag process; link CoC.
4. **release-please** on Conventional Commits — automated version bumps + CHANGELOG, permanently killing the version-drift failure mode (pairs with task 006's corrections).
5. **Demo GIF:** VHS/asciinema script recording `/plan → /review → /implement → /verify` on the fastapi example; embed at README top; keep the script in-repo so it regenerates per major release.
6. **Examples rebuild:** minimal runnable app per example + per-example README (what it demonstrates, how generated) + checked-in transcript (plan.md → ops.json → review verdict → diff) — this is also the eval fixture (task 010) and the invocation-mechanism proof (task 004), so build once, use thrice.
7. **i18n:** language bar at README top; "last synced: <date> (vX.Y)" header per translation; adopt the trim-to-overview strategy; wire the `/translate` command into the release checklist.
8. **Docs site:** MkDocs Material over `docs/` (content exists; rendering + search + link from README) following the IA in docs-review §9; deploy via Pages workflow.
9. **Badges:** coverage (from task 011), PyPI + downloads (after task 001), docs-site link; all on the canonical slug.

## Acceptance Criteria
- GitHub community-profile checklist fully green.
- `git ls-files | grep -E "\.log$|__pycache__|\.pytest_cache|compact-counter"` returns nothing.
- README shows: logo/GIF, language bar, working badges, ≤ ~400 lines.
- Both examples runnable (`README` steps succeed) with committed transcripts.
- Issues open as structured forms; at least 5 labels seeded; Discussions enabled and linked.
- Releases automated: merging a `feat:` commit produces a release PR with correct version + changelog.
- Docs site live and linked.

## Testing Strategy
- CI check that community files exist (extend structure job).
- Link checker on README/docs site.
- `tests/test_repo_hygiene.py`: assert no tracked files matching the debris patterns (turns the purge into a permanent gate).
- Manual: view social preview, open an issue via the new form, follow example READMEs end-to-end.

## Rollback Plan
All additive/cosmetic — revert individual commits. release-please can be disabled by removing its workflow; manual tagging (task 001) remains available. No user-facing runtime behavior changes in this task.

# ClaudeKit — OSS Excellence Review

**Reviewer role:** Product Manager + OSS reviewer, benchmarking against top-tier GitHub projects (LangChain, CrewAI, Aider, OpenHands, Vercel AI SDK, ruff/uv-class repo hygiene).
**Date:** 2026-07-05

---

## 1. Hygiene Checklist Audit

### `.github/` actual contents
```
.github/
├── workflows/ci.yml          ✓ (5 jobs: test matrix 3.8/3.10/3.12, shellcheck, structure, registry, cli-tests)
├── workflows/release.yml     ✓ (tag-triggered, builds sdist/wheel, GitHub Release w/ auto notes)
├── workflows/security.yml    ✓
├── pull_request_template.md  ✓
└── ISSUE_TEMPLATE/
    ├── bug_report.md         ✓ (legacy .md, not YAML forms)
    └── feature_request.md    ✓ (legacy .md, not YAML forms)
```

### Item-by-item

| Item | Status | Findings |
|------|--------|----------|
| **Badges** | ⚠️ Present but broken/stale | 5 shields in README. Version badge hardcodes **v2.0.0** while CHANGELOG tops out at **1.3.0** and there are **zero git tags** — three conflicting version signals. CI badge points to `omarmokhtar/claudekit`; **pyproject.toml Homepage points to `OmarMokhtar-Saad/claudekit`** — the two URLs disagree, so at least one badge/link is dead. No coverage, PyPI, or downloads badge (nothing to point them at yet). |
| **Logo / branding** | ✗ Missing | Text-only header. Top projects (CrewAI, Aider, OpenHands) all lead with a logo + social preview image. |
| **Website / GitHub Pages** | ✗ Missing | `docs/` is solid markdown (7 files) but no rendered site. MkDocs Material over existing docs is ~1 day. |
| **GIF / demo** | ✗ Missing | For a *workflow* product, a 30s asciinema/VHS recording of `/plan → /review → /implement → /verify` is the single highest-leverage README asset. Currently only ASCII diagrams. |
| **Examples quality** | ⚠️ Thin | `examples/{python-fastapi,typescript-nextjs}/` contain **only** CLAUDE.md + CONSTITUTION.md — no runnable app, no before/after, no transcript of a real workflow run. README oversells them as "complete example projects." |
| **Issue templates** | ⚠️ Legacy format | Markdown templates, not YAML issue forms; no `config.yml` (no `blank_issues_disabled`, no contact links routing questions to Discussions). |
| **PR template** | ✓ | Present. |
| **CODEOWNERS** | ✗ Missing | |
| **CODE_OF_CONDUCT.md** | ✗ Missing | Community-health-file gap; GitHub flags this. Contributor Covenant is a 5-min add. |
| **Discussions** | ✗ Not referenced | No links anywhere; presumably not enabled. |
| **Labels strategy** | ✗ None | No `labels.yml`/labeler workflow, no `good first issue`/`help wanted` strategy — critical for attracting first-time contributors to a prompt-asset repo where contributions are cheap. |
| **Release workflow** | ⚠️ Exists, never exercised, likely broken | `release.yml` is sound *but has never run* (no tags). Worse: `pyproject.toml` declares `build-backend = "setuptools.backends._legacy:_Backend"` — **not a valid backend** (should be `setuptools.build_meta`), so the `python -m build` step will fail on first tag push. Also `setuptools-scm` is required but no `[tool.setuptools_scm]` config, while `version` is set statically — contradictory. |
| **semantic-release / changelog automation** | ✗ Manual | CHANGELOG.md is high quality (Keep a Changelog + SemVer, detailed entries) but hand-written; commits already follow Conventional Commits (`feat:`, `fix:`) so release-please/semantic-release is a drop-in. |
| **Signed releases** | ✗ Missing | No Sigstore/GPG signing, no SLSA provenance, no `--attestations` on (nonexistent) PyPI publish. |
| **Community health files** | ⚠️ Partial | ✓ LICENSE (MIT), ✓ SECURITY.md, ✓ CONTRIBUTING.md (thin, 1.6 KB). ✗ CODE_OF_CONDUCT, ✗ SUPPORT.md, ✗ FUNDING.yml, ✗ GOVERNANCE. |
| **Dependabot / dependency hygiene** | ✗ Missing | No `dependabot.yml` (GitHub Actions pins would benefit); ironic given the kit ships a `dependency-audit` skill and `/deps` command. |
| **Benchmarks** | ✗ Missing | README claims "85% token reduction" and quality-gate efficacy with no published methodology or numbers. Top agent projects (Aider's leaderboards, OpenHands' SWE-bench) treat benchmarks as marketing. |
| **Quality gates (kit's own CI)** | ⚠️ Leaky | CI runs only 5 of 14 test files explicitly, and the cli-tests job runs pytest with **`|| true`** — CLI and security test failures cannot fail CI. No coverage measurement (the kit demands 80% of users), no lint/mypy on `src/`. Repo tree also contains committed runtime artifacts: `.claude/hooks/hooks.log`, `cost-tracker.log`, `compact-counter.txt`, a stray nested `.claude/operations/scripts/.claude/hooks/` directory, and `.pytest_cache/`. |
| **PyPI packaging** | ✗ Not published | No tags → no releases → not on PyPI. `pip install claudekit` does not work despite `pyproject.toml` + console scripts (`claudekit`, `ck`). **Naming risk:** `claudekit` is already a well-known *npm* package (carlrannaberg/claudekit, same niche — Claude Code enhancement toolkit). Check PyPI availability and expect brand confusion either way; consider disambiguation before publishing. |
| **Homebrew tap** | ✗ Missing | Reasonable post-PyPI follow-up (`brew install omarmokhtar/tap/claudekit`). |
| **npm wrapper** | ✗ Missing | Lower value — but note Claude Code users live in npm-land; an `npx claudekit init` shim has discovery value. Blocked by the name collision above. |
| **GitHub Action (published)** | ✗ Missing | No consumer-facing action on the Marketplace (see missing-features.md #6). |
| **i18n** | ✓ Standout | READMEs in ar/es/fr/ja/ko/zh — genuinely rare, ahead of most top projects. Keep them synced (they're not linked from the main README header, so nobody finds them). |

---

## 2. Recommendations Ranked by Impact-to-Effort

| Rank | Action | Impact | Effort | Rationale |
|------|--------|--------|--------|-----------|
| 1 | **Fix release pipeline**: correct `build-backend` to `setuptools.build_meta`, reconcile version to one source of truth (2.0.0 everywhere or cut 1.3.0), tag `v` release, verify `release.yml` passes | High | XS | Everything distribution-related is blocked behind this one-line bug + missing tag. |
| 2 | **Fix URL/badge integrity**: one canonical repo URL across README badges, pyproject URLs, install.sh clone command | High | XS | Broken clone/badge links on the README are instant credibility killers. |
| 3 | **Remove `|| true` from CI; run all 14 test files; add coverage + ruff/mypy on `src/`** | High | S | A quality-gates product whose own CI swallows failures is a walking counterexample. |
| 4 | **Publish to PyPI** (after #1; resolve name collision question) with Trusted Publishing + attestations | High | S | Turns `pip install claudekit` from fiction into the headline install path; unlocks PyPI/downloads badges. |
| 5 | **Demo GIF/VHS cast of the plan→review→implement→verify loop** at top of README | High | S | The product is a workflow; show the workflow. Highest conversion-per-hour asset available. |
| 6 | **Claude Code plugin packaging + marketplace.json** (cross-ref missing-features #1) | Very High | M | Distribution through the native channel dwarfs all other growth levers. |
| 7 | **Community health sweep**: CODE_OF_CONDUCT, SUPPORT.md, FUNDING.yml, CODEOWNERS, YAML issue forms + config.yml, enable Discussions, seed labels (`good first issue`, `skill`, `agent`, `template`) | Med | S | One afternoon; gets the GitHub community-profile checklist to green and lowers contribution friction. |
| 8 | **release-please (or semantic-release)** on Conventional Commits for automated versioning + CHANGELOG | Med | S | Commits are already conventional; removes the version-drift failure mode permanently. |
| 9 | **Repo cleanup**: purge committed logs/caches/stray nested dirs; extend .gitignore (`compact-counter.txt`, `.pytest_cache` already ignored but committed) | Med | XS | Hygiene signal; also the stray `.claude/operations/scripts/.claude/` dir suggests a hook CWD bug worth a regression test. |
| 10 | **Rebuild examples as runnable mini-apps** with a recorded transcript (plan.md → ops.json → diff) checked in | Med | M | Examples are the proof-of-claims; current ones are config-only. |
| 11 | **Docs site** (MkDocs Material on Pages) from existing `docs/` | Med | M | Content already exists; rendering + search + link from README. |
| 12 | **Published benchmark**: measure the "85% token reduction" claim with the eval harness; publish methodology | Med | M | Converts marketing claims into defensible data; unique among skill kits. |
| 13 | Signed releases (Sigstore/SLSA), Dependabot for Actions | Low-Med | S | Table stakes for security-branded projects; cheap after #4. |
| 14 | Homebrew tap, npm shim, GitHub Marketplace action | Low | M | Post-PMF distribution polish. |

---

## 3. 30 / 60 / 90-Day Adoption Plan

### Days 0–30 — "Make it real" (credibility + release)
- [ ] Fix `build-backend`, unify version (pick 2.0.0), reconcile all repo URLs (#1, #2)
- [ ] CI hardening: drop `|| true`, run full test suite, add ruff + mypy + coverage gate (#3)
- [ ] Repo cleanup: remove committed logs/caches/stray dirs (#9)
- [ ] Community sweep: COC, SUPPORT, FUNDING, CODEOWNERS, YAML issue forms, labels, enable Discussions (#7)
- [ ] Tag first release; verify release.yml end-to-end; publish to PyPI via Trusted Publishing (#4)
- [ ] Record demo GIF; add to README with i18n links surfaced in header (#5)
- **Exit criteria:** `pip install claudekit && ck doctor` works from a clean machine; README has zero dead links; CI is honest.

### Days 31–60 — "Make it distributable" (native channel + automation)
- [ ] Ship `.claude-plugin/plugin.json` + `marketplace.json`; validate in CI; document `/plugin install` as primary path (#6)
- [ ] Adopt release-please; wire CHANGELOG automation (#8)
- [ ] `ck update` + install manifest (pairs with plugin work; see missing-features #2)
- [ ] Rebuild both examples as runnable apps with checked-in workflow transcripts (#10)
- [ ] MkDocs Material site on GitHub Pages (#11)
- **Exit criteria:** installable and updatable via both `pip` and `/plugin`; docs site live; releases fully automated from merge to tag.

### Days 61–90 — "Make it provable" (evals + trust)
- [ ] Eval harness runner + nightly regression workflow on core agents (missing-features #3)
- [ ] Publish token-reduction / gate-efficacy benchmark with methodology (#12)
- [ ] Signed releases + SLSA provenance + Dependabot (#13)
- [ ] Consumer GitHub Action (`claudekit-action@v1`) on the Marketplace (#14 / missing-features #6)
- [ ] Launch pass: submit to awesome-claude-code lists, plugin marketplaces, write a "constitutional AI-coding workflow" post
- **Exit criteria:** every README claim is backed by a published number or a green badge; a stranger can adopt, verify, and update ClaudeKit without reading the source.

---

## 4. Verdict

The repo is **content-rich but release-poor**. Asset depth (30 agents / 39 commands / 73 skills / ops engine / i18n) is top-decile for the category; distribution and verification are bottom-decile: no tags, no releases, no PyPI presence, a build config that would fail on first release, CI that ignores failures in two jobs, and a README whose install URL and version badge don't match reality. Ninety focused days closes essentially all of it — nothing here requires research, only execution.

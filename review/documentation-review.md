# ClaudeKit — Documentation Review

**Reviewer role:** Documentation Lead
**Date:** 2026-07-05
**Scope:** README.md, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md, docs/ (7 files), examples/, i18n/ (6 translations), .github templates, plus in-tree READMEs
**Ground truth used:** actual file counts in `.claude/` — **28 agents** (30 .md files incl. 2 protocol docs), **39 core commands** + 13 template commands (**52 installed**), **73 skills**, **19 hook scripts**, `settings.json` with 7 hook events.

**Overall Documentation score: 47/100**

---

## 1. README.md (21 KB)

### Structure — good bones

Logical flow (Why → Quick Start → How It Works → Commands → Agents → Operations → Skills → Hooks → Languages → Constitution → Structure → Docs → FAQ). ASCII pipeline diagram is effective. FAQ-in-details is a nice touch. Length (21 KB) is at the upper limit but tolerable *if it were accurate*.

### Accuracy vs. actual code — the core problem

| # | Claim in README | Reality | Fix |
|---|-----------------|---------|-----|
| D-1 | "13 specialized agents" (`README.md:304`), agent table lists 13 (`:157-174`) | 28 agents ship (`silent-failure-hunter`, `harness-optimizer`, `code-reviewer`, `build-error-resolver`, `model-router`, `opensource-*`, `python/typescript-reviewer`, `tdd-guide`, `refactor-cleaner`, `doc-updater`, `code-simplifier`, `performance-optimizer`, `loop-operator` are all undocumented here) | Regenerate the table from agent frontmatter (scriptable — frontmatter has name/model/color/description). |
| D-2 | "17 slash commands" (`:317`), commands table lists 17 (`:133-153`) | 39 in `.claude/commands/` + 13 in `templates/commands/` that the installer merges in ⇒ 52. `/santa`, `/prp-plan…pr`, `/code-review`, `/gan-build`, `/hookify`, `/save-session`, `/opensource`, `/onboard`, `/audit`, `/eval`, `/blueprint`, `/learn`, `/refine`, `/checkpoint`, `/spawn`, `/ship`, `/translate`, `/mode`… all absent | Split into "Core pipeline commands" (keep 17-row table) + generated "Full command reference" page in docs/. |
| D-3 | "~45 skills" (`:234`), skills table categories | 73 skills installed | Same generation approach; the registry (`skills-registry.json`) is already the machine-readable source. |
| D-4 | "29 safety guards" (`:35`, FAQ `:422`) vs. header "Safety Guards (26 Total)" (`:215`) — table rows sum to 26 | Internal contradiction within one file | Count guards in `validate-config-json.py`, cite one number, add a test that greps README against the code constant. |
| D-5 | Hooks section documents 5 hooks configured via `.claude/hooks/config.json` (`:252-260`) | 19 hook scripts; live wiring is `.claude/settings.json` (7 official Claude Code events); config.json now mostly carries `project.*` commands | Rewrite the Hooks section around settings.json; list hook *profiles* (`ECC_HOOK_PROFILE`) which are documented only in the CHANGELOG. |
| D-6 | Project structure block: "13 agents / 17 commands / ~45 skills / 5 hooks" and omits `templates/modes`, `templates/mcp`, `templates/skills`, `templates/hooks`, `src/`, `i18n/` (`:299-349`) | Tree is two minor versions stale | Regenerate with `tree -L 2` + counts script. |
| D-7 | Quick-start clone URL `github.com/omarmokhtar/claudekit` and CI badge slug (`:6,46`) | pyproject + schema `$id` say `OmarMokhtar-Saad/claudekit`; badge 404s on the wrong slug | Canonicalize; CI grep-check. |
| D-8 | Badge `ClaudeKit-v2.0.0` (`:2`) | CHANGELOG's newest entry is 1.3.0 (dated *after* 2.0.0); CLI reports 1.1.0 | Version badge should come from a release tag; fix versioning first (see §2). |
| D-9 | Commands shown do exist ✔ — all 17 table commands have matching `.claude/commands/*.md`. `/plan`, `/debug`, `/coordinator` in Quick Start verified. However README never mentions the **CLI** (`claudekit`/`ck`) at all — the pip-facing surface is invisible | Add a "CLI" section linking docs/cli.md (and fix the broken pip install it documents — see DX review DX-10). |
| D-10 | FAQ "Does it work on Windows?" — good honest answer; FAQ says `--dry-run` "lets you preview all changes" without saying *which tool* takes the flag (it's `execute-json-ops.py`/`claudekit execute`, not install.sh) | Name the command in the answer. |

**Badge quality:** static shields for version/license/python/bash are fine; CI badge broken slug (D-7); missing useful ones: tests count/coverage, PyPI (once published), docs link. Remove `for-the-badge` styling inconsistency risk by keeping all five the same style (currently consistent — good).

---

## 2. CHANGELOG.md

Follows Keep-a-Changelog headings and rich, specific entries (genuinely excellent detail level — file paths, thresholds, flag names). But **semver discipline is broken**:

| # | Problem | Evidence | Fix |
|---|---------|----------|-----|
| D-11 | **Ordering/versioning is incoherent:** `[1.3.0] — 2026-04-11` sits *above* `[2.0.0] — 2026-03-17`. A lower version released a month after 2.0.0, containing major new features. pyproject says 2.0.0, CLI says 1.1.0. There is no 1.2.0 anywhere. | `CHANGELOG.md:8,64`; `pyproject.toml:7`; `src/cli/main.py:13` | Decide the real line: the April release should have been **2.1.0**. Publish a corrective note, retag, and add a CI gate: changelog top version == pyproject version == CLI version. |
| D-12 | **Phantom features:** 1.3.0 lists agents `dead-code-hunter` and `open-source-forker` — neither exists in `.claude/agents/`. Conversely, 9 shipped agents (`silent-failure-hunter`, `harness-optimizer`, `performance-optimizer`, `code-simplifier`, `typescript-reviewer`, `python-reviewer`, `tdd-guide`, `refactor-cleaner`, `doc-updater`) appear in **no** changelog entry. | `CHANGELOG.md:19-20` vs. `ls .claude/agents/` | Reconcile: add a corrected entry; add a doc-drift test (changelog-mentioned agent names must exist). |
| D-13 | No `[Unreleased]` section; no version-compare links footer (Keep-a-Changelog conventions). | whole file | Add both. |
| D-14 | 1.3.0 "Fixed" bullet: "Install counts updated … to accurate 30/37/74/15" — those numbers are themselves wrong today (28 agents excl. protocols / 52 commands post-install / 73 skills). | `CHANGELOG.md:62` | Stop hand-counting; counts belong in generated docs only. |

---

## 3. CONTRIBUTING.md

Short but functional (fork → branch → pytest → conventional commits). Problems:
- Wrong repo slug again (`:9,25`).
- No guidance for the most likely contributions: adding a *command*, a *hook*, a *language template*, or a *translation*; no shellcheck invocation shown despite requiring it; no release process; no code of conduct link.
- "Add tests in `tests/`" for skills — but doesn't say which test file patterns (`test_new_skills.py` exists and asserts registry consistency — say so).
**Fix:** expand to sections per contribution type with the exact files to touch (mirror docs/AGENTS.md "Adding a Custom Agent"), add `shellcheck install.sh .claude/hooks/*.sh` to the checklist, document the release/tag process.

## 4. SECURITY.md

- **Supported versions table says "1.x" only** — the project's own README ships v2.0.0. So the current release is formally unsupported by its own policy. Fix: `2.x — yes / <2.0 — no`.
- `security@claudekit.dev` — unverifiable domain; keep the GitHub private-advisory path as primary.
- Good scope section. Missing: threat model note that agents/skills are *prompts* executed by an LLM with shell access — the single biggest real risk (prompt-injection via repo content) is unmentioned even though the project ships a `prompt-injection-scanner` hook. Add a paragraph.

---

## 5. docs/ Directory

| File | Verdict | Key issues → fixes |
|------|---------|--------------------|
| **AGENTS.md** | Stale | "ships 13 specialized agents" — 15 agents undocumented. Color table contradicts README (Tester: Lime vs Magenta; DevOps: Bronze vs Silver; DB Architect: Indigo vs Bronze). Fix: generate the summary table from frontmatter; document each new agent (one paragraph each, like existing entries). |
| **ARCHITECTURE.md** (28 KB) | Best-written doc; stale numbers | Says 13 agents / 17 commands / **44 skills** — a third distinct skills count (44 vs ~45 vs 73). Directory tree omits `modes`, template dirs. Fix: numbers via generation; keep the prose. Diagrams are ASCII-only — export 2–3 as SVG/Mermaid for the README. |
| **SKILLS.md** | Good structure, partial catalog | Catalog covers ~45 of 73 skills; none of the 1.3.0-era skills (santa-method, gan-harness, prp-plan, hookify, context-keeper, opensource-pipeline) nor templates/skills (token-optimization, session-continuity, …) appear. Registry example shows `"version": "1.1"`. Fix: generate catalog from `skills-registry.json`; keep the authoring guide (the TDD skill-writing section is excellent). |
| **HOOKS.md** | Materially outdated | Documents only the 5 legacy hooks and claims config.json is *the* mechanism; `settings.json` (official events), the 14 newer hooks, and `ECC_HOOK_PROFILE` are absent — yet CHANGELOG 1.1.0 says the format "migrated … to official Claude Code settings.json". This is the most confusing doc for a new user. Fix: rewrite around settings.json events; per-hook reference table for all 19 scripts; explain config.json's remaining role (`project.*` commands); document profiles. Note: `.claude/hooks/README.md` duplicates ~70% of this file and also only covers 5 hooks — keep one, link the other. |
| **CONSTITUTION-GUIDE.md** | Good | Concrete, example-driven, includes anti-patterns. Only nit: references Article numbering that assumes the template — fine. No changes needed beyond linking it from README's Constitution section (currently not linked there, only in the docs table). |
| **CUSTOMIZATION.md** | Good, one landmine | Honestly documents that `--force` re-runs destroy customizations ("back them up first") — that's a product bug documented as a feature; update once `--upgrade` exists. Protected-patterns example edits `shared.py` — verify the variable name still matches code after refactors (add a doc-drift test). |
| **cli.md** | Accurate to the CLI code, but… | Documents `pip install -e .` which fails (broken build backend), and `ck` which therefore never exists. Not linked from README's Documentation table (the table lists 6 docs; cli.md is the 7th, orphaned). Fix: link it; fix pip; add `doctor` exit-code semantics and `config` read-only caveat. |

**Missing documentation (net-new pages needed):**
1. **Migration guide 1.x → 2.0** (breaking: hooks format migration, modes dir, command flags) — mentioned nowhere.
2. **Command reference** for all 39+13 commands (generated).
3. **Operations config reference** — `operations-schema.json` exists but no human-readable doc of every op type/field/guard.
4. **Troubleshooting / FAQ page** (README FAQ is good; move+extend: "hooks not firing", "doctor failures", "pip install fails", "detected wrong language").
5. **Modes guide** (7 behavioral modes ship; zero docs outside CHANGELOG).
6. **MCP guide** (`templates/mcp/README.md` exists but is unlinked from anywhere).
7. **Uninstall/upgrade guide** (once the commands exist).
8. **Rendered architecture diagram** (image) for the README hero.

---

## 6. examples/ and i18n/

- **examples/ have no README.md.** Each contains only `CLAUDE.md` + `CONSTITUTION.md` — no app code, no walkthrough — while README calls them "complete example projects" and "a complete setup". A visitor clicking `examples/python-fastapi/` gets no orientation. Fix: add `README.md` per example (what it demonstrates, how it was generated, a transcript of `/plan → /review → /implement` on it), or relabel in README as "example configurations".
- **i18n/** — 6 translated READMEs at 5–7 KB vs the 21 KB English README: heavily abridged and frozen at the 2.0.0 structure; no "last synced" marker; not linked from the English README (no language switcher line), so they're both stale *and* undiscoverable. `tests/test_i18n.py` exists but evidently checks presence, not freshness. Fix: add a language bar at the top of README; add a sync-date header to each translation; either maintain them via the `/translate` command each release or trim them to a translated *overview* that links to English reference docs (recommended — honest and cheap).

## 7. .github/

- Issue templates: clean, correct labels/prefixes. Improvements: convert to **issue forms** (`.yml`) for structured env capture; the bug template's "ClaudeKit version: e.g. 1.0.0" invites the version confusion — tell users to paste `claudekit --version` *and* installer banner. Add `config.yml` with links to discussions/security advisory.
- PR template exists (good). `release.yml` and `security.yml` workflows are undocumented — one line each in CONTRIBUTING.
- No `CODE_OF_CONDUCT.md`, no `SUPPORT.md`.

## 8. Broken links, duplication, tone

- **Internal links:** automated check across README/CHANGELOG/CONTRIBUTING/SECURITY/docs found **no broken relative links** ✔ (the file-level links are fine; the *content* is what drifts). External repo-slug links are the broken ones (D-7).
- **Duplication:** hooks docs ×3 (docs/HOOKS.md, .claude/hooks/README.md, README §Hooks) — three copies, three drift states. Skills catalog ×2 (SKILLS.md vs registry). Install options ×3 (README, usage(), docs/cli.md). Rule: each fact lives in one generated or canonical place; others link.
- **Tone/consistency:** uniformly professional and direct; consistent voice across docs — genuinely good. Terminology nit: "operations config" vs "ops.json" vs "ops config" used interchangeably — pick "ops.json (operations config)" on first use per page.

---

## 9. Proposed Documentation Information Architecture

```
README.md                      # 400 lines max, generated counts, links out
docs/
├── getting-started/
│   ├── installation.md        # bash + pip + pipx, upgrade, uninstall
│   ├── quickstart.md          # first /plan in 5 minutes (with transcript)
│   └── troubleshooting.md
├── guides/
│   ├── customization.md
│   ├── constitution.md
│   ├── hooks.md               # settings.json-first, profiles, all 19 hooks
│   ├── modes.md               # NEW
│   ├── mcp.md                 # NEW (promote templates/mcp/README.md)
│   └── migration-1.x-to-2.md  # NEW
├── reference/                 # GENERATED where possible
│   ├── cli.md
│   ├── commands.md            # all 52
│   ├── agents.md              # all 28, from frontmatter
│   ├── skills.md              # all 73, from registry
│   ├── ops-config.md          # from operations-schema.json
│   └── config-schema.md
├── architecture/
│   ├── overview.md            # current ARCHITECTURE.md prose + SVG diagrams
│   └── decisions/             # ADRs
└── contributing → link to CONTRIBUTING.md
```

Plus: a `scripts/gen-docs.py` that emits the reference pages and README counts, and a CI job `docs-drift` that fails when generated output differs from committed docs. This single mechanism would have prevented ~70% of the findings above.

## 10. Rewritten README Outline (target ≤ 400 lines)

1. **Hero** — one-liner, language bar (EN | العربية | 中文 | …), badges (version from tag, CI on right slug, PyPI)
2. **What/Why** — 4 bullets + one rendered pipeline image (SVG)
3. **Install** — two tabs: `pipx install claudekit && ck init` / `git clone … && ./install.sh`; link installation guide
4. **Your first task** — 10-line transcript of `/plan → /review → /implement → /verify`
5. **Core pipeline commands** — 8-row table; link full command reference (52)
6. **What's inside** — one summary row: *28 agents · 52 commands · 73 skills · 19 hooks · 11 language templates* (generated), each linking to its reference page
7. **Safety model** — ops.json pipeline, guards (one authoritative count), protected files, rollback
8. **Requirements & platform support**
9. **FAQ** — 5 items, link troubleshooting
10. **Community** — contributing, security, license

Everything else (agent bios, skill catalog, hook tables, constitution articles, language matrix, project tree) moves to docs/reference where it can be generated.

---

## 11. Prioritized Fix List

| Priority | Items |
|----------|-------|
| P0 | D-11/D-12 changelog–reality reconciliation; D-7 repo slug everywhere; SECURITY.md supported versions; D-5/HOOKS.md settings.json rewrite |
| P1 | D-1/2/3/6 regenerate counts & tables (build gen-docs.py + drift CI); AGENTS.md/SKILLS.md completion; link cli.md; migration guide; examples READMEs |
| P2 | i18n sync strategy + language bar; issue forms; ops-config reference; modes/MCP guides; README slim-down per outline; CODE_OF_CONDUCT |

**Score rationale (47/100):** Coverage breadth is real (7 docs, translations, templates, FAQ, changelog detail few projects match) and tone is consistently professional (+). But accuracy drift is systemic: three conflicting skill counts, a 13-vs-28 agent gap, a changelog whose latest version is lower *and later* than the one before it and lists agents that don't exist, a hooks doc describing the previous architecture, and a security policy that doesn't cover the current major version. For a project whose pitch is "auditable and safe," docs that can't be trusted to match the code are the most expensive kind of bug.

# Plan: Fleet-Wide Skill Enhancement — New Checklists, Skill Repairs, Distribution

**Status:** DRAFT — awaiting reviewer (≥90/100 gate) and owner sign-off on the gated items in §8
**Tier:** 2 (multi-file, prompt-corpus + agent routing; no security/schema surface in src/)
**Author:** planner session 2026-08-25
**ops.json:** authored per-phase at implement time from the §4 op manifests (see §6 Execution Protocol — the implementing agent generates and validates each ops.json via /generate-ops → /validate-ops before executing; Phase A ops run through the operations engine per Iron Law; Phases B/C touch repos OUTSIDE this working tree and cannot flow through execute-json-ops.py — they run as the scripted, owner-approved sync in §4.B)

---

## 1. Goal

Close the three verified gaps between the ClaudeKit skill corpus and the 17-project fleet in `~/IdeaProjects`:

1. **Missing product**: no `java-review-checklist` / `kotlin-review-checklist` exist anywhere, while 9 of 17 fleet projects are Java/Maven or Kotlin/Gradle. `code-reviewer` per-language routing (code-reviewer.md:40-41) covers only Python and TypeScript.
2. **Defective product**: three shipped skills are stale or non-actionable — `using-superpowers` (64 refs, routing table contradicts CLAUDE.md review routing), `mcp-integration` (documents servers that don't exist in this environment), `security-checklist` (16 refs, zero executable detection content).
3. **Undistributed product**: newest skills (`python-review-checklist`, `typescript-review-checklist`, `verification-gap-lens`) reached 0–1 of 14 kitted projects; 6 superseded duplicate skills linger in all 14; `rest-framework` is ~44 skills behind; `qa-agent-pro` has no kit.

## 2. Evidence (measured 2026-08-25, this session)

### 2.1 Fleet inventory

| Project | Stack | Kit skills | Needs |
|---|---|---|---|
| ai-agent-system, qaforge-ai, qa-agents | Python | 77–79 | py-checklist, gap-lens, dedupe |
| ApiForge (src is Java), AutomationApp, Eatizaz, Lean, LeanApis, MobileUIAutomator, SehhatyApp | Java/Maven | 77–86 | **java-checklist (new)**, gap-lens, dedupe |
| AppiumLens, shsmartassistant-qa | Kotlin/Gradle | 92 / 78 | **kotlin-checklist (new)**, gap-lens (shsmart-qa has it), dedupe |
| rest-framework | Java/Maven | 34 | full refresh (owner-gated) |
| qa-agent-pro | Python | none | bootstrap (owner-gated) |
| test, qa-api-projects, shsmartassistant-agent | —/empty | none | out of scope |

### 2.2 Verified defects

- `grep -l 'python-review-checklist' */.claude/agents/code-reviewer.md` → **only claudekit**. No downstream code-reviewer has per-language routing.
- Superseded duplicates present in all 14 kitted projects (older forks of current skills): `autonomous-loops`→`autonomous-loop`, `context-priming`→`context-keeper`, `session-continuity`→`context-keeper`, `dependency-audit`→`supply-chain-audit`, `verification-loop`→`verification-before-completion`, `i18n-workflow`→`i18n-patterns`. Both halves of each pair claim the same trigger → ambiguous model routing + always-on description cost.
- `mcp-integration/SKILL.md` documents Sequential Thinking / Memory / Filesystem / Playwright; the environment's actual servers are context7, qa-agent-pro, Miro. Its Context7 section also contradicts the CLAUDE.md Token & Model Policy (main agent calls context7 itself).
- `security-checklist/SKILL.md`: 0 code blocks, 0 commands (measured); its "what to look for" prose names no pattern. Contrast `insecure-defaults` (68 table rows, Bash) and `differential-security-review` (7 executed commands) which do the same job operationally.
- `using-superpowers` "Common Mappings" routes "Review this code" → `receiving-code-review`/`requesting-code-review`; CLAUDE.md routes code review → `code-reviewer` agent (+ per-language checklist). Its priority list omits every 2026 skill. Its "no penalty for invoking an irrelevant skill" line contradicts `context-budget`.
- Gates baseline: `check-context-floor --check` **already exits 1** (pipeline agent bodies 44186/43000 OVER — pre-existing, NOT caused by this plan). Skill descriptions 7934/9000 → headroom ≈ 1066 bytes; five new descriptions (~140 B each ≈ 700 B) fits but leaves <400 B — trim two verbose existing descriptions in the same commit if the row exceeds 9000. The plan must not worsen any row.

### 2.3 External corpus scan (2026-08-25, cached in .claude/reports/research/)

Four external sources reviewed via web-researcher (reports: `trailofbits-skills.md`, `awesome-security-skills.md`, `behisecc-and-prompt-evaluation.md`):

| Source | License | Verdict |
|---|---|---|
| trailofbits/skills (40+ skills) | CC BY-SA 4.0 | Adopt methodology (Phase D1/D2); share-alike applies to derivative skill files |
| 46ki75 prompt-evaluation-claude-code | unstated | Adopt method by reimplementation (D3); do not copy text until license verified |
| Anthropic claude-code-security-review (GH Action) | official | Fleet CI gate candidate (D4) |
| Anthropic-Cybersecurity-Skills (28 API + 13 mobile) | Apache 2.0 | QA-fleet candidates (backlog §9) |
| BehiSecc awesome-claude-skills | catalog | Monitor only; nothing fills a current gap |

## 3. Non-goals

- No harvesting of downstream-local skills (AppiumLens `intellij-platform` etc.) into claudekit — recorded in §9 as backlog.
- No consolidation of the 4 overlapping token skills (`token-budget-advisor`/`context-budget`/`token-optimization`/`usage-monitoring`) — belongs to task 008, owner-gated.
- No changes to `src/`, hooks, or the operations engine.
- No release/version bump.

## 4. Operations

### Phase A — claudekit product changes (this repo; via ops engine)

**A1. Create `.claude/skills/java-review-checklist/SKILL.md`** (~220 lines, mirror python-review-checklist structure exactly):
- Frontmatter: `name`, one-line description ("Use when a diff under review contains Java files — the per-language review checklist code-reviewer loads for `.java`: …", ≤160 chars), `user-invocable: false`, `allowed-tools: Read, Grep, Glob, Bash`.
- Dimensions (each with Bad/Good code pair): (1) null-handling & Optional misuse, (2) equals/hashCode/comparable contracts, (3) exception handling (swallowed InterruptedException, broad catch, try-with-resources), (4) concurrency (unsynchronized shared state, SimpleDateFormat sharing, double-checked locking), (5) security (SQL concatenation → PreparedStatement, Runtime.exec with concatenated strings, XXE-unsafe XML factories, unsafe deserialization/ObjectInputStream), (6) performance (string concat in loops, boxing in hot paths, streams misuse), (7) API/idiom (mutable public fields, missing final, raw types).
- `## Automated Checks` with real commands: `mvn -q compile`, `mvn -q test`, grep patterns for `Statement.*executeQuery.*\+`, `Runtime\.getRuntime\(\)\.exec\(`, `printStackTrace\(\)`, `catch \(Exception`, `new ObjectInputStream`, XXE factories; note SpotBugs/PMD/Checkstyle invocation IF configured in the project pom (detect, don't assume).
- `## Report Format` identical shape to python checklist (Score /100, Critical Security Issues, Verdict APPROVE|REQUEST_CHANGES|BLOCK).

**A2. Create `.claude/skills/kotlin-review-checklist/SKILL.md`** (same shape):
- Dimensions: (1) nullability (`!!` abuse, platform types, lateinit misuse), (2) coroutines (GlobalScope, runBlocking on main paths, missing structured concurrency/cancellation, Dispatchers hardcoding), (3) immutability & data classes (var where val, mutable collections exposed), (4) exception handling (swallowed CancellationException — the classic), (5) security (same SQL/exec/deserialization patterns, plus string templates into commands), (6) interop pitfalls (@JvmStatic/@JvmOverloads, checked exceptions), (7) idiom (scope-function abuse, when-exhaustiveness).
- `## Automated Checks`: `./gradlew -q compileKotlin`, `./gradlew -q test`, detekt/ktlint IF configured (detect), grep patterns for `!!`, `GlobalScope\.`, `runBlocking`, `catch \(e: Exception\)`, SQL concat.

**A2b. Create three white-box / AI-agent testing skills** — harvested from the proven method in `~/IdeaProjects/shsmartassistant-qa` (SDK-DEFECTS.md, COVERAGE-MAP.md, 116-test harness; our own fleet, no license issue). ToB authoring conventions apply (D2): <500 lines, `references/`, capability-gated sections.

- **`whitebox-invariant-testing`** (`user-invocable: false`, tools: Read, Grep, Glob, Bash) — the invariant-first adversarial method: (1) build the invariant table FROM SUT source — KDoc/doc promises, guards, events, fail-closed claims — each row = promise + location; (2) attack each invariant only through harness knobs (overrides, failOn, injected clock, out-of-order + repeated calls), NEVER modifying the SUT (read-only composite-build pattern); (3) hostile-environment sweeps as a standard battery: 5xx-everything, 401-everything, captive-portal 200+HTML, timeout — asserting no crash / no write / no unbounded retry / wire-reached; (4) finding shape: invariant broken + SUT file:line + reproducing test + observed-vs-expected + smallest-diff fix sketch.

- **`defect-pinning`** (`user-invocable: false`) — the RED-pin regression protocol: every confirmed defect gets a reproducing test pinned to its exact failure message, quarantined (`@Ignore`/skip-mark) so the merge gate stays green; a dedicated KnownDefects test file is the single quarantine home; on every SUT change re-run all pins live and restore verbatim (fixed pin ⇒ drop the quarantine mark, it becomes the regression proof); companion coverage map with the five-state legend (✅ covered / 🔴 red pin / ⬜ reachable gap / 🔧 needs harness affordance / ⛔ unreachable from this harness) so each pass starts from a list, not from scratch.

- **`ai-agent-testing`** (`user-invocable: false`) — testing LLM-agent systems deterministically: two-suite doctrine (offline deterministic merge gate with stubbed backend + injected clock vs live-LLM exploratory driver that NEVER gates a merge — transient provider errors make it a non-signal); the agent-invariant catalog to assert: tool-call governance (no write without ready+confirm, exactly-once side effects, refused calls don't consume state), provenance/anti-fabrication gates (failed reads must not mark data as fetched), data honesty (render only ledger-backed values), staleness semantics (user activity resets the clock), model-echo resilience (duplicate/same-value re-fills are no-ops), multi-entry verdict completeness (every fill entry gets matched/stashed/no-match), dependent-scoping (revising a step invalidates transitive dependents), locale/RTL contract; cross-links: upstream exploration → `prompt-evaluation` (D3), CI baseline → `eval-harness`, gap judging → `verification-gap-lens`.

**A3. Edit `.claude/agents/code-reviewer.md`** — extend the per-language block (lines 40-41) with:
- `**java-review-checklist** — load when the diff contains .java files`
- `**kotlin-review-checklist** — load when the diff contains .kt/.kts files`

**A4. Edit `.claude/skills/using-superpowers/SKILL.md`** (surgical, 3 edits — do NOT rewrite the file):
- Common Mappings: "Review this code" row → `code-reviewer agent + per-language review checklist (python/typescript/java/kotlin)`; keep requesting/receiving rows for the PR-etiquette cases they actually cover.
- Priority list: add `verification-gap-lens` (verification tier) and `context-budget` (process tier).
- Replace "There is no penalty for invoking a skill that turns out to be irrelevant" with a calibrated line: irrelevant invocations cost context (`context-budget`); when in doubt between two candidates, read both descriptions first, invoke one.

**A5. Rewrite `.claude/skills/mcp-integration/SKILL.md`** body (keep name/flags):
- Structure: generic "evaluate any MCP server" method (purpose → tool inventory via ToolSearch → cost/latency → when built-ins beat it) + concrete sections ONLY for servers actually shipped/configured (context7 — aligned with CLAUDE.md policy that main agent calls it directly; note that project MCP rosters vary and the skill must instruct detection via ToolSearch/`/mcp`, not assume a roster). Delete Sequential-Thinking/Memory/Filesystem/Playwright sections (that guidance moves to one "common third-party servers" table, 5 rows max).
- Keep byte count ≤ current (6575) — context-floor row must not grow.

**A6. Upgrade `.claude/skills/security-checklist/SKILL.md`** (keep all sections; make them executable):
- Under each Risk section add a fenced `# Detect` block with 1-3 concrete grep/rg patterns (language-agnostic ERE: `shell\s*=\s*True|Runtime\.getRuntime|child_process`, `(SELECT|INSERT|UPDATE|DELETE).*(\+|%s|\$\{|f")`, `(password|api_key|secret|token)\s*[:=]\s*["'][^"']{8,}`, `\.\./` path handling, etc.).
- Add closing `## Escalation` row: deep diff work → `differential-security-review`; config/defaults → `insecure-defaults`; language specifics → the per-language checklist.
- Net growth ≤ 1.5 KB; it is `user-invocable: false` so command-description budget is untouched; verify skill-description row stays ≤ 9000.

**A7. Regenerate + gate (no hand edits):**
- `python3 scripts/gen-registry.py` (new skills registered; code-reviewer mapping updated) then `--check`.
- `python3 scripts/gen-docs.py` (counts: skills 73→78; +1 more if D3 approved) then `--check`.
- `python3 scripts/gen-model-policy.py --check` (should be untouched).
- `python3 scripts/check-context-floor.py --check` — expected: still exit 1 on the PRE-EXISTING pipeline-agent-bodies row; assert skill-descriptions row stays OK and no other row flips. Record before/after numbers in the commit body.
- `python3 -m pytest tests/ -q`, `ruff check src/ tests/ scripts/`, `mypy`, `shellcheck install.sh .claude/hooks/*.sh`.

**A8. Docs:** CHANGELOG `[Unreleased]`: Added (2 checklists + code-reviewer routing), Changed (using-superpowers routing fix, mcp-integration rewrite, security-checklist detection patterns). Update `.ai/SESSION_STATE.md` + `.ai/CHANGELOG_AI.md`.

**A9. Behavioral tests** (new `tests/test_language_checklists.py` or extend existing skill tests, following the existing test conventions):
- Both new SKILL.md files parse (frontmatter fields present, `user-invocable: false`, description ≤160 chars).
- code-reviewer.md contains all four routing lines (py/ts/java/kotlin).
- Registry contains all five new skills after regen (2 checklists + 3 testing skills).
- security-checklist contains ≥6 fenced Detect blocks; mcp-integration contains no occurrence of `Sequential Thinking|Playwright` as a section heading.

**Commit plan (Phase A):** 3 conventional commits — `feat(skills): add java and kotlin review checklists with code-reviewer routing`, `fix(skills): repair stale routing and non-actionable content in using-superpowers, mcp-integration, security-checklist`, `docs(ai): session state + changelog` (or fold docs into each). Co-Authored-By line per convention.

### Phase B — fleet distribution (13 kitted repos; scripted, OUTSIDE ops engine; owner-approved)

Rules of engagement (binding, from fleet memory): surgical sync only; never overwrite project-specific local skills; leave every downstream repo **uncommitted** for the owner; never merge downstream back.

Per project, from the matrix in §2.1:

**B1. Add** (copy directory from claudekit): `verification-gap-lens` (where missing — 13 of 14), plus stack-matched checklist(s): `python-review-checklist` → 3 Python projects; `java-review-checklist` → 7 Java projects; `kotlin-review-checklist` → AppiumLens, shsmartassistant-qa. `typescript-review-checklist` → none (no TS project found; do NOT distribute speculatively). **White-box/agent-testing trio** (`whitebox-invariant-testing`, `defect-pinning`, `ai-agent-testing`) → shsmartassistant-qa (origin project — closes the loop), qa-agents, ai-agent-system, AppiumLens, MobileUIAutomator, ApiForge; other projects on request.

**B2. Surgical edit** each project's `.claude/agents/code-reviewer.md`: insert the per-language routing block after the security-checklist entry (match claudekit's block, but list only the checklists that project received). If a project's code-reviewer.md has diverged beyond recognition of the anchor, SKIP and log it in the sync report — do not force.

**B3. Delete the 6 superseded duplicates** in each of the 14 kitted projects (`autonomous-loops`, `context-priming`, `session-continuity`, `dependency-audit`, `verification-loop`, `i18n-workflow`) — **owner-gated, one approval covering the list**; before each delete, diff against the current-kit successor and abort that project's delete if the local copy contains project-specific additions (>20% novel lines vs the old kit version) — then log instead of delete.

**B4. Skill-registry sidecars:** if the project carries `.claude/skills/skills-registry.json`, regenerate it with the project's own gen script if present; else append entries matching claudekit's shape; else leave absent.

**B5. Sync report:** write `~/IdeaProjects/claudekit/.claude/reports/fleet-sync-2026-08-25.md` — per project: files added / edited / deleted / skipped + reason. This is the artifact the owner reviews before committing downstream.

### Phase C — stragglers (owner-gated, separate approvals)

**C1. rest-framework refresh:** it is 44 skills behind and its 31 hooks may predate current hook contracts. Do NOT surgical-sync; run the supported path instead: `ck adapt`/installer from current claudekit into rest-framework, preserving its 5 local skills (`add-api-test`, `extend-test-infrastructure`, `session-continuity`→migrate to context-keeper convention, `dependency-audit`, `verification-loop`) per the preserve-local rule. Then apply B1–B3 for its Java stack.

**C2. qa-agent-pro bootstrap:** fresh `ck` install (it's the shipped MCP-server product — owner decides whether it gets a kit at all; it may be intentionally kit-free to keep the shipped zip clean. Ask first; default NO-ACTION without explicit yes).

### Phase D — external adoptions (owner-gated; each item separately approvable)

**D1. Enrich `differential-security-review`** with Trail of Bits differential-review methodology: risk-first prioritization (auth/crypto surfaces outrank diff size), size-adaptive depth (small diff = full analysis, large = surgical), and concrete-attack-scenario evidence rule. Derivative content ⇒ CC BY-SA 4.0 attribution block at top of SKILL.md (precedent: verification-gap-lens attribution chain). Keep byte growth ≤ 1.5 KB.

**D2. Apply ToB authoring conventions to A1/A2 as they are written** (no extra approval needed — style only): SKILL.md < 500 lines, `references/` for anything beyond core flow, capability-gated activation (e.g. kotlin checklist's coroutine cluster only when `grep -rl kotlinx.coroutines` hits), situational-trigger descriptions. Also fold these conventions into `writing-skills` (one short subsection, cite source).

**D3. New skill `prompt-evaluation`** — reimplementation (not copy; upstream license unstated) of the 46ki75 method: isolated subagent judges, ONE judge per criterion (compound rubrics ⇒ halo effect), reasoning-before-verdict, pairwise comparison for A/B, versioned eval-set files. Positioned explicitly as the exploratory stage upstream of `eval-harness` (which stays the CI-gated baseline). `user-invocable: true`; wire a cross-reference from eval-harness. Budget check: description ≤160 chars against the 9000-byte floor row.

**D4. Fleet CI security gating** — evaluate Anthropic's official `claude-code-security-review` GitHub Action for the 9 Java/Kotlin fleet repos' CI (diff-aware, line-level PR comments). Evaluation + one pilot repo only; rollout is a separate plan.

## 5. Acceptance criteria

1. Phase A: all §A7 gates pass (context-floor: no new OVER rows; the pre-existing pipeline-bodies OVER is unchanged or improved), tests from A9 green, 2 new skills + 4 routing lines live, CHANGELOG updated, committed conventionally.
2. Phase B: every kitted project (13, excluding rest-framework) has its stack checklist + gap-lens + routing edit OR a logged skip reason; zero project-local skills modified/removed outside the approved dedupe list; all downstream repos left uncommitted; sync report exists.
3. Reviewer verdict ≥90/100 recorded via review-record.py **with the anchored `=== REVIEW ===` block explicitly requested in the review prompt** (known trap: reviewers don't emit it unasked).
4. Rollback: Phase A via ops-engine backup / `git revert`; Phase B via `git checkout -- .claude/` in each downstream repo (uncommitted, so trivially reversible — state this in the sync report).

## 6. Execution protocol

1. `/review` this plan (reviewer agent; request the anchored review block). Iterate via `/refine` until ≥90.
2. Owner sign-off on gated items (§8).
3. Implementer: generate ops.json for Phase A (expect ~12 ops: 2 creates, 4 edits, 2 test files, regens run as validation commands not ops), `/validate-ops`, execute, run gates, commit.
4. **Verifier does not auto-run** — stop and ask the user (policy).
5. Phase B script run (plain bash from claudekit repo, iterating the matrix), then sync report to owner.
6. Phase C only on separate explicit approvals.

## 7. Risks

| Risk | Mitigation |
|---|---|
| New skill descriptions blow the 9000-byte floor row | Both ≤160 chars; assert row in A7 before commit |
| Downstream code-reviewer.md anchors drifted | B2 skip-and-log rule; never force |
| Dedupe deletes a locally-customized skill | B3 diff-before-delete + abort threshold |
| mcp-integration rewrite loses guidance someone relies on | Old content preserved in git history; rewrite keeps a 5-row third-party table |
| Pre-existing context-floor failure blocks the DoD gate | Documented as pre-existing in §2.2; commit body records before/after; fixing it is out of scope (flag to owner) |
| rest-framework's old hooks conflict with new kit | C1 uses the supported installer path, not file copies |

## 8. Owner decisions required before execution

1. Approve Phase B3 dedupe-delete list (6 skills × 14 projects, with the diff-guard).
2. Phase C1 rest-framework full refresh: yes/no.
3. Phase C2 qa-agent-pro kit: yes/no (default no).
4. Phase D1 (CC BY-SA derivative in differential-security-review): yes/no.
5. Phase D3 (`prompt-evaluation` skill, +1 to skill count/context floor): yes/no.
6. Phase D4 pilot repo for the security-review Action (suggest: ApiForge): yes/no + which repo.
7. Acknowledge pre-existing context-floor failure (pipeline agent bodies 44186/43000) — separate fix ticket?

## 9. Backlog seeds (not in this plan)

- Harvest upstream: AppiumLens `intellij-platform`/`theme-system`/`ui-component-library`, MobileUIAutomator `maven-workflow`/`e2e-testing-standards`, qa-agents `flow-diagram`/`miro-diagram` as claudekit template-pack candidates.
- Task 008 extension: consolidate `token-budget-advisor`/`context-budget`/`token-optimization`/`usage-monitoring`.
- Convert the 14 zero-command "standards" encyclopedias (accessibility, api-design, performance, error-handling, clean-architecture, monitoring, refactoring-patterns, code-explanation, db-migration, ci-cd, documentation, containerization, i18n, property-based-testing) to on-demand references/ or add Detect blocks — same treatment as A6.
- Anthropic-Cybersecurity-Skills (Apache 2.0): cherry-pick from its 28 API-security and 13 mobile skills for the QA fleet (OWASP API Top 10, OAuth/JWT) — needs its own selection pass.
- Trail of Bits `supply-chain-audit` deltas (publisher concentration, abandoned-upstream detection) → enrich claudekit's supply-chain-audit.
- Trail of Bits Trailmark (polyglot code graph, 25+ parsers incl. Java/Python) → possible upgrade path for codebase-mapping's project-graph sidecar.
- Fleet sync tooling: no script exists (verified); each sync is bespoke. A `scripts/fleet-sync.py` with the B-rules encoded would de-risk every future pass.

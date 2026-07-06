# ClaudeKit — Final Engineering Audit Report

**Date:** 2026-07-05 · **Version reviewed:** v2.0.0 (pyproject) / CLI 1.1.0 / CHANGELOG 1.3.0 / zero git tags
**Inputs:** 11 specialist reviews (see Index, §10) · **Companion documents:** [`roadmap.md`](roadmap.md), [`tasks/001–014`](tasks/)

---

## 1. Executive Summary

ClaudeKit is a **conceptually strong, execution-broken** project.

The concept is genuinely differentiated: a multi-agent orchestration layer for Claude Code where every change flows through a plan → scored review (≥90/100) → validated, atomic, rollback-capable ops.json execution → verification pipeline, enforced by hooks rather than exhortation. No comparable Claude Code kit has a deterministic, transactional execution engine. The adversarial-review designs (Santa dual review, GAN evaluator loops, anti-anchoring via context-free fresh spawns) are best-in-class ideas, and the asset corpus (28 agents, 39+13 commands, 73 skills, 19 hooks, 11 language templates, 6 translated READMEs) is top-decile for the category. The operations scripts (validate/execute/restore) show real engineering care — atomic writes, manifests, transactional rollback, signal handling.

The execution undermines nearly every promise:

- **The pip package has never been installable** — the declared build backend does not exist (pyproject.toml:3), and no CI job ever built the wheel.
- **The hooks — the entire enforcement layer — have never enforced anything**: install.sh never copies `settings.json` (so hooks are never registered in fresh installs), and every "blocking" hook uses `exit 1`/stdout where Claude Code requires `exit 2`/stderr.
- **The advertised security layer is dead code**: `src/security/` is imported only by its own tests, while docs describe a command-validation pipeline that does not run — and the kit's own core commands ship `--dangerously-skip-permissions`.
- **The pipeline contradicts itself at its critical path**: planner.md embeds an ops.json schema that the kit's own validator rejects, and the implementer's mandatory skill instructs the exact tool usage the implementer's Iron Law forbids.
- **Nothing about its identity is auditable**: five version strings with four values, a CHANGELOG whose latest release is lower *and later* than the previous one, README counts wrong by 2×, two conflicting repo URLs (one 404s), a security policy that doesn't cover the current major version, CI that runs `|| true` on its test jobs, and one test red at head.

None of this requires redesigning the ideas. The defects cluster in the delivery shell — packaging, wiring, versioning, deduplication, CI honesty — and roughly 90 focused days closes the gap (`roadmap.md` v2.1 → v3.0). The strategic move beyond repair is packaging the differentiator (the ops engine + constitutional gates) as a native Claude Code plugin, adding a real update mechanism, and building the eval framework that turns the kit's quality claims from marketing into data.

**Verdict: NOT production-ready.** Recommended for experimentation by users who read the source; not recommendable to teams until v2.1 ships. The distance from here to "credible" is short; the distance from "credible" to "category-defining" is real but fundable by the existing concept quality.

---

## 2. Score Table

Scores for DX, Documentation, Test Coverage, Security, Performance, Feature Completeness, OSS Maturity, and Code Quality come directly from their reviews. Architecture, AI Architecture, Prompt Engineering, Context Engineering, Agent Quality, and CLI are assigned in this synthesis from their reviews' severity profiles, calibrated against the scored reviews.

| Dimension | Score | Weight | One-line justification |
|---|---|---|---|
| **Overall Repository Score** | **49/100** | — | Weighted sum below; conceptually top-decile, executionally bottom-decile — they average out to "promising, unshippable." |
| **Production Readiness** | **NO** | — | Two P0s make the product false-by-default (uninstallable package, non-blocking enforcement); ship-blocker list in roadmap §1. |
| Architecture | 48 | 10% | Sound conceptual design (agents↔artifacts↔ops↔hooks) wrapped in a broken physical layer: 3 P0s, 9 P1s, no manifest, no update path (architecture-review). |
| Code Quality | 54 | 10% | Ops scripts are genuinely well-engineered; but the package doesn't install, enforcement doesn't enforce, and five features are silently dead from wiring drift (code-review). |
| AI Architecture | 62 | 8% | Rare, real enforcement (ops.json + hooks) and correct anti-anchoring designs — undercut by four self-contradictions on the critical path (ai-review). |
| Prompt Engineering | 55 | 5% | Role clarity is excellent (build-error-resolver, loop-operator); score gates are precise-but-uncalibrated theater with no output validation or few-shot output exemplars (ai-review §4). |
| Context Engineering | 45 | 5% | File-based handoffs and fresh-context protocol are exactly right; 12.4K-token routing tax, 28–35K coordinator boots, and four-layer duplication betray the token-economy pitch (ai-review §5, performance-review). |
| Agent Quality | 65 | 5% | Best-written agents are exemplary and frontmatter examples are consistently good; 10 of 30 agents are merge/delete candidates and one references a ghost agent (ai-review §1). |
| Documentation | 47 | 7% | Broad, professional, translated — and systemically untrustworthy: 13-vs-28 agent gap, three skill counts, incoherent changelog, hooks doc describes the previous architecture (documentation-review). |
| CLI | 40 | 4% | Clear verbs and good error-message discipline, but it has never been installable, advertises an env var it doesn't read, and doctor validates against stale magic numbers (developer-experience §2, code-review §9). |
| Developer Experience | 54 | 8% | Decent bash installer and doctor concept; broken pip path, data-destroying failure/upgrade semantics, and a success summary that lies (developer-experience). |
| Security | 32 | 14% | The gap between marketed and actual safety is the finding: dead security layer, fail-open guards, inert file-guard/injection-scanner, and shipped `--dangerously-skip-permissions` (security-review). |
| Performance | 68 | 5% | Install is fast/offline and CLI is fine; costs are the 150–300 ms/tool-call hook chains and the ~12.4K-token routing surface — all fixable by consolidation (performance-review). |
| Test Coverage | 42 | 9% | ~85% file-existence theater, CLI at 0% in-process coverage, the best-tested module is dead code, and a red test ships at head (testing-review). |
| OSS Maturity | 44 | 4% | Content-rich, release-poor: zero tags, no PyPI, no CoC/CODEOWNERS/labels/demo, CI that swallows failures — 90 days of pure execution closes it (oss-excellence). |
| Feature Completeness | 58 | 6% | Prompt-side coverage is excellent; deterministic tooling behind the prompts is thin — no plugin packaging, no update, no evals (missing-features). |

**Weighted overall: 49/100** (Σ score×weight = 49.5).

---

## 3. Top 100 Improvements

Deduplicated across all 11 reviews; grouped by category; source review in brackets. P-ratings and effort in `roadmap.md` §9; implementation detail in `tasks/`.

### A. Packaging & Distribution (1–10)
1. Fix `build-backend` → `setuptools.build_meta`; the package has never installed [arch F-1, code §1, DX-10]
2. Rename top-level `src` package → true src-layout `src/claudekit/` with `claudekit.cli.main:main` entry points [arch F-2, code §1]
3. Ship product assets in the wheel (`.claude/` → package data) so pip isn't parasitic on a git clone [arch F-3, DX-12]
4. Single version source of truth via pyproject + `importlib.metadata`; kill the 4-value drift [arch F-4, code §1, DX-3]
5. Tag the first release; exercise release.yml; publish to PyPI with Trusted Publishing [oss #1, #4]
6. Resolve the `claudekit` npm-name collision before publishing [oss PyPI note]
7. Ship `.claude-plugin/plugin.json` + `marketplace.json` — the native distribution channel [missing #1, oss #6]
8. `ck update` with install-time hash manifest; three-way merge of user modifications [arch F-21, missing #2, DX-5]
9. `ck uninstall` that reverts .gitignore mutations and removes only manifest-listed files [DX-5]
10. Drop dead `setuptools-scm` build dep; declare `jsonschema` as optional extra; bump requires-python ≥3.9 [code §1]

### B. Security (11–25)
11. Remove `--dangerously-skip-permissions` from /plan, /review, /refine [sec §4.1, ai §2.3, arch F-10]
12. Wire `src/security/` as a fail-closed PreToolUse guard or delete it — end the false guarantee [sec §1, code §8]
13. Fix CommandValidator reading `hooks.safeMode` instead of `security.safeMode` [code §8, sec §1a]
14. Split commands on `;`/`&&`/`||`/`|` and validate each segment; de-allowlist bash/sh/xargs/find [sec §1a, testing #3]
15. Fix PathGuard relative-symlink resolution (link dir, not cwd) and substring pattern matching [code §8]
16. Make all blocking guards fail closed on JSON-parse mismatch, with self-tests [sec §3.2]
17. Wire the dormant file-guard.sh and prompt-injection-scanner.sh into settings.json [sec §3.3]
18. Fix the `\x27` secret-regex bug — single-quoted secrets currently pass the commit scan [code §5, sec §3.2]
19. Enforce the autonomous-loop block-list via hook, not narration; sandbox profile for loops [sec §4.2, missing #13]
20. Pin MCP servers to exact versions; drop `npx -y @latest`; default filesystem server to read-only [sec §6, missing #10]
21. Pin GitHub Actions by commit SHA; add dependabot.yml [sec §6, oss #13]
22. Pin test deps with hashes; add least-privilege `permissions:` blocks to workflows [sec §6]
23. Publish SHA256SUMS + Sigstore signatures + SLSA provenance with releases [sec §2.1, oss #13]
24. `git rm --cached` committed hooks.log (159 KB with usernames/paths), cost-tracker.log, counters [sec §5.1, arch F-18]
25. SECURITY.md: support 2.x; disclose the prompt-injection threat model and hooks-are-advisory reality [sec §7, docs §4]

### C. Hooks & Enforcement (26–37)
26. `exit 1` → `exit 2` + stderr in all four blocking hooks — nothing has ever blocked [code §2]
27. install.sh must install/merge `.claude/settings.json` — hooks are dead on arrival without it [arch F-6, code §3]
28. Fix post-tool-use.sh's nonexistent env vars → stdin JSON; revives tool tracking + cost tracker [code §2]
29. Unify the ops filename split-brain (`*.ops.json` vs `ops-*.json`) — validation has matched zero files forever [code §4]
30. Extract `.claude/hooks/lib.sh` (ROOT resolution, logging, JSON extraction) from 10+ copy-pasted variants [code §5, §11]
31. Consolidate per-event hooks into one dispatcher — 9–15 spawns/call → ≤2, ~100 ms saved [code §12.7, perf §3]
32. `ROOT` fallback when `git rev-parse` fails — hooks silently break in non-git dirs [code §2, arch F-24]
33. Remove ops-enforcement.sh's documented cp/sed bypass; gate `sed -i`/`tee`/`>` writes to source paths [ai §3.9]
34. Fix commit-quality bash-4 `${VAR,,}` (breaks stock macOS) and its `-m` extraction regex [code §5]
35. Fix suggest-compact stale-lock freeze and GNU-only `date -r` (daily reset never fires on macOS) [code §5]
36. auto-checkpoint: record stash SHAs not `stash@{0}`; verify `stash apply`; lock the registry [code §6]
37. config-protection: anchor patterns; allow creating a *new* pyproject.toml (currently always blocked) [code §5]

### D. Installer & DX (38–49)
38. Replace the ERR-trap `rm -rf "$DEST"` with staging-dir install + backup + atomic swap [arch F-5, code §3, DX-4]
39. Guard against curl|bash (missing `$CLAUDE_SRC` → destructive trap today) [code §3]
40. `--yes`/non-interactive mode; fail loudly when stdin isn't a TTY [DX-7]
41. Print computed counts in the epilogue — the current summary hardcodes false numbers [code §3, DX-6, arch F-14]
42. Escape sed replacement values — `|`/`&` in a build command corrupts generated docs mid-install [code §3]
43. Idempotent `--force`: install into a fresh dir so stale files don't survive across versions [code §3]
44. Honor `CLAUDEKIT_HOME` — the error message promises it; the code never reads it [code §9, DX-12]
45. doctor: manifest-driven expected counts (stale ≥9/≥8/≥27 lets half-broken installs pass) [code §9, DX-14]
46. doctor: verify every settings.json hook command points at an existing executable; add `--strict` [DX-15]
47. Fix language detection: JS-vs-TS via tsconfig; nested csproj; kotlin false positives [DX-9, code §3]
48. Point users at `claudekit doctor` in the install epilogue and README [DX-13]
49. Init wizard (3 questions filling CLAUDE.project.md/CONSTITUTION/config) — 8–9 setup steps → 3 [DX §6]

### E. AI / Prompts / Orchestration (50–69)
50. Fix planner.md's embedded ops.json schema — it fails the kit's own validator [ai §3.1 — the #1 AI fix]
51. Rewrite execute-operations-config to script-only execution; fix its `allowed-tools` [ai §3.2]
52. Standardize ONE agent-invocation mechanism in one document; end the Task-tool vs `claude -p` split [ai §2.2]
53. Define approval modes (interactive/pipeline/autonomous); rewrite golden-rule around them [ai §3.3]
54. Cut mandatory skill loads to ≤2/agent with inline 5-line digests — saves 60–80K tokens/pipeline [ai §5.2]
55. Add calibration anchors + machine-parseable output contract + arithmetic check to reviewer/verifier [ai §4.1]
56. One reviewer decision taxonomy (agent vs /review command currently disagree) [ai §3.4]
57. Merge autonomous-loop + autonomous-loops; verification-loop + verification-before-completion [ai §6.9]
58. Merge the token/context skill quintet to 2; onboarding pair; dependency pair (73 → ~60 skills) [ai §6.9]
59. Merge python/typescript-reviewer + silent-failure-hunter into code-reviewer (checklists become skills) [ai §1]
60. Merge documenter + doc-updater; convert tdd-guide and model-router to skills/tables [ai §1]
61. Registry becomes authoritative: generate agent skill lists from agentMapping; CI diff check [arch F-13, ai §6.8]
62. Clean registry drift: `loop-start`/`opensource` are commands not agents; `i18n-workflow` doesn't exist [ai §6.8]
63. Fix ghost refs: `opensource-forker` agent, `/generate-ops|/validate-ops|/execute-ops` commands [ai §6.8]
64. Commands ≤40 lines: parse args, name agent, name skills, define artifact contract — nothing else [arch F-19, ai §2.1]
65. Deduplicate four-layer content to canonical homes — ~30–40% corpus reduction [ai §5.3]
66. Wire loop-operator mechanically: loop writes state/loop.json; Stop hook runs stagnation check [ai §6.6]
67. Auto-escalate high-risk plans (auth/migration/public API) to Santa/GAN modes [ai §6.5]
68. Add `/quick-fix` fast path: one-op config generated+validated+executed without full ceremony [ai §6.3]
69. One worked end-to-end example (plan → ops.json → review → execution log) in `_shared/` [ai §4.4]

### F. Testing & CI (70–81)
70. Remove `|| true` from cli-tests/security jobs — failures currently cannot fail CI [oss #3, arch F-23]
71. Run all 14 test files in CI (9 never run); add macOS to the matrix; Windows smoke [testing]
72. Fix the red test by adding a MAX_DELETIONS cap — real unbounded-delete gap [testing]
73. CI `python -m build && pip install` smoke — would have caught the P0 for a year [arch F-23]
74. CI install.sh → doctor --strict integration job on fixture projects — would have caught F-6 [arch F-23]
75. In-process CLI tests (current subprocess approach = 0% coverage of main.py's 272 stmts) [testing]
76. Behavioral hook tests: run guards against good/bad/malformed payloads, assert exit codes [testing #9-10]
77. Frontmatter-schema golden tests for every agent/command/skill; registry integrity in pytest [testing #6-7]
78. Dangerous-instruction lint across all shipped markdown (rm -rf, --dangerously, auto-approve) [testing #8]
79. Eval framework: `ck eval` runner, golden ops.json snapshots, nightly CI for the 5 core agents [missing #3]
80. Structured review.json/verify.json verdicts; hook mechanically gates /implement on score [missing #8]
81. Coverage gate in CI — the kit demands 80% of users and measures 0% of itself [testing, oss #3]

### G. Documentation (82–91)
82. One canonical repo slug everywhere (one of the two current URLs 404s) + CI grep [DX-2, docs D-7, sec §5.3]
83. Renumber the CHANGELOG (1.3.0 released after 2.0.0); add [Unreleased]; remove phantom agents [docs D-11/12]
84. Generate all counts/tables from the tree/registry (`gen-docs.py`) + docs-drift CI job [docs D-1/2/3/6, arch F-14]
85. Rewrite docs/HOOKS.md around settings.json — it documents the previous architecture [docs §5]
86. One guard count (README says both 26 and 29) derived from the validator constant [docs D-4]
87. Migration guide, full command reference, ops-config reference, modes + MCP guides [docs §5]
88. Link docs/cli.md from README (currently orphaned); add a CLI section [docs D-9]
89. i18n: language bar in README, sync-date headers, trim-to-overview strategy [docs §6, oss]
90. Per-example READMEs + runnable apps + checked-in workflow transcripts [docs §6, oss #10]
91. MkDocs Material site on Pages over the existing docs [oss #11]

### H. Performance & Context (92–95)
92. Stop loading skills-registry.json alongside frontmatter (~7K duplicate tokens/session) [perf §6.1]
93. Tier the skill catalog: ~20 core in routing surface, niche behind explicit invocation [perf §6.2]
94. Cache `git rev-parse` once per session (`CK_ROOT`) instead of ~14 hook invocations [perf §7.2]
95. Strip decorative output (progress bars, box diagrams) from agent output formats [ai §5.4]

### I. OSS & Community (96–100)
96. Community sweep: CODE_OF_CONDUCT, SUPPORT.md, FUNDING.yml, CODEOWNERS, YAML issue forms, labels, Discussions [oss #7]
97. Demo GIF of plan→review→implement→verify at the top of README [oss #5]
98. release-please on the already-Conventional commits — kills version drift permanently [oss #8]
99. Consumer GitHub Action (`claudekit-action@v1`): lint assets, validate ops.json in PRs [missing #6]
100. Publish the "85% token reduction" benchmark with methodology — claims become data [oss #12, missing #15]

---

## 4. Top 50 Bugs (ranked)

| # | Sev | Location | Bug | Source |
|---|-----|----------|-----|--------|
| 1 | P0 | pyproject.toml:3 | Build backend `setuptools.backends._legacy:_Backend` doesn't exist — package never installable | code, arch F-1 |
| 2 | P0 | block-no-verify.sh:46, ops-enforcement.sh:96, config-protection.sh:91, commit-quality.sh:133 | Blocking hooks `exit 1`+stdout; Claude Code blocks only on `exit 2`+stderr — no hook has ever blocked | code §2 |
| 3 | P0 | install.sh (absent) | `.claude/settings.json` never installed — all hooks inert in every fresh install | arch F-6, code §3 |
| 4 | P0 | plan.md:30, review.md:55, refine.md:96/112/150 | Shipped commands run sub-agents with `--dangerously-skip-permissions` | sec §4.1 |
| 5 | P0 | .claude/agents/planner.md Phase 3 | Embedded ops.json schema fails the kit's own validator — pipeline broken at source | ai §3.1 |
| 6 | P0 | skills/execute-operations-config | Instructs Edit-tool execution the Implementer's Iron Law and ops-enforcement forbid | ai §3.2 |
| 7 | P1 | install.sh:94-101 | ERR trap `rm -rf "$DEST"` deletes user's pre-existing `.claude/` on any mid-install failure | arch F-5, code §3, DX-4 |
| 8 | P1 | pre-commit.sh:91, settings.json Stop hook vs `.claude/plans/*.ops.json` | Ops filename split-brain — ops validation has matched zero files forever; enforcement blocks the repo's own plan files (ops-enforcement.sh:56) | code §4 |
| 9 | P1 | settings.json PostToolUse; post-tool-use.sh:14 | Fed env vars Claude Code never sets — tool tracking, ops revalidation, cost tracker all dead | code §2 |
| 10 | P1 | src/security/ (whole package) | Advertised security layer imported by nothing but its tests; ARCHITECTURE.md:535 describes a pipeline that doesn't run | sec §1, code §8 |
| 11 | P1 | command_validator.py:94 | Reads `hooks.safeMode`; schema defines it under `security` — user security config silently ignored | code §8 |
| 12 | P1 | command_validator.py:16,79-87 | `bash`/`sh` allowlisted, only argv[0] checked — `bash -c 'rm -rf /'` and `x && rm -rf /` pass | sec §1a |
| 13 | P1 | pyproject.toml:29-40 | Installs top-level package literally named `src` — namespace collision | code §1 |
| 14 | P1 | templates/hooks/auto-checkpoint.sh:144-153 | `stash push` + silently-swallowed `stash apply` can vanish uncommitted work; `stash@{0}` refs drift → prune drops wrong stashes (line 101) | code §6 |
| 15 | P1 | .claude/skills vs templates/skills | 13 duplicated skills, `incident-response` + `spec-driven-development` already diverged; install copy-order decides the winner | arch F-11 |
| 16 | P1 | CHANGELOG.md:8,64 | 1.3.0 dated a month after 2.0.0; CLI says 1.1.0; shared.py says 3.1.0 — version numbers decorative | arch F-4, docs D-11 |
| 17 | P1 | config-protection.sh / security-reminder.sh / ops-enforcement.sh | Blocking guards fail **open** on JSON-shape drift (`2>/dev/null` + exit 0) | sec §3.2 |
| 18 | P1 | config.schema.json:138 vs .claude/hooks/config.json:2 | Shipped config violates its own schema (`_note` vs additionalProperties:false); nothing validates against the schema anyway | code §10, arch F-15 |
| 19 | P1 | validate-config-json.py (validate_file_operations) | No aggregate deletion cap — unbounded `file_delete` in one config; ships a red test | testing |
| 20 | P1 | src/cli/main.py:31-53 | Error text says "Set CLAUDEKIT_HOME"; the variable is never read | code §9, DX-12 |
| 21 | P1 | settings.json wrappers | `ROOT=$(git rev-parse …)` no fallback → paths become `/.claude/hooks/...`; all enforcement disappears in non-git dirs | code §2 |
| 22 | P1 | .github/workflows/ci.yml | `pytest … || true` on cli/security jobs — failures cannot fail CI; 9/14 test files never run | oss, testing |
| 23 | P1 | README.md:6,46 vs pyproject.toml:34 | Two repo slugs; one 404s; unclaimed slug is a squat risk | DX-2, sec §5.3 |
| 24 | P1 | .claude/agents/opensource-packager.md | References Stage-2 agent `opensource-forker` that doesn't exist — pipeline stalls | ai §6.8 |
| 25 | P1 | settings.json → ops-enforcement.sh | Hook referenced by settings.json was untracked in git — fresh clones wire hooks to a missing script | arch F-9 |
| 26 | P2 | pre-commit.sh:115-128 | `\x27` inside `grep -E` classes isn't ERE — single-quoted secrets never detected | code §5 |
| 27 | P2 | commit-quality.sh:60 | `${VAR,,}` requires bash 4 — "bad substitution" on stock macOS /bin/bash 3.2 | code §5 |
| 28 | P2 | src/security/path_guard.py:70 | Relative symlink resolved against cwd instead of link dir — wrong verdicts both ways | code §8 |
| 29 | P2 | suggest-compact.sh:23-34 | mkdir mutex with no stale-lock recovery — one crash freezes the counter forever; `date -r` GNU-only → daily reset never fires on macOS | code §5 |
| 30 | P2 | install.sh:306-337 | sed templating breaks on `\|`/`&` in commands — corrupts output mid-install and triggers the destructive trap | code §3 |
| 31 | P2 | install.sh:399-413 | Epilogue hardcodes false counts ("37 commands"; actual 52) while ignoring computed variables | DX-6 |
| 32 | P2 | install.sh (piped) | curl\|bash: empty BASH_SOURCE → cwd as SCRIPT_DIR → cp fails → ERR trap deletes `.claude`; `read` eats the piped script | code §3 |
| 33 | P2 | execute-json-ops.py:68-72 | atomic_write leaves files with mkstemp's 0600 mode — silent permission change on every edit | code §7 |
| 34 | P2 | execute-json-ops.py:101 | Windows path: lock is O_CREAT\|O_TRUNC (always succeeds) — concurrent executors interleave backups; unlink-after-flock race on Unix | code §7 |
| 35 | P2 | config-protection.sh:77 | Creating a brand-new pyproject.toml is blocked unconditionally (existence check precedes exemption) | code §5 |
| 36 | P2 | block-no-verify.sh:32 | Matches `--no-verify` anywhere — commit messages and `npm publish --no-verify` blocked; `git -c core.hooksPath=` bypasses it entirely | code §5, sec §3.2 |
| 37 | P2 | src/cli/main.py:124-138 | doctor thresholds (≥9/≥8/≥27) vs reality (28/52/73) — half-broken installs pass | code §9, DX-14 |
| 38 | P2 | format-typecheck.sh:29-42 | Reconstructs "edited files" by regex-scraping bash-command logs — Edit/Write invisible; greps count as edits | code §5 |
| 39 | P2 | cost-tracker.sh:26,37 | Counts log lines never written (cascade of #9) — TOOL_CALLS always 0, summary never prints | code §2 |
| 40 | P2 | templates/mcp/mcp-settings.json | `npx -y @latest` ×5 + filesystem `--allow-write .` — unpinned RCE by design on --with-mcp | sec §6 |
| 41 | P2 | validate-config-json.py:5 vs epilog | Docstring says 26 guards, epilog 29, guards 15/27/28 don't exist — numbering fiction | code §7 |
| 42 | P2 | validate-config-json.py:458 | Legacy conversion `file_op['path']` unguarded — malformed legacy config → raw traceback | code §7 |
| 43 | P2 | reviewer.md vs /review command | Two decision taxonomies (APPROVED/CONDITIONAL/REJECTED vs +REVISE) — output format is a coin flip; /refine parses one of them | ai §3.4 |
| 44 | P2 | golden-rule vs loop-start/planner/pipeline | "Never edit without approval" vs autonomous loops and no-human-gate pipeline — models resolve it unpredictably | ai §3.3 |
| 45 | P2 | agentMapping (skills-registry.json) | Contains `loop-start`/`opensource` (commands, not agents) and skill `i18n-workflow` that doesn't exist | ai §6.8 |
| 46 | P2 | templates/generic/CLAUDE.md | Instructs `/generate-ops`, `/validate-ops`, `/execute-ops` — none exist as commands | ai §6.8 |
| 47 | P2 | file-guard.sh:94-97 | Blocks all `*.pem`/`*.key`/`*.crt` by extension with no allowlist — `public.pem`, fixtures false-positive; also never wired | code §6, sec §3.3 |
| 48 | P2 | validate vs execute edit semantics | Validator checks find-patterns against original file; executor applies sequentially — partial-application disagreement; dry-run differs from real run | code §7 |
| 49 | P2 | session-start.sh:77 + context auto-load | Unquoted `basename $(pwd)`; prints unsanitized session-context.md into the transcript — injection vector the scanner never sees | code §5 |
| 50 | P3 | SECURITY.md | Supported-versions table says 1.x only — the current 2.0.0 release is formally unsupported by its own policy | docs §4 |

---

## 5. Top 50 Refactors (ranked by leverage)

1. **Manifest-driven everything:** `claudekit.manifest.json` consumed by install/doctor/CI/docs — makes the drift-bug class impossible [arch F-17]
2. Fix packaging: build_meta + `src/claudekit/` rename + single version + optional-deps extras [code refactor #1]
3. Single hook dispatcher per event: one stdin read, one python parse, correct exit-2 semantics [code #2, perf §7.1]
4. Wire-or-delete `src/security/`; ops scripts import it; expose `claudekit check-command` [code #3, sec §1]
5. install.sh → staging-dir transaction + settings.json install + manifest write + honest epilogue [code #4]
6. Move assets into `src/claudekit/assets/`; `claudekit init` installs from package resources; install.sh becomes a bootstrap [arch F-3, §4.1]
7. One canonical ops-file naming pattern in a shared lib used by all hooks and docs [code #5]
8. Operations scripts → importable package (`python3 -m claudekit.ops …`): kills sys.path hacks, dedupes path validation, CLI imports instead of shelling [code #6]
9. Delete `templates/{skills,commands,hooks,modes}` after merging diverged files; `.claude/` is the only asset tree [arch F-11/F-16]
10. Registry-authoritative agent↔skill wiring: generate "Mandatory Skill Loading" sections; validate agentMapping keys [arch F-13]
11. Generate docs counts/tables from frontmatter+registry (`gen-docs.py`) + drift CI [arch F-14, docs §9]
12. Consolidate agents 30 → ~20 per the ai-review verdict table (merges listed in improvement #59-60) [ai §1]
13. Consolidate skills 73 → ~60 (loop pair, verification pair, token/context quintet, onboarding, dependency clusters) [ai §6.9]
14. Commands to ≤40-line wrappers; procedures live in exactly one skill; tool-needing skills become agents [arch F-19]
15. Deduplicate four-layer prompt content to canonical `_shared/` homes (~30–40% corpus cut) [ai §5.3]
16. Skill-boot diet: ≤2 mandatory loads/agent + inline operating-rules digests (Offender #3 rewrite) [ai §5.2]
17. `ck update`/`uninstall`/`diff` on the hash manifest; managed vs user split on disk (`.claude/claudekit/` vs `local/`) [arch F-21]
18. Extract `.claude/hooks/lib.sh` — kill 10+ copy-pasted log()/config/extractor blocks (already diverged) [code §5]
19. Structured review.json/verify.json with schemas; gate /implement mechanically [missing #8]
20. Reviewer/verifier rewrite: calibration anchors, machine output contract, arithmetic validation (Offender #5) [ai §4.1]
21. using-superpowers rewrite: conditional trigger table replacing absolutism (Offender #4) [ai §3.6]
22. golden-rule rewrite around approval modes (interactive/pipeline/autonomous) [ai §3.3]
23. Replace nested `claude -p` with native subagent invocation; one INVOCATION.md source of truth [arch F-10, ai §2.2]
24. New non-deprecated `.claude/claudekit.json` for project commands; schema validated by doctor; retire config.json's dual life [arch F-15]
25. doctor rewritten against the manifest: exact counts, settings.json↔disk consistency, `--strict`, `--fix` [code #8, DX-15]
26. In-process CLI test rewrite (subprocess → import); testable `main(argv)` [testing]
27. Behavioral test pyramid: 70% unit / 20% integration / 10% asset-golden; prune existence theater [testing]
28. Eval runner + golden suites for the 5 core agents; nightly CI [missing #3]
29. CI proves the product: wheel → install → init fixture → doctor --strict → ops round-trip → exact counts [arch §4.2.6]
30. `templates/` → `languages/` (config.env + CLAUDE.md + detect keys); language add = one directory [arch F-16/F-22]
31. `ck new skill|agent|command` scaffolder; `ck lint` for consumer assets [arch F-22, missing #4]
32. Skill catalog tiering + registry out of the model-visible path (~7K tokens/session) [perf §6]
33. Type hints + frozen dataclasses (`ValidationResult`, `Operation`, `CheckResult`); mypy in CI [code #7]
34. pathlib standardization; `Path.is_relative_to()` replaces `startswith(cwd + os.sep)` in three files [code §12.5]
35. logging framework in ops scripts (print → logging; --verbose/-q); hooks log parse failures instead of 2>/dev/null [code §12.6]
36. CodeManifest fossil cleanup: lock file → `.claude/.claudekit.lock`, gitignore fixes, version alignment [arch F-8]
37. Asset version frontmatter (`version:` + `kit:`) + migrations registry for breaking changes [missing #5]
38. Consumer GitHub Action (composite): lint / validate-ops / eval modes [missing #6]
39. ClaudeKit MCP server exposing validate/execute/rollback/list-backups as tools [missing #10]
40. Real cost analytics from Claude Code transcripts/OTEL instead of log-line counting; `ck cost` [missing #7]
41. Sandbox profile pack: devcontainer + interactive/gated/autonomous settings presets [missing #9]
42. Wire loop-operator mechanically (state/loop.json + Stop-hook stagnation check) [ai §6.6]
43. Coordinator slim-down 60%: keep routing tables, delete duplicated pipeline diagrams; 16 pipelines → ~6 [ai §1, §6.4]
44. Fix revision-budget accounting (3× plan + 2× verify vs "max 3" promise) [ai §6.4/A22]
45. Verifier split: mechanical checks on Haiku, judgment on Sonnet — or strip judgment criteria [ai §4.2]
46. explore agent 410 → ~120 lines; methodology moves to the existing search-first skill [ai §1]
47. Restore-backup cleanup: extract fail() helper (5× copy-paste), sort by manifest timestamp not name [code §7]
48. CLI polish: NO_COLOR/isatty, dead imports, collapsed rollback branches, `config set`, `--json` everywhere [code §9, DX §2]
49. README restructure to the ≤400-line outline; reference pages generated; docs IA per docs-review §9 [docs §9-10]
50. i18n strategy: translated overview + links, synced per release via /translate in the release checklist [docs §6]

---

## 6. Top 25 Missing Features

1. **Claude Code plugin/marketplace packaging** (`.claude-plugin/plugin.json`) — the native channel for exactly this artifact type [missing #1, P0]
2. **Update/sync mechanism** (`ck update`, install manifest, three-way merge) [missing #2, P0]
3. **Eval framework with runner + golden tests + CI** for the 30 agents/73 skills [missing #3, P0–P1]
4. **`ck lint`** for prompt/asset authoring (frontmatter schema, token budgets, dead refs, trigger collisions) [missing #4, P1]
5. **Prompt/asset versioning** (frontmatter `version:`, per-asset diffability) [missing #5, P1]
6. **Consumer GitHub Action** (validate ops.json / lint .claude/ / smoke evals in user CI) [missing #6, P1]
7. **Versioned asset migrations** (`migrations/`, `ck migrate-config`) — the ops schema already drifted once [missing #7, P2]
8. **Structured review/verify verdicts** (review.json schema; mechanical 90/100 gate) [missing #11, P2]
9. **Real cost/token analytics** from transcripts/OTEL (`ck cost --by agent`) — current tracker guesses from log lines [missing #8, P2]
10. **Sandbox execution profiles** (devcontainer + deny-by-default settings for autonomous loops) [missing #13, P2]
11. **ClaudeKit MCP server** (ops engine as MCP tools — stable contract, wider audience) [missing #10, P2]
12. **Deterministic SAST wiring** (semgrep/gitleaks configs called by hooks; reproducible results) [missing #14, P2]
13. **Durable project-memory contract** (decisions/, learned-patterns/ that agents write automatically) [missing #12, P2]
14. **Context measurement tooling** (measure actual context composition; prune by relevance; substantiate the 85% claim) [missing #15, P2]
15. **Windows-native support** (Python CLI absorbs installer/hook duties) [missing #20, P2]
16. **`ck uninstall`** (remove .claude/, revert .gitignore) [DX §2]
17. **`ck doctor --fix`** (chmod hooks, add gitignore entries, repair wiring) [DX §2]
18. **`ck config set`** (config command advertises edit; only reads) [DX §2]
19. **`/quick-fix` fast path** — one-op ops.json without full pipeline ceremony [ai §6.3]
20. **Init wizard** (3-question CLAUDE.project.md/CONSTITUTION fill; --no-wizard for CI) [DX §6]
21. **`ck trace`** — render plan→review→implement→verify handoffs + hook log as a timeline [missing #16, P3]
22. **`ck status --html`** static report (installed assets, last runs, backups, eval pass rate) [missing #17, P3]
23. **OTEL presets** (opt-in templates/telemetry/ with env config + local collector compose) [missing #9, P3]
24. **Language scaffolding** (`detect` keys per language dir; adding a language = one directory) [arch F-22]
25. **Homebrew tap / npx shim** post-PyPI distribution polish [oss #14, P3]

---

## 7. Recommended Architecture

(Condensed from architecture-review §4 — the authoritative version.)

**Core decision:** *the manifest is the source of truth, and one installer consumes it.* ClaudeKit is a prompt-asset monorepo; stop pretending it's primarily a Python package and instead make the Python package the delivery vehicle for the assets.

1. **One canonical asset tree** (`.claude/`, packaged as `claudekit/assets/`). Optionality (mcp, i18n, security-hooks) is a manifest flag, never a second directory. `templates/` shrinks to `languages/`.
2. **`claudekit.manifest.json` drives everything:** install, update, doctor, CI exact-counts, generated docs. A component not in the manifest does not ship.
3. **Proper package:** `src/claudekit/{cli, installer, ops, security, assets}` — ops and security importable *and* vendored; the CLI imports instead of shelling out; install.sh becomes a thin bootstrap (`pipx install claudekit` or pure-bash fallback).
4. **Managed vs user split in target projects:** `.claude/claudekit/` (overwritable, hash-manifested) vs `.claude/local/` (never touched) — enabling a safe `ck update` and making `--force` non-destructive.
5. **Generated, never hand-written:** doc counts, agent skill lists (from the registry), install banners.
6. **Thin commands, single-home procedures:** commands ≤40 lines; each procedure lives in exactly one skill; anything needing tools is an agent.
7. **CI proves the product:** build wheel → install → init fixture → doctor --strict → ops validate/execute/rollback round-trip → exact counts → eval smoke.
8. **Protect the crown jewels during migration:** the operations engine's behavior stays bit-for-bit (wrap in tests first); the prompt corpus migration is pure relocation + deduplication.

Migration runs in 4 shippable increments (stop the bleeding → single source of truth → real package → lifecycle & curation) — see architecture-review §4.3 and `roadmap.md`.

## 8. Recommended Repository Structure

```
claudekit/
├── pyproject.toml                  # hatchling/build_meta; THE version
├── claudekit.manifest.json         # components, profiles, counts — drives everything
├── install.sh                      # thin bootstrap (pipx install || pure-bash fallback)
├── .claude-plugin/                 # plugin.json + marketplace.json (native channel)
├── src/claudekit/
│   ├── cli/                        # init, update, uninstall, doctor(--fix/--strict),
│   │                               #   ops {validate,execute,rollback}, list, config get/set,
│   │                               #   lint, eval, new (scaffolder), version
│   ├── installer/                  # manifest-driven install/update engine
│   ├── ops/                        # validate / execute / restore / shared (importable + vendored)
│   ├── security/                   # CommandValidator/PathGuard — actually imported by ops + hooks
│   ├── evals/                      # runner + assertion engine
│   └── assets/                     # canonical .claude tree, packaged into the wheel
│       ├── agents/ (~20)  commands/ (~28)  skills/ (~60)  modes/  hooks/ (+lib.sh, dispatch.sh)
│       ├── settings.json           # shipped, merged non-destructively
│       ├── mcp/                    # pinned server config (optional component)
│       └── local/                  # CLAUDE.template.md, CONSTITUTION.template.md
├── languages/                      # ex-templates/<lang>: config.env + CLAUDE.md + detect keys
├── evals/                          # suites/ fixtures/ golden/ results/
├── schemas/                        # operations, review, verify, claudekit.json, plugin
├── scripts/                        # gen-docs.py, gen-agent-skills.py, context-audit.py, dup-check.py
├── examples/                       # runnable mini-apps + transcripts (double as eval fixtures)
├── docs/                           # getting-started/ guides/ reference/(generated) architecture/
├── i18n/                           # synced overview translations, linked from README
├── tests/                          # behavioral unit / integration / asset-golden pyramid
└── .github/                        # honest CI, release-please, SHA-pinned actions, community files

# Installed layout in a target project:
.claude/
├── claudekit/                      # managed (hash manifest inside) — safe to update
├── local/                          # user-owned — never touched
├── settings.json                   # merged, never clobbered
└── plans/                          # runtime artifacts (gitignored)
```

## 9. Future Vision (12–24 Months)

See `roadmap.md` §3 for detail. Headlines: **marketplace-first distribution** (plugin as the reference constitutional-workflow kit, with sub-plugin ecosystem gated by lint + evals); **provable quality gates** (published nightly eval dashboards; the first prompt kit with real CI for prompts); **ClaudeKit MCP server** (ops engine as tools, beyond Claude Code); **real observability** (`ck cost`, `ck trace` from actual transcript/OTEL data); **cross-platform** (Python dispatcher replaces bash hooks; native Windows); **contained autonomy** (mechanically-wired loop supervision + mandatory sandbox profiles + risk-based Santa/GAN escalation); **team features** (org marketplaces, shared constitutions, review-score history as a quality metric).

---

## 10. Index of Review Documents

| Document | Scope | Score |
|---|---|---|
| [project-overview.md](project-overview.md) | Vision, system map, workflows, distribution model | — |
| [architecture-review.md](architecture-review.md) | Packaging, boundaries, duplication, config, extension model; target architecture | 48 (derived) |
| [code-review.md](code-review.md) | All executable code; top bugs & refactors | 54 |
| [ai-review.md](ai-review.md) | Agents, commands, skills, hooks, orchestration; instruction conflicts | AI Arch 62 / Prompt 55 / Context 45 / Agent Quality 65 (derived) |
| [developer-experience.md](developer-experience.md) | New-user journey, installer, CLI UX | 54 (CLI sub-score 40, derived) |
| [documentation-review.md](documentation-review.md) | README, changelog, docs/, examples, i18n | 47 |
| [missing-features.md](missing-features.md) | Gap matrix vs product identity; design sketches | Feature Completeness 58 |
| [oss-excellence.md](oss-excellence.md) | Hygiene checklist, release readiness, 30/60/90 plan | 44 |
| [testing-review.md](testing-review.md) | Suite execution, coverage, CI matrix, missing tests | 42 |
| [security-review.md](security-review.md) | Threat model, hooks, prompt-injection, supply chain | 32 |
| [performance-review.md](performance-review.md) | Token economy, hook latency, CLI/install speed | 68 |
| [roadmap.md](roadmap.md) | v2.1 / v3.0 / vision / breaking changes / migration / debt / priority table | — |
| [tasks/](tasks/) | 14 implementation-ready task files (001–014) | — |

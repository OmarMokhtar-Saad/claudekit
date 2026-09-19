---
source: https://llm-wiki.net/
retrieval_date: 2026-09-06
retrieval_method: WebFetch + WebSearch
---

# Research Report: llm-wiki.net

## 1. Site Analysis: What It Is, Who Runs It, How Current

**Project**: LLM Wiki — a set of Markdown-based commands + architecture that turns LLM coding agents (Claude Code, OpenAI Codex, OpenCode, Pi) into research engines and append-only knowledge bases.

**Author/Maintainer**: nvk; MIT-licensed; hosted as both SaaS documentation site and open-source GitHub repo ([nvk/llm-wiki](https://github.com/nvk/llm-wiki)).

**Trustworthiness**: High. This is operational software (not marketing copy or aggregator):
- Explicitly versioned (v0.24.3 at last check)
- Distilled from real multi-agent research workflows
- Emphasizes *transparency over marketing*: contradictions and unresolved states are first-class, audit failures escalate to research, not hidden
- Design is anti-SaaS: "plain Markdown you own," zero runtime dependencies, local-first architecture
- Security model is honest (allowlist/bounds, not zero-trust claims)

**Maturity**: Mature for a 2024–2026 system. The site itself is a *static handbook* (not a blog chasing SEO), focused on precise command reference and architecture rather than marketing narrative.

---

## 2. Site Structure Map

| Section | URL Pattern | Content |
|---------|------------|---------|
| **Home** | `/` | Product overview, installation matrix (Claude Code, Codex, OpenCode, Pi, portable), feature checklist |
| **Chrome Extension** | `/chrome/` | Browser integration: bounded tab access via toolbar click, MCP Native Messaging allowlist, security model |
| **Adapters** | `/adapters/` | External integrations (Google Docs, Skill Factory): route→approve→verify pattern, `.llm-wiki-adapter.json` contract |
| **Technical Reference** | `/llms.txt` | Comprehensive markdown handbook: all commands, architecture, design rationale, FAQ |
| **Installation** | (in /llms.txt) | Platform-specific setup for 5+ agent platforms |
| **Commands** | (in /llms.txt) | Full reference for `/wiki:research`, `/wiki:ingest`, `/wiki:thesis`, `/wiki:query`, `/wiki:compile`, `/wiki:audit`, `/wiki:lint`, etc. |
| **GitHub Repo** | [nvk/llm-wiki](https://github.com/nvk/llm-wiki) | Source, plugins, skills reference, audit patterns in `references/audit.md` |

**Note on structure**: The site design avoids deep URL hierarchies; most docs live in `/llms.txt` (single markdown file) rather than scattered pages, making it portable and offline-friendly.

---

## 3. Concrete Techniques & Patterns Applicable to ClaudeKit

### 1. **Parallel Decomposition with Plan-Before-Dispatch**
**Pattern**: Research mode splits a query into 3–5 independent sub-questions, presents the plan for user confirmation, then dispatches all sub-agents in parallel, with sequential compilation afterward.

**Source**: `/llms.txt` — `/wiki:research --plan` command; GitHub repo workflow.

**How to apply to ClaudeKit**: 
- Extend `coordinator` agent to offer a "plan-only" gate before parallel fan-out. Currently ClaudeKit has planner → reviewer → implementer sequence; adding explicit decomposition visibility + composition gate (before execution) would let users refute splits before parallel work fires.
- Aligns with: Tier 3 multi-phase gate (already exists), but makes it visible in ops.json.

---

### 2. **Adversarial Audit: Seek Counter-Evidence, Never Confirmatory Only**
**Pattern**: Audit command runs *dual* queries: one attempting to prove a claim, one designed to *disprove* it. Findings classified as `supported`, `weakened`, `contradicted`, or `unresolved`.

**Source**: [`audit.md`](https://raw.githubusercontent.com/nvk/llm-wiki/master/plugins/llm-wiki/skills/wiki/references/audit.md) — "look for both corroborating evidence and counter-evidence."

**How to apply to ClaudeKit**:
- `code-reviewer` already does adversarial review; audit.md's *verdict taxonomy* (`weakened` vs `contradicted` vs `unresolved`) is stronger than APPROVE/BLOCK binary.
- Suggestion: add a fourth verdict type to review records: `CONDITIONAL` (supported but with named caveats), with promotion to `APPROVED` only after re-test.
- Affects: `review-record.py` schema + reviewer agent frontmatter.

---

### 3. **Dependency Graph + Staleness Detection**
**Pattern**: Audit recursively traces source chains: if an output depends on article X, and article X was last refreshed 90 days ago in a volatile topic, escalate to re-research.

**Source**: Audit patterns; `topics/.archive/` + `topics/` structure.

**How to apply to ClaudeKit**:
- ClaudeKit tracks plan→execution provenance in `.claude/plans/` + ops.json. Current state: no auto-staleness detector.
- Suggestion: add a `.claude/ops-metadata.json` log with (op_id, timestamp, file_set_hash). Before executing a queued ops.json, check if any input files are stale (>N days, volatile topic).
- Affects: `check-context-floor.py` → new gate `check-ops-staleness.py`.

---

### 4. **Route→Approve→Verify for External Modifications**
**Pattern**: Adapters enforce three gates: (1) match intent to supported ops, (2) validate changes against exact resource + revision, (3) read-back verify before confirming.

**Source**: `/adapters/` — "Exact or explicit routing," "Scoped roots," "Verified artifacts."

**How to apply to ClaudeKit**:
- ClaudeKit's ops.json already does this: an operation names its inputs, the implementer validates inputs exist, executes, then verification gate reads back outcomes.
- Current: verification is optional (via `verifier` agent, user-gated).
- Suggestion: make verification *mandatory* for high-risk ops (security-relevant, >3 files touched, public API). Require a bounded read-back assertion in ops.json (e.g., `verify_assertion: "file X contains Y"`).
- Affects: ops.json schema, implementer execution loop, verifier agent routing.

---

### 5. **Thesis-Driven Research: Claim→Evidence→Verdict**
**Pattern**: `/wiki:thesis "<claim>"` investigates a specific claim, splitting it into 3–5 research paths (academic, technical, applied, news, contrarian), then synthesizes to answer "is this supported, weakened, contradicted, or unresolved?"

**Source**: `/wiki:research --mode thesis` command; compilation synthesis.

**How to apply to ClaudeKit**:
- ClaudeKit's `planner` decomposes tasks; no explicit claim-investigation mode.
- Suggestion: add a `/ck thesis` command for architecture disputes (e.g., "are hooks safer than ops.json dispatch?" → 5 sub-questions → 5 parallel research agents → audited verdict).
- Affects: CLI commands, planner role routing.

---

### 6. **Explicit "Unresolved" as First-Class Verdict**
**Pattern**: Audit refuses to collapse conflicting evidence into false confidence; instead reports `unresolved` with the evidence split named.

**Source**: Audit patterns; design philosophy: "unresolved is better than false confidence."

**How to apply to ClaudeKit**:
- Currently: review gates are APPROVE or BLOCK; if evidence is mixed, consensus is unclear.
- Suggestion: add `UNRESOLVED` verdict type to review-record.py. Escalation rule: if ≥2 reviewers vote UNRESOLVED on the same code change, route to `code-reviewer` (fresh pair) with both previous verdicts shown.
- Affects: review-record.py schema, reviewer agent scoring logic (≥90/100 never reached if UNRESOLVED).

---

### 7. **Topic Archive + Searchable History**
**Pattern**: Inactive wikis move to `topics/.archive/` but remain queryable; default queries skip archive unless explicitly included.

**Source**: Hub-and-spoke architecture; `topics/`, `.archive/` structure.

**How to apply to ClaudeKit**:
- ClaudeKit stores old plans, reviewed code, agent reports in `.claude/plans/`, `.claude/reports/`; no explicit archive boundary.
- Suggestion: add `.claude/archive/` with a `.index` file listing archived ops, reviews, and the reason (e.g., "superseded by plan-Y," "release-tagged"). Searches (via grep in reports/) skip archive by default.
- Affects: directory structure, agent context-building scripts.

---

### 8. **Session Capture as Operational Memory (Not Transcript)**
**Pattern**: Hooks write *redacted* JSONL (harness metadata, git context, small events) + Markdown digests under `.sessions/` *by default*; full transcripts are not stored. Session rehydrate returns compact context for next agent turn.

**Source**: Session capture mechanics; `.sessions/`, `.sessions/feedback/` directories.

**How to apply to ClaudeKit**:
- ClaudeKit's `reflection` receipt writes to `.claude/hooks/` (harness metadata) but no compact rehydration.
- Suggestion: add `.claude/sessions/<session-id>/context.md` with: last plan name, last verifier verdict, open issues from previous review round, quoted next-steps. Agent frontmatter: auto-include session context if available.
- Affects: `hooks/post-hook.sh`, agent context-building.

---

### 9. **Feedback Promotion: Candidate → Durable Knowledge**
**Pattern**: Feedback is *candidate* memory under `.sessions/feedback/`. Explicit `promote` moves high-signal corrections, preferences, approvals into topic wikis (raw/notes/), making them durable.

**Source**: Feedback curation; session promote/feedback promote commands.

**How to apply to ClaudeKit**:
- ClaudeKit stores agent improvements (skills, patterns, technique discoveries) in `.claude/agents/` but no explicit candidate→approved workflow.
- Suggestion: add `.claude/feedback/` directory. After a code-reviewer round, interesting findings (e.g., "this pattern in ops enforcement is more flexible than we thought") are captured as candidates. Weekly: a human or the `maintainer` agent promotes high-signal feedback to `.ai/KNOWLEDGE_BASE.md` or `.ai/PATTERNS.md`.
- Affects: new workflow, agent coordination.

---

### 10. **Dual-Linking: Obsidian + Markdown**
**Pattern**: Every wiki cross-reference uses both Obsidian wikilinks (`[[name]]`) and standard markdown, making content accessible in multiple tools (Obsidian, GitHub, plain editors).

**Source**: Dual linking design principle; hub-and-spoke article structure.

**How to apply to ClaudeKit**:
- ClaudeKit docs live in `docs/` (generated) and `.ai/` (maintainer-facing). Cross-refs are markdown URLs only.
- Suggestion: in `.ai/` docs, add wikilinks for internal cross-refs where Obsidian is commonly used (e.g., `.ai/KNOWLEDGE_BASE.md` → `[[REVIEW_GUIDE]]` + `[REVIEW_GUIDE](REVIEW_GUIDE.md)`). Low friction; backward-compatible.
- Affects: `.ai/` doc format; generates no code changes.

---

### 11. **Compile-to-Notes Pattern: Artifact Sealing + Semantic Privacy**
**Pattern**: Compilation exports comprehensive project handoffs with deterministic sealing, explicit omissions, semantic privacy minimization (e.g., no PII in artifact), and attested overrides.

**Source**: Artifact generation patterns; `/wiki:output` command; "dry-run-first create and refresh."

**How to apply to ClaudeKit**:
- ClaudeKit's `implementer` writes files and archives to PyPI; no semantic privacy gate.
- Suggestion: for release ops (publish to PyPI, ship to fleet), add a dry-run step that generates `RELEASE_MANIFEST.md` with (files changed, version, breaking changes, omissions). Manual review + sign-off before execution.
- Affects: `coordinator` agent role (add release orchestration), ops.json schema (dry-run field).

---

### 12. **Evidence Traceability: Source Chain in Every Output**
**Pattern**: All wiki outputs list their source articles, sections, and exact URLs. If an output uses 3 sources and one is stale, that dependency is recorded and auditable.

**Source**: Audit trails; artifact generation; `.sessions/` event logging.

**How to apply to ClaudeKit**:
- ClaudeKit's ops.json execution logs are bash stderr/stdout; no machine-readable provenance.
- Suggestion: implementer writes each operation outcome as JSON with (op_id, timestamp, files_affected, outcome, source_ops). Verifier and audits read this `.claude/ops-log.jsonl` to trace why a change was made.
- Affects: implementer script, verifier agent, new gate `check-ops-provenance.py`.

---

### 13. **Three-Pass Audit: Librarian + Drift + Provenance + Research**
**Pattern**: A single audit call internally runs: (1) librarian pass (consistency), (2) drift detection (staleness), (3) provenance tracing (source validity), (4) escalation research (if findings conflict).

**Source**: Audit multi-pass architecture; `audit.md` techniques.

**How to apply to ClaudeKit**:
- ClaudeKit has hook validators (linting), verifier agent (logic), but no multi-pass audit.
- Suggestion: add `ck audit` command that runs: (1) `python3 scripts/gen-docs.py --check` (docs-drift), (2) `mypy` (type consistency), (3) `python3 scripts/check-ops-provenance.py` (ops traceability), (4) `pytest` (behavior regression). Output: `AUDIT_REPORT.md` with all four passes, final verdict (PASS/AUDIT_FAILED/INVESTIGATE).
- Affects: new CLI command, new audit scripts.

---

### 14. **Local-First, Zero Runtime Dependencies**
**Pattern**: llm-wiki ships as static markdown files, bash scripts, and JSON configs. No Node, Python runtime, or cloud service required. Agents just execute commands and read/write files.

**Source**: Product design philosophy; "plain Markdown you own."

**How to apply to ClaudeKit**:
- ClaudeKit already follows this (Python stdlib-only, Bash 3.2/macOS-safe, no npm/pip runtime).
- Current rule: "zero runtime dependencies" — this is already enforced via hard rule #8.
- Observation: both systems *converge* on this principle. Keep it.

---

### 15. **Minimal Contracts: `.llm-wiki-adapter.json` + MCP**
**Pattern**: External integrations (adapters) are governed by a single config file (`.llm-wiki-adapter.json`) with: operations supported, input schema, output schema, permission boundaries.

**Source**: Adapters architecture; MCP Native Messaging model.

**How to apply to ClaudeKit**:
- ClaudeKit's agents are coordinated via `.claude/agents/*/INVOCATION.md` + `--allowedTools`.
- Suggestion: consolidate agent surface into a single `.claude/agents/_shared/API.json` with: for each role, (operations, tools, parameter schema, permission floor). Makes agent authoring more disciplined.
- Affects: agent discovery, compliance validation in planner + reviewer.

---

## 4. Contradictions with ClaudeKit's Current Practices

None major. llm-wiki.net and ClaudeKit are *complementary*, not competing:

| Practice | llm-wiki.net | ClaudeKit | Alignment |
|----------|-------|-----------|-----------|
| **Ops indirection** | Adapters route→approve→verify | ops.json + implementer | Exact same pattern; llm-wiki just applies it to external services |
| **Scoring gates** | Audit verdict: supported/weakened/contradicted/unresolved | Review verdict: APPROVED/BLOCK | llm-wiki's 4-class taxonomy is richer; ClaudeKit's binary is simpler but could adopt it |
| **Hook enforcement** | Session capture writes JSONL to `.sessions/` | Pre/PostToolUse hooks write to `.claude/hooks/` | Both use hooks; llm-wiki adds compaction (rehydrate); ClaudeKit doesn't |
| **Agent fan-out** | Research dispatches N parallel agents, synthesizes sequentially | `coordinator` orchestrates parallel phase → serial phase | Identical pattern |
| **Permissioning** | Adapters use scoped roots + explicit gesture (tab click) | `--allowedTools` + INVOCATION.md scoping | Both restrictive; llm-wiki adds visual revocability (UI) |

**No contradictions found.** The only asymmetry: llm-wiki invests in *user-facing feedback loops* (toolbar click, visual markers) and *compact rehydration* for ergonomics; ClaudeKit focuses on *operator-facing auditing* (code review, ops traceability).

---

## 5. What llm-wiki.net Does NOT Cover

**Major gaps relative to ClaudeKit's scope**:

1. **Security enforcement as blocking hooks** — llm-wiki assumes benign agents; ClaudeKit has PreToolUse hooks that exit 2 (fail closed). llm-wiki would benefit from this for high-risk integrations.

2. **Multi-round code review with iterative verdicts** — llm-wiki's audit is read-only; ClaudeKit's reviewer+code-reviewer loop allows multiple rounds with verdict convergence. llm-wiki could adopt this for artifact refinement.

3. **Model capability-tier routing** — llm-wiki treats agents as interchangeable; ClaudeKit routes by tier (most-capable/balanced/fast). For parallel research, adaptive tier selection (use most-capable for edge cases, fast for breadth) would improve cost.

4. **Plan→Review→Execute pipeline with numeric gates** — llm-wiki does research + compile; ClaudeKit adds scored review gates (≥90 plan, ≥80 verify). llm-wiki would need this for shipping artifacts under compliance.

5. **Regression test harness** — llm-wiki is a research/knowledge system; ClaudeKit runs `pytest` on every ops.json. llm-wiki doesn't address continuous artifact quality.

6. **Permission model for edits** — llm-wiki's `external_directory` permission is all-or-nothing; ClaudeKit has fine-grained scope (which files, which operations). llm-wiki would benefit from this for collaborative research.

7. **Deterministic versioning + monotonic release** — ClaudeKit enforces single version source + CI gate; llm-wiki has no explicit release strategy.

---

## Conclusion

**llm-wiki.net is a mature, trustworthy system** focused on *research engines and knowledge compilation for multi-agent LLM systems*. It is:

- **Operationally grounded**: real tools, real workflows, not marketing.
- **Philosophically aligned with ClaudeKit**: local-first, zero runtime deps, evidence-driven, hook-based, parallel dispatch + sequential synthesis.
- **Complementary, not overlapping**: llm-wiki handles knowledge/research; ClaudeKit handles orchestration/enforcement.
- **Rich in audit + feedback patterns** that ClaudeKit should adopt: unresolved verdicts, dual-query research, topic archives, session rehydration, feedback promotion.

**Recommended next actions**:
1. Adopt llm-wiki's 4-class audit verdict taxonomy in review-record.py.
2. Add session rehydration to `.claude/sessions/<id>/context.md`.
3. Implement `.claude/archive/` + `.index` for old plans/reviews.
4. Create `ck audit` command (multi-pass: docs-drift, types, provenance, regressions).
5. Explore capability-tier routing for llm-wiki's parallel research (would reduce cost on stable searches).

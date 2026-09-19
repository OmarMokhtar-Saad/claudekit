# A1 Skill Retrieval Feasibility Spike

**Retrieved: 2026-09-16**

**Question:** Can ClaudeKit's skill/command listing be trimmed so that BM25 retrieval could supply descriptions on demand — or is the token win illusory?

---

## 1. Current Measurement (2026-09-16)

| Source | Files | Chars | Notes |
|---|---:|---:|---|
| `.claude/skills/*/SKILL.md` | 81 | 11,564 | Up from 80 files (Sept 6) |
| `.claude/commands/*.md` | 57 | 5,046 | Stable from Sept 6 |
| **Total** | **138** | **16,610** | ≈ **4,152 tokens** (estimated at 4 chars/token) |

**Change since Sept 6:** +1 skill, +354 chars, +102 tokens. Measurement grows incrementally. At current `skillListingBudgetFraction: 0.03` (6,000 tokens), the listing consumes 69% of the budget with margin. However, this margin depends on the 200K context window assumption in the original measurement.

---

## 2. Claude Code Settings: The Load-Bearing Question

**Settings available in Claude Code:**
- `skillListingBudgetFraction` — Fraction of context window to allocate to skill listing (default: 0.01). Current repo setting: **0.03**.
- `skillListingMaxDescChars` — Max character count per skill's `description` + `when_to_use` (default: 1536). Current repo setting: **1536** (unchanged).

**No other listing-related settings exist.** There is no:
- "names-only mode"
- "description suppression" flag
- "custom formatting" option
- Way to reduce the listing below what Claude Code's algorithm produces

**Claude Code's documented behavior:** When the listing exceeds the budget, Claude Code "keeps skill names but drops descriptions for the least-used skills" (from skill-listing-budget-2026-09-06.md, citing code.claude.com/docs/en/settings-reference).

**Verdict on trimming:** Claude Code has exactly **one mechanical lever**: lower `skillListingBudgetFraction` so the algorithm drops more descriptions. But there is **no setting that produces a names-only listing by design**. Names appear as a fallback when descriptions are dropped; they are not the primary mode.

---

## 3. Hook Injection Mechanism: Can UserPromptSubmit Inject Context?

**Current ClaudeKit UserPromptSubmit hooks** (`.claude/settings.json` lines 54–72):
1. `pre-plan.sh` — Checks for duplicate plans; logs results; **does not output**
2. `injection-scan-gate.sh` — Scans prompt for injection patterns; exits with status only; **does not output**

**How hooks work:**
- **SessionStart** — stdout is documented as injected into context (evidence: session-start.sh prints project info, graph status, memory slice, and this text appears in the UI)
- **UserPromptSubmit** — Hooks receive the user's prompt as stdin; the adoption-candidates report claims "it can inject context" but does not specify the mechanism
- **PostToolUse** — Used for filtering/auditing (e.g., reflection-gate.py, post-tool-use.sh); stdout behavior undocumented

**Direct evidence:** The existing UserPromptSubmit hooks do not output anything. The pre-plan hook logs but does not stdout. The injection-scan-gate outputs warnings to stderr only (conditional, advisory).

**Claim in adoption-candidates report:** "ClaudeKit already registers `UserPromptSubmit` (2 hooks) — that is the mount point, and it can inject context." This is stated but not demonstrated. The report immediately flags the blocker: "injecting a recommendation list does not shrink the harness-generated listing, so the win is only real if the listing itself can be trimmed."

**Conclusion on injection:** UserPromptSubmit *may* support stdout injection (like SessionStart does), but this is not verified in this spike. **Critically, even if it does, the injection would add tokens on top of an unchanged listing.**

---

## 4. The Core Problem: Arithmetic, Not Mechanism

Assume:
- Claude Code listing = 16,610 chars ≈ 4,152 tokens (MEASURED)
- Injected BM25 recommendations = ~300 tokens (per moonlight-lupin report, top-6 skills at ~50 tokens each)
- Current `skillListingBudgetFraction: 0.03` = ~6,000 tokens allocated

**Scenario A (ILLUSORY — current state):**
- Listing: 4,152 tokens
- Budget: 6,000 tokens
- Headroom: ~1,848 tokens
- Injection: +300 tokens (sits in headroom, no loss)
- **Net win: 0 tokens** — the listing is already under budget; injection adds cost

**Scenario B (REAL — if names-only listing is achievable):**
- Listing (names only, hypothetical): ~500 tokens (names are 1–3 words each, ~80 skills × 6 chars avg)
- Budget: 6,000 tokens
- Headroom: ~5,500 tokens
- Injection: +300 tokens (sits in headroom)
- **Net win: ~3,650 tokens** — trimming saves more than injection costs

**Scenario C (PARTIAL — lower the budget, drop some descriptions anyway):**
- Set `skillListingBudgetFraction: 0.005` (~1,000 tokens for a 200K window)
- Claude Code drops descriptions for ~60% of skills (least-used)
- Listing with partial descriptions: ~2,000 tokens
- Injection: +300 tokens
- **Net cost: -1,300 tokens** — we pay 300 to inject what we dropped

---

## 5. The Verdict

**ILLUSORY — The token win does not exist under current conditions.**

**Detailed reasoning:**

1. **Listing cannot be trimmed by design.** Claude Code has no "names-only mode" setting. The only lever is `skillListingBudgetFraction`, which controls how aggressively Claude Code drops descriptions when budgeted space is exceeded. Lowering it drops descriptions, not names. Names appear *as residuals* when descriptions are dropped, not as the primary mode.

2. **Current listing is not over budget.** At 4,152 tokens against a 6,000-token budget (0.03 fraction), the listing fits with margin. Injecting recommendations adds 300 tokens to an allocation that already has ~1,848 tokens of headroom. There is no space being freed to inject into.

3. **Trimming requires deleting content.** The only way to achieve "names-only" is to:
   - Delete or truncate every `description` field in every SKILL.md and command .md, OR
   - Lobby Claude Code to add a names-only mode (out of scope)

   Deleting content is not a "retrieval optimization"—it is destructive. Descriptions serve human-readable documentation and are valuable.

4. **Injection does not reduce the listing.** Even if UserPromptSubmit hooks can inject context (unverified), injecting descriptions does not shrink the listing. Injected text adds to the model's context window; it does not replace the listing. The adoption-candidates report flags this exact trap: "injecting a recommendation list does not shrink the harness-generated listing."

5. **No retrieval precision baseline.** The moonlight-lupin source (BM25 with k1=1.5, b=0.75, top-6) is built on a lexical ranking with no published evaluation. Their own assessment: "no published retrieval metrics — the authors never validated effectiveness." Adopting unproven precision on the premise of a token win that is already illusory would be double speculation.

---

## 6. Why the Confusion Arose

The adoption-candidates report correctly identifies that the listed skills consume ~4,050 tokens and the old default budget was ~2,000 tokens (0.01 fraction). It raises the budget to 0.03 (6,000 tokens) to cover the measurement with margin. This is the right move.

However, it then proposes "trim the listing and inject descriptions" as if these are complementary. They are not:
- Trimming requires deleting content from SKILL.md files (destructive, out of scope for A1).
- Injecting adds tokens to the context window (additive, not reductive).
- The win would only be real if we could *replace* the listing with retrieval, not *supplement* it.

Confusing deletion with design-time control is a category error.

---

## 7. Constraints & Observations

- **No way to control listing format from settings.** Claude Code does not support names-only, descriptions-first, or custom layouts. The harness generates the listing; ClaudeKit cannot reshape it.

- **Current budget headroom is real.** At 4,152 tokens vs. 6,000 token budget, there is ~1,848 tokens of headroom. This is not abundant, but it is adequate to avoid the original problem (silent description drops).

- **Injection as "optional enhancement" is valid.** If UserPromptSubmit *can* inject context (unproven), injecting top-6 relevant skills as a convenience is not harmful—it just doesn't save tokens. It could improve discoverability but adds cost.

- **Deflation risk.** If more skills are added, the 4,152-token measurement will grow. At 15–20 additional skills per quarter (implied by recent growth), the budget will saturate within ~2–3 quarters without intervention.

---

## 8. Recommendation: Do Not Pursue A1 as Described

**A1 should drop to Tier C** unless:

1. **Concrete plan to trim the listing.** Proposed: Delete `description` fields from low-utility skills and use a hook to inject from a separate registry. This requires:
   - Audit which skills have descriptions read vs. not read (no usage data available)
   - Modify gen-docs.py to accept a configuration that allows empty descriptions
   - Build and maintain a BM25 index alongside the repo
   - Measure whether users lose discoverability as a result

   This is scope creep beyond "retrieval optimization." It is a *content redesign*.

2. **Proof that UserPromptSubmit can inject context.** The adoption-candidates report assumes this; it is not verified. A minimal PoC would write a simple hook that prints a test message, verify it appears in Claude Code's UI, and measure its token cost.

3. **Precision baseline for BM25.** Before adopting ranked retrieval, measure recall/precision over a corpus of real prompts (e.g., actual user queries from 10–20 sessions). Benchmark against the naive "all names in the listing" baseline. Require ≥85% precision for top-6 to justify the complexity.

---

## 9. Token-Win Deflation Plan (Safer Alternative)

Instead of retrieval, address token budget proactively:

1. **Monitor measurement quarterly.** Re-run the char count across skills + commands. Alert if growth exceeds 10% per quarter.

2. **Consolidate low-value descriptions.** Audit which skills have short, generic descriptions (e.g., "A skill for X") and standardize them to 50–100 chars (save ~2K chars across fleet).

3. **Shorten `when_to_use` pragmatically.** Most skills have no `when_to_use` clause (0 of 80 as of Sept 6). For skills that add one, keep it to ≤100 chars.

4. **Raise the budget incrementally, not preemptively.** The current 0.03 (6,000 tokens) covers the measurement. Only raise if the measurement justifies it.

These are **boring, safe, measurable** interventions. They avoid speculating on retrieval while addressing the real risk (budget saturation over time).

---

## 10. Summary for Decision-Maker

| Aspect | Finding |
|---|---|
| **Current measurement** | 138 assets, 16,610 chars ≈ 4,152 tokens |
| **Budget status** | 69% of 6,000-token allocation; headroom: ~1,848 tokens |
| **Trimming lever** | Does not exist in Claude Code. "Names-only mode" is a design fiction. |
| **Injection mechanism** | Likely possible (SessionStart proven; UserPromptSubmit unverified) but additive, not reductive. |
| **Token win** | **ILLUSORY** — Injecting 300 tokens to an already-budgeted listing yields zero net gain. |
| **PoC requirements** | Verify UserPromptSubmit injection + measure BM25 precision over real prompts (≥85% top-6). |
| **Recommendation** | Drop A1 to Tier C. Pursue safe, measurable quarterly monitoring and consolidation instead. |

**The honest outcome:** The token ceiling is real (4,152 tokens measured), but the proposed solution does not address it. Adopting BM25 would add complexity and cost without shrinking the listing. Recommend reframing as "optional UX enhancement" (improved discoverability) rather than "token optimization," and measure the precision cost before committing.

# Claude Code Usage Limits by Plan (August 2026)

**Date:** 2026-08-09  
**Question:** Individual Max subscription vs Enterprise/Team premium seats for heavy multi-agent implementation load—exact limits per plan.

---

## 1. Rolling 5-Hour Session Window Mechanics

**Baseline (Pro = 1x):**
- **Pro:** 1x baseline (~44,000 tokens estimated, unconfirmed per Anthropic)
- **Max 5x ($100/mo):** 5x Pro allowance per rolling 5-hour window
- **Max 20x ($200/mo):** 20x Pro allowance per rolling 5-hour window
- **Team Standard:** 1.25x Pro per rolling 5-hour window
- **Team Premium ($100/seat/mo):** 6.25x Pro per rolling 5-hour window
- **Enterprise Premium Seat:** Same as Team Premium (6.25x Pro)

**Key change (May 6, 2026):** All subscription limits were permanently doubled.

**Mechanics:** Window is account-level, rolling (timer starts at first message, resets after 5 hours), not clock-based.

---

## 2. Weekly Caps

**Critical distinction:**
- **Max 5x & Max 20x:** Rolling 5-hour window ONLY. **No weekly ceiling** documented.
- **Team Premium & Enterprise Premium Seats:** Rolling 5-hour window AND separate weekly caps:
  - One cap applies across all models
  - One cap applies specifically to Sonnet models only

**Exact weekly numbers:** NOT published by Anthropic. Users verify remaining capacity in Settings > Usage only.

---

## 3. Model Access & Model-Specific Limits

**Available models on paid plans (Claude Code):**
- Opus 4.6+ (all paid plans)
- Sonnet 5 (all paid plans)
- Fable 5 (Max, Team Premium, Enterprise Premium)

**Context window:** 1,000,000 tokens on Claude Code (Max, Team, Enterprise on Opus 4.6).

**Fable 5 burn rate:**
- Consumes ~**2x the usage tokens of Opus 4.8** against plan limits
- Limited to **50% of weekly usage** on Max and Team Premium (explicit cap)
- After June 23, 2026: Fable 5 exits plan limits entirely; bills at standard API rates ($10/M input, $50/M output) against pre-paid credits

---

## 4. Enterprise Admin Controls & Flexible Limits

**Team/Enterprise Premium Seat Management:**
- Admins assign standard (baseline) or premium seats per user
- Granular spending limits at org and per-user levels
- **"Additional usage at standard API rates"** configurable—administrators can enable overage billing while maintaining caps
- Usage analytics: acceptance rates, deployment patterns, real-time monitoring
- Compliance API: programmatic access to usage data for automated policy enforcement

**Overage model:** Once monthly API credits (included with subscription tier) expire, additional usage bills at standard API rates, not blocked.

---

## 5. Parallel Claude Code Sessions & Window Sharing

**Not explicitly documented**, but inferred from the window structure:
- The 5-hour rolling window is **account-level**, not per-session
- Multiple parallel Claude Code terminal sessions on the same account share a single 5-hour allowance
- Each session drains the same bucket; no session-specific isolation
- Programmatic usage (`claude -p`, Agent SDK, GitHub Actions) draws from the same account window + separate monthly credits

---

## Summary Table

| Plan | Per-Session Multiplier | Weekly Cap? | Fable 5? | Best For |
|------|------------------------|-------------|----------|----------|
| Pro | 1x (~44k tokens est.) | None documented | No | Baseline interactive |
| Max 5x | 5x | None | Yes (50% cap) | Heavy interactive, individual |
| Max 20x | 20x | None | Yes (50% cap) | Very heavy interactive, individual |
| Team Std | 1.25x | Yes (both-model + Sonnet) | No | Light team usage |
| Team Premium | 6.25x | Yes (both-model + Sonnet) | Yes (50% cap) | Medium team usage |
| Enterprise Premium Seat | 6.25x | Yes (both-model + Sonnet) | Yes (50% cap) | Medium team, managed budgets |

---

## Key Unknowns & Limitations

1. **No published token counts:** Anthropic publishes multipliers (1x, 5x, 20x, 1.25x, 6.25x) but no token equivalents. Exact capacity = Anthropic's discretionary choice; peak-hour throttling added in 2026.
2. **Weekly cap specifics:** Exact numbers for Team/Enterprise weekly limits not disclosed; observable via Settings > Usage only.
3. **Opus-specific limits:** No documented multiplier or burn-rate difference between Opus and Sonnet on same plan.
4. **Model context cost:** Whether 1M-token context window on Opus 4.6 Claude Code counts differently against rolling window limits is not documented.
5. **Decision support:** Use ANTHROPIC_API_KEY instead of OAuth subscription for per-token transparency if deploying large multi-agent fleets.

---

## Recommendation: Max vs Enterprise for Heavy Implementation

**Individual Max 20x ($200/mo):**
- 20x baseline, no weekly ceiling, Fable 5 available (50% cap)
- Simpler billing, no admin overhead
- Best if workload fits within single-seat allocation

**Enterprise Premium Seat ($100+/seat/mo, usually higher, org minimum 5-10 seats):**
- 6.25x baseline (lower than Max 20x), but with weekly caps and flexible overage billing at API rates
- Better for cost-predictability at organizational scale
- Admins enable overage billing → effectively unlimited at per-token cost once monthly credits exhaust
- Best for multiple agents or variable load (overage protection)

**Verdict:** For heavy multi-agent load with budget certainty, Enterprise Premium + overage billing is cheaper long-term if you expect to exceed 6.25x Max baseline. Max 20x wins for cost if workload stays within allowance.

---

## Sources

- [Build This Now — Claude Code Usage Limits 2026](https://www.buildthisnow.com/blog/models/claude-code-usage-limits-2026)
- [Jamie Lord — Claude Team Premium vs Max Plans](https://lord.technology/2026/03/28/claude-team-premium-vs-max-plans-usage-limits-pricing-and-which-to-choose.html)
- [Anthropic News — Claude Code and New Admin Controls](https://www.anthropic.com/news/claude-code-on-team-and-enterprise)
- [UsageBox — Fable 5 Usage Limits and Burn Rates](https://usagebox.com/articles/claude-fable-5-usage-limits-subscription-burn-2026)
- [TokenKarma — Anthropic Usage Limits Explained 2026](https://tokenkarma.app/blog/anthropic-usage-limits-explained-2026/)
- [Developers Digest — Claude Usage Limits With Fable 5](https://www.developersdigest.tech/blog/claude-usage-limits-fable-5-explained)

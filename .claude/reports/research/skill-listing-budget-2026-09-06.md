# Skill listing budget — primary sources and measurement

**Date:** 2026-09-06 · **Verified via context7 against code.claude.com** (not from model
memory). Recorded here so the settings change in `.claude/settings.json` can be re-checked
without re-running the research.

## Sources

**<https://code.claude.com/docs/en/settings-reference>**

> `skillListingBudgetFraction`: portion of the context window allocated for presenting
> available skills and their descriptions; defaults to `0.01` (1%); when the listing
> exceeds the cap, Claude Code keeps skill names but drops descriptions for the least-used
> skills.

> `skillListingMaxDescChars`: caps the character count of each skill's description and
> `when_to_use` text; default `1536`.

**<https://code.claude.com/docs/en/skills>**

> `description` and `when_to_use` ... combined text capped at 1,536 characters.

## Measurement (this repo, 2026-09-06)

Counting `description` + `when_to_use` from frontmatter, every file, no exemptions:

| Source | Files | Chars |
|---|---:|---:|
| `.claude/skills/*/SKILL.md` | 80 | 11,256 |
| `.claude/commands/*.md` | 57 | 4,942 |
| **Total** | **137** | **16,198** ≈ **4,050 tokens** |

No skill currently declares `when_to_use` (0 of 80), so today that column contributes
nothing — the measurement still reads it, because a skill that adds one must be charged
for it.

## The conclusion

At the documented default of `0.01`, the budget is **2,000 tokens** at a 200k context
window. The listing measures ~4,050 tokens — **roughly double the budget** — so Claude Code
has been silently dropping descriptions for the least-used skills. `0.03` (6,000 tokens)
covers the measurement with margin.

**Assumption, stated because it is not verified:** the 200,000-token context window. The
docs express the setting as a *fraction*, never in tokens, so any absolute token figure
here — including the 2,000-token default — depends on that assumption.

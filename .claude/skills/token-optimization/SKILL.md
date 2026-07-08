---
name: token-optimization
description: "Use when you need to reduce token consumption by 40-70% -- covers compression levels, abbreviated output, code-only responses, and efficient formatting techniques."
---

# Token Optimization

## Purpose

Minimize token usage in Claude Code interactions while preserving information quality. Applies three progressive compression levels to reduce cost and improve response speed.

---

## Compression Levels

### Level 1: Lean (40% reduction)

Activation: Default for all responses in token-efficient mode.

**Rules:**
- Eliminate filler words: just, simply, basically, actually, really, quite, very, definitely, certainly
- No pleasantries: "Sure!", "Great question!", "Happy to help!", "Absolutely!"
- No preambles: "Let me explain...", "Here's what I found...", "I'll walk you through..."
- No closing summaries or recaps
- No restating the question
- No transition phrases between sections
- Bullet points over paragraphs
- Tables over prose comparisons
- Single-line answers for simple questions

**Example:**

Before (87 tokens):
```
Sure! Let me help you with that. To reverse a list in Python, you have
several options. Here's what I'd recommend: you can use the slice notation
`lst[::-1]` which creates a new reversed list, or you can use the
`lst.reverse()` method which reverses in place. I hope that helps!
```

After (12 tokens):
```
`lst[::-1]` (new list) or `lst.reverse()` (in-place)
```

### Level 2: Compressed (60% reduction)

Activation: `/token-optimize level-2` or when context window exceeds 60%.

**Additional rules on top of Level 1:**
- Use standard abbreviations: fn, impl, cfg, dep, pkg, dir, env, param, ret, err, req, res, auth, db, msg, val, str, int, bool, arr, obj, ctx, ref, spec, doc, lib, util, init, exec
- Omit articles (a, an, the) where unambiguous
- Code-only responses -- no explanation unless logic is non-obvious
- File references: `path/file.ext:L42` format
- Error diagnosis: `Cause: [one line]\nFix: [code or one line]`
- Skip type annotations in explanations when inferable
- One example instead of multiple

**Example:**

Before:
```
The error is caused by a null reference exception in the authentication
module. The `user` variable is null because the database query returned
no results. To fix this, you should add a null check before accessing
the user properties.
```

After:
```
Cause: `user` is null -- db query returned empty
Fix: add null check before property access
```

### Level 3: Ultra-Compressed (70% reduction)

Activation: `/token-optimize level-3` or when context window exceeds 80%.

**Additional rules on top of Level 2:**
- Diff-only for code changes (no full file output)
- Symbol-heavy notation: `->` for returns/leads-to, `=>` for implies, `!` for not/negation, `&` for and, `|` for or, `~` for approximately, `@` for at/located
- No markdown headers -- use inline labels: `[cause]`, `[fix]`, `[note]`
- No code fences for single expressions
- Collapse multi-step instructions to semicolons: `step1; step2; step3`
- Numbers over words: `3` not `three`

**Example:**

Before:
```
## Root Cause
The authentication middleware is not checking for expired tokens.

## Steps to Fix
1. Open `src/middleware/auth.ts`
2. Find the `validateToken` function
3. Add an expiration check after line 42
4. Return 401 if the token is expired
```

After:
```
[cause] auth middleware skips token expiry check
[fix] src/middleware/auth.ts:L42 -> add `if (token.exp < now) return 401`
```

---

## Activation Methods

| Method | Level | Scope |
|--------|-------|-------|
| Token-efficient mode active | 1 | Session |
| `/token-optimize level-2` | 2 | Until changed |
| `/token-optimize level-3` | 3 | Until changed |
| `/token-optimize off` | 0 | Reset to default |
| Context window > 60% | 2 | Auto-triggered |
| Context window > 80% | 3 | Auto-triggered |

---

## Combining with Other Skills

- **With code generation**: emit code only, no explanatory prose
- **With debugging**: use `[cause]/[fix]` pattern, skip reproduction steps if obvious
- **With documentation**: compress to essential API signatures + one-line descriptions
- **With planning**: bullet-point plans, no narrative, skip justifications

---

## Measurement

Track token savings by comparing:
- Compressed output tokens vs estimated default output tokens
- Target: maintain same information density at lower token count
- Alert if compression drops below 30% savings (compression may not be applied correctly)

---

## Exceptions

Do NOT compress:
- Error messages shown to end users (must be clear and complete)
- Security warnings (safety over brevity)
- Code that will be copied verbatim into production
- Legal or compliance text
- Commit messages (follow conventional commit format)
- **Verification evidence** — executed command output, exit codes, pass/fail counts, and
  agent handoff blocks are ALWAYS quoted verbatim (VERIFICATION_PROTOCOL.md outranks this
  skill); compression never applies to the evidence layer

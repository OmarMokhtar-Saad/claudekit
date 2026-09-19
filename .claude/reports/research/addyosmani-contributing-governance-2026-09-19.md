# addyosmani/agent-skills CONTRIBUTING → ClaudeKit governance delta

**Retrieved:** 2026-09-19 via `gh api repos/addyosmani/agent-skills/contents/CONTRIBUTING.md` (raw contents), not model memory.
**Source:** https://github.com/addyosmani/agent-skills/blob/main/CONTRIBUTING.md · MIT
**Companion:** `addyosmani-agent-skills-2026-09-18.md` maps the *repo* (A1–A12). This file maps the *contribution contract* only.

This is a finding, not an instruction. Task 008 applies: extend existing assets, do not install a second catalog.

---

## The five governance items (C1–C5)

### C1. Skill-change rejection ledger
`evals/skill-impact.md` records every **rejected skill/prompt edit**: date, affected skill,
attempted change, before→after rank-1 score, rejected PR link, outcome. Contributors must
search it before proposing, and modifying an existing skill requires the same search.

Non-obvious rule, stated in their own words: land the ledger row on the **default branch
separately** from the rejected proposal — leaving it only on the proposal branch means
closing or force-pushing that branch discards the record.

**Our state:** `.claude/knowledge/rejections/` records rejected **plans** — `<ops-slug>.md`
sections plus append-only `INDEX.jsonl`, single writer `review-record.py cmd_write`, trigger
= 2nd non-approving round for an ops slug. There is **no axis for a rejected skill/prompt
edit**, so an edit that evals already killed can be re-proposed indefinitely.

### C2. CI-enforced per-skill eval cases
Every skill must ship `evals/cases/<skill-name>.json` with ≥3 positive triggers, ≥2 negative
triggers (carrying `owner` — the skill that *should* win), and ≥1 behavioral eval. Execution
evals need real files under `evals/fixtures/`; conversation-shaped skills may use a
reviewer-gated `kind: "dialogue"` eval. **CI enforces this.**

**Our state:** `evals/{definitions,fixtures,cassettes}/` at repo root holds 4 agent-behavior
evals that cost API money (`scripts/run-evals.py`, `ck eval`, `tests/test_evals.py`). There
are **no per-skill positive/negative routing cases**, so nothing fails CI when two skill
descriptions collide — the mechanical duplicate detector task 008 wants.

Separately: `.claude/skills/eval-harness/SKILL.md` documents a `.claude/evals/` layout that
**does not exist on disk**. Doc defect.

### C3. Write the procedure, not the workaround
A step that cannot be justified without naming a model, a model version, or one agent's
private tool name is rejected — describe the *capability* instead.

This is CLAUDE.md's model-routing policy ("policy names capability tiers, never vendor model
names") generalized from `model-policy.json` to all prompt content, and enforceable the same
way `gen-model-policy.py --check` is.

**Measured 2026-09-19** (YAML frontmatter stripped, prose only, across `.claude/skills`,
`.claude/agents`, `.claude/commands`): **21 files, 80 occurrences.**

| File | Hits |
|---|---:|
| `.claude/agents/QUICK_START.md` | 28 |
| `.claude/commands/refine.md` | 9 |
| `.claude/skills/santa-method/SKILL.md` | 6 |
| `.claude/commands/santa.md` | 5 |
| `.claude/skills/usage-monitoring/SKILL.md` | 4 |
| `.claude/skills/gan-harness/SKILL.md` | 3 |
| `.claude/agents/_shared/INVOCATION.md` | 3 |
| `.claude/commands/gan-build.md` | 3 |
| `.claude/skills/opensource-pipeline/SKILL.md` | 2 |
| `.claude/agents/coordinator.md` | 2 |
| `.claude/commands/prp-commit.md` | 2 |
| `.claude/commands/code-review.md` | 2 |
| 9 further files | 1 each |

Not all are violations. `usage-monitoring`'s price table needs real product names;
`coordinator.md` is explaining the migration *away* from names; `INVOCATION.md` records
measured per-model cost evidence. A gate therefore needs a per-entry allowlist with a stated
reason — ordered so the allowlist cannot short-circuit the scan.

Incidental real bug found while measuring: `.claude/commands/prp-commit.md` hardcodes
`Co-Authored-By: Claude Sonnet 4.6`, a stale attribution shipped to every kitted project.

### C4. Repo-scoped files are not user assets
Their `AGENTS.md`/`CLAUDE.md` configure work **on** their repo; CONTRIBUTING forbids telling
users to copy them into their own projects or global agent config. Only `skills/` is reusable.

**Our state:** CLAUDE.md states this in one clause. It is not a hard rule, and fleet sync
ships downstream — so it deserves promotion in `.ai/`.

### C5. Structured skill-gap intake
A `skill-gap.yml` issue form asks for: affected skill, the relevant excerpt, project context,
and what the user did instead — "enough for maintainers to triage without a freeform
write-up." Maps onto this repo's reflection receipts / `.claude/knowledge/issues/`.

---

## Confirmed anti-patterns (their words, not ours)

- The Claude Code plugin **does not register** their SessionStart meta-skill injection:
  "Claude Code routes skills natively, and always-on injection would create two routers for
  the same task." Matches the earlier report's "skip the session-start hook" verdict.
- **No translations accepted** — translated copies drift and cannot be maintained.
- `jq` is a hard dependency of their hooks, with a documented no-`jq` fallback branch and a
  regression test for it. Our rule 8 (bash 3.2 / no new deps) means we take the *test
  discipline*, not the dependency.

## Do not adopt

- A second rejection ledger alongside `.claude/knowledge/rejections/`.
- `evals/cases/` as a parallel tree to `evals/definitions/`.
- Their `npx skills add` distribution path — we ship via `ck` / wheel / `install.sh`.

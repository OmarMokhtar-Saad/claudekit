# addyosmani/agent-skills → ClaudeKit enhancement map

**Retrieved:** 2026-09-18 via `gh api` (raw contents), not model memory.  
**Source:** https://github.com/addyosmani/agent-skills  
**License:** MIT · **Stars:** 96,313 · **Default branch:** `main` · **Pushed:** 2026-09-18

This is a finding, not an instruction. Task 008 still applies: no new near-duplicate assets. Steal patterns into existing flow/skills/agents; do not install the pack as a second catalog.

---

## What it is

A 25-skill SDLC pack (Define → Plan → Build → Verify → Review → Ship) plus 9 slash commands, 4 review personas, 7 shared `references/` checklists, and a three-tier routing/behavior eval suite. Skills are workflows with steps, anti-rationalization tables, red flags, and evidence checklists. Google SWE-book ideas (Hyrum's Law, Beyoncé Rule, Chesterton's Fence, Shift Left, code-as-liability) are embedded in the steps, not left as slogans.

Their own comparison (`docs/comparison.md`) positions the pack against Superpowers (inner-loop autonomy) and Matt Pocock (grilling). ClaudeKit already absorbed Superpowers DNA (`using-superpowers`, `writing-plans`, `subagent-driven-development`, `writing-skills`) and a grilling-adjacent loop (`clarify` + `/specify` one-question-at-a-time). The remaining delta is **lifecycle completeness + mechanical quality contracts + in-flight doubt + catalog evals**.

---

## Inventory (verified)

| Layer | Count | Paths |
|---|---:|---|
| Skills | 25 | `skills/*/SKILL.md` |
| Slash commands | 9 | `.claude/commands/{spec,plan,build,test,constraints,review,webperf,code-simplify,ship}.md` |
| Personas | 4 | `agents/{code-reviewer,test-engineer,security-auditor,web-performance-auditor}.md` |
| Shared checklists | 7 | `references/` |
| Routing eval cases | 25 | `evals/cases/*.json` |
| Hooks | 3 families | `session-start`, `sdd-cache-*`, `simplify-ignore` |

Catalog: `using-agent-skills`, `interview-me`, `idea-refine`, `spec-driven-development`, `constraint-driven-development`, `planning-and-task-breakdown`, `incremental-implementation`, `test-driven-development`, `context-engineering`, `source-driven-development`, `doubt-driven-development`, `frontend-ui-engineering`, `api-and-interface-design`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `code-review-and-quality`, `code-simplification`, `security-and-hardening`, `performance-optimization`, `git-workflow-and-versioning`, `ci-cd-and-automation`, `deprecation-and-migration`, `documentation-and-adrs`, `observability-and-instrumentation`, `shipping-and-launch`.

---

## How it maps onto ClaudeKit

Their command spine vs ours (ours is already larger: 57 commands, 81 skills, 22 agents):

| Theirs | Ours | Fit |
|---|---|---|
| `/spec` | `/specify` + `spec-driven-development` | Same job. Theirs writes `SPEC.md`; ours writes `.specify/features/.../spec.md`. |
| `/plan` | `/plan` + `writing-plans` | Same job. Theirs adds `tasks/todo.md` + explicit AC vs standing DoD. |
| `/build` | `/implement` | **Different philosophy.** Theirs is TDD-in-session. Ours is Iron Law: ops.json only, implementer has no Edit/Write. |
| `/build auto` | `/loop-start` + `autonomous-loop` | Same *intent* (one approval, then run). Theirs keeps per-task RED/GREEN/commit and pauses on irreversible work. |
| `/test` | `/test` + `tester`/`verifier` | Covered. |
| `/constraints` | `constitution` + CLAUDE.md DoD | **Gap.** Theirs is a numbered, mechanical `CONSTRAINTS.md` with ratchets. |
| `/review` | `/review` + `/code-review` + `code-reviewer` | Ours is stronger on mutants/silent-failure. Theirs has change-sizing (~100 lines) and tests-first. |
| `/webperf` | `/performance` + `performance-optimizer` | Covered; theirs is CWV-specific. |
| `/code-simplify` | `refactor-cleaner` + `refactoring-patterns` | No dedicated slash command. |
| `/ship` | `/ship` + `/deploy` | **Name collision, different job.** Theirs: parallel persona fan-out → GO/NO-GO + rollback. Ours: git/CI ship pipeline (tests, secrets, commit). |

Persona overlap is already owned: `code-reviewer`, `tester`/`verifier`, `security-scanner`, `performance-optimizer`. Do not add a second set.

---

## Enhancements worth taking

Ranked by value for *our* flow. V/E are relative to ClaudeKit hard rules (stdlib-only, bash 3.2, no new runtime deps, blocking hooks `exit 2`, task 008).

### A1. Skill anatomy as a writing-skills gate (V:high E:low)

Their required shape: Overview · When / When NOT · Process · Common Rationalizations · Red Flags · Verification (evidence checkboxes). `writing-skills` already wants body <500 lines and overflow to `references/`. It does **not** require a rationalization table or an evidence checklist on every skill.

`using-superpowers` already has one rationalization table (for skipping skills). Most other skills have Anti-Patterns but not "excuse → rebuttal" plus a closable verification list.

**Adopt:** extend `writing-skills` quality checklist; backport the two sections onto the skills that actually route work (`clarify`, `writing-plans`, `executing-plans`, `test-driven-development`, `verification-before-completion`, `systematic-debugging`). Do not mechanically rewrite all 81.

### A2. DEFINE→SHIP decision tree in `using-superpowers` (V:high E:low)

`using-agent-skills` is a phase flowchart that maps a task to exactly one next skill, plus six always-on behaviors: surface assumptions, manage confusion, push back, enforce simplicity, scope discipline, verify-don't-assume.

`using-superpowers` has a smaller "User Says → Skill" table and a process/implementation/coordination priority. The missing piece is a **single phase tree over our catalog**, so the agent does not invent a 15-skill sequence or skip Define.

Also take their rule: "when in doubt, start with a spec" — but bind it to `/specify` / `/clarify`, not their `SPEC.md` path.

**Do not** copy their SessionStart hook that injects the full meta-skill body. They already warn not to wire it on Claude Code (double router + token cost). Our `context-budget` work would regress.

### A3. Interview protocol into `clarify` / `/specify` (V:high E:low)

`interview-me` is the strongest unique Define skill. It is not "ask questions." It is:

1. Hypothesis + confidence number (reason required below ~70%)
2. One question at a time, each with a **guess attached**
3. Probe "want vs should-want" when the user answers in best-practice talk
4. Restate: Outcome / User / Why now / Success / Constraint / **Out of scope**
5. Stop only on explicit yes — "sounds good" / "whatever you think" are not yes
6. 95% stop test: *can I predict the next three answers?* Floor: if several rounds don't raise confidence, say so and step back
7. Non-interactive ban (CI, `/loop`, autonomous-loop)

`/specify` already asks one question at a time. `clarify` already has reverse-question + severity ladder. `request-shaping` already extracts six pipeline dimensions and caps questions at three.

**Delta to port:** hypothesis+confidence, guess-attached questions, want-vs-should-want probe, explicit-yes gate, out-of-scope line. Keep `request-shaping`'s three-question cap for *routing*; use the interview protocol only when the user invoked specify/clarify or the ask is a product "build me X".

Do not add a new `interview-me` skill. That is a near-duplicate of `clarify`.

### A4. `CONSTRAINTS.md` + floor-guard (V:high E:medium)

`constraint-driven-development` writes a project-level numbered bar that outlives the session:

- **Floor (always):** no new suppressions (`@ts-ignore`, `eslint-disable`, `# noqa`), no unimplemented stubs, no skipped/deleted tests without a commit reason, no secrets, file itself cannot be weakened to go green
- **Enforced with numbers:** every row is `{dimension, rule, command, when}` — a number without a command is an aspiration
- **Ratchets:** measure today's coverage/bundle and hold the line
- **Exceptions:** id, path, owner, expiry
- Four-question intake with defaults (so "I don't know" still produces a working file)
- `references/floor-guard.md` watches the diff for a lowered bar

`constitution` is principles. CLAUDE.md DoD is **this repo's** maintainer bar. User-project kitted trees do not get a numbered contract the agent cannot quietly lower.

**Adopt as refinement of `constitution` + `project-adaptation` / `ck adapt`**, not a 26th skill. Mechanical piece (scan staged diff for new suppressions / skipped tests) fits a hook: `exit 2` + stderr, fail closed, no `jq` hard-dep (their hooks require `jq`; ours must stay bash 3.2 / stdlib Python).

Owner-gated: this is user-visible in kitted projects.

### A5. In-flight doubt: CLAIM → EXTRACT → DOUBT → RECONCILE → STOP (V:high E:low)

`doubt-driven-development` is **not** santa-method. Santa is a dual-model gate on a finished artifact. This is a per-decision review while building:

1. CLAIM: one sentence + why it matters
2. EXTRACT: smallest artifact + contract; **strip the reasoning**
3. DOUBT: fresh-context reviewer gets ARTIFACT + CONTRACT only — **never the CLAIM** (anti-anchoring)
4. Optional user-authorized cross-model escalation
5. RECONCILE: every finding classified against the artifact text
6. STOP: bounded loop, not recursion

Triggers: production/security/irreversible, unfamiliar code, or a confident output cheaper to verify now than debug later.

**Adopt into `santa-method` as an "in-flight" mode**, and name it from `/build auto`'s pause list (auth, migrations, payments, deletions, deploys, secrets, anything not `git revert`-able). `council` stays for go/no-go among multiple credible paths.

### A6. `/implement auto` or `/loop` pause contract (V:medium E:medium)

`/build auto` is the cleanest autonomous-loop writeup they have:

- Require a real spec at a known path; README does not count
- Clean baseline (`git status --porcelain`); refuse to absorb unrelated dirty files
- One unambiguous approval (hedged "looks reasonable" is not yes)
- Per-task RED → GREEN → full suite → build → **one commit of only that task's files** — never `git add -A`
- Stop and ask on: test/build failure, spec gap, high-risk / irreversible
- Resume from next pending task on re-invoke

`autonomous-loop` already has safety guards and destructive-op escalation. The transferable contract is **spec-required + dirty-tree refuse + hedged-approval reject + per-task commit isolation + irreversible pause**.

**This repo:** Iron Law stays. Auto-mode cannot give the implementer Edit/Write. At most it can drive validate → dry-run → execute → compile-verify per phase, still through ops.json.

**Kitted user projects:** this is the more natural home, and it is owner-gated.

### A7. Catalog routing evals (V:medium E:medium)

Each skill has `evals/cases/<skill>.json` with:

- `trigger.positive[]` — prompts that must rank the skill in top-K
- `trigger.negative[]` — prompts owned by a *different* skill (collision test)
- `evals[]` — behavioral expectations (dialogue / trace)

Their CI runs structure + routing; behavioral traces are Tier 3. `eval-harness` + `prompt-evaluation` exist; we do not have **per-skill positive/negative routing cases** that fail CI when two descriptions collide.

**Adopt:** a small fixture set for the routing skills (`using-superpowers`, `clarify`, `writing-plans`, `systematic-debugging`, `verification-before-completion`). Fits task 010. Do not import their 25 JS fixtures.

### A8. Reviewer: change sizing + tests-first (V:medium E:low)

`code-review-and-quality` five axes (Correctness, Readability, Architecture, Security, Performance) ≈ our `code-reviewer` (Correctness, Security, Performance, Reliability, Quality). Ours already has mutants and silent-failure hunting.

**Take:**

- Change sizing ~100 lines; split strategies when over
- Review the tests *before* the implementation
- Severity labels Nit / Optional / FYI vs blocker
- "Verify the verification" (did the author actually run what they claim?)

Do not add `web-performance-auditor`. `/performance` + `performance-optimizer` already own that seat.

### A9. Source citation into `search-first` (V:medium E:low)

`source-driven-development`: detect stack+versions → fetch official docs → implement documented patterns → **cite sources** → flag unverified claims. Token policy already says context7 first, then `web-researcher`. `search-first` is "find an existing package/skill/MCP," not "ground this framework call in the current official page."

**Adopt:** a Cite / Unverified block in `search-first` (and in `web-researcher` output). No new skill.

### A10. Launch vs ship split (V:medium E:low)

Their `/ship` is a launch gate: parallel `code-reviewer` + `security-auditor` + `test-engineer`, merge in main context, mandatory rollback plan, GO/NO-GO. Personas do not invoke personas.

Our `/ship` is a release pipeline. Our `/deploy` mentions rollback but is thin on feature-flag lifecycle, staged rollout, error-budget gate, flag owner+expiry.

**Adopt into `/deploy` + `monitoring-observability`**, not by renaming `/ship`. Optionally add a "fan-out review" paragraph to `/ship` that reuses *our* `code-reviewer` / `security-scanner` / `tester` — same pattern as theirs, our agents.

### A11. Deprecation completeness into `/migrate` (V:low-medium E:low)

`/migrate` already generates deprecation notices and phased replacement. Their skill adds: code-as-liability, Hyrum, compulsory vs advisory, strangler / adapter / expand-contract, zombie-code hunt, "how would we remove this in 3 years?" at design time.

Port as sections in `database-migration-patterns` + `/migrate`. No new skill.

### A12. Brainstorming: Not Doing + How Might We (V:low E:low)

`idea-refine` ≈ `brainstorming` (diverge / evaluate / converge). Their extras: How Might We restatement, 5–8 variations via named lenses, **Not Doing (and why)**, save one-pager to `docs/ideas/` only after confirm.

Add Not Doing + assumption-validation checkboxes to `brainstorming`. Do not add `idea-refine`.

---

## Hooks: look, mostly don't copy

| Hook | What it does | Verdict |
|---|---|---|
| `session-start.sh` | Injects the entire `using-agent-skills` body | **Skip.** They say not to wire it on Claude Code. Token regress. |
| `sdd-cache-pre/post` | WebFetch HTTP cache, ETag/Last-Modified, 304 → `exit 2` + cached body on stderr | Interesting for `web-researcher` spend. Needs a spike; depends on `jq`+`curl`. Not a skill enhancement. |
| `simplify-ignore` | Rewrites `simplify-ignore-start/end` blocks to placeholders for the session | Clever, high mutation risk, `jq` dep. Skip unless we have a measured over-simplify problem. |

Their blocking convention (`exit 2` + stderr for cache hit) matches our rule 2. The `jq` hard-dep does not match rule 8 / bash 3.2 portability.

---

## Do not adopt

1. **The pack as a plugin alongside ClaudeKit.** Two routers, two `/ship`s, two `code-reviewer`s. Their `/ship` already defers to a user-level `code-reviewer` — installing both will silently shadow.
2. **Replacing Iron Law with in-session TDD `/build`.** That is a user-project option, not a maintainer-repo change.
3. **Four new personas.** Seats are filled.
4. **25 new skills.** ~14 are already covered; 008 is consolidation.
5. **SessionStart injection of a full SKILL.md.**
6. **`npx skills add` as a distribution path for this repo.** We ship via `ck` / wheel / install.sh.

---

## Suggested first diffs (owner-gated)

Tier 1 (single-file, skip planner) if approved:

1. `writing-skills` — require Rationalizations + Verification on new skills
2. `using-superpowers` — add a DEFINE→SHIP tree mapped to *our* names
3. `clarify` — hypothesis / guess / explicit-yes / out-of-scope
4. `code-reviewer` — tests-first + change-sizing paragraph
5. `search-first` — Cite / Unverified block
6. `brainstorming` — Not Doing list

Tier 2 after that:

7. `constitution` / `project-adaptation` — `CONSTRAINTS.md` template + floor-guard hook
8. `santa-method` — in-flight CLAIM/EXTRACT/DOUBT mode
9. `autonomous-loop` + `/loop-start` — `/build auto` pause/commit contract
10. `eval-harness` — routing fixtures for the five skills that mis-fire most

Stop and ask before any of these. None of this is approved work.

# Adoption candidates: six external repos → ClaudeKit + fleet

Retrieved: 2026-09-16. Sources read via GitHub API/raw, not from model memory.
Per-repo detail: `planning-with-files-and-rtk.md`, `mantis-and-agent-reach.md`,
`moonlight-lupin-agent-skills.md` (same directory).

Star/license/pushed verified directly against `api.github.com` on 2026-09-16:

| Repo | Stars | License | Last push |
|---|---:|---|---|
| Panniantong/agent-reach | 82,193 | MIT | 2026-09-15 |
| rtk-ai/rtk | 80,640 | Apache-2.0 | 2026-09-15 |
| othmanadi/planning-with-files | 26,924 | MIT | 2026-09-15 |
| google/mantis | 1,559 | Apache-2.0 | 2026-09-13 |
| moonlight-lupin/agent-skills | 70 | MIT | 2026-09-12 |

Legend: **V** = value, **E** = effort. Every candidate is judged against ClaudeKit's
hard rules — stdlib-only Python in `src/` and ops scripts, bash-3.2/macOS-safe shell,
no new runtime dependencies (rule 8), blocking hooks `exit 2` + stderr (rule 2).

---

## TIER A — adopt

### A1. BM25 skill retrieval at `UserPromptSubmit` — **DROPPED to Tier C, 2026-09-16**

> **Spike verdict: ILLUSORY.** Measured, not argued — see
> `a1-skill-retrieval-spike-2026-09-16.md`. The listing re-measured at 138 assets /
> 16,610 chars ≈ **4,152 tokens against a ~6,000-token budget** at the current
> `skillListingBudgetFraction` of 0.03 — it is *under* budget, with ~1,850 tokens of
> headroom, so nothing is being dropped today and there is no problem to solve.
>
> The load-bearing finding: Claude Code exposes exactly two levers
> (`skillListingBudgetFraction`, `skillListingMaxDescChars`) and **no names-only mode**.
> The listing cannot be trimmed except by deleting descriptions from source files. So a
> ~300-token injection lands *on top of* an untrimmed listing, inside existing headroom:
> **net saving 0**. The premise below — that retrieval supplies descriptions a trimmed
> listing gave up — has no mechanism behind it.
>
> Reopen only if the listing actually exceeds budget (worth a quarterly re-measure; it
> grew +102 tokens in ten days), and even then only after BM25 precision is measured over
> real prompts rather than asserted.

The original case, kept for the record:

Closes a **measured, still-open** gap. `skill-listing-budget-2026-09-06.md` measured this
repo's listing at 137 assets / 16,198 chars ≈ 4,050 tokens against a documented default
budget of ~2,000 — Claude Code is silently dropping descriptions for least-used skills.
Raising `skillListingBudgetFraction` to `0.03` bought headroom; it did not remove the
ceiling, and the fleet carries 73 skills + 39 commands in every kitted project.

Their mechanism: no pre-built index. At startup, tokenize every skill description, compute
IDF with Lucene-style clipping, precompute BM25 weights (`k1=1.5`, `b=0.75`). Per turn, the
hook tokenizes the user prompt, sums posting-list weights, and injects the top-6 as
`- **{name}** ({id}): {description}` truncated at 200 chars. Sub-millisecond for 128 skills.
~13KB + 26KB of pure-stdlib Python, `pyyaml` only for config — **fits rule 8 as-is**.

Port note: theirs hangs off Hermes' `pre_llm_call` event, which Claude Code does not have.
ClaudeKit already registers `UserPromptSubmit` (2 hooks) — that is the mount point, and it
can inject context. **This needs a feasibility spike before a plan**: injecting a
recommendation list does not shrink the harness-generated listing, so the win is only real
if the listing itself can be trimmed (names-only) while retrieval supplies descriptions.

Honest caveats from the source: BM25 is lexical only ("convert to WebP" may miss a
semantically-matching skill); static top-K=6; **no published retrieval metrics** — the
authors never validated effectiveness. Treat as unproven; gate adoption on our own
precision measurement over a corpus of real prompts, not on their claim.

### A2. Author ≠ reviewer, enforced at runtime (V:high E:low) — mantis

Mantis runs an 18-stage pipeline whose separation of duties is enforced **at runtime** by
Pydantic validation, not by prompt (`mantis-patch` structurally cannot self-grade).

ClaudeKit's equivalent invariant is entirely prompt-enforced: CLAUDE.md's review floor says
"fresh `code-reviewer` instance, never the author," and the quality gates section already
concedes "Prompt-enforced — don't overstate in docs." Two memories record this biting:
`review-record-anchored-block` (verdicts cannot gate execution) and
`code-review-cannot-bind-after-archiving`.

Adoption: `review-record.py` already resolves a config and writes a verdict — add a
mechanical check that the recorded reviewer identity differs from the recorded implementer
identity for that ops.json, and `exit 2` when it does not. Small, testable, and it converts
a documented honesty caveat into a gate.

### A3. PreCompact / context-loss recovery contract (V:high E:low-medium) — planning-with-files

Three files (`task_plan.md`, `findings.md`, `progress.md`) plus lifecycle hooks that
re-inject state at turn start; a catchup script parses the markdown, extracts *incomplete*
phases, and injects a digest, so `/clear` or compaction does not cost the task.

Overlap is real and must be respected, not duplicated: ClaudeKit already ships
`context-keeper`, `/save-session`, `/resume-session`, `.claude/session-context.md`,
`session-start.sh`, `session-memory-context.py`, `suggest-compact.sh`, and one registered
`PreCompact` hook. The transferable delta is narrow and worth taking:

1. **Extract-incomplete-only.** Their catchup injects the *unfinished* phases, not the whole
   file. Our session-context injection is not selective.
2. **Write on the way in, not on the way out.** State survives an *un*graceful end only if it
   was already on disk; `/save-session` is a user-invoked, end-of-session act.

This is a refinement of existing assets. **No new skill** — task 008 is consolidation.

---

## TIER B — strong, gated on a decision

### B1. Declarative output-filter DSL for noisy Bash (V:high E:medium) — rtk

64 embedded TOML filters; hooks transparently rewrite `git status` → `rtk git status`;
filters do regex line-stripping, truncation, grouping, dedup, and the output still reads as
real command output. Operations: `strip_lines_matching`, `keep_lines_matching`, `max_lines`,
`head_lines`, `tail_lines`, `on_empty`. Resolution is hierarchical: project `.rtk/filters.toml`
> global `~/.config/rtk/filters.toml` > built-ins.

Fit: ClaudeKit's `token-optimization` skill is **prose advice**; rtk makes it mechanical, and
our `PostToolUse` (4 hooks) is the mount point. Fleet-wide this is the single highest-leverage
token win — every project runs pytest/ruff/git constantly.

**Blocker: do not vendor rtk.** It is a Rust binary; rule 8 forbids new runtime deps and
bash-3.2/macOS must keep working. What we can adopt is the *design*: a stdlib-Python
`PostToolUse` filter driven by declarative filter definitions, with hierarchical override.
Scope discipline matters — 64 filters is a corpus, not a weekend; start with the 4-5
commands our own logs show are noisiest, measured, not guessed.

Risk worth stating: a filter that swallows the line containing the actual error makes every
downstream debugging session worse. Any filter must be reversible (raw output on demand) and
must never strip stderr on non-zero exit.

### B2. Layered auto-healing config (V:medium E:low) — mantis

Base config + local overrides that self-repair when a key is missing or malformed. ClaudeKit
already has the shape (`.claude/settings.json` + gitignored `settings.local.json`) — and the
CLAUDE.md "session setup gotcha" documents exactly the failure this fixes: when
`settings.local.json` goes missing, `ops-enforcement` blocks Edit/Write and the fix is manual
restoration from CONTRIBUTING.md. Auto-healing that one file removes a recurring session tax
across the whole fleet.

---

## TIER C — consider / reject

### C1. Probe by executing, not by stat'ing (V:medium E:low) — agent-reach

`agent-reach doctor` determines backend availability by *running* the tool, not by checking a
path exists, and reports tiered capability (0=zero-config, 1=free API, 2=browser/auth).

Direct read-across to `ck doctor --strict`. It also rhymes with a hard-won local lesson:
memory `a-passing-check-can-measure-nothing` records three inert green checks in one session,
and `failing-positive-control-means-real-signal` says prove a check can fail first. A doctor
check that stats a file is exactly that failure mode. Worth an audit pass over `ck doctor`'s
existing checks; likely small.

### C2. Multi-backend channel abstraction with user-reorderable preference — agent-reach

Ordered backend list per capability, `backends[0]` preferred, automatic fallback, user
reorders via env var without code changes. Genuinely elegant, and it is the same shape as
our `model-policy.json` tier table (`escalate_to`/`escalate_when`) — which means we already
have it where it matters. **No action.**

### C3. Mantis's 18-stage pipeline, sandbox tiers, SQLite checkpoints — REJECT

Interesting, and the wrong size. It is built on Google ADK (proprietary), and the 4-tier
sandbox (static → gVisor → microVM → cloud GCE) would collide head-on with hard rule 6:
security framing stays honest, "denylist speed bump, not a sandbox." Adopting sandbox
vocabulary we cannot back would make that framing dishonest. Take A2 and B2 from mantis;
leave the rest.

### C4. Multi-platform skill distribution (14+ platforms) — planning-with-files — REJECT

One canonical SKILL.md fanned out to many host platforms. ClaudeKit targets Claude Code;
this solves a problem we do not have.

---

## Fleet applicability

Per `fleet-sync-state`, 14 repos carry ops scripts; kitted projects carry the full
`.claude/` tree. Candidates land in two groups:

- **Ships to every project via the normal sync** (they are `.claude/` assets + stdlib
  scripts): A1, A3, B1, B2.
- **Repo-local to claudekit** (enforcement/CLI internals): A2, C1.

Constraint from `fleet-sync-preserve-local`: sync surgically — never overwrite a downstream
file that carries project-specific content. B1 in particular is per-project by nature (filter
sets differ by stack), so it must ship as base filters + a project-local override file, never
as a wholesale replacement.

---

## Recommended order

1. **A2** — smallest, closes a conceded prompt-only gate, repo-local, no fleet risk.
2. **B2** — removes a recurring session tax, low effort, well-understood shape.
3. **A3** — refine existing context assets; no new assets (task 008).
4. ~~**A1 spike**~~ — **done 2026-09-16, verdict ILLUSORY.** The listing is under budget
   and cannot be trimmed; injection would add ~300 tokens for a net saving of 0. Dropped
   to Tier C. Re-measure quarterly rather than plan it.
5. **B1** — largest and riskiest; scope to the noisiest commands our own logs show, with
   raw-output escape hatch and a hard rule never to strip stderr on failure.

Nothing here is approved or planned. Rule 5 (Golden Rule): no code changes without explicit
user approval.

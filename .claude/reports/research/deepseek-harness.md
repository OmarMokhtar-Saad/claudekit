# Research: deepseek-ai/deepseek-harness (`dsh`)

**Date:** 2026-08-21 · **Method:** GitHub API (README, tree, architecture.md, package READMEs) — primary sources, not blog summaries.

## What it is (verified)

| Field | Value |
|---|---|
| Created | 2026-08-13 (8 days old) |
| Stars | 176,336 |
| Language | TypeScript (pnpm monorepo) · MIT |
| Status | **Developer preview** — "THERE WILL BE COMPATIBILITY-BREAKING CHANGES" |
| Tagline | "Everything is a Plugin", built on [Cordis](https://github.com/cordiverse/cordis) |

An agent harness (the runtime a coding agent runs in) — the same product category as Claude Code itself, **not** the same category as ClaudeKit. ClaudeKit is a prompt corpus + enforcement layer *on top of* a harness. So `dsh` is a source of architectural patterns, not a competitor or a dependency.

Ships a Web UI (`npx @deepseek-ai/dsh web`), a headless one-shot runner, and a Python SDK.

## Architecture in one paragraph

A running `dsh` is a **plugin tree composed at boot from ordered layers**. There is no privileged core: the model adapter, tool registry, session log, and *the agent loop itself* are plugins, each replaceable from config. Plugin registrations are **reversible effects** that unwind on unload. Composition = **profiles** (named stacks, e.g. `web`/`headless`) built from **bundles** (distributable config rows + code), overlaid by `cordis.patch.yml` at bundle → profile → home → `--patch` precedence. `dsh --profile web --dump-config` prints the actual booted tree, and any row can be replaced by a patch.

Three concepts carry most of the design weight:

1. **The append-only session log is the single source of truth.** `deriveMessages()` projects model history from it. The stated invariant: **"Model-visible means logged"** — anything reaching a model request must be reconstructable from the log, asserted at runtime. Fork, resume, transcripts, telemetry, and persistence all derive from this one stream.
2. **Capability seams.** A seam = Service Definition (interface) + Service Provider (impl) + Consumer (usually a model-facing tool). All three roles required — "one role alone is not a seam." Payoff: filesystem and subprocess providers share one execution world, so repointing them at a remote sandbox moves Bash, PTY, and LSP together with zero provider forks.
3. **Typed events as the only extension points**, in three domains: *session* (durable facts), *agent/\** (live, carries the agent handle), *capability* (`fs/*`, `tools/*`, `telemetry/*`). Waterfall events (`agent/pre-step`, `agent/request`, `llm/stream`, `tools/*`) require listeners to call `next()` to delegate.

**Turn flow:** a *step* = one model request + its tool calls; a *turn* = zero or more steps. `agent/pre-step` decides what the model sees and may rewrite or reject the claimed messages — and a rejected claim **still closes a durable turn that spent no step, so the log records the attempt**.

## The package taxonomy (the most useful artifact)

`packages/` — worth reading as a checklist of concerns a mature harness separates:

`acp api attachment boot bundle client code-runtime compaction context core credentials e2b examples experimental extensions feedback fs goal guard hooks host identity interaction jobs llm lsp mcp plan preset runtime-diagnostics sandbox schedule sdk session-query session settings shell skill spill storage subagent subprocess terminal test-support todo typert util web workflow workspace`

Three families relevant to our roadmap:

- **`spill/`** — persists oversized tool output, replaces the inline result with *a bounded preview + a retrieval locator*. Split into storage (`spill`), a local file backend (`spill-local`), and a post-execution policy (`spill-policy`).
- **`compaction/`** — a seam with a summarizing backend (`compaction-basic`, token-pressure triggered), a **model-free tool-result pruner**, and a human `/compact` command. Token *measurement* is a separate LLM-family service from token *policy*.
- **`guard/`** — "loop-hygiene" plugins: `repeat-tool-reminder` (advisory nudges on repeated tool calls) and `timeout-policy` (per-call deadlines as deployment policy). Explicitly *not* a seam — "a self-contained consumer of core services", not swappable.

## Corrections to the first-pass summary

The blog-sourced pass claimed "no token budgeting enforcement" and "20M tokens for simple tasks." Reading the source: `compaction-basic` is explicitly token-pressure triggered, `spill-policy` bounds tool output, and `timeout-policy` enforces per-call budgets. Treat the token-consumption figure as unverified third-party claim. Also unverified: benchmark results — `BENCHMARK.md` is two sentences pointing at the Python SDK, with **no published numbers**.

## Ranked, actionable ideas for ClaudeKit

### 1. "Model-visible means logged" as a ClaudeKit invariant — HIGH fit / LOW effort
Our ops.json execution already writes backups; it does not produce an append-only event stream. Adopting the rule that every model-visible input is reconstructable from a durable log gives us replay, fork, and — critically — **the substrate the eval framework (010) needs**. Right now an eval has nothing stable to score against. This is the prerequisite, and it is the single highest-leverage item.

### 2. The spill pattern for hook and ops output — HIGH fit / LOW effort
Bounded preview + retrieval locator, instead of dumping full tool output into context. Directly serves the context-budget work (009), needs no new deps (stdlib file writes into the session dir), and is the cheapest real token win available. Our `token-optimization` skill *describes* spilling; `dsh` shows it belongs in the harness layer as policy, not in a prompt as advice.

### 3. Separate token *measurement* from token *policy* — HIGH fit / LOW effort
`dsh` keeps counting in the LLM family and thresholds in the compaction backend. Our context-budget design should copy this split, or every future policy change edits the counter.

### 4. Model-free pruning before model-based summarization — HIGH fit / MEDIUM effort
`compaction-tool-result-pruner` drops stale tool results deterministically, with no model call, before paying for summarization. Cheap, testable, and fits our stdlib-only constraint exactly.

### 5. `--dump-config` for the composed hook/agent tree — HIGH fit / LOW effort
`dsh --profile web --dump-config` prints what actually booted. `ck doctor` reports health; it does not print the resolved composition. Given that our #1 recurring session gotcha is "which hook profile is actually active" (`ECC_HOOK_PROFILE`), a `ck config --dump` that prints the resolved, layered, in-precedence-order truth would pay for itself immediately.

### 6. Layered profiles/bundles with explicit precedence — MEDIUM fit / MEDIUM effort
Our `ECC_HOOK_PROFILE` is a flat switch. The bundle → profile → home → `--patch` ordering, where each layer replaces a row *by id*, is a better model for the fleet-sync problem (16 kitted projects where downstream local content must survive a sync). Worth stealing the precedence model even without the plugin machinery.

### 7. Guards as advisory-vs-enforcing, split deliberately — MEDIUM fit / LOW effort
`repeat-tool-reminder` injects a *logged* advisory message rather than blocking. Our hooks are near-uniformly fail-closed `exit 2`. A sanctioned advisory tier — logged, non-blocking nudges — would let us cover loop-hygiene patterns (repeated identical tool calls, thrash) that don't justify a hard block.

### 8. `.agents/notes/implemented/<category>/<date>-<slug>.md` — MEDIUM fit / LOW effort
Dated, categorized, *status-foldered* architecture decision notes, cross-linked from the README of the package they govern. Close to our `.ai/`, but with two things we lack: lifecycle state in the path (`implemented/`) and bidirectional linking from the code's own README. Low-cost improvement to how `.ai/` ages.

### 9. Capability seams (3 roles) — MEDIUM fit / HIGH effort
Correct and principled, but the payoff is provider swapping (local ↔ remote sandbox), which a CLI-shaped kit with zero runtime deps mostly doesn't need. **Note the discipline, skip the machinery.**

### 10. Full Cordis reversible-plugin system — LOW fit / HIGH effort
Hot-reload with effect unwinding is real engineering, and wrong for us: it is TypeScript, dependency-heavy, and aimed at a hosted product. Do not pursue.

## Recommended next step

Items 1–3 and 5 are one coherent piece of work — a durable session event log, spill-bounded output, split measurement/policy, and a config dump — and they land squarely on the two things already at the top of our queue (009 context budget, 010 eval). Suggest scoping that as a Tier 2 plan before touching anything else here.

## Caveats

- Repo is 8 days old and self-described as breaking-change-prone. Borrow *patterns*, take on **no** coupling.
- 176k stars in 8 days is not an organic quality signal; judge the design on the design.
- No published benchmark numbers. Any performance claim about `dsh` is currently unsupported.

---

## Addendum (2026-08-21): direct ClaudeKit interop found

`dsh` ships **first-class Claude Code compatibility**, which changes the "how does this help us" answer:

- **`packages/hooks/hooks-claude-code`** — a bridge plugin that runs a user's existing Claude Code `hooks.json` (or a settings file's `hooks` key) on dsh's own interception points. Honors `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PROJECT_DIR}` substitution, the CC 10-minute default timeout, CC-shaped per-event stdin payloads, and maps hook outcomes onto typed Decisions. **Limits:** only shell-form `type: 'command'` hooks run (`http`/`mcp_tool`/`prompt`/`agent` are parsed-and-skipped with a warning); config is parsed once at load and is process-level, with no per-session discovery yet (`TODO(per-session-hook-config)`).
- **`packages/subagent/subagent-claude-code`** — spawns a real Claude Code child through the official Claude Agent SDK, as one of eight interchangeable subagent providers (in-process spawn, in-process **fork from parent history**, ACP, Codex, dsh-SDK).
- **`hook-protocol`** — the dialect-agnostic half: matcher, **exit-code/stdout codec**, `ctx.shell` execution, and **most-restrictive merge** when several hooks decide on one event.

Implication: ClaudeKit's enforcement layer (`.claude/hooks/*.sh`, exit-2 fail-closed) is portable to dsh today, unmodified, for the command-hook subset. We are not locked to one harness.

Their explicit stance is worth noting: the bridge exists **only** as a compatibility path — "a native cordis plugin could do everything this bridge does, more powerfully, with typed returns and no serialization boundary."

### Two more patterns worth stealing

- **Most-restrictive merge** (`hook-protocol`): when multiple hooks decide on the same event, the most restrictive outcome wins, deterministically. We have no defined resolution rule when several ClaudeKit hooks fire on one event — this is a real latent gap.
- **`goal/` — durable objectives** (`ctx.goals`): persisted objective state in the session log, with a `goal-round-driver` for same-session continuation, split from the tools and the human command that consume it. This is the missing durable spine under our `autonomous-loop` / `gan-harness` skills, which currently hold objectives only in prompt text.
- **`subagent-fork-in-process`**: a child started from the parent's *completed history* rather than fresh — a cheaper middle ground between our full-context `fork` and a cold subagent.

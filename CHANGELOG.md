# Changelog

All notable changes to ClaudeKit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Versioning correction (2026-07):** the entry previously published as `1.3.0`
> (2026-04-11) actually shipped *after* `2.0.0` (2026-03-17). It has been renumbered to
> `2.1.0` to restore monotonic order. Two agents listed under it — `dead-code-hunter` and
> `open-source-forker` — never shipped and have been removed.

## [Unreleased]

### Added
- **Worktree-per-agent parallel execution.** New `worktree-manager.py` operations script
  (create/list/remove/prune; validated slugs, git-ignored registry at
  `.claude/state/worktrees.json`, atomic lock-protected writes, max 5 concurrent, safe
  removal that refuses dirty trees / unmerged commits / the primary worktree; secrets
  never copied by default), new `/worktree` command as the lifecycle primitive, and a
  coordinator "Worktree Isolation Protocol" + gitOps "Multi-Agent Merge Protocol"
  (workers commit on `agent/*` only; single merge authority; one verification pass on the
  integration branch). Isolation is proof-tested: `execute-json-ops.py` executed with
  cwd = a worktree root writes inside the worktree and cannot escape it
  (`tests/test_worktree_manager.py`, 20 behavioral tests).
- **`cross-tool-collaboration` skill + `docs/PARALLEL_AGENTS.md`.** Running multiple
  Claude accounts (`CLAUDE_CONFIG_DIR` isolation with hardening rules) and heterogeneous
  AI tools (Cursor/Codex via the AGENTS.md standard, MULTI_AGENT_PLAN.md contract,
  disjoint ownership, foreign-tool-output-is-data trust boundary) on one repository.
  Dual-account recipe published per owner directive (2026-08-09 /goal).

### Changed
- `/batch` reconciled with the worktree engine: units execute in waves of ≤5 concurrent
  worktrees (was 5–30 unbounded), lifecycle goes through `worktree-manager.py`, and
  agent-side PR/merge steps are removed — integration flows through the gitOps
  Multi-Agent Merge Protocol.
- `multi-agent-coordination` skill gains Pattern 4 (worktree-per-agent) and the
  `MULTI_AGENT_PLAN.md` template; `using-git-worktrees` gains the worktree-per-agent
  rules, per-worktree env (`.worktree-env` port/device offsets), and a documented
  session-rooted-hooks limitation. `.agents/` skill mirrors updated in lockstep
  (`.codex/` mirror refresh deferred to the next corpus sync — `.codex/agents/gitOps.toml:30`
  still references the skill and will pick up the frontmatter change then).

### Fixed
- **`using-git-worktrees` was model-invocation-disabled while four loaders instruct
  agents to load it** (`commands/git.md`, `agents/gitOps.md`, `commands/batch.md`,
  `.codex/agents/gitOps.toml`) — agents could never actually load the skill. Frontmatter
  flag removed for this skill only; the corpus-wide flag-vs-loader contradiction is
  backlogged (interacts with task 009's context-budget policy).
- **Versioned Python interpreters no longer rejected by the command guard.** `python3.12`,
  Homebrew's `python3.14`, `pip3.x` (bare or by absolute path) normalize to their
  allowlisted base (`python3`/`pip3`) for allow/block decisions; multi-Python machines
  previously got per-interpreter "not in allowlist" rejections that stalled sessions.
  Normalization applies to the blocklist too, so it cannot be used to bypass screening
  (`python3.12.evil` does not match). Regression cases in `tests/test_security.py`.

### Added
- **Work-loss protection — a concurrent session can no longer silently wipe accumulated
  work.** Four layers, prompted by a real incident (an external `git checkout` reset a file
  mid-multi-round-plan, destroying five rounds of edits, discovered only via test failures):
  (1) the command guard now blocks destructive git (`reset --hard`, `clean -f`,
  `checkout -- <path>`/`checkout .`, worktree `restore`, `stash drop/clear`) while benign
  forms (branch checkout, `-b`, `restore --staged`, soft/mixed reset) stay allowed;
  (2) `validate-config-json.py --stamp-baseline` records sha256 of every target file into
  ops.json and the executor refuses to run — before any write, dry-run included — when a
  stamped file changed since (`BASELINE DRIFT` report names each file); the /implement flow
  now stamps by default; (3) every successful execution snapshots the post-state of touched
  files under `<backup>/post/` and `restore-backup.py --post` restores that checkpoint —
  forward recovery from an external wipe becomes one command instead of replaying every
  archived ops config; (4) session-start warns when another live Claude session holds a lock
  in `.claude/locks/` (per-pid files, dead pids pruned, warning-only). Behavioral coverage in
  `tests/test_work_loss_protection.py` (15 tests) and `tests/test_security.py` (destructive
  vs benign git corpus).
- **Project graph sidecar — agents query cached structure instead of re-grepping the repo
  each session.** New `.claude/operations/scripts/project-graph.py` (stdlib-only;
  `build`/`query`/`hubs`/`path`/`stale`) stores an agent-built dependency graph at
  `.claude/project-graph.json`. Graphify-inspired patterns, no new dependency: every edge
  carries a confidence tier (`extracted`/`inferred`/`ambiguous`), `hubs` ranks fan-in/fan-out
  and flags GOD-NODE candidates, `path` reports a route's weakest-tier confidence, and
  `stale` re-hashes file-backed nodes (sha256) so an outdated graph is detected, not trusted.
  The LLM (codebase-mapping skill, new Step 7) extracts nodes/edges from any language; the
  script owns validation (anti-traversal ids, no dangling edges, size guards) and integrity
  (hashes, line counts). Explore, planner and refactor-cleaner go graph-first when the sidecar
  exists — script exit 3 means no graph/no match and they fall back to grep, so ungraphed
  projects behave exactly as before. Refactor risk rules: a GOD-NODE is always RISKY; an
  `ambiguous` inbound edge promotes SAFE to CAREFUL. Fully automatic in the workflow: the
  existing session-start hook reports graph status (none / fresh / STALE with the merge
  remediation) each session — no new hook spawn — and explore records back manually-traced
  dependencies via `build --merge`, so the graph accretes as agents work. Behavioral coverage in
  `tests/test_project_graph.py`, including a byte-identity guard on the
  `.claude/skills` ↔ `templates/skills` twins.
- **Per-issue knowledge ledger — the project stops re-diagnosing bugs it already fixed.**
  New `.claude/knowledge/issues/<slug>.md` store (markdown + frontmatter: `signature`,
  `root_cause`, `fix`, `files`, `date`, `verified`) plus
  `.claude/operations/scripts/knowledge-ledger.py` (stdlib-only; `search`/`record`/`list`/
  `prune`). Writes fire **only at the Verifier PASS checkpoint** and only when the existing
  `continuous-learning` reusability+novelty rubric scores >= 10 — no second scoring scheme, no
  write on RETRY/FAIL, duplicate signatures refused, slugs constrained so an entry cannot
  escape the ledger directory. The debugger gains a **Phase 0** that greps the ledger before
  any fresh diagnosis and reports the known root cause (after re-validating it) instead of
  re-deriving it; retrieval is pull-only — never auto-injected into context or CLAUDE.md — and
  keyword-based, so there is no index and no new dependency. Ledger hygiene rides the existing
  periodic backlog/docs-drift sweep: `prune` archives entries whose referenced files are all
  gone. Scope is project-local; cross-project promotion to `~/.claude/skills/learned/` is an
  explicit future phase. Behavioral coverage in `tests/test_knowledge_ledger.py`.
- **Supply chain hardened: every external ref is now pinned, and CI keeps it that way.**
  `security.yml` was still on mutable action tags (`@v4`, `@v5`) and ran with the default token
  scope; it is now SHA-pinned with `permissions: contents: read`, and all three workflows carry
  precise `# vX.Y.Z` comments. The MCP template no longer fetches `@latest`: all five servers are
  pinned to exact versions and the filesystem server ships **read-only** (`--allow-write` is now
  a documented opt-in), with a "what this grants" disclosure in `templates/mcp/README.md`.
  `tests/requirements.txt` became a fully hash-pinned lock generated from the new
  `tests/requirements.in`, installed in CI and release with `--require-hashes`. A new
  `supply-chain-pins` CI job fails on any unpinned `uses:` ref or any `@latest` under
  `templates/mcp/`, and three new `tests/test_mcp.py` assertions enforce the MCP pins. Dependabot
  now also watches the test lock. Release signing, SHA256SUMS and the repo-slug claim remain open
  (task 014 steps 5-7) -- they need a real release and an owner account action.
- **Queued ops configs are now validated against HEAD by the test suite.**
  `test_queued_ops_configs_validate_against_head` runs `validate-config-json.py` over
  every non-archived `.claude/plans/*.json`; a config whose anchors no longer match the
  tree fails the suite instead of failing (or mis-applying) at execution time. Spent or
  stale configs move to the new `.claude/plans/archive/` (see its README). Found live:
  the archived `ops-review-approval-binding.json` was never executed, its anchors target
  the pre-fix `review.md`, and its replacement text would have reintroduced the
  `PLAN TO REVIEW: $PLAN_CONTENT` payload leak — it must be regenerated under the
  path-not-payload contract before being pursued.
- **Zero-LLM-cost regression test for the delivery-transport contract**
  (`tests/test_delivery_contract_smoke.py`). Extracts `/plan`'s actual scripted-path
  bash block and runs it against a stub `claude` binary that emits a ~40KB fake
  plan+ops payload (matching the scale of the originally observed leak); asserts
  the payload lands on disk and validates but never reaches stdout, and stdout
  stays within the documented ≤15-line summary limit. A companion test assembles
  `/refine`'s documented 2-iteration single-script design the same way and asserts
  both iterations write the same fixed `PLAN_FILE`/`OPS_FILE` in place with only
  scoreboard-sized stdout. Pins the transport behavior mechanically so a future
  change can't silently reintroduce either leak.
- **The shell-lint DoD gate is now surfaced, never silent.** CI always ran shellcheck,
  but locally an uninstalled shellcheck meant the documented DoD command simply errored
  and sessions worked around it. `ck doctor` now warns (with the install command) when
  shellcheck is off PATH, and `tests/test_shell_lint.py` runs it per-script when present
  — 21 visible PASS lines, or 21 visible SKIPs naming the install command when absent.
- **Review verdicts are now bound to the artifact they approved.** `/review` recorded
  nothing beyond stdout, so an approved ops.json could be edited post-approval with no way
  for `/implement` to detect it — this happened for real during this session (see
  `plan-review-approval-binding.md`). `review-record.py` hashes ops.json at review time,
  gates `/implement` on a matching APPROVED/`>=90` record, and offers delta review (diff +
  prior findings, score withheld) for small post-approval edits so re-approval doesn't cost
  a full review every time.

### Fixed
- **`/refine` iterations 2+ now delta-review instead of full re-reviewing.** Every
  refine iteration spawned a fresh reviewer that re-read the whole plan + ops.json +
  code (~100k tokens per round; a live 5-iteration run burned ~600k). Cycle B now
  records each verdict via `review-record.py` and hands the next reviewer only the
  diff + the prior findings (sonnet for deltas; full review only when the diff tool
  demands it). Paired convergence rules: defects in sections the delta didn't touch
  that no prior review flagged go to `FOLLOW_UPS` — reported, but excluded from
  `CRITICAL_MAJOR_COUNT` and the score — and two consecutive sub-threshold rounds
  with disjoint findings STOP the loop for a user decision. Fixes both failure
  modes observed live: per-round full-read cost and moving-target scoring that
  never terminates (83 → 88 → new scope each round).
- **`/refine`'s headless iteration-1 planner message was self-contradictory.** It told
  the planner to "report only a short summary" while the wrapper's only delivery channel
  is stdout-to-file — a compliant planner would produce a plan file with no ops.json,
  and the loop would die with "IRON LAW violated" on the very first iteration. Now tells
  the planner its stdout IS the payload, matching iteration 2+'s (already-correct)
  framing.
- **`suggest-compact.sh`'s `PostToolUse` matcher lost Read/Grep/Glob/Task coverage.**
  Narrowed to `Edit|Write|Bash` when the hook was fixed from a no-op `PreToolUse` entry
  earlier — but exploration-heavy tool calls are exactly what ballooned the originally
  observed sessions to 300k+ tokens. Restored to `""` (all tools); also added
  `cd "$ROOT"` to the wrapper so the hook's relative counter-file path can't drift if a
  session's cwd wanders (harmless while the hook was a no-op, now load-bearing).
- **`/review` had the same `PLAN TO REVIEW: $var` leak `/refine` had.** It `cat`'d the
  whole plan file into `$PLAN_CONTENT` and interpolated it into the reviewer prompt every
  run. Now derives the paired `ops-*.json` path from the plan filename and hands the
  reviewer both paths to Read itself — the plan body never enters the main context.
- **The path-not-payload contract is now written down.** `.claude/agents/_shared/
  INVOCATION.md` gained an explicit "Delivery contract" section (interactive spawns write
  their own artifacts and return paths; headless spawns' stdout is redirected straight to
  disk, never teed/echoed); `HANDOFF_PROTOCOL.md`'s handoff rules and `planner.md`'s
  Phase 4 (Save Outputs) now state the same rule explicitly, so future commands/agents
  don't regress `/plan` and `/refine`'s fix.
- **`/plan` leaked its full payload into the main session context twice per cycle.**
  The scripted path piped the entire planner output through `tee`, printing the full
  plan+ops.json as Bash stdout; the interactive path told the planner to return the
  complete plan in its response and then had the main agent re-type it through Write
  (the source of a measured 42,665-char Write). Scripted path now writes silently
  (`printf > file`, no `tee`) and reports only paths + a ≤15-line summary (op count,
  validation verdict, first 3 plan lines). Interactive path now has the planner write
  `.claude/plans/plan-*.md` and `ops-*.json` itself (nothing in this repo's hooks blocks
  an interactive Task-subagent writing to `.claude/plans/` — verified) and return only
  paths + a short summary; the main agent re-validates once but never Reads the plan
  body back into context.
- **`/refine` pasted the full plan into the reviewer's prompt every iteration.** The loop
  stored the plan in a `current_plan=$(...)` shell variable in one Bash call and consumed
  it in a later call (`PLAN TO REVIEW: $current_plan`) — shell state doesn't persist across
  Bash tool calls, so the main agent hand-pasted the entire plan into the reviewer message
  each time (the observed ~26k-token heredoc leak), and each revision iteration re-emitted
  the complete plan + a new ops.json from scratch. `/refine` now fixes `PLAN_FILE`/`OPS_FILE`
  paths once before iteration 1; the planner writes/edits those files in place (interactive:
  via Task-tool Write; scripted: the wrapper script saves stdout to disk, never `echo`s it),
  and the reviewer is handed only the two paths to Read itself. Only the per-iteration
  scoreboard (`=== REFINE REVIEW ITERATION N ===`, a dozen lines) ever enters context.
- **`suggest-compact.sh` context-budget nudge was a complete no-op.** It was registered
  as `PreToolUse` (whose stdout is never shown to the model) and additionally ran its
  tip from a backgrounded subshell with a trailing `&` on the settings entry too, so the
  "run /compact" tip was double-detached from stdout regardless of hook event. Moved to
  `PostToolUse` (matcher `Edit|Write|Bash`, no trailing `&`), counter/tip logic now runs
  in the foreground (still <100ms, file-touch only), and the nudge cadence tightened from
  every 50 tool calls to every 40 with a stronger message. Still `exit 0` always
  (non-blocking).
- **`command-guard.sh` was fail-open by default.** The default `standard` profile
  only *warned* about a validator-flagged Bash command; nothing was actually
  denied unless a project opted into `strict`. `standard` now blocks a flagged
  command and an unparseable payload, matching the documented "denylist" framing.
  One narrower permissive path remains, kept deliberately and documented: if the
  `claude-kit` package isn't installed, the validator can't run at all, and
  blocking every Bash command in that state would brick installs that ship
  `.claude/` without the Python package — `standard` still warns there, `strict`
  blocks it too. `docs/HOOKS.md`, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, and
  several `.ai/*` files described the old warn-only behavior; updated to match.
- **`pre-commit.sh` ran `config.json`'s `project.build_cmd` unscreened.** It was
  handed straight to `bash -c` on every commit touching source files — a
  malicious or corrupted `config.json` (e.g. from a checked-out branch) was
  arbitrary code execution on `git commit`. It's now screened through the same
  CommandValidator that gates the Bash tool before running, and `config.json`
  is refused outright if it's a symlink.
- **Audit-log forging in `command-log-audit.sh`.** The hook wrote the raw Bash command
  straight into `bash-commands.log`, so a command containing embedded newlines could forge
  additional, fake audit entries (attributing arbitrary commands to arbitrary directories).
  `\n`/`\r` are now escaped before the line is written; regression test asserts a forged
  entry stays on a single log line. Low severity — a local audit trail, and anyone running
  the command already has local execution — but the log is now trustworthy as evidence.
- **Agent registration was silently broken for all 28 agents.** Bare `<example>` blocks
  between YAML frontmatter fields made every agent file unparseable, so Claude Code
  registered none of them — both the Task tool and `claude -p --agent <name>` failed with
  "agent not found", disabling the kit's entire dispatch layer (`/plan`, `/review`,
  `/refine`, `/audit`, ...). Examples now live inside the `description:` block scalar
  (routing signal preserved); verified post-fix: `claude -p --agent explore` resolves and
  completes (measured ~13s cold boot). This also resolves the Task-tool-vs-`claude -p`
  contradiction: local agents register fine once frontmatter parses — `INVOCATION.md` now
  documents both mechanisms (Task tool default in-session; scoped `claude -p` for
  scripted/CI paths with the cold-boot cost stated). Structural regression test added.
- **Headless pipeline was broken at the save step (found by end-to-end test).** `claude -p`
  spawns cannot write into `.claude/**` — the platform's sensitive-path gate requires
  interactive approval and no `--allowedTools` grant or settings allow rule bypasses it
  (all three tested). The planner burned turns retrying blocked Writes and ended asking a
  human who isn't there. Now: stdout is the explicit headless delivery contract — the
  planner emits plan + ops.json in its response, `/plan` and `/refine` save via tee and the
  restored `extract-json-from-plan.py` ops script (recreated; it existed only in pre-2.0
  installs), then validate. The implementer likewise no longer stalls when verification
  commands exceed its scoped tool grant — it reports "executed, verification pending" and
  hands off to the verifier. E2E pipeline validated on a fixture: plan(opus $0.68) →
  review(opus $0.18, refutation ran) → implement(sonnet $0.36) → verify(sonnet $0.64,
  scores matched ground truth) ≈ $1.86. `ck doctor` now checks the extract script ships.

### Added
- **`web-researcher` agent (haiku) — the only agent that calls WebSearch/WebFetch.** The
  main agent and planner must delegate external lookups to it; it reads pages inside its own
  context and returns a distilled answer instead of raw page content, with results cached to
  `.claude/reports/research/`. For library/framework/API docs, context7 MCP is tried first.
- **Coordinator Orchestration Protocol v2.** Triage table (trivial fast-path / single task /
  decompose), file-ownership map so no two sub-plans ever write the same file, parallel
  read-only plan+review fan-out, a composition gate that dry-runs all approved ops.json
  files together before anything touches the tree, and disjoint-set parallel execution.
- **Codex CLI mirror.** `.codex/` (28 agents, 26 hooks, `config.toml`) + `.agents/skills/`
  (75 skills) + a Codex-flavored `AGENTS.md`, so the same prompt corpus runs under Codex CLI.
- **Behavioral eval framework (task 010).** `claudekit eval` + `scripts/run-evals.py` +
  `evals/`: each eval spawns a real agent in an isolated fixture workspace and asserts on
  behavior, not prompt text — planner artifacts extractable + validator-APPROVED, reviewer
  verdict-block format + refutation catches a planted phantom-file defect, implementer
  never fabricates verification it couldn't run, verifier numbers match executed ground
  truth. Four evals derived from the 2026-07-08 E2E pipeline run; per-eval cost budgets;
  `--dry-run`/`--list` are free and covered by offline tests. This makes the quality gates
  mechanically checkable instead of prompt-enforced-only.

### Changed
- **Ops engine no longer loses the original file on a multi-operation rollback.**
  `execute-json-ops.py` backed up a file on *every* operation touching it, so a second
  operation overwrote the pristine backup with already-mutated content — a later failure
  then "rolled back" to that intermediate state, and `restore-backup.py` / `/rollback`
  restored the wrong content. Backups are now first-write-wins per run.
- **Ops engine fails closed on anchor drift at apply time.** An edit whose `find` pattern
  is missing or ambiguous in the current (already-mutated) content now aborts and rolls
  back, instead of skip-and-continue with first-occurrence replacement. Dry-run threads
  simulated file state across operations so previews match real sequential execution, and
  the engine prints a unified diff plus a machine-readable `RESULT-JSON:` summary line on
  config load/normalize error, lock contention, manifest failure, operation failure,
  crash, and signal; absence of the line means the process never reached a reported
  exit path (killed outright, or failed before execution began).
- **Validator simulates edits cumulatively.** `validate-config-json.py` GUARDs 10/11 now
  validate each anchor against the content as it will exist when the executor reaches
  that edit — within an operation and across operations on the same file.
- **Implementer contract: reactive reads.** The implementer now validates (a mandatory step
  its own spec previously omitted), dry-runs, and executes by passing paths to the ops
  scripts, and relays the engine's diff and `RESULT-JSON` output as evidence; it reads
  target files only to diagnose reported failures. Mirrored into the Codex corpus.
- **Per-agent model routing tuned for token economy.** `reviewer` opus → sonnet (escalates
  to opus per-call for multi-phase, architecture-touching, or security-relevant plans),
  `implementer` and `explore` sonnet → haiku. `planner` stays opus. The surviving invariant
  is "a quality gate never runs on haiku", not "the reviewer is always opus" — the routing
  spec test now encodes that, and requires the escalation path to stay documented.
- **Hooks no longer break in non-git projects.** All 21 hook wrappers resolved the
  project root with bare `git rev-parse --show-toplevel` — in a project without `.git`
  (e.g. qa-agents) every hook tried to run `/.claude/hooks/...` at the filesystem root and
  failed on every session. Root resolution is now `CLAUDE_PROJECT_DIR` → git → `pwd`;
  verified by executing the real session-start wrapper in a non-git sandbox.
- **Pipeline commands are dual-mechanism.** `/plan`, `/review`, `/refine` name the Task
  tool as the interactive default (local agents register post-frontmatter-fix; no cold
  boot, shared MCP/permissions) and keep scoped `claude -p` as the scripted/CI path — one
  delivery contract for both. The verifier now scopes lint/types/coverage to the changed
  files (full test suite always); `--all` forces the repo-wide audit pass. The
  PostToolUseFailure hook's embedded Python was a guaranteed SyntaxError, logging every
  failed tool as "unknown" — fixed, failures now log the real tool name.
- **Context budget: lazy skill loading (task 009 core).** Agents no longer preload their
  whole skill list: each declares ≤3 mandatory skills (`using-superpowers` + role-core) and
  moves the rest to an explicit on-demand tier with per-skill load triggers ("load when the
  work touches auth/input/secrets", ...). Mandatory preload drops 16,120 → 6,649 lines
  across the 18 skill-loading agents (−59%); coordinator alone 2,397 → ~350 lines. Effort
  is unchanged — the operating rules live in the always-present `_shared` docs; skill
  bodies are depth that loads exactly when the trigger fires.
- **skills-registry.json is now generated, not hand-maintained.** New
  `scripts/gen-registry.py` derives `agentMapping` from the agent files' Skill Loading
  sections (single source of truth) with a `--check` drift gate wired into the test suite
  — the audit had found 10 mapped agents with no skill section and 2 commands mapped as
  agents; the mapping is now 18 honest entries. Budget gate tests: max 3 mandatory skills
  per agent, every on-demand entry must declare its trigger.
- **Frontier-behavior corpus upgrade.** Audited all shared agent docs, 10 core agents, 14
  core commands, and the load-bearing skills against a 10-pattern operating spec (parallel
  batching, persistence, verification, adversarial self-check, evidence integrity, calibrated
  autonomy, read-before-conclude, context economy, root-cause discipline, resumable
  decomposition) so Opus/Sonnet agents operate at frontier level. Highlights:
  - "Batch independent tool calls in ONE message" is now mandated corpus-wide
    (AGENT_TEMPLATE, using-superpowers, TASK_TOOL_SPECIFICATION, coordinator, and the
    verify/debug/explore/audit/santa/plan workflows). The "3+ problems before parallelizing"
    gate is gone (2+ suffices).
  - New mandatory **Refutation Pass** before any PASS/clean/complete claim
    (VERIFICATION_PROTOCOL + verification-before-completion): what breaks it, what wasn't
    run, which claim rests on prose.
  - Evidence integrity: numbers must come from executed output; evidence is exempt from
    silent-mode token caps; templates no longer pre-print fake evidence (refine success
    banner now actually runs the validator + dry-run; loop-start gate lines quote real
    results); token-optimization can never compress verification evidence.
  - Persistence: retries must change approach (never verbatim — including coordinator error
    recovery); executing-plans' mid-plan "Continue?" permission loop removed — an approved
    plan is the permission; checkpoint to files instead.
  - Fixed unexecutable contracts: 8 commands' broken `@agents/` references (the delegated
    agent specs never loaded); reviewer `--dual` no longer tells a spawn-less agent to spawn
    (orchestrated by the command layer); planner frontmatter reconciled with INVOCATION.md
    (Write granted, Agent removed, Bash scoped to the ops validator); INVOCATION.md tool
    table extended from 2 to 10 roles.
  - Model routing: planner sonnet→**opus** (feeds the ≥90 plan gate), verifier
    haiku→**sonnet** (scores a hard ≥80 gate); coordinator stays sonnet (routing is
    table-driven). 24 anchor tests (`tests/test_behavior_spec.py`) pin all of the above.

### Added
- **Legacy-install lifecycle support.** Installs that predate the v2.1 manifest are no
  longer locked out of the lifecycle commands:
  - `claudekit diff` falls back to comparing managed assets (`agents/ commands/ skills/
    hooks/ operations/scripts/ settings.json`) against the kit source when no manifest
    exists, classifying files as `identical` / `differs` / `custom` / `not installed`.
  - With a manifest **and** kit source available, `diff` refines `modified` into
    `locally modified` / `kit-updated` / `both changed`, and lists project-added
    `custom` files.
  - `claudekit update` now works on pre-manifest installs (confirmation-gated full-mode
    reinstall that writes a manifest for next time).
  - The installer preserves project-custom assets across reinstalls: backup files not
    tracked by the old manifest (or, for pre-manifest backups, anything under
    `agents/ commands/ skills/`) are restored into the new tree instead of being
    stranded in `.claude.bak-*`. Old kit-managed files are never resurrected when a
    manifest exists.

### Security
- **Wired the security layer (was dead code).** `CommandValidator`/`PathGuard` are now
  reachable in production via a `PreToolUse` Bash guard (`.claude/hooks/command-guard.sh`)
  and the `claudekit check-command` / `check-path` CLI. Framed honestly as a **denylist
  speed bump, not a sandbox**.
  - `CommandValidator.from_config` now reads the `security` section (was `hooks` — user
    `safeMode`/`allowedCommands` were silently ignored).
  - Inspects every segment of a chained command (`; && || |`) plus `$(...)`/backtick
    substitution payloads, not just `argv[0]`. `bash`/`sh`/`env`/`xargs` removed from the
    allowlist (payload smuggling). Added `find -delete/-exec`, `${IFS}` evasion, and Python
    `os.system`/`subprocess`/`__import__` interpreter-smuggling detection.
  - `PathGuard`: relative symlinks resolved against the link's directory; protected patterns
    (`.env`, `.git/config`, …) matched per path component (`my.envelope.txt` no longer blocked).
  - Guard rollout gated by `ECC_HOOK_PROFILE`: `strict` blocks (fail-closed), `standard`
    warns (default), `minimal` off.

### Changed
- Packaging: fixed the `pyproject.toml` build backend; moved to true `src/claudekit/`
  src-layout; single version source via `importlib.metadata`.
- Prompt layer: planner ops.json schema now references the canonical
  `generate-operations-config` schema; `execute-operations-config` drives all changes through
  `execute-json-ops.py` (no manual Edit/Write).
- Docs: rewrote `docs/HOOKS.md` around `settings.json` + `ECC_HOOK_PROFILE` (the real model);
  corrected the canonical repo slug to `OmarMokhtar-Saad/claudekit` everywhere;
  `docs/ARCHITECTURE.md`/`SECURITY.md` now describe what actually runs.

### Added
- `/adapt` command + `project-adaptation` skill: adapt ClaudeKit to any project and
  language (including stacks without a dedicated template) — detect installation
  state, learn the project, configure `config.json` commands / `CLAUDE.md` /
  `CONSTITUTION.md` / hook profile / `.agentignore`, verify with evidence
  (hook block test, ops round-trip, `ck doctor`), and record adaptation decisions.
- CLI install-lifecycle commands built on the install manifest (`.claudekit-manifest.json`):
  `claudekit diff` (show locally-modified managed files), `claudekit update` (re-install over an
  existing project, warning before overwriting local edits; installer backs up first), and
  `claudekit uninstall` (remove managed files to a recoverable backup). Plus `ck init
  --full/--minimal/--yes` and `ck doctor --strict`.
- `MAX_DELETIONS` guard (max 3 `file_delete` operations per plan) in the ops validator.
- `scripts/gen-docs.py` — generates component counts from the filesystem and, with `--check`,
  fails CI when any doc hard-codes a stale count (the new `docs-drift` gate).
- CI: whole-suite test job, macOS matrix, `install.sh → doctor` integration job, coverage
  gate, `ruff`/`mypy` lint, dangling-hook-path check, and SHA-pinned actions + Dependabot.
- Wheel now bundles the runtime asset tree (`setup.py` → `<prefix>/share/claudekit`), so a
  plain `pip install` is self-contained and `ck init` works with no source checkout.

### Fixed
- Packaging: `find_claudekit_root` resolved to `src/` (not the repo root) after the src-layout
  move, breaking `ck init`; now walks up to `.claude/agents`. `CLAUDEKIT_HOME` is honored.
- `skills-registry.json`: `documenter` referenced a non-existent skill (`i18n-workflow` →
  `i18n-patterns`), which failed the validate-registry gate.
- Installer: template rendering used `sed s|{{X}}|$VAL|` — values with `&`/`|`/`\` (e.g.
  `npm run build && npm test`) corrupted output; replaced with literal Python substitution.
  C# detection now searches subdirs for `*.csproj`/`*.sln`. `set -E` so staging cleanup fires
  on a helper failure. `settings.local.json` is preserved across a reinstall.
- Hooks: `suggest-compact` daily reset was GNU-`date -r`-only (broken on macOS) — now stores the
  date in the counter file, with stale-lock cleanup. `format-typecheck` read edited files from
  the wrong log (Bash commands, not Edit/Write targets) — now uses a dedicated `edited-files.log`.
  `auto-checkpoint` stored a positional `stash@{0}` ref that pruned the wrong stash — now uses the
  stable stash SHA. Wired the dormant `file-guard`/`prompt-injection-scanner` as advisory hooks.
  Fixed the latently-red shellcheck CI job (`.shellcheckrc`).

## [2.1.0] — 2026-04-11

### Added

#### Agents (6 new — total: 28)
- **code-reviewer** (Opus) — Reviews actual code/diffs with 5 dimensions: Correctness, Security, Performance, Reliability, Code Quality; confidence-filtered findings with file:line references
- **build-error-resolver** (Sonnet) — Minimum-diff error fixer; THE ONE RULE: fix the error only; max 7 iterations; never uses `@ts-ignore`
- **loop-operator** (Sonnet) — Autonomous loop monitor with 3 intervention levels: Warn, Pause+Report, Emergency Stop; stagnation detection
- **opensource-sanitizer** (Sonnet) — Stage 1+2 of open-source pipeline; BLOCKER/WARNING classification across 6 categories (secrets, infra, PII, tooling, legal, artifacts)
- **opensource-packager** (Haiku) — Stage 3 of open-source pipeline; generates CLAUDE.md, README, LICENSE, .env.example, CONTRIBUTING.md, .github/ templates from actual code
- **model-router** (Haiku) — 4-dimension scoring rubric (reasoning depth, output complexity, error cost, domain novelty) → haiku/sonnet/opus recommendation

#### Skills (6 new — total: 73)
- **santa-method** — Adversarial dual-review: Skeptic (Opus) + Pragmatist (Sonnet) spawned simultaneously with no shared context (anti-anchoring)
- **hookify** — Analyzes behavior patterns → classifies tool call → generates prevention hook → settings.json diff → verification tests
- **context-keeper** — Structured save/resume: required fields, freshness validation (<4h full trust, 4-24h verify, >72h warn stale)
- **prp-plan** — Product Requirements Process plan phase: "A fresh agent with this plan should implement correctly without re-exploring"
- **gan-harness** — GAN-style generate-evaluate-iterate loop; anti-anchoring Evaluator spawned fresh each iteration; configurable threshold and max iterations
- **opensource-pipeline** — 3-stage hard-gated pipeline; Stage 2 only runs if Stage 1 PASSES; never modifies original source

#### Commands (13 new — total: 37)
- **/santa** — Dual adversarial review with anti-anchoring; `--strict` raises threshold to 95/100
- **/hookify** — Generate hook from behavior description or session transcript
- **/save-session** — Serialize session state to `.claude/session-context.md`
- **/resume-session** — Load and validate saved session context with freshness check
- **/model-route** — Route a task description to optimal model with scoring breakdown
- **/prp-plan** — Phase 1: deep recon → context-rich plan document (the "contract")
- **/prp-implement** — Phase 2: execute plan with per-step verification and 6-gate final check
- **/prp-commit** — Phase 3: natural-language file targeting → smart conventional commit
- **/prp-pr** — Phase 4: auto-discover PR template, generate description from commits and plan
- **/build-fix** — Fix build/type errors with minimum diff; max 7 iterations; never suppresses
- **/code-review** — Review files, directories, or GitHub PRs with ranked findings report
- **/gan-build** — GAN harness command: `--mode fast|standard|quality|strict`, `--threshold N`, `--max-iter N`
- **/opensource** — Full 3-stage open-source pipeline: `--sanitize-only`, `--package-only`, `--license MIT|Apache|GPL`
- **/loop-start** — Start monitored autonomous loop: `--agent <name>`, `--max-iter N`, `--stall-after N`

#### Hooks (6 new — total: 15)
- **config-protection.sh** (PreToolUse) — Blocks edits to ESLint, tsconfig, Prettier, Biome, pyproject and 15 other config files; respects `ECC_HOOK_PROFILE`
- **commit-quality.sh** (PreToolUse/Bash) — Warns on generic messages, debug artifacts; BLOCKS on staged secrets (`.env`, `.pem`, `.key`)
- **security-reminder.sh** (PreToolUse/Write) — Non-blocking warnings for `shell=True`, SQL concat, `innerHTML`, TLS disabled, weak crypto, permissive CORS
- **suggest-compact.sh** (PostToolUse, async) — Suggests `/compact` every 50 tool calls; daily counter reset
- **session-start.sh** (SessionStart) — Detects package manager, loads config commands, prints startup summary, auto-loads recent session context
- **format-typecheck.sh** (Stop, async) — Runs Biome/Prettier + `tsc --noEmit` on all JS/TS files edited in session; strict mode only

#### System
- **ECC_HOOK_PROFILE** env var — `minimal|standard|strict` controls hook activation without file edits
- **Anti-anchoring protocol** — Both Santa reviewers and GAN Evaluators spawned with no shared context or prior conversation history
- **PRP lifecycle** — 4-phase workflow (plan→implement→commit→PR) where each phase is a dedicated command with explicit handoff contract

### Fixed
- `pre-commit.sh` path: `find operations/ -name "ops.json"` → `find .claude/plans/ -name "ops-*.json"` (planner writes to `.claude/plans/`)
- `skills-registry.json` `agentMapping` structure: confirmed as dict (agent_name → list of skill IDs), not a list
- Documented component counts corrected to match the filesystem: 28 agents / 39 commands / 73 skills / 19 hooks, now generated and CI-enforced by `scripts/gen-docs.py`

## [2.0.0] — 2026-03-17

### Added
- **7 Behavioral Modes**: default, brainstorm, token-efficient, deep-research, implementation, review, orchestration
- **5 MCP Server Configurations**: Context7, Sequential Thinking, Playwright, Memory, Filesystem
- **Universal Command Flags**: --mode, --depth, --format, --persona, --save, --checkpoint
- **Spec-Driven Development Workflow**: /specify, /clarify, /analyze, /checklist commands
- **Security Hooks**: file-guard (195+ patterns), check-comment-replacement, prompt-injection-scanner
- **Checkpoint System**: /checkpoint create/restore/list with auto-checkpoint hook
- **Parallel Execution**: /spawn, /batch, /ship commands for parallel agent work
- **International Support**: READMEs in Arabic, Chinese, Spanish, French, Japanese, Korean
- **10 Advanced Skills**: token-optimization, codebase-mapping, session-continuity, autonomous-loop, context-priming, hook-profiling, safe-command-approval, usage-monitoring, prompt-injection-defense, incident-response
- **/translate command**: Multi-language documentation translation
- **/mode command**: Switch behavioral modes per session
- **/index command**: Generate project structure index
- **/load command**: Context loader for project components
- **/flags command**: Universal flags reference
- **.agentignore template**: Gitignore-style file for AI agent access control
- **i18n-workflow skill**: Internationalization patterns and RTL support
- **mcp-integration skill**: MCP server usage guidelines
- **spec-driven-development skill**: Specification-first workflow patterns
- **command-flags skill**: Universal flag parsing system

### Changed
- Bumped version to 2.0.0
- Expanded skill count from 45 to 55+
- Expanded command count from 17 to 27+
- Added modes directory to template structure
- Added mcp directory to template structure
- Added i18n directory with 6 language translations

## [1.1.0] - 2026-03-16

### Added
- 4 new agents: tester, security-scanner, devops, database-architect (total: 13)
- 9 new commands: /explore, /security, /deps, /rollback, /test, /deploy, /performance, /migrate, /batch (total: 17)
- 18 new skills including Trail of Bits-inspired security skills, enterprise patterns, and i18n/a11y (total: 45)
- 4 new language templates: Rust, C#, Ruby, PHP (total: 11)
- Official Claude Code hooks via .claude/settings.json (7 event types)
- Professional README with shields.io badges and comprehensive documentation

### Fixed
- 43+ bugs fixed across security, cross-references, and compliance
- All agent frontmatter updated with tools and example blocks per Claude Code official docs
- All skill frontmatter updated with disable-model-invocation, user-invocable, allowed-tools
- Hooks format migrated from custom config.json to official Claude Code settings.json
- Kotlin language detection now works correctly (moved before Java check)
- Template {{PROJECT_NAME}} substitution now works for all language templates
- Command injection vulnerabilities fixed in all hook scripts
- install.sh config.env sourcing security hardened

## [1.0.0] - 2026-03-16

### Added
- 9 specialized agents: coordinator, planner, reviewer, implementer, verifier, debugger, documenter, gitOps, explore
- 8 slash commands: /plan, /review, /implement, /verify, /debug, /docs, /git, /coordinator
- 27 generic skills covering planning, review, implementation, testing, debugging, git, and more
- 5 workflow hooks: pre-commit, post-implement, pre-plan, pre-push, post-tool-use
- Operations system with validate, execute, and restore scripts (CodeManifest v3.1.0)
- One-command installer (`install.sh`) with language detection
- 7 language templates: Python, TypeScript, Java, Go, Kotlin, Swift, Generic
- 2 complete examples: Python/FastAPI and TypeScript/Next.js
- CLAUDE.template.md and CONSTITUTION.template.md for project customization
- Shared agent templates and protocols
- Skills registry for agent-skill mapping
- Comprehensive documentation (Architecture, Customization, Agents, Skills, Hooks, Constitution Guide)
- CI/CD pipeline with GitHub Actions
- Issue and PR templates

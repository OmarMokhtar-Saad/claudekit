# Specialist Agents: loop-operator, opensource-sanitizer, opensource-packager, model-router

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## loop-operator

**Purpose.** Supervisor for autonomous agent loops: detects stagnation, error spirals, and runaway iterations; pauses loops with a clear status report; issues emergency stops on destructive operations.

**Inputs.** Loop state + iteration logs. **Outputs.** Healthy Loop Report, Pause Report (Level 2, with last-3-iteration pattern analysis and human options), or Emergency Stop Report (Level 3, with detected operation, danger explanation, last safe state, rollback command).

**Frontmatter (verbatim).**
- `name: loop-operator`
- `description: Monitors and safely intervenes in autonomous agent loops. Detects stagnation, error spirals, and runaway iterations. Pauses the loop and reports state when intervention is needed. Use as a supervisor when running long autonomous loops.`
- `model: sonnet` | `color: purple`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Phase 1 assess loop state (read `.claude/state/loop-<task-id>.json`, last N iteration outputs, iteration count vs max) → Phase 2 detect problems via the stagnation table (2+ identical outputs; 3 iterations of error growth; ≥3 iterations with no file changes; max iterations reached; same tool+args 3+ times) → Phase 3 decide level (1 Warn and continue; 2 Pause + report requiring a human decision; 3 Emergency Stop for `git push --force`, `rm -rf`, `DROP TABLE`, security violations, safety bypasses) → Phase 4 report.

**Dependencies.** Skills: `using-superpowers`, `autonomous-loop`. References `/rollback` and `/loop-start` command territory (see [./COMMANDS.md](./COMMANDS.md)). Level 1 warnings log to `.claude/hooks/hooks.log`.

**Memory/context.** Reads `.claude/state/loop-<task-id>.json` (read-only — "NEVER modify loop state files") and loop logs; writes warnings to `.claude/hooks/hooks.log`.

**Failure recovery.** It IS the recovery mechanism: never continues a loop classified Level 2/3, never runs extra iterations to "verify," never dismisses stagnation signals, never intervenes in healthy loops.

**Example invocation.**
```bash
echo "The build-fix loop seems stuck. Inspect .claude/state/loop-*.json, check the last 5 iterations, and decide the intervention level." | \
  claude -p --agent loop-operator --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** One frontmatter example. Slight tension between "read-only monitoring" and logging warnings to hooks.log (done via Bash append since it has no Write tool).

---

## opensource-sanitizer

**Purpose.** Stage 1 of the open-source release pipeline: read-only scan for secrets, internal infrastructure, PII, internal tooling references, license/legal issues, and development artifacts. Hard gate: downstream stages (Forker, Packager) may only run on PASS.

**Inputs.** The codebase to be released. **Outputs.** `OPEN-SOURCE SANITIZATION REPORT` with `VERDICT: PASS | FAIL` (FAIL = any BLOCKER finding), findings grouped BLOCKER/HIGH/MEDIUM/SAFE with redacted matches, and next-step commands (`/opensource --sanitize-only`, `/opensource --package-only`).

**Frontmatter (verbatim).**
- `name: opensource-sanitizer`
- `description: Scans a codebase for secrets, internal references, employee names, and private infrastructure details before open-sourcing. Produces a PASS/FAIL report with specific file:line findings. Stage 1 of the open-source pipeline — Stage 2 (forker) only runs if this PASSES.`
- `model: sonnet` | `color: red`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Phase 1 scope (list non-binary files, skip binaries, check .gitignore efficacy) → Phase 2 parallel scan of six categories (secrets/credentials incl. AWS keys, GitHub PATs, private keys, connection strings; internal URLs and private IP ranges; PII incl. employee emails/names/phones; internal tooling refs; license/legal incl. GPL disclosure; dev artifacts incl. production data fixtures and committed .env) → Phase 3 false-positive filter (`*.example`, placeholders, vendored dirs, synthetic fixtures) → Phase 4 verdict and report.

**Dependencies.** Skills: `using-superpowers`, `security-checklist`, `supply-chain-audit`. Downstream: opensource-forker (Stage 2 — referenced but **no agent file exists**), opensource-packager (Stage 3). Invoked via `/opensource` command flags (see [./COMMANDS.md](./COMMANDS.md)).

**Memory/context.** Strictly read-only; never modifies files. Sanitize reports are checked by the packager at `.claude/reports/sanitize-*.md`.

**Failure recovery.** FAIL verdict blocks the pipeline; user fixes and re-runs `--sanitize-only`.

**Example invocation.**
```bash
echo "Is this repo safe to open source? Run all 6 scan categories and produce the PASS/FAIL report." | \
  claude -p --agent opensource-sanitizer --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** Its own file never states where the report is written; that path convention (`.claude/reports/sanitize-*.md`) only appears in opensource-packager's prerequisite check. The Stage 2 "forker" is a phantom agent.

---

## opensource-packager

**Purpose.** Stage 3 of the open-source pipeline: generates complete release packaging for a sanitized repo — project-specific CLAUDE.md, setup.sh, README sections, LICENSE, CONTRIBUTING.md, GitHub issue/PR templates, and `.env.example`. All content derived from the actual codebase, never generic templates.

**Inputs.** Sanitized codebase (a `VERDICT: PASS` sanitize report must exist). **Outputs.** The 7 artifact groups plus an `OPEN-SOURCE PACKAGING COMPLETE` report listing manual pre-publish steps.

**Frontmatter (verbatim).**
- `name: opensource-packager`
- `description: Stage 3 of the open-source pipeline. Generates complete open-source packaging for a sanitized repo — CLAUDE.md, setup.sh, README.md structure, LICENSE, CONTRIBUTING.md, and GitHub templates. Only runs after opensource-sanitizer PASSES and opensource-forker completes.`
- `model: haiku` | `color: green`
- `tools: ["Read", "Glob", "Bash", "Write"]`

**Internal workflow.** Prerequisite gate (`ls .claude/reports/sanitize-*.md | xargs grep -l "VERDICT: PASS"` — STOP if absent) → Phase 1 analyze codebase (tech stack, package manager, scripts, test framework, linter, directory map) → Phase 2 generate each artifact from real data (CLAUDE.md with actual install/build/test/lint commands; LICENSE detected from manifest license field, MIT default) → Phase 3 verify (README section grep, `chmod +x setup.sh`, no placeholder commands in CLAUDE.md).

**Dependencies.** Skills: `using-superpowers`, `documentation-standards`. Upstream gate: opensource-sanitizer PASS report in `.claude/reports/`. Never commits (GitOps's job).

**Memory/context.** Reads `.claude/reports/sanitize-*.md`; writes release files at repo root and `.github/`.

**Failure recovery.** Hard STOP if no PASS report. Never overwrites a detailed README (appends missing sections only).

**Example invocation.**
```bash
echo "Package this repo for open source release. Verify the sanitizer PASS report first." | \
  claude -p --agent opensource-packager --model haiku --allowedTools "Read,Glob,Bash,Write"
```

**Improvement notes.** Depends on the nonexistent Stage 2 forker in its description. Only agent whose tool list orders `Write` last / omits Grep and Edit.

---

## model-router

**Purpose.** Cost-optimization: scores any task on four 0–3 dimensions and recommends Haiku / Sonnet / Opus, with override rules and relative cost estimates. Runs on Haiku itself "so the routing cost is always worth it."

**Inputs.** A task description. **Outputs.** `MODEL ROUTING RECOMMENDATION` — per-dimension scores with reasons, total /12, recommendation, applied override, reasoning, relative cost table, and the `--model` flag to use.

**Frontmatter (verbatim).**
- `name: model-router`
- `description: Routes tasks to the optimal Claude model (haiku/sonnet/opus) based on complexity scoring, token estimation, and required reasoning depth. Use before spawning expensive agents to optimize cost without sacrificing quality.`
- `model: haiku` | `color: cyan`
- `tools: ["Read"]`

**Internal workflow.** Score Reasoning Depth, Output Complexity, Error Cost, Domain Novelty (each 0–3) → sum: 0–3 Haiku, 4–7 Sonnet, 8–10 Sonnet (heavy), 11–12 Opus → apply overrides (security review → min Sonnet, recommend Opus; code review for merge approval → min Opus; documentation → max Sonnet; routing itself → always Haiku) → emit recommendation. A fast-lookup table maps 17 common tasks to models.

**Dependencies.** Routed via coordinator's "Model Select" row. Referenced relative costs: Haiku 1x, Sonnet 5x, Opus 15x, all 200k context.

**Memory/context.** None — Read-only, single tool.

**Failure recovery.** "NEVER refuse to route — always give a recommendation even if uncertain."

**Example invocation.**
```bash
echo "Which model should I use to design a new auth system?" | \
  claude -p --agent model-router --model haiku --allowedTools "Read"
```

**Improvement notes.** Its override "code review for merge approval → minimum Opus" conflicts with its own lookup table ("Code review (non-critical) | Sonnet") only superficially, but conflicts materially with typescript-reviewer and python-reviewer running on Sonnet while producing merge verdicts (APPROVE/BLOCK). Also lists "Multi-agent coordination | Sonnet", matching the coordinator's model.

---


# Knowledge Base — Philosophies, Patterns, Lessons

The distilled judgment of everyone (human and AI) who has worked on ClaudeKit. Complements [DECISIONS.md](DECISIONS.md) (specific choices) and [MEMORY.md](MEMORY.md) (hard invariants).

## Philosophies

- **Review:** two kinds, never conflated — *plan* review (reviewer, pre-implementation, 90/100) and *code* review (code-reviewer, post-implementation). Findings need file:line references and severity. Adversarial designs (Santa, GAN, council) exist because single reviewers anchor; fresh context per evaluation round is the mechanism, not a nicety.
- **Refactoring:** minimal-diff bias everywhere (build-error-resolver's whole identity); dead-code removal in risk-ordered batches (SAFE→CAREFUL→RISKY); simplification must preserve behavior; consolidation (of the kit's own corpus) beats accretion.
- **Testing:** behavioral over structural. The suite's history is the lesson — ~85% of pre-audit tests were file-existence "theater" while the product was broken; the tests that matter run hooks in subprocesses and assert exit codes, build the wheel and install it in a clean venv, prove secrets block commits. Coverage gate: security module ≥85%.
- **Performance:** the scarce resources are tokens and hook latency, not CPU. Budget context like money (context-budget skill); prefer file references over inline content; cheap models for mechanical steps.
- **Security:** honest denylist framing; fail closed; validate every segment of chained commands; protect files by pattern at multiple layers (PathGuard + ops guards + config-protection hook); never trade the platform's permission system for convenience.
- **Documentation:** filesystem is the source of truth; counts are generated; audience split is strict (users get docs/, maintainers get .ai/); a doc that contradicts the tree is a bug (CI-gated where possible).
- **Prompt engineering:** reference, don't duplicate; examples are load-bearing; constraints as IRON LAW/NEVER with STOP conditions; output contracts machine-parseable where a downstream consumer exists. See [PROMPTS.md](PROMPTS.md).

## Preferred patterns

Staging + backup + atomic swap for anything that overwrites user data · manifest + sha256 for anything updatable · `lib.sh`-style shared helpers over copy-paste (10+ hook variants were consolidated) · deterministic Python for safety-critical paths, prompts only for judgment · hard gates between pipeline stages (opensource Stage 2 only if Stage 1 PASSES) · iteration caps on all loops (build-fix 7, refine/gan configurable) · single-source-of-truth documents (INVOCATION.md, generate-operations-config).

## Anti-patterns (all observed in this repo's history)

Existence-theater tests · exit-1 "blocking" hooks · embedded schema copies that drift · hand-maintained counts · `|| true` in CI · GNU-only shellisms · `--dangerously-skip-permissions` · unbounded deletes · trap-based cleanup that deletes user data · version numbers that go backwards · advertising features that aren't wired (the original "dead security layer" gap between marketing and reality).

## Hidden assumptions

- Hooks assume a **git repo** (`git rev-parse --show-toplevel` with lib.sh fallback) — behavior in non-git dirs is degraded by design.
- Claude Code semantics: PreToolUse exit 2 blocks; stdin JSON payloads; `.claude/` directory conventions; frontmatter-driven agent selection. A Claude Code breaking change is this project's biggest external risk.
- The user's project has *one* root `CLAUDE.md`; ClaudeKit installs and owns specific paths (manifest-listed) and must never clobber `.claude/local/` or `settings.local.json`.
- `python3` and `bash` exist on PATH in user environments; jq is *not* assumed (hooks parse JSON via python3).

## Important edge cases

Single-quoted secrets in diffs (`\x27` regex class) · commit messages via `-m` vs editor (commit-quality parses both) · `git commit --no-verify` disguised with quotes (`--no-ver"ify"`) · relative symlinks resolved against link dir, not cwd · `my.envelope.txt` must not match the `.env` protected pattern (component-level matching) · creating a *new* protected-type file (allowed) vs modifying (guarded) · ops.json with multiple `find` matches (GUARD 11 ambiguity rejection) · macOS BSD vs GNU tool differences.

## Recurring bug classes (watch for)

Path resolution after layout moves (`find_claudekit_root` → `src/` bug) · registry/dangling references when renaming skills · sed template rendering with special chars in values · stale hardcoded expectations in `doctor` when counts change · Python-version matrix issues (setuptools absent on py3.12+ — `0c9223b`).

## Things future models must NEVER change

1. The Iron Law (ops.json mandatory; implementer has no Edit/Write).
2. Fail-closed blocking hooks (exit 2 + stderr).
3. Permission gating (no `--dangerously-skip-permissions`, scoped tools).
4. Protected-file guards and MAX_DELETIONS cap.
5. Golden rule: no code changes without explicit user approval.
6. Honest security framing ("speed bump, not a sandbox").
7. Monotonic versioning with the three synchronized version locations.
8. Generated counts (never hand-edit).
9. macOS/bash-3.2 compatibility.
10. Zero runtime Python dependencies.

## Things future models SHOULD improve

Corpus consolidation (008) · eval-grounded gates (010) · one hook dispatcher per event (009) · true three-way `ck update` merge · plugin packaging (007) · machine-parseable review verdicts · the 16 prompt-layer inconsistencies in [AGENTS.md](AGENTS.md#known-issues) · MCP server pinning · release signing (014) · behavioral test expansion (012) · OSS community health files (013).

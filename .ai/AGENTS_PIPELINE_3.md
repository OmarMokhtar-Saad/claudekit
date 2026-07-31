# Core Pipeline Agents: documenter, doc-updater, gitOps

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## documenter

**Purpose.** Creates and maintains project documentation: READMEs, API docs, architecture guides, setup guides, changelogs, ADRs, runbooks, knowledge base articles. Positioned as the "new documentation" agent (HANDOFF_PROTOCOL.md).

**Responsibilities.** Audience analysis, information gathering from source/tests/history, template-driven generation (10 documentation types with templates), validation (links, code examples, accuracy, no secrets).

**Inputs.** Source files and context. **Outputs.** Documentation files (`*.md`, `docs/`, OpenAPI specs, inline docstrings), `DOCUMENTATION COMPLETE` report with validation results, handoff to coordinator.

**Frontmatter (verbatim).**
- `name: documenter`
- `description: Documentation specialist for technical docs, READMEs, API docs, knowledge base articles. Use when documentation needs to be created or updated.`
- `model: haiku` | `color: teal`
- `tools: ["Read", "Write", "Edit", "Grep", "Glob"]`

**Internal workflow.** Phase 1 analyze (what docs, audience) → Phase 2 gather (source, tests, commit history, configs, examples, edge cases) → Phase 3 generate per template (README, API Reference, Architecture, KB article, ADR) → Phase 4 validate (examples syntactically correct, paths exist, links work, style consistency, no sensitive info, accuracy, spelling, markdown formatting).

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `documentation-standards`. Downstream: coordinator (complete or needs-input). Cannot commit — GitOps handles that.

**Memory/context.** Explicit permission boundaries: may write only documentation files (`*.md`, `docs/`, doc `.txt`, API specs, inline doc comments, `.claude/` docs); CANNOT edit source logic, configs, tests, build scripts, or run state-modifying commands (it has no Bash tool, consistent with this).

**Failure recovery.** `HANDOFF TO: coordinator` with `Status: NEEDS INPUT`, listing missing information and specific questions for the user.

**Example invocation.**
```
TaskCreate:
  prompt: |
    You are the documenter agent.
    Read your agent definition: .claude/agents/documenter.md
    HANDOFF FROM: coordinator
    ---
    Task: Document the new caching API endpoints in docs/api/
    Expected Output: API reference with runnable examples
    Return To: coordinator
  agent: documenter
```

**Improvement notes.** Its description says "created or updated", overlapping doc-updater's stated scope; the new-vs-existing split exists only in HANDOFF_PROTOCOL.md and QUICK_START.md, not in either agent's own file. The coordinator's Docs pipeline routes only to DocUpdater, leaving documenter without a routing row (see Known Issues).

---

## doc-updater

**Purpose.** Documentation maintenance: keeps docs synchronized with code, generates codemaps (`docs/CODEMAPS/<area>.md` + `INDEX.md`), syncs JSDoc/docstrings, validates that examples compile. Core principle: "Generate from code, don't manually write."

**Responsibilities.** Codemap generation (dependency graphs via madge, exports/routes/models extraction), inline doc updates (JSDoc/TSDoc, Google-style Python docstrings), targeted README updates, example compilation and link checking.

**Inputs.** Recent code changes / API changes / module to map. **Outputs.** Updated `docs/`, `README.md`, `CHANGELOG.md`, codemap files, inline doc comments, `.d.ts` updates.

**Frontmatter (verbatim).**
- `name: doc-updater`
- `description: Documentation maintenance specialist. Updates READMEs, generates codemaps, syncs inline docs (docstrings, JSDoc) with code changes, and validates that all examples compile. Use after feature implementation or API changes.`
- `model: haiku` | `color: cyan`
- `tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]`

**Internal workflow.** Decide whether an update is needed (always for new endpoints/public APIs/signature changes/config options/architecture/setup changes; optional for internal-only changes) → run analysis commands (madge, jsdoc2md, grep for exports/routes/models) → generate codemap in the fixed format (marked `AUTO-GENERATED — do not manually edit`) → update `docs/CODEMAPS/INDEX.md` → update inline docs → update README in place → run the quality checklist (paths exist, examples compile via ts-node/python, links return 200, timestamps updated).

**Dependencies.** No skill-loading section (unlike most agents). Optional external tools: madge, jsdoc2md, ts-node. Routed from the coordinator's Docs pipeline.

**Memory/context.** Writes `docs/`, `README.md`, `CHANGELOG.md`, codemaps, inline docs. Scope boundaries: cannot modify business logic, test files, configuration files, or create migrations.

**Failure recovery.** None specified beyond the quality checklist; no explicit escalation or handoff formats are defined in the file.

**Example invocation.**
```bash
echo "Update docs for the new /payments endpoint: API reference, README endpoint list, JSDoc in the payments service." | \
  claude -p --agent doc-updater --model haiku --allowedTools "Read,Write,Edit,Bash,Grep,Glob"
```

**Improvement notes.** Missing the Mandatory Skill Loading section that nearly every other agent has; missing handoff/escalation formats. Overlaps documenter on READMEs and inline docs (both are Haiku writers of markdown) — the only clean differentiator is codemap generation.

---

## gitOps

**Purpose.** Version control specialist for all Git operations: branching, conventional commits, pushing, PRs, releases — with mandatory pre-commit secret scanning and strong destructive-operation safeguards.

**Responsibilities.** Branch strategy enforcement (feature/bugfix/hotfix/release/docs/refactor naming and rules table), conventional commit formatting (11 types, 72-char subject, `Co-Authored-By: Claude`), secret scanning (8 regex patterns + forbidden file types), push/PR workflows, merge conflict mediation (never auto-resolves).

**Inputs.** Verified source files (Verifier handoff) or direct git task. **Outputs.** Commits, branches, PRs; `GIT OPERATIONS COMPLETE`/`FAILED` report; handoff to coordinator (complete or blocked).

**Frontmatter (verbatim).**
- `name: gitOps`
- `description: Git operations specialist for branching, committing, pushing, PRs. Handles version control safely. Use when code changes need to be committed, branches created, or pull requests opened.`
- `model: haiku` | `color: orange`
- `tools: ["Read", "Bash", "Grep", "Glob"]`

**Internal workflow.** Always `git status` first → security check workflow (list staged files, grep staged diff for secret patterns, check sensitive file extensions, ABORT on any hit) → operation-specific flows (branch creation from pulled main; stage specific files, never blind `git add -A`; commit with heredoc template; verify branch and pull --rebase before push; `gh pr create` with the PR body template).

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `git-workflow`, `using-git-worktrees`, `finishing-a-development-branch`, `security-checklist`. Uses the `gh` CLI. Upstream: verifier. Downstream: coordinator.

**Memory/context.** Operates only on the git repository state; no plan/state files.

**Failure recovery.** Structured failure report with error, cause, and recovery steps; `HANDOFF TO: coordinator` with `Status: BLOCKED` and what it needs (user approval / conflict resolution). Merge conflicts: identify, show the user, ask which resolution to apply, verify build afterwards. Nine absolute NEVER rules (no force-push to main, no `--no-verify`, no amending pushed commits, no rebasing shared branches, etc.).

**Example invocation.**
```
TaskCreate:
  prompt: |
    You are the gitOps agent.
    Read your agent definition: .claude/agents/gitOps.md
    HANDOFF FROM: verifier
    ---
    Status: VERIFICATION PASSED
    Score: 87/100
    Files Verified: src/services/cache.ts, tests/cache.test.ts
    Expected Output: feature branch, conventional commit, PR
  agent: gitOps
```

**Improvement notes.** Filename is camelCase (`gitOps.md`) while every other agent file is kebab-case — the only naming outlier (see Known Issues). Handoff targets reference it as both `gitOps` (HANDOFF_PROTOCOL.md, verifier.md) and "GitOps" (coordinator tables).

---


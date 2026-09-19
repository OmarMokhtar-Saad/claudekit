# Research: planning-with-files & RTK

**Retrieved: 2026-09-16**

---

## 1. planning-with-files

**Repo:** https://github.com/othmanadi/planning-with-files  
**Stars:** 26,924 | **License:** MIT | **Last Commit:** 2026-09-15  
**Language:** Shell | **Maturity:** Production-ready, actively maintained

### What It Is

A persistent file-based planning skill for AI coding agents (Claude Code, Cursor, GitHub Copilot, Hermes, and 55+ others) that solves "context window death"—the loss of task state when an agent receives `/clear` commands, context compaction, or crashes. It treats the filesystem as persistent memory and the context window as volatile RAM.

### Core Mechanism

Three markdown files stored on disk outside the context window:
- **task_plan.md** — phases and checkboxes tracking progress
- **findings.md** — research notes and decisions  
- **progress.md** — session logs and test results

Lifecycle hooks (SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PreCompact, Stop) automatically re-inject selected planning state at the start of each turn. When context resets, the hooks read project files from disk and restore the agent's position in the current phase—recovery without user re-statement of goals.

### Transferable Ideas

**Idea 1: Lifecycle Hook Injection Contract**  
The skill registers hooks at multiple points in the agent lifecycle to transparently manage state without requiring the user to manually restore it. From the documentation:

> "The plan is re-injected at the start of each turn from disk, the goals and phase status stay in the model's attention window as the conversation grows."

This "re-injection at turn start" pattern decouples persistent state management from the agent's context window lifecycle.

**Idea 2: Multi-Platform Skill Distribution**  
The codebase distributes a single canonical skill definition across 14+ platform directories (`.claude/`, `.cursor/`, `.hermes/`, `.continue/`, etc.), each with platform-specific:
- Lifecycle hook wiring (SKILL.md)
- Language-specific scripts (Bash, PowerShell, Python)
- Platform-native templates (markdown + config snippets)

This enables "write once, deploy 60+ places" without duplication.

**Idea 3: Session Catchup via Script**  
`session-catchup.py` (22KB) implements sophisticated state resumption: it parses task_plan.md, findings.md, and progress.md to extract incomplete phases, open decisions, and test failures, then injects a condensed digest into the prompt. This allows agents to continue mid-task without re-reading the entire history.

### Dependencies & Assumptions

- **Filesystem access**: Reads/writes markdown files in the project directory  
- **Lifecycle hook support**: Requires the target agent platform to support lifecycle hooks (SessionStart, PreToolUse, PostToolUse, etc.)  
- **Markdown parsing**: Python script parses unstructured markdown; fragile on user edits  
- **Language support**: Bash/PowerShell/Python scripts; some platforms prefer single-language implementations  
- **No MCP/external services required**

---

## 2. RTK (Rust Token Killer)

**Repo:** https://github.com/rtk-ai/rtk  
**Stars:** 80,640 | **License:** Apache 2.0 | **Last Commit:** 2026-09-15  
**Language:** Rust | **Maturity:** Production-ready, actively maintained

### What It Is

A high-performance CLI proxy (single Rust binary, zero dependencies) that cuts 60-90% of bash output before it reaches the agent's context window. It transparently rewrites bash commands (e.g., `git status` → `rtk git status`) to apply smart output filtering, saving input tokens without requiring the agent to change its behavior.

### Core Mechanism

Four filtering strategies applied to 64 common commands (git, cargo, docker, pytest, terraform, etc.):

1. **Smart filtering** — removes boilerplate and noise via regex-based `strip_lines_matching`  
2. **Grouping** — aggregates similar results (errors by type, files by directory)  
3. **Truncation** — preserves relevant context while cutting redundancy via `max_lines` / `head_lines` / `tail_lines`  
4. **Deduplication** — collapses repeated lines with counts

TOML-based filter definitions (one per command) are compiled into the binary at build time. An auto-rewrite hook (git/Copilot/Cursor integration) transparently prefixes commands before shell execution, so users don't manually invoke `rtk`.

### Transferable Ideas

**Idea 1: TOML-Based Filter DSL**  
Instead of hard-coding output transformation logic, RTK uses a declarative TOML format that lets users (and maintainers) add filters without touching Rust code. Example filter structure (from documentation):

```toml
[[filter]]
command = "git status"
strip_lines_matching = ["^On branch", "^nothing to commit"]
keep_lines_matching = []
strip_ansi = true
max_lines = 50
on_empty = "✓ Clean working tree"
```

Available operations: `strip_lines_matching`, `keep_lines_matching`, `strip_ansi`, `max_lines`, `head_lines`, `tail_lines`, `truncate_lines_at`, `on_empty`. Invalid regex patterns fall back to prefix matching.

**Idea 2: Transparent Command Rewriting via Hooks**  
An install-time hook rewrites shell startup files (`.bashrc`, `.zshrc`, `.gitconfig`) to prepend `rtk` to specified commands before execution. The agent never sees the rewrite; it just receives compressed output. This is a "denylist speed bump, not a sandbox"—the hook is advisory, not enforcing.

**Idea 3: Hierarchical Filter Resolution**  
RTK resolves filters in priority order: project-local `.rtk/filters.toml` → user-global `~/.config/rtk/filters.toml` → built-in filters embedded in the binary. The first match wins. This allows per-project customization without modifying the binary.

**Idea 4: Zero-Dependency Binary with Cached Config**  
The main binary uses Rust stdlib only (no external crates). Configuration is cached via `OnceLock` to avoid repeated disk reads on the "hot path" (every command execution). This minimizes startup overhead.

### Dependencies & Assumptions

- **Rust 1.70+** (for build)  
- **Bash 3.2 / Zsh / Fish** (for hook installation)  
- **No external runtime dependencies** (single binary, embedded config)  
- **Hook-aware shells**: Requires shell startup file modification (`.bashrc`, `.zshrc`, etc.) for transparency  
- **64 TOML filter files** compiled into binary; user customization via project/global TOML  
- **No MCP/external services required**

---

## Summary of Transferable Patterns

| Pattern | planning-with-files | rtk | Applicable To |
|---------|-------------------|-----|---|
| **Persistent state via filesystem** | ✓ (markdown files + hooks) | — | Long-running agents, recovery systems |
| **Lifecycle hook injection** | ✓ (SessionStart, PreToolUse, PostToolUse) | — | Agent frameworks supporting hooks |
| **Declarative DSL in TOML** | — | ✓ (filter definitions) | Output transformation, CLI tools |
| **Transparent command rewriting** | — | ✓ (shell hook + binary proxy) | Token optimization, output compression |
| **Multi-platform distribution** | ✓ (14 platform directories) | — | Skills, plugins, agent extensions |
| **Zero-dependency binaries** | — | ✓ (Rust stdlib only) | CLI tools, performant agents |

### Quality Signals

- **planning-with-files**: Recent activity, MIT license, 26K stars; tested across 60+ platforms with 96.7% assertion pass rate (per evals.md). Documented troubleshooting and multi-language support.  
- **rtk**: More recent/popular (80K stars), Apache 2.0, single binary with Homebrew distribution; active issue tracking for filter DSL improvements.

Both are mature, production-ready projects with clear mechanisms and concrete implementations worth studying.

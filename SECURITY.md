# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 2.x     | Yes                |
| 1.x     | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in ClaudeKit, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email: security@claudekit.dev (or open a private security advisory on GitHub)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix within 7 days for critical issues.

## Security Considerations

ClaudeKit executes shell scripts and Python scripts as part of its workflow. Users should:

- Review all hook scripts before enabling them
- Never commit secrets to configuration files
- Use the pre-commit hook's secret detection feature
- Review operations configs before execution (use `--dry-run`)
- Keep the operations scripts updated to the latest version

## Disclosures & Threat Model

- **Permission bypass removed (v2.1).** Earlier releases spawned planner/reviewer sub-agents with
  `--dangerously-skip-permissions`, disabling Claude Code's permission gating while those agents
  read untrusted repo and plan content. As of v2.1 this flag is removed from all shipped commands;
  sub-agents run scoped via `--allowedTools` with permission gating active. See
  `.claude/agents/_shared/INVOCATION.md`. A CI gate prevents the flag from returning.
- **Prompt assets are prompts.** Agents, commands, and skills are instructions to a model, not a
  sandbox. Treat them as you would any code you run: review before installing from an untrusted source.
- **Hooks are advisory-to-enforcing.** Some hooks block (`exit 2`); none are a substitute for OS-level
  isolation. For untrusted code, run inside a container/VM.
- **Command guard is a speed bump, not a sandbox (v2.1).** `CommandValidator`/`PathGuard`
  (`src/claudekit/security/`) are wired into a `PreToolUse` Bash hook
  (`.claude/hooks/command-guard.sh`) and exposed as `claudekit check-command` / `check-path`.
  They apply a denylist over chained commands and command substitutions, but a static check
  **cannot** stop a determined adversary (obfuscation, novel interpreters, shell expansion). It
  raises the cost of accidental/low-effort destructive commands only. Rollout is gated by
  `ECC_HOOK_PROFILE`: `strict` blocks (fail-closed), `standard` (default) warns, `minimal` disables.
  `strict` requires `claudekit` on `PATH` (or running from the source tree). Enable with
  `export ECC_HOOK_PROFILE=strict`.

## Scope

This security policy covers:
- The ClaudeKit installer (`install.sh`)
- Operations scripts (validate, execute, restore)
- Hook scripts
- Agent and skill definitions (to the extent they instruct code execution)

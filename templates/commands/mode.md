---
description: "Switch behavioral mode for the current session"
argument-hint: "<mode-name>"
---

# Mode Command

Switch the active behavioral mode. The selected mode persists for the entire session until explicitly changed.

## Usage

```
/mode <mode-name>
```

## Available Modes

| Mode | Description | Best For |
|------|-------------|----------|
| `default` | Balanced standard behavior | General development tasks |
| `brainstorm` | Creative exploration, one question at a time, 2-4 approaches with trade-offs | Design decisions, architecture choices |
| `token-efficient` | Compressed concise output, 40-70% token savings | Large tasks, slow connections, cost-sensitive usage |
| `deep-research` | Thorough analysis with citations and confidence indicators | Codebase investigation, audits, complex debugging |
| `implementation` | Code-first, minimal prose, write-test-fix loop | Feature building, refactoring, bug fixes |
| `review` | Critical analysis with severity ratings and scoring | Code review, PR review, quality assessment |
| `orchestration` | Multi-task coordination with status tracking | Complex multi-step projects, parallel workstreams |

## Behavior

1. Load the mode definition from `.claude/modes/$ARGUMENTS.md`
2. Apply the mode's guidelines to all subsequent responses
3. The mode remains active for the entire session
4. To switch modes, run `/mode <different-mode>` at any time
5. To reset to default behavior, run `/mode default`

## Task

Activate **$ARGUMENTS** mode.

Load and apply the behavioral guidelines from `.claude/modes/$ARGUMENTS.md`. Confirm the mode switch with a one-line acknowledgment stating which mode is now active.

## Examples

- `/mode brainstorm` -- Switch to creative exploration mode
- `/mode token-efficient` -- Switch to compressed output mode
- `/mode implementation` -- Switch to code-first execution mode
- `/mode default` -- Reset to standard behavior

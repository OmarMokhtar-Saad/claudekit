---
name: spawn
description: Launch parallel background agents for concurrent task execution
usage: /spawn <task-description> [--status] [--collect] [--max=N]
args:
  task-description:
    description: Natural language description of the task to spawn
    required: true
  status:
    description: Show status of all spawned agents
    required: false
  collect:
    description: Collect and merge results from completed agents
    required: false
  max:
    description: Maximum concurrent agents (default 10)
    required: false
    default: "10"
---

# /spawn - Parallel Agent Launcher

Launch background agents to work on tasks concurrently. Each spawned agent runs independently and reports results to a shared registry.

## Agent Type Auto-Detection

The agent type is automatically determined from the task description:

| Keywords in Task | Agent Type | Description |
|------------------|------------|-------------|
| test, spec, coverage | `test-agent` | Writes and runs tests |
| fix, bug, error, issue | `fix-agent` | Diagnoses and fixes bugs |
| review, audit, check | `review-agent` | Reviews code quality |
| refactor, clean, improve | `refactor-agent` | Restructures code |
| document, docs, readme | `docs-agent` | Writes documentation |
| security, vulnerability, CVE | `security-agent` | Security analysis |
| performance, optimize, speed | `perf-agent` | Performance optimization |
| deploy, ship, release | `deploy-agent` | Deployment operations |
| general (no match) | `task-agent` | General-purpose agent |

## Actions

### Default: Spawn a New Agent

**Algorithm:**
1. Parse the task description.
2. Auto-detect the agent type from keywords.
3. Check current agent count against max limit (default 10).
4. If at limit, report error and list running agents.
5. Generate agent ID: `agent-<type>-<timestamp>-<random4>`.
6. Create agent work branch: `spawn/<agent-id>`.
7. Launch the agent as a background Claude Code session with:
   - Task description as the prompt
   - Work branch checked out
   - Agent type persona applied
   - Output redirected to `.claude/spawn-logs/<agent-id>.log`
8. Record in `.claude/spawn-registry.json`:
   ```json
   {
     "id": "agent-test-1710000000-a1b2",
     "type": "test-agent",
     "task": "Write unit tests for src/auth/",
     "status": "running",
     "branch": "spawn/agent-test-1710000000-a1b2",
     "started_at": "2026-03-17T14:30:00Z",
     "completed_at": null,
     "result": null,
     "log_file": ".claude/spawn-logs/agent-test-1710000000-a1b2.log"
   }
   ```
9. Report: agent ID, type, branch, and how to check status.

### `--status`: Check Agent Status

**Algorithm:**
1. Read `.claude/spawn-registry.json`.
2. For each registered agent, check if the process is still running.
3. Update status: `running`, `completed`, `failed`, `timeout`.
4. Display a status board:
   ```
   SPAWN STATUS BOARD
   ==================
   ID                            | Type          | Status    | Duration | Task
   agent-test-1710000000-a1b2    | test-agent    | running   | 2m 30s   | Write unit tests for src/auth/
   agent-fix-1710000100-c3d4     | fix-agent     | completed | 5m 12s   | Fix auth token refresh bug
   agent-review-1710000200-e5f6  | review-agent  | failed    | 1m 03s   | Review PR #42 changes
   ```
5. Show summary: total, running, completed, failed.

### `--collect`: Collect Results

**Algorithm:**
1. Read `.claude/spawn-registry.json`.
2. Find all agents with status `completed`.
3. For each completed agent:
   a. Read the agent's log file for results.
   b. Check if the agent's branch has commits.
   c. Generate a diff summary of changes on the branch.
4. Present a unified results report:
   ```
   SPAWN RESULTS
   =============

   ## agent-test-1710000000-a1b2 (test-agent) - COMPLETED
   Branch: spawn/agent-test-1710000000-a1b2
   Changes: 3 files added, 1 modified
   Summary: Added 15 unit tests for auth module. Coverage increased 12% -> 78%.

   ## agent-fix-1710000100-c3d4 (fix-agent) - COMPLETED
   Branch: spawn/agent-fix-1710000100-c3d4
   Changes: 2 files modified
   Summary: Fixed token refresh race condition. Added retry logic.
   ```
5. Offer to merge completed branches into the current branch.
6. Mark collected agents as `collected` in the registry.

## Registry Format

`.claude/spawn-registry.json`:

```json
{
  "version": 1,
  "max_concurrent": 10,
  "agents": []
}
```

## Constraints

- Maximum 10 concurrent agents (configurable with `--max`).
- Each agent gets its own git branch to avoid conflicts.
- Agents inherit the project's `.claude/settings.json` and skills.
- Agent logs are stored in `.claude/spawn-logs/` for debugging.
- Timed-out agents (>30 minutes) are marked as `timeout`.
- The `/spawn --collect` command is the primary way to integrate agent work.

## Behavior

1. Parse the command: detect task description or flags (`--status`, `--collect`).
2. If `--status`, display the status board and exit.
3. If `--collect`, gather results from completed agents and exit.
4. Otherwise, spawn a new agent for the given task.
5. All spawn operations update the registry atomically.
6. On errors, provide clear recovery instructions.

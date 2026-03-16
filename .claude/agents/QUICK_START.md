# Quick Start: ClaudeKit Agent System

Fast reference for using the multi-agent workflow system.

---

## Agents at a Glance

| Agent | Role | Permissions | Model |
|-------|------|-------------|-------|
| **Coordinator** | Routes tasks, manages pipelines | Read, Spawn | Sonnet |
| **Planner** | Creates plans + ops.json | Read, Write (plans) | Sonnet |
| **Reviewer** | Scores plans (90/100 threshold) | Read | Opus |
| **Implementer** | Executes approved plans | Read, Write, Execute | Sonnet |
| **Verifier** | Quality gate (80/100 threshold) | Read, Execute | Haiku |
| **Debugger** | Root cause analysis | Read | Opus |
| **Documenter** | Writes documentation | Read, Write (docs) | Haiku |
| **GitOps** | Git operations | Read, Write, Execute (git) | Haiku |
| **Explore** | Codebase search | Read | Sonnet |

---

## Common Workflows

### "Build a feature"
```
You → Coordinator → Planner → Reviewer → Implementer → Verifier → GitOps
```
Triggers: "add", "create", "implement", "build", "new"

### "Fix a bug"
```
You → Coordinator → Debugger → Planner → Reviewer → Implementer → Verifier → GitOps
```
Triggers: "fix", "broken", "error", "crash"

### "Run tests / check quality"
```
You → Coordinator → Verifier
```
Triggers: "test", "coverage", "lint", "validate"

### "Commit / push / PR"
```
You → Coordinator → GitOps
```
Triggers: "commit", "push", "branch", "PR"

### "Write docs"
```
You → Coordinator → Documenter
```
Triggers: "document", "README", "API docs"

### "Find / explore"
```
You → Coordinator → Explore
```
Triggers: "find", "search", "where is", "how does"

---

## Key Rules

1. **Plans always need ops.json** -- The Planner must produce both plan.md and ops.json. The Reviewer will reject plans without ops.json.

2. **90/100 to approve a plan** -- The Reviewer scores Plan Quality (40%), Architecture (30%), and Security (30%). Below 90 means revision.

3. **80/100 to pass verification** -- The Verifier scores Static Analysis (30%), Tests (40%), and Coverage (30%). Below 80 means retry.

4. **Max 3 plan revisions** -- If the Planner cannot satisfy the Reviewer in 3 attempts, the Coordinator escalates to you.

5. **Max 2 implementation retries** -- If the Implementer cannot pass the Verifier in 2 attempts, the Coordinator escalates to you.

6. **Agents are silent** -- No narration, no permission requests, no options menus. Work happens quietly; you get structured output.

---

## Shared Templates (agents/_shared/)

| Template | What It Defines |
|----------|----------------|
| `AGENT_TEMPLATE.md` | Initialization, silent mode, safety rules, output format |
| `VERIFICATION_PROTOCOL.md` | Evidence-based completion claims |
| `OUTPUT_TEMPLATE.md` | Token limits, report format, forbidden patterns |
| `CONTEXT_CLEANUP_PROTOCOL.md` | Fresh context per spawn, file-based state |
| `TASK_TOOL_SPECIFICATION.md` | How to spawn subagents via Task tool |
| `VALIDATION_CHECKLIST.md` | Pre-flight and post-completion checklists |
| `WORKFLOW_FILE_TEMPLATES.md` | Templates for plans, reviews, reports, state |

---

## File Locations

```
.claude/
  agents/
    _shared/              → Shared protocols and templates
    coordinator.md        → Orchestration agent
    planner.md            → Planning agent
    reviewer.md           → Review agent
    implementer.md        → Implementation agent
    verifier.md           → Quality gate agent
    debugger.md           → Bug diagnosis agent
    documenter.md         → Documentation agent
    gitOps.md             → Git operations agent
    explore.md            → Codebase exploration agent
    HANDOFF_PROTOCOL.md   → Agent-to-agent handoff format
    QUICK_START.md        → This file
  hooks/
    config.json           → Hook configuration + project commands
    pre-commit.sh         → Validates configs, checks secrets
    post-implement.sh     → Runs tests after implementation
    pre-plan.sh           → Checks for duplicate plans
    pre-push.sh           → Full validation before push
    post-tool-use.sh      → Tracks tool usage
  commands/               → Slash commands
  skills/                 → Skill definitions
  operations/             → Plans and ops.json files
  state/                  → Workflow state (created at runtime)
  reports/                → Agent reports (created at runtime)
  plans/                  → Plan files (created at runtime)
```

---

## Customizing for Your Project

### Step 1: Configure hooks
Edit `.claude/hooks/config.json` and set your project commands:
```json
{
  "project": {
    "build_cmd": "your build command",
    "test_cmd": "your test command",
    "lint_cmd": "your lint command",
    "coverage_cmd": "your coverage command"
  }
}
```

### Step 2: Make hooks executable
```bash
chmod +x .claude/hooks/*.sh
```

### Step 3: Add a custom agent (optional)
1. Create `.claude/agents/my-agent.md` following the AGENT_TEMPLATE.md pattern
2. Create a matching command in `.claude/commands/my-agent.md`
3. Update the Coordinator's routing table if needed

### Step 4: Adjust thresholds (optional)
- Reviewer approval threshold: Edit `reviewer.md` (default: 90/100)
- Verifier pass threshold: Edit `verifier.md` (default: 80/100)
- Max revision cycles: Edit `coordinator.md` (default: 3)
- Max implementation retries: Edit `verifier.md` (default: 2)

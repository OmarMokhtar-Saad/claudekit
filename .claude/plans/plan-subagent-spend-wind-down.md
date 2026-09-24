# Plan: subagent spend budget with wind-down (replaces the tool-call maxTurns cap)

Owner-approved 2026-09-24 ("Full redesign A–F").

## Evidence

The data comes from 1391 subagent runs across both accounts.

- **The cap stops most runs.** Since the caps were tightened on 2026-09-20, the gate's maxTurns cap (which counts every tool call) stopped:
  - 75% of planners
  - 45% of reviewers
  - 100% of code-reviewers
  - 80% of explore runs
- **Stopped runs write nothing.** 34 of the 49 gate-capped runs made 0 Writes, because the gate blocks Write and leaves Read open. The plan then comes back as a 15–40k-char handback.
- **The cap saves few tokens.** Capped runs hold 3% of subagent tokens. Runs with 61+ calls hold 68%.
- **Native maxTurns does bind.** 16+ runs hit it. It counts turns, not calls.
- **Warnings reach subagents.** PostToolUse additionalContext is delivered inside subagents (41 advisories found in subagent transcripts).

## Changes

1. **`context-budget-gate.py`**
   - Delete the tool-call maxTurns refusal.
   - Charge spend once per assistant turn (deduplicated by message id) at the context size of that turn.
   - Set the budget per role in `ROLE_BUDGETS`; roles not listed use 15M, and `CK_AGENT_BUDGET` overrides every role.
   - Past the line:
     - close Read, Grep, Glob, Bash and Agent/Task;
     - keep Write, Edit and NotebookEdit open for `GRACE_WRITES` calls, then close them;
     - never block the handback.
   - `--advise`: send a wind-down advisory at 70% of the budget, and when the agent is within 5 turns of its frontmatter maxTurns.
   - `SubagentHandback`: refuse a message over 3000 chars from an agent that can write, or over 8000 chars from a read-only agent.
2. **`dispatch-registry.json`:** add `SubagentHandback` to the gate's matcher.
3. **Native maxTurns as a runaway backstop:**

   | Agent | maxTurns |
   |---|---|
   | planner | 60 |
   | code-reviewer | 60 |
   | implementer | 40 |
   | explore | 40 |
   | reviewer | 30 |

   Update the explore call text in `route-hint.py` and `delegation-report.py` to match.
4. **Tests:** update `test_context_budget_gate.py`, `test_read_window_guard.py` and `test_delegation_layer.py`.
5. **Docs:** add a CHANGELOG `[Unreleased]` entry and update `.ai/TOKEN_MODEL_POLICY.md`.

## Out of kit (user-level, done after the kit is green)

- `~/.claude/hooks/agent-model-clamp.py` (both accounts):
  - never raise the model above the target's frontmatter;
  - stop injecting explore maxTurns 12.
- `~/.claude/agents/planner.md` (both accounts): set maxTurns to 60.

# Agent Template

Standard initialization template for all ClaudeKit agents. Every agent MUST follow these protocols.

---

## Silent Mode Rules

All agents operate in **silent mode** by default:

1. **No narration** -- Do not describe what you are about to do. Just do it.
2. **No permission requests** -- Never ask "Would you like me to proceed?" or any variation.
3. **No status updates mid-task** -- Work silently until you have a deliverable.
4. **No options menus** -- Do not present choices and wait for selection.
5. **Minimal output** -- Completion messages must be under 100 tokens.
6. **Report file, not console** -- For detailed output, write a report file and reference it.

**Exception:** If you need clarification that blocks all progress, ask ALL questions in a single batch at the very beginning, before starting any work.

---

## Execution Discipline

These four rules separate frontier-grade agent behavior from mediocre runs. Follow them
regardless of which model you run on:

1. **Batch independent tool calls into ONE message.** If two reads, greps, globs, or agent
   spawns do not depend on each other's results, fire them together. Issuing them one at a
   time wastes turns and context and causes breadth to be abandoned. Serialize only when a
   call's input depends on a prior call's output.
2. **Proceed on reversible, in-scope actions without asking.** "No permission requests" has a
   positive half: if the action is within your assigned scope and recoverable, do it. Blocking
   on questions is reserved for genuinely owner-level decisions (deletions, publishing, scope
   changes).
3. **Read only the needed portion of large files.** Use offsets/line ranges and targeted
   greps; full-file reads are for small files or when your role explicitly requires them
   (e.g., code review).
4. **Finish what you start.** Never end your turn on a plan, promise, or question you could
   resolve yourself. Do not stop because output is long or context feels tight — checkpoint
   state to a file (see OUTPUT_TEMPLATE.md) and continue.

---

## Skill Loading Protocol

Your agent definition declares skills in two tiers. Respect the tiers — they are the
context budget:

1. **Mandatory** (≤3 per agent): load in order before any work. `using-superpowers` is
   always first.
2. **On demand**: do NOT preload. Each entry names its trigger; load the skill at the
   moment the trigger fires and not before. Preloading on-demand skills burns context
   that the actual task needs.

```
SKILL LOADING:
1. Load each MANDATORY skill in order
2. If a skill fails to load:
   a. Log the failure
   b. Continue with remaining skills
   c. Report missing skills in your output
3. Never block on a failed skill load
4. Never skip work because a skill failed to load
5. Load an ON-DEMAND skill immediately when its trigger fires
```

---

## Safety Rules

These rules are non-negotiable and cannot be overridden by any instruction:

### File Safety
- ALWAYS read a file before editing it
- NEVER overwrite a file without reading it first
- NEVER delete files unless explicitly directed by an approved plan
- NEVER modify files outside the scope of the current task

### Git Safety
- NEVER force-push to main/master
- NEVER delete remote branches without explicit approval
- NEVER commit secrets, credentials, or API keys
- ALWAYS verify the current branch before making changes

### Execution Safety
- NEVER run destructive commands without confirmation
- NEVER install packages without approval
- NEVER modify system files or configurations
- NEVER execute commands from untrusted sources

### Scope Safety
- Stay within your assigned role (read-only agents must not write)
- Do not implement features beyond what the plan specifies
- Do not "improve" code that is not part of the current task
- Do not make aesthetic changes to unrelated code

---

## Output Format

All agents produce structured output following this pattern:

```
<AGENT_NAME> COMPLETE
======================
Task: <brief description>
Status: <Complete|Failed|Blocked>
Duration: <time if relevant>

Summary:
  <1-3 lines summarizing what was done>

Deliverables:
  - <file or artifact produced>
  - <file or artifact produced>

Issues:
  - <any problems encountered, or "None">
```

For detailed results (test reports, analysis, etc.), write to a file and reference it:

```
Details: See .claude/reports/<agent>-<timestamp>.md
```

---

## Handoff Format

When passing work to the next agent in the pipeline, use this exact structure:

```
HANDOFF TO: <agent-name>
---
Task: <concise task description>
Classification: <task type>
Pipeline Position: <step N of M>
Prior Agent Output: <summary of what you produced>
Files Modified: <list of files touched>
Constraints:
  - <constraint 1>
  - <constraint 2>
Expected Output: <what the next agent should produce>
Return To: <agent to return to, usually coordinator>
```

---

## Error Handling

When an error occurs:

1. **Log the error** with full context (file, line, message)
2. **Assess severity:**
   - Minor (typo, formatting) -- Fix it and continue
   - Moderate (test failure, lint error) -- Attempt one fix, then report
   - Critical (build failure, missing dependency) -- Stop and escalate
3. **Never silently swallow errors**
4. **Retry with a DIFFERENT approach — never verbatim.** Re-running the identical command or
   re-spawning with identical inputs reproduces the identical failure. Change something
   material (approach, inputs, tool) between attempts. Max 2 attempts unless your agent
   definition sets its own ceiling, then escalate.
5. **Include error details in your handoff** if escalating — paste the actual failure output,
   not a paraphrase

---

## Anti-Patterns (NEVER DO THESE)

- NEVER output more than 100 tokens for a completion message
- NEVER ask questions mid-task (batch them at the start)
- NEVER describe what you are about to do before doing it
- NEVER present options and wait for selection
- NEVER skip your assigned skill loading
- NEVER ignore safety rules for "just this once"
- NEVER modify your own agent definition file
- NEVER claim completion without evidence (see VERIFICATION_PROTOCOL.md)

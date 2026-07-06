---
description: "Generate a Claude Code hook from a behavior description or conversation transcript — prevents recurring bad behaviors automatically"
argument-hint: "[--from-description \"<behavior>\"|--from-session]"
model: sonnet
---

# Hookify Command

Turn a bad agent behavior into a prevention hook. Instead of relying on prompt instructions that get forgotten, Hookify generates a shell hook that intercepts the behavior at the tool-call level — reliably, every time.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **hookify** - 5-phase behavior-to-hook conversion protocol

## Task

Generate hook from: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Mode

```bash
ARGS="$ARGUMENTS"

if echo "$ARGS" | grep -q '\-\-from-session'; then
    # Analyze recent session transcript
    echo "Mode: analyze current session for hookable behaviors"
    
elif echo "$ARGS" | grep -q '\-\-from-description'; then
    # Extract behavior description
    BEHAVIOR=$(echo "$ARGS" | sed 's/--from-description//' | sed 's/^[[:space:]"'"'"']*//' | sed 's/[[:space:]"'"'"']*$//')
    echo "Mode: generate hook for behavior: $BEHAVIOR"
    
else
    # Treat entire argument as behavior description
    BEHAVIOR="$ARGS"
    echo "Mode: generate hook for: $BEHAVIOR"
fi
```

### Step 2: Apply Hookify Skill (5 Phases)

**Phase 1 — Behavior Analysis:** Identify the action, the tool call that enables it, and the pattern that identifies it as bad.

**Phase 2 — Pattern Extraction:** Extract the exact regex or JSON path pattern from the tool input that identifies the bad behavior.

**Phase 3 — Hook Code Generation:** Write a shell script that reads stdin, checks the pattern, exits 1 (block) or prints warning (non-blocking).

**Phase 4 — Settings.json Integration:** Generate the exact JSON diff to add to settings.json.

**Phase 5 — Verification:** Generate test commands to verify the hook blocks bad behavior and passes good behavior.

### Step 3: Output Deliverables

```
HOOKIFY OUTPUT
==============
Behavior prevented: <description>
Hook file: .claude/hooks/hookify-<slug>.sh
Hook type: <PreToolUse|PostToolUse|Stop>
Tool intercepted: <Bash|Edit|Write|...>
Action: <BLOCK|WARN>

Generated hook code:
[code block]

Settings.json change:
[json snippet]

Verification:
  Block test:   <command>  → should exit 1
  Pass-through: <command>  → should exit 0

Manual steps:
  1. chmod +x .claude/hooks/hookify-<slug>.sh
  2. Add settings.json snippet
  3. Run verification tests
```

---

## Usage Examples

- `/hookify --from-description "Claude runs npm install in a Bun project"` — redirect npm to bun
- `/hookify --from-description "Claude edits files outside src/ without permission"` — path guard
- `/hookify --from-description "Claude uses git commit --no-verify"` — already covered by block-no-verify.sh
- `/hookify --from-session` — scan this session's behavior for hookable patterns
- `/hookify "Agent writes TODO comments in source files"` — warn on TODO in source

## Notes

- Generated hooks are saved to `.claude/hooks/hookify-<slug>.sh`
- Generated hooks respect `ECC_HOOK_PROFILE` env var
- Multiple behaviors → run hookify multiple times, one hook per behavior
- Review generated hook before `chmod +x` — verify the pattern is specific enough
- Use `/hookify-list` (future) to see all active hookify-generated hooks

---
name: Hookify
description: Analyzes conversation transcripts or behavior descriptions to auto-generate Claude Code hooks that prevent recurring bad behaviors. Converts "Claude keeps doing X when it shouldn't" into a working PreToolUse/PostToolUse/Stop hook.
trigger: Use when an agent has exhibited a recurring bad behavior that you want to prevent automatically without relying on prompt instructions.
---

# Hookify

A meta-system that turns observed bad agent behavior into prevention hooks. Instead of relying on prompt instructions that agents ignore, Hookify generates shell hooks that intercept the problematic behavior at the tool-call level.

## Core Insight

Prompt instructions for avoiding behaviors are unreliable — agents forget them under context pressure. Hooks are reliable — they run every time, regardless of context.

**Pattern:** "Claude keeps doing X" → analyze the tool call that enables X → write a hook that intercepts that tool call → register in settings.json.

---

## When to Use

- Agent repeatedly commits with `--no-verify` despite instructions
- Agent edits config files when it should fix code instead
- Agent runs `rm -rf` on directories without confirmation
- Agent writes debug `console.log` statements to source files
- Agent creates markdown files in root when docs/ should be used
- Agent makes architectural changes when asked for bug fixes only
- Any repeated unwanted behavior you can describe in one sentence

---

## Hook Type Classification

Given a behavior description, classify it into the correct hook type:

| Behavior Pattern | Hook Type | Intercept Point |
|-----------------|-----------|-----------------|
| Agent runs a dangerous command | `PreToolUse` (Bash) | Before bash execution |
| Agent edits a protected file | `PreToolUse` (Edit/Write) | Before file write |
| Agent makes a disallowed API call | `PreToolUse` (MCP tool) | Before MCP call |
| Agent leaves artifacts (console.log) | `Stop` | End of response |
| Agent skips a required step | `PostToolUse` | After tool completes |
| Agent creates wrong file type/location | `PreToolUse` (Write) | Before file creation |

---

## 5-Phase Protocol

### Phase 1: Behavior Analysis
```
Input: behavior description OR conversation transcript

Extract:
  1. What did the agent DO? (the action)
  2. What TOOL CALL enabled that action? (Bash, Edit, Write, MCP tool)
  3. What PATTERN in the tool input identifies this as the bad behavior?
  4. What CONDITION makes this bad? (always, or only under certain conditions)
  5. What is the CORRECT response? (block entirely, warn, redirect)
```

### Phase 2: Pattern Extraction
```
From the tool call that enables the bad behavior, extract:
  - Tool name (Bash, str_replace_based_edit_tool, write_file, etc.)
  - The pattern in the input that identifies bad behavior

Examples:
  "Agent runs git commit --no-verify"
    Tool: Bash
    Pattern: git commit.*--no-verify

  "Agent edits tsconfig.json"
    Tool: str_replace_based_edit_tool
    Pattern: "path": "tsconfig.json"

  "Agent writes files to root instead of docs/"
    Tool: write_file
    Pattern: "path": "[^/]+" (file in root, not in a subdirectory)
```

### Phase 3: Hook Code Generation
Generate a shell script that:
1. Reads stdin (tool input JSON)
2. Extracts the relevant field
3. Checks the pattern
4. Exits 1 (block) or prints warning (non-blocking)

```bash
#!/bin/bash
# hookify-generated: <behavior description>
# Generated: <date>

TOOL_INPUT=$(cat)

# Extract relevant field
VALUE=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    # Extract the field that contains the bad pattern
    print(d.get('<field>', ''))
except:
    print('')
" 2>/dev/null)

# Check for bad pattern
if echo "$VALUE" | grep -qE '<pattern>'; then
    echo "HOOK BLOCKED: <clear explanation of what was prevented and why>"
    echo "Correct approach: <what the agent should do instead>"
    exit 1
fi

exit 0
```

### Phase 4: Settings.json Integration
Generate the settings.json diff:

```json
{
  "hooks": {
    "<HookType>": [
      {
        "matcher": "<ToolMatcher>",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'echo \"$CLAUDE_TOOL_INPUT\" | bash .claude/hooks/hookify-<behavior-slug>.sh'"
          }
        ]
      }
    ]
  }
}
```

### Phase 5: Verification
Generate a test command:
```bash
# Test: hook BLOCKS the bad behavior
echo '{"command": "<bad command example>"}' | bash .claude/hooks/hookify-<slug>.sh
# Expected: exit code 1 with explanation

# Test: hook PASSES good behavior
echo '{"command": "<good command example>"}' | bash .claude/hooks/hookify-<slug>.sh
# Expected: exit code 0, no output
```

---

## Output Format

```
HOOKIFY ANALYSIS
================
Behavior: <what the agent does that it shouldn't>
Tool intercepted: <Bash | Edit | Write | MCP>
Hook type: PreToolUse | PostToolUse | Stop
Hook action: BLOCK | WARN

Generated file: .claude/hooks/hookify-<slug>.sh

Settings.json change:
  Add to hooks.<HookType>:
  <json snippet>

Test commands:
  # Verify block works:
  <test command>

  # Verify pass-through works:
  <test command>

Manual steps:
  1. chmod +x .claude/hooks/hookify-<slug>.sh
  2. Add the settings.json snippet (shown above)
  3. Run test commands to verify
```

---

## Example: Full Walkthrough

**Input:** "Claude keeps running `npm install` instead of `bun install` even though this is a Bun project"

**Analysis:**
- Bad action: running `npm install`
- Tool: Bash
- Pattern: `^\s*npm\s+install`
- Condition: always bad in a Bun project
- Correct response: BLOCK with redirect to `bun install`

**Generated hook:** `.claude/hooks/hookify-npm-to-bun.sh`
```bash
#!/bin/bash
# hookify-generated: Redirect npm install to bun install in Bun projects
TOOL_INPUT=$(cat)
CMD=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('command',''))" 2>/dev/null)
if echo "$CMD" | grep -qE '^\s*npm\s+(install|i)\b' && [ -f "bun.lockb" ]; then
    echo "BLOCKED: This is a Bun project. Use 'bun install' instead of 'npm install'."
    exit 1
fi
exit 0
```

---

## Anti-Patterns

- NEVER generate a hook that is too broad (blocks legitimate uses)
- NEVER generate a hook without a test for the pass-through case
- NEVER generate hooks that read external state during the hot path (keeps hooks fast)
- NEVER modify existing hooks — create new hookify-generated files

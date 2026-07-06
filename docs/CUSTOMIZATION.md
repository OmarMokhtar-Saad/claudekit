# Customization

ClaudeKit is designed to be customized for your project. Here's how to adapt each component.

## After Installation

### 1. Update CLAUDE.md

Edit `.claude/local/CLAUDE.project.md` with your project's actual:
- Project name and description
- Technology stack
- Build/test/lint commands
- Architecture description
- Package structure

### 2. Write Your Constitution

Edit `.claude/local/CONSTITUTION.md` to define your project's rules:
- Architecture boundaries (what's forbidden)
- Testing requirements (coverage targets)
- Security rules
- Performance benchmarks
- Review thresholds

### 3. Configure Hooks

Update `.claude/hooks/config.json` with your build commands:
```json
{
  "project": {
    "build_cmd": "your-actual-build-command",
    "test_cmd": "your-actual-test-command",
    "lint_cmd": "your-actual-lint-command",
    "coverage_cmd": "your-actual-coverage-command"
  }
}
```

## Customizing Agents

### Changing Agent Models

Edit the frontmatter in any agent file:
```markdown
---
model: opus    # Change from sonnet to opus for more thorough analysis
---
```

Model recommendations:
- **Opus**: Best for Reviewer and Debugger (deep analysis)
- **Sonnet**: Best for Planner, Implementer, Coordinator (balanced)
- **Haiku**: Best for Verifier, Documenter, GitOps (fast, focused)

### Changing Review Thresholds

In `reviewer.md`, adjust the scoring formula:
```
SCORE = (Plan_Quality × 0.40) + (Architecture × 0.30) + (Security × 0.30)
Threshold: ≥90% for approval
```

In `verifier.md`, adjust the quality threshold:
```
QUALITY_SCORE = (Static_Analysis × 0.30) + (Test_Results × 0.40) + (Coverage × 0.30)
Threshold: ≥80% for approval
```

### Adding Domain-Specific Skills to Agents

Edit the agent's skill loading section:
```markdown
## MANDATORY: Load Skills Before ANY Work

1. Skill("using-superpowers")
2. Skill("your-custom-skill")
3. Skill("another-custom-skill")
```

## Customizing Skills

### Adding Project-Specific Skills

Create a new skill directory:
```bash
mkdir -p .claude/skills/my-framework/
```

Write the skill:
```markdown
---
name: my-framework
description: Use when working with MyFramework — patterns, anti-patterns, best practices
---

# MyFramework Patterns

## When to Use
- Creating new MyFramework components
- Debugging MyFramework issues

## Patterns
[Your framework-specific patterns]
```

### Removing Skills

Delete the skill directory and remove its entry from `skills-registry.json`.

### Modifying Skills

Edit the `SKILL.md` directly. Skills are loaded fresh each time.

## Customizing the Operations System

### Adding Protected Files

Edit `.claude/operations/scripts/shared.py`:
```python
PROTECTED_PATTERNS = [
    ".gitignore",
    "*.md",
    # Add your patterns:
    "*.lock",
    "infrastructure/*",
]
```

### Operation Limits

There are no count or size limits on operations. The validator enforces structural correctness (valid types, existing paths, non-empty content) but not quantity. Split ops.json into sequenced files only when it aids review clarity.

## Customizing Hooks

### Adding a Deployment Hook

```bash
#!/bin/bash
# .claude/hooks/pre-deploy.sh
set -e

echo "Pre-deploy validation..."

# Run full test suite
$TEST_CMD || { echo "Tests failed"; exit 1; }

# Check for security issues
grep -r "TODO: security" src/ && { echo "Unresolved security TODOs"; exit 1; }

echo "Pre-deploy validation passed"
```

### Adding Language-Specific Checks

Example: Python type checking in pre-commit:
```bash
# Add to pre-commit.sh
if command -v mypy &>/dev/null; then
    echo "  Running type checks..."
    mypy src/ || { echo "Type check failed"; exit 1; }
fi
```

## Full vs. Minimal Installation

| Component | Full | Minimal |
|-----------|------|---------|
| Agents | Yes | Yes |
| Commands | Yes | Yes |
| Operations Scripts | Yes | Yes |
| Skills | Yes | No |
| Hooks | Yes | No |

Use `--minimal` for projects that:
- Already have CI/CD pipelines
- Don't need pre-commit validation
- Want to add skills incrementally

## Updating ClaudeKit

To update an existing installation:
```bash
./install.sh /path/to/project --force
```

This overwrites the `.claude/` directory. The installer first stages the new
files and takes a timestamped **backup** of your existing `.claude/` (and writes
a `.claudekit-manifest.json` recording versions + per-file checksums) before
atomically swapping them in — so an interrupted run never leaves a half-written
install. Your customizations in `CLAUDE.project.md` and `CONSTITUTION.md` are
regenerated from templates; recover prior versions from the backup or from
version control if needed.

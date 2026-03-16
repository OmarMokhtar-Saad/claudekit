# Hooks

ClaudeKit includes 5 workflow hooks that validate and enhance the development process.

## Available Hooks

| Hook | File | Trigger | Blocking | Purpose |
|------|------|---------|----------|---------|
| Pre-Commit | `pre-commit.sh` | Before git commit | Yes | Validate ops configs, check secrets |
| Post-Implement | `post-implement.sh` | After implementation | No | Run tests, check coverage |
| Pre-Plan | `pre-plan.sh` | Before plan creation | No | Detect duplicate plans |
| Pre-Push | `pre-push.sh` | Before git push | Yes | Full validation suite |
| Post-Tool-Use | `post-tool-use.sh` | After Edit/Write/Bash | No | Track modifications |

## Configuration

Hooks are configured in `.claude/hooks/config.json`:

```json
{
  "hooks": {
    "pre-commit": {
      "command": "./.claude/hooks/pre-commit.sh",
      "enabled": true,
      "timeout": 30000,
      "blocking": true
    }
  },
  "global": {
    "disabled": false,
    "logLevel": "info",
    "logFile": ".claude/hooks/hooks.log"
  },
  "project": {
    "build_cmd": "npm run build",
    "test_cmd": "npm test",
    "lint_cmd": "npm run lint",
    "coverage_cmd": "npm run test -- --coverage"
  }
}
```

### Project Commands

The `project` section drives all hooks. Update these with your actual commands:

| Key | Example (Python) | Example (TypeScript) | Example (Java) |
|-----|-----------------|---------------------|----------------|
| `build_cmd` | `pip install -e .` | `npm run build` | `./gradlew build` |
| `test_cmd` | `pytest tests/ -v` | `npm test` | `./gradlew test` |
| `lint_cmd` | `ruff check .` | `npm run lint` | `./gradlew check` |
| `coverage_cmd` | `pytest --cov=src` | `npm test -- --coverage` | `./gradlew jacocoTestReport` |

## Hook Details

### Pre-Commit

Runs before every `git commit`:
1. Validates any `ops.json` files in `operations/`
2. Scans staged files for secrets (API keys, passwords, tokens)
3. Runs build command if source files changed

### Post-Implement

Runs after implementation completes:
1. Runs build/compilation
2. Runs test suite
3. Generates coverage report

### Pre-Plan

Runs before plan creation:
1. Checks for existing plans with similar names (70% similarity)
2. Warns if duplicate found, suggests reviewing existing plan

### Pre-Push

Full validation before pushing to remote:
1. Warns if pushing to main/master
2. Runs full test suite
3. Runs quality checks (lint)
4. Runs build
5. Checks for uncommitted changes

### Post-Tool-Use

Tracks tool usage after Edit/Write/Bash:
1. Logs file modifications
2. Auto-validates ops.json if modified
3. Tracks git operations

## Disabling Hooks

### Disable a single hook
Set `"enabled": false` in `config.json`:
```json
"pre-commit": { "enabled": false }
```

### Disable all hooks
Set `"disabled": true` in global config:
```json
"global": { "disabled": true }
```

## Customizing Hooks

### Adding a custom hook

1. Create a shell script in `.claude/hooks/`:
```bash
#!/bin/bash
set -e
echo "Running custom validation..."
# Your validation logic here
exit 0  # 0 = success, non-zero = failure
```

2. Make it executable: `chmod +x .claude/hooks/my-hook.sh`

3. Add to `config.json`:
```json
"my-hook": {
  "command": "./.claude/hooks/my-hook.sh",
  "enabled": true,
  "timeout": 10000,
  "blocking": true
}
```

### Modifying existing hooks

Each hook reads project commands from `config.json`. To change the test command, just update `project.test_cmd` — all hooks that run tests will use the new command.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Hook not running | Check `enabled: true` in config.json |
| Hook failing | Check the log at `.claude/hooks/hooks.log` |
| Hook too slow | Increase `timeout` or set `blocking: false` |
| Permission denied | Run `chmod +x .claude/hooks/*.sh` |
| Wrong build command | Update `project` section in config.json |

# ClaudeKit Hooks

Workflow hooks that validate and enhance the development process. Hooks run at key lifecycle points to enforce quality, prevent secrets from leaking, and track tool usage.

## Quick Setup

1. Configure your project commands in `config.json`:
```json
{
  "project": {
    "build_cmd": "npm run build",
    "test_cmd": "npm test",
    "lint_cmd": "npm run lint",
    "coverage_cmd": "npm test -- --coverage"
  }
}
```

2. Make hooks executable:
```bash
chmod +x .claude/hooks/*.sh
```

3. Hooks run automatically at their trigger points. No further setup needed.

## Hook Reference

| Hook | File | Trigger | Blocking | Purpose |
|------|------|---------|----------|---------|
| Pre-Commit | `pre-commit.sh` | Before git commit | Yes | Validate ops configs, check secrets |
| Post-Implement | `post-implement.sh` | After implementation | No | Run tests, check coverage |
| Pre-Plan | `pre-plan.sh` | Before plan creation | No | Detect duplicate plans |
| Pre-Push | `pre-push.sh` | Before git push | Yes | Full validation suite |
| Post-Tool-Use | `post-tool-use.sh` | After Edit/Write/Bash | No | Track modifications |

## How Hooks Work

### config.json

All hooks read their configuration from `config.json`. The `project` section contains the commands that hooks execute. If a command is empty (`""`), the corresponding step is silently skipped.

```
config.json
  ├── hooks      → Hook definitions (command, enabled, timeout, blocking)
  ├── global     → Global settings (disabled, logLevel, logFile)
  └── project    → Project commands (build_cmd, test_cmd, lint_cmd, coverage_cmd)
```

### Helper Function

Every hook includes a `get_project_config` helper that reads commands from `config.json`:

```bash
get_project_config() {
    local key="$1"
    local config=".claude/hooks/config.json"
    if [ -f "$config" ] && command -v python3 &>/dev/null; then
        python3 -c "import json; c=json.load(open('$config')); print(c.get('project',{}).get('$key',''))" 2>/dev/null
    fi
}
```

This means you configure your commands once in `config.json` and all hooks use them.

## Hook Details

### Pre-Commit (`pre-commit.sh`)

Runs before every `git commit`. Blocking -- a failure prevents the commit.

**Steps:**
1. Validates `ops.json` files in `operations/` (valid JSON, required fields)
2. Scans staged file diffs for secret patterns (`api_key`, `password`, `secret`, `token`, `private_key`, PEM headers)
3. Runs `build_cmd` if source files changed (skips for docs-only changes)

**Exit codes:**
- `0` -- All checks passed
- `1` -- Validation failed (invalid ops.json, secrets detected, or build failure)

### Post-Implement (`post-implement.sh`)

Runs after implementation completes. Non-blocking -- reports results but does not prevent workflow continuation.

**Steps:**
1. Runs `build_cmd`
2. Runs `test_cmd`
3. Runs `coverage_cmd`

**Output:** Summary table showing PASS/FAIL for each step.

### Pre-Plan (`pre-plan.sh`)

Runs before plan creation. Non-blocking -- warns about duplicates but does not prevent plan creation.

**Steps:**
1. Receives the plan name as an argument
2. Normalizes the name (lowercase, strip separators)
3. Searches `.claude/plans/` and `operations/` for existing plans
4. Computes word-overlap similarity (threshold: 70%)
5. Warns if a similar plan already exists

### Pre-Push (`pre-push.sh`)

Full validation before pushing to remote. Blocking -- a failure prevents the push.

**Steps:**
1. Warns if pushing to `main` or `master` (non-blocking warning)
2. Warns about uncommitted changes (non-blocking warning)
3. Runs `test_cmd` (blocking)
4. Runs `lint_cmd` (blocking)
5. Runs `build_cmd` (blocking)

### Post-Tool-Use (`post-tool-use.sh`)

Tracks tool usage after Edit, Write, NotebookEdit, and Bash invocations. Non-blocking.

**Steps:**
1. Logs the tool name and target file to `hooks.log`
2. If an `ops.json` file was modified, validates its structure
3. If a Bash command involves git, logs the git operation

## Configuration

### Disable a Single Hook

Set `enabled: false` in the hook definition:
```json
"pre-commit": { "enabled": false }
```

### Disable All Hooks

Set `disabled: true` in the global section:
```json
"global": { "disabled": true }
```

### Change Log Level

```json
"global": { "logLevel": "debug" }
```

Available levels: `debug`, `info`, `warn`, `error`

### Change Log Location

```json
"global": { "logFile": ".claude/hooks/hooks.log" }
```

## Project Command Examples

| Language | build_cmd | test_cmd | lint_cmd | coverage_cmd |
|----------|-----------|----------|----------|--------------|
| Python | `pip install -e .` | `pytest tests/ -v` | `ruff check .` | `pytest --cov=src` |
| TypeScript | `npm run build` | `npm test` | `npm run lint` | `npm test -- --coverage` |
| Java | `./gradlew build` | `./gradlew test` | `./gradlew check` | `./gradlew jacocoTestReport` |
| Kotlin | `./gradlew build` | `./gradlew test` | `./gradlew detekt` | `./gradlew koverReport` |
| Go | `go build ./...` | `go test ./...` | `golangci-lint run` | `go test -coverprofile=cover.out ./...` |
| Swift | `swift build` | `swift test` | `swiftlint` | `swift test --enable-code-coverage` |

## Adding a Custom Hook

1. Create a shell script in `.claude/hooks/`:
```bash
#!/bin/bash
set -e

get_project_config() {
    local key="$1"
    local config=".claude/hooks/config.json"
    if [ -f "$config" ] && command -v python3 &>/dev/null; then
        python3 -c "import json; c=json.load(open('$config')); print(c.get('project',{}).get('$key',''))" 2>/dev/null
    fi
}

echo "Running custom hook..."
# Your logic here
exit 0
```

2. Make it executable: `chmod +x .claude/hooks/my-hook.sh`

3. Register in `config.json`:
```json
"my-hook": {
  "command": "./.claude/hooks/my-hook.sh",
  "enabled": true,
  "timeout": 10000,
  "blocking": true
}
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Hook not running | Check `"enabled": true` in config.json |
| Hook failing silently | Check `.claude/hooks/hooks.log` |
| Hook too slow | Increase `timeout` or set `"blocking": false` |
| Permission denied | Run `chmod +x .claude/hooks/*.sh` |
| python3 not found | Install Python 3 or adjust the helper function |
| Wrong build command | Update the `project` section in config.json |
| Secrets false positive | Review the pattern list in `pre-commit.sh` |

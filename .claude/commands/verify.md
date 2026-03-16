---
description: "Run unified quality and test validation via verifier agent"
model: haiku
---

# Verifier Command

Invoke the verifier agent to run comprehensive quality and test validation.

## Agent Reference

See @agents/verifier.md for the full agent specification.

## Task

Run quality validation: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **test-driven-development** - Test quality and coverage analysis
- **verification-before-completion** - Multi-layer verification gates

## Scoring Formula

See the Verifier agent specification for the scoring formula and evaluation criteria. Pass threshold: 80/100.

## Workflow

### Phase 1: Environment Check
- Verify build tools are available
- Check for required configuration files
- Identify the project type and build system
- Determine which test frameworks are in use

### Phase 2: Build Validation
- Run the project build command
- Capture and categorize any errors or warnings
- Verify all build artifacts are generated

### Phase 3: Test Execution
- Run the full test suite
- Capture pass/fail results per test
- Identify any flaky or skipped tests
- Run coverage analysis if available

### Phase 4: Static Analysis
- Run linter(s) configured for the project
- Check for type errors (if typed language)
- Identify code style violations
- Check for known anti-patterns

### Phase 5: Integration Checks
- Verify cross-module imports resolve
- Check for circular dependencies
- Validate configuration files are consistent

### Phase 6: Report
Generate a comprehensive quality report.

## Decision Logic

- **Score >= 90**: PASS -- code is ready for commit
- **Score 70-89**: WARN -- issues should be addressed, list them
- **Score < 70**: FAIL -- significant issues found, must be fixed

## Output Format

```
## Quality Validation Report

### Status: PASS / WARN / FAIL
### Score: XX/100

### Build
- Status: PASS/FAIL
- Errors: N
- Warnings: N

### Tests
- Status: PASS/FAIL
- Passed: N
- Failed: N
- Skipped: N
- Coverage: XX%

### Code Quality
- Lint errors: N
- Lint warnings: N
- Type errors: N

### Issues
1. [CRITICAL/MAJOR/MINOR] Description
   - File: path/to/file
   - Suggestion: how to fix

### Recommendation
[Next action based on score]
```

## Usage Examples

- `/verify` -- Run full validation suite on the current project
- `/verify tests only` -- Run only the test suite
- `/verify lint` -- Run only static analysis
- `/verify build` -- Run only build validation
- `/verify path/to/module` -- Validate a specific module
- `/verify --quick` -- Run fast checks only (build + lint, skip full test suite)

## Notes

- If no arguments are provided, run the full validation suite
- Respect project-specific configuration (.eslintrc, tsconfig.json, etc.)
- Do not modify any files -- this is a read-only validation pass
- If a check cannot be run (missing tool), score that dimension as N/A and adjust weights

---
name: test
description: "Generate, run, and analyze tests for specific files or features"
argument-hint: "<file-or-feature> [--generate|--run|--coverage|--mutation]"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Test Command

Generate, execute, and analyze tests for a target file or feature.

## Agent Reference

See @agents/tester.md for the full agent specification.

## Task

Test target: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **golden-rule** - No code changes without explicit approval
- **test-driven-development** - RED/GREEN/REFACTOR workflow

## Workflow

### Phase 1: Discovery
- Identify the target file(s) or feature from $ARGUMENTS
- Detect the project's test framework and conventions (Jest, Pytest, JUnit, etc.)
- Locate existing tests for the target (co-located or in test directories)
- Analyze the target's public API, dependencies, and edge cases

### Phase 2: Test Generation (--generate)
- **Unit tests**: One test file per source file, covering every public method
- **Integration tests**: Cross-module interactions and dependency boundaries
- Follow the project's existing test naming and structure conventions
- Generate descriptive test names that document expected behavior
- Include edge cases: null inputs, empty collections, boundary values, error paths
- Mock external dependencies; never mock the unit under test

### Phase 3: Test Execution (--run)
- Run the full test suite for the target scope
- Capture pass/fail results with timing information
- Identify flaky tests (run twice if failures detected)
- Report failures with stack traces and contextual hints

### Phase 4: Coverage Analysis (--coverage)
- Run tests with coverage instrumentation enabled
- Report line, branch, and function coverage for the target
- Identify uncovered critical paths and dead code
- Suggest targeted tests to close coverage gaps

### Phase 5: Mutation Testing (--mutation)
- Identify key logic in the target (conditionals, arithmetic, returns)
- Propose mutations (negate conditions, swap operators, remove calls)
- Assess whether existing tests would catch each mutation
- Report mutation score and surviving mutants with fix suggestions

### Phase 6: Quality Assessment
- Rate test quality: assertion density, edge case coverage, readability
- Flag test anti-patterns: testing implementation details, brittle selectors, sleep-based waits
- Verify tests are deterministic and independent

## Output Format

```
## Test Report

### Target: [file or feature]
### Mode: generate | run | coverage | mutation | full

### Test Generation
- Tests created: N files, M test cases
- Types: unit (X), integration (Y)

### Execution Results
- Total: N tests
- Passed: N
- Failed: N
- Skipped: N
- Duration: Xs

### Coverage
- Lines: XX%
- Branches: XX%
- Functions: XX%
- Uncovered critical paths: [list]

### Mutation Score
- Mutants generated: N
- Killed: N (XX%)
- Survived: N
- Suggestions: [targeted tests to kill survivors]

### Quality Assessment
- Assertion density: X per test (target: >= 2)
- Edge case coverage: HIGH / MEDIUM / LOW
- Anti-patterns found: [list or "none"]

### Next Steps
- [actionable recommendations]
```

## Usage Examples

- `/test src/services/user.ts` -- Full analysis: generate, run, coverage
- `/test src/services/user.ts --generate` -- Generate tests only
- `/test src/services/user.ts --run` -- Run existing tests only
- `/test src/services/user.ts --coverage` -- Coverage analysis only
- `/test src/services/user.ts --mutation` -- Mutation testing only
- `/test auth module` -- Test the entire auth feature

## Notes

- If no flag is provided, run all phases in sequence
- Respect project .gitignore and test configuration files
- Never generate tests that depend on execution order
- Generated tests must pass before being reported as complete
- Use `/verify` after generation to validate overall project health

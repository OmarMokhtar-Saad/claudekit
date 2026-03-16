# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.x     | Yes                |

## Reporting a Vulnerability

If you discover a security vulnerability in ClaudeKit, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email: security@claudekit.dev (or open a private security advisory on GitHub)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix within 7 days for critical issues.

## Security Considerations

ClaudeKit executes shell scripts and Python scripts as part of its workflow. Users should:

- Review all hook scripts before enabling them
- Never commit secrets to configuration files
- Use the pre-commit hook's secret detection feature
- Review operations configs before execution (use `--dry-run`)
- Keep the operations scripts updated to the latest version

## Scope

This security policy covers:
- The ClaudeKit installer (`install.sh`)
- Operations scripts (validate, execute, restore)
- Hook scripts
- Agent and skill definitions (to the extent they instruct code execution)

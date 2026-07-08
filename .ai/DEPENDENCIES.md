# Dependencies

## Runtime (user-facing)

**None.** Zero Python runtime dependencies is a product feature ([DECISIONS.md](DECISIONS.md) #2). Requirements on the user's machine: Python ≥3.9, bash ≥3.2 (stock macOS OK), git. `python3` is used by hooks for JSON parsing (no jq dependency). Optional extra: `jsonschema>=4` (`pip install claude-kit[validation]`) — the ops validator uses it when present, degrades gracefully otherwise.

## Development (`pip install -e ".[dev]"`)

pytest, pytest-timeout, pytest-cov, coverage, ruff, mypy, jsonschema>=4. Also `tests/requirements.txt` for CI. Build: `setuptools>=64` (+ `build` for wheels; py3.12+ environments must install setuptools explicitly — `0c9223b`). shellcheck for shell lint (CI installs it).

## CI / GitHub Actions

All actions **SHA-pinned** (audit item 21); Dependabot (`.github/dependabot.yml`) keeps pins fresh. Workflows: `ci.yml` (11 jobs), `release.yml` (PyPI **Trusted Publishing** — no token secrets), `security.yml`. Renovate/upgrade policy: accept Dependabot PRs when CI is green; never unpin.

## MCP servers (optional templates, `templates/mcp/`)

Context7, Sequential Thinking, Playwright, Memory, Filesystem — currently referenced via `npx -y @latest` (**unpinned — known debt #11, task 014**; pin exact versions, default filesystem to read-only).

## External services

GitHub (repo, Actions, releases) · PyPI (`claude-kit` via Trusted Publishing) · Claude Code (the runtime platform — its hook/agent/settings semantics are this project's largest external coupling; watch its changelog for breaking changes to PreToolUse exit-code contract, frontmatter fields, settings.json schema).

## Version constraints recap

Python ≥3.9 (pyproject `requires-python`) · test matrix 3.9/3.10/3.12/3.13 · ruff target py39 · mypy python_version 3.9 · bash 3.2 floor for all shipped shell.

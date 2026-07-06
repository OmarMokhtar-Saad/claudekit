<p align="center">
  <img src="https://img.shields.io/badge/ClaudeKit-v2.1.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/bash-4.0%2B-4EAA25?style=for-the-badge&logo=gnubash&logoColor=white" alt="Bash">
  <img src="https://img.shields.io/github/actions/workflow/status/OmarMokhtar-Saad/claudekit/ci.yml?style=for-the-badge&label=CI" alt="CI">
</p>

<h1 align="center">ClaudeKit</h1>

<p align="center">
  <strong>A production-grade multi-agent orchestration system for <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>.</strong><br>
  Structured planning. Review gates. Safe execution. Quality verification. Any language.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#how-it-works">How It Works</a> &middot;
  <a href="#commands">Commands</a> &middot;
  <a href="docs/ARCHITECTURE.md">Architecture</a> &middot;
  <a href="docs/CUSTOMIZATION.md">Customization</a> &middot;
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Why ClaudeKit?

Claude Code is powerful on its own. ClaudeKit makes it **structured, safe, and auditable**.

Without ClaudeKit, an AI assistant makes changes directly — no plan, no review, no rollback. With ClaudeKit, every change follows a pipeline: plan it, review it, execute it safely, verify the result.

- **Plans before code** — Every task produces a structured plan with an operations config before any file is touched.
- **Quality gates** — Plans must score 90/100 to proceed. Implementations must score 80/100 to pass.
- **Safe execution** — All file operations are atomic, backed up, and rollback-capable. 29 safety guards validate every config.
- **Any language** — Auto-detects Python, TypeScript, Java, Go, Kotlin, Swift, Rust, C#, Ruby, PHP. Extensible to any stack.
- **Zero lock-in** — Pure Markdown agents, JSON configs, shell hooks. No runtime dependencies. Copy in, copy out.

---

## Quick Start

### Install

```bash
git clone https://github.com/OmarMokhtar-Saad/claudekit.git
./claudekit/install.sh /path/to/your-project --full
```

The installer auto-detects your language, copies the `.claude/` directory into your project, generates a `CLAUDE.md` and `CONSTITUTION.md`, and configures hooks with your build/test/lint commands.

### Use

Open your project in Claude Code and run:

```
/plan Add user authentication with JWT tokens
```

ClaudeKit takes over — the Planner explores your codebase, writes a plan with an ops.json config, the Reviewer validates it, the Implementer executes it with automatic backup, and the Verifier checks the result.

### Install Options

```bash
# Full install (agents + commands + skills + hooks + operations)
./install.sh ./my-project --full

# Minimal install (agents + commands + operations only)
./install.sh ./my-project --minimal

# Pre-configure language
./install.sh ./my-project --full --language typescript

# Overwrite existing installation
./install.sh ./my-project --full --force
```

---

## How It Works

```
                    ┌─────────────┐
                    │   You ask    │
                    │  Claude Code │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Coordinator │  Classifies task, selects workflow
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │        Planner          │  Explores codebase → writes plan + ops.json
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │    Reviewer (90/100)     │  Validates plan, architecture, security
              │    ✗ Reject → re-plan   │
              └────────────┬────────────┘
                           │ ✓ Approved
              ┌────────────▼────────────┐
              │      Implementer        │  Executes ops.json with backup + rollback
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │    Verifier (80/100)     │  Tests, coverage, static analysis
              │    ✗ Fail → fix or flag │
              └────────────┬────────────┘
                           │ ✓ Passed
              ┌────────────▼────────────┐
              │        GitOps           │  Branch, commit, PR
              └─────────────────────────┘

        Parallel Agents:
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Tester  │  │ Debugger │  │ Explore  │
        │ (tests)  │  │ (diag)   │  │ (search) │
        └──────────┘  └──────────┘  └──────────┘
```

### Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Single responsibility** | Each agent has exactly one job. The Planner plans. The Reviewer reviews. No overlap. |
| **File-based handoffs** | Agents communicate through files (`plan.md`, `ops.json`, `reviewer.md`), not context passing. 85% token reduction. |
| **Config-driven** | No hardcoded build commands. Everything reads from `config.json`. |
| **Safe by default** | Atomic writes, automatic backups, execution locks, rollback on failure. |
| **Copy, not link** | Your project is fully self-contained after installation. No external dependencies. |

---

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/plan` | Create an implementation plan with ops.json | `/plan Add rate limiting to API` |
| `/review` | Validate a plan (90/100 threshold) | `/review` |
| `/implement` | Execute an approved plan | `/implement` |
| `/verify` | Run quality checks (80/100 threshold) | `/verify` |
| `/debug` | Diagnose a bug (read-only) | `/debug Why does login return 500?` |
| `/docs` | Generate documentation | `/docs API reference for auth module` |
| `/git` | Git operations | `/git commit "feat: add auth"` |
| `/coordinator` | Multi-agent orchestration | `/coordinator Migrate database schema` |
| `/explore` | Explore codebase architecture | `/explore How does the auth module work?` |
| `/security` | Run security analysis | `/security Scan auth module for vulnerabilities` |
| `/deps` | Audit dependencies | `/deps Check for outdated packages and CVEs` |
| `/rollback` | Rollback last operations | `/rollback` |
| `/test` | Generate and run tests | `/test src/services/auth.ts --generate` |
| `/deploy` | Release prep, containerize, CI/CD | `/deploy release` |
| `/performance` | Profile and optimize | `/performance src/api/ --queries` |
| `/migrate` | Database/API/framework migrations | `/migrate schema add-users-table` |
| `/batch` | Parallel large-scale changes | `/batch migrate all components from class to hooks` |

---

## Agents

| Agent | Responsibility | Model | Color |
|-------|---------------|-------|-------|
| **Coordinator** | Classifies tasks, orchestrates workflows, manages agent handoffs | Sonnet | Gray |
| **Planner** | Explores codebase, writes implementation plans + ops.json configs | Sonnet | Cyan |
| **Reviewer** | Multi-dimensional plan validation — Plan Quality (40%), Architecture (30%), Security (30%) | Opus | Blue |
| **Implementer** | Executes approved plans via operations scripts with automatic backup | Sonnet | Green |
| **Verifier** | Quality validation — Static Analysis (30%), Tests (40%), Coverage (30%) | Haiku | Purple |
| **Debugger** | Read-only root cause analysis using 4-phase systematic debugging | Opus | Red |
| **Documenter** | Creates and maintains technical documentation | Haiku | Teal |
| **GitOps** | Branching, committing, PR creation, release management | Haiku | Orange |
| **Explore** | Fast codebase exploration, pattern discovery, architecture mapping | Sonnet | Yellow |
| **Tester** | Dedicated test writing — unit, integration, E2E, coverage gap analysis | Sonnet | Magenta |
| **Security Scanner** | OWASP Top 10 scanning, secret detection, dependency CVE analysis | Opus | Crimson |
| **DevOps** | CI/CD pipelines, containerization, deployment, infrastructure-as-code | Sonnet | Silver |
| **Database Architect** | Schema design, migrations, query optimization, data modeling | Sonnet | Bronze |

---

## Operations System

The operations system is the safety layer between "plan" and "code change." Every modification goes through a validated JSON config.

### Pipeline

```
ops.json  →  validate-config-json.py  →  execute-json-ops.py  →  backups/
                 (29 guards)               (atomic + rollback)     (manifest)
```

### Operations Config Format

```json
{
  "plan": "add-error-handling",
  "operations": [
    {
      "type": "code_edit",
      "path": "src/auth.py",
      "edits": [
        { "find": "def login():", "replace": "def login() -> Result:" }
      ]
    },
    {
      "type": "file_create",
      "path": "src/errors.py",
      "content": "class AuthError(Exception):\n    pass\n"
    },
    {
      "type": "file_delete",
      "path": "src/old_auth.py",
      "reason": "Replaced by new auth module with proper error handling"
    }
  ]
}
```

### Safety Guards (26 Total)

| Category | Guards | Examples |
|----------|--------|----------|
| **Code Editing** | 11 | Pattern exists in file, no ambiguous matches, action type validation |
| **File Operations** | 6 | Protected file check, deletion reason required, file existence check |
| **Backup/Restore** | 6 | Path format consistency, backup directory writable, collision detection |
| **Security** | 3 | Null byte rejection, operation type validation |

### Protected Files

These files cannot be deleted via operations config:

`.gitignore` · `*.md` · `Makefile` · `Dockerfile` · `requirements.txt` · `package.json` · `pyproject.toml` · `tsconfig.json` · `setup.py` · `Pipfile` · `yarn.lock`

---

## Skills

ClaudeKit includes 73 reusable skills that agents load on-demand:

| Category | Skills |
|----------|--------|
| **Workflow** | writing-plans, executing-plans, brainstorming, generate-operations-config, validate-operations-config, execute-operations-config |
| **Quality** | clean-architecture, test-driven-development, verification-before-completion, systematic-debugging, refactoring-patterns, error-handling |
| **Security** | security-checklist, golden-rule (no changes without approval) |
| **API & Data** | api-design-patterns, database-migration-patterns |
| **DevOps** | ci-cd-pipeline, monitoring-observability, dependency-audit, incident-response |
| **Accessibility & i18n** | accessibility-standards, i18n-patterns |
| **Git** | git-workflow, using-git-worktrees, finishing-a-development-branch |
| **Collaboration** | multi-agent-coordination, dispatching-parallel-agents, subagent-driven-development, clarify, requesting-code-review, receiving-code-review |
| **Meta** | using-superpowers, writing-skills, constitution, documentation-standards, context-first-workflow, performance-guidelines |

---

## Hooks

| Hook | Trigger | Blocking | Purpose |
|------|---------|----------|---------|
| **pre-commit** | Before `git commit` | Yes | Validates ops.json configs, scans for hardcoded secrets |
| **post-implement** | After implementation | No | Runs build, test suite, coverage report |
| **pre-plan** | Before plan creation | No | Detects duplicate plans using string similarity |
| **pre-push** | Before `git push` | Yes | Full validation: tests, lint, build must all pass |
| **post-tool-use** | After Edit/Write/Bash | No | Tracks modifications, validates ops.json on edit |

All hook commands are configured in `.claude/hooks/config.json` — no hardcoded values.

---

## Language Support

| Language | Detection | Build | Test | Lint | Coverage |
|----------|-----------|-------|------|------|----------|
| **Python** | `pyproject.toml`, `requirements.txt`, `setup.py` | `pip install -e .` | `pytest` | `ruff` + `mypy` | `pytest --cov` |
| **TypeScript** | `package.json`, `tsconfig.json` | `npm run build` | `npm test` | `eslint` | `npm run coverage` |
| **Java** | `build.gradle`, `pom.xml` | `./gradlew build` | `./gradlew test` | `./gradlew check` | `./gradlew jacocoTestReport` |
| **Go** | `go.mod` | `go build ./...` | `go test ./...` | `golangci-lint` | `go test -coverprofile` |
| **Kotlin** | `build.gradle.kts` + `kotlin` | `./gradlew build` | `./gradlew test` | `detekt` | `./gradlew koverReport` |
| **Swift** | `Package.swift` | `swift build` | `swift test` | `swiftlint` | `swift test --enable-code-coverage` |
| **Rust** | `Cargo.toml` | `cargo build` | `cargo test` | `cargo clippy` | `cargo tarpaulin` |
| **C#/.NET** | `*.csproj`, `*.sln` | `dotnet build` | `dotnet test` | `dotnet format` | `dotnet test --collect:"XPlat Code Coverage"` |
| **Ruby** | `Gemfile` | `bundle install` | `bundle exec rspec` | `rubocop` | `simplecov` |
| **PHP** | `composer.json` | `composer install` | `phpunit` | `phpstan` + `php-cs-fixer` | `phpunit --coverage-html` |
| **Generic** | Fallback | Manual | Manual | Manual | Manual |

---

## Constitution

Each project gets a `CONSTITUTION.md` — a governance document that agents enforce:

| Article | Scope | Violation Penalty |
|---------|-------|-------------------|
| I. Architecture | Layer boundaries, forbidden dependencies | AUTO-REJECT (score = 0) |
| II. Code Quality | Style guide, naming, error handling | Major (-20 pts) |
| III. Testing | 80% new code, 90% critical paths, 70% overall | Major (-20 pts) |
| IV. Security | OWASP Top 10, no hardcoded secrets | AUTO-REJECT |
| V. Operations | ops.json mandatory, protected files, safety limits | AUTO-REJECT |
| VI. Performance | Response times, resource constraints | Minor (-5 pts) |
| VII. Documentation | Public APIs documented, plans include verification | Minor (-5 pts) |
| VIII. Review | 90/100 plan threshold, 80/100 quality threshold | Enforced automatically |

---

## Project Structure

<!-- BEGIN GENERATED:inventory -->
| Component | Count |
|-----------|------:|
| Agents    | 28 |
| Commands  | 39 |
| Skills    | 73 |
| Hooks     | 19 |
<!-- END GENERATED:inventory -->

> Counts above are generated by `scripts/gen-docs.py` from the filesystem and
> enforced in CI (`docs-drift`).

```
claudekit/
├── .claude/                          # Core system (copied to your project)
│   ├── agents/                       # 28 specialized agents
│   │   ├── coordinator.md
│   │   ├── planner.md
│   │   ├── reviewer.md
│   │   ├── implementer.md
│   │   ├── verifier.md
│   │   ├── debugger.md
│   │   ├── documenter.md
│   │   ├── gitOps.md
│   │   ├── explore.md
│   │   └── _shared/                  # Templates and protocols
│   ├── commands/                     # 39 slash commands
│   ├── skills/                       # 73 domain skills + registry
│   ├── hooks/                        # 19 workflow hooks + lib.sh
│   ├── operations/scripts/           # Validate, execute, restore
│   └── local/                        # CLAUDE.md + CONSTITUTION.md templates
├── templates/                        # 11 language-specific templates
│   ├── python/
│   ├── typescript/
│   ├── java/
│   ├── go/
│   ├── kotlin/
│   ├── swift/
│   ├── rust/
│   ├── csharp/
│   ├── ruby/
│   ├── php/
│   └── generic/
├── examples/                         # Complete example projects
│   ├── python-fastapi/
│   └── typescript-nextjs/
├── docs/                             # Documentation
│   ├── ARCHITECTURE.md
│   ├── AGENTS.md
│   ├── SKILLS.md
│   ├── HOOKS.md
│   ├── CUSTOMIZATION.md
│   └── CONSTITUTION-GUIDE.md
├── tests/                            # Test suite (110 tests)
├── .github/workflows/ci.yml          # CI/CD pipeline
├── install.sh                        # One-command installer
├── CONTRIBUTING.md
├── CHANGELOG.md
├── SECURITY.md
└── LICENSE (MIT)
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, agent interactions, file-based state management |
| [Agents](docs/AGENTS.md) | Specifications for the core agents (run `ck agents` for the full list of all 28) |
| [Skills](docs/SKILLS.md) | Skill catalog, creation guide, registry format |
| [Hooks](docs/HOOKS.md) | Hook system, `settings.json` wiring, `ECC_HOOK_PROFILE`, troubleshooting |
| [CLI Reference](docs/cli.md) | `claudekit` / `ck` command reference |
| [Customization](docs/CUSTOMIZATION.md) | Adapting ClaudeKit to your specific project |
| [Constitution Guide](docs/CONSTITUTION-GUIDE.md) | Writing governance rules and compliance articles |

---

## Requirements

| Requirement | Version | Purpose |
|-------------|---------|---------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Latest | CLI environment |
| Python | 3.8+ | Operations scripts (validate, execute, restore) |
| Bash | 4.0+ | Installer and hook scripts |
| Git | 2.0+ | Version control operations |

No external Python packages are required for production use. The operations scripts use only the Python standard library. Test dependencies (`pytest`, `jsonschema`) are listed in `tests/requirements.txt`.

---

## Examples

### Python / FastAPI

```bash
./install.sh ./my-fastapi-app --full --language python
```

See [`examples/python-fastapi/`](examples/python-fastapi/) for a complete setup with constitution, architecture rules, and testing requirements.

### TypeScript / Next.js

```bash
./install.sh ./my-nextjs-app --full --language typescript
```

See [`examples/typescript-nextjs/`](examples/typescript-nextjs/) for a complete setup with component architecture and build pipeline configuration.

---

## FAQ

<details>
<summary><strong>Does ClaudeKit work with any programming language?</strong></summary>

Yes. ClaudeKit ships templates for Python, TypeScript, Java, Go, Kotlin, Swift, Rust, C#, Ruby, and PHP. For any other language, use the `generic` template and configure your build/test/lint commands in `.claude/hooks/config.json`.
</details>

<details>
<summary><strong>Can I use only parts of ClaudeKit?</strong></summary>

Yes. Use `--minimal` to install only agents, commands, and operations scripts (no skills or hooks). You can also selectively delete components you don't need after installation.
</details>

<details>
<summary><strong>What happens if an operation fails?</strong></summary>

The executor creates a full backup before any operation runs. If any operation fails, all changes are automatically rolled back to the pre-execution state. You can also manually restore from any backup using `restore-backup.py`.
</details>

<details>
<summary><strong>Is ClaudeKit safe to use on production codebases?</strong></summary>

ClaudeKit is designed with safety as a core principle: 29 validation guards, atomic file writes, automatic backups, execution locks, protected file patterns, and mandatory review gates. The `--dry-run` flag lets you preview all changes before execution. That said, always review plans and use version control.
</details>

<details>
<summary><strong>Can I customize the review thresholds?</strong></summary>

Yes. Edit the `CONSTITUTION.md` in your project to change the plan review threshold (default 90/100) and quality verification threshold (default 80/100).
</details>

<details>
<summary><strong>Does it work on Windows?</strong></summary>

ClaudeKit requires a Unix-like environment (macOS or Linux). On Windows, use WSL (Windows Subsystem for Linux). The Python operations scripts work cross-platform, but the installer and hooks require Bash.
</details>

---

## Contributing

We welcome contributions of all kinds — bug reports, feature requests, new skills, new language templates, documentation improvements.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, development setup, and the process for adding new agents or skills.

---

## Security

If you discover a security vulnerability, please report it responsibly. **Do not open a public issue.**

See [SECURITY.md](SECURITY.md) for reporting instructions and security considerations.

---

## License

[MIT License](LICENSE) — Copyright (c) 2026 Omar Mokhtar

ClaudeKit is free and open-source software. Use it, modify it, distribute it. No restrictions.

---

<p align="center">
  <sub>Built for developers who want AI-assisted development to be structured, safe, and auditable.</sub>
</p>

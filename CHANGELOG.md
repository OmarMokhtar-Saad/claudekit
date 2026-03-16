# Changelog

All notable changes to ClaudeKit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-03-16

### Added
- 4 new agents: tester, security-scanner, devops, database-architect (total: 13)
- 9 new commands: /explore, /security, /deps, /rollback, /test, /deploy, /performance, /migrate, /batch (total: 17)
- 18 new skills including Trail of Bits-inspired security skills, enterprise patterns, and i18n/a11y (total: 45)
- 4 new language templates: Rust, C#, Ruby, PHP (total: 11)
- Official Claude Code hooks via .claude/settings.json (7 event types)
- Professional README with shields.io badges and comprehensive documentation

### Fixed
- 43+ bugs fixed across security, cross-references, and compliance
- All agent frontmatter updated with tools and example blocks per Claude Code official docs
- All skill frontmatter updated with disable-model-invocation, user-invocable, allowed-tools
- Hooks format migrated from custom config.json to official Claude Code settings.json
- Kotlin language detection now works correctly (moved before Java check)
- Template {{PROJECT_NAME}} substitution now works for all language templates
- Command injection vulnerabilities fixed in all hook scripts
- install.sh config.env sourcing security hardened

## [1.0.0] - 2026-03-16

### Added
- 9 specialized agents: coordinator, planner, reviewer, implementer, verifier, debugger, documenter, gitOps, explore
- 8 slash commands: /plan, /review, /implement, /verify, /debug, /docs, /git, /coordinator
- 27 generic skills covering planning, review, implementation, testing, debugging, git, and more
- 5 workflow hooks: pre-commit, post-implement, pre-plan, pre-push, post-tool-use
- Operations system with validate, execute, and restore scripts (CodeManifest v3.1.0)
- One-command installer (`install.sh`) with language detection
- 7 language templates: Python, TypeScript, Java, Go, Kotlin, Swift, Generic
- 2 complete examples: Python/FastAPI and TypeScript/Next.js
- CLAUDE.template.md and CONSTITUTION.template.md for project customization
- Shared agent templates and protocols
- Skills registry for agent-skill mapping
- Comprehensive documentation (Architecture, Customization, Agents, Skills, Hooks, Constitution Guide)
- CI/CD pipeline with GitHub Actions
- Issue and PR templates

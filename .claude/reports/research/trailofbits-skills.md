# Trail of Bits Claude Code Skills — Research Report

**Date**: 2026-08-25  
**Source**: https://github.com/trailofbits/skills

## Complete Skills List (40+ skills across 8 plugin categories)

### Blockchain Security (11 skills)
- **solidity-vulnerability-scanner** — Detects reentrancy, overflow, delegation patterns in Solidity
- **solana-vulnerability-scanner** — Identifies transaction validation, state management vulnerabilities
- **rust-review** — Analyzes unsafe code, concurrency hazards, FFI/panic-DoS in Rust
- **cosmos-vulnerability-scanner** — Cosmos-specific state and message handling flaws
- **cairo-vulnerability-scanner** — Cairo language vulnerability patterns
- **algorand-vulnerability-scanner** — Algorand-specific contract flaws
- **substrate-vulnerability-scanner** — Substrate blockchain vulnerabilities
- **ton-vulnerability-scanner** — TON blockchain analysis
- **code-maturity-assessor** — Risk stratification and maturity scoring
- **guidelines-advisor** — Smart contract security best practices
- **token-integration-analyzer** — Token contract audit focus

### Code & Audit Infrastructure (7 skills)
- **differential-review** — 6-phase risk-based security code review (adaptive by codebase size)
- **audit-context-building** — Domain/function-level baseline context for audits
- **audit-augmentation** — Augments existing audit findings
- **audit-prep-assistant** — Preparation workflow for audits
- **secure-workflow-guide** — Audit workflow methodology
- **agentic-actions-auditor** — Autonomous attacker modeling
- **trailmark** — Polyglot static code graph builder (25+ language parsers)

### Development & Testing (6 skills)
- **code-improver** — Code quality and style refactoring
- **pr-improver** — Pull request quality improvement
- **skill-improver** — Skill development and enhancement
- **c-review** — C/C++ vulnerability detection with Python analysis utilities
- **testing-handbook** — Unit test design patterns and strategies
- **burpsuite-project-parser** — Security testing integration

### Meta & Operations (4 skills)
- **chrome-mcp-troubleshooting** — MCP debugging and integration
- **supply-chain-audit** — Dependency and build system risk
- **verification-gap-lens** — Test coverage gap identification
- **prompt-injection-defense** — LLM input validation and attack scenarios

---

## Most Substantive Skills: Deep Structure & Effectiveness

### 1. **Differential-Review** (6-phase security review framework)

**Structure**:
- SKILL.md as entry point with risk-first decision tree
- `references/` subdirectory with `methodology.md`, `adversarial.md`, `reporting.md`
- Phase progression: Triage → Code Analysis → Test Coverage → Blast Radius → Adversarial Modeling → Reporting

**Effectiveness**:
- **Adaptive scope**: Codebase size triggers analysis depth (SMALL <20 files: full dependency analysis; MEDIUM 20–200: critical paths only; LARGE 200+: surgical essential components)
- **Risk-first prioritization**: "Authentication, cryptography, value transfer, external calls" override superficial change size
- **Explicit false positives**: "Small PR ≠ quick review" and "knowing codebase ≠ no blind spots"
- **Evidence-driven findings**: Concrete attack scenarios, git history, line numbers required; written output files ensure persistence

**Detection**: Risk classification via automated metadata; no executable scanners—pure methodology.

---

### 2. **Rust-Review** (parallel vulnerability cluster analysis)

**Structure**:
- Modular vulnerability classes mapped to parallel worker clusters
- Deterministic cluster selection based on codebase capabilities (`has_unsafe`, `has_ffi`, `has_concurrency`, `has_async`, `has_packed_repr`, `has_fs_io`)
- Output: SARIF + markdown with deduplication and FP-filtering

**Vulnerability Classes Detected**:
- Memory safety (use-after-free, double-free, `Vec::set_len` misuse, unsafe boundary violations)
- Concurrency hazards (data races, ABBA deadlocks, panic-induced DoS)
- FFI safety (ABI mismatches, `repr(C)` violations)
- Async runtime mistakes, panic-based DoS, TOCTOU, path traversal, information disclosure

**Effectiveness**:
- **Parallel workers by risk class**: Each cluster focuses on independent vulnerability domain, reducing false positives
- **Capability detection**: Only activates relevant analyzers (no FFI analysis if no `unsafe` blocks exist)
- **Severity ranking + FP-filtering** before reporting

**Detection**: Mixed—prose methodology + executable Rust AST analysis (implicit in worker design).

---

### 3. **Trailmark** (polyglot static code graph builder)

**Structure**:
- 25+ language parsers (Solidity, Rust, Python, JavaScript, Go, C/C++, Java, etc.)
- 4 enrichment passes: blast radius, entry points, privilege boundaries, taint propagation
- Outputs: named subgraphs, cross-language call relationships, structured queries

**What makes it effective**:
- **Multi-pass annotation**: Materializes security metadata as queryable subgraphs before human analysis
- **Polyglot support**: Merges supported languages, preserving cross-boundary calls (e.g., JavaScript calling Rust via FFI)
- **Security-focused queries**: Answers "which functions reach sensitive sinks," "attack surface," "untrusted data hotspots," "privilege crossing paths"
- **Evidence collection**: Produces subgraph slices and structural diffs for handoff to mutation testing, triage, variant analysis

**Detection**: Executable static analysis producing annotated graphs; no prose-only component.

---

### 4. **Audit-Context-Building** (domain/function-level baseline)

**Structure**:
- Progressive disclosure: SKILL.md → `references/ANALYSIS_FORMAT.md`, `DOMAIN_NOTES.md`, `FUNCTION_MICRO_ANALYSIS_EXAMPLE.md`
- Workflow: `audit-context.js` JavaScript asset for automation

**Effectiveness**:
- Establishes baseline context for high-risk changes in differential review
- Reduces blind spots by forcing explicit domain knowledge capture
- Integrates with differential-review and issue-writer for handoff workflows

**Detection**: Prose methodology with optional executable workflow asset (JavaScript).

---

### 5. **Testing Handbook** (unit test design patterns)

**Structure**:
- Pedagogical SKILL.md with decision trees for test strategy
- Supporting documents on testing validation and adversarial scenarios

**Effectiveness**:
- Teaches deterministic, behavior-focused test patterns
- Integrates mutation testing concepts
- Bridges code review and test coverage gaps

**Detection**: Prose methodology; no executable components.

---

### 6. **C-Review** (C/C++ vulnerability detection)

**Structure**:
- SKILL.md + Python utilities for findings assembly and analysis
- Shell scripts for code scanning integration

**Effectiveness**:
- Uses Python AST and regex tooling for pattern detection
- Produces structured findings suitable for downstream mutation testing
- Integrates with audit reporting workflow

**Detection**: Executable Python utilities + shell scripts (mixed approach).

---

### 7. **Agentic-Actions-Auditor** (autonomous attacker modeling)

**Structure**:
- Agent-driven autonomous vulnerability modeling
- Vector analysis documents in `references/`
- Integration point for differential-review's Phase 5

**Effectiveness**:
- Removes human bottleneck in adversarial scenario generation
- Produces concrete exploit chains and risk quantification

**Detection**: Agentic orchestration (no standalone executable; operates within Claude Code workflow).

---

### 8. **Supply-Chain-Audit** (dependency and build risk)

**Structure**:
- Vulnerability pattern matching for supply chain attack vectors
- Integration with audit workflows

**Effectiveness**:
- Transitive dependency analysis
- Build system configuration audit
- Manifest and lock file validation

**Detection**: Pattern-driven analysis; executable scanning potential.

---

## Strategic Value for ClaudeKit Ecosystems

### QA/Test-Automation Fleet (Java/Maven, Kotlin/Gradle, Python, Appium, API Testing)

**High-value skills to adapt**:
1. **Differential-review** — Adaptable to test code CR; 6-phase methodology applies to test strategy review
2. **Testing-handbook** — Direct adoption for deterministic test design patterns
3. **Audit-context-building** — Test environment/fixture baseline capture
4. **Trailmark** — Java/Kotlin AST analysis for test code structure; Appium test flow graphs
5. **Agentic-actions-auditor** — Test failure scenario modeling (what breaks tests?)

**Not directly applicable**: Blockchain scanners, C-review (language mismatch); Trailmark's polyglot support covers Java/Kotlin/Python but not mobile/API-specific patterns.

### Meta-Repo Shipping Skills/Agents/Hooks (ClaudeKit Itself)

**Overlaps with existing ClaudeKit skills**:
- `differential-security-review` ↔ **differential-review** — ClaudeKit's existing diff-security skill; Trail of Bits' 6-phase framework is complementary
- `security-checklist` ↔ **code-maturity-assessor** — Risk stratification methodology
- `insecure-defaults` + `prompt-injection-defense` — Supply chain + LLM-specific audit concepts
- `verification-gap-lens` ↔ **testing-handbook** — Direct alignment on test coverage gaps

**Valuable additions**:
1. **Audit-context-building** — Fills gap between ClaudeKit's checklist-driven approach and context-rich handoffs
2. **Trailmark integration** — Polyglot code graph capability for multi-language projects
3. **Agentic-actions-auditor methodology** — Autonomous scenario modeling pattern applicable beyond security
4. **Audit-augmentation** — Finding enrichment workflow for handoff pipelines

**Execution & Detection Patterns to Copy**:
- Mixed strategy: prose methodology + executable utilities (Python AST + shell scripts)
- Progressive disclosure with `references/` subdirectory
- Risk-stratified routing (size/capability-based worker cluster selection)
- SARIF + markdown reporting for tooling interoperability

---

## License & Authoring Conventions

**License**: Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)  
Required: attribution to creators, share-alike derivative works, allow downstream use

**SKILL.md Frontmatter** (YAML required):
```yaml
---
name: skill-name              # kebab-case, max 64 chars
description: "Third-person description (quoted if contains colons)"
allowed-tools: Read Grep      # Optional: space-delimited tool restrictions
---
```

**Authoring Standards**:
- **Keep SKILL.md under 500 lines** — split into `references/` subdirectory
- **Progressive disclosure** — quick start first, detailed docs linked separately
- **Gerund naming** — "analyzing-contracts" not "contract-analyzer"
- **Behavioral guidance over dumps** — teach lookup patterns, explain trade-offs
- **Third-person descriptions** with situational triggers ("Use when auditing Solidity" not "I help with security")
- **One level of reference depth** — SKILL.md links to files, files don't chain
- **Risk-first classification** — HIGH/MEDIUM/LOW for findings
- **Evidence-driven findings** — git history + line numbers + concrete scenarios
- **Executable detection** — Mix prose + Python utilities + shell scripts as needed
- **Validation before delivery** — `validate-skills.py` gates release

---

## Summary: Why Trail of Bits Skills Matter for ClaudeKit

1. **Risk-stratified methodology** — Adaptive by codebase size/capability, not blanket policies
2. **Polyglot support** — Handles heterogeneous fleet (Java, Kotlin, Python, Rust, C, Solidity, etc.)
3. **Handoff-ready outputs** — Structured findings (SARIF + markdown) suitable for downstream tooling
4. **Autonomous agentic patterns** — Models for orchestrating parallel workers and scenario generation
5. **Mixed execution strategy** — Prose guidance + executable utilities, not monolithic scripts
6. **Production maturity** — Real audit trophy case; ~40 skills across 8 domains; >1 year field validation

**Adoption strategy for ClaudeKit**: Core audit-context + differential-review methodology; adapt testing-handbook for QA fleet; integrate Trailmark concepts into skill improver; copy CC BY-SA licensing + progressive-disclosure structure.

# Specialist Agents: tester, security-scanner, devops

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

# Specialist Agents

## tester

**Purpose.** Dedicated test writing: generates unit, integration, E2E, snapshot, and contract tests for existing code to improve coverage. Writes tests only — never production code.

**Responsibilities.** Interface analysis, test planning, AAA-pattern test generation with mocks, verification that all generated tests pass, quality scoring.

**Inputs.** Target source files and test requirements. **Outputs.** Test files, coverage before/after, a Test Quality Score (Coverage + Quality + Edge Cases) / 3 with an 80/100 pass threshold, handoff to verifier or coordinator.

**Frontmatter (verbatim).**
- `name: tester`
- `description: Dedicated test writing specialist. Generates unit tests, integration tests, and E2E tests for existing code. Use when test coverage needs to be improved or new tests need to be written.`
- `model: sonnet` | `color: magenta`
- `tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]`

**Internal workflow.** Phase 1 Analyze (public symbols, types, exceptions, edge cases, mockable dependencies) → Phase 2 Plan (test types, grouping, prioritization, count estimate) → Phase 3 Generate (project conventions, descriptive describe/it, AAA, ≥2 assertions per case, mock externals but never the unit under test) → Phase 4 Verify (run tests, confirm no existing tests broke, measure coverage improvement, flag flaky tests).

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `test-driven-development`, `verification-before-completion`. Downstream: verifier (`Status: TESTS GENERATED`) or coordinator (`Status: TESTER BLOCKED`).

**Memory/context.** Test files only; never modifies production source.

**Failure recovery.** Escalation handoff to coordinator with reason (cannot generate meaningful tests / target too complex / missing dependencies), what was attempted, and a recommendation.

**Example invocation.**
```
TaskCreate:
  prompt: |
    You are the tester agent.
    Read your agent definition: .claude/agents/tester.md
    HANDOFF FROM: coordinator
    ---
    Task: Write unit tests for src/services/user.ts
    Expected Output: test files, coverage delta, quality score
    Return To: verifier
  agent: tester
```

**Improvement notes.** Not present in any coordinator classification row or pipeline diagram — it appears only in the coordinator's Handoff Table and QUICK_START's agent list. Its role overlaps tdd-guide (which also writes tests, but before implementation) — see Known Issues.

---

## security-scanner

**Purpose.** Read-only, active security auditing: SAST analysis, dependency CVE detection, secret scanning, configuration hardening review. Goes beyond the Reviewer's plan-level security checklist.

**Responsibilities.** 5-phase scan (dependency audit, SAST, configuration review, secret detection, report generation), CVSS-like severity scoring, prioritized remediation lists.

**Inputs.** Source files, dependency manifests, configs. **Outputs.** `SECURITY AUDIT REPORT` with executive summary, aggregate risk score (1–10), release recommendation (BLOCK / PROCEED WITH FIXES / PROCEED), and a handoff recommendation to the Planner for remediation planning.

**Frontmatter (verbatim).**
- `name: security-scanner`
- `description: Active security vulnerability scanner. Performs SAST analysis, dependency CVE detection, secret scanning, and configuration hardening checks. Read-only diagnostic agent. Use when the codebase needs a security audit beyond the plan review checklist.`
- `model: opus` | `color: crimson`
- `tools: ["Read", "Bash", "Grep", "Glob"]`

**Internal workflow.** Phase 1 dependency audit (npm audit / pip-audit / cargo audit / govulncheck / bundle-audit; exploitability and reachability assessment; EOL and single-maintainer flags) → Phase 2 SAST (injection, auth flaws, weak crypto, insecure deserialization, dynamic code eval) → Phase 3 configuration (security headers, TLS ≥1.2, CORS, rate limiting, error leakage) → Phase 4 secret detection (source, .gitignore coverage, unexpected places, git history sampling) → Phase 5 report with severity scoring table (9–10 CRITICAL blocks release … 1–3 LOW).

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `security-checklist`, `supply-chain-audit`; conditionally `ci-cd-pipeline`, `performance-guidelines`, `incident-response`. Runs in parallel with silent-failure-hunter in the Security Audit pipeline. Downstream: planner.

**Memory/context.** Read-only; Edit/Write FORBIDDEN. Redacts all secret values in reports.

**Failure recovery.** No partial-scan reporting: "NEVER report a clean scan without completing all 5 phases." Findings must have evidence; never dismisses without proof of non-exploitability.

**Example invocation.**
```bash
echo "Run a full security scan on the auth module before release. Produce the Security Audit Report." | \
  claude -p --agent security-scanner --model opus --allowedTools "Read,Bash,Grep,Glob"
```

**Improvement notes.** QUICK_START.md lists it as Sonnet; frontmatter says `model: opus` — a direct contradiction. It also has no coordinator classification keyword row of its own (it is only reachable via the Security Audit parallel pipeline).

---

## devops

**Purpose.** Infrastructure and deployment specialist: CI/CD pipelines (GitHub Actions structure), multi-stage Dockerfiles, Kubernetes manifests, environment/secret management, IaC directory layout.

**Responsibilities.** Pre-flight discovery of existing infra files, pipeline generation with environment gating (dev/staging/production approval table), Dockerfile hardening rules, K8s pod security rules, secret management do/do-not tables.

**Inputs.** Infrastructure requirements. **Outputs.** CI/CD configs, Dockerfiles, docker-compose, K8s manifests; handoffs to planner (new infra design) and security-scanner (security review).

**Frontmatter (verbatim).**
- `name: devops`
- `description: DevOps and infrastructure specialist. Manages CI/CD pipelines, Docker containers, Kubernetes manifests, cloud configuration, and deployment workflows. Use when infrastructure or deployment configuration needs to be created or modified.`
- `model: sonnet` | `color: steel`
- `tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]`

**Internal workflow.** Pre-flight checklist (project runtime, existing CI/container/K8s/env files, golden-rule approval) → generate per templates: 8-stage pipeline structure (trigger → env → lint → test → build → security → staging deploy → production with manual gate); 3-stage Docker builds; K8s resource structure with probes, security contexts, HPA, NetworkPolicy.

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `ci-cd-pipeline`, `containerization-patterns`, `monitoring-observability`; conditionally `security-checklist`, `supply-chain-audit`, `database-migration-patterns`. Handoff targets: planner, security-scanner.

**Memory/context.** Writes infra files only; no `.claude/state` usage documented.

**Failure recovery.** None specified beyond pre-flight blocking and its NEVER list (no :latest in prod, no secrets in configs, no root containers, no missing health checks/resource limits, always consider rollback).

**Example invocation.**
```
TaskCreate:
  prompt: |
    You are the devops agent.
    Read your agent definition: .claude/agents/devops.md
    HANDOFF FROM: coordinator
    ---
    Task: Set up GitHub Actions CI/CD for this Python project
    Expected Output: .github/workflows/ci.yml + deploy.yml
    Return To: coordinator
  agent: devops
```

**Improvement notes.** No coordinator classification row routes to devops; it is reachable only by name. No escalation/failure handoff format defined.

---


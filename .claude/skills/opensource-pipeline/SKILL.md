---
name: opensource-pipeline
description: "3-stage pipeline for safely open-sourcing private code: Sanitizer (scan) → Forker (transform) → Packager (package). Hard gate: Stage 2 only runs if Stage 1 PASSES."
type: skill
version: "1.0.0"
disable-model-invocation: false
user-invocable: false
allowed-tools:
  - Agent
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# Open-Source Pipeline Skill

A three-stage, hard-gated pipeline for transforming private/internal code into a safe, well-packaged open-source release. No stage runs until the previous stage has explicitly passed.

## The Hard Gate Rule

```
Stage 1 (Sanitizer) → PASS required → Stage 2 (Forker) → PASS required → Stage 3 (Packager)
```

**If Sanitizer returns FAIL: pipeline stops. No exceptions.**
Shipping internal infrastructure details, credentials, or PII in an open-source release is irreversible. The gate is the entire point.

## Stage 1: Sanitizer (Read-Only Audit)

**Agent:** `opensource-sanitizer` (Sonnet)  
**Input:** Target directory path  
**Output:** `PASS` or `FAIL` with findings report

### What It Scans

| Category | Examples | Severity |
|----------|----------|----------|
| Secrets / Credentials | API keys, tokens, passwords, private keys | BLOCKER |
| Internal Infrastructure | Internal hostnames, VPN endpoints, internal URLs | BLOCKER |
| PII | Email addresses, phone numbers, employee names in code | BLOCKER |
| Internal Tooling References | Internal CI/CD, proprietary SDKs, internal package names | WARNING |
| License / Legal Issues | Copyleft deps requiring disclosure, unlicensed snippets | WARNING |
| Development Artifacts | TODO with internal names, debug logs with internal data | WARNING |

### Pass/Fail Criteria

- **PASS:** Zero BLOCKER findings
- **FAIL:** Any BLOCKER finding, regardless of WARNING count

### Sanitizer Output Format

```
OPEN-SOURCE SANITIZER REPORT
==============================
Target: <directory>
Files scanned: N
Scan time: <timestamp>

VERDICT: PASS | FAIL

BLOCKER findings (must fix before Stage 2):
  [B1] src/config/db.ts:14 — Hardcoded connection string with password
       Pattern: postgresql://admin:hunter2@internal-db.company.com/prod
       Fix: Move to environment variable

  [B2] src/utils/auth.ts:88 — Internal OAuth endpoint
       Pattern: https://auth.internal.company.com/oauth/token
       Fix: Make configurable via environment variable

WARNING findings (fix before publishing but do not block):
  [W1] src/services/email.ts:22 — Internal email domain in comment
  [W2] README.md:15 — References internal Jira ticket
  [W3] package.json:8 — Private npm registry scope @company/

GATE DECISION: FAIL — 2 BLOCKER findings must be resolved
```

## Stage 2: Forker (Safe Transformation)

**Agent:** `opensource-sanitizer` acting as Forker (or dedicated agent)  
**Prerequisite:** Stage 1 must have returned PASS  
**Input:** Target directory + Sanitizer report  
**Output:** Transformed copy in `.claude/opensource-staging/`

### Transformations Applied

1. **Secret Externalization** — Replace hardcoded secrets with env var references
2. **Internal URL Scrubbing** — Replace internal hostnames with configurable placeholders
3. **Comment Sanitization** — Remove internal ticket numbers, employee names, internal notes
4. **Dependency Cleaning** — Replace private package references with public alternatives or feature-flag them out
5. **Config Template Generation** — Create `.env.example` with all required variables documented

### What Forker NEVER Does

- Does NOT delete business logic
- Does NOT rename public APIs or exported types
- Does NOT restructure the project layout
- Does NOT modify test files unless they contain secrets

### Staging Directory

All transformations write to `.claude/opensource-staging/` — the original source is never modified. This staging directory is what Stage 3 packages.

## Stage 3: Packager

**Agent:** `opensource-packager` (Haiku)  
**Prerequisite:** Stage 2 must have completed successfully  
**Input:** `.claude/opensource-staging/` directory  
**Output:** Publishable package with complete open-source scaffolding

### What It Generates

#### Required Files
- `CLAUDE.md` — Project-specific AI agent instructions (generated from actual code, never generic)
- `README.md` — With installation, usage, contributing sections
- `LICENSE` — Appropriate license (MIT default, configurable)
- `.env.example` — All required environment variables documented
- `CONTRIBUTING.md` — Development setup, PR process, code of conduct reference

#### GitHub Templates (`.github/`)
- `pull_request_template.md`
- `ISSUE_TEMPLATE/bug_report.md`
- `ISSUE_TEMPLATE/feature_request.md`
- `workflows/ci.yml` — Basic CI that matches the project's detected test runner

#### Quality Checks Before Packaging
- Verify no BLOCKERs remain in staging directory (re-runs Sanitizer on staging)
- Verify all `.env.example` variables are documented
- Verify LICENSE year matches current year
- Verify README has at minimum: description, installation, usage sections

### Packager Output Format

```
OPEN-SOURCE PACKAGER REPORT
=============================
Source: .claude/opensource-staging/
Output: .claude/opensource-output/

Files generated:
  + CLAUDE.md (project-specific, 847 chars)
  + README.md (1,203 chars)
  + LICENSE (MIT, 2026)
  + .env.example (12 variables documented)
  + CONTRIBUTING.md
  + .github/pull_request_template.md
  + .github/ISSUE_TEMPLATE/bug_report.md
  + .github/ISSUE_TEMPLATE/feature_request.md
  + .github/workflows/ci.yml

Post-package verification:
  Sanitizer re-scan: PASS (0 BLOCKERs, 0 WARNINGs)
  Env vars documented: 12 / 12
  README sections: ✓ description, ✓ installation, ✓ usage

READY TO PUBLISH
Next steps:
  1. Review .claude/opensource-output/ carefully
  2. git init in output dir + push to new GitHub repo
  3. Consider /santa for final review of CLAUDE.md and README
```

## Pipeline Orchestration

When running the full pipeline via `/opensource`:

```python
# Pseudo-orchestration (actual execution is agent-driven)

result = Sanitizer.scan(target_dir)

if result.verdict != "PASS":
    print(f"PIPELINE STOPPED: {len(result.blockers)} BLOCKERs found")
    print("Fix all BLOCKERs and re-run /opensource")
    exit()

staging = Forker.transform(target_dir, result)

# Re-verify staging before packaging
verify = Sanitizer.scan(staging.path)
if verify.verdict != "PASS":
    print("PIPELINE STOPPED: Forker introduced new issues")
    exit()

package = Packager.generate(staging.path)
print(package.report)
```

## Usage Modes

| Flag | Behavior |
|------|----------|
| (none) | Full 3-stage pipeline |
| `--sanitize-only` | Run Stage 1 only — produces blocker report without transforming |
| `--package-only` | Run Stage 3 only — assumes staging dir already exists |
| `--skip-warnings` | Treat WARNINGs as informational, never as blockers |
| `--license MIT\|Apache\|GPL` | Override license type in Stage 3 |

## Examples

```
/opensource .                          # run full pipeline on current directory
/opensource src/ --sanitize-only       # audit only — no transformation
/opensource --package-only             # package existing .claude/opensource-staging/
/opensource . --license Apache         # full pipeline with Apache 2.0 license
```

## Error Recovery

If the pipeline fails at any stage, no cleanup is needed — the original source is never modified. Simply fix the issues and re-run the pipeline from Stage 1.

If Stage 3 fails after Stage 2 has run, you can re-run with `--package-only` to avoid re-running the full transformation.

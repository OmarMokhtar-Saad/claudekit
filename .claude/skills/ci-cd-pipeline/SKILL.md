---
name: ci-cd-pipeline
description: "Use when designing or reviewing CI/CD pipelines - stage design, artifact promotion, environment gating"
user-invocable: false
---

# CI/CD Pipeline

## Core Principle

**The pipeline is the source of truth for deployment readiness.** If the pipeline passes, the code is deployable. If any stage fails, the code does not advance. No exceptions, no manual overrides for production.

---

## Pipeline Stage Design

### Standard Pipeline Stages

```
[Commit] -> [Build] -> [Test] -> [Security] -> [Stage] -> [Approve] -> [Deploy]
```

| Stage | Purpose | Failure Action |
|---|---|---|
| **Build** | Compile, resolve dependencies, produce artifacts | Block: code does not compile |
| **Unit Test** | Run fast, isolated tests | Block: logic errors detected |
| **Lint / Format** | Enforce code style and static analysis | Block: style violations |
| **Integration Test** | Test component interactions | Block: integration broken |
| **Security Scan** | CVE audit, SAST, secret detection | Block on critical/high findings |
| **Staging Deploy** | Deploy to staging environment | Block: deployment fails |
| **Smoke Test** | Verify critical paths in staging | Block: core functionality broken |
| **Approval Gate** | Human review for production | Block: not approved |
| **Production Deploy** | Deploy to production | Rollback on failure |
| **Post-Deploy Verify** | Smoke tests against production | Trigger rollback if failed |

### Stage Rules

- Each stage MUST have a clear pass/fail criterion
- Stages MUST run in order (no skipping)
- Earlier stages SHOULD be faster (fail fast principle)
- Each stage SHOULD be independently retriable without re-running previous stages

---

## Artifact Promotion

### The Artifact Rule

**Build once, deploy the same artifact everywhere.** Never rebuild for different environments.

```
Build Stage -> Artifact Registry
                    |
              [same artifact]
                    |
        +-----------+-----------+
        |           |           |
    Dev Deploy  Stage Deploy  Prod Deploy
```

### Environment Configuration

| Element | In Artifact | In Environment Config |
|---|---|---|
| Application code | Yes | No |
| Compiled assets | Yes | No |
| Database URLs | No | Yes |
| API keys / secrets | No | Yes (via secret manager) |
| Feature flags | No | Yes (via flag service) |
| Log levels | No | Yes |

### Artifact Versioning

- Use semantic versioning for releases (v1.2.3)
- Use commit SHA for intermediate builds
- Tag artifacts with metadata (git ref, build number, timestamp)
- Retain production artifacts for at least 30 days for rollback

---

## Environment Gating

### Gate Types

| Gate | When to Use | Automation |
|---|---|---|
| **Automatic** | Test stages, security scans | Fully automated pass/fail |
| **Manual Approval** | Production deploys | Human clicks approve |
| **Scheduled** | Maintenance windows | Deploys at specified time |
| **Canary** | Gradual rollout | Route percentage of traffic |

### Environment Promotion Path

```
Development -> Staging -> Production

Development: Auto-deploy on merge to main
Staging: Auto-deploy after all tests pass
Production: Manual approval + canary rollout
```

### Canary Deployment

```
Phase 1: 1% traffic  -> monitor 15 min -> check error rates
Phase 2: 10% traffic -> monitor 15 min -> check error rates
Phase 3: 50% traffic -> monitor 15 min -> check error rates
Phase 4: 100% traffic -> monitor 30 min -> declare stable
```

At any phase, if error rates exceed threshold, auto-rollback to previous version.

---

## Cache Strategies

### What to Cache

| Cache Target | Strategy | Invalidation |
|---|---|---|
| Dependencies | Cache by lock file hash | Lock file changes |
| Build artifacts | Cache by source hash | Source code changes |
| Docker layers | Layer caching | Dockerfile changes |
| Test fixtures | Cache by fixture hash | Fixture data changes |

### Cache Rules

- ALWAYS use a content-based cache key (hash of inputs)
- NEVER cache secrets or credentials
- Set maximum cache lifetime (7-30 days)
- Cache miss MUST NOT cause build failure (fallback to clean build)
- Monitor cache hit rates -- low rates indicate poor key design

### Cache Key Examples

```
# Dependencies: hash of lock file
deps-${hashFiles('package-lock.json')}

# Build: hash of source + deps
build-${hashFiles('src/**')}-${hashFiles('package-lock.json')}

# Docker: hash of Dockerfile + context
docker-${hashFiles('Dockerfile')}-${hashFiles('src/**')}
```

---

## Pipeline Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Manual deployments | Inconsistent, error-prone | Automate all deployments |
| Skipping stages for "hot fixes" | Bypasses safety checks | Fast-track pipeline with all stages |
| Building different artifacts per env | "Works on staging" != works in prod | Build once, configure per environment |
| No rollback plan | Stuck with broken deployment | Automated rollback on failure |
| Long-running test suite blocking | Slow feedback, developers avoid running | Parallelize tests, use test splitting |
| Secrets in pipeline config | Leaked in logs or artifacts | Use secret manager with injection |

---

## Pipeline Checklist

- [ ] All stages have clear pass/fail criteria
- [ ] Artifacts are built once and promoted across environments
- [ ] Secrets are managed via secret manager, never in pipeline config
- [ ] Cache keys are content-based and expire appropriately
- [ ] Production deployments require approval gates
- [ ] Rollback is automated and tested
- [ ] Pipeline execution time is under 15 minutes for core feedback
- [ ] Flaky tests are tracked and quarantined
- [ ] Pipeline configuration is version-controlled alongside application code

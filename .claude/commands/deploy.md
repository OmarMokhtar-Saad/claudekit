---
name: deploy
description: "Prepare releases, containerize, and manage deployment workflows"
argument-hint: "<action> [release|containerize|ci-setup|checklist]"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Deploy Command

Prepare releases, generate deployment artifacts, and validate deployment readiness.

## Task

Deploy action: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **golden-rule** - No code changes without explicit approval
- **verification-before-completion** - Pre-deployment verification gates

## Workflow

### Action: release
Prepare a versioned release with changelog and tags.

1. Detect current version from package.json, Cargo.toml, pyproject.toml, or build.gradle
2. Determine next version based on conventional commits (major/minor/patch)
3. Generate or update CHANGELOG.md from commit history since last tag
4. Bump version in all relevant manifest files
5. Create a signed git tag with the release notes
6. Suggest the release command (npm publish, cargo publish, etc.)

### Action: containerize
Generate a production-ready Dockerfile.

1. Detect project language, runtime, and build system
2. Generate a multi-stage Dockerfile (build + runtime stages)
3. Apply best practices: non-root user, minimal base image, layer caching
4. Generate .dockerignore if missing
5. Include health check endpoint if applicable
6. Validate with `docker build --check` if Docker is available

### Action: ci-setup
Generate CI/CD pipeline configuration.

1. Detect the repository host (GitHub, GitLab, Bitbucket)
2. Generate pipeline configuration for the detected platform:
   - **GitHub Actions**: `.github/workflows/ci.yml`
   - **GitLab CI**: `.gitlab-ci.yml`
   - **Bitbucket**: `bitbucket-pipelines.yml`
3. Include stages: lint, test, build, deploy
4. Configure caching for dependencies
5. Add environment-specific deploy jobs (staging, production)
6. Include security scanning steps (SAST, dependency audit)

### Action: checklist
Validate pre-deployment readiness.

1. **Build passes**: Compile or bundle without errors
2. **Tests pass**: Full suite green with no skipped critical tests
3. **No known vulnerabilities**: Run dependency audit
4. **Environment variables documented**: All required env vars listed
5. **Database migrations ready**: Migration files present and reversible
6. **Rollback plan exists**: Previous version can be restored
7. **Monitoring configured**: Health checks, alerts, log aggregation
8. **Documentation updated**: API docs, deployment guide current

## Output Format

```
## Deployment Report

### Action: [release|containerize|ci-setup|checklist]
### Status: READY / NOT READY / PARTIAL

### Release (if applicable)
- Current version: X.Y.Z
- Next version: X.Y.Z
- Changelog entries: N
- Files updated: [list]
- Tag: vX.Y.Z

### Container (if applicable)
- Base image: [image:tag]
- Build stages: N
- Final image size: ~XMB (estimated)
- Security: non-root, no secrets in image

### CI/CD (if applicable)
- Platform: [GitHub Actions|GitLab CI|Bitbucket]
- Stages: [list]
- File created: [path]

### Checklist (if applicable)
- [ ] Build passes
- [ ] Tests pass
- [ ] No vulnerabilities
- [ ] Env vars documented
- [ ] Migrations ready
- [ ] Rollback plan
- [ ] Monitoring configured
- [ ] Docs updated
- Overall: X/8 checks passed

### Next Steps
- [actionable recommendations]
```

## Usage Examples

- `/deploy release` -- Prepare a versioned release with changelog
- `/deploy containerize` -- Generate a production Dockerfile
- `/deploy ci-setup` -- Generate CI/CD pipeline configuration
- `/deploy checklist` -- Run pre-deployment readiness validation
- `/deploy release --major` -- Force a major version bump

## Notes

- Never push tags or publish packages without explicit user approval
- Never embed secrets or credentials in generated files
- Generated Dockerfiles should target the smallest viable base image
- CI pipelines should fail fast: lint before test, test before build
- Always include a rollback mechanism in deployment artifacts

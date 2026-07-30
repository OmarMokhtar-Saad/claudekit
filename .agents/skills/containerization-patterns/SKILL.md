---
name: containerization-patterns
description: Use when containerizing applications — covers Docker multi-stage builds, layer optimization, security hardening, health checks, compose patterns, and Kubernetes manifests.
user-invocable: false
---

# Containerization Patterns

## Core Principle

**Containers are immutable deployment units. Build once, run identically everywhere.** A container image that works in staging must be the exact same image deployed to production. Configuration differences come from the environment, not from the image.

---

## Dockerfile Best Practices

### Rule Reference Table

| Rule | Impact | Priority |
|---|---|---|
| Pin base image tags or digests | Reproducible builds | Critical |
| Use multi-stage builds | Smaller images, no build tools in prod | Critical |
| Run as non-root user | Container security | Critical |
| Use .dockerignore | Faster builds, no secrets leaked | High |
| Order layers by change frequency | Cache efficiency | High |
| Combine RUN commands | Fewer layers, smaller images | Medium |
| Use COPY not ADD | Explicit behavior | Medium |
| Set HEALTHCHECK | Orchestrator integration | High |
| Remove package caches | Smaller image size | Medium |
| Set proper ENTRYPOINT and CMD | Correct signal handling | High |

---

## Multi-Stage Build Patterns

### Pattern 1: Build and Runtime Separation

```
# Stage 1: Dependencies (cached unless lock file changes)
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --production=false

# Stage 2: Build (cached unless source changes)
FROM deps AS build
COPY src/ ./src/
COPY tsconfig.json ./
RUN npm run build

# Stage 3: Production (minimal image)
FROM node:20-alpine AS production
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
USER app
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:3000/health || exit 1
EXPOSE 3000
ENTRYPOINT ["node", "dist/index.js"]
```

### Pattern 2: Compiled Language (Go, Rust, C++)

```
# Build stage with full toolchain
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /app

# Production stage with minimal image
FROM scratch
COPY --from=build /app /app
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
USER 65534:65534
ENTRYPOINT ["/app"]
```

### Pattern 3: Python with Virtual Environment

```
FROM python:3.12-slim AS build
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS production
WORKDIR /app
RUN groupadd -r app && useradd -r -g app app
COPY --from=build /opt/venv /opt/venv
COPY src/ ./src/
ENV PATH="/opt/venv/bin:$PATH"
USER app
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Security Hardening Checklist

### Image Security

- [ ] Base image is from a trusted registry (Docker Official, Chainguard, etc.)
- [ ] Base image tag is pinned to a specific version (not :latest)
- [ ] Image is scanned for CVEs before pushing (trivy, grype, or snyk)
- [ ] No secrets or credentials baked into the image
- [ ] Build arguments with secrets use `--mount=type=secret` (BuildKit)

### Runtime Security

- [ ] Container runs as non-root user (USER directive)
- [ ] Root filesystem is read-only where possible
- [ ] Only required ports are exposed
- [ ] Linux capabilities are dropped (--cap-drop=ALL, add back only needed)
- [ ] No privileged mode (--privileged=false)
- [ ] Seccomp and AppArmor profiles applied

### Supply Chain Security

- [ ] Base images are verified with signatures or digests
- [ ] Dependencies installed from trusted registries only
- [ ] Multi-stage builds exclude build tools from production image
- [ ] .dockerignore excludes .env, .git, credentials, and IDE files

---

## Docker Compose Patterns

### Development Compose

```yaml
# docker-compose.yml (development)
services:
  app:
    build:
      context: .
      target: deps    # Stop at dependency stage for dev
    volumes:
      - ./src:/app/src          # Hot reload
      - /app/node_modules       # Preserve container modules
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=development
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: devpass
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dev"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

### Production Compose

```yaml
# docker-compose.prod.yml
services:
  app:
    image: registry.example.com/app:${VERSION}
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 128M
      restart_policy:
        condition: on-failure
        max_attempts: 3
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    read_only: true
    tmpfs:
      - /tmp
```

### Compose Rules

- ALWAYS use `depends_on` with `condition: service_healthy`
- ALWAYS set resource limits in production compose files
- ALWAYS use named volumes for persistent data
- NEVER put secrets in compose files (use `docker secret` or env files outside VCS)
- ALWAYS define health checks for every service

---

## Kubernetes Manifest Templates

### Deployment with Best Practices

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
  labels:
    app.kubernetes.io/name: app
    app.kubernetes.io/version: "1.0.0"
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: app
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        fsGroup: 1000
      containers:
        - name: app
          image: registry.example.com/app:1.0.0
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: 250m
              memory: 128Mi
            limits:
              cpu: "1"
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /ready
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
```

---

## .dockerignore Template

```
.git
.github
.env
.env.*
*.md
LICENSE
docker-compose*.yml
Dockerfile*
.dockerignore
node_modules
__pycache__
*.pyc
.pytest_cache
coverage/
.nyc_output
.idea
.vscode
*.swp
*.swo
```

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Using :latest tag | Non-reproducible builds | Pin specific version or digest |
| Running as root | Container escape = host root | USER directive with non-root |
| COPY . . without .dockerignore | Secrets and junk in image | Maintain .dockerignore |
| Installing dev dependencies in prod | Larger attack surface, bigger image | Multi-stage with prod-only deps |
| Single-stage Dockerfile | Build tools in production image | Multi-stage builds |
| Hardcoded config in image | Cannot change without rebuild | Environment variables or config mounts |
| No health check | Orchestrator cannot detect failures | HEALTHCHECK instruction |
| ADD for local files | Unexpected extraction behavior | COPY for files, ADD only for URLs/tarballs |

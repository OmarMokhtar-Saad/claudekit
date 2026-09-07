# OmniRoute Research Report

**Date:** 2026-09-06  
**Inquiry:** Evaluate OmniRoute as a reference for ClaudeKit's multi-agent orchestration patterns, particularly routing and resilience strategies.

## 1. Project Identification

**Repository:** [diegosouzapw/OmniRoute](https://github.com/diegosouzapw/OmniRoute)  
**Language:** TypeScript 100% (zero `any` in core)  
**License:** MIT  
**Scale:** 352+ AI providers, 1,200+ models; 3,025 merged PRs from 535 external contributors  
**Status:** Active; comprehensive Next.js 16 + React 19 + Tailwind dashboard; npm + Docker + Electron + PWA deployment options  

(Note: Multiple forks exist—ChrisCompton, pitbaden, BunsDev—but diegosouzapw is the canonical upstream with 550+ contributors and 1.51B free tokens/month routing track record.)

## 2. Core Problem & Architecture

**Problem:** Fragmented AI inference—users must manage multiple API keys, quotas, providers' outages, and cost/latency tradeoffs across 300+ provider surfaces. OmniRoute unifies them behind a single OpenAI-compatible endpoint.

**Architecture (3-layer):**
- **Routing intelligence:** 19 strategies (Priority, Cost-Optimized, Least-Used, LKGP, Fusion, Pipeline, Auto-Combo); `auto` model ID auto-selects balanced defaults; task-specific variants (`auto/cheap`, `auto/fast`, `auto/coding`).
- **Resilience layer:** Provider circuit breakers (whole-provider failure isolation) + connection cooldown with exponential backoff (per-account) + model-specific lockouts (per-model 429 handling).
- **Compression & telemetry:** 12-stage pipeline (RTK, Caveman, LLMLingua-2, etc.) saves 15–95% tokens; optional cost headers (X-OmniRoute-* on every response).

## 3. Routing Model (Mechanism & Configuration)

### Mechanism
The **Auto-Combo engine** dynamically scores every candidate provider across **16 factors:** health status, available quota, cost efficiency (live pricing data), latency, task suitability, model quality, and model lockout state. Scoring is continuous; not a static config.

### Configuration Shape
1. **Combos** (provider chains, persisted in SQLite dashboard):
   - *Premium combo:* Claude Opus → GLM-4.7 → MiniMax (tier-based fallback)
   - *Zero-cost combo:* Kimi K2.7 → Qwen (free-to-free fallback)
   - UI drag-and-drop reordering; no YAML/JSON config files required.

2. **Account-level routing strategies** (6 built-in):
   - **Fill First:** Primary exhausts quota before switching
   - **Round Robin:** Cycles through accounts (sticky limit: 3 calls)
   - **P2C:** Picks healthier of 2 random accounts
   - **Random:** Fisher-Yates shuffle per request
   - **Least Used:** Routes to oldest `lastUsedAt` timestamp
   - **Cost Optimized:** Lowest priority value preference

3. **Fallback chains** define global ordering for all requests (e.g., Subscription → API Key → Cost-optimized → Free).

4. **Auto-routing variants** ship preset—no user configuration:
   - `auto` = balanced (default)
   - `auto/coding` = optimized for code generation
   - `auto/cheap` = minimize cost
   - `auto/fast` = minimize latency

### Configuration Minimal Principle
Fresh installs work **zero-config**. Keyless free providers (OpenCode, Felo) pre-connected. Advanced customization is **API-driven** (dashboard combos) not file-based. Reflects declarative, runtime-adaptive routing design.

## 4. Notable Engineering Practices

### Code Quality & Testing
- **60%+ coverage gate** enforced (statements, lines, functions, branches)
- **122 unit test files** across providers, rate limiting, caching, DB, OAuth, API validation
- **Zod v4 schemas** validate all inputs (not string parsing)
- **Error handling discipline:** Catch blocks must include intent rationale or emit `console.debug` for external failures—never silently swallow errors in SSE streams
- **TypeScript strict + TSDoc** on all `src/` code

### Branching & Release
- **Feature branches** always off active `release/vX.Y.Z`, never direct to `main`
- **Conventional commits** (feat:, fix:, docs:, test:, refactor:, chore:)
- **Auto-publish to npm** when GitHub Release created; integrity sentinel via `BUILD_SHA`
- **Changelog fragments** under `changelog.d/` for user-facing changes (incremental, not hand-edited)

### Security Patterns
- **Public credentials** routed through `resolvePublicCred()` (never string literals)
- **Error responses** sanitized via `buildErrorBody()` to prevent stack trace leakage
- **Shell commands** passed via environment variables, not string interpolation
- **Credentials encrypted at rest** (AES-256-GCM); local-first (no vendor prompt-processing hop)
- **Prompt-injection guards** on every LLM route

### Repository Structure
- **120 domain modules** in SQLite schema (modular provider definitions)
- **CLI-driven admin:** 80+ commands for setup, configuration, health, remote instance control
- **Multi-deployment:** npm (global), Docker (multi-arch), Electron, PWA, Termux/Android
- **MCP server:** 110 tools over stdio/HTTP/SSE for agent integration
- **A2A protocol:** JSON-RPC 2.0 for agent-to-agent communication

### Documentation Conventions
- **Wiki** with separate guides: Setup, User, API Reference
- **Contributing guide** with explicit development workflow, testing checklist, security checklist
- **README first-class:** stats, architecture, quick-start, deployment options in one file
- **Telemetry docs:** Optional, disabled by default; cost headers on responses (X-OmniRoute-*)

## 5. Outage, Rate Limit, Capability Tier Handling

### Outage Resilience
- **Circuit breaker states** tracked per-provider: CLOSED (healthy) / DEGRADED (slow/flaky) / OPEN (failed) / HALF-OPEN (testing recovery)
- **Auto-recovery:** Circuit waits for exponential-backoff interval, then enters HALF-OPEN; one successful request moves to CLOSED
- **Per-account cooldown:** Failed connection gets cooldown timer; next attempt after backoff

### Rate Limit Handling
- **Upstream Retry-After hints** honored (respects provider directives)
- **Model-specific lockout:** If a specific model exhausts quota (429), only that model is locked; combo can still route to alternatives
- **Wait-for-cooldown setting:** Auto-retries when all candidates cool down simultaneously, preventing premature failures
- **Live quota tracking:** Combo candidates scored by remaining tokens/month and current account load

### Capability Tiers
- **Model-level fallback:** Combo defines exact tier sequence (e.g., Claude Opus → GLM-4 → MiniMax means capability degradation steps)
- **Auto-combo scoring:** Task suitability factor means `auto/coding` prefers code-trained models; `auto/cheap` prioritizes low cost; `auto/fast` prioritizes low latency
- **Global fallback chain:** Subscription → API Key → Cheap → Free ensures service never fully stops

## Key Ideas Transferable to ClaudeKit

1. **Combo pattern:** Ordered provider chains (like skill selection) with UI-driven reordering beats file-based config.
2. **19-strategy routing library:** Pluggable strategy set (Priority, Cost, Random, P2C, LKGP) as a reusable module.
3. **Auto-combo scoring:** 16-factor dynamic scoring (health, cost, latency, task fit) for automatic agent/skill selection without explicit policy files.
4. **Circuit breaker + cooldown + lockout:** Three-layer resilience; copy this exactly for agent/skill failure isolation.
5. **Compression pipeline:** Modular stack (RTK → Caveman → LLMLingua-2) saves tokens; architecture reusable for prompt optimization.
6. **Conventional commit + changelog.d/:** Incremental changelog fragments enforced at PR time prevents hand-edit drift.
7. **Zod validation on all inputs:** Shields against malformed agent/skill definitions.
8. **MCP server + A2A protocol:** Both present in OmniRoute; ClaudeKit already has MCP integration—study how OmniRoute exposes 110+ tools over multiple transports.
9. **Zero-config principle:** Fresh deploys should work without keys; pre-load free/demo agents/skills.
10. **Build integrity sentinel:** `BUILD_SHA` for VPS/fleet deployments; ClaudeKit's fleet-sync model could adopt same guarantee.

---

**Sources:**
- [OmniRoute GitHub Repository](https://github.com/diegosouzapw/OmniRoute)
- [OmniRoute README](https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/README.md)
- [OmniRoute User Guide](https://github.com/diegosouzapw/OmniRoute/blob/main/docs/guides/USER_GUIDE.md)
- [OmniRoute Contributing Guide](https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/CONTRIBUTING.md)
- [OmniRoute Official Site](https://www.omniroute.online/)
- [DevToolLab Blog: OmniRoute Overview](https://devtoollab.com/blog/omniroute-free-ai-gateway)

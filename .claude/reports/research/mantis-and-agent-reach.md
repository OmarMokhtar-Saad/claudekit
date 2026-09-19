# Technical Research: Mantis & Agent-Reach

Retrieved: 2026-09-16

---

## 1. Google Mantis

**Repository:** https://github.com/google/mantis

### What It Is

Mantis is a modular, stack-agnostic security review toolkit for AI coding agents to autonomously find, reproduce, and patch vulnerabilities in software. Built on Google's Agent Development Kit (ADK), it orchestrates 15+ specialized agents through an 18-stage deterministic pipeline that enforces security invariants via runtime gates—not prompt constraints—including code indexing, threat modeling, research execution, sandbox-based verification, adversarial patching, and risk calibration. All findings must be manually verified by security experts before reporting. Last commit: 2026-09-13. **1,559 stars.** Apache 2.0. Production-grade, actively maintained.

### Concrete Mechanisms

#### 1. Security Invariant Enforcement (Deterministic Gates)
Rather than instruction-based constraints, the runtime enforces six core invariants via `sandbox_tools.py` and `schemas.py` (Pydantic validation):
- Evidence & Re-attack (sentinel checks)
- Separation of Duties (orchestrated by `mantis-patch` agent)
- Regression Tracking (lineage schemas + snapshot matching)
- Target Immutability (read-only host, mutations in `workspace/` or isolated sandboxes)
- State Resumption (`BudgetController` checkpointing with resumable run IDs)
- Fail-Safe Backward Compatibility (schema defaults + degradation gates)

#### 2. 18-Stage Multi-Agent Pipeline
Coordinated workflow with budget enforcement (2,000 LLM calls, 500 graph steps):
```
History → StructuralIndex → Architect → ThreatModeler → Planner
  ↓
Researcher → Deduplicator → Reviewer → Critic → Reproducer
  ↓
Chainer → Patcher → Calibrator → Reflector → Reporter
```
Each stage is a specialized agent with isolated execution. The `mantis-plan` agent reads `workspace/kb/THREAT_MODEL.md` and outputs `workspace/plan.json` containing investigations, then subsequent passes use Mode B (targeted deep dives) versus Mode A (exhaustive crawl).

#### 3. Sandbox Abstraction Layer
Four isolation backends configured in `workflow.json`/`workflow.local.json`:
- Static-only (no virtualization)
- gVisor (OCI container)
- MicroSandbox (hardware microVM)
- Hardened GCE VMs (cloud)

Tool registry validation, topological checks, and sandbox policy enforcement are deterministic gates.

#### 4. Structural Index + KB Architecture
`mantis-structural-index` and `mantis-pipeline-adapter` maintain a central canonical indexing that defines locator resolution and semantic units. Reference files include `calibration_rules.md` and `patch_rebasing.md` guidance.

### Transferable Ideas (Verbatim Excerpts)

**Separation of Duties via Orchestration:**
> "Separation of Duties – Orchestrated by `mantis-patch` to prevent self-grading bias"

Rather than a single agent grading its own patches, a dedicated orchestrator agent hands off to a separate patching agent. This is enforced at the runtime level, not left to prompt discretion.

**State Resumption Design:**
> "Strictly read-only on the host target checkout; all mutations constrained to `workspace/` or isolated guest sandboxes"

Checkpointing is managed by `BudgetController` and resumable via `--resume <run_id>`, enabling long-running audits to survive interruption without losing progress.

**Configuration Auto-Healing:**
From reference implementation docs: "When you run `./run.sh` or `scripts/configure.py --auto`, Mantis auto-heals unconfigured placeholders." Layered config (base `workflow.json` + machine-specific `workflow.local.json`) is a reusable pattern for agent personalization.

### Dependencies & Assumptions

- **Language:** Python
- **Runtime:** Google ADK (proprietary Agent Development Kit)
- **External services:** None mandatory (sandbox backends are optional; static-only works offline)
- **Database:** SQLite for checkpoint storage
- **MCP servers:** None required

---

## 2. Agent-Reach

**Repository:** https://github.com/Panniantong/agent-reach

### What It Is

Agent-Reach is a Python CLI that gives AI agents "eyes to see the entire internet" by providing a unified abstraction layer for scraping, searching, and reading content from 15+ platforms (Twitter, Reddit, YouTube, Bilibili, GitHub, Xiaohongshu, etc.) without configuration. It handles multi-backend selection (primary + automatic fallback), platform-specific command routing, and browser session management via Chrome DevTools Protocol. Cookies and auth are stored locally and never transmitted. Last commit: 2026-09-15. **82,191 stars.** MIT. Widely adopted, production-grade.

### Concrete Mechanisms

#### 1. Channel Abstraction with Multi-Backend Selection
Each platform (YouTube, Twitter, GitHub, etc.) is a `Channel` object with attributes:
```python
class Channel:
    name: str              # "youtube"
    description: str       # "YouTube Videos"
    backends: List[str]    # ordered list: ["yt-dlp", "youtube-cli"]
    tier: int              # 0=zero-config, 1=free key, 2=setup
    active_backend: str    # currently active (set by check())
    
    def ordered_backends(config) -> List[str]:
        # Respects user overrides via <channel>_backend env var
        # Unknown values ignored so stale overrides never hide working backends
        
    def check(config) -> Tuple[str, str]:
        # Returns ('ok'|'warn'|'off'|'error', message)
        # MUST "really probe" tools, not just shutil.which()
```

Backend switching reorders the list; system treats `backends[0]` as preferred with fallbacks in list order.

#### 2. Platform-Specific Skill Routing
Skill activates when users mention research/search keywords. Routes through capability model:

| Category | Platforms | Backends |
|----------|-----------|----------|
| Search | Exa, GitHub | API-based (zero-config) |
| Social | Twitter, Bilibili, Reddit, etc. | OpenCLI + platform CLIs |
| Career | LinkedIn, Boss | Chrome DevTools + tools |
| Web | URLs, RSS | Jina, curl |
| Video | YouTube, Bilibili | yt-dlp, platform tools |

**Capability tiers:** 0 (no setup), 1 (free API key), 2 (browser/auth required).

#### 3. Diagnostic Interface
```bash
agent-reach doctor --json
```
Reports each channel's status and current active backend. This enables agents to declare platform usage before execution and understand fallback routing.

#### 4. Session & Cookie Management
For authenticated platforms (Xiaohongshu, Twitter, Reddit, Boss Zhipin), the system manages browser sessions via CDP (Chrome DevTools Protocol) with "Cookie 只存在你本地，不上传不外传" (cookies stored locally, never transmitted).

### Transferable Ideas (Verbatim Excerpts)

**Backend Abstraction Principle:**
> "Switching backends means reordering this list through user configuration—not code modification."

Each channel maintains an ordered list of backends; user config (env var or settings) reorders without code changes. This decouples capability discovery from implementation selection.

**Robust Backend Probing:**
> "Subclasses should 'really probe them' rather than relying on `shutil.which()` alone, since stale virtual environment shims may pass that check but fail execution."

The `check()` method must execute the tool (e.g., `yt-dlp --version`), not just check if it exists, because virtual env artifacts can deceive file-based detection.

**Stale Override Safety:**
> "Unknown values are ignored so a stale override can never hide working backends."

If a user sets `YOUTUBE_BACKEND=old-tool-name` and that tool is removed from the list, the system ignores it and falls back to `backends[0]` instead of failing silently.

### Dependencies & Assumptions

- **Language:** Python ≥3.10
- **Core deps:** requests, feedparser, pyyaml, loguru, rich, yt-dlp (v2026.07.04+)
- **Optional:** playwright, browser-cookie3 (for browser-based platforms)
- **No MCP servers required** (standalone CLI tool)
- **External services:** Optional (Exa API for search, GitHub API, platform CLIs via PATH)
- **Runtime:** Stores persistent data in `~/.agent-reach/`, temp in `/tmp/`

---

## Cross-Repo Insights

**Mantis** emphasizes **deterministic enforcement** (runtime gates, schema validation, separation of duties) for high-assurance security workflows.

**Agent-Reach** emphasizes **multi-backend abstraction** (swappable implementations, tier-based capability discovery, diagnostic interfaces) for resilient capability integration.

**Shared patterns:**
- Configuration auto-healing and layering (Mantis: `workflow.json` + `workflow.local.json`; Agent-Reach: env overrides with fallback logic)
- Deterministic validation (Mantis: Pydantic schemas; Agent-Reach: `check()` probing)
- State resumption / checkpoint model (Mantis explicit; Agent-Reach implicit in backend persistence)
- Separation of verification from execution (Mantis agents; Agent-Reach channel abstraction)

Both repos are production-grade, actively maintained (commits within 48 hours of 2026-09-16), and emphasize **runtime guarantees over prompt constraints**.

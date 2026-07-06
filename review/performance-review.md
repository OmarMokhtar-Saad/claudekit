# ClaudeKit — Performance Review (Performance Engineer)

**Date:** 2026-07-05
**Frame:** For a prompt-asset framework, "performance" = (a) token & latency economy of context loaded into every session, (b) per-tool-call hook overhead, (c) CLI/install speed.
**Method:** `wc -c` on assets (÷4 ≈ tokens), live `time` of hooks and CLI on this machine (Python 3.12, Linux).

---

## 1. Always-on / mandatory-per-session context

Claude Code auto-loads on session start: the project `CLAUDE.md`, hook stdout (SessionStart), and — because agents/skills/commands are markdown with frontmatter — their **descriptions** are surfaced for routing. Measured sizes:

| Asset | Bytes | ≈ Tokens | Loaded when |
|---|---|---|---|
| Generated `CLAUDE.project.md` (from template) | ~1,980 | ~495 | Every session (always) |
| Generated `CONSTITUTION.md` | ~5,366 | ~1,340 | Referenced/loaded most sessions |
| SessionStart hook stdout | ~5 lines | ~60 | Every session |
| **Agent frontmatter (30 agents, name+desc)** | ~26,020 | ~6,500 | Surfaced for agent routing |
| **Skill frontmatter (74 skills)** | ~16,304 | ~4,076 | Surfaced for skill routing |
| **Command frontmatter (39 commands)** | ~7,391 | ~1,848 | Surfaced for command routing |
| `skills-registry.json` | 28,304 | ~7,076 | If loaded by router/CLI |
| `.claude/agents/_shared/*` (7 files) | 32,161 | ~8,040 | On-demand per agent (not always) |

**Mandatory floor per session** (CLAUDE.md + CONSTITUTION + session-start): **~1,900 tokens** — reasonable.

**Routing-surface tax** (agent + skill + command descriptions the model must see to pick one): **~12,400 tokens** before any work happens. This scales linearly with catalog size and is the dominant token cost. The registry JSON (~7,076 tokens) is a **near-duplicate** of the skill frontmatter (~4,076 tokens) — if both are ever loaded, ~11k tokens describe the same 74 skills twice.

Full asset footprint on disk: `.claude` = **1.74 MB**, `templates` = **0.37 MB**; skills markdown alone = **439 KB** (~110k tokens if ever fully expanded, but skills load on-demand so this is not per-session).

---

## 2. Duplicate content loaded twice

- **skills-registry.json vs skill frontmatter** — same 74 skill names+descriptions in two formats (~7k + ~4k tokens). Pick one source of truth. Est. saving if the model only sees frontmatter: **~7,000 tokens/session**.
- **`.claude/skills` vs `templates/skills`** — 13 skill names are duplicated across both trees (`autonomous-loop`, `codebase-mapping`, `command-flags`, `context-priming`, `hook-profiling`, `incident-response`, `mcp-integration`, `prompt-injection-defense`, `safe-command-approval`, `session-continuity`, `spec-driven-development`, `token-optimization`, `usage-monitoring`). install.sh copies **both** into `.claude/skills/`, so the installed catalog carries near-identical pairs. Disk + routing bloat; dedupe at install.
- **74 installed skills is a large routing catalog.** Many are niche (`insecure-defaults`, `property-based-testing`, `static-analysis-integration`). Every one adds ~55 tokens of description to the routing surface whether or not it's ever used.

---

## 3. Hook overhead per tool call

Subprocess count from `.claude/settings.json`:

- **Every `Write`/`Edit`:** 3 hooks (ops-enforcement, config-protection, security-reminder). Each spawns `bash` → `git rev-parse` → **2-3 `python3` interpreters** to parse JSON fields. That's ~9-12 process spawns per edit.
- **Every `Bash` call:** 4 hooks (pre-commit-gate wrapper, commit-quality, pre-push-gate wrapper, block-no-verify) + unconditional `suggest-compact &`. Each wrapper spawns `bash` + `git rev-parse` + a `python3` to extract `command`. ~12-15 spawns per Bash call.
- Each hook independently re-runs `git rev-parse --show-toplevel` and re-invokes `python3` for JSON parsing (cold interpreter each time).

**Measured (this machine):**
- `python3 -c pass` cold start: **~12 ms** (each hook pays this 1-3×).
- `block-no-verify.sh` (1 hook, 1 python parse): **~46 ms**.
- `commit-quality.sh` (non-git early-exit): **~22 ms**.
- `session-start.sh` (multiple python3 config reads): **~93 ms**.
- **Edit chain (3 hooks) + Bash chain (2 representative): ~322 ms** wall for one simulated edit+command round.

So a realistic **Edit tool call costs ~150-250 ms of hook latency**, a **Bash call ~200-300 ms**, dominated by repeated Python interpreter cold-starts and `git rev-parse`. Over a session of hundreds of tool calls this is tens of seconds of pure hook overhead, plus it serializes before the tool result returns for **blocking** (non-`&`) hooks.

Biggest wins:
1. **Collapse per-edit hooks into one dispatcher script** that reads stdin once, parses JSON once (single `python3`), and runs all checks in-process. Cuts ~3 python spawns → 1 per edit. Est. **~60-100 ms saved per Edit**.
2. **Cache `git rev-parse`** — settings.json calls it in ~14 separate hook commands; resolve `ROOT` once (env from SessionStart) instead of per-hook. Est. **~5-10 ms × N hooks**.
3. **Replace `python3 -c` JSON extraction with `jq`** (single fast binary) or do it inside the one dispatcher. Python cold-start (~12 ms) is the per-hook tax; `jq` is ~1-2 ms.

---

## 4. CLI startup

`time python3 src/cli/main.py --help` (from repo root): **~211 ms**. `main.py` is 396 lines with only stdlib imports (`argparse`, `json`, `os`, `shutil`, `subprocess`, `sys`, `time`, `pathlib`) — the cost is essentially Python interpreter start (~120-140 ms baseline here) + import. Acceptable for a CLI, but note the console scripts don't currently install (code-review P0 build backend), so this path is only reachable via `python3 src/cli/main.py`. No lazy-import work needed; the ~200 ms is interpreter-bound, not code-bound.

---

## 5. Install speed

- **Network calls: 0** (`grep -c curl|wget|git clone install.sh` = 0) — install is pure local file copy, fast and offline-capable. Good.
- **Files copied (full mode):** ~37 agents + ~52 commands (core+templates) + ~87 skill markdown files + 12 operations scripts + 15 hooks + 7 modes ≈ **200+ files**, total installed tree **~209 files / 1.74 MB**.
- Cost is dominated by many small `cp` calls in loops (per-skill-dir loop, lines 183-199) plus **3 `python3` invocations** (hook config JSON edit, and `sed` template renders). Wall time is sub-second on any modern disk; not a concern. The only inefficiency is copying **both** `.claude/skills` and `templates/skills` (the 13 duplicates from §2), inflating the installed catalog.

---

## 6. Token-waste ranking (highest impact first)

| Rank | Optimization | Est. saving | How |
|---|---|---|---|
| 1 | Don't load `skills-registry.json` **and** skill frontmatter | **~7,000 tok/session** | Single source of truth for skill routing; drop the JSON from the model-visible path. |
| 2 | Prune / tier the 74-skill catalog (lazy-describe rarely-used skills) | **~2,000-4,000 tok/session** | Keep top ~20 core skills in the routing surface; move niche skills behind explicit invocation. ~55 tok each. |
| 3 | Dedupe the 13 `.claude/skills` ↔ `templates/skills` pairs at install | **~700 tok** + disk | Copy one canonical copy; skip template dup if same name exists. |
| 4 | Trim CONSTITUTION generated per project (~1,340 tok) if loaded every turn | **up to ~1,000 tok** | Load on-demand / summarize; keep full text in file, load a 1-paragraph digest. |
| 5 | Trim `_shared/*` (~8k tok) loading — ensure loaded per-agent-on-demand, not globally | **~8,000 tok** if currently over-loaded | Confirm agents pull only the shared templates they cite; only `QUICK_START.md` references `_shared`. |

## 7. Latency-waste ranking (seconds saved)

| Rank | Optimization | Est. saving | How |
|---|---|---|---|
| 1 | One dispatcher hook per event (single stdin read + single python parse) | **~60-100 ms / Edit, ~80-120 ms / Bash** | Merge the 3 edit-hooks and the Bash-hooks into one script each. |
| 2 | Resolve `git rev-parse` once (env), not per-hook | **~5-10 ms × ~14 hook cmds** | Set `CK_ROOT` in SessionStart; reference in all hooks. |
| 3 | Replace per-hook `python3 -c` JSON parse with `jq` | **~10 ms / hook** | jq ~1-2 ms vs python ~12 ms cold start. |
| 4 | Ensure only advisory hooks use `&`; keep blocking guards synchronous but fast | neutral | Already mostly done; don't background guards. |

---

## Scores & summary

**Install:** fast, offline, no network — good. **CLI:** ~211 ms, interpreter-bound — fine. **Hooks:** the real cost — ~9-15 process spawns and ~150-300 ms per tool call from repeated Python cold-starts and `git rev-parse`, worth consolidating into per-event dispatchers. **Tokens:** the routing surface (~12.4k tokens of agent/skill/command descriptions) plus a redundant registry JSON (~7k duplicate) is the dominant per-session cost; the 74-skill catalog and `.claude`/`templates` skill duplication inflate it further. Mandatory floor (CLAUDE.md + CONSTITUTION) is lean at ~1.9k tokens.

Top single wins: **(1)** stop loading skills-registry.json alongside frontmatter (~7k tok/session), **(2)** collapse per-tool-call hooks into one dispatcher (~100 ms/call), **(3)** prune/tier the skill catalog.

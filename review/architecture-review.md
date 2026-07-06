# ClaudeKit — Architecture Review

**Scope:** folder organization, module boundaries, dependency graph, distribution, packaging, extension model, configuration, duplication, scalability.
**Stance:** future maintainer/CTO. Severities: **P0** = broken/user-harming now · **P1** = structural defect, fix this quarter · **P2** = debt, fix opportunistically · **P3** = polish.

---

## 1. Executive Summary

ClaudeKit's conceptual architecture (agents ↔ artifacts ↔ operations engine ↔ hooks) is sound and even elegant. Its *physical* architecture is not: the pip package cannot build, the installer omits the file that makes hooks work, four different version numbers coexist, ~13 skills exist in two diverged copies, install logic is hardcoded prose in bash rather than driven by any manifest, and every count in the docs is stale. The repo is a **prompt-asset monorepo pretending to be a Python package**, and the pretense is where almost all defects live.

The good news: nothing here requires redesigning the ideas. It requires one honest decision — *the manifest is the source of truth, and one installer consumes it* — plus a packaging cleanup.

---

## 2. Findings

### 2.1 Packaging & Distribution

#### F-1. The pip package cannot be built or installed — **P0**
`pyproject.toml` declares:

```toml
build-backend = "setuptools.backends._legacy:_Backend"
```

No such module exists in any setuptools release (verified: `import setuptools.backends` → `ModuleNotFoundError`, setuptools 59.6). Every `pip install .`, `pip install -e .`, and the documented `docs/cli.md` install path fails at build time. The `claudekit`/`ck` entry points are unreachable. This means **one of the two advertised distribution channels has never worked** in its current form — which also tells us no CI job exercises `pip install` (confirmed: CI never builds the package).

**Fix:** `build-backend = "setuptools.build_meta"` (or better: migrate to `hatchling`). Add a CI job that does `pip install . && claudekit --version && claudekit doctor` in a temp project. This is a one-line fix; the absence of any test catching it is the deeper finding.

#### F-2. `src.*` installed as a top-level package named `src` — **P0**
```toml
[tool.setuptools.packages.find]
include = ["src*"]
[project.scripts]
claudekit = "src.cli.main:main"
```
Once F-1 is fixed, this ships a top-level importable package literally called `src`. Any other project on the machine that also (mis)packages `src`, or any user code doing `import src`, collides. It also leaks an implementation detail into the public namespace and makes the console script fragile.

**Fix:** Adopt the actual src-layout: `src/claudekit/{cli,security,ops}/`, `packages.find where = ["src"]`, entry point `claudekit.cli.main:main`. Keep a deprecation shim only if anything imports `src.security` externally (nothing does — see F-7).

#### F-3. The wheel contains no product — **P1**
No `MANIFEST.in`, no `package-data`, no `tool.setuptools.data-files`. A built wheel would contain `src/**` only: the CLI and two security modules — **not** `.claude/` (agents/skills/commands/hooks/operations), not `templates/`, not `install.sh`. `claudekit init` papers over this by hunting for a repo checkout at runtime (`find_claudekit_root`: `~/claudekit`, `~/.claudekit`) and subprocessing `install.sh`. So the pip artifact is a wrapper that only works if you *also* did the git-clone install. The two distribution paths are not redundant; the pip path is **parasitic on the other**.

**Fix:** Package the assets: move the canonical asset tree into `src/claudekit/assets/` (or use `importlib.resources`), have `claudekit init` install from packaged assets, and reduce `install.sh` to a bootstrap that downloads/installs the pip package (or a pure-bash fallback for no-Python environments). One code path, two entry ramps.

#### F-4. Version chaos: four disagreeing version numbers — **P1**
| Location | Version |
|---|---|
| `pyproject.toml`, `install.sh`, README badge | 2.0.0 |
| `src/cli/main.py __version__` | 1.1.0 |
| CHANGELOG latest entry | **1.3.0, dated 2026-04-11 — a month *after* 2.0.0 (2026-03-17)** |
| `operations/scripts/shared.py __version__` | 3.1.0 |
| skills-registry.json | "2.0" |

The CHANGELOG ordering (1.3.0 released after 2.0.0) suggests version numbers are decorative. For a tool whose pitch is *auditability*, this is reputationally corrosive.

**Fix:** Single source of truth (`pyproject.toml` version, exposed via `importlib.metadata`; install.sh reads it at release time via CI templating). Renumber the CHANGELOG (that 1.3.0 entry is really 2.1.0). Add a CI check that README badge == pyproject == install.sh.

#### F-5. `install.sh --force` failure path can delete the user's pre-existing `.claude/` — **P1**
```bash
trap '_cleanup_on_failure' ERR   # → rm -rf "$DEST"
```
If a user reinstalls over an existing `.claude/` and any later step fails (e.g., missing python3 for hook config), the trap **removes the entire `.claude/` directory including their customized CLAUDE.project.md, CONSTITUTION.md, custom skills**. Data loss by design.

**Fix:** Install into `.claude.staging.$$/`, atomically swap on success, and on failure remove only the staging dir. Back up an existing `.claude/` to `.claude.bak-<ts>/` before swap.

#### F-6. Installer never installs `.claude/settings.json` → hooks are dead on arrival — **P0**
`install.sh` copies agents, commands, skills, hooks (`*.sh`), modes, operations, local templates — but **never `settings.json`**, which is the only mechanism (per the repo's own deprecation note in `hooks/config.json`) that registers hooks with Claude Code. Result: a `--full` install ships 17 hook scripts that are never invoked. `claudekit doctor` even encodes this failure as a mere warning ("No Claude Code hooks configured"). The flagship safety features — ops-enforcement, config-protection, secret scanning on commit — are inert in every fresh installation.

**Fix:** Ship a rendered `settings.json` (merged non-destructively if one exists — Claude Code supports `settings.local.json`; consider installing there). Add an install-time smoke test: run `claudekit doctor` post-install in CI against a temp project and require zero warnings on the hook checks.

---

### 2.2 Module Boundaries & Dependency Graph

#### F-7. `src/security/` is dead code — **P1**
`CommandValidator` and `PathGuard` are imported by exactly two things: their own tests and a mention in `docs/ARCHITECTURE.md`. No hook calls them, the operations scripts reimplement their own (different) path/null-byte/protection checks, the CLI never touches them, and they are not copied into target projects. So the "Security Layer" in the architecture diagram is fiction: two well-written classes with no call sites, while the *actual* enforcement lives in duplicated ad-hoc bash (`file-guard.sh`, `pre-commit.sh` grep patterns) and in `execute-json-ops.py`'s inline checks. Three parallel security implementations, none shared.

**Fix:** Either (a) make the operations scripts import these modules (requires packaging them together — supports the F-3 restructure), or (b) delete them. Do not keep a "security layer" whose only consumer is its test file.

#### F-8. Operations scripts are vendored into target projects with their own identity — **P2**
`shared.py` says *"Shared constants and utilities for **CodeManifest** scripts"* (a previous project name), versions itself independently (3.1.0), and the executor's lock file is `.codemanifest.lock` — while `install.sh` gitignores `.claude-core.lock`, a lock file **nothing creates**. The gitignore also adds `operations/**/state.json` although plans/ops now live in `.claude/plans/`. These are fossilized layers from three naming eras (CodeManifest → claude-core → ClaudeKit).

**Fix:** One rename pass: lock file `.claude/.claudekit.lock`, correct gitignore entries, delete the CodeManifest references, align script version with the release version.

#### F-9. The dependency graph is implicit and cyclic-ish through the filesystem — **P2**
Actual edges: settings.json → hooks/*.sh → config.json (`project.*` commands) + operations scripts; commands → agents (`claude -p --agent`) → skills (prose lists) → registry (parallel truth); install.sh → hardcoded knowledge of *all* of the above; CLI → install.sh + operations scripts. Nothing declares these edges; they are string references in prose and bash. Evidence of what this causes: `.claude/settings.json` references `ops-enforcement.sh`, which is **untracked in git** — a fresh clone has hooks wired to a script that does not exist. Similarly, `.claude/operations/scripts/.claude/hooks/hooks.log` exists on disk — a hook ran with the wrong CWD and recreated the log path *inside the scripts directory*, precisely because paths are resolved by convention, not contract.

**Fix:** See F-17 (manifest). Also: commit or remove `ops-enforcement.sh`; make every hook resolve `ROOT` once and refuse to run if `$ROOT/.claude` is absent; add a CI check that every path mentioned in settings.json exists in the tree.

#### F-10. Commands spawning nested `claude -p ... --dangerously-skip-permissions` — **P1**
`/plan` (and siblings) instruct the model to Bash-spawn a *second* Claude Code process with permissions disabled, claiming "Verified mechanism: `--agent <name>` loads `.claude/agents/<name>.md`". This is (a) an undocumented/unstable CLI coupling that will break silently across Claude Code releases, (b) a permission-model bypass baked into the safety product, (c) doubled token cost and lost context vs. the native Task/subagent mechanism that Claude Code provides for exactly this purpose.

**Fix:** Use the native subagent invocation (agents in `.claude/agents/` are already discoverable by the Task tool). Reserve headless `claude -p` for the autonomous-loop commands where a detached process is genuinely required — and never with `--dangerously-skip-permissions` by default; make it an explicit opt-in flag of `/loop-start`.

---

### 2.3 Duplication & Source-of-Truth Failures

#### F-11. `.claude/skills/` vs `templates/skills/`: 13 duplicated skills, 2 already diverged — **P1**
`autonomous-loop, codebase-mapping, command-flags, context-priming, hook-profiling, incident-response, mcp-integration, prompt-injection-defense, safe-command-approval, session-continuity, spec-driven-development, token-optimization, usage-monitoring` exist in both trees; `incident-response` and `spec-driven-development` have **different content**. install.sh copies both trees into the same destination, so which version a user gets depends on copy order. This is the textbook copy-paste divergence failure, one release old.

**Fix:** Delete `templates/skills/` entirely; `.claude/skills/` is canonical. Same for `templates/commands/` and `templates/hooks/` and `templates/modes/` — merge them into `.claude/` (they're not language-specific, so "templates" is the wrong home; see F-16). If some assets are meant to be optional, express that in the manifest (component: `optional`), not by directory placement.

#### F-12. `autonomous-loop` vs `autonomous-loops` — **P2**
Two skills covering the same concept (Ralph-pattern iterative loops vs convergence-loop guidance), both loaded by different agents/commands. Skill discovery is description-matching; near-duplicate names sabotage it.

**Fix:** Merge into one `autonomous-loop` skill with two sections; update coordinator/loop-start references and the registry.

#### F-13. Registry vs prose skill lists: two parallel truths — **P2**
`skills-registry.json` maps agents→skills, and each agent .md contains a hand-written "Mandatory Skill Loading" list. Nothing keeps them synchronized (the registry's `agentMapping` even contains keys `opensource` and `loop-start`, which are *commands*, not agents — the taxonomy has already drifted). CI validates registry-internal integrity only.

**Fix:** Make the registry authoritative: generate the "Mandatory Skill Loading" section of each agent file from `agentMapping` (a 30-line build script + CI diff check), and validate that every `agentMapping` key corresponds to an actual `agents/*.md`.

#### F-14. Documentation counts are wrong everywhere — **P2**
README/ARCHITECTURE/AGENTS.md say 13 agents, 17 commands, ~44/45 skills. Reality: 28 agents, 39 commands, 73 skills. `install.sh` hardcodes a *prose list* of agents and commands in its success banner (already listing agents that don't exist, e.g. the CHANGELOG's `dead-code-hunter` and `open-source-forker` never landed in `.claude/agents/`). CI asserts floors of "≥13 agents, ≥17 commands" — a check that can never catch a regression from 28 to 14.

**Fix:** Counts must be computed, never written: install.sh prints `$(ls | wc -l)` (it already computes AGENT_COUNT — then ignores it in the banner); docs tables generated from the registry/frontmatter by a `make docs` step; CI pins exact counts via a generated manifest and fails on unexplained drift.

---

### 2.4 Configuration System

#### F-15. `config.schema.json` validates a deprecated file, and nothing runs the validation — **P1**
The repo-root schema describes `.claude/hooks/config.json` — a file whose own header says *"DEPRECATED: superseded by .claude/settings.json"*. Grep shows exactly one consumer of the schema: a passing mention inside the `multi-agent-coordination` skill. Neither the CLI (`cmd_config`, `doctor`), nor install.sh, nor any hook, nor CI ever validates config.json against it. Meanwhile the *deprecated* file is still load-bearing: install.sh writes `project.build_cmd/...` into it and every hook reads commands from it. So: the schema is dead, the deprecated file is alive, and the live file (settings.json) has no schema.

**Fix:** Split the concerns. (1) `project` commands → a new, small, *non-deprecated* `.claude/claudekit.json` (or reuse CLAUDE.md-adjacent config) with a schema that `doctor` and CI actually validate (`jsonschema` is already a test dep). (2) Delete the hook-definition half of config.json and its schema. (3) Ship a schema for the parts of settings.json ClaudeKit generates.

---

### 2.5 Folder Organization & Repo Hygiene

#### F-16. `templates/` conflates two unrelated ideas — **P2**
`templates/<language>/` (per-language config.env + CLAUDE.md — genuine templates, rendered/parameterized) sits next to `templates/{commands,skills,hooks,modes,mcp}` (verbatim assets, copied as-is, duplicating `.claude/`). The directory name communicates nothing about which is which, and the installer needs special-case branches for each subtree.

**Fix:** `templates/` keeps only languages (rename to `languages/` for honesty). Everything copied verbatim lives under `.claude/` (canonical asset tree). Optional bundles (mcp, i18n, security-hooks) are manifest-flagged groups, not directories in a different tree.

#### F-17. No manifest/registry drives installation — the central missing abstraction — **P1**
install.sh is 470 lines of imperative copy logic with hardcoded component knowledge, hardcoded counts, hardcoded skill-merge order, and special cases per directory. Adding a component type (modes, mcp, i18n each got their own bespoke block) grows the script linearly and is the direct cause of F-6 (settings.json forgotten), F-11 (double-copy), and F-14 (stale banners). The CLI's `doctor` then re-hardcodes the same expectations (≥9 agents, ≥27 skills…) independently.

**Fix:** A single `claudekit.manifest.json` at repo root:

```json
{
  "version": "2.1.0",
  "components": {
    "agents":    {"src": ".claude/agents",    "profile": ["minimal","full"]},
    "commands":  {"src": ".claude/commands",  "profile": ["minimal","full"]},
    "operations":{"src": ".claude/operations","profile": ["minimal","full"]},
    "skills":    {"src": ".claude/skills",    "profile": ["full"]},
    "hooks":     {"src": ".claude/hooks",     "profile": ["full"], "post": "chmod+x"},
    "settings":  {"src": ".claude/settings.json", "profile": ["full"], "merge": "settings-local"},
    "modes":     {"src": ".claude/modes",     "profile": ["full"]},
    "mcp":       {"src": ".claude/mcp",       "profile": ["opt:mcp"]},
    "i18n":      {"src": "i18n",              "profile": ["opt:i18n"]}
  }
}
```

Installer (Python and/or bash) iterates the manifest; `doctor` verifies against the same manifest; CI counts against the same manifest; docs tables generate from it. One truth, four consumers.

#### F-18. Dogfooding debris pollutes the working tree — **P3**
`.claude/plans/` holds 20+ generated `plan-2026…md` artifacts (one tracked in git), `.claude/hooks/{hooks.log,cost-tracker.log,compact-counter.txt}` sit on disk, and the stray `.claude/operations/scripts/.claude/hooks/` nesting (F-9) persists. `.gitignore` covers `*.log` but not plans, counters, or session files.

**Fix:** gitignore `.claude/plans/`, `.claude/session-*.{md,json}`, `.claude/hooks/*.txt`; delete the stray nested dir; move the one intentional plan (`blueprint-professional-upgrade.md`) to `docs/` if it's meant to be kept.

---

### 2.6 Skills / Agents / Commands Boundary

#### F-19. The three-way taxonomy is conceptually clean but operationally blurry — **P2**
Intended model: **agents** = who (persona + permissions + model), **skills** = how (loadable knowledge), **commands** = entry points (user intent → agent). In practice: commands duplicate agent content (implement.md restates the implementer's pre-flight checklist); skills duplicate command logic (hookify skill vs /hookify command describe the same 5-phase protocol twice); several "skills" are really workflows-with-side-effects (`gan-harness` declares `allowed-tools: Agent, Write, Bash` — that's an agent in a skill costume); and the registry maps commands as agents (F-13). Each duplication is a future divergence (the incident-response divergence in F-11 shows the failure mode is real, not theoretical).

**Fix:** Adopt a rule and enforce it in review: commands are ≤40 lines — parse args, name the agent, name the skills, define the artifact contract, nothing else. Any procedural content lives in exactly one skill. Skills that need tools/spawning become agents. Add a lint (`tests/test_structure.py` extension) that flags commands over a line budget and skills with `allowed-tools: Agent`.

#### F-20. Prompt-count inflation: 73 skills / 28 agents is past the point of diminishing returns — **P2** (overengineering)
Skill discovery is the model matching descriptions; with 73 skills, several near-synonymous (autonomous-loop/-loops, context-keeper/session-continuity, token-optimization/token-budget-advisor/context-budget, verification-loop/verification-before-completion), selection accuracy degrades and mandatory-load lists balloon (coordinator loads 12 skills before any work — that's tens of KB of preamble per invocation, in direct tension with the "85% token reduction" pitch). Similarly, three review agents (reviewer, code-reviewer, typescript-/python-reviewer) plus santa plus gan-harness overlap heavily.

**Fix:** Curate ruthlessly toward ~45 skills / ~18 agents: merge the token/context trio, the verification pair, the session pair, fold language reviewers into code-reviewer parameterization. Track a "corpus budget" the way you track token budgets. Underengineering note (the mirror image): what's *missing* while duplicates abound is any eval harness proving these prompts work — `eval-harness` exists as a skill (prompt), but there is no repo-level regression suite running any agent against fixtures.

---

### 2.7 Extension & Update Model

#### F-21. No update path; `--force` reinstall destroys customization — **P1**
docs/CUSTOMIZATION.md: *"This overwrites the `.claude/` directory. Your customizations… will be regenerated from templates, so back them up first."* For a framework that encourages editing agents, thresholds, skills, and constitution in place, having *no upgrade story* means every installation forks permanently at install time. Combined with F-5, an upgrade attempt can actively destroy data.

**Fix:** (1) Separate ClaudeKit-owned files from user-owned files on disk: `.claude/claudekit/` (managed, overwritable) vs `.claude/local/` + `.claude/skills-local/` (user, never touched). (2) `claudekit update` command: staged copy, checksum comparison against the shipped manifest, three-way handling (unchanged→replace, user-modified→keep + `.new` file, removed→prompt). (3) Record installed version + file hashes in `.claude/.claudekit-manifest.json` at install time so update/doctor can diff.

#### F-22. Extension model is "edit the framework's files" — **P2**
Adding a language = new `templates/<lang>/config.env` + editing `detect_language()` in install.sh + editing the README table (three places). Adding an agent = file + command + registry edit + agent prose lists. Adding a hook = script + settings.json surgery. There is no `claudekit add-skill/add-agent` scaffolding, no local-override directory, no plugin namespace — even though Claude Code itself now has a plugin/marketplace format that this project could target.

**Fix:** Language detection driven by a `detect` key in each language's config (e.g. `DETECT_FILES="go.mod"`), so adding a language is one directory. `claudekit new skill|agent|command <name>` scaffolder. Longer term: package ClaudeKit as a Claude Code plugin (its agents/commands/skills map 1:1 onto the plugin format), which outsources the entire install/update problem.

---

### 2.8 Cross-Platform & CI

#### F-23. CI gates are decorative in places — **P2**
`cli-tests` and `security` pytest steps run with `|| true` (cannot fail); the structure job asserts stale floors (≥13/≥17); no job builds the pip package (would have caught F-1 for a year); no job runs install.sh end-to-end against a fixture project and then `claudekit doctor` (would have caught F-6). Shellcheck coverage is good but only for `.claude/hooks/`, not `templates/hooks/`.

**Fix:** Remove `|| true`; add `pip install . + smoke` job; add `install.sh → doctor --strict` integration job (fixture projects per language, at least python + typescript); shellcheck all `*.sh` recursively; pin counts from the manifest.

#### F-24. Hard Bash/Unix dependency contradicts the "any language" positioning — **P3**
Windows requires WSL; hooks additionally assume `git rev-parse` succeeds (non-git projects get silently broken hooks — `ROOT` empty → sources `/​.claude/hooks/...`). Acceptable short-term, but the settings.json hook commands should at minimum guard `[ -n "$ROOT" ] || exit 0`.

---

## 3. Severity Summary

| # | Finding | Severity |
|---|---|---|
| F-1 | pip build backend invalid — package cannot install | **P0** |
| F-6 | settings.json never installed — all hooks inert in fresh installs | **P0** |
| F-2 | top-level `src` package name | **P0** (upon F-1 fix) |
| F-3 | wheel ships no assets; pip path parasitic on git clone | P1 |
| F-4 | four conflicting version numbers; CHANGELOG out of order | P1 |
| F-5 | ERR trap `rm -rf .claude` can destroy user data | P1 |
| F-7 | `src/security` dead code; 3 parallel security impls | P1 |
| F-10 | nested `claude -p --dangerously-skip-permissions` invocation | P1 |
| F-11 | 13 duplicated skills across trees, 2 diverged | P1 |
| F-15 | schema validates deprecated config; nothing runs it | P1 |
| F-17 | no manifest driving install/doctor/CI/docs | P1 |
| F-21 | no update path; reinstall destroys customization | P1 |
| F-8, F-9, F-12, F-13, F-14, F-16, F-19, F-20, F-22, F-23 | naming fossils, implicit deps, near-dup skills, parallel truths, stale docs/counts, templates conflation, blurry taxonomy, corpus inflation, no scaffolding, decorative CI | P2 |
| F-18, F-24 | repo debris; bash/git assumptions | P3 |

---

## 4. Recommended Architecture

### 4.1 Target structure

```
claudekit/
├── pyproject.toml                    # hatchling; version = single source of truth
├── claudekit.manifest.json           # components, profiles, counts — drives EVERYTHING
├── install.sh                        # thin bootstrap: pipx install claudekit || pure-bash fallback
├── src/claudekit/                    # proper package (fixes F-1/2/3)
│   ├── cli/                          # init, doctor, update, validate, execute, rollback,
│   │   │                             #   new (scaffolder), agents, config
│   ├── installer/                    # manifest-driven install/update engine (replaces bash logic)
│   ├── ops/                          # validate/execute/restore/shared — importable AND vendored
│   ├── security/                     # CommandValidator/PathGuard, actually imported by ops+hooks
│   └── assets/                       # ← canonical .claude tree, packaged into the wheel
│       ├── agents/  commands/  skills/  modes/  hooks/  mcp/
│       ├── settings.json
│       └── local/ (CLAUDE.template.md, CONSTITUTION.template.md)
├── languages/                        # ex-templates/<lang>: config.env + CLAUDE.md + detect rules
├── examples/  docs/  i18n/  tests/  .github/
```

Installed layout in a target project:

```
.claude/
├── claudekit/            # managed: agents, commands, skills, hooks, ops, modes (+ hash manifest)
├── local/                # user-owned: CLAUDE.project.md, CONSTITUTION.md, custom skills/agents
├── settings.json         # merged, never clobbered
└── plans/  (gitignored)  # runtime artifacts
```

### 4.2 Rules that keep it healthy

1. **Manifest is law.** install, update, doctor, CI counts, and docs tables all read `claudekit.manifest.json`. A component not in the manifest does not ship.
2. **One copy of every asset.** `.claude` canonical tree only; optionality is a manifest flag, not a second directory.
3. **Generated, never hand-written:** doc counts, agent skill lists (from registry), install banners.
4. **Managed vs user split on disk** enables `claudekit update` (three-way, checksum-based) and makes `--force` safe.
5. **Commands are thin** (≤40 lines, no procedure); procedures live in exactly one skill; anything needing tools is an agent.
6. **CI proves the product:** build wheel → install → `init` fixture project → `doctor --strict` → run one ops.json round-trip (validate→execute→rollback) → exact-count checks.

### 4.3 Migration sketch (4 increments, each shippable)

| Phase | Work | Outcome |
|---|---|---|
| **1. Stop the bleeding (days)** | Fix build backend (F-1); rename package to `claudekit` (F-2); copy settings.json in install.sh (F-6); staging-dir install with safe trap (F-5); commit `ops-enforcement.sh`; align versions + renumber CHANGELOG (F-4); remove CI `|| true`; delete `.claude/plans` debris + gitignore | Both distribution paths minimally honest; hooks actually fire |
| **2. Single source of truth (1–2 wks)** | Introduce `claudekit.manifest.json`; rewrite install.sh loop + doctor + CI structure job against it; delete `templates/{skills,commands,hooks,modes}` after merging diverged files into `.claude/` (F-11/16); regenerate doc tables (F-14) | Duplication class of bugs becomes structurally impossible |
| **3. Real package (2–3 wks)** | Move assets into `src/claudekit/assets`; `claudekit init` installs from package resources; install.sh becomes bootstrap; ops scripts import `claudekit.security` (F-7); new config file for project commands + schema validated in doctor (F-15); `pip` smoke job in CI | pip is the primary channel; install.sh is a convenience |
| **4. Lifecycle & curation (ongoing)** | `claudekit update` with hash manifest (F-21); `claudekit new` scaffolder + language `detect` keys (F-22); replace nested `claude -p` with native subagents (F-10); merge duplicate skills, prune corpus to budget (F-12/19/20); evaluate shipping as a Claude Code plugin | Upgradable installs; sustainable growth of agents/skills/languages |

### 4.4 What to protect while migrating

The operations engine (validate → execute → restore, atomic writes, lock, manifested backups) is the best-engineered code in the repo — keep its behavior bit-for-bit and wrap it in tests before moving it. The agent/skill prose corpus is the product's moat; migration must be pure relocation + deduplication, with the registry-driven generation preventing regressions in agent↔skill wiring.

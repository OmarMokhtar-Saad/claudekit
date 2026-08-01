# MCP Server Configurations

Pre-configured Model Context Protocol (MCP) server definitions for use with Claude Code. These servers extend Claude's capabilities with documentation lookup, structured reasoning, browser automation, persistent memory, and filesystem access.

## What this grants (read before enabling)

Enabling these servers is a trust decision, not a configuration detail. Every entry below launches `npx`, which **downloads and executes code from the npm registry** on your machine, with your user's permissions, inside your project. Once running, an MCP server is a tool the model can call -- its capabilities become the model's capabilities.

Concretely, `--with-mcp` grants:

| Server | What it can do | Blast radius |
|---|---|---|
| `context7` | Outbound HTTPS to Upstash to fetch documentation | The library names and versions you look up leave your machine |
| `sequential-thinking` | A local reasoning scratchpad; no I/O | Minimal |
| `playwright` | Drives a real browser: navigate, click, submit forms, screenshot | Any site reachable from your machine, using your network position and any logged-in session in that browser profile |
| `memory` | Reads and writes a local JSON store that persists across sessions | Anything written there is replayed into future sessions |
| `filesystem` | Reads files under the path you pass as an argument | Everything under that path -- including `.env` files and credentials, if they are in scope |

Mitigations already applied in this template:

- **Exact version pins.** Every package is pinned to a specific version (`@x.y.z`), never a floating `latest` tag. A compromised *new* release of any of these packages does not reach you until someone deliberately bumps the pin. This does **not** make the fetch safe: pinning fixes *which* remote code runs, not *that* remote code runs, and npm provides no signature verification here.
- **Filesystem read-only by default.** The filesystem server ships without `--allow-write`. Write access is an explicit opt-in (see below).
- **Least scope.** The filesystem server is scoped to `.` (the project directory), never `/` or `$HOME`.

If that trade is not acceptable for your threat model, do not enable the server. Each entry is independent and can be omitted.

## Prerequisites

- **Node.js 18+** (required for all servers via `npx`)
- **npm** (bundled with Node.js)

Verify your setup:

```bash
node --version   # Must be >= 18.0.0
npm --version
```

## Included Servers

### 1. Context7 (`@upstash/context7-mcp`)

Provides live, version-specific documentation lookup for libraries and frameworks. Instead of relying on training data that may be outdated, Context7 fetches current docs on demand.

**Use cases:**
- Looking up API signatures for a specific library version
- Checking migration guides between framework versions
- Verifying current best practices for a dependency

**No additional configuration required.** Runs statelessly via `npx`.

---

### 2. Sequential Thinking (`@modelcontextprotocol/server-sequential-thinking`)

Enables structured, multi-step reasoning through a dedicated thinking tool. Useful for problems that benefit from explicit decomposition before jumping to a solution.

**Use cases:**
- Breaking down complex architectural decisions
- Analyzing tradeoffs between multiple approaches
- Debugging intricate issues step by step
- Working through logic-heavy problems methodically

**No additional configuration required.** Runs statelessly via `npx`.

---

### 3. Playwright (`@playwright/mcp`)

Provides browser automation capabilities through the Playwright testing framework. Claude can navigate web pages, interact with elements, take screenshots, and verify UI behavior.

**Use cases:**
- Testing web application flows end to end
- Capturing screenshots for visual verification
- Scraping structured data from web pages
- Automating repetitive browser tasks during development

**Prerequisites:**
- Playwright browsers may be installed on first use
- Run `npx playwright install` manually if you need browsers pre-installed

---

### 4. Memory (`@modelcontextprotocol/server-memory`)

Provides persistent key-value memory that survives across sessions. Claude can store and retrieve facts, decisions, preferences, and project context.

**Use cases:**
- Remembering project conventions and decisions across sessions
- Storing user preferences (code style, naming conventions)
- Tracking architectural decisions and their rationale
- Maintaining a knowledge base about the codebase

**Storage:** Data is persisted locally in a JSON file managed by the server.

---

### 5. Filesystem (`@modelcontextprotocol/server-filesystem`)

Provides scoped filesystem access. Every path the server may touch is passed as an argument; anything outside those paths is inaccessible to it.

**Use cases:**
- Reading project files through the MCP protocol
- Bulk inspection of file-based configuration
- Answering questions about files the model would otherwise have to open one at a time

**Default in this template -- read-only, scoped to the project directory:**

```json
"args": ["-y", "@modelcontextprotocol/server-filesystem@2026.7.10", "."]
```

**Opt-in to write access (a deliberate change, not the shipped default):**

```json
"args": ["-y", "@modelcontextprotocol/server-filesystem@2026.7.10", "--allow-write", "."]
```

**Security note:** adding `--allow-write` lets the model create, overwrite, and delete files anywhere under the scoped path -- including files it was never asked to touch, and including `.env` files, keys, and shell history if they live in scope. Claude Code's own Edit/Write tools are covered by this kit's hooks and permission prompts; the MCP filesystem server is not. If you do enable writes, scope them to a specific subdirectory (`./src`, `./docs`) rather than `.`.

---

## Installation

### Option A: Copy the full configuration

Copy `mcp-settings.json` to your Claude Code settings location:

```bash
# Project-level (recommended)
cp mcp-settings.json .claude/settings.json

# Or merge into an existing settings file
```

### Option B: Add individual servers

Copy specific server entries from `mcp-settings.json` into your existing `mcpServers` configuration. Each server is independent and can be enabled separately.

## Customization

### Filesystem server scope

By default the filesystem server is read-only and scoped to `.` (the project directory). Narrow the scope by replacing the trailing path argument:

```json
"args": ["-y", "@modelcontextprotocol/server-filesystem@2026.7.10", "./src"]
```

Write access is opt-in; see the security note in the Filesystem section above.

### Updating the pinned versions

Every server is pinned to an exact version. To bump one:

1. Review what changed -- `npm view <package> versions` plus the package's own changelog.
2. Edit the version in `mcp-settings.json` **and** in the table in `templates/commands/mcp.md`.
3. Re-run the test suite. `tests/test_mcp.py` enforces that every package spec is an exact `@x.y.z` and that the filesystem server carries no `--allow-write`.

Never reintroduce a floating `latest` tag: CI fails on any such spec under `templates/mcp/`.

### Disabling a server

Remove or comment out the server entry from your `mcpServers` configuration. Each server runs independently.

## Troubleshooting

| Problem | Solution |
|---|---|
| `npx` command not found | Install Node.js 18+ from https://nodejs.org |
| Server fails to start | Run the `npx` command manually in a terminal to see error output |
| Playwright browsers missing | Run `npx playwright install` to download browser binaries |
| Memory server data lost | Check file permissions in the server's data directory |
| Filesystem server permission denied | Verify the scoped path argument is correct and readable; writing requires the explicit `--allow-write` opt-in |

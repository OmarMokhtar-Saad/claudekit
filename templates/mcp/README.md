# MCP Server Configurations

Pre-configured Model Context Protocol (MCP) server definitions for use with Claude Code. These servers extend Claude's capabilities with documentation lookup, structured reasoning, browser automation, persistent memory, and filesystem access.

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

### 3. Playwright (`@playwright/mcp@latest`)

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

Provides sandboxed filesystem access with explicit read/write permissions. The `--allow-write .` flag grants write access to the current working directory.

**Use cases:**
- Reading and writing project files through the MCP protocol
- Performing bulk file operations
- Managing file-based configuration

**Security note:** The `--allow-write .` argument restricts write access to the current directory. Adjust the path argument to control the scope of filesystem access. Remove `--allow-write` entirely for read-only mode.

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

### Filesystem server path

By default the filesystem server has write access to `.` (current directory). Change this to restrict or expand access:

```json
"args": ["-y", "@modelcontextprotocol/server-filesystem", "--allow-write", "/path/to/allowed/dir"]
```

### Disabling a server

Remove or comment out the server entry from your `mcpServers` configuration. Each server runs independently.

## Troubleshooting

| Problem | Solution |
|---|---|
| `npx` command not found | Install Node.js 18+ from https://nodejs.org |
| Server fails to start | Run the `npx` command manually in a terminal to see error output |
| Playwright browsers missing | Run `npx playwright install` to download browser binaries |
| Memory server data lost | Check file permissions in the server's data directory |
| Filesystem server permission denied | Verify the `--allow-write` path is correct and accessible |

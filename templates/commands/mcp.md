---
description: "Manage MCP server configurations -- list, enable, or disable servers"
argument-hint: "<list|enable|disable> [server-name]"
---

# MCP Server Management

Manage Model Context Protocol server configurations for this project.

## Task

MCP server operation: $ARGUMENTS

## Available Servers

| Server | Package | Purpose |
|---|---|---|
| `context7` | `@upstash/context7-mcp@latest` | Live documentation lookup for libraries and frameworks |
| `sequential-thinking` | `@modelcontextprotocol/server-sequential-thinking` | Structured multi-step reasoning |
| `playwright` | `@playwright/mcp@latest` | Browser automation and testing |
| `memory` | `@modelcontextprotocol/server-memory` | Persistent key-value memory across sessions |
| `filesystem` | `@modelcontextprotocol/server-filesystem` | Sandboxed filesystem read/write access |

## Operations

### List (`/mcp list`)

1. Read the current MCP settings from `.claude/settings.json` (or project config)
2. Display each configured server with its status
3. Show the command and arguments for each server
4. Note any servers from the template that are not yet configured

### Enable (`/mcp enable <server-name>`)

1. Read the server definition from `templates/mcp/mcp-settings.json`
2. Validate the server name exists in the template
3. Add the server entry to `.claude/settings.json` under `mcpServers`
4. Create the settings file if it does not exist
5. Confirm the server was added

### Disable (`/mcp disable <server-name>`)

1. Read the current `.claude/settings.json`
2. Validate the server name exists in the current configuration
3. Remove the server entry from `mcpServers`
4. Confirm the server was removed

## Prerequisites

- **Node.js 18+** is required for all MCP servers (they run via `npx`)
- Verify with: `node --version`

## Safety Rules

- NEVER overwrite user-customized server arguments without confirmation
- NEVER remove servers that were not added by this tool without confirmation
- ALWAYS preserve existing non-MCP settings when modifying the settings file
- ALWAYS validate JSON syntax after modifications

## Output

After each operation, display:
- The current state of all MCP server configurations
- Any warnings (missing Node.js, invalid config, etc.)
- Suggested next steps

## Usage Examples

- `/mcp list` -- Show all configured and available MCP servers
- `/mcp enable context7` -- Add the Context7 documentation server
- `/mcp enable playwright` -- Add browser automation capabilities
- `/mcp disable memory` -- Remove the memory server
- `/mcp enable all` -- Enable all available servers

---
name: mcp-integration
description: "Use when working with MCP servers — provides guidelines for Context7 (docs), Sequential Thinking (reasoning), Playwright (browser), Memory (persistence), Filesystem (file operations)"
disable-model-invocation: true
argument-hint: "<server-name-or-task>"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# MCP Integration

## Core Principle

**Use the right MCP server for the right task.** Each server has a specific purpose. Using the wrong server wastes time and produces poor results. When multiple servers could help, combine them deliberately.

---

## Server Selection Guide

### When to Use Context7

**Purpose:** Fetch live, version-specific documentation for libraries and frameworks.

**Use when:**
- You need to check the API of a specific library version
- The user asks about a library and you are unsure of the current API
- You need migration guides between versions
- You want to verify that a function, method, or option still exists in the latest release

**Do NOT use when:**
- The question is about general programming concepts (use your training data)
- The library is internal or proprietary (Context7 only covers public packages)
- You already have high confidence in the answer from recent training data

**Best practices:**
- Always specify the library version when querying
- Prefer Context7 over guessing when the API has changed between versions
- Cache the key findings mentally for the duration of the conversation

---

### When to Use Sequential Thinking

**Purpose:** Decompose complex problems into explicit, ordered reasoning steps.

**Use when:**
- The problem has multiple interacting constraints
- You need to evaluate tradeoffs between 3+ options
- The user asks you to "think through" or "analyze" a decision
- Debugging requires isolating variables systematically
- Architectural decisions affect multiple parts of the system

**Do NOT use when:**
- The task is straightforward and does not require decomposition
- You are executing a well-defined plan (use the plan directly)
- The answer is a simple fact lookup

**Best practices:**
- Start with a clear problem statement as the first thinking step
- Number your steps and reference previous steps explicitly
- End with a synthesis step that combines the findings into a recommendation
- Use this server before making irreversible decisions

---

### When to Use Playwright

**Purpose:** Automate browser interactions -- navigate, click, type, screenshot, and verify web content.

**Use when:**
- Testing a web application's UI flow end to end
- The user needs a screenshot of a web page or component
- You need to verify that a deployed change looks correct
- Scraping structured data from a web page
- Filling out forms or automating repetitive browser tasks

**Do NOT use when:**
- You only need to make HTTP API calls (use `curl` or `fetch` instead)
- The task involves only reading static HTML files (use the filesystem)
- The target site blocks automated browsers

**Best practices:**
- Always wait for page loads and element visibility before interacting
- Take screenshots at key steps for verification
- Use CSS selectors or accessible roles for element targeting, not fragile XPaths
- Close the browser session when done to free resources
- Handle navigation errors gracefully (timeouts, 404s, redirects)

---

### When to Use Memory

**Purpose:** Store and retrieve persistent key-value data across sessions.

**Use when:**
- The user states a preference that should persist ("I always use tabs", "Our API prefix is /v2")
- An architectural decision is made and should be remembered
- You need to track project-specific conventions discovered during exploration
- Storing the results of a lengthy analysis for future reference

**Do NOT use when:**
- The information is already in project files (CLAUDE.md, config files, etc.)
- The data is temporary and only relevant to the current task
- You are storing large code blocks (use files instead)

**Best practices:**
- Use descriptive, namespaced keys: `project.convention.naming`, `decision.auth.strategy`
- Store concise values -- summaries, not full documents
- Check memory at the start of sessions for relevant context
- Update stale entries rather than creating duplicates
- Delete entries that are no longer relevant

---

### When to Use Filesystem

**Purpose:** Read and write files through the MCP protocol with explicit permission scoping.

**Use when:**
- The MCP filesystem server provides capabilities beyond the built-in file tools
- You need to perform operations that respect the server's permission boundaries
- Working in a context where MCP is the primary file access mechanism

**Do NOT use when:**
- Built-in Read, Write, and Edit tools are available and sufficient (prefer these)
- You need to access files outside the allowed directory scope
- The operation is a simple single-file read or write

**Best practices:**
- Prefer the built-in file tools (Read, Write, Edit) over the MCP filesystem server when both are available
- Respect the `--allow-write` boundary -- do not attempt writes outside the allowed path
- Verify file existence before writing to avoid accidental overwrites

---

## Combining Servers

Some tasks benefit from using multiple MCP servers together:

| Scenario | Servers | Flow |
|---|---|---|
| Evaluate a new library | Context7 + Sequential Thinking | Fetch docs, then reason through fit |
| Debug a UI issue | Playwright + Sequential Thinking | Capture current behavior, then analyze |
| Onboard to a project | Context7 + Memory | Look up stack docs, store conventions |
| Make an architecture decision | Sequential Thinking + Memory | Reason through options, store decision |
| Verify a deployment | Playwright + Memory | Check the UI, record verification result |

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Using Context7 for everything | Wastes time on queries you can answer from training | Only use for version-specific or uncertain APIs |
| Skipping Sequential Thinking on complex decisions | Leads to shallow analysis and missed tradeoffs | Take the time to reason explicitly |
| Using Playwright for API testing | Browser overhead is unnecessary for non-UI tests | Use `curl`, `httpie`, or language-native HTTP clients |
| Storing everything in Memory | Clutters the memory store, makes retrieval noisy | Store only decisions, preferences, and conventions |
| Using Filesystem MCP when built-in tools work | Adds unnecessary indirection | Prefer Read/Write/Edit tools |

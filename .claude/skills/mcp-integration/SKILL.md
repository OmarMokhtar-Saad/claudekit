---
name: mcp-integration
description: "Use when working with MCP servers — how to inventory the servers actually connected, judge whether one beats a built-in tool, and budget their context cost"
disable-model-invocation: true
argument-hint: "<server-name-or-task>"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# MCP Integration

## Core Principle

**Never reason about an MCP server from memory — inventory the ones actually connected,
then decide.** MCP rosters are per-project and per-machine: a server this file names may
be absent here, and a server you need may be connected under a prefix you have not seen.
Every claim about "which servers we have" is a measurement, not a recollection.

---

## Step 1 — Inventory What Is Actually Connected

Do this before recommending, invoking, or ruling out any server.

```bash
# The configured roster, per scope
claude mcp list 2>/dev/null
```

Inside a session: run `/mcp` for connection status, and use `ToolSearch` to find the
tools a server actually exposes — server names are opaque, tool names are not.

```
ToolSearch: "select:mcp__<server>__<tool>,mcp__<server>__<other>"   # load known tools
ToolSearch: "+<server> <capability>"                                # discover by keyword
```

Batch every tool you expect to need into ONE `ToolSearch` call; each separate call is a
wasted round-trip. If a tool does not come back, the server is not connected — say so
and fall back, rather than calling a name that will fail validation.

---

## Step 2 — Decide: Server or Built-In?

An MCP server earns its call only when it beats the built-in tools on a specific axis.
Ask in this order:

| Question | If yes | If no |
|---|---|---|
| Does it reach data the built-ins cannot? (live docs, a SaaS API, a browser) | Candidate | Use built-ins |
| Is the answer time-sensitive or version-specific? | Candidate | Use training data |
| Is the round-trip cheaper than doing it locally? | Candidate | Use built-ins |
| Are its tool schemas already loaded, or cheap to load? | Call it | Weigh the load cost |

**The default is built-ins.** `Read`/`Write`/`Edit`/`Grep`/`Bash` are already loaded,
already permitted, and cost nothing to discover. A server that duplicates them adds
indirection, latency, and schema tokens for the same result.

---

## Step 3 — Budget the Context Cost

Deferred tool schemas are not free: each one you load stays in context for the rest of
the session. Load what the task needs, not what the server offers.

- Load in one batched `ToolSearch`, at the moment of use — not speculatively.
- Prefer a server whose tools return *distilled* results over one that returns raw pages;
  a large tool result costs more than the call saved.
- If a server's output is large and you need one fact from it, say what you need in the
  call rather than fetching and filtering afterwards.
- See `context-budget` for measuring the always-on floor these schemas sit on top of.

---

## Documentation Lookups (context7)

context7 is the documentation server this project standardizes on. Per the CLAUDE.md
Token & Model Policy: **the main agent and planner call context7 directly** for library
and API docs. Do not delegate a context7 lookup to `web-researcher` — that agent has no
MCP access, so delegating it spends a web search to answer a question the docs server
would have answered exactly.

Order of resort for an external-information question:

1. `.claude/reports/research/` — a prior distilled answer may already exist.
2. context7 — library, framework, SDK, API, CLI docs. `resolve-library-id`, then
   `query-docs`. Use it even when you think you know the answer; training data lags.
3. `web-researcher` agent — everything context7 does not cover (error messages in the
   wild, tool flags, current events, non-library questions).

Do not use context7 for general programming concepts, internal or proprietary packages,
business-logic debugging, or code review — none of those are in its corpus.

---

## Common Third-Party Servers

Reference only. **Confirm presence with Step 1 before assuming any of these exist here.**

ClaudeKit ships five of these as *installable* options — `context7`,
`sequential-thinking`, `playwright`, `memory`, `filesystem` — pinned in
`templates/mcp/mcp-settings.json`, one guidance section each in
`templates/mcp/README.md`, enabled with `/mcp enable <name>`. **Shipped is not the
same as connected**: that catalogue says what a project *can* install, Step 1 says what
this session actually has. Read the catalogue to decide what to enable; run Step 1
before calling anything.

| Server | Use it for | Prefer instead when |
|---|---|---|
| Browser automation (Playwright, Claude-in-Chrome) | UI flows, screenshots, console/network capture | The task is an HTTP call — use `curl` |
| Issue trackers (Jira, Linear, GitHub) | Reading ticket state, filing issues | The repo already answers it — use `git`/`gh` |
| Filesystem | File access where built-ins are unavailable or scoped out | Built-in `Read`/`Write`/`Edit` work — always prefer these |
| Memory / knowledge stores | Cross-session facts not derivable from the repo | It is in `CLAUDE.md` or a config file — read that |
| Design/canvas (Miro, Figma) | Reading or producing board and design artifacts | Text or a committed diagram would do |

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Instead |
|---|---|---|
| Naming a server without checking it is connected | The call fails, or you rule out a tool that is present | Step 1 first, every time |
| One `ToolSearch` per tool | Each call is a full round-trip | Batch into one `select:` query |
| Delegating context7 to `web-researcher` | That agent has no MCP access — it burns a web search | Call context7 yourself |
| Loading a server's whole tool surface up front | Schemas stay in context all session | Load at the point of use |
| Using an MCP filesystem/exec server where built-ins work | Indirection with no benefit | `Read`/`Write`/`Edit`/`Bash` |
| Asking context7 about business logic | Not in its corpus — you get confident noise | Read the code |

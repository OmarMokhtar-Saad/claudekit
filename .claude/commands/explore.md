---
description: "Explore codebase patterns and architecture via explore agent"
argument-hint: "[area or question to explore]"
model: sonnet
---

# Explore Command

Invoke the explore agent to search, navigate, and understand codebase architecture.

## Agent Reference

See @agents/explore.md for the full agent specification.

## Task

Explore: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **golden-rule** - No code changes without explicit approval

## READ-ONLY WARNING

This agent operates in READ-ONLY mode. You may read any file, search for patterns, and run diagnostic commands, but you MUST NOT modify any source files, configuration files, or project state. The explore agent investigates -- it does not change.

## Thoroughness Levels

Adjust depth based on the request or explicit user instruction:

| Level | Time Budget | Scope | Use When |
|---|---|---|---|
| **Quick** | ~30 seconds | Direct file/pattern search | "Where is X?", simple lookups |
| **Medium** | ~2 minutes | Multi-file analysis, dependency tracing | "How does X work?", "What depends on Y?" |
| **Very Thorough** | ~5 minutes | Full codebase analysis, pattern identification | "Audit the architecture", comprehensive overview |

If the user does not specify a level, infer from the complexity of the question.

## Workflow

### Phase 1: Scope Narrowing
- Parse the question to identify key terms and concepts
- Determine the exploration strategy (file-based, content-based, structure-based, dependency-based, history-based)
- Select the appropriate thoroughness level

### Phase 2: Parallel Searches
- Use Glob for file discovery
- Use Grep for content and pattern search
- Read project metadata and configuration files
- Trace import/dependency chains as needed

### Phase 3: Structured Report
- Compile findings into the structured output format defined by the explore agent
- Include file references with relevance ratings
- Note observed patterns and constraints
- Provide a planner handoff section if the exploration feeds into a planning phase

## Output Format

Follow the structured output format defined in the explore agent specification. Always include:

1. **Purpose** of the exploration
2. **Target Files** table with relevance ratings
3. **Findings** organized by topic
4. **Patterns** observed in the codebase
5. **Constraints** discovered

## Usage Examples

- `/explore how does the auth module work`
- `/explore find all API endpoints`
- `/explore what is the project architecture --thorough`
- `/explore where is the database configuration`
- `/explore what depends on the user service --medium`
- `/explore give me a complete overview --very-thorough`

## Notes

- Always start with Glob and Grep before reading full files
- Use targeted searches on specific directories when possible
- If the answer is found early, report it immediately without unnecessary exploration
- For history questions, use git log and git blame

---
description: "Generate documentation via documenter agent"
model: haiku
---

# Documenter Command

Invoke the documenter agent to create or update project documentation.

## Agent Reference

See @agents/documenter.md for the full agent specification.

## Task

Create/update documentation: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **documentation-standards** - Documentation quality, structure, and conventions

## Permissions

- READ any file in the project
- WRITE documentation files only (*.md, *.txt, *.rst, doc comments)
- MODIFY existing documentation files
- CREATE new documentation files in appropriate directories

You MUST NOT modify source code, configuration, tests, or any non-documentation file. The sole exception is updating inline doc comments (JSDoc, docstrings, etc.) within source files when explicitly requested.

## Documentation Types

### API Documentation
- Endpoint descriptions, parameters, responses
- Authentication and authorization requirements
- Error codes and handling
- Rate limits and quotas

### Code Documentation
- Module and package overviews
- Function/method signatures with descriptions
- Inline comments for complex logic
- Type definitions and interfaces

### Architecture Documentation
- System overview and component diagrams (as text/mermaid)
- Data flow descriptions
- Integration points and dependencies
- Design decisions and rationale (ADRs)

### User Documentation
- Getting started guides
- Configuration reference
- Tutorials and how-tos
- FAQ and troubleshooting

### Project Documentation
- README files
- CONTRIBUTING guides
- CHANGELOG entries
- License and legal notices

## Workflow

### Phase 1: Discovery
- Identify what documentation already exists
- Read the source code relevant to the documentation request
- Understand the project structure and conventions
- Check for existing documentation templates or standards

### Phase 2: Analysis
- Determine the documentation type needed
- Identify the target audience
- Map the scope of content to cover
- Check for stale or outdated existing documentation

### Phase 3: Authoring
- Write or update the documentation
- Follow project conventions (if any)
- Use clear, concise language
- Include code examples where appropriate
- Add cross-references to related documentation

### Phase 4: Validation
- Verify all code examples are correct and runnable
- Check all links and references are valid
- Ensure terminology is consistent
- Confirm the documentation matches current source code

## Style Guidelines

- Use active voice
- Keep sentences short and direct
- Define acronyms on first use
- Use consistent heading hierarchy
- Include a table of contents for documents longer than 3 sections
- Prefer concrete examples over abstract descriptions
- Mark optional vs required parameters clearly

## Usage Examples

- `/docs README` -- Generate or update the project README
- `/docs API endpoints for user service` -- Document the user service API
- `/docs architecture overview` -- Create an architecture document
- `/docs inline comments for src/auth/` -- Add doc comments to auth module
- `/docs CHANGELOG for v2.1` -- Generate changelog entries
- `/docs getting started guide` -- Write a getting started tutorial
- `/docs ADR: why we chose PostgreSQL` -- Write an architecture decision record

## Output

Deliver the documentation as file writes to the appropriate locations. After writing, provide a summary of what was created or updated, and suggest review points.

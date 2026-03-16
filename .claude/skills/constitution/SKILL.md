---
name: constitution
description: "Use when setting up project governance - creates and manages CONSTITUTION.md with immutable principles"
disable-model-invocation: true
argument-hint: "[project-name]"
---

# Constitution

## Core Principle

**A project constitution defines the immutable principles that govern all decisions.** Unlike skills (which define processes), the constitution defines values and non-negotiable rules that shape every aspect of the project.

---

## When to Use

### Create a Constitution When:

- Setting up a new project from scratch
- Establishing governance for a team
- Defining boundaries that must never be crossed
- Creating a shared set of non-negotiable principles

### Do NOT Create a Constitution When:

- The project already has one (amend instead)
- You just need a process document (use a skill instead)
- The principles are still being debated (resolve first)

---

## The Process

### Step 1: Gather Information

Before writing a constitution, understand:

1. **Project purpose** - What does this project exist to do?
2. **Stakeholders** - Who is affected by decisions?
3. **Values** - What matters most to the team?
4. **Risks** - What failures must be prevented at all costs?
5. **Boundaries** - What is absolutely off-limits?

Questions to ask:
```
- What would cause you to reject a contribution, no matter how good the code?
- What rules should never be broken, even under time pressure?
- What values should guide every decision when the right answer is unclear?
- What happened in the past that should never happen again?
```

### Step 2: Generate the Constitution

Structure the constitution as a set of articles:

```markdown
# Project Constitution

## Preamble
[Why this constitution exists, one paragraph]

## Article 1: [Principle Name]
[Statement of the principle]
### Rationale
[Why this principle exists]
### Implications
[What this means in practice]

## Article 2: [Principle Name]
...

## Amendment Process
[How this constitution can be changed]
```

### Step 3: Integrate

1. Place `CONSTITUTION.md` in the project root
2. Reference it from CLAUDE.md or equivalent project config
3. Ensure all agents load it at startup
4. Add it to onboarding documentation

### Step 4: Verify Integration

- Confirm the constitution is loaded by agent sessions
- Test a scenario where a principle would be violated
- Verify the agent respects the constitution

---

## Article Structure

Each article should contain:

### Statement

One clear, unambiguous sentence stating the principle.

```
"All code changes require explicit approval before implementation."
"No secrets shall be stored in version control."
"Tests must pass before any merge to the main branch."
```

### Rationale

Why this principle is non-negotiable. Reference specific failures or risks.

```
"This principle exists because [event] happened, which caused [consequence].
Without this rule, we risk [negative outcome]."
```

### Implications

What this principle means for day-to-day work:

```
"This means:
- Agents must present plans before editing code
- Automated changes must be reviewed before commit
- Emergency fixes still require verbal approval"
```

### Exceptions (if any)

If there are legitimate exceptions, enumerate them explicitly:

```
"Exceptions:
- Read-only operations (grep, search, read) do not require approval
- Automated formatting during pre-commit hooks is pre-approved"
```

---

## Example Articles

### Example: Code Modification Governance

```markdown
## Article 1: The Golden Rule

All code modifications require explicit user approval before implementation.

### Rationale
Unauthorized code changes, even well-intentioned ones, can introduce bugs,
break existing functionality, or conflict with ongoing work by other developers.

### Implications
- Every edit must be preceded by a plan presented to the user
- The user must explicitly approve before any Write or Edit operation
- This applies to all agents, including subagents
- Read-only operations are exempt

### Exceptions
- Subagents executing pre-approved plan tasks
- Automated formatting by pre-commit hooks
```

### Example: Security Baseline

```markdown
## Article 2: Security First

No code shall be merged that introduces known security vulnerabilities.

### Rationale
Security vulnerabilities put users and data at risk. The cost of
preventing a vulnerability is always less than the cost of a breach.

### Implications
- All changes undergo security review (see security-checklist skill)
- Dependencies with known CVEs must not be added
- Secrets must never appear in source code or logs
- Input from external sources must always be validated

### Exceptions
- None. There are no circumstances where a known vulnerability is acceptable.
```

---

## Amendment Process

The constitution should define how it can be changed:

### Standard Amendment

```
1. Propose the amendment with rationale
2. Review period (minimum: documented discussion)
3. All stakeholders must approve
4. Document the change with date and reason
5. Update CONSTITUTION.md
```

### Emergency Amendment

```
1. Document the urgent need
2. Get approval from project owner
3. Apply the amendment
4. Conduct full review within 48 hours
5. Revert if review does not confirm the change
```

### What Cannot Be Amended

Some principles may be truly immutable:
- Security fundamentals
- Data protection commitments
- Ethical boundaries

Mark these clearly:

```markdown
## Immutable Articles
The following articles cannot be amended or removed:
- Article 2: Security First
- Article 5: User Data Protection
```

---

## Constitution vs Skills vs Documentation

| Aspect | Constitution | Skills | Documentation |
|---|---|---|---|
| **Purpose** | Define values and boundaries | Define processes | Record knowledge |
| **Mutability** | Immutable (mostly) | Evolves with practice | Updated frequently |
| **Scope** | Project-wide | Task-specific | Topic-specific |
| **Authority** | Overrides everything | Guides behavior | Informs decisions |
| **Audience** | Everyone | Agents and developers | Developers and users |

---

## Verification

After creating or amending the constitution:

- [ ] All articles have Statement, Rationale, and Implications
- [ ] The amendment process is defined
- [ ] The constitution is referenced in project config
- [ ] All active agents can access the constitution
- [ ] No articles contradict each other
- [ ] Immutable articles are clearly marked
- [ ] The preamble explains the constitution's purpose

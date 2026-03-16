---
name: writing-skills
description: "Use when creating new skills - TDD approach to process documentation"
disable-model-invocation: true
argument-hint: "<skill-name>"
---

# Writing Skills

## Core Principle

**No skill without a failing test.** Just as TDD ensures code correctness, skills should only be created when there is evidence of a process gap that caused a real problem.

---

## The Iron Law

**Do not create a skill unless you can point to a specific failure that would have been prevented by the skill.**

This prevents:
- Speculative skills that no one uses
- Over-documentation that dilutes important skills
- Skills that duplicate existing knowledge

---

## TDD Mapping for Skills

| TDD Concept | Skill Equivalent |
|---|---|
| Failing test | A real failure caused by missing process |
| Write the test | Document the failure scenario |
| Make it pass | Write the skill that prevents the failure |
| Refactor | Improve the skill based on usage |
| Test regression | The failure does not recur |

---

## When to Create a New Skill

### Create a Skill When:

1. **Pattern recurrence**: The same mistake happened twice or more
2. **Non-obvious process**: The correct approach is not intuitive
3. **Critical path**: Getting it wrong has significant consequences
4. **Onboarding need**: New team members/agents need this knowledge
5. **Complex coordination**: Multiple steps must happen in a specific order

### Do NOT Create a Skill When:

1. **One-off situation**: It happened once and is unlikely to recur
2. **Common knowledge**: Any competent agent would do this naturally
3. **Existing skill covers it**: Extend the existing skill instead
4. **Better as code**: If it can be automated, automate it instead of documenting it
5. **Volatile process**: If the process is still changing rapidly, wait until it stabilizes

---

## Skill Structure

Every skill file follows this structure:

```markdown
---
name: skill-name
description: "Use when [trigger condition] - [what it ensures]"
---

# Skill Title

## Core Principle
[One sentence that captures the essential rule]

## The Process / The Rule
[Main content - steps, rules, tables]

## When to Apply
[Conditions that trigger this skill]

## Red Flags / Anti-Patterns
[Common mistakes to avoid]

## Examples
[Concrete examples of correct usage]
```

---

## YAML Frontmatter Rules

### Required Fields

| Field | Format | Purpose |
|---|---|---|
| `name` | lowercase-kebab-case | Unique identifier for the skill |
| `description` | "Use when..." string | Helps agents decide when to load the skill |

### Description Format

The description MUST start with "Use when" to enable automatic skill matching:

```yaml
# Good
description: "Use when diagnosing bugs - 4-phase root cause investigation methodology"
description: "Use when about to modify code - ensures no edits without explicit approval"

# Bad
description: "A guide to debugging"           # Does not start with "Use when"
description: "Use when you want to debug"      # Too vague
description: "Debugging methodology"           # Not a trigger condition
```

### CSO (Cognitive Skill Optimization)

Descriptions should be optimized for agent skill-matching:

1. **Trigger word**: Start with "Use when" + specific trigger
2. **Context**: Include the situation type (debugging, modifying, reviewing)
3. **Outcome**: State what the skill ensures or provides
4. **Keep under 120 characters** for readability in skill listings

---

## Skill Content Guidelines

### Length

- **Minimum**: 30 lines (anything shorter is probably too thin to be useful)
- **Maximum**: 150 lines (anything longer should be split into multiple skills)
- **Sweet spot**: 60-100 lines

### Tone

- Imperative and direct
- Use MUST/SHOULD/MAY per RFC 2119 conventions
- Avoid hedging language ("perhaps", "maybe", "you might want to")
- Be specific, not generic

### Tables vs Prose

- Use **tables** for: comparisons, checklists, decision matrices, quick reference
- Use **prose** for: explanations of why, context-setting, process narratives
- Use **code blocks** for: examples, templates, command sequences

### Red Flags and Anti-Patterns

Every skill SHOULD include a section on what goes wrong:
- Common rationalizations for skipping the process
- Mistakes that look right but are wrong
- Patterns that indicate the skill is not being followed

---

## Skill Lifecycle

### 1. Identify the Gap

```
Failure occurred: [description]
Root cause: Missing process for [situation]
Existing skills checked: [none cover this / partial coverage in X]
Decision: Create new skill
```

### 2. Draft the Skill

- Follow the structure template above
- Include the triggering failure as a motivating example
- Have another agent/person review the draft

### 3. Integrate the Skill

- Place in `.claude/skills/<skill-name>/SKILL.md`
- Verify it loads correctly
- Test with a scenario that previously failed

### 4. Iterate

- After first use, refine based on friction points
- Add edge cases discovered during use
- Remove sections that are not useful in practice

### 5. Retire (if needed)

- If the process is automated, the skill may no longer be needed
- If the process changes fundamentally, rewrite rather than patch
- Mark deprecated skills clearly

---

## Skill Quality Checklist

Before publishing a new skill:

- [ ] Name is unique and descriptive
- [ ] Description starts with "Use when"
- [ ] Core principle is stated in one sentence
- [ ] Process/rules are clear and actionable
- [ ] Red flags or anti-patterns are documented
- [ ] Length is between 30-150 lines
- [ ] No project-specific or language-specific references (unless intentional)
- [ ] Tested against the original failure scenario
- [ ] Does not duplicate an existing skill

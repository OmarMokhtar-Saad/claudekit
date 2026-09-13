# Incident Response -- on-call runbook patterns

Moved verbatim from SKILL.md.

## On-Call Runbook Patterns

### Runbook Structure

```
RUNBOOK: [Service/Component Name]

Symptoms:
  - [observable indicators that trigger this runbook]

Quick Checks:
  1. [first thing to verify]
  2. [second thing to verify]
  3. [third thing to verify]

Common Fixes:
  1. [most likely fix with exact commands]
  2. [second most likely fix]
  3. [third most likely fix]

Escalation:
  - If none of the above work, contact: [team/person]
  - Relevant dashboards: [links]
  - Relevant logs: [locations]
```

### Runbook Rules

- Write for someone woken up at 3 AM (clear, step-by-step, no assumptions)
- Include exact commands, not descriptions of commands
- Include expected output so the responder knows if it worked
- Keep runbooks under 1 page (link to detailed docs if needed)
- Review and update runbooks after every incident that uses them

---

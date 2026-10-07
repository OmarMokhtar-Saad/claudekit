# Incident Response -- postmortem rules and template

Moved verbatim from SKILL.md.

## Post-Mortem Rules

- **Blameless**: Focus on systems and processes, not individuals
- **Honest**: Do not downplay the impact or skip uncomfortable truths
- **Actionable**: Every lesson learned produces a concrete action item with an owner
- **Timely**: Complete within 5 business days of incident resolution
- **Shared**: Publish to the team so everyone learns from the incident

## Postmortem Template

```markdown
# Postmortem: <Incident Title>

**Date**: <incident date>
**Severity**: SEV-<X>
**Duration**: <total time from detection to resolution>
**Authors**: <postmortem authors>

## Summary

<2-3 sentence summary of what happened, the impact, and how it was resolved>

## Timeline (all times in UTC)

| Time | Event |
|------|-------|
| HH:MM | <First symptom detected> |
| HH:MM | <Incident declared> |
| HH:MM | <Root cause identified> |
| HH:MM | <Mitigation applied> |
| HH:MM | <Incident resolved> |

## Impact

- **Duration**: <time users were affected>
- **Users affected**: <number or percentage>
- **Revenue impact**: <if applicable>
- **Data impact**: <any data loss or corruption>
- **SLA impact**: <any SLA breaches>

## Root Cause

<Detailed technical explanation of what caused the incident>

## Detection

<How was the incident detected? Monitoring, user report, manual check?>
<Could it have been detected earlier? How?>

## Mitigation

<What was done to reduce the immediate impact?>
<How effective was the mitigation?>

## Resolution

<What was the permanent fix?>
<How was it validated?>

## Lessons Learned

### What went well

- <thing that went well>
- <thing that went well>

### What went wrong

- <thing that went wrong>
- <thing that went wrong>

### Where we got lucky

- <thing that could have been worse>

## Action Items

| Action | Owner | Priority | Due Date |
|--------|-------|----------|----------|
| <action item> | <owner> | P1/P2/P3 | <date> |
| <action item> | <owner> | P1/P2/P3 | <date> |
| <action item> | <owner> | P1/P2/P3 | <date> |

## References

- <link to incident channel>
- <link to relevant dashboards>
- <link to related PRs/commits>
```

---

---
name: incident-response
description: "Use when handling production incidents - triage process, war room coordination, post-mortem writing"
user-invocable: false
---

# Incident Response

## Core Principle

**Speed of detection and clarity of communication determine incident outcomes.** A well-coordinated response with clear roles resolves incidents faster than heroic individual effort.

---

## Severity Classification

| Severity | Definition | Response Time | Examples |
|---|---|---|---|
| **SEV1** | Service down, all users affected | Immediate (< 15 min) | Total outage, data breach, data loss |
| **SEV2** | Major feature broken, many users affected | < 30 min | Payment processing down, auth failures |
| **SEV3** | Minor feature broken, some users affected | < 2 hours | Search degraded, slow page loads |
| **SEV4** | Cosmetic or low-impact issue | Next business day | UI glitch, minor logging error |

---

## Triage Process

### Step 1: Detect and Classify

```
1. Confirm the issue is real (not a false alarm)
2. Determine severity based on user impact
3. Identify the affected system(s)
4. Check: Is this a known issue with an existing workaround?
```

### Step 2: Communicate

- **SEV1/SEV2**: Declare incident immediately, notify on-call and stakeholders
- **SEV3**: Open incident ticket, notify team lead
- **SEV4**: Open bug ticket, triage in next planning session

### Step 3: Assign Roles

| Role | Responsibility |
|---|---|
| **Incident Commander (IC)** | Coordinates response, makes decisions, manages communication |
| **Technical Lead** | Investigates root cause, directs debugging |
| **Communications Lead** | Updates status page, notifies stakeholders |
| **Scribe** | Documents timeline, actions taken, decisions made |

---

## War Room Coordination

### Rules of Engagement

- One person talks at a time (IC moderates)
- All actions are announced before execution
- No changes to production without IC approval
- Status updates every 15 minutes (SEV1) or 30 minutes (SEV2)
- Keep the communication channel focused (no side conversations)

### Communication Template

```
INCIDENT UPDATE - [timestamp]
Severity: SEV[X]
Status: Investigating / Identified / Monitoring / Resolved
Impact: [who is affected and how]
Current Action: [what is being done right now]
Next Update: [when to expect the next update]
```

### Escalation Triggers

| Condition | Action |
|---|---|
| No progress after 30 minutes | Escalate to senior engineer |
| SEV1 not resolved after 1 hour | Escalate to engineering leadership |
| Customer data at risk | Notify security team and legal |
| Third-party dependency failure | Contact vendor support |

---

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

## Post-Mortem Writing

### Post-Mortem Template

```
## Post-Mortem: [Incident Title]

### Summary
- **Date**: [date]
- **Duration**: [start time] to [end time] ([total duration])
- **Severity**: SEV[X]
- **Impact**: [number of users affected, revenue impact if applicable]

### Timeline
| Time | Event |
|---|---|
| HH:MM | [what happened] |
| HH:MM | [what happened] |

### Root Cause
[Clear explanation of what caused the incident]

### Contributing Factors
- [factor that made the incident worse or more likely]

### What Went Well
- [things the team did right during response]

### What Went Poorly
- [things that slowed resolution or made impact worse]

### Action Items
| Action | Owner | Priority | Due Date |
|---|---|---|---|
| [specific action] | [person] | P1/P2/P3 | [date] |
```

### Post-Mortem Rules

- **Blameless**: Focus on systems and processes, not individuals
- **Honest**: Do not downplay the impact or skip uncomfortable truths
- **Actionable**: Every lesson learned produces a concrete action item with an owner
- **Timely**: Complete within 5 business days of incident resolution
- **Shared**: Publish to the team so everyone learns from the incident

---

## Incident Response Checklist

- [ ] Incident detected and severity classified
- [ ] Roles assigned (IC, Technical Lead, Comms, Scribe)
- [ ] Status page updated (if customer-facing)
- [ ] Communication channel established
- [ ] Regular status updates being sent
- [ ] Root cause identified
- [ ] Fix applied and verified
- [ ] Monitoring confirms resolution
- [ ] Post-mortem scheduled
- [ ] Action items tracked and assigned

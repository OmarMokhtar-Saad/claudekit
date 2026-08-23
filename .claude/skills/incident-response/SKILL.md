---
name: incident-response
description: "Use when handling production incidents - triage process, war room coordination, post-mortem writing"
user-invocable: false
---

# Incident Response

## Purpose

Provide a structured framework for handling production incidents from initial detection through postmortem. Defines severity levels, communication protocols, investigation procedures, rollback strategies, and postmortem templates.

---

## Incident Phases

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
│  DETECT  │ -> │  TRIAGE  │ -> │ INVESTIGATE  │ -> │ MITIGATE │ -> │ RESOLVE  │ -> │ POSTMORTEM │
└──────────┘    └──────────┘    └──────────────┘    └──────────┘    └──────────┘    └────────────┘
```

### Phase 1: Detect

**Goal**: Confirm the incident is real and capture initial data.

Steps:
1. Verify the report: Is this a real incident or a false alarm?
2. Identify symptoms: What is the user-visible impact?
3. Check monitoring dashboards: Error rates, latency, availability
4. Check recent deployments: Was anything deployed in the last 24 hours?
5. Capture initial evidence: screenshots, error messages, log excerpts

**Output**: Incident declaration with initial symptom description.

### Phase 2: Triage

**Goal**: Classify severity and assemble the response team.

Steps:
1. Classify severity (see Severity Classification below)
2. Identify affected systems and services
3. Estimate user impact (percentage of users affected, revenue impact)
4. Assign incident commander (IC)
5. Open incident communication channel
6. Notify stakeholders based on severity level

**Output**: Severity classification, assigned IC, stakeholder notification sent.

### Phase 3: Investigate

**Goal**: Find the root cause.

Steps:
1. Form a hypothesis based on symptoms
2. Gather evidence:
   - Application logs (filter by timeframe around incident start)
   - Infrastructure metrics (CPU, memory, disk, network)
   - Database metrics (connections, query latency, deadlocks)
   - Deployment history (what changed recently?)
   - Dependency status (third-party service outages?)
3. Narrow the search:
   - Use binary search on timeline to find the inflection point
   - Compare healthy and unhealthy instances
   - Check for recent config changes
4. Confirm root cause with evidence
5. Document the investigation trail

**Output**: Confirmed root cause with supporting evidence.

### Phase 4: Mitigate

**Goal**: Stop the bleeding -- reduce user impact as quickly as possible.

Options (in order of preference):
1. **Feature flag**: Disable the broken feature
2. **Rollback**: Revert to the last known good deployment
3. **Hotfix**: Apply a minimal fix to production
4. **Scale**: Add capacity if the issue is load-related
5. **Redirect**: Route traffic away from the affected service
6. **Failover**: Switch to backup system or region

Mitigation rules:
- ALWAYS prefer rollback over hotfix when possible
- NEVER apply an untested hotfix to production
- ALWAYS monitor the mitigation to confirm it reduces impact
- Document the mitigation action and timestamp

**Output**: Impact reduced, mitigation confirmed effective.

### Phase 5: Resolve

**Goal**: Fully fix the underlying issue and confirm normal operation.

Steps:
1. Implement the permanent fix (may be the same as mitigation or a more thorough fix)
2. Test the fix in staging/pre-production
3. Deploy the fix to production with careful monitoring
4. Verify all symptoms have resolved
5. Monitor for recurrence (minimum 30 minutes for SEV-1/2)
6. Confirm with stakeholders that service is restored
7. Close the incident channel

**Output**: Incident resolved, normal operation confirmed.

### Phase 6: Postmortem

**Goal**: Learn from the incident and prevent recurrence.

Timeline:
- SEV-1: Postmortem within 24 hours
- SEV-2: Postmortem within 3 business days
- SEV-3: Postmortem within 1 week
- SEV-4: Optional, at team discretion

See Postmortem Template below.

---

## Severity Classification

### SEV-1: Critical

| Attribute | Criteria |
|-----------|----------|
| User impact | Complete service outage or data loss |
| Users affected | > 50% of users |
| Revenue impact | Direct revenue loss |
| Data impact | Data corruption or unauthorized access |
| Response time | Immediate (within 15 minutes) |
| Communication | All stakeholders notified immediately |
| Escalation | Engineering leadership + on-call + relevant team leads |

### SEV-2: High

| Attribute | Criteria |
|-----------|----------|
| User impact | Major feature unavailable or severely degraded |
| Users affected | 10-50% of users |
| Revenue impact | Indirect revenue impact |
| Data impact | Risk of data inconsistency |
| Response time | Within 30 minutes |
| Communication | Engineering team + product management |
| Escalation | On-call + relevant team lead |

### SEV-3: Medium

| Attribute | Criteria |
|-----------|----------|
| User impact | Minor feature degraded, workaround available |
| Users affected | < 10% of users |
| Revenue impact | Minimal |
| Data impact | No data risk |
| Response time | Within 2 hours |
| Communication | Engineering team |
| Escalation | Relevant team |

### SEV-4: Low

| Attribute | Criteria |
|-----------|----------|
| User impact | Cosmetic issue or minor inconvenience |
| Users affected | Few individual reports |
| Revenue impact | None |
| Data impact | None |
| Response time | Next business day |
| Communication | Ticket created |
| Escalation | Normal sprint workflow |

---

## Communication Templates

### Incident Declaration

```
INCIDENT DECLARED: [SEV-X] <title>

Impact: <user-visible impact description>
Affected: <systems/services affected>
Started: <timestamp or "investigating">
Status: Investigating
IC: <incident commander name>
Channel: <incident channel link>

Next update in: <15min for SEV-1, 30min for SEV-2, 1hr for SEV-3>
```

### Status Update

```
UPDATE: [SEV-X] <title>

Status: <Investigating | Identified | Mitigating | Monitoring | Resolved>
Root cause: <if identified, otherwise "Under investigation">
Mitigation: <action taken or planned>
ETA to resolution: <estimate>
User impact: <current impact level>

Next update in: <timeframe>
```

### Resolution Notice

```
RESOLVED: [SEV-X] <title>

Duration: <total incident duration>
Root cause: <brief summary>
Resolution: <what fixed it>
Impact: <summary of user impact during incident>
Postmortem: <scheduled date>

All systems are operating normally.
```

---

## Rollback Procedures

### Application Rollback

```bash
# 1. Identify the last known good version
git log --oneline -10

# 2. Verify the target version in staging
git checkout <good-version-tag>
# Run smoke tests

# 3. Deploy the rollback
# (Use your deployment tool -- examples:)
# Kubernetes: kubectl rollout undo deployment/<name>
# AWS ECS: aws ecs update-service --force-new-deployment
# Heroku: heroku releases:rollback v<N>

# 4. Verify rollback
# Check health endpoints, error rates, key metrics

# 5. Document
echo "Rolled back from <bad-version> to <good-version> at $(date -u)"
```

### Database Rollback

1. NEVER rollback database migrations blindly in production
2. Check if the migration is backward-compatible
3. If backward-compatible: leave the migration, rollback the application
4. If not backward-compatible: apply a compensating migration (forward-fix)
5. ALWAYS have a tested rollback script for every migration before deploying

### Configuration Rollback

1. Revert the config change in the config management system
2. Verify the previous config values are correct
3. Apply the config change (may require service restart)
4. Monitor for restoration of normal behavior

---

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

## Integration

- **debugger** agent is invoked during the Investigation phase for root cause analysis
- **git** agent handles rollback operations and identifying recent changes
- **security scanner** is invoked if the incident involves security concerns
- **coordinator** manages the multi-agent workflow during incident response
- **session-continuity** preserves incident investigation context across sessions

<!-- Sections below were unique to the .claude/skills/ copy of this skill. Until
2026-08-23 install.sh copied templates/skills LAST into the same destination, so the
body above is what every install has actually shipped since April and the sections
below shipped nowhere. The copy-order fix makes .claude/skills/ authoritative, so they
are unioned in here rather than lost: the body above carries the phases, severities,
comms templates and rollback procedures; these carry the coordination and on-call
material that had no equivalent there. -->

## Response Roles

| Role | Responsibility |
|---|---|
| **Incident Commander (IC)** | Coordinates response, makes decisions, manages communication |
| **Technical Lead** | Investigates root cause, directs debugging |
| **Communications Lead** | Updates status page, notifies stakeholders |
| **Scribe** | Documents timeline, actions taken, decisions made |

## War Room Coordination

### Rules of Engagement

- One person talks at a time (IC moderates)
- All actions are announced before execution
- No changes to production without IC approval
- Status updates every 15 minutes (SEV-1) or 30 minutes (SEV-2)
- Keep the communication channel focused (no side conversations)

### Update Cadence

Use the `### Status Update` template above — it is the one status format this
skill defines. The war room adds only the cadence: post an update at the interval
`### Incident Declaration` sets (15min SEV-1, 30min SEV-2, 1hr SEV-3), even when there is nothing new to report, and say so
explicitly rather than going quiet.

### Escalation Triggers

| Condition | Action |
|---|---|
| No progress after 30 minutes | Escalate to senior engineer |
| SEV-2 not resolved after 1 hour | Escalate to engineering leadership |
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

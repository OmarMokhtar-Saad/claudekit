# Incident Response -- communication, roles and war room

Moved verbatim from SKILL.md.

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

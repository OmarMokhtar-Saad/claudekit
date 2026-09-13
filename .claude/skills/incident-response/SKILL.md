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

DETECT -> TRIAGE -> INVESTIGATE -> MITIGATE -> RESOLVE -> POSTMORTEM

| Phase | Goal | Output |
|---|---|---|
| Detect | Confirm the incident is real and capture initial data | Incident declaration with initial symptom description |
| Triage | Classify severity and assemble the response team | Severity, assigned IC, stakeholders notified |
| Investigate | Find the root cause | Confirmed root cause with supporting evidence |
| Mitigate | Stop the bleeding -- reduce user impact as quickly as possible | Impact reduced, mitigation confirmed effective |
| Resolve | Fully fix the underlying issue and confirm normal operation | Incident resolved, normal operation confirmed |
| Postmortem | Learn from the incident and prevent recurrence | Postmortem with owned action items |

Read [references/phases.md](references/phases.md) when you work a phase -- the step lists for every phase.

### Mitigation (in order of preference)

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

Monitor for recurrence after the fix (minimum 30 minutes for SEV-1/2).

## Severity at a glance

| SEV | User impact | Users affected | Respond within | Updates every |
|---|---|---|---|---|
| 1 Critical | Complete outage or data loss | > 50% | 15 minutes | 15min |
| 2 High | Major feature unavailable or severely degraded | 10-50% | 30 minutes | 30min |
| 3 Medium | Minor feature degraded, workaround available | < 10% | 2 hours | 1hr |
| 4 Low | Cosmetic issue or minor inconvenience | Few individual reports | Next business day | -- (ticket created) |

Read [references/severity.md](references/severity.md) when you classify an incident -- full criteria (revenue, data, communication, escalation) per level.

### Postmortem timeline

- SEV-1: Postmortem within 24 hours
- SEV-2: Postmortem within 3 business days
- SEV-3: Postmortem within 1 week
- SEV-4: Optional, at team discretion

### Database rollback

1. NEVER rollback database migrations blindly in production
2. Check if the migration is backward-compatible
3. If backward-compatible: leave the migration, rollback the application
4. If not backward-compatible: apply a compensating migration (forward-fix)
5. ALWAYS have a tested rollback script for every migration before deploying

## Post-Mortem Rules

- **Blameless**: Focus on systems and processes, not individuals
- **Honest**: Do not downplay the impact or skip uncomfortable truths
- **Actionable**: Every lesson learned produces a concrete action item with an owner
- **Timely**: Complete within 5 business days of incident resolution
- **Shared**: Publish to the team so everyone learns from the incident

## War Room

- One person talks at a time (IC moderates)
- All actions are announced before execution
- No changes to production without IC approval
- Status updates every 15 minutes (SEV-1) or 30 minutes (SEV-2)
- Keep the communication channel focused (no side conversations)

| Condition | Action |
|---|---|
| No progress after 30 minutes | Escalate to senior engineer |
| SEV-2 not resolved after 1 hour | Escalate to engineering leadership |
| Customer data at risk | Notify security team and legal |
| Third-party dependency failure | Contact vendor support |

## References

Read [references/communication.md](references/communication.md) when you post a declaration, status update or resolution notice, or staff the response roles and war-room cadence.
Read [references/rollback.md](references/rollback.md) when you roll back an application, database or configuration.
Read [references/postmortem.md](references/postmortem.md) when you write the postmortem -- the full template.
Read [references/runbooks.md](references/runbooks.md) when you write or use an on-call runbook.

## Integration

- **debugger** agent is invoked during the Investigation phase for root cause analysis
- **git** agent handles rollback operations and identifying recent changes
- **security scanner** is invoked if the incident involves security concerns
- **coordinator** manages the multi-agent workflow during incident response
- **context-keeper** preserves incident investigation context across sessions


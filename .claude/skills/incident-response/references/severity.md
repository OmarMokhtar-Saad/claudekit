# Incident Response -- severity classification

Moved verbatim from SKILL.md.

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
